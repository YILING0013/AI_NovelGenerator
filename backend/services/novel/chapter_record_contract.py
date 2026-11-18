"""章后确认记录的输入；本模块不保存事件或修改实体。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from backend.api.contracts import (
    ObjectIdString, StrictRequestModel, StrictResponseModel, is_business_id,
    is_object_id,
)
from backend.services.novel.chapter_revision_contract import ChapterRevisionReadV1
from backend.services.llm.candidate_contract import CandidateBasisV1


class ChapterRecordEvidenceV1(StrictRequestModel):
    "Bản chỉnh sửa chương bất biến và nguyên văn do tác giả chọn, start tính từ 0 theo mã Unicode code point."

    # 引文的空白和换行也是正文，不能套用普通表单的 strip。
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    chapter_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    revision_id: ObjectIdString
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí theo code point Unicode; JavaScript phải dùng Array.from(content), không được dùng vị trí kiểu UTF-16.")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterRecordEntityRefV1(StrictRequestModel):
    "Thực thể liên quan chỉ dùng danh mục hiện có và ID ổn định; việc thuộc cùng một cuốn sách vẫn phải được dịch vụ lưu xác minh."

    entity_type: Literal[
        "character", "faction", "character_relation", "faction_relation",
        "character_faction_binding", "item", "location", "world_rule",
        "character_volume_state", "faction_volume_state",
    ]
    entity_id: str

    @model_validator(mode="after")
    def validate_identity(self) -> "ChapterRecordEntityRefV1":
        """按真实实体类别检查 ID，拒绝名称或另一类实体的 ID。

        Args:
            无。
        Returns:
            类别与 ID 匹配的引用；尚未证明该实体在本书存在。
        """
        valid = (is_object_id(self.entity_id) if self.entity_type.endswith("_volume_state")
                 else is_business_id(self.entity_type, self.entity_id))
        if not valid:
            raise ValueError("ID và loại thực thể liên quan không nhất quán")
        return self


class ChapterEventConfirmV1(StrictRequestModel):
    "Đầu vào cố định để tác giả xác nhận sự kiện đã xảy ra; không nhận kế hoạch, trạng thái mô hình hay patch tùy ý."

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class ChapterReportConfirmV1(StrictRequestModel):
    "Bổ sung báo cáo trong cùng chương; phiên bản kỳ vọng đầu tiên bằng 0, các lần sau gắn với phiên bản báo cáo tác giả đã đọc."

    expected_report_version: int = Field(ge=0, le=2**63 - 2)
    summary: str = Field(min_length=1, max_length=12000)
    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list, max_length=50)
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class ChapterEventReadV1(StrictResponseModel):
    "Các trường công khai của sự kiện bất biến, không gồm rào chṙn cơ sở dữ liệu hay khóa yêu cầu."

    event_id: ObjectIdString
    novel_id: ObjectIdString
    title: str
    content: str
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1]
    confirmed_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    needs_review: bool


class ChapterReportReadV1(StrictResponseModel):
    "Mỗi bản báo cáo giữ danh tính, nguồn và thời gian xác nhận riêng."

    report_id: ObjectIdString
    novel_id: ObjectIdString
    chapter_id: ObjectIdString
    report_version: int = Field(ge=1)
    previous_report_id: ObjectIdString | None
    summary: str
    issues: list[str]
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1]
    confirmed_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    needs_review: bool


class ChapterRecordVoidV1(StrictRequestModel):
    "Vô hiệu hóa một chiều, không sửa nội dung gốc và không hoàn tác thay đổi thực thể."

    reason: str = Field(min_length=1, max_length=1000)


class ChapterPsychologicalStateConfirmV1(StrictRequestModel):
    "Xác nhận minh thị trạng thái tâm lý thực tế của nhân vật trong quyển này; không nhận kế hoạch hay sửa đổi tùy ý."

    state_id: ObjectIdString
    expected_version: int = Field(ge=1, le=2**63 - 2)
    psychological_state: str = Field(max_length=1000)
    evidence: ChapterRecordEvidenceV1


class ChapterPsychologicalValuesV1(StrictResponseModel):
    "Trường được phép duy nhất thực sự được sửa."

    psychological_state: str = Field(max_length=1000)


class EntityStateHistoryReadV1(StrictResponseModel):
    "Giá trị trước/sau của cập nhật domain thật; khoảng trống phiên bản do chỉnh sửa thường được phép giữ."

    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["character_volume_state"]
    entity_id: ObjectIdString
    character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    volume_id: ObjectIdString
    before_version: int = Field(ge=1)
    after_version: int = Field(ge=2)
    before: ChapterPsychologicalValuesV1
    after: ChapterPsychologicalValuesV1
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool


class ChapterPsychologicalStateResultV1(StrictResponseModel):
    "Phản hồi thành công gốc; khi không có thay đổi thì chỉ giữ biên nhận, không bịa lịch sử trạng thái."

    novel_id: ObjectIdString
    state_id: ObjectIdString
    state_version: int = Field(ge=1)
    psychological_state: str = Field(max_length=1000)
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool
    history: EntityStateHistoryReadV1 | None


class ChapterItemOwnerConfirmV1(StrictRequestModel):
    "Người giữ vật phẩm A→B được cố định khi xác nhận kiểm tra; chỉ được cập nhật trường người giữ."

    item_id: str = Field(pattern=r"^item_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)
    from_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    to_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    evidence: ChapterRecordEvidenceV1
    basis: CandidateBasisV1

    @model_validator(mode="after")
    def require_different_holders(self) -> "ChapterItemOwnerConfirmV1":
        """拒绝持有人未改变的请求。

        Args:
            无。
        Returns:
            两个持有人不同的确认输入。
        """
        if self.from_character_id == self.to_character_id:
            raise ValueError("Vui lòng chọn một người nắm giữ mới khác")
        return self


class ChapterItemOwnerValuesV1(StrictResponseModel):
    "Trường vật phẩm duy nhất thực sự được sửa trong lần này."

    owner_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")


class ItemStateHistoryReadV1(StrictResponseModel):
    "Thay đổi người giữ thực tế của vật phẩm toàn sách; không thêm trường đặc thù của trạng thái quyển nhân vật."

    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["item"]
    entity_id: ObjectIdString
    item_id: str = Field(pattern=r"^item_[0-9]{6,19}$")
    before_version: int = Field(ge=1)
    after_version: int = Field(ge=2)
    before: ChapterItemOwnerValuesV1
    after: ChapterItemOwnerValuesV1
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool


class ChapterCharacterRelationStateConfirmV1(StrictRequestModel):
    "Tác giả xác nhận trạng thái hiện tại của quan hệ đã có, định danh và đầu cuối giữ theo căn cứ kiểm tra gốc."

    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)
    current_state: str = Field(min_length=1, max_length=2000)
    evidence: ChapterRecordEvidenceV1
    basis: CandidateBasisV1


class ChapterCharacterRelationStateValuesV1(StrictResponseModel):
    "Giữ nguyên giá trị gốc của trạng thái quan hệ, không trim hay chuẩn hóa Unicode với dữ liệu lịch sử."

    current_state: str = Field(min_length=1, max_length=2000)


class CharacterRelationStateHistoryReadV1(StrictResponseModel):
    "Thay đổi trạng thái thật của quan hệ nhân vật toàn sách; đóng băng định danh vật lý gốc và hai đầu cuối."

    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["character_relation"]
    entity_id: ObjectIdString
    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    source_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    target_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    before_version: int = Field(ge=1)
    after_version: int = Field(ge=2)
    before: ChapterCharacterRelationStateValuesV1
    after: ChapterCharacterRelationStateValuesV1
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool


ChapterStateHistoryReadV1 = Annotated[
    EntityStateHistoryReadV1 | ItemStateHistoryReadV1 | CharacterRelationStateHistoryReadV1,
    Field(discriminator="entity_type"),
]


class ChapterItemOwnerResultV1(StrictResponseModel):
    "Phản hồi thành công gốc giữ phiên bản thực tế và lịch sử thay đổi; phát lại không ghi đề vật phẩm hiện tại."

    novel_id: ObjectIdString
    item_id: str = Field(pattern=r"^item_[0-9]{6,19}$")
    item_version: int = Field(ge=2)
    owner_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool
    history: ItemStateHistoryReadV1


class ChapterCharacterRelationStateResultV1(StrictResponseModel):
    "Dù không thay đổi vẫn giữ định danh quan hệ và hai đầu cuối gốc; biên nhận không bị các lượt xóa hoặc sửa về sau thay thế."

    novel_id: ObjectIdString
    entity_id: ObjectIdString
    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    source_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    target_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    relation_version: int = Field(ge=1)
    current_state: str = Field(min_length=1, max_length=2000)
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool
    history: CharacterRelationStateHistoryReadV1 | None


class ChapterRecordDeleteCountsV1(StrictRequestModel):
    "Xóa toàn sách phải được phê duyệt minh thị với đầy đủ số lượng, gồm biên nhận đã hủy, bản cũ và không thay đổi."

    events: int = Field(ge=0)
    chapter_reports: int = Field(ge=0)
    entity_state_history: int = Field(ge=0)
    chapter_record_confirmation_receipts: int = Field(ge=0)
    report_heads: int = Field(ge=0)


class ChapterReportHeadReadV1(StrictResponseModel):
    "Đầu báo cáo hiện hành vẫn chiếm phiên bản; sau khi hủy không coi báo cáo cũ là báo cáo hiện hành."

    chapter_id: ObjectIdString
    report_version: int = Field(ge=0)
    report_id: ObjectIdString | None
    report: ChapterReportReadV1 | None


class ChapterRecordSourceReadV1(StrictResponseModel):
    "Chỉ đọc bản chỉnh sửa gốc và vị trí thu hồi hiện tại; không thay đổi bản ghi cùng biên nhận thành công gốc."

    revision: ChapterRevisionReadV1
    deleted_sources: list[Literal["novel", "volume", "arc", "scene", "chapter"]]


def serialize_chapter_record(document: dict, kind: Literal["event", "report", "history"]) -> dict:
    """过滤内部来源父链和护栏，生成严格公开响应。

    Args:
        document: 已补充动态 needs_review 的 BSON 记录。
        kind: 事件、报告或实际变化历史。
    Returns:
        仅包含公开字段的严格响应。
    """
    model = {"event": ChapterEventReadV1, "report": ChapterReportReadV1, "history": EntityStateHistoryReadV1}[kind]
    if kind == "history" and document["entity_type"] == "item":
        model = ItemStateHistoryReadV1
    elif kind == "history" and document["entity_type"] == "character_relation":
        model = CharacterRelationStateHistoryReadV1
    fields = {name: document[name] for name in model.model_fields if name in document}
    fields[{"event": "event_id", "report": "report_id", "history": "history_id"}[kind]] = str(document["_id"])
    for name in ("novel_id", "chapter_id", "previous_report_id", "volume_id", "entity_id"):
        if name in fields and fields[name] is not None:
            fields[name] = str(fields[name])
    return model.model_validate(fields).model_dump()
