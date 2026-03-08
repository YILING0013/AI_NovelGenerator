# fix_return_statement.py
# -*- coding: utf-8 -*-
"""
修复 return 语句，添加 few_shot_example
"""

def fix_return():
    filepath = 'novel_generator/blueprint.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 替换 return 语句
    old_return = '        return prompt_header + strict_requirements'
    new_return = '        return prompt_header + few_shot_example + strict_requirements'

    if old_return not in content:
        print("❌ 未找到要替换的 return 语句")
        return False

    content = content.replace(old_return, new_return)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ 已修复 return 语句，添加了 few_shot_example")
    return True


if __name__ == "__main__":
    fix_return()
