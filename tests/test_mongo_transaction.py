"""MongoDB 事务封装的单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from backend.db import transaction
from backend.db.errors import TransactionNotSupportedError


class FakeSession:
    """模拟 PyMongo Async session。

    Args:
        无。

    Returns:
        用于测试的异步上下文管理器实例。
    """

    async def __aenter__(self):
        """进入异步上下文。

        Args:
            无。

        Returns:
            当前 session 实例。
        """
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """退出异步上下文。

        Args:
            exc_type: 异常类型。
            exc: 异常实例。
            tb: 异常堆栈。

        Returns:
            不吞掉异常。
        """
        return False

    async def with_transaction(self, callback):
        """模拟事务执行。

        Args:
            callback: 接收 session 的异步回调。

        Returns:
            回调返回值。
        """
        return await callback(self)


class FakeClient:
    """模拟 PyMongo Async client。

    Args:
        session: start_session 应返回的 FakeSession。

    Returns:
        用于测试的客户端对象。
    """

    def __init__(self, session: FakeSession):
        self.session = session

    def start_session(self):
        """返回模拟 session。

        Args:
            无。

        Returns:
            FakeSession 实例。
        """
        return self.session


def test_run_mongo_write_unit_uses_session_when_transactions_supported(monkeypatch):
    session = FakeSession()
    seen = {}

    monkeypatch.setattr(transaction, "get_config_value", lambda key, default=None: "auto")
    monkeypatch.setattr(transaction, "_detect_transaction_support", lambda: _async_return(True))
    monkeypatch.setattr(transaction, "get_client", lambda: FakeClient(session))

    async def callback(active_session):
        """记录传入的 session。

        Args:
            active_session: 事务 session。

        Returns:
            固定结果字符串。
        """
        seen["session"] = active_session
        return "ok"

    result = asyncio.run(transaction.run_mongo_write_unit(callback, "unit_test"))

    assert result == "ok"
    assert seen["session"] is session


def test_run_mongo_write_unit_falls_back_when_transactions_unsupported(monkeypatch):
    monkeypatch.setattr(transaction, "get_config_value", lambda key, default=None: "auto")
    monkeypatch.setattr(transaction, "_detect_transaction_support", lambda: _async_return(False))
    transaction.reset_transaction_capability_cache()

    async def callback(active_session):
        """确认降级路径传入 None。

        Args:
            active_session: 降级时应为 None。

        Returns:
            session 参数。
        """
        return active_session

    result = asyncio.run(transaction.run_mongo_write_unit(callback, "unit_test"))

    assert result is None


def test_run_mongo_write_unit_disabled_mode_skips_detection(monkeypatch):
    monkeypatch.setattr(transaction, "get_config_value", lambda key, default=None: "disabled")

    async def fail_if_called():
        """事务禁用时不应调用检测。

        Args:
            无。

        Returns:
            无。
        """
        raise AssertionError("transaction detection should not run")

    monkeypatch.setattr(transaction, "_detect_transaction_support", fail_if_called)

    async def callback(active_session):
        """返回降级 session 参数。

        Args:
            active_session: 禁用事务时应为 None。

        Returns:
            session 参数。
        """
        return active_session

    result = asyncio.run(transaction.run_mongo_write_unit(callback, "unit_test"))

    assert result is None


def test_run_mongo_write_unit_required_mode_rejects_unsupported(monkeypatch):
    monkeypatch.setattr(transaction, "get_config_value", lambda key, default=None: "required")
    monkeypatch.setattr(transaction, "_detect_transaction_support", lambda: _async_return(False))

    async def callback(active_session):
        """该回调在 required 且不支持事务时不应执行。

        Args:
            active_session: 事务 session。

        Returns:
            无。
        """
        raise AssertionError("callback should not run")

    with pytest.raises(TransactionNotSupportedError):
        asyncio.run(transaction.run_mongo_write_unit(callback, "unit_test"))


async def _async_return(value):
    """将普通值包装成异步返回值。

    Args:
        value: 需要返回的值。

    Returns:
        原样返回 value。
    """
    return value
