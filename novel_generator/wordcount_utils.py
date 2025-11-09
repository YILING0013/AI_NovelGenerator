# novel_generator/wordcount_utils.py
# -*- coding: utf-8 -*-
"""
统一的字数统计工具
"""

import re
import os

def count_chapter_words(text_or_path, count_type='chinese'):
    """
    统计章节字数的标准函数

    Args:
        text_or_path: 文本内容或文件路径
        count_type: 统计类型
            - 'chinese': 仅统计中文字符（推荐）
            - 'all': 统计所有字符（不含行号）
            - 'file': 文件大小（字节）

    Returns:
        dict: 包含各种统计结果
    """

    # 如果是文件路径，读取内容
    if isinstance(text_or_path, str) and os.path.exists(text_or_path):
        with open(text_or_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = text_or_path

    # 去除行号前缀
    lines = content.split('\n')
    clean_lines = []
    for line in lines:
        clean_line = re.sub(r'^\s*\d+→\s*', '', line)
        clean_lines.append(clean_line)

    clean_text = '\n'.join(clean_lines).strip()

    # 统计各种字数
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_text))
    all_chars = len(clean_text.replace('\n', ''))

    # 如果是文件路径，获取文件大小
    file_size = 0
    if isinstance(text_or_path, str) and os.path.exists(text_or_path):
        file_size = os.path.getsize(text_or_path)

    return {
        'chinese_chars': chinese_chars,      # 中文字符数（推荐标准）
        'all_chars': all_chars,             # 所有字符数
        'file_size': file_size,             # 文件大小
        'lines_count': len(clean_lines),     # 行数
        'clean_text': clean_text             # 清理后的文本
    }

def should_auto_enrich(content_or_path, target_words, min_words, auto_enrich_enabled):
    """
    判断是否应该触发自动扩写

    Args:
        content_or_path: 章节内容或文件路径
        target_words: 期望字数
        min_words: 最低字数
        auto_enrich_enabled: 是否启用自动扩写

    Returns:
        dict: 判断结果和建议
    """

    if not auto_enrich_enabled:
        return {
            'should_enrich': False,
            'reason': '自动扩写未启用',
            'current_words': 0,
            'target_ratio': 0
        }

    stats = count_chapter_words(content_or_path)
    current_words = stats['chinese_chars']

    # 基于中文字符数的智能扩写逻辑
    target_threshold = 0.8 * target_words  # 期望字数的80%
    min_threshold = 0.7 * min_words       # 最低字数的70%

    should_enrich = False
    reason = ""

    if current_words < min_threshold:
        should_enrich = True
        reason = f"字数({current_words})低于最低字数({min_words})的70%"
    elif current_words < target_threshold:
        should_enrich = True
        reason = f"字数({current_words})低于期望字数({target_words})的80%"
    else:
        reason = f"字数({current_words})符合要求"

    target_ratio = current_words / target_words if target_words > 0 else 0

    return {
        'should_enrich': should_enrich,
        'reason': reason,
        'current_words': current_words,
        'target_words': target_words,
        'target_ratio': target_ratio,
        'stats': stats
    }

def format_word_count_display(stats):
    """
    格式化字数显示信息

    Args:
        stats: count_chapter_words返回的统计结果

    Returns:
        str: 格式化的显示信息
    """

    return f"{stats['chinese_chars']}中文字符 (总计{stats['all_chars']}字符)"

def analyze_chapter_quality(content_or_path, target_words):
    """
    分析章节质量并提供建议

    Args:
        content_or_path: 章节内容或文件路径
        target_words: 期望字数

    Returns:
        dict: 质量分析结果
    """

    stats = count_chapter_words(content_or_path)
    current_words = stats['chinese_chars']
    ratio = current_words / target_words if target_words > 0 else 0

    # 质量评级
    if ratio >= 0.9:
        quality = "优秀"
        suggestion = "字数充足，质量良好"
    elif ratio >= 0.7:
        quality = "良好"
        suggestion = "字数基本达标"
    elif ratio >= 0.5:
        quality = "一般"
        suggestion = "建议扩写或补充内容"
    else:
        quality = "不足"
        suggestion = "字数明显不足，强烈建议扩写"

    return {
        'quality': quality,
        'ratio': ratio,
        'current_words': current_words,
        'target_words': target_words,
        'suggestion': suggestion,
        'stats': stats
    }