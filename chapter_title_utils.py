# -*- coding: utf-8 -*-
"""
章节标题工具函数
提供章节标题的清理、格式化和处理功能
"""

def clean_chapter_title(title: str) -> str:
    """
    清理章节标题，去除格式符号

    Args:
        title: 原始章节标题

    Returns:
        清理后的章节标题
    """
    if not title:
        return title

    # 去除首尾空白
    title = title.strip()

    # 去除常见的Markdown格式符号
    title = title.rstrip('**').rstrip('*').strip()  # 去除末尾的**
    title = title.lstrip('**').lstrip('*').strip()  # 去除开头的**

    # 去除可能的其他格式符号
    title = title.rstrip('【】】').strip()
    title = title.lstrip('【【】').strip()

    return title

def format_chapter_title_line(chapter_number: int, title: str) -> str:
    """
    格式化章节标题行

    Args:
        chapter_number: 章节编号
        title: 章节标题

    Returns:
        格式化后的章节标题行，例如: "第1章 废柴之死，系统新生"
    """
    cleaned_title = clean_chapter_title(title)
    return f"第{chapter_number}章 {cleaned_title}"

def content_already_has_title(content: str, chapter_number: int) -> bool:
    """
    检查内容是否已经包含章节标题

    Args:
        content: 章节内容
        chapter_number: 章节编号

    Returns:
        如果内容已经包含标题返回True，否则返回False
    """
    import re

    if not content:
        return False

    # 使用增强的检测功能
    try:
        from fix_chapter_title_duplication import enhanced_content_has_title
        has_title, _ = enhanced_content_has_title(content, chapter_number)
        return has_title
    except ImportError:
        # 回退到简单检测
        content_stripped = content.strip()
        # 支持更多格式的标题检测
        patterns = [
            f"第{chapter_number}章",
            f"第 {chapter_number} 章",
            f"第{chapter_number} 章",
            f"第 {chapter_number}章"
        ]

        for pattern in patterns:
            if content_stripped.startswith(pattern):
                return True
        return False

def add_chapter_title_if_missing(content: str, chapter_number: int, title: str) -> str:
    """
    如果章节内容没有标题，则添加标题行

    Args:
        content: 章节内容
        chapter_number: 章节编号
        title: 章节标题

    Returns:
        带标题的章节内容
    """
    # 使用增强的标题处理
    try:
        from fix_chapter_title_duplication import ensure_single_title
        return ensure_single_title(content, chapter_number, title)
    except ImportError:
        # 回退到原始逻辑
        if content_already_has_title(content, chapter_number):
            return content

        title_line = format_chapter_title_line(chapter_number, title)
        return f"{title_line}\n\n{content.strip()}"

def check_duplicate_titles(content: str, chapter_number: int) -> bool:
    """
    检查是否存在重复的章节标题

    Args:
        content: 章节内容
        chapter_number: 章节编号

    Returns:
        如果存在重复标题返回True，否则返回False
    """
    try:
        from fix_chapter_title_duplication import enhanced_content_has_title
        _, has_duplicate = enhanced_content_has_title(content, chapter_number)
        return has_duplicate
    except ImportError:
        # 简单的重复检测
        import re
        pattern = f"第{chapter_number}章"
        matches = re.findall(pattern, content)
        return len(matches) > 1