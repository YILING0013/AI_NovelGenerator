# fix_chunked_prompt.py
# -*- coding: utf-8 -*-
"""
修复 chunked_chapter_blueprint_prompt 中的第8-13节
"""

def fix_prompt():
    with open('temp_chunked_prompt.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 找到并删除第8-13节的内容
    # 第8节从 "## 8. 系统机制整合" 开始
    # 到 "## 13. 质量自查清单" 结束
    new_lines = []
    skip = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # 检测是否到达第8节
        if stripped.startswith('## 8.'):
            skip = True
            continue
        
        # 如果正在跳过，继续直到遇到强制要求部分
        if skip:
            if stripped.startswith('🚨【绝对强制性要求'):
                skip = False
                new_lines.append(line)
            continue
        
        new_lines.append(line)
    
    # 修改格式要求说明
    final_lines = []
    for line in new_lines:
        # 将 "13节数字格式" 改为 "7节数字格式"
        line = line.replace('13节数字格式', '7节数字格式')
        line = line.replace('13节', '7节')
        final_lines.append(line)
    
    with open('temp_chunked_prompt_fixed.txt', 'w', encoding='utf-8') as f:
        f.writelines(final_lines)
    
    print(f"✅ 已修复 chunked_chapter_blueprint_prompt")
    print(f"   原行数: {len(lines)}")
    print(f"   新行数: {len(final_lines)}")
    print(f"   删除行数: {len(lines) - len(final_lines)}")

if __name__ == "__main__":
    fix_prompt()
