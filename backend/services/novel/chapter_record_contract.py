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
    """作者选定的不可变章修订和原文，start 从零按 Unicode 码点计算。"""

    # 引文的空白和换行也是正文，不能套用普通表单的 strip。
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    chapter_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    revision_id: ObjectIdString
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(ge=0, le=2**31 - 1, description="Unicode 码点下标；JavaScript 使用 Array.from(content)，不能使用 UTF-16 下标。")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterRecordEntityRefV1(StrictRequestModel):
    """相关实体仅使用现有类别和稳定 ID；同书归属仍须保存服务核验。"""

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
            raise ValueError("相关实体 ID 与类别不一致")
        return self


class ChapterEventConfirmV1(StrictRequestModel):
    """作者确认已发生事件的固定输入；不接受计划、模型状态或任意 patch。"""

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class ChapterReportConfirmV1(StrictRequestModel):
    """追加同章报告；首次期望版本为零，后续绑定作者已读报告版本。"""

    expected_report_version: int = Field(ge=0, le=2**63 - 2)
    summary: str = Field(min_length=1, max_length=12000)
    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(default_factory=list, max_length=50)
    evidence: ChapterRecordEvidenceV1
    related_entities: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class ChapterEventReadV1(StrictResponseModel):
    """不可变事件的公开字段，不包含数据库护栏或请求键。"""

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
    """每版报告保留自己的身份、来源与确认时间。"""

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
    """单向作废，不修改原内容、不撤销实体变化。"""

    reason: str = Field(min_length=1, max_length=1000)


class ChapterPsychologicalStateConfirmV1(StrictRequestModel):
    """明确确认人物本卷实际心理状态，不接收计划或任意修改。"""

    state_id: ObjectIdString
    expected_version: int = Field(ge=1, le=2**63 - 2)
    psychological_state: str = Field(max_length=1000)
    evidence: ChapterRecordEvidenceV1


class ChapterPsychologicalValuesV1(StrictResponseModel):
    """实际修改的唯一允许字段。"""

    psychological_state: str = Field(max_length=1000)


class EntityStateHistoryReadV1(StrictResponseModel):
    """真实领域更新的前后值；普通编辑造成的版本空号允许保留。"""

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
    """原成功响应；无变化只保留回执，不虚构状态历史。"""

    novel_id: ObjectIdString
    state_id: ObjectIdString
    state_version: int = Field(ge=1)
    psychological_state: str = Field(max_length=1000)
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool
    history: EntityStateHistoryReadV1 | None


class ChapterItemOwnerConfirmV1(StrictRequestModel):
    """确认检查时固定的物品持有人 A→B，只能更新持有人字段。"""

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
            raise ValueError("请选择不同的新持有人")
        return self


class ChapterItemOwnerValuesV1(StrictResponseModel):
    """本次实际修改的唯一物品字段。"""

    owner_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")


class ItemStateHistoryReadV1(StrictResponseModel):
    """全书物品的实际持有人变化，不添加人物卷状态专用字段。"""

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
    """作者确认既有关系的当前状态，身份和端点沿用原检查依据。"""

    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)
    current_state: str = Field(min_length=1, max_length=2000)
    evidence: ChapterRecordEvidenceV1
    basis: CandidateBasisV1


class ChapterCharacterRelationStateValuesV1(StrictResponseModel):
    """保留关系状态原值，不对历史执行 trim 或 Unicode 规范化。"""

    current_state: str = Field(min_length=1, max_length=2000)


class CharacterRelationStateHistoryReadV1(StrictResponseModel):
    """全书人物关系的真实状态变化，固定原物理身份和两个端点。"""

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
    """原成功响应保留实际版本与变化历史，重放不覆盖当前物品。"""

    novel_id: ObjectIdString
    item_id: str = Field(pattern=r"^item_[0-9]{6,19}$")
    item_version: int = Field(ge=2)
    owner_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    evidence: ChapterRecordEvidenceV1
    confirmed_at: datetime
    needs_review: bool
    history: ItemStateHistoryReadV1


class ChapterCharacterRelationStateResultV1(StrictResponseModel):
    """无变化也保留原关系身份和端点，回执不会被后来删除或修改替换。"""

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
    """整书删除必须明确批准的完整数量，包括作废、旧版和无变化回执。"""

    events: int = Field(ge=0)
    chapter_reports: int = Field(ge=0)
    entity_state_history: int = Field(ge=0)
    chapter_record_confirmation_receipts: int = Field(ge=0)
    report_heads: int = Field(ge=0)


class ChapterReportHeadReadV1(StrictResponseModel):
    """当前报告头仍占版本；作废后不把旧报告当作当前报告。"""

    chapter_id: ObjectIdString
    report_version: int = Field(ge=0)
    report_id: ObjectIdString | None
    report: ChapterReportReadV1 | None


class ChapterRecordSourceReadV1(StrictResponseModel):
    """只读原修订和当前回收位置，不改变记录及原成功回执。"""

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
