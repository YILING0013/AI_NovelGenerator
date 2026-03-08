# -*- coding: utf-8 -*-
"""
蓝图索引器的单元测试

测试目的：确保正则表达式能正确匹配所有已知的章节标题格式。
这些测试用例来自真实的 Novel_directory.txt 文件，
防止以后改正则时漏掉某种格式。
"""

import unittest
import re
import tempfile
import os
import sys

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 被测试的正则（复制自 blueprint.py）
HEADER_PATTERN = re.compile(r'^[\s#*]*第(\d+)章(.*)', re.MULTILINE)


class TestChapterHeaderRegex(unittest.TestCase):
    """测试章节标题正则表达式"""
    
    def test_markdown_format(self):
        """格式：### **第1章 - 标题**"""
        line = "### **第1章 - 废柴之死，系统新生**"
        match = HEADER_PATTERN.search(line)
        self.assertIsNotNone(match, f"未能匹配: {line}")
        self.assertEqual(match.group(1), "1")
    
    def test_plain_format(self):
        """格式：第25章 - 标题（无Markdown标记）"""
        line = "第25章 - 暴力模式，碾压全场"
        match = HEADER_PATTERN.search(line)
        self.assertIsNotNone(match, f"未能匹配: {line}")
        self.assertEqual(match.group(1), "25")
    
    def test_indented_format(self):
        """格式：  第30章 - 标题（有缩进）"""
        line = "  第30章 - 某个标题"
        match = HEADER_PATTERN.search(line)
        self.assertIsNotNone(match, f"未能匹配: {line}")
        self.assertEqual(match.group(1), "30")
    
    def test_three_digit_chapter(self):
        """格式：第260章（三位数章节号）"""
        line = "### **第260章 - 最终章节**"
        match = HEADER_PATTERN.search(line)
        self.assertIsNotNone(match, f"未能匹配: {line}")
        self.assertEqual(match.group(1), "260")
    
    def test_no_title_separator(self):
        """格式：第50章标题（无分隔符）"""
        line = "第50章标题内容"
        match = HEADER_PATTERN.search(line)
        self.assertIsNotNone(match, f"未能匹配: {line}")
        self.assertEqual(match.group(1), "50")
    
    def test_should_not_match_inline_reference(self):
        """不应匹配：正文中引用的章节号"""
        line = "在本章第27章提到的内容"
        # 这个会匹配，但因为不在行首，实际使用中会被 ^ 过滤
        # 我们的模式用了 ^ 锚定，所以这种情况不会误匹配
        # 这里测试的是带有前缀的情况
        line_with_prefix = "伏笔管理：植入伏笔 - 第25章植入"
        match = HEADER_PATTERN.match(line_with_prefix)
        # match() 从头匹配，"伏" 不是空格/# /*，所以应该不匹配
        self.assertIsNone(match, f"不应匹配: {line_with_prefix}")


class TestBlueprintIndexer(unittest.TestCase):
    """测试蓝图索引器的核心功能"""
    
    def setUp(self):
        """创建临时测试文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.temp_dir, "wxhyj")
        os.makedirs(self.project_dir, exist_ok=True)
        
    def tearDown(self):
        """清理临时文件"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_blueprint(self, content):
        """创建测试用蓝图文件"""
        filepath = os.path.join(self.project_dir, "Novel_directory.txt")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return self.temp_dir
    
    def test_mixed_format_chapters(self):
        """测试混合格式的章节能否被正确索引"""
        content = """序言部分

### **第1章 - Markdown格式**
这是第1章的内容。

第2章 - 纯文本格式
这是第2章的内容。

  第3章 - 带缩进格式
这是第3章的内容。
"""
        project_path = self._create_test_blueprint(content)
        
        # 导入并测试
        from novel_generator.core.blueprint import IndexedBlueprint
        bp = IndexedBlueprint(project_path)
        
        self.assertTrue(bp.chapter_exists(1), "应该存在第1章")
        self.assertTrue(bp.chapter_exists(2), "应该存在第2章")
        self.assertTrue(bp.chapter_exists(3), "应该存在第3章")
        self.assertFalse(bp.chapter_exists(4), "不应存在第4章")
        
        # 检查内容是否正确
        ch1 = bp.get_chapter_content(1)
        self.assertIn("Markdown格式", ch1)
        self.assertIn("第1章的内容", ch1)
        
        ch2 = bp.get_chapter_content(2)
        self.assertIn("纯文本格式", ch2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
