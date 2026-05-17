"""Anthropic Claude 客户端实现，基于 anthropic 官方 SDK。"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

import anthropic
from anthropic import AsyncAnthropic
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


def _pydantic_to_json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """将 Pydantic 模型转换为 Claude 所需的 JSON Schema 格式。"""
    raw = schema.model_json_schema()
    # Claude 的 tool input_schema 不接受顶层 $defs / definitions，需要内联展开
    # 对于简单 Schema 直接使用即可；复杂嵌套由 SDK 自动处理
    return raw


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude 客户端，通过 anthropic SDK 调用 Messages API。

    结构化输出通过 tool_use 模式实现：定义一个包含目标 Schema 的 tool，
    强制模型以 tool_use 形式返回结构化 JSON。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "claude") -> None:
        super().__init__(config, provider_name)
        self._http_client = anthropic.DefaultAsyncHttpxClient(
            trust_env=config.use_system_proxy,
            timeout=float(config.timeout_seconds),
        )
        client_kwargs: dict[str, Any] = {
            "api_key": config.api_key,
            "timeout": float(config.timeout_seconds),
            "max_retries": config.max_retries,
            "http_client": self._http_client,
        }
        if config.base_url:
            client_kwargs["base_url"] = config.base_url
        self._client = AsyncAnthropic(**client_kwargs)

    def _build_params(self, request: LLMRequest) -> dict[str, Any]:
        """构建 Claude Messages API 调用参数。"""
        # Claude 的 messages 不含 system 角色，system 通过独立参数传入
        messages: list[dict[str, str]] = []
        for msg in request.messages:
            role = msg["role"]
            if role == "system":
                continue  # system 通过 system 参数传入
            # Claude 仅支持 "user" 和 "assistant"
            messages.append({"role": role, "content": msg["content"]})

        params: dict[str, Any] = {
            "model": self._resolve_model(request),
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
        }

        # 合并所有 system 内容
        system_parts: list[str] = []
        if request.system_prompt:
            system_parts.append(request.system_prompt)
        for msg in request.messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
        if system_parts:
            params["system"] = "\n".join(system_parts)

        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.top_p is not None:
            params["top_p"] = request.top_p
        if request.stop is not None:
            params["stop_sequences"] = request.stop

        return params

    def _map_error(self, exc: Exception, model: str = "") -> LLMError:
        """将 Anthropic SDK 异常映射为自定义异常。"""
        kwargs = {"provider": self.provider_name, "model": model}
        if isinstance(exc, anthropic.AuthenticationError):
            return LLMAuthError(str(exc), **kwargs)
        if isinstance(exc, anthropic.RateLimitError):
            return LLMRateLimitError(str(exc), **kwargs)
        if isinstance(exc, anthropic.APITimeoutError):
            return LLMTimeoutError(str(exc), **kwargs)
        if isinstance(exc, anthropic.APIError):
            return LLMResponseError(str(exc), **kwargs)
        return LLMError(str(exc), **kwargs)

    @staticmethod
    def _extract_usage(usage: Any) -> TokenUsage:
        """从 Claude 响应中提取 Token 用量。"""
        if usage is None:
            return TokenUsage()
        input_t = getattr(usage, "input_tokens", 0) or 0
        output_t = getattr(usage, "output_tokens", 0) or 0
        return TokenUsage(
            input_tokens=input_t,
            output_tokens=output_t,
            total_tokens=input_t + output_t,
        )

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """调用 Claude Messages API 进行普通文本生成。"""
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        try:
            resp = await self._client.messages.create(**self._build_params(request))
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # 提取文本内容（Claude 返回 content blocks 列表）
        text_parts: list[str] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
        content = "".join(text_parts)

        result = LLMResponse(
            content=content,
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else None,
            usage=self._extract_usage(resp.usage),
            model=resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=resp.stop_reason or "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """通过 Claude 的 tool_use 模式进行结构化 JSON 输出。

        定义一个名为 "structured_output" 的 tool，其 input_schema 为目标
        Pydantic Schema 对应的 JSON Schema，并通过 tool_choice 强制模型
        以 tool_use 形式返回结构化数据。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        tool_def = {
            "name": "structured_output",
            "description": f"按照 {schema.__name__} 结构输出结果",
            "input_schema": _pydantic_to_json_schema(schema),
        }

        try:
            params = self._build_params(request)
            params["tools"] = [tool_def]
            params["tool_choice"] = {"type": "tool", "name": "structured_output"}
            resp = await self._client.messages.create(**params)
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # 从 tool_use block 中提取结构化数据
        tool_input: dict[str, Any] | None = None
        for block in resp.content:
            if block.type == "tool_use" and block.name == "structured_output":
                tool_input = block.input
                break

        if tool_input is None:
            error = LLMSchemaError(
                "Claude 未返回有效的 tool_use 结构化输出",
                provider=self.provider_name,
                model=model,
            )
            log_llm_error(error, provider=self.provider_name, model=model)
            raise error

        # 验证返回的数据符合 Schema
        try:
            parsed = schema.model_validate(tool_input)
        except Exception as parse_exc:
            error = LLMSchemaError(
                f"Claude 返回内容无法解析为目标 Schema: {parse_exc}",
                provider=self.provider_name,
                model=model,
            )
            log_llm_error(error, provider=self.provider_name, model=model)
            raise error from parse_exc

        result = LLMResponse(
            content=parsed.model_dump_json(),
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else None,
            usage=self._extract_usage(resp.usage),
            model=resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=resp.stop_reason or "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式调用 Claude Messages API，逐块 yield 生成文本。"""
        # 流式入口统一标记请求语义，保证调试日志与实际 SDK 调用保持一致。
        request = self._apply_defaults(request).model_copy(update={"stream": True})
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)

        try:
            params = self._build_params(request)
            async with self._client.messages.stream(**params) as stream:

                async def raw_chunks() -> AsyncGenerator[str, None]:
                    async for text in stream.text_stream:
                        yield text

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
        """执行 Claude tool_use Function Calling 两轮探测。

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
            "name": probe.tool_name,
            "description": probe.tool_description,
            "input_schema": probe.parameters_schema,
        }

        try:
            params = self._build_params(request)
            params["tools"] = [tool_def]
            params["tool_choice"] = {"type": "tool", "name": probe.tool_name}
            first_resp = await self._client.messages.create(**params)
            tool_block = next(
                (
                    block
                    for block in first_resp.content
                    if block.type == "tool_use" and block.name == probe.tool_name
                ),
                None,
            )
            if tool_block is None:
                raise ValueError("模型未返回指定工具调用")

            actual_args = dict(tool_block.input or {})
            self._validate_probe_arguments(actual_args, probe.expected_arguments)

            # Claude 需要带回 assistant 的 tool_use 块与 user 的 tool_result 块完成二轮。
            messages = list(params["messages"])
            messages.append(
                {
                    "role": "assistant",
                    "content": [block.model_dump() for block in first_resp.content],
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(probe.tool_result, ensure_ascii=False),
                        },
                        {
                            "type": "text",
                            "text": probe.final_response_prompt,
                        },
                    ],
                }
            )
            final_params = self._build_params(request)
            final_params["messages"] = messages
            final_params["tools"] = [tool_def]
            final_resp = await self._client.messages.create(**final_params)
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text_parts: list[str] = []
        for block in final_resp.content:
            if block.type == "text":
                text_parts.append(block.text)
        content = "".join(text_parts)
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
                "tool_call": first_resp.model_dump() if hasattr(first_resp, "model_dump") else None,
                "final": final_resp.model_dump() if hasattr(final_resp, "model_dump") else None,
            },
            usage=TokenUsage(
                input_tokens=first_usage.input_tokens + final_usage.input_tokens,
                output_tokens=first_usage.output_tokens + final_usage.output_tokens,
                total_tokens=first_usage.total_tokens + final_usage.total_tokens,
            ),
            model=final_resp.model or model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=final_resp.stop_reason or "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result
