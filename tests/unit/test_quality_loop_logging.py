from __future__ import annotations

from typing import cast

from novel_generator.quality_loop_controller import (
    LLM_LOG_PROMPT_CHAR_LIMIT,
    QualityLoopController,
)


def test_log_llm_conversation_keeps_long_prompt_for_runtime_audit(tmp_path):
    controller = cast(
        QualityLoopController,
        cast(object, type("_DummyController", (), {"llm_log_dir": str(tmp_path / "llm_logs")})()),
    )
    prompt = "A" * (LLM_LOG_PROMPT_CHAR_LIMIT + 37)
    response = "ok"

    QualityLoopController._log_llm_conversation(
        controller,
        chapter_num=1,
        iteration=1,
        stage="draft",
        prompt=prompt,
        response=response,
    )

    log_files = list((tmp_path / "llm_logs" / "chapter_1").glob("iter1_draft_*.md"))
    assert len(log_files) == 1

    content = log_files[0].read_text(encoding="utf-8")
    marker_start = "## Prompt\n\n```\n"
    marker_end = "\n```\n\n## Response"
    prompt_block = content.split(marker_start, 1)[1].split(marker_end, 1)[0]

    assert prompt_block.startswith("A" * LLM_LOG_PROMPT_CHAR_LIMIT)
    assert prompt_block.endswith("...")
    assert len(prompt_block) == LLM_LOG_PROMPT_CHAR_LIMIT + 3
