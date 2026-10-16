"""记录真实的 LLM 请求、响应和失败证据。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextvars import ContextVar
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx2 as httpx
from pydantic import BaseModel

from backend.llm.models import LLMResponse, TokenUsage
from backend.llm.provider_probe import active_provider_probe, observe_provider_request
from backend.runtime import is_backend_debug_enabled, log_context, log_exception

logger = logging.getLogger("llm")


def format_payload(payload: Any) -> str:
    """把日志数据排成可读文本，原样保留正文和字段。

    Args:
        payload: 文本、JSON 数据或 SDK 返回的 Pydantic 对象。

    Returns:
        完整文本；没有长度限制或内容替换。
    """
    if isinstance(payload, str):
        return payload
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", warnings=False)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


class LLMCall:
    """管理一次模型调用的日志，供三个 Provider 的所有生成入口共用。"""

    def __init__(
        self, provider: str, model: str, operation: str, *,
        schema: type[BaseModel] | None = None,
        use_system_proxy: bool = False,
    ) -> None:
        """准备调用标识及当前调用收到的数据。

        Args:
            provider: Provider 配置别名。
            model: 已确定的实际请求模型。
            operation: text、schema、stream 或 function_call。
            schema: 结构化调用的目标模型。
            use_system_proxy: 是否使用系统代理。

        Returns:
            无。
        """
        self.provider = provider
        self.model = model
        self.operation = operation
        self.schema = schema
        self.use_system_proxy = use_system_proxy
        self.call_id = uuid4().hex
        self.http_sequence = 0
        self.last_response: str | None = None
        self.last_response_printed = False
        self.chunks: list[str] = []
        self.chunk_count = 0
        self.result: LLMResponse | None = None
        self.url = ""
        self.usage: TokenUsage | None = None
        self.finish_reason = ""
        self.parse_input_logged = False

    def __enter__(self) -> LLMCall:
        """绑定当前调用，使 HTTP 钩子和上层日志使用相同编号。

        Args:
            无。

        Returns:
            当前调用的日志对象。
        """
        self.started = perf_counter()
        self.context_token = log_context.set({**log_context.get(), "call_id": self.call_id})
        self.call_token = _current_call.set(self)
        logger.info("[LLM 调用] provider=%s model=%s operation=%s system_proxy=%s", self.provider, self.model, self.operation, self.use_system_proxy)
        return self

    def __exit__(self, _exc_type, error: BaseException | None, _traceback) -> None:
        """记录完成、中断或取消，再恢复上层调用上下文。

        Args:
            _exc_type: with 语句收到的异常类型。
            error: 已保留原始 cause 的调用异常。
            _traceback: 异常的堆栈。

        Returns:
            无；异常继续向调用方抛出。
        """
        cancelled = isinstance(error, (asyncio.CancelledError, GeneratorExit))
        status = "cancelled" if cancelled else "failed" if error is not None else "completed"
        try:
            if error is not None and not cancelled:
                # SDK 可能在返回对象前就解析失败；HTTP 钩子已保存该响应。
                if self.last_response is not None and not self.last_response_printed:
                    logger.error("[LLM 失败原始响应] payload=\n%s", self.last_response)
                if self.schema is not None and not self.parse_input_logged:
                    logger.error("[LLM 目标 Schema] payload=\n%s", format_payload(self.schema.model_json_schema()))
                log_exception(logger, f"[LLM 异常] provider={self.provider} model={self.model}", error)
            # 流式正文只在结束时合并输出，避免每个 token 都打印整份 SDK 事件。
            if self.operation == "stream" and (is_backend_debug_enabled() or error is not None):
                level = logging.ERROR if status == "failed" else logging.WARNING if cancelled else logging.DEBUG
                logger.log(level, "[LLM 流式累计正文] status=%s chunks=%d content=\n%s", status, self.chunk_count, "".join(self.chunks))
            result = self.result
            usage = result.usage if result is not None else self.usage
            logger.info(
                "[LLM 结束] provider=%s model=%s operation=%s status=%s url=%s duration=%dms chunks=%d usage=%s finish=%s",
                self.provider, result.model if result is not None else self.model,
                self.operation, status, self.url, int((perf_counter() - self.started) * 1000),
                self.chunk_count, usage.model_dump() if usage is not None else None,
                result.finish_reason if result is not None else self.finish_reason,
            )
        finally:
            _current_call.reset(self.call_token)
            log_context.reset(self.context_token)


_current_call: ContextVar[LLMCall] = ContextVar("llm_call")


async def log_http_request(request: httpx.Request) -> None:
    """记录 SDK 最终发出的请求；重试和工具二轮请求各占一个发送序号。

    Args:
        request: HTTPX 已准备好、尚未发送的请求。

    Returns:
        无。
    """
    call = _current_call.get()
    if active_provider_probe.get() is not None:
        observe_provider_request(json.loads(request.content))
    call.http_sequence += 1
    call.last_response = None
    call.last_response_printed = False
    call.url = str(request.url)
    request.extensions["llm_send_sequence"] = call.http_sequence
    request.extensions["llm_send_started"] = perf_counter()
    logger.info(
        "[LLM HTTP 请求] send=%d provider=%s model=%s method=%s url=%s timeout=%s",
        call.http_sequence, call.provider, call.model, request.method, request.url,
        request.extensions.get("timeout"),
    )
    if is_backend_debug_enabled():
        logger.debug("[LLM 实际请求体] send=%d payload=\n%s", call.http_sequence, request.content.decode("utf-8"))


async def log_http_response(response: httpx.Response) -> None:
    """在 SDK 解析前记录非流式响应，流式正文留给客户端逐块读取。

    Args:
        response: HTTPX 收到的响应头和响应流。

    Returns:
        无；读取过的非流式正文仍由 HTTPX 缓存供 SDK 使用。
    """
    call = _current_call.get()
    sequence = response.request.extensions["llm_send_sequence"]
    logger.info(
        "[LLM HTTP 响应] send=%d status=%d url=%s duration=%dms request_id=%s content_type=%s",
        sequence, response.status_code, response.url,
        int((perf_counter() - response.request.extensions["llm_send_started"]) * 1000),
        response.headers.get("x-request-id") or response.headers.get("request-id") or response.headers.get("x-goog-request-id", ""),
        response.headers.get("content-type", ""),
    )
    probe = active_provider_probe.get()
    if probe is not None:
        probe._http_status = response.status_code
        if response.is_success and probe.reasoning_status == "unknown":
            probe.reasoning_status = "sent"
    # 不提前读取成功的 SSE 流，否则实时生成会变成等待整段响应。
    if response.is_success and "text/event-stream" in response.headers.get("content-type", "").lower():
        return
    await response.aread()
    if probe is not None and response.status_code in {400, 422} and probe.reasoning_status == "unknown":
        # 只接受指向本次实际参数的明确拒绝，模型名和请求回显不能作为依据。
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        error = payload.get("error", payload) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            parameter = error.get("param")
            message = error.get("message", "")
            message = message if isinstance(message, str) else ""
            reasoning_parameters = [key for key in probe.sent_parameters if
                "reasoning" in key or "thinking" in key.lower() or key == "output_config.effort"]
            if isinstance(parameter, str):
                matches_sent = any(parameter == key or (
                    key.startswith(parameter + ".") and ("reasoning" in parameter or "thinking" in parameter.lower())
                ) for key in reasoning_parameters)
                explicit_code = error.get("code") in ("unsupported_parameter", "unsupported_value", "invalid_parameter", "invalid_value")
                if matches_sent and (explicit_code or re.search(r"^(?:unsupported|invalid) (?:parameter|value)\b", message, re.IGNORECASE)):
                    probe.reasoning_status = "rejected"
    call.last_response = response.text
    if response.is_error or is_backend_debug_enabled():
        logger.log(
            logging.WARNING if response.is_error else logging.DEBUG,
            "[LLM 原始响应] send=%d status=%d payload=\n%s", sequence, response.status_code, response.text,
        )
        call.last_response_printed = True


def log_parse_error(error: Exception, *, content: Any, schema: type[BaseModel], message: str) -> None:
    """保留参与解析的完整输入和目标结构，包括进入格式审校前的失败。

    Args:
        error: JSON 或字段校验异常。
        content: 实际送入解析器的数据。
        schema: 解析器要求的 Pydantic 模型。
        message: 所在步骤及下一步动作。

    Returns:
        无。
    """
    call = _current_call.get(None)
    if call is not None:
        call.parse_input_logged = True
    logger.error("[LLM 解析输入] %s content=\n%s\nschema=\n%s", message, format_payload(content), format_payload(schema.model_json_schema()))
    log_exception(logger, message, error)
