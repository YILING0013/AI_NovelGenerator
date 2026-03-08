# fix_prompt_add_fewshot.py
# -*- coding: utf-8 -*-
"""
修复 _create_strict_prompt_with_guide 函数
添加 Few-Shot 示例以提高LLM生成质量
"""

import re

def fix_blueprint_prompt():
    """修复 blueprint.py 中的 prompt 构建函数"""

    filepath = 'novel_generator/blueprint.py'

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 找到需要修改的位置
    # 在 "        # 2. 模板与格式约束" 之前插入 Few-Shot 示例

    # 构建要插入的内容
    few_shot_section = '''        # 2. Few-Shot示例（展示正确的格式）
        few_shot_example = f"""

📚 **参考范例**（学习其格式和深度，但严禁抄袭剧情）：

{BLUEPRINT_FEW_SHOT_EXAMPLE}

⚠️ **重要警告**：上述范例仅用于学习格式。你现在的任务是生成 **第{start_chapter}章到第{end_chapter}章** 的内容，必须根据【生成指南】和【已有章节】继续推进剧情，**绝对禁止**复制范例中的剧情！

"""

        # 3. 模板与格式约束'''

    # 替换
    pattern = r'        # 2\. 模板与格式约束'
    replacement = few_shot_section

    new_content = re.sub(pattern, replacement, content, count=1)

    if new_content == content:
        print("❌ 未找到要替换的位置")
        return False

    # 保存
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("✅ 已添加 Few-Shot 示例到 prompt 构建函数")
    return True


if __name__ == "__main__":
    fix_blueprint_prompt()
