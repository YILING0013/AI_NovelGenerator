"""详细剧情与卷资料准备的内容指纹和事务保存。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import touch_dependency_endpoint_guards
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import canonical_request_hash, build_idempotency_fingerprint, update_versioned_document
from backend.services.novel.plot_contract import PLOT_TASKS, PlotGenerateInputV1, PlotConfirmV1, VolumePreparationConfirmV1, VolumePlotResultV1, ArcPlotResultV1, PlotSourceConflictReportV1


def plot_hash(plot: str) -> str:
    """计算已确认剧情的内容摘要。

    Args:
        plot: 独立剧情正文。
    Returns:
        不受统计、时间或版本影响的摘要。
    """
    return canonical_request_hash({"plot": plot})


def preparation_content_fingerprint(sources: list[tuple[str, dict[str, Any]]], *, character_facts: list[dict[str, Any]], fact_reads: list[dict[str, Any]]) -> str:
    """按实际小说、实体和状态内容识别准备资料变化，忽略派生统计。

    Args:
        sources: 本次实际读取的资料类别与完整文档。
        character_facts: 同一位置共享读取的人物结果。
        fact_reads: 该次原始事实依据，包含空选择和目录范围。
    Returns:
        排除显示版本和更新时间、保留内容及空集合变化的摘要。
    """
    from backend.services.novel.writing_context import character_position_content, position_content

    facts_by_id = {item["character_id"]: item for item in character_facts}
    values = []
    for kind, document in sources:
        if kind == "character_relation":
            value = {key: document.get(key) for key in ("relation_id", "source_character_id", "target_character_id", "relation_type", "description", "is_active")}
            value.update(resource_type=kind, id=document["relation_id"])
        elif kind == "character":
            value = character_position_content(document, facts_by_id[document["character_id"]])
        else:
            value = position_content(document, kind)
        values.append(value)
    return canonical_request_hash({"sources": sorted(values, key=lambda value: (value["resource_type"], value["id"])), "fact_reads": fact_reads})


def plot_source_fingerprint(chain: list[tuple[str, dict[str, Any]]], neighbors: dict[str, Any]) -> str:
    """只记录上级剧情、当前规划及相邻边界，避免相邻剧情互相过期。

    Args:
        chain: 小说到当前卷或篇章的正式父链。
        neighbors: 当前部分的前后同级对象。
    Returns:
        持久剧情就绪状态使用的内容摘要。
    """
    from backend.services.novel.writing_context import writing_content

    plans = []
    for index, (kind, document) in enumerate(chain):
        value = writing_content(document, kind)
        for field in ("plot_source_fingerprint", "preparation", "location_ids"):
            value.pop(field, None)
        if index == len(chain) - 1:
            value.pop("plot", None)
        if isinstance(value.get("planning"), dict):
            value["planning"] = {key: item for key, item in value["planning"].items() if not key.endswith("_ids")}
        plans.append(value)
    boundaries = {}
    for name, document in neighbors.items():
        if document is None:
            boundaries[name] = None
            continue
        planning = document.get("planning") or {}
        boundaries[name] = {"id": str(document.get("_id") or document.get("id")), "order_index": document["order_index"], "start_state": planning.get("start_state", ""), "end_state": planning.get("end_state", "")}
    return canonical_request_hash({"plans": plans, "neighbors": boundaries})


async def load_plot_sources(novel_id: str, kind: str, target_id: str, *, session: AsyncClientSession | None = None, updated_fields: dict[str, Any] | None = None, allow_write_lock: bool = False, parent_chain: list[tuple[str, dict[str, Any]]] | None = None) -> tuple[list, dict, str]:
    """读取剧情就绪所需的最少来源，人工保存也使用同一计算方式。

    Args:
        novel_id: 当前小说。
        kind: volume 或 arc。
        target_id: 当前对象。
        session: 保存事务。
        updated_fields: 本次将保存的剧情和规划。
        allow_write_lock: 调用方已持有当前事务资料写锁。
        parent_chain: 当前 session 的同一次活动事务中已校验且尚未修改的父链；位置相同才复用。
    Returns:
        父链、相邻边界和最终内容指纹。
    """
    from backend.services.novel.writing_context import load_writing_parents, COLLECTIONS, PARENTS

    if (session is not None and session.in_transaction and parent_chain
            and str(parent_chain[0][1]["_id"]) == novel_id
            and parent_chain[-1][0] == kind
            and str(parent_chain[-1][1]["_id"]) == target_id):
        chain = list(parent_chain)
    else:
        chain = await load_writing_parents(novel_id, kind, target_id, session=session, allow_write_lock=allow_write_lock)
    target = chain[-1][1]
    siblings = await BaseRepository(COLLECTIONS[kind]).collection.find({"novel_id": ObjectId(novel_id), f"{PARENTS[kind]}_id": target[f"{PARENTS[kind]}_id"], "is_deleted": False}, session=session).sort("order_index", 1).to_list(length=None)
    index = next(i for i, row in enumerate(siblings) if row["_id"] == target["_id"])
    neighbors = {"previous": siblings[index - 1] if index else None, "next": siblings[index + 1] if index + 1 < len(siblings) else None}
    if updated_fields:
        chain[-1] = (kind, {**target, **updated_fields})
    return chain, neighbors, plot_source_fingerprint(chain, neighbors)


async def preserve_plots_after_novel_rename(before: dict[str, Any], after: dict[str, Any], *, session: AsyncClientSession) -> None:
    """改书名时保留原本有效的剧情，不重新认可已经过期的剧情。

    Args:
        before: 按原版本成功更新前的小说。
        after: 同一事务中更新后的小说；调用方已确认只变更书名等显示资料。
        session: 改名与剧情指纹共用的事务。
    Returns:
        无；剧情正文、准备标记和篇章版本保持原样。
    """
    volumes = await BaseRepository("volumes").collection.find({"novel_id": before["_id"], "is_deleted": False}, session=session).sort("order_index", 1).to_list(length=None)
    arcs = await BaseRepository("arcs").collection.find({"novel_id": before["_id"], "is_deleted": False}, session=session).sort("order_index", 1).to_list(length=None)
    groups = [("volume", [], volumes)]
    groups.extend(("arc", [("volume", volume)], [arc for arc in arcs if arc["volume_id"] == volume["_id"]]) for volume in volumes)
    for kind, parents, siblings in groups:
        for index, target in enumerate(siblings):
            if not target.get("plot", "").strip():
                continue
            neighbors = {"previous": siblings[index - 1] if index else None, "next": siblings[index + 1] if index + 1 < len(siblings) else None}
            old_fingerprint = plot_source_fingerprint([("novel", before), *parents, (kind, target)], neighbors)
            if target.get("plot_source_fingerprint") != old_fingerprint:
                continue
            # 使用原有摘要合同核对旧来源，不凭旧格式或非空剧情推断有效。
            fingerprint = plot_source_fingerprint([("novel", after), *parents, (kind, target)], neighbors)
            result = await BaseRepository("volumes" if kind == "volume" else "arcs").collection.update_one(
                {"_id": target["_id"], "version": target["version"], "plot_source_fingerprint": old_fingerprint, "is_deleted": False},
                {"$set": {"plot_source_fingerprint": fingerprint}}, session=session,
            )
            if result.matched_count != 1:
                from backend.db.errors import VersionConflictError
                raise VersionConflictError("改书名时剧情已被其他操作修改，请重试")


def plot_prompt_context(context: dict[str, Any], target_type: str, target_id: str) -> dict[str, Any]:
    """生成资料不携带当前部分的旧剧情，避免重生成退化为旧稿缩写。

    Args:
        context: 保留给作者预览和来源核对的完整资料。
        target_type: 当前要生成剧情的卷或篇章。
        target_id: 当前部分的正式 ID。
    Returns:
        独立的提示词资料；上级剧情、已定规划和已有下级保持原样。
    """
    result = deepcopy(context)
    result.pop("current_plot", None)
    for part in result["plan"]:
        if part["resource_type"] == target_type and part["id"] == target_id:
            part.pop("plot", None)
    return result


async def load_plot_context(task: str, parameters: dict[str, Any], scope: dict[str, Any], *, session: AsyncClientSession | None = None, check_ready: bool = True) -> dict[str, Any]:
    """为剧情生成读取正式资料，不要求当前已有剧情或准备标记。

    Args:
        task: 两种剧情任务之一。
        parameters: 作者要求。
        scope: 路径固定的位置与目标版本。
        session: 确认时复用事务。
        check_ready: 编辑器预览可不检查目标版本。
    Returns:
        图资料节点和候选确认共同使用的输入、资料及依据。
    """
    from backend.services.novel.writing_context import load_writing_context, writing_plot_missing

    # 位置版本属于流程读取依据，不能扩进旧剧情请求并改变已保存回执的摘要。
    request = PlotGenerateInputV1.model_validate({key: value for key, value in {**parameters, **scope}.items()
                                                if key not in {"reading_intent", "reading_version"}})
    if PLOT_TASKS[task] != request.target_type:
        raise DomainApiError("PLOT_TARGET_INVALID", "剧情任务与当前部分不匹配", status_code=422)
    writing_task = "plan_arcs_by_ai" if request.target_type == "volume" else "plan_scenes_by_ai"
    data = await load_writing_context(writing_task, {"user_guidance": request.user_guidance}, {"novel_id": request.novel_id, "target_type": request.target_type, "target_id": request.target_id, "reading_intent": "replan", "reading_version": 1}, session=session, check_ready=False)
    target = data["chain"][-1][1]
    if check_ready and request.target_type == "arc":
        missing = await writing_plot_missing(data["chain"][:-1], session=session)
        if missing:
            raise DomainApiError("PLOT_PARENT_NOT_READY", "请先确认卷剧情和卷资料", status_code=409, field_errors={item["field"]: item["message"] for item in missing})
    if check_ready and target["version"] != request.expected_version:
        raise DomainApiError("PLOT_VERSION_CONFLICT", "当前部分已修改，请刷新后重新生成剧情", status_code=409)
    data["request"] = data["generation_input"] = request
    data["context"]["has_children"] = bool(data["context"]["existing_children"])
    data["context"]["current_plot"] = target.get("plot", "")
    data["context"]["planning_editable"] = not data["context"]["has_children"]
    if request.target_type == "arc":
        siblings = [document for document in data["siblings"] if document["_id"] != target["_id"]]
        values = [{"id": str(document["_id"]), "title": document["title"], "order_index": document["order_index"], "planning": {field: (document.get("planning") or {}).get(field) for field in ("target_chapter_count", "target_word_count")}} for document in siblings]
        data["context"]["sibling_plans"] = values
        data["context_basis"]["reads"].append({"kind": "neighbors", "scope": {"novel_id": request.novel_id, "target_type": "arc", "target_id": request.target_id, "range": "plot_budget_siblings"}, "fingerprint": canonical_request_hash(values)})
        sources = {(source["resource_type"], source["id"]): source for source in data["source_refs"]}
        for document in siblings:
            identity = str(document["_id"])
            sources[("arc", identity)] = {"resource_type": "arc", "id": identity, "version": document["version"]}
            data["guards"][("arcs", identity)] = document
        data["source_refs"] = list(sources.values())
    return data


async def stamp_manual_plot(novel_id: str, kind: str, target_id: str, fields: dict[str, Any], *, session: AsyncClientSession | None = None) -> None:
    """人工保存剧情时重新确认当前规划依据，清空剧情则移除有效标记。

    Args:
        novel_id: 当前小说。
        kind: 卷或篇章。
        target_id: 当前对象。
        fields: 将保存的明确字段，就地补充服务器计算的指纹。
        session: 保存事务。
    Returns:
        无；不接受客户端自行提供指纹。
    """
    if "plot" not in fields:
        return
    if not fields["plot"].strip():
        fields["plot_source_fingerprint"] = None
        return
    chain, neighbors, fingerprint = await load_plot_sources(novel_id, kind, target_id, session=session, updated_fields=fields)
    if session is not None:
        from backend.services.novel.writing_context import COLLECTIONS, protect_writing_sources
        guards = {(COLLECTIONS[part], str(doc["_id"])): doc for part, doc in chain}
        guards.update({(COLLECTIONS[kind], str(doc["_id"])): doc for doc in neighbors.values() if doc is not None})
        await protect_writing_sources({"guards": guards}, session=session)
    fields["plot_source_fingerprint"] = fingerprint


def validate_plot_candidate(task: str, candidate: dict[str, Any], data: dict[str, Any], *, confirming: bool = False) -> dict[str, Any]:
    """校验剧情并保留已定预算、边界和正式实体引用。

    Args:
        task: 当前剧情任务。
        candidate: 模型或作者审核后的候选。
        data: 本次正式资料。
        confirming: 是否处于确认阶段。
    Returns:
        适合审核及保存的规范候选。
    """
    kind = PLOT_TASKS[task]
    result_model = VolumePlotResultV1 if kind == "volume" else ArcPlotResultV1
    try:
        result = result_model.model_validate(candidate).model_dump(mode="json")
    except ValidationError as exc:
        errors = exc.errors(include_input=False, include_url=False)
        # 只保留规划文字的编辑机会；剧情、预算和引用错误仍按原规则拒绝。
        if any(not issue["loc"] or issue["loc"][0] != "planning"
               or any(str(part).endswith("_ids") or part in {"target_chapter_count", "target_word_count"}
                      for part in issue["loc"][1:]) for issue in errors):
            raise
        field_errors = {}
        for issue in errors:
            field = "candidate." + ".".join(str(part) for part in issue["loc"])
            if issue["type"] == "extra_forbidden":
                message = f"{'卷' if kind == 'volume' else '篇章'}规划不使用此字段"
            elif issue["type"] == "missing":
                message = "请填写此规划字段"
            elif issue["type"] == "string_type":
                message = "请填写文字"
            elif issue["type"] == "list_type":
                message = "请填写列表"
            else:
                message = "此规划字段的格式或长度不符合要求"
            field_errors[field] = message
        raise DomainApiError("PLOT_PLANNING_INVALID", "配套规划格式不正确，请检查规划字段",
                             status_code=422 if confirming else 502, field_errors=field_errors) from exc
    original = data["chain"][-1][1].get("planning") or {}
    protected = {"start_state", "end_state", "target_chapter_count", "target_word_count"}
    protected.update(key for key in original if key.endswith("_ids"))
    # 剧情步骤完善文字，不重新决定已确认的实体与预算。
    for key in protected:
        if key in original and original[key] not in (None, ""):
            result["planning"][key] = deepcopy(original[key])
    if PLOT_TASKS[task] == "arc" and not data.get("context", {}).get("has_children"):
        parent = next((document for kind, document in data["chain"] if kind == "volume"), None)
        siblings = data.get("context", {}).get("sibling_plans", [])
        for field in ("target_chapter_count", "target_word_count"):
            budget = (parent.get("planning") or {}).get(field) if parent else None
            if budget is None:
                continue
            minimum = 1 if field == "target_chapter_count" else 0
            used = sum((sibling.get("planning") or {}).get(field) or minimum for sibling in siblings)
            requested = result["planning"].get(field) or minimum
            if used + requested > budget:
                raise DomainApiError("PLOT_BUDGET_EXCEEDED", "当前篇章与同卷其他篇章的预算超过卷预算，请调整规划", status_code=422 if confirming else 502, details={"field": field, "budget": budget, "existing": used, "candidate": requested})
    return result


async def confirm_plot(task: str, target_id: str, request: PlotConfirmV1, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
    """复查原资料并在一个事务中保存剧情、规划和幂等回执。

    Args:
        task: 路由固定的剧情任务。
        target_id: 目标卷或篇章。
        request: 审核内容与原依据。
        idempotency_key: 本次确认重试保持不变的键。
        session: 调用方的保存事务；提供时不另开事务。

    Returns:
        已保存正式对象；失败不留下部分数据。
    """
    from backend.services.novel.writing_generation import merge_writing_reads, writing_candidate_fingerprint
    from backend.services.novel.writing_context import load_writing_parents, protect_writing_sources, COLLECTIONS
    from backend.services.task_flows.registry import TASKS

    basis, inputs = request.basis, request.basis.generation_input
    spec = TASKS[task]
    if inputs.target_id != target_id or inputs.target_type != PLOT_TASKS[task] or basis.workflow != task or basis.novel_id != inputs.novel_id or (basis.step, basis.schema_id, basis.schema_version) != (spec.step, spec.schema_id, spec.schema_version):
        raise DomainApiError("PLOT_CANDIDATE_MISMATCH", "候选不属于当前剧情任务", status_code=409)
    if request.expected_version != inputs.expected_version:
        raise DomainApiError("PLOT_VERSION_CONFLICT", "确认版本必须保持生成时的目标版本", status_code=409)
    confirmation = request.model_dump(mode="json")
    # 新增空字段不改变旧命令的摘要，升级前丢失响应的确认仍可按原键重试。
    if confirmation["candidate"]["source_conflicts"] is None:
        confirmation["candidate"].pop("source_conflicts")
    if confirmation["source_conflict_review"] is None:
        confirmation.pop("source_conflict_review")
    fingerprint = build_idempotency_fingerprint(idempotency_key, {"task": task, "target_id": target_id, **confirmation})
    receipts = BaseRepository("writing_confirmation_receipts").collection
    receipt_query = {"novel_id": ObjectId(inputs.novel_id), "operation": task, "idempotency_key_hash": fingerprint.key_hash}

    async def save(session):
        await load_writing_parents(inputs.novel_id, inputs.target_type, target_id, session=session)
        receipt = await receipts.find_one(receipt_query, session=session)
        if receipt:
            if receipt["request_hash"] != fingerprint.request_hash:
                raise DomainApiError("PLOT_IDEMPOTENCY_CONFLICT", "同一确认键不能用于不同内容", status_code=409)
            return receipt["result"]
        snapshot = basis.flow_snapshot
        if snapshot is None or snapshot["scope"].get("target_id") != target_id:
            raise DomainApiError("PLOT_CANDIDATE_MISMATCH", "候选缺少原流程和位置", status_code=409)
        from backend.services.task_flows.store import flow_store
        from backend.services.task_flows.plot_source_conflicts import PLOT_SOURCE_CONFLICTS_CONTRACT
        flow = flow_store().get(snapshot["flow_ref"]["id"], snapshot["flow_ref"]["revision"])
        reports_sources = any(node.config.get("source_conflicts") == PLOT_SOURCE_CONFLICTS_CONTRACT for node in flow.nodes)
        has_report = "plot_source_conflicts_v1" in snapshot["execution"]
        has_report_inputs = "plot_source_conflict_inputs" in snapshot["execution"]
        if reports_sources != has_report or reports_sources != has_report_inputs:
            raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "疑似冲突报告与原流程不一致，请重新生成", status_code=409)
        data = await load_plot_context(task, {}, inputs.model_dump(mode="json"), session=session)
        contexts = [data]
        report_context = None
        report_inputs = snapshot["execution"].get("plot_source_conflict_inputs")
        records = snapshot["execution"].get("writing_reads", [])
        if len(records) > 20:
            raise DomainApiError("PLOT_CANDIDATE_MISMATCH", "候选资料读取次数无效", status_code=409)
        for record in records:
            read_scope = record.get("scope", snapshot["scope"])
            if any(read_scope.get(field) != getattr(inputs, field) for field in ("novel_id", "target_type", "target_id", "expected_version")):
                raise DomainApiError("PLOT_CANDIDATE_MISMATCH", "资料读取位置与当前剧情不一致", status_code=409)
            loaded = await load_plot_context(task, record["parameters"], read_scope, session=session)
            if loaded["context_basis"] != record["basis"]:
                raise DomainApiError("PLOT_SOURCE_CHANGED", "生成剧情所用资料已变化，请保留草稿并重新生成", status_code=409)
            contexts.append(loaded)
            if report_inputs and report_inputs.get("parameters") == record["parameters"] and report_inputs.get("scope") == read_scope:
                report_context = loaded
        current_basis = merge_writing_reads([item["context_basis"] for item in contexts])
        if current_basis != basis.context_basis.model_dump(mode="json") or writing_candidate_fingerprint(task, inputs, current_basis, snapshot) != basis.input_fingerprint:
            raise DomainApiError("PLOT_SOURCE_CHANGED", "生成剧情所用资料或输入已变化", status_code=409)
        agent_reads = snapshot["execution"].get("agent_reads", [])
        if agent_reads:
            from backend.services.task_flows.book_tools import replay_book_reads
            await replay_book_reads(snapshot["scope"], agent_reads, session=session, protect=True)
        # 报告只核对实际送给报告节点的资料，不扩大到本次其他节点读到的内容。
        report = None
        if report_inputs is not None:
            from backend.services.task_flows.plot_source_conflicts import build_plot_source_conflicts
            if report_context is None:
                raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "疑似冲突报告缺少原资料，请重新生成", status_code=409)
            related_reads = report_inputs.get("agent_reads", [])
            read_hashes = {canonical_request_hash(read) for read in agent_reads}
            if any(canonical_request_hash(read) not in read_hashes for read in related_reads):
                raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "疑似冲突报告的读取记录不一致，请重新生成", status_code=409)
            previous_text = []
            if related_reads:
                from backend.services.task_flows.book_tools import replay_book_reads
                related = await replay_book_reads(snapshot["scope"], related_reads, session=session)
                previous_text = related["previous_text"]
            report = PlotSourceConflictReportV1.model_validate(build_plot_source_conflicts(
                [item.model_dump(mode="json") for item in request.candidate.source_conflicts] if request.candidate.source_conflicts is not None else None,
                plot_prompt_context(report_context["context"], inputs.target_type, target_id), previous_text,
            )).model_dump(mode="json")
            if report != snapshot["execution"].get("plot_source_conflicts_v1"):
                raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "疑似冲突报告已改变，请保留草稿并重新生成", status_code=422)
        elif request.candidate.source_conflicts is not None or "plot_source_conflicts_v1" in snapshot["execution"]:
            raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "此候选没有可核对的原报告，请重新生成", status_code=422)
        review = request.source_conflict_review
        if review is not None:
            if report is None or review.report.model_dump(mode="json") != report:
                raise DomainApiError("PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "请使用本次候选的原疑似冲突报告", status_code=422)
            expected_ids = {item["id"] for item in report["items"]}
            decision_ids = [decision.conflict_id for decision in review.decisions]
            if (len(decision_ids) != len(set(decision_ids)) or set(decision_ids) != expected_ids
                    or any(not decision.confirmed for decision in review.decisions)):
                raise DomainApiError("PLOT_SOURCE_CONFLICT_REVIEW_REQUIRED", "请逐项核对来源并确认当前候选，确认项不能缺少、重复或多出", status_code=422)
        elif report is not None and report["items"]:
            raise DomainApiError("PLOT_SOURCE_CONFLICT_REVIEW_REQUIRED", "请逐项核对疑似冲突的来源并确认当前候选", status_code=422)
        await protect_writing_sources({"guards": {key: doc for item in contexts for key, doc in item["guards"].items()},
                                       "fact_reads": [read for read in basis.context_basis.model_dump(mode="json")["reads"]
                                                      if read["kind"] in {"character_facts", "character_relation_facts"}]}, session=session)
        candidate = validate_plot_candidate(task, request.candidate.model_dump(mode="json"), data, confirming=True)
        fields = {"plot": candidate["plot"]}
        if not data["context"]["has_children"]:
            fields["planning"] = candidate["planning"]
        saved_content_hash = canonical_request_hash(fields)
        if review is not None:
            confirmed_content = review.confirmed_content.model_dump(mode="json")
            if confirmed_content["planning"] is None:
                confirmed_content.pop("planning")
            if canonical_request_hash(confirmed_content) != saved_content_hash:
                raise DomainApiError("PLOT_SOURCE_CONFLICT_CONTENT_CHANGED", "候选内容已修改，请重新核对来源并确认当前候选", status_code=422)
        _, _, source_hash = await load_plot_sources(inputs.novel_id, inputs.target_type, target_id, session=session, updated_fields=fields)
        fields["plot_source_fingerprint"] = source_hash
        document = await update_versioned_document(BaseRepository(COLLECTIONS[inputs.target_type]).collection, {"_id": ObjectId(target_id), "novel_id": ObjectId(inputs.novel_id)}, inputs.expected_version, fields, is_deleted=False, session=session)
        if document is None:
            raise DomainApiError("PLOT_VERSION_CONFLICT", "当前部分已修改，请保留剧情并刷新后比较", status_code=409)
        if inputs.target_type == "volume":
            from backend.api.default_routers.volume_router import serialize_volume
            public = serialize_volume(document).model_dump(mode="json", by_alias=True)
        else:
            from backend.services.novel.arc_contract import ArcReadV1, serialize_arc
            public = ArcReadV1.model_validate(serialize_arc(document)).model_dump(mode="json")
        result = {"operation": task, "ids": [target_id], "data": [public]}
        receipt = {**receipt_query, "request_hash": fingerprint.request_hash, "result": result, "created_at": get_utc_now()}
        if report is not None:
            receipt["source_conflict_review"] = {
                "report": report,
                "decisions": [decision.model_dump(mode="json") for decision in review.decisions] if review is not None else [],
                "saved_content_hash": saved_content_hash,
            }
        await receipts.insert_one(receipt, session=session)
        return result

    if session is not None:
        return await save(session)

    return await run_mongo_write_unit(save, "confirm_plot", require_transaction=True, retry_connection_error=True)


async def require_preparation_stage(novel_id: str, volume_id: str, kind: str, *, session: AsyncClientSession | None = None, allow_write_lock: bool = False) -> dict[str, Any]:
    """要求当前剧情有效且前一类资料已确认，允许该类没有参与实体。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        kind: factions、characters 或 locations。
        session: 可选确认事务。
        allow_write_lock: 地点确认已经持有当前事务写锁。
    Returns:
        当前卷快照。
    """
    chain, _, fingerprint = await load_plot_sources(novel_id, "volume", volume_id, session=session, allow_write_lock=allow_write_lock)
    volume = chain[-1][1]
    if not volume.get("plot", "").strip() or volume.get("plot_source_fingerprint") != fingerprint:
        raise DomainApiError("VOLUME_PLOT_REQUIRED", "请先确认当前卷的详细剧情", status_code=409)
    previous = {"factions": None, "characters": "factions", "locations": "characters"}[kind]
    if previous and volume.get("preparation", {}).get(previous) != plot_hash(volume["plot"]):
        raise DomainApiError("VOLUME_PREPARATION_REQUIRED", "请先确认上一类卷资料", status_code=409)
    return volume


async def record_preparation(novel_id: str, volume_id: str, kind: str, *, session: AsyncClientSession, location_ids: list[str] | None = None, allow_write_lock: bool = False) -> dict[str, Any]:
    """在调用方事务里保存当前剧情对应的准备标记和地点参与引用。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        kind: 当前资料类别。
        session: 已开启的确认事务。
        location_ids: 地点阶段审核后的正式 ID。
        allow_write_lock: 地点确认已经持有同一事务写锁。
    Returns:
        写后卷快照。
    """
    volume = await require_preparation_stage(novel_id, volume_id, kind, session=session, allow_write_lock=allow_write_lock)
    from backend.services.novel.writing_context import COLLECTIONS, protect_writing_sources
    chain, neighbors, _ = await load_plot_sources(novel_id, "volume", volume_id, session=session, allow_write_lock=allow_write_lock)
    guards = {(COLLECTIONS[part], str(doc["_id"])): doc for part, doc in chain}
    guards.update({("volumes", str(doc["_id"])): doc for doc in neighbors.values() if doc is not None})
    await protect_writing_sources({"guards": guards}, session=session)
    fields = {f"preparation.{kind}": plot_hash(volume["plot"])}
    if location_ids is not None:
        if len(location_ids) != len(set(location_ids)):
            raise DomainApiError("VOLUME_LOCATION_INVALID", "本卷地点不能重复", status_code=422)
        collection = BaseRepository("locations").collection
        queries = []
        for identity in location_ids:
            query = {"novel_id": ObjectId(novel_id), "location_id": identity, "is_deleted": False, "status": "active", "location_order_pending_token": None}
            document = await collection.find_one(query, session=session)
            if document is None:
                raise DomainApiError("VOLUME_LOCATION_UNAVAILABLE", "本卷地点不存在或已停用", status_code=409)
            queries.append({**query, "_id": document["_id"], "version": document["version"]})
        await touch_dependency_endpoint_guards(collection, queries, session=session)
        fields["location_ids"] = location_ids
    updated = await update_versioned_document(BaseRepository("volumes").collection, {"_id": ObjectId(volume_id), "novel_id": ObjectId(novel_id)}, volume["version"], fields, is_deleted=False, session=session)
    if updated is None:
        raise DomainApiError("VOLUME_PREPARATION_CHANGED", "当前卷已修改，请刷新后重新确认", status_code=409)
    return updated


async def confirm_preparation(novel_id: str, volume_id: str, kind: str, request: VolumePreparationConfirmV1, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
    """作者检查已有资料后确认当前阶段，不调用模型或新建档案。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        kind: 确认资料类别。
        request: 当前卷版本和可选地点参与列表。
        idempotency_key: 本次确认的重试键。
        session: 调用方的保存事务；提供时不另开事务。

    Returns:
        已更新的正式卷。
    """
    from backend.api.default_routers.volume_router import serialize_volume
    from backend.services.novel.writing_context import load_writing_parents

    if kind != "locations" and request.location_ids is not None:
        raise DomainApiError("VOLUME_PREPARATION_INVALID", "只有地点阶段可以修改本卷地点", status_code=422)
    fingerprint = build_idempotency_fingerprint(idempotency_key, {"novel_id": novel_id, "volume_id": volume_id, "kind": kind, **request.model_dump(mode="json")})
    receipts = BaseRepository("writing_confirmation_receipts").collection
    query = {"novel_id": ObjectId(novel_id), "operation": f"prepare_{kind}", "idempotency_key_hash": fingerprint.key_hash}

    async def save(session):
        await load_writing_parents(novel_id, "volume", volume_id, session=session)
        receipt = await receipts.find_one(query, session=session)
        if receipt:
            if receipt["request_hash"] != fingerprint.request_hash:
                raise DomainApiError("VOLUME_PREPARATION_CONFLICT", "同一确认键不能用于不同内容", status_code=409)
            return receipt["result"]
        volume = await require_preparation_stage(novel_id, volume_id, kind, session=session)
        if volume["version"] != request.expected_version:
            raise DomainApiError("VOLUME_VERSION_CONFLICT", "当前卷已修改，请刷新后重新确认", status_code=409)
        updated = await record_preparation(novel_id, volume_id, kind, session=session, location_ids=(request.location_ids if request.location_ids is not None else volume.get("location_ids", [])) if kind == "locations" else None)
        result = serialize_volume(updated).model_dump(mode="json", by_alias=True)
        await receipts.insert_one({**query, "request_hash": fingerprint.request_hash, "result": result, "created_at": get_utc_now()}, session=session)
        return result

    if session is not None:
        return await save(session)

    return await run_mongo_write_unit(save, "confirm_volume_preparation", require_transaction=True)


async def clear_preparation(novel_id: str, volume_id: str, kind: str, *, expected_version: int, location_ids: list[str] | None = None, session: AsyncClientSession) -> dict[str, Any]:
    """撤回准备确认，后续阶段也需要重新检查。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        kind: 撤回的势力、角色或地点阶段。
        expected_version: 作者确认时的卷版本。
        location_ids: 撤回地点确认时恢复的原地点选择。
        session: 调用方的保存事务。
    Returns:
        写后卷记录；不会把旧剧情的确认标记复制到新剧情。
    """
    from backend.services.novel.writing_context import load_writing_parents

    chain = await load_writing_parents(novel_id, "volume", volume_id, session=session)
    volume = chain[-1][1]
    if volume["version"] != expected_version:
        raise DomainApiError("VOLUME_VERSION_CONFLICT", "当前卷已修改，请刷新后重新检查", status_code=409)
    stages = ("factions", "characters", "locations")
    if kind not in stages or (location_ids is not None and kind != "locations"):
        raise DomainApiError("VOLUME_PREPARATION_INVALID", "准备阶段或地点选择不正确", status_code=422)
    preparation = {key: value for key, value in volume.get("preparation", {}).items() if key in stages[:stages.index(kind)]}
    fields = {"preparation": preparation}
    if location_ids is not None:
        if len(location_ids) != len(set(location_ids)):
            raise DomainApiError("VOLUME_LOCATION_INVALID", "本卷地点不能重复", status_code=422)
        collection = BaseRepository("locations").collection
        queries = []
        for identity in location_ids:
            query = {"novel_id": ObjectId(novel_id), "location_id": identity, "is_deleted": False, "status": "active", "location_order_pending_token": None}
            document = await collection.find_one(query, session=session)
            if document is None:
                raise DomainApiError("VOLUME_LOCATION_UNAVAILABLE", "原地点已不可用，请重新选择", status_code=409)
            queries.append({**query, "_id": document["_id"], "version": document["version"]})
        await touch_dependency_endpoint_guards(collection, queries, session=session)
        fields["location_ids"] = location_ids
    updated = await update_versioned_document(BaseRepository("volumes").collection, {"_id": ObjectId(volume_id), "novel_id": ObjectId(novel_id)}, expected_version, fields, is_deleted=False, session=session)
    if updated is None:
        raise DomainApiError("VOLUME_PREPARATION_CHANGED", "卷资料已变化，请重新检查", status_code=409)
    return updated
