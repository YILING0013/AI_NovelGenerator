# scripts/fix_novel_directory.py
# -*- coding: utf-8 -*-
"""
Novel_directory.txt 格式修复工具

功能：
1. 检测并删除重复章节
2. 统一章节编号格式（统一为 "第X章" 无空格）
3. 统一章节标题格式（统一为 "## X. 标题"）
4. 删除第1章开头的重复蓝图说明
5. 生成修复报告

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import re
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.chapter_utils import extract_chapter_number, split_chapters_by_header


def fix_novel_directory(input_file: str, output_file: str = None, dry_run: bool = False):
    """
    修复 Novel_directory.txt 的格式问题

    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径（None则覆盖原文件）
        dry_run: 是否只分析不修改
    """
    print(f"📖 正在分析: {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 检测章节重复
    print("\n🔍 检测章节重复...")
    chapters = split_chapters_by_header(content)
    chapter_numbers = {}

    duplicates = []
    for ch in chapters:
        num = ch['chapter_number']
        if num in chapter_numbers:
            duplicates.append({
                'number': num,
                'first_title': chapter_numbers[num]['title'],
                'second_title': ch['title'],
                'first_line': chapter_numbers[num]['header_line'],
                'second_line': ch['header_line']
            })
        else:
            chapter_numbers[num] = ch

    if duplicates:
        print(f"⚠️ 发现 {len(duplicates)} 个重复章节:")
        for dup in duplicates:
            print(f"  - 第{dup['number']}章:")
            print(f"    1. {dup['first_title']}")
            print(f"    2. {dup['second_title']}")
    else:
        print("✅ 未发现重复章节")

    # 2. 统一章节编号格式
    print("\n🔧 统一章节编号格式...")
    lines = content.splitlines()
    fixed_lines = []
    removed_first_chapter_duplicate = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 检测章节标题行
        chapter_num = extract_chapter_number(stripped)

        if chapter_num is not None:
            # 统一为 "第X章" 格式（无空格）
            # 替换各种变体
            fixed_line = re.sub(r'第\s*(\d+)\s*章\s*', rf'第\1章', stripped)

            # 保留破折号后的标题
            if ' - ' in stripped or ' -' in stripped or '- ' in stripped:
                # 提取标题
                match = re.search(r'[-–—]\s*(.+)$', stripped)
                if match:
                    title = match.group(1).strip()
                    fixed_line = f"第{chapter_num}章 - {title}"

            # 如果是第1章，检查是否是重复的蓝图说明部分
            if chapter_num == 1 and i < 100:  # 前100行内的第1章
                # 跳过第1章开头的蓝图说明（1-54行）
                if not fixed_line.startswith("第1章 - "):
                    print(f"🗑️ 跳过第1章开头的蓝图说明（第{i+1}行）")
                    removed_first_chapter_duplicate = True
                    continue

            fixed_lines.append(fixed_line)
        else:
            # 统一章节内的小节格式为 "## X. 标题"
            if stripped.startswith('#') and re.match(r'^##?\s*\d+\.', stripped):
                # 统一为 "## X. 标题" 格式
                match = re.match(r'^##?\s*(\d+)\.\s*(.+)', stripped)
                if match:
                    num = match.group(1)
                    title = match.group(2).strip()
                    fixed_lines.append(f"## {num}. {title}")
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)

    fixed_content = '\n'.join(fixed_lines)

    # 3. 统计信息
    print(f"\n📊 修复统计:")
    print(f"  - 重复章节: {len(duplicates)} 个")
    print(f"  - 删除第1章重复蓝图说明: {'是' if removed_first_chapter_duplicate else '否'}")

    # 4. 保存修复后的内容
    if not dry_run:
        output_path = output_file or input_file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print(f"\n✅ 修复后的文件已保存: {output_path}")
    else:
        print(f"\n🔍 Dry run 模式，未保存文件")

    return {
        'duplicates': duplicates,
        'fixed_content': fixed_content,
        'removed_duplicate': removed_first_chapter_duplicate
    }


def analyze_directory_format(input_file: str):
    """
    分析目录文件的格式问题

    Args:
        input_file: 输入文件路径
    """
    print(f"\n{'='*60}")
    print(f"📋 格式分析报告: {input_file}")
    print(f"{'='*60}")

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()

    # 统计章节标题格式
    chapter_formats = {}
    for line in lines:
        stripped = line.strip()
        if re.match(r'^第\s*\d+\s*章', stripped):
            # 统计格式类型
            if '第' in stripped and '章' in stripped:
                if '  ' in stripped:  # 有空格
                    format_type = "有空格 (第 X 章)"
                else:  # 无空格
                    format_type = "无空格 (第X章)"
                chapter_formats[format_type] = chapter_formats.get(format_type, 0) + 1

    # 统计小节格式
    section_formats = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('##'):
            section_formats['## X. 格式'] = section_formats.get('## X. 格式', 0) + 1
        elif stripped.startswith('###'):
            section_formats['### X. 格式'] = section_formats.get('### X. 格式', 0) + 1
        elif re.match(r'^\d+\.\s', stripped):
            section_formats['纯数字 (X.)'] = section_formats.get('纯数字 (X.)', 0) + 1

    print("\n📌 章节标题格式分布:")
    for fmt, count in chapter_formats.items():
        print(f"  - {fmt}: {count} 个")

    print("\n📌 小节标题格式分布:")
    for fmt, count in section_formats.items():
        print(f"  - {fmt}: {count} 个")

    # 检测重复章节
    print("\n🔍 重复章节检测:")
    chapters = split_chapters_by_header(content)
    chapter_numbers = {}
    has_duplicates = False

    for ch in chapters:
        num = ch['chapter_number']
        if num in chapter_numbers:
            has_duplicates = True
            print(f"  ⚠️ 第{num}章重复:")
            print(f"     1. {chapter_numbers[num]['title']}")
            print(f"     2. {ch['title']}")
        else:
            chapter_numbers[num] = ch

    if not has_duplicates:
        print("  ✅ 未发现重复章节")

    print(f"\n📈 总计: {len(chapters)} 个章节")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='修复 Novel_directory.txt 格式问题')
    parser.add_argument('input_file', nargs='?', default='wxhyj/Novel_directory.txt',
                       help='输入文件路径（默认: wxhyj/Novel_directory.txt）')
    parser.add_argument('-o', '--output', help='输出文件路径（默认覆盖原文件）')
    parser.add_argument('--dry-run', action='store_true', help='只分析不修改')
    parser.add_argument('--analyze-only', action='store_true', help='只分析格式问题')

    args = parser.parse_args()

    if args.analyze_only:
        analyze_directory_format(args.input_file)
    else:
        fix_novel_directory(args.input_file, args.output, args.dry_run)
        if not args.dry_run:
            print("\n" + "="*60)
            print("修复完成！请检查文件内容是否正确。")
            print("="*60)
