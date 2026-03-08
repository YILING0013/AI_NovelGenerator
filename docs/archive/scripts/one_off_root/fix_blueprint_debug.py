#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 blueprint_debug.py 中的章节混叠检测逻辑
"""

import re

def fix_mixed_detection():
    """修复章节混叠检测逻辑"""

    file_path = "novel_generator/blueprint_debug.py"

    # 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 定义要替换的旧逻辑（更精确的模式匹配，避免误匹配）
    old_pattern = r'''        # 🔍 首先检测章节混叠（章节标题出现在其他章节的内容中）
        content_mixed_chapters = \[\]
        for i, line in enumerate\(lines\):
            # 检查非行首位置的章节标题（在7个节的内容中）
            # 修复：使用正确的正则表达式字符串转义
            if not re\.match\(r'\^##\s\*\\\d+\\\.\|^\s\*\$', line\):  # 不是节标题或空行
                # 检查是否包含下一章的标题
                for next_chap in range\(expected_start \+ 1, expected_end \+ 2\):
                    # 匹配模式：第X章 - 标题 或 第X章\\n
                    if re\.search\(r'第\\\s\*' \+ str\(next_chap\) \+ r'\\\s\*章', line\):
                        # 检查这一行是否以节标题开头（即新的章节开始）
                        if not re\.match\(r'\^##\s\*\\\d+\\\.', line\):
                            # 找到混叠：章节标题出现在内容中
                            content_mixed_chapters\.append\(\{
                                'line_num': i \+ 1,
                                'content': line\.strip\(\)\[:80\],
                                'detected_chapter': next_chap
                            \}\)'''

    # 新的逻辑
    new_code = r'''        # 🔍 首先检测章节混叠（章节标题出现在其他章节的内容中）
        # 🚨 修复：只检测真正的独立章节标题行，忽略合法的上下文引用（如"启下"中的提及）
        content_mixed_chapters = []

        # 需要跳过的上下文：在以下节中，"第X章"的引用是合法的
        allowed_sections = {
            '衔接设计', '伏笔埋设', '启下', '伏笔', '回顾', '总结', '设计', '埋设'
        }

        current_section = None

        for i, line in enumerate(lines):
            stripped_line = line.strip()

            # 检测当前在哪个节
            if re.match(r'^##?\s*\d+\.\s*([\u4e00-\u9fa5]+)', stripped_line):
                section_title_match = re.match(r'^##?\s*\d+\.\s*([\u4e00-\u9fa5]+)', stripped_line)
                if section_title_match:
                    current_section = section_title_match.group(1)
                continue

            # 如果当前在允许引用"第X章"的节中，跳过检测
            if current_section and any(allowed in current_section for allowed in allowed_sections):
                continue

            # 如果是空行或格式标记（如**章节**: 第X章），跳过
            if not stripped_line or re.match(r'^\*\*[\u4e00-\u9fa5]+\*\*[:：]', stripped_line):
                continue

            # 检测章节标题（只检测行首的独立章节标题）
            if re.match(r'^第\s*\d+\s*章', stripped_line):
                chapter_match = re.search(r'第\s*(\d+)\s*章', stripped_line)
                if chapter_match:
                    detected_chapter = int(chapter_match.group(1))
                    # 只有当章节号超出预期范围时才标记为混叠
                    if detected_chapter > expected_end or detected_chapter < expected_start:
                        content_mixed_chapters.append({
                            'line_num': i + 1,
                            'content': stripped_line[:80],
                            'detected_chapter': detected_chapter
                        })'''

    # 尝试替换
    if re.search(old_pattern, content, re.DOTALL):
        content = re.sub(old_pattern, new_code, content, flags=re.DOTALL)
        print("✅ 成功替换章节混叠检测逻辑")
    else:
        print("❌ 未找到要替换的代码段，尝试手动修复...")
        # 手动查找并替换
        lines = content.split('\n')
        new_lines = []
        skip = False
        in_mixed_detection = False
        indent_level = 0

        for line in lines:
            # 检测混叠检测代码的开始
            if '        # 🔍 首先检测章节混叠' in line and not in_mixed_detection:
                in_mixed_detection = True
                new_lines.append(new_code)
                continue

            # 如果在混叠检测代码中，跳过原有代码
            if in_mixed_detection:
                # 检测混叠检测代码的结束（下一个空的 if 语句或错误检查）
                if line.strip().startswith('if content_mixed_chapters:') and 'content_mixed_chapters.append' in line:
                    continue
                elif line.strip().startswith('if content_mixed_chapters:'):
                    # 混叠检测代码结束
                    in_mixed_detection = False
                    new_lines.append(line)
                    continue
                else:
                    continue

            new_lines.append(line)

        content = '\n'.join(new_lines)
        print("✅ 手动修复完成")

    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 文件已更新: {file_path}")

if __name__ == "__main__":
    fix_mixed_detection()
