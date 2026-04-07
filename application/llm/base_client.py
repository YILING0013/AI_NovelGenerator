"""LLM 客户端抽象基类，定义统一的生成接口。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from pydantic import BaseModel

from application.llm.config import LLMProviderConfig
from application.llm.models import LLMRequest, LLMResponse


_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</think>", re.IGNORECASE)


class _ThinkStreamFilter:
    """流式文本过滤器，支持跨 chunk 移除 <think>...</think> 内容。"""

    def __init__(self) -> None:
        self._buffer = ""
        self._inside_think = False

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""

        self._buffer += chunk
        output_parts: list[str] = []

        while self._buffer:
            if self._inside_think:
                close_match = _THINK_CLOSE_RE.search(self._buffer)
                if close_match:
                    self._buffer = self._buffer[close_match.end():]
                    self._inside_think = False
                    continue

                keep_len = len("</think>") - 1
                if len(self._buffer) > keep_len:
                    self._buffer = self._buffer[-keep_len:]
                break

            open_match = _THINK_OPEN_RE.search(self._buffer)
            if open_match:
                if open_match.start() > 0:
                    output_parts.append(self._buffer[:open_match.start()])
                self._buffer = self._buffer[open_match.end():]
                self._inside_think = True
                continue

            safe_length = self._safe_emit_length(self._buffer)
            if safe_length <= 0:
                break
            output_parts.append(self._buffer[:safe_length])
            self._buffer = self._buffer[safe_length:]

        return "".join(output_parts)

    def finish(self) -> str:
        if self._inside_think:
            return ""
        if self._is_potential_think_prefix(self._buffer):
            return ""
        return BaseLLMClient._sanitize_text_content(self._buffer)

    def _safe_emit_length(self, text: str) -> int:
        last_lt = text.rfind("<")
        if last_lt == -1:
            return len(text)
        tail = text[last_lt:]
        if self._is_potential_think_prefix(tail):
            return last_lt
        return len(text)

    @staticmethod
    def _is_potential_think_prefix(text: str) -> bool:
        lowered = text.lower()

        if "<think".startswith(lowered) or "</think>".startswith(lowered):
            return True

        if lowered.startswith("<think"):
            if len(lowered) == len("<think"):
                return True
            next_char = lowered[len("<think")]
            return not (next_char.isalnum() or next_char == "_")

        if lowered.startswith("</think"):
            if len(lowered) == len("</think"):
                return True
            next_char = lowered[len("</think")]
            return next_char == ">"

        return False


class BaseLLMClient(ABC):
    """所有 LLM 服务商客户端的抽象基类。

    子类需实现 text_generate / schema_generate / stream_text 三个核心方法。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "") -> None:
        self.config = config
        self.provider_name = provider_name

    def _resolve_model(self, request: LLMRequest) -> str:
        """确定实际使用的模型名称，请求未指定时回退到服务商默认模型。"""
        return request.model or self.config.default_model

    def _apply_defaults(self, request: LLMRequest) -> LLMRequest:
        """将服务商配置中的生成参数默认值合并到请求中（请求级别优先）。"""
        cfg = self.config
        overrides: dict = {}
        if request.temperature is None and cfg.temperature is not None:
            overrides["temperature"] = cfg.temperature
        if request.top_p is None and cfg.top_p is not None:
            overrides["top_p"] = cfg.top_p
        if request.max_tokens is None and cfg.max_tokens is not None:
            overrides["max_tokens"] = cfg.max_tokens
        if request.presence_penalty is None and cfg.presence_penalty is not None:
            overrides["presence_penalty"] = cfg.presence_penalty
        if request.frequency_penalty is None and cfg.frequency_penalty is not None:
            overrides["frequency_penalty"] = cfg.frequency_penalty
        if not request.system_prompt and cfg.system_prompt:
            overrides["system_prompt"] = cfg.system_prompt
        if not overrides:
            return request
        return request.model_copy(update=overrides)

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """将 system_prompt 与 messages 合并为完整消息列表。"""
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)
        return messages

    @staticmethod
    def _sanitize_text_content(text: str) -> str:
        """移除响应文本中的 <think>...</think> 思维链。"""
        if not text:
            return text

        sanitized = _THINK_BLOCK_RE.sub("", text)
        sanitized = _THINK_OPEN_RE.sub("", sanitized)
        sanitized = _THINK_CLOSE_RE.sub("", sanitized)

        if sanitized != text:
            return sanitized.strip()
        return sanitized

    @classmethod
    def _sanitize_raw_response(cls, payload: Any) -> Any:
        """递归清洗原始响应中的 think 标签。"""
        if isinstance(payload, str):
            return cls._sanitize_text_content(payload)
        if isinstance(payload, list):
            return [cls._sanitize_raw_response(item) for item in payload]
        if isinstance(payload, tuple):
            return tuple(cls._sanitize_raw_response(item) for item in payload)
        if isinstance(payload, dict):
            return {key: cls._sanitize_raw_response(value) for key, value in payload.items()}
        return payload

    def _finalize_response(self, response: LLMResponse) -> LLMResponse:
        """在返回前统一清洗 content 与 raw_response。"""
        clean_content = self._sanitize_text_content(response.content)
        clean_raw_response = self._sanitize_raw_response(response.raw_response)

        if clean_content == response.content and clean_raw_response == response.raw_response:
            return response

        return response.model_copy(
            update={
                "content": clean_content,
                "raw_response": clean_raw_response,
            }
        )

    async def _sanitize_stream_chunks(
        self,
        chunks: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """统一清洗流式输出中的 think 标签。"""
        stream_filter = _ThinkStreamFilter()
        async for chunk in chunks:
            clean_chunk = stream_filter.feed(chunk)
            if clean_chunk:
                yield clean_chunk

        tail = stream_filter.finish()
        if tail:
            yield tail

    @abstractmethod
    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """普通文本生成。"""

    @abstractmethod
    async def schema_generate(
        self, request: LLMRequest, schema: type[BaseModel]
    ) -> LLMResponse:
        """结构化 JSON 输出，按 Pydantic Schema 约束生成。"""

    @abstractmethod
    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式文本输出，逐块 yield 生成内容。"""
