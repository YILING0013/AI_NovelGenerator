"""读取单卷资料并在同一事务中确认实体档案及卷参与状态。"""

from __future__ import annotations

import json
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.db.errors import DuplicateKeyError, NotFoundError, TransactionNotSupportedError
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.character_relation_repository import character_relation_repo
from backend.db.repositories.character_volume_state_repository import character_volume_state_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.faction_volume_state_repository import faction_volume_state_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.repositories.volume_command_receipt_repository import volume_command_receipt_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, build_snapshot_version_filter, canonical_request_hash
from backend.llm.schemas.character_volume_state_pydantic import CharacterVolumeStateReadV1
from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumeStateReadV1
from backend.llm.schemas.volume_entity_pydantic import (
    VOLUME_ENTITY_TASKS, VolumeEntityGenerationInputV1,
    VolumeCharactersResultV1, VolumeFactionsResultV1,
    VolumeCharactersConfirmedV1, VolumeFactionsConfirmedV1,
    VolumeCharactersPlanConfirmV1, VolumeCharactersPlanResultV1,
)
from backend.services.llm.candidate_contract import CandidateSourceRefV1, MAX_CANDIDATE_SOURCE_REFS
from backend.services.novel.writing_context import (
    character_position_content, character_relation_position_content, position_content,
    read_character_relation_context, resolve_writing_position,
)
from backend.services.novel.character_service import CharacterService, normalize_character_name
from backend.services.novel.character_volume_state_service import CharacterVolumeStateService
from backend.services.novel.faction_service import FactionService
from backend.services.novel.faction_volume_state_service import FactionVolumeStateService


async def load_volume_entity_context(
    task: str, generation_input: VolumeEntityGenerationInputV1, *, session: AsyncClientSession | None = None,
    require_preparation: bool = True,
) -> dict[str, Any]:
    """读取目标卷开始前的设计资料，原始档案只用于候选校验。

    Args:
        task: 卷内人物或势力任务。
        generation_input: 路径范围、卷版本和作者选择。
        session: 确认时复用的事务。
        require_preparation: 编辑器预览可跳过尚未完成的剧情和准备步骤。
    Returns:
        原始来源、候选校验资料和可交给模型的公开内容。
    """
    kind = VOLUME_ENTITY_TASKS[task]
    novel_id, volume_id = generation_input.novel_id, generation_input.volume_id
    try:
        novel = await novel_repo.get_novel_by_id(novel_id, session=session)
        volume = await volume_repo.get_volume_by_id(volume_id, session=session)
    except NotFoundError as exc:
        raise DomainApiError("VOLUME_ENTITY_REFERENCE_UNAVAILABLE", "小说或当前卷不存在，请刷新后重试", status_code=404) from exc
    if volume["novel_id"] != to_object_id(novel_id):
        raise DomainApiError("VOLUME_ENTITY_VOLUME_NOT_FOUND", "当前卷不存在或不属于这部小说", status_code=404)
    if generation_input.selection_mode != "auto" and volume["version"] != generation_input.volume_expected_version:
        raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "当前卷已修改，请刷新后重新生成", status_code=409)
    if require_preparation and generation_input.selection_mode == "auto":
        from backend.services.novel.plot_service import require_preparation_stage
        await require_preparation_stage(novel_id, volume_id, kind, session=session)

    if kind == "characters":
        entity_repo, state_repo = character_repo, character_volume_state_repo
        entity_field, resource_type = "character_id", "character"
        entities = [item for item in await character_repo.get_characters_by_novel(novel_id, session=session) if item["status"] == "active"]
    else:
        entity_repo, state_repo = faction_repo, faction_volume_state_repo
        entity_field, resource_type = "faction_id", "faction"
        entities = [item for item in await faction_repo.get_factions_by_novel(novel_id, session=session) if item["active_status"] == "active" and (item["level_type"] == "core" or str(item["volume_id"]) == volume_id)]
    entities_by_id = {item[entity_field]: item for item in entities}
    if set(generation_input.selected_existing_ids) - entities_by_id.keys():
        raise DomainApiError("VOLUME_ENTITY_REFERENCE_UNAVAILABLE", "所选档案不存在、已停用或不属于当前卷可用范围", status_code=404)
    states = [item for item in await state_repo.list_by_volume(novel_id, volume_id, session=session) if item[entity_field] in entities_by_id]
    states_by_entity = {item[entity_field]: item for item in states}
    relations = []
    if kind == "characters":
        relations = [item for item in await character_relation_repo.list_relations(novel_id, session=session) if item.get("is_active") is True and {item["source_character_id"], item["target_character_id"]} <= entities_by_id.keys()]

    # 保存时写同一批来源，使读到资料后的并发修改触发事务冲突；空卷状态范围由父卷与小说争用保护。
    sources = [("novel", novel_id, novel_repo, novel), ("volume", volume_id, volume_repo, volume)]
    sources.extend((resource_type, item[entity_field], entity_repo, item) for item in entities)
    sources.extend((f"{resource_type}_volume_state", str(item["state_id"]), state_repo, item) for item in states)
    sources.extend(("character_relation", item["relation_id"], character_relation_repo, item) for item in relations)
    source_refs = sorted((CandidateSourceRefV1(resource_type=resource, id=identity, version=int(document["version"])) for resource, identity, _, document in sources), key=lambda ref: (ref.resource_type, ref.id))
    if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
        raise DomainApiError("VOLUME_ENTITY_CONTEXT_TOO_LARGE", "当前卷资料超过可读取范围，请减少资料后重试", status_code=422)
    position = resolve_writing_position(
        {"target_type": "volume", "target_id": volume_id, "reading_intent": "replan", "reading_version": 1},
        {"volume": {volume["_id"]: volume}},
    )
    fact_reads = []
    character_facts = {}
    relation_facts = {}
    if kind == "characters":
        from backend.services.novel.character_fact_service import read_character_facts
        facts = await read_character_facts(novel_id, sorted(entities_by_id), {
            "target_type": "volume", "target_id": volume_id,
            "reading_intent": "replan", "reading_version": 1,
        }, session=session)
        if facts["position"] != position:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
        fact_reads = facts["reads"]
        character_facts = {row["character_id"]: row for row in facts["characters"]}
        if entities_by_id.keys() != character_facts.keys():
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物在读取期间已变化，请重新读取", status_code=409)
        relation_facts, relation_reads, relation_position = await read_character_relation_context(
            novel_id, sorted(item["relation_id"] for item in relations), {
                "target_type": "volume", "target_id": volume_id,
                "reading_intent": "replan", "reading_version": 1,
            }, session=session,
        )
        if relation_position != position:
            raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
        fact_reads = [*fact_reads, *relation_reads]
    context = {
        "reading_semantics": "position",
        "position": position,
        "novel": position_content(novel, "novel"),
        "volume": {"volume_id": volume_id, "version": volume["version"], **position_content(volume, "volume"), "position": position},
        "new_count": generation_input.new_count,
        "selection_mode": generation_input.selection_mode,
        "selected_existing_ids": generation_input.selected_existing_ids,
        "user_guidance": generation_input.user_guidance,
        "existing_profiles": [{entity_field: item[entity_field], "version": item["version"],
            **(character_position_content(item, character_facts[item[entity_field]]) if kind == "characters" else position_content(item, resource_type))} for item in entities],
        "volume_states": [{"state_id": str(item["state_id"]), "version": item["version"], **position_content(item, f"{resource_type}_volume_state")} for item in states],
        "character_relations": [{"version": item["version"], **character_relation_position_content(item, relation_facts[item["relation_id"]])} for item in relations],
    }
    prompt_context = json.dumps(sanitize_json_value(context), ensure_ascii=False, sort_keys=True)
    if len(prompt_context) > 200000:
        raise DomainApiError("VOLUME_ENTITY_CONTEXT_TOO_LARGE", "当前卷资料过长，请减少资料后重试", status_code=422)
    data = {"generation_input": generation_input, "kind": kind, "sources": sources, "source_refs": source_refs, "entities": entities_by_id, "states": states_by_entity, "relations": {item["relation_id"]: item for item in relations}, "entity_context": prompt_context, "fact_reads": fact_reads}
    if require_preparation and generation_input.selection_mode == "auto":
        from backend.services.novel.plot_service import preparation_content_fingerprint
        data["content_fingerprint"] = canonical_request_hash({
            "reading_contract": "position_v1", "position": position,
            "source_content_fingerprint": preparation_content_fingerprint(
                [(resource, document) for resource, _, _, document in sources],
                character_facts=list(character_facts.values()), fact_reads=fact_reads,
            ),
        })
    return data


def validate_volume_entity_candidates(task: str, candidate: dict[str, Any], data: dict[str, Any], *, confirming: bool = False, plans: bool = False) -> dict[str, Any]:
    """验证候选数量、身份、卷归属及状态版本，审核允许删除部分候选。

    Args:
        task: 路由固定的卷内任务。
        candidate: 模型结果或审核后的候选集合。
        data: 本次重新读取的正式资料。
        confirming: 确认阶段允许减少候选，不允许增加原请求外的对象。
    Returns:
        可安全用于显示或确认的规范候选。
    """
    kind = VOLUME_ENTITY_TASKS[task]
    model = (VolumeCharactersPlanResultV1 if plans else VolumeCharactersResultV1) if kind == "characters" else VolumeFactionsResultV1
    result = model.model_validate(candidate).model_dump(mode="json")
    rows = result[kind]
    entity_field = "character_id" if kind == "characters" else "faction_id"
    inputs = data["generation_input"]
    if not rows and inputs.selection_mode != "auto":
        raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "请至少保留一个候选", status_code=422 if confirming else 502)
    status = 422 if confirming else 502
    refs, existing_ids, names = set(), set(), set()
    new_count = 0
    for row in rows:
        if row["candidate_ref"] in refs:
            raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "候选标识不能重复", status_code=status)
        refs.add(row["candidate_ref"])
        identity = row[entity_field]
        if identity is not None:
            if identity not in inputs.selected_existing_ids or identity in existing_ids:
                raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "候选包含未选择或重复的已有档案", status_code=status)
            existing_ids.add(identity)
            state = data["states"].get(identity)
            expected = state["version"] if state else None
            if row["state_expected_version"] != expected:
                raise DomainApiError("VOLUME_ENTITY_STATE_VERSION_CONFLICT", "卷状态版本不一致，请保留候选并重新生成", status_code=409 if confirming else 502)
        else:
            new_count += 1
            profile = row["profile"]
            if kind == "characters":
                name = normalize_character_name(profile["name"])[1]
                duplicate = any(normalize_character_name(item["name"])[1] == name for item in data["entities"].values())
            else:
                from backend.db.repositories.faction_repository import normalize_faction_name
                name = (profile["level_type"], normalize_faction_name(profile["name"])[1])
                duplicate = any(item.get("level_type") == profile["level_type"] and str(item.get("volume_id")) == inputs.volume_id and normalize_faction_name(item["name"])[1] == name[1] for item in data["entities"].values())
                if profile["volume_id"] not in (None, inputs.volume_id):
                    raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "新势力必须归属当前卷", status_code=status)
                if profile["parent_faction_id"] is not None and profile["parent_faction_id"] not in data["entities"]:
                    raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "父势力必须是本次读取的核心势力或同卷势力", status_code=status)
            if name in names or duplicate:
                raise DomainApiError("VOLUME_ENTITY_NAME_CONFLICT", "新档案名称重复，请修改或选择已有档案", status_code=409 if confirming else 502)
            names.add(name)
        if kind == "characters":
            for relation_id in row["state"]["relationship_focus_ids"]:
                relation = data["relations"].get(relation_id)
                if identity is None or relation is None or identity not in {relation["source_character_id"], relation["target_character_id"]}:
                    raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "关系焦点必须涉及所选已有角色，新角色不能引用尚不存在的关系", status_code=status)
    if new_count > inputs.new_count or (not confirming and (new_count != inputs.new_count or existing_ids != set(inputs.selected_existing_ids))):
        raise DomainApiError("VOLUME_ENTITY_RESULT_INVALID", "候选数量与本次新建数量或已有档案选择不一致", status_code=status)
    return result


async def confirm_volume_entities(task: str, novel_id: str, volume_id: str, request: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
    """在一次必需事务内复查来源，保存档案与卷状态，并记录原键回执。

    Args:
        task: 确认路由固定的卷内任务。
        novel_id: 路径指定的小说。
        volume_id: 路径指定的卷。
        request: 严格审核列表及原始生成依据。
        idempotency_key: 保存失败后重试保持不变的请求键。
        session: 调用方事务；提供时不另开事务。
    Returns:
        公开卷状态列表和候选到正式实体 ID 的映射；失败整体回滚。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint, compute_preparation_fingerprint

    basis, kind = request.basis, VOLUME_ENTITY_TASKS[task]
    plans = isinstance(request, VolumeCharactersPlanConfirmV1)
    response_model = VolumeCharactersConfirmedV1 if kind == "characters" else VolumeFactionsConfirmedV1
    inputs = basis.generation_input
    if basis.workflow != task or inputs.novel_id != novel_id or inputs.volume_id != volume_id:
        raise DomainApiError("VOLUME_ENTITY_SCOPE_MISMATCH", "候选不属于当前小说、卷或任务", status_code=422)
    fingerprint = build_idempotency_fingerprint(idempotency_key, {"operation": task, "novel_id": novel_id, "volume_id": volume_id, **request.model_dump(mode="json")})

    async def replay(session: AsyncClientSession | None = None) -> dict[str, Any] | None:
        """同一键只回放相同命令，回放不受保存后的来源版本变化影响。"""
        receipt = await volume_command_receipt_repo.find_receipt(novel_id, fingerprint.key_hash, session=session)
        if receipt is None:
            return None
        if receipt["request_hash"] != fingerprint.request_hash:
            raise DomainApiError("VOLUME_ENTITY_IDEMPOTENCY_CONFLICT", "同一确认键已用于不同内容", status_code=409)
        await novel_repo.get_novel_by_id(novel_id, session=session)
        await volume_repo.get_volume_by_id(volume_id, session=session)
        # 回执沿用 JSON 日期；只在返回时按严格 JSON 契约恢复 datetime，不重新建档。
        return response_model.model_validate_json(json.dumps(receipt["result"], ensure_ascii=False)).model_dump()

    original = await replay(session)
    if original is not None:
        return original

    async def write(session: AsyncClientSession) -> dict[str, Any]:
        """先复查，再复用领域写入，所有状态与回执共享同一事务。"""
        original = await replay(session)
        if original is not None:
            return original
        execution = basis.flow_snapshot["execution"]
        if "character_fact_reads" not in execution:
            raise DomainApiError("CHARACTER_FACT_CONTRACT_REQUIRED", "原候选未保存人物事实依据，请保留候选并重新生成", status_code=409)
        original_reads = [*execution["character_fact_reads"], *execution.get("item_fact_reads", [])]
        if kind == "characters":
            if (execution.get("relation_reading_contract") != "character_relation_facts_v1"
                    or "character_relation_fact_reads" not in execution):
                raise DomainApiError("CHARACTER_RELATION_FACT_CONTRACT_REQUIRED", "原候选未保存关系事实依据，请保留候选并重新生成", status_code=409)
            original_reads = [*original_reads, *execution["character_relation_fact_reads"]]
        if kind == "characters" and not plans and any(row.character_id is None for row in request.candidates):
            raise DomainApiError("CHARACTER_FACT_CONTRACT_REQUIRED", "新人物需要明确起点，请先在人物详情确认初始设定", status_code=409)
        from backend.services.novel.writing_context import revalidate_position_fact_reads
        await revalidate_position_fact_reads(original_reads, session=session, protect=True)
        data = await load_volume_entity_context(task, inputs, session=session)
        if any(read not in original_reads for read in data["fact_reads"]):
            raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "候选缺少当前人物或关系查询的原依据，请保留候选并重新生成", status_code=409)
        try:
            current_fingerprint = compute_preparation_fingerprint(task, inputs, data["content_fingerprint"], basis.flow_snapshot) if inputs.selection_mode == "auto" else compute_flow_candidate_fingerprint(task, inputs, data["source_refs"], basis.flow_snapshot)
        except (KeyError, ValueError) as exc:
            raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "原流程或生成输入已变化，请重新生成", status_code=409) from exc
        changed = data["content_fingerprint"] != basis.content_fingerprint if inputs.selection_mode == "auto" else [ref.model_dump() for ref in data["source_refs"]] != sorted([ref.model_dump() for ref in basis.source_refs], key=lambda ref: (ref["resource_type"], ref["id"]))
        if current_fingerprint != basis.input_fingerprint or changed:
            raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "生成所用资料已变化，请保留候选并重新生成", status_code=409)
        if basis.flow_snapshot["execution"].get("agent_reads"):
            from backend.services.task_flows.book_tools import replay_book_reads
            await replay_book_reads(basis.flow_snapshot["scope"], basis.flow_snapshot["execution"]["agent_reads"], session=session, protect=True)
        result = validate_volume_entity_candidates(task, {kind: [item.model_dump(mode="json") for item in request.candidates]}, data, confirming=True, plans=plans)
        if kind == "characters" and not plans:
            from backend.services.novel.character_fact_service import ensure_character_fields_unmanaged
            from backend.services.novel.character_volume_state_service import STATE_FACT_FIELDS
            # 原候选的九字段状态不能逐人删字段升级；整批在首个人物状态保存前检查。
            await ensure_character_fields_unmanaged(novel_id, [row["character_id"] for row in result[kind]],
                                                     list(STATE_FACT_FIELDS), session=session)
        for resource_type, _, repository, document in data["sources"]:
            field = "writing_guard_revision" if resource_type in {"novel", "volume"} else "dependency_guard_revision"
            guarded = await repository.collection.update_one({"_id": document["_id"], "is_deleted": False, **build_snapshot_version_filter(document)}, {"$inc": {field: 1}}, session=session)
            if guarded.matched_count != 1:
                raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "资料在确认期间已变化，请保留候选并重试", status_code=409)
        new_characters = {}
        if plans:
            from backend.services.novel.character_fact_batch_service import create_character_fact_batch
            from backend.services.novel.character_fact_contract import CharacterFactCreateDataV1, CHARACTER_FACT_FIELDS
            candidates = []
            for row in request.candidates:
                if row.character_id is not None:
                    continue
                profile = row.profile.model_dump(mode="json", exclude_unset=True)
                facts = {name: value for name, value in profile.items() if name in CHARACTER_FACT_FIELDS}
                if row.initial_facts is not None:
                    facts.update(row.initial_facts.model_dump(mode="json"))
                candidates.append({"candidate_ref": row.candidate_ref,
                    "profile": {name: value for name, value in profile.items() if name in CharacterFactCreateDataV1.model_fields},
                    "facts": facts})
            if candidates:
                created = await create_character_fact_batch(novel_id, {
                    "position": {"version": 1, "intent": "volume_start", "target_type": "volume", "target_id": volume_id},
                    "candidates": candidates, "confirmed": True,
                }, idempotency_key=f"volume-profiles:{fingerprint.key_hash}", session=session)
                new_characters = {row["candidate_ref"]: row["character_id"] for row in created["characters"]}
        states, mapping = [], {}
        entity_field = "character_id" if kind == "characters" else "faction_id"
        state_model = CharacterVolumeStateReadV1 if kind == "characters" else FactionVolumeStateReadV1
        for index, row in enumerate(result[kind]):
            identity = row[entity_field]
            # 子命令键由本批键和候选顺序确定，避免重试生成不同身份。
            command_key = f"ent:{fingerprint.key_hash}:{index}"
            if identity is None:
                if kind == "characters":
                    identity = new_characters[row["candidate_ref"]]
                else:
                    entity = await FactionService.create_faction(novel_id, {**row["profile"], "volume_id": volume_id}, idempotency_key=command_key, session=session)
                    identity = entity[entity_field]
            state_service = CharacterVolumeStateService if kind == "characters" else FactionVolumeStateService
            if plans:
                existing_state = data["states"].get(identity)
                if existing_state is None:
                    state = await state_service.create_plan(novel_id, volume_id, identity, row["state"], idempotency_key=command_key, session=session)
                else:
                    state = await state_service.update_plan(novel_id, str(existing_state["state_id"]),
                        {**row["state"], "expected_version": row["state_expected_version"]}, session=session)
            else:
                state = await state_service.upsert_state(novel_id, volume_id, identity, {**row["state"], "expected_version": row["state_expected_version"]}, idempotency_key=command_key, session=session)
            public = {key: value for key, value in state.items() if key in state_model.model_fields}
            for field in ("state_id", "novel_id", "volume_id", "source_state_id"):
                if public.get(field) is not None:
                    public[field] = str(public[field])
            states.append(state_model.model_validate(public).model_dump())
            mapping[row["candidate_ref"]] = identity
        if inputs.selection_mode == "auto":
            from backend.services.novel.plot_service import record_preparation
            await record_preparation(novel_id, volume_id, kind, session=session)
        # 提交前验证完整响应，避免正式档案已经保存，HTTP 才发现返回类型不对。
        response = response_model.model_validate({"novel_id": novel_id, "volume_id": volume_id, "data": states, "mapping": mapping})
        await volume_command_receipt_repo.create_receipt({"novel_id": novel_id, "volume_id": to_object_id(volume_id), "operation": task, "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash, "result": response.model_dump(mode="json")}, session=session)
        return response.model_dump()

    if session is not None:
        return await write(session)

    try:
        return await run_mongo_write_unit(write, "confirm_volume_entities", require_transaction=True)
    except TransactionNotSupportedError as exc:
        raise DomainApiError("VOLUME_ENTITY_TRANSACTION_REQUIRED", "保存档案和卷状态需要数据库事务，请检查数据库配置", status_code=503) from exc
    except (DuplicateKeyError, OperationFailure) as exc:
        original = await replay()
        if original is not None:
            return original
        if isinstance(exc, DuplicateKeyError) or exc.code == 112:
            raise DomainApiError("VOLUME_ENTITY_WRITE_CONFLICT", "档案或卷状态已被其他操作修改，请保留候选并重试", status_code=409) from exc
        raise
    except NotFoundError as exc:
        raise DomainApiError("VOLUME_ENTITY_REFERENCE_UNAVAILABLE", "小说、卷或所选档案已不存在，请保留候选并刷新", status_code=404) from exc
