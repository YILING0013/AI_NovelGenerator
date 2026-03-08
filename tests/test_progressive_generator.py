# tests/test_progressive_generator.py
# -*- coding: utf-8 -*-
"""
三阶段渐进式蓝图生成器 - 单元测试

测试范围：
1. 多层验证系统
2. 标题验证逻辑
3. 章节格式验证
4. 重复检测

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

from novel_generator.progressive_blueprint_generator import (
    ProgressiveConfig,
    MultiLevelValidator
)


class TestProgressiveConfig(unittest.TestCase):
    """测试配置类"""

    def test_default_config(self):
        """测试默认配置"""
        config = ProgressiveConfig()

        self.assertEqual(config.STAGE1_MAX_RETRIES, 5)
        self.assertEqual(config.STAGE2_MAX_RETRIES, 5)
        self.assertEqual(config.ENABLE_SELF_REFLECTION, True)
        self.assertEqual(config.ENABLE_CONSISTENCY_CHECK, True)


class TestTitleValidation(unittest.TestCase):
    """测试标题验证逻辑"""

    def test_title_format_correct(self):
        """测试：正确的标题格式"""
        correct_titles = [
            "第1章 - 乱葬岗的修复师",
            "第7章 - 笨拙的赝品与无价的真品",
            "第20章 - 最终决战",
        ]

        pattern = r'^第\d+章\s+-\s+.+$'

        for title in correct_titles:
            self.assertRegex(title, pattern, f"标题格式应正确: {title}")

    def test_title_format_incorrect(self):
        """测试：错误的标题格式"""
        incorrect_titles = [
            "第 1 章 - 乱葬岗的修复师",  # 空格太多
            "第1章[标题]",  # 缺少破折号
            "第1章",  # 无标题
            "第一章 - 标题",  # 中文数字
        ]

        pattern = r'^第\d+章\s+-\s+.+$'

        for title in incorrect_titles:
            self.assertNotRegex(title, pattern, f"标题格式应不正确: {title}")

    def test_extract_chapter_numbers(self):
        """测试：提取章节编号"""
        titles = [
            "第1章 - 标题A",
            "第2章 - 标题B",
            "第7章 - 标题C",
            "第20章 - 标题D",
        ]

        numbers = []
        for title in titles:
            match = re.match(r'^第(\d+)章', title)
            if match:
                numbers.append(int(match.group(1)))

        self.assertEqual(numbers, [1, 2, 7, 20])

    def test_duplicate_detection(self):
        """测试：重复章节检测"""
        titles = [
            "第1章 - 标题A",
            "第2章 - 标题B",
            "第3章 - 标题C",
            "第2章 - 标题D",  # 重复！
            "第4章 - 标题E",
        ]

        numbers = []
        for title in titles:
            match = re.match(r'^第(\d+)章', title)
            if match:
                numbers.append(int(match.group(1)))

        # 检测重复
        unique_numbers = set()
        duplicate_numbers = set()
        for num in numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        self.assertIn(2, duplicate_numbers)
        self.assertEqual(duplicate_numbers, {2})


class TestMultiLevelValidator(unittest.TestCase):
    """测试多层验证系统"""

    def setUp(self):
        """设置测试环境"""
        self.config = ProgressiveConfig()
        self.architecture_text = """
# 小说架构

## 角色设定
- 主角：张昊
- 女主：苏清雪
- 宿敌：萧尘
"""
        self.validator = MultiLevelValidator(self.architecture_text, self.config)

    def test_level1_structure_valid(self):
        """测试：层级1 结构验证 - 有效内容"""
        valid_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
*   **章节**：第1章 - 乱葬岗的修复师
*   **定位**：第1卷 蛰伏篇 - 子幕1 初入江湖
*   **核心功能**：开篇立人设
*   **字数目标**：3000-5000字
*   **出场角色**：张昊

## 2. 张力与冲突
*   **冲突类型**：生存
*   **核心冲突点**：在乱葬岗被误认为死人
*   **紧张感曲线**：
    *   **铺垫**：主角苏醒
    *   **爬升**：遭遇官兵
    *   **爆发**：展示修复技艺
    *   **回落/悬念**：引起注意

## 3. 匠心思维应用
*   **思维模式**：断代鉴定
*   **应用场景**：鉴定古董

## 4. 伏笔与信息差
*   **本章植入伏笔**：
    *   修复技艺 -> 第5章揭示

## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动

## 6. 剧情精要
*   **开场**：主角在乱葬岗苏醒
*   **发展**：
    *   被误认为死人
    *   展示修复技艺
*   **高潮**：成功修复一件古董
*   **收尾**：引起各方注意

## 7. 衔接设计
*   **承上**：承接主角苏醒后的生存危机
*   **转场**：从乱葬岗转入城内调查
*   **启下**：为后续势力关注埋下伏笔
"""

        result = self.validator._validate_level1_structure(valid_content)

        self.assertTrue(result['valid'], f"结构验证应该通过: {result['errors']}")

    def test_level1_structure_missing_module(self):
        """测试：层级1 结构验证 - 缺少模块"""
        invalid_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
*   **定位**：第1卷
"""

        result = self.validator._validate_level1_structure(invalid_content)

        self.assertFalse(result['valid'])
        self.assertTrue(any("缺少必需模块" in e for e in result['errors']))

    def test_level2_format_valid(self):
        """测试：层级2 格式验证 - 有效格式"""
        valid_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
*   **章节**：第1章 - 乱葬岗的修复师
"""

        result = self.validator._validate_level2_format(valid_content, 1)

        self.assertTrue(result['valid'], f"格式验证应该通过: {result['errors']}")

    def test_level2_format_incorrect_title(self):
        """测试：层级2 格式验证 - 标题格式错误"""
        invalid_content = """
第 1 章 - 乱葬岗的修复师

## 1. 基础元信息
"""

        result = self.validator._validate_level2_format(invalid_content, 1)

        self.assertFalse(result['valid'])
        # "第 1 章" 不会匹配正则 r'^第\d+章'，所以会报"未找到章节标题"
        self.assertTrue(any("未找到章节标题" in e for e in result['errors']))

    def test_level2_format_wrong_chapter_number(self):
        """测试：层级2 格式验证 - 章节编号不匹配"""
        invalid_content = """
第2章 - 乱葬岗的修复师

## 1. 基础元信息
"""

        result = self.validator._validate_level2_format(invalid_content, 1)

        self.assertFalse(result['valid'])
        self.assertTrue(any("编号不匹配" in e for e in result['errors']))

    def test_level3_content_too_short(self):
        """测试：层级3 内容完整性验证 - 内容过少"""
        short_content = """
第1章 - 标题

## 1. 基础元信息
*   **定位**：第1卷
"""

        result = self.validator._validate_level3_content(short_content)

        self.assertFalse(result['valid'])
        self.assertTrue(any("内容过少" in e for e in result['errors']))

    def test_level4_consistency_architecture_driven(self):
        """测试：层级4 一致性验证 - 由架构驱动（不做固定禁名拦截）"""
        content = """
第1章 - 标题

## 6. 剧情精要
*   **开场**：张浩遇到苏清寒
"""

        result = self.validator._validate_level4_consistency(content)

        self.assertTrue(result['valid'])
        self.assertEqual(result['errors'], [])

    def test_multi_level_validation_all_valid(self):
        """测试：多层验证 - 全部通过"""
        valid_content = """
第1章 - 乱葬岗的修复师

## 1. 基础元信息
*   **章节**：第1章 - 乱葬岗的修复师
*   **定位**：第1卷 蛰伏篇
*   **核心功能**：开篇立人设
*   **字数目标**：3000-5000字
*   **出场角色**：张昊

## 2. 张力与冲突
*   **冲突类型**：生存
*   **核心冲突点**：被误认为死人
*   **紧张感曲线**：
    *   **铺垫**：苏醒
    *   **爬升**：遭遇官兵
    *   **爆发**：展示技艺
    *   **回落**：引起注意

## 3. 匠心思维应用
*   **思维模式**：断代鉴定

## 4. 伏笔与信息差
*   **本章植入伏笔**：
    *   修复技艺 -> 第5章

## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动

## 6. 剧情精要
*   **开场**：主角苏醒
*   **发展**：
    *   被发现
    *   展示技艺
*   **高潮**：修复古董
*   **收尾**：引起注意

## 7. 衔接设计
*   **承上**：承接前文主角危机
*   **转场**：从乱葬岗转入城内
*   **启下**：为后续势力冲突埋伏笔
"""

        result = self.validator.validate_all_levels(valid_content, 1)

        # 由于启用了自我反思（但测试环境中没有LLM），可能会有warning
        # 但其他层级应该通过
        self.assertTrue(result['level1_structure']['valid'], f"层级1应通过: {result.get('errors', [])}")
        self.assertTrue(result['level2_format']['valid'], f"层级2应通过: {result.get('errors', [])}")
        self.assertTrue(result['level3_content']['valid'], f"层级3应通过: {result.get('errors', [])}")
        self.assertTrue(result['level4_consistency']['valid'], f"层级4应通过: {result.get('errors', [])}")


class TestTitleSequenceValidation(unittest.TestCase):
    """测试标题序列验证"""

    def test_validate_title_sequence_valid(self):
        """测试：有效的标题序列"""
        titles = [
            "第1章 - 标题A",
            "第2章 - 标题B",
            "第3章 - 标题C",
            "第4章 - 标题D",
            "第5章 - 标题E",
        ]

        # 验证
        result = {'valid': True, 'errors': []}

        # 数量
        if len(titles) != 5:
            result['valid'] = False
            result['errors'].append("数量错误")

        # 格式和编号
        numbers = []
        for title in titles:
            if not re.match(r'^第\d+章\s+-\s+.+$', title):
                result['valid'] = False
                result['errors'].append(f"格式错误: {title}")
            else:
                match = re.match(r'^第(\d+)章', title)
                if match:
                    numbers.append(int(match.group(1)))

        # 连续性
        if sorted(numbers) != list(range(1, 6)):
            result['valid'] = False
            result['errors'].append("编号不连续")

        # 重复
        if len(numbers) != len(set(numbers)):
            result['valid'] = False
            result['errors'].append("存在重复编号")

        self.assertTrue(result['valid'], f"验证应通过: {result['errors']}")

    def test_validate_title_sequence_duplicates(self):
        """测试：重复的标题序列"""
        titles = [
            "第1章 - 标题A",
            "第2章 - 标题B",
            "第2章 - 标题C",  # 重复！
            "第3章 - 标题D",
        ]

        numbers = []
        for title in titles:
            match = re.match(r'^第(\d+)章', title)
            if match:
                numbers.append(int(match.group(1)))

        # 检测重复
        unique_numbers = set()
        duplicate_numbers = set()
        for num in numbers:
            if num in unique_numbers:
                duplicate_numbers.add(num)
            else:
                unique_numbers.add(num)

        self.assertEqual(duplicate_numbers, {2})

    def test_validate_title_sequence_gaps(self):
        """测试：有缺口的标题序列"""
        titles = [
            "第1章 - 标题A",
            "第2章 - 标题B",
            "第4章 - 标题D",  # 缺少第3章！
            "第5章 - 标题E",
        ]

        numbers = []
        for title in titles:
            match = re.match(r'^第(\d+)章', title)
            if match:
                numbers.append(int(match.group(1)))

        self.assertEqual(numbers, [1, 2, 4, 5])
        self.assertNotEqual(sorted(numbers), list(range(1, 6)))


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
