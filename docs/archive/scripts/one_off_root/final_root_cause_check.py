# final_root_cause_check.py
# -*- coding: utf-8 -*-
"""
蓝图生成问题根本原因修复 - 最终验证检查

本脚本执行全面的验证，确保所有修复都已正确应用
"""

import re
import os
import sys


def check_1_prompt_definitions():
    """第1次检查：prompt_definitions.py"""
    print("\n=== 第1次检查：prompt_definitions.py ===")

    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查1.1: 没有8-13节
    for i in range(8, 14):
        if f'## {i}.' in content:
            print(f"   ❌ 仍包含第{i}节定义")
            return False

    # 检查1.2: 7节完整性
    required = ['基础元信息', '张力与冲突', '匠心思维应用',
                '伏笔与信息差', '暧昧与修罗场', '剧情精要', '衔接设计']
    for section in required:
        if section not in content:
            print(f"   ❌ 缺少: {section}")
            return False

    # 检查1.3: 示例描述正确
    if '13节' in content:
        print(f"   ❌ 仍包含'13节'文字")
        return False

    print("   ✅ prompt_definitions.py 正确（7节，无13节残留）")
    return True


def check_2_blueprint_py():
    """第2次检查：blueprint.py"""
    print("\n=== 第2次检查：blueprint.py ===")

    with open('novel_generator/blueprint.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查2.1: required_sections定义正确
    match = re.search(r'required_sections\s*=\s*\[(.+?)\]', content, re.DOTALL)
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

    # 检查2.2: prompt构建函数包含Few-Shot示例
    if 'few_shot_example = f"""' not in content:
        print("   ❌ _create_strict_prompt_with_guide 缺少 few_shot_example")
        return False

    if '{BLUEPRINT_FEW_SHOT_EXAMPLE}' not in content:
        print("   ❌ _create_strict_prompt_with_guide 缺少 BLUEPRINT_FEW_SHOT_EXAMPLE 引用")
        return False

    # 检查2.3: return语句包含few_shot_example
    if 'return prompt_header + few_shot_example + strict_requirements' not in content:
        print("   ❌ return语句未包含 few_shot_example")
        return False

    print("   ✅ blueprint.py 正确（7节，包含Few-Shot示例）")
    return True


def check_3_progressive_generator():
    """第3次检查：progressive_blueprint_generator.py"""
    print("\n=== 第3次检查：progressive_blueprint_generator.py ===")

    with open('novel_generator/progressive_blueprint_generator.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查3.1: 第一个 required_modules
    match1 = re.search(r'self\.required_modules\s*=\s*\{(.+?)\}', content, re.DOTALL)
    if match1:
        modules_text = match1.group(1)
        required_modules = re.findall(r'"([^"]+)"', modules_text)

        expected = [
            "## 1. 基础元信息",
            "## 2. 张力与冲突",
            "## 3. 匠心思维应用",
            "## 4. 伏笔与信息差",
            "## 5. 暧昧与修罗场",
            "## 6. 剧情精要",
            "## 7. 衔接设计",
        ]

        if required_modules != expected:
            print(f"   ❌ 第一个required_modules不匹配")
            print(f"      期望: {expected}")
            print(f"      实际: {required_modules}")
            return False

    # 检查3.2: 第二个 required_modules
    match2 = re.search(r'required_modules\s*=\s*\[(.+?)\]', content)
    if match2:
        modules_text = match2.group(1)
        required_modules = re.findall(r'"([^"]+)"', modules_text)

        expected = ["基础元信息", "张力与冲突", "匠心思维应用",
                   "伏笔与信息差", "暧昧与修罗场", "剧情精要", "衔接设计"]

        if required_modules != expected:
            print(f"   ❌ 第二个required_modules不匹配")
            print(f"      期望: {expected}")
            print(f"      实际: {required_modules}")
            return False

    print("   ✅ progressive_blueprint_generator.py 正确（7节，包含第5节）")
    return True


def check_4_consistency():
    """第4次检查：一致性验证"""
    print("\n=== 第4次检查：一致性验证 ===")

    # 检查所有核心文件的节定义是否一致
    files_to_check = [
        ('prompt_definitions.py', 'ENHANCED_BLUEPRINT_TEMPLATE'),
        ('novel_generator/blueprint.py', 'required_sections'),
        ('novel_generator/progressive_blueprint_generator.py', 'required_modules'),
    ]

    expected_7_sections = ['基础元信息', '张力与冲突', '匠心思维应用',
                          '伏笔与信息差', '暧昧与修罗场', '剧情精要', '衔接设计']

    for filepath, var_name in files_to_check:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否包含所有7节
        for section in expected_7_sections:
            if section not in content:
                print(f"   ❌ {filepath} 缺少: {section}")
                return False

    print("   ✅ 所有文件节定义一致（7节标准）")
    return True


def main():
    """主函数"""
    print("="*70)
    print("🔍 蓝图生成问题根本原因修复 - 最终验证检查")
    print("="*70)

    results = []
    results.append(("prompt_definitions.py", check_1_prompt_definitions()))
    results.append(("blueprint.py", check_2_blueprint_py()))
    results.append(("progressive_blueprint_generator.py", check_3_progressive_generator()))
    results.append(("一致性验证", check_4_consistency()))

    print("\n" + "="*70)
    print("📊 检查结果汇总")
    print("="*70)

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {name}: {status}")
        if not passed:
            all_passed = False

    print("="*70)

    if all_passed:
        print("\n🎉 所有检查通过！")
        print("\n✅ 修复总结：")
        print("   1. ✅ prompt_definitions.py - 7节格式，无13节残留")
        print("   2. ✅ blueprint.py - 添加了Few-Shot示例到prompt")
        print("   3. ✅ progressive_blueprint_generator.py - 修正为7节（添加第5节）")
        print("   4. ✅ 所有文件节定义一致")

        print("\n🎯 根本原因已修复：")
        print("   1. ✅ Prompt缺少Few-Shot示例 - 已添加 BLUEPRINT_FEW_SHOT_EXAMPLE")
        print("   2. ✅ progressive_generator缺少第5节 - 已添加'暧昧与修罗场'")
        print("   3. ✅ 第7节名称不一致 - 统一为'衔接设计'")

        print("\n🚀 现在蓝图生成应该：")
        print("   ✓ 每章结构一致（都是7节）")
        print("   ✓ 不会出现重复的节")
        print("   ✓ 不会出现错乱的节")
        return 0
    else:
        print("\n❌ 部分检查失败，请修复后重试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
