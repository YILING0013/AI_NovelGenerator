from __future__ import annotations

from novel_generator.architecture_parser import ArchitectureParser


def test_architecture_parser_splits_markdown_numbered_sections(tmp_path):
    architecture_file = tmp_path / "Novel_architecture.txt"
    architecture_file.write_text(
        """
## 0. 项目总纲
核心书名：《测试书》
目标字数：100万字

## 1. 核心种子
主角重生后争夺命运书写权。

## 2. 主角战力体系
【星历术】效果：用于时序推演。
""".strip(),
        encoding="utf-8",
    )

    parser = ArchitectureParser(str(tmp_path))
    data = parser.parse()

    assert 0 in parser.sections
    assert 1 in parser.sections
    assert data.title == "测试书"
    assert 0 in data.sections_parsed
