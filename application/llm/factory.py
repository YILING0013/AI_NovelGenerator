"""LLM 客户端工厂，根据服务商别名创建对应客户端实例。"""

from __future__ import annotations

from application.llm.base_client import BaseLLMClient
from application.llm.config import get_provider_config


def create_llm_client(provider_name: str | None = None) -> BaseLLMClient:
    """根据服务商别名创建 LLM 客户端。

    provider_name 为用户自定义的配置别名（如 "deepseek_chat"、"gemini_flash"），
    工厂通过配置中的 type 字段决定实例化哪种客户端：
      - "openai": OpenAI 兼容客户端
      - "gemini": Google Gemini 客户端
      - "claude": Anthropic Claude 客户端
    """
    config = get_provider_config(provider_name)

    if not config.enabled:
        name = provider_name or "default"
        raise ValueError(f"LLM 服务商 '{name}' 未启用，请在配置中设置 enabled: true")

    if not config.api_key:
        raise ValueError("LLM 服务商未配置 api_key")

    provider_type = config.type
    alias = provider_name or "default"

    if provider_type == "openai":
        from application.llm.openai_client import OpenAICompatibleClient
        return OpenAICompatibleClient(config, provider_name=alias)

    if provider_type == "gemini":
        from application.llm.gemini_client import GeminiClient
        return GeminiClient(config, provider_name=alias)

    if provider_type == "claude":
        from application.llm.claude_client import ClaudeClient
        return ClaudeClient(config, provider_name=alias)

    raise ValueError(f"不支持的 LLM 服务商类型: {provider_type}")
