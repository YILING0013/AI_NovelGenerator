# scripts/analyze_and_fix_directory.py
# -*- coding: utf-8 -*-
"""
Novel_directory.txt 深度分析和修复工具

功能：
1. 检测所有重复章节
2. 统一格式为 "第X章"（无空格）
3. 清理多余内容
4. 生成详细报告

使用方法：
    python scripts/analyze_and_fix_directory.py
"""

import re
import os
from collections import Counter
from datetime import datetime


def analyze_novel_directory(file_path: str = "wxhyj/Novel_directory.txt"):
    """深度分析目录文件"""
    print(f"📖 正在分析: {file_path}")

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 提取所有章节标题行
    chapter_pattern = r'^(第\s*\d+\s*章\s*-.+)$'
    lines = content.splitlines()
    chapter_lines = []

    for i, line in enumerate(lines, 1):
        if re.match(chapter_pattern, line):
            chapter_lines.append({
                'line_num': i,
                'content': line.strip()
            })

    print(f"\n📊 分析结果:")
    print(f"  - 总行数: {len(lines)}")
    print(f"  - 章节标题行数: {len(chapter_lines)}")

    # 2. 提取章节编号
    chapter_numbers = []
    for ch in chapter_lines:
        # 提取编号（兼容有空格和无空格的格式）
        match = re.search(r'第\s*(\d+)\s*章', ch['content'])
        if match:
            num = int(match.group(1))
            chapter_numbers.append(num)
            ch['number'] = num

    # 3. 统计重复
    counter = Counter(chapter_numbers)
    duplicates = {num: count for num, count in counter.items() if count > 1}

    if duplicates:
        print(f"\n⚠️ 发现 {len(duplicates)} 个重复章节:")
        for num, count in sorted(duplicates.items()):
            print(f"  - 第{num}章: 出现{count}次")
    else:
        print(f"\n✅ 无重复章节")

    # 4. 格式统计
    format_with_space = 0
    format_without_space = 0

    for ch in chapter_lines:
        if '第 ' in ch['content'] and ' 章' in ch['content']:
            format_with_space += 1
        elif re.match(r'^第\d+章', ch['content']):
            format_without_space += 1

    print(f"\n📝 格式分布:")
    print(f"  - 有空格 (第 X 章): {format_with_space} 个")
    print(f"  - 无空格 (第X章): {format_without_space} 个")

    # 5. 重复章节详情
    if duplicates:
        print(f"\n🔍 重复章节详情:")
        for dup_num in sorted(duplicates.keys()):
            print(f"\n  第{dup_num}章 (出现{duplicates[dup_num]}次):")
            for ch in chapter_lines:
                if ch.get('number') == dup_num:
                    print(f"    行{ch['line_num']}: {ch['content'][:60]}...")

    return {
        'total_lines': len(lines),
        'chapter_lines': chapter_lines,
        'chapter_numbers': chapter_numbers,
        'duplicates': duplicates,
        'format_with_space': format_with_space,
        'format_without_space': format_without_space,
    }


def fix_novel_directory(file_path: str = "wxhyj/Novel_directory.txt", dry_run: bool = False):
    """修复目录文件"""
    print(f"\n🔧 开始修复: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 备份原文件
    backup_path = file_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"💾 已备份到: {backup_path}")

    lines = content.splitlines()
    fixed_lines = []

    # 用于检测重复
    seen_chapters = set()
    duplicate_count = 0
    removed_count = 0

    for line in lines:
        stripped = line.strip()

        # 检测章节标题
        chapter_match = re.match(r'^(第\s*)(\d+)(\s*)(章)(\s*)(-)?\s*(.*)$', stripped)

        if chapter_match:
            # 提取章节编号
            chapter_num = int(chapter_match.group(2))

            # 检查是否重复
            if chapter_num in seen_chapters:
                print(f"  🗑️ 删除重复: 第{chapter_num}章")
                duplicate_count += 1
                removed_count += 1
                continue

            seen_chapters.add(chapter_num)

            # 统一格式：第X章 - [标题]（无空格）
            fixed_line = f"第{chapter_num}章"

            # 添加破折号和标题（如果有）
            title = chapter_match.group(7).strip()
            if title:
                fixed_line += f" - {title}"

            fixed_lines.append(fixed_line)
        else:
            # 非章节标题行，保持不变
            fixed_lines.append(stripped)

    # 清理多余空行
    cleaned_lines = []
    prev_empty = False
    for line in fixed_lines:
        if line == "":
            if not prev_empty:
                cleaned_lines.append(line)
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    final_content = '\n'.join(cleaned_lines)

    # 统计修复后的章节数
    final_chapters = re.findall(r'^第(\d+)章', final_content, re.MULTILINE)
    final_numbers = [int(x) for x in final_chapters]

    print(f"\n📊 修复统计:")
    print(f"  - 删除重复: {duplicate_count} 个")
    print(f"  - 最终章节数: {len(final_numbers)}")
    print(f"  - 章节编号: {sorted(final_numbers)[:10]}... (前10章)")

    if not dry_run:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        print(f"\n✅ 修复完成: {file_path}")
    else:
        print(f"\n🔍 Dry run 模式，未保存文件")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='分析和修复 Novel_directory.txt')
    parser.add_argument('--file', default='wxhyj/Novel_directory.txt',
                       help='文件路径')
    parser.add_argument('--dry-run', action='store_true',
                       help='只分析不修改')
    parser.add_argument('--fix', action='store_true',
                       help='执行修复')

    args = parser.parse_args()

    # 分析
    result = analyze_novel_directory(args.file)

    # 如果需要修复
    if args.fix or args.dry_run:
        fix_novel_directory(args.file, dry_run=args.dry_run)
