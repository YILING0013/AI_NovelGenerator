#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节目录修复脚本 v2

问题分析：
Novel_directory.txt 存在章节标记错误，导致：
1. 第116行标记为"第2章"，但实际内容应该是第3章
2. 第266行标记为"第3章"，但实际内容应该是第4章
3. 章节被错误地分割和重复标记

根本原因：
LLM生成蓝图时，将每个章节分成了两部分：
- 第一部分：正确的章节标记（如"章节序号：第2章"）
- 第二部分：错误的单独行标记（如单独一行的"第2章"）

这导致章节边界混乱，需要重新整理。
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterBoundaryDetector:
    """章节边界检测器"""

    # 章节标题模式（在"启下"或直接出现的章节预告）
    CHAPTER预告_PATTERN = r'第(\d+)章\s*-\s*([^\\n]+)'

    # 正式章节序号模式
    CHAPTER序号_PATTERN = r'章节序号：\s*第(\d+)章'

    # 单独的章节标记行（问题所在！）
    CHAPTER单独标记_PATTERN = r'^第(\d+)章$'

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.lines: List[str] = []
        self.chapter_boundaries: List[Dict] = []
        self.issues: List[str] = []

    def load_file(self):
        """加载文件"""
        logger.info(f"正在加载文件: {self.filepath}")
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        logger.info(f"加载完成，共 {len(self.lines)} 行")

    def detect_chapters(self):
        """检测所有章节边界"""
        logger.info("正在检测章节边界...")

        chapters = []
        pending预告 = None  # 待处理的章节预告

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # 1. 检测章节预告（如"第2章 - 窑变与废料"）
            preview_match = re.search(self.CHAPTER预告_PATTERN, stripped)
            if preview_match and '启下' in self.lines[max(0, i-3):i]:
                chapter_num = int(preview_match.group(1))
                chapter_title = preview_match.group(2).strip()
                pending预告 = {
                    'num': chapter_num,
                    'title': chapter_title,
                    'line': i,
                    'type': 'preview'
                }
                logger.debug(f"检测到章节预告: 第{chapter_num}章 - {chapter_title} (第{i}行)")
                continue

            # 2. 检测正式章节序号（如"章节序号：第2章"）
            formal_match = re.search(self.CHAPTER序号_PATTERN, stripped)
            if formal_match:
                chapter_num = int(formal_match.group(1))

                # 如果有待处理的预告，验证是否匹配
                if pending预告 and pending预告['num'] == chapter_num:
                    chapters.append({
                        'num': chapter_num,
                        'title': pending预告['title'],
                        'start_line': pending预告['line'],
                        'formal_line': i,
                        'type': 'formal'
                    })
                    logger.info(f"✓ 确认章节: 第{chapter_num}章 - {pending预告['title']}")
                    pending预告 = None
                else:
                    # 没有预告的章节
                    chapters.append({
                        'num': chapter_num,
                        'title': '未知',
                        'start_line': i,
                        'formal_line': i,
                        'type': 'formal_no_preview'
                    })
                    logger.warning(f"⚠ 发现无预告的章节: 第{chapter_num}章 (第{i}行)")
                continue

            # 3. 检测单独的章节标记（问题所在！）
            standalone_match = re.match(self.CHAPTER单独标记_PATTERN, stripped)
            if standalone_match:
                chapter_num = int(standalone_match.group(1))
                logger.warning(f"❌ 检测到错误的单独章节标记: 第{chapter_num}章 (第{i}行)")
                self.issues.append(
                    f"第{i}行: 发现单独的'第{chapter_num}章'标记，"
                    f"这应该是下一个章节的正式开始"
                )

        self.chapter_boundaries = chapters

        # 计算每个章节的结束行
        for i in range(len(chapters)):
            if i < len(chapters) - 1:
                chapters[i]['end_line'] = chapters[i + 1]['start_line'] - 1
            else:
                chapters[i]['end_line'] = len(self.lines)

        logger.info(f"检测完成，共发现 {len(chapters)} 个章节")

    def analyze_duplicates(self):
        """分析重复的章节内容"""
        logger.info("\\n正在分析章节重复...")

        # 检查是否有章节编号跳跃
        expected_nums = list(range(1, len(self.chapter_boundaries) + 1))
        actual_nums = [ch['num'] for ch in self.chapter_boundaries]

        if actual_nums != expected_nums:
            logger.error("❌ 章节编号不连续！")
            logger.error(f"   期望: {expected_nums}")
            logger.error(f"   实际: {actual_nums}")

            # 找出缺失的章节号
            missing = set(expected_nums) - set(actual_nums)
            if missing:
                logger.error(f"   缺失: {sorted(missing)}")

            # 找出多余的章节号
            extra = set(actual_nums) - set(expected_nums)
            if extra:
                logger.error(f"   多余: {sorted(extra)}")

    def generate_report(self):
        """生成详细报告"""
        report = []
        report.append("=" * 100)
        report.append("章节目录问题诊断报告")
        report.append("=" * 100)
        report.append(f"\\n文件: {self.filepath}")
        report.append(f"总行数: {len(self.lines)}")
        report.append(f"检测到的章节数: {len(self.chapter_boundaries)}")
        report.append("")

        # 章节详细信息
        report.append("章节详细信息:")
        report.append("-" * 100)
        for ch in self.chapter_boundaries:
            length = ch['end_line'] - ch['start_line'] + 1
            report.append(
                f"  第{ch['num']:2d}章 {ch['title']:30s} | "
                f"预告行: {ch['start_line']:4d} | 正式行: {ch.get('formal_line', 'N/A'):4d} | "
                f"结束行: {ch['end_line']:4d} | 长度: {length:4d}行"
            )
        report.append("")

        # 问题列表
        report.append("检测到的问题:")
        report.append("-" * 100)
        if self.issues:
            for issue in self.issues:
                report.append(f"  ❌ {issue}")
        else:
            report.append("  ✓ 未发现问题")
        report.append("")

        # 根本原因分析
        report.append("根本原因分析:")
        report.append("-" * 100)
        report.append("  问题模式:")
        report.append("    每个章节被错误地分成了两部分:")
        report.append("    1. 第一部分: 章节预告 + 正式章节序号 (正确)")
        report.append("    2. 第二部分: 单独的章节标记行 (错误，导致章节错位)")
        report.append("")
        report.append("  示例:")
        report.append("    第60行:  ...第2章 - 窑变与废料")
        report.append("    第63行:  章节序号：第2章  ← 正确的第2章开始")
        report.append("    ...")
        report.append("    第116行: 第2章  ← 错误！这应该是第3章的标记")
        report.append("    ...")
        report.append("    第266行: 第3章  ← 错误！这应该是第4章的标记")
        report.append("")

        # 修复建议
        report.append("修复建议:")
        report.append("-" * 100)
        report.append("  方案1: 手动删除错误的章节标记")
        report.append("    - 删除第116行的 '第2章'")
        report.append("    - 删除第266行的 '第3章'")
        report.append("    - 重新编号后续章节")
        report.append("")
        report.append("  方案2: 重新生成章节目录")
        report.append("    - 检查蓝图生成代码中的章节标记逻辑")
        report.append("    - 确保每个章节只有一个明确的开始标记")
        report.append("")

        report.append("=" * 100)

        return "\\n".join(report)

    def suggest_fix(self):
        """提出具体的修复建议"""
        logger.info("\\n具体的修复建议:")
        logger.info("=" * 80)

        # 找出所有错误的单独章节标记
        for i, line in enumerate(self.lines, 1):
            if re.match(self.CHAPTER单独标记_PATTERN, line.strip()):
                context_start = max(0, i - 3)
                context_end = min(len(self.lines), i + 3)
                logger.info(f"\\n第 {i} 行发现错误的章节标记:")
                logger.info("-" * 60)
                for j in range(context_start, context_end):
                    prefix = ">>>" if j == i - 1 else "   "
                    logger.info(f"{prefix} {j+1:4d} | {self.lines[j].rstrip()}")
                logger.info("-" * 60)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python fix_chapter_directory_v2.py <文件路径>")
        sys.exit(1)

    filepath = sys.argv[1]

    detector = ChapterBoundaryDetector(filepath)
    detector.load_file()
    detector.detect_chapters()
    detector.analyze_duplicates()

    # 生成报告
    report = detector.generate_report()
    print(report)

    # 保存报告
    report_path = Path(filepath).parent / "chapter_diagnosis_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info(f"\\n报告已保存到: {report_path}")

    # 显示修复建议
    detector.suggest_fix()


if __name__ == '__main__':
    main()
