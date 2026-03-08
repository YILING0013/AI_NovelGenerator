# add_chunked_prompt.py
# -*- coding: utf-8 -*-
"""
将修复后的 chunked_chapter_blueprint_prompt 添加到 prompt_definitions.py
"""

def add_chunked_prompt():
    # 读取修复后的 chunked_prompt
    with open('temp_chunked_prompt_fixed.txt', 'r', encoding='utf-8') as f:
        chunked_content = f.read()
    
    # 读取当前的 prompt_definitions.py
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 在 BLUEPRINT_FEW_SHOT_EXAMPLE 结束后添加 chunked_chapter_blueprint_prompt
    # 找到添加位置（在 triple quotes 之后，summary_prompt 之前）
    marker = '# =============== 6. 前文摘要更新 ==================='
    
    new_content = content.replace(
        marker,
        f'# =============== 分块生成章节蓝图提示词 ================\n{chunked_content}\n\n{marker}'
    )
    
    with open('prompt_definitions.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ 已添加 chunked_chapter_blueprint_prompt 到 prompt_definitions.py")

if __name__ == "__main__":
    add_chunked_prompt()
