"""短期保存资料整理的原生对话；浏览器只持有一次性续跑凭证。"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
import threading
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.api.error_protocol import DomainApiError


TTL_SECONDS = 30 * 60
MAX_ENTRIES = 64
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class AgentContinuation(BaseModel):
    """作者明确选择的续跑凭证和新增模型请求次数。"""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128)
    additional_rounds: int = Field(ge=1, le=16, strict=True)


@dataclass
class _SavedContinuation:
    state: Any
    binding: str
    expires_at: float
    size: int
    claimed: bool = False
    additional_rounds: int | None = None


_continuations: OrderedDict[str, _SavedContinuation] = OrderedDict()
_lock = threading.Lock()


def _prune() -> None:
    now = time.time()
    for token, entry in list(_continuations.items()):
        if entry.expires_at <= now and not entry.claimed:
            del _continuations[token]


def _entry(token: str, binding: str) -> _SavedContinuation:
    _prune()
    entry = _continuations.get(token)
    if entry is None:
        raise DomainApiError("AGENT_CONTINUATION_EXPIRED", "续跑记录已过期、已使用或服务已重启，请重新整理", status_code=409)
    if entry.binding != binding:
        raise DomainApiError("AGENT_CONTINUATION_CHANGED", "流程、输入、位置或模型设置已变化，请重新整理", status_code=409)
    if entry.claimed:
        raise DomainApiError("AGENT_CONTINUATION_BUSY", "这份资料正在续跑，请等待本次请求结束", status_code=409)
    return entry


def _public(token: str, entry: _SavedContinuation) -> dict[str, Any]:
    value = {"token": token, "instance_path": entry.state.instance_path,
             "round": entry.state.round, "call_count": entry.state.total_calls,
             "expires_at": datetime.fromtimestamp(entry.expires_at, timezone.utc).isoformat()}
    if entry.state.last_error:
        value["last_error"] = entry.state.last_error
    return value


def lookup_agent_continuation(continuation: AgentContinuation, *, binding: str, completed_nodes: dict[str, Any] | None = None) -> str:
    """在执行流程前检查凭证与本次输入，返回需要续跑的节点位置。

    Args:
        continuation: 浏览器提交的凭证及新增轮数。
        binding: 服务端对流程、任务、范围、输入和模型配置计算的散列。
        completed_nodes: 可选，接收同次流程已完成的付费节点，供核对资料后恢复输出。
    Returns:
        原资料节点的实例位置，不包含原生模型对话。
    """
    with _lock:
        entry = _entry(continuation.token, binding)
        if entry.additional_rounds is not None and entry.additional_rounds != continuation.additional_rounds:
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "中断后重试须沿用本次已选择的新增轮数", status_code=409)
        if completed_nodes is not None:
            completed_nodes.update(deepcopy(entry.state.completed_nodes))
        return entry.state.instance_path


def claim_agent_continuation(continuation: AgentContinuation, *, binding: str, instance_path: str) -> Any:
    """只允许一个请求领取原状态，同一凭证重试不会重复增加预算。

    Args:
        continuation: 浏览器提交的凭证及新增轮数。
        binding: 服务端计算的本次请求散列。
        instance_path: 当前实际运行的资料节点位置。
    Returns:
        仅供服务端继续执行的原状态。
    """
    with _lock:
        entry = _entry(continuation.token, binding)
        if entry.state.instance_path != instance_path:
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "续跑节点与原整理节点不一致，请重新整理", status_code=409)
        if entry.additional_rounds is None:
            entry.additional_rounds = continuation.additional_rounds
            entry.state.round_limit += continuation.additional_rounds
            entry.state.call_limit += 3 * continuation.additional_rounds
        elif entry.additional_rounds != continuation.additional_rounds:
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "中断后重试须沿用本次已选择的新增轮数", status_code=409)
        entry.claimed = True
        return entry.state


def save_agent_continuation(state: Any, *, binding: str, size: int, previous_token: str | None = None) -> dict[str, Any]:
    """达到预算后短期保存状态并换发凭证；不把模型历史发送到浏览器。

    Args:
        state: 原生对话、待执行调用及资料记录等服务端状态。
        binding: 原流程与输入的服务端散列。
        size: 待保存状态的估算字节数，用于限制内存。
        previous_token: 本次续跑已领取的旧凭证，换发时使其失效。
    Returns:
        可放入预算错误的公开续跑信息。
    """
    with _lock:
        _prune()
        if previous_token:
            _continuations.pop(previous_token, None)
        if size > MAX_ENTRY_BYTES:
            raise DomainApiError("AGENT_CONTINUATION_TOO_LARGE", "已整理资料超过续跑保存上限，请缩小资料范围后重新整理", status_code=422)
        if len(_continuations) >= MAX_ENTRIES or sum(entry.size for entry in _continuations.values()) + size > MAX_TOTAL_BYTES:
            raise DomainApiError("AGENT_CONTINUATION_CAPACITY", "当前保存的续跑记录已满，请稍后重新整理", status_code=503)
        token = secrets.token_urlsafe(32)
        entry = _SavedContinuation(state=state, binding=binding, expires_at=time.time() + TTL_SECONDS, size=size)
        _continuations[token] = entry
        return _public(token, entry)


def release_agent_continuation(token: str, *, size: int, discard: bool = False) -> dict[str, Any] | None:
    """取消或请求失败时释放领取；成功与资料变化时直接消费凭证。

    Args:
        token: 本次领取的凭证。
        size: 当前状态的估算大小。
        discard: 是否使凭证失效，不再允许重试。
    Returns:
        仍可重试时的公开信息；已消费或无法保存时返回空。
    """
    with _lock:
        entry = _continuations.get(token)
        if entry is None:
            return None
        if discard or size > MAX_ENTRY_BYTES or sum(value.size for key, value in _continuations.items() if key != token) + size > MAX_TOTAL_BYTES:
            del _continuations[token]
            return None
        entry.claimed = False
        entry.size = size
        return _public(token, entry)
