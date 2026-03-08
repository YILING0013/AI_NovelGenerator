from __future__ import annotations

from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_context,
    build_runtime_architecture_view,
    contains_archive_sections,
)


def test_runtime_view_keeps_only_execution_ranges():
    architecture_text = """
## 0. Meta
keep-0

## 12. Core
keep-12

## 13. Archive Start
drop-13

## 45. Archive Mid
drop-45

## 88. Runtime Restart
keep-88

## 136. Runtime Gate
keep-136
""".strip()

    runtime_text = build_runtime_architecture_view(architecture_text)

    assert "## 0." in runtime_text
    assert "## 12." in runtime_text
    assert "## 88." in runtime_text
    assert "## 136." in runtime_text
    assert "## 13." not in runtime_text
    assert "## 45." not in runtime_text
    assert contains_archive_sections(runtime_text) is False


def test_runtime_view_falls_back_to_original_when_no_top_sections():
    raw_text = "架构文本没有标准二级标题"

    runtime_text = build_runtime_architecture_view(raw_text)

    assert runtime_text == raw_text


def test_runtime_architecture_context_respects_budget_and_keeps_required_sections():
    architecture_text = """
## 0. Meta
meta-line-0

## 12. Core
core-line-12

## 88. Runtime
runtime-line-88

## 104. Style
style-line-104

## 136. Gate
gate-line-136
""".strip()

    context = build_runtime_architecture_context(
        architecture_text,
        max_chars=120,
        required_sections=(0, 88, 136),
        section_numbers_hint=(104,),
    )

    assert "## 0." in context
    assert "## 88." in context
    assert "## 136." in context
    assert len(context) <= 120 + 64  # 允许附加裁剪提示


def test_runtime_architecture_context_prioritizes_focus_hint_sections():
    architecture_text = """
## 0. Meta
meta

## 88. Runtime
runtime

## 104. Style Rule
古典口吻 诗性表达 文风宪章

## 120. Misc
杂项说明

## 136. Gate
gate
""".strip()

    context = build_runtime_architecture_context(
        architecture_text,
        max_chars=280,
        focus_text="古典口吻 文风",
        required_sections=(0, 88, 136),
    )

    assert "## 104. Style Rule" in context
