#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
章节目录去重清理脚本
保留每个章节号的最后一个版本（假设最后的版本是最新的）
"""

import re
import sys
from pathlib import Path
from collections import OrderedDict

def deduplicate_novel_directory(file_path: str) -> dict:
    """
    去重章节目录，保留每个章节号的最后一个版本
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 使用正则按 "第X章" 分割内容
    chapter_pattern = r'^(第\d+章\s*[-—]?\s*.*?)(?=^第\d+章|\Z)'
    matches = re.findall(chapter_pattern, content, re.MULTILINE | re.DOTALL)
    
    print(f"原始章节条目数: {len(matches)}")
    
    # 使用 OrderedDict 保留每个章节号的最后一个版本
    chapters = OrderedDict()
    
    for section in matches:
        section = section.strip()
        if not section:
            continue
        
        match = re.search(r'第(\d+)章', section)
        if match:
            chapter_number = int(match.group(1))
            # 覆盖，保留最后出现的版本
            chapters[chapter_number] = section
    
    print(f"去重后唯一章节数: {len(chapters)}")
    
    # 按章节号排序
    sorted_chapters = sorted(chapters.items(), key=lambda x: x[0])
    
    # 重建内容
    new_content = "\n\n".join([ch[1] for ch in sorted_chapters])
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"已保存去重后的目录文件")
    
    return {
        'original_count': len(matches),
        'unique_count': len(chapters),
        'removed': len(matches) - len(chapters)
    }

if __name__ == "__main__":
    file_path = Path(__file__).parent.parent / "wxhyj" / "Novel_directory.txt"
    
    if not file_path.exists():
        print(f"文件不存在: {file_path}")
        sys.exit(1)
    
    result = deduplicate_novel_directory(str(file_path))
    print(f"\n清理完成:")
    print(f"  - 原始条目: {result['original_count']}")
    print(f"  - 保留条目: {result['unique_count']}")
    print(f"  - 删除重复: {result['removed']}")
