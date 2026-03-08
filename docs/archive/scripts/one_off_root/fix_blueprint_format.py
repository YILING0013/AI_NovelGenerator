# fix_blueprint_format.py
# -*- coding: utf-8 -*-
"""
蓝图格式统一修复工具

问题根源分析：
1. prompt_definitions.py 中的 ENHANCED_BLUEPRINT_TEMPLATE 包含13节格式
2. blueprint.py 中的验证逻辑只检查7个必需的节
3. 这种不一致导致 LLM 生成的内容格式混乱

修复方案：
1. 将 prompt_definitions.py 中的模板统一为7节格式
2. 确保 BLUEPRINT_FEW_SHOT_EXAMPLE 使用7节格式
3. 确保验证逻辑与模板一致
"""

import re
import os

# 定义标准的7节格式模板
STANDARD_7_SECTION_TEMPLATE = """
### **第{chapter_number}章 - [章节标题]**

## 1. 基础元信息
*   **章节序号**：第{chapter_number}章
*   **章节标题**：[章节标题]
*   **定位**：第[X]卷 [卷名] - 子幕[X] [子幕名]
*   **核心功能**：[一句话概括本章在全书中的作用]
*   **字数目标**：[3000-5000]字
*   **出场角色**：[列出本章登场的所有主要及次要角色]

## 2. 张力与冲突
*   **冲突类型**：[生存/权力/情感/理念等]
*   **核心冲突点**：[具体冲突内容]
*   **紧张感曲线**：[铺垫→爬升→爆发→回落/悬念]

## 3. 匠心思维应用
*   **应用场景**：[具体场景]
*   **思维模式**：[本源透视/去沁/金缮等]
*   **视觉化描述**：[错误写法 vs 正确写法]
*   **经典台词**：[代表性台词]

## 4. 伏笔与信息差
*   **本章植入伏笔**：[列出伏笔]
*   **本章回收伏笔**：[如有]
*   **信息差控制**：[主角知道 vs 敌人以为]

## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：[描述女性角色互动，如林小雨、苏清雪等]
*   **🚨 重要**：即使本章不涉及任何女性角色，也**必须保留此节**，并填写"本章不涉及女性角色互动"
*   **格式要求**：
    - 如果涉及：详细描述互动内容
    - 如果不涉及：必须写"本章不涉及女性角色互动"（不能省略整个节）

## 6. 剧情精要
*   **开场**：[开场场景]
*   **发展**：[节点1、节点2、节点3...]
*   **高潮**：[高潮事件]
*   **收尾**：[结尾状态/悬念]

## 7. 衔接设计
*   **承上**：[承接前文]
*   **转场**：[转场方式]
*   **启下**：[为后续埋下伏笔]
"""

def fix_prompt_definitions():
    """
    修复 prompt_definitions.py 中的模板定义
    """
    filepath = "prompt_definitions.py"

    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return False

    # 读取文件
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 备份原文件
    backup_path = filepath + ".backup_7section_fix"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 已备份原文件到: {backup_path}")

    # 修复 ENHANCED_BLUEPRINT_TEMPLATE - 移除第8-13节
    # 找到 ## 7. 衔接设计 的结束位置
    pattern = r'(## 7\. 衔接设计.*?)(\n## 8\.|\Z)'
    replacement = r'\1\n\n🚨 **格式禁忌**：\n- **严禁重复任何节标题**："## 1. 基础元信息"、"## 2. 张力与冲突"等在每章中只能出现一次\n- **严禁省略任何节**：所有7个节都必须有内容，包括"暧昧与修罗场"\n- **特别强调**："暧昧与修罗场"节即使不涉及女性角色，也必须保留并填写"本章不涉及女性角色互动"\n- **严禁**在"基础元信息"中重复写"第X章 - 标题"\n- **严禁**在正文中引用具体章节号（如"第1章"、"第50章"）\n- 只在章节开头写一次标题，后续用"本章"代替\n- 引用其他章节时，用"后续章节"、"前文"代替\n"""'

    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # 移除第8-13节的内容
    # 首先找到 ## 7. 衔接设计 之后的内容
    lines = new_content.split('\n')
    new_lines = []
    skip = False
    found_section_7 = False

    for i, line in enumerate(lines):
        # 检查是否到达第8节
        if line.startswith('## 8.'):
            skip = True
            continue

        # 如果正在跳过，继续直到找到模板结束的 """
        if skip:
            if '"""' in line and i > 100:  # 确保不是模板开始
                skip = False
                # 添加结束标记
                new_lines.append(line)
            continue

        new_lines.append(line)

    new_content = '\n'.join(new_lines)

    # 保存修复后的文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"✅ 已修复: {filepath}")
    print(f"   - 移除了第8-13节格式")
    print(f"   - 统一为7节标准格式")
    print(f"   - 添加了明确的格式禁忌说明")

    return True


def verify_fix():
    """
    验证修复是否成功
    """
    filepath = "prompt_definitions.py"

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否还有第8节
    if '## 8.' in content:
        print("⚠️ 警告：仍然检测到第8节，可能未完全修复")
        return False

    # 检查是否包含7节格式
    required_sections = [
        "## 1. 基础元信息",
        "## 2. 张力与冲突",
        "## 3. 匠心思维应用",
        "## 4. 伏笔与信息差",
        "## 5. 暧昧与修罗场",
        "## 6. 剧情精要",
        "## 7. 衔接设计"
    ]

    missing = []
    for section in required_sections:
        if section not in content:
            missing.append(section)

    if missing:
        print(f"❌ 验证失败：缺少以下节: {missing}")
        return False

    print("✅ 验证通过：模板已统一为7节格式")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 蓝图格式统一修复工具")
    print("=" * 60)

    # 执行修复
    if fix_prompt_definitions():
        print("\n" + "=" * 60)
        print("📋 验证修复结果...")
        verify_fix()
        print("=" * 60)
        print("\n✅ 修复完成！")
        print("\n下一步：")
        print("1. 检查 prompt_definitions.py 中的 BLUEPRINT_FEW_SHOT_EXAMPLE")
        print("2. 确保示例也使用7节格式")
        print("3. 运行测试脚本验证修复效果")
    else:
        print("\n❌ 修复失败，请检查文件权限和路径")
