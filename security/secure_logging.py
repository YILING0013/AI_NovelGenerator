# secure_logging.py
# -*- coding: utf-8 -*-
"""
安全日志管理模块
防止敏感信息泄露到日志中
"""

import logging
import re
import json
import os
from typing import Any, Dict, List
from functools import wraps


class SecureLogFilter(logging.Filter):
    """
    安全日志过滤器
    过滤敏感信息
    """

    SENSITIVE_PATTERNS = [
        # API密钥模式
        r'(?i)(api[_-]?key|apikey|token)\s*[:=]\s*["\']?([a-zA-Z0-9_-]{16,})["\']?',
        r'(?i)sk-[a-zA-Z0-9]{20,}',
        r'(?i)[a-zA-Z0-9_-]{32,}',

        # 密码模式
        r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]{4,})["\']?',

        # 端口号模式
        r'(?i)(port)\s*[:=]\s*["\']?(\d{1,5})["\']?',

        # 私有信息
        r'(?i)(username|user|email)\s*[:=]\s*["\']?([^"\'\s@]+@[^"\'\s@]+\.[^"\'\s@]+)["\']?',

        # 文件路径中的敏感信息
        r'([/\\]Users[/\\][^/\\]+|[/\\]home[/\\][^/\\]+)',
        r'[A-Z]:\\[^\\]*(\\[^\\]*)*',
    ]

    REPLACEMENT_PATTERNS = [
        ('api_key', 'api_key'),
        ('apikey', 'apikey'),
        ('password', 'password'),
        ('passwd', 'passwd'),
        ('pwd', 'pwd'),
        ('token', 'token'),
        ('sk-', 'sk-'),
    ]

    def __init__(self):
        super().__init__()
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.SENSITIVE_PATTERNS]

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤日志记录中的敏感信息"""
        if hasattr(record, 'msg'):
            record.msg = self._sanitize_message(str(record.msg))

        if hasattr(record, 'args') and record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self._sanitize_message(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)

        return True

    def _sanitize_message(self, message: str) -> str:
        """清理消息中的敏感信息"""
        sanitized = message

        # 应用所有模式进行清理
        for pattern in self.compiled_patterns:
            sanitized = pattern.sub(self._replacement_function, sanitized)

        # 特殊处理：移除过长的字符串（可能是密钥）
        sanitized = re.sub(r'\b[a-zA-Z0-9_-]{20,}\b', '[REDACTED_LONG_STRING]', sanitized)

        return sanitized

    def _replacement_function(self, match):
        """替换函数"""
        full_match = match.group(0)

        # 检查匹配类型并适当替换
        for key, replacement in self.REPLACEMENT_PATTERNS:
            if key.lower() in full_match.lower():
                if key == 'sk-':
                    # OpenAI API密钥
                    return f'{replacement}[REDACTED]'
                elif '=' in full_match or ':' in full_match:
                    # 键值对形式
                    return f'{key}: [REDACTED]'

        # 默认替换
        return '[REDACTED]'


class SecureLogger:
    """
    安全日志管理器
    """

    def __init__(self, name: str = 'ai_novel_generator', log_file: str = 'app.log'):
        self.logger = logging.getLogger(name)
        self.log_file = log_file
        self._setup_logger()

    def _setup_logger(self):
        """设置安全的日志记录器"""
        # 清除现有的处理器
        self.logger.handlers.clear()

        # 设置日志级别
        self.logger.setLevel(logging.INFO)

        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 添加安全过滤器
        secure_filter = SecureLogFilter()

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(secure_filter)
        self.logger.addHandler(console_handler)

        # 文件处理器
        try:
            # 确保日志目录存在
            log_dir = os.path.dirname(self.log_file) if os.path.dirname(self.log_file) else '.'
            os.makedirs(log_dir, exist_ok=True)

            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(secure_filter)
            self.logger.addHandler(file_handler)

            # 设置日志文件权限（仅所有者可读写）
            if os.name != 'nt':  # 非Windows系统
                os.chmod(self.log_file, 0o600)

        except Exception as e:
            # 如果文件处理器创建失败，只使用控制台处理器
            self.logger.warning(f"无法创建日志文件处理器: {e}")

    def debug(self, message: str, **kwargs):
        """安全调试日志"""
        self.logger.debug(self._sanitize_log_data(message, **kwargs))

    def info(self, message: str, **kwargs):
        """安全信息日志"""
        self.logger.info(self._sanitize_log_data(message, **kwargs))

    def warning(self, message: str, **kwargs):
        """安全警告日志"""
        self.logger.warning(self._sanitize_log_data(message, **kwargs))

    def error(self, message: str, **kwargs):
        """安全错误日志"""
        self.logger.error(self._sanitize_log_data(message, **kwargs))

    def critical(self, message: str, **kwargs):
        """安全严重错误日志"""
        self.logger.critical(self._sanitize_log_data(message, **kwargs))

    def _sanitize_log_data(self, message: str, **kwargs) -> str:
        """清理日志数据中的敏感信息"""
        # 基本消息清理
        sanitized = str(message)

        # 清理关键字段参数中的敏感信息
        sensitive_fields = ['api_key', 'password', 'token', 'username', 'email']

        for key, value in kwargs.items():
            if any(sensitive in key.lower() for sensitive in sensitive_fields):
                # 替换敏感字段值
                sanitized = sanitized.replace(str(value), '[REDACTED]')
            elif key == 'url' and isinstance(value, str):
                # 清理URL中的敏感信息
                sanitized = self._sanitize_url(str(value), sanitized)

        return sanitized

    def _sanitize_url(self, url: str, message: str) -> str:
        """清理URL中的敏感信息"""
        # 匹配API密钥参数
        api_key_pattern = r'([&?]api[_-]?key=)[^&\s]+'
        sanitized = re.sub(api_key_pattern, r'\1[REDACTED]', message, flags=re.IGNORECASE)

        # 匹配token参数
        token_pattern = r'([&?]token=)[^&\s]+'
        sanitized = re.sub(token_pattern, r'\1[REDACTED]', sanitized, flags=re.IGNORECASE)

        return sanitized

    def log_api_call(self, method: str, url: str, status_code: int = None, error: str = None):
        """安全的API调用日志"""
        # 清理URL中的敏感信息
        clean_url = self._sanitize_url_in_endpoint(url)

        if status_code:
            if 200 <= status_code < 300:
                self.info(f"API调用成功: {method} {clean_url} - {status_code}")
            else:
                self.warning(f"API调用失败: {method} {clean_url} - {status_code}")

        if error:
            self.error(f"API调用错误: {method} {clean_url} - {error}")

    def _sanitize_url_in_endpoint(self, url: str) -> str:
        """清理URL端点中的敏感信息"""
        # 移除API密钥和token参数
        sanitized = re.sub(r'[?&]api[_-]?key=[^&\s]+', '', url, flags=re.IGNORECASE)
        sanitized = re.sub(r'[?&]token=[^&\s]+', '', sanitized, flags=re.IGNORECASE)

        # 清理移除参数后可能残留的&或?
        sanitized = re.sub(r'[?&]$', '', sanitized)
        sanitized = re.sub(r'&(?=&|$)', '', sanitized)

        return sanitized


def secure_log_function(logger: SecureLogger = None):
    """
    安全日志装饰器
    自动清理函数调用中的敏感信息
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            log = logger or SecureLogger()

            # 记录函数调用开始
            func_name = f"{func.__module__}.{func.__name__}"
            log.debug(f"开始执行: {func_name}")

            try:
                result = func(*args, **kwargs)
                log.debug(f"成功完成: {func_name}")
                return result

            except Exception as e:
                log.error(f"执行失败: {func_name} - {str(e)}")
                raise

        return wrapper
    return decorator


# 全局安全日志记录器
secure_logger = SecureLogger()


def get_secure_logger(name: str = 'ai_novel_generator', log_file: str = 'app.log') -> SecureLogger:
    """获取安全日志记录器"""
    return SecureLogger(name, log_file)