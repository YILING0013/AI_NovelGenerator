"""
验证调试助手 - 用于诊断生成失败的原因

使用方法：
1. 生成失败后，在Python控制台中运行此脚本
2. 它会读取wxhyj/Novel_directory.txt（如果存在）并显示验证错误
"""

import os
import sys
import re

def analyze_directory_file(filepath="wxhyj/Novel_directory.txt"):
    """分析目录文件，找出所有验证问题"""

    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    print("=" * 80)
    print(f"分析文件: {filepath}")
    print(f"文件大小: {len(content)} 字符")
    print("=" * 80)

    # 提取所有章节
    chapter_pattern = r'(?:^|\n)\s*#{1,3}\s*\*{0,2}\s*第(\d+)章'
    chapters = re.findall(chapter_pattern, content, re.MULTILINE)

    print(f"\n📚 找到 {len(chapters)} 个章节: {[int(c) for c in chapters]}")

    # 检查每个章节的节
    required_sections = [
        "## 1. 基础元信息",
        "## 2. 张力与冲突",
        "## 3. 匠心思维应用",
        "## 4. 伏笔与信息差",
        "## 5. 暧昧与修罗场",
        "## 6. 剧情精要",
        "## 7. 衔接设计"
    ]

    lines = content.split('\n')
    current_chapter = None
    issues = []

    for i, line in enumerate(lines):
        # 检测章节标题
        chapter_match = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', line.strip())
        if chapter_match:
            current_chapter = int(chapter_match.group(1))

            # 检查章节的节
            chapter_lines = []
            j = i + 1
            while j < len(lines):
                next_chapter = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', lines[j].strip())
                if next_chapter:
                    break
                chapter_lines.append(lines[j])
                j += 1

            chapter_text = '\n'.join(chapter_lines)

            print(f"\n第{current_chapter}章:")

            missing = []
            for section in required_sections:
                section_name = section.split('.', 1)[1].strip() if '.' in section else section
                if section not in chapter_text and section_name not in chapter_text:
                    missing.append(section_name)

            if missing:
                print(f"  ❌ 缺失节: {', '.join(missing)}")
                issues.append(f"第{current_chapter}章缺失: {', '.join(missing)}")
            else:
                print(f"  ✅ 所有节都存在")

            # 检查内容长度
            if len(chapter_text) < 500:
                print(f"  ⚠️ 内容太少: {len(chapter_text)} 字符")
                issues.append(f"第{current_chapter}章内容太少")

    print("\n" + "=" * 80)
    print("问题总结")
    print("=" * 80)

    if issues:
        print(f"\n发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("\n✅ 未发现问题")

    # 检查格式问题
    print("\n" + "=" * 80)
    print("格式检查")
    print("=" * 80)

    # 检查是否有"第 X 章"格式（有空格）
    loose_pattern = r"(?m)^[#*\s]*第\s+\d+\s+章"
    loose_matches = re.findall(loose_pattern, content)
    if loose_matches:
        print(f"⚠️ 发现 {len(loose_matches)} 个格式混乱（使用了 '第 X 章' 格式）")

    # 检查是否有重复的章节
    chapter_numbers = [int(c) for c in chapters]
    from collections import Counter
    counts = Counter(chapter_numbers)
    duplicates = {k: v for k, v in counts.items() if v > 1}
    if duplicates:
        print(f"⚠️ 发现重复的章节: {duplicates}")

    return issues

def show_sample_content(filepath="wxhyj/Novel_directory.txt", lines=100):
    """显示文件的前N行"""
    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    print("=" * 80)
    print(f"文件前 {lines} 行")
    print("=" * 80)
    print('\n'.join(content.split('\n')[:lines]))

def main():
    print("🔍 小说目录验证调试助手")
    print("=" * 80)

    # 分析文件
    issues = analyze_directory_file()

    # 显示示例内容
    if os.path.exists("wxhyj/Novel_directory.txt"):
        print("\n")
        show_sample_content(lines=50)

    # 给出建议
    print("\n" + "=" * 80)
    print("建议")
    print("=" * 80)

    if issues:
        print("\n发现问题，建议：")
        print("1. 如果缺失节，运行修复脚本: python post_generation_fixer.py")
        print("2. 如果内容太少，调整LLM的max_tokens参数")
        print("3. 如果格式混乱，运行格式清理")
        print("4. 查看详细的LLM日志了解生成过程")
    else:
        print("\n文件格式正确！")
        print("如果仍然生成失败，可能是：")
        print("1. API调用问题 - 检查API key和网络")
        print("2. LLM返回内容不符合预期 - 调整temperature或prompt")
        print("3. 验证逻辑过于严格 - 考虑放宽验证规则")

if __name__ == "__main__":
    main()
