from __future__ import annotations

from novel_generator import finalization as finalization_module


def test_normalize_protagonist_name_replaces_numeric_placeholder_in_text():
    source = "1从后巷翻出，1：你们先走。"
    normalized = finalization_module._normalize_protagonist_name_drift(source, "秦昭野")

    assert "秦昭野从后巷翻出" in normalized
    assert "秦昭野：你们先走" in normalized
    assert "1从后巷翻出" not in normalized


def test_normalize_protagonist_name_does_not_touch_chapter_number():
    source = "第1章 寒门惊雷，死局求生。第1卷开始。"
    normalized = finalization_module._normalize_protagonist_name_drift(source, "秦昭野")

    assert normalized == source


def test_normalize_protagonist_name_does_not_touch_ordinary_numeric_quantifier():
    source = "他今天只出手1次，就压住了全场。"
    normalized = finalization_module._normalize_protagonist_name_drift(source, "秦昭野")

    assert normalized == source
