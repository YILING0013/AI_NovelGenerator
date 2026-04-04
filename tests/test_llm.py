"""LLM 的 pytest 集成测试。默认使用环境变量中的 OpenAI 兼容接口配置。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from application.llm.config import LLMProviderConfig
from application.llm.models import LLMRequest
from application.llm.openai_client import OpenAICompatibleClient
from application.services.llm.llm_service import LLMService
from pydantic_definitions.novel_pydantic import ExtractIdeaSchema, NovelMetaSchema


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def openai_provider_config() -> LLMProviderConfig:
    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

    if not base_url or not api_key:
        pytest.skip("未设置 OPENAI_BASE_URL / OPENAI_API_KEY，跳过 LLM 集成测试")

    return LLMProviderConfig(
        type="openai",
        base_url=base_url,
        api_key=api_key,
        default_model=model,
        enabled=True,
        timeout_seconds=120,
        max_retries=2,
        supports_streaming=True,
        supports_json_schema=True,
        supports_function_calling=True,
    )


@pytest.fixture
def openai_client(openai_provider_config: LLMProviderConfig) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(openai_provider_config, provider_name="pytest_openai")


@pytest.fixture
def llm_service(monkeypatch: pytest.MonkeyPatch, openai_provider_config: LLMProviderConfig) -> LLMService:
    from application.llm import factory

    def _fake_get_provider_config(provider_name: str | None = None) -> LLMProviderConfig:
        return openai_provider_config

    monkeypatch.setattr(factory, "get_provider_config", _fake_get_provider_config)
    return LLMService(provider_name="pytest_openai")


def test_openai_text_generate(openai_client: OpenAICompatibleClient):
    request = LLMRequest(
        messages=[{"role": "user", "content": "用一句话介绍什么是玄幻小说。"}],
        temperature=0.7,
        max_tokens=200,
    )

    response = _run(openai_client.text_generate(request))

    assert response.success is True
    assert response.content
    assert response.model


def test_openai_schema_extract_idea(openai_client: OpenAICompatibleClient):
    request = LLMRequest(
        system_prompt="你是资深中文网络小说策划编辑。请根据用户给出的创意提取故事构思要素。",
        messages=[
            {
                "role": "user",
                "content": (
                    "我想写一个关于废材少年意外获得上古传承，"
                    "在修仙世界中一路逆袭、登临绝顶的故事。"
                    "整体风格偏热血燃向，面向男频读者。"
                ),
            }
        ],
        temperature=0.7,
        max_tokens=500,
    )

    response = _run(openai_client.schema_generate(request, ExtractIdeaSchema))
    parsed = ExtractIdeaSchema.model_validate_json(response.content)

    assert response.success is True
    assert parsed.genre
    assert parsed.tone
    assert parsed.core_idea


def test_openai_schema_novel_meta(openai_client: OpenAICompatibleClient):
    request = LLMRequest(
        system_prompt="你是资深中文网络小说策划编辑。",
        messages=[
            {
                "role": "user",
                "content": (
                    "请生成一部东方玄幻小说的基础信息。"
                    "主题是成长与权力，故事核心是一个被家族放逐的少年，"
                    "凭借坚韧意志与神秘血脉觉醒，在各大势力的夹缝中崛起，"
                    "最终站上大陆巅峰。"
                ),
            }
        ],
        temperature=0.7,
        max_tokens=1000,
    )

    response = _run(openai_client.schema_generate(request, NovelMetaSchema))
    parsed = NovelMetaSchema.model_validate_json(response.content)

    assert response.success is True
    assert parsed.title
    assert parsed.summary
    assert parsed.worldview
    assert parsed.narrative_pov in {"第一人称", "第三人称有限视角", "全知视角"}


def test_openai_stream_text(openai_client: OpenAICompatibleClient):
    request = LLMRequest(
        messages=[{"role": "user", "content": "用三句话写一段玄幻小说的开场白。"}],
        temperature=0.8,
        max_tokens=300,
    )

    async def _collect() -> str:
        chunks: list[str] = []
        async for chunk in openai_client.stream_text(request):
            chunks.append(chunk)
        return "".join(chunks)

    full_text = _run(_collect())

    assert full_text
    assert len(full_text) > 20


def test_llm_service_openai(llm_service: LLMService):
    text = _run(
        llm_service.generate_text(
            prompt="用一句话形容修仙世界的壮丽。",
            system_prompt="你是一位文笔优美的小说作者。",
            temperature=0.7,
            max_tokens=200,
        )
    )
    idea = _run(
        llm_service.generate_structured(
            prompt="我想写一个末世废土风格的科幻小说，主角在废墟中寻找失落文明的秘密。",
            schema=ExtractIdeaSchema,
            system_prompt="你是资深中文网络小说策划编辑。请提取故事构思要素。",
            temperature=0.7,
            max_tokens=500,
        )
    )

    assert text
    assert isinstance(idea, ExtractIdeaSchema)
    assert idea.plot


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
