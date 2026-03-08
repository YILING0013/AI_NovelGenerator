# -*- coding: utf-8 -*-
"""
生成管线接口定义 - 模块化架构

该模块定义了小说生成系统的核心接口，实现：
1. 清晰的组件边界
2. 可替换的模块接口
3. 统一的数据流
4. 松耦合的架构
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum

import logging

logger = logging.getLogger(__name__)


class GenerationStage(Enum):
    """生成阶段枚举"""
    INITIALIZATION = "initialization"
    BLUEPRINT_GENERATION = "blueprint_generation"
    PROMPT_DRAFTING = "prompt_drafting"
    CHAPTER_GENERATION = "chapter_generation"
    QUALITY_CHECKING = "quality_checking"
    FINALIZATION = "finalization"


@dataclass
class GenerationContext:
    """生成上下文 - 在整个管线中传递"""
    # 基础配置
    project_path: str
    chapter_number: int
    total_chapters: int

    # LLM配置
    interface_format: str
    api_key: str
    base_url: str
    model_name: str
    temperature: float
    max_tokens: int
    timeout: int

    # 小说数据
    novel_architecture: Optional[str] = None
    chapter_directory: Optional[str] = None
    world_state: Optional[Dict[str, Any]] = None

    # 前后文
    previous_chapters: Optional[List[str]] = None
    next_chapter_summary: Optional[str] = None

    # 用户输入
    user_guidance: Optional[str] = None
    characters_involved: Optional[List[str]] = None
    scene_location: Optional[str] = None

    # 元数据
    metadata: Optional[Dict[str, Any]] = None

    def get_llm_config(self) -> Dict[str, Any]:
        """获取LLM配置字典"""
        return {
            "interface_format": self.interface_format,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout
        }


@dataclass
class GenerationResult:
    """生成结果 - 各阶段返回的数据"""
    success: bool
    stage: GenerationStage
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    logs: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "stage": self.stage.value,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "logs": self.logs
        }


@dataclass
class BlueprintData:
    """蓝图数据结构"""
    chapter_number: int
    chapter_title: str
    content: str  # 蓝图文本内容
    validation_report: Optional[Dict[str, Any]] = None


@dataclass
class PromptData:
    """提示词数据结构"""
    prompt_type: str  # draft, continuation, optimization
    content: str
    context: Optional[Dict[str, Any]] = None


@dataclass
class ChapterData:
    """章节数据结构"""
    chapter_number: int
    chapter_title: str
    content: str
    word_count: int
    quality_score: Optional[float] = None
    validation_report: Optional[Dict[str, Any]] = None


# ============== 组件接口定义 ==============

class LLMAdapter(ABC):
    """LLM适配器接口"""

    @abstractmethod
    def invoke(self, prompt: str, **kwargs) -> str:
        """
        调用LLM

        Args:
            prompt: 提示词
            **kwargs: 额外参数

        Returns:
            LLM响应
        """
        pass

    @abstractmethod
    def batch_invoke(self, prompts: List[str], **kwargs) -> List[str]:
        """
        批量调用LLM

        Args:
            prompts: 提示词列表
            **kwargs: 额外参数

        Returns:
            LLM响应列表
        """
        pass


class BlueprintGenerator(ABC):
    """蓝图生成器接口"""

    @abstractmethod
    def generate(
        self,
        context: GenerationContext
    ) -> BlueprintData:
        """
        生成章节蓝图

        Args:
            context: 生成上下文

        Returns:
            蓝图数据
        """
        pass


class PromptBuilder(ABC):
    """提示词构建器接口"""

    @abstractmethod
    def build_draft_prompt(
        self,
        context: GenerationContext,
        blueprint: BlueprintData
    ) -> PromptData:
        """
        构建草稿提示词

        Args:
            context: 生成上下文
            blueprint: 蓝图数据

        Returns:
            提示词数据
        """
        pass

    @abstractmethod
    def build_continuation_prompt(
        self,
        context: GenerationContext,
        previous_content: str
    ) -> PromptData:
        """
        构建续写提示词

        Args:
            context: 生成上下文
            previous_content: 前文内容

        Returns:
            提示词数据
        """
        pass


class ChapterGenerator(ABC):
    """章节生成器接口"""

    @abstractmethod
    def generate(
        self,
        context: GenerationContext,
        prompt: PromptData
    ) -> ChapterData:
        """
        生成章节内容

        Args:
            context: 生成上下文
            prompt: 提示词数据

        Returns:
            章节数据
        """
        pass


class QualityChecker(ABC):
    """质量检查器接口"""

    @abstractmethod
    def check(
        self,
        context: GenerationContext,
        chapter: ChapterData
    ) -> Dict[str, Any]:
        """
        检查章节质量

        Args:
            context: 生成上下文
            chapter: 章节数据

        Returns:
            质量检查报告
        """
        pass


class Finalizer(ABC):
    """最终处理接口"""

    @abstractmethod
    def finalize(
        self,
        context: GenerationContext,
        chapter: ChapterData,
        quality_report: Dict[str, Any]
    ) -> ChapterData:
        """
        最终处理章节

        Args:
            context: 生成上下文
            chapter: 章节数据
            quality_report: 质量检查报告

        Returns:
            处理后的章节数据
        """
        pass


class Validator(ABC):
    """验证器接口"""

    @abstractmethod
    def validate_blueprint(
        self,
        blueprint_text: str
    ) -> Dict[str, Any]:
        """
        验证蓝图格式

        Args:
            blueprint_text: 蓝图文本

        Returns:
            验证报告
        """
        pass

    @abstractmethod
    def validate_chapter(
        self,
        chapter_data: Dict[str, Any],
        chapter_number: int
    ) -> Dict[str, Any]:
        """
        验证章节数据

        Args:
            chapter_data: 章节数据
            chapter_number: 章节号

        Returns:
            验证报告
        """
        pass


# ============== 管线接口 ==============

class PipelineStage(ABC):
    """管线阶段基类"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"Pipeline.{name}")

    @abstractmethod
    def execute(
        self,
        context: GenerationContext,
        input_data: Any = None
    ) -> GenerationResult:
        """
        执行阶段

        Args:
            context: 生成上下文
            input_data: 输入数据

        Returns:
            生成结果
        """
        pass

    def pre_execute(self, context: GenerationContext):
        """执行前钩子"""
        self.logger.info(f"阶段 {self.name} 开始执行")

    def post_execute(
        self,
        context: GenerationContext,
        result: GenerationResult
    ):
        """执行后钩子"""
        if result.success:
            self.logger.info(f"阶段 {self.name} 执行成功")
        else:
            self.logger.error(f"阶段 {self.name} 执行失败: {result.error}")


class Pipeline(ABC):
    """生成管线接口"""

    def __init__(self, name: str):
        self.name = name
        self.stages: List[PipelineStage] = []
        self.logger = logging.getLogger(f"Pipeline.{name}")

    def add_stage(self, stage: PipelineStage):
        """添加阶段"""
        self.stages.append(stage)
        self.logger.info(f"添加阶段: {stage.name}")

    def execute(
        self,
        context: GenerationContext,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> GenerationResult:
        """
        执行管线

        Args:
            context: 生成上下文
            progress_callback: 进度回调函数

        Returns:
            最终生成结果
        """
        self.logger.info(f"管线 {self.name} 开始执行")

        last_result = None
        last_input = None

        for stage in self.stages:
            try:
                # 执行前钩子
                stage.pre_execute(context)

                # 调用进度回调
                if progress_callback:
                    progress_callback(f"执行阶段: {stage.name}")

                # 执行阶段
                result = stage.execute(context, last_input)

                # 执行后钩子
                stage.post_execute(context, result)

                # 检查是否成功
                if not result.success:
                    self.logger.error(f"管线在阶段 {stage.name} 失败")
                    return result

                # 传递结果到下一阶段
                last_result = result
                last_input = result.data

            except Exception as e:
                error_msg = f"阶段 {stage.name} 执行异常: {str(e)}"
                self.logger.error(error_msg, exc_info=True)

                return GenerationResult(
                    success=False,
                    stage=stage.name,
                    error=error_msg
                )

        self.logger.info(f"管线 {self.name} 执行完成")
        return last_result


# ============== 数据加载器接口 ==============

class DataLoader(ABC):
    """数据加载器接口"""

    @abstractmethod
    def load_architecture(self, path: str) -> str:
        """加载小说架构"""
        pass

    @abstractmethod
    def load_chapter_directory(self, path: str) -> str:
        """加载章节目录"""
        pass

    @abstractmethod
    def load_world_state(self, path: str) -> Dict[str, Any]:
        """加载世界状态"""
        pass

    @abstractmethod
    def load_previous_chapters(
        self,
        path: str,
        chapter_number: int,
        count: int = 3
    ) -> List[str]:
        """加载前几章内容"""
        pass


class DataSaver(ABC):
    """数据保存器接口"""

    @abstractmethod
    def save_blueprint(
        self,
        path: str,
        chapter_number: int,
        blueprint: BlueprintData
    ):
        """保存章节蓝图"""
        pass

    @abstractmethod
    def save_chapter(
        self,
        path: str,
        chapter: ChapterData
    ):
        """保存章节内容"""
        pass

    @abstractmethod
    def save_log(
        self,
        path: str,
        log_data: Dict[str, Any]
    ):
        """保存日志"""
        pass


# ============== 事件处理器接口 ==============

class EventHandler(ABC):
    """事件处理器接口"""

    @abstractmethod
    def on_stage_start(self, stage_name: str, context: GenerationContext):
        """阶段开始事件"""
        pass

    @abstractmethod
    def on_stage_complete(
        self,
        stage_name: str,
        result: GenerationResult,
        context: GenerationContext
    ):
        """阶段完成事件"""
        pass

    @abstractmethod
    def on_stage_error(
        self,
        stage_name: str,
        error: str,
        context: GenerationContext
    ):
        """阶段错误事件"""
        pass

    @abstractmethod
    def on_pipeline_complete(
        self,
        result: GenerationResult,
        context: GenerationContext
    ):
        """管线完成事件"""
        pass
