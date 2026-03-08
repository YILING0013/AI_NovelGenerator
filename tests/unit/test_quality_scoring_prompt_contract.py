from __future__ import annotations

from chapter_quality_analyzer import LLMSemanticScorer


def test_contextual_scoring_prompt_enforces_json_only_output() -> None:
    prompt = LLMSemanticScorer.SCORING_PROMPT_WITH_CONTEXT

    assert "只允许输出一个JSON对象" in prompt
    assert "禁止Markdown代码块" in prompt
    assert "所有评分字段必须是0-10之间的数字" in prompt


def test_contextual_scoring_prompt_checks_continuity_costs() -> None:
    prompt = LLMSemanticScorer.SCORING_PROMPT_WITH_CONTEXT

    assert "已成立的后果、代价、未解问题、关系变化必须延续" in prompt
    assert "伤势、代价、误会、关系变化在本章被无解释重置" in prompt


def test_plain_scoring_prompt_checks_continuity_and_actionability() -> None:
    prompt = LLMSemanticScorer.SCORING_PROMPT

    assert "已成立的后果、代价、误会、关系变化需持续生效" in prompt
    assert "章节只堆新设定、不处理旧问题，导致连续性断裂" in prompt
    assert "问题描述`与`修改建议`必须简短、具体、可执行" in prompt
