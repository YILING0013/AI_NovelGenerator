# fix_double_quotes.py
# -*- coding: utf-8 -*-
"""
修复 prompt_definitions.py 中残留的双引号问题
"""

def fix_file():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 查找连续的三个双引号（除了正常的字符串结束）
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 如果这一行是 """ 且不是字符串定义的开始，删除它
        if stripped == '"""':
            # 检查前一行是否也是 """（这种情况要删除一个）
            if i > 0 and new_lines and new_lines[-1].strip() == '"""':
                print(f"   删除第{i+1}行的重复三引号")
                i += 1
                continue
        
        new_lines.append(line)
        i += 1
    
    with open('prompt_definitions.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✅ 已修复双引号问题")

def verify():
    with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 检查是否有连续的 """
    consecutive_quotes = []
    for i in range(len(lines) - 1):
        if lines[i].strip() == '"""' and lines[i+1].strip() == '"""':
            consecutive_quotes.append(i + 1)
    
    if consecutive_quotes:
        print(f"❌ 仍有连续的三引号在第: {consecutive_quotes} 行")
        return False
    
    print("✅ 验证通过：没有连续的三引号")
    
    # 尝试导入模块验证语法
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("prompt_definitions", "prompt_definitions.py")
        if spec and spec.loader:
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        print("✅ 语法验证通过")
        return True
    except Exception as e:
        print(f"❌ 语法错误: {e}")
        return False

if __name__ == "__main__":
    fix_file()
    verify()
