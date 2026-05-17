"""LLM Provider 接口能力测试服务。"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field

from backend.llm.base_client import BaseLLMClient
from backend.llm.config import LLMProviderConfig
from backend.llm.factory import create_llm_client_from_config
from backend.llm.logger import log_provider_test_raw_response
from backend.llm.models import LLMFunctionCallProbe, LLMRequest
from backend.llm.prompts.prompt_selector import load_llm_provider_test_prompts

ProviderTestCapability = Literal["connection", "streaming", "json_schema", "function_calling"]
ProviderTestStatus = Literal["passed", "failed", "skipped"]
ClientFactory = Callable[[LLMProviderConfig, str], BaseLLMClient]

PROBE_TOKEN = "probe-token-73"
FUNCTION_TOOL_NAME = "report_provider_probe"
FUNCTION_EXPECTED_TEXT = f"PROVIDER_FUNCTION_OK {PROBE_TOKEN}"
SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{12,})")


class ProviderTestRequest(BaseModel):
    """前端发起 Provider 接口测试的请求体。"""

    alias: str = Field(default="", description="当前 Provider 别名")
    provider: LLMProviderConfig = Field(description="当前表单中的 Provider 配置")


class ProviderCapabilityResult(BaseModel):
    """单项能力测试结果。"""

    capability: ProviderTestCapability = Field(description="能力标识")
    label: str = Field(description="前端展示名称")
    status: ProviderTestStatus = Field(description="测试状态")
    duration_ms: int = Field(default=0, description="测试耗时，单位毫秒")
    message: str = Field(default="", description="结果摘要或错误原因")


class ProviderCapabilityRecommendation(BaseModel):
    """接口测试完成后建议回填的 Provider 能力开关。"""

    supports_streaming: bool = Field(default=False, description="是否建议启用流式输出")
    supports_json_schema: bool = Field(default=False, description="是否建议启用 JSON Schema")
    supports_function_calling: bool = Field(default=False, description="是否建议启用 Function Calling")


class ProviderTestResponse(BaseModel):
    """Provider 接口测试响应体。"""

    alias: str = Field(default="", description="当前 Provider 别名")
    provider_type: str = Field(default="", description="Provider 客户端类别")
    model: str = Field(default="", description="测试模型")
    summary: str = Field(default="", description="测试总结")
    results: list[ProviderCapabilityResult] = Field(default_factory=list, description="逐项测试结果")
    recommendations: ProviderCapabilityRecommendation = Field(
        default_factory=ProviderCapabilityRecommendation,
        description="建议回填的能力开关",
    )


class ProviderJsonProbeSchema(BaseModel):
    """JSON Schema 探测期望模型返回的最小结构。"""

    code: Literal["ok"] = Field(description="固定返回 ok")
    message: str = Field(description="简短状态文本")


def _default_client_factory(config: LLMProviderConfig, alias: str) -> BaseLLMClient:
    """创建用于接口测试的临时 LLM 客户端。

    Args:
        config: 当前表单提交的 Provider 配置。
        alias: 当前 Provider 别名。

    Returns:
        对应类型的 LLM 客户端实例。
    """
    return create_llm_client_from_config(config, provider_name=alias, require_enabled=False)


def _build_probe_request(prompt: str) -> LLMRequest:
    """构造低成本的接口测试请求。

    Args:
        prompt: 当前测试步骤使用的极简提示词。

    Returns:
        可直接传入底层客户端的 LLM 请求。
    """
    return LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=64,
    )


def _redact_sensitive_text(text: str, api_key: str = "") -> str:
    """清理错误文本中的敏感凭据。

    Args:
        text: 原始错误文本。
        api_key: 当前表单中的 API Key。

    Returns:
        已脱敏的错误文本。
    """
    if not text:
        return ""

    redacted = text
    if api_key:
        redacted = redacted.replace(api_key, "***")
    return SECRET_PATTERN.sub("***", redacted)


def _build_failure_message(exc: Exception, api_key: str) -> str:
    """生成单项测试失败摘要。

    Args:
        exc: 捕获到的异常。
        api_key: 当前表单中的 API Key，用于脱敏。

    Returns:
        适合返回前端展示的失败摘要。
    """
    message = str(exc) or type(exc).__name__
    return _redact_sensitive_text(message, api_key)


def _result(
    capability: ProviderTestCapability,
    label: str,
    status: ProviderTestStatus,
    *,
    duration_ms: int = 0,
    message: str = "",
) -> ProviderCapabilityResult:
    """创建统一格式的单项测试结果。

    Args:
        capability: 能力标识。
        label: 前端展示名称。
        status: 测试状态。
        duration_ms: 测试耗时，单位毫秒。
        message: 结果摘要或错误原因。

    Returns:
        单项测试结果模型。
    """
    return ProviderCapabilityResult(
        capability=capability,
        label=label,
        status=status,
        duration_ms=duration_ms,
        message=message,
    )


async def _run_step(
    capability: ProviderTestCapability,
    label: str,
    api_key: str,
    runner: Callable[[], Awaitable[None]],
    *,
    success_message: str = "测试通过",
) -> ProviderCapabilityResult:
    """执行单个 Provider 能力测试步骤。

    Args:
        capability: 能力标识。
        label: 前端展示名称。
        api_key: 当前表单中的 API Key，用于错误脱敏。
        runner: 实际执行测试的异步回调。
        success_message: 测试通过时展示给前端的结果摘要。

    Returns:
        单项测试结果。
    """
    start = time.perf_counter()
    try:
        await runner()
    except Exception as exc:
        return _result(
            capability,
            label,
            "failed",
            duration_ms=int((time.perf_counter() - start) * 1000),
            message=_build_failure_message(exc, api_key),
        )

    return _result(
        capability,
        label,
        "passed",
        duration_ms=int((time.perf_counter() - start) * 1000),
        message=success_message,
    )


def _build_function_probe(prompts: dict[str, str]) -> LLMFunctionCallProbe:
    """构造 Function Calling 完整两轮探测参数。

    Args:
        prompts: 已加载的 Provider 测试提示词。

    Returns:
        Function Calling 探测参数。
    """
    tool_result = {
        "token": PROBE_TOKEN,
        "status": "ok",
        "message": "provider probe ready",
    }
    return LLMFunctionCallProbe(
        tool_name=FUNCTION_TOOL_NAME,
        tool_description="Report that the provider function calling probe is available.",
        parameters_schema={
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "description": "The fixed probe token.",
                },
                "status": {
                    "type": "string",
                    "enum": ["ok"],
                    "description": "Probe status.",
                },
            },
            "required": ["token", "status"],
            "additionalProperties": False,
        },
        expected_arguments={"token": PROBE_TOKEN, "status": "ok"},
        tool_result=tool_result,
        final_response_prompt=prompts["function_result_probe_prompt"].format(
            tool_result=json.dumps(tool_result, ensure_ascii=False),
            probe_token=PROBE_TOKEN,
        ),
        expected_final_text=FUNCTION_EXPECTED_TEXT,
    )


async def test_llm_provider_capabilities(
    request: ProviderTestRequest,
    *,
    client_factory: ClientFactory = _default_client_factory,
) -> ProviderTestResponse:
    """按顺序测试 LLM Provider 接口与三项能力。

    Args:
        request: 前端提交的 Provider 测试请求。
        client_factory: 客户端工厂，测试中可注入 fake client。

    Returns:
        包含逐项结果和能力开关建议值的测试响应。
    """
    prompts = load_llm_provider_test_prompts()
    alias = request.alias.strip() or "unsaved_provider"
    provider = request.provider
    api_key = provider.api_key
    try:
        client = client_factory(provider, alias)
    except Exception as exc:
        connection = _result(
            "connection",
            "接口可用性",
            "failed",
            message=_build_failure_message(exc, api_key),
        )
        skipped = [
            _result("streaming", "流式输出", "skipped", message="连接测试未通过"),
            _result("json_schema", "JSON Schema", "skipped", message="连接测试未通过"),
            _result("function_calling", "Function Calling", "skipped", message="连接测试未通过"),
        ]
        return ProviderTestResponse(
            alias=alias,
            provider_type=provider.type,
            model=provider.default_model,
            summary="连接测试失败，已跳过能力探测",
            results=[connection, *skipped],
        )

    async def run_connection() -> None:
        """执行普通文本接口可用性测试。

        Args:
            无。

        Returns:
            无。
        """
        response = await client.text_generate(_build_probe_request(prompts["text_probe_prompt"]))
        log_provider_test_raw_response(
            alias,
            "connection",
            response.raw_response or {"content": response.content},
        )
        if "PROVIDER_TEXT_OK" not in response.content:
            raise ValueError("文本接口返回内容未包含约定标记")

    async def run_streaming(log_capability: ProviderTestCapability = "streaming") -> None:
        """执行流式输出能力测试。

        Args:
            log_capability: 原始响应日志中标记的测试步骤。

        Returns:
            无。
        """
        chunks: list[str] = []
        stream_request = _build_probe_request(prompts["stream_probe_prompt"]).model_copy(update={"stream": True})
        async for chunk in client.stream_text(stream_request):
            chunks.append(chunk)
        full_text = "".join(chunks)
        log_provider_test_raw_response(
            alias,
            log_capability,
            {"chunks": chunks, "content": full_text},
        )
        if not chunks or "PROVIDER_STREAM_OK" not in full_text:
            raise ValueError("流式接口返回内容未包含约定标记")

    initial_stream_result = await _run_step(
        "connection",
        "接口可用性",
        api_key,
        lambda: run_streaming("connection"),
        success_message="流式接口可用，已同步完成流式检查",
    )

    results: list[ProviderCapabilityResult] = [initial_stream_result]
    if initial_stream_result.status == "passed":
        results.append(
            _result(
                "streaming",
                "流式输出",
                "passed",
                duration_ms=initial_stream_result.duration_ms,
                message="流式接口可用",
            )
        )
    else:
        connection_result = await _run_step("connection", "接口可用性", api_key, run_connection)
        results[0] = connection_result

        if connection_result.status != "passed":
            results.extend(
                [
                    _result(
                        "streaming",
                        "流式输出",
                        "skipped",
                        message=f"连接测试未通过；初次流式失败: {initial_stream_result.message}",
                    ),
                    _result("json_schema", "JSON Schema", "skipped", message="连接测试未通过"),
                    _result("function_calling", "Function Calling", "skipped", message="连接测试未通过"),
                ]
            )
            return ProviderTestResponse(
                alias=alias,
                provider_type=provider.type,
                model=provider.default_model,
                summary="连接测试失败，已跳过能力探测",
                results=results,
            )

        # 普通接口可用时再复测流式能力，避免把必须 stream=true 的模型误判为不可用。
        results.append(await _run_step("streaming", "流式输出", api_key, run_streaming))

    async def run_json_schema() -> None:
        """执行 JSON Schema 结构化输出能力测试。

        Args:
            无。

        Returns:
            无。
        """
        response = await client.schema_generate(
            _build_probe_request(prompts["json_schema_probe_prompt"]),
            ProviderJsonProbeSchema,
        )
        log_provider_test_raw_response(
            alias,
            "json_schema",
            response.raw_response or {"content": response.content},
        )
        parsed = ProviderJsonProbeSchema.model_validate_json(response.content)
        if parsed.code != "ok":
            raise ValueError("结构化响应字段不符合预期")

    async def run_function_calling() -> None:
        """执行 Function Calling 完整两轮能力测试。

        Args:
            无。

        Returns:
            无。
        """
        response = await client.function_call_probe(
            _build_probe_request(prompts["function_call_probe_prompt"]),
            _build_function_probe(prompts),
        )
        log_provider_test_raw_response(
            alias,
            "function_calling",
            response.raw_response or {"content": response.content},
        )

    results.append(await _run_step("json_schema", "JSON Schema", api_key, run_json_schema))
    results.append(await _run_step("function_calling", "Function Calling", api_key, run_function_calling))

    recommendation = ProviderCapabilityRecommendation(
        supports_streaming=results[1].status == "passed",
        supports_json_schema=results[2].status == "passed",
        supports_function_calling=results[3].status == "passed",
    )
    passed_count = sum(1 for item in results if item.status == "passed")
    return ProviderTestResponse(
        alias=alias,
        provider_type=provider.type,
        model=provider.default_model,
        summary=f"{passed_count}/{len(results)} 项测试通过，能力开关已生成建议值",
        results=results,
        recommendations=recommendation,
    )
