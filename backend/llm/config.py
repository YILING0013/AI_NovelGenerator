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
    "Cấu hình kết nối của một nhà cung cấp LLM.\n\n    Trường type quyết định chế độ giao diện (openai / gemini / claude / deepseek),\n    key cấu hình đóng vai trò bí danh do người dùng tự đặt, cùng một type có thể khai báo nhiều cấu hình với bí danh khác nhau.\n    "

    type: LLMProviderType = Field(default="openai", description="Chế độ API: openai / gemini / claude / deepseek")
    base_url: str = Field(default="", description="Địa chỉ gốc API của nhà cung cấp")
    api_key: str = Field(default="", description="API Key")
    default_model: str = Field(default="", description="Tên mô hình mặc định")
    enabled: bool = Field(default=False, description="Có bật hay không")
    timeout_seconds: int = Field(default=60, description="Thời gian chờ yêu cầu (giây)")
    max_retries: int = Field(default=2, description="Số lần thử lại tối đa")
    max_concurrency: int = Field(default=5, description="Số yêu cầu đồng thời tối đa")
    use_system_proxy: bool = Field(default=False, description="Có cho phép SDK đọc cấu hình proxy hệ thống")
    supports_streaming: bool = Field(default=True, description="Có hỗ trợ streaming")
    supports_json_schema: bool = Field(default=False, description="Có hỗ trợ output JSON Schema")
    supports_json_output: bool | None = Field(default=None, description="Công tắc JSON Output; nếu chưa đặt thì giữ cấu hình tương thích cũ")
    supports_function_calling: bool = Field(default=False, description="Có hỗ trợ function calling")
    api_mode: LLMApiMode = Field(default="auto", description="Cách gọi API; chế độ tự động chọn API phiên bản mới cho địa chỉ chính thức")
    structured_output_mode: StructuredOutputMode = Field(default="auto", description="Phương thức output có cấu trúc")

    # 模型或接口资料，只校验数值，不改变任何请求预算。
    context_window_tokens: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="Tổng dung lượng ngữ cảnh, không rõ thì để trống")
    input_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="Giới hạn đầu vào mỗi lần, không rõ thì để trống")
    output_token_limit: int | None = Field(default=None, gt=0, le=9007199254740991, strict=True, description="Giới hạn output của mô hình hoặc API, không rõ thì để trống")

    # 生成参数默认值（请求未指定时使用，请求级别优先）
    temperature: float | None = Field(default=None, ge=0, le=2, description="Nhiệt độ sampling mặc định")
    top_p: float | None = Field(default=None, ge=0, le=1, description="Xác suất nucleus sampling mặc định")
    max_tokens: int | None = Field(default=None, gt=0, description="Số token sinh tối đa mặc định")
    system_prompt: str | None = Field(default=None, description="Prompt hệ thống mặc định")
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, description="Mức phạt presence mặc định")
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, description="Mức phạt frequency mặc định")

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
                raise ValueError(f"{self.type} không hỗ trợ API {self.api_mode}, vui lòng chỉnh lại chế độ API")
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
                raise ValueError("JSON Output chỉ dùng cho API tương thích OpenAI")
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
    "Cấu hình tổng thể LLM, gồm nhà cung cấp mặc định và danh sách toàn bộ nhà cung cấp."

    default_provider: str = Field(default="openai_gpt4o_mini", description="Biệt danh nhà cung cấp mặc định")
    format_review_provider: str = Field(default="", description="Biệt danh nhà cung cấp dùng để kiểm tra định dạng, cần hỗ trợ JSON Schema hoặc JSON Output")
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict, description="Ánh xạ cấu hình nhà cung cấp (key là biệt danh)")


def get_llm_config() -> LLMConfig:
    """从应用配置中读取并解析 LLM 配置段。"""
    raw = get_config_value("llm", {})
    return LLMConfig.model_validate(raw)


def get_provider_config(provider_name: str | None = None) -> LLMProviderConfig:
    """获取指定别名的服务商配置，未指定时返回默认服务商。"""
    llm_cfg = get_llm_config()
    name = provider_name or llm_cfg.default_provider
    if name not in llm_cfg.providers:
        raise ValueError(f"Không tìm thấy cấu hình nhà cung cấp LLM: {name}")
    return llm_cfg.providers[name]
