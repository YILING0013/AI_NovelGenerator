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

    alias: str = Field(default="", description="Biệt danh nhà cung cấp hiện tại")
    provider: LLMProviderConfig = Field(description="Cấu hình nhà cung cấp trong biểu mẫu hiện tại")
    use_stored_api_key: bool = Field(
        default=False,
        description="Có chỉ dùng API Key đã lưu của biệt danh này trong quá trình kiểm tra phía server hay không",
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
                raise ValueError("Khi dùng API Key đã lưu, bắt buộc phải cung cấp biệt danh nhà cung cấp")
            if api_key:
                raise ValueError("Khi dùng API Key đã lưu, không được đồng thời gửi API Key tạm dạng plaintext")
        elif re.fullmatch(r"^(?:\*{3,}|•{3,}|已配置|configured)$", api_key, re.IGNORECASE):
            raise ValueError("Không được dùng placeholder đã che để kiểm tra nhà cung cấp")
        return self


class ProviderCapabilityResult(BaseModel):
    """单项能力测试结果。"""

    capability: ProviderTestCapability = Field(description="Mã định danh khả năng")
    label: str = Field(description="Tên hiển thị trên giao diện")
    status: ProviderTestStatus = Field(description="Trạng thái kiểm tra")
    duration_ms: int = Field(default=0, description="Thời gian kiểm tra, đơn vị mili giây")
    message: str = Field(default="", description="Tóm tắt kết quả hoặc nguyên nhân lỗi")
    details: ProviderProbeDetails | None = None
    _determined: bool = PrivateAttr(default=True)


class ProviderCapabilityRecommendation(BaseModel):
    """接口测试完成后建议回填的 Provider 能力开关。"""

    supports_streaming: bool = Field(default=False, description="Có đề xuất bật streaming")
    supports_json_schema: bool = Field(default=False, description="Có đề xuất bật JSON Schema")
    supports_function_calling: bool = Field(default=False, description="Có đề xuất bật Function Calling")
    supports_json_output: bool = Field(default=False, description="Có đề xuất bật JSON Output")


class ProviderTestResponse(BaseModel):
    """Provider 接口测试响应体。"""

    alias: str = Field(default="", description="Biệt danh nhà cung cấp hiện tại")
    provider_type: str = Field(default="", description="Loại client nhà cung cấp")
    model: str = Field(default="", description="Mô hình kiểm tra")
    summary: str = Field(default="", description="Tổng kết kiểm tra")
    api_mode: str = ""
    output_budget: int = 4096
    results: list[ProviderCapabilityResult] = Field(default_factory=list, description="Kết quả kiểm tra từng hạng mục")
    recommendations: ProviderCapabilityRecommendation = Field(
        default_factory=ProviderCapabilityRecommendation,
        description="Các công tắc khả năng được đề xuất cập nhật",
    )


class ProviderJsonProbeSchema(BaseModel):
    """JSON Schema 探测期望模型返回的最小结构。"""

    code: Literal["ok"] = Field(description="Luôn trả về ok")
    message: str = Field(description="Văn bản trạng thái ngắn gọn")


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
    success_message: str = "Kiểm tra đạt",
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
        logger.info("[Bắt đầu kiểm tra nhà cung cấp] provider=%s capability=%s", provider_alias, capability)
        details = ProviderProbeDetails()
        token = active_provider_probe.set(details)
        try:
            await runner()
        except Exception as exc:
            log_exception(logger, f"[Kiểm tra nhà cung cấp thất bại] provider={provider_alias} capability={capability}", exc)
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
                message=_build_failure_message(exc, api_key) + ("; lần này không xác định được khả năng, giữ nguyên công tắc cũ" if uncertain else ""),
            )
            result._determined = not uncertain
        else:
            logger.info("[Hoàn tất kiểm tra nhà cung cấp] provider=%s capability=%s duration=%dms", provider_alias, capability, int((time.perf_counter() - start) * 1000))
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
        log_exception(logger, f"[Khởi tạo nhà cung cấp thất bại] provider={alias}", exc)
        connection = _result(
            "connection",
            "Tính sẵn sàng của API",
            "failed",
            message=_build_failure_message(exc, api_key),
        )
        skipped = [
            _result("streaming", "Streaming", "skipped", message="Kiểm tra kết nối không đạt"),
            _result("json_schema", json_label, "skipped", message="Kiểm tra kết nối không đạt"),
            _result("function_calling", "Function Calling", "skipped", message="Kiểm tra kết nối không đạt"),
        ]
        return ProviderTestResponse(
            alias=alias,
            provider_type=provider.type,
            model=provider.default_model,
            summary="Kiểm tra kết nối thất bại, đã bỏ qua dò khả năng và giữ nguyên công tắc cũ",
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
            logger.error("[Xác thực phản hồi văn bản của nhà cung cấp thất bại] response=\n%s", format_payload(response.raw_response if response.raw_response is not None else response.content))
            raise ValueError("Nội dung API văn bản trả về không chứa marker theo quy ước")

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
            logger.error("[Xác thực streaming của nhà cung cấp thất bại] content=\n%s", full_text)
            raise ValueError("Nội dung API streaming trả về không chứa marker theo quy ước")

    initial_stream_result = await _run_step(
        "connection",
        "Tính sẵn sàng của API",
        alias,
        api_key,
        run_streaming,
        success_message="API streaming khả dụng, đã hoàn tất kiểm tra streaming đồng bộ",
    )

    results: list[ProviderCapabilityResult] = [initial_stream_result]
    if initial_stream_result.status == "passed":
        results.append(
            _result(
                "streaming",
                "Streaming",
                "passed",
                duration_ms=initial_stream_result.duration_ms,
                message="API streaming khả dụng",
            )
        )
        results[-1].details = initial_stream_result.details
    else:
        connection_result = await _run_step("connection", "Tính sẵn sàng của API", alias, api_key, run_connection)
        results[0] = connection_result

        if connection_result.status != "passed":
            results.extend(
                [
                    _result(
                        "streaming",
                        "Streaming",
                        "skipped",
                        message=f"Kiểm tra kết nối không đạt; lỗi streaming lần đầu: {initial_stream_result.message}",
                    ),
                    _result("json_schema", json_label, "skipped", message="Kiểm tra kết nối không đạt"),
                    _result("function_calling", "Function Calling", "skipped", message="Kiểm tra kết nối không đạt"),
                ]
            )
            return ProviderTestResponse(
                alias=alias,
                provider_type=provider.type,
                model=provider.default_model,
                summary="Kiểm tra kết nối thất bại, đã bỏ qua dò khả năng và giữ nguyên công tắc cũ",
                recommendations=recommendation, api_mode=api_mode, output_budget=output_budget,
                results=results,
            )

        # 普通接口可用时再复测流式能力，避免把必须 stream=true 的模型误判为不可用。
        results.append(await _run_step("streaming", "Streaming", alias, api_key, run_streaming))

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
                raise ValueError("Các trường phản hồi có cấu trúc không đúng như dự kiến")
        except ValueError as exc:
            log_parse_error(exc, content=response.content, schema=ProviderJsonProbeSchema, message="Xác thực bài kiểm tra có cấu trúc của nhà cung cấp thất bại")
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
        success_message="JSON Schema gốc và xác thực trường cục bộ đều đạt" if provider.uses_native_schema else "Đã xác thực output và trường cục bộ thành công; API hiện tại không dùng JSON Schema gốc",
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
        summary=f"{passed_count}/{len(results)} hạng mục kiểm tra đạt, đã quyết định cập nhật công tắc cho từng hạng mục, các hạng mục còn lại giữ nguyên giá trị",
        api_mode=api_mode, output_budget=output_budget,
        results=results,
        recommendations=recommendation,
    )
