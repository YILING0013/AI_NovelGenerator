"""单卷、单篇章详细剧情的生成、审核与准备确认。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StringConstraints

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.arc_contract import ArcPlanningV1
from backend.llm.schemas.volume_planning_pydantic import VolumePlanningV1
from backend.services.novel.writing_contract import WritingContextBasisV1


PLOT_TASKS = {"generate_volume_plot_by_ai": "volume", "generate_arc_plot_by_ai": "arc"}


class PlotGenerateInputV1(StrictRequestModel):
    "Đầu vào tạo cốt truyện cho quyển hoặc vòng truyện đã có; phiên bản đích dùng để ngăn ghi đề bản thảo thủ công."

    novel_id: ObjectIdString
    target_type: Literal["volume", "arc"]
    target_id: ObjectIdString
    expected_version: int = Field(ge=1)
    user_guidance: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(default="", max_length=5000, title="作者要求")


class PlotSourceReferenceV1(StrictRequestModel):
    "Nguồn đã lưu do mô hình chỉ ra; vị trí sai và tham chiếu rỗng được giữ nguyên cho tác giả đối chiếu."

    model_config = ConfigDict(str_strip_whitespace=False)

    resource_type: str = Field(max_length=64)
    id: str = Field(max_length=100)
    field: str = Field(max_length=200)
    quote: str = Field(max_length=2000)


class PlotSourceConflictV1(StrictRequestModel):
    "Một cặp nghi xung đột giữa văn bản chương và kế hoạch cũ; không thay tác giả quyết định bên nào đúng."

    model_config = ConfigDict(str_strip_whitespace=False)

    message: str = Field(max_length=1000)
    saved_text: PlotSourceReferenceV1
    old_plan: PlotSourceReferenceV1


class PlotSourceVerificationV1(StrictRequestModel):
    "Khớp trích dẫn chỉ nghĩa là câu gốc xuất hiện trong đầu vào thực tế, không đảm bảo phán đoán ngữ nghĩa là đúng."

    status: Literal["matched", "unverified"]
    source_truncated: bool | None


class PlotVerifiedSourceV1(PlotSourceReferenceV1):
    "Trạng thái tham chiếu đã máy chủ đối chiếu và việc cắt ngắn phần nhập thực tế."

    verification: PlotSourceVerificationV1


class PlotSourceConflictItemV1(StrictRequestModel):
    "Báo cáo hai nguồn kèm mã ổn định; server không tự phán xung đột là thật hay giả."

    model_config = ConfigDict(str_strip_whitespace=False)

    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    message: str = Field(max_length=1000)
    saved_text: PlotVerifiedSourceV1
    old_plan: PlotVerifiedSourceV1
    semantic_check: Literal["not_performed"]


class PlotSourceConflictReportV1(StrictRequestModel):
    "Phân biệt chưa báo cáo và báo cáo rỗng, không hiểu luồng cũ là đã kiểm tra mà không có xung đột."

    reported: bool
    items: list[PlotSourceConflictItemV1] = Field(max_length=12)


class PlotSourceConflictDecisionV1(StrictRequestModel):
    "Tác giả xác nhận đã đối chiếu một cặp nguồn và phê duyệt ứng viên lần này, hoặc có thể kết luận mô hình báo động giả."

    conflict_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool
    note: str = Field(default="", max_length=500)


class PlotConfirmedContentV1(StrictRequestModel):
    "Nội dung đã lưu thực tế mà tác giả nhìn thấy khi tích chọn xác nhận; khi đã có mục con thì không gồm kế hoạch."

    plot: str = Field(min_length=1, max_length=40000)
    planning: VolumePlanningV1 | ArcPlanningV1 | None = None


class PlotSourceConflictReviewV1(StrictRequestModel):
    "Báo cáo gốc cùng các quyết định của tác giả theo từng mục, gửi kèm lần xác nhận này."

    report: PlotSourceConflictReportV1
    decisions: list[PlotSourceConflictDecisionV1] = Field(max_length=12)
    confirmed_content: PlotConfirmedContentV1


class PlotResultV1(StrictRequestModel):
    "Kế hoạch độc lập cho cốt truyện dài và đề xuất hoàn thiện; phần mô tả bao phủ chỉ dùng để duyệt."

    plot: str = Field(min_length=1, max_length=40000)
    planning: VolumePlanningV1 | ArcPlanningV1
    coverage_notes: str = Field(default="", max_length=5000)
    source_conflicts: list[PlotSourceConflictV1] | None = Field(default=None, max_length=12)


class VolumePlotResultV1(PlotResultV1):
    "cốt truyện của tập chỉ đi kèm kế hoạch tập; giao diện chung vẫn tương thích hai loại ứng viên đã có."

    planning: VolumePlanningV1


class ArcPlotResultV1(PlotResultV1):
    "cốt truyện của vòng truyện chỉ đi kèm kế hoạch vòng truyện, không nhận trường kế hoạch tập."

    planning: ArcPlanningV1


class PlotCandidateBasisV1(CandidateBasisV1):
    "Ứng viêncốt truyện gắn với luồng gốc, nội dung thực đã đọc và phiên bản đích."

    generation_input: PlotGenerateInputV1
    context_basis: WritingContextBasisV1


class PlotGenerationEnvelopeV1(StrictResponseModel):
    "Ứng viên cốt truyện dùng chung cho yêu cầu thường và sự kiện hoàn tất SSE."

    workflow: str
    step: str
    schema_id: str
    schema_version: int
    candidate: PlotResultV1
    basis: PlotCandidateBasisV1
    context: dict[str, Any] = Field(default_factory=dict)
    prepared_context: dict[str, Any] | None = None
    coverage_review: dict[str, Any] | None = None


class PlotConfirmV1(StrictRequestModel):
    "Xác nhận cốt truyện sau khi đã duyệt, không sửa kế hoạch của các phần khác."

    candidate: PlotResultV1
    basis: PlotCandidateBasisV1
    expected_version: int = Field(ge=1)
    source_conflict_review: PlotSourceConflictReviewV1 | None = None


class VolumePreparationConfirmV1(StrictRequestModel):
    "Xác nhận giai đoạn chuẩn bị hiện tại sau khi kiểm tra thủ công tài liệu sẵn có, cho phép không tham gia."

    expected_version: int = Field(ge=1)
    location_ids: list[str] | None = Field(default=None, max_length=50)
