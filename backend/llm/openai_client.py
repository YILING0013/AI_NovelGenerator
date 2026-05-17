"""OpenAI 兼容客户端实现，支持 OpenAI / DeepSeek / OpenRouter 等兼容平台。"""

from __future__ import annotations

import time
import json
import re
from typing import Any, AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.llm.base_client import BaseLLMClient
from backend.llm.config import LLMProviderConfig
from backend.llm.exceptions import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
)
from backend.llm.logger import log_llm_error, log_llm_request, log_llm_response
from backend.llm.models import LLMFunctionCallProbe, LLMRequest, LLMResponse, TokenUsage


_API_VERSION_RE = re.compile(r"^v\d+(?:[a-z0-9._-]+)?$", re.IGNORECASE)
_OPENAI_ENDPOINT_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("chat", "completions"),
    ("responses",),
    ("response",),
    ("completions",),
    ("embeddings",),
    ("images",),
    ("audio", "speech"),
    ("audio", "transcriptions"),
    ("audio", "translations"),
    ("moderations",),
    ("models",),
    ("files",),
    ("batches",),
    ("uploads",),
    ("assistants",),
    ("threads",),
    ("vector_stores",),
    ("fine_tuning", "jobs"),
)


def _trim_openai_endpoint_suffixes(segments: list[str]) -> list[str]:
    """移除用户误填到 base_url 末尾的 OpenAI 接口端点路径。

    Args:
        segments: URL path 拆分后的路径片段。

    Returns:
        已去掉已知接口端点尾巴的路径片段。
    """
    remaining = list(segments)
    while remaining:
        lowered = [segment.lower() for segment in remaining]
        matched = False
        for suffix in _OPENAI_ENDPOINT_SUFFIXES:
            if len(remaining) >= len(suffix) and tuple(lowered[-len(suffix) :]) == suffix:
                del remaining[-len(suffix) :]
                matched = True
                break
        if not matched:
            break
    return remaining


def _build_openai_sdk_base_url(base_url: str) -> str | None:
    """将配置中的 OpenAI 根地址转换为 SDK 需要的版本根地址。

    Args:
        base_url: 用户配置的服务根地址，兼容旧配置中已包含版本路径的地址。

    Returns:
        SDK 可直接使用的 base_url；空配置返回 None 以保留 SDK 默认行为。
    """
    trimmed = base_url.strip()
    if not trimmed:
        return None

    parsed = urlsplit(trimmed)
    if parsed.scheme and parsed.netloc:
        segments = _trim_openai_endpoint_suffixes([segment for segment in parsed.path.split("/") if segment])
        if not segments or not _API_VERSION_RE.fullmatch(segments[-1]):
            # 配置文件只保存服务根地址，OpenAI 兼容 SDK 调用前统一补到版本根路径。
            segments.append("v1")
        path = "/" + "/".join(segments)
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    segments = _trim_openai_endpoint_suffixes([segment for segment in trimmed.rstrip("/").split("/") if segment])
    if segments and _API_VERSION_RE.fullmatch(segments[-1]):
        return "/".join(segments)
    return f"{'/'.join(segments)}/v1"


class OpenAICompatibleClient(BaseLLMClient):
    """基于 Chat Completions API 的 OpenAI 兼容客户端。

    兼容所有支持 /v1/chat/completions 端点的服务商，
    结构化输出通过 beta.chat.completions.parse() 实现。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "openai") -> None:
        super().__init__(config, provider_name)
        self._http_client = openai.DefaultAsyncHttpxClient(
            trust_env=config.use_system_proxy,
            timeout=float(config.timeout_seconds),
        )
        self._client = AsyncOpenAI(
            base_url=_build_openai_sdk_base_url(config.base_url),
            api_key=config.api_key,
            timeout=float(config.timeout_seconds),
            max_retries=config.max_retries,
            http_client=self._http_client,
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
            raw_response=resp.model_dump(warnings=False) if hasattr(resp, "model_dump") else None,
            usage=self._extract_usage(resp.usage),
            model=resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=(choice.finish_reason or "") if choice else "",
            success=True,
        )
        result = self._finalize_response(result)
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
        result = self._finalize_response(result)
        log_llm_response(result)
        return result

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式调用 Chat Completions API，逐块 yield 生成文本。"""
        # 流式入口统一标记请求语义，保证调试日志与实际 SDK 调用保持一致。
        request = self._apply_defaults(request).model_copy(update={"stream": True})
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)

        try:
            params = self._build_params(request)
            params["stream"] = True
            stream = await self._client.chat.completions.create(**params)

            async def raw_chunks() -> AsyncGenerator[str, None]:
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

            async for clean_chunk in self._sanitize_stream_chunks(raw_chunks()):
                yield clean_chunk
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

    async def function_call_probe(
        self,
        request: LLMRequest,
        probe: LLMFunctionCallProbe,
    ) -> LLMResponse:
        """执行 OpenAI 兼容 Function Calling 两轮探测。

        Args:
            request: 第一轮触发工具调用的 LLM 请求。
            probe: 工具定义、期望参数和二轮校验文本。

        Returns:
            包含第二轮最终回复的 LLM 响应。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()
        tool_def = {
            "type": "function",
            "function": {
                "name": probe.tool_name,
                "description": probe.tool_description,
                "parameters": probe.parameters_schema,
                "strict": True,
            },
        }

        try:
            params = self._build_params(request)
            params["tools"] = [tool_def]
            params["tool_choice"] = {
                "type": "function",
                "function": {"name": probe.tool_name},
            }
            first_resp = await self._client.chat.completions.create(**params)
            first_choice = first_resp.choices[0] if first_resp.choices else None
            tool_calls = list(getattr(first_choice.message, "tool_calls", None) or []) if first_choice else []
            tool_call = next(
                (
                    call
                    for call in tool_calls
                    if getattr(getattr(call, "function", None), "name", "") == probe.tool_name
                ),
                None,
            )
            if tool_call is None:
                raise ValueError("模型未返回指定工具调用")

            actual_args = json.loads(tool_call.function.arguments or "{}")
            self._validate_probe_arguments(actual_args, probe.expected_arguments)

            # 第二轮把本地模拟工具结果回传给模型，确认接口能完成真实 tool-call 循环。
            messages = self._build_messages(request)
            messages.append(
                {
                    "role": "assistant",
                    "content": first_choice.message.content or "",
                    "tool_calls": [call.model_dump(exclude_none=True) for call in tool_calls],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(probe.tool_result, ensure_ascii=False),
                }
            )
            messages.append({"role": "user", "content": probe.final_response_prompt})
            final_request = request.model_copy(update={"messages": messages, "system_prompt": ""})
            final_resp = await self._client.chat.completions.create(**self._build_params(final_request))
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        final_choice = final_resp.choices[0] if final_resp.choices else None
        content = (final_choice.message.content or "") if final_choice else ""
        try:
            self._validate_probe_final_text(content, probe.expected_final_text)
        except ValueError as exc:
            mapped = LLMResponseError(str(exc), provider=self.provider_name, model=model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        first_usage = self._extract_usage(first_resp.usage)
        final_usage = self._extract_usage(final_resp.usage)
        result = LLMResponse(
            content=content,
            raw_response={
                "tool_call": first_resp.model_dump(warnings=False) if hasattr(first_resp, "model_dump") else None,
                "final": final_resp.model_dump(warnings=False) if hasattr(final_resp, "model_dump") else None,
            },
            usage=TokenUsage(
                input_tokens=first_usage.input_tokens + final_usage.input_tokens,
                output_tokens=first_usage.output_tokens + final_usage.output_tokens,
                total_tokens=first_usage.total_tokens + final_usage.total_tokens,
            ),
            model=final_resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=(final_choice.finish_reason or "") if final_choice else "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result
