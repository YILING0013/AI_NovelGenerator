# -*- coding: utf-8 -*-
"""
章节目录解析器测试
"""
import pytest
from chapter_directory_parser import ChapterDirectoryParser

class TestChapterDirectoryParser:
    """章节目录解析器测试类"""

    def test_parse_basic_fields(self):
        """测试基础字段解析"""
        parser = ChapterDirectoryParser()
        content = """第一章：测试章节
章节标题：测试章节
字数目标：1500
核心冲突：测试冲突
时间地点：测试地点
本章简介：测试简介"""

        result = parser.parse(content)
        assert result["chapter_title"] == "测试章节"
        assert result["word_count_target"] == 1500
        assert result["core_conflict"] == "测试冲突"

    def test_parse_extended_fields(self):
        """测试扩展字段解析"""
        parser = ChapterDirectoryParser()
        content = """第一章：测试章节
章节标题：测试章节
情感弧光：测试弧光
钩子设计：测试钩子
伏笔线索：测试伏笔
冲突设计：测试冲突设计"""

        result = parser.parse(content)
        assert result["emotional_arc"] == "测试弧光"
        assert result["hook_design"] == "测试钩子"
        assert result["foreshadowing"] == "测试伏笔"
        assert result["conflict_design"] == "测试冲突设计"

    def test_missing_fields_handling(self):
        """测试缺失字段处理"""
        parser = ChapterDirectoryParser()
        content = """第一章：测试章节
章节标题：测试章节"""

        result = parser.parse(content)
        assert result["chapter_title"] == "测试章节"
        assert result["word_count_target"] is None  # 默认值

    def test_multiple_chapters(self):
        """测试多章节解析"""
        parser = ChapterDirectoryParser()
        content = """第一章：第一章
章节标题：第一章

第二章：第二章
章节标题：第二章"""

        results = parser.parse_multiple(content)
        assert len(results) == 2
        assert results[0]["chapter_title"] == "第一章"
        assert results[1]["chapter_title"] == "第二章"
