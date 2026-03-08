# blueprint_strict_requirements_fix.py
# -*- coding: utf-8 -*-
"""
简化 strict_requirements，消除重复警告
"""

def fix_strict_requirements():
    """修复 strict_requirements 部分"""

    print("=" * 60)
    print("简化 strict_requirements")
    print("=" * 60)

    file_path = "novel_generator/blueprint.py"
    backup_path = f"{file_path}.strict_req_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 1. 备份
    print(f"1. 备份文件到: {backup_path}")
    import shutil
    from datetime import datetime
    shutil.copy2(file_path, backup_path)

    # 2. 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 3. 新的简化的 strict_requirements
    new_strict_requirements = """        strict_requirements = f\"\"\"
🚨【绝对强制性要求】🚨

1. 格式规范（严格执行）：

{BLUEPRINT_FORMAT_V3}

2. 完整性铁律：

   - 每章必须包含全部 7 个节
   - 所有 7 个节都不能省略
   - 如果某节不涉及，填写"不涉及"

3. 批次要求：

   - 本次生成第{start_chapter}章到第{end_chapter}章（共{end_chapter - start_chapter + 1}章）
   - 严格按顺序生成，不得跳跃或重复
   - 每章必须完整独立，不得混入其他章节

4. 禁止事项：

   - 禁止任何形式的省略（包括但不限于"..."、"略"等）
   - 禁止重复生成同一章节
   - 禁止在"基础元信息"中重复写章节标题
   - 禁止在正文中引用具体章节号（用"本章"或"后续章节"代替）

5. 字数要求：

   - 每章字数目标：3000-5000 字
   - 确保内容充实详细

\"\"\"
"""

    # 4. 查找并替换
    old_pattern = 'strict_requirements = f"""'
    if old_pattern in content:
        print("2. 找到 strict_requirements，开始替换")
        
        # 找到结束位置
        end_idx = content.find('"""', content.find(old_pattern) + 100)
        if end_idx == -1:
            print("   警告：找不到结束位置，使用默认值")
            end_idx = content.find('\n\n        return prompt_header + few_shot_example + strict_requirements')
            if end_idx == -1:
                print("   错误：无法找到替换位置")
                return False

        # 执行替换
        start_idx = content.find(old_pattern)
        content = content[:start_idx] + new_strict_requirements + content[end_idx + len('"""'):]
        
        print("3. strict_requirements 已简化")
    else:
        print("2. 警告：未找到 strict_requirements 定义")
        return False

    # 5. 写入文件
    print(f"4. 写入修复后的文件")
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ strict_requirements 修复完成")
    return True


if __name__ == "__main__":
    from datetime import datetime
    
    # 需要先导入 BLUEPRINT_FORMAT_V3
    try:
        # 先检查是否已修复
        with open('prompt_definitions.py', 'r', encoding='utf-8') as f:
            if 'BLUEPRINT_FORMAT_V3' in f.read():
                print("✅ BLUEPRINT_FORMAT_V3 已存在")
                # 继续修复 strict_requirements
                fix_strict_requirements()
            else:
                print("❌ BLUEPRINT_FORMAT_V3 不存在，请先运行 blueprint_format_fix.py")
    except FileNotFoundError:
        print("❌ 文件不存在，请先运行 blueprint_format_fix.py")
    except Exception as e:
        print(f"❌ 修复失败: {e}")
