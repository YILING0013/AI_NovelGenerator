# novel_generator/chapter_utils.py
# -*- coding: utf-8 -*-
"""
统一的章节解析工具模块

本模块整合了分散在多个文件中的章节解析逻辑，解决代码重复问题。
提供统一的章节标题、章节内容提取和章节信息解析功能。

主要功能：
1. extract_chapter_number() - 从文本中提取章节号
2. extract_chapter_title() - 从文本中提取章节标题
3. split_chapters() - 将全文按章节分割
4. parse_chapter_header() - 解析章节标题行

作者: AI架构重构团队
创建日期: 2026-01-04
"""

import re
from typing import List, Optional, Dict, Any, Tuple


# ============================================
# 常量定义
# ============================================

# 章节标题模式集合（支持多种格式）
CHAPTER_PATTERNS = {
    # 格式1: ### **第1章 - 标题** 或 ### **第1章 - [标题]**
    'markdown_bold': re.compile(r'^###\s*\*{0,2}\*第\s*(\d+)\s*章\s*[-–—]\s*(.*?)\s*\*{0,2}\*?$'),

    # 格式2: 第1章 - 标题
    'simple': re.compile(r'^第\s*(\d+)\s*章\s*[-–—]\s*(.*?)$'),

    # 格式3: 第1章) (无标题格式)
    'no_title': re.compile(r'^第\s*(\d+)\s*章\s*\)?$'),

    # 格式4: 第1章 标题 (无分隔符)
    'no_separator': re.compile(r'^第\s*(\d+)\s*章\s*(.*?)$'),

    # 格式5: 第1章][标题] (方括号格式)
    'brackets': re.compile(r'^第\s*(\d+)\s*章\]\s*\[?(.*?)\]?$'),

    # 验证模式：任何包含"第X章"的行
    'generic': re.compile(r'^[#*\s]*第\s*(\d+)\s*章')
}


# ============================================
# 核心工具函数
# ============================================

def extract_chapter_number(text: str) -> Optional[int]:
    """
    从文本中提取章节号

    支持多种格式：
    - "### **第1章 - 标题**" -> 1
    - "第1章 - 标题" -> 1
    - "第1章)" -> 1
    - "第1章][标题]" -> 1

    Args:
        text: 可能包含章节标题的文本行

    Returns:
        章节号，如果未找到则返回 None

    Examples:
        >>> extract_chapter_number("第1章 - 开篇")
        1
        >>> extract_chapter_number("### **第10章 - 高潮")
        10
        >>> extract_chapter_number("无效文本")
        None
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # 尝试所有模式
    for pattern_name, pattern in CHAPTER_PATTERNS.items():
        if pattern_name == 'generic':
            continue  # generic 用作最后的后备

        match = pattern.match(text)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue

    # 如果所有特定模式都失败，尝试通用模式
    generic_match = CHAPTER_PATTERNS['generic'].search(text)
    if generic_match:
        try:
            return int(generic_match.group(1))
        except (ValueError, IndexError):
            pass

    return None


def extract_chapter_title(text: str) -> str:
    """
    从章节标题行中提取标题内容

    Args:
        text: 章节标题行（如 "第1章 - 开篇"）

    Returns:
        章节标题，如果无标题则返回空字符串

    Examples:
        >>> extract_chapter_title("第1章 - 风雪夜的转折点")
        '风雪夜的转折点'
        >>> extract_chapter_title("第1章")
        ''
        >>> extract_chapter_title("### **第1章 - [开篇]**")
        '开篇'
    """
    if not text or not text.strip():
        return ""

    text = text.strip()

    # 尝试从各格式中提取标题
    for pattern in [CHAPTER_PATTERNS['markdown_bold'],
                    CHAPTER_PATTERNS['simple'],
                    CHAPTER_PATTERNS['brackets']]:
        match = pattern.match(text)
        if match and len(match.groups()) >= 2:
            title = match.group(2).strip()
            # 先移除外层方括号（如 [开篇] -> 开篇）
            title = re.sub(r'^\[([\s\S]*)\]$', r'\1', title)
            # 再移除可能的 Markdown 符号
            title = re.sub(r'^\*+|\*+$', '', title.strip())
            return title if title else ""

    return ""


def split_chapters_by_header(content: str, min_chapter: int = 1,
                             max_chapter: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    将内容按章节标题分割成块

    Args:
        content: 完整的章节蓝图文本
        min_chapter: 最小章节号（默认1）
        max_chapter: 最大章节号（None表示无限制）

    Returns:
        章节块列表，每个元素包含：
        {
            'chapter_number': int,
            'title': str,
            'header_line': str,
            'content_start': int,
            'content_end': int
        }
    """
    if not content:
        return []

    lines = content.splitlines()
    chapters = []
    current_chapter = None

    for line_num, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        # 检查是否是章节标题行
        chapter_num = extract_chapter_number(stripped_line)

        if chapter_num is not None:
            # 检查章节号是否在范围内
            if chapter_num < min_chapter:
                continue
            if max_chapter is not None and chapter_num > max_chapter:
                continue

            # 保存上一章节的内容结束位置
            if current_chapter is not None:
                current_chapter['content_end'] = line_num

            # 创建新章节
            title = extract_chapter_title(stripped_line)
            chapters.append({
                'chapter_number': chapter_num,
                'title': title,
                'header_line': stripped_line,
                'content_start': line_num + 1,
                'content_end': len(lines)
            })
            current_chapter = chapters[-1]
        elif current_chapter is not None:
            # 当前章节继续中
            pass

    return chapters


def extract_single_chapter(content: str, chapter_num: int) -> Optional[str]:
    """
    从完整内容中提取指定章节的内容

    Args:
        content: 完整的章节蓝图文本
        chapter_num: 要提取的章节号

    Returns:
        指定章节的内容文本，如果未找到则返回 None

    Examples:
        >>> content = "第1章 - 开篇\\n内容...\\n第2章 - 继续\\n更多内容..."
        >>> extract_single_chapter(content, 1)
        '第1章 - 开篇\\n内容...'
    """
    chapters = split_chapters_by_header(content, chapter_num, chapter_num)

    if not chapters:
        return None

    chapter = chapters[0]
    lines = content.splitlines()

    # 提取从 header_line 到下一章之前的所有内容
    start = chapter['content_start']
    end = chapter['content_end']

    # 重新组合章节内容
    chapter_lines = [chapter['header_line']] + lines[start:end]
    return '\n'.join(chapter_lines)


def get_chapter_info_header(chapter_content: str) -> Dict[str, Any]:
    """
    从章节内容中提取结构化信息（仅解析头部信息）

    Args:
        chapter_content: 单个章节的完整内容

    Returns:
        包含章节信息的字典：
        {
            'chapter_number': int,
            'chapter_title': str,
            'raw_header': str,
            'fields': Dict[str, str]  # 提取的字段值
        }
    """
    if not chapter_content:
        return {}

    lines = chapter_content.splitlines()
    if not lines:
        return {}

    # 第一行应该是章节标题
    header_line = lines[0].strip()
    chapter_num = extract_chapter_number(header_line)
    chapter_title = extract_chapter_title(header_line)

    # 解析后续行中的字段
    fields = {}
    for line in lines[1:]:
        stripped = line.strip()
        # 跳过空行
        if not stripped:
            continue
        # 遇到非字段行，停止解析
        if stripped[0] not in ('*', '·', '-'):
            # 但要兼容新格式的 "## X. 标题" 模式
            if stripped.startswith('## '):
                # 这是新格式的子标题，继续解析
                pass
            else:
                break

        # 提取字段名和值
        if ':' in stripped or '：' in stripped:
            if ':' in stripped:
                key, value = stripped.split(':', 1)
            else:
                key, value = stripped.split('：', 1)

            key = key.strip('*·- ')
            value = value.strip()

            if key and value:
                fields[key] = value

    return {
        'chapter_number': chapter_num or 0,
        'chapter_title': chapter_title,
        'raw_header': header_line,
        'fields': fields
    }


def validate_chapter_number(content: str, expected_chapter: int) -> bool:
    """
    验证内容是否包含预期的章节号

    Args:
        content: 要验证的内容
        expected_chapter: 期望的章节号

    Returns:
        如果内容包含预期章节号则返回 True
    """
    if not content:
        return False

    # 检查章节号是否存在
    pattern = re.compile(r'第\s*' + str(expected_chapter) + r'\s*章')
    return bool(pattern.search(content))


def get_next_chapter_number(content: str) -> Optional[int]:
    """
    从内容中获取下一个章节号

    用于确定续写时应从哪一章开始。

    Args:
        content: 完整的章节蓝图文本

    Returns:
        最后的章节号 + 1，如果没有章节则返回 1
    """
    if not content:
        return 1

    chapters = split_chapters_by_header(content)
    if not chapters:
        return 1

    last_chapter = chapters[-1]
    return last_chapter['chapter_number'] + 1


# ============================================
# 便捷函数
# ============================================

def parse_chapter_range(content: str, start: int = 1, end: Optional[int] = None
                      ) -> Dict[int, str]:
    """
    解析指定范围的章节

    Args:
        content: 完整的章节蓝图文本
        start: 起始章节号（包含）
        end: 结束章节号（包含），None 表示到最后

    Returns:
        字典，键为章节号，值为章节内容
    """
    result = {}
    chapters = split_chapters_by_header(content, start, end)

    for chapter_info in chapters:
        ch_num = chapter_info['chapter_number']
        result[ch_num] = extract_single_chapter(content, ch_num)

    return result


def count_chapters(content: str) -> int:
    """
    统计内容中的章节数量

    Args:
        content: 章节蓝图文本

    Returns:
        章节总数
    """
    return len(split_chapters_by_header(content))


# ============================================
# 测试代码
# ============================================

if __name__ == "__main__":
    # 简单测试
    test_content = """
第1章 - 风雪夜的转折点

## 1. 基础元信息
*   **章节**：第 1 章 - 风雪夜的转折点
*   **定位**：第 1 卷 瓷骨道心 - 子幕 1 破碎的开端

第2章 - 洞悉本源

## 1. 基础元信息
*   **章节**：第 2 章 - 洞悉本源
"""

    print(f"章节数量: {count_chapters(test_content)}")
    print(f"下一章节: {get_next_chapter_number(test_content)}")
    print(f"第1章标题: {extract_chapter_title('第1章 - 风雪夜的转折点')}")
