from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from backend.api.llm_routers import create_novel_router
from backend.llm.config import LLMConfig, LLMProviderConfig


def _run(coro):
    """运行异步测试协程。

    Args:
        coro: 待执行的异步协程。

    Returns:
        协程执行结果。
    """
    return asyncio.run(coro)


def _enabled_provider(*, supports_json_schema: bool = True) -> LLMProviderConfig:
    """构造可用于字段改写测试的启用 Provider。

    Args:
        supports_json_schema: Provider 是否声明支持 JSON Schema。

    Returns:
        启用状态的 Provider 配置。
    """
    return LLMProviderConfig(
        type="openai",
        base_url="https://example.com/v1",
        api_key="test-key",
        default_model="test-model",
        enabled=True,
        supports_json_schema=supports_json_schema,
    )


def test_normalize_rewrite_value_handles_text_and_list() -> None:
    assert create_novel_router._normalize_rewrite_value("summary", ["第一段", "第二段"]) == "第一段\n第二段"
    assert create_novel_router._normalize_rewrite_value("title", "  新标题  ") == "新标题"


def test_normalize_rewrite_value_handles_tags() -> None:
    assert create_novel_router._normalize_rewrite_value("tags", "科幻、冒险,成长") == [
        "科幻",
        "冒险",
        "成长",
    ]


def test_normalize_rewrite_value_rejects_invalid_narrative_pov() -> None:
    with pytest.raises(ValueError, match="叙事视角只能为"):
        create_novel_router._normalize_rewrite_value("narrative_pov", "第二人称")


def test_normalize_rewrite_result_rejects_field_mismatch() -> None:
    result = create_novel_router.NovelFieldRewriteResult(target_field="title", value="新标题")

    with pytest.raises(ValueError, match="AI 返回字段不一致"):
        create_novel_router._normalize_rewrite_result("summary", result)


def test_validate_rewrite_provider_rejects_missing_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        create_novel_router,
        "get_llm_config",
        lambda: LLMConfig(default_provider="missing", providers={}),
    )

    with pytest.raises(HTTPException) as exc:
        create_novel_router._validate_rewrite_provider("missing")

    assert exc.value.status_code == 400
    assert "Provider 不存在" in exc.value.detail


def test_validate_rewrite_provider_rejects_disabled_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    disabled_provider = _enabled_provider().model_copy(update={"enabled": False})
    llm_config = LLMConfig(default_provider="disabled", providers={"disabled": disabled_provider})

    monkeypatch.setattr(create_novel_router, "get_llm_config", lambda: llm_config)
    monkeypatch.setattr(create_novel_router, "get_provider_config", lambda provider: disabled_provider)

    with pytest.raises(HTTPException) as exc:
        create_novel_router._validate_rewrite_provider("disabled")

    assert exc.value.status_code == 400
    assert "Provider 未启用" in exc.value.detail


def test_build_rewrite_prompt_contains_request_context_and_history() -> None:
    req = create_novel_router.NovelFieldRewriteRequest(
        provider="test_provider",
        target_field="plot",
        instruction="让主线更悬疑",
        current_value="主角在废土寻找真相。",
        context={
            "title": "废土回声",
            "plot": "主角在废土寻找真相。",
            "number_of_chapters": 120,
            "_rewriteState": {"ignored": True},
        },
        chat_history=[
            create_novel_router.NovelRewriteChatMessage(role="user", content="保留废土设定"),
            create_novel_router.NovelRewriteChatMessage(role="assistant", content="已保留废土设定"),
        ],
    )

    prompt = create_novel_router._build_rewrite_prompt(req, use_json_schema=True)

    assert "主线剧情 (plot)" in prompt
    assert "让主线更悬疑" in prompt
    assert "主角在废土寻找真相。" in prompt
    assert "废土回声" in prompt
    assert "保留废土设定" in prompt
    assert '"plot"' not in prompt
    assert "_rewriteState" not in prompt


def test_rewrite_novel_field_uses_selected_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_config = _enabled_provider()
    llm_config = LLMConfig(default_provider="rewrite_provider", providers={"rewrite_provider": provider_config})
    captured: dict[str, object] = {}

    class FakeLLMService:
        """记录字段改写调用参数的假 LLMService。"""

        def __init__(self, provider_name: str | None = None) -> None:
            captured["provider_name"] = provider_name

        async def generate_structured(self, prompt: str, schema):
            captured["prompt"] = prompt
            captured["schema"] = schema
            return create_novel_router.NovelFieldRewriteResult(
                target_field="summary",
                value="改写后的简介",
            )

    monkeypatch.setattr(create_novel_router, "get_llm_config", lambda: llm_config)
    monkeypatch.setattr(create_novel_router, "get_provider_config", lambda provider: provider_config)
    monkeypatch.setattr(create_novel_router, "LLMService", FakeLLMService)

    req = create_novel_router.NovelFieldRewriteRequest(
        provider="rewrite_provider",
        target_field="summary",
        instruction="更有悬念",
        current_value="旧简介",
        context={"title": "测试小说", "summary": "旧简介"},
    )

    response = _run(create_novel_router.rewrite_novel_field(req))

    assert response == {"target_field": "summary", "value": "改写后的简介"}
    assert captured["provider_name"] == "rewrite_provider"
    assert captured["schema"] is create_novel_router.NovelFieldRewriteResult
    assert "更有悬念" in str(captured["prompt"])
