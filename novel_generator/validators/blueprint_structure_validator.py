#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蓝图结构验证器

功能：
1. 检测蓝图生成后的格式问题
2. 发现重复的章节标记
3. 验证章节标题格式是否符合标准
4. 提供自动修复建议

使用示例：
    from novel_generator.validators.blueprint_structure_validator import BlueprintValidator

    validator = BlueprintValidator()
    result = validator.validate_file("your_novel_dir/Novel_directory.txt")

    if not result['is_valid']:
        print(result['errors'])
        # 可选择自动修复
        fixed_content = validator.fix_blueprint_structure(content)
"""

import re
import logging
from typing import Dict, List, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class BlueprintValidator:
    """蓝图结构验证器"""

    # 标准的章节标题格式
    STANDARD_CHAPTER_HEADER = r'^###\s*\*\*第\s*(\d+)\s*章\s*[-–—]\s*([^*]+)\*\*'
    # 兼容的纯文本章节标题格式：第1章 - 标题
    PLAIN_CHAPTER_HEADER = r'^第\s*(\d+)\s*章\s*[-–—]\s*(.+)$'

    # 章节序号格式
    CHAPTER_NUMBER_FORMAT = r'章节[序号标题]*[:：]\s*第\s*(\d+)\s*章'

    # 错误的单独章节标记（需要警告）
    STANDALONE_CHAPTER_MARKER = r'^第\s*(\d+)\s*章$'

    # 章节内容中的节标题
    SECTION_HEADER_PATTERN = r'^##\s+\d+\.\s+[\u4e00-\u9fa5]+'

    def __init__(self):
        self.issues = []
        self.warnings = []
        self.suggestions = []

    def _parse_chapter_header(self, line: str) -> Optional[Dict]:
        """解析章节标题，兼容Markdown与纯文本格式。"""
        stripped = line.strip()
        match = re.match(self.STANDARD_CHAPTER_HEADER, stripped)
        if match:
            return {
                'chapter_num': int(match.group(1)),
                'title': match.group(2).strip(),
                'format': 'markdown'
            }

        match = re.match(self.PLAIN_CHAPTER_HEADER, stripped)
        if match:
            return {
                'chapter_num': int(match.group(1)),
                'title': match.group(2).strip(),
                'format': 'plain'
            }

        return None

    def validate_file(self, filepath: str) -> Dict:
        """验证蓝图文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.validate_content(content, filepath)
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return {
                'is_valid': False,
                'errors': [f"无法读取文件: {e}"],
                'warnings': [],
                'suggestions': []
            }

    def validate_content(self, content: str, source: str = "<content>") -> Dict:
        """
        验证蓝图内容

        Args:
            content: 蓝图文本内容
            source: 内容来源标识（文件路径或其他标识符）

        Returns:
            包含验证结果的字典
        """
        self.issues = []
        self.warnings = []
        self.suggestions = []

        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'suggestions': [],
            'source': source
        }

        # 1. 检查内容是否为空
        if not content or not content.strip():
            result['is_valid'] = False
            result['errors'].append("🚨 内容为空")
            return result

        lines = content.split('\n')

        # 2. 检测章节结构
        chapters = self._detect_chapters(lines)

        # 3. 验证章节编号连续性
        self._validate_chapter_continuity(chapters)

        # 4. 检测重复的章节标记
        self._detect_duplicate_chapter_markers(lines, chapters)

        # 5. 验证每个章节的格式
        self._validate_chapter_formats(lines, chapters)

        # 6. 检测内容混叠
        self._detect_content_mixing(lines, chapters)

        # 汇总结果
        result['errors'] = self.issues
        result['warnings'] = self.warnings
        result['suggestions'] = self.suggestions

        if self.issues:
            result['is_valid'] = False

        result['chapters'] = chapters

        return result

    def _detect_chapters(self, lines: List[str]) -> List[Dict]:
        """检测所有章节"""
        chapters = []
        current_chapter = None

        for i, line in enumerate(lines, 1):
            chapter_header = self._parse_chapter_header(line)
            if chapter_header:
                if current_chapter:
                    chapters.append(current_chapter)

                current_chapter = {
                    'line_num': i,
                    'chapter_num': chapter_header['chapter_num'],
                    'title': chapter_header['title'],
                    'header_line': line.strip(),
                    'format': chapter_header['format']
                }

            # 检测章节序号标记
            elif re.search(self.CHAPTER_NUMBER_FORMAT, line.strip()):
                if current_chapter and 'number_line' not in current_chapter:
                    current_chapter['number_line'] = i
                    current_chapter['number_format'] = 'formal'

        # 添加最后一个章节
        if current_chapter:
            chapters.append(current_chapter)

        return chapters

    def _validate_chapter_continuity(self, chapters: List[Dict]):
        """验证章节编号连续性"""
        if not chapters:
            self.issues.append("🚨 未检测到任何章节")
            return

        chapter_numbers = [ch['chapter_num'] for ch in chapters]

        # 检查是否连续
        expected = list(range(1, len(chapters) + 1))
        if chapter_numbers != expected:
            # 找出缺失和多余的章节
            missing = set(expected) - set(chapter_numbers)
            extra = set(chapter_numbers) - set(expected)

            if missing:
                self.issues.append(f"🚨 章节编号不连续，缺失: {sorted(missing)}")

            if extra:
                self.warnings.append(f"⚠️ 发现多余的章节编号: {sorted(extra)}")

    def _detect_duplicate_chapter_markers(self, lines: List[str], chapters: List[Dict]):
        """检测重复的章节标记"""
        # 收集所有章节标记的位置
        all_markers = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            chapter_header = self._parse_chapter_header(stripped)
            if chapter_header:
                all_markers.append({
                    'line': i,
                    'num': chapter_header['chapter_num'],
                    'type': 'standard_header',
                    'content': stripped
                })
                continue

            # 检测章节序号标记
            match_num = re.search(self.CHAPTER_NUMBER_FORMAT, stripped)
            if match_num:
                all_markers.append({
                    'line': i,
                    'num': int(match_num.group(1)),
                    'type': 'formal_number',
                    'content': stripped
                })
                continue

            # 检测单独的章节标记（可能是错误的）
            match_standalone = re.match(self.STANDALONE_CHAPTER_MARKER, stripped)
            if match_standalone:
                all_markers.append({
                    'line': i,
                    'num': int(match_standalone.group(1)),
                    'type': 'standalone',
                    'content': stripped
                })

        # 检查每个章节号是否有多个标记
        chapter_marker_map = {}
        for marker in all_markers:
            num = marker['num']
            if num not in chapter_marker_map:
                chapter_marker_map[num] = []
            chapter_marker_map[num].append(marker)

        for num, markers in sorted(chapter_marker_map.items()):
            if len(markers) > 1:
                # 检查是否有重复的standalone标记
                standalones = [m for m in markers if m['type'] == 'standalone']
                if standalones:
                    for standalone in standalones:
                        self.issues.append(
                            f"🚨 第{standalone['line']}行: 发现重复的章节标记 "
                            f"'{standalone['content']}'，章节{num}已有正式标记"
                        )

                    self.suggestions.append(
                        f"💡 建议: 删除第{num}章的单独章节标记行（"
                        f"第{', '.join(str(s['line']) for s in standalones)}行）"
                    )

    def _validate_chapter_formats(self, lines: List[str], chapters: List[Dict]):
        """验证每个章节的格式"""
        required_sections = [
            "1. 基础元信息",
            "2. 张力与冲突",
            "6. 剧情精要",
            "7. 衔接设计"
        ]

        for ch in chapters:
            # 获取章节内容范围
            start_idx = ch['line_num'] - 1
            end_idx = (chapters.index(ch) + 1 < len(chapters)
                      and chapters[chapters.index(ch) + 1]['line_num'] - 1
                      or len(lines))

            chapter_lines = lines[start_idx:end_idx]
            chapter_text = '\n'.join(chapter_lines)

            # 检查必需的节
            missing_sections = []
            for section in required_sections:
                if section not in chapter_text:
                    missing_sections.append(section)

            if missing_sections:
                self.warnings.append(
                    f"⚠️ 第{ch['chapter_num']}章缺少必需的节: {', '.join(missing_sections)}"
                )

    def _detect_content_mixing(self, lines: List[str], chapters: List[Dict]):
        """检测内容混叠（一个章节包含另一个章节的内容）"""
        if len(chapters) < 2:
            return

        for i, ch in enumerate(chapters[:-1]):
            next_ch = chapters[i + 1]

            # 获取当前章节的内容
            start_idx = ch['line_num'] - 1
            end_idx = next_ch['line_num'] - 1
            chapter_lines = lines[start_idx:end_idx]
            chapter_text = '\n'.join(chapter_lines)

            # 检查是否包含下一章节的标题
            next_title_pattern = rf"第\s*{next_ch['chapter_num']}\s*章"

            # 只在非"承上/启下"的上下文中检查
            for line_idx, line in enumerate(chapter_lines):
                if '启下' not in line and re.search(next_title_pattern, line):
                    self.warnings.append(
                        f"⚠️ 第{ch['chapter_num']}章的内容中可能包含第{next_ch['chapter_num']}章的引用 "
                        f"(第{start_idx + line_idx + 1}行)"
                    )

    def fix_blueprint_structure(self, content: str) -> Tuple[str, List[str]]:
        """
        尝试自动修复蓝图结构

        Returns:
            (修复后的内容, 修复操作列表)
        """
        lines = content.split('\n')
        fixes = []
        fixed_lines = []

        # 跟踪已处理的章节号
        processed_chapters = set()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            should_remove = False

            # 检查是否是单独的章节标记
            match = re.match(self.STANDALONE_CHAPTER_MARKER, stripped)
            if match:
                chapter_num = int(match.group(1))

                # 检查是否已经有正式标记
                if chapter_num in processed_chapters:
                    should_remove = True
                    fixes.append(f"删除第{i}行的重复章节标记: '{stripped}'")
                else:
                    # 这是第一次见到这个章节号，保留它
                    processed_chapters.add(chapter_num)

            # 检查是否有章节序号标记
            match = re.search(self.CHAPTER_NUMBER_FORMAT, stripped)
            if match:
                chapter_num = int(match.group(1))
                processed_chapters.add(chapter_num)

            if not should_remove:
                fixed_lines.append(line)

        return '\n'.join(fixed_lines), fixes

    def generate_report(self, validation_result: Dict) -> str:
        """生成可读的验证报告"""
        report = []
        report.append("=" * 80)
        report.append("蓝图结构验证报告")
        report.append("=" * 80)
        report.append(f"来源: {validation_result['source']}")
        report.append(f"状态: {'✅ 通过' if validation_result['is_valid'] else '❌ 失败'}")
        report.append("")

        if validation_result.get('chapters'):
            report.append(f"检测到 {len(validation_result['chapters'])} 个章节:")
            for ch in validation_result['chapters']:
                report.append(f"  - 第{ch['chapter_num']}章: {ch.get('title', '无标题')}")
            report.append("")

        if validation_result['errors']:
            report.append("错误:")
            report.append("-" * 80)
            for error in validation_result['errors']:
                report.append(f"  {error}")
            report.append("")

        if validation_result['warnings']:
            report.append("警告:")
            report.append("-" * 80)
            for warning in validation_result['warnings']:
                report.append(f"  {warning}")
            report.append("")

        if validation_result['suggestions']:
            report.append("建议:")
            report.append("-" * 80)
            for suggestion in validation_result['suggestions']:
                report.append(f"  {suggestion}")
            report.append("")

        report.append("=" * 80)

        return '\n'.join(report)


# 便捷函数
def validate_blueprint_file(filepath: str) -> Dict:
    """验证蓝图文件的便捷函数"""
    validator = BlueprintValidator()
    return validator.validate_file(filepath)


def validate_blueprint_content(content: str, source: str = "<content>") -> Dict:
    """验证蓝图内容的便捷函数"""
    validator = BlueprintValidator()
    return validator.validate_content(content, source)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("用法: python blueprint_structure_validator.py <文件路径>")
        sys.exit(1)

    filepath = sys.argv[1]

    validator = BlueprintValidator()
    result = validator.validate_file(filepath)

    print(validator.generate_report(result))

    # 如果有错误，尝试自动修复
    if not result['is_valid'] and result.get('errors'):
        print("\n正在尝试自动修复...")

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        fixed_content, fixes = validator.fix_blueprint_structure(content)

        if fixes:
            print("\n执行的修复操作:")
            for fix in fixes:
                print(f"  - {fix}")

            # 保存修复后的文件
            output_path = str(filepath).replace('.txt', '_fixed.txt')
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)

            print(f"\n修复后的文件已保存到: {output_path}")
        else:
            print("无法自动修复，请手动检查")
