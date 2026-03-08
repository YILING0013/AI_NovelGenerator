# -*- coding: utf-8 -*-
"""
重构的生成管线实现

该模块实现了模块化的生成管线，替换原有的紧耦合代码。
"""
import logging
import json
import os
import re
from typing import Optional, Callable, Any, Dict, List

from .pipeline_interfaces import (
    GenerationContext,
    GenerationResult,
    BlueprintData,
    PromptData,
    ChapterData,
    GenerationStage,
    PipelineStage,
    Pipeline,
    LLMAdapter,
    BlueprintGenerator,
    PromptBuilder,
    ChapterGenerator,
    QualityChecker,
    Finalizer,
    Validator,
    DataLoader,
    DataSaver,
    EventHandler
)

from .schema_validator import SchemaValidator
from .error_handler import ErrorHandler, intelligent_retry

logger = logging.getLogger(__name__)


def _read_text_file(file_path: str) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ""


class LocalFileDataLoader(DataLoader):
    def load_architecture(self, path: str) -> str:
        from utils import resolve_architecture_file

        if not path:
            return ""
        architecture_file = resolve_architecture_file(path, prefer_active=False)
        return _read_text_file(architecture_file)

    def load_chapter_directory(self, path: str) -> str:
        if not path:
            return ""
        directory_file = os.path.join(path, "Novel_directory.txt")
        return _read_text_file(directory_file)

    def load_world_state(self, path: str) -> Dict[str, Any]:
        if not path:
            return {}
        world_state_file = os.path.join(path, "world_state.json")
        if not os.path.exists(world_state_file):
            return {}
        try:
            with open(world_state_file, 'r', encoding='utf-8') as file:
                loaded = json.load(file)
            return loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def load_previous_chapters(self, path: str, chapter_number: int, count: int = 3) -> List[str]:
        if not path or chapter_number <= 1 or count <= 0:
            return []

        chapters_dir = os.path.join(path, "chapters")
        start_chapter = max(1, chapter_number - count)
        result: List[str] = []

        for index in range(start_chapter, chapter_number):
            chapter_file = os.path.join(chapters_dir, f"chapter_{index}.txt")
            chapter_text = _read_text_file(chapter_file).strip()
            if chapter_text:
                result.append(chapter_text)

        return result


class LocalFileDataSaver(DataSaver):
    def save_blueprint(self, path: str, chapter_number: int, blueprint: BlueprintData):
        if not path:
            return
        blueprint_dir = os.path.join(path, "blueprints")
        os.makedirs(blueprint_dir, exist_ok=True)
        blueprint_file = os.path.join(blueprint_dir, f"chapter_{chapter_number}.txt")
        with open(blueprint_file, 'w', encoding='utf-8') as file:
            file.write(blueprint.content)

    def save_chapter(self, path: str, chapter: ChapterData):
        if not path:
            return
        chapter_dir = os.path.join(path, "chapters")
        os.makedirs(chapter_dir, exist_ok=True)
        chapter_file = os.path.join(chapter_dir, f"chapter_{chapter.chapter_number}.txt")
        with open(chapter_file, 'w', encoding='utf-8') as file:
            file.write(chapter.content)

    def save_log(self, path: str, log_data: Dict[str, Any]):
        if not path:
            return
        log_file = os.path.join(path, "pipeline_log.json")
        try:
            existing_logs = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as file:
                    loaded = json.load(file)
                if isinstance(loaded, list):
                    existing_logs = loaded
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            existing_logs = []

        existing_logs.append(log_data)
        with open(log_file, 'w', encoding='utf-8') as file:
            json.dump(existing_logs, file, ensure_ascii=False, indent=2)


class LoggingEventHandler(EventHandler):
    def __init__(self, event_logger: Optional[logging.Logger] = None):
        self._logger = event_logger or logging.getLogger("Pipeline.Events")

    def on_stage_start(self, stage_name: str, context: GenerationContext):
        self._logger.info("阶段开始: %s (chapter=%s)", stage_name, context.chapter_number)

    def on_stage_complete(self, stage_name: str, result: GenerationResult, context: GenerationContext):
        self._logger.info(
            "阶段完成: %s (chapter=%s, success=%s)",
            stage_name,
            context.chapter_number,
            result.success,
        )

    def on_stage_error(self, stage_name: str, error: str, context: GenerationContext):
        self._logger.error("阶段失败: %s (chapter=%s) %s", stage_name, context.chapter_number, error)

    def on_pipeline_complete(self, result: GenerationResult, context: GenerationContext):
        self._logger.info("管线结束: chapter=%s success=%s", context.chapter_number, result.success)


class RuntimeValidatorAdapter(Validator):
    def __init__(self, validator: SchemaValidator):
        self._validator = validator

    def validate_blueprint(self, blueprint_text: str) -> Dict[str, Any]:
        return self._validator.validate_blueprint_format(blueprint_text)

    def validate_chapter(self, chapter_data: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
        report = self._validator.validate_chapter_directory_entry(chapter_data, chapter_number)
        return {
            "is_valid": report.is_valid,
            "errors": report.errors,
            "warnings": report.warnings,
            "suggestions": report.suggestions,
        }


class RuntimeBlueprintGenerator(BlueprintGenerator):
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def generate(self, context: GenerationContext) -> BlueprintData:
        from chapter_directory_parser import load_chapter_info
        from novel_generator.blueprint import Strict_Chapter_blueprint_generate

        directory_file = os.path.join(context.project_path, "Novel_directory.txt")
        directory_text = _read_text_file(directory_file)

        if not directory_text.strip():
            Strict_Chapter_blueprint_generate(
                interface_format=context.interface_format,
                api_key=context.api_key,
                base_url=context.base_url,
                llm_model=context.model_name,
                filepath=context.project_path,
                number_of_chapters=max(context.total_chapters, context.chapter_number),
                user_guidance=context.user_guidance or "",
                temperature=context.temperature,
                max_tokens=context.max_tokens,
                timeout=context.timeout,
                batch_size=1,
                auto_optimize=False,
                optimize_per_batch=False,
            )
            directory_text = _read_text_file(directory_file)

        chapter_info = {}
        if directory_text.strip():
            loaded = load_chapter_info(
                context.project_path,
                context.chapter_number,
                blueprint_text_fallback=directory_text,
            )
            if isinstance(loaded, dict):
                chapter_info = loaded

        chapter_title = str(chapter_info.get("chapter_title") or f"第{context.chapter_number}章")
        chapter_summary = str(chapter_info.get("chapter_summary") or chapter_info.get("chapter_purpose") or "")
        blueprint_content = (
            f"第{context.chapter_number}章 - {chapter_title}\n"
            f"chapter_summary: {chapter_summary}\n"
            f"chapter_role: {chapter_info.get('chapter_role', '')}\n"
            f"suspense_level: {chapter_info.get('suspense_level', '中等')}"
        )

        return BlueprintData(
            chapter_number=context.chapter_number,
            chapter_title=chapter_title,
            content=blueprint_content,
        )


class RuntimePromptBuilder(PromptBuilder):
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def build_draft_prompt(self, context: GenerationContext, blueprint: BlueprintData) -> PromptData:
        from novel_generator.chapter import build_chapter_prompt

        characters_text = context.characters_involved
        if isinstance(characters_text, list):
            characters_text = "、".join([str(item) for item in characters_text if item])
        elif not isinstance(characters_text, str):
            characters_text = ""

        prompt = build_chapter_prompt(
            api_key=context.api_key,
            base_url=context.base_url,
            model_name=context.model_name,
            filepath=context.project_path,
            novel_number=context.chapter_number,
            word_number=int(self._config.get('word_number', 3000)),
            temperature=context.temperature,
            user_guidance=context.user_guidance or "",
            characters_involved=characters_text,
            key_items=str(self._config.get('key_items', '')),
            scene_location=context.scene_location or "",
            time_constraint=str(self._config.get('time_constraint', '')),
            embedding_api_key=str(self._config.get('embedding_api_key', '')),
            embedding_url=str(self._config.get('embedding_url', '')),
            embedding_interface_format=str(self._config.get('embedding_interface_format', 'OpenAI')),
            embedding_model_name=str(self._config.get('embedding_model_name', 'text-embedding-ada-002')),
            embedding_retrieval_k=int(self._config.get('embedding_retrieval_k', 2)),
            interface_format=context.interface_format,
            max_tokens=context.max_tokens,
            timeout=context.timeout,
            next_chapter_summary=context.next_chapter_summary or "",
        )
        return PromptData(prompt_type="draft", content=prompt, context={"blueprint": blueprint.content})

    def build_continuation_prompt(self, context: GenerationContext, previous_content: str) -> PromptData:
        return PromptData(
            prompt_type="continuation",
            content=f"请续写以下内容，保持风格一致：\n\n{previous_content}",
            context={"chapter_number": context.chapter_number},
        )


class RuntimeChapterGenerator(ChapterGenerator):
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def generate(self, context: GenerationContext, prompt: PromptData) -> ChapterData:
        from novel_generator.chapter import generate_chapter_draft
        from novel_generator.wordcount_utils import count_chapter_words

        characters_text = context.characters_involved
        if isinstance(characters_text, list):
            characters_text = "、".join([str(item) for item in characters_text if item])
        elif not isinstance(characters_text, str):
            characters_text = ""

        chapter_content = generate_chapter_draft(
            api_key=context.api_key,
            base_url=context.base_url,
            model_name=context.model_name,
            filepath=context.project_path,
            novel_number=context.chapter_number,
            word_number=int(self._config.get('word_number', 3000)),
            temperature=context.temperature,
            user_guidance=context.user_guidance or "",
            characters_involved=characters_text,
            key_items=str(self._config.get('key_items', '')),
            scene_location=context.scene_location or "",
            time_constraint=str(self._config.get('time_constraint', '')),
            embedding_api_key=str(self._config.get('embedding_api_key', '')),
            embedding_url=str(self._config.get('embedding_url', '')),
            embedding_interface_format=str(self._config.get('embedding_interface_format', 'OpenAI')),
            embedding_model_name=str(self._config.get('embedding_model_name', 'text-embedding-ada-002')),
            embedding_retrieval_k=int(self._config.get('embedding_retrieval_k', 2)),
            interface_format=context.interface_format,
            max_tokens=context.max_tokens,
            timeout=context.timeout,
            custom_prompt_text=prompt.content,
            custom_prompt_is_complete=True,
        )

        first_line = chapter_content.splitlines()[0].strip() if chapter_content else ""
        title_match = re.match(r'^第\s*\d+\s*章\s+(.+)$', first_line)
        chapter_title = title_match.group(1).strip() if title_match else f"第{context.chapter_number}章"
        chapter_stats = count_chapter_words(chapter_content)

        return ChapterData(
            chapter_number=context.chapter_number,
            chapter_title=chapter_title,
            content=chapter_content,
            word_count=int(chapter_stats.get('chinese_chars', len(chapter_content))),
        )


class RuntimeQualityChecker(QualityChecker):
    def check(self, context: GenerationContext, chapter: ChapterData) -> Dict[str, Any]:
        target_words = max(1, int(context.metadata.get('target_word_count', 3000) if context.metadata else 3000))
        ratio = min(chapter.word_count / target_words, 1.0)
        overall_score = max(0.0, min(1.0, 0.7 + ratio * 0.3))
        return {
            "overall_score": overall_score,
            "word_count": chapter.word_count,
            "target_word_count": target_words,
        }


class RuntimeFinalizer(Finalizer):
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def finalize(self, context: GenerationContext, chapter: ChapterData, quality_report: Dict[str, Any]) -> ChapterData:
        from novel_generator.finalization import finalize_chapter
        from novel_generator.wordcount_utils import count_chapter_words

        finalize_chapter(
            novel_number=context.chapter_number,
            word_number=int(self._config.get('word_number', 3000)),
            api_key=context.api_key,
            base_url=context.base_url,
            model_name=context.model_name,
            temperature=context.temperature,
            filepath=context.project_path,
            embedding_api_key=str(self._config.get('embedding_api_key', '')),
            embedding_url=str(self._config.get('embedding_url', '')),
            embedding_interface_format=str(self._config.get('embedding_interface_format', 'OpenAI')),
            embedding_model_name=str(self._config.get('embedding_model_name', 'text-embedding-ada-002')),
            interface_format=context.interface_format,
            max_tokens=context.max_tokens,
            timeout=context.timeout,
        )

        chapter_file = os.path.join(context.project_path, "chapters", f"chapter_{context.chapter_number}.txt")
        finalized_content = _read_text_file(chapter_file).strip() or chapter.content
        chapter_stats = count_chapter_words(finalized_content)

        return ChapterData(
            chapter_number=chapter.chapter_number,
            chapter_title=chapter.chapter_title,
            content=finalized_content,
            word_count=int(chapter_stats.get('chinese_chars', chapter.word_count)),
            quality_score=chapter.quality_score,
            validation_report=chapter.validation_report,
        )


# ============== LLM适配器实现 ==============

class DefaultLLMAdapter(LLMAdapter):
    """默认的LLM适配器实现"""

    def __init__(self, adapter):
        """
        初始化适配器

        Args:
            adapter: 现有的LLM适配器实例
        """
        self._adapter = adapter

    @intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str, **kwargs) -> str:
        """调用LLM"""
        return self._adapter.invoke(prompt, **kwargs)

    def batch_invoke(self, prompts: List[str], **kwargs) -> List[str]:
        """批量调用LLM"""
        results = []
        for prompt in prompts:
            result = self.invoke(prompt, **kwargs)
            results.append(result)
        return results


# ============== 蓝图生成阶段 ==============

class BlueprintGenerationStage(PipelineStage):
    """蓝图生成阶段"""

    def __init__(self, generator: BlueprintGenerator, validator: Validator):
        super().__init__("BlueprintGeneration")
        self.generator = generator
        self.validator = validator

    def execute(
        self,
        context: GenerationContext,
        input_data: Any = None
    ) -> GenerationResult:
        """
        执行蓝图生成

        Args:
            context: 生成上下文
            input_data: 输入数据（未使用）

        Returns:
            生成结果
        """
        try:
            # 1. 生成蓝图
            self.logger.info(f"开始生成第 {context.chapter_number} 章的蓝图")
            blueprint = self.generator.generate(context)

            # 2. 验证蓝图
            self.logger.info("验证蓝图格式")
            validation_report = self.validator.validate_blueprint(blueprint.content)

            # 3. 检查验证结果
            if not validation_report.get("is_valid", True):
                error_msg = f"蓝图验证失败: {validation_report.get('errors', [])}"
                self.logger.error(error_msg)
                return GenerationResult(
                    success=False,
                    stage=GenerationStage.BLUEPRINT_GENERATION,
                    error=error_msg,
                    metadata={"validation_report": validation_report}
                )

            # 4. 保存验证报告
            blueprint.validation_report = validation_report

            self.logger.info(f"蓝图生成成功: {blueprint.chapter_title}")

            return GenerationResult(
                success=True,
                stage=GenerationStage.BLUEPRINT_GENERATION,
                data=blueprint,
                metadata={"validation_report": validation_report}
            )

        except (ValueError, TypeError, RuntimeError, OSError, json.JSONDecodeError) as e:
            error_msg = f"蓝图生成异常: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return GenerationResult(
                success=False,
                stage=GenerationStage.BLUEPRINT_GENERATION,
                error=error_msg
            )


# ============== 提示词构建阶段 ==============

class PromptBuildingStage(PipelineStage):
    """提示词构建阶段"""

    def __init__(self, builder: PromptBuilder):
        super().__init__("PromptBuilding")
        self.builder = builder

    def execute(
        self,
        context: GenerationContext,
        input_data: Any = None
    ) -> GenerationResult:
        """
        执行提示词构建

        Args:
            context: 生成上下文
            input_data: 蓝图数据

        Returns:
            生成结果
        """
        try:
            blueprint = input_data
            if not isinstance(blueprint, BlueprintData):
                raise ValueError(f"输入数据类型错误，期望 BlueprintData，实际 {type(input_data)}")

            self.logger.info(f"构建第 {context.chapter_number} 章的提示词")

            # 构建提示词
            prompt_data = self.builder.build_draft_prompt(context, blueprint)

            self.logger.info(f"提示词构建成功，长度: {len(prompt_data.content)}")

            return GenerationResult(
                success=True,
                stage=GenerationStage.PROMPT_DRAFTING,
                data=prompt_data,
                metadata={"prompt_length": len(prompt_data.content)}
            )

        except (ValueError, TypeError, RuntimeError) as e:
            error_msg = f"提示词构建异常: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return GenerationResult(
                success=False,
                stage=GenerationStage.PROMPT_DRAFTING,
                error=error_msg
            )


# ============== 章节生成阶段 ==============

class ChapterGenerationStage(PipelineStage):
    """章节生成阶段"""

    def __init__(
        self,
        generator: ChapterGenerator,
        validator: Validator,
        quality_checker: QualityChecker,
        max_retries: int = 3
    ):
        super().__init__("ChapterGeneration")
        self.generator = generator
        self.validator = validator
        self.quality_checker = quality_checker
        self.max_retries = max_retries

    @intelligent_retry(max_attempts=3)
    def execute(
        self,
        context: GenerationContext,
        input_data: Any = None
    ) -> GenerationResult:
        """
        执行章节生成

        Args:
            context: 生成上下文
            input_data: 提示词数据

        Returns:
            生成结果
        """
        try:
            prompt_data = input_data
            if not isinstance(prompt_data, PromptData):
                raise ValueError(f"输入数据类型错误，期望 PromptData，实际 {type(input_data)}")

            self.logger.info(f"开始生成第 {context.chapter_number} 章内容")

            # 1. 生成章节
            chapter = self.generator.generate(context, prompt_data)

            # 2. 验证章节数据
            self.logger.info("验证章节数据")
            chapter_dict = {
                "chapter_number": chapter.chapter_number,
                "chapter_title": chapter.chapter_title,
                "chapter_summary": chapter.content[:500] + "...",
                "target_word_count": chapter.word_count
            }
            validation_report = self.validator.validate_chapter(
                chapter_dict,
                context.chapter_number
            )

            # 3. 质量检查
            self.logger.info("执行质量检查")
            quality_report = self.quality_checker.check(context, chapter)

            # 4. 记录质量分数
            chapter.quality_score = quality_report.get("overall_score", 0.0)
            chapter.validation_report = validation_report

            self.logger.info(
                f"章节生成成功，字数: {chapter.word_count}, "
                f"质量分数: {chapter.quality_score}"
            )

            return GenerationResult(
                success=True,
                stage=GenerationStage.CHAPTER_GENERATION,
                data=chapter,
                metadata={
                    "validation_report": validation_report,
                    "quality_report": quality_report
                }
            )

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            error_msg = f"章节生成异常: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return GenerationResult(
                success=False,
                stage=GenerationStage.CHAPTER_GENERATION,
                error=error_msg
            )


# ============== 最终处理阶段 ==============

class FinalizationStage(PipelineStage):
    """最终处理阶段"""

    def __init__(self, finalizer: Finalizer, saver: DataSaver):
        super().__init__("Finalization")
        self.finalizer = finalizer
        self.saver = saver

    def execute(
        self,
        context: GenerationContext,
        input_data: Any = None
    ) -> GenerationResult:
        """
        执行最终处理

        Args:
            context: 生成上下文
            input_data: 章节数据

        Returns:
            生成结果
        """
        try:
            chapter = input_data
            if not isinstance(chapter, ChapterData):
                raise ValueError(f"输入数据类型错误，期望 ChapterData，实际 {type(input_data)}")

            self.logger.info(f"最终处理第 {context.chapter_number} 章")

            # 1. 最终处理
            quality_report = chapter.validation_report or {}
            finalized_chapter = self.finalizer.finalize(
                context,
                chapter,
                quality_report
            )

            # 2. 保存章节
            self.logger.info(f"保存第 {context.chapter_number} 章")
            self.saver.save_chapter(context.project_path, finalized_chapter)

            self.logger.info(f"最终处理完成: {finalized_chapter.chapter_title}")

            return GenerationResult(
                success=True,
                stage=GenerationStage.FINALIZATION,
                data=finalized_chapter
            )

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            error_msg = f"最终处理异常: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return GenerationResult(
                success=False,
                stage=GenerationStage.FINALIZATION,
                error=error_msg
            )


# ============== 完整生成管线 ==============

class NovelGenerationPipeline(Pipeline):
    """完整的小说生成管线"""

    def __init__(
        self,
        name: str = "NovelGeneration",
        data_loader: Optional[DataLoader] = None,
        data_saver: Optional[DataSaver] = None,
        event_handler: Optional[EventHandler] = None
    ):
        """
        初始化管线

        Args:
            name: 管线名称
            data_loader: 数据加载器
            data_saver: 数据保存器
            event_handler: 事件处理器
        """
        super().__init__(name)
        self.data_loader = data_loader
        self.data_saver = data_saver
        self.event_handler = event_handler
        self.logger = logging.getLogger(f"Pipeline.{name}")

    def execute_single_chapter(
        self,
        chapter_number: int,
        config: Dict[str, Any],
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> GenerationResult:
        """
        执行单章生成

        Args:
            chapter_number: 章节号
            config: 配置字典
            progress_callback: 进度回调函数

        Returns:
            生成结果
        """
        self.logger.info(f"开始生成第 {chapter_number} 章")

        # 1. 构建生成上下文
        context = self._build_context(chapter_number, config)

        # 2. 触发事件
        if self.event_handler:
            self.event_handler.on_stage_start("Pipeline", context)

        # 3. 执行管线
        result = self.execute(context, progress_callback)

        # 4. 触发完成事件
        if self.event_handler:
            self.event_handler.on_pipeline_complete(result, context)

        return result

    def _build_context(
        self,
        chapter_number: int,
        config: Dict[str, Any]
    ) -> GenerationContext:
        """
        构建生成上下文

        Args:
            chapter_number: 章节号
            config: 配置字典

        Returns:
            生成上下文
        """
        project_path = str(config.get('project_path') or '')

        # 加载必要的数据
        if self.data_loader:
            novel_architecture = self.data_loader.load_architecture(project_path)
            chapter_directory = self.data_loader.load_chapter_directory(project_path)
            world_state = self.data_loader.load_world_state(project_path)
            previous_chapters = self.data_loader.load_previous_chapters(project_path, chapter_number, count=3)
        else:
            novel_architecture = None
            chapter_directory = None
            world_state = None
            previous_chapters = None

        next_chapter_summary = None
        if chapter_directory:
            try:
                from chapter_directory_parser import load_chapter_info

                next_chapter_info = load_chapter_info(
                    project_path,
                    chapter_number + 1,
                    blueprint_text_fallback=chapter_directory,
                )
                if isinstance(next_chapter_info, dict):
                    candidate_summary = (
                        next_chapter_info.get('chapter_summary')
                        or next_chapter_info.get('chapter_purpose')
                    )
                    next_chapter_summary = str(candidate_summary) if candidate_summary else None
            except (ValueError, TypeError, AttributeError):
                next_chapter_summary = None

        return GenerationContext(
            project_path=project_path,
            chapter_number=chapter_number,
            total_chapters=int(config.get('num_chapters', 100) or 100),
            interface_format=str(config.get('interface_format', 'openai') or 'openai'),
            api_key=str(config.get('api_key', '') or ''),
            base_url=str(config.get('base_url', '') or ''),
            model_name=str(config.get('model_name', 'gpt-3.5-turbo') or 'gpt-3.5-turbo'),
            temperature=float(config.get('temperature', 0.8) or 0.8),
            max_tokens=int(config.get('max_tokens', 4000) or 4000),
            timeout=int(config.get('timeout', 60) or 60),
            novel_architecture=novel_architecture,
            chapter_directory=chapter_directory,
            world_state=world_state,
            previous_chapters=previous_chapters,
            next_chapter_summary=next_chapter_summary,
            user_guidance=config.get('user_guidance'),
            characters_involved=config.get('characters_involved'),
            scene_location=config.get('scene_location'),
            metadata={
                'target_word_count': int(config.get('word_number', 3000) or 3000),
            },
        )


# ============== 工厂类 ==============

class PipelineFactory:
    """管线工厂 - 创建管线实例"""

    @staticmethod
    def create_default_pipeline(
        config: Dict[str, Any],
        error_handler: Optional[ErrorHandler] = None
    ) -> NovelGenerationPipeline:
        """
        创建默认管线

        Args:
            config: 配置字典
            error_handler: 错误处理器

        Returns:
            小说生成管线
        """
        validator = SchemaValidator(strict_mode=True)
        validator_adapter = RuntimeValidatorAdapter(validator)

        data_loader = LocalFileDataLoader()
        data_saver = LocalFileDataSaver()
        event_handler = LoggingEventHandler(logger)

        blueprint_generator = RuntimeBlueprintGenerator(config)
        prompt_builder = RuntimePromptBuilder(config)
        chapter_generator = RuntimeChapterGenerator(config)
        quality_checker = RuntimeQualityChecker()
        finalizer = RuntimeFinalizer(config)

        # 创建管线
        pipeline = NovelGenerationPipeline(
            name="NovelGeneration",
            data_loader=data_loader,
            data_saver=data_saver,
            event_handler=event_handler,
        )

        pipeline.add_stage(BlueprintGenerationStage(blueprint_generator, validator_adapter))
        pipeline.add_stage(PromptBuildingStage(prompt_builder))
        pipeline.add_stage(ChapterGenerationStage(chapter_generator, validator_adapter, quality_checker))
        pipeline.add_stage(FinalizationStage(finalizer, data_saver))

        return pipeline
