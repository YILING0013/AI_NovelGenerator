from __future__ import annotations

from novel_generator.chapter_contract_guard import (
    build_chapter_contract,
    build_chapter_contract_prompt,
    detect_chapter_contract_drift,
    detect_paragraph_contract_drift,
    merge_chapter_paragraphs,
    split_chapter_paragraphs,
)


def test_build_chapter_contract_collects_required_and_forbidden_terms():
    contract = build_chapter_contract(
        {
            "chapter_title": "夜雨追凶",
            "chapter_role": "冲突升级",
            "chapter_purpose": "追查线索并锁定嫌疑人",
            "characters_involved": "林舟、苏璃",
            "key_items": "天书残页、玄铁令",
            "scene_location": "青石镇、破庙",
        },
        user_guidance="禁止内容：程序、Bug、检测到",
    )

    required = contract["required_terms"]
    assert "林舟" in required["characters"]
    assert "天书残页" in required["key_items"]
    assert "青石镇" in required["locations"]
    assert "程序" in contract["forbidden_terms"]
    assert "Bug" in contract["forbidden_terms"]


def test_build_chapter_contract_prompt_contains_contract_lines():
    contract = build_chapter_contract(
        {
            "chapter_title": "夜雨追凶",
            "chapter_role": "冲突升级",
            "chapter_purpose": "追查线索",
            "characters_involved": "林舟、苏璃",
            "key_items": "天书残页",
            "scene_location": "青石镇",
        }
    )
    prompt = build_chapter_contract_prompt(contract)

    assert "章节契约卡" in prompt
    assert "必须覆盖人物锚点" in prompt
    assert "林舟" in prompt


def test_detect_chapter_contract_drift_flags_missing_required_and_forbidden():
    contract = build_chapter_contract(
        {
            "characters_involved": "林舟、苏璃",
            "key_items": "天书残页",
            "scene_location": "青石镇",
        },
        user_guidance="禁止内容：程序",
    )
    chapter_text = "苏璃在破庙里开启了程序面板，却没有提到关键道具。"
    issues = detect_chapter_contract_drift(chapter_text, contract, max_issues=4)

    assert any("未覆盖关键要素" in issue for issue in issues)
    assert any("命中禁止要素" in issue for issue in issues)


def test_detect_chapter_contract_drift_passes_when_contract_is_covered():
    contract = build_chapter_contract(
        {
            "characters_involved": "林舟、苏璃",
            "key_items": "天书残页",
            "scene_location": "青石镇",
        },
        user_guidance="禁止内容：程序",
    )
    chapter_text = "林舟与苏璃在青石镇破庙中争夺天书残页，气氛紧绷。"
    issues = detect_chapter_contract_drift(chapter_text, contract)

    assert issues == []


def test_split_and_merge_chapter_paragraphs_roundtrip():
    content = "第一段。\n\n第二段。\n\n第三段。"
    paragraphs = split_chapter_paragraphs(content)
    merged = merge_chapter_paragraphs(paragraphs)

    assert paragraphs == ["第一段。", "第二段。", "第三段。"]
    assert merged == content


def test_detect_paragraph_contract_drift_flags_forbidden_and_opening_anchor():
    contract = build_chapter_contract(
        {
            "characters_involved": "林舟、苏璃",
            "scene_location": "青石镇",
            "key_items": "天书残页",
        },
        user_guidance="禁止内容：程序",
    )
    text = "雨夜里，山门外空无一人。\n\n苏璃打开了程序面板，眉头紧皱。"
    issues = detect_paragraph_contract_drift(text, contract, max_paragraph_issues=4, opening_window=1)

    assert any(issue.get("paragraph_index") == 1 for issue in issues)
    assert any("命中禁止要素" in "；".join(issue.get("issues", [])) for issue in issues)
    assert any("开篇人物锚点缺失" in "；".join(issue.get("issues", [])) for issue in issues)
