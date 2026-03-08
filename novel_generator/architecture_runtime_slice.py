from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


TOP_SECTION_HEADING_RE = re.compile(r"^##\s+(\d+)\.\s+.*$", re.MULTILINE)
_FOCUS_TERM_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff·_-]{2,16}")
_FOCUS_STOP_WORDS = {
    "以及",
    "然后",
    "这个",
    "那个",
    "章节",
    "本章",
    "当前",
    "要求",
    "内容",
    "需要",
    "可以",
    "必须",
    "生成",
    "剧情",
    "人物",
    "设定",
    "世界观",
    "故事",
    "小说",
    "主线",
}


def split_top_sections(text: str) -> list[tuple[int, str]]:
    matches = list(TOP_SECTION_HEADING_RE.finditer(text or ""))
    sections: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        section_num = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((section_num, text[start:end].strip()))
    return sections


def _in_ranges(section_num: int, ranges: Iterable[tuple[int, int]]) -> bool:
    for start, end in ranges:
        if start <= section_num <= end:
            return True
    return False


def build_runtime_architecture_view(
    architecture_text: str,
    ranges: tuple[tuple[int, int], ...] = ((0, 12), (88, 136)),
) -> str:
    text = (architecture_text or "").strip()
    if not text:
        return ""

    sections = split_top_sections(text)
    if not sections:
        return text

    filtered = [body for section_num, body in sections if _in_ranges(section_num, ranges)]
    return "\n\n".join(filtered).strip()


def _extract_focus_terms(*parts: Any, max_terms: int = 24) -> list[str]:
    terms: list[str] = []
    for part in parts:
        text = str(part or "")
        if not text.strip():
            continue
        for token in _FOCUS_TERM_RE.findall(text.lower()):
            if token in _FOCUS_STOP_WORDS:
                continue
            if token not in terms:
                terms.append(token)
                if len(terms) >= max_terms:
                    return terms
    return terms


def build_runtime_architecture_context(
    architecture_text: str,
    *,
    max_chars: int = 18000,
    required_sections: tuple[int, ...] = (0, 88, 136),
    focus_text: str = "",
    section_numbers_hint: tuple[int, ...] = (),
    max_chars_per_section: int = 2800,
    ignore_budget: bool = False,
) -> str:
    """
    构建“预算内运行时架构上下文”，防止整份架构塞入上下文导致漂移。
    策略：
    1) 先过滤在线执行白名单（0-12,88-136）；
    2) 必保关键节 required_sections；
    3) 结合 focus_text / section hint 对剩余节排序；
    4) 在 max_chars 预算内拼接，必要时按节截断。
    """
    runtime_text = build_runtime_architecture_view(architecture_text)
    if not runtime_text:
        text = (architecture_text or "").strip()
        return text[: max(1000, int(max_chars))] if text else ""

    if ignore_budget:
        return runtime_text

    sections = split_top_sections(runtime_text)
    if not sections:
        return runtime_text[: max(1000, int(max_chars))]

    budget = max(1000, int(max_chars))
    per_section_limit = max(300, int(max_chars_per_section))
    focus_terms = _extract_focus_terms(focus_text)
    hint_set = {int(x) for x in section_numbers_hint}

    section_map = {num: body for num, body in sections}
    ordered_numbers = [num for num, _ in sections]
    required = [num for num in required_sections if num in section_map]
    remaining = [num for num in ordered_numbers if num not in required]

    def _section_score(section_num: int, section_body: str) -> int:
        score = 0
        lowered = section_body.lower()
        if section_num in hint_set:
            score += 200
        for term in focus_terms:
            if term in lowered:
                score += 5
        return score

    ranked_remaining = sorted(
        remaining,
        key=lambda num: (_section_score(num, section_map[num]), -num),
        reverse=True,
    )
    candidates = required + ranked_remaining

    selected_parts: list[str] = []
    used_chars = 0
    truncated = False

    for section_num in candidates:
        body = section_map.get(section_num, "").strip()
        if not body:
            continue
        clipped = body
        if len(clipped) > per_section_limit:
            clipped = clipped[:per_section_limit].rstrip()
            truncated = True

        extra_sep = 2 if selected_parts else 0
        extra_len = len(clipped) + extra_sep
        remaining_budget = budget - used_chars
        if extra_len > remaining_budget:
            # required 节允许在预算末尾做最小截断保留
            if section_num in required and remaining_budget > 120:
                take_len = max(120, remaining_budget - extra_sep)
                clipped = clipped[:take_len].rstrip()
                extra_len = len(clipped) + extra_sep
                truncated = True
            else:
                continue

        if extra_len <= 0:
            continue
        selected_parts.append(clipped)
        used_chars += extra_len
        if used_chars >= budget:
            break

    context_text = "\n\n".join(selected_parts).strip()
    if not context_text:
        context_text = runtime_text[:budget]
        truncated = True

    if truncated and len(context_text) + 32 <= budget:
        context_text = (
            context_text
            + "\n\n【系统提示：运行时架构已按预算裁剪，避免上下文漂移】"
        )
    return context_text


def contains_archive_sections(runtime_text: str, archive_start: int = 13, archive_end: int = 87) -> bool:
    for section_num, _ in split_top_sections(runtime_text or ""):
        if archive_start <= section_num <= archive_end:
            return True
    return False


def build_runtime_guardrail_brief(
    architecture_text: str,
    section_numbers: tuple[int, ...] = (0, 88, 136),
    max_chars_per_section: int = 1200,
) -> str:
    runtime_text = build_runtime_architecture_view(architecture_text)
    if not runtime_text:
        return ""

    section_map = {section_num: body for section_num, body in split_top_sections(runtime_text)}
    parts: list[str] = []
    for section_num in section_numbers:
        body = section_map.get(section_num, "").strip()
        if not body:
            continue
        if len(body) > max_chars_per_section:
            body = body[:max_chars_per_section].rstrip()
        parts.append(body)

    if not parts:
        return ""

    return "【运行时硬约束摘要】\n" + "\n\n".join(parts)


def collect_runtime_architecture_issues(
    architecture_text: str,
    required_sections: tuple[int, ...] = (0, 88, 136),
) -> list[str]:
    runtime_text = build_runtime_architecture_view(architecture_text)
    issues: list[str] = []
    if not runtime_text.strip():
        issues.append("运行时架构为空")
        return issues

    if contains_archive_sections(runtime_text):
        issues.append("运行时架构包含归档节（13-87）")

    section_numbers = {section_num for section_num, _ in split_top_sections(runtime_text)}
    for required in required_sections:
        if required not in section_numbers:
            issues.append(f"运行时架构缺少关键节：{required}")

    return issues
