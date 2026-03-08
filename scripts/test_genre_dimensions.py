# -*- coding: utf-8 -*-
"""测试题材维度扩展功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chapter_quality_analyzer import ChapterQualityAnalyzer
import json

# 测试wxhyj小说
novel_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj"
analyzer = ChapterQualityAnalyzer(novel_path)

print("=" * 50)
print("题材维度扩展测试")
print("=" * 50)
print(f"检测到题材: {analyzer.genre}")
print()

# 读取第1章测试
chapter_file = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\chapters\chapter_1.txt"
with open(chapter_file, 'r', encoding='utf-8') as f:
    content = f.read()

scores = analyzer.analyze_content(content)

print("=== 基础8维度评分 ===")
for key in ["剧情连贯性", "角色一致性", "写作质量", "情感张力", "系统机制"]:
    if key in scores:
        print(f"  {key}: {scores[key]:.1f}")
print(f"  综合评分: {scores.get('综合评分', 0):.1f}")
print()

if "题材维度" in scores:
    print("=== 题材扩展维度评分 ===")
    for dim, data in scores["题材维度"].items():
        print(f"  {data['name']}: {data['score']:.2f} - {data['details']}")
    print(f"  题材综合分: {scores['题材综合分']:.1f}")
    print()
    
    if "题材改进建议" in scores:
        print("=== 改进建议 ===")
        for hint in scores["题材改进建议"]:
            print(f"  {hint}")
else:
    print("未检测到题材维度评分")

print()
print("=" * 50)
