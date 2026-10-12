"""剧情候选的双来源原句核对；不判断两段文字在意思上是否冲突。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.db.write_contracts import canonical_request_hash


PLOT_SOURCE_CONFLICTS_CONTRACT = "plot_source_conflicts_v1"
_REFERENCE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {name: {"type": "string", "maxLength": limit}
                   for name, limit in (("resource_type", 64), ("id", 100), ("field", 200), ("quote", 2000))},
    "required": ["resource_type", "id", "field", "quote"],
}
PLOT_SOURCE_CONFLICTS_SCHEMA = {
    "anyOf": [{"type": "array", "maxItems": 12, "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"message": {"type": "string", "maxLength": 1000},
                       "saved_text": deepcopy(_REFERENCE_SCHEMA), "old_plan": deepcopy(_REFERENCE_SCHEMA)},
        "required": ["message", "saved_text", "old_plan"],
    }}, {"type": "null"}], "default": None,
}


def build_plot_source_conflicts(raw_conflicts: list[dict[str, Any]] | None,
                                prompt_context: dict[str, Any],
                                previous_text: list[dict[str, Any]]) -> dict[str, Any]:
    """只核对报告节点实际收到的保存原文，保留错引文供作者审阅。

    Args:
        raw_conflicts: 模型原始报告；空值表示没有报告，空数组表示本次未报告冲突。
        prompt_context: 已去掉当前旧剧情、实际送入该模型节点的服务端资料。
        previous_text: 该节点直接收到的整理结果中，由服务端读取的前文片段。
    Returns:
        带稳定编号、逐字匹配和截断状态的报告；不接受模型自报核实状态。
    """
    result = {"reported": raw_conflicts is not None, "items": []}
    if raw_conflicts is None:
        return result
    sources = [*prompt_context.get("plan", []), *prompt_context.get("existing_children", []),
               *prompt_context.get("search_results", []), *previous_text]
    sources.extend(value for value in prompt_context.get("neighbors", {}).values() if value is not None)
    if prompt_context.get("edit_target"):
        sources.append(prompt_context["edit_target"])
    if prompt_context.get("previous_written"):
        previous = prompt_context["previous_written"]
        sources.append({**previous, "resource_type": "chapter", "id": previous["chapter_id"]})

    for index, conflict in enumerate(raw_conflicts):
        # 只复制原始四个定位字段；不能把模型或缓存自报的 matched 当成核实结果。
        raw = {"message": conflict["message"], **{
            side: {key: conflict[side][key] for key in ("resource_type", "id", "field", "quote")}
            for side in ("saved_text", "old_plan")}}
        item = {"id": canonical_request_hash({"index": index, "conflict": raw}),
                **deepcopy(raw), "semantic_check": "not_performed"}
        for side in ("saved_text", "old_plan"):
            reference = raw[side]
            path = reference["field"].split(".")
            allowed = (reference["resource_type"] == "chapter" and reference["field"] in {"excerpt", "content"}
                       if side == "saved_text" else
                       reference["resource_type"] in {"novel", "volume", "arc", "scene", "chapter"}
                       and path[0] in {"plot", "planning", "summary", "goal", "theme", "core_idea", "core_seed"})
            matches = []
            available = []
            for document in sources:
                if not allowed or (document.get("resource_type"), document.get("id")) != (reference["resource_type"], reference["id"]):
                    continue
                value: Any = document
                for part in path:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    elif (isinstance(value, list) and part.isascii() and part.isdigit()
                          and len(part) <= len(str(len(value))) and str(int(part)) == part and int(part) < len(value)):
                        value = value[int(part)]
                    else:
                        value = None
                        break
                if isinstance(value, str):
                    available.append(document)
                    if reference["quote"].strip() and reference["quote"] in value:
                        matches.append(document)
            located = matches or available
            item[side]["verification"] = {
                "status": "matched" if matches else "unverified",
                "source_truncated": (any(bool(document.get("truncated")) for document in located)
                                     if side == "saved_text" else False) if located else None,
            }
        result["items"].append(item)
    return result
