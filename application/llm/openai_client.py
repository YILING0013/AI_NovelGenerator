"""OpenAI 兼容客户端实现，支持 OpenAI / DeepSeek / OpenRouter 等兼容平台。"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

from application.llm.base_client import BaseLLMClient
from application.llm.config import LLMProviderConfig
from application.llm.exceptions import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
)
from application.llm.logger import log_llm_error, log_llm_request, log_llm_response
from application.llm.models import LLMRequest, LLMResponse, TokenUsage


class OpenAICompatibleClient(BaseLLMClient):
    """基于 Chat Completions API 的 OpenAI 兼容客户端。

    兼容所有支持 /v1/chat/completions 端点的服务商，
    结构化输出通过 beta.chat.completions.parse() 实现。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "openai") -> None:
        super().__init__(config, provider_name)
        self._client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=float(config.timeout_seconds),
            max_retries=config.max_retries,
        )

    def _build_params(self, request: LLMRequest) -> dict[str, Any]:
        """根据请求构建 Chat Completions API 调用参数。"""
        params: dict[str, Any] = {
            "model": self._resolve_model(request),
            "messages": self._build_messages(request),
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.top_p is not None:
            params["top_p"] = request.top_p
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.presence_penalty is not None:
            params["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            params["frequency_penalty"] = request.frequency_penalty
        if request.stop is not None:
            params["stop"] = request.stop
        return params

    def _map_error(self, exc: Exception, model: str = "") -> LLMError:
        """将 OpenAI SDK 异常映射为自定义异常。"""
        kwargs = {"provider": self.provider_name, "model": model}
        if isinstance(exc, openai.AuthenticationError):
            return LLMAuthError(str(exc), **kwargs)
        if isinstance(exc, openai.RateLimitError):
            return LLMRateLimitError(str(exc), **kwargs)
        if isinstance(exc, openai.APITimeoutError):
            return LLMTimeoutError(str(exc), **kwargs)
        if isinstance(exc, openai.APIError):
            return LLMResponseError(str(exc), **kwargs)
        return LLMError(str(exc), **kwargs)

    @staticmethod
    def _extract_usage(usage: Any) -> TokenUsage:
        """从响应中提取 Token 用量。"""
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """调用 Chat Completions API 进行普通文本生成。"""
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        try:
            resp = await self._client.chat.completions.create(**self._build_params(request))
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0] if resp.choices else None
        result = LLMResponse(
            content=(choice.message.content or "") if choice else "",
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else None,
            usage=self._extract_usage(resp.usage),
            model=resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=(choice.finish_reason or "") if choice else "",
            success=True,
        )
        log_llm_response(result)
        return result

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """通过 beta.chat.completions.parse() 进行结构化 JSON 输出。

        将 Pydantic Schema 作为 response_format 传入，SDK 自动处理
        JSON Schema 注入与响应解析，返回的 content 为序列化后的 JSON 字符串。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        try:
            params = self._build_params(request)
            resp = await self._client.beta.chat.completions.parse(
                **params,
                response_format=schema,
            )
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0] if resp.choices else None

        # 提取解析后的结构化对象
        parsed_obj = choice.message.parsed if choice else None
        if parsed_obj is None:
            refusal = getattr(choice.message, "refusal", None) if choice else None
            err_msg = refusal or "模型未返回有效的结构化输出"
            error = LLMSchemaError(err_msg, provider=self.provider_name, model=model)
            log_llm_error(error, provider=self.provider_name, model=model)
            raise error

        result = LLMResponse(
            content=parsed_obj.model_dump_json(),
            raw_response=resp.model_dump(warnings=False) if hasattr(resp, "model_dump") else None,
            usage=self._extract_usage(resp.usage),
            model=resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=(choice.finish_reason or "") if choice else "",
            success=True,
        )
        log_llm_response(result)
        return result

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式调用 Chat Completions API，逐块 yield 生成文本。"""
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)

        try:
            params = self._build_params(request)
            params["stream"] = True
            stream = await self._client.chat.completions.create(**params)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc
