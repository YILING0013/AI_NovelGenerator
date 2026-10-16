"""势力整批采用必须原子保存，回放只读取首次冻结的完整结果。"""

from hashlib import sha256
import json

from bson import ObjectId
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.db.base import BaseRepository
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint
from backend.llm.schemas.faction_relation_pydantic import FactionRelationResponseV1
from backend.services.llm.faction_generation_contract import build_core_factions_source_refs, compute_core_factions_input_fingerprint
from backend.services.novel.chapter_record_source import protect_chapter_record_sources
from backend.services.novel.faction_fact_batch_contract import FactionFactBatchCreateV1, FactionFactBatchResultV1
from backend.services.novel import faction_fact_service
from backend.services.novel.faction_relation_service import FactionRelationService
from backend.services.novel.faction_service import FactionService


async def _validate_generation(novel_id, generation, *, session):
    """复验原生成输入、完整势力和关系集合、事实读取及工具来源。"""
    if generation is None:
        return None
    from backend.services.novel.writing_context import revalidate_position_fact_reads
    from backend.services.task_flows.book_tools import replay_book_reads

    basis, inputs = generation.basis, generation.generation_input
    if (basis.novel_id != novel_id or inputs.novel_id != novel_id
            or basis.workflow != "create_factions_by_ai" or basis.step != "create_core_factions"
            or basis.schema_id != "faction.core_generation.result" or basis.schema_version != 2):
        raise DomainApiError("FACTION_BATCH_SOURCE_CHANGED", "这批结果不属于当前作品或操作", status_code=409)
    novel = await BaseRepository("novels").collection.find_one({"_id": ObjectId(novel_id), "is_deleted": False}, session=session)
    if novel is None:
        raise DomainApiError("NOVEL_NOT_FOUND", "作品不存在或已回收", status_code=404)
    query = {"novel_id": ObjectId(novel_id), "is_deleted": False}
    factions = await BaseRepository("factions").collection.find(
        {**query, "level_type": "core", "active_status": "active"}, session=session,
    ).to_list(length=None)
    faction_ids = {row["faction_id"] for row in factions}
    relations = await BaseRepository("faction_relations").collection.find({
        **query, "is_active": True, "source_faction_id": {"$in": sorted(faction_ids)},
        "target_faction_id": {"$in": sorted(faction_ids)},
    }, session=session).to_list(length=None)
    refs = build_core_factions_source_refs(novel, factions, relations)
    try:
        fingerprint = compute_core_factions_input_fingerprint(inputs.model_dump(mode="json"), refs, flow_snapshot=basis.flow_snapshot)
    except (KeyError, ValueError) as exc:
        raise DomainApiError("FACTION_BATCH_SOURCE_CHANGED", "生成所用方案已变化，请保留这批编辑内容", status_code=409) from exc
    ordered = lambda rows: sorted((row.resource_type, row.id, row.version) for row in rows)
    if fingerprint != basis.input_fingerprint or ordered(refs) != ordered(basis.source_refs):
        raise DomainApiError("FACTION_BATCH_SOURCE_CHANGED", "生成所用资料已变化，请保留这批编辑内容", status_code=409)
    execution = basis.flow_snapshot["execution"]
    # 核心势力生成沿用已发布的未定位设计合同；作者在采用时才明确新势力起点。
    # 不能要求本来没有执行的位置读取，也不能把旧裸候选补签为当前合同。
    if execution.get("faction_design_contract") != "unlocated_faction_profile_v1" or not isinstance(execution.get("faction_fact_reads"), list):
        raise DomainApiError("FACTION_FACT_CONTRACT_REQUIRED", "原候选缺少完整设计资料依据，请保留候选并重新生成", status_code=409)
    reads = [read for name in ("character_fact_reads", "character_relation_fact_reads", "item_fact_reads", "faction_fact_reads") for read in execution.get(name, [])]
    await revalidate_position_fact_reads(reads, session=session, protect=True)
    if execution.get("agent_reads"):
        await replay_book_reads(basis.flow_snapshot["scope"], execution["agent_reads"], session=session, protect=True)
    sources = [("novels", novel), *(("factions", row) for row in factions), *(("faction_relations", row) for row in relations)]
    await protect_chapter_record_sources({(name, str(row["_id"])): row for name, row in sources}, session=session)
    return faction_ids


async def create_faction_fact_batch(novel_id: str, data, *, idempotency_key: str, session=None) -> dict:
    """同一事务保存全部档案、事实、关系和原请求回执。

    Args:
        novel_id: 当前作品。
        data: 明确位置、实际采用内容及可选原生成依据。
        idempotency_key: 首次派发的原键，未知响应重试不能替换。
        session: 可选调用方已开启的事务。
    Returns:
        首次完整公开结果；来源或实体后来改变不影响同请求回放。
    """
    request = FactionFactBatchCreateV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))
    original = request.model_dump(mode="json")
    fingerprint = build_idempotency_fingerprint(idempotency_key, {"operation": "create_factions", "novel_id": novel_id, "data": original})
    receipt_id = ObjectId(sha256(f"{novel_id}:create_factions:{fingerprint.key_hash}".encode()).hexdigest()[:24])

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("势力整批采用必须使用同一事务")
        receipts = BaseRepository("faction_creation_batch_receipts").collection
        receipt = await receipts.find_one({"_id": receipt_id}, session=current_session)
        if receipt is not None:
            if receipt["request_hash"] != fingerprint.request_hash or receipt["idempotency_key_hash"] != fingerprint.key_hash:
                raise DomainApiError("FACTION_BATCH_IDEMPOTENCY_CONFLICT", "这次保存请求已用于其他内容，请保留原请求", status_code=409)
            return FactionFactBatchResultV1.model_validate_json(json.dumps(receipt["result"], ensure_ascii=False)).model_dump(mode="json")
        existing_ids = await _validate_generation(novel_id, request.generation, session=current_session)
        if existing_ids is None:
            existing_ids = {endpoint.faction_id for row in request.relations for endpoint in (row.source, row.target) if endpoint.kind == "existing"}
        faction_rows, faction_map = [], {}
        for index, candidate in enumerate(request.candidates):
            facts = candidate.facts.model_dump(mode="json")
            preview = await faction_fact_service.preview_faction_facts(novel_id, {
                "operation": "create", "target": {"candidate": candidate.profile.model_dump(mode="json")},
                "position": request.position.model_dump(mode="json"),
                "source": {"kind": "author", "note": "作者采用这批势力在此处的资料"}, "fields": sorted(facts),
            }, session=current_session)
            saved = await faction_fact_service.confirm_faction_facts(novel_id, {
                "operation": "create", "basis": preview["basis"], "after": facts, "confirmed": True,
            }, idempotency_key=f"faction-batch:{fingerprint.key_hash}:{index}", session=current_session)
            faction_rows.append({"candidate_ref": candidate.candidate_ref, "result": saved})
            faction_map[candidate.candidate_ref] = saved["faction_id"]
        payloads = [FactionService._normalize_generated_relation(row.model_dump(mode="json"),
            faction_ref_map=faction_map, existing_faction_ids=existing_ids) for row in request.relations]
        relations = await FactionRelationService.bulk_create_relations(novel_id, payloads, session=current_session)
        relation_rows = [{"relation_ref": requested.relation_ref,
            "result": FactionRelationResponseV1.model_validate_json(json.dumps(sanitize_json_value({
                name: value for name, value in saved.items() if name in FactionRelationResponseV1.model_fields
            }), ensure_ascii=False)).model_dump(mode="json")} for requested, saved in zip(request.relations, relations, strict=True)]
        result = FactionFactBatchResultV1.model_validate_json(json.dumps({
            "novel_id": novel_id, "factions": faction_rows, "relations": relation_rows,
            "faction_ref_map": faction_map,
            "relation_ref_map": {row["relation_ref"]: row["result"]["relation_id"] for row in relation_rows},
        }, ensure_ascii=False)).model_dump(mode="json")
        await receipts.insert_one({"_id": receipt_id, "novel_id": ObjectId(novel_id), "operation": "create_factions",
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
            "request": original, "result": result, "created_at": get_utc_now()}, session=current_session)
        return result

    if session is not None:
        return await save(session)
    try:
        return await run_mongo_write_unit(save, "create_faction_fact_batch", require_transaction=True)
    except OperationFailure as exc:
        if exc.code == 112 and exc.has_error_label("TransientTransactionError") and not exc.has_error_label("UnknownTransactionCommitResult"):
            raise DomainApiError("FACTION_BATCH_SAVE_RETRY", "另一处也在保存，请重试这批保存；已填写的内容会保留", status_code=503) from exc
        raise
