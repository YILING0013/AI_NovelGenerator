"""MongoDB 写入事务与降级执行工具。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import AutoReconnect, OperationFailure

from backend.config.config import get_config_value
from backend.db.errors import TransactionNotSupportedError
from backend.db.mongo import get_client

logger = logging.getLogger(__name__)

T = TypeVar("T")

_transaction_capability_cache: tuple[AsyncMongoClient, bool] | None = None
_fallback_warning_logged = False


def reset_transaction_capability_cache() -> None:
    """显式清空事务能力缓存和降级提示状态。

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
    global _transaction_capability_cache, _fallback_warning_logged
    client = get_client()
    if _transaction_capability_cache is not None and _transaction_capability_cache[0] is client:
        return _transaction_capability_cache[1]

    try:
        hello = await client.admin.command("hello")
    except OperationFailure:
        # 旧服务端可能不支持 hello，退回兼容命令。
        hello = await client.admin.command("isMaster")

    has_session_timeout = hello.get("logicalSessionTimeoutMinutes") is not None
    is_replica_set = bool(hello.get("setName"))
    is_sharded_cluster = hello.get("msg") == "isdbgrid"
    supported = bool(has_session_timeout and (is_replica_set or is_sharded_cluster))
    # 旧连接的探测可能晚于连接替换完成，不能覆盖新连接的能力和降级提示状态。
    if get_client() is client:
        if _transaction_capability_cache is None or _transaction_capability_cache[0] is not client:
            _fallback_warning_logged = False
        _transaction_capability_cache = (client, supported)
    return supported


async def supports_mongo_transactions() -> bool:
    """返回当前 MongoDB 部署是否支持多文档事务。

    Args:
        无。

    Returns:
        副本集或分片集群且支持会话时返回 True；standalone 返回 False。
    """
    return await _detect_transaction_support()


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
    *,
    require_transaction: bool = False,
    retry_connection_error: bool = False,
) -> T:
    """执行跨集合写入；要求事务的命令不允许降级。

    Args:
        callback: 接收 AsyncClientSession 或 None 的异步写入回调。
        operation_name: 用于日志和异常说明的操作名称。
        require_transaction: 为 True 时必须使用事务，配置禁用或部署不支持时拒绝写入。
        retry_connection_error: 仅供全部读写都在事务内的回调启用；提交前临时断连可重开一次事务。

    Returns:
        回调返回的业务结果。

    Notes:
        默认仅执行一次业务回调。显式启用断连恢复时，也不重跑已进入提交阶段的回调。
        明确要求事务但实际不支持时抛出 TransactionNotSupportedError；其余异常和取消
        原样上抛，事务负责中止未提交写入。
    """
    mode = _get_transaction_mode()
    if mode == "disabled":
        if require_transaction:
            raise TransactionNotSupportedError("当前操作必须使用事务，但数据库事务已禁用")
        return await callback(None)

    supports_transactions = await supports_mongo_transactions()
    if not supports_transactions:
        if require_transaction or mode == "required":
            raise TransactionNotSupportedError(
                "MongoDB transaction mode is required, but current deployment does not support transactions."
            )
        return await _run_without_transaction(callback, operation_name)

    client = get_client()
    for attempt in range(2 if retry_connection_error else 1):
        callback_started = False
        callback_finished = False
        try:
            async with client.start_session() as session:
                # 不使用 with_transaction，避免把所有临时事务错误都自动重跑。
                async with await session.start_transaction():
                    callback_started = True
                    result = await callback(session)
                    # 退出事务上下文会提交；从这里起断连也不能重新执行保存。
                    callback_finished = True
                    return result
        except AutoReconnect as exc:
            if (not retry_connection_error or attempt or not callback_started or callback_finished
                    or not exc.has_error_label("TransientTransactionError")
                    or exc.has_error_label("UnknownTransactionCommitResult")):
                raise
            # 事务上下文已中止失败回调；下一轮使用新会话重新复查资料与原确认键。
            logger.warning("MongoDB connection failed before commit; retrying operation '%s' once.", operation_name)
        except OperationFailure as exc:
            if require_transaction and _is_transaction_unsupported_error(exc):
                raise TransactionNotSupportedError("当前操作必须使用事务，但数据库不支持事务") from exc
            # 只有业务回调开始前确认部署不支持事务时才允许降级，避免提交失败后重复写入。
            if mode == "auto" and not callback_started and _is_transaction_unsupported_error(exc):
                return await _run_without_transaction(callback, operation_name)
            raise
