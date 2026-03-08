# -*- coding: utf-8 -*-
"""
叙事模式重复检测器 (Pattern Detector)
检测连续多章使用相同叙事结构模式（如总是"困境→领悟→反杀"）。
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class NarrativePatternDetector:
    """叙事结构模式检测器"""
    
    PATTERN_DB_FILE = ".narrative_patterns.json"
    
    # 叙事动作关键词分类
    NARRATIVE_ACTIONS = {
        "困境": ["危险", "困境", "绝境", "被困", "围攻", "受伤", "失败", "挫折", "陷入"],
        "领悟": ["领悟", "突破", "顿悟", "明白", "理解", "灵感", "开窍", "恍然"],
        "战斗": ["战斗", "交手", "厮杀", "对决", "出手", "攻击", "防御", "反击"],
        "反杀": ["反杀", "逆袭", "反败为胜", "绝地翻盘", "一击制敌", "扭转"],
        "升级": ["突破", "进阶", "晋升", "境界提升", "实力暴涨", "获得", "觉醒"],
        "情感": ["温柔", "暧昧", "感动", "泪", "心疼", "关心", "思念", "深情"],
        "阴谋": ["阴谋", "陷阱", "背叛", "暗算", "密谋", "算计", "设局", "圈套"],
        "探索": ["探索", "发现", "秘境", "遗迹", "宝物", "线索", "调查", "进入"],
        "修炼": ["修炼", "闭关", "练功", "参悟", "打坐", "炼丹", "炼器"],
        "社交": ["宴会", "拜师", "结盟", "谈判", "拜访", "交易", "传授"],
    }
    
    LOOKBACK_CHAPTERS = 10  # 回看最近N章
    SIMILARITY_THRESHOLD = 0.7  # 结构相似度阈值
    
    def __init__(self, novel_path: str):
        self.novel_path = Path(novel_path)
        self.pattern_db_file = self.novel_path / self.PATTERN_DB_FILE
        self._pattern_db = self._load_pattern_db()
    
    def _load_pattern_db(self) -> Dict[str, Any]:
        if self.pattern_db_file.exists():
            try:
                with open(self.pattern_db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"chapters": {}}
    
    def _save_pattern_db(self):
        try:
            with open(self.pattern_db_file, 'w', encoding='utf-8') as f:
                json.dump(self._pattern_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存叙事模式库失败: {e}")
    
    def extract_pattern(self, content: str) -> List[str]:
        """
        提取章节的叙事结构模式
        返回: ["困境", "战斗", "领悟", "反杀"] 这样的序列
        """
        # 将内容分成段落组
        paragraphs = content.split('\n')
        section_size = max(1, len(paragraphs) // 5)  # 分成5段分析
        
        pattern_sequence = []
        for i in range(0, len(paragraphs), section_size):
            section = '\n'.join(paragraphs[i:i + section_size])
            dominant_action = self._detect_dominant_action(section)
            if dominant_action and (not pattern_sequence or pattern_sequence[-1] != dominant_action):
                pattern_sequence.append(dominant_action)
        
        return pattern_sequence
    
    def _detect_dominant_action(self, text: str) -> Optional[str]:
        """检测一段文本的主导叙事动作"""
        scores = {}
        for action, keywords in self.NARRATIVE_ACTIONS.items():
            count = sum(text.count(kw) for kw in keywords)
            if count > 0:
                scores[action] = count
        
        if scores:
            return max(scores, key=scores.get)
        return None
    
    def record_chapter_pattern(self, content: str, chapter_num: int):
        """记录章节的叙事模式"""
        pattern = self.extract_pattern(content)
        self._pattern_db["chapters"][str(chapter_num)] = {
            "pattern": pattern,
            "pattern_str": "→".join(pattern)
        }
        self._save_pattern_db()
        logger.info(f"📊 第{chapter_num}章叙事模式: {'→'.join(pattern)}")
    
    def compute_pattern_similarity(self, pattern_a: List[str], pattern_b: List[str]) -> float:
        """计算两个叙事模式的相似度"""
        if not pattern_a or not pattern_b:
            return 0.0
        
        # 使用最长公共子序列
        m, n = len(pattern_a), len(pattern_b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if pattern_a[i-1] == pattern_b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        lcs_length = dp[m][n]
        return lcs_length / max(m, n)
    
    def check_pattern_repetition(self, content: str, chapter_num: int) -> List[str]:
        """
        检测叙事模式是否与最近的章节重复
        返回: 问题描述列表
        """
        current_pattern = self.extract_pattern(content)
        if not current_pattern:
            return []
        
        issues = []
        similar_chapters = []
        
        for ch_str, ch_data in self._pattern_db.get("chapters", {}).items():
            ch_num = int(ch_str)
            if ch_num >= chapter_num:
                continue
            if chapter_num - ch_num > self.LOOKBACK_CHAPTERS:
                continue
            
            old_pattern = ch_data.get("pattern", [])
            sim = self.compute_pattern_similarity(current_pattern, old_pattern)
            if sim >= self.SIMILARITY_THRESHOLD:
                similar_chapters.append((ch_num, sim, ch_data.get("pattern_str", "")))
        
        if len(similar_chapters) >= 2:
            ch_list = ", ".join(f"第{ch}章({sim:.0%})" for ch, sim, _ in similar_chapters[:3])
            current_str = "→".join(current_pattern)
            issues.append(
                f"本章叙事模式'{current_str}'与近期 {ch_list} 高度相似，"
                f"建议调整叙事结构避免读者疲劳"
            )
        elif len(similar_chapters) == 1:
            ch, sim, old_str = similar_chapters[0]
            if sim >= 0.9:
                issues.append(
                    f"本章叙事模式与第{ch}章几乎完全相同('{old_str}')，强烈建议重构"
                )
        
        return issues
