"""
UI Generation Module
专门用于小说生成的各个组件模块

这个模块将原来的巨无霸类OptimizedGenerationHandler拆分为多个专门的类，
每个类负责单一职责，提高代码的可维护性和可测试性。

主要组件:
- ChapterGenerator: 章节生成核心逻辑
- ContentValidator: 内容验证和质量控制
- OptimizationEngine: 性能优化和处理
- ProgressReporter: 进度报告和状态管理
- ErrorHandler: 统一错误处理
- ConfigurationManager: 配置管理
"""

from .chapter_generator import ChapterGenerator, ChapterGenerationRequest, ChapterGenerationResult
from .content_validator import ContentValidator, ValidationLevel, ValidationReport
from .optimization_engine import OptimizationEngine, OptimizationType, OptimizationContext, OptimizationResult
from .progress_reporter import ProgressReporter, GenerationStatus, ProgressEvent
from .error_handler import ErrorHandler, ErrorSeverity, ErrorCategory
from .config_manager import ConfigurationManager

__all__ = [
    'ChapterGenerator',
    'ChapterGenerationRequest',
    'ChapterGenerationResult',
    'ContentValidator',
    'ValidationLevel',
    'ValidationReport',
    'OptimizationEngine',
    'OptimizationType',
    'OptimizationContext',
    'OptimizationResult',
    'ProgressReporter',
    'GenerationStatus',
    'ProgressEvent',
    'ErrorHandler',
    'ErrorSeverity',
    'ErrorCategory',
    'ConfigurationManager'
]