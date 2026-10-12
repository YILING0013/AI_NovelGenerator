"""一次保存作者采用的人物或关系，内部复用原事实确认与必需事务。"""

from hashlib import sha256

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint
from backend.services.llm.character_generation_contract import (
    build_core_character_source_refs, build_character_relation_source_refs,
)
from backend.services.novel.character_fact_batch_contract import (
    CharacterFactBatchCreateV1, CharacterFactBatchResultV1,
    CharacterRelationFactBatchCreateV1, CharacterRelationFactBatchResultV1,
)
from backend.services.novel.chapter_record_source import protect_chapter_record_sources
from backend.services.novel import character_fact_service, character_relation_fact_service
from backend.services.novel.character_faction_binding_service import CharacterFactionBindingService
from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint


async def _validate_generation(novel_id, generation, *, relation, session):
    """在同一事务重读生成时的完整集合，包含空集合查询及工具读取。"""
    if generation is None:
        return
    from backend.services.task_flows.registry import TASKS
    from backend.services.task_flows.book_tools import replay_book_reads
    from backend.services.novel.writing_context import revalidate_position_fact_reads

    task = "create_character_relations_by_ai" if relation else "create_characters_by_ai"
    basis, inputs = generation.basis, generation.generation_input
    spec = TASKS[task]
    if (basis.novel_id != novel_id or inputs.novel_id != novel_id or basis.workflow != task
            or basis.step != spec.step or basis.schema_id != spec.schema_id or basis.schema_version != spec.schema_version):
        raise DomainApiError("CHARACTER_BATCH_SOURCE_CHANGED", "这批结果不属于当前作品或操作", status_code=409)
    novel = await BaseRepository("novels").collection.find_one({"_id": ObjectId(novel_id), "is_deleted": False}, session=session)
    if novel is None:
        raise DomainApiError("NOVEL_NOT_FOUND", "作品不存在或已回收", status_code=404)
    query = {"novel_id": ObjectId(novel_id), "is_deleted": False}
    characters = await BaseRepository("characters").collection.find(
        {**query, **({"character_id": {"$in": inputs.character_ids}} if relation else {})}, session=session,
    ).to_list(length=None)
    sources = [("novels", novel), *(("characters", row) for row in characters)]
    if relation:
        bindings = await BaseRepository("character_faction_bindings").collection.find(
            {**query, "is_active": True, "character_id": {"$in": inputs.character_ids}}, session=session,
        ).to_list(length=None)
        relations = await BaseRepository("character_relations").collection.find({
            **query, "is_active": True, "source_character_id": {"$in": inputs.character_ids},
            "target_character_id": {"$in": inputs.character_ids},
        }, session=session).to_list(length=None)
        refs = build_character_relation_source_refs(novel, characters, bindings, relations)
        sources.extend(("character_faction_bindings", row) for row in bindings)
        sources.extend(("character_relations", row) for row in relations)
    else:
        factions = await BaseRepository("factions").collection.find(
            {**query, "level_type": "core", "active_status": "active"}, session=session,
        ).to_list(length=None)
        refs = build_core_character_source_refs(novel, factions, characters)
        sources.extend(("factions", row) for row in factions)
    try:
        fingerprint = compute_flow_candidate_fingerprint(task, inputs, refs, basis.flow_snapshot)
    except (KeyError, ValueError) as exc:
        raise DomainApiError("CHARACTER_BATCH_SOURCE_CHANGED", "生成所用方案已变化，请保留这批编辑内容", status_code=409) from exc
    ordered_refs = lambda rows: sorted((row.resource_type, row.id, row.version) for row in rows)
    if fingerprint != basis.input_fingerprint or ordered_refs(refs) != ordered_refs(basis.source_refs):
        raise DomainApiError("CHARACTER_BATCH_SOURCE_CHANGED", "生成所用资料已变化，请保留这批编辑内容", status_code=409)
    execution = basis.flow_snapshot["execution"]
    reads = [*execution.get("character_fact_reads", []), *execution.get("character_relation_fact_reads", []), *execution.get("item_fact_reads", [])]
    await revalidate_position_fact_reads(reads, session=session, protect=True)
    if execution.get("agent_reads"):
        await replay_book_reads(basis.flow_snapshot["scope"], execution["agent_reads"], session=session, protect=True)
    await protect_chapter_record_sources({(name, str(row["_id"])): row for name, row in sources}, session=session)


async def _save_batch(novel_id, request, *, idempotency_key, relation, session):
    """两种整批新建共用原请求回执和事务边界，不开放任意写入编排。"""
    novel_id = str(ObjectId(novel_id))
    operation = "create_relations" if relation else "create_characters"
    original = request.model_dump(mode="json")
    fingerprint = build_idempotency_fingerprint(idempotency_key, {
        "operation": operation, "novel_id": novel_id, "data": original,
    })
    # 固定物理键让同键竞争受 Mongo 自身唯一约束保护，不依赖启动时是否已补索引。
    receipt_id = ObjectId(sha256(f"{novel_id}:{operation}:{fingerprint.key_hash}".encode()).hexdigest()[:24])
    result_model = CharacterRelationFactBatchResultV1 if relation else CharacterFactBatchResultV1

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("整批人物或关系保存必须使用同一事务")
        receipts = BaseRepository("character_creation_batch_receipts").collection
        receipt = await receipts.find_one({"_id": receipt_id}, session=current_session)
        if receipt is not None:
            if receipt["request_hash"] != fingerprint.request_hash or receipt["idempotency_key_hash"] != fingerprint.key_hash:
                raise DomainApiError("CHARACTER_BATCH_IDEMPOTENCY_CONFLICT", "这次保存请求已用于其他内容，请保留原请求", status_code=409)
            return result_model.model_validate(receipt["result"]).model_dump(mode="json")
        await _validate_generation(novel_id, request.generation, relation=relation, session=current_session)
        saved_rows, saved_bindings = [], []
        for candidate in request.candidates:
            facts = candidate.facts.model_dump(mode="json")
            data = {"operation": "create", "target": {"candidate": candidate.profile.model_dump(mode="json")},
                    "position": request.position.model_dump(mode="json"),
                    "source": {"kind": "author", "note": "作者采用这批人物关系初始资料" if relation else "作者采用这批人物初始资料"},
                    "fields": sorted(facts)}
            if not relation:
                guards = {}
                for binding in candidate.bindings:
                    faction = await BaseRepository("factions").collection.find_one({
                        "novel_id": ObjectId(novel_id), "faction_id": binding.faction_id,
                        "version": binding.faction_version, "is_deleted": False, "active_status": "active",
                    }, session=current_session)
                    if faction is None:
                        raise DomainApiError("CHARACTER_BATCH_BINDING_CHANGED", "人物所属势力已变化，请保留这批编辑内容", status_code=409)
                    guards["factions", str(faction["_id"])] = faction
                await protect_chapter_record_sources(guards, session=current_session)
                data["references"] = [{"entity_type": "faction", "entity_id": identity} for identity in dict.fromkeys(row.faction_id for row in candidate.bindings)]
            service = character_relation_fact_service if relation else character_fact_service
            preview = await (service.preview_character_relation_facts if relation else service.preview_character_facts)(
                novel_id, data, session=current_session,
            )
            command = {"operation": "create", "basis": preview["basis"], "after": facts, "confirmed": True}
            saved = await (service.confirm_character_relation_facts if relation else service.confirm_character_facts)(
                novel_id, command, idempotency_key=f"batch:{fingerprint.key_hash}:{len(saved_rows)}", session=current_session,
            )
            identity = "relation_id" if relation else "character_id"
            saved_rows.append({"candidate_ref": candidate.candidate_ref, "entity_id": saved["entity_id"],
                               identity: saved[identity], "version": saved["after_version"], "history_id": saved["record"]["history_id"]})
            if not relation and candidate.bindings:
                bindings = await CharacterFactionBindingService.bulk_create_bindings(novel_id, [
                    {**row.model_dump(exclude={"faction_version"}), "character_id": saved["character_id"]}
                    for row in candidate.bindings
                ], session=current_session)
                saved_bindings.extend({"candidate_ref": candidate.candidate_ref, "binding_id": row["binding_id"], "version": row["version"]} for row in bindings)
        result = result_model.model_validate({"novel_id": novel_id,
            **({"relations": saved_rows} if relation else {"characters": saved_rows, "bindings": saved_bindings}),
        }).model_dump(mode="json")
        await receipts.insert_one({"_id": receipt_id, "novel_id": ObjectId(novel_id), "operation": operation,
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
            "request": original, "result": result, "created_at": get_utc_now()}, session=current_session)
        return result

    if session is not None:
        return await save(session)
    try:
        return await run_mongo_write_unit(save, operation, require_transaction=True)
    except OperationFailure as exc:
        # 原事务层不自动重跑业务。暂时争用继续保留原请求，不把它误标成可改稿的新请求。
        if exc.code == 112 and exc.has_error_label("TransientTransactionError") and not exc.has_error_label("UnknownTransactionCommitResult"):
            raise DomainApiError("CHARACTER_BATCH_SAVE_RETRY", "另一处也在保存，请重试这批保存；已填写的内容会保留", status_code=503) from exc
        raise


async def create_character_fact_batch(
    novel_id: str, data: CharacterFactBatchCreateV1 | dict, *, idempotency_key: str,
    session: AsyncClientSession | None = None,
) -> dict:
    """一次保存人物、初始资料及势力归属；任何失败整批回滚。

    Args:
        novel_id: 当前作品。
        data: 每人的实际字段、共同起点、归属及可选原生成依据。
        idempotency_key: 首次派发保留的原键；重试必须保持原请求。
        session: 可选调用方已开启的事务，不另开事务。
    Returns:
        CharacterFactBatchResultV1 的 JSON；重试优先返回原成功结果。
    """
    return await _save_batch(novel_id, CharacterFactBatchCreateV1.model_validate(data),
                             idempotency_key=idempotency_key, relation=False, session=session)


async def create_character_relation_fact_batch(
    novel_id: str, data: CharacterRelationFactBatchCreateV1 | dict, *, idempotency_key: str,
    session: AsyncClientSession | None = None,
) -> dict:
    """一次保存整批关系及各自初始状态，不覆盖已有关系。

    Args:
        novel_id: 当前作品。
        data: 关系候选、共同起点及可选原生成依据。
        idempotency_key: 首次派发保留的原键。
        session: 可选调用方已开启的事务。
    Returns:
        CharacterRelationFactBatchResultV1 的 JSON；成功重试不重新核对今天的资料。
    """
    return await _save_batch(novel_id, CharacterRelationFactBatchCreateV1.model_validate(data),
                             idempotency_key=idempotency_key, relation=True, session=session)
