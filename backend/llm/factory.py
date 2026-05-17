"""LLM 客户端工厂，根据服务商别名创建对应客户端实例。"""

from __future__ import annotations

from backend.llm.base_client import BaseLLMClient
from backend.llm.config import LLMProviderConfig, get_provider_config


def create_llm_client(
    provider_name: str | None = None,
    *,
    timeout_seconds: int | None = None,
) -> BaseLLMClient:
    """根据服务商别名创建 LLM 客户端。

    provider_name 为用户自定义的配置别名（如 "deepseek_chat"、"gemini_flash"），
    工厂通过配置中的 type 字段决定实例化哪种客户端：
      - "openai": OpenAI 兼容客户端
      - "gemini": Google Gemini 客户端
      - "claude": Anthropic Claude 客户端

    Args:
        provider_name: 用户自定义 Provider 别名，空值表示默认 Provider。
        timeout_seconds: 临时覆盖的请求超时时间。

    Returns:
        对应类型的 LLM 客户端实例。
    """
    config = get_provider_config(provider_name)
    return create_llm_client_from_config(
        config,
        provider_name=provider_name,
        timeout_seconds=timeout_seconds,
        require_enabled=True,
    )


def create_llm_client_from_config(
    config: LLMProviderConfig,
    provider_name: str | None = None,
    *,
    timeout_seconds: int | None = None,
    require_enabled: bool = True,
) -> BaseLLMClient:
    """根据已解析的 Provider 配置创建 LLM 客户端。

    Args:
        config: 已解析的单个 Provider 配置。
        provider_name: 用户自定义别名，用于日志与错误定位。
        timeout_seconds: 临时覆盖的请求超时时间。
        require_enabled: 是否要求 Provider 已启用。

    Returns:
        对应类型的 LLM 客户端实例。

    Raises:
        ValueError: Provider 未启用、缺少 API Key 或类型不受支持时抛出。
    """
    if timeout_seconds is not None and timeout_seconds > 0:
        config = config.model_copy(update={"timeout_seconds": timeout_seconds})

    if require_enabled and not config.enabled:
        name = provider_name or "default"
        raise ValueError(f"LLM 服务商 '{name}' 未启用，请在配置中设置 enabled: true")

    if not config.api_key:
        raise ValueError("LLM 服务商未配置 api_key")

    provider_type = config.type
    alias = provider_name or "default"

    if provider_type == "openai":
        from backend.llm.openai_client import OpenAICompatibleClient
        return OpenAICompatibleClient(config, provider_name=alias)

    if provider_type == "gemini":
        from backend.llm.gemini_client import GeminiClient
        return GeminiClient(config, provider_name=alias)

    if provider_type == "claude":
        from backend.llm.claude_client import ClaudeClient
        return ClaudeClient(config, provider_name=alias)

    raise ValueError(f"不支持的 LLM 服务商类型: {provider_type}")
