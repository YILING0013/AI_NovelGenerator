"""LLM 模块集成测试脚本。

直接实例化各平台客户端进行测试，无需启动完整应用。
使用方式: 
在环境变量中设置密钥，方式示例:
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:GEMINI_API_KEY="AIza..."
$env:CLAUDE_API_KEY="sk-ant-..."

设置好环境变量后，运行以下命令执行测试:
python -m tests.test_llm openai    # 仅测试 OpenAI（默认）
python -m tests.test_llm gemini    # 仅测试 Gemini（需填 API Key）
python -m tests.test_llm claude    # 仅测试 Claude（需填 API Key）
python -m tests.test_llm all       # 全部平台
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from application.llm.base_client import BaseLLMClient
from application.llm.config import LLMProviderConfig
from application.llm.exceptions import LLMError
from application.llm.models import LLMRequest
from application.llm.openai_client import OpenAICompatibleClient
from application.llm.gemini_client import GeminiClient
from application.llm.claude_client import ClaudeClient
from pydantic_definitions.novel_pydantic import ExtractIdeaSchema, NovelMetaSchema

#  日志配置 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

DIVIDER = "=" * 60

OPENAI_CONFIG = LLMProviderConfig(
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    api_key=os.environ.get("OPENAI_API_KEY", ""),
    default_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    enabled=True,
    timeout_seconds=120,
    max_retries=2,
    supports_streaming=True,
    supports_json_schema=True,
    supports_function_calling=True,
)

# Google Gemini
GEMINI_CONFIG = LLMProviderConfig(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    default_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
    enabled=True,
    timeout_seconds=120,
    max_retries=2,
    supports_streaming=True,
    supports_json_schema=True,
    supports_function_calling=True,
)

# Anthropic Claude
CLAUDE_CONFIG = LLMProviderConfig(
    api_key=os.environ.get("CLAUDE_API_KEY", ""),
    default_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    enabled=True,
    timeout_seconds=120,
    max_retries=2,
    supports_streaming=True,
    supports_json_schema=True,
    supports_function_calling=True,
)


def make_client(provider: str) -> BaseLLMClient:
    """根据平台名创建测试客户端。"""
    if provider == "openai":
        return OpenAICompatibleClient(OPENAI_CONFIG, provider_name="test_openai")
    if provider == "gemini":
        if not GEMINI_CONFIG.api_key:
            raise ValueError("请在 GEMINI_CONFIG 中填入有效的 Gemini API Key")
        return GeminiClient(GEMINI_CONFIG, provider_name="test_gemini")
    if provider == "claude":
        if not CLAUDE_CONFIG.api_key:
            raise ValueError("请在 CLAUDE_CONFIG 中填入有效的 Claude API Key")
        return ClaudeClient(CLAUDE_CONFIG, provider_name="test_claude")
    raise ValueError(f"未知的测试平台: {provider}")


#  测试 1: 普通文本生成 
async def test_text_generate(provider: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"测试 [{provider}]: text_generate — 普通文本生成")
    print(DIVIDER)

    client = make_client(provider)
    request = LLMRequest(
        messages=[{"role": "user", "content": "用一句话介绍什么是玄幻小说。"}],
        temperature=0.7,
        max_tokens=200,
    )
    response = await client.text_generate(request)

    assert response.success, f"调用失败: {response.error}"
    assert response.content, "返回内容为空"
    print(f"[模型] {response.model}")
    print(f"[Token] {response.usage.total_tokens}")
    print(f"[耗时] {response.duration_ms}ms")
    print(f"[内容] {response.content}")
    print(f"✅ [{provider}] text_generate 测试通过")


#  测试 2: 结构化输出 — ExtractIdeaSchema 
async def test_schema_extract_idea(provider: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"测试 [{provider}]: schema_generate — ExtractIdeaSchema")
    print(DIVIDER)

    client = make_client(provider)
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
    response = await client.schema_generate(request, ExtractIdeaSchema)

    assert response.success, f"调用失败: {response.error}"
    parsed = ExtractIdeaSchema.model_validate_json(response.content)
    print(f"[模型] {response.model}")
    print(f"[Token] {response.usage.total_tokens}")
    print(f"[耗时] {response.duration_ms}ms")
    print(f"[结果] {parsed.model_dump()}")
    assert parsed.theme, "theme 字段为空"
    assert parsed.genre, "genre 字段为空"
    print(f"✅ [{provider}] schema_generate (ExtractIdeaSchema) 测试通过")


#  测试 3: 结构化输出 — NovelMetaSchema 
async def test_schema_novel_meta(provider: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"测试 [{provider}]: schema_generate — NovelMetaSchema")
    print(DIVIDER)

    client = make_client(provider)
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
    response = await client.schema_generate(request, NovelMetaSchema)

    assert response.success, f"调用失败: {response.error}"
    parsed = NovelMetaSchema.model_validate_json(response.content)
    print(f"[模型] {response.model}")
    print(f"[Token] {response.usage.total_tokens}")
    print(f"[耗时] {response.duration_ms}ms")
    print(f"[标题] {parsed.title}")
    print(f"[副标题] {parsed.subtitle}")
    print(f"[简介] {parsed.summary[:80]}...")
    print(f"[视角] {parsed.narrative_pov}")
    print(f"[风格] {parsed.writing_style}")
    print(f"[时代] {parsed.setting}")
    assert parsed.title, "title 字段为空"
    assert parsed.summary, "summary 字段为空"
    print(f"✅ [{provider}] schema_generate (NovelMetaSchema) 测试通过")


#  测试 4: 流式文本输出 
async def test_stream_text(provider: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"测试 [{provider}]: stream_text — 流式文本输出")
    print(DIVIDER)

    client = make_client(provider)
    request = LLMRequest(
        messages=[{"role": "user", "content": "用三句话写一段玄幻小说的开场白。"}],
        temperature=0.8,
        max_tokens=300,
    )
    chunks: list[str] = []
    print("[流式输出] ", end="", flush=True)
    async for chunk in client.stream_text(request):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    print()

    full_text = "".join(chunks)
    assert full_text, "流式输出内容为空"
    print(f"[总长度] {len(full_text)} 字符")
    print(f"✅ [{provider}] stream_text 测试通过")


#  测试 5: LLMService 高层封装 ─
async def test_llm_service() -> None:
    """通过 LLMService 测试（仅使用 OpenAI Compatible）。"""
    print(f"\n{DIVIDER}")
    print("测试 [service]: LLMService — 高层服务封装")
    print(DIVIDER)

    if not OPENAI_CONFIG.api_key:
        raise ValueError("请设置环境变量 OPENAI_API_KEY 后再运行 LLMService 测试")

    from application.config import update_config
    update_config({
        "llm": {
            "default_provider": "test_openai",
            "providers": {
                "test_openai": {
                    "type": "openai",
                    "base_url": OPENAI_CONFIG.base_url,
                    "api_key": OPENAI_CONFIG.api_key,
                    "default_model": OPENAI_CONFIG.default_model,
                    "enabled": True,
                    "timeout_seconds": 120,
                    "max_retries": 2,
                    "supports_streaming": True,
                    "supports_json_schema": True,
                    "supports_function_calling": True,
                }
            },
        }
    })

    from application.services.llm import LLMService

    svc = LLMService()

    # 文本生成
    text = await svc.generate_text(
        prompt="用一句话形容修仙世界的壮丽。",
        system_prompt="你是一位文笔优美的小说作者。",
        temperature=0.7,
        max_tokens=200,
    )
    assert text, "LLMService.generate_text 返回为空"
    print(f"[文本生成] {text}")

    # 结构化生成
    idea = await svc.generate_structured(
        prompt="我想写一个末世废土风格的科幻小说，主角在废墟中寻找失落文明的秘密。",
        schema=ExtractIdeaSchema,
        system_prompt="你是资深中文网络小说策划编辑。请提取故事构思要素。",
        temperature=0.7,
        max_tokens=500,
    )
    assert isinstance(idea, ExtractIdeaSchema), f"返回类型错误: {type(idea)}"
    print(f"[结构化生成] {idea.model_dump()}")

    print("✅ [service] LLMService 测试通过")


#  按平台运行测试套件 
async def run_provider_tests(provider: str) -> tuple[int, int]:
    """运行指定平台的全部测试，返回 (passed, failed)。"""
    tests = [
        (f"[{provider}] text_generate", test_text_generate),
        (f"[{provider}] schema (ExtractIdea)", test_schema_extract_idea),
        (f"[{provider}] schema (NovelMeta)", test_schema_novel_meta),
        (f"[{provider}] stream_text", test_stream_text),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            await fn(provider)
            passed += 1
        except LLMError as e:
            print(f"\n❌ {name} 失败 (LLM 异常): [{type(e).__name__}] {e}")
            failed += 1
        except (AssertionError, ValueError) as e:
            print(f"\n❌ {name} 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {name} 失败 (未知异常): [{type(e).__name__}] {e}")
            failed += 1
    return passed, failed

async def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "openai"

    if arg == "all":
        providers = ["openai", "gemini", "claude"]
    else:
        providers = [arg]

    total_passed = 0
    total_failed = 0

    for provider in providers:
        print(f"\n{'#' * 60}")
        print(f"# 平台: {provider.upper()}")
        print(f"{'#' * 60}")
        try:
            p, f = await run_provider_tests(provider)
            total_passed += p
            total_failed += f
        except ValueError as e:
            print(f"\n⚠️ 跳过 {provider}: {e}")

    # LLMService 测试（仅 OpenAI）
    if "openai" in providers:
        try:
            await test_llm_service()
            total_passed += 1
        except Exception as e:
            print(f"\n❌ [service] LLMService 失败: [{type(e).__name__}] {e}")
            total_failed += 1

    print(f"\n{DIVIDER}")
    print(f"测试完成: {total_passed} 通过, {total_failed} 失败 / 共 {total_passed + total_failed} 项")
    print(DIVIDER)

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
