# -*- coding: utf-8 -*-
"""
错误处理增强模块 - 统一的错误处理和重试机制

该模块提供：
1. 统一的异常类型
2. 智能重试机制
3. 详细的错误日志
4. 优雅的错误恢复
"""
import logging
import time
from typing import Callable, Type, Tuple, Any, Optional
from functools import wraps
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(Enum):
    """错误分类"""
    API_ERROR = "API错误"
    VALIDATION_ERROR = "验证错误"
    PARSE_ERROR = "解析错误"
    NETWORK_ERROR = "网络错误"
    TIMEOUT_ERROR = "超时错误"
    UNKNOWN_ERROR = "未知错误"


class NovelGenerationError(Exception):
    """小说生成基础异常"""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        chapter_number: Optional[int] = None,
        context: Optional[dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.chapter_number = chapter_number
        self.context = context or {}


class APITimeoutError(NovelGenerationError):
    """API超时错误"""

    def __init__(self, message: str, timeout: float, chapter_number: Optional[int] = None):
        super().__init__(
            message,
            category=ErrorCategory.TIMEOUT_ERROR,
            chapter_number=chapter_number,
            context={"timeout": timeout}
        )
        self.timeout = timeout


class APIRateLimitError(NovelGenerationError):
    """API限流错误"""

    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(
            message,
            category=ErrorCategory.API_ERROR,
            context={"retry_after": retry_after}
        )
        self.retry_after = retry_after


class ValidationError(NovelGenerationError):
    """验证错误"""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION_ERROR,
            context={"field": field}
        )
        self.field = field


class ParseError(NovelGenerationError):
    """解析错误"""

    def __init__(
        self,
        message: str,
        content_preview: Optional[str] = None,
        line_number: Optional[int] = None
    ):
        super().__init__(
            message,
            category=ErrorCategory.PARSE_ERROR,
            context={
                "line_number": line_number,
                "content_preview": content_preview[:100] if content_preview else None
            }
        )
        self.line_number = line_number


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


def intelligent_retry(
    max_attempts: int = 3,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
    log_errors: bool = True
):
    """
    智能重试装饰器

    根据错误类型采用不同的重试策略：
    - API限流：指数退避
    - 网络错误：短延迟重试
    - 验证错误：不重试
    - 超时错误：增加超时时间重试

    Args:
        max_attempts: 最大重试次数
        retry_on: 需要重试的异常类型
        log_errors: 是否记录错误日志
    """
    config = RetryConfig(max_attempts=max_attempts)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e

                    # 判断是否应该重试
                    if isinstance(e, ValidationError):
                        # 验证错误不重试
                        if log_errors:
                            logging.error(f"验证错误，不重试: {e}")
                        raise

                    # 计算延迟时间
                    if attempt < config.max_attempts - 1:
                        delay = config.base_delay * (config.exponential_base ** attempt)

                        # 添加随机抖动
                        if config.jitter:
                            import random
                            delay = delay * (0.5 + random.random())

                        # 限制最大延迟
                        delay = min(delay, config.max_delay)

                        # 记录错误
                        if log_errors:
                            logging.warning(
                                f"{func.__name__} 第 {attempt + 1} 次失败: {str(e)[:100]}"
                            )
                            logging.info(f"等待 {delay:.2f} 秒后重试...")

                        time.sleep(delay)

            # 所有重试都失败
            if log_errors:
                logging.error(f"{func.__name__} 所有重试失败，已达到最大次数: {config.max_attempts}")

            raise last_exception

        return wrapper
    return decorator


class ErrorHandler:
    """统一错误处理器"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初始化错误处理器

        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self.error_counts = {}
        self.recent_errors = []

    def handle_exception(
        self,
        exception: Exception,
        context: Optional[dict] = None,
        reraise: bool = True
    ) -> Optional[dict]:
        """
        处理异常

        Args:
            exception: 异常对象
            context: 额外上下文信息
            reraise: 是否重新抛出异常

        Returns:
            错误信息字典（如果reraise=False）
        """
        # 记录错误统计
        error_type = type(exception).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        # 记录最近的错误
        error_info = {
            "type": error_type,
            "message": str(exception)[:200],
            "timestamp": time.time(),
            "context": context
        }
        self.recent_errors.append(error_info)

        # 只保留最近100个错误
        if len(self.recent_errors) > 100:
            self.recent_errors = self.recent_errors[-100:]

        # 根据异常类型选择日志级别
        if isinstance(exception, (APITimeoutError, APIRateLimitError)):
            self.logger.warning(f"API错误: {exception}")
        elif isinstance(exception, ValidationError):
            self.logger.error(f"验证错误: {exception}")
        elif isinstance(exception, ParseError):
            self.logger.error(f"解析错误: {exception}")
        else:
            self.logger.error(f"未知错误: {exception}", exc_info=True)

        # 输出详细错误信息
        if context:
            self.logger.debug(f"错误上下文: {context}")

        if isinstance(exception, NovelGenerationError) and exception.context:
            self.logger.debug(f"异常上下文: {exception.context}")

        if reraise:
            raise exception

        return error_info

    def get_error_statistics(self) -> dict:
        """
        获取错误统计信息

        Returns:
            错误统计字典
        """
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_counts": self.error_counts,
            "recent_errors_count": len(self.recent_errors),
            "unique_error_types": len(self.error_counts)
        }

    def get_recent_errors(self, limit: int = 10) -> list:
        """
        获取最近的错误

        Args:
            limit: 返回的错误数量限制

        Returns:
            错误列表
        """
        return self.recent_errors[-limit:]

    def reset_statistics(self):
        """重置错误统计"""
        self.error_counts = {}
        self.recent_errors = []

    def has_error_pattern(self, pattern: str) -> bool:
        """
        检查是否出现特定的错误模式

        Args:
            pattern: 要搜索的错误模式

        Returns:
            是否找到匹配的错误
        """
        for error in self.recent_errors:
            if pattern.lower() in error['message'].lower():
                return True
        return False


# 全局错误处理器实例
_global_error_handler = None


def get_global_error_handler() -> ErrorHandler:
    """获取全局错误处理器"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def safe_execute(
    func: Callable,
    *args,
    error_handler: Optional[ErrorHandler] = None,
    default_return: Any = None,
    **kwargs
) -> Any:
    """
    安全执行函数，捕获所有异常

    Args:
        func: 要执行的函数
        *args: 函数参数
        error_handler: 错误处理器
        default_return: 出错时的默认返回值
        **kwargs: 函数关键字参数

    Returns:
        函数执行结果或默认值
    """
    handler = error_handler or get_global_error_handler()

    try:
        return func(*args, **kwargs)
    except Exception as e:
        handler.handle_exception(e, reraise=False)
        return default_return


def context_sensitive_retry(
    error_types: Tuple[Type[Exception], ...],
    max_retries: int = 3
):
    """
    上下文相关的重试装饰器

    根据章节号和错误类型调整重试策略

    Args:
        error_types: 需要重试的异常类型
        max_retries: 最大重试次数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # 尝试从kwargs中提取章节号
            chapter_number = kwargs.get('chapter_number')

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except error_types as e:
                    if attempt < max_retries - 1:
                        # 根据章节号和错误类型调整延迟
                        if isinstance(e, (APITimeoutError, APIRateLimitError)):
                            # API错误使用指数退避
                            delay = min(2 ** attempt * 5, 60)
                        else:
                            # 其他错误使用较短延迟
                            delay = min(1 + attempt * 2, 10)

                        # 如果是特定章节，增加延迟
                        if chapter_number and chapter_number % 10 == 0:
                            delay *= 1.5

                        logging.warning(
                            f"{func.__name__} (章节 {chapter_number}) "
                            f"第 {attempt + 1} 次失败: {str(e)[:100]}"
                        )
                        logging.info(f"等待 {delay:.2f} 秒后重试...")
                        time.sleep(delay)

            # 所有重试都失败
            raise

        return wrapper
    return decorator
