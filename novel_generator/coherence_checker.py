#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
章节衔接检查器
验证相邻章节之间的逻辑连贯性
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChapterState:
    """章节状态信息"""
    chapter_number: int
    
    # 场景信息
    location: str = ""
    time_period: str = ""
    
    # 角色状态
    present_characters: List[str] = field(default_factory=list)
    character_states: Dict[str, str] = field(default_factory=dict)  # 角色:状态(受伤/修炼/战斗等)
    
    # 剧情状态
    active_conflicts: List[str] = field(default_factory=list)
    resolved_conflicts: List[str] = field(default_factory=list)
    
    # 伏笔信息
    setup_foreshadowing: List[str] = field(default_factory=list)  # 本章埋下的伏笔
    payoff_foreshadowing: List[str] = field(default_factory=list)  # 本章回收的伏笔
    
    # 修为变化
    cultivation_changes: Dict[str, str] = field(default_factory=dict)


@dataclass
class CoherenceIssue:
    """衔接问题"""
    issue_type: str  # location_jump, character_inconsistency, timeline_error, etc.
    description: str
    severity: str = "medium"  # low, medium, high, critical
    chapter_pair: Tuple[int, int] = (0, 0)


class CoherenceChecker:
    """章节衔接检查器"""
    
    # 地点关键词
    LOCATION_KEYWORDS = [
        "宗门", "山门", "秘境", "洞府", "城池", "荒野", "北荒", "南疆", 
        "西漠", "东海", "冥界", "天宫", "深渊", "禁地"
    ]
    
    # 时间关键词
    TIME_KEYWORDS = [
        "清晨", "傍晚", "夜晚", "子时", "三日后", "月余", "年后", 
        "翌日", "当晚", "此刻", "片刻后"
    ]
    
    # 角色状态关键词
    STATE_KEYWORDS = {
        "受伤": ["重伤", "轻伤", "濒死", "吐血", "昏迷"],
        "战斗": ["交手", "对战", "厮杀", "激战", "血战"],
        "修炼": ["闭关", "突破", "修炼", "悟道", "参悟"],
        "移动": ["离开", "前往", "抵达", "返回", "赶往"]
    }
    
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.directory_path = self.filepath / "Novel_directory.txt"
        
        # Dynamic character loading from architecture
        self.main_characters: List[str] = []
        self.core_characters: set = set()
        self._load_characters_from_architecture()
    
    def _load_characters_from_architecture(self):
        """Load character names from architecture file dynamically"""
        try:
            from .architecture_parser import ArchitectureParser
            parser = ArchitectureParser(str(self.filepath))
            parser.parse()
            
            # Build main characters list
            self.main_characters = [parser.protagonist] + parser.female_leads
            if parser.antagonist and parser.antagonist != parser.DEFAULT_ANTAGONIST:
                self.main_characters.append(parser.antagonist)
            
            # Core characters = protagonist + female leads
            self.core_characters = set(parser.female_leads)
            
            logger.info(f"Loaded {len(self.main_characters)} characters from architecture")
        except Exception as e:
            logger.warning(f"Failed to load characters from architecture: {e}")
            # Fallback-empty; will not check character coherence
            self.main_characters = []
            self.core_characters = set()
    
    def extract_chapter_state(self, chapter_content: str, chapter_number: int) -> ChapterState:
        """从章节内容中提取状态信息"""
        state = ChapterState(chapter_number=chapter_number)
        
        # 提取地点
        for loc in self.LOCATION_KEYWORDS:
            if loc in chapter_content:
                state.location = loc
                break
        
        # 提取时间
        for time_kw in self.TIME_KEYWORDS:
            if time_kw in chapter_content:
                state.time_period = time_kw
                break
        
        # 提取出场角色 (Dynamic from architecture)
        for char in self.main_characters:
            if char in chapter_content:
                state.present_characters.append(char)
        
        # 提取角色状态
        for char in state.present_characters:
            for state_type, keywords in self.STATE_KEYWORDS.items():
                for kw in keywords:
                    if f"{char}" in chapter_content and kw in chapter_content:
                        state.character_states[char] = state_type
                        break
        
        # 提取冲突信息
        conflict_patterns = [
            r"与.{2,6}交手", r".{2,6}袭击", r"敌人.{2,10}", 
            r"危机", r"绝境", r"困境"
        ]
        for pattern in conflict_patterns:
            matches = re.findall(pattern, chapter_content)
            state.active_conflicts.extend(matches[:3])
        
        # 提取伏笔信息
        foreshadow_patterns = [
            r"暗中.*?(?:注视|窥探|布置)",
            r"日后.*?(?:必|定会)",
            r"此事.*?(?:蹊跷|古怪|隐情)",
            r"(?:伏笔|铺垫|暗示)"
        ]
        for pattern in foreshadow_patterns:
            matches = re.findall(pattern, chapter_content)
            state.setup_foreshadowing.extend(matches[:2])
        
        return state
    
    def check_adjacent_coherence(self, prev_state: ChapterState, 
                                  curr_state: ChapterState) -> List[CoherenceIssue]:
        """检查相邻章节的衔接问题（优化版 - 降低误报率）"""
        issues = []
        chapter_pair = (prev_state.chapter_number, curr_state.chapter_number)
        
        # 1. 地点跳跃检查 - 使用黑名单策略，只标记极端不合理的跳跃
        if prev_state.location and curr_state.location:
            if prev_state.location != curr_state.location:
                # 定义绝对不合理的跳跃（需要章节过渡）
                impossible_jumps = [
                    ("冥界", "天宫"), ("天宫", "冥界"),
                    ("深渊", "天宫"), ("天宫", "深渊"),
                ]
                transition = (prev_state.location, curr_state.location)
                reverse = (curr_state.location, prev_state.location)
                
                # 只有极端跳跃才报错
                if transition in impossible_jumps or reverse in impossible_jumps:
                    issues.append(CoherenceIssue(
                        issue_type="location_jump",
                        description=f"极端地点跳跃: {prev_state.location} → {curr_state.location}（需要过渡章节）",
                        severity="high",
                        chapter_pair=chapter_pair
                    ))
        
        # 2. 角色状态连续性检查 - 保持原逻辑
        for char, prev_status in prev_state.character_states.items():
            if char in curr_state.present_characters:
                curr_status = curr_state.character_states.get(char, "")
                
                # 受伤状态应该延续或恢复
                if prev_status == "受伤" and curr_status == "战斗":
                    issues.append(CoherenceIssue(
                        issue_type="character_inconsistency",
                        description=f"{char}上章受伤，本章直接战斗（缺少恢复描述）",
                        severity="medium",
                        chapter_pair=chapter_pair
                    ))
        
        # 3. 角色消失检查 - 只检查核心角色（主角团）
        for char in prev_state.present_characters:
            if char in self.core_characters and char not in curr_state.present_characters:
                # 仅在连续3章以上消失才报警（这里简化为不报警，只做记录）
                pass  # 暂时禁用，角色进出场景是正常的叙事手法
        
        # 4. 冲突延续性检查 - 只检查高优先级冲突关键词
        critical_conflict_keywords = ["生死", "决战", "大劫", "覆灭", "围攻"]
        for conflict in prev_state.active_conflicts:
            if conflict and conflict not in prev_state.resolved_conflicts:
                # 只有包含关键冲突词的才检查延续性
                is_critical = any(kw in conflict for kw in critical_conflict_keywords)
                if is_critical:
                    if not any(c in str(curr_state.active_conflicts) for c in conflict.split()):
                        issues.append(CoherenceIssue(
                            issue_type="unresolved_conflict",
                            description=f"重大冲突未延续: '{conflict[:20]}...'",
                            severity="medium",
                            chapter_pair=chapter_pair
                        ))
        
        return issues
    
    def check_all_chapters(self, chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """检查所有章节的衔接"""
        all_issues = []
        chapter_states = []
        
        # 提取所有章节状态
        for chapter in chapters:
            state = self.extract_chapter_state(
                chapter['content'], 
                chapter['chapter_number']
            )
            chapter_states.append(state)
        
        # 检查相邻章节
        for i in range(1, len(chapter_states)):
            issues = self.check_adjacent_coherence(
                chapter_states[i-1], 
                chapter_states[i]
            )
            all_issues.extend(issues)
        
        # 统计问题
        issue_counts = {}
        for issue in all_issues:
            issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1
        
        # 计算衔接分数
        max_issues = len(chapters) * 3  # 假设每章最多3个问题
        actual_issues = len(all_issues)
        coherence_score = max(0, 100 - (actual_issues / max_issues) * 100) if max_issues > 0 else 100
        
        return {
            'total_chapters': len(chapters),
            'total_issues': len(all_issues),
            'coherence_score': coherence_score,
            'issues': all_issues[:50],  # 最多返回50个问题
            'issue_breakdown': issue_counts
        }
    
    def get_transition_summary(self, prev_chapter: int, curr_chapter: int, 
                                chapters: List[Dict[str, Any]]) -> str:
        """获取两章之间的过渡摘要（用于修复提示）"""
        prev_content = ""
        curr_content = ""
        
        for ch in chapters:
            if ch['chapter_number'] == prev_chapter:
                prev_content = ch['content']
            elif ch['chapter_number'] == curr_chapter:
                curr_content = ch['content']
        
        if not prev_content or not curr_content:
            return ""
        
        prev_state = self.extract_chapter_state(prev_content, prev_chapter)
        curr_state = self.extract_chapter_state(curr_content, curr_chapter)
        
        summary = f"""
## 第{prev_chapter}章结束状态:
- 地点: {prev_state.location or '未知'}
- 出场角色: {', '.join(prev_state.present_characters) or '未知'}
- 活跃冲突: {', '.join(prev_state.active_conflicts[:3]) or '无'}

## 第{curr_chapter}章开始状态:
- 地点: {curr_state.location or '未知'}
- 出场角色: {', '.join(curr_state.present_characters) or '未知'}
"""
        return summary


def check_chapter_coherence(filepath: str, 
                             chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """便捷函数：检查章节衔接"""
    checker = CoherenceChecker(filepath)
    return checker.check_all_chapters(chapters)
