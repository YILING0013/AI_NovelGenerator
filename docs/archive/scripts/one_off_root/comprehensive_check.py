# comprehensive_check.py
# -*- coding: utf-8 -*-
"""
蓝图格式完整性综合检查脚本
进行多轮深度检查，确保没有遗漏任何问题
"""

import re
import os
import sys


def check_1_sections():
    """第1次检查：节标题完整性"""
    print("\n=== 第1次检查：节标题完整性 ===")

    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查第8-13节
    for i in range(8, 14):
        if f'## {i}.' in content:
            print(f"   ❌ 发现第{i}节")
            return False

    # 检查7节完整性
    required = ['基础元信息', '张力与冲突', '匠心思维应用',
                '伏笔与信息差', '暧昧与修罗场', '剧情精要', '衔接设计']
    for section in required:
        if section not in content:
            print(f"   ❌ 缺少: {section}")
            return False

    print("   ✅ 只包含7节，格式完整")
    return True


def check_2_text():
    """第2次检查：文本内容"""
    print("\n=== 第2次检查：文本内容 ===")

    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查"13节"文字
    if '13节' in content:
        print("   ❌ 仍包含'13节'文字")
        return False

    # 检查"13-section"
    if '13-section' in content:
        print("   ❌ 仍包含'13-section'文字")
        return False

    print("   ✅ 没有13节相关文字")
    return True


def check_3_modules():
    """第3次检查：模块导入"""
    print("\n=== 第3次检查：模块导入 ===")

    try:
        from prompt_definitions import (
            ENHANCED_BLUEPRINT_TEMPLATE,
            BLUEPRINT_FEW_SHOT_EXAMPLE,
            chunked_chapter_blueprint_prompt
        )

        # 验证模板内容
        for i in range(8, 14):
            if f'## {i}.' in ENHANCED_BLUEPRINT_TEMPLATE:
                print(f"   ❌ ENHANCED_BLUEPRINT_TEMPLATE 包含第{i}节")
                return False
            if f'## {i}.' in BLUEPRINT_FEW_SHOT_EXAMPLE:
                print(f"   ❌ BLUEPRINT_FEW_SHOT_EXAMPLE 包含第{i}节")
                return False

        print("   ✅ 所有模块导入成功，内容正确")
        return True
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False


def check_4_core_files():
    """第4次检查：核心文件"""
    print("\n=== 第4次检查：核心文件 ===")

    core_files = [
        'novel_generator/blueprint.py',
        'novel_generator/chapter.py',
        'prompt_definitions.py'
    ]

    for filepath in core_files:
        if not os.path.exists(filepath):
            print(f"   ❌ 文件不存在: {filepath}")
            return False

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        for i in range(8, 14):
            if f'## {i}.' in content:
                print(f"   ❌ {filepath} 包含第{i}节")
                return False

    print("   ✅ 所有核心文件干净")
    return True


def check_5_consistency():
    """第5次检查：一致性验证"""
    print("\n=== 第5次检查：一致性验证 ===")

    # 获取验证逻辑中的必需节
    # 这里我们直接检查源码
    with open('novel_generator/blueprint.py', 'r', encoding='utf-8') as f:
        bp_content = f.read()

    # 提取required_sections
    match = re.search(r'required_sections\s*=\s*\[(.+?)\]', bp_content, re.DOTALL)
    if not match:
        print("   ❌ 无法找到required_sections定义")
        return False

    required_text = match.group(1)
    required_sections = re.findall(r'"([^"]+)"', required_text)

    expected = ['基础元信息', '张力与冲突', '匠心思维应用',
                '伏笔与信息差', '暧昧与修罗场', '剧情精要', '衔接设计']

    if required_sections != expected:
        print(f"   ❌ required_sections不匹配")
        print(f"      期望: {expected}")
        print(f"      实际: {required_sections}")
        return False

    print("   ✅ 验证逻辑与模板一致")
    return True


def main():
    """主函数"""
    print("="*60)
    print("🔍 蓝图格式完整性综合检查")
    print("="*60)

    results = []
    results.append(("节标题完整性", check_1_sections()))
    results.append(("文本内容", check_2_text()))
    results.append(("模块导入", check_3_modules()))
    results.append(("核心文件", check_4_core_files()))
    results.append(("一致性验证", check_5_consistency()))

    print("\n" + "="*60)
    print("📊 检查结果汇总")
    print("="*60)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {name}: {status}")
        if not passed:
            all_passed = False

    print("="*60)

    if all_passed:
        print("\n🎉 所有检查通过！")
        print("\n✅ 确认：")
        print("   1. 只包含7节格式")
        print("   2. 没有13节相关内容")
        print("   3. 所有模块正常导入")
        print("   4. 核心文件全部干净")
        print("   5. 验证逻辑与模板一致")
        return 0
    else:
        print("\n❌ 部分检查失败，请修复后重试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
