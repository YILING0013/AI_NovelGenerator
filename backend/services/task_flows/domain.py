"""将流程的资料输入与最终结果接到已有业务校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from backend.api.error_protocol import DomainApiError
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.llm.prompts.prompt_selector import PROMPT_TEMPLATE_FIELDS
from backend.llm.exceptions import LLMSchemaError
from backend.services.llm.character_generation_service import CharacterGenerationService
from backend.services.llm.faction_generation_contract import (
    build_core_factions_generation_strategy,
    build_core_factions_source_refs,
    compact_existing_core_factions,
    format_faction_novel_text,
)
from backend.services.llm.faction_relation_generation_service import FactionRelationGenerationService
from backend.services.llm.item_generation_context import load_item_generation_context
from backend.services.llm.item_generation_contract import build_items_generation_input
from backend.services.llm.item_generation_service import ItemGenerationService
from backend.services.llm.novel_generation_contract import (
    NOVEL_REWRITE_FIELD_LABELS,
    canonicalize_novel_rewrite_input,
    compact_rewrite_context,
    format_rewrite_history,
    format_rewrite_value,
)
from backend.services.llm.volume_location_generation_service import VolumeLocationGenerationService
from backend.services.llm.volume_planning_generation_service import VolumePlanningGenerationService
from backend.services.llm.world_rule_generation_contract import build_core_world_rules_generation_input
from backend.services.llm.world_rule_generation_service import WorldRuleGenerationService
from backend.services.novel.faction_service import FactionService
from backend.services.task_flows.registry import TASKS
from backend.llm.schemas.writing_pydantic import WRITING_TASKS
from backend.llm.schemas.volume_entity_pydantic import VOLUME_ENTITY_TASKS, VolumeEntityGenerationInputV1
from backend.services.llm.volume_entity_generation_service import load_volume_entity_context, validate_volume_entity_candidates
from backend.services.novel.plot_contract import PLOT_TASKS
from backend.services.novel.chapter_check_contract import (
    CHAPTER_CHECK_TASK, ChapterCheckInputV1,
    CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, ChapterItemOwnerCheckInputV1,
    CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, ChapterCharacterRelationStateCheckInputV1,
    CHAPTER_WORLD_RULES_CHECK_TASK, ChapterWorldRulesCheckInputV1,
)


@dataclass
class TaskContext:
    """一次资料读取使用的业务输入、正式来源和校验数据。"""

    request: Any
    generation_input: Any
    data: dict[str, Any]
    ports: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


def prepared_task_parameters(task: str, parameters: dict[str, Any], scope: dict[str, Any], prepared: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """把已核对的整理结果接到原业务输入，操作位置始终来自路由。

    Args:
        task: 当前生成任务。
        parameters: 作者输入或结果节点的业务参数。
        scope: 路由固定的位置。
        prepared: 本轮 Agent 实际完成的整理结果。
    Returns:
        最终业务参数和资料选择范围。
    """
    if task in {CHAPTER_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK}:
        # 图中的资料和结果端口均无权更换原请求的章修订或检查目标。
        return {}, dict(scope)
    values, actual_scope = dict(parameters), dict(scope)
    values.pop("prepared_context", None)
    if prepared is None:
        return values, actual_scope
    from .agent_contract import PreparedContextV1
    from .book_tools import normalize_agent_scope
    report = PreparedContextV1.model_validate(prepared)
    if (report.target.reading_version != 1 or not report.target.reading_intent
            or report.target.model_dump(mode="json") != normalize_agent_scope(scope, task=task)):
        raise DomainApiError("AGENT_SCOPE_CHANGED", "整理报告的读取位置已变化，请保留草稿并重新整理", status_code=409)
    selected = report.selected_entities.model_dump(mode="json") if hasattr(report.selected_entities, "model_dump") else report.selected_entities
    counts = report.new_counts.model_dump(mode="json")
    if task in WRITING_TASKS:
        actual_scope["selected_entities"] = selected
        if scope.get("chapter_context_version") == 1:
            # 原作者选择留在 run.scope；完成后的空集合不再当作尚未选择。
            for field, identities in scope.get("selected_entities", {}).items():
                if set(identities) - set(selected[field]):
                    raise DomainApiError("WRITING_MATERIAL_MISSING", "整理结果遗漏作者明确选择的资料，请继续整理", status_code=409)
            actual_scope["chapter_selection_complete"] = True
        if task != "write_chapter_by_ai":
            if not report.remaining:
                values["count"] = 0
            elif values.get("count_mode", "fixed") == "auto":
                values["count"] = report.suggested_count
    elif task in VOLUME_ENTITY_TASKS:
        kind = "character" if task == "create_characters_for_volume_by_ai" else "faction"
        if values.get("selection_mode", "auto") == "auto":
            values.update(selection_mode="auto", selected_existing_ids=selected[f"{kind}_ids"], new_count=counts[kind])
    elif task == "create_locations_for_volume_by_ai":
        if values.get("selection_mode", "auto") == "auto":
            values.update(selection_mode="auto", selected_existing_location_ids=selected["location_ids"], location_count=counts["location"])
    return values, actual_scope


async def load_task_context(task: str, parameters: dict[str, Any], scope: dict[str, Any], generation_params: dict[str, Any]) -> TaskContext:
    """读取当前业务任务资料，不调用模型或保存候选。

    Args:
        task: 原页面的业务任务。
        parameters: 图中传到资料节点的业务参数。
        scope: 原页面提供的小说、卷及字段位置。
        generation_params: 本次公共模型参数。
    Returns:
        资料输出端口与末端业务校验所需的原始上下文。
    """
    if task == CHAPTER_CHECK_TASK:
        from backend.services.novel.chapter_check_service import load_chapter_check_context
        request = ChapterCheckInputV1.model_validate(scope)
        data = await load_chapter_check_context(request)
        return TaskContext(request, request, data, {
            "chapter_content": data["chapter_content"],
            "current_psychological_state": data["psychological_state"],
            "character_id": data["target"]["character_id"],
            "character_name": data["character_name"],
        }, {"check_target": data["target"]})
    if task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
        from backend.services.novel.chapter_check_service import (
            load_chapter_character_relation_state_check_context, load_chapter_character_relation_facts_check_context,
        )
        request = ChapterCharacterRelationStateCheckInputV1.model_validate(scope)
        data = (await load_chapter_character_relation_facts_check_context(request) if task == CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK
                else await load_chapter_character_relation_state_check_context(request))
        extra = {"check_target": data["target"]}
        if task == CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK:
            extra["checked_facts"] = data["checked_facts"]
        return TaskContext(request, request, data, {
            "chapter_content": data["chapter_content"],
            "relation_context": json.dumps(data["relation"], ensure_ascii=False),
            "source_character_context": json.dumps(data["source_character"], ensure_ascii=False),
            "target_character_context": json.dumps(data["target_character"], ensure_ascii=False),
        }, extra)
    if task == CHAPTER_WORLD_RULES_CHECK_TASK:
        from backend.services.novel.chapter_check_service import load_chapter_world_rules_check_context
        request = ChapterWorldRulesCheckInputV1.model_validate(scope)
        data = await load_chapter_world_rules_check_context(request)
        return TaskContext(request, request, data, {
            "chapter_content": data["chapter_content"], "world_rules_context": data["world_rules_context"],
        }, {"checked_rules": data["rules"]})
    if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        from backend.services.novel.chapter_check_service import load_chapter_item_owner_check_context, load_chapter_item_owner_facts_check_context
        request = ChapterItemOwnerCheckInputV1.model_validate(scope)
        data = (await load_chapter_item_owner_facts_check_context(request) if task == CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK
                else await load_chapter_item_owner_check_context(request))
        extra = {"check_target": data["target"]}
        if task == CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK:
            extra["checked_facts"] = data["checked_facts"]
        return TaskContext(request, request, data, {
            "chapter_content": data["chapter_content"],
            "item_context": json.dumps(data["item"], ensure_ascii=False),
            "from_character_context": json.dumps(data["from_character"], ensure_ascii=False),
            "to_character_context": json.dumps(data["to_character"], ensure_ascii=False),
        }, extra)
    if task in PLOT_TASKS:
        from backend.services.novel.plot_service import load_plot_context, plot_prompt_context
        data = await load_plot_context(task, parameters, scope)
        prompt_context = plot_prompt_context(data["context"], data["request"].target_type, data["request"].target_id)
        return TaskContext(data["request"], data["request"], data, {"writing_context": json.dumps(prompt_context, ensure_ascii=False)}, {"context": data["context"]})
    if task in WRITING_TASKS:
        from backend.services.novel.writing_context import load_writing_context
        data = await load_writing_context(task, parameters, scope)
        return TaskContext(data["request"], data["request"], data, {"writing_context": json.dumps(data["context"], ensure_ascii=False)}, {"context": data["context"]})
    spec = TASKS[task]
    payload = {**parameters, **generation_params, **scope, "use_stream": True}
    request = spec.request_model.model_validate({k: v for k, v in payload.items() if k in spec.request_model.model_fields})
    if task in VOLUME_ENTITY_TASKS:
        gen = VolumeEntityGenerationInputV1.model_validate({**request.model_dump(include={"new_count", "selected_existing_ids", "user_guidance", "volume_expected_version", "selection_mode"}), "novel_id": scope["novel_id"], "volume_id": scope["volume_id"]})
        data = await load_volume_entity_context(task, gen)
        return TaskContext(request, gen, data, {"entity_context": data["entity_context"]})
    extra: dict[str, Any] = {}
    if task == "create_characters_by_ai":
        data = await CharacterGenerationService.load_core_context(request)
        gen = request
    elif task == "create_character_relations_by_ai":
        data = await CharacterGenerationService.load_relation_context(request)
        gen = request
    elif task == "create_faction_relations_by_ai":
        data = await FactionRelationGenerationService.load_context(request)
        gen = request
    elif task == "create_world_rules_by_ai":
        gen = build_core_world_rules_generation_input(scope["novel_id"], request)
        data = await WorldRuleGenerationService.load_context(gen)
    elif task == "create_volume_skeleton_by_ai":
        gen, data, impacts = await VolumePlanningGenerationService.load_skeleton_context(scope["novel_id"], request)
        extra["impacts"] = [i.model_dump(mode="json") for i in impacts]
    elif task == "plan_volume_launch_by_ai":
        gen, data, impact = await VolumePlanningGenerationService.load_launch_context(scope["novel_id"], scope["volume_id"], request)
        extra["impact"] = impact.model_dump(mode="json")
    elif task == "create_locations_for_volume_by_ai":
        gen, data = await VolumeLocationGenerationService.load_context(scope["novel_id"], scope["volume_id"], request)
    elif task == "create_items_by_ai":
        gen = build_items_generation_input(scope["novel_id"], request)
        data = await load_item_generation_context(gen)
    elif task == "create_factions_by_ai":
        novel = await novel_repo.get_novel_by_id(request.novel_id)
        factions = await faction_repo.get_active_core_factions(request.novel_id)
        ids = {f["faction_id"] for f in factions}
        if any(t.faction_id not in ids for t in request.existing_relation_targets):
            raise DomainApiError("FACTION_REFERENCE_INVALID", "指定的已有阵营不存在", status_code=422)
        if request.faction_count is not None and request.faction_count - request.independent_faction_count == 1 and (not factions or (request.faction_count == 1 and not request.connect_to_existing)):
            raise DomainApiError("FACTION_RELATION_INPUT_INVALID", "只有一个势力需要建立关系，却没有可连接的对象。请调整生成数量或连接已有势力", status_code=422)
        relations = [
            relation
            for relation in await faction_relation_repo.get_relations_by_novel(request.novel_id, active_only=True)
            if relation.get("source_faction_id") in ids and relation.get("target_faction_id") in ids
        ]
        refs = build_core_factions_source_refs(novel, factions, relations)
        if len(refs) > 2000:
            raise DomainApiError("FACTION_GENERATION_SOURCE_BUDGET_EXCEEDED", "正式来源超过 2000 项", status_code=422)
        values = {
            key: format_faction_novel_text(novel, key)
            for key in (
                "plot", "tone", "target_audience", "core_idea", "core_seed", "title",
                "summary", "worldview", "writing_style", "narrative_pov", "era_background",
            )
        }
        values.update(
            genre=format_faction_novel_text(novel, "genre", "未分类"),
            number_of_chapters=novel.get("number_of_chapters") or 100,
            words_per_chapter=novel.get("words_per_chapter") or 3000,
            tags_json=json.dumps(novel.get("tags") or [], ensure_ascii=False),
            existing_core_factions_json=json.dumps(compact_existing_core_factions(factions), ensure_ascii=False, indent=2),
            faction_count=request.faction_count,
            generation_strategy=build_core_factions_generation_strategy(request, factions),
        )
        return TaskContext(request, request, {"novel": novel, "factions": factions, "relations": relations, "source_refs": refs}, values)
    elif task == "rewrite_novel_field_by_ai":
        novel = await novel_repo.get_novel_by_id(request.novel_id) if request.novel_id else None
        gen = canonicalize_novel_rewrite_input(request, novel=novel)
        # 正式小说只替换这两个字段，保留已校验的历史消息对象。
        effective = request.model_copy(update={"current_value": gen.current_value, "context": gen.context})
        ports = {
            "target_field_label": NOVEL_REWRITE_FIELD_LABELS[effective.target_field],
            "target_field": effective.target_field,
            "instruction": effective.instruction.strip(),
            "current_value": format_rewrite_value(effective.current_value) or "无",
            "context_json": json.dumps(compact_rewrite_context(effective.context, effective.target_field), ensure_ascii=False, indent=2),
            "history_text": format_rewrite_history(effective.chat_history),
        }
        refs = [{"resource_type": "novel", "id": scope["novel_id"], "version": int(novel["version"])}] if novel else []
        return TaskContext(effective, gen, {"novel": novel, "source_refs": refs}, ports)
    else:
        raise ValueError(f"任务 {task} 没有资料读取节点")

    # 数量是可空整数端口；只有原 JSON 文本端口需要序列化，不能把 AI 决定的 None 写成字符串。
    fields = PROMPT_TEMPLATE_FIELDS[spec.step + "_prompt_base"]
    values = data["prompt_input"]
    ports = {}
    for key in fields:
        value = values[key[:-5] if key.endswith("_json") else key]
        if key == "user_guidance":
            value = value or "无"
        elif isinstance(value, (dict, list, bool)) or (value is None and key not in {"character_count", "faction_count", "item_count", "core_rule_count"}):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        ports[key] = value
    return TaskContext(request, gen, data, ports, extra)


async def validate_task_result(task: str, candidate: dict[str, Any], context: TaskContext | None) -> dict[str, Any]:
    """复用原任务的最终结构、数量和正式引用校验。

    Args:
        task: 候选所属原任务。
        candidate: 结果节点映射出的业务字段。
        context: 本次读取的资料与业务参数；新书不需要。
    Returns:
        通过业务校验的 JSON 候选。
    """
    if task == CHAPTER_CHECK_TASK:
        from backend.services.novel.chapter_check_service import validate_chapter_check_result
        assert context is not None
        return validate_chapter_check_result(candidate, context.data)
    if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        from backend.services.novel.chapter_check_service import validate_chapter_item_owner_check_result
        assert context is not None
        return validate_chapter_item_owner_check_result(candidate, context.data)
    if task in {CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK}:
        from backend.services.novel.chapter_check_service import validate_chapter_character_relation_state_check_result
        assert context is not None
        return validate_chapter_character_relation_state_check_result(candidate, context.data, result_model=TASKS[task].result_model)
    if task == CHAPTER_WORLD_RULES_CHECK_TASK:
        from backend.services.novel.chapter_check_service import validate_chapter_world_rules_check_result
        assert context is not None
        return validate_chapter_world_rules_check_result(candidate, context.data)
    if task in PLOT_TASKS:
        from backend.services.novel.plot_service import validate_plot_candidate
        assert context is not None
        return validate_plot_candidate(task, candidate, context.data)
    if task in WRITING_TASKS:
        from backend.services.novel.writing_generation import validate_writing_candidate
        assert context is not None
        return validate_writing_candidate(task, candidate, context.data)
    if task in VOLUME_ENTITY_TASKS:
        assert context is not None
        return validate_volume_entity_candidates(task, candidate, context.data)
    result = TASKS[task].result_model.model_validate(candidate)
    if task == "create_novel_by_ai":
        return result.model_dump(mode="json")
    assert context is not None
    req, gen, data = context.request, context.generation_input, context.data
    if task == "create_characters_by_ai":
        CharacterGenerationService.validate_core_result(result, req, data)
    elif task == "create_character_relations_by_ai":
        await CharacterGenerationService.validate_relation_result(req.novel_id, result, data)
    elif task == "create_faction_relations_by_ai":
        await FactionRelationGenerationService.validate_result(req.novel_id, result, data)
    elif task == "create_world_rules_by_ai":
        WorldRuleGenerationService.validate_result(result, gen, data)
    elif task == "create_volume_skeleton_by_ai":
        VolumePlanningGenerationService.validate_skeleton_result(result, gen, data)
    elif task == "plan_volume_launch_by_ai":
        conflict = VolumePlanningGenerationService.validate_launch_result(result, data)
        context.extra["impact"]["next_start_state_conflict"] = conflict
    elif task == "create_locations_for_volume_by_ai":
        VolumeLocationGenerationService.validate_result(result, gen, data)
    elif task == "create_items_by_ai":
        ItemGenerationService.validate_result(result, gen, data)
    elif task == "create_factions_by_ai":
        try:
            FactionService.validate_core_factions_result(result, req, data["factions"])
        except LLMSchemaError as exc:
            # 此处只包含已解析候选的业务检查，模型解析异常仍保留通用错误。
            raise DomainApiError("CORE_FACTIONS_OUTPUT_INVALID", str(exc), status_code=502,
                                 details={"message": str(exc)}) from exc
    elif task == "rewrite_novel_field_by_ai" and result.target_field != req.target_field:
        raise DomainApiError("CANDIDATE_TARGET_INVALID", "改写结果的目标字段不一致", status_code=502)
    return result.model_dump(mode="json")
