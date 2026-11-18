"""小说助手的公开请求与工具参数，不接受任意数据库字段。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString


ResourceKind = Literal["novel", "volume", "arc", "scene", "chapter", "character", "faction", "location", "item", "world_rule", "character_relation", "faction_relation", "character_faction_binding", "character_volume_state", "faction_volume_state", "foreshadowing"]


class AssistantModel(BaseModel):
    "Từ chối tham số không khai báo; khoảng trắng trong nội dung giữ nguyên."

    model_config = ConfigDict(extra="forbid")


class ResourceRef(AssistantModel):
    "Vị trí ổn định của một loại tài liệu trong tiểu thuyết."

    resource_type: ResourceKind
    id: str = Field(min_length=1, max_length=100)


class ContextAttachment(ResourceRef):
    "Tư liệu hoặc bản thảo mà người dùng minh thị chọn; không coi bản thảo trên trang là nội dung đã lưu."

    fields: list[str] = Field(default_factory=list, max_length=30)
    usage: Literal["reference", "target"] = "reference"
    origin: Literal["saved", "draft"] = "saved"
    version: int | None = Field(default=None, ge=1)
    text: str | None = Field(default=None, max_length=12000)


class SessionCreate(AssistantModel):
    "Tạo một hội thoại độc lập mới cho tiểu thuyết hiện tại."

    title: str = Field(default="Cuộc trò chuyện mới", min_length=1, max_length=100)
    mode: Literal["review", "auto"] = "review"
    provider: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=200)


class SessionUpdate(AssistantModel):
    "Sửa cài đặt phiên; vòng đang thực thi giữ nguyên cấu hình lúc gửi."

    title: str | None = Field(default=None, min_length=1, max_length=100)
    archived: bool | None = None
    mode: Literal["review", "auto"] | None = None
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)


class TurnRequest(AssistantModel):
    "Cố định trang hiện tại và tệp đính kèm của tác giả khi gửi."

    message: str = Field(min_length=1, max_length=16000)
    attachments: list[ContextAttachment] = Field(default_factory=list, max_length=20)
    location: ResourceRef | None = None
    writing_target: ResourceRef | None = None
    allow_navigation: bool = False
    execution_mode: Literal["auto", "review"] | None = None


class AnswerRequest(AssistantModel):
    "Trả lời câu hỏi gốc; không được thay mục tiêu gốc, cài đặt mô hình hay sửa bản chỉnh sửa."

    question_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=5000)
    confirmation_token: str | None = Field(default=None, max_length=64)


class ContinueRequest(AssistantModel):
    "Số 0 nghĩa là chạy tiếp theo ngân sách còn lại; số dương là số vòng tác giả minh thị cộng thêm."

    additional_rounds: int = Field(default=4, ge=0, le=16)


class WritingAnswerMeaning(AssistantModel):
    "Lớp ngoài dùng bộ hỏi đáp đầy đủ để làm rõ đối tượng được chỉ; subtask chỉ nhận các hành động sáng tác cố định này."

    answer_id: str
    supported: bool
    actions: list[Literal["continue_request", "preserve_plot", "preserve_ending", "rewrite_expression", "expand_detail", "condense", "more_subtle", "more_direct", "more_dialogue", "less_dialogue", "preserve_viewpoint"]] = Field(max_length=4)
    resolved_by_answer_id: str | None = Field(default=None, description="Sự mơ hồ của câu trả lời ngắn này đã được làm rõ bởi câu trả lời nào của tác giả đưa ra sau đó; chỉ điền ID câu trả lời thật, không điền văn bản câu hỏi")


class WritingAnswerReview(AssistantModel):
    "Đối chiếu từng câu trả lời theo đúng thứ tự gốc, không cho phép mô hình xuất tóm tắt, trích dẫn hay văn bản cốt truyện tự do."

    answers: list[WritingAnswerMeaning]


class ChangeOperation(AssistantModel):
    "Một thao tác nghiệp vụ ứng viên; phía server riêng cố định phiên bản gốc và giá trị trước."

    action: Literal["create", "update", "delete", "restore", "reorder", "status", "preparation"]
    resource_type: ResourceKind
    id: str | None = Field(default=None, max_length=100)
    parent_id: str | None = Field(default=None, max_length=100)
    temporary_id: str | None = Field(default=None, pattern=r"^new_[A-Za-z0-9_]{1,60}$")
    fields: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reject_foreshadowing_write(self) -> "ChangeOperation":
        """首版助手只能读取伏笔，不暂存或执行其写入。

        Args:
            无。
        Returns:
            原业务允许的修改操作。
        """
        if self.resource_type == "foreshadowing":
            raise ValueError("Chi tiết phục bút chỉ để đọc, hãy để tác giả ghi hoặc sửa ở bàn làm việc phục bút")
        return self


class ChangeEdit(AssistantModel):
    "Chỉnh sửa ứng viên nghiệp vụ chưa lưu, căn cứ gốc không được trình duyệt thay thế."

    expected_revision: int = Field(ge=1)
    operations: list[ChangeOperation] | None = Field(default=None, min_length=1, max_length=50)
    candidate: dict[str, Any] | None = None

    @model_validator(mode="after")
    def one_candidate(self):
        """普通修改与原任务候选只能提交一种。"""
        if (self.operations is None) == (self.candidate is None):
            raise ValueError("Hãy gửi một trong hai loại: chỉnh sửa thông thường hoặc ứng viên nhiệm vụ gốc")
        return self


class ChangeApproval(AssistantModel):
    "Chấp nhận phiên bản chỉnh sửa được chỉ định; tách riêng rủi ro thao tác nguy hiểm và rủi ro nội dung."

    expected_revision: int = Field(ge=1)
    confirm_lifecycle: bool = False
    accept_content_risk: bool = False
    confirmation_token: str | None = Field(default=None, max_length=64)


class ReviewIssue(AssistantModel):
    "Kiểm tra nội dung phải chỉ tới nguồn thực tế, nội dung chưa kiểm tra được liệt kê riêng."

    severity: Literal["conflict", "suggestion", "unchecked"]
    message: str = Field(min_length=1, max_length=2000)
    sources: list[ResourceRef] = Field(default_factory=list, max_length=20)


class ReviewResult(AssistantModel):
    "Kết luận có cấu trúc từ một lượt mô hình xét duyệt độc lập."

    summary: str = Field(min_length=1, max_length=2000)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=50)
    author_intent_supported: bool = False


class NavigationTarget(ResourceRef):
    "Frontend ánh xạ vị trí nội bộ theo loại nghiệp vụ, không thực thi URL do mô hình trả về."

    field: str | None = Field(default=None, max_length=100)


class FactChangeRequest(AssistantModel):
    "Trợ lý chỉ cung cấp nội dung đề xuất sửa; căn cứ, nguyên văn tác giả và confirmed đều do phía server tạo."

    resource_type: Literal["character", "character_relation", "item", "faction"]
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    id: str | None = None
    candidate: dict[str, Any] | None = None
    position: dict[str, Any]
    after: dict[str, Any]
    replaces: dict[str, str] | str | None = None
    resolves: dict[str, list[str]] | list[str] | None = None
    evidence: dict[str, Any] | None = None
