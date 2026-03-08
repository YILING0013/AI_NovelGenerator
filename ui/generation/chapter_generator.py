"""
Chapter Generator
章节生成器类

负责小说章节内容的核心生成逻辑，包括草稿生成、定稿处理、内容丰富等功能。
这是整个生成系统的心脏，整合了各种优化策略和质量控制措施。

主要功能:
- 章节草稿生成
- 章节定稿处理
- 内容自动丰富
- 字数控制和调整
- 生成进度管理
"""

import os
import logging
import time
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from pathlib import Path

from novel_generator import (
    generate_chapter_draft,
    finalize_chapter,
    enrich_chapter_text,
    build_chapter_prompt
)
from utils import save_string_to_txt
from .config_manager import ConfigurationManager
from .error_handler import ErrorHandler

# 预生成验证器
try:
    from novel_generator.pre_generation_validator import get_chapter_enhancement, validate_before_generation
    PRE_VALIDATOR_AVAILABLE = True
except ImportError:
    PRE_VALIDATOR_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ChapterGenerationRequest:
    """章节生成请求"""
    chapter_id: int
    word_count: int
    min_word_count: int
    auto_enrich: bool = True
    optimization_enabled: bool = True
    context: Dict[str, Any] = None

    def __post_init__(self):
        if self.context is None:
            self.context = {}


@dataclass
class ChapterGenerationResult:
    """章节生成结果"""
    chapter_id: int
    content: str
    draft_content: Optional[str] = None
    final_content: Optional[str] = None
    word_count: int = 0
    generation_time: float = 0.0
    success: bool = False
    error_message: Optional[str] = None
    optimization_applied: Dict[str, Any] = None

    def __post_init__(self):
        if self.optimization_applied is None:
            self.optimization_applied = {}


class ChapterGenerator:
    """章节生成器类 - 负责章节内容的核心生成逻辑"""

    def __init__(
        self,
        config_manager: ConfigurationManager,
        error_handler: ErrorHandler,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ):
        """
        初始化章节生成器

        Args:
            config_manager: 配置管理器
            error_handler: 错误处理器
            progress_callback: 进度回调函数
        """
        self.config_manager = config_manager
        self.error_handler = error_handler
        self.progress_callback = progress_callback

        # 生成统计
        self.generation_stats = {
            'total_generated': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0.0,
            'average_time': 0.0
        }
        
        # === 新增：质量增强器 ===
        self.quality_enhancer = None
        try:
            from quality.generation_enhancer import create_quality_enhancer
            filepath = self.config_manager.get_novel_parameters().get('filepath', '')
            if filepath:
                self.quality_enhancer = create_quality_enhancer(filepath)
                logger.info("质量增强器已加载")
        except Exception as e:
            logger.warning(f"质量增强器加载失败: {e}")

        logger.info("ChapterGenerator 初始化完成")

    def generate_chapter_batch(self, request: ChapterGenerationRequest) -> ChapterGenerationResult:
        """
        批量生成章节（单章节的完整生成流程）

        Args:
            request: 章节生成请求

        Returns:
            ChapterGenerationResult: 生成结果
        """
        start_time = time.time()
        logger.info(f"开始生成第{request.chapter_id}章")

        try:
            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 0)

            # 第一步：生成草稿
            draft_result = self._generate_draft(request)
            if not draft_result['success']:
                return self._create_error_result(
                    request.chapter_id,
                    draft_result['error'],
                    start_time
                )

            draft_content = draft_result['content']

            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 30)

            # 第二步：内容验证和优化
            optimized_content = self._optimize_content(draft_content, request)

            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 60)

            # 第三步：字数检查和自动扩写
            final_content = self._ensure_word_count(optimized_content, request)

            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 80)

            # 第四步：定稿处理
            finalized_content = self._finalize_chapter(final_content, request)

            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 90)

            # 第五步：保存章节
            self._save_chapter(request.chapter_id, finalized_content)

            # 更新进度
            if self.progress_callback:
                self.progress_callback(request.chapter_id, 100)

            # 统计信息
            generation_time = time.time() - start_time
            self._update_stats(True, generation_time)

            logger.info(f"第{request.chapter_id}章生成完成，耗时{generation_time:.2f}秒")

            return ChapterGenerationResult(
                chapter_id=request.chapter_id,
                content=finalized_content,
                draft_content=draft_content,
                final_content=finalized_content,
                word_count=len(finalized_content),
                generation_time=generation_time,
                success=True
            )

        except Exception as e:
            generation_time = time.time() - start_time
            self._update_stats(False, generation_time)

            # 使用错误处理器处理异常
            error_result = self.error_handler.handle_error(
                e,
                {
                    'chapter_id': request.chapter_id,
                    'word_count': request.word_count,
                    'operation': 'chapter_generation'
                }
            )

            return self._create_error_result(
                request.chapter_id,
                str(e),
                start_time,
                error_result
            )

    def _generate_draft(self, request: ChapterGenerationRequest) -> Dict[str, Any]:
        """生成章节草稿"""
        try:
            # 获取草稿配置
            draft_config = self.config_manager.get_draft_config()
            novel_params = self.config_manager.get_novel_parameters()
            
            # === 新增：质量增强分析 ===
            quality_enhancement_text = ""
            if self.quality_enhancer:
                try:
                    enhancement_result = self.quality_enhancer.analyze_before_generation(request.chapter_id)
                    quality_enhancement_text = self.quality_enhancer.get_prompt_enhancement(enhancement_result)
                    if quality_enhancement_text:
                        logger.info(f"第{request.chapter_id}章应用质量增强建议")
                except Exception as e:
                    logger.warning(f"质量增强分析失败: {e}")
            
            # === 新增：预生成验证器（整合分卷校正、修为约束、重大事件等） ===
            pre_validation_text = ""
            if PRE_VALIDATOR_AVAILABLE:
                try:
                    filepath = novel_params.get('filepath', '')
                    pre_validation_text = get_chapter_enhancement(filepath, request.chapter_id)
                    if pre_validation_text:
                        logger.info(f"第{request.chapter_id}章应用预生成验证增强")
                except Exception as e:
                    logger.warning(f"预生成验证失败: {e}")
            else:
                # 回退到单独的分卷校正
                try:
                    from prompts import get_volume_info
                    volume_info = get_volume_info(request.chapter_id)
                    pre_validation_text = f"\n\n{volume_info['position_text']}\n"
                    logger.info(f"第{request.chapter_id}章分卷定位: {volume_info['full_position']}")
                except Exception as e:
                    logger.warning(f"分卷定位获取失败: {e}")
            
            # 合并自定义提示词（质量增强 + 预生成验证）
            custom_prompt = quality_enhancement_text + pre_validation_text

            # 构建生成提示
            prompt = build_chapter_prompt(
                api_key=draft_config['api_key'],
                base_url=draft_config['base_url'],
                model_name=draft_config['model_name'],
                filepath=novel_params['filepath'],
                novel_number=request.chapter_id,
                word_number=request.word_count,
                temperature=draft_config['temperature'],
                user_guidance=novel_params['user_guidance'],
                characters_involved=novel_params['characters_involved'],
                key_items=novel_params['key_items'],
                scene_location=novel_params['scene_location'],
                time_constraint=novel_params['time_constraint'],
                embedding_api_key=self.config_manager.get_embedding_config().get('api_key', ''),
                embedding_url=self.config_manager.get_embedding_config().get('base_url', ''),
                embedding_interface_format=self.config_manager.get_embedding_config().get('interface_format', ''),
                embedding_model_name=self.config_manager.get_embedding_config().get('model_name', ''),
                embedding_retrieval_k=4,
                interface_format=draft_config['interface_format'],
                max_tokens=draft_config['max_tokens'],
                timeout=draft_config['timeout'],
                custom_prompt_text=custom_prompt
            )

            # 调用生成函数
            draft_content = generate_chapter_draft(
                api_key=draft_config['api_key'],
                base_url=draft_config['base_url'],
                model_name=draft_config['model_name'],
                filepath=novel_params['filepath'],
                novel_number=request.chapter_id,
                word_number=request.word_count,
                temperature=draft_config['temperature'],
                user_guidance=novel_params['user_guidance'],
                characters_involved=novel_params['characters_involved'],
                key_items=novel_params['key_items'],
                scene_location=novel_params['scene_location'],
                time_constraint=novel_params['time_constraint'],
                embedding_api_key=self.config_manager.get_embedding_config().get('api_key', ''),
                embedding_url=self.config_manager.get_embedding_config().get('base_url', ''),
                embedding_interface_format=self.config_manager.get_embedding_config().get('interface_format', ''),
                embedding_model_name=self.config_manager.get_embedding_config().get('model_name', ''),
                embedding_retrieval_k=4,
                interface_format=draft_config['interface_format'],
                max_tokens=draft_config['max_tokens'],
                timeout=draft_config['timeout'],
                custom_prompt_text=""
            )

            if not draft_content or not draft_content.strip():
                return {
                    'success': False,
                    'error': '生成的草稿内容为空',
                    'content': None
                }

            return {
                'success': True,
                'content': draft_content,
                'word_count': len(draft_content)
            }

        except Exception as e:
            logger.error(f"生成第{request.chapter_id}章草稿失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'content': None
            }

    def _optimize_content(self, content: str, request: ChapterGenerationRequest) -> str:
        """优化内容（应用各种优化策略）"""
        if not request.optimization_enabled:
            return content

        try:
            optimized_content = content

            # 这里可以集成各种优化策略
            # 比如：情绪工程、知识库检索、模板引擎等

            # 语言纯度检查和修复
            if self.config_manager.get_novel_parameters().get('language_purity_enabled', True):
                optimized_content = self._apply_language_purity(optimized_content)

            return optimized_content

        except Exception as e:
            logger.warning(f"内容优化失败，使用原始内容: {e}")
            return content

    def _apply_language_purity(self, content: str) -> str:
        """应用语言纯度检查"""
        # 这里可以集成语言纯度检查逻辑
        # 目前暂时返回原内容
        return content

    def _ensure_word_count(
        self,
        content: str,
        request: ChapterGenerationRequest
    ) -> str:
        """确保内容达到目标字数"""
        current_word_count = len(content)

        if current_word_count >= request.min_word_count:
            return content

        if not request.auto_enrich:
            logger.warning(f"第{request.chapter_id}章字数不足: {current_word_count}/{request.min_word_count}")
            return content

        try:
            # 尝试内容丰富
            enriched_content = enrich_chapter_text(
                content=content,
                target_word_count=request.word_count,
                current_word_count=current_word_count
            )

            if len(enriched_content) > current_word_count:
                logger.info(f"第{request.chapter_id}章内容丰富成功: {current_word_count} -> {len(enriched_content)}")
                return enriched_content
            else:
                logger.warning(f"第{request.chapter_id}章内容丰富失败")
                return content

        except Exception as e:
            logger.warning(f"第{request.chapter_id}章内容丰富出错: {e}")
            return content

    def _finalize_chapter(self, content: str, request: ChapterGenerationRequest) -> str:
        """章节定稿处理"""
        try:
            # 获取定稿配置
            final_config = self.config_manager.get_final_config()
            novel_params = self.config_manager.get_novel_parameters()

            # 调用定稿函数
            finalized_content = finalize_chapter(
                filepath=novel_params['filepath'],
                novel_number=request.chapter_id,
                chapter_content=content,
                interface_format=final_config['interface_format'],
                api_key=final_config['api_key'],
                base_url=final_config['base_url'],
                model_name=final_config['model_name'],
                temperature=final_config['temperature'],
                max_tokens=final_config['max_tokens'],
                timeout=final_config['timeout']
            )

            return finalized_content if finalized_content else content

        except Exception as e:
            logger.warning(f"第{request.chapter_id}章定稿失败，使用未定稿内容: {e}")
            return content

    def _save_chapter(self, chapter_id: int, content: str) -> None:
        """保存章节内容"""
        try:
            novel_params = self.config_manager.get_novel_parameters()
            filepath = novel_params['filepath']

            if not filepath:
                raise ValueError("文件路径未配置")

            # 确保目录存在
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # 保存文件
            save_string_to_txt(content, filepath)

            logger.info(f"第{chapter_id}章已保存到: {filepath}")

        except Exception as e:
            logger.error(f"保存第{chapter_id}章失败: {e}")
            raise

    def _create_error_result(
        self,
        chapter_id: int,
        error_message: str,
        start_time: float,
        error_result: Optional[Dict[str, Any]] = None
    ) -> ChapterGenerationResult:
        """创建错误结果"""
        return ChapterGenerationResult(
            chapter_id=chapter_id,
            content="",
            generation_time=time.time() - start_time,
            success=False,
            error_message=error_message
        )

    def _update_stats(self, success: bool, generation_time: float) -> None:
        """更新生成统计"""
        self.generation_stats['total_generated'] += 1
        self.generation_stats['total_time'] += generation_time

        if success:
            self.generation_stats['successful'] += 1
        else:
            self.generation_stats['failed'] += 1

        # 计算平均时间
        if self.generation_stats['total_generated'] > 0:
            self.generation_stats['average_time'] = (
                self.generation_stats['total_time'] / self.generation_stats['total_generated']
            )

    def get_generation_stats(self) -> Dict[str, Any]:
        """获取生成统计信息"""
        success_rate = 0.0
        if self.generation_stats['total_generated'] > 0:
            success_rate = (
                self.generation_stats['successful'] / self.generation_stats['total_generated'] * 100
            )

        return {
            **self.generation_stats,
            'success_rate': round(success_rate, 2)
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self.generation_stats = {
            'total_generated': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0.0,
            'average_time': 0.0
        }
        logger.info("生成统计已重置")

    def validate_generation_request(self, request: ChapterGenerationRequest) -> bool:
        """验证生成请求的有效性"""
        try:
            # 基本参数验证
            if request.chapter_id <= 0:
                logger.error("章节ID必须大于0")
                return False

            if request.word_count <= 0:
                logger.error("目标字数必须大于0")
                return False

            if request.min_word_count <= 0:
                logger.error("最小字数必须大于0")
                return False

            if request.min_word_count > request.word_count:
                logger.error("最小字数不能大于目标字数")
                return False

            # 配置验证
            try:
                self.config_manager.get_draft_config()
                self.config_manager.get_final_config()
                self.config_manager.get_novel_parameters()
            except Exception as e:
                logger.error(f"配置验证失败: {e}")
                return False

            return True

        except Exception as e:
            logger.error(f"请求验证失败: {e}")
            return False