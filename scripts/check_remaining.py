# -*- coding: utf-8 -*-
"""查看剩余问题"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.validators.placeholder import PlaceholderDetector
from novel_generator.validators.structure import StructureValidator
from novel_generator.validators.base import ValidationContext

ctx = ValidationContext(r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator")

print("=" * 50)
print("剩余占位符:")
d = PlaceholderDetector(ctx)
r = d.scan_all_chapters()
for ch, placeholders in r.items():
    print(f"  第{ch}章: {placeholders}")

print("\n" + "=" * 50)
print("结构不完整:")
v = StructureValidator(ctx)
r2 = v.scan_all_chapters()
for ch, info in r2.items():
    print(f"  第{ch}章: 缺少 {info['missing']}")
