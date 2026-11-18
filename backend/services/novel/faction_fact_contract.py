"""势力十一字段的内部记录、读取与保存合同；尚未接产品入口。"""

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Literal, get_args
import unicodedata

from bson import ObjectId
from pydantic import ConfigDict, Field, JsonValue, RootModel, SerializerFunctionWrapHandler, model_serializer, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.faction_volume_state_pydantic import FactionId
from backend.llm.schemas.character_pydantic import _validate_bson_safe_extra
from backend.db.write_contracts import canonical_request_hash
from backend.services.novel.chapter_record_contract import ChapterRecordEntityRefV1
from backend.services.novel.character_fact_contract import (
    FactConfirmed, FactHash, FactSchemaVersion, FactTimestamp, FactVersion,
    CharacterFactAuthorSourceV1 as FactAuthorSourceV1,
    CharacterFactActiveV1 as FactActiveV1,
    CharacterFactReplacedV1 as FactReplacedV1,
    CharacterFactVoidedV1 as FactVoidedV1,
    CharacterFactDirectoryEntryV1 as FactDirectoryEntryV1,
    CharacterFactReadPositionV1 as FactReadPositionV1,
    CharacterFactReferenceReadV1 as FactReferenceReadV1,
    CharacterFactSourceObservationV1 as FactSourceObservationV1,
    CharacterFactPositionV1 as FactPositionV1,
    CharacterFactProtectedSourceV1 as FactProtectedSourceV1,
    CharacterFactSourceV1 as FactSourceV1,
    CharacterFactUnknownReason as FactUnknownReason,
    CharacterFactValidityV1 as FactValidityV1,
)


FactionFactField = Literal[
    "faction_type", "positioning", "organization_style", "core_values", "is_public",
    "actual_goal", "public_stance", "power_level", "resources", "influence_scope", "story_status",
]
FACTION_FACT_FIELDS = frozenset(get_args(FactionFactField))
FACTION_FACT_PROFILE_FIELDS = FACTION_FACT_FIELDS - {"actual_goal", "power_level", "resources", "story_status"}
FactionFactOperation = Literal["create", "establish", "correct_initial", "change", "replace", "void"]
FactionFactFields = Annotated[list[FactionFactField], Field(min_length=1, max_length=11)]


def faction_legacy_fields(fields: set[str]) -> tuple[set[str], set[str]]:
    """列出所选字段的旧原文键，不把旧目标、优势或计划自动改成事实。

    Args:
        fields: 作者选中的固定事实字段。
    Returns:
        主档和卷状态应冻结的原键集合。
    """
    profile = set(fields & FACTION_FACT_PROFILE_FIELDS)
    state = set(fields & {"public_stance", "power_level", "resources", "influence_scope"})
    if "actual_goal" in fields:
        profile.update({"core_goal", "hidden_goal"})
        state.update({"hidden_agenda", "current_goal"})
    if "resources" in fields:
        profile.add("resources_and_advantages")
    if "story_status" in fields:
        state.add("active_status")
    return profile, state


class FactionFactValuesV1(StrictRequestModel):
    """仅保留提交的已知值及原文；缺键、明确清空和未知各自独立。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)

    faction_type: str | None = Field(default=None, max_length=80)
    positioning: str | None = Field(default=None, max_length=500)
    organization_style: str | None = Field(default=None, max_length=300)
    core_values: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=6)
    is_public: bool | None = None
    actual_goal: str | None = Field(default=None, max_length=1000)
    public_stance: str | None = Field(default=None, max_length=1000)
    power_level: int | None = Field(default=None, ge=1, le=5)
    resources: list[Annotated[str, Field(min_length=1)]] | None = Field(default=None, max_length=20)
    influence_scope: str | None = Field(default=None, max_length=1000)
    story_status: Literal["active", "dormant", "dissolved"] | None = None

    @model_validator(mode="after")
    def validate_values(self) -> "FactionFactValuesV1":
        """拒绝 null 和重复资源，不整理原文、资源顺序或价值观重复项。

        Args:
            无。
        Returns:
            保留实际提交字段的严格值。
        """
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Giá trị sự kiện thế lực không được là null; trạng thái chưa biết phải được biểu thị riêng")
        if self.resources is not None and len(self.resources) != len(set(self.resources)):
            raise ValueError("resources không được trùng lặp")
        return self


    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict:
        """嵌套序列化保留缺键和明确的 false、空串、空数组。

        Args:
            handler: Pydantic 原序列化函数。
        Returns:
            仅包含实际提供字段的字典。
        """
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class FactionFactCreateDataV1(StrictResponseModel):
    """新建身份、设计和未定位资料；十一事实字段只在 after 提交。"""

    name: str = Field(min_length=1, max_length=80)
    alias: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=10)
    level_type: Literal["core", "volume", "local"] = "core"
    parent_faction_id: FactionId | None = None
    volume_id: ObjectIdString | None = None
    core_goal: str = Field(default="", max_length=500)
    hidden_goal: str = Field(default="", max_length=500)
    resources_and_advantages: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=6)
    conflict_with_mainline: str = Field(default="", max_length=600)
    expandability: str = Field(default="", max_length=500)
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=8)
    first_appearance_volume_id: str | None = Field(default=None, max_length=100)
    first_appearance_chapter_id: str | None = Field(default=None, max_length=100)
    sort_order: int | None = Field(default=None, ge=0)
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_candidate(self) -> "FactionFactCreateDataV1":
        """沿旧创建的层级和扩展数据边界检查，不向原候选补字段。"""
        if not unicodedata.normalize("NFKC", self.name).strip():
            raise ValueError("Tên thế lực không được để trống")
        if (self.level_type == "core") != (self.volume_id is None):
            raise ValueError("Thế lực cốt lõi không có quyển trực thuộc; thế lực trong quyển hoặc cục bộ phải chỉ định quyển trực thuộc")
        _validate_bson_safe_extra(self.extra)
        return self

    @model_serializer(mode="wrap")
    def serialize_present(self, handler: SerializerFunctionWrapHandler) -> dict:
        """仅冻结作者实际提交的候选字段；保留合法 null 与缺项的区别。"""
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class FactionFactBeforeV1(StrictResponseModel):
    """原值和未知原因分别保存，不从旧主档或卷状态补值。"""

    values: FactionFactValuesV1
    unknown: dict[FactionFactField, FactUnknownReason]

    @model_validator(mode="after")
    def validate_partition(self) -> "FactionFactBeforeV1":
        """核对同一字段只属于已知或未知之一。

        Args:
            无。
        Returns:
            字段不重叠的原值。
        """
        if self.values.model_fields_set & self.unknown.keys():
            raise ValueError("Cùng một trường của thế lực không thể vừa đã biết vừa chưa biết")
        return self


class FactionFactRecordV1(StrictResponseModel):
    """同一势力的一次多字段确认；作废只改变对应字段的有效性。"""

    schema_id: Literal["faction.fact"]
    schema_version: FactSchemaVersion
    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["faction"]
    entity_id: ObjectIdString
    faction_id: FactionId
    faction_name: str = Field(min_length=1, max_length=80)
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    before_version: FactVersion | None
    after_version: FactVersion
    before: FactionFactBeforeV1
    after: FactionFactValuesV1
    previous: dict[FactionFactField, ObjectIdString | None]
    replaces: dict[FactionFactField, ObjectIdString]
    resolves: dict[FactionFactField, list[ObjectIdString]]
    validity: dict[FactionFactField, FactValidityV1]
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_record(self) -> "FactionFactRecordV1":
        """核对字段集合、真实版本、来源父链及逐字段处置引用。

        Args:
            无。
        Returns:
            可供纯读取器求值的严格势力记录。
        """
        kinds = ["novel"] if self.position.intent == "book_start" else ["novel", "volume"] if self.position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
        sources = self.protected_sources
        if ([row.resource_type for row in sources] != kinds
                or ObjectId(sources[0].id) != ObjectId(self.novel_id)
                or ObjectId(sources[-1].id) != ObjectId(self.position.target_id)
                or any(ObjectId(row.parent_id) != ObjectId(sources[index - 1].id)
                       for index, row in enumerate(sources) if index)):
            raise ValueError("Sự kiện thế lực phải lưu đầy đủ chuỗi cha từ cuốn sách đến mỏ neo vị trí")
        fields = self.after.model_fields_set
        if (not fields or fields != self.before.values.model_fields_set | self.before.unknown.keys()
                or fields != self.previous.keys() or fields != self.validity.keys()
                or not self.replaces.keys() <= fields or not self.resolves.keys() <= fields):
            raise ValueError("Tập hợp trường gồm giá trị trước/sau, căn cứ giá trị trước và hiệu lực của bản ghi thế lực không nhất quán")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("Giá trị trước đã biết phải có nguồn; previous của giá trị trước chưa biết phải là null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1 or self.before.values.model_fields_set
                    or set(self.before.unknown.values()) != {"nonexistent"} or self.replaces or self.resolves):
                raise ValueError("Điểm khởi tạo thế lực mới phải dùng phiên bản thật bằng 1 và before không tồn tại")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("Mỗi lần xác nhận với thế lực đã có chỉ được tăng thêm một phiên bản thật")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("Lệnh điểm khởi tạo thế lực không được lưu thay đổi sau khi chương hoàn thành")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("Lệnh thay đổi sau chương của thế lực phải lưu bản ghi thay đổi")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("Điểm khởi tạo thủ công của thế lực phải dùng mô tả của tác giả")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("Thay đổi sau chương của thế lực phải có vị trí sau chương và bằng chứng nguyên văn")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("Bằng chứng thay đổi thế lực phải lấy từ chương đã có hiệu lực")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("Đính chính ban đầu của thế lực chỉ được áp dụng cho thời điểm đầu sách")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("Thay thế thế lực phải chỉ rõ bản ghi gốc")
        references = [*self.previous.values(), *self.replaces.values(),
                      *(identity for values in self.resolves.values() for identity in values)]
        if any(ObjectId(identity) == ObjectId(self.history_id) for identity in references if identity is not None):
            raise ValueError("Sự kiện thế lực không được tự tham chiếu làm giá trị trước hoặc đối tượng xử lý")
        for identities in self.resolves.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("Gỡ vô hiệu sự kiện thế lực phải liệt kê các bản ghi gốc không trùng lặp")
        for state in self.validity.values():
            if state.state == "replaced" and ObjectId(state.by_history_id) == ObjectId(self.history_id):
                raise ValueError("Sự kiện thế lực không được tự thay thế chính nó")
        return self


class FactionFactsAtPositionV1(StrictResponseModel):
    """一个势力在明确位置的十一字段结果，不包含设计和卷计划。"""

    entity_id: ObjectIdString
    faction_id: FactionId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion
    values: FactionFactValuesV1
    unknown: dict[FactionFactField, FactUnknownReason]
    blockers: dict[FactionFactField, list[ObjectIdString]]
    origins: dict[FactionFactField, ObjectIdString]
    claimed_fields: list[FactionFactField] = Field(max_length=11)

    @model_validator(mode="after")
    def validate_fields(self) -> "FactionFactsAtPositionV1":
        """核对已知/未知、来源、阻断和永久认领的完整分区。

        Args:
            无。
        Returns:
            每字段只表达一个结果的严格读取值。
        """
        known = self.values.model_fields_set
        if known & self.unknown.keys() or known | self.unknown.keys() != FACTION_FACT_FIELDS:
            raise ValueError("Khi đọc phải xác định rõ từng trường của thế lực là đã biết hay chưa biết")
        if (self.origins.keys() != known or self.blockers.keys() != {
                name for name, reason in self.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}
        }):
            raise ValueError("Giá trị thế lực đã biết phải có nguồn; mục chờ rà soát không được mang giá trị khả dụng")
        if "nonexistent" in self.unknown.values():
            raise ValueError("Kết quả đọc của thế lực đang tồn tại không được tuyên bố mục tiêu không tồn tại")
        claimed = known | {name for name, reason in self.unknown.items() if reason != "unclaimed"}
        if set(self.claimed_fields) != claimed or len(self.claimed_fields) != len(claimed):
            raise ValueError("Trường đăng ký nhận thế lực không được trùng lặp và phải nhất quán với giá trị đã biết hoặc lý do chưa biết")
        for identities in self.blockers.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("Các chặn của sự kiện thế lực phải liệt kê bản ghi gốc không trùng lặp")
        return self


class FactionFactIdentityReadV1(StrictResponseModel):
    """读取时的势力身份；管理状态不解释为剧情状态。"""

    entity_id: ObjectIdString
    faction_id: FactionId
    name: str = Field(min_length=1, max_length=80)
    is_deleted: bool


class FactionFactHistoryObservationV1(StrictResponseModel):
    """冻结历史原文摘要和当时逐字段有效性。"""

    history_id: ObjectIdString
    entity_id: ObjectIdString
    immutable_fingerprint: FactHash
    validity: dict[FactionFactField, FactValidityV1]


class FactionFactReadV1(StrictResponseModel):
    """明确选择及完整目录的可复验读取，空选择也保留。"""

    kind: Literal["faction_facts"]
    novel_id: ObjectIdString
    faction_ids: list[FactionId]
    position: FactReadPositionV1
    directory: list[FactDirectoryEntryV1]
    identities: list[FactionFactIdentityReadV1]
    history: list[FactionFactHistoryObservationV1]
    sources: list[FactSourceObservationV1]
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_read(self) -> "FactionFactReadV1":
        """拒绝重复身份和摘要不一致的冻结读取。"""
        if (len(self.faction_ids) != len(set(self.faction_ids))
                or len(self.identities) != len({ObjectId(row.entity_id) for row in self.identities})
                or len(self.identities) != len({row.faction_id for row in self.identities})
                or any(row.faction_id not in self.faction_ids for row in self.identities)
                or len(self.history) != len({ObjectId(row.history_id) for row in self.history})):
            raise ValueError("Lựa chọn hoặc danh tính thực tế khi đọc thế lực bị trùng lặp, không nhất quán")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("Bản tóm tắt khi đọc thế lực không nhất quán với nội dung gốc")
        return self


class FactionFactReadResultV1(StrictResponseModel):
    """内部共享读取的结果及空范围依据。"""

    novel_id: ObjectIdString
    position: FactReadPositionV1
    factions: list[FactionFactsAtPositionV1]
    missing_faction_ids: list[FactionId]
    reads: list[FactionFactReadV1] = Field(min_length=1)


class FactionFactExistingTargetV1(StrictResponseModel):
    """冻结实际势力主档身份和版本。"""

    kind: Literal["existing"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    faction_id: FactionId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion


class FactionFactNewTargetV1(StrictResponseModel):
    """只预分配物理身份；业务编号在确认事务内分配。"""

    kind: Literal["new"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    candidate: FactionFactCreateDataV1
    normalized_name: str = Field(min_length=1, max_length=80)
    entity_exists: Literal[False]
    name_matches: list[ObjectIdString] = Field(max_length=0)

    @model_validator(mode="before")
    @classmethod
    def require_absence(cls, data):
        """缺项或整数零不能代替已确认不存在。"""
        if isinstance(data, dict) and data.get("entity_exists") is not False:
            raise ValueError("Tạo thế lực mới phải xác nhận rõ danh tính này không tồn tại")
        return data

    @model_validator(mode="after")
    def validate_name(self) -> "FactionFactNewTargetV1":
        """冻结名称沿用旧势力的 NFKC 名称规则，事实原文不参与。"""
        name = unicodedata.normalize("NFKC", self.candidate.name).strip()
        if self.candidate.name != name or self.normalized_name != name.casefold():
            raise ValueError("Tên thế lực mới không nhất quán với khóa duy nhất đang hoạt động")
        return self


FactionFactTargetV1 = Annotated[FactionFactExistingTargetV1 | FactionFactNewTargetV1, Field(discriminator="kind")]


class FactionFactPreviewExistingTargetV1(StrictResponseModel):
    """作者原先读取的身份和版本。"""

    entity_id: ObjectIdString
    faction_id: FactionId
    expected_version: FactVersion


class FactionFactPreviewNewTargetV1(StrictResponseModel):
    """新建只提供明确候选，不接受客户端分配正式身份。"""

    candidate: FactionFactCreateDataV1


class FactionFactCreatePreviewInputV1(StrictResponseModel):
    """人工新建选择起点及事实字段，缺省字段不参与确认。"""

    operation: Literal["create"]
    target: FactionFactPreviewNewTargetV1
    position: FactPositionV1
    source: FactAuthorSourceV1
    fields: FactionFactFields
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class FactionFactExistingPreviewInputV1(StrictResponseModel):
    """已有势力的起点、变化或替代预览。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    target: FactionFactPreviewExistingTargetV1
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    fields: FactionFactFields
    replaces: dict[FactionFactField, ObjectIdString] = Field(default_factory=dict)
    resolves: dict[FactionFactField, list[ObjectIdString]] = Field(default_factory=dict)
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class FactionFactVoidPreviewInputV1(StrictResponseModel):
    """作废从原记录取得位置和来源，不接受另一个章锚。"""

    operation: Literal["void"]
    target: FactionFactPreviewExistingTargetV1
    targets: dict[FactionFactField, ObjectIdString] = Field(min_length=1, max_length=11)
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class FactionFactPreviewInputV1(RootModel[Annotated[
    FactionFactCreatePreviewInputV1 | FactionFactExistingPreviewInputV1 | FactionFactVoidPreviewInputV1,
    Field(discriminator="operation"),
]]):
    """按动作区分内部预览输入，依据由服务生成。"""

    @model_validator(mode="after")
    def validate_selection(self) -> "FactionFactPreviewInputV1":
        """拒绝重复字段和跨字段处置。"""
        value = self.root
        if value.operation == "void":
            return self
        if len(value.fields) != len(set(value.fields)):
            raise ValueError("Trường xem trước thế lực không được trùng lặp")
        if value.operation != "create" and (not value.replaces.keys() <= set(value.fields)
                or not value.resolves.keys() <= set(value.fields)):
            raise ValueError("Việc xử lý thế lực phải thuộc về trường đã chọn")
        return self


class _FactionLegacySparseV1(StrictResponseModel):
    """旧原文保留缺项、null 和原空白，不补默认值。"""

    @model_serializer(mode="wrap")
    def serialize_present(self, handler: SerializerFunctionWrapHandler) -> dict:
        """只返回原记录实际存在的键。"""
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class FactionFactLegacyProfileRawV1(_FactionLegacySparseV1):
    """主档原键，目标和资源优势只是参考。"""

    faction_type: str | None = None
    positioning: str | None = None
    organization_style: str | None = None
    core_values: list[str] | None = None
    is_public: bool | None = None
    public_stance: str | None = None
    influence_scope: str | None = None
    core_goal: str | None = None
    hidden_goal: str | None = None
    resources_and_advantages: list[str] | None = None


class FactionFactLegacyStateRawV1(_FactionLegacySparseV1):
    """卷状态保留旧剧情状态键和旧计划目标键。"""

    power_level: int | None = None
    resources: list[str] | None = None
    public_stance: str | None = None
    influence_scope: str | None = None
    active_status: str | None = None
    hidden_agenda: str | None = None
    current_goal: str | None = None


class FactionFactLegacyStateNotesV1(_FactionLegacySparseV1):
    """卷起点说明不参与事实合并。"""

    start_state: str | None = None


class FactionFactLegacyVolumeV1(StrictResponseModel):
    """预览时卷的可读身份信息。"""

    title: str
    version: FactVersion
    is_deleted: bool


class FactionFactLegacyProfileSourceV1(StrictResponseModel):
    """原主档身份、版本及所选字段原文。"""

    kind: Literal["profile"]
    entity_id: ObjectIdString
    faction_id: FactionId
    version: FactVersion
    raw: FactionFactLegacyProfileRawV1


class FactionFactLegacyStateSourceV1(StrictResponseModel):
    """所有保留卷状态的所选原文，包括回收状态。"""

    kind: Literal["volume_state"]
    state_id: ObjectIdString
    faction_id: FactionId
    version: FactVersion
    is_deleted: bool
    volume_id: ObjectIdString
    volume: FactionFactLegacyVolumeV1 | None
    raw: FactionFactLegacyStateRawV1
    notes: FactionFactLegacyStateNotesV1


FactionFactLegacySourceV1 = Annotated[FactionFactLegacyProfileSourceV1 | FactionFactLegacyStateSourceV1, Field(discriminator="kind")]


class FactionFactBasisV1(StrictResponseModel):
    """作者实际预览的势力、位置、原值、原文和处置对象。"""

    schema_version: FactSchemaVersion
    operation: FactionFactOperation
    kind: Literal["start", "change"]
    target: FactionFactTargetV1
    position: FactPositionV1
    source: FactSourceV1
    fields: FactionFactFields
    before: FactionFactBeforeV1
    previous: dict[FactionFactField, ObjectIdString | None]
    replaces: dict[FactionFactField, ObjectIdString]
    resolves: dict[FactionFactField, list[ObjectIdString]]
    void_targets: dict[FactionFactField, ObjectIdString]
    targets: list[FactionFactRecordV1]
    blockers: dict[FactionFactField, list[ObjectIdString]]
    field_sources: list[FactionFactRecordV1]
    references: list[ChapterRecordEntityRefV1] = Field(max_length=50)
    reference_reads: list[FactReferenceReadV1] = Field(max_length=50)
    legacy_sources: list[FactionFactLegacySourceV1]
    reads: list[FactionFactReadV1] = Field(min_length=1, max_length=1)
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_basis(self) -> "FactionFactBasisV1":
        """核对冻结内容自洽，今日来源有效性由保存事务重读。"""
        fields = set(self.fields)
        if (len(fields) != len(self.fields) or fields != self.before.values.model_fields_set | self.before.unknown.keys()
                or fields != self.previous.keys() or not self.replaces.keys() <= fields or not self.resolves.keys() <= fields):
            raise ValueError("Trường xem trước, giá trị trước và việc xử lý của thế lực không nhất quán")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("Giá trị trước đã biết của thế lực phải có nguồn; previous chưa biết phải để trống")
        required = {name for name, reason in self.before.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}}
        if self.blockers.keys() != required or any(not ids or len(ids) != len({ObjectId(i) for i in ids}) for ids in self.blockers.values()):
            raise ValueError("Bản xem trước thế lực phải giữ lại các bản ghi chặn cụ thể")
        if (self.operation == "create") != (self.target.kind == "new"):
            raise ValueError("Không được dùng lẫn mục tiêu thế lực mới tạo và thế lực đã có")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("Thao tác điểm khởi tạo thế lực phải dùng loại khởi tạo")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("Thao tác thay đổi thế lực phải dùng loại thay đổi")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("Điểm khởi tạo thế lực phải có mô tả của tác giả")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("Thay đổi thế lực phải có bằng chứng sau chương")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("Trích dẫn của thế lực phải lấy từ chương đã có hiệu lực")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("Đính chính ban đầu của thế lực chỉ được áp dụng cho đầu sách")
        kinds = ["novel"] if self.position.intent == "book_start" else ["novel", "volume"] if self.position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
        if ([r.resource_type for r in self.protected_sources] != kinds
                or ObjectId(self.protected_sources[0].id) != ObjectId(self.target.novel_id)
                or ObjectId(self.protected_sources[-1].id) != ObjectId(self.position.target_id)
                or any(ObjectId(r.parent_id) != ObjectId(self.protected_sources[i - 1].id) for i, r in enumerate(self.protected_sources) if i)):
            raise ValueError("Bản xem trước thế lực phải đóng băng đầy đủ chuỗi cha vị trí")
        targets = {r.history_id: r for r in self.targets}
        requested = set(self.void_targets.values()) | set(self.replaces.values()) | {i for ids in self.resolves.values() for i in ids}
        if targets.keys() != requested or len(targets) != len(self.targets):
            raise ValueError("Ảnh chụp xử lý thế lực phải tương ứng chính xác với bản ghi đã chọn")
        if self.operation == "void":
            if self.void_targets.keys() != fields or self.replaces or self.resolves:
                raise ValueError("Hủy bỏ phải chọn bản ghi gốc theo từng trường")
            for name, identity in self.void_targets.items():
                row = targets[identity]
                if (name not in row.after.model_fields_set or row.validity[name].state != "active"
                        or row.position != self.position or row.kind != self.kind or row.source != self.source):
                    raise ValueError("Mục tiêu hủy bỏ phải là trường đang hoạt động gốc ở cùng vị trí và cùng nguồn")
        elif self.void_targets:
            raise ValueError("Thao tác không phải hủy bỏ không được kèm theo mục tiêu hủy bỏ")
        for name, identity in self.replaces.items():
            row = targets[identity]
            if (name not in row.after.model_fields_set or row.validity[name].state != "active"
                    or row.position != self.position or row.kind != self.kind):
                raise ValueError("Thay thế phải chỉ rõ trường đang hoạt động gốc cùng vị trí và cùng loại")
        for name, identities in self.resolves.items():
            if (not identities or len(identities) != len({ObjectId(i) for i in identities})
                    or not set(identities) <= set(self.blockers.get(name, []))
                    or any(name not in targets[i].after.model_fields_set for i in identities)):
                raise ValueError("Đối tượng gỡ phải nằm trong các chặn được liệt kê rõ của trường đó")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("Thay thế thế lực phải chỉ rõ bản ghi gốc")
        sources = {r.history_id: r for r in self.field_sources}
        expected_sources = {i for i in self.previous.values() if i is not None} | {i for ids in self.blockers.values() for i in ids}
        if sources.keys() != expected_sources or len(sources) != len(self.field_sources):
            raise ValueError("Ảnh chụp giá trị trước và các chặn của thế lực không đầy đủ")
        for name in fields:
            for identity in ([self.previous[name]] if self.previous[name] is not None else []) + self.blockers.get(name, []):
                if name not in sources[identity].after.model_fields_set:
                    raise ValueError("Nguồn giá trị trước của thế lực thiếu trường tương ứng")
            if self.previous[name] is not None and getattr(self.before.values, name) != getattr(sources[self.previous[name]].after, name):
                raise ValueError("Giá trị trước của thế lực khác với bản ghi gốc")
        if self.target.kind == "new":
            if (self.before.values.model_fields_set or set(self.before.unknown.values()) != {"nonexistent"}
                    or self.targets or self.field_sources or self.legacy_sources):
                raise ValueError("Thế lực mới không được làm giả nguyên văn cũ hoặc giá trị trước đã biết")
        else:
            profile_keys, state_keys = faction_legacy_fields(fields)
            if not self.legacy_sources or self.legacy_sources[0].kind != "profile":
                raise ValueError("Thế lực đã có phải đóng băng nguyên văn cũ trong hồ sơ chính")
            profile = self.legacy_sources[0]
            if (ObjectId(profile.entity_id) != ObjectId(self.target.entity_id) or profile.faction_id != self.target.faction_id
                    or profile.version != self.target.version or not profile.raw.model_fields_set <= profile_keys):
                raise ValueError("Danh tính, phiên bản hoặc trường của nguyên văn cũ trong hồ sơ chính thế lực không nhất quán")
            state_ids, volumes = [], {}
            for state in self.legacy_sources[1:]:
                if (not state_keys or state.kind != "volume_state" or state.faction_id != self.target.faction_id
                        or not state.raw.model_fields_set <= state_keys):
                    raise ValueError("Nguyên văn cũ theo quyển của thế lực chứa danh tính hoặc trường không liên quan")
                state_ids.append(ObjectId(state.state_id))
                volume_id = ObjectId(state.volume_id)
                if volume_id in volumes and volumes[volume_id] != state.volume:
                    raise ValueError("Ảnh chụp tài liệu cũ trong cùng quyển không được mâu thuẫn")
                volumes[volume_id] = state.volume
            if state_ids != sorted(set(state_ids)):
                raise ValueError("Nguyên văn theo quyển của thế lực phải sắp xếp theo danh tính vật lý duy nhất")
        refs = [(r.entity_type, r.entity_id) for r in self.references]
        observed_refs = [(r.reference.entity_type, r.reference.entity_id) for r in self.reference_reads]
        if len(refs) != len(set(refs)) or len(observed_refs) != len(set(observed_refs)) or set(refs) != set(observed_refs):
            raise ValueError("Tham chiếu thủ công của thế lực phải tương ứng với danh tính thực tế và phiên bản duy nhất")
        observations, snapshots = {}, {}
        for read in self.reads:
            if read.novel_id != self.target.novel_id:
                raise ValueError("Bản đọc xem trước thế lực không được vươn sang cuốn sách khác")
            if self.target.kind == "new":
                if read.faction_ids or read.identities or read.history:
                    raise ValueError("Bản xem trước thế lực mới phải giữ bản đọc có danh tính trống")
            elif (read.faction_ids != [self.target.faction_id] or [r.model_dump() for r in read.identities] != [{
                    "entity_id": self.target.entity_id, "faction_id": self.target.faction_id, "name": self.target.name, "is_deleted": False}]):
                raise ValueError("Danh tính trong bản xem trước thế lực không nhất quán với bản đọc gốc")
            for row in read.history:
                if observations.setdefault(row.history_id, row) != row:
                    raise ValueError("Các quan sát lịch sử của thế lực không được mâu thuẫn")
        for row in [*self.targets, *self.field_sources]:
            observation = observations.get(row.history_id)
            if (row.novel_id != self.target.novel_id or row.entity_id != self.target.entity_id
                    or self.target.kind != "existing" or row.faction_id != self.target.faction_id
                    or snapshots.setdefault(row.history_id, row) != row or observation is None
                    or observation.entity_id != row.entity_id or observation.validity != row.validity
                    or observation.immutable_fingerprint != canonical_request_hash(row.model_dump(exclude={"validity"}, exclude_unset=True))):
                raise ValueError("Giá trị gốc và ảnh chụp xử lý của thế lực phải gắn chính xác với bản đọc gốc")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"}, exclude_unset=True)) != self.fingerprint:
            raise ValueError("Tóm tắt bản xem trước thế lực không nhất quán với nội dung gốc")
        return self


class FactionFactCreateConfirmV1(StrictResponseModel):
    """作者确认新建，候选和身份只来自原依据。"""

    operation: Literal["create"]
    basis: FactionFactBasisV1
    after: FactionFactValuesV1
    confirmed: FactConfirmed


class FactionFactExistingConfirmV1(StrictResponseModel):
    """作者可改所选字段值，原身份、版本和来源保持冻结。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    basis: FactionFactBasisV1
    expected_version: FactVersion
    after: FactionFactValuesV1
    confirmed: FactConfirmed


class FactionFactVoidConfirmV1(StrictResponseModel):
    """作废只处置原活动字段，不产生假数值变化。"""

    operation: Literal["void"]
    basis: FactionFactBasisV1
    expected_version: FactVersion
    targets: dict[FactionFactField, ObjectIdString]
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def require_reason(self) -> "FactionFactVoidConfirmV1":
        """保留作者原说明，但拒绝纯空白理由。"""
        if not self.reason.strip():
            raise ValueError("Vui lòng nhập lý do hủy bỏ")
        return self


class FactionFactConfirmV1(RootModel[Annotated[
    FactionFactCreateConfirmV1 | FactionFactExistingConfirmV1 | FactionFactVoidConfirmV1,
    Field(discriminator="operation"),
]]):
    """严格区分创建、已有实体确认和作废。"""

    @model_validator(mode="after")
    def validate_command(self) -> "FactionFactConfirmV1":
        """冻结的动作、版本和字段必须与本次确认一致。"""
        command, basis = self.root, self.root.basis
        if command.operation != basis.operation:
            raise ValueError("Hành động xác nhận thế lực khác với bản xem trước gốc")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("Phiên bản xác nhận thế lực khác với bản xem trước gốc")
        if command.operation == "void":
            if command.targets != basis.void_targets:
                raise ValueError("Mục tiêu hủy bỏ thế lực khác với bản xem trước gốc")
        elif command.after.model_fields_set != set(basis.fields):
            raise ValueError("Giá trị xác nhận thế lực phải tương ứng chính xác với trường trong bản xem trước gốc")
        return self


class FactionFactValidityChangeV1(StrictResponseModel):
    """原记录单个字段的一次实际处置。"""

    history_id: ObjectIdString
    field: FactionFactField
    before: FactActiveV1
    after: Annotated[FactReplacedV1 | FactVoidedV1, Field(discriminator="state")]


class FactionFactResultV1(StrictResponseModel):
    """首次完整成功结果，重放不改成当前查询值。"""

    schema_version: FactSchemaVersion
    operation: FactionFactOperation
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    faction_id: FactionId
    faction_name: str = Field(min_length=1, max_length=80)
    before_version: FactVersion | None
    after_version: FactVersion
    record: FactionFactRecordV1 | None
    validity_changes: list[FactionFactValidityChangeV1]
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_result(self) -> "FactionFactResultV1":
        """一次命令使用一个真实主档版本，作废不制造历史行。"""
        if self.operation == "create":
            if self.before_version is not None or self.after_version != 1:
                raise ValueError("Kết quả tạo thế lực mới thành công phải dùng phiên bản thật bằng một")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("Kết quả thành công của thế lực phải tiến thêm đúng một phiên bản")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("Chỉ thao tác hủy bỏ thế lực là không tạo bản ghi sự kiện mới")
        if self.record is not None:
            for key in ("operation", "novel_id", "entity_id", "faction_id", "faction_name", "before_version", "after_version", "confirmed_at"):
                if getattr(self, key) != getattr(self.record, key):
                    raise ValueError("Danh tính, phiên bản hoặc thời gian trong kết quả thế lực không nhất quán với bản ghi gốc")
            if any(state.state != "active" for state in self.record.validity.values()):
                raise ValueError("Bản ghi thành công đầu tiên của thế lực phải giữ trạng thái hoạt động của thời điểm đó")
        keys = [(ObjectId(r.history_id), r.field) for r in self.validity_changes]
        if len(keys) != len(set(keys)):
            raise ValueError("Trường thế lực không được xử lý lặp lại trong cùng một lệnh")
        return self


class FactionFactReceiptRequestV1(StrictResponseModel):
    """参与幂等摘要的完整原请求。"""

    operation: FactionFactOperation
    novel_id: ObjectIdString
    target_id: ObjectIdString
    data: FactionFactConfirmV1


class FactionFactReceiptV1(StrictResponseModel):
    """既有回执集合内的势力 schema，原请求与原结果不可重算覆盖。"""

    schema_id: Literal["faction.fact.receipt"]
    schema_version: FactSchemaVersion
    receipt_id: ObjectIdString
    novel_id: ObjectIdString
    operation: FactionFactOperation
    idempotency_key_hash: FactHash
    request_hash: FactHash
    request: FactionFactReceiptRequestV1
    result: FactionFactResultV1
    position: FactPositionV1
    source: FactSourceV1
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    created_at: FactTimestamp

    @model_validator(mode="after")
    def validate_receipt(self) -> "FactionFactReceiptV1":
        """核对原请求、来源、结果及处置配对，不要求历史参考今天仍存在。"""
        command, result = self.request.data.root, self.result
        basis = command.basis
        if (self.operation != self.request.operation or self.operation != command.operation or self.operation != result.operation
                or self.novel_id != self.request.novel_id or self.novel_id != basis.target.novel_id or self.novel_id != result.novel_id
                or self.request.target_id != basis.target.entity_id or result.entity_id != basis.target.entity_id
                or self.position != basis.position or self.source != basis.source or self.protected_sources != basis.protected_sources
                or self.created_at != result.confirmed_at):
            raise ValueError("Danh tính, hành động, thời gian hoặc nguồn trong biên nhận thế lực khác với yêu cầu gốc")
        if canonical_request_hash(self.request.model_dump(exclude_unset=True)) != self.request_hash:
            raise ValueError("Tóm tắt yêu cầu gốc trong biên nhận thế lực không nhất quán")
        if basis.target.kind == "existing" and (result.faction_id != basis.target.faction_id
                or result.faction_name != basis.target.name or result.before_version != basis.target.version):
            raise ValueError("Biên nhận thế lực phải giữ nguyên mục tiêu và phiên bản gốc")
        if basis.target.kind == "new" and result.faction_name != basis.target.candidate.name:
            raise ValueError("Tên trong kết quả thế lực mới phải lấy từ ứng viên đã đóng băng")
        if result.record is not None:
            row = result.record
            if (any(getattr(row, key) != getattr(basis, key) for key in (
                    "kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources"))
                    or row.after != command.after):
                raise ValueError("Bản ghi thành công của thế lực phải tương ứng với bản xem trước gốc và giá trị tác giả đã xác nhận")
            expected = {(identity, name, "replaced", row.history_id) for name, identity in basis.replaces.items()}
        else:
            expected = {(identity, name, "voided", self.idempotency_key_hash) for name, identity in command.targets.items()}
        actual = {(r.history_id, r.field, r.after.state, r.after.by_history_id if r.after.state == "replaced" else r.after.by_receipt_key_hash)
                  for r in result.validity_changes}
        if actual != expected:
            raise ValueError("Kết quả xử lý trong biên nhận thế lực khác với yêu cầu gốc")
        return self


def parse_faction_fact_record(document: dict) -> dict:
    """解析原始 BSON 势力事实，保留原文、稀疏字段和时间。

    Args:
        document: 既有历史集合中的原始文档。
    Returns:
        严格公开记录；拒绝错误 BSON 身份和混合 schema。
    """
    if ("history_id" in document or any(not isinstance(document.get(key), ObjectId) for key in ("_id", "novel_id", "entity_id"))
            or not isinstance(document.get("confirmed_at"), datetime)):
        raise ValueError("Sự kiện thế lực phải giữ danh tính BSON và thời gian xác nhận")
    payload = {key: value for key, value in document.items() if key != "_id"}
    payload.update(history_id=str(document["_id"]), novel_id=str(document["novel_id"]), entity_id=str(document["entity_id"]))
    return FactionFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)


def faction_fact_record_document(record: dict) -> dict:
    """将已校验记录保存为原集合 BSON，不新增额外审计字段。

    Args:
        record: 严格公开记录。
    Returns:
        只有三个顶层身份转换为 ObjectId 的文档。
    """
    data = FactionFactRecordV1.model_validate(record).model_dump(exclude_unset=True)
    identity = ObjectId(data.pop("history_id"))
    data.update(novel_id=ObjectId(data["novel_id"]), entity_id=ObjectId(data["entity_id"]))
    return {"_id": identity, **data}


def validate_faction_fact_receipt(document: dict) -> dict:
    """核验原 BSON 回执后返回首次结果副本，不重算今日资料。

    Args:
        document: 原始回执文档。
    Returns:
        原成功 JSON 结果，错误回执明确拒绝。
    """
    if ("receipt_id" in document or not isinstance(document.get("_id"), ObjectId)
            or not isinstance(document.get("novel_id"), ObjectId) or not isinstance(document.get("created_at"), datetime)):
        raise ValueError("Biên nhận thế lực phải lưu danh tính BSON và thời gian")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("Tóm tắt biên nhận thế lực phải tương ứng với yêu cầu gốc")
    payload = {key: value for key, value in document.items() if key != "_id"}
    payload.update(receipt_id=str(document["_id"]), novel_id=str(document["novel_id"]))
    FactionFactReceiptV1.model_validate(payload)
    return deepcopy(document["result"])
