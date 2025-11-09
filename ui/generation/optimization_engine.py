"""
Optimization Engine
性能优化引擎类

负责管理各种性能优化功能，包括情绪工程、知识库检索、模板引擎、平台适配等。
这些优化功能可以显著提升生成内容的质量和效率。

主要功能:
- 情绪上下文分析
- 动态知识库检索
- 模板引擎应用
- 平台特定适配
- 优化策略组合
"""

import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)


class OptimizationType(Enum):
    """优化类型"""
    EMOTION_ENGINEERING = "emotion_engineering"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    TEMPLATE_ENGINE = "template_engine"
    PLATFORM_ADAPTER = "platform_adapter"
    STYLE_OPTIMIZATION = "style_optimization"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"


@dataclass
class OptimizationContext:
    """优化上下文"""
    chapter_id: int
    word_count: int
    content_type: str  # "draft", "final", "outline"
    target_audience: Optional[str] = None
    genre: Optional[str] = None
    custom_params: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_params is None:
            self.custom_params = {}


@dataclass
class OptimizationResult:
    """优化结果"""
    optimization_type: OptimizationType
    success: bool
    data: Dict[str, Any]
    confidence: float  # 0-1
    processing_time: float = 0.0
    error_message: Optional[str] = None


class OptimizationEngine:
    """性能优化引擎类"""

    def __init__(self, error_handler: ErrorHandler):
        """
        初始化优化引擎

        Args:
            error_handler: 错误处理器
        """
        self.error_handler = error_handler
        self.optimization_stats = {
            'total_optimizations': 0,
            'successful': 0,
            'failed': 0,
            'by_type': {}
        }

        # 优化系统状态
        self.systems_available = self._check_optimization_systems()
        self.active_optimizations = set()

        # 初始化优化系统
        self.optimization_systems = {}
        if self.systems_available:
            self._init_optimization_systems()

        logger.info("OptimizationEngine 初始化完成")

    def _check_optimization_systems(self) -> bool:
        """检查优化系统是否可用"""
        try:
            # 尝试导入优化系统
            from emotion_engineering_system import create_emotion_engineering_system
            from dynamic_world_knowledge_base import create_dynamic_world_knowledge_base
            from template_based_creation_engine import create_template_based_creation_engine
            from tomato_platform_adapter import create_tomato_platform_adapter
            from optimized_knowledge_retrieval import create_optimized_knowledge_retrieval
            return True
        except ImportError as e:
            logger.warning(f"部分优化系统不可用: {e}")
            return False

    def _init_optimization_systems(self) -> None:
        """初始化优化系统"""
        try:
            # 情绪工程系统
            from emotion_engineering_system import create_emotion_engineering_system
            self.optimization_systems['emotion'] = create_emotion_engineering_system({
                'auto_save_interval': 60,
                'emotion_decay_rate': 0.03,
                'shuangdian_frequency': 0.4,
                'personalization_enabled': True
            })

            # 动态知识库
            from dynamic_world_knowledge_base import create_dynamic_world_knowledge_base
            self.optimization_systems['knowledge'] = create_dynamic_world_knowledge_base(
                "",
                {
                    'auto_save_interval': 120,
                    'consistency_check_enabled': True,
                    'auto_fix_enabled': True,
                    'knowledge_graph_enabled': True
                }
            )

            # 模板化创作引擎
            from template_based_creation_engine import create_template_based_creation_engine
            self.optimization_systems['template_engine'] = create_template_based_creation_engine()

            # 番茄平台适配器
            from tomato_platform_adapter import create_tomato_platform_adapter
            self.optimization_systems['tomato_adapter'] = create_tomato_platform_adapter()

            # 优化知识库检索
            from optimized_knowledge_retrieval import create_optimized_knowledge_retrieval
            self.optimization_systems['optimized_retrieval'] = create_optimized_knowledge_retrieval()

            logger.info("所有优化系统初始化成功")

        except Exception as e:
            logger.error(f"优化系统初始化失败: {e}")
            self.systems_available = False

    def analyze_emotion_context(self, context: OptimizationContext) -> OptimizationResult:
        """分析情绪上下文"""
        optimization_type = OptimizationType.EMOTION_ENGINEERING

        if not self._is_system_available('emotion'):
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message="情绪工程系统不可用"
            )

        try:
            import time
            start_time = time.time()

            emotion_system = self.optimization_systems['emotion']
            emotion_system.update_emotional_state(f"第{context.chapter_id}章内容")

            # 检查是否应该触发爽点
            template = emotion_system.should_trigger_shuangdian({
                'chapter_id': context.chapter_id,
                'keywords': self._extract_keywords(context),
                'scene_type': self._detect_scene_type(context)
            })

            result_data = {
                'current_emotion': emotion_system.emotional_metrics.current_value,
                'emotional_state': emotion_system.emotional_metrics.get_state().value,
                'should_trigger_shuangdian': template is not None,
                'template': {
                    'name': template.name,
                    'description': template.description,
                    'parameters': template.parameters
                } if template else None,
                'emotion_trend': self._calculate_emotion_trend(emotion_system)
            }

            processing_time = time.time() - start_time

            self._update_stats(optimization_type, True)

            logger.info(f"情绪分析完成: 第{context.chapter_id}章")

            return OptimizationResult(
                optimization_type=optimization_type,
                success=True,
                data=result_data,
                confidence=0.8 if template else 0.6,
                processing_time=processing_time
            )

        except Exception as e:
            self._update_stats(optimization_type, False)
            logger.error(f"情绪分析失败: {e}")
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message=str(e)
            )

    def retrieve_knowledge_context(self, context: OptimizationContext) -> OptimizationResult:
        """检索知识上下文"""
        optimization_type = OptimizationType.KNOWLEDGE_RETRIEVAL

        if not self._is_system_available('knowledge'):
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message="知识库系统不可用"
            )

        try:
            import time
            start_time = time.time()

            knowledge_system = self.optimization_systems['knowledge']
            context_items = knowledge_system.get_relevant_context(
                f"第{context.chapter_id}章",
                limit=min(5, max(2, context.word_count // 1000))
            )

            # 处理检索结果
            processed_items = []
            for item in context_items:
                processed_items.append({
                    'content': item.get('content', '')[:500],  # 限制长度
                    'relevance_score': item.get('relevance_score', 0.5),
                    'source': item.get('source', 'unknown'),
                    'type': item.get('type', 'text')
                })

            result_data = {
                'context_items': processed_items,
                'total_items': len(processed_items),
                'retrieval_confidence': sum(item['relevance_score'] for item in processed_items) / len(processed_items) if processed_items else 0.0,
                'knowledge_coverage': self._calculate_knowledge_coverage(processed_items)
            }

            processing_time = time.time() - start_time

            self._update_stats(optimization_type, True)

            logger.info(f"知识检索完成: 第{context.chapter_id}章，检索到{len(processed_items)}条相关内容")

            return OptimizationResult(
                optimization_type=optimization_type,
                success=True,
                data=result_data,
                confidence=result_data['retrieval_confidence'],
                processing_time=processing_time
            )

        except Exception as e:
            self._update_stats(optimization_type, False)
            logger.error(f"知识检索失败: {e}")
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message=str(e)
            )

    def apply_template_engine(self, context: OptimizationContext) -> OptimizationResult:
        """应用模板引擎"""
        optimization_type = OptimizationType.TEMPLATE_ENGINE

        if not self._is_system_available('template_engine'):
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message="模板引擎不可用"
            )

        try:
            import time
            start_time = time.time()

            template_system = self.optimization_systems['template_engine']

            # 分析章节类型和推荐模板
            chapter_analysis = self._analyze_chapter_type(context)
            recommended_templates = template_system.recommend_templates(
                chapter_type=chapter_analysis['type'],
                word_count=context.word_count,
                scene_type=chapter_analysis['scene_type'],
                emotional_tone=chapter_analysis['emotional_tone']
            )

            result_data = {
                'chapter_type': chapter_analysis['type'],
                'recommended_templates': recommended_templates[:3],  # 限制数量
                'template_confidence': self._calculate_template_confidence(recommended_templates),
                'style_suggestions': self._generate_style_suggestions(chapter_analysis)
            }

            processing_time = time.time() - start_time

            self._update_stats(optimization_type, True)

            logger.info(f"模板引擎应用完成: 第{context.chapter_id}章，推荐{len(recommended_templates)}个模板")

            return OptimizationResult(
                optimization_type=optimization_type,
                success=True,
                data=result_data,
                confidence=result_data['template_confidence'],
                processing_time=processing_time
            )

        except Exception as e:
            self._update_stats(optimization_type, False)
            logger.error(f"模板引擎应用失败: {e}")
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message=str(e)
            )

    def apply_platform_adapter(self, context: OptimizationContext) -> OptimizationResult:
        """应用平台适配器"""
        optimization_type = OptimizationType.PLATFORM_ADAPTER

        if not self._is_system_available('tomato_adapter'):
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message="平台适配器不可用"
            )

        try:
            import time
            start_time = time.time()

            adapter_system = self.optimization_systems['tomato_adapter']

            # 分析平台适配需求
            platform_analysis = adapter_system.analyze_platform_requirements(
                chapter_id=context.chapter_id,
                target_word_count=context.word_count,
                content_type=context.content_type,
                target_platform="tomato"  # 可以配置不同平台
            )

            result_data = {
                'platform_strategy': platform_analysis.get('strategy', {}),
                'word_optimization': platform_analysis.get('word_optimization', {}),
                'style_adjustments': platform_analysis.get('style_adjustments', {}),
                'seo_suggestions': platform_analysis.get('seo_suggestions', []),
                'readability_score': platform_analysis.get('readability_score', 0.0)
            }

            processing_time = time.time() - start_time

            self._update_stats(optimization_type, True)

            logger.info(f"平台适配完成: 第{context.chapter_id}章")

            return OptimizationResult(
                optimization_type=optimization_type,
                success=True,
                data=result_data,
                confidence=0.7,
                processing_time=processing_time
            )

        except Exception as e:
            self._update_stats(optimization_type, False)
            logger.error(f"平台适配失败: {e}")
            return OptimizationResult(
                optimization_type=optimization_type,
                success=False,
                data={},
                confidence=0.0,
                error_message=str(e)
            )

    def apply_combined_optimization(
        self,
        context: OptimizationContext,
        enabled_optimizations: List[OptimizationType] = None
    ) -> Dict[str, OptimizationResult]:
        """应用组合优化策略"""
        if enabled_optimizations is None:
            enabled_optimizations = [
                OptimizationType.EMOTION_ENGINEERING,
                OptimizationType.KNOWLEDGE_RETRIEVAL,
                OptimizationType.TEMPLATE_ENGINE,
                OptimizationType.PLATFORM_ADAPTER
            ]

        results = {}

        for optimization_type in enabled_optimizations:
            try:
                if optimization_type == OptimizationType.EMOTION_ENGINEERING:
                    results[str(optimization_type.value)] = self.analyze_emotion_context(context)
                elif optimization_type == OptimizationType.KNOWLEDGE_RETRIEVAL:
                    results[str(optimization_type.value)] = self.retrieve_knowledge_context(context)
                elif optimization_type == OptimizationType.TEMPLATE_ENGINE:
                    results[str(optimization_type.value)] = self.apply_template_engine(context)
                elif optimization_type == OptimizationType.PLATFORM_ADAPTER:
                    results[str(optimization_type.value)] = self.apply_platform_adapter(context)

            except Exception as e:
                logger.error(f"应用优化 {optimization_type.value} 失败: {e}")
                results[str(optimization_type.value)] = OptimizationResult(
                    optimization_type=optimization_type,
                    success=False,
                    data={},
                    confidence=0.0,
                    error_message=str(e)
                )

        logger.info(f"组合优化完成: 第{context.chapter_id}章，应用了{len(enabled_optimizations)}种优化")
        return results

    def _is_system_available(self, system_name: str) -> bool:
        """检查优化系统是否可用"""
        return self.systems_available and system_name in self.optimization_systems

    def _extract_keywords(self, context: OptimizationContext) -> List[str]:
        """提取关键词"""
        # 基于上下文提取关键词
        keywords = []

        if context.custom_params:
            keywords.extend(context.custom_params.get('keywords', []))

        # 基于章节ID生成默认关键词
        chapter_type_keywords = {
            1: ["开始", "介绍", "世界观"],
            10: ["冲突", "转折", "发展"],
            20: ["高潮", "决战", "突破"],
            50: ["结局", "总结", "收尾"]
        }

        base_keywords = chapter_type_keywords.get(context.chapter_id, ["发展", "情节", "故事"])
        keywords.extend(base_keywords)

        return keywords[:5]  # 限制关键词数量

    def _detect_scene_type(self, context: OptimizationContext) -> str:
        """检测场景类型"""
        # 简单的场景类型检测
        if context.chapter_id <= 5:
            return "introduction"
        elif context.chapter_id <= 15:
            return "development"
        elif context.chapter_id <= 30:
            return "climax"
        else:
            return "resolution"

    def _calculate_emotion_trend(self, emotion_system) -> Dict[str, Any]:
        """计算情绪趋势"""
        try:
            if hasattr(emotion_system, 'emotional_metrics'):
                metrics = emotion_system.emotional_metrics
                return {
                    'trend': 'increasing' if metrics.current_value > metrics.previous_value else 'decreasing',
                    'volatility': getattr(metrics, 'volatility', 0.5),
                    'satisfaction_level': getattr(metrics, 'satisfaction_level', 0.7)
                }
        except:
            pass
        return {'trend': 'stable', 'volatility': 0.5, 'satisfaction_level': 0.7}

    def _analyze_chapter_type(self, context: OptimizationContext) -> Dict[str, Any]:
        """分析章节类型"""
        # 简单的章节类型分析
        if context.chapter_id == 1:
            return {
                'type': 'opening',
                'scene_type': 'introduction',
                'emotional_tone': 'neutral',
                'complexity': 'low'
            }
        elif context.chapter_id % 10 == 0:
            return {
                'type': 'milestone',
                'scene_type': 'climax',
                'emotional_tone': 'intense',
                'complexity': 'high'
            }
        else:
            return {
                'type': 'development',
                'scene_type': 'progression',
                'emotional_tone': 'moderate',
                'complexity': 'medium'
            }

    def _calculate_template_confidence(self, templates: List[Dict]) -> float:
        """计算模板置信度"""
        if not templates:
            return 0.0
        return sum(t.get('confidence', 0.5) for t in templates) / len(templates)

    def _generate_style_suggestions(self, chapter_analysis: Dict) -> List[str]:
        """生成风格建议"""
        suggestions = []

        if chapter_analysis['complexity'] == 'high':
            suggestions.append("注意控制章节复杂度，确保读者理解")

        if chapter_analysis['emotional_tone'] == 'intense':
            suggestions.append("加强情绪描写，提升读者代入感")

        if chapter_analysis['type'] == 'milestone':
            suggestions.append("突出重要转折点，强化情节张力")

        return suggestions

    def _calculate_knowledge_coverage(self, items: List[Dict]) -> float:
        """计算知识覆盖率"""
        if not items:
            return 0.0

        # 简单的覆盖率计算
        coverage_scores = [item.get('relevance_score', 0.5) for item in items]
        return sum(coverage_scores) / len(coverage_scores)

    def _update_stats(self, optimization_type: OptimizationType, success: bool) -> None:
        """更新优化统计"""
        self.optimization_stats['total_optimizations'] += 1

        type_key = str(optimization_type.value)
        if type_key not in self.optimization_stats['by_type']:
            self.optimization_stats['by_type'][type_key] = {
                'total': 0,
                'successful': 0,
                'failed': 0
            }

        self.optimization_stats['by_type'][type_key]['total'] += 1

        if success:
            self.optimization_stats['successful'] += 1
            self.optimization_stats['by_type'][type_key]['successful'] += 1
        else:
            self.optimization_stats['failed'] += 1
            self.optimization_stats['by_type'][type_key]['failed'] += 1

    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计"""
        total = self.optimization_stats['total_optimizations']
        if total == 0:
            return {
                **self.optimization_stats,
                'success_rate': 0.0,
                'by_type_success_rates': {}
            }

        success_rate = self.optimization_stats['successful'] / total * 100
        by_type_success_rates = {}

        for type_key, stats in self.optimization_stats['by_type'].items():
            if stats['total'] > 0:
                by_type_success_rates[type_key] = stats['successful'] / stats['total'] * 100

        return {
            **self.optimization_stats,
            'success_rate': round(success_rate, 2),
            'by_type_success_rates': {k: round(v, 2) for k, v in by_type_success_rates.items()}
        }

    def reset_stats(self) -> None:
        """重置优化统计"""
        self.optimization_stats = {
            'total_optimizations': 0,
            'successful': 0,
            'failed': 0,
            'by_type': {}
        }
        logger.info("优化统计已重置")