"""逐级候选复查和一次事务内的审核确认保存。"""

from __future__ import annotations

from pymongo.asynchronous.client_session import AsyncClientSession

from typing import Any

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.confirmation_timing import WritingConfirmationTiming
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint, canonical_request_hash
from backend.llm.schemas.writing_pydantic import WRITING_RESULTS, WRITING_TASKS, WritingGenerateInputV1
from backend.services.novel.writing_context import load_writing_context, load_writing_parents, protect_writing_sources
from backend.services.novel.writing_contract import WritingConfirmV1, WritingContextBasisV1


def merge_writing_reads(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    """合并实际执行的资料节点，空查询和不同查询范围均保留。

    Args:
        contexts: 生成或确认中重新读取的内容依据。
    Returns:
        不包含统计版本的稳定依据；同一读取中途变化则拒绝。
    """
    reads = {}
    for context in contexts:
        for read in context["reads"]:
            if read["kind"] in {"character_facts", "character_relation_facts", "item_facts"}:
                ids_field = {"character_facts": "character_ids", "character_relation_facts": "relation_ids", "item_facts": "item_ids"}[read["kind"]]
                selection = {"novel_id": read["novel_id"], ids_field: read[ids_field],
                             "position": {name: read["position"][name] for name in ("version", "intent", "target_type", "target_id")}}
            else:
                selection = read["scope"]
            key = canonical_request_hash({"kind": read["kind"], "scope": selection})
            if key in reads and reads[key] != read:
                raise DomainApiError("WRITING_SOURCE_CHANGED", "生成期间资料已修改，请重新生成", status_code=409)
            reads[key] = read
    return WritingContextBasisV1.model_validate({"reads": [reads[key] for key in sorted(reads)]}).model_dump(mode="json")


def writing_candidate_fingerprint(task: str, generation_input: Any, context_basis: dict[str, Any], snapshot: dict[str, Any]) -> str:
    """将原图版本、实际输入和内容读取绑定，忽略来源的展示版本。

    Args:
        task: 层级任务。
        generation_input: 实际业务输入。
        context_basis: 本次实际内容与查询依据。
        snapshot: 原图修订和生成设置快照。
    Returns:
        可在不读取当前模型设置的情况下复验的摘要。
    """
    from backend.services.task_flows.candidate import flow_fingerprint_inputs
    return canonical_request_hash({"task": task, "inputs": flow_fingerprint_inputs(task, generation_input, snapshot), "context_basis": context_basis})


def validate_writing_candidate(task: str, candidate: dict[str, Any], data: dict[str, Any], *, confirming: bool = False) -> dict[str, Any]:
    """先校验正式内容白名单、数量、实体引用和整条候选重复，再检查预算。

    Args:
        task: 生成任务。
        candidate: 模型输出或作者审核后的候选。
        data: 当前任务上下文。
        confirming: 审核时允许删除部分候选，不能增加未请求数量。
    Returns:
        可交给领域确认的候选内容。
    """
    result = WRITING_RESULTS[task].model_validate(candidate).model_dump(mode="json")
    if task == "write_chapter_by_ai":
        return result
    entries = result[WRITING_TASKS[task][1]]
    count = data["request"].count
    if not entries and count != 0:
        raise DomainApiError("WRITING_RESULT_COUNT_INVALID", "本次尚需规划内容，候选不能为空", status_code=422 if confirming else 502)
    if len(entries) > count or (not confirming and len(entries) != count):
        raise DomainApiError("WRITING_RESULT_COUNT_INVALID", "生成结果数量与本次要求不一致", status_code=422 if confirming else 502)
    allowed: dict[str, set[str]] = {}
    for entity in data["context"]["selected_entities"]:
        allowed.setdefault(entity["resource_type"], set()).add(entity["id"])
    # 引用错误不能靠改预算解决，必须先拒绝，避免返回可编辑预算候选。
    for index, entry in enumerate(entries):
        planning = entry["planning"]
        for field, kind in (("character_ids", "character"), ("faction_ids", "faction"), ("location_ids", "location"), ("item_ids", "item"), ("rule_ids", "world_rule")):
            fields = {
                f"candidate.{WRITING_TASKS[task][1]}.{index}.planning.{field}.{reference_index}": "该资料未在本次读取"
                for reference_index, reference in enumerate(planning.get(field, []))
                if reference not in allowed.get(kind, set())
            }
            if fields:
                raise DomainApiError("WRITING_RESULT_REFERENCE_INVALID", "候选引用了本次未读取的资料，请重新选择资料后生成", status_code=422 if confirming else 502,
                                     field_errors=fields)
        if planning.get("pov_character_id") and planning["pov_character_id"] not in allowed.get("character", set()):
            raise DomainApiError("WRITING_RESULT_REFERENCE_INVALID", "视角人物不在本次资料中", status_code=422 if confirming else 502,
                                 field_errors={f"candidate.{WRITING_TASKS[task][1]}.{index}.planning.pov_character_id": "请使用本次已读取的人物"})
    # 比较 DTO 补齐默认值后的整条内容，标出每组重复中的全部候选。
    duplicate_fields = {
        f"candidate.{WRITING_TASKS[task][1]}.{index}": "与本批其他候选内容完全相同"
        for index, entry in enumerate(entries)
        if any(entry == other for other_index, other in enumerate(entries) if other_index != index)
    }
    if duplicate_fields:
        raise DomainApiError("WRITING_RESULT_DUPLICATE", "本批存在内容完全相同的候选，请修改或删除重复项", status_code=422 if confirming else 502,
                             field_errors=duplicate_fields)
    # 只在上下文给出预算时核对，不把未确定预算当作零。
    parent_plan = data["context"]["plan"][-1].get("planning") or {}
    existing = data["context"].get("existing_children", [])
    for field in ("target_word_count", "target_chapter_count"):
        budget = parent_plan.get(field)
        if budget is None:
            continue
        used = sum((child.get("planning") or {}).get(field) or 0 for child in existing)
        requested = sum(entry["planning"].get(field) or 0 for entry in entries)
        if field == "target_chapter_count":
            # 当前层级最终都要落到章节；未分配预算的篇章或场景也至少占一章。
            used = sum((child.get("planning") or {}).get(field) or 1 for child in existing)
            requested = sum(entry["planning"].get(field) or 1 for entry in entries)
            if task == "plan_chapters_by_ai":
                used, requested = len(existing), len(entries)
        if requested and used + requested > budget:
            fields = ({"candidate.chapters": "章节数量超过当前场景预算"} if task == "plan_chapters_by_ai" and field == "target_chapter_count" else {
                f"candidate.{WRITING_TASKS[task][1]}.{index}.planning.{field}": "本批预算合计超过上级剩余额度"
                for index in range(len(entries))
            })
            raise DomainApiError("WRITING_RESULT_BUDGET_EXCEEDED", "已有规划与本批候选超过上级预算，请调整候选", status_code=422 if confirming else 502,
                                 field_errors=fields, details={"field": field, "budget": budget, "existing": used, "candidate": requested})
        if not (task == "plan_chapters_by_ai" and field == "target_chapter_count"):
            missing = [index + 1 for index, entry in enumerate(entries) if entry["planning"].get(field) is None]
            if missing:
                # 一次定位所有缺失预算，作者无需补完一个字段后再保存才能看见下一个。
                fields = {
                    f"candidate.{WRITING_TASKS[task][1]}.{index}.planning.{budget_field}": "请分配目标字数" if budget_field == "target_word_count" else "请分配目标章节数"
                    for budget_field in ("target_word_count", "target_chapter_count")
                    if parent_plan.get(budget_field) is not None and not (task == "plan_chapters_by_ai" and budget_field == "target_chapter_count")
                    for index, entry in enumerate(entries) if entry["planning"].get(budget_field) is None
                }
                raise DomainApiError("WRITING_RESULT_BUDGET_MISSING", "上级已有预算，请为每个候选分配对应预算后重新确认", status_code=422 if confirming else 502,
                                     field_errors=fields, details={"field": field, "budget": budget, "candidate_indices": missing})
    return result


async def confirm_writing(task: str, parent_id: str, request: WritingConfirmV1, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
    """在一个必需事务内复查来源、保存审核批次和写入幂等回执。

    Args:
        task: 确认路由固定的任务。
        parent_id: 路径指定的生成父级或正文目标。
        request: 作者审核的内容及原始依据。
        idempotency_key: 重试保持不变的确认键。
        session: 调用方事务；提供时不另开事务。
    Returns:
        同次确认的正式对象和 ID；任何失败都不留下部分批次。
    """
    with WritingConfirmationTiming(task, owns_transaction=session is None) as timing:
        from backend.services.novel.arc_contract import ArcReadV1, serialize_arc
        from backend.services.novel.arc_service import ArcService
        from backend.services.novel.scene_contract import SceneReadV1, serialize_scene
        from backend.services.novel.scene_service import SceneService
        from backend.services.novel.chapter_contract import ChapterReadV2, serialize_chapter
        from backend.services.novel.chapter_service import ChapterService
        from backend.services.task_flows.registry import TASKS

        basis = request.basis
        inputs = basis.generation_input
        spec = TASKS[task]
        if (basis.workflow, basis.step, basis.schema_id, basis.schema_version) != (task, spec.step, spec.schema_id, spec.schema_version) or inputs.target_id != str(ObjectId(parent_id)) or inputs.novel_id != basis.novel_id or inputs.target_type != WRITING_TASKS[task][0]:
            raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "候选不属于当前确认位置", status_code=409)
        expected = inputs.expected_version
        if request.expected_version != expected:
            raise DomainApiError("WRITING_VERSION_CONFLICT", "确认版本必须保持生成时读取的目标版本", status_code=409)
        payload = request.model_dump(mode="json")
        # 旧冻结请求没有读取位置字段；新增默认值不能改变它原来的成功回执键。
        for field in ("reading_intent", "reading_version"):
            if field not in inputs.model_fields_set:
                payload["basis"]["generation_input"].pop(field, None)
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"task": task, "parent_id": parent_id, **payload})
        receipts = BaseRepository("writing_confirmation_receipts").collection
        receipt_query = {"novel_id": ObjectId(inputs.novel_id), "operation": task, "idempotency_key_hash": fingerprint.key_hash}

        async def save(session):
            timing.phase("父链与回执检查")
            # 回执不重新检查已被本次保存改变的子项，但仍服从整条父链的回收状态。
            parent_chain = await load_writing_parents(inputs.novel_id, inputs.target_type, inputs.target_id, session=session)
            existing = await receipts.find_one(receipt_query, session=session)
            if existing:
                if existing["request_hash"] != fingerprint.request_hash:
                    raise DomainApiError("WRITING_IDEMPOTENCY_CONFLICT", "同一确认键不能用于不同内容", status_code=409)
                timing.phase("回调完成至事务与会话退出" if timing.owns_transaction else "回调返回")
                return existing["result"]
            if inputs.reading_version != 1 or inputs.reading_intent is None:
                raise DomainApiError("WRITING_READING_CONTRACT_CHANGED", "此候选没有固定读取位置，请保留草稿并重新生成", status_code=409)
            snapshot = basis.flow_snapshot
            if snapshot is None or snapshot.get("scope", {}).get("target_id") != inputs.target_id:
                raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "候选缺少原图及操作位置", status_code=409)
            timing.phase("来源复查（含Agent保护）")
            data = await load_writing_context(task, {}, inputs.model_dump(mode="json"), session=session, parent_chain=parent_chain)
            contexts = [data]
            # 同一事务快照中，相同完整输入只读一次；每条历史依据仍逐一核对。
            loaded_contexts = {canonical_request_hash(inputs.model_dump(mode="json")): data}
            records = snapshot["execution"].get("writing_reads", [])
            if len(records) > 20:
                raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "候选资料读取次数无效", status_code=409)
            for record in records:
                read_scope = record.get("scope", snapshot["scope"])
                if any(read_scope.get(key) != snapshot["scope"].get(key) for key in ("novel_id", "target_type", "target_id")):
                    raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "资料读取位置与本次任务不一致", status_code=409)
                read_input = WritingGenerateInputV1.model_validate({**record["parameters"], **read_scope})
                read_key = canonical_request_hash(read_input.model_dump(mode="json"))
                loaded = loaded_contexts.get(read_key)
                if loaded is None:
                    loaded = await load_writing_context(task, record["parameters"], read_scope, session=session, parent_chain=parent_chain)
                    loaded_contexts[read_key] = loaded
                if loaded["context_basis"] != record["basis"]:
                    raise DomainApiError("WRITING_SOURCE_CHANGED", "候选使用的资料已变化，请保留草稿并重新生成", status_code=409)
                contexts.append(loaded)
            current_basis = merge_writing_reads([value["context_basis"] for value in contexts])
            if current_basis != basis.context_basis.model_dump(mode="json"):
                raise DomainApiError("WRITING_SOURCE_CHANGED", "候选使用的规划、前文或查询结果已变化", status_code=409)
            try:
                current_fingerprint = writing_candidate_fingerprint(task, inputs, current_basis, snapshot)
            except (ValueError, KeyError) as exc:
                raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "生成时的方案或输入已不匹配", status_code=409) from exc
            if current_fingerprint != basis.input_fingerprint:
                raise DomainApiError("WRITING_CANDIDATE_MISMATCH", "候选依据与生成输入不一致", status_code=409)
            agent_reads = snapshot["execution"].get("agent_reads", [])
            protected_agent_guards = {}
            if agent_reads:
                from backend.services.task_flows.book_tools import replay_book_reads
                replayed = await replay_book_reads(snapshot["scope"], agent_reads, session=session, protect=True)
                protected_agent_guards = replayed["guards"]
            timing.phase("候选校验")
            candidate = validate_writing_candidate(task, request.candidate, data, confirming=True)
            # Agent 已在当前事务保护过的同一文档不再重复写入内部计数。
            merged_guards = {key: document for value in contexts for key, document in value["guards"].items() if key not in protected_agent_guards}
            timing.phase("来源版本保护")
            await protect_writing_sources({"guards": merged_guards, "fact_reads": [
                read for read in basis.context_basis.model_dump(mode="json")["reads"] if read["kind"] in {"character_facts", "character_relation_facts", "item_facts"}
            ]}, session=session)
            timing.phase("业务保存（含引用与版本保护）")
            if task == "write_chapter_by_ai":
                document = await ChapterService.update_chapter_in_session(parent_id, {"content": candidate["content"], "expected_version": expected}, session=session, source="writing")
                documents = [document]
                read_model, serialize = ChapterReadV2, serialize_chapter
            elif task == "plan_chapters_by_ai":
                documents = await ChapterService.create_chapters_in_session(parent_id, [
                    (fields, f"writing:{fingerprint.key_hash}:{index}")
                    for index, fields in enumerate(candidate["chapters"])
                ], session=session)
                read_model, serialize = ChapterReadV2, serialize_chapter
            elif task == "plan_arcs_by_ai":
                documents = await ArcService.create_arcs_in_session(parent_id, [
                    (fields, f"writing:{fingerprint.key_hash}:{index}")
                    for index, fields in enumerate(candidate["arcs"])
                ], session=session)
                read_model, serialize = ArcReadV1, serialize_arc
            else:
                read_model, serialize = SceneReadV1, serialize_scene
                documents = []
                for index, fields in enumerate(candidate[WRITING_TASKS[task][1]]):
                    # 子项键由整次确认键和次序稳定生成，同一事务中不重复开写入单元。
                    document = await SceneService.create_scene_in_session(parent_id, fields, idempotency_key=f"writing:{fingerprint.key_hash}:{index}", session=session)
                    documents.append(document)
            timing.phase("响应构造")
            result = {"operation": task, "ids": [str(document["_id"]) for document in documents], "data": [read_model.model_validate(serialize(document)).model_dump(mode="json") for document in documents]}
            timing.phase("回执写入")
            await receipts.insert_one({**receipt_query, "request_hash": fingerprint.request_hash, "result": result, "created_at": get_utc_now()}, session=session)
            # 回调返回后还要退出事务和会话；这段时间不等于提交命令的驱动耗时。
            timing.phase("回调完成至事务与会话退出" if timing.owns_transaction else "回调返回")
            return result

        timing.phase("事务准备")
        if session is not None:
            return await save(session)

        return await run_mongo_write_unit(save, "confirm_writing", require_transaction=True)
