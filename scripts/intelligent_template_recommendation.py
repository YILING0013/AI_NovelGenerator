# intelligent_template_recommendation.py
# -*- coding: utf-8 -*-
"""
智能模板推荐系统 - 基于上下文和历史选择的智能模板推荐
深度分析您的AI NovelGenerator使用模式，提供个性化模板建议

核心功能：
1. 基于情节发展阶段智能推荐模板
2. 根据情绪曲线选择最佳模板类型
3. 分析历史使用模式，优化推荐策略
4. 多维度评分系统，确保推荐质量
5. 学习用户偏好，持续优化推荐效果
"""

import time
import json
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import pickle
import os

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PlotStage(Enum):
    """情节发展阶段"""
    EARLY = "early"          # 早期（1-10章）
    DEVELOPMENT = "development"  # 发展期（11-30章）
    CLIMAX = "climax"       # 高潮期（31-50章）
    RESOLUTION = "resolution"  # 解决期（51章+）

class EmotionState(Enum):
    """情绪状态"""
    TENSION = "tension"      # 紧张积累
    EXCITEMENT = "excitement"  # 兴奋激动
    STABLE = "stable"        # 稳定平缓
    CRISIS = "crisis"        # 危机时刻
    VICTORY = "victory"      # 胜利喜悦

@dataclass
class TemplateRecommendation:
    """模板推荐结果"""
    template_id: str
    template_name: str
    template_type: str
    confidence_score: float
    reasoning: List[str]
    expected_emotion_impact: float
    complexity_score: float
    suitability_tags: List[str]

@dataclass
class UserPreference:
    """用户偏好"""
    preferred_template_types: Dict[str, float] = field(default_factory=dict)
    emotion_intensity_preference: float = 0.7
    complexity_tolerance: float = 0.5
    favorite_tags: List[str] = field(default_factory=list)
    avoided_elements: List[str] = field(default_factory=list)

class UsageAnalyzer:
    """使用模式分析器"""

    def __init__(self):
        self.usage_history = deque(maxlen=1000)
        self.preference_profile = UserPreference()
        self.pattern_cache = {}

    def record_template_usage(self, template_id: str, template_type: str,
                              chapter_id: int, emotion_before: float,
                              emotion_after: float, user_satisfaction: float = None):
        """记录模板使用情况"""
        usage_record = {
            'template_id': template_id,
            'template_type': template_type,
            'chapter_id': chapter_id,
            'emotion_before': emotion_before,
            'emotion_after': emotion_after,
            'emotion_change': emotion_after - emotion_before,
            'timestamp': time.time(),
            'user_satisfaction': user_satisfaction
        }

        self.usage_history.append(usage_record)
        self._update_preference_profile()

    def _update_preference_profile(self):
        """更新用户偏好档案"""
        if not self.usage_history:
            return

        # 分析模板类型偏好
        type_usage = defaultdict(list)
        for record in self.usage_history:
            type_usage[record['template_type']].append(record['emotion_change'])

        # 计算每种模板类型的平均情绪变化
        self.preference_profile.preferred_template_types = {}
        for template_type, changes in type_usage.items():
            avg_change = np.mean(changes)
            self.preference_profile.preferred_template_types[template_type] = max(0, avg_change)

        # 分析情绪强度偏好
        emotion_changes = [r['emotion_change'] for r in self.usage_history]
        if emotion_changes:
            self.preference_profile.emotion_intensity_preference = np.mean(np.abs(emotion_changes))

        # 分析复杂度容忍度（基于章节编号）
        chapter_ids = [r['chapter_id'] for r in self.usage_history]
        if len(set(chapter_ids)) > 1:
            self.preference_profile.complexity_tolerance = np.std(chapter_ids) / 50.0
            self.preference_profile.complexity_tolerance = min(1.0, self.preference_profile.complexity_tolerance)

    def get_most_used_templates(self, limit: int = 5) -> List[str]:
        """获取最常用的模板"""
        template_counts = defaultdict(int)
        for record in self.usage_history:
            template_counts[record['template_id']] += 1

        return sorted(template_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

class ContextAnalyzer:
    """上下文分析器"""

    def __init__(self):
        self.emotion_keywords = {
            EmotionState.TENSION: ["紧张", "压抑", "危机", "危险", "威胁"],
            EmotionState.EXCITEMENT: ["兴奋", "激动", "喜悦", "期待", "热血"],
            EmotionState.STABLE: ["平静", "稳定", "思考", "规划", "准备"],
            EmotionState.CRISIS: ["绝境", "危机", "死亡", "失败", "绝望"],
            EmotionState.VICTORY: ["胜利", "成功", "击败", "碾压", "胜利"]
        }

    def analyze_current_emotion_state(self, content: str, emotion_value: float) -> EmotionState:
        """分析当前情绪状态"""
        if emotion_value < 0.3:
            return EmotionState.CRISIS
        elif emotion_value < 0.5:
            return EmotionState.TENSION
        elif emotion_value < 0.7:
            return EmotionState.STABLE
        elif emotion_value < 0.85:
            return EmotionState.EXCITEMENT
        else:
            return EmotionState.VICTORY

    def determine_plot_stage(self, chapter_id: int, total_chapters: int) -> PlotStage:
        """确定情节发展阶段"""
        progress = chapter_id / max(total_chapters, 1)

        if progress <= 0.2:
            return PlotStage.EARLY
        elif progress <= 0.6:
            return PlotStage.DEVELOPMENT
        elif progress <= 0.8:
            return PlotStage.CLIMAX
        else:
            return PlotStage.RESOLUTION

    def extract_content_features(self, content: str) -> Dict[str, Any]:
        """提取内容特征"""
        features = {
            'length': len(content),
            'character_count': content.count('人物') + content.count('角色'),
            'dialogue_ratio': content.count('"') / max(len(content), 1),
            'action_density': content.count('战斗') + content.count('动作'),
            'emotion_density': sum(len(keywords) for keywords in self.emotion_keywords.values()
                               for keyword in keywords if keyword in content) / max(len(content), 1)
        }

        return features

class TemplateScorer:
    """模板评分器"""

    def __init__(self):
        self.scoring_weights = {
            'context_match': 0.3,
            'emotion_appropriateness': 0.25,
            'plot_stage_suitability': 0.2,
            'user_preference': 0.15,
            'complexity_match': 0.1
        }

    def score_template(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any],
                      user_preference: UserPreference) -> float:
        """综合评分模板"""
        scores = {}

        # 上下文匹配度
        scores['context_match'] = self._score_context_match(template_info, context_analysis)

        # 情绪适当性
        scores['emotion_appropriateness'] = self._score_emotion_appropriateness(template_info, context_analysis)

        # 情节阶段适用性
        scores['plot_stage_suitability'] = self._score_plot_stage_suitability(template_info, context_analysis)

        # 用户偏好匹配
        scores['user_preference'] = self._score_user_preference(template_info, user_preference)

        # 复杂度匹配
        scores['complexity_match'] = self._score_complexity_match(template_info, context_analysis)

        # 加权总分
        total_score = sum(score * self.scoring_weights[category]
                          for category, score in scores.items())

        return min(total_score, 1.0)

    def _score_context_match(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any]) -> float:
        """评分上下文匹配度"""
        content_features = context_analysis.get('content_features', {})
        template_tags = template_info.get('tags', [])

        score = 0.5  # 基础分

        # 根据内容特征调整评分
        if content_features.get('dialogue_ratio', 0) > 0.3 and '情感' in template_tags:
            score += 0.2
        if content_features.get('action_density', 0) > 0.1 and '战斗' in template_tags:
            score += 0.2
        if content_features.get('emotion_density', 0) > 0.05 and '爽点' in template_tags:
            score += 0.2

        return min(score, 1.0)

    def _score_emotion_appropriateness(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any]) -> float:
        """评分情绪适当性"""
        current_emotion = context_analysis.get('current_emotion_state')
        template_type = template_info.get('type', '')

        # 情绪状态与模板类型的映射
        emotion_template_map = {
            EmotionState.CRISIS: ['revenge', 'breakthrough'],
            EmotionState.TENSION: ['undercover', 'tournament'],
            EmotionState.EXCITEMENT: ['auction', 'secret_realm'],
            EmotionState.STABLE: ['beauty_rescue', 'master_inheritance'],
            EmotionState.VICTORY: ['system_flow', 'mysterious_org']
        }

        if current_emotion in emotion_template_map:
            if template_type in emotion_template_map[current_emotion]:
                return 0.9
            elif template_type in [t for types in emotion_template_map.values() for t in types]:
                return 0.6

        return 0.5

    def _score_plot_stage_suitability(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any]) -> float:
        """评分情节阶段适用性"""
        plot_stage = context_analysis.get('plot_stage')
        template_difficulty = template_info.get('difficulty', 'normal')

        stage_difficulty_map = {
            PlotStage.EARLY: {'easy': 0.9, 'normal': 0.7, 'hard': 0.5},
            PlotStage.DEVELOPMENT: {'easy': 0.7, 'normal': 0.9, 'hard': 0.7},
            PlotStage.CLIMAX: {'easy': 0.5, 'normal': 0.8, 'hard': 0.9},
            PlotStage.RESOLUTION: {'easy': 0.8, 'normal': 0.9, 'hard': 0.6}
        }

        if plot_stage in stage_difficulty_map:
            return stage_difficulty_map[plot_stage].get(template_difficulty, 0.5)

        return 0.6

    def _score_user_preference(self, template_info: Dict[str, Any], user_preference: UserPreference) -> float:
        """评分用户偏好匹配"""
        template_type = template_info.get('type', '')
        template_tags = template_info.get('tags', [])

        # 检查模板类型偏好
        type_preference = user_preference.preferred_template_types.get(template_type, 0.5)

        # 检查标签偏好
        tag_preference = 0.5
        favorite_tags_count = sum(1 for tag in template_tags if tag in user_preference.favorite_tags)
        if template_tags:
            tag_preference = 0.5 + (favorite_tags_count / len(template_tags)) * 0.5

        # 检查避免元素
        avoided_count = sum(1 for tag in template_tags if tag in user_preference.avoided_elements)
        if template_tags and avoided_count > 0:
            tag_preference *= (1 - avoided_count / len(template_tags))

        return (type_preference + tag_preference) / 2

    def _score_complexity_match(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any]) -> float:
        """评分复杂度匹配"""
        template_difficulty = template_info.get('difficulty', 'normal')
        user_complexity_tolerance = context_analysis.get('user_complexity_tolerance', 0.5)

        difficulty_scores = {'easy': 0.3, 'normal': 0.6, 'hard': 0.9}
        template_complexity = difficulty_scores.get(template_difficulty, 0.6)

        # 计算复杂度匹配度
        diff = abs(template_complexity - user_complexity_tolerance)
        return max(0, 1 - diff)

class IntelligentTemplateRecommender:
    """智能模板推荐器主类"""

    def __init__(self):
        self.usage_analyzer = UsageAnalyzer()
        self.context_analyzer = ContextAnalyzer()
        self.template_scorer = TemplateScorer()
        self.recommendation_history = deque(maxlen=500)
        self.recommendation_stats = {
            'total_recommendations': 0,
            'accepted_recommendations': 0,
            'average_confidence': 0.0
        }

        logger.info("🧠 智能模板推荐系统初始化完成")

    def recommend_template(self, template_library: Dict[str, Any], chapter_id: int,
                          total_chapters: int, current_content: str,
                          emotion_value: float, user_feedback: Optional[Dict] = None) -> List[TemplateRecommendation]:
        """推荐最适合的模板"""

        # 分析上下文
        context_analysis = {
            'plot_stage': self.context_analyzer.determine_plot_stage(chapter_id, total_chapters),
            'current_emotion_state': self.context_analyzer.analyze_current_emotion_state(current_content, emotion_value),
            'content_features': self.context_analyzer.extract_content_features(current_content),
            'user_complexity_tolerance': self.usage_analyzer.preference_profile.complexity_tolerance
        }

        # 为每个模板评分
        scored_templates = []
        for template_id, template_info in template_library.items():
            score = self.template_scorer.score_template(
                template_info, context_analysis, self.usage_analyzer.preference_profile
            )

            if score > 0.3:  # 只考虑评分超过0.3的模板
                recommendation = TemplateRecommendation(
                    template_id=template_id,
                    template_name=template_info.get('name', template_id),
                    template_type=template_info.get('type', 'unknown'),
                    confidence_score=score,
                    reasoning=self._generate_reasoning(template_info, context_analysis, score),
                    expected_emotion_impact=template_info.get('emotional_impact', 0.7),
                    complexity_score={'easy': 0.3, 'normal': 0.6, 'hard': 0.9}.get(template_info.get('difficulty', 'normal'), 0.6),
                    suitability_tags=template_info.get('tags', [])
                )
                scored_templates.append(recommendation)

        # 按评分排序
        scored_templates.sort(key=lambda x: x.confidence_score, reverse=True)

        # 记录推荐历史
        self._record_recommendation(scored_templates[:5], context_analysis)

        # 更新统计
        self.recommendation_stats['total_recommendations'] += len(scored_templates)
        if scored_templates:
            avg_confidence = np.mean([r.confidence_score for r in scored_templates])
            self.recommendation_stats['average_confidence'] = avg_confidence

        logger.info(f"🎯 智能推荐完成：{len(scored_templates)}个候选模板")

        return scored_templates[:5]  # 返回前5个推荐

    def _generate_reasoning(self, template_info: Dict[str, Any], context_analysis: Dict[str, Any], score: float) -> List[str]:
        """生成推荐理由"""
        reasoning = []

        # 基于情节阶段
        plot_stage = context_analysis.get('plot_stage')
        template_difficulty = template_info.get('difficulty', 'normal')

        stage_reasons = {
            PlotStage.EARLY: {'easy': '适合早期发展', 'normal': '平衡难度适中', 'hard': '挑战性较强'},
            PlotStage.DEVELOPMENT: {'easy': '稳定推进', 'normal': '发展阶段理想', 'hard': '加速发展'},
            PlotStage.CLIMAX: {'easy': '高潮铺垫', 'normal': '高潮阶段适合', 'hard': '高潮激战'},
            PlotStage.RESOLUTION: {'easy': '完美收尾', 'normal': '结局适中', 'hard': '复杂结局'}
        }

        if plot_stage in stage_reasons and template_difficulty in stage_reasons[plot_stage]:
            reasoning.append(stage_reasons[plot_stage][template_difficulty])

        # 基于情绪状态
        current_emotion = context_analysis.get('current_emotion_state')
        emotion_reasons = {
            EmotionState.CRISIS: '适合危机处理和突破',
            EmotionState.TENSION: '有助于紧张情节推进',
            EmotionState.STABLE: '适合稳定发展',
            EmotionState.EXCITEMENT: '增强兴奋感',
            EmotionState.VICTORY: '巩固胜利喜悦'
        }

        if current_emotion in emotion_reasons:
            reasoning.append(emotion_reasons[current_emotion])

        # 基于用户偏好
        template_type = template_info.get('type', '')
        user_pref_score = self.usage_analyzer.preference_profile.preferred_template_types.get(template_type, 0)
        if user_pref_score > 0.7:
            reasoning.append('符合用户历史偏好')
        elif user_pref_score > 0.5:
            reasoning.append('用户较为偏好此类型')

        # 基于评分
        if score > 0.8:
            reasoning.append('综合评分极高')
        elif score > 0.6:
            reasoning.append('综合评分良好')

        if not reasoning:
            reasoning.append('基于多维度分析推荐')

        return reasoning

    def _record_recommendation(self, recommendations: List[TemplateRecommendation], context_analysis: Dict[str, Any]):
        """记录推荐历史"""
        record = {
            'recommendations': recommendations,
            'context': context_analysis,
            'timestamp': time.time()
        }
        self.recommendation_history.append(record)

    def record_user_feedback(self, template_id: str, satisfaction_score: float):
        """记录用户反馈"""
        # 更新使用分析器
        self.usage_analyzer.preference_profile.preferred_template_types[template_id] = satisfaction_score

        # 更新统计
        self.recommendation_stats['accepted_recommendations'] += 1

        logger.info(f"📝 用户反馈记录：模板 {template_id} 满意度 {satisfaction_score}")

    def get_recommendation_stats(self) -> Dict[str, Any]:
        """获取推荐统计信息"""
        acceptance_rate = (
            self.recommendation_stats['accepted_recommendations'] /
            max(self.recommendation_stats['total_recommendations'], 1) * 100
        )

        return {
            'total_recommendations': self.recommendation_stats['total_recommendations'],
            'accepted_recommendations': self.recommendation_stats['accepted_recommendations'],
            'acceptance_rate': f"{acceptance_rate:.1f}%",
            'average_confidence': f"{self.recommendation_stats['average_confidence']:.2f}",
            'most_used_templates': self.usage_analyzer.get_most_used_templates(3),
            'user_preferences': {
                'preferred_types': list(self.usage_analyzer.preference_profile.preferred_template_types.keys())[:5],
                'emotion_intensity': f"{self.usage_analyzer.preference_profile.emotion_intensity_preference:.2f}",
                'complexity_tolerance': f"{self.usage_analyzer.preference_profile.complexity_tolerance:.2f}"
            }
        }

    def export_preference_profile(self, filepath: str):
        """导出用户偏好档案"""
        profile_data = {
            'preferences': self.usage_analyzer.preference_profile.__dict__,
            'recommendation_stats': self.recommendation_stats,
            'export_timestamp': time.time()
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=2)
            logger.info(f"📁 用户偏好档案已导出：{filepath}")
        except Exception as e:
            logger.error(f"导出偏好档案失败：{e}")

    def import_preference_profile(self, filepath: str):
        """导入用户偏好档案"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)

            # 恢复用户偏好
            preferences = profile_data.get('preferences', {})
            self.usage_analyzer.preference_profile = UserPreference(**preferences)

            # 恢复统计信息
            if 'recommendation_stats' in profile_data:
                self.recommendation_stats.update(profile_data['recommendation_stats'])

            logger.info(f"📁 用户偏好档案已导入：{filepath}")
        except Exception as e:
            logger.error(f"导入偏好档案失败：{e}")

def create_intelligent_template_recommender() -> IntelligentTemplateRecommender:
    """创建智能模板推荐器实例"""
    return IntelligentTemplateRecommender()

# 测试代码
if __name__ == "__main__":
    print("🧠 测试智能模板推荐系统...")

    recommender = create_intelligent_template_recommender()

    # 模拟模板库
    mock_templates = {
        "template_1": {
            "name": "复仇爽点模板",
            "type": "revenge",
            "difficulty": "normal",
            "tags": ["复仇", "打脸", "爽点"],
            "emotional_impact": 0.8
        },
        "template_2": {
            "name": "突破升级模板",
            "type": "breakthrough",
            "difficulty": "hard",
            "tags": ["突破", "升级", "实力"],
            "emotional_impact": 0.9
        }
    }

    # 模拟推荐场景
    recommendations = recommender.recommend_template(
        mock_templates, chapter_id=15, total_chapters=50,
        current_content="主角面临危机，需要突破...", emotion_value=0.3
    )

    print(f"✅ 推荐完成：{len(recommendations)}个推荐")
    for i, rec in enumerate(recommendations, 1):
        print(f"  {i}. {rec.template_name} (置信度: {rec.confidence_score:.2f})")

    stats = recommender.get_recommendation_stats()
    print(f"📊 推荐统计：{stats}")

    print("🎉 智能模板推荐系统测试完成！")