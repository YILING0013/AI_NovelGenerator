"""LLM 调用日志工具。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from application.runtime import is_backend_debug_enabled

if TYPE_CHECKING:
    from application.llm.models import LLMRequest, LLMResponse

logger = logging.getLogger("llm")


def _format_debug_payload(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(payload)


def log_llm_request(request: LLMRequest, provider: str) -> None:
    """记录 LLM 请求摘要。"""
    logger.info(
        "[LLM 请求] provider=%s model=%s messages=%d temperature=%s max_tokens=%s",
        provider,
        request.model or "(default)",
        len(request.messages),
        request.temperature,
        request.max_tokens,
    )
    if is_backend_debug_enabled():
        logger.debug(
            "[LLM 请求详情] provider=%s payload=\n%s",
            provider,
            _format_debug_payload(
                {
                    "model": request.model or "(default)",
                    "system_prompt": request.system_prompt,
                    "messages": request.messages,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "max_tokens": request.max_tokens,
                    "presence_penalty": request.presence_penalty,
                    "frequency_penalty": request.frequency_penalty,
                    "stop": request.stop,
                    "stream": request.stream,
                    "metadata": request.metadata,
                }
            ),
        )


def log_llm_response(response: LLMResponse) -> None:
    """记录 LLM 响应摘要。"""
    if response.success:
        logger.info(
            "[LLM 响应] provider=%s model=%s tokens=%d duration=%dms finish=%s",
            response.provider,
            response.model,
            response.usage.total_tokens,
            response.duration_ms,
            response.finish_reason,
        )
    else:
        logger.warning(
            "[LLM 响应失败] provider=%s model=%s error=%s duration=%dms",
            response.provider,
            response.model,
            response.error,
            response.duration_ms,
        )

    if is_backend_debug_enabled():
        raw_payload = response.raw_response
        if raw_payload is None:
            raw_payload = {"content": response.content}
        logger.debug(
            "[LLM 原始响应] provider=%s model=%s payload=\n%s",
            response.provider,
            response.model,
            _format_debug_payload(raw_payload),
        )


def log_llm_error(error: Exception, *, provider: str = "", model: str = "") -> None:
    """记录 LLM 调用异常。"""
    logger.error(
        "[LLM 异常] provider=%s model=%s type=%s message=%s",
        provider,
        model,
        type(error).__name__,
        str(error),
    )
