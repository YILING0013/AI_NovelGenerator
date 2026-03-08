# scripts/repair_novel_directory.py
# -*- coding: utf-8 -*-
"""
Novel_directory.txt 智能修复工具

功能：
1. 自动删除重复章节（保留第一个）
2. 统一所有小节格式为 "## X. 标题"
3. 清理多余的空行
4. 生成修复报告

使用方法：
    python scripts/repair_novel_directory.py
"""

import re
import os
import sys


def repair_novel_directory(file_path: str = "wxhyj/Novel_directory.txt"):
    """
    修复 Novel_directory.txt 的格式问题

    Args:
        file_path: 文件路径
    """
    print(f"📖 正在修复: {file_path}")

    # 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 分割成章节
    chapter_pattern = re.compile(r'^第\s*(\d+)\s*章\s*-', re.MULTILINE)
    chapters = []
    matches = list(chapter_pattern.finditer(content))

    for i, match in enumerate(matches):
        start = match.start()
        # 下一章的开始位置
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        chapter_title = match.group(0)
        chapter_num = int(match.group(1))

        chapters.append({
            'number': chapter_num,
            'title': chapter_title,
            'start': start,
            'end': end,
            'content': content[start:end]
        })

    # 检测重复章节
    print(f"\n🔍 检测到 {len(chapters)} 个章节")

    seen_numbers = {}
    duplicates = []
    unique_chapters = []

    for ch in chapters:
        num = ch['number']
        if num in seen_numbers:
            duplicates.append({
                'number': num,
                'first': seen_numbers[num]['title'],
                'second': ch['title']
            })
            print(f"⚠️ 发现重复：第{num}章")
            print(f"  保留: {seen_numbers[num]['title']}")
            print(f"  删除: {ch['title']}")
        else:
            seen_numbers[num] = ch
            unique_chapters.append(ch)

    # 处理每个章节的内容
    print(f"\n🔧 处理章节内容...")
    repaired_chapters = []

    for ch in unique_chapters:
        chapter_content = ch['content']

        # 统一小节格式：将 "1. 标题" 或 "### 1. 标题" 改为 "## 1. 标题"
        lines = chapter_content.splitlines()
        fixed_lines = []

        for line in lines:
            stripped = line.strip()

            # 跳过空行（但保留一个空行间隔）
            if not stripped:
                fixed_lines.append("")
                continue

            # 匹配小节标题（纯数字格式）
            match = re.match(r'^(\d+)\.\s+(.+)', stripped)
            if match and not stripped.startswith('#'):
                num = match.group(1)
                title = match.group(2).strip()
                fixed_lines.append(f"## {num}. {title}")
            # 已经是 ## 格式的，保持不变
            elif stripped.startswith('##'):
                fixed_lines.append(stripped)
            # 已经是 ### 格式的，改为 ##
            elif stripped.startswith('###'):
                match = re.match(r'^###\s*(\d+)\.\s*(.+)', stripped)
                if match:
                    num = match.group(1)
                    title = match.group(2).strip()
                    fixed_lines.append(f"## {num}. {title}")
                else:
                    fixed_lines.append(stripped)
            else:
                fixed_lines.append(stripped)

        # 清理多余的空行（连续空行不超过2个）
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

        repaired_chapters.append('\n'.join(cleaned_lines))

    # 拼接所有章节
    final_content = '\n\n'.join(repaired_chapters)

    # 备份原文件
    backup_path = file_path + '.backup'
    with open(backup_path, 'w', encoding='utf-8') as f:
        with open(file_path, 'r', encoding='utf-8') as original:
            f.write(original.read())
    print(f"\n💾 原文件已备份到: {backup_path}")

    # 保存修复后的文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print(f"✅ 修复完成！")
    print(f"📊 修复统计:")
    print(f"  - 原始章节数: {len(chapters)}")
    print(f"  - 删除重复: {len(duplicates)}")
    print(f"  - 最终章节数: {len(unique_chapters)}")


if __name__ == "__main__":
    repair_novel_directory()
