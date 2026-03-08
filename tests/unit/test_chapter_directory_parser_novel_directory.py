from __future__ import annotations

from chapter_directory_parser import get_chapter_info_from_blueprint


def test_get_chapter_info_supports_novel_directory_fields():
    blueprint_text = """
第1章 - 寒门惊雷，死局求生
## 1. 基础元信息
定位：第1卷 边荒血火 - 子幕1 命轨重置
核心功能：确立重生与生存危机的双重悬念
出场角色：秦昭野（主角）、秦德海（反派）
## 2. 张力与冲突
核心冲突点：主角仅剩三天寿命，必须破局
紧张感曲线：压抑→爆发→回落

第2章 - 废脉藏锋，天书血祭
## 1. 基础元信息
定位：第1卷 边荒死局 - 子幕2 绝境初醒
核心功能：激活天书并确立隐锋生存策略
出场角色：秦昭野（主角）、赵三（恶奴）
## 2. 张力与冲突
核心冲突点：废脉与求生欲的矛盾
紧张感曲线：压抑→剧痛→紧迫
""".strip()

    info = get_chapter_info_from_blueprint(blueprint_text, 1)

    assert info["chapter_title"] == "寒门惊雷，死局求生"
    assert info["chapter_role"] == "第1卷 边荒血火 - 子幕1 命轨重置"
    assert info["chapter_purpose"] == "确立重生与生存危机的双重悬念"
    assert info["chapter_summary"] == "主角仅剩三天寿命，必须破局"
    assert info["suspense_level"] == "压抑→爆发→回落"
    assert "秦昭野" in info["characters_involved"]


def test_get_chapter_info_includes_next_chapter_summary():
    blueprint_text = """
第1章 - A
核心冲突点：第一章冲突

第2章 - B
核心冲突点：第二章冲突
""".strip()

    info = get_chapter_info_from_blueprint(blueprint_text, 1)
    assert info["chapter_summary"] == "第一章冲突"
    assert info["next_chapter_summary"] == "第二章冲突"
