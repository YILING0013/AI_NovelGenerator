"""Google Gemini 客户端实现，基于 google-genai 官方 SDK。"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator

from google import genai
from google.genai import types
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


class GeminiClient(BaseLLMClient):
    """Google Gemini 客户端，通过 google-genai SDK 调用 Gemini API。"""

    def __init__(self, config: LLMProviderConfig, provider_name: str = "gemini") -> None:
        super().__init__(config, provider_name)
        client_kwargs: dict[str, Any] = {"api_key": config.api_key}
        http_options_kwargs: dict[str, Any] = {
            "timeout": int(config.timeout_seconds * 1000),
            "client_args": {"trust_env": config.use_system_proxy},
            "async_client_args": {"trust_env": config.use_system_proxy},
        }
        if config.base_url:
            http_options_kwargs["base_url"] = config.base_url
        self._http_options = types.HttpOptions(**http_options_kwargs)
        client_kwargs["http_options"] = self._http_options
        self._client = genai.Client(**client_kwargs)

    def _build_contents(self, request: LLMRequest) -> list[types.Content]:
        """将 messages 转换为 Gemini SDK 的 Content 列表。"""
        contents: list[types.Content] = []
        for msg in request.messages:
            role = msg["role"]
            # Gemini 仅识别 "user" 和 "model" 角色
            if role == "assistant":
                role = "model"
            elif role == "system":
                # system 消息通过 system_instruction 处理，此处跳过
                continue
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        return contents

    def _build_config(self, request: LLMRequest) -> types.GenerateContentConfig:
        """构建 Gemini 生成配置参数。"""
        kwargs: dict[str, Any] = {}
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.top_p is not None:
            kwargs["top_p"] = request.top_p
        if request.max_tokens is not None:
            kwargs["max_output_tokens"] = request.max_tokens
        if request.presence_penalty is not None:
            kwargs["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            kwargs["frequency_penalty"] = request.frequency_penalty
        if request.stop is not None:
            kwargs["stop_sequences"] = request.stop
        if request.system_prompt:
            kwargs["system_instruction"] = request.system_prompt
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _exception_search_text(exc: Exception) -> str:
        """汇总异常链的类型与消息，兼容 httpx.ReadTimeout 这类空消息异常。"""
        parts: list[str] = []
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            parts.append(type(current).__name__)
            parts.append(str(current))
            current = current.__cause__ or current.__context__
        return " ".join(parts).lower()

    def _map_error(self, exc: Exception, model: str = "") -> LLMError:
        """将 Gemini SDK 异常映射为自定义异常。"""
        kwargs = {"provider": self.provider_name, "model": model}
        exc_str = self._exception_search_text(exc)
        if "api_key" in exc_str or "authentication" in exc_str or "permission" in exc_str:
            return LLMAuthError(str(exc), **kwargs)
        if "rate" in exc_str or "quota" in exc_str or "resource_exhausted" in exc_str:
            return LLMRateLimitError(str(exc), **kwargs)
        if "timeout" in exc_str or "deadline" in exc_str:
            return LLMTimeoutError(str(exc), **kwargs)
        return LLMResponseError(str(exc), **kwargs)

    @staticmethod
    def _extract_usage(usage_metadata: Any) -> TokenUsage:
        """从 Gemini 响应中提取 Token 用量。"""
        if usage_metadata is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=getattr(usage_metadata, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage_metadata, "candidates_token_count", 0) or 0,
            total_tokens=getattr(usage_metadata, "total_token_count", 0) or 0,
        )

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """调用 Gemini API 进行普通文本生成。"""
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=self._build_contents(request),
                config=self._build_config(request),
            )
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        result = LLMResponse(
            content=resp.text or "",
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else {"text": resp.text or ""},
            usage=self._extract_usage(resp.usage_metadata),
            model=model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=resp.candidates[0].finish_reason.name if resp.candidates else "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """通过 Gemini 的 response_schema 进行结构化 JSON 输出。

        将 Pydantic Schema 通过 generation_config 中的 response_mime_type
        和 response_schema 传入，获取符合 Schema 约束的 JSON 响应。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)
        start = time.perf_counter()

        try:
            config = self._build_config(request)
            config.response_mime_type = "application/json"
            config.response_schema = schema

            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=self._build_contents(request),
                config=config,
            )
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        text = self._sanitize_text_content(resp.text or "")

        # 验证返回的 JSON 能被 Schema 解析
        try:
            parsed = schema.model_validate_json(text)
        except Exception as parse_exc:
            error = LLMSchemaError(
                f"Gemini 返回内容无法解析为目标 Schema: {parse_exc}",
                provider=self.provider_name,
                model=model,
            )
            log_llm_error(error, provider=self.provider_name, model=model)
            raise error from parse_exc

        result = LLMResponse(
            content=parsed.model_dump_json(),
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else {"text": text},
            usage=self._extract_usage(resp.usage_metadata),
            model=model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=resp.candidates[0].finish_reason.name if resp.candidates else "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式调用 Gemini API，逐块 yield 生成文本。"""
        # 流式入口统一标记请求语义，保证调试日志与实际 SDK 调用保持一致。
        request = self._apply_defaults(request).model_copy(update={"stream": True})
        model = self._resolve_model(request)
        log_llm_request(request, self.provider_name)

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=model,
                contents=self._build_contents(request),
                config=self._build_config(request),
            )

            async def raw_chunks() -> AsyncGenerator[str, None]:
                async for chunk in stream:
                    if chunk.text:
                        yield chunk.text

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
        """执行 Gemini Function Calling 两轮探测。

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
        tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=probe.tool_name,
                    description=probe.tool_description,
                    parameters_json_schema=probe.parameters_schema,
                )
            ]
        )

        try:
            config = self._build_config(request)
            config.tools = [tool]
            config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY,
                    allowed_function_names=[probe.tool_name],
                )
            )
            contents = self._build_contents(request)
            first_resp = await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            first_content = first_resp.candidates[0].content if first_resp.candidates else None
            function_call = None
            for part in getattr(first_content, "parts", []) or []:
                if getattr(part, "function_call", None) and part.function_call.name == probe.tool_name:
                    function_call = part.function_call
                    break
            if function_call is None:
                raise ValueError("模型未返回指定工具调用")

            actual_args = dict(function_call.args or {})
            self._validate_probe_arguments(actual_args, probe.expected_arguments)

            # Gemini 需要把模型上一轮 content 与本地 function response 一起带回上下文。
            final_contents = list(contents)
            final_contents.append(first_content)
            final_contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=probe.tool_name,
                            response=probe.tool_result,
                        ),
                        types.Part(text=probe.final_response_prompt),
                    ],
                )
            )
            final_config = self._build_config(request)
            final_config.tools = [tool]
            final_resp = await self._client.aio.models.generate_content(
                model=model,
                contents=final_contents,
                config=final_config,
            )
        except Exception as exc:
            mapped = self._map_error(exc, model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        content = self._sanitize_text_content(final_resp.text or "")
        try:
            self._validate_probe_final_text(content, probe.expected_final_text)
        except ValueError as exc:
            mapped = LLMResponseError(str(exc), provider=self.provider_name, model=model)
            log_llm_error(mapped, provider=self.provider_name, model=model)
            raise mapped from exc

        first_usage = self._extract_usage(first_resp.usage_metadata)
        final_usage = self._extract_usage(final_resp.usage_metadata)
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
            model=model,
            provider=self.provider_name,
            duration_ms=elapsed_ms,
            finish_reason=final_resp.candidates[0].finish_reason.name if final_resp.candidates else "",
            success=True,
        )
        result = self._finalize_response(result)
        log_llm_response(result)
        return result
