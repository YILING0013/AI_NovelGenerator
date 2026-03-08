#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 blueprint.py 中的 chapter_list 生成逻辑
从已有内容中仅提取章节标题，避免展示旧格式导致LLM模仿错误格式
"""

import re

# 读取文件
with open('novel_generator/blueprint.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 要插入的新函数（使用原始字符串避免转义问题）
new_function = r'''    def _extract_chapter_titles_only(self, existing_content: str, max_chapters: int = 10) -> str:
        """
        从已有内容中仅提取章节标题，避免展示旧格式导致LLM模仿错误格式

        Args:
            existing_content: 已有的章节目录内容
            max_chapters: 最多提取多少章的标题

        Returns:
            格式化的章节标题列表字符串
        """
        if not existing_content:
            return ""

        import re

        # 匹配多种章节标题格式
        patterns = [
            r'^(第\d+章[：\s\-——]+.+?)(?:\n|$)',  # 第1章：标题 或 第1章 - 标题
            r'^第(\d+)章[：\s\-——]*(.+?)(?:\n|$)',  # 第1章标题
            r'^【(.+?)】.*?章节.*?[:：](.+?)(?:\n|$)',  # 【基础元信息】章节标题：xxx
        ]

        titles = []
        seen_chapters = set()

        for line in existing_content.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 尝试匹配章节标题
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    # 提取章节号和标题
                    if '第' in line and '章' in line:
                        # 直接使用匹配到的完整标题行
                        title = line
                        # 提取章节号用于去重
                        chapter_match = re.search(r'第(\d+)章', title)
                        if chapter_match:
                            chapter_num = chapter_match.group(1)
                            if chapter_num not in seen_chapters:
                                seen_chapters.add(chapter_num)
                                titles.append(title)
                    break

            if len(titles) >= max_chapters:
                break

        if titles:
            # 返回简洁的标题列表
            result = "以下是已生成章节的标题列表（仅用于了解剧情连贯性）：\n"
            result += "\n".join(titles)
            return result
        else:
            # 如果无法提取标题，返回空字符串
            return ""

'''

# 找到插入位置（在 _create_strict_prompt_with_guide 之前）
insertion_pattern = r'(        return result\n\n)(    def _create_strict_prompt_with_guide)'

# 替换：添加新函数
replacement = r'\1' + new_function + r'\2'

new_content = re.sub(insertion_pattern, replacement, content, count=1)

# 修改 chapter_list 的生成方式
old_chapter_list = r'chapter_list=existing_content\[-2000:\] if existing_content else ""'
new_chapter_list = 'chapter_list=self._extract_chapter_titles_only(existing_content[-5000:]) if existing_content else ""'

new_content = new_content.replace(old_chapter_list, new_chapter_list)

# 写回文件
with open('novel_generator/blueprint.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ 修复已应用！")
print("1. 添加了 _extract_chapter_titles_only() 函数")
print("2. 修改了 chapter_list 生成逻辑，现在只提取章节标题")
