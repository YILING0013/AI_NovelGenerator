"""只测量写作确认的服务阶段和真实 Mongo 命令，不读取命令正文。"""

from __future__ import annotations

import asyncio
from collections import Counter
from contextvars import ContextVar
import json
import logging
from time import perf_counter
from uuid import uuid4

from pymongo.monitoring import CommandListener


logger = logging.getLogger(__name__)
_current_confirmation: ContextVar[WritingConfirmationTiming | None] = ContextVar("writing_confirmation_timing", default=None)


class WritingConfirmationTiming:
    """记录一次确认；外部事务仅记录本次回调，不代替调用方判断提交。"""

    def __init__(self, task: str, *, owns_transaction: bool) -> None:
        """准备独立计数，不接收候选正文、确认键或连接信息。

        Args:
            task: 路由固定的写作任务名。
            owns_transaction: 当前服务是否负责开启和结束事务。
        Returns:
            无。
        """
        self.task = task
        self.owns_transaction = owns_transaction
        self.call_id = uuid4().hex
        self.phases: dict[str, dict] = {}
        self.command_durations: Counter[str] = Counter()
        self.closed = False
        self.phase_name = "请求校验"

    def __enter__(self) -> WritingConfirmationTiming:
        """绑定本次确认的统计。

        Args:
            无。
        Returns:
            本次确认计时对象。
        """
        self.started = self.phase_started = perf_counter()
        self.phase(self.phase_name)
        self.token = _current_confirmation.set(self)
        return self

    def phase(self, name: str) -> None:
        """结束上一阶段并开始下一阶段；重复阶段累计耗时和命令。

        Args:
            name: 代码中固定的阶段名称。
        Returns:
            无。
        """
        now = perf_counter()
        if self.phase_name in self.phases:
            self.phases[self.phase_name]["duration_ms"] += (now - self.phase_started) * 1000
        self.phase_name, self.phase_started = name, now
        self.phases.setdefault(name, {"duration_ms": 0.0, "started": Counter(), "succeeded": Counter(), "failed": Counter(), "driver_command_ms": 0.0})

    def __exit__(self, _exc_type, error: BaseException | None, _traceback) -> None:
        """输出数值和固定标识，保留原异常或取消，并恢复上层统计。

        Args:
            _exc_type: with 收到的异常类型。
            error: 原异常，仅记录类型名。
            _traceback: 原异常堆栈，不写入计时日志。
        Returns:
            无；不拦截异常。
        """
        ended = perf_counter()
        self.phases[self.phase_name]["duration_ms"] += (ended - self.phase_started) * 1000
        self.closed = True
        try:
            started, succeeded, failed = Counter(), Counter(), Counter()
            for values in self.phases.values():
                started.update(values["started"])
                succeeded.update(values["succeeded"])
                failed.update(values["failed"])
            status = "cancelled" if isinstance(error, (asyncio.CancelledError, GeneratorExit)) else "failed" if error else "completed" if self.owns_transaction else "callback_completed"
            summary = {
                "call_id": self.call_id, "task": self.task, "status": status,
                "transaction_owner": "service" if self.owns_transaction else "caller",
                "service_total_ms": round((ended - self.started) * 1000, 3),
                "commands_started": dict(started), "commands_succeeded": dict(succeeded), "commands_failed": dict(failed),
                "driver_command_durations_ms": {name: round(duration, 3) for name, duration in self.command_durations.items()},
                "error_type": type(error).__name__ if error else None,
                "phases": {name: {**values, "duration_ms": round(values["duration_ms"], 3), "driver_command_ms": round(values["driver_command_ms"], 3)} for name, values in self.phases.items()},
            }
            logger.info("[确认保存计时] %s", json.dumps(summary, ensure_ascii=False), extra={"confirmation_timing": summary})
        finally:
            _current_confirmation.reset(self.token)


class ConfirmationCommandListener(CommandListener):
    """按当前确认统计驱动实际命令，包含 admin 上的提交和中止。"""

    def started(self, event) -> None:
        """累计真正开始发送的命令，创建惰性游标本身不会计数。

        Args:
            event: 驱动命令开始事件，仅使用命令名。
        Returns:
            无。
        """
        timing = _current_confirmation.get()
        if timing is not None and not timing.closed:
            timing.phases[timing.phase_name]["started"][event.command_name] += 1

    def succeeded(self, event) -> None:
        """累计成功命令和驱动耗时，不读取响应。

        Args:
            event: 驱动命令成功事件。
        Returns:
            无。
        """
        timing = _current_confirmation.get()
        if timing is not None and not timing.closed:
            phase = timing.phases[timing.phase_name]
            phase["succeeded"][event.command_name] += 1
            phase["driver_command_ms"] += event.duration_micros / 1000
            timing.command_durations[event.command_name] += event.duration_micros / 1000

    def failed(self, event) -> None:
        """累计失败命令和驱动耗时，不读取错误内容。

        Args:
            event: 驱动命令失败事件。
        Returns:
            无。
        """
        timing = _current_confirmation.get()
        if timing is not None and not timing.closed:
            phase = timing.phases[timing.phase_name]
            phase["failed"][event.command_name] += 1
            phase["driver_command_ms"] += event.duration_micros / 1000
            timing.command_durations[event.command_name] += event.duration_micros / 1000


confirmation_commands = ConfirmationCommandListener()
