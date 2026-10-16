"""Anthropic Claude 客户端实现，基于 anthropic 官方 SDK。"""

from __future__ import annotations

import json
import time
import re
from typing import Any, AsyncGenerator

import anthropic
from anthropic import AsyncAnthropic, transform_schema
from pydantic import BaseModel

from backend.llm.base_client import BaseLLMClient, _BeforeSendError, _ThinkStreamFilter
from backend.llm.config import LLMProviderConfig
from backend.llm.exceptions import LLMConnectionError
from backend.llm.exceptions import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMSchemaError,
    LLMTimeoutError,
)
from backend.llm.provider_probe import observe_provider_response
from backend.llm.logger import LLMCall, log_http_request, log_http_response, log_parse_error
from backend.llm.json_guard import reject_duplicate_json_keys
from backend.llm.models import LLMFunctionCallProbe, LLMRequest, LLMResponse, TokenUsage, LLMToolCall, LLMToolDefinition, LLMToolResult, LLMToolTurn


def _json_member_slices(raw: str) -> dict[str, str]:
    """提取对象中各字段的原文，避免工具参数在检查前丢掉重复字段。

    Args:
        raw: 服务商响应中的一个 JSON 对象。
    Returns:
        字段名及其值的原始 JSON 文本。
    """
    decoder = json.JSONDecoder()
    members = {}
    position = 1
    while True:
        position += len(raw[position:]) - len(raw[position:].lstrip())
        if raw[position] == "}":
            return members
        key, position = decoder.raw_decode(raw, position)
        position += len(raw[position:]) - len(raw[position:].lstrip()) + 1
        position += len(raw[position:]) - len(raw[position:].lstrip())
        start = position
        _, position = decoder.raw_decode(raw, position)
        members[key] = raw[start:position]
        position += len(raw[position:]) - len(raw[position:].lstrip())
        if raw[position] == ",":
            position += 1


def build_claude_parameters(request: LLMRequest, config: LLMProviderConfig) -> dict[str, Any]:
    """构建实际调用和任务图预览共用的参数。

    Args:
        request: 已合并默认值的请求。
        config: Provider 配置。
    Returns:
        不含凭据的 Messages 参数。
    """
    # Claude 的 messages 不含 system 角色，system 通过独立参数传入
    messages: list[dict[str, str]] = []
    for msg in request.messages:
        role = msg["role"]
        if role == "system":
            continue  # system 通过 system 参数传入
        # Claude 仅支持 "user" 和 "assistant"
        messages.append({"role": role, "content": msg["content"]})

    params: dict[str, Any] = {
        "model": request.model or config.default_model,
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

    # 当前 SDK 已移除采样参数，避免让用户误以为设置仍生效。
    if request.temperature is not None or request.top_p is not None:
        raise ValueError("Claude 当前接口不再支持 temperature 和 top_p，请关闭这两个采样参数")
    if request.reasoning_mode or request.verbosity:
        raise ValueError("Claude 不支持 OpenAI 的推理模式或输出详细程度参数")
    if request.reasoning_effort not in (None, "low", "medium", "high", "xhigh", "max"):
        raise ValueError("Claude 思考等级支持 low、medium、high、xhigh、max")
    model = params["model"].lower()
    thinking_mode = request.thinking_mode
    if request.thinking_budget is not None:
        if thinking_mode not in (None, "enabled"):
            raise ValueError("手动思考预算不能与自适应或关闭思考同时设置")
        if re.search(r"claude-(?:opus-4-[78]|\w+-5|mythos)", model):
            raise ValueError("当前 Claude 模型使用自适应思考，请取消 token 预算并选择思考等级")
        if not 1024 <= request.thinking_budget < params["max_tokens"]:
            raise ValueError("Claude 思考预算至少为 1024，且必须小于最大输出 token 数")
        params["thinking"] = {"type": "enabled", "budget_tokens": request.thinking_budget}
    elif thinking_mode == "enabled":
        raise ValueError("Claude enabled 模式需要思考预算；新模型请选择 adaptive")
    elif thinking_mode:
        if thinking_mode == "disabled" and ("opus-5-5" in model or "sonnet-5-5" in model):
            raise ValueError("当前 Claude 模型不能关闭思考，请降低思考等级")
        if thinking_mode == "between_tools" and request.reasoning_effort in {"xhigh", "max"}:
            raise ValueError("between_tools 使用 low、medium、high 等级；模型是否支持请查看接口测试结果")
        params["thinking"] = {"type": thinking_mode}
    elif request.reasoning_effort and re.search(r"claude-(?:opus-4-[678]|sonnet-4-6)", model):
        params["thinking"] = {"type": "adaptive"}
    if request.reasoning_effort:
        params["output_config"] = {"effort": request.reasoning_effort}
    if request.json_output_schema is not None and config.supports_json_schema and config.structured_output_mode != "tool_call":
        params.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": transform_schema(request.json_output_schema)}
    if request.stop is not None:
        params["stop_sequences"] = request.stop

    return params


class _ClaudeBeforeSendError(_BeforeSendError, anthropic.AnthropicError):
    """让 Claude SDK 直接抛回校验失败，不包装成可重试的连接错误。"""


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude 客户端，通过 anthropic SDK 调用 Messages API。

    结构化输出使用 output_config.format，旧模型可显式选择 tool_use 兼容模式。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "claude") -> None:
        super().__init__(config, provider_name)
        self._http_client = anthropic.DefaultAsyncHttpxClient(
            trust_env=config.use_system_proxy,
            timeout=float(config.timeout_seconds),
            event_hooks={"request": [self._before_http_request, log_http_request], "response": [log_http_response]},
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

    async def _before_http_request(self, request: Any) -> None:
        """沿用实例回调，只让 SDK 识别校验失败不是连接失败。"""
        try:
            await super()._before_http_request(request)
        except _BeforeSendError as exc:
            raise _ClaudeBeforeSendError(exc.original) from None

    def _build_params(self, request: LLMRequest) -> dict[str, Any]:
        return build_claude_parameters(request, self.config)

    def _map_error(self, exc: Exception, model: str = "") -> LLMError:
        """将 Anthropic SDK 异常映射为自定义异常。"""
        if isinstance(exc, _BeforeSendError):
            exc.__cause__ = exc.__context__ = None
            raise exc.original from exc.original.__cause__
        kwargs = {"provider": self.provider_name, "model": model}
        if isinstance(exc, LLMError):
            return exc
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

    async def _create_message(self, params: dict[str, Any], *, stream: bool) -> Any:
        """按已选方式请求，流式时收齐文本、工具参数和思考签名。

        Args:
            params: 已构建的 Messages 参数。
            stream: 是否使用流式请求。
        Returns:
            SDK 完整消息，供原有解析和两轮上下文复用。
        """
        if not stream:
            return await self._client.messages.create(**params)
        finished = False
        tool_json: dict[int, str] = {}
        async with self._client.messages.stream(**params) as events:
            async for event in events:
                observe_provider_response(event, self.config.resolved_api_mode)
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    tool_json[event.index] = ""
                elif event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                    tool_json[event.index] += event.delta.partial_json
                elif event.type == "content_block_stop" and tool_json.get(event.index):
                    # SDK 允许部分 JSON，必须另查原文是否完整且没有重复字段。
                    reject_duplicate_json_keys(tool_json[event.index])
                    json.loads(tool_json[event.index])
                elif event.type == "message_stop":
                    finished = True
            if not finished:
                raise LLMConnectionError("Claude 响应流提前断开，请重试", provider=self.provider_name)
            response = await events.get_final_message()
        if response.stop_reason not in {"end_turn", "stop_sequence", "tool_use"}:
            raise LLMResponseError(f"Claude 回复未完成：{response.stop_reason}", provider=self.provider_name)
        return response

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """调用 Claude Messages API 进行普通文本生成。"""
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "text", use_system_proxy=self.config.use_system_proxy) as call:
            start = time.perf_counter()

            try:
                resp = await self._client.messages.create(**self._build_params(request))
                observe_provider_response(resp, self.config.resolved_api_mode)
            except LLMError:
                raise
            except Exception as exc:
                mapped = self._map_error(exc, model)
                raise mapped from exc

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # 提取文本内容（Claude 返回 content blocks 列表）
            text_parts: list[str] = []
            for block in resp.content:
                if block.type == "text":
                    text_parts.append(block.text)
            content = "".join(text_parts)

            if resp.stop_reason == "max_tokens":
                call.finish_reason = resp.stop_reason
                call.usage = self._extract_usage(resp.usage)
                raise LLMResponseError(
                    "模型输出达到长度上限，内容未完成", provider=self.provider_name, model=model,
                    partial_text=content,
                )
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
            if request.json_output_schema is not None:
                reject_duplicate_json_keys(result.content)
            result = self._finalize_response(result, preserve_json_strings=request.json_output_schema is not None)
            call.result = result
            return result

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """使用原生 JSON Schema 输出，或用户明确选择的旧工具输出方式。

        Args:
            request: 消息与生成参数。
            schema: 业务需要的 Pydantic 结构。
        Returns:
            通过本地完整校验的 JSON 响应。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "schema", schema=schema, use_system_proxy=self.config.use_system_proxy) as call:
            start = time.perf_counter()

            tool_def = {
                "name": "structured_output",
                "description": f"按照 {schema.__name__} 结构输出结果",
                "input_schema": schema.model_json_schema(),
            }

            try:
                params = self._build_params(request)
                if self.config.structured_output_mode == "tool_call":
                    if params.get("thinking", {}).get("type") in {"enabled", "adaptive", "between_tools"}:
                        raise ValueError("工具式结构化输出不能强制调用思考模型，请选择原生 JSON Schema")
                    params["tools"] = [tool_def]
                    params["tool_choice"] = {"type": "tool", "name": "structured_output"}
                    if request.stream:
                        resp = await self._create_message(params, stream=True)
                    else:
                        raw_response = await self._client.messages.with_raw_response.create(**params)
                        raw_body = (await raw_response.text()).strip()
                        # SDK 会把 input 转成 dict；仅检查约定工具的参数原文，不检查协议历史。
                        try:
                            content = _json_member_slices(raw_body).get("content", "[]")
                            decoder = json.JSONDecoder()
                            position = 1
                            while position < len(content):
                                position += len(content[position:]) - len(content[position:].lstrip())
                                if content[position] == "]":
                                    break
                                block, end = decoder.raw_decode(content, position)
                                if block.get("type") == "tool_use" and block.get("name") == "structured_output":
                                    fields = _json_member_slices(content[position:end])
                                    if "input" in fields:
                                        reject_duplicate_json_keys(fields["input"])
                                    break
                                position = end
                                position += len(content[position:]) - len(content[position:].lstrip())
                                if content[position] == ",":
                                    position += 1
                        except json.JSONDecodeError:
                            # 非 JSON 响应仍交给 SDK 和原有错误处理。
                            pass
                        resp = await raw_response.parse()
                    observe_provider_response(resp, self.config.resolved_api_mode)
                else:
                    params.setdefault("output_config", {})["format"] = {"type": "json_schema", "schema": transform_schema(schema)}
                    resp = await self._create_message(params, stream=request.stream)
                    observe_provider_response(resp, self.config.resolved_api_mode)
            except LLMError:
                raise
            except Exception as exc:
                mapped = self._map_error(exc, model)
                raise mapped from exc

            elapsed_ms = int((time.perf_counter() - start) * 1000)

            if resp.stop_reason in {"max_tokens", "refusal"}:
                raise LLMSchemaError(f"Claude 未完成结构化输出：{resp.stop_reason}", provider=self.provider_name, model=model)
            # 原生输出从文本读取，旧接口只读取约定的工具参数。
            tool_input: dict[str, Any] | str | None = None
            if self.config.structured_output_mode == "tool_call":
                for block in resp.content:
                    if block.type == "tool_use" and block.name == "structured_output":
                        tool_input = block.input
                        break
            else:
                tool_input = "".join(block.text for block in resp.content if block.type == "text")

            if tool_input is None:
                error = LLMSchemaError(
                    "Claude 未返回有效的 tool_use 结构化输出",
                    provider=self.provider_name,
                    model=model,
                )
                raise error

            # 验证返回的数据符合 Schema
            if isinstance(tool_input, str):
                reject_duplicate_json_keys(tool_input)
            try:
                parsed = schema.model_validate_json(tool_input) if isinstance(tool_input, str) else schema.model_validate(tool_input)
            except Exception as parse_exc:
                log_parse_error(parse_exc, content=tool_input, schema=schema, message="Claude 结构化输出校验失败")
                error = LLMSchemaError(
                    f"Claude 返回内容无法解析为目标 Schema: {parse_exc}",
                    provider=self.provider_name,
                    model=model,
                )
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
            result = self._finalize_response(result, preserve_json_strings=True)
            call.result = result
            return result

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式调用 Claude Messages API，逐块 yield 生成文本。"""
        # 流式入口统一标记请求语义，保证调试日志与实际 SDK 调用保持一致。
        request = self._apply_defaults(request).model_copy(update={"stream": True})
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "stream", use_system_proxy=self.config.use_system_proxy) as call:

            try:
                params = self._build_params(request)
                stream = await self._client.messages.create(**params, stream=True)
                stream_filter = _ThinkStreamFilter(preserve_json_strings=request.json_output_schema is not None)
                async with stream:
                    async for event in stream:
                        observe_provider_response(event, self.config.resolved_api_mode)
                        call.chunk_count += 1
                        if event.type == "message_start":
                            call.usage = self._extract_usage(event.message.usage)
                        elif event.type == "message_delta":
                            call.finish_reason = event.delta.stop_reason or ""
                            input_tokens = event.usage.input_tokens or call.usage.input_tokens
                            output_tokens = event.usage.output_tokens
                            call.usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens)
                        if event.type == "content_block_delta" and event.delta.type == "text_delta":
                            text = event.delta.text
                            call.chunks.append(text)
                            clean_text = stream_filter.feed(text)
                            if clean_text:
                                yield clean_text
                if not call.finish_reason:
                    raise LLMConnectionError("Claude 响应流提前断开，请重试", provider=self.provider_name, model=model)
                if call.finish_reason == "max_tokens":
                    raise LLMResponseError(
                        "模型输出达到长度上限，内容未完成", provider=self.provider_name, model=model,
                        partial_text="".join(call.chunks),
                    )
                if request.json_output_schema is not None:
                    reject_duplicate_json_keys("".join(call.chunks))
                tail = stream_filter.finish()
                if tail:
                    yield tail
            except LLMError:
                raise
            except Exception as exc:
                mapped = self._map_error(exc, model)
                raise mapped from exc

    async def tool_turn(
        self, request: LLMRequest, tools: list[LLMToolDefinition], *,
        history: list[dict[str, Any]] | None = None,
        results: list[LLMToolResult] | None = None,
    ) -> LLMToolTurn:
        """执行 Claude 工具对话，保留思考块并紧接着回传全部调用结果。

        Args:
            request: 固定的提示和参数。
            tools: 服务端工具白名单。
            history: 本客户端上一轮返回的原生消息。
            results: 上轮全部调用的结果。
        Returns:
            本轮调用、正文、用量及完整原生消息。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        params = self._build_params(request)
        if "output_config" in params:
            params["output_config"].pop("format", None)
        messages = list(history) if history is not None else params["messages"]
        if results:
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": result.id,
                 "content": json.dumps(result.content, ensure_ascii=False), "is_error": result.is_error}
                for result in results
            ]})
        params.update(messages=messages, tool_choice={"type": "auto"}, tools=[
            {"name": tool.name, "description": tool.description, "input_schema": tool.parameters} for tool in tools
        ])
        try:
            response = await self._create_message(params, stream=request.stream)
            observe_provider_response(response, self.config.resolved_api_mode)
            if response.stop_reason not in {"end_turn", "stop_sequence", "tool_use"}:
                raise LLMResponseError(f"Claude 工具回复未完成：{response.stop_reason}，请检查输出上限或输入", provider=self.provider_name, model=model)
            messages.append({"role": "assistant", "content": [block.model_dump(mode="json", exclude_none=True) for block in response.content]})
            calls = [LLMToolCall(id=block.id, name=block.name, arguments=block.input)
                     for block in response.content if block.type == "tool_use"]
            text = "".join(block.text for block in response.content if block.type == "text")
            return LLMToolTurn(content=self._sanitize_text_content(text), calls=calls, history=messages,
                               usage=self._extract_usage(response.usage), finish_reason=response.stop_reason or "")
        except LLMError:
            raise
        except Exception as exc:
            raise self._map_error(exc, model) from exc

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
        with LLMCall(self.provider_name, model, "function_call", use_system_proxy=self.config.use_system_proxy) as call:
            start = time.perf_counter()
            tool_def = {
                "name": probe.tool_name,
                "description": probe.tool_description,
                "input_schema": probe.parameters_schema,
            }

            try:
                params = self._build_params(request)
                params["tools"] = [tool_def]
                params["tool_choice"] = {"type": "auto"}
                first_resp = await self._create_message(params, stream=request.stream)
                observe_provider_response(first_resp, self.config.resolved_api_mode)
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
                final_resp = await self._create_message(final_params, stream=request.stream)
                observe_provider_response(final_resp, self.config.resolved_api_mode)
            except LLMError:
                raise
            except Exception as exc:
                mapped = self._map_error(exc, model)
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
            call.result = result
            return result
