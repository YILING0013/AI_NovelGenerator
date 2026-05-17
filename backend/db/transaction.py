"""MongoDB 写入事务与降级执行工具。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.config.config import get_config_value
from backend.db.errors import TransactionNotSupportedError
from backend.db.mongo import get_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

_transaction_capability_cache: bool | None = None
_fallback_warning_logged = False


def reset_transaction_capability_cache() -> None:
    """清空事务能力缓存，通常在 MongoDB 客户端重连后调用。

    Args:
        无。

    Returns:
        无。
    """
    global _transaction_capability_cache, _fallback_warning_logged
    _transaction_capability_cache = None
    _fallback_warning_logged = False


def _get_transaction_mode() -> str:
    """读取并规范化事务模式配置。

    Args:
        无。

    Returns:
        返回 auto、required 或 disabled 之一。
    """
    raw_mode = str(get_config_value("mongo_transaction_mode", "auto")).strip().lower()
    if raw_mode not in {"auto", "required", "disabled"}:
        logger.warning("Invalid mongo_transaction_mode=%s, fallback to auto.", raw_mode)
        return "auto"
    return raw_mode


async def _detect_transaction_support() -> bool:
    """检测当前 MongoDB 部署是否支持多文档事务。

    Args:
        无。

    Returns:
        支持事务时返回 True，否则返回 False。
    """
    global _transaction_capability_cache
    if _transaction_capability_cache is not None:
        return _transaction_capability_cache

    client = get_client()
    try:
        hello = await client.admin.command("hello")
    except OperationFailure:
        # 旧服务端可能不支持 hello，退回兼容命令。
        hello = await client.admin.command("isMaster")

    has_session_timeout = hello.get("logicalSessionTimeoutMinutes") is not None
    is_replica_set = bool(hello.get("setName"))
    is_sharded_cluster = hello.get("msg") == "isdbgrid"
    _transaction_capability_cache = bool(has_session_timeout and (is_replica_set or is_sharded_cluster))
    return _transaction_capability_cache


def _is_transaction_unsupported_error(exc: OperationFailure) -> bool:
    """判断异常是否属于部署不支持事务。

    Args:
        exc: PyMongo 返回的操作异常。

    Returns:
        可安全降级为非事务顺序写入时返回 True。
    """
    message = str(exc).lower()
    return exc.code == 20 or "transaction numbers are only allowed" in message


async def _run_without_transaction(
    callback: Callable[[AsyncClientSession | None], Awaitable[T]],
    operation_name: str,
) -> T:
    """以无事务方式执行写入单元，并只记录一次降级提示。

    Args:
        callback: 接收 session 参数的异步写入回调。
        operation_name: 用于日志定位的业务操作名称。

    Returns:
        回调返回值。
    """
    global _fallback_warning_logged
    if not _fallback_warning_logged:
        logger.warning(
            "MongoDB deployment does not support multi-document transactions; "
            "operation '%s' is running with ordered writes fallback.",
            operation_name,
        )
        _fallback_warning_logged = True
    return await callback(None)


async def run_mongo_write_unit(
    callback: Callable[[AsyncClientSession | None], Awaitable[T]],
    operation_name: str = "mongo_write_unit",
) -> T:
    """执行一个跨集合 MongoDB 写入单元，支持事务并在 auto 模式下降级。

    Args:
        callback: 接收 AsyncClientSession 或 None 的异步写入回调。
        operation_name: 用于日志和异常说明的操作名称。

    Returns:
        回调返回的业务结果。
    """
    mode = _get_transaction_mode()
    if mode == "disabled":
        return await callback(None)

    supports_transactions = await _detect_transaction_support()
    if not supports_transactions:
        if mode == "required":
            raise TransactionNotSupportedError(
                "MongoDB transaction mode is required, but current deployment does not support transactions."
            )
        return await _run_without_transaction(callback, operation_name)

    client = get_client()
    try:
        async with client.start_session() as session:
            return await session.with_transaction(callback)
    except OperationFailure as exc:
        if mode == "auto" and _is_transaction_unsupported_error(exc):
            return await _run_without_transaction(callback, operation_name)
        raise
