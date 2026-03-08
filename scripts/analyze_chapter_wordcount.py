#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析章节字数统计 - 统一字数标准
"""

import os
import re

def analyze_chapter_wordcount(chapters_dir: str = None):
    """分析章节文件的实际字数，统一统计标准"""
    
    if not chapters_dir:
        import sys
        if len(sys.argv) > 1:
            chapters_dir = sys.argv[1]
        else:
            print("Usage: python analyze_chapter_wordcount.py <chapters_directory>")
            sys.exit(1)

    print("🧠 Ultra-Think 章节字数统计分析")
    print("=" * 60)

    def count_content_chars(file_path):
        """统计实际内容字符数（去除行号前缀）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 去除行号前缀 (格式如 "1→", "2→", "123→")
            lines = content.split('\n')
            clean_content = []

            for line in lines:
                # 使用正则表达式去除行号前缀
                clean_line = re.sub(r'^\s*\d+→\s*', '', line)
                clean_content.append(clean_line)

            # 重新组合并去除首尾空白
            clean_text = '\n'.join(clean_content).strip()

            # 统计各种字数
            total_chars = len(clean_text)  # 包含换行符的总字符数
            text_chars = len(clean_text.replace('\n', ''))  # 纯文本字符数
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_text))  # 中文字符数

            return {
                'total_chars': total_chars,
                'text_chars': text_chars,
                'chinese_chars': chinese_chars,
                'clean_text_length': len(clean_text)
            }

        except Exception as e:
            print(f"❌ 读取文件失败 {file_path}: {e}")
            return None

    print("📊 各章节字数统计对比:")
    print("文件名                总字符数  纯文本  中文字符  文件大小")
    print("-" * 65)

    chapter_files = []
    for i in range(1, 21):  # 检查1-20章
        file_path = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if os.path.exists(file_path):
            chapter_files.append(file_path)

    total_chinese = 0
    chapters_under_5000 = []

    for file_path in sorted(chapter_files):
        filename = os.path.basename(file_path)

        # 文件大小
        file_size = os.path.getsize(file_path)

        # 内容统计
        stats = count_content_chars(file_path)
        if stats:
            total_chinese += stats['chinese_chars']

            # 检查是否少于5000中文字符
            if stats['chinese_chars'] < 5000:
                chapters_under_5000.append({
                    'filename': filename,
                    'chars': stats['chinese_chars']
                })

            print(f"{filename:<20} {stats['total_chars']:>8} {stats['text_chars']:>8} {stats['chinese_chars']:>8} {file_size:>8}")

    print("-" * 65)

    if chapter_files:
        avg_chinese = total_chinese / len(chapter_files)
        print(f"\n📈 统计摘要:")
        print(f"  总章节数: {len(chapter_files)}")
        print(f"  平均中文字符: {avg_chinese:.0f}")
        print(f"  总中文字符: {total_chinese:,}")

    if chapters_under_5000:
        print(f"\n⚠️ 少于5000字的章节:")
        for chapter in chapters_under_5000:
            print(f"  {chapter['filename']}: {chapter['chars']} 字符")
    else:
        print(f"\n✅ 所有章节都超过5000字")

    print(f"\n💡 建议的字数统计标准:")
    print(f"1. 使用 '中文字符数' 作为主要统计标准")
    print(f"2. 自动扩写触发条件: 中文字符 < 期望字数的80%")
    print(f"3. 在UI中显示: '当前XXX字 (中文YYY字)'")

    # 检查第18章的具体情况
    chapter_18_path = os.path.join(chapters_dir, "chapter_18.txt")
    if os.path.exists(chapter_18_path):
        print(f"\n🔍 第18章详细分析:")
        stats = count_content_chars(chapter_18_path)
        if stats:
            print(f"  文件大小: {os.path.getsize(chapter_18_path)} 字节")
            print(f"  总字符数: {stats['total_chars']}")
            print(f"  纯文本字符: {stats['text_chars']}")
            print(f"  中文字符: {stats['chinese_chars']} ← 这应该是实际字数")

            # 显示前100个字符作为示例
            with open(chapter_18_path, 'r', encoding='utf-8') as f:
                content = f.read()
                clean_content = re.sub(r'^\s*\d+→\s*', '', content, flags=re.MULTILINE)
                preview = clean_content[:100]
                print(f"  内容预览: {preview}...")

if __name__ == "__main__":
    analyze_chapter_wordcount()