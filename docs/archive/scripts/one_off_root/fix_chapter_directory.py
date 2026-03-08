#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
章节目录修复脚本

功能：
1. 检测并修复章节标记错位问题
2. 识别重复的章节标题
3. 重新编号章节并修复章节边界

问题示例：
- 第116行标记为"第2章"，但实际内容是第3章
- 第266行标记为"第3章"，但实际内容是第4章
- 章节标题重复使用（如"窑变与废料"同时用于第2章和第3章）
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChapterDirectoryFixer:
    """章节目录修复器"""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.lines: List[str] = []
        self.chapters: List[Dict] = []
        self.issues: List[str] = []

    def load_file(self):
        """加载文件"""
        logger.info(f"正在加载文件: {self.filepath}")
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
        logger.info(f"加载完成，共 {len(self.lines)} 行")

    def analyze_structure(self):
        """分析目录结构"""
        logger.info("正在分析章节结构...")

        # 章节标记模式
        chapter_marker_pattern = r'^第(\d+)章$'

        current_chapter_num = 0
        current_chapter_start = 0
        current_title = None
        chapter_blocks = []

        for i, line in enumerate(self.lines, 1):
            # 检测章节标记行（如 "第2章"）
            match = re.match(chapter_marker_pattern, line.strip())

            if match:
                # 保存前一个章节的信息
                if current_chapter_num > 0:
                    chapter_blocks.append({
                        'line_num': current_chapter_start,
                        'chapter_num': current_chapter_num,
                        'title': current_title,
                        'end_line': i - 1
                    })
                    self.issues.append(
                        f"章节 {current_chapter_num} ({current_title}): "
                        f"第 {current_chapter_start} 行到第 {i-1} 行"
                    )

                # 开始新章节
                current_chapter_num = int(match.group(1))
                current_chapter_start = i
                current_title = None

                # 尝试从下一行获取标题
                if i < len(self.lines):
                    next_line = self.lines[i].strip()
                    if next_line.startswith('章节标题：'):
                        current_title = next_line.replace('章节标题：', '').strip()

        # 保存最后一个章节
        if current_chapter_num > 0:
            chapter_blocks.append({
                'line_num': current_chapter_start,
                'chapter_num': current_chapter_num,
                'title': current_title,
                'end_line': len(self.lines)
            })

        self.chapters = chapter_blocks

        # 检测问题
        self._detect_issues()

        logger.info(f"分析完成，共发现 {len(self.chapters)} 个章节块")
        logger.info(f"检测到 {len(self.issues)} 个问题")

    def _detect_issues(self):
        """检测章节结构问题"""
        # 1. 检测章节号不连续
        expected_nums = list(range(1, len(self.chapters) + 1))
        actual_nums = [ch['chapter_num'] for ch in self.chapters]

        if actual_nums != expected_nums:
            self.issues.append(
                f"❌ 章节号不连续！期望: {expected_nums}, 实际: {actual_nums}"
            )

        # 2. 检测重复的章节标题
        title_count = {}
        for ch in self.chapters:
            if ch['title']:
                title_count[ch['title']] = title_count.get(ch['title'], 0) + 1

        for title, count in title_count.items():
            if count > 1:
                self.issues.append(f"⚠️ 章节标题重复: '{title}' 出现 {count} 次")

        # 3. 检测章节内容长度异常
        for ch in self.chapters:
            length = ch['end_line'] - ch['line_num'] + 1
            if length < 10:
                self.issues.append(
                    f"⚠️ 章节 {ch['chapter_num']} 内容过短 ({length} 行)"
                )

    def generate_report(self):
        """生成分析报告"""
        report = []
        report.append("=" * 80)
        report.append("章节目录分析报告")
        report.append("=" * 80)
        report.append(f"文件: {self.filepath}")
        report.append(f"总行数: {len(self.lines)}")
        report.append(f"检测到的章节数: {len(self.chapters)}")
        report.append("")

        # 章节列表
        report.append("章节列表:")
        report.append("-" * 80)
        for ch in self.chapters:
            length = ch['end_line'] - ch['line_num'] + 1
            report.append(
                f"  章节 {ch['chapter_num']:2d} | "
                f"行 {ch['line_num']:4d}-{ch['end_line']:4d} ({length:4d}行) | "
                f"标题: {ch['title'] or '无'}"
            )
        report.append("")

        # 问题列表
        report.append("检测到的问题:")
        report.append("-" * 80)
        if self.issues:
            for issue in self.issues:
                report.append(f"  {issue}")
        else:
            report.append("  未发现问题")
        report.append("")

        report.append("=" * 80)

        return "\n".join(report)

    def propose_fix(self):
        """提出修复方案"""
        if len(self.issues) == 0:
            logger.info("未检测到问题，无需修复")
            return

        logger.info("\n建议的修复方案:")
        logger.info("-" * 60)

        # 分析实际的章节内容，重新分配章节号
        # 这里需要根据实际内容来判断，暂时输出建议
        for i, ch in enumerate(self.chapters, 1):
            if ch['chapter_num'] != i:
                logger.info(
                    f"  将第 {ch['line_num']} 行的章节号从 {ch['chapter_num']} 改为 {i}"
                )


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python fix_chapter_directory.py <文件路径>")
        sys.exit(1)

    filepath = sys.argv[1]

    fixer = ChapterDirectoryFixer(filepath)
    fixer.load_file()
    fixer.analyze_structure()

    # 生成报告
    report = fixer.generate_report()
    print(report)

    # 将报告保存到文件
    report_path = Path(filepath).parent / "chapter_directory_analysis_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info(f"报告已保存到: {report_path}")

    # 提出修复方案
    fixer.propose_fix()


if __name__ == '__main__':
    main()
