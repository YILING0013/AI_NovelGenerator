"""为模拟生成符合字段结构的确定性示例，不调用模型。"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .contracts import FlowValidationError
from .graph import _resolve, _validate_value


_PATTERN_EXAMPLES = {
    r"^[0-9a-f]{64}$": "0" * 64,
    r"^[0-9a-fA-F]{24}$": "0123456789abcdef01234567",
    r"^[a-z][a-z0-9_]{0,63}$": "example_field",
    r"^[a-z][a-z0-9]*(?:_[a-z0-9]+){1,5}$": "example_entity",
    r"^char_[0-9]{6,}$": "char_000001",
    r"^character_[0-9]{2,3}$": "character_01",
    r"^cr_[0-9]{6,}$": "cr_000001",
    r"^fac_[0-9]{6,}$": "fac_000001",
    r"^faction_[0-9]{3}$": "faction_001",
    r"^item_candidate_[0-9]+$": "item_candidate_1",
    r"^loc_[0-9]{6,}$": "loc_000001",
    r"^relation_[0-9]{3}$": "relation_001",
    r"^rule_[0-9]{6,}$": "rule_000001",
    r"^rule_candidate_[0-9]+$": "rule_candidate_1",
}

_TEXT_EXAMPLES = {
    "title": "雾港来信", "name": "林舟", "subtitle": "一封没有署名的信",
    "user_idea": "一名记录员发现城市档案每天都会少掉一个人的名字。",
    "user_guidance": "突出人物选择造成的后果，保留下一步调查的线索。",
    "instruction": "保留原有设定，补充人物动机和关键冲突。",
    "summary": "记录员收到一封来信，沿着被抹去的档案追查失踪者。",
    "plot": "记录员在雾港发现档案被改写，追查线索时与守档人发生冲突，最终决定公开真相。",
    "core_idea": "记忆可以被改写，但人必须为自己的选择负责。",
    "core_seed": "记录员想找回失踪亲人的档案，守档人却认为删除记忆能保护城市。",
    "description": "此处填写该对象在故事中的具体作用和需要保留的细节。",
    "goal": "查明来信的来源", "current_goal": "核对失踪者的最后记录",
    "start_state": "主角带着来信抵达雾港", "end_state": "主角得到通往旧档案馆的线索",
    "content": "雾从港口漫进街道。林舟打开来信，认出了那个早已从档案中消失的名字。",
    "worldview": "城市依靠公共档案保存居民记忆，修改档案会改变人们对往事的认知。",
    "reason": "该选择会推动当前冲突，并为后续情节留下线索。",
    "genre": "悬疑", "tone": "克制而紧张", "provider": "preview_example",
    "target_field": "summary", "target_field_label": "简介", "history_text": "无",
}


def example_value(schema: dict[str, Any], root: dict[str, Any] | None = None, *,
                  name: str = "字段", index: int = 0) -> Any:
    """按已有结构生成一个可校验的示例；复杂自定义正则由作者填写。

    Args:
        schema: 当前字段的 JSON Schema。
        root: 包含共享引用的完整结构。
        name: 用于解释示例含义的字段名。
        index: 数组位置，用于产生不同的候选编号。
    Returns:
        满足结构的 JSON 值；无法确定合法值时抛出明确错误。
    """
    root = root or schema
    resolved = _resolve(schema, root)
    candidates = []
    if "const" in resolved:
        candidates.append(resolved["const"])
    if "default" in resolved:
        candidates.append(resolved["default"])
    candidates.extend(resolved.get("examples", []))
    if "enum" in resolved:
        values = resolved["enum"]
        candidates.extend(values[index % len(values):] + values[:index % len(values)])
    for value in candidates:
        try:
            _validate_value(schema, value, root, name)
            return deepcopy(value)
        except FlowValidationError:
            continue
    choices = resolved.get("anyOf", resolved.get("oneOf"))
    if choices:
        for choice in choices:
            try:
                value = example_value({**{k: v for k, v in resolved.items() if k not in {"anyOf", "oneOf"}}, **choice}, root, name=name, index=index)
                _validate_value(schema, value, root, name)
                return value
            except FlowValidationError:
                continue
        raise FlowValidationError(f"{name} 无法自动生成符合结构的示例，请临时填写示例")
    kind = resolved.get("type", "object" if "properties" in resolved else "string")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "null")
    if kind == "object":
        required = resolved.get("required", [])
        properties = resolved.get("properties", {})
        names = [*required, *(key for key in properties if key not in required)]
        names = names[:resolved.get("maxProperties", len(names))]
        value = {key: example_value(properties[key], root, name=key, index=index) for key in names}
    elif kind == "array":
        count = max(resolved.get("minItems", 0), min(1, resolved.get("maxItems", 1)))
        value = [example_value(resolved.get("items", {}), root, name=name, index=position) for position in range(count)]
    elif kind in {"integer", "number"}:
        step = resolved.get("multipleOf", 1 if kind == "integer" else 0.5)
        minimum = resolved.get("minimum", 0)
        minimum = max(minimum, resolved.get("exclusiveMinimum", minimum - step) + step)
        value = math.ceil(minimum / step) * step
        if value == 0 and resolved.get("maximum", 1) >= 1 and resolved.get("exclusiveMaximum", 2) > 1:
            value = math.ceil(1 / step) * step
        if kind == "integer":
            value = int(value)
    elif kind == "boolean":
        value = True
    elif kind == "null":
        value = None
    else:
        pattern = resolved.get("pattern")
        if pattern:
            value = _PATTERN_EXAMPLES.get(pattern)
            if value is None:
                raise FlowValidationError(f"{name} 需要符合格式 {pattern}，请临时填写示例")
            if index and value[-1:].isdigit():
                value = value[:-1] + str((index + 1) % 10)
        else:
            id_prefix = {"character_ids": "char", "faction_ids": "fac", "selected_existing_location_ids": "loc"}.get(name)
            value = f"{id_prefix}_{index + 1:06d}" if id_prefix else _TEXT_EXAMPLES.get(name, f"{resolved.get('title') or name}的假设示例")
            if index and not id_prefix:
                value += str(index + 1)
        minimum = resolved.get("minLength", 0)
        if len(value) < minimum:
            value = (value * (minimum // max(len(value), 1) + 1))[:minimum]
        value = value[:resolved.get("maxLength", len(value))]
    _validate_value(schema, value, root, name)
    return value


def missing_example(name: str) -> Any:
    """为尚未建立的小说资料提供结构明确的小例子。

    Args:
        name: 缺失的端口或 JSON 字段名。
    Returns:
        只用于本次模拟的业务形状示例。
    """
    key = name.removesuffix("_json")
    if key in {"novel_profile", "novel_summary", "novel", "context"}:
        return {"title": "雾港来信", "summary": _TEXT_EXAMPLES["summary"], "genre": "悬疑"}
    if key == "planning":
        return {"premise": "一封来信暴露了档案中的矛盾", "major_conflict": "主角追查真相，档案局试图隐瞒记录",
                "start_state": _TEXT_EXAMPLES["start_state"], "end_state": _TEXT_EXAMPLES["end_state"],
                "key_turning_points": ["主角找到第一份被改写的档案"], "target_chapter_count": 10, "target_word_count": 30000}
    if key in {"volume_launch_package", "target_volume", "previous_volume", "next_volume", "volume"}:
        return {"title": "第一卷：雾港", "goal": _TEXT_EXAMPLES["goal"], "planning": missing_example("planning")}
    if key == "writing_context":
        return {"plan": [{"resource_type": "novel", "id": "0123456789abcdef01234567", **missing_example("novel")},
                         {"resource_type": "volume", "id": "0123456789abcdef01234568", **missing_example("volume")}],
                "neighbors": {"previous": None, "next": None}, "existing_children": [], "previous_written": None,
                "selected_entities": [], "volume_states": [], "search_results": [], "edit_target": None,
                "user_guidance": _TEXT_EXAMPLES["user_guidance"], "count": 2, "target_word_count": 3000,
                "truncation": {"previous_excerpt_limit": 6000, "previous_truncated": False}}
    if key == "entity_context":
        return {"novel": missing_example("novel"), "volume": missing_example("volume"), "user_guidance": _TEXT_EXAMPLES["user_guidance"],
                "new_count": 2, "selected_existing_ids": [], "existing_profiles": [], "volume_states": [], "character_relations": []}
    if key in {"characters", "protagonists", "existing_core_characters", "existing_profiles", "selected_entities"}:
        return [{"character_id": "char_000001", "name": "林舟", "role_type": "protagonist", "identity": "记录员"}]
    if key in {"factions", "core_factions", "existing_core_factions"}:
        return [{"faction_id": "fac_000001", "name": "雾港档案局", "core_goal": "保存城市的记忆"}]
    if key == "factions_and_relations":
        return {"factions": missing_example("factions"), "faction_relations": [], "character_relations": [], "character_faction_bindings": []}
    if key == "neighbors":
        return {"previous": None, "next": None}
    if key in {"existing_children", "search_results"}:
        return []
    if key in {"previous_written", "edit_target"}:
        return None
    if key in {"active_world_rules", "existing_world_rules", "world_rules"}:
        return [{"rule_id": "rule_000001", "name": "档案与记忆", "statement": _TEXT_EXAMPLES["worldview"]}]
    if key in {"existing_items", "items"}:
        return [{"item_id": "item_000001", "name": "旧式记录终端", "description": "读取被隐藏的档案"}]
    if key in {"locations", "existing_locations", "selected_existing_locations"}:
        return [{"location_id": "loc_000001", "name": "旧档案馆", "description": "保存早期城市记录的建筑"}]
    if key in {"existing_relations", "relations", "faction_relations", "character_relations", "faction_bindings", "character_volume_states", "faction_volume_states", "volume_states"}:
        return []
    if key in {"existing_volumes", "volumes"}:
        return [missing_example("volume")]
    if key in {"tags", "key_beats", "key_turning_points"}:
        return ["调查线索" if key != "tags" else "悬疑"]
    if key.endswith("_count") or key in {"number_of_chapters", "words_per_chapter", "version", "order_index"}:
        return 1
    return _TEXT_EXAMPLES.get(key, f"{key}的假设示例")
