"""Provider 默认值、单次生成和任务节点共用的思考参数。"""

from typing import Literal

from pydantic import BaseModel, Field


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
ThinkingMode = Literal["enabled", "disabled", "adaptive", "between_tools"]
ReasoningMode = Literal["standard", "pro"]
Verbosity = Literal["low", "medium", "high"]


class ReasoningOptions(BaseModel):
    """可选思考参数；空值沿用 Provider 或模型默认值，具体限制由接口检查。"""

    reasoning_effort: ReasoningEffort | None = Field(default=None, description="思考等级")
    thinking_mode: ThinkingMode | None = Field(default=None, description="DeepSeek / Claude 思考模式")
    thinking_budget: int | None = Field(default=None, ge=-1, description="旧版 Gemini / Claude 思考 token 预算")
    reasoning_mode: ReasoningMode | None = Field(default=None, description="OpenAI Responses 标准或 Pro 推理")
    verbosity: Verbosity | None = Field(default=None, description="OpenAI 输出详细程度")


REASONING_FIELDS = tuple(ReasoningOptions.model_fields)
