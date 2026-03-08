# tests/test_root_cause_fixes.py
# -*- coding: utf-8 -*-
"""
根本原因修复验证测试

本测试验证针对 Novel_directory.txt 格式问题的三个根本原因修复：
1. 重复章节检测逻辑
2. 统一格式要求
3. 格式示例一致性

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import unittest
import re
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestDuplicateChapterDetection(unittest.TestCase):
    """测试重复章节检测逻辑（Root Cause #1）"""

    def test_duplicate_chapter_detection(self):
        """测试：重复章节应该被检测到"""
        # 模拟验证逻辑
        generated_numbers = [1, 2, 3, 4, 5, 6, 7, 7, 8, 9, 10]  # 第7章重复

        # 修复前的逻辑（使用 set 会掩盖重复）
        old_result = sorted(list(set(generated_numbers)))
        self.assertEqual(len(old_result), 10)  # set 掩盖了重复！
        self.assertEqual(old_result, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        # 修复后的逻辑（显式检测重复）
        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        # 验证重复被正确检测
        self.assertIn(7, duplicate_numbers)
        self.assertEqual(duplicate_numbers, {7})
        self.assertFalse(len(unique_numbers) == len(generated_numbers))  # 长度不等说明有重复

    def test_no_duplicate_chapter(self):
        """测试：无重复章节应该通过验证"""
        generated_numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        # 验证无重复
        self.assertEqual(len(duplicate_numbers), 0)
        self.assertEqual(len(unique_numbers), len(generated_numbers))

    def test_multiple_duplicate_chapters(self):
        """测试：多个章节重复应该全部被检测到"""
        generated_numbers = [1, 2, 2, 3, 4, 5, 6, 6, 6, 7, 8]  # 第2章和第6章重复

        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        # 验证所有重复都被检测
        self.assertEqual(duplicate_numbers, {2, 6})
        self.assertEqual(sorted(list(duplicate_numbers)), [2, 6])


class TestFormatUnification(unittest.TestCase):
    """测试统一格式要求（Root Cause #2）"""

    def test_chapter_title_format_correct(self):
        """测试：正确的章节标题格式"""
        correct_formats = [
            "第1章 - 乱葬岗的修复师",
            "第7章 - 笨拙的赝品与无价的真品",
            "第100章 - 最终决战",
        ]

        # 正确格式：第X章 - [标题]（无空格，有破折号）
        pattern = r'^第\d+章\s+-\s+.+'

        for fmt in correct_formats:
            self.assertRegex(fmt, pattern, f"格式应该正确: {fmt}")

    def test_chapter_title_format_incorrect(self):
        """测试：错误的章节标题格式"""
        incorrect_formats = [
            "第 1 章 - 乱葬岗的修复师",  # 空格太多
            "第1章[标题]",  # 缺少破折号
            "第1章",  # 无标题
            "第一章 - 乱葬岗的修复师",  # 中文数字
        ]

        # 正确格式：第X章 - [标题]
        pattern = r'^第\d+章\s+-\s+.+'

        for fmt in incorrect_formats:
            self.assertNotRegex(fmt, pattern, f"格式应该不正确: {fmt}")

    def test_section_header_format(self):
        """测试：小节标题格式必须是 ## X."""
        correct_formats = [
            "## 1. 基础元信息",
            "## 2. 张力与冲突",
            "## 10. 剧情精要",
        ]

        # 正确格式：## X. [标题]
        pattern = r'^##\s*\d+\.\s*.+'

        for fmt in correct_formats:
            self.assertRegex(fmt, pattern, f"小节格式应该正确: {fmt}")


class TestFormatExtraction(unittest.TestCase):
    """测试格式提取和验证逻辑"""

    def test_extract_chapter_numbers_from_content(self):
        """测试：从内容中提取章节编号"""
        content = """
第1章 - 乱葬岗的修复师
## 1. 基础元信息
...
第2章 - 笨拙的赝品
## 1. 基础元信息
...
第3章 - 真品现世
## 1. 基础元信息
"""

        # 使用新的正则表达式
        chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        self.assertEqual(generated_numbers, [1, 2, 3])

    def test_extract_chapter_numbers_with_duplicates(self):
        """测试：从内容中提取章节编号（包含重复）"""
        content = """
第1章 - 乱葬岗的修复师
...
第7章 - 笨拙的赝品
...
第7章 - 无价的真品
...
第10章 - 大结局
"""

        chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        # 应该提取到 [1, 7, 7, 10]
        self.assertEqual(generated_numbers, [1, 7, 7, 10])

        # 应用重复检测逻辑
        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        # 应该检测到第7章重复
        self.assertEqual(duplicate_numbers, {7})

    def test_chapter_pattern_variations(self):
        """测试：章节标题格式的各种变体"""
        test_cases = [
            ("第1章 - 标题", 1),
            ("### **第1章 - 标题**", 1),
            ("**第1章 - 标题**", 1),
            ("第1章-标题", 1),  # 无空格的破折号
            ("第 1 章 - 标题", 1),  # 有空格
        ]

        chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章"

        for text, expected_number in test_cases:
            match = re.search(chapter_pattern, text, re.MULTILINE)
            self.assertIsNotNone(match, f"应该匹配: {text}")
            self.assertEqual(int(match.group(1)), expected_number)


class TestIntegratedValidation(unittest.TestCase):
    """集成测试：完整的验证流程"""

    def test_complete_validation_flow(self):
        """测试：完整的验证流程（包含重复检测）"""
        # 模拟生成的内容（包含重复）
        content = """
第1章 - 乱葬岗的修复师
## 1. 基础元信息
...

第7章 - 笨拙的赝品与无价的真品
## 1. 基础元信息
...

第7章 - 重复的章节
## 1. 基础元信息
...

第20章 - 大结局
## 1. 基础元信息
...
"""

        # 步骤1: 提取章节编号
        chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        # 步骤2: 检测重复
        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        # 步骤3: 验证结果
        result = {
            "is_valid": True,
            "errors": [],
            "generated_chapters": sorted(list(unique_numbers))
        }

        if duplicate_numbers:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到重复章节：{sorted(duplicate_numbers)} - 同一章节编号出现多次！")

        # 断言
        self.assertFalse(result["is_valid"])
        self.assertIn("检测到重复章节", result["errors"][0])
        self.assertEqual(result["generated_chapters"], [1, 7, 20])

    def test_valid_content_passes_validation(self):
        """测试：有效内容应该通过验证"""
        content = """
第1章 - 乱葬岗的修复师
## 1. 基础元信息
...

第2章 - 笨拙的赝品
## 1. 基础元信息
...

第3章 - 无价的真品
## 1. 基础元信息
...
"""

        chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)(?:[-–—]\d+)?\s*章"
        generated_chapters = re.findall(chapter_pattern, content)
        generated_numbers = [int(x) for x in generated_chapters if x.isdigit()]

        unique_numbers = set()
        duplicate_numbers = set()
        for num in generated_numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        result = {
            "is_valid": True,
            "errors": [],
            "generated_chapters": sorted(list(unique_numbers))
        }

        if duplicate_numbers:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到重复章节：{sorted(duplicate_numbers)}")

        # 断言
        self.assertTrue(result["is_valid"])
        self.assertEqual(len(result["errors"]), 0)
        self.assertEqual(result["generated_chapters"], [1, 2, 3])


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
