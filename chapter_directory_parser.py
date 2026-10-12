# chapter_blueprint_parser.py
# -*- coding: utf-8 -*-
import re


_CHINESE_HEADER_PATTERN = re.compile(
    r"^第\s*(\d+)\s*章(?:\s*[-—–:：]\s*|\s+)?(.+?)?$"
)
_ENGLISH_HEADER_PATTERN = re.compile(
    r"^chapter\s+(\d+)(?:\s*[-—–:：]\s*|\s+)?(.+?)?$",
    re.IGNORECASE
)

_FIELD_ALIASES = (
    ("chapter_role", (r"本章定位", r"章节定位", r"chapter\s+role")),
    ("chapter_purpose", (r"核心作用", r"core\s+function", r"core\s+purpose")),
    ("suspense_level", (r"悬念密度", r"suspense\s+density")),
    ("foreshadowing", (r"伏笔操作", r"伏笔设计", r"foreshadowing(?:\s+design)?")),
    ("plot_twist_level", (r"认知颠覆(?:强度)?", r"转折程度", r"cognitive\s+subversion", r"twist\s+level")),
    ("chapter_summary", (r"本章简述", r"章节简述", r"chapter\s+summary")),
)
_FIELD_PATTERNS = [
    (
        key,
        re.compile(rf"^(?:{'|'.join(aliases)})\s*[:：]\s*(.*)$", re.IGNORECASE)
    )
    for key, aliases in _FIELD_ALIASES
]
_LINE_PREFIX_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*|>\s*|[-*+]\s+|\d+[.)、]\s*|[├└│╰╭─━┬┴┼]+\s*)+"
)
_WRAPPERS = (
    ("[", "]"),
    ("【", "】"),
    ("《", "》"),
    ("「", "」"),
    ("『", "』"),
    ("“", "”"),
    ('"', '"'),
    ("'", "'"),
)


def _strip_line_prefix(line: str) -> str:
    return _LINE_PREFIX_PATTERN.sub("", line.strip()).strip()


def _strip_wrapping_punctuation(text: str) -> str:
    text = text.strip()
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for left, right in _WRAPPERS:
            if text.startswith(left) and text.endswith(right):
                text = text[len(left):-len(right)].strip()
                changed = True
                break
    return text


def _new_chapter(chapter_number: int, chapter_title: str) -> dict:
    return {
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "chapter_role": "",
        "chapter_purpose": "",
        "suspense_level": "",
        "foreshadowing": "",
        "plot_twist_level": "",
        "chapter_summary": ""
    }


def _parse_chapter_header(line: str):
    normalized = _strip_line_prefix(line)
    for pattern in (_CHINESE_HEADER_PATTERN, _ENGLISH_HEADER_PATTERN):
        match = pattern.match(normalized)
        if match:
            chapter_number = int(match.group(1))
            chapter_title = _strip_wrapping_punctuation(match.group(2) or "")
            return chapter_number, chapter_title
    return None


def _parse_field_line(line: str):
    normalized = _strip_line_prefix(line).replace("**", "").strip()
    for key, pattern in _FIELD_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return key, _strip_wrapping_punctuation(match.group(1))
    return None


def parse_chapter_blueprint(blueprint_text: str):
    """
    解析整份章节蓝图文本，返回一个列表，每个元素是一个 dict：
    {
      "chapter_number": int,
      "chapter_title": str,
      "chapter_role": str,       # 本章定位
      "chapter_purpose": str,    # 核心作用
      "suspense_level": str,     # 悬念密度
      "foreshadowing": str,      # 伏笔操作
      "plot_twist_level": str,   # 认知颠覆
      "chapter_summary": str     # 本章简述
    }
    """
    results = []
    current_chapter = None

    for raw_line in (blueprint_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header = _parse_chapter_header(line)
        if header:
            if current_chapter:
                results.append(current_chapter)
            chapter_number, chapter_title = header
            current_chapter = _new_chapter(chapter_number, chapter_title)
            continue

        if not current_chapter:
            continue

        field = _parse_field_line(line)
        if field:
            key, value = field
            current_chapter[key] = value

    if current_chapter:
        results.append(current_chapter)

    # 按照 chapter_number 排序后返回
    results.sort(key=lambda x: x["chapter_number"])
    return results


def get_chapter_info_from_blueprint(blueprint_text: str, target_chapter_number: int):
    """
    在已经加载好的章节蓝图文本中，找到对应章号的结构化信息，返回一个 dict。
    若找不到则返回一个默认的结构。
    """
    all_chapters = parse_chapter_blueprint(blueprint_text)
    for ch in all_chapters:
        if ch["chapter_number"] == target_chapter_number:
            return ch
    # 默认返回
    return {
        "chapter_number": target_chapter_number,
        "chapter_title": f"第{target_chapter_number}章",
        "chapter_role": "",
        "chapter_purpose": "",
        "suspense_level": "",
        "foreshadowing": "",
        "plot_twist_level": "",
        "chapter_summary": ""
    }
