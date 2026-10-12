"""为流程查看读取小说资料；假设值不参与数据库查询或正式生成。"""

from __future__ import annotations

import json
from typing import Any

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.character_relation_repository import character_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.llm.schemas.character_pydantic import CharacterCreateRequestV1
from backend.llm.schemas.faction_creation_pydantic import FactionCreateRequestV1
from backend.llm.schemas.item_pydantic import ItemsGenerationInputV1
from backend.llm.schemas.location_pydantic import VolumeLocationsGenerationInputV1
from backend.llm.schemas.novel_pydantic import ExistingFactionRelationTargetV2
from backend.llm.schemas.volume_entity_pydantic import VOLUME_ENTITY_TASKS, VolumeEntityGenerationInputV1
from backend.llm.schemas.volume_planning_pydantic import VolumePlanningV1
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesGenerationInputV1
from backend.llm.schemas.writing_pydantic import WRITING_TASKS
from backend.services.llm.character_generation_service import CharacterGenerationService
from backend.services.llm.faction_generation_contract import (
    build_core_factions_generation_strategy, build_core_factions_source_refs,
    compact_existing_core_factions, format_faction_novel_text,
)
from backend.services.llm.faction_relation_generation_service import FactionRelationGenerationService
from backend.services.llm.item_generation_context import load_item_generation_context
from backend.services.llm.novel_generation_contract import (
    NOVEL_REWRITE_CONTEXT_FIELDS, NOVEL_REWRITE_FIELD_LABELS,
    compact_rewrite_context, format_rewrite_value,
)
from backend.services.llm.volume_entity_generation_service import load_volume_entity_context
from backend.services.llm.volume_location_generation_context import (
    LOCATION_FIELDS, NOVEL_SUMMARY_FIELDS, WORLD_RULE_FIELDS,
    load_volume_location_generation_context,
)
from backend.services.llm.volume_planning_context import load_volume_planning_context
from backend.services.llm.volume_planning_generation_service import _volume_prompt_projection
from backend.services.llm.world_rule_generation_service import WorldRuleGenerationService
from backend.services.novel.world_rule_service import WorldRuleService
from backend.services.novel.plot_contract import PLOT_TASKS
from backend.services.novel.chapter_check_contract import CHAPTER_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK
from backend.services.novel.plot_service import load_plot_context, plot_prompt_context
from backend.services.novel.writing_context import (
    NOVEL_FIELDS, load_writing_context, load_writing_parents, volume_missing_fields, position_content,
)
from backend.services.task_flows.defaults import builtin_flow
from backend.services.task_flows.preview_examples import missing_example
from backend.services.task_flows.registry import TASKS


# 这些端口在正式流程中始终传 JSON 文本；未选小说时也需要按同样格式显示示例。
JSON_CONTEXT_PORTS = {
    "context_json", "writing_context", "entity_context", "active_world_rules",
    "allow_incremental", "allow_isolated_characters", "allow_isolated_factions",
    "characters", "existing_world_rules", "faction_relations", "factions",
    "novel_summary", "protagonists", "existing_volumes", "factions_and_relations",
    "novel_profile", "target_order_range", "previous_volume", "target_volume",
    "next_volume", "character_volume_states", "existing_locations",
    "faction_volume_states", "selected_existing_locations", "volume_launch_package",
}


def _project(document: dict[str, Any], fields: Any) -> dict[str, Any]:
    """提取已有生成器允许显示的字段。

    Args:
        document: 已读取的小说资料。
        fields: 对应生成器的公开字段白名单。
    Returns:
        保留真实空值、排除内部字段的资料。
    """
    return {field: document.get(field) for field in fields}


def _finish(task: str, values: dict[str, Any], refs: list, missing: list, origins: dict) -> dict[str, Any]:
    """按正式资料节点的端口类型序列化预览内容。

    Args:
        task: 当前任务。
        values: 尚未序列化的公开资料。
        refs: 实际读取的资源版本。
        missing: 需要显示示例的具体字段。
        origins: 来自开始输入或小说资料的字段说明。
    Returns:
        节点端口、JSON 端口名、真实来源和缺项。
    """
    context = next((node for node in builtin_flow(task).nodes if node.type == "context"), None)
    ports = {}
    json_ports = [name for name in context.outputs if name.endswith("_json") or name in JSON_CONTEXT_PORTS] if context else []
    if context:
        for name, schema in context.outputs.items():
            key = name if name in values else name.removesuffix("_json")
            if key not in values:
                continue
            value = sanitize_json_value(values[key])
            if name == "user_guidance":
                value = value or "无"
            elif name in json_ports or (schema.get("type") == "string" and not isinstance(value, str)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if name not in json_ports:
                    json_ports.append(name)
            ports[name] = value
    sources = [ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref for ref in refs]
    return {"ports": ports, "json_ports": json_ports, "source_refs": sources, "missing": missing, "origins": origins}


async def load_preview_context(task: str, parameters: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    """读取任务已有资料，允许尚未填写的生成前提。

    Args:
        task: 编辑器正在查看的业务任务。
        parameters: 节点中的假设输入，仅用于公开文本和数量展示。
        scope: 用户选择的真实小说、当前部分与实体范围。
    Returns:
        ports 保持正式端口格式；missing.path 指向 JSON 解码后的字段，
        example/schema 仅供上层生成示例，不会被本函数用于数据库查询。
    """
    flow = builtin_flow(task)
    context = next((node for node in flow.nodes if node.type == "context"), None)
    if context is None:
        return _finish(task, {}, [], [], {})
    if task == CHAPTER_CHECK_TASK:
        # 编辑器没有经过章后来源选择，示例不能拿来查询真实资料。
        missing = [{"port": name, "path": [], "note": "请在章后确认中选择章修订和人物卷状态"} for name in context.outputs]
        return _finish(task, {}, [], missing, {})
    if task in {CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK}:
        missing = [{"port": name, "path": [], "note": "请在章后确认中选择章修订、物品和前后持有人"} for name in context.outputs]
        return _finish(task, {}, [], missing, {})
    if task == CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK:
        missing = [{"port": name, "path": [], "note": "请在章后确认中选择章修订和人物关系"} for name in context.outputs]
        return _finish(task, {}, [], missing, {})
    if task == CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK:
        missing = [{"port": name, "path": [], "note": "人物关系事实检查尚未接入章后页面，需要选定章修订和人物关系"} for name in context.outputs]
        return _finish(task, {}, [], missing, {})
    if task == CHAPTER_WORLD_RULES_CHECK_TASK:
        missing = [{"port": name, "path": [], "note": "请在章后报告中选择章修订和一至五条全书活动规则"} for name in context.outputs]
        return _finish(task, {}, [], missing, {})
    start = next(node for node in flow.nodes if node.type == "input")
    params = {**{name: schema["default"] for name, schema in start.outputs.items() if "default" in schema}, **parameters}
    if not scope.get("novel_id"):
        values = {name: params[name] for name, schema in context.outputs.items() if name in params and not (params[name] is None and schema.get("type") in {"integer", "number"})}
        origins = {name: [{"path": [], "origin": "user_input", "parameter": name}] for name in values}
        missing = [{"port": name, "path": [], "note": "尚未选择小说"} for name in context.outputs if name not in values]
        if task in WRITING_TASKS or task in PLOT_TASKS:
            sample = missing_example("writing_context")
            sample["plan"] = sample["plan"][:1]
            target_type = PLOT_TASKS[task] if task in PLOT_TASKS else WRITING_TASKS[task][0]
            ancestors = {"novel_id": sample["plan"][0]["id"]}
            for index, kind in enumerate(("volume", "arc", "scene", "chapter"), 1):
                planning = missing_example("planning") if kind == "volume" else {
                    "goal": "本部分要实现的目标", "start_state": "开始时的情形", "end_state": "结束时的情形", "target_word_count": 3000,
                    **({"beats": ["主角取得新的线索"], "pov_character_id": None, "must_include": [], "must_avoid": []} if kind == "chapter" else {"key_beats": ["主角取得新的线索"], "continuity_notes": "", "target_chapter_count": 2, "character_ids": [], "faction_ids": [], "location_ids": [], "item_ids": [], "rule_ids": []}),
                }
                identity = f"{index:024x}"
                sample["plan"].append({"resource_type": kind, "id": identity, **ancestors, "order_index": 1, "title": f"示例{dict(volume='卷', arc='篇章', scene='场景', chapter='章节')[kind]}", "summary": "当前部分的假设概要", "planning": planning})
                ancestors[f"{kind}_id"] = identity
                if kind == target_type:
                    break
            sample["edit_target"] = {**sample["plan"][-1], "content": "当前章节已保存正文的假设示例。"} if target_type == "chapter" else None
            if task in PLOT_TASKS:
                sample.update(has_children=False, planning_editable=True)
            sample.update({name: params[name] for name in ("user_guidance", "count", "target_word_count") if name in params})
            missing[0]["example"] = sample
            origins["writing_context"] = [{"path": [name], "origin": "user_input", "parameter": name} for name in ("user_guidance", "count", "target_word_count") if name in params]
        elif task in VOLUME_ENTITY_TASKS:
            sample = missing_example("entity_context")
            sample.update({name: params[name] for name in ("new_count", "selected_existing_ids", "user_guidance") if name in params})
            missing[0]["example"] = sample
            origins["entity_context"] = [{"path": [name], "origin": "user_input", "parameter": name} for name in ("new_count", "selected_existing_ids", "user_guidance") if name in params]
        return _finish(task, values, [], missing, origins)

    novel_id = scope["novel_id"]
    novel = await novel_repo.get_novel_by_id(novel_id)
    refs: list = [{"resource_type": "novel", "id": novel_id, "version": novel["version"]}]
    missing: list[dict[str, Any]] = []
    origins: dict[str, list[dict[str, Any]]] = {}
    values: dict[str, Any] = {}
    for name in context.outputs:
        if name in params:
            origins[name] = [{"path": [], "origin": "user_input", "parameter": name}]

    if task == "rewrite_novel_field_by_ai":
        target = scope.get("target_field")
        if target is not None and target not in NOVEL_REWRITE_FIELD_LABELS:
            raise DomainApiError("TASK_FLOW_PREVIEW_SCOPE_INVALID", "请选择有效的小说字段", status_code=422)
        values = {
            "context_json": compact_rewrite_context({key: novel.get(key) for key in NOVEL_REWRITE_CONTEXT_FIELDS if key in novel}, target or ""),
            "instruction": params.get("instruction", "请补充该字段的细节"),
        }
        origins["instruction"] = [{"path": [], "origin": "user_input", "parameter": "instruction"}]
        missing.append({"port": "history_text", "path": [], "note": "对话记录来自改写页面，本次未导入", "example": "用户: 保留原有情节，补充细节\nAI: 上一次改写的假设结果"})
        if target:
            values.update(target_field=target, target_field_label=NOVEL_REWRITE_FIELD_LABELS[target], current_value=format_rewrite_value(novel.get(target)) or "无")
            if novel.get(target) is None or novel.get(target) == "":
                missing.append({"port": "current_value", "path": [], "note": f"小说尚未填写{NOVEL_REWRITE_FIELD_LABELS[target]}"})
        else:
            missing.extend({"port": name, "path": [], "note": "尚未选择改写字段"} for name in ("target_field", "target_field_label", "current_value"))

    elif task == "create_factions_by_ai":
        factions = await faction_repo.get_active_core_factions(novel_id)
        ids = {item["faction_id"] for item in factions}
        relations = [item for item in await faction_relation_repo.get_relations_by_novel(novel_id, active_only=True) if item.get("source_faction_id") in ids and item.get("target_faction_id") in ids]
        targets = [ExistingFactionRelationTargetV2.model_construct(**item) for item in params.get("existing_relation_targets", [])]
        request = TASKS[task].request_model.model_construct(**{**params, "novel_id": novel_id, "existing_relation_targets": targets})
        values = {key: format_faction_novel_text(novel, key) for key in ("plot", "tone", "target_audience", "core_idea", "core_seed", "title", "summary", "worldview", "writing_style", "narrative_pov", "era_background")}
        values.update(genre=format_faction_novel_text(novel, "genre", "未分类"), number_of_chapters=novel.get("number_of_chapters") or 100, words_per_chapter=novel.get("words_per_chapter") or 3000, tags_json=novel.get("tags") or [], existing_core_factions_json=compact_existing_core_factions(factions), faction_count=request.faction_count, generation_strategy=build_core_factions_generation_strategy(request, factions))
        refs = build_core_factions_source_refs(novel, factions, relations)
        origins["generation_strategy"] = [{"path": [], "origin": "user_input", "parameter": name} for name in params]
        for name in values:
            if name not in {"tags_json", "existing_core_factions_json", "faction_count", "generation_strategy"} and (novel.get(name) is None or novel.get(name) == ""):
                missing.append({"port": name, "path": [], "note": "小说尚未填写此项"})

    elif task == "create_characters_by_ai":
        request = TASKS[task].request_model.model_construct(**{**params, "novel_id": novel_id})
        data = await CharacterGenerationService.load_core_context(request, require_readiness=False)
        values, refs = data["prompt_input"], data["source_refs"]
        if not values["core_factions"]:
            missing.append({"port": "core_factions_json", "path": ["0"], "note": "生成角色所需的核心势力尚未创建", "example": {"faction_id": "fac_999999", "name": "示例势力", "core_goal": "这个势力希望实现的目标"}})

    elif task in {"create_character_relations_by_ai", "create_faction_relations_by_ai"}:
        is_character = task == "create_character_relations_by_ai"
        key = "character_ids" if is_character else "faction_ids"
        selected = scope.get(f"selected_{key}", [])
        requested = params.get(key, selected)
        actual_ids = [identity for identity in requested if identity in selected]
        # 假设输入可以改变范围，但只有明确选过的真实 ID 能进入数据库查询。
        request = TASKS[task].request_model.model_construct(**{**params, "novel_id": novel_id, key: actual_ids})
        data = await (CharacterGenerationService.load_relation_context(request) if is_character else FactionRelationGenerationService.load_context(request))
        values, refs = data["prompt_input"], data["source_refs"]
        port = "characters_json" if is_character else "factions_json"
        content_key, identity_key = ("characters", "character_id") if is_character else ("factions", "faction_id")
        actual = {item[identity_key]: item for item in values[content_key]}
        values[content_key] = [actual.get(identity) for identity in requested]
        if request.relation_count_limit is None:
            count = max(2, len(requested))
            values["relation_count_limit"] = min(count * (count - 1), max(20, (count + 1) // 2))
        for index in range(max(2, len(requested))):
            if index < len(requested) and requested[index] in actual:
                continue
            identity = requested[index] if index < len(requested) else f"{'char' if is_character else 'fac'}_{999999 - index:06d}"
            note = "此 ID 未在资料范围中选择，显示假设档案，不读取小说资料" if index < len(requested) else "关系预览至少需要两个可用对象"
            missing.append({"port": port, "path": [str(index)], "note": note, "example": {identity_key: identity, "name": f"示例{'角色' if is_character else '势力'} {index + 1}"}})

    elif task == "create_world_rules_by_ai":
        generation_input = CoreWorldRulesGenerationInputV1.model_construct(**params, novel_id=novel_id)
        data = await WorldRuleGenerationService.load_context(generation_input, require_readiness=False)
        values, refs = data["prompt_input"], data["source_refs"]
        for name, label in (("protagonists", "主角"), ("factions", "核心势力")):
            if not values[name]:
                missing.append({"port": name, "path": ["0"], "note": f"生成世界规则所需的{label}尚未创建", "example": {"name": f"示例{label}"}})

    elif task == "create_items_by_ai":
        data = await load_item_generation_context(ItemsGenerationInputV1.model_construct(**params, novel_id=novel_id))
        values, refs = data["prompt_input"], data["source_refs"]

    elif task in {"create_volume_skeleton_by_ai", "plan_volume_launch_by_ai"}:
        volume_id = scope.get("volume_id") if task == "plan_volume_launch_by_ai" else None
        data = await load_volume_planning_context(novel_id, target_volume_id=volume_id)
        values, refs = {**data["prompt_facts"], **params}, data["source_refs"]
        if task == "plan_volume_launch_by_ai":
            values.pop("existing_volumes", None)
            if volume_id:
                index = next(i for i, item in enumerate(data["volumes"]) if str(item["_id"]) == volume_id)
                target = data["volumes"][index]
                values.update(target_volume=_volume_prompt_projection(target), previous_volume=_volume_prompt_projection(data["volumes"][index - 1]) if index else None, next_volume=_volume_prompt_projection(data["volumes"][index + 1]) if index + 1 < len(data["volumes"]) else None)
                for name in ("target_chapter_count", "target_word_count"):
                    if values.get(name) is None:
                        saved = (target.get("planning") or {}).get(name)
                        if saved is not None:
                            values[name] = saved
                            origins.pop(name, None)
                        else:
                            missing.append({"port": name, "path": [], "note": "当前卷未填写此项，实际生成时需要输入", "example": 10 if name == "target_chapter_count" else 30000})
            else:
                missing.extend({"port": name, "path": [], "note": "尚未选择当前卷", "example": {"title": "示例卷", "summary": "该卷的内容概要", "planning": None}} for name in ("target_volume", "previous_volume", "next_volume"))
                missing.extend({"port": name, "path": [], "note": "当前卷尚未选定，实际生成时需要填写此项", "example": 10 if name == "target_chapter_count" else 30000} for name in ("target_chapter_count", "target_word_count") if values.get(name) is None)
        for name, label in (("protagonists", "主角"), ("factions_and_relations", "核心势力")):
            absent = not values[name] if name == "protagonists" else not values[name]["factions"]
            if absent:
                missing.append({"port": name, "path": ["0"] if name == "protagonists" else ["factions", "0"], "note": f"生成卷规划所需的{label}尚未创建", "example": {"name": f"示例{label}"}})

    elif task == "create_locations_for_volume_by_ai":
        volume_id = scope.get("volume_id")
        available_selection = scope.get("selected_location_ids", [])
        requested = params.get("selected_existing_location_ids", available_selection)
        selected = [identity for identity in requested if identity in available_selection]
        if volume_id:
            volume = await volume_repo.get_volume_by_id(volume_id)
            generation_input = VolumeLocationsGenerationInputV1.model_construct(**{**params, "novel_id": novel_id, "volume_id": volume_id, "volume_expected_version": volume["version"], "selected_existing_location_ids": selected})
            data = await load_volume_location_generation_context(generation_input, require_planning=False)
            values, refs = data["prompt_input"], data["source_refs"]
            if volume.get("planning") is None:
                missing.append({"port": "volume_launch_package", "path": ["planning"], "note": "当前卷尚未填写规划", "schema": VolumePlanningV1.model_json_schema()})
            else:
                missing.extend({"port": "volume_launch_package", "path": item["field"].split("."), "note": item["message"]} for item in volume_missing_fields(volume))
        else:
            rules = (await WorldRuleService.get_world_rule_context(novel_id))["active_rules"]
            locations = [item for item in await location_repo.list_locations(novel_id) if item.get("status") == "active" and item.get("location_order_pending_token") is None]
            by_id = {item["location_id"]: item for item in locations}
            if any(identity not in by_id for identity in selected):
                raise DomainApiError("SELECTED_LOCATION_NOT_FOUND", "所选地点不存在、已停用或不属于当前小说", status_code=404)
            values = {**params, "novel_summary": position_content(novel, "novel"), "active_world_rules": [position_content(item, "world_rule") for item in rules], "existing_locations": [{"location_id": item["location_id"], **position_content(item, "location")} for item in locations], "selected_existing_locations": [{"location_id": identity, **position_content(by_id[identity], "location")} for identity in selected], "reading_semantics": "position_not_selected"}
            refs += [{"resource_type": kind, "id": item[identity], "version": item["version"]} for kind, records, identity in (("world_rule", rules, "rule_id"), ("location", locations, "location_id")) for item in records]
            missing.extend({"port": name, "path": [], "note": "尚未选择当前卷"} for name in ("volume_launch_package", "character_volume_states", "faction_volume_states"))
        selected_locations = {item["location_id"]: item for item in values["selected_existing_locations"]}
        values["selected_existing_locations"] = [selected_locations.get(identity) for identity in requested]
        missing.extend({"port": "selected_existing_locations", "path": [str(index)], "note": "此 ID 未在资料范围中选择，显示假设地点，不读取对应档案", "example": {"location_id": identity, "name": "示例地点", "description": "本次假设选用的地点"}} for index, identity in enumerate(requested) if identity not in selected_locations)

    elif task in VOLUME_ENTITY_TASKS:
        volume_id = scope.get("volume_id")
        is_character = task == "create_characters_for_volume_by_ai"
        available_selection = scope.get("selected_character_ids" if is_character else "selected_faction_ids", [])
        requested = params.get("selected_existing_ids", available_selection)
        selected = [identity for identity in requested if identity in available_selection]
        if volume_id:
            volume = await volume_repo.get_volume_by_id(volume_id)
            generation_input = VolumeEntityGenerationInputV1.model_construct(**{**params, "novel_id": novel_id, "volume_id": volume_id, "volume_expected_version": volume["version"], "selected_existing_ids": selected})
            data = await load_volume_entity_context(task, generation_input, require_preparation=False)
            values, refs = {"entity_context": json.loads(data["entity_context"])}, data["source_refs"]
        else:
            records = await (character_repo.get_characters_by_novel(novel_id) if is_character else faction_repo.get_factions_by_novel(novel_id))
            identity = "character_id" if is_character else "faction_id"
            records = [item for item in records if item.get("status" if is_character else "active_status") == "active" and (is_character or item.get("level_type") == "core")]
            if set(selected) - {item[identity] for item in records}:
                raise DomainApiError("VOLUME_ENTITY_REFERENCE_UNAVAILABLE", "所选档案不存在、已停用或不属于当前范围", status_code=404)
            relations = []
            if is_character:
                available = {item[identity] for item in records}
                relations = [item for item in await character_relation_repo.list_relations(novel_id) if item.get("is_active") is True and {item["source_character_id"], item["target_character_id"]} <= available]
            values = {"entity_context": {"novel": position_content(novel, "novel"), "new_count": params["new_count"], "selected_existing_ids": selected, "user_guidance": params["user_guidance"], "existing_profiles": [{identity: item[identity], **position_content(item, "character" if is_character else "faction"), "version": item["version"]} for item in records], "character_relations": [position_content(item, "character_relation") for item in relations], "reading_semantics": "position_not_selected"}}
            refs += [{"resource_type": "character" if is_character else "faction", "id": item[identity], "version": item["version"]} for item in records]
            refs += [{"resource_type": "character_relation", "id": item["relation_id"], "version": item["version"]} for item in relations]
            missing.extend({"port": "entity_context", "path": [name], "note": "尚未选择当前卷"} for name in ("volume", "volume_states"))
        values["entity_context"]["selected_existing_ids"] = requested
        identity_key = "character_id" if is_character else "faction_id"
        existing_ids = {item[identity_key] for item in values["entity_context"]["existing_profiles"]}
        unknown_ids = [identity for identity in requested if identity not in existing_ids]
        first_example = len(values["entity_context"]["existing_profiles"])
        missing.extend({"port": "entity_context", "path": ["existing_profiles", str(first_example + index)], "note": "输入中的 ID 仅用作本次假设，不读取对应档案", "example": {identity_key: identity, "name": "示例角色" if is_character else "示例势力"}} for index, identity in enumerate(unknown_ids))
        origins["entity_context"] = [{"path": [name], "origin": "user_input", "parameter": name} for name in ("new_count", "selected_existing_ids", "user_guidance")]

    elif task in WRITING_TASKS or task in PLOT_TASKS:
        target_type = PLOT_TASKS[task] if task in PLOT_TASKS else WRITING_TASKS[task][0]
        target_id = scope.get("target_id") or scope.get(f"{target_type}_id")
        if scope.get("target_type", target_type) != target_type:
            raise DomainApiError("WRITING_TARGET_INVALID", "任务与当前部分不匹配", status_code=422)
        if target_id:
            chain = await load_writing_parents(novel_id, target_type, target_id)
            selected_entities = {field: scope.get(f"selected_{field}", []) for field in ("character_ids", "faction_ids", "location_ids", "item_ids", "rule_ids")}
            writing_scope = {"novel_id": novel_id, "target_type": target_type, "target_id": target_id, "selected_entities": selected_entities}
            if target_type == "chapter" or task in PLOT_TASKS:
                writing_scope["expected_version"] = chain[-1][1]["version"]
            # 沿用正式资料读取及父链检查，只跳过尚未填写的规划前提。
            if task in PLOT_TASKS:
                writing_scope.pop("selected_entities")
                data = await load_plot_context(task, {"user_guidance": params.get("user_guidance", "")}, writing_scope, check_ready=False)
            else:
                data = await load_writing_context(task, params, writing_scope, check_ready=False)
            values, refs = {"writing_context": data["context"]}, data["source_refs"]
            for item in data["missing"]:
                parts = item["field"].split(".")
                index = next(i for i, (kind, _) in enumerate(chain) if kind == "volume") if parts[0] == "volume" else len(chain) - 1
                path = parts[1:] if parts[0] == "volume" else parts
                if path[0] == "planning" and data["context"]["plan"][index].get("planning") is None:
                    data["context"]["plan"][index]["planning"] = {}
                missing.append({"port": "writing_context", "path": ["plan", str(index), *path], "note": item["message"]})
            if task in PLOT_TASKS:
                values["writing_context"] = plot_prompt_context(data["context"], target_type, target_id)
        else:
            values = {"writing_context": {"plan": [{"resource_type": "novel", "id": novel_id, **{name: novel[name] for name in NOVEL_FIELDS if name in novel}}], "truncation": {"previous_excerpt_limit": 6000, "previous_truncated": False}, **{name: params[name] for name in ("user_guidance", "count", "target_word_count") if name in params}}}
            missing.append({"port": "writing_context", "path": ["plan", "1"], "note": "尚未选择需要查看的卷、篇章、场景或章节", "example": {"resource_type": target_type, "title": "示例当前部分", "planning": {"goal": "本部分要实现的目标", "start_state": "开始时的情形", "end_state": "结束时的情形"}}})
            examples = {
                "neighbors": {"previous": None, "next": None},
                "existing_children": [],
                "previous_written": {"kind": "written_excerpt", "chapter_id": "0123456789abcdef01234567", "title": "示例前章", "summary": "前章已经发生的事件", "excerpt": "这里显示前章实际正文的末尾片段。", "truncated": False},
                "selected_entities": [{"resource_type": "character", "id": "char_999999", "name": "示例角色"}],
                "volume_states": [], "search_results": [],
                "edit_target": {"resource_type": "chapter", "id": "0123456789abcdef01234567", "title": "示例当前章", "content": "当前章节已保存的正文。"} if target_type == "chapter" else None,
            }
            if task in PLOT_TASKS:
                examples.update(has_children=False, planning_editable=True)
            missing.extend({"port": "writing_context", "path": [name], "note": "选定当前部分后读取对应资料", "example": example} for name, example in examples.items())
        origins["writing_context"] = [{"path": [name], "origin": "user_input", "parameter": name} for name in ("user_guidance", "count", "target_word_count") if name in values["writing_context"]]

    return _finish(task, values, refs, missing, origins)
