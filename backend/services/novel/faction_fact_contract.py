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
            raise ValueError("势力事实值不能为 null；未知须单独表示")
        if self.resources is not None and len(self.resources) != len(set(self.resources)):
            raise ValueError("resources 不能重复")
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
            raise ValueError("势力名称不能为空")
        if (self.level_type == "core") != (self.volume_id is None):
            raise ValueError("核心势力无归属卷，卷内或局部势力必须指定归属卷")
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
            raise ValueError("同一势力字段不能同时已知和未知")
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
            raise ValueError("势力事实必须保存从本书到位置锚的完整父链")
        fields = self.after.model_fields_set
        if (not fields or fields != self.before.values.model_fields_set | self.before.unknown.keys()
                or fields != self.previous.keys() or fields != self.validity.keys()
                or not self.replaces.keys() <= fields or not self.resolves.keys() <= fields):
            raise ValueError("势力记录前后值、前值依据及有效性的字段集合不一致")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("已知前值须有来源，未知前值的 previous 必须为 null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1 or self.before.values.model_fields_set
                    or set(self.before.unknown.values()) != {"nonexistent"} or self.replaces or self.resolves):
                raise ValueError("新建势力起点必须使用真实版本 1 和不存在的 before")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("已有势力一次确认只能增加一个真实版本")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("势力起点命令不能保存成章后变化")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("势力章后变化命令必须保存变化记录")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("势力人工起点必须使用作者说明")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("势力章后变化必须有章后位置和原文证据")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("势力变化证据必须来自生效章节")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("势力初始更正只能作用于书初")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("势力替代必须明确原记录")
        references = [*self.previous.values(), *self.replaces.values(),
                      *(identity for values in self.resolves.values() for identity in values)]
        if any(ObjectId(identity) == ObjectId(self.history_id) for identity in references if identity is not None):
            raise ValueError("势力事实不能引用自己作为前值或处置对象")
        for identities in self.resolves.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("解除势力事实失效须列出不重复的原记录")
        for state in self.validity.values():
            if state.state == "replaced" and ObjectId(state.by_history_id) == ObjectId(self.history_id):
                raise ValueError("势力事实不能被自己替代")
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
            raise ValueError("读取必须明确每个势力字段已知或未知")
        if (self.origins.keys() != known or self.blockers.keys() != {
                name for name, reason in self.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}
        }):
            raise ValueError("已知势力值须有来源，待复核不能带可用值")
        if "nonexistent" in self.unknown.values():
            raise ValueError("现存势力的读取结果不能声明目标不存在")
        claimed = known | {name for name, reason in self.unknown.items() if reason != "unclaimed"}
        if set(self.claimed_fields) != claimed or len(self.claimed_fields) != len(claimed):
            raise ValueError("势力认领字段不能重复，且须与已知值或未知原因一致")
        for identities in self.blockers.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("势力事实阻断须列出不重复的原记录")
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
            raise ValueError("势力读取的选择或实际身份重复、不一致")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("势力读取摘要与原内容不一致")
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
            raise ValueError("新建势力必须明确确认身份不存在")
        return data

    @model_validator(mode="after")
    def validate_name(self) -> "FactionFactNewTargetV1":
        """冻结名称沿用旧势力的 NFKC 名称规则，事实原文不参与。"""
        name = unicodedata.normalize("NFKC", self.candidate.name).strip()
        if self.candidate.name != name or self.normalized_name != name.casefold():
            raise ValueError("新势力名称与活动唯一键不一致")
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
            raise ValueError("势力预览字段不能重复")
        if value.operation != "create" and (not value.replaces.keys() <= set(value.fields)
                or not value.resolves.keys() <= set(value.fields)):
            raise ValueError("势力处置必须属于所选字段")
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
            raise ValueError("势力预览字段、前值及处置不一致")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("势力已知前值须有来源，未知 previous 必须为空")
        required = {name for name, reason in self.before.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}}
        if self.blockers.keys() != required or any(not ids or len(ids) != len({ObjectId(i) for i in ids}) for ids in self.blockers.values()):
            raise ValueError("势力预览须保留具体阻断记录")
        if (self.operation == "create") != (self.target.kind == "new"):
            raise ValueError("势力新建与已有目标不能混用")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("势力起点操作必须使用起点类型")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("势力变化操作必须使用变化类型")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("势力起点必须有作者说明")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("势力变化必须有章后证据")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("势力引文必须来自生效章节")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("势力初始更正只能作用书初")
        kinds = ["novel"] if self.position.intent == "book_start" else ["novel", "volume"] if self.position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
        if ([r.resource_type for r in self.protected_sources] != kinds
                or ObjectId(self.protected_sources[0].id) != ObjectId(self.target.novel_id)
                or ObjectId(self.protected_sources[-1].id) != ObjectId(self.position.target_id)
                or any(ObjectId(r.parent_id) != ObjectId(self.protected_sources[i - 1].id) for i, r in enumerate(self.protected_sources) if i)):
            raise ValueError("势力预览必须冻结完整位置父链")
        targets = {r.history_id: r for r in self.targets}
        requested = set(self.void_targets.values()) | set(self.replaces.values()) | {i for ids in self.resolves.values() for i in ids}
        if targets.keys() != requested or len(targets) != len(self.targets):
            raise ValueError("势力处置快照必须精确对应所选记录")
        if self.operation == "void":
            if self.void_targets.keys() != fields or self.replaces or self.resolves:
                raise ValueError("作废必须逐字段选择原记录")
            for name, identity in self.void_targets.items():
                row = targets[identity]
                if (name not in row.after.model_fields_set or row.validity[name].state != "active"
                        or row.position != self.position or row.kind != self.kind or row.source != self.source):
                    raise ValueError("作废目标须为同位置、同来源的原活动字段")
        elif self.void_targets:
            raise ValueError("非作废不能携带作废目标")
        for name, identity in self.replaces.items():
            row = targets[identity]
            if (name not in row.after.model_fields_set or row.validity[name].state != "active"
                    or row.position != self.position or row.kind != self.kind):
                raise ValueError("替代须明确同位置同类型的原活动字段")
        for name, identities in self.resolves.items():
            if (not identities or len(identities) != len({ObjectId(i) for i in identities})
                    or not set(identities) <= set(self.blockers.get(name, []))
                    or any(name not in targets[i].after.model_fields_set for i in identities)):
                raise ValueError("解除对象须来自该字段明确列出的阻断")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("势力替代必须明确原记录")
        sources = {r.history_id: r for r in self.field_sources}
        expected_sources = {i for i in self.previous.values() if i is not None} | {i for ids in self.blockers.values() for i in ids}
        if sources.keys() != expected_sources or len(sources) != len(self.field_sources):
            raise ValueError("势力前值及阻断快照不完整")
        for name in fields:
            for identity in ([self.previous[name]] if self.previous[name] is not None else []) + self.blockers.get(name, []):
                if name not in sources[identity].after.model_fields_set:
                    raise ValueError("势力前值来源缺少对应字段")
            if self.previous[name] is not None and getattr(self.before.values, name) != getattr(sources[self.previous[name]].after, name):
                raise ValueError("势力前值与原记录不同")
        if self.target.kind == "new":
            if (self.before.values.model_fields_set or set(self.before.unknown.values()) != {"nonexistent"}
                    or self.targets or self.field_sources or self.legacy_sources):
                raise ValueError("新势力不能伪造旧原文或已知前值")
        else:
            profile_keys, state_keys = faction_legacy_fields(fields)
            if not self.legacy_sources or self.legacy_sources[0].kind != "profile":
                raise ValueError("已有势力必须冻结主档旧原文")
            profile = self.legacy_sources[0]
            if (ObjectId(profile.entity_id) != ObjectId(self.target.entity_id) or profile.faction_id != self.target.faction_id
                    or profile.version != self.target.version or not profile.raw.model_fields_set <= profile_keys):
                raise ValueError("势力主档旧原文的身份、版本或字段不一致")
            state_ids, volumes = [], {}
            for state in self.legacy_sources[1:]:
                if (not state_keys or state.kind != "volume_state" or state.faction_id != self.target.faction_id
                        or not state.raw.model_fields_set <= state_keys):
                    raise ValueError("势力卷旧原文包含无关身份或字段")
                state_ids.append(ObjectId(state.state_id))
                volume_id = ObjectId(state.volume_id)
                if volume_id in volumes and volumes[volume_id] != state.volume:
                    raise ValueError("同卷旧资料快照不能矛盾")
                volumes[volume_id] = state.volume
            if state_ids != sorted(set(state_ids)):
                raise ValueError("势力卷原文须按唯一物理身份排序")
        refs = [(r.entity_type, r.entity_id) for r in self.references]
        observed_refs = [(r.reference.entity_type, r.reference.entity_id) for r in self.reference_reads]
        if len(refs) != len(set(refs)) or len(observed_refs) != len(set(observed_refs)) or set(refs) != set(observed_refs):
            raise ValueError("势力人工引用须对应唯一实际身份及版本")
        observations, snapshots = {}, {}
        for read in self.reads:
            if read.novel_id != self.target.novel_id:
                raise ValueError("势力预览读取不能跨书")
            if self.target.kind == "new":
                if read.faction_ids or read.identities or read.history:
                    raise ValueError("新势力预览必须保留空身份读取")
            elif (read.faction_ids != [self.target.faction_id] or [r.model_dump() for r in read.identities] != [{
                    "entity_id": self.target.entity_id, "faction_id": self.target.faction_id, "name": self.target.name, "is_deleted": False}]):
                raise ValueError("势力预览与原读取身份不一致")
            for row in read.history:
                if observations.setdefault(row.history_id, row) != row:
                    raise ValueError("势力历史观察不能矛盾")
        for row in [*self.targets, *self.field_sources]:
            observation = observations.get(row.history_id)
            if (row.novel_id != self.target.novel_id or row.entity_id != self.target.entity_id
                    or self.target.kind != "existing" or row.faction_id != self.target.faction_id
                    or snapshots.setdefault(row.history_id, row) != row or observation is None
                    or observation.entity_id != row.entity_id or observation.validity != row.validity
                    or observation.immutable_fingerprint != canonical_request_hash(row.model_dump(exclude={"validity"}, exclude_unset=True))):
                raise ValueError("势力原值和处置快照须精确绑定原读取")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"}, exclude_unset=True)) != self.fingerprint:
            raise ValueError("势力预览摘要与原内容不一致")
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
            raise ValueError("请填写作废原因")
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
            raise ValueError("势力确认动作与原预览不同")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("势力确认版本与原预览不同")
        if command.operation == "void":
            if command.targets != basis.void_targets:
                raise ValueError("势力作废目标与原预览不同")
        elif command.after.model_fields_set != set(basis.fields):
            raise ValueError("势力确认值须精确对应原预览字段")
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
                raise ValueError("新势力成功必须使用真实版本一")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("势力成功结果必须推进一个版本")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("只有势力作废不产生新事实记录")
        if self.record is not None:
            for key in ("operation", "novel_id", "entity_id", "faction_id", "faction_name", "before_version", "after_version", "confirmed_at"):
                if getattr(self, key) != getattr(self.record, key):
                    raise ValueError("势力结果与原记录身份、版本或时间不一致")
            if any(state.state != "active" for state in self.record.validity.values()):
                raise ValueError("势力首次成功记录必须保留当时活动状态")
        keys = [(ObjectId(r.history_id), r.field) for r in self.validity_changes]
        if len(keys) != len(set(keys)):
            raise ValueError("势力字段不能在一次命令里重复处置")
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
            raise ValueError("势力回执的身份、动作、时间或来源与原请求不同")
        if canonical_request_hash(self.request.model_dump(exclude_unset=True)) != self.request_hash:
            raise ValueError("势力回执的原请求摘要不一致")
        if basis.target.kind == "existing" and (result.faction_id != basis.target.faction_id
                or result.faction_name != basis.target.name or result.before_version != basis.target.version):
            raise ValueError("势力回执必须保留原目标和版本")
        if basis.target.kind == "new" and result.faction_name != basis.target.candidate.name:
            raise ValueError("新势力结果名称必须来自冻结候选")
        if result.record is not None:
            row = result.record
            if (any(getattr(row, key) != getattr(basis, key) for key in (
                    "kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources"))
                    or row.after != command.after):
                raise ValueError("势力成功记录必须对应原预览和作者确认值")
            expected = {(identity, name, "replaced", row.history_id) for name, identity in basis.replaces.items()}
        else:
            expected = {(identity, name, "voided", self.idempotency_key_hash) for name, identity in command.targets.items()}
        actual = {(r.history_id, r.field, r.after.state, r.after.by_history_id if r.after.state == "replaced" else r.after.by_receipt_key_hash)
                  for r in result.validity_changes}
        if actual != expected:
            raise ValueError("势力回执处置结果与原请求不同")
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
        raise ValueError("势力事实必须保留 BSON 身份和确认时间")
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
        raise ValueError("势力回执必须保存 BSON 身份和时间")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("势力回执摘要必须对应原请求")
    payload = {key: value for key, value in document.items() if key != "_id"}
    payload.update(receipt_id=str(document["_id"]), novel_id=str(document["novel_id"]))
    FactionFactReceiptV1.model_validate(payload)
    return deepcopy(document["result"])
