"""LLM 统一请求/响应数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from backend.llm.generation_options import ReasoningOptions


class TokenUsage(BaseModel):
    """Token 用量统计。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMRequest(ReasoningOptions):
    """统一的 LLM 调用请求参数。"""

    model: str | None = Field(default=None, description="Tên mô hình; để trống thì dùng mô hình mặc định của nhà cung cấp")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="Danh sách tin nhắn hội thoại")
    system_prompt: str = Field(default="", description="Câu lệnh hệ thống")
    temperature: float | None = Field(default=None, ge=0, le=2, description="Nhiệt độ lấy mẫu")
    top_p: float | None = Field(default=None, ge=0, le=1, description="Xác suất lấy mẫu hạt nhân")
    max_tokens: int | None = Field(default=None, gt=0, description="Số token tối đa được tạo")
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, description="Mức phạt hiện diện")
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, description="Mức phạt tần suất")
    stop: list[str] | None = Field(default=None, description="Chuỗi dừng")
    stream: bool = Field(default=False, description="Có trả về theo luồng hay không")
    json_output_schema: dict[str, Any] | None = Field(
        default=None, description="Cấu trúc JSON mục tiêu của đầu ra, dùng để ràng buộc khi trả về theo luồng và kiểm tra cục bộ"
    )
    metadata: dict[str, Any] | None = Field(default=None, description="Metadata bổ sung")


class LLMResponse(BaseModel):
    """统一的 LLM 调用响应结构。"""

    content: str = Field(default="", description="Nội dung văn bản được tạo")
    raw_response: dict[str, Any] | None = Field(default=None, description="Phản hồi gốc")
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Mức tiêu thụ token")
    model: str = Field(default="", description="Mô hình thực tế đã sử dụng")
    provider: str = Field(default="", description="Tên nhà cung cấp dịch vụ")
    duration_ms: int = Field(default=0, description="Thời gian xử lý yêu cầu (miligiây)")
    finish_reason: str = Field(default="", description="Nguyên nhân kết thúc")
    success: bool = Field(default=True, description="Có thành công hay không")
    error: str = Field(default="", description="Thông tin lỗi")


class LLMFunctionCallProbe(BaseModel):
    """Function Calling 能力探测参数。"""

    tool_name: str = Field(description="Tên công cụ thử nghiệm")
    tool_description: str = Field(description="Mô tả công cụ thử nghiệm")
    parameters_schema: dict[str, Any] = Field(description="JSON Schema của tham số đầu vào công cụ")
    expected_arguments: dict[str, Any] = Field(description="Tham số công cụ mà mô hình dự kiến sẽ tạo ra")
    tool_result: dict[str, Any] = Field(description="Kết quả thực thi công cụ được mô phỏng cục bộ")
    final_response_prompt: str = Field(description="Câu lệnh yêu cầu phản hồi cuối sau khi gửi kết quả công cụ trở lại mô hình")
    expected_final_text: str = Field(description="Văn bản bắt buộc phải có trong phản hồi cuối")


class LLMToolDefinition(BaseModel):
    """服务端允许模型调用的一个工具。"""

    name: str
    description: str
    parameters: dict[str, Any]


class LLMToolCall(BaseModel):
    """模型请求的原生调用；Gemini 旧模型可以不返回 ID。"""

    id: str | None = None
    name: str
    arguments: dict[str, Any]


class LLMToolResult(BaseModel):
    """一次调用的执行结果，保留原调用 ID 和名称。"""

    id: str | None = None
    name: str
    content: dict[str, Any]
    is_error: bool = False


class LLMToolTurn(BaseModel):
    """一轮工具对话；原生历史只供客户端续接，不能发送到浏览器。"""

    content: str = ""
    calls: list[LLMToolCall] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = ""
