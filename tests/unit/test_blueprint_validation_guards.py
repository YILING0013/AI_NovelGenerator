from __future__ import annotations

from pathlib import Path

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


def _build_chapter(chapter_num: int, title: str, location: str) -> str:
    return "\n".join(
        [
            f"第{chapter_num}章 - {title}",
            "## 1. 基础元信息",
            f"章节序号：第{chapter_num}章",
            f"章节标题：{title}",
            f"定位：{location}",
            "核心功能：推进主线",
            "字数目标：4500字",
            "出场角色：主角",
            "## 2. 张力与冲突",
            "冲突类型：生存",
            "核心冲突点：测试冲突",
            "紧张感曲线：铺垫→爬升→爆发→回落",
            "## 3. 匠心思维应用",
            "应用场景：测试",
            "思维模式：测试",
            "视觉化描述：测试",
            "经典台词：测试",
            "## 4. 伏笔与信息差",
            "本章植入伏笔：测试",
            "本章回收伏笔：无",
            "信息差控制：测试",
            "## 5. 暧昧与修罗场",
            "涉及的女性角色互动：本章不涉及女性角色互动",
            "## 6. 剧情精要",
            "开场：测试",
            "发展：测试",
            "高潮：测试",
            "收尾：测试",
            "## 7. 衔接设计",
            "承上：测试",
            "转场：测试",
            "启下：测试",
        ]
    )


def test_strict_validation_blocks_location_placeholders(monkeypatch) -> None:
    generator = _create_generator(monkeypatch)
    content = _build_chapter(1, "测试标题", "第X卷 未知 - 子幕X 待定")

    report = generator._strict_validation(content, 1, 1)

    assert report["is_valid"] is False
    assert any("定位含占位符" in item for item in report["errors"])


def test_collect_recent_title_conflicts_detects_duplicate_title(monkeypatch) -> None:
    generator = _create_generator(monkeypatch)
    existing = "\n\n".join(
        [
            _build_chapter(1, "起势", "第1卷 序幕 - 子幕1 开端"),
            _build_chapter(2, "暗流", "第1卷 序幕 - 子幕2 发酵"),
            _build_chapter(3, "重复标题", "第1卷 序幕 - 子幕3 反转"),
        ]
    )
    generated = _build_chapter(4, "重复标题", "第1卷 序幕 - 子幕4 承压")

    conflicts = generator._collect_recent_title_conflicts(generated, existing, lookback=120)

    assert conflicts
    assert "标题重复" in conflicts[0]


def test_builtin_gate_blocks_duplicate_titles_and_location_placeholders(monkeypatch, tmp_path: Path) -> None:
    generator = _create_generator(monkeypatch)
    directory_file = tmp_path / "Novel_directory.txt"
    directory_file.write_text(
        "\n\n".join(
            [
                _build_chapter(1, "重复标题", "第X卷 未知 - 子幕1 开端"),
                _build_chapter(2, "重复标题", "第1卷 正卷 - 子幕2 推进"),
            ]
        ),
        encoding="utf-8",
    )

    passed, report = generator._run_builtin_directory_quality_gate(str(directory_file))
    reasons = report.get("hard_fail_reasons", [])

    assert passed is False
    assert any("章节标题重复" in str(reason) for reason in reasons)
    assert any("定位字段含占位符" in str(reason) for reason in reasons)
