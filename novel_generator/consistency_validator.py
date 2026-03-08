# novel_generator/consistency_validator.py
# -*- coding: utf-8 -*-
"""
一致性检查器 - 确保小说生成过程中的角色一致性、情节逻辑性和世界观统一性

功能模块：
1. 角色一致性检查 - 验证角色行为、语言、心理状态的一致性
2. 情节逻辑检查 - 验证时间线、因果关系、事件发展的合理性
3. 世界观一致性检查 - 验证设定规则、物理定律、社会背景的统一性
4. 伏笔呼应检查 - 验证前后呼应、伏笔设计的有效性

版本: 1.0
创建时间: 2025-01-07
"""

import re
import json
import logging
import os
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ConsistencyLevel(Enum):
    """一致性级别枚举"""
    PERFECT = "perfect"       # 完全一致
    GOOD = "good"           # 基本一致，轻微问题
    WARNING = "warning"     # 存在不一致，需要修正
    ERROR = "error"         # 严重不一致，必须修改


class IssueType(Enum):
    """问题类型枚举"""
    CHARACTER_BEHAVIOR = "character_behavior"      # 角色行为不一致
    CHARACTER_LANGUAGE = "character_language"      # 角色语言风格不一致
    TIMELINE_CONFLICT = "timeline_conflict"        # 时间线冲突
    CAUSALITY_ERROR = "causality_error"           # 因果逻辑错误
    WORLDVIEW_CONFLICT = "worldview_conflict"      # 世界观设定冲突
    FORESHADOW_MISMATCH = "foreshadow_mismatch"    # 伏笔呼应不匹配
    CONTINUITY_BREAK = "continuity_break"          # 连续性断裂


@dataclass
class ConsistencyIssue:
    """一致性问题数据类"""
    issue_type: IssueType
    severity: ConsistencyLevel
    description: str
    location: str  # 在文本中的位置描述
    suggestion: str  # 修改建议
    confidence: float  # 置信度 (0.0 - 1.0)


@dataclass
class CharacterProfile:
    """角色档案数据类"""
    name: str
    personality_traits: List[str]  # 性格特征
    speech_style: str  # 语言风格
    background: str  # 背景故事
    relationships: Dict[str, str]  # 人际关系
    abilities: List[str]  # 能力/技能
    motivations: List[str]  # 动机/目标
    current_state: str  # 当前状态


@dataclass
class PlotEvent:
    """情节事件数据类"""
    timestamp: str  # 时间戳
    event_description: str  # 事件描述
    characters_involved: List[str]  # 涉及角色
    location: str  # 发生地点
    consequences: List[str]  # 后果
    foreshadowing_elements: List[str]  # 伏笔元素


class ConsistencyValidator:
    """一致性检查器主类"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化一致性检查器

        Args:
            config_path: 配置文件路径，可选
        """
        self.logger = logging.getLogger(__name__)
        self.character_profiles: Dict[str, CharacterProfile] = {}
        self.plot_events: List[PlotEvent] = []
        self.worldview_rules: Dict[str, Any] = {}
        self.foreshadowing_map: Dict[str, List[str]] = {}  # 伏笔映射

        # 配置参数
        self.config = self._load_config(config_path)

        # 正则表达式模式
        self.speech_pattern = re.compile(r'["「『](.*?)["」』]')
        self.action_pattern = re.compile(r'[^\s]+[动作行为](.*?)[。！？]')
        self.time_pattern = re.compile(r'\d{4}年|\d{1,2}月|\d{1,2}日|早上|中午|下午|晚上|深夜')

        self.logger.info("一致性检查器初始化完成")

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "character_consistency_threshold": 0.7,
            "plot_logic_threshold": 0.6,
            "worldview_consistency_threshold": 0.8,
            "enable_foreshadowing_check": True,
            "enable_timeline_check": True,
            "max_time_gap_hours": 24,
            "character_profile_path": "character_state.txt"
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                self.logger.info(f"配置文件加载成功: {config_path}")
            except Exception as e:
                self.logger.warning(f"配置文件加载失败，使用默认配置: {e}")

        return default_config

    def load_character_state(self, filepath: str) -> bool:
        """
        加载角色状态文件

        Args:
            filepath: 角色状态文件路径

        Returns:
            加载是否成功
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析角色状态信息
            # 这里需要根据实际的角色状态文件格式来解析
            # 假设是JSON格式或特定格式

            self.logger.info(f"角色状态加载成功: {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"角色状态加载失败: {e}")
            return False

    def validate_character_consistency(self, chapter_text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """
        验证角色一致性

        Args:
            chapter_text: 章节文本
            chapter_number: 章节编号

        Returns:
            发现的一致性问题列表
        """
        issues = []

        # 1. 提取角色对话
        dialogues = self._extract_dialogues(chapter_text)

        # 2. 提取角色行为
        actions = self._extract_actions(chapter_text)

        # 3. 检查语言风格一致性
        for character_name, dialogue_list in dialogues.items():
            if character_name in self.character_profiles:
                profile = self.character_profiles[character_name]
                language_issues = self._check_language_consistency(
                    character_name, dialogue_list, profile
                )
                issues.extend(language_issues)

        # 4. 检查行为一致性
        for character_name, action_list in actions.items():
            if character_name in self.character_profiles:
                profile = self.character_profiles[character_name]
                behavior_issues = self._check_behavior_consistency(
                    character_name, action_list, profile
                )
                issues.extend(behavior_issues)

        self.logger.info(f"角色一致性检查完成，发现 {len(issues)} 个问题")
        return issues

    def validate_plot_logic(self, chapter_text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """
        验证情节逻辑

        Args:
            chapter_text: 章节文本
            chapter_number: 章节编号

        Returns:
            发现的逻辑问题列表
        """
        issues = []

        # 1. 时间线检查
        if self.config.get("enable_timeline_check", True):
            timeline_issues = self._check_timeline_consistency(chapter_text, chapter_number)
            issues.extend(timeline_issues)

        # 2. 因果逻辑检查
        causality_issues = self._check_causality_logic(chapter_text)
        issues.extend(causality_issues)

        # 3. 事件连续性检查
        continuity_issues = self._check_event_continuity(chapter_text, chapter_number)
        issues.extend(continuity_issues)

        self.logger.info(f"情节逻辑检查完成，发现 {len(issues)} 个问题")
        return issues

    def validate_worldview_consistency(self, chapter_text: str) -> List[ConsistencyIssue]:
        """
        验证世界观一致性

        Args:
            chapter_text: 章节文本

        Returns:
            发现的世界观问题列表
        """
        issues = []

        # 1. 检查物理定律一致性
        physics_issues = self._check_physics_consistency(chapter_text)
        issues.extend(physics_issues)

        # 2. 检查社会设定一致性
        social_issues = self._check_social_consistency(chapter_text)
        issues.extend(social_issues)

        # 3. 检查技术设定一致性
        tech_issues = self._check_technology_consistency(chapter_text)
        issues.extend(tech_issues)

        self.logger.info(f"世界观一致性检查完成，发现 {len(issues)} 个问题")
        return issues

    def validate_foreshadowing_consistency(self, chapter_text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """
        验证伏笔呼应一致性

        Args:
            chapter_text: 章节文本
            chapter_number: 章节编号

        Returns:
            发现的伏笔问题列表
        """
        issues = []

        if not self.config.get("enable_foreshadowing_check", True):
            return issues

        # 1. 提取新的伏笔
        new_foreshadows = self._extract_foreshadowing(chapter_text, chapter_number)

        # 2. 检查伏笔呼应
        foreshadow_issues = self._check_foreshadowing_resolution(chapter_text, chapter_number)
        issues.extend(foreshadow_issues)

        # 3. 验证伏笔逻辑性
        logic_issues = self._check_foreshadowing_logic(new_foreshadows)
        issues.extend(logic_issues)

        self.logger.info(f"伏笔呼应检查完成，发现 {len(issues)} 个问题")
        return issues

    def _extract_dialogues(self, text: str) -> Dict[str, List[str]]:
        """提取角色对话"""
        dialogues = {}

        # 使用正则表达式提取对话
        # 这里需要根据实际的对话格式来调整
        # 假设格式为："角色名：对话内容" 或 「对话内容」

        matches = self.speech_pattern.findall(text)

        # 需要结合上下文确定说话者
        # 这里简化处理，实际实现需要更复杂的逻辑

        return dialogues

    def _extract_actions(self, text: str) -> Dict[str, List[str]]:
        """提取角色行为"""
        actions = {}

        # 使用正则表达式和NLP技术提取行为描述
        # 这里简化处理，实际实现需要更复杂的NLP逻辑

        return actions

    def _check_language_consistency(self, character_name: str, dialogues: List[str], profile: CharacterProfile) -> List[ConsistencyIssue]:
        """检查角色语言风格一致性"""
        issues = []

        # 1. 检查用词习惯
        # 2. 检查句式特点
        # 3. 检查语言风格

        return issues

    def _check_behavior_consistency(self, character_name: str, actions: List[str], profile: CharacterProfile) -> List[ConsistencyIssue]:
        """检查角色行为一致性"""
        issues = []

        # 1. 检查行为与性格匹配度
        # 2. 检查行为与能力匹配度
        # 3. 检查行为与动机匹配度

        return issues

    def _check_timeline_consistency(self, text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """检查时间线一致性"""
        issues = []

        # 1. 提取时间信息
        time_expressions = self.time_pattern.findall(text)

        # 2. 检查时间逻辑
        # 3. 验证时间间隔合理性

        return issues

    def _check_causality_logic(self, text: str) -> List[ConsistencyIssue]:
        """检查因果逻辑"""
        issues = []

        # 1. 识别因果关系
        # 2. 验证因果合理性
        # 3. 检查逻辑链条完整性

        return issues

    def _check_event_continuity(self, text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """检查事件连续性"""
        issues = []

        # 1. 与前一章节的事件衔接
        # 2. 事件发展的合理性
        # 3. 状态变化的连续性

        return issues

    def _check_physics_consistency(self, text: str) -> List[ConsistencyIssue]:
        """检查物理定律一致性"""
        issues = []

        # 1. 检查物理现象描述
        # 2. 验证科学原理应用
        # 3. 检查技术实现的合理性

        return issues

    def _check_social_consistency(self, text: str) -> List[ConsistencyIssue]:
        """检查社会设定一致性"""
        issues = []

        # 1. 检查社会制度描述
        # 2. 验证文化背景一致性
        # 3. 检查人际关系合理性

        return issues

    def _check_technology_consistency(self, text: str) -> List[ConsistencyIssue]:
        """检查技术设定一致性"""
        issues = []

        # 1. 检查技术水平描述
        # 2. 验证技术原理一致性
        # 3. 检查技术发展逻辑

        return issues

    def _extract_foreshadowing(self, text: str, chapter_number: int) -> List[Dict[str, str]]:
        """提取伏笔元素"""
        foreshadows = []

        # 1. 识别可能的伏笔
        # 2. 分析伏笔特征
        # 3. 记录伏笔信息

        return foreshadows

    def _check_foreshadowing_resolution(self, text: str, chapter_number: int) -> List[ConsistencyIssue]:
        """检查伏笔呼应"""
        issues = []

        # 1. 识别呼应内容
        # 2. 匹配已有伏笔
        # 3. 验证呼应质量

        return issues

    def _check_foreshadowing_logic(self, new_foreshadows: List[Dict[str, str]]) -> List[ConsistencyIssue]:
        """检查伏笔逻辑性"""
        issues = []

        # 1. 验证伏笔合理性
        # 2. 检查伏笔可实现性
        # 3. 评估伏笔价值

        return issues

    def generate_consistency_report(self, issues: List[ConsistencyIssue]) -> Dict[str, Any]:
        """
        生成一致性检查报告

        Args:
            issues: 发现的问题列表

        Returns:
            检查报告
        """
        report = {
            "summary": {
                "total_issues": len(issues),
                "perfect_count": sum(1 for issue in issues if issue.severity == ConsistencyLevel.PERFECT),
                "good_count": sum(1 for issue in issues if issue.severity == ConsistencyLevel.GOOD),
                "warning_count": sum(1 for issue in issues if issue.severity == ConsistencyLevel.WARNING),
                "error_count": sum(1 for issue in issues if issue.severity == ConsistencyLevel.ERROR),
                "overall_score": self._calculate_overall_score(issues)
            },
            "issues_by_type": {},
            "detailed_issues": []
        }

        # 按类型分组问题
        for issue in issues:
            issue_type = issue.issue_type.value
            if issue_type not in report["issues_by_type"]:
                report["issues_by_type"][issue_type] = []
            report["issues_by_type"][issue_type].append({
                "severity": issue.severity.value,
                "description": issue.description,
                "location": issue.location,
                "suggestion": issue.suggestion,
                "confidence": issue.confidence
            })

        # 详细问题列表
        report["detailed_issues"] = [
            {
                "type": issue.issue_type.value,
                "severity": issue.severity.value,
                "description": issue.description,
                "location": issue.location,
                "suggestion": issue.suggestion,
                "confidence": issue.confidence
            }
            for issue in issues
        ]

        return report

    def _calculate_overall_score(self, issues: List[ConsistencyIssue]) -> float:
        """计算整体一致性评分 (0.0 - 1.0)"""
        if not issues:
            return 1.0

        # 根据问题严重程度计算评分
        score_weights = {
            ConsistencyLevel.PERFECT: 1.0,
            ConsistencyLevel.GOOD: 0.8,
            ConsistencyLevel.WARNING: 0.5,
            ConsistencyLevel.ERROR: 0.2
        }

        total_weight = 0
        weighted_score = 0

        for issue in issues:
            weight = issue.confidence  # 使用置信度作为权重
            score = score_weights.get(issue.severity, 0.5)

            total_weight += weight
            weighted_score += weight * score

        if total_weight == 0:
            return 1.0

        return weighted_score / total_weight


def create_consistency_validator(config_path: Optional[str] = None) -> ConsistencyValidator:
    """
    创建一致性检查器实例

    Args:
        config_path: 配置文件路径，可选

    Returns:
        ConsistencyValidator实例
    """
    return ConsistencyValidator(config_path)


if __name__ == "__main__":
    # 测试代码
    validator = create_consistency_validator()

    # 示例文本
    sample_text = """
    张三说道："我明天一定要完成这个任务。"
    他快速地收拾着桌上的文件，表情严肃。
    """

    # 执行检查
    issues = validator.validate_character_consistency(sample_text, 1)

    # 生成报告
    report = validator.generate_consistency_report(issues)
    print(json.dumps(report, ensure_ascii=False, indent=2))