"""LLM 服务商配置模型与配置读取工具。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from application.config import get_config_value

# 支持的客户端类别
LLMProviderType = Literal["openai", "gemini", "claude"]


class LLMProviderConfig(BaseModel):
    """单个 LLM 服务商的接入配置。

    type 字段决定使用哪种客户端类别（openai / gemini / claude），
    配置的 key 作为用户自定义别名，同一 type 可定义多个不同别名的配置。
    """

    type: LLMProviderType = Field(default="openai", description="客户端类别: openai / gemini / claude")
    base_url: str = Field(default="", description="服务商 API 基地址")
    api_key: str = Field(default="", description="API Key")
    default_model: str = Field(default="", description="默认模型名称")
    enabled: bool = Field(default=False, description="是否启用")
    timeout_seconds: int = Field(default=60, description="请求超时（秒）")
    max_retries: int = Field(default=2, description="最大重试次数")
    max_concurrency: int = Field(default=5, description="最大并发数")
    supports_streaming: bool = Field(default=True, description="是否支持流式输出")
    supports_json_schema: bool = Field(default=False, description="是否支持 JSON Schema 输出")
    supports_function_calling: bool = Field(default=False, description="是否支持 function calling")


class LLMConfig(BaseModel):
    """LLM 总体配置，包含默认服务商与所有服务商列表。"""

    default_provider: str = Field(default="openai_gpt4o_mini", description="默认服务商别名")
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict, description="服务商配置映射（key 为别名）")


def get_llm_config() -> LLMConfig:
    """从应用配置中读取并解析 LLM 配置段。"""
    raw = get_config_value("llm", {})
    return LLMConfig.model_validate(raw)


def get_provider_config(provider_name: str | None = None) -> LLMProviderConfig:
    """获取指定别名的服务商配置，未指定时返回默认服务商。"""
    llm_cfg = get_llm_config()
    name = provider_name or llm_cfg.default_provider
    if name not in llm_cfg.providers:
        raise ValueError(f"未找到 LLM 服务商配置: {name}")
    return llm_cfg.providers[name]
