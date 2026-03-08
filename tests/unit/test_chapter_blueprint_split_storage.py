from __future__ import annotations

from chapter_directory_parser import (
    get_chapter_blueprint_file,
    load_chapter_info,
    split_blueprint_to_chapter_files,
)


_SAMPLE_BLUEPRINT = """
第1章 - 起势
## 1. 基础元信息
章节标题：起势
核心冲突点：第一章冲突

第2章 - 转折
## 1. 基础元信息
章节标题：转折
核心冲突点：第二章冲突
""".strip()


def test_split_blueprint_to_chapter_files_writes_per_chapter_files(tmp_path):
    result = split_blueprint_to_chapter_files(str(tmp_path), _SAMPLE_BLUEPRINT, remove_stale=True)

    chapter1 = tmp_path / "chapter_blueprints" / "chapter_1.txt"
    chapter2 = tmp_path / "chapter_blueprints" / "chapter_2.txt"
    assert result["chapter_count"] == 2
    assert chapter1.exists()
    assert chapter2.exists()
    assert "第1章 - 起势" in chapter1.read_text(encoding="utf-8")


def test_split_blueprint_to_chapter_files_remove_stale(tmp_path):
    split_dir = tmp_path / "chapter_blueprints"
    split_dir.mkdir(parents=True, exist_ok=True)
    stale = split_dir / "chapter_99.txt"
    stale.write_text("stale", encoding="utf-8")

    result = split_blueprint_to_chapter_files(str(tmp_path), _SAMPLE_BLUEPRINT, remove_stale=True)
    assert stale.as_posix() in result["removed_files"]
    assert not stale.exists()


def test_load_chapter_info_fallback_creates_split_cache(tmp_path):
    info = load_chapter_info(
        str(tmp_path),
        1,
        blueprint_text_fallback=_SAMPLE_BLUEPRINT,
    )

    chapter_file = get_chapter_blueprint_file(str(tmp_path), 1)
    assert info["chapter_title"] == "起势"
    assert info["chapter_summary"] == "第一章冲突"
    assert info["next_chapter_summary"] == "第二章冲突"
    assert chapter_file.endswith("chapter_blueprints/chapter_1.txt")
