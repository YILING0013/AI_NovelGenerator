# fix_template_sections.py
# -*- coding: utf-8 -*-
"""
从 ENHANCED_BLUEPRINT_TEMPLATE 中删除第8-13节
"""

def fix_template():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 找到 ENHANCED_BLUEPRINT_TEMPLATE 并删除第8-13节
    # 在 "## 7. 衔接设计" 之后，""" 之前删除所有内容
    lines = content.split('\n')
    new_lines = []
    in_template = False
    skip_until_end = False
    
    for i, line in enumerate(lines):
        # 检测进入模板
        if 'ENHANCED_BLUEPRINT_TEMPLATE = """' in line:
            in_template = True
            new_lines.append(line)
            continue
        
        if in_template:
            # 检测是否到达第8节
            if line.strip().startswith('## 8.'):
                skip_until_end = True
                continue
            
            # 如果正在跳过，检查是否到达模板结束
            if skip_until_end:
                if line.strip() == '"""':
                    skip_until_end = False
                    new_lines.append(line)
                continue
        
        new_lines.append(line)
    
    new_content = '\n'.join(new_lines)
    
    with open('prompt_definitions.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ 已删除 ENHANCED_BLUEPRINT_TEMPLATE 中的第8-13节")

def verify():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查第8-13节
    sections_found = []
    for i in range(8, 14):
        if f'## {i}.' in content:
            sections_found.append(str(i))
    
    if sections_found:
        print(f"❌ 仍有第{', '.join(sections_found)}节")
        return False
    
    print("✅ 验证通过：所有第8-13节已删除")
    return True

if __name__ == "__main__":
    fix_template()
    verify()
