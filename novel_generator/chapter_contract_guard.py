from __future__ import annotations

import re
from typing import Any


_TERM_SPLIT_RE = re.compile(r"[、,，/|；;。\n\t ]+")
_QUOTED_TERM_RE = re.compile(r"[“\"'《【]([^”\"'》】]{1,20})[”\"'》】]")
_FORBIDDEN_LINE_RE = re.compile(r"(?:禁止|严禁|不得)(?:内容)?[:：]\s*(.+)")
_CHARACTER_ITEM_SPLIT_RE = re.compile(r"[、;\n]+")
_CHARACTER_NAME_RE = re.compile(r"^[A-Za-z\u4e00-\u9fff·]{2,12}$")

_TERM_STOP_WORDS = {
    "无",
    "暂无",
    "未知",
    "未指定",
    "待定",
    "本章",
    "章节",
    "内容",
    "剧情",
    "人物",
    "角色",
    "场景",
    "地点",
}

_CHARACTER_STOP_WORDS = {
    "主角",
    "女主",
    "男主",
    "反派",
    "路人",
    "炮灰",
    "背景板",
    "背景",
    "无名",
    "暗处窥视者",
    "暗处窥视的目光",
    "魔门死士",
    "赵家打手",
    "路人炮灰",
}


def _normalize_term(raw_term: Any) -> str:
    term = str(raw_term or "").strip()
    if not term:
        return ""
    term = re.sub(r"^[\s\-\*\d\.、:：]+", "", term)
    term = re.sub(r"[，,。；;、\s]+$", "", term)
    term = term.strip("()（）[]【】<>《》\"'“”‘’")
    if not term or term in _TERM_STOP_WORDS:
        return ""
    if len(term) > 24:
        return ""
    return term


def _dedupe_keep_order(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = _normalize_term(item)
        if not normalized or normalized in result:
            continue
        result.append(normalized)
        if len(result) >= max(1, int(limit)):
            break
    return result


def _split_terms(raw_text: Any, limit: int = 8) -> list[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []
    parts = _TERM_SPLIT_RE.split(text)
    return _dedupe_keep_order(parts, limit=limit)


def _extract_forbidden_terms(user_guidance: Any, limit: int = 12) -> list[str]:
    text = str(user_guidance or "")
    if not text.strip():
        return []

    candidates: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        quoted = _QUOTED_TERM_RE.findall(stripped)
        candidates.extend(quoted)

        match = _FORBIDDEN_LINE_RE.search(stripped)
        if match:
            candidates.extend(_TERM_SPLIT_RE.split(match.group(1)))
            continue

        if any(marker in stripped for marker in ("禁止", "严禁", "不得")):
            # 兜底：提取关键词形式（如“禁止A/B/C”）
            tail = stripped
            for marker in ("禁止", "严禁", "不得"):
                if marker in tail:
                    tail = tail.split(marker, 1)[1]
            candidates.extend(_TERM_SPLIT_RE.split(tail))

    return _dedupe_keep_order(candidates, limit=limit)


def _extract_character_names(raw_text: Any, limit: int = 6) -> list[str]:
    text = str(raw_text or "").strip()
    if not text:
        return []

    names: list[str] = []
    for chunk in _CHARACTER_ITEM_SPLIT_RE.split(text):
        item = str(chunk or "").strip()
        if not item:
            continue
        # 去掉角色说明括号（如“秦昭野（主角）”）
        item = re.sub(r"[（(【\[].*$", "", item).strip()
        # 兜底：去掉逗号/斜杠后面的补充说明
        item = re.split(r"[，,/|；;\t ]+", item, maxsplit=1)[0].strip()
        candidate = _normalize_term(item)
        if not candidate:
            continue
        if candidate in _CHARACTER_STOP_WORDS:
            continue
        if not _CHARACTER_NAME_RE.match(candidate):
            continue
        if candidate in names:
            continue
        names.append(candidate)
        if len(names) >= max(1, int(limit)):
            break
    return names


def build_chapter_contract(
    chapter_info: dict[str, Any] | None,
    *,
    characters_involved: Any = "",
    key_items: Any = "",
    scene_location: Any = "",
    time_constraint: Any = "",
    user_guidance: Any = "",
) -> dict[str, Any]:
    info = chapter_info if isinstance(chapter_info, dict) else {}

    characters_text = str(characters_involved or info.get("characters_involved", ""))
    key_items_text = str(key_items or info.get("key_items", ""))
    location_text = str(scene_location or info.get("scene_location", ""))
    time_text = str(time_constraint or info.get("time_constraint", ""))

    forbidden_from_info = _split_terms(info.get("forbidden_terms", ""), limit=12)
    forbidden_from_guidance = _extract_forbidden_terms(user_guidance, limit=12)

    contract = {
        "chapter_title": str(info.get("chapter_title", "")).strip(),
        "chapter_role": str(info.get("chapter_role", "")).strip(),
        "chapter_purpose": str(info.get("chapter_purpose", "")).strip(),
        "chapter_summary": str(info.get("chapter_summary", "")).strip(),
        "required_terms": {
            "characters": _extract_character_names(characters_text, limit=6),
            "key_items": _split_terms(key_items_text, limit=6),
            "locations": _split_terms(location_text, limit=4),
            "time_constraints": _split_terms(time_text, limit=4),
        },
        "forbidden_terms": _dedupe_keep_order(forbidden_from_info + forbidden_from_guidance, limit=12),
    }
    return contract


def build_chapter_contract_prompt(contract: dict[str, Any] | None) -> str:
    data = contract if isinstance(contract, dict) else {}
    required = data.get("required_terms", {}) if isinstance(data.get("required_terms"), dict) else {}
    forbidden_terms = data.get("forbidden_terms", [])
    forbidden = [str(x).strip() for x in forbidden_terms if str(x).strip()] if isinstance(forbidden_terms, list) else []

    lines: list[str] = ["【章节契约卡（防漂移硬约束）】"]
    chapter_title = str(data.get("chapter_title", "")).strip()
    chapter_role = str(data.get("chapter_role", "")).strip()
    chapter_purpose = str(data.get("chapter_purpose", "")).strip()

    if chapter_title:
        lines.append(f"- 章节标题锚点：{chapter_title}")
    if chapter_role:
        lines.append(f"- 章节定位：{chapter_role}")
    if chapter_purpose:
        lines.append(f"- 本章目标：{chapter_purpose}")

    characters = required.get("characters", []) if isinstance(required.get("characters"), list) else []
    key_items = required.get("key_items", []) if isinstance(required.get("key_items"), list) else []
    locations = required.get("locations", []) if isinstance(required.get("locations"), list) else []
    time_constraints = required.get("time_constraints", []) if isinstance(required.get("time_constraints"), list) else []

    if characters:
        lines.append(f"- 必须覆盖人物锚点：{'、'.join(characters[:4])}")
    if key_items:
        lines.append(f"- 必须覆盖关键要素：{'、'.join(key_items[:4])}")
    if locations:
        lines.append(f"- 必须覆盖场景锚点：{'、'.join(locations[:3])}")
    if time_constraints:
        lines.append(f"- 时间约束提示：{'、'.join(time_constraints[:3])}")
    if forbidden:
        lines.append(f"- 禁止触发要素：{'、'.join(forbidden[:6])}")

    if len(lines) <= 1:
        return ""
    lines.append("- 若正文与契约冲突，以本契约为最高优先级。")
    return "\n".join(lines)


def detect_chapter_contract_drift(
    chapter_text: Any,
    contract: dict[str, Any] | None,
    *,
    max_issues: int = 3,
) -> list[str]:
    text = str(chapter_text or "")
    if not text.strip():
        return ["章节契约漂移: 正文为空"]

    data = contract if isinstance(contract, dict) else {}
    required = data.get("required_terms", {}) if isinstance(data.get("required_terms"), dict) else {}
    forbidden_raw = data.get("forbidden_terms", [])
    forbidden = [str(x).strip() for x in forbidden_raw if str(x).strip()] if isinstance(forbidden_raw, list) else []

    issues: list[str] = []
    required_labels = {
        "characters": "人物锚点",
        "key_items": "关键要素",
        "locations": "场景锚点",
    }
    for key, label in required_labels.items():
        terms_raw = required.get(key, [])
        terms = [str(x).strip() for x in terms_raw if str(x).strip()] if isinstance(terms_raw, list) else []
        if not terms:
            continue
        selected = terms[:3]
        if not any(term in text for term in selected):
            issues.append(f"章节契约漂移: 未覆盖{label}({ '、'.join(selected) })")

    matched_forbidden = [term for term in forbidden if len(term) >= 2 and term in text]
    if matched_forbidden:
        issues.append(f"章节契约漂移: 命中禁止要素({ '、'.join(matched_forbidden[:4]) })")

    deduped = _dedupe_keep_order(issues, limit=max_issues)
    return deduped


def split_chapter_paragraphs(chapter_text: Any) -> list[str]:
    text = str(chapter_text or "").strip()
    if not text:
        return []
    parts = re.split(r"\n\s*\n+", text)
    return [part.strip() for part in parts if part and part.strip()]


def merge_chapter_paragraphs(paragraphs: list[str]) -> str:
    cleaned = [str(p).strip() for p in (paragraphs or []) if str(p).strip()]
    return "\n\n".join(cleaned)


def detect_paragraph_contract_drift(
    chapter_text: Any,
    contract: dict[str, Any] | None,
    *,
    max_paragraph_issues: int = 3,
    opening_window: int = 2,
) -> list[dict[str, Any]]:
    paragraphs = split_chapter_paragraphs(chapter_text)
    if not paragraphs:
        return []

    data = contract if isinstance(contract, dict) else {}
    required = data.get("required_terms", {}) if isinstance(data.get("required_terms"), dict) else {}
    forbidden_raw = data.get("forbidden_terms", [])
    forbidden = [str(x).strip() for x in forbidden_raw if str(x).strip()] if isinstance(forbidden_raw, list) else []

    issues: list[dict[str, Any]] = []
    max_items = max(1, int(max_paragraph_issues))

    for idx, paragraph in enumerate(paragraphs):
        para_issues: list[str] = []
        matched_forbidden = [term for term in forbidden if len(term) >= 2 and term in paragraph]
        if matched_forbidden:
            para_issues.append(f"命中禁止要素({ '、'.join(matched_forbidden[:4]) })")
        if para_issues:
            issues.append(
                {
                    "paragraph_index": idx,
                    "issues": para_issues,
                    "paragraph_preview": paragraph[:90],
                }
            )
            if len(issues) >= max_items:
                return issues

    window = max(1, int(opening_window))
    opening_text = "\n".join(paragraphs[:window])
    opening_required = {
        "characters": "人物锚点",
        "locations": "场景锚点",
    }
    opening_miss: list[str] = []
    for key, label in opening_required.items():
        terms_raw = required.get(key, [])
        terms = [str(x).strip() for x in terms_raw if str(x).strip()] if isinstance(terms_raw, list) else []
        if not terms:
            continue
        selected = terms[:2]
        if not any(term in opening_text for term in selected):
            opening_miss.append(f"开篇{label}缺失({ '、'.join(selected) })")

    if opening_miss and len(issues) < max_items:
        issues.append(
            {
                "paragraph_index": 0,
                "issues": opening_miss[:2],
                "paragraph_preview": paragraphs[0][:90],
            }
        )

    return issues[:max_items]


__all__ = [
    "build_chapter_contract",
    "build_chapter_contract_prompt",
    "detect_chapter_contract_drift",
    "detect_paragraph_contract_drift",
    "split_chapter_paragraphs",
    "merge_chapter_paragraphs",
]
