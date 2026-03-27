"""LLM 调用日志工具。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.llm.models import LLMRequest, LLMResponse

logger = logging.getLogger("llm")


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


def log_llm_error(error: Exception, *, provider: str = "", model: str = "") -> None:
    """记录 LLM 调用异常。"""
    logger.error(
        "[LLM 异常] provider=%s model=%s type=%s message=%s",
        provider,
        model,
        type(error).__name__,
        str(error),
    )
