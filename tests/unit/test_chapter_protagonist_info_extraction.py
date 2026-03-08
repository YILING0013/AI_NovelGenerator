from __future__ import annotations

from pathlib import Path

from novel_generator import chapter as chapter_module


def test_extract_protagonist_info_prefers_explicit_real_name(monkeypatch, tmp_path: Path):
    architecture_path = tmp_path / "Novel_architecture.txt"
    architecture_path.write_text(
        """
## 0. 项目总纲
一句话故事：
主角重生边荒废脉，持残缺天书“看见命运缝线”。

### 4.3 天书系统（主角核心秘契）

### 5.1 主角成长弧
主角实名：秦昭野（字：玄戈）
主角推进路线建议（阶段化）：
1. 开局先求生。
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        chapter_module,
        "resolve_architecture_file",
        lambda *_args, **_kwargs: str(architecture_path),
    )

    info = chapter_module.extract_protagonist_info(str(tmp_path))

    assert info["protagonist_name"] == "秦昭野"
    assert info["protagonist_name"] != "1"
    assert info["system_name"] == "天书系统"
    assert "命运缝线" in info["core_abilities"]


def test_extract_protagonist_info_does_not_treat_numbered_list_as_name(monkeypatch, tmp_path: Path):
    architecture_path = tmp_path / "Novel_architecture.txt"
    architecture_path.write_text(
        """
### 5.1 主角成长弧
主角推进路线建议（阶段化）：
1. 先隐藏身份。
2. 再积累资源。
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        chapter_module,
        "resolve_architecture_file",
        lambda *_args, **_kwargs: str(architecture_path),
    )

    info = chapter_module.extract_protagonist_info(str(tmp_path))

    assert info["protagonist_name"] == "（未指定）"
    assert info["protagonist_name"] != "1"


def test_extract_protagonist_info_rejects_numeric_placeholder(monkeypatch, tmp_path: Path):
    architecture_path = tmp_path / "Novel_architecture.txt"
    architecture_path.write_text(
        """
主角：1
### 4.3 天书系统（主角核心秘契）
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        chapter_module,
        "resolve_architecture_file",
        lambda *_args, **_kwargs: str(architecture_path),
    )

    info = chapter_module.extract_protagonist_info(str(tmp_path))

    assert info["protagonist_name"] == "（未指定）"
    assert info["system_name"] == "天书系统"
