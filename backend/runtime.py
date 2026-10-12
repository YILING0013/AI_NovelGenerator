"""运行时调试与日志配置。"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterable

BACKEND_DEBUG_ENV_VAR = "NOVEL_GENERATOR_BACKEND_DEBUG"
BACKEND_PORT_ENV_VAR = "NOVEL_GENERATOR_BACKEND_PORT"
FRONTEND_PORT_ENV_VAR = "NOVEL_GENERATOR_FRONTEND_PORT"
DEFAULT_BACKEND_PORT = 8200
DEFAULT_FRONTEND_PORT = 3300
_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}

# 每次绑定都创建新字典，异步请求和子任务不会修改彼此的日志上下文。
log_context: ContextVar[dict[str, str]] = ContextVar("log_context", default={})


@contextmanager
def bind_log_context(**fields: str) -> Iterator[None]:
    """在当前请求或步骤内补充日志关联信息，退出时恢复上层信息。

    Args:
        **fields: 请求、流程、节点或模型调用的标识。

    Yields:
        无；绑定在 with 语句内有效。
    """
    token = log_context.set({**log_context.get(), **fields})
    try:
        yield
    finally:
        log_context.reset(token)


class LogContextFilter(logging.Filter):
    """把当前异步请求的关联信息写入日志记录。"""

    def filter(self, record: logging.LogRecord) -> bool:
        """补充格式化器需要的上下文，保留所有日志。

        Args:
            record: 即将输出的日志记录。

        Returns:
            始终为 True。
        """
        record.context = " ".join(f"{key}={value}" for key, value in log_context.get().items())
        return True


def log_exception(
    target: logging.Logger,
    message: str,
    error: BaseException,
    *,
    level: int = logging.ERROR,
) -> None:
    """记录真实异常链；上层再次遇到同一错误时只记录失败位置。

    Args:
        target: 当前模块的 logger。
        message: 失败的操作及必要数据。
        error: 原始异常或保留了 cause 的业务异常。
        level: 日志级别，默认 ERROR。

    Returns:
        无。
    """
    current: BaseException | None = error
    while current is not None:
        if getattr(current, "_log_recorded", False):
            target.log(level, "%s type=%s error=%s", message, type(error).__name__, error, stacklevel=2)
            return
        current = current.__cause__ or current.__context__

    target.log(
        level, "%s type=%s error=%s", message, type(error).__name__, error,
        exc_info=(type(error), error, error.__traceback__),
        stack_info=error.__traceback__ is None, stacklevel=2,
    )
    error._log_recorded = True


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def _get_port_from_env(env_name: str, default_port: int) -> int:
    raw_value = os.getenv(env_name, str(default_port)).strip()
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{env_name} 必须是整数，当前值为 {raw_value!r}") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{env_name} 必须位于 1 到 65535 之间，当前值为 {port}")
    return port


def get_backend_port() -> int:
    """读取并校验后端监听端口。

    Args:
        无。

    Returns:
        环境变量指定的有效 TCP 端口；未指定时返回项目默认端口。

    Raises:
        ValueError: 环境变量不是整数或超出有效端口范围。
    """
    return _get_port_from_env(BACKEND_PORT_ENV_VAR, DEFAULT_BACKEND_PORT)


def get_frontend_port() -> int:
    """读取并校验前端监听端口。

    Args:
        无。

    Returns:
        环境变量指定的有效 TCP 端口；未指定时返回项目默认端口。

    Raises:
        ValueError: 环境变量不是整数或超出有效端口范围。
    """
    return _get_port_from_env(FRONTEND_PORT_ENV_VAR, DEFAULT_FRONTEND_PORT)


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


def set_backend_debug_enabled(enabled: bool) -> None:
    """立即切换应用日志和 AI 原始内容的输出，不重建日志处理器。

    Args:
        enabled: 是否输出调试日志。

    Returns:
        无。
    """
    os.environ[BACKEND_DEBUG_ENV_VAR] = "1" if enabled else "0"
    for name in ("main", "backend", "llm"):
        logging.getLogger(name).setLevel(get_backend_log_level())
    logging.getLogger(__name__).info("调试日志已%s", "开启" if enabled else "关闭")


def build_uvicorn_log_config() -> dict[str, Any]:
    """生成适用于 uvicorn 的控制台日志配置。"""
    app_log_level = get_backend_log_level()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s | %(levelprefix)s | %(name)s | %(filename)s:%(lineno)d | %(context)s | %(message)s",
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
        "filters": {
            "context": {"()": "backend.runtime.LogContextFilter"},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
                "filters": ["context"],
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
            "backend": {
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
        },
    }
