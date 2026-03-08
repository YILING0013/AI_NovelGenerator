# fix_orphaned_template.py
# -*- coding: utf-8 -*-
"""
删除 prompt_definitions.py 中第1155-1315行的孤立模板（包含第8-13节）
"""

def fix_file():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 删除第1155-1315行（Python索引从0开始，所以是1154-1314）
    # 这段内容是孤立的模板，不属于任何变量
    new_lines = lines[:1154] + lines[1315:]
    
    with open('prompt_definitions.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✅ 已删除第1155-1315行（共{1315-1154}行）")
    print(f"   原文件行数: {len(lines)}")
    print(f"   新文件行数: {len(new_lines)}")

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
    
    # 检查7节格式
    required = ['## 1. 基础元信息', '## 2. 张力与冲突', '## 3. 匠心思维应用',
               '## 4. 伏笔与信息差', '## 5. 暧昧与修罗场', '## 6. 剧情精要', '## 7. 衔接设计']
    
    missing = []
    for section in required:
        if section not in content:
            missing.append(section)
    
    if missing:
        print(f"❌ 缺少: {missing}")
        return False
    
    print("✅ 验证通过：所有第8-13节已删除，7节格式完整")
    return True

if __name__ == "__main__":
    fix_file()
    verify()
