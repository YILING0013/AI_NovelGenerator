# scripts/finalize_directory_format.py
# -*- coding: utf-8 -*-
"""
Novel_directory.txt 最终格式修复

功能：
1. 统一章节编号格式为 "第X章"（无空格）
2. 统一所有小节格式为 "## X. 标题"
3. 清理多余空行
4. 确保格式一致性

使用方法：
    python scripts/finalize_directory_format.py
"""

import re


def finalize_format(file_path: str = "wxhyj/Novel_directory.txt"):
    """最终格式修复"""
    print(f"📖 正在修复: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 统一章节编号格式：第X章（无空格）
    content = re.sub(r'第\s*(\d+)\s*章\s*', rf'第\1章', content)

    # 2. 统一所有小节格式为 ## X. 标题
    lines = content.splitlines()
    fixed_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            fixed_lines.append("")
            continue

        # 匹配小节标题（可能是 "1."、"## 1."、"### 1." 等）
        match = re.match(r'^#*\s*(\d+)\.\s+(.+)', stripped)
        if match:
            num = match.group(1)
            title = match.group(2).strip()
            fixed_lines.append(f"## {num}. {title}")
        else:
            # 纯数字开头但没有 # 的（如 "1. 标题"）
            match = re.match(r'^(\d+)\.\s+(.+)', stripped)
            if match:
                num = match.group(1)
                title = match.group(2).strip()
                # 只处理1-10的小节编号（避免误匹配其他数字）
                if int(num) <= 10:
                    fixed_lines.append(f"## {num}. {title}")
                else:
                    fixed_lines.append(stripped)
            else:
                fixed_lines.append(stripped)

    # 3. 清理多余空行（连续空行不超过2个）
    cleaned_lines = []
    empty_count = 0

    for line in fixed_lines:
        if line == "":
            empty_count += 1
            if empty_count <= 2:
                cleaned_lines.append(line)
        else:
            empty_count = 0
            cleaned_lines.append(line)

    final_content = '\n'.join(cleaned_lines)

    # 4. 备份并保存
    backup_path = file_path + '.backup2'
    with open(backup_path, 'w', encoding='utf-8') as f:
        with open(file_path, 'r', encoding='utf-8') as original:
            f.write(original.read())
    print(f"💾 原文件已备份到: {backup_path}")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print(f"✅ 格式修复完成！")

    # 验证结果
    print(f"\n📊 格式验证:")
    chapter_headers = re.findall(r'^第(\d+)章', final_content, re.MULTILINE)
    print(f"  - 章节总数: {len(chapter_headers)}")
    print(f"  - 章节编号: {list(map(int, chapter_headers[:5]))}... (前5章)")

    section_headers = re.findall(r'^##\s*(\d+)\.', final_content, re.MULTILINE)
    print(f"  - ## 格式小节: {len(section_headers)} 个")


if __name__ == "__main__":
    finalize_format()
