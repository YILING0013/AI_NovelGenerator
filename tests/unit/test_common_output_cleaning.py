# -*- coding: utf-8 -*-
"""Regression tests for LLM chapter output cleaning utilities."""

from novel_generator.common import clean_llm_output, extract_revised_text_payload


def test_extract_revised_text_from_half_structured_payload() -> None:
    long_body = "这是正文。" * 80
    payload = (
        '"change_log": ["修复1"],\n'
        '"self_check": ["ok"],\n'
        f'"revised_text": "第7章 请君入瓮\\n\\n{long_body}'
    )

    extracted = extract_revised_text_payload(payload)

    assert extracted is not None
    assert extracted.startswith("第7章 请君入瓮")
    assert "change_log" not in extracted
    assert "\\n" not in extracted


def test_clean_llm_output_removes_editorial_preamble_and_appendix() -> None:
    text = (
        "你好，我是负责本项目的金牌编辑。\n\n"
        "第14章 腥红画屏后的妖瞳\n\n"
        "正文第一段。\n\n"
        "编辑修改精评\n"
        "*   视觉优化\n"
    )

    cleaned = clean_llm_output(text)

    assert cleaned.startswith("第14章 腥红画屏后的妖瞳")
    assert "金牌编辑" not in cleaned
    assert "编辑修改精评" not in cleaned


def test_clean_llm_output_prefers_revised_text_field() -> None:
    body = "正文段落。" * 100
    payload = (
        "{\n"
        '  "change_log": ["改动A"],\n'
        '  "self_check": ["通过"],\n'
        f'  "revised_text": "第5章 剜心之偿\\n\\n{body}"\n'
        "}\n"
    )

    cleaned = clean_llm_output(payload)

    assert cleaned.startswith("第5章 剜心之偿")
    assert "change_log" not in cleaned
    assert "self_check" not in cleaned
