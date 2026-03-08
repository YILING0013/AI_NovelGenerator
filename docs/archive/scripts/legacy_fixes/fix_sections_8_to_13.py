# fix_sections_8_to_13.py
# -*- coding: utf-8 -*-
"""
彻底修复 prompt_definitions.py，移除所有第8-13节
"""

import re

def fix_file():
    # 读取原备份文件
    backup_path = 'docs/archive/legacy_prompts/prompt_definitions.py.backup_7section_fix'
    with open(backup_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    i = 0
    in_template = False
    in_example = False
    skip_section = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检测是否进入模板
        if 'ENHANCED_BLUEPRINT_TEMPLATE = """' in stripped:
            in_template = True
            new_lines.append(line)
            i += 1
            continue

        # 检测模板结束
        if in_template and stripped == '"""' and i > 100:
            in_template = False
            new_lines.append(line)
            i += 1
            continue

        # 检测是否进入示例
        if 'BLUEPRINT_FEW_SHOT_EXAMPLE = """' in stripped:
            in_example = True
            new_lines.append(line)
            i += 1
            continue

        # 检测示例结束
        if in_example and stripped == '"""' and i > 1000:
            in_example = False
            new_lines.append(line)
            i += 1
            continue

        # 在模板或示例中，检查是否遇到第8-13节
        if (in_template or in_example) and stripped.startswith('## 8.'):
            # 跳过这一行以及后续行，直到遇到下一个章节标题或示例结束
            skip_section = True
            i += 1
            continue

        if skip_section:
            # 检查是否到达下一个章节或示例结束
            if stripped.startswith('### **第'):
                # 下一个章节开始
                skip_section = False
                new_lines.append(line)
            elif (in_template or in_example) and stripped == '"""':
                # 示例或模板结束
                skip_section = False
                new_lines.append(line)
            # 否则继续跳过
            i += 1
            continue

        new_lines.append(line)
        i += 1

    # 写入修复后的文件
    with open('prompt_definitions.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print("✅ 已完成修复")

def verify():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查第8-13节
    for i in range(8, 14):
        if f'## {i}.' in content:
            print(f"❌ 仍有第{i}节")
            return False

    # 检查7节格式
    required = ['## 1. 基础元信息', '## 2. 张力与冲突', '## 3. 匠心思维应用',
               '## 4. 伏笔与信息差', '## 5. 暧昧与修罗场', '## 6. 剧情精要', '## 7. 衔接设计']

    for section in required:
        if section not in content:
            print(f"❌ 缺少: {section}")
            return False

    print("✅ 验证通过")
    return True

if __name__ == "__main__":
    fix_file()
    verify()
