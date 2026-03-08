# -*- coding: utf-8 -*-
"""
蓝图文件修复脚本 - 修正分卷命名和章节编号问题
"""

import re
import os
from typing import Tuple, Optional

# 正确的分卷映射（根据Novel_architecture.txt）
VOLUME_MAPPING = {
    (1, 80): {
        "volume": "第一卷",
        "name": "系统觉醒篇",
        "subacts": {
            (1, 27): "子幕1：觉醒触发",
            (28, 67): "子幕2：初试锋芒",
            (68, 80): "子幕3：声名鹊起"
        }
    },
    (81, 160): {
        "volume": "第二卷",
        "name": "宗门争霸篇",
        "subacts": {
            (81, 107): "子幕1：暗流涌动",
            (108, 147): "子幕2：群雄逐鹿",
            (148, 160): "子幕3：霸业初成"
        }
    },
    (161, 240): {
        "volume": "第三卷",
        "name": "复仇之路篇",
        "subacts": {
            (161, 187): "子幕1：真相初现",
            (188, 227): "子幕2：血海深仇",
            (228, 240): "子幕3：尘埃落定"
        }
    },
    (241, 320): {
        "volume": "第四卷",
        "name": "统一天下篇",
        "subacts": {
            (241, 267): "子幕1：势力雏形",
            (268, 307): "子幕2：纵横捭阖",
            (308, 320): "子幕3：天下归心"
        }
    },
    (321, 400): {
        "volume": "第五卷",
        "name": "飞升成仙篇",
        "subacts": {
            (321, 347): "子幕1：天劫将至",
            (348, 387): "子幕2：灭世浩劫",
            (388, 400): "子幕3：飞升仙界"
        }
    }
}


def get_correct_volume_info(chapter_num: int) -> Optional[dict]:
    """根据章节号获取正确的分卷信息"""
    for (start, end), info in VOLUME_MAPPING.items():
        if start <= chapter_num <= end:
            # 获取子幕信息
            subact = None
            for (sub_start, sub_end), subact_name in info["subacts"].items():
                if sub_start <= chapter_num <= sub_end:
                    subact = subact_name
                    break
            return {
                "volume": info["volume"],
                "name": info["name"],
                "subact": subact,
                "chapter": chapter_num
            }
    return None


def extract_chapter_number(text: str) -> Optional[int]:
    """从文本中提取章节号"""
    # 匹配 "第X章" 格式
    patterns = [
        r"###\s*\*\*第(\d+)章",  # ### **第X章
        r"第(\d+)章\s*-",  # 第X章 -
        r"第(\d+)章[：:]",  # 第X章：
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def fix_volume_label(line: str, chapter_num: int) -> str:
    """修正分卷标签"""
    if chapter_num is None:
        return line
    
    correct_info = get_correct_volume_info(chapter_num)
    if not correct_info:
        return line
    
    # 检测并修正"定位："行
    if "定位：" in line:
        # 构建正确的定位字符串
        correct_position = f"定位：{correct_info['volume']}：{correct_info['name']} - {correct_info['subact']} (第{chapter_num}章)"
        
        # 提取现有定位信息并替换
        old_pattern = r"定位：.*"
        if re.search(old_pattern, line):
            new_line = re.sub(old_pattern, correct_position, line)
            return new_line
    
    return line


def process_blueprint_file(input_path: str, output_path: str):
    """处理蓝图文件"""
    print(f"开始处理: {input_path}")
    
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"总行数: {len(lines)}")
    
    # 统计修复情况
    stats = {
        "total_lines": len(lines),
        "volume_fixes": 0,
        "chapters_found": 0,
        "errors": []
    }
    
    current_chapter = None
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # 尝试从章节标题行提取章节号
        chapter_num = extract_chapter_number(line)
        if chapter_num:
            current_chapter = chapter_num
            stats["chapters_found"] += 1
        
        # 修正分卷标签
        if current_chapter and "定位：" in line:
            original_line = line
            fixed_line = fix_volume_label(line, current_chapter)
            if fixed_line != original_line:
                stats["volume_fixes"] += 1
                if stats["volume_fixes"] <= 10:  # 只显示前10个修复
                    print(f"\n修复 #{stats['volume_fixes']} (第{current_chapter}章):")
                    print(f"  原: {original_line.strip()[:80]}...")
                    print(f"  新: {fixed_line.strip()[:80]}...")
            fixed_lines.append(fixed_line)
        else:
            fixed_lines.append(line)
    
    # 写入修复后的文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print(f"\n=== 修复完成 ===")
    print(f"总行数: {stats['total_lines']}")
    print(f"发现章节数: {stats['chapters_found']}")
    print(f"修复分卷标签数: {stats['volume_fixes']}")
    print(f"输出文件: {output_path}")
    
    return stats


def verify_fixes(file_path: str):
    """验证修复结果"""
    print(f"\n=== 验证修复结果 ===")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查常见错误是否还存在
    errors = []
    
    # 错误1: "第五卷：复仇之路篇"
    if "第五卷：复仇之路篇" in content:
        count = content.count("第五卷：复仇之路篇")
        errors.append(f"仍存在'第五卷：复仇之路篇': {count}处")
    
    # 检查正确的分卷名称
    correct_patterns = [
        ("第一卷：系统觉醒篇", 80),
        ("第二卷：宗门争霸篇", 80),
        ("第三卷：复仇之路篇", 80),
        ("第四卷：统一天下篇", 80),
        ("第五卷：飞升成仙篇", 80),
    ]
    
    for pattern, expected_min in correct_patterns:
        count = content.count(pattern)
        print(f"  {pattern}: {count}处")
    
    if errors:
        print("\n⚠️ 仍存在的错误:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ 所有已知错误已修复!")
    
    return len(errors) == 0


if __name__ == "__main__":
    # 设置路径
    base_dir = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj"
    input_file = os.path.join(base_dir, "Novel_directory.txt")
    output_file = os.path.join(base_dir, "Novel_directory_fixed.txt")
    
    # 执行修复
    stats = process_blueprint_file(input_file, output_file)
    
    # 验证修复结果
    success = verify_fixes(output_file)
    
    if success:
        print("\n=== 建议操作 ===")
        print("1. 检查 Novel_directory_fixed.txt 确认修复正确")
        print("2. 备份原文件: Novel_directory.txt -> Novel_directory_backup.txt")
        print("3. 替换: Novel_directory_fixed.txt -> Novel_directory.txt")
