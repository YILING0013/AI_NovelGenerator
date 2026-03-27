"""LLM 统一请求/响应数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TokenUsage(BaseModel):
    """Token 用量统计。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMRequest(BaseModel):
    """统一的 LLM 调用请求参数。"""

    model: str | None = Field(default=None, description="模型名称，为空时使用服务商默认模型")
    messages: list[dict[str, str]] = Field(default_factory=list, description="对话消息列表")
    system_prompt: str = Field(default="", description="系统提示词")
    temperature: float | None = Field(default=None, ge=0, le=2, description="采样温度")
    top_p: float | None = Field(default=None, ge=0, le=1, description="核采样概率")
    max_tokens: int | None = Field(default=None, gt=0, description="最大生成 token 数")
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, description="存在惩罚")
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, description="频率惩罚")
    stop: list[str] | None = Field(default=None, description="停止序列")
    stream: bool = Field(default=False, description="是否流式输出")
    metadata: dict[str, Any] | None = Field(default=None, description="额外元数据")


class LLMResponse(BaseModel):
    """统一的 LLM 调用响应结构。"""

    content: str = Field(default="", description="生成的文本内容")
    raw_response: dict[str, Any] | None = Field(default=None, description="原始响应")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 用量")
    model: str = Field(default="", description="实际使用的模型")
    provider: str = Field(default="", description="服务商名称")
    duration_ms: int = Field(default=0, description="请求耗时（毫秒）")
    finish_reason: str = Field(default="", description="结束原因")
    success: bool = Field(default=True, description="是否成功")
    error: str = Field(default="", description="错误信息")
