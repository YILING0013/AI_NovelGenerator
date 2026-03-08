# -*- coding: utf-8 -*-
"""
LLM 一致性审校服务。
统一替代根目录 legacy consistency_checker.py 中的实现，避免多入口分叉。
"""

import os
import re

from llm_adapters import create_llm_adapter
from novel_generator.common import write_llm_interaction_log
from novel_generator.generation_state_facade import GenerationStateFacade


CONSISTENCY_PROMPT = """\
请检查下面的小说设定与最新章节是否存在明显冲突或不一致之处，如有请列出：
- 小说设定：
{novel_setting}

- 角色状态（可能包含重要信息）：
{character_state}

- 前文摘要：
{global_summary}

- 已记录的未解决冲突或剧情要点：
{plot_arcs}

- 最新章节内容：
{chapter_text}

如果存在冲突或不一致，请按“问题-原因-建议修复”格式列出；否则请返回“无明显冲突”。
"""


CONFLICT_KEYWORDS = r"(冲突|矛盾|不一致|前后不符|违背设定|时间线错误|逻辑硬伤|设定硬伤|OOC|互斥)"
CERTAINTY_MARKERS = r"(存在|发现|出现|检测到|命中|确认|明确|严重|必须修复|仍有)"
NEGATION_MARKERS = r"(无|未|没有|并无|未见|不存在)"
TENTATIVE_MARKERS = r"(可能|疑似|潜在|建议关注|建议优化|可考虑|或许|倾向)"
HARD_CONFLICT_MARKERS = r"(硬性冲突|致命冲突|逻辑崩坏|无法自洽|完全矛盾|明确冲突)"
POLICY_SUGGESTION_MARKERS = (
    "设定集", "条款", "口径", "补充", "建议", "可考虑", "优化", "完善", "映射",
    "统一", "术语修正", "概念", "规则层", "在`", "在“", "在\"", "请在",
)
EVIDENCE_MARKERS = (
    "证据", "原文", "原句", "上一章", "前文", "本章", "片段", "句子", "段落",
    "写道", "提到", "显示", "出现在",
)
MAX_CONFLICT_ITEM_CHARS = 320

MAX_REVIEW_NOVEL_SETTING_CHARS = 18000
MAX_REVIEW_CHARACTER_STATE_CHARS = 7000
MAX_REVIEW_GLOBAL_SUMMARY_CHARS = 6000
MAX_REVIEW_PLOT_ARCS_CHARS = 2500
MAX_REVIEW_CHAPTER_TEXT_CHARS = 14000


def _load_plot_arcs_text(filepath: str, plot_arcs_text: str | None = None) -> str:
    if plot_arcs_text is not None:
        return str(plot_arcs_text or "").strip()
    plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
    if not os.path.exists(plot_arcs_file):
        return ""
    try:
        with open(plot_arcs_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def build_ledger_backed_review_inputs(
    filepath: str,
    chapter_number: int,
    plot_arcs_text: str | None = None,
) -> tuple[str, str, str]:
    current_plot_arcs_text = _load_plot_arcs_text(filepath, plot_arcs_text=plot_arcs_text)
    memory_context = GenerationStateFacade(filepath).load_review_memory_context(
        current_chapter_num=chapter_number,
        plot_arcs_text=current_plot_arcs_text,
    )
    return (
        memory_context.character_state_text,
        memory_context.global_summary_text,
        memory_context.plot_arcs_text,
    )


def _clip_with_head_tail(text: str, max_chars: int, label: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""
    if len(content) <= max_chars:
        return content

    head_chars = max(200, int(max_chars * 0.72))
    tail_chars = max(120, max_chars - head_chars - 120)
    omitted = max(0, len(content) - head_chars - tail_chars)
    head = content[:head_chars].rstrip()
    tail = content[-tail_chars:].lstrip()
    return (
        f"{head}\n\n"
        f"...[{label}内容较长，已省略约{omitted}字符]...\n\n"
        f"{tail}"
    )


def _prepare_review_inputs(
    novel_setting: str,
    character_state: str,
    global_summary: str,
    plot_arcs: str,
    chapter_text: str,
) -> tuple[str, str, str, str, str]:
    return (
        _clip_with_head_tail(novel_setting, MAX_REVIEW_NOVEL_SETTING_CHARS, "小说设定"),
        _clip_with_head_tail(character_state, MAX_REVIEW_CHARACTER_STATE_CHARS, "角色状态"),
        _clip_with_head_tail(global_summary, MAX_REVIEW_GLOBAL_SUMMARY_CHARS, "前文摘要"),
        _clip_with_head_tail(plot_arcs, MAX_REVIEW_PLOT_ARCS_CHARS, "剧情要点"),
        _clip_with_head_tail(chapter_text, MAX_REVIEW_CHAPTER_TEXT_CHARS, "最新章节"),
    )


def _normalize_line(line: str) -> str:
    text = (line or "").strip()
    text = re.sub(r"^\s*#{1,6}\s*", "", text)
    text = re.sub(r"^\s*[\-\*\d\.\)、:：]+\s*", "", text)
    return text.strip()


def _has_evidence_hint(text: str) -> bool:
    if not text:
        return False
    if any(marker in text for marker in EVIDENCE_MARKERS):
        return True
    if re.search(r"[“\"'].*?[”\"']", text):
        return True
    return False


def _is_policy_suggestion(text: str) -> bool:
    if not text:
        return False
    return any(marker in text for marker in POLICY_SUGGESTION_MARKERS)


def _truncate_conflict_item(text: str, max_chars: int = MAX_CONFLICT_ITEM_CHARS) -> str:
    content = (text or "").strip()
    if len(content) <= max_chars:
        return content
    return content[:max_chars].rstrip() + "..."


def check_consistency(
    novel_setting: str,
    character_state: str,
    global_summary: str,
    chapter_text: str,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.3,
    plot_arcs: str = "",
    interface_format: str = "OpenAI",
    max_tokens: int = 2048,
    timeout: int = 600,
) -> str:
    """调用 LLM 做一致性审校，返回纯文本结果。"""
    (
        novel_setting_for_review,
        character_state_for_review,
        global_summary_for_review,
        plot_arcs_for_review,
        chapter_text_for_review,
    ) = _prepare_review_inputs(
        novel_setting=novel_setting,
        character_state=character_state,
        global_summary=global_summary,
        plot_arcs=plot_arcs,
        chapter_text=chapter_text,
    )

    prompt = CONSISTENCY_PROMPT.format(
        novel_setting=novel_setting_for_review,
        character_state=character_state_for_review,
        global_summary=global_summary_for_review,
        plot_arcs=plot_arcs_for_review,
        chapter_text=chapter_text_for_review,
    )
    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    response = llm_adapter.invoke(prompt)
    write_llm_interaction_log(
        prompt=prompt,
        response=str(response or ""),
        stage="consistency_review",
        extra_meta={
            "model_name": model_name,
            "interface_format": interface_format,
        },
    )
    if not response:
        return "审校Agent无回复"
    return response.strip()


def has_obvious_conflict(review_text: str) -> bool:
    """判断 LLM 审校是否报告了明确冲突。

    仅在出现“明确存在冲突/矛盾/不一致”的表达时返回 True，
    避免把“未发现冲突但给出优化建议”的回复误判为硬阻断。
    """
    text = (review_text or "").strip()
    if not text:
        return False

    no_conflict_patterns = [
        r"无明显冲突",
        r"未发现明显冲突",
        r"未发现冲突",
        r"未检测到冲突",
        r"未见明显矛盾",
        r"不存在明显(冲突|矛盾|不一致)",
        r"总体(一致|连贯)",
        r"基本(一致|连贯)",
        r"无实质(冲突|矛盾)",
        r"无硬性(冲突|矛盾)",
    ]
    if any(re.search(p, text, flags=re.IGNORECASE) for p in no_conflict_patterns):
        # 若文本明确声明“无冲突”，仅当同时存在明确冲突证据时才拦截。
        # 这里不直接 return，交给下方逐句规则二次确认。
        pass

    clauses = [c.strip() for c in re.split(r"[。\n；;!?！？]+", text) if c.strip()]
    global_has_evidence = _has_evidence_hint(text)
    for raw_clause in clauses:
        clause = _normalize_line(raw_clause)
        if not clause:
            continue
        problem_prefix = re.search(r"^\s*问题\s*\d*\s*[:：]", clause) is not None
        has_conflict_kw = re.search(CONFLICT_KEYWORDS, clause, flags=re.IGNORECASE) is not None
        has_evidence = _has_evidence_hint(clause)
        is_policy = _is_policy_suggestion(clause)

        if not has_conflict_kw:
            if (
                problem_prefix
                and (has_evidence or global_has_evidence)
                and not re.search(TENTATIVE_MARKERS, clause, flags=re.IGNORECASE)
            ):
                return True
            continue

        has_negation = re.search(NEGATION_MARKERS, clause, flags=re.IGNORECASE) is not None
        has_certainty = re.search(CERTAINTY_MARKERS, clause, flags=re.IGNORECASE) is not None
        is_tentative = re.search(TENTATIVE_MARKERS, clause, flags=re.IGNORECASE) is not None
        has_hard_marker = re.search(HARD_CONFLICT_MARKERS, clause, flags=re.IGNORECASE) is not None

        # 常见表达："未发现硬性冲突，但存在潜在风险" -> 仅提示风险，不做硬阻断
        if re.search(r"未发现硬性(冲突|矛盾).*(潜在|可能|建议)", clause):
            continue

        # 否定表达优先判为非冲突，如“未发现冲突/无明显矛盾”。
        if has_negation and not re.search(r"(但|不过|然而|仍|依然|仍有|但有)", clause):
            continue

        # 仅“潜在/可能”风险不触发硬阻断。
        if is_tentative and not re.search(r"(严重|硬性|重大|必须修复)", clause):
            continue

        # 纯“设定条款优化/口径补充”类建议，不做硬阻断（除非给出明确证据）。
        if is_policy and not has_evidence and not has_hard_marker:
            continue

        # 结构化“问题X”默认视为冲突项（排除建议/口径类）。
        if problem_prefix and not is_tentative and not is_policy:
            return True

        # 对 LLM 结论做保守约束：默认要求“冲突 + 证据”才硬阻断。
        # 仅在明确使用“硬性/致命/无法自洽”等词时允许无证据阻断。
        if not has_evidence and not has_hard_marker:
            continue

        # 有冲突关键词 + 明确性表达，或直接出现强冲突词，即判定为冲突。
        if has_hard_marker or has_certainty or re.search(r"(严重|硬性|重大)", clause):
            return True

    return False


def extract_conflict_items(review_text: str, limit: int = 3) -> list[str]:
    """从一致性审校文本中提取明确冲突条目。"""
    text = (review_text or "").strip()
    if not text:
        return []
    items: list[str] = []
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    global_has_evidence = _has_evidence_hint(text)
    for raw_line in lines:
        if len(items) >= limit:
            break
        line = _normalize_line(raw_line)
        if not line:
            continue
        if re.search(r"(结论|报告|如下|存在\s*\d+\s*处|存在明显冲突|明显冲突与不一致)", line):
            continue
        if re.search(r"^(经|经过|基于|根据|检查|核对|比对|复核).*(存在|发现).*(冲突|不一致)", line):
            continue
        if re.search(r"(存在|发现).*(\d+|多处).*(冲突|不一致)", line) and "问题" not in line:
            continue
        has_conflict_kw = re.search(CONFLICT_KEYWORDS, line, flags=re.IGNORECASE) is not None
        has_evidence = _has_evidence_hint(line)
        is_policy = _is_policy_suggestion(line)
        has_hard_marker = re.search(HARD_CONFLICT_MARKERS, line, flags=re.IGNORECASE) is not None

        if not has_conflict_kw:
            if (
                re.search(r"^\s*问题\s*\d*\s*[:：]", line)
                and (has_evidence or global_has_evidence)
                and not re.search(TENTATIVE_MARKERS, line, flags=re.IGNORECASE)
            ):
                items.append(_truncate_conflict_item(line))
            continue
        if re.search(NEGATION_MARKERS, line, flags=re.IGNORECASE) and not re.search(r"(但|不过|然而|仍|依然|仍有|但有)", line):
            continue
        if re.search(TENTATIVE_MARKERS, line, flags=re.IGNORECASE) and not re.search(r"(严重|硬性|重大|必须修复)", line):
            continue
        if is_policy and not has_evidence and not has_hard_marker:
            continue
        if re.search(r"^\s*问题\s*\d*\s*[:：]", line) and not is_policy:
            items.append(_truncate_conflict_item(line))
            continue
        if not has_evidence and not has_hard_marker:
            continue
        items.append(_truncate_conflict_item(line))
    return items
