"""
Error Handler
错误处理器类

提供统一的错误处理、异常管理和回退策略。
这是系统稳定性的重要保障，确保各种异常情况都能得到妥善处理。

主要功能:
- 统一的异常捕获和处理
- 智能的回退策略
- 详细的错误日志记录
- 用户友好的错误提示
"""

import logging
import traceback
from typing import Dict, Any, Optional, Callable, Type
from enum import Enum
import tkinter as tk
from tkinter import messagebox

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"          # 低级错误，不影响主要功能
    MEDIUM = "medium"    # 中级错误，影响部分功能
    HIGH = "high"        # 高级错误，影响主要功能
    CRITICAL = "critical" # 严重错误，可能导致系统崩溃


class ErrorCategory(Enum):
    """错误类别"""
    CONFIG_ERROR = "config"           # 配置错误
    NETWORK_ERROR = "network"         # 网络错误
    LLM_ERROR = "llm"                 # LLM调用错误
    FILE_ERROR = "file"               # 文件操作错误
    VALIDATION_ERROR = "validation"   # 验证错误
    SYSTEM_ERROR = "system"           # 系统错误
    UNKNOWN_ERROR = "unknown"         # 未知错误


class ErrorHandler:
    """统一的错误处理器"""

    def __init__(self, ui_instance=None):
        """
        初始化错误处理器

        Args:
            ui_instance: GUI实例，用于显示错误提示
        """
        self.ui = ui_instance
        self.error_count = 0
        self.error_history = []  # 错误历史记录
        self.fallback_strategies = {}  # 回退策略
        self.max_error_history = 100  # 最大错误历史记录数

        # 注册默认回退策略
        self._register_default_fallback_strategies()

        logger.info("ErrorHandler 初始化完成")

    def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        show_user_message: bool = True
    ) -> Dict[str, Any]:
        """
        统一处理错误

        Args:
            error: 异常对象
            context: 错误上下文信息
            severity: 错误严重程度
            show_user_message: 是否显示用户提示

        Returns:
            Dict[str, Any]: 错误处理结果
            - handled: 是否已处理
            - fallback_used: 是否使用了回退策略
            - result: 回退策略的结果（如果有）
            - error_id: 错误ID
        """
        self.error_count += 1
        error_id = f"ERR_{self.error_count:04d}"

        # 分析错误
        error_info = self._analyze_error(error, context, severity, error_id)

        # 记录错误
        self._log_error(error_info)

        # 保存到历史记录
        self._save_to_history(error_info)

        # 尝试回退策略
        fallback_result = self._try_fallback_strategy(error_info)

        # 显示用户提示
        if show_user_message and self.ui:
            self._show_user_message(error_info, fallback_result)

        return {
            'handled': True,
            'fallback_used': fallback_result['used'],
            'result': fallback_result['result'],
            'error_id': error_id,
            'error_info': error_info
        }

    def register_fallback_strategy(
        self,
        error_type: Type[Exception],
        strategy: Callable[[Exception, Dict[str, Any]], Any],
        description: str = ""
    ) -> None:
        """
        注册回退策略

        Args:
            error_type: 异常类型
            strategy: 回退策略函数
            description: 策略描述
        """
        if error_type not in self.fallback_strategies:
            self.fallback_strategies[error_type] = []

        self.fallback_strategies[error_type].append({
            'strategy': strategy,
            'description': description,
            'registered_at': self._get_timestamp()
        })

        logger.info(f"注册回退策略: {error_type.__name__} - {description}")

    def _analyze_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        severity: ErrorSeverity,
        error_id: str
    ) -> Dict[str, Any]:
        """分析错误信息"""
        return {
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'error_category': self._categorize_error(error),
            'severity': severity,
            'context': context or {},
            'traceback': traceback.format_exc(),
            'timestamp': self._get_timestamp(),
            'user_friendly_message': self._create_user_friendly_message(error)
        }

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """对错误进行分类"""
        error_message = str(error).lower()
        error_type = type(error).__name__.lower()

        if 'connection' in error_message or 'network' in error_message:
            return ErrorCategory.NETWORK_ERROR
        elif 'api' in error_message or 'openai' in error_message or 'llm' in error_type:
            return ErrorCategory.LLM_ERROR
        elif 'file' in error_message or 'path' in error_message or 'directory' in error_message:
            return ErrorCategory.FILE_ERROR
        elif 'config' in error_message or 'invalid' in error_message:
            return ErrorCategory.CONFIG_ERROR
        elif 'validation' in error_message or 'invalid' in error_message:
            return ErrorCategory.VALIDATION_ERROR
        elif 'permission' in error_message or 'access' in error_message:
            return ErrorCategory.SYSTEM_ERROR
        else:
            return ErrorCategory.UNKNOWN_ERROR

    def _create_user_friendly_message(self, error: Exception) -> str:
        """创建用户友好的错误消息"""
        error_message = str(error).lower()

        if 'connection' in error_message:
            return "网络连接错误，请检查网络设置和API密钥"
        elif 'timeout' in error_message:
            return "请求超时，请稍后重试"
        elif 'api' in error_message or 'key' in error_message:
            return "API配置错误，请检查API密钥和服务设置"
        elif 'file' in error_message or 'path' in error_message:
            return "文件操作错误，请检查文件路径和权限"
        elif 'rate limit' in error_message:
            return "API调用频率过高，请稍后重试"
        elif 'token' in error_message:
            return "Token不足，请减少生成内容或增加最大Token数"
        else:
            return f"发生错误: {str(error)}"

    def _log_error(self, error_info: Dict[str, Any]) -> None:
        """记录错误日志"""
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }.get(error_info['severity'], logging.ERROR)

        logger.log(
            log_level,
            f"错误 [{error_info['error_id']}] {error_info['error_type']}: {error_info['error_message']}"
        )

        if error_info['severity'] in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            logger.debug(f"错误详情:\n{error_info['traceback']}")

    def _save_to_history(self, error_info: Dict[str, Any]) -> None:
        """保存错误到历史记录"""
        self.error_history.append(error_info)

        # 限制历史记录数量
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]

    def _try_fallback_strategy(self, error_info: Dict[str, Any]) -> Dict[str, Any]:
        """尝试回退策略"""
        error_type = type(Exception(error_info['error_message']))

        # 查找匹配的回退策略
        strategies = []
        for strategy_type, strategy_list in self.fallback_strategies.items():
            if issubclass(error_type, strategy_type):
                strategies.extend(strategy_list)

        if not strategies:
            return {'used': False, 'result': None}

        # 尝试第一个可用的策略
        for strategy_info in strategies:
            try:
                result = strategy_info['strategy'](
                    Exception(error_info['error_message']),
                    error_info['context']
                )
                logger.info(f"回退策略成功: {strategy_info['description']}")
                return {
                    'used': True,
                    'result': result,
                    'strategy': strategy_info['description']
                }
            except Exception as fallback_error:
                logger.warning(f"回退策略失败: {strategy_info['description']} - {fallback_error}")
                continue

        return {'used': False, 'result': None}

    def _show_user_message(
        self,
        error_info: Dict[str, Any],
        fallback_result: Dict[str, Any]
    ) -> None:
        """显示用户提示"""
        severity = error_info['severity']
        message = error_info['user_friendly_message']

        if fallback_result['used']:
            message += f"\n\n已自动使用回退策略: {fallback_result['strategy']}"

        # 根据严重程度选择提示框类型
        if severity == ErrorSeverity.CRITICAL:
            messagebox.showerror(f"严重错误 [{error_info['error_id']}]", message)
        elif severity == ErrorSeverity.HIGH:
            messagebox.showerror(f"错误 [{error_info['error_id']}]", message)
        elif severity == ErrorSeverity.MEDIUM:
            messagebox.showwarning(f"警告 [{error_info['error_id']}]", message)
        else:
            messagebox.showinfo(f"提示 [{error_info['error_id']}]", message)

    def _register_default_fallback_strategies(self) -> None:
        """注册默认回退策略"""
        # 网络错误回退策略
        self.register_fallback_strategy(
            ConnectionError,
            lambda error, context: self._fallback_network_error(error, context),
            "网络错误回退：使用本地缓存或重试"
        )

        # API错误回退策略
        self.register_fallback_strategy(
            ValueError,
            lambda error, context: self._fallback_config_error(error, context),
            "配置错误回退：使用默认配置"
        )

        # 文件错误回退策略
        self.register_fallback_strategy(
            FileNotFoundError,
            lambda error, context: self._fallback_file_error(error, context),
            "文件错误回退：创建新文件或使用临时目录"
        )

    def _fallback_network_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """网络错误回退策略"""
        logger.info("执行网络错误回退策略")
        # 这里可以实现具体的回退逻辑
        # 比如：使用本地缓存、切换到备用API、延迟重试等
        return None

    def _fallback_config_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """配置错误回退策略"""
        logger.info("执行配置错误回退策略")
        # 返回默认配置
        return {
            'interface_format': 'OpenAI',
            'api_key': '',
            'base_url': 'https://api.openai.com/v1',
            'model_name': 'gpt-3.5-turbo',
            'temperature': 0.7,
            'max_tokens': 60000,
            'timeout': 600
        }

    def _fallback_file_error(self, error: Exception, context: Dict[str, Any]) -> Any:
        """文件错误回退策略"""
        logger.info("执行文件错误回退策略")
        # 返回临时文件路径
        import tempfile
        return tempfile.mktemp(suffix='.txt')

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        import datetime
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        if not self.error_history:
            return {
                'total_errors': 0,
                'by_category': {},
                'by_severity': {},
                'recent_errors': []
            }

        # 按类别统计
        by_category = {}
        for error in self.error_history:
            category = error['error_category'].value
            by_category[category] = by_category.get(category, 0) + 1

        # 按严重程度统计
        by_severity = {}
        for error in self.error_history:
            severity = error['severity'].value
            by_severity[severity] = by_severity.get(severity, 0) + 1

        # 最近的错误（最近10条）
        recent_errors = [
            {
                'error_id': error['error_id'],
                'error_type': error['error_type'],
                'message': error['user_friendly_message'],
                'timestamp': error['timestamp']
            }
            for error in self.error_history[-10:]
        ]

        return {
            'total_errors': len(self.error_history),
            'by_category': by_category,
            'by_severity': by_severity,
            'recent_errors': recent_errors
        }

    def clear_error_history(self) -> None:
        """清除错误历史记录"""
        self.error_history.clear()
        self.error_count = 0
        logger.info("错误历史记录已清除")