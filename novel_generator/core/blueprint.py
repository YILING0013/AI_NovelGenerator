# -*- coding: utf-8 -*-
"""
核心蓝图访问层 (v2.1: 使用search增强兼容性)
提供高效、统一的小说蓝图文件访问接口
使用索引机制实现懒加载，避免将整个大文件加载到内存
"""

import os
import re
from typing import Dict, Tuple, Generator


def _resolve_blueprint_path(project_path: str) -> str:
    """Resolve Novel_directory.txt across current and legacy project layouts."""
    primary = os.path.join(project_path, "Novel_directory.txt")
    candidates = [
        primary,
        os.path.join(project_path, "novel_directory.txt"),
        os.path.join(project_path, "wxhyj", "Novel_directory.txt"),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    try:
        for entry in sorted(os.listdir(project_path)):
            candidate = os.path.join(project_path, entry, "Novel_directory.txt")
            if os.path.exists(candidate):
                return candidate
    except OSError:
        pass

    return primary


class IndexedBlueprint:
    """
    索引化蓝图访问器
    Builds an in-memory index of chapter offsets, reading content on-demand.
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.blueprint_path = _resolve_blueprint_path(project_path)
        # index format: {chapter_num: (start_offset, length)}
        self._index: Dict[int, Tuple[int, int]] = {}
        self._initialized = False
        self._titles: Dict[int, str] = {}
        
    def _build_index(self):
        """构建文件索引（只扫描一次）"""
        if self._initialized:
            return
            
        if not os.path.exists(self.blueprint_path):
            self.blueprint_path = _resolve_blueprint_path(self.project_path)

        if not os.path.exists(self.blueprint_path):
            self._initialized = True
            return

        # 匹配模式：宽容模式，匹配行首可能包含空格、#、* 的 "第X章"
        # 支持多种格式："第1章)"、"第1章 - 标题"、"第1章 标题" 等
        pattern = re.compile(r'^[\s#*]*第(\d+)章[)\s\-：:]*(.*)') 
        
        current_chapter = None
        current_start = 0
        
        with open(self.blueprint_path, 'rb') as f:
            offset = 0
            for line in f:
                line_len = len(line)
                try:
                    # 尝试解码行首部分来判断是否是标题
                    # 增加解码缓冲区
                    decoded = line[:300].decode('utf-8', errors='ignore')
                    # 使用 search 查找匹配
                    match = pattern.search(decoded)
                    if match:
                        # 发现新章节，先结算上一个章节
                        if current_chapter is not None:
                            start_byte = self._index[current_chapter][0]
                            # 长度 = 当前标题行之前的总字节数 - 起始字节数
                            length = offset - start_byte
                            self._index[current_chapter] = (start_byte, length)
                        
                        # 记录新章节
                        c_num = int(match.group(1))
                        # 清理标题
                        raw_title = match.group(2)
                        title = raw_title.replace('*', '').strip()
                        if title.startswith('- '): title = title[2:]
                        if title.startswith(': '): title = title[2:]
                        
                        self._titles[c_num] = title
                        
                        current_chapter = c_num
                        # 内容从标题行开始（包含标题）
                        self._index[c_num] = (offset, 0)
                        
                except Exception:
                    pass
                
                offset += line_len
            
            # 结算最后一个章节
            if current_chapter is not None:
                start_byte = self._index[current_chapter][0]
                length = offset - start_byte
                self._index[current_chapter] = (start_byte, length)
                
        self._initialized = True

    def get_chapter_content(self, chapter_num: int) -> str:
        """获取指定章节内容（按需读取）"""
        self._build_index()
        
        if chapter_num not in self._index:
            return ""
            
        offset, length = self._index[chapter_num]
        
        with open(self.blueprint_path, 'rb') as f:
            f.seek(offset)
            content_bytes = f.read(length)
            return content_bytes.decode('utf-8', errors='ignore')

    def get_chapter_title(self, chapter_num: int) -> str:
        """获取章节标题"""
        self._build_index()
        return self._titles.get(chapter_num, "")

    def chapter_exists(self, chapter_num: int) -> bool:
        """检查章节是否存在"""
        self._build_index()
        return chapter_num in self._index

    def iter_chapters(self) -> Generator[int, None, None]:
        """迭代所有存在的章节号"""
        self._build_index()
        for num in sorted(self._index.keys()):
            yield num

    @property
    def total_chapters(self) -> int:
        self._build_index()
        return len(self._index)


# 全局缓存实例
_blueprint_instances = {}

def get_blueprint(project_path: str) -> IndexedBlueprint:
    cache_key = os.path.abspath(project_path)
    if cache_key not in _blueprint_instances:
        _blueprint_instances[cache_key] = IndexedBlueprint(project_path)
    # 如果路径相同但index为空（可能初始化失败），可以尝试重新load？
    # 目前单例模式如果参数没变就返回同一个对象，对象内部状态保持。
    return _blueprint_instances[cache_key]
