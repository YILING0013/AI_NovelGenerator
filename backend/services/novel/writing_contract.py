"""层级生成候选的内容依据与审核确认契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.writing_pydantic import WritingGenerateInputV1
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.character_fact_contract import CharacterFactReadV1
from backend.services.novel.character_relation_fact_contract import CharacterRelationFactReadV1
from backend.services.novel.item_fact_contract import ItemFactReadV1
from backend.services.novel.faction_fact_contract import FactionFactReadV1


class WritingReadV1(StrictRequestModel):
    "Một kiểu đọc nội dung với ngữ nghĩa cố định, bao gồm cả truy vấn trống."

    kind: Literal["parent_chain", "children", "neighbors", "previous_written", "selected_entities", "selected_relations", "volume_states", "literal_search", "edit_target", "plot_sources", "volume_participants", "reading_position"]
    scope: dict[str, Any]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class WritingContextBasisV1(StrictRequestModel):
    "Chỉ băm nội dung nghiệp vụ thực tế, không dùng phiên bản thống kê của phần tử tổ tiên."

    version: Literal[1] = 1
    reads: list[WritingReadV1 | CharacterFactReadV1 | CharacterRelationFactReadV1 | ItemFactReadV1 | FactionFactReadV1] = Field(min_length=1, max_length=200)


class WritingCandidateBasisV1(CandidateBasisV1):
    "Căn cứ dành riêng cho bốn loại tác vụ viết, các tác vụ cũ tiếp tục dùng hợp đồng phiên bản nguyên bản."

    generation_input: WritingGenerateInputV1
    context_basis: WritingContextBasisV1


class WritingGenerationEnvelopeV1(StrictResponseModel):
    "Phản hồi thường và done.result của SSE dùng chung cùng một kết quả."

    workflow: str
    step: str
    schema_id: str
    schema_version: int
    candidate: dict[str, Any]
    basis: WritingCandidateBasisV1
    context: dict[str, Any]
    prepared_context: dict[str, Any] | None = None
    coverage_review: dict[str, Any] | None = None


class WritingConfirmV1(StrictRequestModel):
    "Chỉ gửi nội dung đã được tác giả duyệt cùng căn cứ tạo sinh; bổ sung không yêu cầu phiên bản cũ của tổ tiên."

    candidate: dict[str, Any] = Field(min_length=1)
    basis: WritingCandidateBasisV1
    expected_version: int | None = Field(default=None, ge=1)


class WritingConfirmResultV1(StrictResponseModel):
    "Đối tượng chính thức và ID ổn định của cùng lượt xác nhận, giúp frontend định vị nhánh hiện tại."

    operation: str
    ids: list[ObjectIdString]
    data: list[dict[str, Any]]


class WritingMissingV1(StrictResponseModel):
    "Các trường mà đối tượng hiện tại cần bổ sung."

    field: str
    message: str


class WritingReadinessV1(StrictResponseModel):
    "Trạng thái có thể thực thi của phần hiện tại, không lưu tiến độ lâu dài."

    target_type: Literal["volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    novel_id: ObjectIdString
    can_create_child: bool
    create_missing_fields: list[WritingMissingV1]
    can_refine: bool
    can_write: bool
    can_generate_plot: bool = False
    plot_status: Literal["missing", "stale", "ready"] = "missing"
    preparation: dict[str, bool] = Field(default_factory=dict)
    missing_fields: list[WritingMissingV1]
    blockers: list[dict[str, str]]
    parent_chain: list[dict[str, str]]
    expected_version: int
