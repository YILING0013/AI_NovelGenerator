"""现有 AI 任务的业务边界；步骤与提示词由流程文件管理。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.character_pydantic import CoreCharactersGenerateRequestV1, CoreCharactersResultSchemaV1
from backend.llm.schemas.character_relation_pydantic import CharacterRelationsGenerateRequestV1, CharacterRelationsResultSchemaV1
from backend.llm.schemas.faction_relation_pydantic import FactionRelationsGenerateRequestV1, FactionRelationsResultSchemaV1
from backend.llm.schemas.novel_pydantic import GenerateCoreFactionsRequestV2, CoreFactionsResultSchema
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesGenerateRequestV1, CoreWorldRulesResultV1
from backend.llm.schemas.volume_planning_pydantic import VolumeSkeletonGenerateRequestV1, VolumeSkeletonResultV1, VolumeLaunchGenerateRequestV1, VolumeLaunchPackageResultV1
from backend.llm.schemas.location_pydantic import VolumeLocationsGenerateRequestV1, VolumeLocationsResultV1
from backend.llm.schemas.item_pydantic import ItemsGenerateRequestV1, ItemsResultV1
from backend.services.llm.novel_generation_contract import AICreateNovelRequestV1, NovelCreateFieldsV1, NovelFieldRewriteRequestV1, NovelFieldRewriteCandidateV1
from backend.llm.schemas.writing_pydantic import WRITING_RESULTS, WRITING_SCOPE_FIELDS, WritingGenerateInputV1
from backend.llm.schemas.volume_entity_pydantic import VolumeEntityGenerateRequestV1, VolumeCharactersResultV1, VolumeFactionsResultV1
from backend.services.novel.plot_contract import PLOT_TASKS, PlotGenerateInputV1, PlotResultV1
from backend.services.novel.chapter_check_contract import (
    CHAPTER_CHECK_TASK, CHAPTER_CHECK_SCOPE_FIELDS, ChapterCheckInputV1, ChapterCheckResultV1,
    CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_SCOPE_FIELDS,
    ChapterItemOwnerCheckInputV1, ChapterItemOwnerCheckResultV1,
    CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_SCOPE_FIELDS,
    ChapterCharacterRelationStateCheckInputV1, ChapterCharacterRelationStateCheckResultV1, ChapterCharacterRelationStateCheckResultV2,
    CHAPTER_WORLD_RULES_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_SCOPE_FIELDS,
    ChapterWorldRulesCheckInputV1, ChapterWorldRulesCheckResultV1,
)


GENERATION_FIELDS = {*REASONING_FIELDS, "temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "system_prompt"}
SCOPE_FIELDS = {"novel_id", "volume_id", "target_field", "current_value", "context", "chat_history", "novel_expected_version", "volume_expected_version"}
TRANSPORT_FIELDS = {"use_stream"}
CONTENT_TASKS = set(WRITING_RESULTS) | set(PLOT_TASKS)
AGENT_TASKS = CONTENT_TASKS | {"create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai", "create_locations_for_volume_by_ai"}


def require_prepared_generation(flow):
    """检查结果使用的 AI 步骤确实接收整理结果，旧图仍可打开编辑。

    Args:
        flow: 已通过普通图校验的任务方案。
    Returns:
        无；缺少整理连线时给出可定位的错误。
    """
    from .contracts import FlowValidationError
    from .graph import template_fields
    if flow.task not in AGENT_TASKS:
        return

    def contains_prepared(value):
        return any(contains_prepared(child) for child in value.values()) if isinstance(value, dict) else bool(value)

    def inspect_graph(graph, inherited, path):
        nodes = {node.id: node for node in graph.nodes}
        output = next(node for node in graph.nodes if node.type == "output")
        dependencies = {node.id: {edge.source for edge in [*graph.edges, *graph.control_edges] if edge.target == node.id} for node in graph.nodes}
        needed = {output.id}
        pending = [output.id]
        while pending:
            for source in dependencies[pending.pop()] - needed:
                needed.add(source)
                pending.append(source)
        results = {}
        pending = [node.id for node in graph.nodes if node.id in needed]
        while pending:
            identity = next(name for name in pending if dependencies[name] <= results.keys())
            pending.remove(identity)
            node = nodes[identity]
            inputs = {name: False for name in node.inputs}
            for edge in graph.edges:
                if edge.target != identity:
                    continue
                value = results[edge.source].get(edge.source_port, False)
                # 打包后只取某个字段时，不能把同包中未读取的整理结果也算进去。
                for part in edge.source_path:
                    value = value.get(part, False) if isinstance(value, dict) else value
                inputs[edge.target_port] = value
            cfg = node.config
            if node.type == "input":
                values = {name: inherited.get(name, False) for name in node.outputs}
            elif node.type == "agent":
                values = {"prepared_context": True}
            elif node.type == "constant":
                values = {name: False for name in node.outputs}
            elif node.type == "context":
                values = {name: contains_prepared(inputs.get("prepared_context", False)) for name in node.outputs}
            elif node.type in {"template", "llm"}:
                base = cfg.get("template" if node.type == "template" else "prompt", "")
                used = template_fields(base)
                if cfg.get("review_evidence") == "writing_review_v1":
                    # 新契约由服务端把同一份整理意见及真实来源填入，避免再次拼接整份报告。
                    inputs["review_material"] = inputs.get("prepared_context", False)
                if node.type == "llm":
                    used |= template_fields(cfg.get("system_prompt") or "")
                prepared = any(contains_prepared(inputs.get(name, False)) for name in used)
                if node.type == "llm" and not prepared and cfg.get("format_suffix"):
                    suffixes = ["text_prompt"] if cfg.get("force_text_prompt") or cfg.get("mode") == "text" else ["text_prompt", "schema_prompt"]
                    suffix_prepared = []
                    for name in suffixes:
                        suffix = cfg.get(name, "")
                        suffix_prepared.append(any(contains_prepared(inputs.get(field, False)) for field in template_fields(suffix)))
                    prepared = all(suffix_prepared)
                if node.type == "llm" and not prepared:
                    raise FlowValidationError(f"{path}/{node.label or node.id} 的提示词没有使用资料整理结果，请补齐数据连线和占位符")
                values = {name: prepared for name in node.outputs}
            elif node.type in {"subflow", "foreach"}:
                child_inputs = dict(inputs)
                if node.type == "foreach":
                    child_inputs[cfg.get("item_input", "item")] = child_inputs.pop(cfg.get("items_input", "items"), False)
                    child_inputs[cfg.get("index_input", "index")] = False
                values = inspect_graph(graph.subflows[cfg["subflow_id"]], child_inputs, f"{path}/{node.label or node.id}")
                if node.type == "foreach":
                    values = {cfg.get("output_port", next(iter(node.outputs), "items")): values}
            elif node.type == "merge":
                mode = cfg.get("mode", "selected")
                prepared = all(contains_prepared(value) for value in inputs.values()) if mode == "selected" else contains_prepared(inputs)
                values = {cfg.get("output_port", next(iter(node.outputs), "value")): prepared}
            elif node.type == "condition":
                values = {name: inputs.get(name, False) for name in node.outputs}
            else:
                fields = cfg.get("fields" if node.type == "compose" else "output_fields")
                values = {name: inputs.get(source, False) for name, source in fields.items()} if fields is not None else inputs
                if node.type == "compose" and cfg.get("output_port"):
                    values = {cfg["output_port"]: values}
            results[identity] = values
        return results[output.id]

    if not contains_prepared(inspect_graph(flow, {}, flow.name)):
        raise FlowValidationError("当前方案缺少接入结果的 AI 整理资料节点，请采用新版副本或补齐连线")


@dataclass(frozen=True)
class TaskSpec:
    """一个已有业务按钮的输入、输出与候选标识。"""

    task: str
    label: str
    step: str
    request_model: type[BaseModel]
    result_model: type[BaseModel]
    schema_id: str
    schema_version: int = 1
    prompt_family: str = ""


TASKS = {
    item.task: item for item in (
        TaskSpec(CHAPTER_CHECK_TASK, "章后心理检查", "check_chapter_psychological_state", ChapterCheckInputV1, ChapterCheckResultV1, "chapter.psychological_state_check.result"),
        TaskSpec(CHAPTER_ITEM_OWNER_CHECK_TASK, "章后物品持有人检查", "check_chapter_item_owner", ChapterItemOwnerCheckInputV1, ChapterItemOwnerCheckResultV1, "chapter.item_owner_check.result"),
        TaskSpec(CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, "章后物品事实转交检查", "check_chapter_item_owner_facts", ChapterItemOwnerCheckInputV1, ChapterItemOwnerCheckResultV1, "chapter.item_owner_check.result", 2),
        TaskSpec(CHAPTER_WORLD_RULES_CHECK_TASK, "章后世界规则疑点检查", "check_chapter_world_rules", ChapterWorldRulesCheckInputV1, ChapterWorldRulesCheckResultV1, "chapter.world_rules_check.result"),
        TaskSpec(CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, "章后人物关系检查", "check_chapter_character_relation_state", ChapterCharacterRelationStateCheckInputV1, ChapterCharacterRelationStateCheckResultV1, "chapter.character_relation_state_check.result"),
        TaskSpec(CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, "章后人物关系事实检查", "check_chapter_character_relation_facts", ChapterCharacterRelationStateCheckInputV1, ChapterCharacterRelationStateCheckResultV2, "chapter.character_relation_state_check.result", 2),
        TaskSpec("create_novel_by_ai", "AI 创建小说", "novel_meta", AICreateNovelRequestV1, NovelCreateFieldsV1, "novel.create_candidate"),
        TaskSpec("rewrite_novel_field_by_ai", "小说字段改写", "novel_field", NovelFieldRewriteRequestV1, NovelFieldRewriteCandidateV1, "novel.field_rewrite_candidate", prompt_family="rewrite_novel_field"),
        TaskSpec("create_factions_by_ai", "核心势力", "create_core_factions", GenerateCoreFactionsRequestV2, CoreFactionsResultSchema, "faction.core_generation.result", 2),
        TaskSpec("create_characters_by_ai", "核心角色", "create_core_characters", CoreCharactersGenerateRequestV1, CoreCharactersResultSchemaV1, "character.core_generation.result"),
        TaskSpec("create_character_relations_by_ai", "人物关系", "create_character_relations", CharacterRelationsGenerateRequestV1, CharacterRelationsResultSchemaV1, "character.relation_generation.result"),
        TaskSpec("create_faction_relations_by_ai", "势力关系", "create_faction_relations", FactionRelationsGenerateRequestV1, FactionRelationsResultSchemaV1, "faction.relation_generation.result"),
        TaskSpec("create_world_rules_by_ai", "世界规则", "create_core_world_rules", CoreWorldRulesGenerateRequestV1, CoreWorldRulesResultV1, "world_rule.core_generation.result"),
        TaskSpec("create_volume_skeleton_by_ai", "卷骨架", "create_volume_skeleton", VolumeSkeletonGenerateRequestV1, VolumeSkeletonResultV1, "volume_skeleton_result"),
        TaskSpec("plan_volume_launch_by_ai", "开卷包", "create_volume_launch_package", VolumeLaunchGenerateRequestV1, VolumeLaunchPackageResultV1, "volume_launch_package_result"),
        TaskSpec("create_locations_for_volume_by_ai", "单卷地点", "create_locations_for_volume", VolumeLocationsGenerateRequestV1, VolumeLocationsResultV1, "volume_locations_result"),
        TaskSpec("create_characters_for_volume_by_ai", "卷内角色", "create_characters_for_volume", VolumeEntityGenerateRequestV1, VolumeCharactersResultV1, "volume_characters_result"),
        TaskSpec("create_factions_for_volume_by_ai", "卷内势力", "create_factions_for_volume", VolumeEntityGenerateRequestV1, VolumeFactionsResultV1, "volume_factions_result"),
        TaskSpec("create_items_by_ai", "物品", "create_items", ItemsGenerateRequestV1, ItemsResultV1, "item.generation.result"),
        *(TaskSpec(task, "生成本卷剧情" if kind == "volume" else "生成篇章剧情", task.removesuffix("_by_ai"), PlotGenerateInputV1, PlotResultV1, f"plot.{kind}.result") for task, kind in PLOT_TASKS.items()),
        *(TaskSpec(task, label, task.removesuffix("_by_ai"), WritingGenerateInputV1, WRITING_RESULTS[task], f"writing.{task.removesuffix('_by_ai')}.result") for task, label in (
            ("plan_arcs_by_ai", "生成篇章规划"), ("plan_scenes_by_ai", "生成场景规划"),
            ("plan_chapters_by_ai", "生成章节计划"), ("write_chapter_by_ai", "生成本章正文"),
        )),
    )
}


def validate_task_definition(flow):
    """检查根任务的候选字段与业务参数映射，再允许保存或调用模型。

    Args:
        flow: 当前任务的完整图；子流程使用自己的通用输入输出契约。
    Returns:
        已通过图结构和原业务结果映射检查的图。
    """
    from .contracts import FlowValidationError
    from .defaults import builtin_flow
    from .graph import port_schema, port_types_compatible, validate_flow, validate_values

    flow = validate_flow(flow)
    if flow.task not in TASKS:
        raise FlowValidationError("未知业务任务")
    spec = TASKS[flow.task]
    output = next(node for node in flow.nodes if node.type == "output")
    candidate_fields = output.config.get("candidate_fields", {key: key for key in output.inputs})
    result_schema = spec.result_model.model_json_schema()
    missing = set(result_schema.get("required", [])) - candidate_fields.keys()
    unknown = candidate_fields.keys() - result_schema["properties"].keys()
    if missing or unknown:
        raise FlowValidationError(f"任务结果字段映射不完整：缺少 {', '.join(sorted(missing)) or '无'}；未知 {', '.join(sorted(unknown)) or '无'}")
    for target, source in candidate_fields.items():
        if not port_types_compatible(output.inputs[source], result_schema["properties"][target], source_root=port_schema(output, output=False), target_root=result_schema):
            raise FlowValidationError(f"任务结果 {target} 的输入类型不符合原业务字段")
    scope_fields = CHAPTER_CHECK_SCOPE_FIELDS if flow.task == CHAPTER_CHECK_TASK else ({"novel_id"} | WRITING_SCOPE_FIELDS) if flow.task in CONTENT_TASKS else SCOPE_FIELDS
    if flow.task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        scope_fields = CHAPTER_ITEM_OWNER_CHECK_SCOPE_FIELDS
    if flow.task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
        scope_fields = CHAPTER_CHARACTER_RELATION_STATE_CHECK_SCOPE_FIELDS
    if flow.task == CHAPTER_WORLD_RULES_CHECK_TASK:
        scope_fields = CHAPTER_WORLD_RULES_CHECK_SCOPE_FIELDS
    allowed_parameters = set(spec.request_model.model_fields) - GENERATION_FIELDS - scope_fields - TRANSPORT_FIELDS
    context_definition = next((node for node in builtin_flow(flow.task).nodes if node.type == "context"), None)
    pending = [flow]
    while pending:
        graph = pending.pop()
        pending.extend(graph.subflows.values())
        for node in graph.nodes:
            if flow.task == CHAPTER_CHECK_TASK and node.type == "agent":
                raise FlowValidationError("章后心理检查不能使用 Agent 节点，请只使用选定章正文和原心理状态")
            if flow.task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK} and node.type == "agent":
                raise FlowValidationError("章后物品持有人检查不能使用 Agent 节点，请只使用选定章正文、物品和两名人物")
            if flow.task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK} and node.type == "agent":
                raise FlowValidationError("章后人物关系检查不能使用 Agent 节点，请只使用选定章正文、关系和两名人物")
            if flow.task == CHAPTER_WORLD_RULES_CHECK_TASK and node.type == "agent":
                raise FlowValidationError("章后世界规则检查不能使用 Agent 节点，请只使用选定章正文和规则")
            if graph is not flow and "candidate_check" in node.config:
                raise FlowValidationError("候选检查只能声明在主流程中")
            if graph is not flow and "source_conflicts" in node.config:
                raise FlowValidationError("双来源报告只能声明在主流程中")
            if node.type != "context":
                continue
            if context_definition is None:
                raise FlowValidationError("当前任务没有可读取的已有资料")
            context_parameters = allowed_parameters | ({"prepared_context"} if flow.task in AGENT_TASKS else set())
            if node.inputs.keys() - context_parameters:
                raise FlowValidationError(f"{node.label or node.id} 的输入必须使用当前任务的业务参数名")
            unknown = node.outputs.keys() - context_definition.outputs.keys()
            if unknown:
                raise FlowValidationError(f"{node.label or node.id} 的资料字段不存在：{', '.join(sorted(unknown))}")
            for name, schema in node.outputs.items():
                if not port_types_compatible(context_definition.outputs[name], schema, source_root=port_schema(context_definition, output=True), target_root=port_schema(node, output=True)):
                    raise FlowValidationError(f"{node.label or node.id} 的资料字段 {name} 类型不一致")
    checks = [node for node in flow.nodes if "candidate_check" in node.config]
    conflict_checks = [node for node in flow.nodes if "source_conflicts" in node.config]
    if conflict_checks and (flow.task not in PLOT_TASKS or len(conflict_checks) != 1):
        raise FlowValidationError("卷或篇章剧情只能声明一个双来源报告节点")
    if checks and (flow.task not in {"plan_arcs_by_ai", "plan_scenes_by_ai", "plan_chapters_by_ai"} or len(checks) != 1):
        raise FlowValidationError("三层规划任务只能声明一个候选检查节点")
    if flow.task == "create_novel_by_ai":
        return flow
    parameter_fields = output.config.get("parameter_fields", {})
    unknown = parameter_fields.keys() - allowed_parameters
    request_schema = spec.request_model.model_json_schema()
    required = set(request_schema.get("required", [])) & allowed_parameters
    missing = required - parameter_fields.keys()
    if unknown or missing:
        raise FlowValidationError(f"任务结果业务参数映射不完整：缺少 {', '.join(sorted(missing)) or '无'}；未知 {', '.join(sorted(unknown)) or '无'}")
    for target, source in parameter_fields.items():
        if not port_types_compatible(output.inputs[source], request_schema["properties"][target], source_root=port_schema(output, output=False), target_root=request_schema):
            raise FlowValidationError(f"业务参数 {target} 的输入类型不一致")
    if conflict_checks:
        from .graph import template_fields
        from .plot_source_conflicts import PLOT_SOURCE_CONFLICTS_SCHEMA
        report = conflict_checks[0]
        nodes = {node.id: node for node in flow.nodes}
        sources = {(edge.target, edge.target_port): (edge.source, edge.source_port, tuple(edge.source_path))
                   for edge in flow.edges}
        if (report.outputs.get("source_conflicts") != PLOT_SOURCE_CONFLICTS_SCHEMA
                or output.inputs.get(candidate_fields.get("source_conflicts")) != PLOT_SOURCE_CONFLICTS_SCHEMA
                or sources.get((output.id, candidate_fields.get("source_conflicts"))) != (report.id, "source_conflicts", ())):
            raise FlowValidationError("双来源报告必须使用 plot_source_conflicts_v1 格式并直接连接实际结果")
        if not {"writing_context", "prepared_context", "plot"} <= template_fields(report.config.get("prompt", "")):
            raise FlowValidationError("双来源报告提示词必须包含实际资料、整理结果和候选剧情")
        context_origin = sources.get((report.id, "writing_context"))
        prepared_origin = sources.get((report.id, "prepared_context"))
        if (not context_origin or context_origin[1:] != ("writing_context", ())
                or nodes[context_origin[0]].type != "context"):
            raise FlowValidationError("双来源报告必须直接使用服务端读取的 writing_context")
        if (not prepared_origin or prepared_origin[1:] != ("prepared_context", ())
                or nodes[prepared_origin[0]].type != "agent"):
            raise FlowValidationError("双来源报告必须直接使用相关 AI 整理完成的 prepared_context")
        context = nodes[context_origin[0]]
        if sources.get((context.id, "prepared_context")) != prepared_origin:
            raise FlowValidationError("双来源报告和资料节点必须使用同一份整理结果")
        plot_origin = sources.get((report.id, "plot"))
        if not plot_origin or plot_origin != sources.get((output.id, candidate_fields.get("plot"))):
            raise FlowValidationError("双来源报告必须使用结果实际采用的候选剧情")
        if set(context.inputs) - {"prepared_context"} != set(parameter_fields):
            raise FlowValidationError("双来源报告的资料参数必须与结果业务参数完整对应")
        for parameter, name in parameter_fields.items():
            context_default = context.values.get(parameter, context.inputs[parameter].get("default"))
            result_default = output.values.get(name, output.inputs[name].get("default"))
            if sources.get((context.id, parameter)) != sources.get((output.id, name)) or context_default != result_default:
                raise FlowValidationError(f"双来源报告的资料参数 {parameter} 必须与结果使用相同连线和默认值")
    if checks:
        review = checks[0]
        if review.config.get("review_evidence"):
            from .graph import template_fields
            from .review_evidence import REVIEW_INPUT_SCHEMA, REVIEW_OUTPUT_SCHEMA
            if review.outputs.get("review") != REVIEW_OUTPUT_SCHEMA or output.inputs.get("review") != REVIEW_OUTPUT_SCHEMA:
                raise FlowValidationError("候选检查的审核原句必须使用 writing_review_v1 的完整输出格式")
            if "review_material" not in review.inputs or not {"review_material", *candidate_fields.values()} <= template_fields(review.config.get("prompt", "")):
                raise FlowValidationError("审核提示词必须包含 review_material 原文资料和实际候选")
            if (review.inputs["review_material"] != REVIEW_INPUT_SCHEMA
                    or "review_material" in {*candidate_fields.values(), *parameter_fields.values(), *review.values}
                    or any(edge.target == review.id and edge.target_port == "review_material" for edge in flow.edges)):
                raise FlowValidationError("审核原句的 review_material 仅由服务端填入，不能用于候选、参数、常量或连线")
        if set(review.outputs) != {"review"} or not port_types_compatible(
            {"type": ["object", "null"]}, review.outputs["review"],
            source_root={}, target_root=port_schema(review, output=True),
        ):
            raise FlowValidationError("候选检查节点必须输出可为空的 review 意见")
        validate_values(review.outputs, {"review": None}, "候选检查", root=port_schema(review, output=True))
        if "review" in output.inputs:
            validate_values({"review": output.inputs["review"]}, {"review": None}, "候选检查结果", root=port_schema(output, output=False))
        nodes = {node.id: node for node in flow.nodes}
        # 只比较图中实际连线和默认值，不能拿另一份候选或资料代替结果检查。
        defaults = {}
        for node in flow.nodes:
            values = validate_values(node.inputs, {key: value for key, value in node.values.items() if key in node.inputs},
                                     node.label or node.id, allow_missing=True, root=port_schema(node, output=False))
            defaults.update({(node.id, name): ("value", values[name]) if name in values else ("missing",) for name in node.inputs})
        sources = dict(defaults)
        sources.update({(edge.target, edge.target_port):
                        ("edge", edge.source, edge.source_port, tuple(edge.source_path))
                        for edge in flow.edges})
        if sources.get((output.id, "review")) != ("edge", review.id, "review", ()):
            raise FlowValidationError("结果的 review 必须直接连接候选检查节点")
        for name in {*candidate_fields.values(), *parameter_fields.values(), "prepared_context"}:
            origin = sources.get((output.id, name))
            if name not in review.inputs or origin is None or sources[(review.id, name)] != origin or defaults[(review.id, name)] != defaults[(output.id, name)]:
                raise FlowValidationError(f"候选检查的 {name} 必须与结果使用相同连线或默认值")
            if name in {*candidate_fields.values(), "prepared_context"} and origin[0] != "edge":
                raise FlowValidationError(f"候选检查的 {name} 必须连接实际结果来源")
        prepared_origin = sources[(review.id, "prepared_context")]
        if nodes[prepared_origin[1]].type != "agent" or prepared_origin[2:] != ("prepared_context", ()):
            raise FlowValidationError("候选检查必须直接使用 AI 整理完成的 prepared_context")
        context_origin = sources.get((review.id, "writing_context"))
        if not context_origin or context_origin[0] != "edge" or context_origin[2:] != ("writing_context", ()) or nodes[context_origin[1]].type != "context":
            raise FlowValidationError("候选检查的 writing_context 必须直接连接实际资料节点")
        context = nodes[context_origin[1]]
        if sources.get((context.id, "prepared_context")) != prepared_origin or defaults.get((context.id, "prepared_context")) != defaults[(review.id, "prepared_context")]:
            raise FlowValidationError("候选检查和资料节点必须使用同一份整理结果")
        if set(context.inputs) - {"prepared_context"} != set(parameter_fields):
            raise FlowValidationError("候选检查的资料参数必须与结果业务参数完整对应")
        for parameter, name in parameter_fields.items():
            if sources.get((context.id, parameter)) != sources[(review.id, name)] or defaults[(context.id, parameter)] != defaults[(review.id, name)]:
                raise FlowValidationError(f"候选检查的资料参数 {parameter} 必须与结果使用相同连线或默认值")
    return flow
