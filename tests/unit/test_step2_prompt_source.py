from __future__ import annotations

import prompt_definitions
from novel_generator.blueprint import StrictChapterGenerator


def _create_generator(monkeypatch) -> StrictChapterGenerator:
    monkeypatch.setattr(
        "novel_generator.blueprint.create_llm_adapter",
        lambda **kwargs: object(),
    )
    return StrictChapterGenerator(
        interface_format="test",
        api_key="test",
        base_url="http://test.local",
        llm_model="test-model",
        timeout=1,
    )


def test_step2_guided_prompt_comes_from_prompt_definitions(monkeypatch):
    generator = _create_generator(monkeypatch)

    rendered = generator._create_strict_prompt_with_guide(
        architecture_text="架构文本",
        context_guide="情节锁定：第3章必须出现主角与反派首次正面冲突",
        chapter_list="第1章 - 开端\n第2章 - 发酵",
        start_chapter=3,
        end_chapter=4,
        user_guidance="额外要求：强化冲突升级",
    )

    expected = prompt_definitions.STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT.format(
        novel_title="本书",
        start_chapter=3,
        end_chapter=4,
        chapter_count=2,
        context_guide="情节锁定：第3章必须出现主角与反派首次正面冲突",
        chapter_list="第1章 - 开端\n第2章 - 发酵",
        user_guidance="额外要求：强化冲突升级",
        blueprint_example=prompt_definitions.BLUEPRINT_EXAMPLE_V3.strip(),
    )

    assert rendered == expected
