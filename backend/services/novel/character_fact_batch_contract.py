"""人物和关系的整批新建；字段缺项保持未知，原请求可直接重试。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.character_pydantic import CoreCharactersGenerationInputV1
from backend.llm.schemas.character_relation_pydantic import CharacterRelationsGenerationInputV1
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.character_fact_contract import (
    CharacterFactCreateDataV1, CharacterFactPositionV1, CharacterFactValuesV1,
    CharacterId, FactConfirmed, FactVersion,
)
from backend.services.novel.character_relation_fact_contract import (
    CharacterRelationFactCreateDataV1, CharacterRelationFactValuesV1, CharacterRelationId,
)

CandidateRef = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,79}$")]


class CharacterBatchGenerationV1(StrictRequestModel):
    "Giữ nguyên đầu vào sinh nhân vật gốc, không được dùng cấu hình hiện tại để thay căn cứ cũ."

    basis: CandidateBasisV1
    generation_input: CoreCharactersGenerationInputV1


class CharacterRelationBatchGenerationV1(StrictRequestModel):
    "Giữ lại đầu vào sinh quan hệ gốc và các nhân vật đã chọn."

    basis: CandidateBasisV1
    generation_input: CharacterRelationsGenerationInputV1


class CharacterBatchBindingV1(StrictRequestModel):
    "Quy thuộc ban đầu của nhân vật mới; chuyển quy thuộc chính của nhân vật đã có vẫn dùng giao diện chuyên dụng cũ."

    faction_id: str = Field(pattern=r"^fac_[0-9]{6,19}$")
    faction_version: FactVersion
    membership_type: Literal["primary", "secondary", "covert"]
    role_title: str | None = Field(default=None, max_length=100)
    public_status: str | None = Field(default=None, max_length=200)
    loyalty_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)


class CharacterBatchCandidateV1(StrictRequestModel):
    "Mỗi nhân vật luôn được lưu theo tham chiếu ổn định, không phụ thuộc chỉ mục đang chọn trên trang."

    candidate_ref: CandidateRef
    profile: CharacterFactCreateDataV1
    facts: CharacterFactValuesV1
    bindings: list[CharacterBatchBindingV1] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_actual_fields(self) -> "CharacterBatchCandidateV1":
        """不替缺失资料编造起点值。"""
        if not self.facts.model_fields_set:
            raise ValueError("Hãy giữ lại ít nhất một thông tin nhân vật đã thực sự điền")
        return self


class CharacterRelationBatchCandidateV1(StrictRequestModel):
    "Thiết kế quan hệ và trạng thái khởi điểm đã xác định được gửi riêng biệt."

    candidate_ref: CandidateRef
    profile: CharacterRelationFactCreateDataV1
    facts: CharacterRelationFactValuesV1

    @model_validator(mode="after")
    def require_actual_state(self) -> "CharacterRelationBatchCandidateV1":
        """没有关系状态时保留原稿，不补造文字。"""
        if "current_state" not in self.facts.model_fields_set:
            raise ValueError("Hãy điền trạng thái lúc bắt đầu của quan hệ này")
        return self


class CharacterFactBatchCreateV1(StrictRequestModel):
    "Chấp nhận cả loạt nhân vật trong một lần; xem trước nội bộ không cần tác giả thao tác từng nhân vật."

    position: CharacterFactPositionV1
    candidates: list[CharacterBatchCandidateV1] = Field(min_length=1, max_length=50)
    generation: CharacterBatchGenerationV1 | None = None
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def unique_candidates(self) -> "CharacterFactBatchCreateV1":
        """重复引用无法准确恢复原请求，进入事务前即拒绝。"""
        refs = [row.candidate_ref for row in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("Tham chiếu ứng viên nhân vật không được trùng lặp")
        return self


class CharacterRelationFactBatchCreateV1(StrictRequestModel):
    "Áp dụng cả loạt quan hệ trong một lần; ghi đề nội dung đã có vẫn đi qua giao diện so sánh và xác nhận cũ."

    position: CharacterFactPositionV1
    candidates: list[CharacterRelationBatchCandidateV1] = Field(min_length=1, max_length=500)
    generation: CharacterRelationBatchGenerationV1 | None = None
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def unique_candidates(self) -> "CharacterRelationFactBatchCreateV1":
        """整批关系保留一一对应的身份。"""
        refs = [row.candidate_ref for row in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("Tham chiếu ứng viên quan hệ không được trùng lặp")
        return self


class CharacterBatchSavedV1(StrictResponseModel):
    "Kết quả lưu chỉ trả về danh tính và phiên bản cần cho việc làm mới và định vị."

    candidate_ref: CandidateRef
    entity_id: ObjectIdString
    character_id: CharacterId
    version: FactVersion
    history_id: ObjectIdString


class CharacterBatchBindingSavedV1(StrictResponseModel):
    "Kết quả liên kết trỏ về danh sách gốc qua tham chiếu ứng viên nhân vật."

    candidate_ref: CandidateRef
    binding_id: str = Field(pattern=r"^cfb_[0-9]{6,19}$")
    version: FactVersion


class CharacterFactBatchResultV1(StrictResponseModel):
    "Kết quả bất biến của lần lưu đầu tiên cho cả lô nhân vật."

    novel_id: ObjectIdString
    characters: list[CharacterBatchSavedV1] = Field(min_length=1, max_length=50)
    bindings: list[CharacterBatchBindingSavedV1] = Field(max_length=1000)


class CharacterRelationBatchSavedV1(StrictResponseModel):
    "Danh tính ổn định của quan hệ và bản ghi khởi điểm."

    candidate_ref: CandidateRef
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    version: FactVersion
    history_id: ObjectIdString


class CharacterRelationFactBatchResultV1(StrictResponseModel):
    "Kết quả bất biến của lần lưu đầu tiên cho cả lô quan hệ."

    novel_id: ObjectIdString
    relations: list[CharacterRelationBatchSavedV1] = Field(min_length=1, max_length=500)
