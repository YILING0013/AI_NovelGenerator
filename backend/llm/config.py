"""LLM 服务商配置模型与配置读取工具。"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from backend.config import get_config_value
from backend.llm.generation_options import ReasoningOptions

# 支持的客户端类别
LLMProviderType = Literal["openai", "gemini", "claude", "deepseek"]
LLMApiMode = Literal["auto", "responses", "chat_completions", "interactions", "generate_content"]
StructuredOutputMode = Literal["auto", "json_schema", "json_object", "tool_call"]


class LLMProviderConfig(ReasoningOptions):
    """单个 LLM 服务商的接入配置。

    type 字段决定接口模式（openai / gemini / claude / deepseek），
    配置的 key 作为用户自定义别名，同一 type 可定义多个不同别名的配置。
    """

    type: LLMProviderType = Field(default="openai", description="接口模式: openai / gemini / claude / deepseek")
    base_url: str = Field(default="", description="服务商 API 基地址")
    api_key: str = Field(default="", description="API Key")
    default_model: str = Field(default="", description="默认模型名称")
    enabled: bool = Field(default=False, description="是否启用")
    timeout_seconds: int = Field(default=60, description="请求超时（秒）")
    max_retries: int = Field(default=2, description="最大重试次数")
    max_concurrency: int = Field(default=5, description="最大并发数")
    use_system_proxy: bool = Field(default=False, description="是否允许 SDK 读取系统代理配置")
    supports_streaming: bool = Field(default=True, description="是否支持流式输出")
    supports_json_schema: bool = Field(default=False, description="是否支持 JSON Schema 输出")
    supports_json_output: bool | None = Field(default=None, description="JSON Output 开关；未设置时保留旧兼容配置")
    supports_function_calling: bool = Field(default=False, description="是否支持 function calling")
    api_mode: LLMApiMode = Field(default="auto", description="调用接口；自动模式为官方地址选择新版接口")
    structured_output_mode: StructuredOutputMode = Field(default="auto", description="结构化输出方式")

    # 模型或接口资料，只校验数值，不改变任何请求预算。
    context_window_tokens: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="上下文总容量，未知留空")
    input_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="单次输入上限，未知留空")
    output_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="模型或接口输出上限，未知留空")

    # 生成参数默认值（请求未指定时使用，请求级别优先）
    temperature: float | None = Field(default=None, ge=0, le=2, description="默认采样温度")
    top_p: float | None = Field(default=None, ge=0, le=1, description="默认核采样概率")
    max_tokens: int | None = Field(default=None, gt=0, description="默认最大生成 token 数")
    system_prompt: str | None = Field(default=None, description="默认系统提示词")
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, description="默认存在惩罚")
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, description="默认频率惩罚")

    @property
    def is_deepseek(self) -> bool:
        """判断当前配置是否选用 DeepSeek 兼容模式。

        Returns:
            选择 DeepSeek 模式时返回 True，与接口地址和模型名称无关。
        """
        return self.type == "deepseek"

    @property
    def resolved_api_mode(self) -> str:
        """选择实际接口；自定义地址默认保留兼容接口，可在设置中明确切换。

        Returns:
            当前 Provider 使用的接口名称。
        """
        allowed = {"openai": {"responses", "chat_completions"},
                   "deepseek": {"responses", "chat_completions"},
                   "gemini": {"interactions", "generate_content"}, "claude": {"messages"}}
        if self.api_mode != "auto":
            if self.api_mode not in allowed[self.type]:
                raise ValueError(f"{self.type} 不支持接口 {self.api_mode}，请修改接口模式")
            return self.api_mode
        host = urlsplit(self.base_url).hostname
        official = not self.base_url or host in {
            "openai": {"api.openai.com"}, "deepseek": {"api.deepseek.com"},
            "gemini": {"generativelanguage.googleapis.com"}, "claude": {"api.anthropic.com"},
        }[self.type]
        if self.type == "claude":
            return "messages"
        if self.type == "gemini":
            return "interactions" if official else "generate_content"
        return "responses" if official else "chat_completions"

    @property
    def resolved_structured_output_mode(self) -> str:
        """解析实际输出格式，保留旧自动配置的行为。

        Returns:
            json_object、json_schema 或 tool_call。
        """
        if self.structured_output_mode != "auto":
            if self.structured_output_mode == "json_object" and self.type not in {"openai", "deepseek"}:
                raise ValueError("JSON Output 仅用于 OpenAI 兼容接口")
            return self.structured_output_mode
        return "json_object" if self.is_deepseek and self.resolved_api_mode == "chat_completions" else "json_schema"

    @property
    def json_output_enabled(self) -> bool:
        """保留旧 JSON Output 配置，并尊重后续手动开关。

        Returns:
            当前是否启用 JSON Output。
        """
        return self.supports_json_output if self.supports_json_output is not None else self.resolved_structured_output_mode == "json_object"

    @property
    def uses_native_schema(self) -> bool:
        """区分原生 Schema 与仅保证 JSON 对象的输出方式。

        Returns:
            当前选择原生 Schema 时为 True。
        """
        return self.resolved_structured_output_mode == "json_schema"


class LLMConfig(BaseModel):
    """LLM 总体配置，包含默认服务商与所有服务商列表。"""

    default_provider: str = Field(default="openai_gpt4o_mini", description="默认服务商别名")
    format_review_provider: str = Field(default="", description="格式审校服务商别名，需支持 JSON Schema 或 JSON Output")
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
