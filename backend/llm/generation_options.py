"""Provider 默认值、单次生成和任务节点共用的思考参数。"""

from typing import Literal

from pydantic import BaseModel, Field


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
ThinkingMode = Literal["enabled", "disabled", "adaptive", "between_tools"]
ReasoningMode = Literal["standard", "pro"]
Verbosity = Literal["low", "medium", "high"]


class ReasoningOptions(BaseModel):
    """可选思考参数；空值沿用 Provider 或模型默认值，具体限制由接口检查。"""

    reasoning_effort: ReasoningEffort | None = Field(default=None, description="Cấp độ tư duy")
    thinking_mode: ThinkingMode | None = Field(default=None, description="Chế độ tư duy DeepSeek / Claude")
    thinking_budget: int | None = Field(default=None, ge=-1, description="Ngân sách token tư duy của Gemini / Claude đời cũ")
    reasoning_mode: ReasoningMode | None = Field(default=None, description="Chế độ reasoning chuẩn hoặc Pro của OpenAI Responses")
    verbosity: Verbosity | None = Field(default=None, description="Mức độ chi tiết output của OpenAI")


REASONING_FIELDS = tuple(ReasoningOptions.model_fields)
