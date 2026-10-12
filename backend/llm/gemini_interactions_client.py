"""Gemini Interactions 正式接口，客户端自行保留完整对话步骤。"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any, AsyncGenerator

from pydantic import BaseModel, ValidationError

from backend.llm.base_client import _ThinkStreamFilter
from backend.llm.exceptions import LLMError, LLMResponseError, LLMSchemaError
from backend.llm.gemini_client import GeminiClient, build_gemini_generation_config
from backend.llm.logger import LLMCall
from backend.llm.json_guard import reject_duplicate_json_keys
from backend.llm.models import LLMFunctionCallProbe, LLMRequest, LLMResponse, LLMToolCall, LLMToolDefinition, LLMToolResult, LLMToolTurn, TokenUsage


def build_interaction_parameters(request: LLMRequest, model: str, schema: type[BaseModel] | None = None) -> dict[str, Any]:
    """构建 Interactions 请求，正式调用和任务图模拟使用相同参数。

    Args:
        request: 已合并默认值的请求。
        model: 实际模型。
        schema: 可选的原生输出结构。
    Returns:
        无凭据、关闭服务端存储的 SDK 参数。
    """
    params: dict[str, Any] = {
        "model": model, "store": False,
        "input": [{"type": "model_output" if msg["role"] == "assistant" else "user_input",
                   "content": [{"type": "text", "text": msg["content"]}]}
                  for msg in request.messages if msg["role"] != "system"],
        "generation_config": build_gemini_generation_config(request, model, interactions=True),
    }
    system_parts = [request.system_prompt] if request.system_prompt else []
    system_parts.extend(msg["content"] for msg in request.messages if msg["role"] == "system")
    if system_parts:
        params["system_instruction"] = "\n".join(system_parts)
    if schema is not None:
        params["response_format"] = {"type": "text", "mime_type": "application/json", "schema": schema.model_json_schema()}
    return params


class GeminiInteractionsClient(GeminiClient):
    """沿用 GenAI SDK 连接与错误处理，使用 Interactions 的步骤协议。"""

    @staticmethod
    def _extract_usage(usage: Any) -> TokenUsage:
        if usage is None:
            return TokenUsage()
        return TokenUsage(input_tokens=usage.total_input_tokens or 0,
                          output_tokens=(usage.total_output_tokens or 0) + (usage.total_thought_tokens or 0),
                          total_tokens=usage.total_tokens or 0)

    def _check_interaction(self, response: Any, model: str, *, tools: bool = False) -> None:
        """只接受完成的响应，工具对话还允许等待工具结果。"""
        if response.status not in ({"completed", "requires_action"} if tools else {"completed"}):
            raise LLMResponseError(f"Gemini 请求未完成：{response.status}，请检查输出上限或输入",
                                   provider=self.provider_name, model=model)

    async def _generate(self, request: LLMRequest, schema: type[BaseModel] | None = None) -> LLMResponse:
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "schema" if schema else "text", schema=schema,
                     use_system_proxy=self.config.use_system_proxy) as call:
            start = time.perf_counter()
            try:
                response = await self._client.aio.interactions.create(**build_interaction_parameters(request, model, schema))
                self._check_interaction(response, model)
                content = response.output_text or ""
                if schema is not None or request.json_output_schema is not None:
                    reject_duplicate_json_keys(content)
                if schema is not None:
                    try:
                        content = schema.model_validate_json(content).model_dump_json()
                    except ValidationError as exc:
                        raise LLMSchemaError("Gemini 返回的 JSON 不符合目标结构", provider=self.provider_name, model=model) from exc
                result = self._finalize_response(LLMResponse(
                    content=content, raw_response=response.model_dump(mode="json"), usage=self._extract_usage(response.usage),
                    model=model, provider=self.provider_name, duration_ms=int((time.perf_counter() - start) * 1000),
                    finish_reason=response.status,
                ), preserve_json_strings=schema is not None or request.json_output_schema is not None)
                call.result = result
                return result
            except LLMError:
                raise
            except Exception as exc:
                raise self._map_error(exc, model) from exc

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """生成正文。

        Args:
            request: 消息与生成参数。
        Returns:
            正文、原始响应及用量。
        """
        return await self._generate(request)

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """使用新版 response_format 生成并校验 JSON。

        Args:
            request: 消息与生成参数。
            schema: 业务需要的输出结构。
        Returns:
            已校验的 JSON 及用量。
        """
        return await self._generate(request, schema)

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """转发正文事件，思考及签名不会发给前端。

        Args:
            request: 消息与生成参数。
        Yields:
            正文增量；截断、失败或断流时抛错。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "stream", use_system_proxy=self.config.use_system_proxy) as call:
            finished = False
            stream_filter = _ThinkStreamFilter(preserve_json_strings=request.json_output_schema is not None)
            try:
                params = build_interaction_parameters(request, model)
                if request.json_output_schema is not None and self.config.supports_json_schema:
                    params["response_format"] = {"type": "text", "mime_type": "application/json", "schema": request.json_output_schema}
                stream = await self._client.aio.interactions.create(**params, stream=True)
                async with stream:
                    async for event in stream:
                        call.chunk_count += 1
                        if event.event_type == "step.delta" and event.delta.type == "text":
                            call.chunks.append(event.delta.text)
                            text = stream_filter.feed(event.delta.text)
                            if text:
                                yield text
                        elif event.event_type == "interaction.completed":
                            self._check_interaction(event.interaction, model)
                            call.usage = self._extract_usage(event.interaction.usage)
                            call.finish_reason = event.interaction.status
                            finished = True
                        elif event.event_type == "error":
                            raise LLMResponseError(str(event.error), provider=self.provider_name, model=model)
                        elif event.event_type == "interaction.status_update" and event.status in {"failed", "incomplete", "cancelled"}:
                            raise LLMResponseError(f"Gemini 请求未完成：{event.status}", provider=self.provider_name, model=model)
                if not finished:
                    raise LLMResponseError("Gemini 响应流提前断开，请重试", provider=self.provider_name, model=model)
                if request.json_output_schema is not None:
                    reject_duplicate_json_keys("".join(call.chunks))
                tail = stream_filter.finish()
                if tail:
                    yield tail
            except LLMError:
                raise
            except Exception as exc:
                raise self._map_error(exc, model) from exc

    async def tool_turn(self, request: LLMRequest, tools: list[LLMToolDefinition], *,
                        history: list[dict[str, Any]] | None = None,
                        results: list[LLMToolResult] | None = None) -> LLMToolTurn:
        """执行工具对话，并原样保存 thought、签名和所有调用步骤。

        Args:
            request: 固定的消息与参数。
            tools: 允许调用的工具。
            history: 前轮完整步骤。
            results: 全部工具执行结果。
        Returns:
            正文、工具调用、用量与私有步骤历史。
        """
        request = self._apply_defaults(request)
        model = self._resolve_model(request)
        try:
            params = build_interaction_parameters(request, model)
            steps = deepcopy(history) if history is not None else params["input"]
            steps.extend({"type": "function_result", "name": result.name, "call_id": result.id,
                          "result": [{"type": "text", "text": json.dumps(result.content, ensure_ascii=False)}]}
                         for result in results or [])
            params.update(input=steps, tools=[{"type": "function", **tool.model_dump()} for tool in tools])
            params["generation_config"]["tool_choice"] = "auto"
            response = await self._client.aio.interactions.create(**params)
            self._check_interaction(response, model, tools=True)
            steps.extend(step.model_dump(mode="json", exclude_none=True) for step in response.steps or [])
            calls = [LLMToolCall(id=step.id, name=step.name, arguments=step.arguments)
                     for step in response.steps or [] if step.type == "function_call"]
            return LLMToolTurn(content=self._sanitize_text_content(response.output_text or ""), calls=calls,
                               history=steps, usage=self._extract_usage(response.usage), finish_reason=response.status)
        except LLMError:
            raise
        except Exception as exc:
            raise self._map_error(exc, model) from exc

    async def function_call_probe(self, request: LLMRequest, probe: LLMFunctionCallProbe) -> LLMResponse:
        """通过正式工具对话路径测试两轮交互。

        Args:
            request: 触发工具的提示。
            probe: 期望参数和模拟工具结果。
        Returns:
            最终回复与两轮合计用量。
        """
        model = self._resolve_model(request)
        with LLMCall(self.provider_name, model, "function_call", use_system_proxy=self.config.use_system_proxy) as call:
            start = time.perf_counter()
            tools = [LLMToolDefinition(name=probe.tool_name, description=probe.tool_description, parameters=probe.parameters_schema)]
            first = await self.tool_turn(request, tools)
            if not first.calls or any(item.name != probe.tool_name for item in first.calls):
                raise LLMResponseError("Gemini 未返回指定工具调用", provider=self.provider_name, model=model)
            for item in first.calls:
                self._validate_probe_arguments(item.arguments, probe.expected_arguments)
            results = [LLMToolResult(id=item.id, name=item.name,
                                    content={**probe.tool_result, "next_instruction": probe.final_response_prompt}) for item in first.calls]
            final = await self.tool_turn(request, tools, history=first.history, results=results)
            self._validate_probe_final_text(final.content, probe.expected_final_text)
            result = LLMResponse(content=final.content, model=model, provider=self.provider_name,
                                 raw_response={"history": final.history}, finish_reason=final.finish_reason,
                                 duration_ms=int((time.perf_counter() - start) * 1000),
                                 usage=TokenUsage(**{key: value + final.usage.model_dump()[key] for key, value in first.usage.model_dump().items()}))
            call.result = result
            return result
