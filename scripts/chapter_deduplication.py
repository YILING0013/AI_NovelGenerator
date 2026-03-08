# chapter_deduplication.py
# -*- coding: utf-8 -*-
"""
章节交叉去重检测模块
用于检测相邻章节间的内容重复并提供修正建议
"""

from difflib import SequenceMatcher
from typing import List, Tuple, Optional
import re


class ChapterDeduplicationDetector:
    """章节去重检测器"""
    
    def __init__(self, min_overlap_length: int = 100, similarity_threshold: float = 0.85):
        """
        初始化去重检测器
        
        Args:
            min_overlap_length: 触发重复警告的最小字符数
            similarity_threshold: 相似度阈值(0-1),超过此值视为重复
        """
        self.min_overlap_length = min_overlap_length
        self.similarity_threshold = similarity_threshold
    
    def find_overlaps(self, text1: str, text2: str) -> List[Tuple[int, int, int, int, str]]:
        """
        查找两段文本间的重复部分
        
        Args:
            text1: 第一段文本(前章)
            text2: 第二段文本(后章)
            
        Returns:
            重复段落列表,每项为(text1_start, text1_end, text2_start, text2_end, overlap_text)
        """
        overlaps = []
        
        # 使用滑动窗口检测重复
        # 从后章末尾往前找,因为重复通常出现在章节衔接处
        text1_end = text1[-2000:] if len(text1) > 2000 else text1  # 只检查前章末尾2000字
        text2_start = text2[:2000] if len(text2) > 2000 else text2  # 只检查后章开头2000字
        
        # 使用SequenceMatcher查找最长公共子串
        matcher = SequenceMatcher(None, text1_end, text2_start)
        matching_blocks = matcher.get_matching_blocks()
        
        for match in matching_blocks:
            i, j, size = match.a, match.b, match.size
            
            # 只关注长度超过阈值的匹配
            if size >= self.min_overlap_length:
                overlap_text = text1_end[i:i+size]
                
                # 计算相似度(考虑标点空格)
                similarity = self._calculate_similarity(overlap_text, text2_start[j:j+size])
                
                if similarity >= self.similarity_threshold:
                    # 计算在原文本中的位置
                    text1_start_pos = len(text1) - len(text1_end) + i
                    text1_end_pos = text1_start_pos + size
                    
                    overlaps.append((
                        text1_start_pos,
                        text1_end_pos,
                        j,
                        j + size,
                        overlap_text
                    ))
        
        return overlaps
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        # 移除空白字符后比较
        clean1 = re.sub(r'\s+', '', text1)
        clean2 = re.sub(r'\s+', '', text2)
        
        matcher = SequenceMatcher(None, clean1, clean2)
        return matcher.ratio()
    
    def check_cross_chapter_overlap(
        self, 
        current_chapter: str, 
        previous_chapter: Optional[str]
    ) -> dict:
        """
        检测当前章节与前一章节的重复
        
        Args:
            current_chapter: 当前章节内容
            previous_chapter: 前一章节内容(可选)
            
        Returns:
            检测结果字典
        """
        result = {
            'has_overlap': False,
            'overlap_count': 0,
            'overlaps': [],
            'total_overlap_chars': 0,
            'suggestions': []
        }
        
        if not previous_chapter:
            return result
        
        # 查找重复
        overlaps = self.find_overlaps(previous_chapter, current_chapter)
        
        if overlaps:
            result['has_overlap'] = True
            result['overlap_count'] = len(overlaps)
            
            for prev_start, prev_end, curr_start, curr_end, overlap_text in overlaps:
                overlap_info = {
                    'previous_chapter_range': (prev_start, prev_end),
                    'current_chapter_range': (curr_start, curr_end),
                    'overlap_text': overlap_text[:200] + '...' if len(overlap_text) > 200 else overlap_text,
                    'length': len(overlap_text)
                }
                result['overlaps'].append(overlap_info)
                result['total_overlap_chars'] += len(overlap_text)
            
            # 生成修复建议
            result['suggestions'] = self._generate_fix_suggestions(overlaps, current_chapter)
        
        return result
    
    def _generate_fix_suggestions(self, overlaps: List, current_chapter: str) -> List[str]:
        """生成修复建议"""
        suggestions = []
        
        for _, _, curr_start, curr_end, overlap_text in overlaps:
            # 建议删除重复部分
            if curr_start < 500:  # 如果重复出现在章节开头
                suggestions.append(
                    f"建议删除当前章节开头的重复内容({len(overlap_text)}字): "
                    f"'{overlap_text[:50]}...'"
                )
            else:
                suggestions.append(
                    f"发现内容重复({len(overlap_text)}字),位置: {curr_start}-{curr_end}"
                )
        
        return suggestions
    
    def auto_fix_overlap(self, current_chapter: str, overlap_info: dict) -> str:
        """
        自动修复重复内容
        
        Args:
            current_chapter: 当前章节内容
            overlap_info: 重复检测结果
            
        Returns:
            修复后的章节内容
        """
        if not overlap_info['has_overlap']:
            return current_chapter
        
        # 从后往前删除重复部分,避免位置偏移
        fixed_content = current_chapter
        overlaps_sorted = sorted(
            overlap_info['overlaps'],
            key=lambda x: x['current_chapter_range'][0],
            reverse=True
        )
        
        for overlap in overlaps_sorted:
            start, end = overlap['current_chapter_range']
            
            # 只删除开头1500字内的重复(通常是章节衔接重复)
            if start < 1500:
                fixed_content = fixed_content[:start] + fixed_content[end:]
        
        return fixed_content


def create_deduplication_detector(
    min_overlap_length: int = 100,
    similarity_threshold: float = 0.85
) -> ChapterDeduplicationDetector:
    """创建去重检测器"""
    return ChapterDeduplicationDetector(min_overlap_length, similarity_threshold)


# 使用示例
if __name__ == "__main__":
    detector = create_deduplication_detector(min_overlap_length=100)
    
    # 模拟测试
    chapter1 = "前文内容" * 100 + "重复段落内容" * 50
    chapter2 = "重复段落内容" * 50 + "后文内容" * 100
    
    result = detector.check_cross_chapter_overlap(chapter2, chapter1)
    
    if result['has_overlap']:
        print(f"发现{result['overlap_count']}处重复,共{result['total_overlap_chars']}字")
        for suggestion in result['suggestions']:
            print(f"  - {suggestion}")
        
        # 自动修复
        fixed = detector.auto_fix_overlap(chapter2, result)
        print(f"\n修复后字数: {len(fixed)} (原: {len(chapter2)})")
