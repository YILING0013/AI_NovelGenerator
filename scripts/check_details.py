# -*- coding: utf-8 -*-
"""查看重复和一致性问题详情"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.validators.duplicate import DuplicateDetector
from novel_generator.validators.consistency import ConsistencyValidator
from novel_generator.validators.base import ValidationContext

ctx = ValidationContext(r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator")

print("=" * 50)
print("重复章节详情:")
d = DuplicateDetector(ctx)
duplicates = d.scan_all_chapters()
for ch1, ch2, sim, common in duplicates:
    print(f"  第{ch1}章 vs 第{ch2}章: 相似度 {sim:.1%}")
    if common:
        print(f"    共同内容: {common[0][:60]}...")

print("\n" + "=" * 50)
print("一致性问题（前10个）:")
c = ConsistencyValidator(ctx)
issues = c.scan_all_chapters()
for ch, issue_list in issues[:10]:
    print(f"  第{ch}章: {issue_list}")
