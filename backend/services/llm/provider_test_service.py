"""LLM Provider 接口能力测试服务。"""

from __future__ import annotations

import json
import logging
from contextlib import aclosing
import re
import time
from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from backend.llm.base_client import BaseLLMClient
from backend.llm.config import LLMProviderConfig
from backend.llm.factory import create_llm_client_from_config
from backend.llm.exceptions import LLMAuthError, LLMError, LLMRateLimitError, LLMResponseError, LLMTimeoutError
from backend.llm.provider_probe import ProviderProbeDetails, active_provider_probe
from backend.llm.logger import format_payload, log_parse_error
from backend.runtime import bind_log_context, log_exception
from backend.llm.models import LLMFunctionCallProbe, LLMRequest
from backend.llm.prompts.prompt_selector import load_llm_provider_test_prompts

logger = logging.getLogger(__name__)

ProviderTestCapability = Literal["connection", "streaming", "json_schema", "function_calling"]
ProviderTestStatus = Literal["passed", "failed", "skipped"]
ClientFactory = Callable[[LLMProviderConfig, str], BaseLLMClient]

PROBE_TOKEN = "probe-token-73"
FUNCTION_TOOL_NAME = "report_provider_probe"
FUNCTION_EXPECTED_TEXT = f"PROVIDER_FUNCTION_OK {PROBE_TOKEN}"
SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{12,})")


class ProviderTestRequest(BaseModel):
    """前端发起 Provider 接口测试的请求体。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    alias: str = Field(default="", description="当前 Provider 别名")
    provider: LLMProviderConfig = Field(description="当前表单中的 Provider 配置")
    use_stored_api_key: bool = Field(
        default=False,
        description="是否只在服务端测试期间使用该别名已保存的 API Key",
    )

    @model_validator(mode="after")
    def validate_secret_source(self) -> "ProviderTestRequest":
        """校验一次性明文与已保存密钥选择互斥。

        Args:
            无。

        Returns:
            密钥来源明确且不会把掩码发送到 Provider 的请求。
        """
        api_key = self.provider.api_key.strip()
        if self.use_stored_api_key:
            if not self.alias.strip():
                raise ValueError("使用已保存 API Key 时必须提供 Provider 别名")
            if api_key:
                raise ValueError("使用已保存 API Key 时不能同时提交一次性明文")
        elif re.fullmatch(r"^(?:\*{3,}|•{3,}|已配置|configured)$", api_key, re.IGNORECASE):
            raise ValueError("不能使用掩码占位符测试 Provider")
        return self


class ProviderCapabilityResult(BaseModel):
    """单项能力测试结果。"""

    capability: ProviderTestCapability = Field(description="能力标识")
    label: str = Field(description="前端展示名称")
    status: ProviderTestStatus = Field(description="测试状态")
    duration_ms: int = Field(default=0, description="测试耗时，单位毫秒")
    message: str = Field(default="", description="结果摘要或错误原因")
    details: ProviderProbeDetails | None = None
    _determined: bool = PrivateAttr(default=True)


class ProviderCapabilityRecommendation(BaseModel):
    """接口测试完成后建议回填的 Provider 能力开关。"""

    supports_streaming: bool = Field(default=False, description="是否建议启用流式输出")
    supports_json_schema: bool = Field(default=False, description="是否建议启用 JSON Schema")
    supports_function_calling: bool = Field(default=False, description="是否建议启用 Function Calling")
    supports_json_output: bool = Field(default=False, description="是否建议启用 JSON Output")


class ProviderTestResponse(BaseModel):
    """Provider 接口测试响应体。"""

    alias: str = Field(default="", description="当前 Provider 别名")
    provider_type: str = Field(default="", description="Provider 客户端类别")
    model: str = Field(default="", description="测试模型")
    summary: str = Field(default="", description="测试总结")
    api_mode: str = ""
    output_budget: int = 4096
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


def _build_probe_request(prompt: str, output_budget: int = 4096, *, stream: bool = False) -> LLMRequest:
    """构造低成本的接口测试请求。

    Args:
        prompt: 当前测试步骤使用的极简提示词。
        output_budget: 表单中的输出预算，未填时为 4096。
        stream: 沿用连接测试已验证的请求方式。

    Returns:
        可直接传入底层客户端的 LLM 请求。
    """
    return LLMRequest(
        messages=[{"role": "user", "content": prompt}],
        # 推理模型也会消耗输出额度；采样参数沿用实际服务配置。
        max_tokens=output_budget,
        stream=stream,
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
    provider_alias: str,
    api_key: str,
    runner: Callable[[], Awaitable[None]],
    *,
    success_message: str = "测试通过",
) -> ProviderCapabilityResult:
    """执行单个 Provider 能力测试步骤。

    Args:
        capability: 能力标识。
        label: 前端展示名称。
        provider_alias: 当前 Provider 别名，用于调试日志定位。
        api_key: 当前表单中的 API Key，用于错误脱敏。
        runner: 实际执行测试的异步回调。
        success_message: 测试通过时展示给前端的结果摘要。

    Returns:
        单项测试结果。
    """
    with bind_log_context(provider_test=capability):
        start = time.perf_counter()
        logger.info("[Provider 测试开始] provider=%s capability=%s", provider_alias, capability)
        details = ProviderProbeDetails()
        token = active_provider_probe.set(details)
        try:
            await runner()
        except Exception as exc:
            log_exception(logger, f"[Provider 测试失败] provider={provider_alias} capability={capability}", exc)
            # 无法完成请求时保留输入开关；正常响应的内容校验失败仍按实际结果关闭。
            uncertain = (
                isinstance(exc, (LLMAuthError, LLMRateLimitError, LLMTimeoutError, TimeoutError, ConnectionError))
                or type(exc) is LLMError
                or details._http_status in {401, 403, 408, 409, 429}
                or (details._http_status is not None and details._http_status >= 500)
                or (details._send_count > 0 and details._http_status is None)
                or details._incomplete
                or (isinstance(exc, LLMResponseError) and "提前断开" in str(exc))
            )
            result = _result(
                capability, label, "failed",
                duration_ms=int((time.perf_counter() - start) * 1000),
                message=_build_failure_message(exc, api_key) + ("；本次无法判断能力，保留原开关" if uncertain else ""),
            )
            result._determined = not uncertain
        else:
            logger.info("[Provider 测试完成] provider=%s capability=%s duration=%dms", provider_alias, capability, int((time.perf_counter() - start) * 1000))
            result = _result(capability, label, "passed", duration_ms=int((time.perf_counter() - start) * 1000), message=success_message)
        finally:
            active_provider_probe.reset(token)
        result.details = details
        return result


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
    output_budget = provider.max_tokens or 4096
    api_mode = ""
    recommendation = ProviderCapabilityRecommendation(
        supports_streaming=provider.supports_streaming,
        supports_json_schema=provider.supports_json_schema,
        supports_json_output=bool(provider.supports_json_output),
        supports_function_calling=provider.supports_function_calling,
    )
    json_label = "JSON Schema"
    try:
        recommendation.supports_json_output = provider.json_output_enabled
        json_label = "JSON Schema" if provider.uses_native_schema else "JSON Output" if provider.resolved_structured_output_mode == "json_object" else "Tool Output"
        api_mode = provider.resolved_api_mode
        client = client_factory(provider, alias)
    except Exception as exc:
        log_exception(logger, f"[Provider 初始化失败] provider={alias}", exc)
        connection = _result(
            "connection",
            "接口可用性",
            "failed",
            message=_build_failure_message(exc, api_key),
        )
        skipped = [
            _result("streaming", "流式输出", "skipped", message="连接测试未通过"),
            _result("json_schema", json_label, "skipped", message="连接测试未通过"),
            _result("function_calling", "Function Calling", "skipped", message="连接测试未通过"),
        ]
        return ProviderTestResponse(
            alias=alias,
            provider_type=provider.type,
            model=provider.default_model,
            summary="连接测试失败，已跳过能力探测并保留原开关",
            recommendations=recommendation, api_mode=api_mode, output_budget=output_budget,
            results=[connection, *skipped],
        )

    async def run_connection() -> None:
        """执行普通文本接口可用性测试。

        Args:
            无。

        Returns:
            无。
        """
        response = await client.text_generate(_build_probe_request(prompts["text_probe_prompt"], output_budget))
        if "PROVIDER_TEXT_OK" not in response.content:
            logger.error("[Provider 文本校验失败] response=\n%s", format_payload(response.raw_response if response.raw_response is not None else response.content))
            raise ValueError("文本接口返回内容未包含约定标记")

    async def run_streaming() -> None:
        """执行流式输出能力测试。

        Args:
            无。

        Returns:
            无。
        """
        chunks: list[str] = []
        stream_request = _build_probe_request(prompts["stream_probe_prompt"], output_budget).model_copy(update={"stream": True})
        async with aclosing(client.stream_text(stream_request)) as events:
            async for chunk in events:
                chunks.append(chunk)
        full_text = "".join(chunks)
        if not chunks or "PROVIDER_STREAM_OK" not in full_text:
            logger.error("[Provider 流式校验失败] content=\n%s", full_text)
            raise ValueError("流式接口返回内容未包含约定标记")

    initial_stream_result = await _run_step(
        "connection",
        "接口可用性",
        alias,
        api_key,
        run_streaming,
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
        results[-1].details = initial_stream_result.details
    else:
        connection_result = await _run_step("connection", "接口可用性", alias, api_key, run_connection)
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
                    _result("json_schema", json_label, "skipped", message="连接测试未通过"),
                    _result("function_calling", "Function Calling", "skipped", message="连接测试未通过"),
                ]
            )
            return ProviderTestResponse(
                alias=alias,
                provider_type=provider.type,
                model=provider.default_model,
                summary="连接测试失败，已跳过能力探测并保留原开关",
                recommendations=recommendation, api_mode=api_mode, output_budget=output_budget,
                results=results,
            )

        # 普通接口可用时再复测流式能力，避免把必须 stream=true 的模型误判为不可用。
        results.append(await _run_step("streaming", "流式输出", alias, api_key, run_streaming))

    async def run_json_schema() -> None:
        """测试所选接口的结构化输出，并在本地校验字段。

        Args:
            无。

        Returns:
            无。
        """
        response = await client.schema_generate(
            _build_probe_request(prompts["json_schema_probe_prompt"], output_budget, stream=initial_stream_result.status == "passed"),
            ProviderJsonProbeSchema,
        )
        try:
            parsed = ProviderJsonProbeSchema.model_validate_json(response.content)
            if parsed.code != "ok":
                raise ValueError("结构化响应字段不符合预期")
        except ValueError as exc:
            log_parse_error(exc, content=response.content, schema=ProviderJsonProbeSchema, message="Provider 结构化测试校验失败")
            raise

    async def run_function_calling() -> None:
        """执行 Function Calling 完整两轮能力测试。

        Args:
            无。

        Returns:
            无。
        """
        await client.function_call_probe(
            _build_probe_request(prompts["function_call_probe_prompt"], output_budget, stream=initial_stream_result.status == "passed"),
            _build_function_probe(prompts),
        )

    results.append(await _run_step(
        "json_schema", json_label, alias, api_key, run_json_schema,
        success_message="原生 JSON Schema 与本地字段校验通过" if provider.uses_native_schema else "输出与本地字段校验通过；当前接口未使用原生 JSON Schema",
    ))
    results.append(await _run_step("function_calling", "Function Calling", alias, api_key, run_function_calling))

    for result in results[1:]:
        if result._determined and result.status != "skipped":
            value = result.status == "passed"
            if result.capability == "json_schema" and provider.resolved_structured_output_mode == "json_object":
                recommendation.supports_json_output = value
                continue
            setattr(recommendation, f"supports_{result.capability}", value)
    passed_count = sum(1 for item in results if item.status == "passed")
    return ProviderTestResponse(
        alias=alias,
        provider_type=provider.type,
        model=provider.default_model,
        summary=f"{passed_count}/{len(results)} 项测试通过，已判定项目更新开关，其余保留原值",
        api_mode=api_mode, output_budget=output_budget,
        results=results,
        recommendations=recommendation,
    )
