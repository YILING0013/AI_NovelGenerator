# simple_blueprint_fix.py
# -*- coding: utf-8 -*-
"""
简化版蓝图格式修复脚本
"""

import os
import shutil
from datetime import datetime

def main():
    print("🔧 蓝图格式简化修复")
    print("=" * 60)
    
    # 1. 备份 blueprint.py
    file_path = "novel_generator/blueprint.py"
    backup_path = f"{file_path}.backup_simple_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"1. 备份到: {backup_path}")
    shutil.copy2(file_path, backup_path)
    
    # 2. 读取文件
    print("2. 读取文件...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 3. 计数修复项
    print("3. 分析需要修复的内容...")
    
    # 查找所有重复的警告关键词
    keywords = [
        "绝对禁止省略",
        "零容忍政策",
        "每个章节都必须严格使用",
        "所有7个节都必须存在"
        "严禁生成多余章节",
        "不得省略任何一节",
    ]
    
    count = 0
    for keyword in keywords:
        occurrences = content.count(keyword)
        if occurrences > 2:
            count += occurrences
            print(f"   - '{keyword}': {occurrences} 次 (重复 {occurrences-2} 次)")
    
    print(f"\n总重复次数: {count}")
    
    # 4. 建议的下一步
    print("\n" + "=" * 60)
    print("修复建议")
    print("=" * 60)
    print("由于重复警告过于复杂，建议采用以下方案之一：")
    print("")
    print("方案 A - 渐进式修复（推荐）:")
    print("  1. 删除第 691-766 行的 strict_requirements 定义")
    print("  2. 替换为简化的版本（见 BLUEPRINT_FORMAT_V3）")
    print("  3. 测试验证")
    print("")
    print("方案 B - 完全重写:")
    print("  1. 删除所有重复的格式定义")
    print("  2. 使用统一的 V3.0 格式")
    print("  3. 重写验证逻辑")
    print("")
    print("⚠️ 注意：建议先在测试环境验证，确认无误后再应用到生产环境")
    
    print("\n" + "=" * 60)
    print("已完成")
    print("=" * 60)
    print(f"备份文件: {backup_path}")
    print("原始文件保持不变，可以随时回滚")

if __name__ == "__main__":
    main()
