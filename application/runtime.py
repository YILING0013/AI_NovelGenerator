"""运行时调试与日志配置。"""

from __future__ import annotations

import os
import sys
from typing import Any, Iterable

BACKEND_DEBUG_ENV_VAR = "NOVEL_GENERATOR_BACKEND_DEBUG"
_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def apply_runtime_flags_from_argv(argv: Iterable[str] | None = None) -> bool:
    """根据命令行参数与环境变量解析后端调试开关。"""
    args = list(sys.argv[1:] if argv is None else argv)

    if "--debug" in args:
        enabled = True
    elif "--no-debug" in args:
        enabled = False
    else:
        enabled = _is_truthy(os.getenv(BACKEND_DEBUG_ENV_VAR))

    os.environ[BACKEND_DEBUG_ENV_VAR] = "1" if enabled else "0"
    return enabled


def is_backend_debug_enabled() -> bool:
    """返回当前后端是否启用调试模式。"""
    return _is_truthy(os.getenv(BACKEND_DEBUG_ENV_VAR))


def get_backend_log_level() -> str:
    """根据调试状态返回日志级别。"""
    return "DEBUG" if is_backend_debug_enabled() else "INFO"


def build_uvicorn_log_config() -> dict[str, Any]:
    """生成适用于 uvicorn 的控制台日志配置。"""
    app_log_level = get_backend_log_level()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s | %(levelprefix)s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": False,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": "%(asctime)s | %(levelprefix)s | %(client_addr)s - \"%(request_line)s\" %(status_code)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": False,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "handlers": ["default"],
            "level": "WARNING",
        },
        "loggers": {
            "main": {
                "handlers": ["default"],
                "level": app_log_level,
                "propagate": False,
            },
            "application": {
                "handlers": ["default"],
                "level": app_log_level,
                "propagate": False,
            },
            "llm": {
                "handlers": ["default"],
                "level": app_log_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
            "httpcore": {
                "level": "WARNING",
            },
            "httpx": {
                "level": "WARNING",
            },
            "openai": {
                "level": "WARNING",
            },
            "anthropic": {
                "level": "WARNING",
            },
            "google": {
                "level": "WARNING",
            },
            "pymongo": {
                "level": "WARNING",
            },
            "motor": {
                "level": "WARNING",
            },
        },
    }