"""三层规划审核的原句定位；文字匹配不代表审核结论正确。"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any


REVIEW_EVIDENCE_CONTRACT = "writing_review_v1"
REVIEW_SOURCE_CHAR_LIMIT = 200000
REVIEW_INPUT_SCHEMA = {"type": "object", "additionalProperties": True, "default": {}}
REVIEW_OUTPUT_SCHEMA = {
    "anyOf": [{
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "integer", "const": 1},
            "summary": {"type": "string"},
            "issues": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "candidate_index": {"type": "integer"},
                    "message": {"type": "string"},
                    "candidate_field": {"type": "string"},
                    "candidate_quote": {"type": "string"},
                    "source": {"anyOf": [{
                        "type": "object", "additionalProperties": False,
                        "properties": {name: {"type": "string"} for name in ("resource_type", "id", "field", "quote")},
                        "required": ["resource_type", "id", "field", "quote"],
                    }, {"type": "null"}]},
                    "verification": {"anyOf": [{
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "candidate": {"type": "string"}, "source": {"type": "string"},
                            "status": {"type": "string"}, "semantic_check": {"type": "string"},
                            "source_truncated": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                        },
                    }, {"type": "null"}]},
                },
                "required": ["candidate_index", "message", "candidate_field", "candidate_quote", "source"],
            }},
        },
        "required": ["schema_version", "summary", "issues"],
    }, {"type": "null"}],
}


def _field_facts(document: dict[str, Any]) -> tuple[dict[str, bool], dict[str, int]]:
    """列出实际字段是否有值和数组长度，不推断文字含义。"""
    presence = {}
    counts = {}
    pending = [(key, value) for key, value in document.items()]
    while pending:
        path, value = pending.pop()
        presence[path] = value is not None and (bool(value.strip()) if isinstance(value, str) else bool(value) if isinstance(value, (list, dict)) else True)
        if isinstance(value, dict):
            pending.extend((f"{path}.{key}", item) for key, item in value.items())
        elif isinstance(value, list):
            counts[path] = len(value)
    return presence, counts


def build_review_material(context: dict[str, Any], read_material: dict[str, Any], candidates: list[dict[str, Any]], prepared: dict[str, Any]) -> dict[str, Any]:
    """整理本次审核实际可见的原文和代码已检查的事实。

    Args:
        context: 候选检查使用的真实写作上下文。
        read_material: 通过原读取指纹复查的服务端资料。
        candidates: 本次已通过结构、数量、引用和预算检查的候选。
        prepared: 资料整理意见，只用于区分已选实体和实际读取。
    Returns:
        去重且有明确范围的来源、确定性事实和非原文整理意见。
    """
    documents = [*context.get("plan", []), *context.get("existing_children", []),
                 *context.get("selected_entities", []), *context.get("relations", []), *context.get("volume_states", []),
                 *context.get("search_results", [])]
    documents.extend(value for value in context.get("neighbors", {}).values() if value is not None)
    if context.get("edit_target"):
        documents.append(context["edit_target"])
    if context.get("previous_written"):
        previous = context["previous_written"]
        documents.append({**previous, "resource_type": "chapter", "id": previous["chapter_id"]})
    for name in ("selected_entities", "volume_states", "relations", "previous_text"):
        documents.extend(read_material.get(name, []))

    # 同一位置的同一实体只提供一次字段。章节检索与末尾阅读可能返回不同片段，均保留原文。
    combined = {}
    for document in documents:
        key = (document["resource_type"], document["id"])
        if key not in combined:
            combined[key] = deepcopy(document)
            continue
        saved = combined[key]
        for name, value in document.items():
            if name not in saved:
                saved[name] = deepcopy(value)
            elif saved[name] != value and name == "excerpt":
                excerpts = saved.setdefault("additional_excerpts", [])
                if value not in excerpts:
                    excerpts.append(deepcopy(value))

    sources = []
    characters = 0
    omitted = 0
    for document in combined.values():
        encoded = json.dumps(document, ensure_ascii=False, sort_keys=True)
        # 不截断字段来凑预算；未提供的整份资料不能被当成本次审核的引文依据。
        if characters + len(encoded) > REVIEW_SOURCE_CHAR_LIMIT:
            omitted += 1
            continue
        sources.append(deepcopy(document))
        characters += len(encoded)

    candidate_facts = []
    for index, candidate in enumerate(candidates, 1):
        presence, counts = _field_facts(candidate)
        candidate_facts.append({"candidate_index": index, "field_presence": presence, "array_counts": counts})
    kinds = {"character_ids": "character", "faction_ids": "faction", "location_ids": "location", "item_ids": "item", "rule_ids": "world_rule"}
    return {
        "sources": sources,
        "facts": {
            "checks_passed": ["structure", "candidate_count", "entity_references", "budget"],
            "candidate_count": len(candidates), "candidates": candidate_facts,
            "sources": [{"resource_type": item["resource_type"], "id": item["id"], "array_counts": _field_facts(item)[1]} for item in sources],
            "selected_entity_refs": [{"resource_type": kinds[field], "id": identity}
                                     for field, ids in prepared.get("selected_entities", {}).items()
                                     for identity in ids],
            "read_entity_refs": [{"resource_type": item["resource_type"], "id": item["id"]}
                                 for item in read_material.get("selected_entities", [])],
            "source_scope": "provided_sources_only", "sources_omitted": omitted,
            "source_character_limit": REVIEW_SOURCE_CHAR_LIMIT,
            "truncation": deepcopy(context.get("truncation", {})),
            "position": deepcopy(context.get("position")),
        },
        "preparation": {key: deepcopy(prepared[key]) for key in ("boundaries", "coverage", "remaining", "suggested_count") if key in prepared},
    }


def _field_quote_matches(document: dict[str, Any], path: str, quote: str) -> bool:
    """只接受指定字符串字段中的非空逐字引文，不跨字段拼接。"""
    if not path or not quote.strip():
        return False
    value: Any = document
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif (isinstance(value, list) and part.isascii() and part.isdigit() and len(part) <= len(str(len(value)))
              and str(int(part)) == part and int(part) < len(value)):
            value = value[int(part)]
        else:
            return False
    return isinstance(value, str) and quote in value


def verify_review_evidence(review: dict[str, Any] | None, candidates: list[dict[str, Any]], sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """覆盖模型自报状态，按本次候选和实际提供的原文核对引文。

    Args:
        review: 新契约的模型意见，可为空。
        candidates: 实际送入审核的有序候选。
        sources: 实际送入审核的服务端原文，不能包含整理总结。
    Returns:
        保留所有意见的副本；匹配只证明原句存在，不判断意见是否正确。
    """
    if review is None:
        return None
    result = deepcopy(review)
    for issue in result["issues"]:
        index = issue["candidate_index"]
        candidate_matches = (result.get("schema_version") == 1 and type(index) is int and 1 <= index <= len(candidates)
                             and _field_quote_matches(candidates[index - 1], issue.get("candidate_field", ""), issue.get("candidate_quote", "")))
        source = issue.get("source")
        matching_sources = [document for document in sources
                            if result.get("schema_version") == 1 and source is not None and document.get("resource_type") == source["resource_type"]
                            and document.get("id") == source["id"]
                            and _field_quote_matches(document, source["field"], source["quote"])]
        source_status = "not_provided" if source is None else "matched" if matching_sources else "unverified"
        issue["verification"] = {
            "candidate": "matched" if candidate_matches else "unverified",
            "source": source_status,
            "status": "matched" if candidate_matches and source_status != "unverified" else "unverified",
            "source_truncated": any(bool(document.get("truncated")) for document in matching_sources) if matching_sources else None,
            "semantic_check": "not_performed",
        }
    return result
