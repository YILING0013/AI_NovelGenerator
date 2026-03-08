# -*- coding: utf-8 -*-
"""临时脚本：查看深度扫描结果"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.batch_pre_checker import BatchPreChecker

checker = BatchPreChecker(r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator")
report = checker.run_all_checks(deep_scan=True)

print("=" * 50)
print("基础检查:")
for k, v in report["checks"].items():
    print(f"  {k}: {v['status']} {v.get('score', '')}")

print("\n深度扫描:")
for k, v in report.get("deep_checks", {}).items():
    status = v.get("status", "未知")
    print(f"  {k}: {status}")
    
    # 显示详细信息
    if "chapters_affected" in v:
        print(f"    影响章节数: {v['chapters_affected']}")
    if "pairs_found" in v:
        print(f"    重复对数: {v['pairs_found']}")
    if "count" in v:
        print(f"    问题总数: {v['count']}")
