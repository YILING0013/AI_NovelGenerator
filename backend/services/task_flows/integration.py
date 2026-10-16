"""让原有生成接口执行当前方案，并返回原页面可确认的候选。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from copy import deepcopy
import json
import logging
from typing import Any

from anyio import CancelScope
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.types import Send

from backend.api.error_protocol import DomainApiError, sse_error_payload, sse_event
from backend.llm.config import get_llm_config
from backend.runtime import bind_log_context
from backend.llm.schemas.writing_pydantic import WRITING_RESULTS, WRITING_TASKS, WRITING_SCOPE_FIELDS
from backend.llm.schemas.volume_entity_pydantic import VOLUME_ENTITY_TASKS
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.plot_contract import PLOT_TASKS
from backend.services.novel.chapter_check_contract import (
    CHAPTER_CHECK_TASK, CHAPTER_CHECK_SCOPE_FIELDS, ChapterCheckInputV1,
    CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_SCOPE_FIELDS, ChapterItemOwnerCheckInputV1,
    CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_SCOPE_FIELDS, ChapterCharacterRelationStateCheckInputV1,
    CHAPTER_WORLD_RULES_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_SCOPE_FIELDS, ChapterWorldRulesCheckInputV1,
)
from . import store as task_flow_store
from .candidate import compute_flow_candidate_fingerprint, compute_preparation_fingerprint
from .contracts import CachedNode, Flow, FlowRef, FlowValidationError, GraphRunRequest, Node
from .domain import load_task_context, validate_task_result, prepared_task_parameters
from .engine import execute_flow
from .graph import canonical_hash, flow_fingerprint, port_schema, validate_values
from .llm import FlowModels
from .agent_continuation import (
    FlowContinuationState, agent_continuation_progress, claim_agent_continuation,
    lookup_agent_continuation, release_agent_continuation, save_agent_continuation, update_agent_continuation,
)
from .registry import AGENT_TASKS, CONTENT_TASKS, GENERATION_FIELDS, SCOPE_FIELDS, TASKS, TRANSPORT_FIELDS, validate_task_definition, require_prepared_generation
from .review_evidence import build_review_material, verify_review_evidence
from .plot_source_conflicts import build_plot_source_conflicts


logger = logging.getLogger(__name__)
REPAIRABLE_TASKS = {"create_factions_by_ai", "create_volume_skeleton_by_ai", "plan_volume_launch_by_ai"}
FACTION_DESIGN_TASKS = {"create_factions_by_ai", "create_characters_by_ai", "create_faction_relations_by_ai",
                        "create_items_by_ai", "create_world_rules_by_ai", "create_volume_skeleton_by_ai"}


class TaskFlowStreamingResponse(StreamingResponse):
    """发送中断时，在原迭代任务内关闭流程，及时释放续跑占用。"""

    async def stream_response(self, send: Send) -> None:
        """兼容框架直接发送和子任务发送两条路径，保留原取消异常。

        Args:
            send: 当前请求的 ASGI 发送函数。
        Returns:
            无。
        """
        try:
            await super().stream_response(send)
        finally:
            # 不能交给生成器回收任务：日志 ContextVar 必须在原上下文退出。
            # 框架取消作用域已取消时，也让已有 finally 完成清理。
            with CancelScope(shield=True):
                await self.body_iterator.aclose()


def _candidate_validation_error(task: str, exc: Exception) -> DomainApiError | None:
    """只把已有候选的结构与业务后验错误交给响应修复。

    Args:
        task: 当前业务任务。
        exc: 最终候选校验抛出的异常。
    Returns:
        可修复且包含具体原因的公开错误，其他异常返回空值。
    """
    if task not in REPAIRABLE_TASKS:
        return None
    if isinstance(exc, DomainApiError) and exc.code == "CORE_FACTIONS_OUTPUT_INVALID":
        return DomainApiError(exc.code, exc.message, status_code=502, details={"message": exc.message})
    if isinstance(exc, ValidationError):
        message = "；".join(
            f"{'.'.join(str(part) for part in issue['loc']) or '$'}：{issue['msg']}"
            for issue in exc.errors(include_input=False, include_url=False)
        )
        return DomainApiError("TASK_FLOW_RESULT_INVALID", message[:2000], status_code=502, details={"message": message})
    if isinstance(exc, GenerationDomainError) and exc.code in {"VOLUME_SKELETON_OUTPUT_INVALID", "VOLUME_LAUNCH_OUTPUT_INVALID"}:
        return DomainApiError(exc.code, exc.message, status_code=502, details={"message": exc.message})
    return None


def prepare_flow(task: str, request: GraphRunRequest, scope: dict[str, Any], *, stream: bool = True) -> tuple[Flow, GraphRunRequest, FlowModels]:
    """检查任务图请求，并在响应前报告表单错误。

    Args:
        task: 原业务入口所属任务。
        request: 任务图请求。
        scope: 路径中的小说与卷位置，优先于请求体。
        stream: 当前路由是否允许文本流调用。
    Returns:
        已检查的图、统一请求与固定模型配置。
    """
    run = request.model_copy(deep=True)
    allowed_scope = CHAPTER_CHECK_SCOPE_FIELDS if task == CHAPTER_CHECK_TASK else ({"novel_id"} | WRITING_SCOPE_FIELDS) if task in CONTENT_TASKS else SCOPE_FIELDS
    if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        allowed_scope = CHAPTER_ITEM_OWNER_CHECK_SCOPE_FIELDS
    if task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
        allowed_scope = CHAPTER_CHARACTER_RELATION_STATE_CHECK_SCOPE_FIELDS
    if task == CHAPTER_WORLD_RULES_CHECK_TASK:
        allowed_scope = CHAPTER_WORLD_RULES_CHECK_SCOPE_FIELDS
    unknown_scope = set(run.scope) - allowed_scope
    if unknown_scope:
        raise DomainApiError("TASK_FLOW_SCOPE_INVALID", "操作位置包含未声明字段", field_errors={key: "不属于原页面的操作位置" for key in unknown_scope})
    run.scope.update(scope)
    if task in AGENT_TASKS:
        from .book_tools import normalize_agent_scope
        position_scope = normalize_agent_scope(run.scope, task=task)
        run.scope.update({key: position_scope[key] for key in ("reading_version", "reading_intent")})
    if task == CHAPTER_CHECK_TASK:
        try:
            run.scope = ChapterCheckInputV1.model_validate(run.scope).model_dump(mode="json")
        except ValidationError as exc:
            raise DomainApiError("CHAPTER_CHECK_INPUT_INVALID", "请选择有效的章修订和人物卷状态版本", status_code=422,
                                 details={"errors": exc.errors(include_input=False, include_url=False)}) from exc
    if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        try:
            run.scope = ChapterItemOwnerCheckInputV1.model_validate(run.scope).model_dump(mode="json")
            # 与确认入口使用同一种 ID 写法，避免合法大写来源造成依据冲突。
            run.scope["novel_id"] = run.scope["novel_id"].lower()
            for field in ("chapter_id", "revision_id"):
                run.scope["source"][field] = run.scope["source"][field].lower()
        except ValidationError as exc:
            raise DomainApiError("CHAPTER_ITEM_OWNER_CHECK_INPUT_INVALID", "请选择有效章修订、物品版本和不同的持有人", status_code=422,
                                 details={"errors": exc.errors(include_input=False, include_url=False)}) from exc
    if task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
        try:
            run.scope = ChapterCharacterRelationStateCheckInputV1.model_validate(run.scope).model_dump(mode="json")
            run.scope["novel_id"] = run.scope["novel_id"].lower()
            for field in ("chapter_id", "revision_id"):
                run.scope["source"][field] = run.scope["source"][field].lower()
        except ValidationError as exc:
            raise DomainApiError("CHAPTER_RELATION_STATE_CHECK_INPUT_INVALID", "请选择有效章修订、人物关系和原版本", status_code=422,
                                 details={"errors": exc.errors(include_input=False, include_url=False)}) from exc
    if task == CHAPTER_WORLD_RULES_CHECK_TASK:
        try:
            run.scope = ChapterWorldRulesCheckInputV1.model_validate(run.scope).model_dump(mode="json")
            run.scope["novel_id"] = run.scope["novel_id"].lower()
            for field in ("chapter_id", "revision_id"):
                run.scope["source"][field] = run.scope["source"][field].lower()
        except ValidationError as exc:
            raise DomainApiError("CHAPTER_WORLD_RULES_CHECK_INPUT_INVALID", "请选择有效章修订和一至五条不重复的世界规则及原版本", status_code=422,
                                 details={"errors": exc.errors(include_input=False, include_url=False)}) from exc
    if run.repair is not None and task not in REPAIRABLE_TASKS:
        raise DomainApiError("TASK_FLOW_REPAIR_UNSUPPORTED", "当前任务不支持响应修复")
    if (run.repair is not None and task == "create_volume_skeleton_by_ai"
            and run.repair.flow_snapshot.execution.get("relation_design_contract") != "unlocated_relation_profile_v1"):
        # 在创建 SSE 响应前拒绝旧合同，流式页面也能收到明确的 409。
        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求未区分关系设计与未定位状态，请保留草稿并重新生成", status_code=409)
    if run.agent_continuation is not None and (task not in AGENT_TASKS or run.repair is not None):
        raise DomainApiError("AGENT_CONTINUATION_UNSUPPORTED", "当前任务或响应修复不能续跑资料整理")
    if (run.repair is not None and task in FACTION_DESIGN_TASKS
            and run.repair.flow_snapshot.execution.get("faction_design_contract") != "unlocated_faction_profile_v1"):
        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求未区分势力设计与未定位资料，请保留草稿并重新生成", status_code=409)
    store = task_flow_store.flow_store()
    try:
        flow = store.get(run.flow_ref.id, run.flow_ref.revision) if run.flow_ref else store.get_default(task)
    except KeyError as exc:
        raise DomainApiError("TASK_FLOW_NOT_FOUND", "所选流程修订不存在", status_code=404) from exc
    if flow.task != task:
        raise DomainApiError("TASK_FLOW_TASK_MISMATCH", "所选方案不属于当前任务")
    try:
        model_config = get_llm_config()
    except (ValueError, RuntimeError) as exc:
        raise DomainApiError("LLM_PROVIDER_UNAVAILABLE", "模型配置无法读取，请检查设置", status_code=503) from exc
    try:
        flow = validate_task_definition(flow)
        require_prepared_generation(flow)
        chapter_version = next((node.config.get("chapter_context_version") for node in flow.nodes if node.type == "agent" and node.config.get("chapter_context_version")), None)
        if run.scope.get("chapter_context_version") not in {None, chapter_version} or run.scope.get("chapter_selection_complete"):
            raise DomainApiError("TASK_FLOW_SCOPE_INVALID", "本章资料模式由所选方案固定，最终选择须由本次整理完成", status_code=422)
        if chapter_version:
            run.scope["chapter_context_version"] = chapter_version
        start = next(node for node in flow.nodes if node.type == "input")
        values = {**start.values, **run.flow_inputs}
        missing = {key: "请填写此项" for key, schema in start.outputs.items() if schema.get("required", "default" not in schema) and key not in values and "default" not in schema}
        if missing:
            raise DomainApiError("TASK_FLOW_INPUT_INVALID", "开始表单有未填写的字段", field_errors=missing)
        run.flow_inputs = validate_values(start.outputs, values, start.label or start.id, root=port_schema(start, output=True))
        unknown_parameters = set(run.generation_params) - GENERATION_FIELDS
        if unknown_parameters:
            raise DomainApiError("TASK_FLOW_PARAMETERS_INVALID", "生成参数包含未声明字段", field_errors={key: "未知生成参数" for key in unknown_parameters})
        models = FlowModels(flow, model_config, run.generation_params, bool(stream and run.use_stream), repairing=run.repair is not None)
    except (FlowValidationError, ValidationError) as exc:
        raise DomainApiError("TASK_FLOW_INVALID", "流程或开始输入有误", details={"errors": [str(exc)]}) from exc
    run.flow_ref = FlowRef(id=flow.id, revision=flow.revision)
    return flow, run, models


async def task_flow_events(task: str, flow: Flow, run: GraphRunRequest, models: FlowModels, *, preflight=None) -> AsyncIterator[dict[str, Any]]:
    """执行图，复验结果并保留生成时的业务输入和方案依据。

    Args:
        task: 原业务任务。
        flow: 已固定的不可变修订。
        run: 已校验的开始输入与原页面位置。
        models: 已固定模型配置的节点调用器。
        preflight: 新层级任务在 HTTP 响应前完成的局部预检。
    Yields:
        原接口 SSE 所需的节点进度、错误或单一完成事件。
    """
    with bind_log_context(task=task, flow_id=flow.id):
        chapter_version = next((node.config.get("chapter_context_version") for node in flow.nodes if node.type == "agent" and node.config.get("chapter_context_version")), None)
        if chapter_version:
            run.scope["chapter_context_version"] = chapter_version
        if task in AGENT_TASKS:
            from .book_tools import normalize_agent_scope
            position_scope = normalize_agent_scope(run.scope, task=task)
            run.scope.update({key: position_scope[key] for key in ("reading_version", "reading_intent")})
        terminal_emitted = False
        execution = {"models": models.snapshot, "scope": run.scope, "source_refs_by_node": {}, "character_fact_reads": [], "character_relation_fact_reads": [], "item_fact_reads": [], "faction_fact_reads": []}
        if task == "create_characters_for_volume_by_ai":
            from backend.llm.schemas.volume_entity_pydantic import CHARACTER_PLAN_CONTRACT
            execution["character_candidate_contract"] = CHARACTER_PLAN_CONTRACT
        if task in AGENT_TASKS | {"plan_volume_launch_by_ai"}:
            # 旧节点缓存没有这份读取合同，不能带着全书摘要进入新的按位置生成。
            execution["reading_contract"] = "position_v1"
            execution["faction_reading_contract"] = "faction_facts_v1"
        if task == "create_factions_for_volume_by_ai":
            execution["faction_candidate_contract"] = "explicit_faction_values_v1"
        if task in FACTION_DESIGN_TASKS:
            execution["faction_design_contract"] = "unlocated_faction_profile_v1"
        if task in AGENT_TASKS | {CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
            execution["item_reading_contract"] = "item_facts_v1"
        if task in AGENT_TASKS | {"plan_volume_launch_by_ai", CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
            execution["relation_reading_contract"] = "character_relation_facts_v1"
        if task in {"create_character_relations_by_ai", "create_volume_skeleton_by_ai"}:
            # 无位置的关系状态只作未定位原文；旧缓存不能借本轮标签冒充新执行。
            execution["relation_design_contract"] = "unlocated_relation_profile_v1"
        if run.repair is not None:
            if task in AGENT_TASKS | {"plan_volume_launch_by_ai"} and run.repair.flow_snapshot.execution.get("reading_contract") != "position_v1":
                raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求未保存按位置读取依据，请保留草稿并重新生成", status_code=409)
            execution = deepcopy(run.repair.flow_snapshot.execution)
            if task == "create_characters_for_volume_by_ai" and execution.get("character_candidate_contract") != CHARACTER_PLAN_CONTRACT:
                raise DomainApiError("CHARACTER_CANDIDATE_CONTRACT_REQUIRED", "旧人物候选请保留原稿，使用新版方案重新生成", status_code=409)
            if task == "create_factions_for_volume_by_ai" and execution.get("faction_candidate_contract") != "explicit_faction_values_v1":
                raise DomainApiError("FACTION_CANDIDATE_CONTRACT_REQUIRED", "旧候选无法区分明确事实与默认值，请保留草稿并重新生成", status_code=409)
            if task in AGENT_TASKS | {"plan_volume_launch_by_ai"} and (execution.get("faction_reading_contract") != "faction_facts_v1"
                                        or "faction_fact_reads" not in execution):
                raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求没有势力事实读取依据，请保留草稿并重新生成", status_code=409)
            if task in AGENT_TASKS and (execution.get("item_reading_contract") != "item_facts_v1"
                                       or "item_fact_reads" not in execution):
                raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求没有物品事实读取依据，请保留草稿并重新生成", status_code=409)
            if task in AGENT_TASKS | {"plan_volume_launch_by_ai"} and (execution.get("relation_reading_contract") != "character_relation_facts_v1"
                                        or "character_relation_fact_reads" not in execution):
                raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求没有关系事实读取依据，请保留草稿并重新生成", status_code=409)
            if (task in AGENT_TASKS | {CHAPTER_CHECK_TASK, "plan_volume_launch_by_ai", "create_volume_skeleton_by_ai"}
                    and "character_fact_reads" not in execution):
                raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧修复请求没有人物事实读取依据，请保留草稿并重新生成", status_code=409)
            execution["repair_models"] = models.snapshot

        def remember_fact_reads(reads: list[dict[str, Any]]) -> None:
            """分别留下原人物、关系与物品读取，后续节点不能用新依据替换。"""
            for read in reads:
                if read.get("kind") == "character_facts":
                    execution["character_fact_reads"].append(deepcopy(read))
                elif read.get("kind") == "character_relation_facts":
                    if "character_relation_fact_reads" not in execution:
                        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧请求没有关系事实读取依据，请保留草稿并重新生成", status_code=409)
                    execution["character_relation_fact_reads"].append(deepcopy(read))
                elif read.get("kind") == "item_facts":
                    if "item_fact_reads" not in execution:
                        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧请求没有物品事实读取依据，请保留草稿并重新生成", status_code=409)
                    execution["item_fact_reads"].append(deepcopy(read))
                elif read.get("kind") == "faction_facts":
                    if "faction_fact_reads" not in execution:
                        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧请求没有势力事实读取依据，请保留草稿并重新生成", status_code=409)
                    execution["faction_fact_reads"].append(deepcopy(read))
                else:
                    raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "事实读取种类不受支持，请保留草稿并重新读取", status_code=409)
        context_count = 0
        writing_contexts = []
        prepared = None
        context_records = []
        review_context = None
        review_node = next((node for node in flow.nodes if node.config.get("candidate_check")), None)
        review_node_id = review_node.id if review_node else "review_coverage"
        prepared_instance = None
        review_context_node = None
        conflict_node = next((node for node in flow.nodes if node.config.get("source_conflicts")), None)
        conflict_context_node = None
        conflict_context = None
        conflict_inputs = None
        if review_node is not None:
            source = next(edge.source for edge in flow.edges if edge.target == review_node.id and edge.target_port == "prepared_context")
            prepared_instance = f"{flow.id}/{source}"
            source = next(edge.source for edge in flow.edges if edge.target == review_node.id and edge.target_port == "writing_context")
            review_context_node = next(node for node in flow.nodes if node.id == source)
        if conflict_node is not None:
            source = next(edge.source for edge in flow.edges if edge.target == conflict_node.id and edge.target_port == "prepared_context")
            prepared_instance = f"{flow.id}/{source}"
            source = next(edge.source for edge in flow.edges if edge.target == conflict_node.id and edge.target_port == "writing_context")
            conflict_context_node = next(node for node in flow.nodes if node.id == source)
        automatic_preparation = False
        execution["agent_reads"] = []
        # 令牌不进入候选依据；只有原任务、输入和模型配置可以接续这段对话。
        continuation_binding = canonical_hash({
            "task": task, "flow_ref": run.flow_ref.model_dump() if run.flow_ref else None,
            "definition": flow_fingerprint(flow), "scope": run.scope,
            "flow_inputs": run.flow_inputs, "generation_params": run.generation_params,
            "models": models.snapshot, "provider_config": models.config.model_dump(mode="json"),
            "relation_reading_contract": execution.get("relation_reading_contract"),
            "item_reading_contract": execution.get("item_reading_contract"),
            "faction_reading_contract": execution.get("faction_reading_contract"),
            **({"faction_candidate_contract": execution.get("faction_candidate_contract")} if task == "create_factions_for_volume_by_ai" else {}),
            **({"character_candidate_contract": execution.get("character_candidate_contract")} if task == "create_characters_for_volume_by_ai" else {}),
        })
        continuation_instance = None
        continuation_used = False
        completed_nodes: dict[str, dict[str, Any]] = {}
        resumed_nodes: dict[str, dict[str, Any]] = {}
        flow_state: FlowContinuationState | None = None
        flow_token: str | None = None
        graphs = [flow]
        has_agent = False
        while graphs:
            graph = graphs.pop()
            has_agent = has_agent or any(node.type == "agent" for node in graph.nodes)
            graphs.extend(graph.subflows.values())
        if task in CONTENT_TASKS:
            execution.pop("source_refs_by_node")
            execution["writing_reads"] = []

        async def validate_reads(additional_agent_reads: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            """每次发送和完成前重放原依据；不替换已发送历史、整理报告或冻结依据。"""
            if flow_state is not None and flow_token is not None:
                update_agent_continuation(flow_token, size=flow_state.size())
            for record in execution.get("writing_reads", []):
                reread = await load_task_context(task, record["parameters"], record.get("scope", run.scope), run.generation_params)
                if reread.data["context_basis"] != record["basis"]:
                    raise DomainApiError("WRITING_SOURCE_CHANGED", "生成期间规划、前文或查询结果已变化", status_code=409)
            from backend.services.novel.writing_context import revalidate_position_fact_reads
            await revalidate_position_fact_reads([*execution.get("character_fact_reads", []),
                                                  *execution.get("character_relation_fact_reads", []),
                                                  *execution.get("item_fact_reads", []),
                                                  *execution.get("faction_fact_reads", [])])
            for parameters, read_scope, previous in context_records:
                if task in AGENT_TASKS - CONTENT_TASKS or task == "plan_volume_launch_by_ai" or "fact_reads" in previous.data:
                    reread = await load_task_context(task, parameters, read_scope, run.generation_params)
                    if task == CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK and reread.data["fact_reads"] != previous.data["fact_reads"]:
                        # 重读已经发现事实变化时，不能只看主档版本后仍发送原值。
                        raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "检查期间章前关系事实已变化，请保留草稿并重新检查", status_code=409)
                    if task == CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK and reread.data["fact_reads"] != previous.data["fact_reads"]:
                        raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "检查期间章前物品状态已变化，请保留草稿并重新检查", status_code=409)
                    old = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in previous.data["source_refs"]]
                    current = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in reread.data["source_refs"]]
                    changed = (reread.data["content_fingerprint"] != previous.data["content_fingerprint"]
                               if getattr(previous.generation_input, "selection_mode", "manual") == "auto" else current != old)
                    if changed:
                        raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "整理资料期间来源已变化，请重新生成", status_code=409)
            agent_reads = [*execution["agent_reads"], *(additional_agent_reads or [])]
            if agent_reads:
                from .book_tools import replay_book_reads
                return await replay_book_reads(run.scope, agent_reads)
            return {}

        original_before_send = getattr(models, "before_send", None)
        models.before_send = validate_reads

        async def read_context(node: Node, parameters: dict[str, Any]) -> dict[str, Any]:
            nonlocal context_count, review_context, conflict_context, conflict_inputs
            chapter_report = parameters.get("prepared_context")
            parameters, context_scope = prepared_task_parameters(task, parameters, run.scope, parameters.get("prepared_context"))
            loaded = await load_task_context(task, parameters, context_scope, run.generation_params)
            if task == CHAPTER_WORLD_RULES_CHECK_TASK and loaded.data["rules"] != initial.data["rules"]:
                raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "检查期间所选规则已变化，请重新读取后检查", status_code=409)
            if node is review_context_node:
                review_context = loaded
            if node is conflict_context_node:
                conflict_context = loaded
                conflict_inputs = {"parameters": deepcopy(parameters), "scope": deepcopy(context_scope)}
            context_count += 1
            context_records.append((parameters, context_scope, loaded))
            if "fact_reads" in loaded.data:
                remember_fact_reads(loaded.data["fact_reads"])
            if task in CONTENT_TASKS:
                remember_fact_reads([read for read in loaded.data["context_basis"]["reads"]
                                     if read["kind"] in {"character_facts", "character_relation_facts", "item_facts", "faction_facts"}])
                if context_count > 19:
                    raise DomainApiError("WRITING_CONTEXT_LIMIT", "单次任务最多读取 19 次资料，请减少重复节点", status_code=422)
                execution["writing_reads"].append({"parameters": parameters, "basis": loaded.data["context_basis"], "scope": context_scope})
                writing_contexts.append(loaded.data)
            else:
                execution["source_refs_by_node"][f"{context_count}:{node.id}"] = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in loaded.data["source_refs"]]
            if chapter_version == 1 and chapter_report is not None:
                from .agent_contract import PreparedContextV1
                from .book_tools import assemble_chapter_context, replay_book_reads
                material = await replay_book_reads(run.scope, execution["agent_reads"])
                loaded.ports["writing_context"] = json.dumps(assemble_chapter_context(
                    loaded.data["context"], PreparedContextV1.model_validate(chapter_report), material,
                ), ensure_ascii=False)
            return {key: loaded.ports[key] for key in node.outputs}

        async def check_candidate(node: Node, inputs: dict[str, Any]) -> bool:
            # 保存和运行前已核对接线；这里使用原资料节点实际读取的数据，不在生成后换一份资料。
            output = next(item for item in flow.nodes if item.type == "output")
            assert review_context is not None
            loaded = review_context
            parameters = {name: inputs[port] for name, port in output.config["parameter_fields"].items() if port in inputs}
            parameters, scope = prepared_task_parameters(task, parameters, run.scope, inputs["prepared_context"])
            request = TASKS[task].request_model.model_validate({**parameters, **scope})
            if request != loaded.request or inputs["writing_context"] != loaded.ports["writing_context"]:
                raise FlowValidationError("候选检查的参数或资料与实际读取不一致")
            candidate = {name: inputs[port] for name, port in output.config["candidate_fields"].items()}
            try:
                await validate_task_result(task, candidate, loaded)
            except (DomainApiError, ValidationError):
                # 此处只决定是否调用审核模型。先让末端复查来源，再按原规则报告硬错误或预算错误。
                return False
            if node.config.get("review_evidence"):
                from .book_tools import replay_book_reads
                read_material = await replay_book_reads(run.scope, execution["agent_reads"]) if execution["agent_reads"] else {}
                inputs["review_material"] = build_review_material(
                    loaded.data["context"], read_material, candidate[WRITING_TASKS[task][1]], inputs["prepared_context"],
                )
            return True

        def check_review_evidence(node: Node, inputs: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
            # 原文由上面的服务端检查填入；缓存中的核验状态每次都重新计算。
            review = outputs.get("review")
            if review is None:
                return outputs
            output = next(item for item in flow.nodes if item.type == "output")
            candidate_port = output.config["candidate_fields"][WRITING_TASKS[task][1]]
            return {"review": verify_review_evidence(review, inputs[candidate_port], inputs["review_material"]["sources"])}

        async def organize(node: Node, inputs: dict[str, Any], instance: str) -> AsyncIterator[dict[str, Any]]:
            nonlocal prepared, continuation_used
            from .agent import execute_agent
            continuation = run.agent_continuation if instance == continuation_instance else None
            if instance in resumed_nodes or (run.agent_continuation is not None and not continuation_used and continuation is None):
                saved = resumed_nodes.get(instance)
                if saved is None or saved.get("agent_input_hash") != canonical_hash(inputs):
                    raise DomainApiError("AGENT_CONTINUATION_CHANGED", "前序资料节点或输入已变化，请重新整理", status_code=409)
                from .book_tools import replay_book_reads
                await replay_book_reads(run.scope, saved["agent_reads"])
                execution["agent_reads"].extend(deepcopy(saved["agent_reads"]))
                if prepared_instance is None or instance == prepared_instance:
                    prepared = deepcopy(saved["outputs"]["prepared_context"])
                    execution["prepared_context"] = prepared
                completed_nodes[instance] = deepcopy(saved)
                yield {"status": "done", "outputs": deepcopy(saved["outputs"])}
                return
            if continuation is not None:
                continuation_used = True
            first_read = len(execution["agent_reads"])
            async with aclosing(execute_agent(node, inputs, instance, models=models, scope=run.scope,
                                             reads=execution["agent_reads"], continuation=continuation,
                                             continuation_binding=continuation_binding,
                                             completed_nodes=completed_nodes, flow_state=flow_state, flow_token=flow_token)) as events:
                async for event in events:
                    value = event.get("data", event)
                    if "outputs" in value:
                        report = value["outputs"]["prepared_context"]
                        # 声明了检查的图，末端也使用同一份整理报告，不受其他 Agent 的完成顺序影响。
                        if prepared_instance is None or instance == prepared_instance:
                            prepared = report
                            execution["prepared_context"] = prepared
                        if task in WRITING_TASKS and report.get("missing_required"):
                            raise DomainApiError("WRITING_MATERIAL_MISSING", "请先补齐本次剧情必需的资料", status_code=409,
                                                 details={"missing": report["missing_required"], "prepared_context": report})
                    yield event
            completed_nodes[instance] = {"agent_input_hash": canonical_hash(inputs),
                                         "agent_reads": deepcopy(execution["agent_reads"][first_read:]),
                                         "outputs": {"prepared_context": deepcopy(report)}}
            if flow_state is not None:
                flow_state.agent = None
                update_agent_continuation(flow_token, size=flow_state.size())

        async def generate(node: Node, inputs: dict[str, Any], instance: str) -> AsyncIterator[dict[str, Any]]:
            if run.agent_continuation is not None and not continuation_used:
                # 原本完成的模型节点由服务端结果恢复；不能在续跑前偷偷重跑付费步骤。
                raise DomainApiError("AGENT_CONTINUATION_CHANGED", "原整理节点之前出现了需要重新生成的步骤，请重新整理", status_code=409)
            if flow_state is not None:
                fingerprint = canonical_hash({"node": node.model_dump(mode="json"), "inputs": inputs, "execution": execution})
                if flow_state.model_call is None:
                    flow_state.model_call = {"instance_path": instance, "input_fingerprint": fingerprint}
                elif (flow_state.model_call["instance_path"] != instance
                      or flow_state.model_call["input_fingerprint"] != fingerprint):
                    raise DomainApiError("AGENT_CONTINUATION_CHANGED", "未完成模型节点的输入或来源已变化，请重新生成", status_code=409)
                models.recovery_state, models.recovery_token = flow_state, flow_token
            async with aclosing(models.execute(node, inputs, instance)) as events:
                async for event in events:
                    value = event.get("data", event)
                    if (node is review_node if review_node else node.id == review_node_id) and "outputs" in value:
                        execution["coverage_review"] = value["outputs"].get("review")
                    yield event

        async def run_events() -> AsyncIterator[dict[str, Any]]:
            if run.repair is None:
                trusted = [CachedNode.model_validate({key: value[key] for key in CachedNode.model_fields})
                           for value in resumed_nodes.values() if "input_fingerprint" in value]
                async with aclosing(execute_flow(flow, run.flow_inputs, context=read_context, llm=generate, agent=organize,
                                                cached_nodes=run.cached_nodes, resumed_nodes=trusted, execution_context=execution,
                                                candidate_check=check_candidate, review_evidence=check_review_evidence)) as events:
                    async for event in events:
                        yield event
                return

            repair = run.repair
            snapshot = repair.flow_snapshot
            if (
                snapshot.flow_ref != run.flow_ref or snapshot.definition_hash != flow_fingerprint(flow)
                or snapshot.flow_inputs != run.flow_inputs or snapshot.scope != run.scope
            ):
                raise DomainApiError("TASK_FLOW_REPAIR_INPUT_CHANGED", "修复输入与原生成流程不一致，请重新生成", status_code=409)
            context = await load_task_context(task, repair.business_inputs, run.scope, run.generation_params)
            business_input = context.generation_input.model_dump(mode="json", exclude=TRANSPORT_FIELDS)
            if business_input != snapshot.business_input:
                raise DomainApiError("TASK_FLOW_REPAIR_INPUT_CHANGED", "修复输入与原业务参数不一致，请重新生成", status_code=409)
            source_values = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in context.data["source_refs"]]
            current_sources = {(ref["resource_type"], ref["id"]): ref["version"] for ref in source_values}
            original_sources = {(ref.resource_type, ref.id): ref.version for ref in repair.source_refs}
            if current_sources != original_sources:
                raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "生成依据已修改，请重新生成", status_code=409)
            context_records.append((repair.business_inputs, run.scope, context))
            try:
                await validate_task_result(task, repair.candidate, context)
            except Exception as exc:
                problem = _candidate_validation_error(task, exc)
                if problem is None:
                    raise
            else:
                raise DomainApiError("TASK_FLOW_REPAIR_NOT_NEEDED", "响应已通过校验，无须调用 AI 修复")

            metadata = {"node_id": "repair_response", "instance_path": f"{flow.id}/repair_response", "label": "repair_response"}
            yield {"event": "step", "data": {**metadata, "state": "running"}}
            async with aclosing(models.repair_result(repair.candidate, problem.details["message"], TASKS[task].result_model, {
                "business_input": business_input, "reference_material": context.ports,
            })) as events:
                async for event in events:
                    if event["status"] != "done":
                        yield {"event": "progress", "data": {**event, **metadata, "state": "running"}}
                        continue
                    yield {"event": "step", "data": {**metadata, "state": "done"}}
                    yield {"event": "done", "data": {"result": {"candidate": event["candidate"], "business_inputs": repair.business_inputs}}}

        try:
            if has_agent and run.repair is None:
                if run.agent_continuation is not None:
                    continuation_instance = lookup_agent_continuation(run.agent_continuation, binding=continuation_binding)
                    flow_state = claim_agent_continuation(run.agent_continuation, binding=continuation_binding, instance_path=continuation_instance)
                    flow_token = run.agent_continuation.token
                    resumed_nodes = deepcopy(flow_state.completed_nodes)
                    continuation_used = flow_state.agent is None
                else:
                    flow_state = FlowContinuationState()
                    checkpoint = save_agent_continuation(flow_state, binding=continuation_binding, size=flow_state.size(), reason="network", claimed=True)
                    flow_token = checkpoint["token"]
                completed_nodes = flow_state.completed_nodes
                yield {"event": "progress", "data": {"agent_continuation": agent_continuation_progress(flow_token)}}
                if flow_state.result is not None:
                    # 交付已校验的原候选及原依据；不重跑模型，不执行正式保存。
                    terminal_emitted = True
                    yield {"event": "done", "data": {"success": True, "result": deepcopy(flow_state.result)}}
                    return
                update_agent_continuation(flow_token, size=flow_state.size())
            if task in {CHAPTER_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK}:
                # 删掉资料节点也不能跳过付费前核验，绑定只来自原请求。
                initial = preflight or await load_task_context(task, {}, run.scope, run.generation_params)
                if "fact_reads" in initial.data:
                    remember_fact_reads(initial.data["fact_reads"])
                    context_records.append(({}, deepcopy(run.scope), initial))
                if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK}:
                    # 首次完整依据同时进入节点缓存签名，旧模型结果不能套上新人物版本。
                    execution["source_refs_by_node"]["preflight"] = [ref.model_dump(mode="json") for ref in initial.data["source_refs"]]
                if task == CHAPTER_WORLD_RULES_CHECK_TASK:
                    # 完整快照也参与节点缓存签名，不用新规则快照包装旧模型结果。
                    execution["world_rules_check_rules"] = deepcopy(initial.data["rules"])
            if task in VOLUME_ENTITY_TASKS:
                parameters = {key: value for key, value in run.flow_inputs.items() if key in TASKS[task].request_model.model_fields and key not in SCOPE_FIELDS | GENERATION_FIELDS | TRANSPORT_FIELDS}
                initial = preflight or await load_task_context(task, parameters, run.scope, run.generation_params)
                remember_fact_reads(initial.data.get("fact_reads", []))
                execution["source_refs_by_node"]["preflight"] = [ref.model_dump(mode="json") for ref in initial.data["source_refs"]]
                context_records.append((parameters, run.scope, initial))
            if task in CONTENT_TASKS:
                parameters = {key: value for key, value in run.flow_inputs.items() if key in TASKS[task].request_model.model_fields and key not in WRITING_SCOPE_FIELDS | {"novel_id"}}
                initial = preflight or await load_task_context(task, parameters, run.scope, run.generation_params)
                remember_fact_reads([read for read in initial.data["context_basis"]["reads"]
                                     if read["kind"] in {"character_facts", "character_relation_facts", "item_facts", "faction_facts"}])
                execution["writing_reads"].append({"parameters": parameters, "basis": initial.data["context_basis"]})
                writing_contexts.append(initial.data)
            async with aclosing(run_events()) as events:
                async for event in events:
                    if event["event"] != "done":
                        value = event["data"]
                        if event["event"] == "step" and value.get("state") == "done" and "outputs" in value and "input_fingerprint" in value:
                            instance = value["instance_path"]
                            completed_nodes[instance] = {**completed_nodes.get(instance, {}),
                                                         **{key: deepcopy(value[key]) for key in CachedNode.model_fields}}
                            if flow_state is not None:
                                if flow_state.model_call is not None and flow_state.model_call["instance_path"] == instance:
                                    flow_state.model_call = None
                                update_agent_continuation(flow_token, size=flow_state.size())
                        is_review = (value.get("instance_path") == f"{flow.id}/{review_node_id}" if review_node else value.get("node_id") == review_node_id)
                        if event["event"] == "step" and is_review and value.get("state") == "done":
                            # 命中缓存也恢复检查意见，候选依据不能随是否命中缓存改变。
                            review = deepcopy(event["data"]["outputs"].get("review"))
                            if isinstance(review, dict) and (review_node is None or not review_node.config.get("review_evidence")):
                                # 旧自定义格式不能靠同名字段冒充服务端核验，定义和意见原文仍保留。
                                for issue in review.get("issues", []):
                                    if isinstance(issue, dict):
                                        issue.pop("verification", None)
                            execution["coverage_review"] = review
                        if event["event"] == "error":
                            terminal_emitted = True
                            if flow_state is not None:
                                if value.get("code") in {"AGENT_ROUND_BUDGET_EXCEEDED", "AGENT_TOOL_BUDGET_EXCEEDED"}:
                                    # 再次耗尽预算须重新选择；旧请求不能在丢失提示后再次追加轮数。
                                    checkpoint = save_agent_continuation(flow_state, binding=continuation_binding,
                                        size=flow_state.size(), previous_token=flow_token, reason="budget", claimed=True)
                                    flow_token = checkpoint["token"]
                                value.setdefault("details", {})["agent_continuation"] = release_agent_continuation(flow_token, size=flow_state.size())
                                flow_token = None
                        yield event
                        continue
                    if run.agent_continuation is not None and not continuation_used:
                        raise DomainApiError("AGENT_CONTINUATION_NODE_MISSING", "本次流程没有到达原资料整理节点，请重新整理", status_code=409)
                    final = event["data"]["result"]
                    context = None
                    if task != "create_novel_by_ai":
                        final_parameters, final_scope = prepared_task_parameters(task, final["business_inputs"], run.scope, prepared)
                        context = await load_task_context(task, final_parameters, final_scope, run.generation_params)
                        business_input = context.generation_input.model_dump(mode="json", exclude=TRANSPORT_FIELDS)
                    else:
                        business_input = run.model_dump(mode="json", exclude={"cached_nodes", "use_stream"})
                        # 确认 DTO 保留完整新请求格式，缓存永远不参与候选依据。
                        business_input["cached_nodes"] = []
                        business_input["use_stream"] = run.use_stream
                    if task == CHAPTER_WORLD_RULES_CHECK_TASK and context.data["rules"] != initial.data["rules"]:
                        raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "检查期间所选规则已变化，请重新读取后检查", status_code=409)
                    if task == CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK and context.data["fact_reads"] != initial.data["fact_reads"]:
                        # 来源短暂改变后恢复，也不能把末端新读到的事实贴到原检查依据上。
                        raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "检查期间章前关系事实已变化，请保留草稿并重新检查", status_code=409)
                    if task == CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK and context.data["fact_reads"] != initial.data["fact_reads"]:
                        raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "检查期间章前物品状态已变化，请保留草稿并重新检查", status_code=409)
                    refs = context.data["source_refs"] if context else []
                    automatic_preparation = bool(context and task in AGENT_TASKS - CONTENT_TASKS and getattr(context.generation_input, "selection_mode", "manual") == "auto")
                    source_values = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in refs]
                    read_material = await validate_reads()
                    if task in CONTENT_TASKS:
                        from backend.services.novel.writing_generation import merge_writing_reads, writing_candidate_fingerprint
                        writing_contexts.append(context.data)
                        content_basis = merge_writing_reads([loaded["context_basis"] for loaded in writing_contexts])
                        source_values = list({(ref["resource_type"], ref["id"]): ref for loaded in writing_contexts for ref in loaded["source_refs"]}.values())
                    else:
                        final_versions = {(ref["resource_type"], ref["id"]): ref["version"] for ref in source_values}
                        if run.repair is not None and final_versions != {(ref.resource_type, ref.id): ref.version for ref in run.repair.source_refs}:
                            raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "修复期间资料已修改，请重新生成", status_code=409)
                        for sources in ([] if prepared is not None and task not in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK} else execution["source_refs_by_node"].values()):
                            if (task in VOLUME_ENTITY_TASKS or task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK}) and final_versions != {(source["resource_type"], source["id"]): source["version"] for source in sources}:
                                raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "生成期间档案或卷状态已新增、删除或修改，请重新生成", status_code=409)
                            for source in sources:
                                identity = (source["resource_type"], source["id"])
                                if identity not in final_versions:
                                    raise DomainApiError("TASK_FLOW_RESULT_SCOPE_MISMATCH", "结果节点的业务参数没有包含流程读取的资料，请检查参数连线")
                                if final_versions[identity] != source["version"]:
                                    raise DomainApiError("CANDIDATE_SOURCE_CHANGED", "生成期间资料已修改，请重新生成", status_code=409)
                    if task in PLOT_TASKS:
                        if conflict_node is not None:
                            # 原资料和工具读取已经重查；缓存、续跑及可编辑错误都从同一处核对原句。
                            related_reads = completed_nodes[prepared_instance]["agent_reads"]
                            if related_reads != execution["agent_reads"]:
                                from .book_tools import replay_book_reads
                                read_material = await replay_book_reads(run.scope, related_reads) if related_reads else {}
                            execution["plot_source_conflict_inputs"] = {**conflict_inputs, "agent_reads": deepcopy(related_reads)}
                            execution["plot_source_conflicts_v1"] = build_plot_source_conflicts(
                                final["candidate"].get("source_conflicts"), json.loads(conflict_context.ports["writing_context"]),
                                read_material.get("previous_text", []),
                            )
                        else:
                            # 旧自定义图没有声明实际来源接线；不能把同名输出当成已核对报告。
                            final["candidate"]["source_conflicts"] = None
                            execution.pop("plot_source_conflict_inputs", None)
                            execution.pop("plot_source_conflicts_v1", None)
                    snapshot = {
                        "flow_ref": run.flow_ref.model_dump(mode="json"),
                        "definition_hash": flow_fingerprint(flow),
                        "flow_inputs": run.flow_inputs,
                        "scope": run.scope,
                        "business_input": business_input,
                        "execution": execution,
                    }
                    spec = TASKS[task]
                    common = {"workflow": task, "step": spec.step, "schema_id": spec.schema_id, "schema_version": spec.schema_version}
                    basis = {
                        **common, "novel_id": run.scope.get("novel_id"),
                        "source_refs": source_values,
                        "flow_ref": snapshot["flow_ref"], "flow_snapshot": snapshot,
                        "input_fingerprint": (writing_candidate_fingerprint(task, business_input, content_basis, snapshot) if task in CONTENT_TASKS else
                                              compute_preparation_fingerprint(task, business_input, context.data["content_fingerprint"], snapshot) if automatic_preparation else
                                              compute_flow_candidate_fingerprint(task, business_input, refs, snapshot)),
                    }
                    if task in AGENT_TASKS - CONTENT_TASKS:
                        basis["content_fingerprint"] = context.data["content_fingerprint"] if automatic_preparation else None
                    if task in CONTENT_TASKS:
                        basis.update(generation_input=business_input, context_basis=content_basis)
                    if task in {"create_world_rules_by_ai", "create_volume_skeleton_by_ai", "plan_volume_launch_by_ai", "create_locations_for_volume_by_ai", "create_items_by_ai"} or task in VOLUME_ENTITY_TASKS:
                        basis["generation_input"] = business_input
                    envelope = {**common, "candidate": final["candidate"], "basis": basis, **(context.extra if context else {})}
                    if task == "create_characters_for_volume_by_ai":
                        envelope["contract"] = execution["character_candidate_contract"]
                    if prepared is not None and task in CONTENT_TASKS:
                        envelope.update(prepared_context=prepared, coverage_review=execution.get("coverage_review"))
                    try:
                        envelope["candidate"] = await validate_task_result(task, final["candidate"], context)
                    except Exception as exc:
                        if task in PLOT_TASKS and isinstance(exc, DomainApiError) and exc.code == "PLOT_PLANNING_INVALID":
                            # 来源已复查。保留剧情并明确使用原规划，不把错层级字段映射成新规划。
                            retained = {**final["candidate"], "planning": deepcopy(context.data["chain"][-1][1].get("planning") or {})}
                            envelope["candidate"] = await validate_task_result(task, retained, context)
                            exc.message = "配套规划格式不正确，已保留原规划，请审核剧情"
                            exc.details["editable_candidate"] = envelope
                            raise
                        if task in WRITING_TASKS and isinstance(exc, DomainApiError) and exc.code in {"WRITING_RESULT_BUDGET_MISSING", "WRITING_RESULT_BUDGET_EXCEEDED"}:
                            # 此时结构和来源已核对，只让作者编辑原候选；保存仍须通过全部检查。
                            envelope["candidate"] = WRITING_RESULTS[task].model_validate(final["candidate"]).model_dump(mode="json")
                            exc.details["editable_candidate"] = envelope
                            raise
                        problem = _candidate_validation_error(task, exc)
                        if problem is None:
                            raise
                        # 仅保留浏览器已有的生成资料，不保存候选，也不自动重跑模型。
                        problem.details["repair"] = {
                            "candidate": final["candidate"], "business_inputs": final["business_inputs"],
                            "source_refs": source_values, "flow_snapshot": snapshot,
                        }
                        raise problem from exc
                    logger.info("[任务生成完成]")
                    if flow_state is not None:
                        flow_state.result = deepcopy(envelope)
                        flow_state.completed_nodes = {}
                        update_agent_continuation(flow_token, size=flow_state.size())
                    terminal_emitted = True
                    yield {"event": "done", "data": {"success": True, "result": envelope}}
        except (asyncio.CancelledError, GeneratorExit):
            if not terminal_emitted:
                logger.info("[任务生成取消]")
            raise
        except Exception as exc:
            terminal_emitted = True
            data = sse_error_payload(exc, fallback_message="流程执行失败")
            if flow_state is not None and flow_token is not None:
                data.setdefault("details", {})["agent_continuation"] = release_agent_continuation(flow_token, size=flow_state.size())
                flow_token = None
            yield {"event": "error", "data": data}
        finally:
            if flow_token is not None:
                release_agent_continuation(flow_token, size=flow_state.size())
            models.before_send = original_before_send
            models.recovery_state = models.recovery_token = None


async def generate_task_flow(task: str, request: GraphRunRequest, *, scope: dict[str, Any] | None = None, stream: bool = False, on_event: Callable[[dict], Awaitable[None]] | None = None) -> Any:
    """原生成路由共用的唯一执行入口，不保存正式业务数据。

    Args:
        task: 原业务任务。
        request: 任务图请求。
        scope: 路径指定的小说、卷位置。
        stream: 原路由是否返回 SSE。
        on_event: 可选的进度记录；供小说助手持久化原任务状态。
    Returns:
        原候选信封或页面持有的 SSE 响应。
    """
    flow, run, models = prepare_flow(task, request, scope or {}, stream=stream)
    preflight = None
    if task == "create_factions_by_ai":
        from backend.db.repositories.faction_repository import faction_repo

        parameters = {key: value for key, value in run.flow_inputs.items() if key in TASKS[task].request_model.model_fields and key not in SCOPE_FIELDS | GENERATION_FIELDS | TRANSPORT_FIELDS}
        try:
            faction_request = TASKS[task].request_model.model_validate({key: value for key, value in {**parameters, **run.scope}.items() if key in TASKS[task].request_model.model_fields})
        except ValidationError as exc:
            raise DomainApiError("FACTION_INPUT_INVALID", "请先选择已保存的作品，并填写有效的势力数量", status_code=422) from exc
        factions = await faction_repo.get_active_core_factions(faction_request.novel_id)
        # 单个势力没有关系对象是正常起步；固定后的实际输入也进入候选依据。
        # 已有节点或修复请求保留原输入，不能给旧模型结果换一套要求。
        if not run.cached_nodes and run.repair is None and run.flow_inputs.get("faction_count") == 1 and (not factions or not run.flow_inputs.get("connect_to_existing")):
            run.flow_inputs["independent_faction_count"] = 1
            parameters["independent_faction_count"] = 1
        preflight = await load_task_context(task, parameters, run.scope, run.generation_params)
    if task in {CHAPTER_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK}:
        preflight = await load_task_context(task, {}, run.scope, run.generation_params)
    if task in VOLUME_ENTITY_TASKS:
        parameters = {key: value for key, value in run.flow_inputs.items() if key in TASKS[task].request_model.model_fields and key not in SCOPE_FIELDS | GENERATION_FIELDS | TRANSPORT_FIELDS}
        try:
            preflight = await load_task_context(task, parameters, run.scope, run.generation_params)
        except ValidationError as exc:
            raise DomainApiError("VOLUME_ENTITY_INPUT_INVALID", "请选择当前卷版本和有效的档案数量", status_code=422) from exc
    if task in CONTENT_TASKS:
        # 图可以改线或删掉 context；付费调用前仍必须通过当前位置检查。
        parameters = {key: value for key, value in run.flow_inputs.items() if key in TASKS[task].request_model.model_fields and key not in WRITING_SCOPE_FIELDS | {"novel_id"}}
        preflight = await load_task_context(task, parameters, run.scope, run.generation_params)
    if stream:
        async def body() -> AsyncIterator[str]:
            async with aclosing(task_flow_events(task, flow, run, models, preflight=preflight)) as events:
                async for event in events:
                    yield sse_event(event["event"], event["data"])
        return TaskFlowStreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    async with aclosing(task_flow_events(task, flow, run, models, preflight=preflight)) as events:
        async for event in events:
            if on_event is not None:
                await on_event(event)
            if event["event"] == "done":
                return event["data"]["result"]
            if event["event"] == "error":
                data = event["data"]
                error = DomainApiError(data.get("code", "TASK_FLOW_FAILED"), data.get("message", "流程执行失败"), status_code=data.get("status_code", 502), field_errors=data.get("field_errors"), details={**data.get("details", {}), "node_id": data.get("node_id"), "instance_path": data.get("instance_path"), "partial_outputs": data.get("partial_outputs", {})})
                # 原异常已在 error 事件生成前记录，HTTP 边界只需补充失败位置。
                error._log_recorded = True
                raise error
    raise DomainApiError("TASK_FLOW_RESULT_MISSING", "流程没有返回候选", status_code=502)
