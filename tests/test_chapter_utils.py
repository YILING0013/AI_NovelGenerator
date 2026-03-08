# tests/test_chapter_utils.py
# -*- coding: utf-8 -*-
"""
chapter_utils.py 模块单元测试

测试统一章节解析工具的各项功能。

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import unittest
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.chapter_utils import (
    extract_chapter_number,
    extract_chapter_title,
    split_chapters_by_header,
    extract_single_chapter,
    get_chapter_info_header,
    validate_chapter_number,
    get_next_chapter_number,
    parse_chapter_range,
    count_chapters
)


class TestExtractChapterNumber(unittest.TestCase):
    """测试章节号提取功能"""

    def test_markdown_bold_format(self):
        """测试 Markdown 加粗格式"""
        self.assertEqual(extract_chapter_number("### **第1章 - 标题**"), 1)
        self.assertEqual(extract_chapter_number("### **第10章 - 高潮**"), 10)

    def test_simple_format(self):
        """测试简单格式"""
        self.assertEqual(extract_chapter_number("第1章 - 开篇"), 1)
        self.assertEqual(extract_chapter_number("第5章 - 洞悉本源"), 5)

    def test_no_title_format(self):
        """测试无标题格式"""
        self.assertEqual(extract_chapter_number("第1章)"), 1)

    def test_no_separator_format(self):
        """测试无分隔符格式"""
        self.assertEqual(extract_chapter_number("第1章 标题"), 1)

    def test_brackets_format(self):
        """测试方括号格式"""
        self.assertEqual(extract_chapter_number("第1章][标题]"), 1)

    def test_invalid_text(self):
        """测试无效文本"""
        self.assertIsNone(extract_chapter_number("无效文本"))
        self.assertIsNone(extract_chapter_number(""))
        self.assertIsNone(extract_chapter_number("第章"))


class TestExtractChapterTitle(unittest.TestCase):
    """测试章节标题提取功能"""

    def test_simple_title(self):
        """测试简单标题提取"""
        self.assertEqual(extract_chapter_title("第1章 - 乱葬岗的修复师"), "乱葬岗的修复师")
        self.assertEqual(extract_chapter_title("第2章 - 洞悉本源"), "洞悉本源")

    def test_markdown_title(self):
        """测试 Markdown 格式标题"""
        self.assertEqual(extract_chapter_title("### **第1章 - [开篇]**"), "开篇")

    def test_no_title(self):
        """测试无标题情况"""
        self.assertEqual(extract_chapter_title("第1章"), "")

    def test_invalid_text(self):
        """测试无效文本"""
        self.assertEqual(extract_chapter_title(""), "")
        self.assertEqual(extract_chapter_title("无效文本"), "")


class TestSplitChaptersByHeader(unittest.TestCase):
    """测试章节分割功能"""

    def setUp(self):
        """测试前准备"""
        self.test_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
*   **章节**：第 1 章 - 乱葬岗的修复师
*   **定位**：第 1 卷 瓷骨道心 - 子幕 1 破碎的开端

第2章 - 洞悉本源

## 1. 基础元信息
*   **章节**：第 2 章 - 洞悉本源
"""

    def test_split_all_chapters(self):
        """测试分割所有章节"""
        chapters = split_chapters_by_header(self.test_content)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['chapter_number'], 1)
        self.assertEqual(chapters[1]['chapter_number'], 2)

    def test_split_with_range(self):
        """测试指定范围分割"""
        chapters = split_chapters_by_header(self.test_content, min_chapter=2, max_chapter=2)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['chapter_number'], 2)

    def test_chapter_info(self):
        """测试章节信息"""
        chapters = split_chapters_by_header(self.test_content)
        first_chapter = chapters[0]
        self.assertEqual(first_chapter['title'], "乱葬岗的修复师")
        self.assertEqual(first_chapter['header_line'], "第1章 - 乱葬岗的修复师")

    def test_empty_content(self):
        """测试空内容"""
        chapters = split_chapters_by_header("")
        self.assertEqual(len(chapters), 0)


class TestExtractSingleChapter(unittest.TestCase):
    """测试单章提取功能"""

    def setUp(self):
        """测试前准备"""
        self.test_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
内容1

第2章 - 洞悉本源

## 1. 基础元信息
内容2
"""

    def test_extract_existing_chapter(self):
        """测试提取存在的章节"""
        chapter = extract_single_chapter(self.test_content, 1)
        self.assertIsNotNone(chapter)
        self.assertIn("第1章 - 乱葬岗的修复师", chapter)
        self.assertIn("内容1", chapter)

    def test_extract_nonexistent_chapter(self):
        """测试提取不存在的章节"""
        chapter = extract_single_chapter(self.test_content, 3)
        self.assertIsNone(chapter)


class TestGetChapterInfoHeader(unittest.TestCase):
    """测试章节头部信息解析"""

    def test_parse_header(self):
        """测试解析头部"""
        content = """第1章 - 乱葬岗的修复师

*   **章节**：第 1 章
*   **定位**：第 1 卷
"""
        info = get_chapter_info_header(content)
        self.assertEqual(info['chapter_number'], 1)
        self.assertEqual(info['chapter_title'], "乱葬岗的修复师")
        self.assertEqual(info['raw_header'], "第1章 - 乱葬岗的修复师")
        self.assertIn('章节', info['fields'])

    def test_empty_content(self):
        """测试空内容"""
        info = get_chapter_info_header("")
        self.assertEqual(info, {})


class TestValidateChapterNumber(unittest.TestCase):
    """测试章节号验证"""

    def test_valid_chapter(self):
        """测试有效章节号"""
        content = "第1章 - 标题\n内容"
        self.assertTrue(validate_chapter_number(content, 1))

    def test_invalid_chapter(self):
        """测试无效章节号"""
        content = "第2章 - 标题\n内容"
        self.assertFalse(validate_chapter_number(content, 1))

    def test_empty_content(self):
        """测试空内容"""
        self.assertFalse(validate_chapter_number("", 1))


class TestGetNextChapterNumber(unittest.TestCase):
    """测试获取下一章节号"""

    def test_with_existing_chapters(self):
        """测试有现有章节"""
        content = """
第1章 - 标题1
内容1

第5章 - 标题5
内容5
"""
        self.assertEqual(get_next_chapter_number(content), 6)

    def test_with_empty_content(self):
        """测试空内容"""
        self.assertEqual(get_next_chapter_number(""), 1)


class TestParseChapterRange(unittest.TestCase):
    """测试范围解析"""

    def setUp(self):
        """测试前准备"""
        self.test_content = """
第1章 - 标题1
内容1

第2章 - 标题2
内容2

第3章 - 标题3
内容3
"""

    def test_parse_range(self):
        """测试范围解析"""
        result = parse_chapter_range(self.test_content, 1, 2)
        self.assertEqual(len(result), 2)
        self.assertIn(1, result)
        self.assertIn(2, result)

    def test_parse_single(self):
        """测试单章解析"""
        result = parse_chapter_range(self.test_content, 2, 2)
        self.assertEqual(len(result), 1)
        self.assertIn(2, result)


class TestCountChapters(unittest.TestCase):
    """测试章节数量统计"""

    def test_count(self):
        """测试统计数量"""
        content = """
第1章 - 标题1
内容1

第2章 - 标题2
内容2
"""
        self.assertEqual(count_chapters(content), 2)

    def test_count_empty(self):
        """测试空内容"""
        self.assertEqual(count_chapters(""), 0)


if __name__ == '__main__':
    unittest.main()
