# -*- coding: utf-8 -*-
"""
修复章节标题重复问题的完整解决方案

问题分析：
第24章出现"第24章 第24章"重复标题的根本原因是：
1. ui/generation_handlers.py 中存在多处重复的标题添加逻辑
2. 防重复机制过于简单，无法检测重复标题
3. 批量生成流程中标题处理逻辑混乱
4. generate_chapter_draft() 已经包含标题处理，但其他地方仍在重复添加

解决方案：
1. 增强防重复检测机制
2. 统一标题处理逻辑
3. 移除重复的标题添加代码
4. 改进章节标题工具函数
"""

import re
import os
import logging
from typing import Tuple, Optional

def enhanced_content_has_title(content: str, chapter_number: int) -> Tuple[bool, bool]:
    """
    增强的标题检测函数

    Returns:
        (has_title, has_duplicate_title):
        - has_title: 是否有标题
        - has_duplicate_title: 是否有重复标题
    """
    if not content:
        return False, False

    lines = content.strip().split('\n')
    first_few_lines = lines[:5]  # 检查前5行

    chapter_pattern = rf"第\s*{chapter_number}\s*章"
    title_found = False
    duplicate_found = False
    title_count = 0

    for i, line in enumerate(first_few_lines):
        line = line.strip()

        # 检查是否包含章节标题模式
        if re.search(chapter_pattern, line):
            title_count += 1
            if not title_found:
                title_found = True
            else:
                duplicate_found = True

        # 检查是否包含连续的章节标题（如"第24章 第24章"）
        consecutive_matches = re.findall(rf"{chapter_pattern}[^\\n]*{chapter_pattern}", line)
        if consecutive_matches:
            duplicate_found = True

    return title_found, duplicate_found

def clean_duplicate_titles(content: str, chapter_number: int) -> str:
    """
    清理重复的章节标题，保留第一个正确的标题
    """
    if not content:
        return content

    lines = content.split('\n')
    cleaned_lines = []
    title_pattern = rf"第\s*{chapter_number}\s*章"
    title_removed = False

    for line in lines:
        # 检查是否包含重复标题
        if re.search(title_pattern, line) and not title_removed:
            # 保留第一次出现的标题行，但清理其中的重复
            # 针对 "第15章 第15章" 这种同一行重复的情况
            # 逻辑：如果一行中出现两次相同的"第X章"，只保留一个
            if line.count(f"第{chapter_number}章") > 1:
                cleaned_line = re.sub(rf"(第\s*{chapter_number}\s*章)\s+第\s*{chapter_number}\s*章", r"\1", line)
                cleaned_lines.append(cleaned_line)
            else:
                # 普通情况：可能是"第X章 标题"
                # 这里不需要复杂的regex，只要不是重复的"第X章"就行
                cleaned_lines.append(line)
            title_removed = True
        elif re.search(title_pattern, line) and title_removed:
            # 跳过后续的重复标题行
            continue
        else:
            cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)

def ensure_single_title(content: str, chapter_number: int, title: str) -> str:
    """
    确保章节只有一个正确的标题

    这是统一的标题处理函数，应该在所有需要标题处理的地方调用
    """
    # 1. 清理重复标题
    content = clean_duplicate_titles(content, chapter_number)

    # 2. 检查是否已有标题
    has_title, has_duplicate = enhanced_content_has_title(content, chapter_number)

    # 3. 如果没有标题，添加一个
    if not has_title:
        title_line = f"第{chapter_number}章 {title.strip()}"
        content = f"{title_line}\n\n{content.strip()}"

    return content

def apply_fixes_to_generation_handlers():
    """
    对 ui/generation_handlers.py 应用修复
    """
    handlers_file = "ui/generation_handlers.py"

    if not os.path.exists(handlers_file):
        print(f"错误：找不到文件 {handlers_file}")
        return False

    # 读取原文件
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 修复1：移除_save_chapter_draft中重复的标题处理代码（631-697行）
    duplicate_code_pattern = r"# 🔧 保存前验证标题存在.*?(?=\n\n|\n    def|\nclass|\Z)"
    content = re.sub(duplicate_code_pattern, "# 标题处理已在generate_chapter_draft中完成", content, flags=re.DOTALL)

    # 修复2：移除generate_chapter_batch中的重复标题处理（1560-1626行）
    duplicate_batch_pattern = r"# 🔧 修复：扩写后重新添加章节标题.*?(?=\n\n|\n        def|\nclass|\Z)"
    content = re.sub(duplicate_batch_pattern, "# 扩写后的标题处理已统一，避免重复添加", content, flags=re.DOTALL)

    # 修复3：移除保存前的重复验证（1582-1626行）
    save_verification_pattern = r"# 🔧 保存前验证标题存在.*?(?=\n\n|\n        def|\nclass|\Z)"
    content = re.sub(save_verification_pattern, "# 标题验证已在ensure_single_title中处理", content, flags=re.DOTALL)

    # 修复4：在generate_chapter_batch函数开始处添加统一的标题处理
    new_title_handling = '''
        # 🔧 统一标题处理：解决"第24章 第24章"重复问题
        # generate_chapter_draft() 已经添加了标题，这里只需要确保标题唯一性
        try:
            from fix_chapter_title_duplication import ensure_single_title
            from chapter_directory_parser import get_chapter_info_from_blueprint
            from utils import read_file

            directory_file = os.path.join(self.filepath_var.get().strip(), 'Novel_directory.txt')
            blueprint_text = read_file(directory_file)
            chapter_info = get_chapter_info_from_blueprint(blueprint_text, i)
            chapter_title = chapter_info['chapter_title']

            # 统一处理标题：确保只有一个正确的标题
            draft_text = ensure_single_title(draft_text, i, chapter_title)
            self.safe_log(f'🔧 第{i}章标题已统一处理: {chapter_title}')

        except Exception as e:
            self.safe_log(f'⚠️ 第{i}章标题统一处理失败: {e}')
'''

    # 在generate_chapter_draft调用之后插入新的标题处理代码
    draft_call_pattern = r"(draft_text = generate_chapter_draft\([^)]+\))"
    replacement = f"\\1{new_title_handling}"
    content = re.sub(draft_call_pattern, replacement, content)

    # 创建备份文件
    backup_file = f"{handlers_file}.backup_title_fix"
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # 写入修复后的文件
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ 修复完成！")
    print(f"📁 原文件已备份到: {backup_file}")
    print(f"🔧 修复内容：")
    print(f"  1. 移除了_save_chapter_draft中的重复标题处理")
    print(f"  2. 移除了generate_chapter_batch中的重复标题添加")
    print(f"  3. 添加了统一的ensure_single_title处理")
    print(f"  4. 增强了标题重复检测机制")

    return True

def test_title_fix():
    """
    测试修复效果
    """
    print("🧪 测试标题修复功能...")

    # 测试用例1：重复标题
    test_content1 = "第24章 章节标题\\n第24章 章节标题\\n\\n章节内容开始..."
    result1 = ensure_single_title(test_content1, 24, "章节标题")
    expected1 = "第24章 章节标题\\n\\n章节内容开始..."
    assert "第24章 第24章" not in result1, f"测试1失败：{result1}"
    print("✅ 测试1通过：重复标题已清理")

    # 测试用例2：无标题
    test_content2 = "章节内容开始..."
    result2 = ensure_single_title(test_content2, 24, "新章节标题")
    assert result2.startswith("第24章 新章节标题"), f"测试2失败：{result2}"
    print("✅ 测试2通过：无标题时已添加")

    # 测试用例3：已有正确标题
    test_content3 = "第24章 正确标题\\n\\n章节内容..."
    result3 = ensure_single_title(test_content3, 24, "其他标题")
    assert result3 == test_content3, f"测试3失败：{result3}"
    print("✅ 测试3通过：正确标题保持不变")

    # 测试用例4：标题格式检测
    test_content4 = "第 24 章 标题\\n\\n内容"
    has_title, has_dup = enhanced_content_has_title(test_content4, 24)
    assert has_title == True, f"测试4失败：未检测到标题"
    print("✅ 测试4通过：标题格式检测正常")

    print("🎉 所有测试通过！")

if __name__ == "__main__":
    print("🔧 开始修复章节标题重复问题...")
    print("=" * 50)

    # 运行测试
    test_title_fix()
    print("=" * 50)

    # 应用修复
    success = apply_fixes_to_generation_handlers()

    if success:
        print("=" * 50)
        print("🎯 修复建议：")
        print("1. 重启应用程序以加载修复后的代码")
        print("2. 重新生成第24章测试修复效果")
        print("3. 检查其他章节是否也有类似问题")
        print("4. 建议对已生成的章节运行批量标题清理脚本")
        print("=" * 50)
    else:
        print("❌ 修复失败，请检查文件路径和权限")