#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说章节完整性分析器 - Ultra-Think深度分析版本
"""

import re
import os

def analyze_novel_directory(file_path: str = None):
    """深度分析小说目录完整性"""
    
    if not file_path:
        import sys
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
        else:
            print("Usage: python chapter_completeness_analyzer.py <Novel_directory.txt>")
            sys.exit(1)

    if not os.path.exists(file_path):
        return {"error": "文件不存在"}

    print("🧠 Ultra-Think 深度分析模式启动")
    print("=" * 60)

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. 章节提取和分析
    chapter_pattern = r'###\s*\*{0,2}第\s*(\d+)\s*章.*'
    chapters = re.findall(chapter_pattern, content)
    chapter_numbers = [int(ch) for ch in chapters if ch.isdigit()]

    unique_chapters = sorted(list(set(chapter_numbers)))
    expected_chapters = list(range(1, 391))  # 期望1-390章

    print(f"📊 基础统计:")
    print(f"  总文件大小: {len(content):,} 字符 ({len(content)/1024/1024:.2f} MB)")
    print(f"  总行数: {content.count(chr(10)):,} 行")
    print(f"  识别章节总数: {len(chapters)} (包含重复)")
    print(f"  去重章节数: {len(unique_chapters)}")
    print(f"  期望章节数: 390")

    # 2. 章节连续性分析
    missing_chapters = [ch for ch in expected_chapters if ch not in unique_chapters]
    duplicate_chapters = [ch for ch in chapters if chapters.count(ch) > 1]

    print(f"\n🔍 章节完整性分析:")
    print(f"  ✅ 存在章节: {len(unique_chapters)} 章")
    print(f"  ❌ 缺失章节: {len(missing_chapters)} 章")
    print(f"  🔄 重复章节: {len(set(duplicate_chapters))} 章")

    completion_rate = (len(unique_chapters) / 390) * 100
    print(f"  📈 完成率: {completion_rate:.1f}%")

    # 3. 章节分布分析
    print(f"\n📋 章节分布分析:")

    # 分析章节编号的分组
    groups = {}
    for ch in unique_chapters:
        group = (ch - 1) // 10  # 每10章一组
        group_name = f"第{group*10+1}-{group*10+10}章"
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(ch)

    for group_name, ch_list in sorted(groups.items()):
        print(f"  {group_name}: {len(ch_list)}章 ({', '.join(map(str, ch_list[:5]))}{'...' if len(ch_list)>5 else ''})")

    # 4. 缺失章节详情
    if missing_chapters:
        print(f"\n❌ 缺失章节详情:")
        missing_groups = {}
        for ch in missing_chapters:
            group = (ch - 1) // 50  # 每50章一组显示
            group_name = f"第{group*50+1}-{group*50+50}章"
            if group_name not in missing_groups:
                missing_groups[group_name] = []
            missing_groups[group_name].append(ch)

        for group_name, missing_list in sorted(missing_groups.items()):
            print(f"  {group_name}: 缺失{len(missing_list)}章")
            if len(missing_list) <= 20:
                print(f"    具体缺失: {', '.join(map(str, missing_list))}")
            else:
                print(f"    具体缺失: {', '.join(map(str, missing_list[:10]))}... (共{len(missing_list)}章)")

    # 5. 内容结构分析
    print(f"\n🏗️ 内容结构分析:")

    # 检查标准模块
    modules = [
        "【基础元信息】",
        "【张力架构设计】",
        "【情感轨迹工程】",
        "【核心结构矩阵】",
        "【情节精要蓝图】",
        "【系统机制整合】",
        "【多层次悬念体系】",
        "【创作执行指南】",
        "【系统性衔接设计】"
    ]

    module_counts = {}
    for module in modules:
        count = content.count(module)
        module_counts[module] = count
        print(f"  {module}: {count} 个")

    # 6. 格式一致性检查
    print(f"\n📝 格式一致性检查:")

    # 检查不同的章节标题格式
    format_patterns = [
        (r'### \*\*第(\d+)章', "### **第X章"),
        (r'### 第(\d+)章', "### 第X章"),
        (r'##\*第(\d+)章', "##*第X章"),
    ]

    format_counts = {}
    for pattern, format_name in format_patterns:
        matches = re.findall(pattern, content)
        format_counts[format_name] = len(matches)
        if matches:
            print(f"  {format_name}: {len(matches)} 个")

    # 7. 异常检测
    print(f"\n⚠️ 异常检测:")

    # 检查可能的截断
    incomplete_ends = content.count('---\n\n### 第') - content.count('收尾策略')
    if incomplete_ends > 0:
        print(f"  可能的截断章节: {incomplete_ends} 个")

    # 检查异常短的章节
    chapters_with_length = {}
    for i in range(1, 391):
        chapter_pattern = rf'###\s*\*{{0,2}}第\s*{i}\s*章.*?(?=###\s*\*{{0,2}}第\s*\d+\s*章|$)'
        match = re.search(chapter_pattern, content, re.DOTALL)
        if match:
            chapters_with_length[i] = len(match.group(0))

    if chapters_with_length:
        avg_length = sum(chapters_with_length.values()) / len(chapters_with_length)
        short_chapters = [ch for ch, length in chapters_with_length.items() if length < avg_length * 0.3]
        if short_chapters:
            print(f"  异常短章节: {len(short_chapters)} 个 (少于平均长度的30%)")
            if len(short_chapters) <= 10:
                print(f"    具体章节: {', '.join(map(str, short_chapters))}")

    # 8. 总结和建议
    print(f"\n📋 分析总结:")

    issues = []
    if len(missing_chapters) > 0:
        issues.append(f"严重缺失: {len(missing_chapters)}章内容缺失")
    if len(set(duplicate_chapters)) > 0:
        issues.append(f"重复问题: {len(set(duplicate_chapters))}章重复出现")
    if completion_rate < 50:
        issues.append("完成率过低: 建议重新生成缺失章节")
    if len(content) > 5 * 1024 * 1024:  # 5MB
        issues.append("文件过大: 建议按卷分割")

    if issues:
        print("  🚨 发现问题:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  ✅ 未发现严重问题")

    print(f"\n💡 建议:")
    if len(missing_chapters) > 200:
        print("  1. 优先补充第1-20章内容（关键开篇章节）")
        print("  2. 考虑重新生成完整目录")
        print("  3. 建立章节完整性验证机制")
    elif len(missing_chapters) > 0:
        print("  1. 按批次补充缺失章节")
        print("  2. 重点保证剧情连贯性")
    else:
        print("  1. 定期备份文件")
        print("  2. 建立版本控制机制")

    return {
        "total_chapters": len(unique_chapters),
        "missing_chapters": len(missing_chapters),
        "completion_rate": completion_rate,
        "file_size_mb": len(content) / 1024 / 1024,
        "issues": issues
    }

if __name__ == "__main__":
    result = analyze_novel_directory()
    print(f"\n🎯 Ultra-Think 分析完成!")