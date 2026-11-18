"""LLM 统一请求/响应数据结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from backend.llm.generation_options import ReasoningOptions


class TokenUsage(BaseModel):
    "Thống kê sử dụng Token."

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LLMRequest(ReasoningOptions):
    "Tham số gọi LLM hợp nhất."

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
    "Cấu trúc phản hồi gọi LLM hợp nhất."

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
    "Tham số thăm dò năng lực Function Calling."

    tool_name: str = Field(description="Tên công cụ thử nghiệm")
    tool_description: str = Field(description="Mô tả công cụ thử nghiệm")
    parameters_schema: dict[str, Any] = Field(description="JSON Schema của tham số đầu vào công cụ")
    expected_arguments: dict[str, Any] = Field(description="Tham số công cụ mà mô hình dự kiến sẽ tạo ra")
    tool_result: dict[str, Any] = Field(description="Kết quả thực thi công cụ được mô phỏng cục bộ")
    final_response_prompt: str = Field(description="Câu lệnh yêu cầu phản hồi cuối sau khi gửi kết quả công cụ trở lại mô hình")
    expected_final_text: str = Field(description="Văn bản bắt buộc phải có trong phản hồi cuối")


class LLMToolDefinition(BaseModel):
    "Một công cụ mà máy chủ cho phép mô hình gọi."

    name: str
    description: str
    parameters: dict[str, Any]


class LLMToolCall(BaseModel):
    "Lời gọi native trong yêu cầu mô hình; các mô hình Gemini cũ có thể không trả về ID."

    id: str | None = None
    name: str
    arguments: dict[str, Any]


class LLMToolResult(BaseModel):
    "Kết quả thực thi của một lần gọi, giữ nguyên ID và tên của lời gọi gốc."

    id: str | None = None
    name: str
    content: dict[str, Any]
    is_error: bool = False


class LLMToolTurn(BaseModel):
    "Một vòng hội thoại công cụ; lịch sử native chỉ để client nối tiếp, không được gửi xuống trình duyệt."

    content: str = ""
    calls: list[LLMToolCall] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = ""
