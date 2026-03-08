#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节目录自动修复脚本

功能：
自动删除错误的单独章节标记行，修复章节错位问题。

检测的问题行：
- 第116行：单独的"第2章"标记
- 第266行：单独的"第3章"标记
- 第720行：单独的"第7章"标记

修复策略：
1. 删除这些错误的单独章节标记行
2. 保留正确的章节序号标记（如"章节序号：第2章"）
3. 生成修复后的文件
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterDirectoryAutoFixer:
    """章节目录自动修复器"""

    # 单独的章节标记模式（需要删除的）
    STANDALONE_CHAPTER_PATTERN = re.compile(r'^第(\d+)章$')

    # 正式的章节序号模式（需要保留的）
    FORMAL_CHAPTER_PATTERN = re.compile(r'章节序号[：:]\s*第(\d+)章')

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.lines: List[str] = []
        self.removed_lines: List[Tuple[int, str]] = []
        self.backup_path: Path = None

    def load_file(self):
        """加载文件"""
        logger.info(f"正在加载文件: {self.filepath}")
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        logger.info(f"加载完成，共 {len(self.lines)} 行")

    def create_backup(self):
        """创建备份文件"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{self.filepath.stem}_backup_{timestamp}{self.filepath.suffix}"
        self.backup_path = self.filepath.parent / backup_name

        logger.info(f"正在创建备份: {self.backup_path}")
        with open(self.backup_path, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)
        logger.info("备份创建完成")

    def analyze_and_fix(self):
        """分析并修复问题"""
        logger.info("\\n正在分析并修复问题...")

        # 首先扫描所有正式的章节序号位置
        formal_chapters = {}
        for i, line in enumerate(self.lines, 1):
            match = self.FORMAL_CHAPTER_PATTERN.search(line)
            if match:
                chapter_num = int(match.group(1))
                formal_chapters[chapter_num] = i

        fixed_lines = []
        removed_count = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # 检查是否是单独的章节标记
            if self.STANDALONE_CHAPTER_PATTERN.match(stripped):
                # 检查下一行是否是章节标题
                next_line = self.lines[i] if i < len(self.lines) else ""

                # 如果下一行以"章节标题："开头
                if next_line.strip().startswith("章节标题："):
                    chapter_num = int(self.STANDALONE_CHAPTER_PATTERN.match(stripped).group(1))

                    # 检查是否已经存在正式的章节序号标记
                    if chapter_num in formal_chapters:
                        # 如果正式标记在这之前，说明这个单独标记是重复的，应该删除
                        if formal_chapters[chapter_num] < i:
                            logger.warning(f"  删除第 {i} 行: 重复的章节标记 '第{chapter_num}章' (正式标记在第 {formal_chapters[chapter_num]} 行)")
                            self.removed_lines.append((i, line))
                            removed_count += 1
                            continue  # 跳过这一行
                        else:
                            # 正式标记在后面，说明这个单独标记是正确的（如第1章）
                            logger.info(f"  保留第 {i} 行: 正确的章节标记 '第{chapter_num}章' (正式标记在第 {formal_chapters[chapter_num]} 行)")

            # 保留其他所有行
            fixed_lines.append(line)

        self.lines = fixed_lines
        logger.info(f"\\n修复完成，共删除 {removed_count} 行")

    def validate_fix(self):
        """验证修复结果"""
        logger.info("\\n正在验证修复结果...")

        issues = []
        warning = []

        # 1. 检查是否还有错误的单独章节标记（排除第1章）
        for i, line in enumerate(self.lines, 1):
            if self.STANDALONE_CHAPTER_PATTERN.match(line.strip()):
                # 检查下一行是否是章节标题
                next_line = self.lines[i] if i < len(self.lines) else ""
                if next_line.strip().startswith("章节标题："):
                    # 第1章的单独标记是正确的，跳过
                    if i == 1:
                        continue
                    issues.append(f"第 {i} 行: 仍有错误的单独章节标记")

        # 2. 检查章节编号连续性
        chapter_numbers = []

        # 首先查找第1章（可能是单独的标记）
        if self.lines[0].strip() == "第1章":
            chapter_numbers.append((1, 1))

        # 然后查找所有正式的章节序号
        for i, line in enumerate(self.lines, 1):
            match = self.FORMAL_CHAPTER_PATTERN.search(line)
            if match:
                chapter_numbers.append((i, int(match.group(1))))

        if chapter_numbers:
            expected = list(range(1, len(chapter_numbers) + 1))
            actual = [num for _, num in chapter_numbers]

            if expected != actual:
                issues.append(
                    f"章节编号不连续: 期望 {expected}, 实际 {actual}"
                )

        if issues:
            logger.error("❌ 验证失败！发现以下问题:")
            for issue in issues:
                logger.error(f"  - {issue}")
            return False
        elif warning:
            logger.warning("⚠️ 验证通过，但发现以下警告:")
            for warn in warning:
                logger.warning(f"  - {warn}")
            return True
        else:
            logger.info("✓ 验证通过！未发现问题")
            return True

    def save_fixed_file(self):
        """保存修复后的文件"""
        output_path = self.filepath.parent / f"{self.filepath.stem}_fixed{self.filepath.suffix}"

        logger.info(f"\\n正在保存修复后的文件: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(self.lines)
        logger.info("保存完成")

        return output_path

    def generate_summary(self):
        """生成修复摘要"""
        summary = []
        summary.append("=" * 80)
        summary.append("章节目录修复摘要")
        summary.append("=" * 80)
        summary.append(f"\\n原始文件: {self.filepath}")
        summary.append(f"备份文件: {self.backup_path}")
        summary.append(f"原始行数: {len(self.lines) + len(self.removed_lines)}")
        summary.append(f"修复后行数: {len(self.lines)}")
        summary.append(f"删除行数: {len(self.removed_lines)}")
        summary.append("")

        if self.removed_lines:
            summary.append("删除的行:")
            summary.append("-" * 80)
            for line_num, line_content in self.removed_lines:
                summary.append(f"  第 {line_num:4d} 行: {line_content.rstrip()}")
            summary.append("")

        summary.append("=" * 80)

        return "\\n".join(summary)

    def fix(self):
        """执行完整的修复流程"""
        try:
            # 1. 加载文件
            self.load_file()

            # 2. 创建备份
            self.create_backup()

            # 3. 分析并修复
            self.analyze_and_fix()

            # 4. 验证修复结果
            if not self.validate_fix():
                logger.error("\\n❌ 验证失败，修复中止")
                return False

            # 5. 保存修复后的文件
            output_path = self.save_fixed_file()

            # 6. 生成摘要
            summary = self.generate_summary()
            print("\\n" + summary)

            # 保存摘要
            summary_path = self.filepath.parent / "fix_summary.txt"
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            logger.info(f"\\n摘要已保存到: {summary_path}")

            logger.info(f"\\n✓ 修复完成！修复后的文件: {output_path}")
            logger.info(f"请检查修复后的文件，确认无误后可替换原始文件")
            logger.info(f"替换命令: mv '{output_path}' '{self.filepath}'")

            return True

        except Exception as e:
            logger.error(f"\\n❌ 修复过程中出错: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python auto_fix_chapter_directory.py <文件路径>")
        print("示例: python auto_fix_chapter_directory.py wxhyj/Novel_directory.txt")
        sys.exit(1)

    filepath = sys.argv[1]

    fixer = ChapterDirectoryAutoFixer(filepath)
    success = fixer.fix()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
