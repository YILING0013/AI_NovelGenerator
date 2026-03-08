# -*- coding: utf-8 -*-
"""
内容重复检测器 (P2)
检测相邻章节之间的内容重复
"""

import re
from typing import Dict, List, Set, Tuple
from .base import BaseValidator


class DuplicateDetector(BaseValidator):
    """检测章节间内容重复"""
    
    name = "duplicate_detector"
    
    # 需要检查重复的关键字段
    KEY_FIELDS = [
        "关键对话",
        "情感记忆点",
        "经典台词",
        "关键场景",
    ]
    
    # 相似度阈值
    SIMILARITY_THRESHOLD = 0.7
    
    def _extract_key_content(self, content: str) -> Set[str]:
        """提取关键内容片段"""
        key_parts = set()
        
        for field in self.KEY_FIELDS:
            # 尝试提取字段内容
            pattern = rf'{field}[：:]\s*(.+?)(?=\n【|\n\*\*|$)'
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                # 清理并分割为句子
                sentences = re.split(r'[。！？\n]', match)
                for s in sentences:
                    s = s.strip()
                    if len(s) > 10:  # 忽略太短的句子
                        key_parts.add(s)
        
        return key_parts
    
    def _calculate_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """计算两个集合的Jaccard相似度"""
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def compare_chapters(self, ch1_num: int, ch2_num: int) -> Dict:
        """
        比较两个章节的相似度
        
        Returns:
            {
                "similarity": float (0-1),
                "is_duplicate": bool,
                "common_parts": [str, ...],
            }
        """
        content1 = self.context.blueprint.get_chapter_content(ch1_num)
        content2 = self.context.blueprint.get_chapter_content(ch2_num)
        
        if not content1 or not content2:
            return {"similarity": 0.0, "is_duplicate": False, "common_parts": []}
        
        parts1 = self._extract_key_content(content1)
        parts2 = self._extract_key_content(content2)
        
        similarity = self._calculate_similarity(parts1, parts2)
        common = list(parts1 & parts2)
        
        return {
            "similarity": similarity,
            "is_duplicate": similarity >= self.SIMILARITY_THRESHOLD,
            "common_parts": common[:5],  # 最多返回5个
        }
    
    def validate(self, chapter_num: int = None, content: str = None) -> Dict:
        """
        验证单章与相邻章节的重复度
        
        Returns:
            {
                "passed": bool,
                "score": float,
                "prev_similarity": float,
                "next_similarity": float,
            }
        """
        if chapter_num is None:
            return {"passed": True, "score": 1.0, "prev_similarity": 0, "next_similarity": 0}
        
        prev_sim = 0.0
        next_sim = 0.0
        
        # 检查与上一章的重复
        if self.context.blueprint.chapter_exists(chapter_num - 1):
            result = self.compare_chapters(chapter_num - 1, chapter_num)
            prev_sim = result["similarity"]
        
        # 检查与下一章的重复
        if self.context.blueprint.chapter_exists(chapter_num + 1):
            result = self.compare_chapters(chapter_num, chapter_num + 1)
            next_sim = result["similarity"]
        
        max_sim = max(prev_sim, next_sim)
        passed = max_sim < self.SIMILARITY_THRESHOLD
        
        return {
            "passed": passed,
            "score": 1.0 - max_sim,
            "prev_similarity": prev_sim,
            "next_similarity": next_sim,
        }
    
    def scan_all_chapters(self) -> List[Tuple[int, int, float, List[str]]]:
        """
        扫描所有相邻章节对的重复情况
        
        Returns:
            [(ch1, ch2, similarity, common_parts), ...]
        """
        duplicates = []
        chapters = list(self.context.blueprint.iter_chapters())
        
        for i in range(len(chapters) - 1):
            ch1, ch2 = chapters[i], chapters[i + 1]
            result = self.compare_chapters(ch1, ch2)
            
            if result["is_duplicate"]:
                duplicates.append((ch1, ch2, result["similarity"], result["common_parts"]))
        
        return duplicates
    
    def generate_report(self) -> str:
        """生成重复检测报告"""
        duplicates = self.scan_all_chapters()
        
        if not duplicates:
            return "✅ 未发现相邻章节内容重复"
        
        lines = [f"⚠️ 发现 {len(duplicates)} 对相邻章节内容高度重复:\n"]
        
        for ch1, ch2, sim, common in duplicates[:10]:  # 最多显示10对
            lines.append(f"  第{ch1}章 ↔ 第{ch2}章: 相似度 {sim:.1%}")
            if common:
                lines.append(f"      重复内容: \"{common[0][:30]}...\"")
        
        if len(duplicates) > 10:
            lines.append(f"  ... 还有 {len(duplicates) - 10} 对")
        
        return "\n".join(lines)
