# -*- coding: utf-8 -*-
"""
章节目录解析器测试 - 基于实际代码结构
"""
import pytest
from chapter_directory_parser import parse_chapter_blueprint

class TestChapterDirectoryParser:
    """章节目录解析器测试类"""

    def test_parse_basic_fields(self):
        """测试基础字段解析"""
        content = """### **第1章 - 勇气的考验**
本章定位：[开端章节]
核心作用：[引入主人公]
悬念密度：[中等]
伏笔操作：[古树符号]
认知颠覆：[无]
本章简述：[主人公开始冒险旅程]"""

        results = parse_chapter_blueprint(content)
        assert len(results) == 1
        assert results[0]["chapter_number"] == 1
        assert results[0]["chapter_role"] == "开端章节"
        assert results[0]["chapter_purpose"] == "引入主人公"

    def test_parse_extended_fields(self):
        """测试扩展字段解析"""
        content = """### **第2章 - 智慧的启迪**
写作重点：智慧成长
作用：解开古老谜题
张力评级：中等
长期伏笔：壁画预言
递进式悬念：下一个谜题暗示"""

        results = parse_chapter_blueprint(content)
        assert len(results) == 1
        assert results[0]["chapter_number"] == 2
        assert results[0]["chapter_title"] == "智慧的启迪"

    def test_missing_fields_handling(self):
        """测试缺失字段处理"""
        content = """### **第3章 - 简单章节**
本章简述：[简单描述]"""

        results = parse_chapter_blueprint(content)
        assert len(results) == 1
        assert results[0]["chapter_number"] == 3
        assert results[0]["chapter_title"] == "简单章节"

    def test_multiple_chapters(self):
        """测试多章节解析"""
        content = """### **第1章 - 第一章**
本章定位：[开端]

### **第2章 - 第二章**
本章定位：[发展]"""

        results = parse_chapter_blueprint(content)
        assert len(results) == 2
        assert results[0]["chapter_number"] == 1
        assert results[1]["chapter_number"] == 2