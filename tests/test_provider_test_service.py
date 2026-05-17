from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator

from pydantic import BaseModel

from backend.llm.base_client import BaseLLMClient
from backend.llm.config import LLMProviderConfig
from backend.llm.models import LLMFunctionCallProbe, LLMRequest, LLMResponse
from backend.services.llm.provider_test_service import (
    ProviderTestRequest,
    test_llm_provider_capabilities as run_llm_provider_capabilities,
)


def _run(coro):
    """运行异步测试协程。

    Args:
        coro: 需要执行的协程对象。

    Returns:
        协程执行结果。
    """
    return asyncio.run(coro)


def _provider_config() -> LLMProviderConfig:
    """构造测试用 Provider 配置。

    Args:
        无。

    Returns:
        可用于 fake client 的 Provider 配置。
    """
    return LLMProviderConfig(
        type="openai",
        base_url="https://example.test/v1",
        api_key="sk-test-secret",
        default_model="test-model",
        enabled=False,
        timeout_seconds=5,
        max_retries=0,
    )


class FakeProviderClient(BaseLLMClient):
    """Provider 能力测试专用 fake client。"""

    def __init__(
        self,
        failures: set[str] | None = None,
        calls: list[str] | None = None,
        stream_failures_before_success: int = 0,
    ) -> None:
        super().__init__(_provider_config(), provider_name="fake")
        self.failures = failures or set()
        self.calls = calls if calls is not None else []
        self.stream_failures_before_success = stream_failures_before_success

    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """模拟普通文本接口。

        Args:
            request: LLM 请求。

        Returns:
            fake 文本响应。
        """
        self.calls.append("text_generate")
        if "connection" in self.failures:
            raise ValueError("auth failed for sk-test-secret")
        return LLMResponse(content="PROVIDER_TEXT_OK")

    async def schema_generate(self, request: LLMRequest, schema: type[BaseModel]) -> LLMResponse:
        """模拟结构化输出接口。

        Args:
            request: LLM 请求。
            schema: 目标 Pydantic Schema。

        Returns:
            fake JSON Schema 响应。
        """
        self.calls.append("schema_generate")
        if "json_schema" in self.failures:
            raise ValueError("schema unsupported")
        return LLMResponse(content='{"code":"ok","message":"ready"}')

    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """模拟流式输出接口。

        Args:
            request: LLM 请求。

        Returns:
            异步文本分块生成器。
        """
        self.calls.append("stream_text")
        if not request.stream:
            raise ValueError("stream flag was false")
        if "connection" in self.failures:
            raise ValueError("auth failed for sk-test-secret")
        if self.stream_failures_before_success > 0:
            self.stream_failures_before_success -= 1
            raise ValueError("temporary stream failure")
        if "streaming" in self.failures:
            raise ValueError("stream unsupported")
        yield "PROVIDER_"
        yield "STREAM_OK"

    async def function_call_probe(
        self,
        request: LLMRequest,
        probe: LLMFunctionCallProbe,
    ) -> LLMResponse:
        """模拟 Function Calling 两轮探测。

        Args:
            request: LLM 请求。
            probe: Function Calling 探测参数。

        Returns:
            fake 二轮最终响应。
        """
        self.calls.append("function_call_probe")
        if "function_calling" in self.failures:
            raise ValueError("final response missed tool result")
        return LLMResponse(content=probe.expected_final_text)


def _factory(
    failures: set[str] | None = None,
    *,
    calls: list[str] | None = None,
    stream_failures_before_success: int = 0,
):
    """构造 fake client factory。

    Args:
        failures: 需要模拟失败的能力集合。
        calls: 记录 fake client 方法调用顺序的列表。
        stream_failures_before_success: 流式接口成功前需要模拟的失败次数。

    Returns:
        可注入服务层的 fake client factory。
    """
    def create_client(_config: LLMProviderConfig, _alias: str) -> BaseLLMClient:
        """返回 fake Provider 客户端。

        Args:
            _config: Provider 配置。
            _alias: Provider 别名。

        Returns:
            fake Provider 客户端。
        """
        return FakeProviderClient(failures, calls, stream_failures_before_success)

    return create_client


def _request() -> ProviderTestRequest:
    """构造 Provider 测试请求。

    Args:
        无。

    Returns:
        Provider 测试请求模型。
    """
    return ProviderTestRequest(alias="pytest_provider", provider=_provider_config())


def test_provider_test_all_passes_and_recommends_all_capabilities() -> None:
    calls: list[str] = []
    response = _run(run_llm_provider_capabilities(_request(), client_factory=_factory(calls=calls)))

    assert [item.status for item in response.results] == ["passed", "passed", "passed", "passed"]
    assert calls == ["stream_text", "schema_generate", "function_call_probe"]
    assert response.recommendations.supports_streaming is True
    assert response.recommendations.supports_json_schema is True
    assert response.recommendations.supports_function_calling is True


def test_provider_test_connection_failure_skips_capabilities_and_redacts_secret() -> None:
    response = _run(
        run_llm_provider_capabilities(
            _request(),
            client_factory=_factory({"connection"}),
        )
    )

    assert response.results[0].status == "failed"
    assert [item.status for item in response.results[1:]] == ["skipped", "skipped", "skipped"]
    assert "sk-test-secret" not in response.results[0].message
    assert "***" in response.results[0].message


def test_provider_test_single_capability_failure_keeps_later_tests() -> None:
    calls: list[str] = []
    response = _run(
        run_llm_provider_capabilities(
            _request(),
            client_factory=_factory({"streaming"}, calls=calls),
        )
    )

    statuses = {item.capability: item.status for item in response.results}
    assert statuses["connection"] == "passed"
    assert statuses["streaming"] == "failed"
    assert statuses["json_schema"] == "passed"
    assert statuses["function_calling"] == "passed"
    assert calls == ["stream_text", "text_generate", "stream_text", "schema_generate", "function_call_probe"]
    assert response.recommendations.supports_streaming is False
    assert response.recommendations.supports_json_schema is True
    assert response.recommendations.supports_function_calling is True


def test_provider_test_retries_streaming_after_text_connection_success() -> None:
    calls: list[str] = []
    response = _run(
        run_llm_provider_capabilities(
            _request(),
            client_factory=_factory(calls=calls, stream_failures_before_success=1),
        )
    )

    statuses = {item.capability: item.status for item in response.results}
    assert statuses["connection"] == "passed"
    assert statuses["streaming"] == "passed"
    assert calls == ["stream_text", "text_generate", "stream_text", "schema_generate", "function_call_probe"]
    assert response.recommendations.supports_streaming is True


def test_provider_test_function_calling_second_round_failure_updates_recommendation() -> None:
    response = _run(
        run_llm_provider_capabilities(
            _request(),
            client_factory=_factory({"function_calling"}),
        )
    )

    statuses = {item.capability: item.status for item in response.results}
    assert statuses["function_calling"] == "failed"
    assert response.recommendations.supports_function_calling is False


def test_provider_test_logs_raw_response_when_backend_debug_enabled(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("NOVEL_GENERATOR_BACKEND_DEBUG", "1")
    caplog.set_level(logging.DEBUG, logger="llm")

    _run(run_llm_provider_capabilities(_request(), client_factory=_factory()))

    assert "[Provider 测试原始响应]" in caplog.text
    assert "PROVIDER_STREAM_OK" in caplog.text
