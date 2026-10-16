"""短期保存资料对话、完成节点与候选；浏览器只持有排他续跑凭证。"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import secrets
import threading
import time
import pickle
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.api.error_protocol import DomainApiError


TTL_SECONDS = 30 * 60
MAX_ENTRIES = 64
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class AgentContinuation(BaseModel):
    """作者明确选择的续跑凭证；网络恢复不增加模型轮数。"""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128)
    additional_rounds: int = Field(ge=0, le=16, strict=True)


@dataclass
class FlowContinuationState:
    """原续跑记录的流程状态；只保存在服务端，不信任浏览器的整理结果。"""

    agent: Any = None
    # 图按顺序执行，只需保存当前未完成模型节点的完整生成和审校回复。
    model_call: dict[str, Any] | None = None
    completed_nodes: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None

    @property
    def instance_path(self) -> str:
        return self.agent.instance_path if self.agent is not None else ""

    @property
    def round(self) -> int:
        return self.agent.round if self.agent is not None else 0

    @property
    def total_calls(self) -> int:
        return self.agent.total_calls if self.agent is not None else 0

    @property
    def last_error(self) -> str | None:
        return self.agent.last_error if self.agent is not None else None

    def size(self) -> int:
        """计量当前完整记录。

        Args:
            无。
        Returns:
            包含本轮增长和最终候选的序列化字节数。
        """
        return len(pickle.dumps(self, protocol=5))


@dataclass
class _SavedContinuation:
    state: Any
    binding: str
    expires_at: float
    size: int
    reason: str = "budget"
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
    if entry.reason == "network":
        value.update(reason="network", resume_rounds=entry.additional_rounds or 0)
    if isinstance(entry.state, FlowContinuationState):
        value.update(flow_recovery=True, running=entry.claimed, result_ready=entry.state.result is not None)
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
        if entry.reason == "network" and continuation.additional_rounds != (entry.additional_rounds or 0):
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "恢复连接不能增加整理轮数，请沿用原请求", status_code=409)
        if entry.reason == "budget" and continuation.additional_rounds == 0:
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "整理次数已用完，请选择增加轮数", status_code=409)
        if entry.additional_rounds is None:
            entry.additional_rounds = continuation.additional_rounds
            agent = entry.state.agent if isinstance(entry.state, FlowContinuationState) else entry.state
            if agent is not None:
                agent.round_limit += continuation.additional_rounds
                agent.call_limit += 3 * continuation.additional_rounds
        elif entry.additional_rounds != continuation.additional_rounds:
            raise DomainApiError("AGENT_CONTINUATION_CHANGED", "中断后重试须沿用本次已选择的新增轮数", status_code=409)
        entry.claimed = True
        entry.reason = "network"
        return entry.state


def update_agent_continuation(token: str, *, size: int, reason: str | None = None) -> dict[str, Any]:
    """在安全停止点核算实际增长；超限保留结果并暂停，不能继续付费。

    Args:
        token: 当前流程独占的原凭证。
        size: 当前完整状态大小；即使超限也登记实际占用。
        reason: 达到预算时改变恢复方式，不释放并发领取。
    Returns:
        最新公开进度；超限抛明确错误，已完成状态仍然保留。
    """
    with _lock:
        _prune()
        entry = _continuations[token]
        entry.size = size
        if reason is not None:
            entry.reason = reason
        details = {"agent_continuation": _public(token, entry)}
        if size > MAX_ENTRY_BYTES:
            raise DomainApiError("AGENT_CONTINUATION_TOO_LARGE", "本轮资料超过恢复容量，已保留进度并暂停。请保留当前资料，放弃本轮后缩小范围重新生成", status_code=422, details=details)
        if sum(value.size for value in _continuations.values()) > MAX_TOTAL_BYTES:
            raise DomainApiError("AGENT_CONTINUATION_CAPACITY", "恢复记录占用已满，已保留本轮进度。请等待其他记录释放后恢复", status_code=503, details=details)
        return _public(token, entry)


def save_agent_continuation(state: Any, *, binding: str, size: int, previous_token: str | None = None, reason: str = "budget", claimed: bool = False) -> dict[str, Any]:
    """发送前登记状态，达到预算后换发凭证；不把模型历史发送到浏览器。

    Args:
        state: 原生对话、待执行调用及资料记录等服务端状态。
        binding: 原流程与输入的服务端散列。
        size: 待保存状态的估算字节数，用于限制内存。
        previous_token: 本次续跑已领取的旧凭证，换发时使其失效。
        reason: 预算耗尽或连接恢复，连接恢复不增加预算。
        claimed: 首次发送前直接占用凭证，避免另一个请求同时恢复。
    Returns:
        可放入进度或错误的公开续跑信息。
    """
    with _lock:
        _prune()
        previous = _continuations.get(previous_token) if previous_token else None
        if size > MAX_ENTRY_BYTES:
            raise DomainApiError("AGENT_CONTINUATION_TOO_LARGE", "已整理资料超过续跑保存上限，请缩小资料范围后重新整理", status_code=422)
        if (len(_continuations) - bool(previous) >= MAX_ENTRIES
                or sum(entry.size for entry in _continuations.values()) - (previous.size if previous else 0) + size > MAX_TOTAL_BYTES):
            raise DomainApiError("AGENT_CONTINUATION_CAPACITY", "当前保存的续跑记录已满，请稍后重新整理", status_code=503)
        if previous_token:
            _continuations.pop(previous_token, None)
        token = secrets.token_urlsafe(32)
        entry = _SavedContinuation(state=state, binding=binding, expires_at=time.time() + TTL_SECONDS, size=size, reason=reason, claimed=claimed)
        _continuations[token] = entry
        return _public(token, entry)


def release_agent_continuation(token: str, *, size: int, discard: bool = False) -> dict[str, Any] | None:
    """请求停止后释放领取并重新计算保留期限；显式丢弃才消费凭证。

    Args:
        token: 本次领取的凭证。
        size: 当前状态的估算大小。
        discard: 是否使凭证失效，不再允许重试。
    Returns:
        仍可恢复时的公开信息；已消费时返回空。
    """
    with _lock:
        entry = _continuations.get(token)
        if entry is None:
            return None
        if discard:
            del _continuations[token]
            return None
        entry.claimed = False
        entry.size = size
        entry.expires_at = time.time() + TTL_SECONDS
        return _public(token, entry)


def agent_continuation_progress(token: str) -> dict[str, Any]:
    """读取当前执行者已领取的公开进度，供断线后恢复。

    Args:
        token: 当前执行者持有的凭证。
    Returns:
        不含对话和模型凭据的恢复信息。
    """
    with _lock:
        return _public(token, _continuations[token])
