"""人物事实、人工预览及原成功回执的固定合同。"""

from copy import deepcopy
from datetime import datetime, timedelta
import re
from typing import Annotated, Literal, get_args

from bson import ObjectId
from pydantic import BeforeValidator, ConfigDict, Field, JsonValue, RootModel, field_validator, SerializerFunctionWrapHandler, model_serializer, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.character_pydantic import CharacterImportanceLevel, CharacterRoleType, _validate_bson_safe_extra
from backend.services.novel.chapter_record_contract import ChapterRecordEntityRefV1, ChapterRecordEvidenceV1


CharacterFactField = Literal[
    "gender", "age_group", "race", "identity", "appearance", "personality",
    "core_desire", "core_fear", "strengths", "weaknesses", "abilities",
    "psychological_state", "public_state", "hidden_state", "actual_goal",
]
CHARACTER_FACT_FIELDS = frozenset(get_args(CharacterFactField))
CHARACTER_FACT_SITUATION_FIELDS = frozenset({"psychological_state", "public_state", "hidden_state", "actual_goal"})
CHARACTER_FACT_PROFILE_FIELDS = CHARACTER_FACT_FIELDS - CHARACTER_FACT_SITUATION_FIELDS
CharacterFactUnknownReason = Literal[
    "nonexistent", "unclaimed", "before_start", "voided", "needs_review", "unresolved_reference",
]
CharacterFactOperation = Literal["create", "establish", "correct_initial", "change", "replace", "void"]
CharacterId = Annotated[str, Field(pattern=r"^char_[0-9]{6,19}$")]
FactHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FactVersion = Annotated[int, Field(ge=1, le=2**63 - 1)]
FactFields = Annotated[list[CharacterFactField], Field(min_length=1, max_length=15)]


def _require_schema_one(value: object) -> int:
    """各新版合同只接受整数 1，不能以布尔真冒充版本。"""
    if type(value) is not int or value != 1:
        raise ValueError("人物事实合同版本必须为整数 1")
    return value


def _require_author_confirmation(value: object) -> bool:
    """作者确认必须是布尔真，拒绝整数和字符串强转。"""
    if value is not True:
        raise ValueError("必须由作者明确确认")
    return True


def _fact_timestamp(value: object) -> datetime:
    """仅接受规范 UTC 毫秒时间或其完整 ISO 文本，保持冻结摘要稳定。"""
    if isinstance(value, str):
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?", value) is None:
            raise ValueError("人物事实时间必须是完整的规范 UTC ISO 时间")
        parsed = datetime.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("人物事实时间不能改变冻结文本")
        value = parsed
    if not isinstance(value, datetime) or value.microsecond % 1000:
        raise ValueError("人物事实时间必须是 UTC 毫秒 datetime 或规范 ISO 文本")
    if value.tzinfo is not None:
        if value.utcoffset() != timedelta(0):
            raise ValueError("人物事实时间必须使用 UTC")
        value = value.replace(tzinfo=None)
    return value


FactTimestamp = Annotated[datetime, BeforeValidator(_fact_timestamp)]
FactSchemaVersion = Annotated[Literal[1], BeforeValidator(_require_schema_one)]
FactConfirmed = Annotated[Literal[True], BeforeValidator(_require_author_confirmation)]


class CharacterFactValuesV1(StrictRequestModel):
    """只表达作者提交的已知值，不从缺省字段推断未知或清空。

    空对象可供全未知的前值结构使用，不代表一个合法确认动作。调用方使用
    model_dump(exclude_unset=True) 保留字段集合，不能按真假过滤明确的空值。
    本类型规范化输入，不用于重新解析历史原文或直接提供模型输出 Schema。
    """

    gender: str | None = Field(default=None, min_length=1, max_length=80)
    age_group: str | None = Field(default=None, min_length=1, max_length=80)
    race: str | None = Field(default=None, min_length=1, max_length=80)
    identity: str | None = Field(default=None, min_length=1, max_length=500)
    appearance: str | None = Field(default=None, min_length=1, max_length=1000)
    personality: str | None = Field(default=None, min_length=1, max_length=1000)
    core_desire: str | None = Field(default=None, min_length=1, max_length=1000)
    core_fear: str | None = Field(default=None, min_length=1, max_length=1000)
    strengths: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=12)
    weaknesses: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=12)
    abilities: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=12)
    psychological_state: str | None = Field(default=None, max_length=1000)
    public_state: str | None = Field(default=None, max_length=1000)
    hidden_state: str | None = Field(default=None, max_length=1000)
    actual_goal: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def reject_explicit_null(self) -> "CharacterFactValuesV1":
        """拒绝显式 null，保留未提交字段与空字符串/数组的区别。

        Args:
            无。
        Returns:
            仅包含严格已知值的输入模型。
        """
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("人物事实值不能为 null；未知状态须由读取依据明确表示")
        return self

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict[str, str | list[str]]:
        """嵌套返回也只保存实际字段，不能把缺省 None 变成十五个空值。"""
        return {field: value for field, value in handler(self).items() if field in self.model_fields_set}


class CharacterFactStoredValuesV1(CharacterFactValuesV1):
    """记录和冻结依据保留原字符串，不重新清理历史空白。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)


class CharacterFactPositionV1(StrictResponseModel):
    """人物资料只保存书初、卷初或章前后的稳定位置，不保存数字章号。"""

    version: FactSchemaVersion = 1
    intent: Literal["book_start", "volume_start", "chapter_before", "chapter_after"]
    target_type: Literal["novel", "volume", "chapter"]
    target_id: ObjectIdString

    @model_validator(mode="after")
    def validate_target(self) -> "CharacterFactPositionV1":
        """核对书初、卷初和章节位置的目标类别。"""
        expected = "novel" if self.intent == "book_start" else "volume" if self.intent == "volume_start" else "chapter"
        if self.target_type != expected:
            raise ValueError("故事开始时指向作品，本卷开始指向卷，章前后指向章节")
        return self


class CharacterFactReadPositionV1(StrictResponseModel):
    """共享 P1 的实际读取位置，包含空父级开始与追加。"""

    version: FactSchemaVersion = 1
    intent: Literal["book_start", "volume_start", "chapter_before", "chapter_after", "replan", "append"]
    target_type: Literal["novel", "volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    order: list[Annotated[int, Field(ge=0)]] = Field(max_length=4)

    @model_validator(mode="after")
    def validate_position(self) -> "CharacterFactReadPositionV1":
        """保持 P1 的层级深度和操作边界。"""
        allowed = ({"book_start"} if self.target_type == "novel" else
                   {"chapter_before", "chapter_after"} if self.target_type == "chapter" else
                   {"volume_start", "replan", "append"} if self.target_type == "volume" else {"replan", "append"})
        depth = {"novel": 0, "volume": 1, "arc": 2, "scene": 3, "chapter": 4}[self.target_type]
        if self.intent not in allowed or len(self.order) != depth:
            raise ValueError("读取操作或顺序深度与目标类别不一致")
        return self


class CharacterFactAuthorSourceV1(StrictResponseModel):
    """作者说明是人工起点来源，不伪造章节引文。"""

    kind: Literal["author"]
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_note(self) -> "CharacterFactAuthorSourceV1":
        """说明不能只有空白，但保留作者实际书写格式。"""
        if not self.note.strip():
            raise ValueError("请填写人工确认说明")
        return self


class CharacterFactChapterSourceV1(StrictResponseModel):
    """章后变化保留原修订及码点引文。"""

    kind: Literal["chapter"]
    evidence: ChapterRecordEvidenceV1


CharacterFactSourceV1 = Annotated[
    CharacterFactAuthorSourceV1 | CharacterFactChapterSourceV1, Field(discriminator="kind"),
]


class CharacterFactBeforeV1(StrictResponseModel):
    """已知原值和未知原因分开，未知字段绝不夹带猜测值。"""

    values: CharacterFactStoredValuesV1
    unknown: dict[CharacterFactField, CharacterFactUnknownReason]

    @model_validator(mode="after")
    def validate_partition(self) -> "CharacterFactBeforeV1":
        """同一字段只能是已知或未知之一。"""
        if self.values.model_fields_set & self.unknown.keys():
            raise ValueError("同一人物字段不能同时已知和未知")
        return self


class CharacterFactActiveV1(StrictResponseModel):
    """尚未被作者替代或作废的确认。"""

    state: Literal["active"]


class CharacterFactReplacedV1(StrictResponseModel):
    """只替代原记录的对应字段。"""

    state: Literal["replaced"]
    by_history_id: ObjectIdString


class CharacterFactVoidedV1(StrictResponseModel):
    """以原成功命令键追溯作废，不反向执行 before。"""

    state: Literal["voided"]
    by_receipt_key_hash: FactHash


CharacterFactValidityV1 = Annotated[
    CharacterFactActiveV1 | CharacterFactReplacedV1 | CharacterFactVoidedV1,
    Field(discriminator="state"),
]


class CharacterFactProtectedSourceV1(StrictResponseModel):
    """真正的位置或引文父链，供永久删除保护使用。"""

    resource_type: Literal["novel", "volume", "arc", "scene", "chapter"]
    id: ObjectIdString
    parent_id: ObjectIdString | None

    @model_validator(mode="after")
    def validate_parent(self) -> "CharacterFactProtectedSourceV1":
        """只有小说没有父级。"""
        if (self.resource_type == "novel") != (self.parent_id is None):
            raise ValueError("来源父级与层级不一致")
        return self


def _validate_protected_sources(novel_id: str, position: CharacterFactPositionV1,
                                sources: list[CharacterFactProtectedSourceV1]) -> None:
    """记录与预览共用完整锚父链核对；不访问今日目录。"""
    kinds = ["novel"] if position.intent == "book_start" else ["novel", "volume"] if position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
    if ([source.resource_type for source in sources] != kinds or sources[0].id != novel_id
            or sources[-1].id != position.target_id
            or any(source.parent_id != sources[index - 1].id for index, source in enumerate(sources) if index)):
        raise ValueError("真正来源必须保存从本书到位置锚的完整父链")


class CharacterFactRecordV1(StrictResponseModel):
    """同一人物的一次多字段确认；字段有效性以外内容不可改写。"""

    schema_id: Literal["character.fact"]
    schema_version: FactSchemaVersion
    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["character"]
    entity_id: ObjectIdString
    character_id: CharacterId
    character_name: str = Field(min_length=1, max_length=80)
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    kind: Literal["start", "change"]
    position: CharacterFactPositionV1
    source: CharacterFactSourceV1
    before_version: FactVersion | None
    after_version: FactVersion
    before: CharacterFactBeforeV1
    after: CharacterFactStoredValuesV1
    previous: dict[CharacterFactField, ObjectIdString | None]
    replaces: dict[CharacterFactField, ObjectIdString]
    resolves: dict[CharacterFactField, list[ObjectIdString]]
    validity: dict[CharacterFactField, CharacterFactValidityV1]
    protected_sources: list[CharacterFactProtectedSourceV1] = Field(min_length=1, max_length=5)
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_record(self) -> "CharacterFactRecordV1":
        """核对字段分区、真实创建版本及起点和变化的固定区别。"""
        _validate_protected_sources(self.novel_id, self.position, self.protected_sources)
        fields = self.after.model_fields_set
        if (not fields or fields != self.before.values.model_fields_set | self.before.unknown.keys()
                or fields != self.previous.keys() or fields != self.validity.keys()
                or not self.replaces.keys() <= fields or not self.resolves.keys() <= fields):
            raise ValueError("记录前后值、前值依据及有效性的字段集合不一致")
        if (any(self.previous[field] is None for field in self.before.values.model_fields_set)
                or any(self.previous[field] is not None for field in self.before.unknown)):
            raise ValueError("previous 只承载已知前值依据，未知前值必须为 null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1 or self.before.values.model_fields_set
                    or set(self.before.unknown.values()) != {"nonexistent"} or any(self.previous.values())
                    or self.replaces or self.resolves):
                raise ValueError("新建起点必须使用真实版本 1 和不存在的 before")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("已有实体一次确认只能增加一个真实版本")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("起点命令不能保存成章后变化")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("章后变化命令必须保存变化记录")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("人工起点必须使用作者说明")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("章后变化必须有章后位置和原文证据")
        if self.source.kind == "chapter" and self.source.evidence.chapter_id != self.position.target_id:
            raise ValueError("变化证据必须来自生效章节")
        if self.position.intent == "book_start" and self.position.target_id != self.novel_id:
            raise ValueError("书初锚必须属于当前小说")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("初始更正只能作用于书初")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("替代命令必须明确原记录")
        references = [*self.previous.values(), *self.replaces.values(),
                      *(identity for values in self.resolves.values() for identity in values)]
        if self.history_id in references:
            raise ValueError("人物事实不能引用自己作为前值或处置对象")
        for field, values in self.resolves.items():
            if not values or len(values) != len(set(values)):
                raise ValueError("解除失效必须列出不重复的原记录")
        for state in self.validity.values():
            if state.state == "replaced" and state.by_history_id == self.history_id:
                raise ValueError("人物事实不能被自己替代")
        return self


class CharacterFactDirectoryEntryV1(StrictResponseModel):
    """冻结 P1 的目录身份、直接父级和顺序，不带正文或统计版本。"""

    resource_type: Literal["volume", "arc", "scene", "chapter"]
    id: ObjectIdString
    parent_id: ObjectIdString
    order_index: int = Field(ge=0)


class CharacterFactIdentityReadV1(StrictResponseModel):
    """人物读取身份；无关主档版本变化不直接判事实过期。"""

    entity_id: ObjectIdString
    character_id: CharacterId
    name: str = Field(min_length=1, max_length=80)
    is_deleted: bool


class CharacterFactHistoryObservationV1(StrictResponseModel):
    """只冻结记录原文摘要和当时逐字段状态，避免重复存整段历史。"""

    history_id: ObjectIdString
    entity_id: ObjectIdString
    immutable_fingerprint: FactHash
    validity: dict[CharacterFactField, CharacterFactValidityV1]


class CharacterFactSourceObservationV1(StrictResponseModel):
    """当前正文和不可变修订都参加复验，不使用章节统计版本。"""

    chapter_id: ObjectIdString
    exists: bool
    content_hash: FactHash | None
    is_deleted: bool | None
    parents_active: bool
    revision_id: ObjectIdString | None
    revision_version: FactVersion | None
    revision_hash: FactHash | None
    revision_valid: bool

    @model_validator(mode="after")
    def validate_observation(self) -> "CharacterFactSourceObservationV1":
        """缺失来源和无引文位置锚不能伪造正文或修订。"""
        if self.exists != (self.content_hash is not None and self.is_deleted is not None):
            raise ValueError("章节存在状态与正文观察不一致")
        if not self.exists and (self.content_hash is not None or self.is_deleted is not None or self.parents_active):
            raise ValueError("缺失章节不能带正文或活动父级")
        if self.revision_id is None and (self.revision_version is not None or self.revision_hash is not None or self.revision_valid):
            raise ValueError("无修订来源不能声明修订有效")
        if self.revision_valid and (self.revision_hash is None or self.revision_version is None):
            raise ValueError("有效修订必须保存其实际版本和正文摘要")
        return self


class CharacterFactReadV1(StrictResponseModel):
    """可按原选择重新查询的事实读取依据，空查询也保留。"""

    kind: Literal["character_facts"]
    novel_id: ObjectIdString
    character_ids: list[CharacterId]
    position: CharacterFactReadPositionV1
    directory: list[CharacterFactDirectoryEntryV1]
    identities: list[CharacterFactIdentityReadV1]
    history: list[CharacterFactHistoryObservationV1]
    sources: list[CharacterFactSourceObservationV1]
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_fingerprint(self) -> "CharacterFactReadV1":
        """摘要只核对原冻结内容，不查询今天的目录或来源。"""
        if len(self.character_ids) != len(set(self.character_ids)):
            raise ValueError("人物读取选择不能重复")
        identities = {row.entity_id: row for row in self.identities}
        if (len(identities) != len(self.identities)
                or len({row.character_id for row in self.identities}) != len(self.identities)
                or any(row.character_id not in self.character_ids for row in self.identities)):
            raise ValueError("读取身份必须是不重复的原业务选择")
        if len({row.history_id for row in self.history}) != len(self.history):
            raise ValueError("读取记录观察不能重复")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("人物读取摘要与冻结内容不一致")
        return self


class CharacterFactsAtPositionV1(StrictResponseModel):
    """一个人物在指定位置的十五字段结果；来源只指确认记录。"""

    entity_id: ObjectIdString
    character_id: CharacterId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion
    values: CharacterFactStoredValuesV1
    unknown: dict[CharacterFactField, CharacterFactUnknownReason]
    blockers: dict[CharacterFactField, list[ObjectIdString]]
    origins: dict[CharacterFactField, ObjectIdString]
    claimed_fields: list[CharacterFactField] = Field(max_length=15)

    @model_validator(mode="after")
    def validate_fields(self) -> "CharacterFactsAtPositionV1":
        """已知、未知精确分区；作废不解除字段接管。"""
        known = self.values.model_fields_set
        if known & self.unknown.keys() or known | self.unknown.keys() != CHARACTER_FACT_FIELDS:
            raise ValueError("读取必须明确每个人物字段已知或未知")
        if (self.origins.keys() != known or self.blockers.keys() != {
            field for field, reason in self.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}
        }):
            raise ValueError("已知值须有来源，待复核不能带可用值")
        if len(self.claimed_fields) != len(set(self.claimed_fields)) or not known <= set(self.claimed_fields):
            raise ValueError("接管字段不重复且须包含全部已知字段")
        for field, identities in self.blockers.items():
            if self.unknown[field] not in {"voided", "needs_review", "unresolved_reference"} or not identities or len(identities) != len(set(identities)):
                raise ValueError("待复核须明确不重复的阻断记录")
        return self


class CharacterFactReadResultV1(StrictResponseModel):
    """共享读取返回值，不把缺失人物或空结果省略出依据。"""

    novel_id: ObjectIdString
    position: CharacterFactReadPositionV1
    characters: list[CharacterFactsAtPositionV1]
    missing_character_ids: list[CharacterId]
    reads: list[CharacterFactReadV1] = Field(min_length=1)


class CharacterFactCreateDataV1(StrictResponseModel):
    """新人物索引和设计资料；十五个事实字段只在 after 提交一次。"""

    name: str = Field(min_length=1, max_length=80)
    aliases: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=10)
    role_type: CharacterRoleType
    importance_level: CharacterImportanceLevel
    is_core_character: bool = False
    conflict_with_mainline: str = Field(default="", max_length=1000)
    relationship_with_protagonist: str = Field(default="", max_length=1000)
    initial_state: str = Field(default="", max_length=1000)
    growth_direction: str = Field(default="", max_length=1000)
    story_function: str = Field(default="", max_length=1000)
    arc_seed: str = Field(default="", max_length=1000)
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=10)
    sort_order: int = Field(default=0, ge=0, le=2**31 - 1)
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def validate_extra(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """沿用人物创建的 BSON 安全约束，保留实际扩展资料。"""
        return _validate_bson_safe_extra(value)

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict[str, JsonValue]:
        """HTTP 也只返回原候选字段，不能补默认值改变已冻结的摘要。"""
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class CharacterFactExistingTargetV1(StrictResponseModel):
    """已有人物必须按物理身份、业务身份和作者原版本确认。"""

    kind: Literal["existing"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    character_id: CharacterId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion


class CharacterFactNewTargetV1(StrictResponseModel):
    """新建预览不预占业务号或伪造已存在的版本。"""

    kind: Literal["new"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    normalized_name: str = Field(min_length=1, max_length=80)
    candidate: CharacterFactCreateDataV1
    entity_exists: Literal[False]
    name_matches: list[ObjectIdString] = Field(max_length=0)

    @model_validator(mode="before")
    @classmethod
    def require_actual_absence(cls, value: object) -> object:
        """新建预览必须明确确认目标和同名查询均为空。"""
        if isinstance(value, dict) and value.get("entity_exists") is not False:
            raise ValueError("新建预览必须确认物理身份不存在")
        return value


CharacterFactTargetV1 = Annotated[
    CharacterFactExistingTargetV1 | CharacterFactNewTargetV1, Field(discriminator="kind"),
]


class CharacterFactPreviewExistingTargetV1(StrictRequestModel):
    """预览请求只传正式身份和原版本，不接受客户端名称替换目标。"""

    entity_id: ObjectIdString
    character_id: CharacterId
    expected_version: FactVersion


class CharacterFactPreviewNewTargetV1(StrictRequestModel):
    """新人物预览由服务端预分配物理身份。"""

    candidate: CharacterFactCreateDataV1


class CharacterFactCreatePreviewInputV1(StrictRequestModel):
    """新建预览只选择起点及字段，尚不占用业务 ID。"""

    operation: Literal["create"]
    target: CharacterFactPreviewNewTargetV1
    position: CharacterFactPositionV1
    source: CharacterFactAuthorSourceV1
    fields: FactFields
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class CharacterFactExistingPreviewInputV1(StrictRequestModel):
    """已有实体预览明确位置、字段和原记录处置，不接受客户端依据。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    target: CharacterFactPreviewExistingTargetV1
    kind: Literal["start", "change"]
    position: CharacterFactPositionV1
    source: CharacterFactSourceV1
    fields: FactFields
    replaces: dict[CharacterFactField, ObjectIdString] = Field(default_factory=dict)
    resolves: dict[CharacterFactField, list[ObjectIdString]] = Field(default_factory=dict)
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class CharacterFactVoidPreviewInputV1(StrictRequestModel):
    """作废位置和来源由原记录决定，客户端只明确所选记录字段。"""

    operation: Literal["void"]
    target: CharacterFactPreviewExistingTargetV1
    targets: dict[CharacterFactField, ObjectIdString] = Field(min_length=1, max_length=15)
    references: list[ChapterRecordEntityRefV1] = Field(default_factory=list, max_length=50)


class CharacterFactPreviewInputV1(RootModel[Annotated[
    CharacterFactCreatePreviewInputV1 | CharacterFactExistingPreviewInputV1 | CharacterFactVoidPreviewInputV1,
    Field(discriminator="operation"),
]]):
    """人工预览输入按操作分支，冻结依据完全由服务端生成。"""

    @model_validator(mode="after")
    def validate_selection(self) -> "CharacterFactPreviewInputV1":
        """在读库前拒绝重复字段、错位操作和任意处置字段。"""
        value = self.root
        if value.operation == "void":
            return self
        fields = set(value.fields)
        if len(fields) != len(value.fields):
            raise ValueError("预览字段不能重复")
        if value.operation == "create":
            return self
        if not value.replaces.keys() <= fields or not value.resolves.keys() <= fields:
            raise ValueError("处置对象必须属于所选字段")
        if value.operation in {"establish", "correct_initial"} and value.kind != "start":
            raise ValueError("起点命令必须预览起点")
        if value.operation == "change" and value.kind != "change":
            raise ValueError("变化命令必须预览章后变化")
        if value.kind == "start" and value.source.kind != "author":
            raise ValueError("人工起点需要作者说明")
        if value.kind == "change" and (value.source.kind != "chapter" or value.position.intent != "chapter_after"):
            raise ValueError("变化预览需要章后位置和章节证据")
        if value.source.kind == "chapter" and value.source.evidence.chapter_id != value.position.target_id:
            raise ValueError("章节证据必须属于生效位置")
        if value.operation == "correct_initial" and value.position.intent != "book_start":
            raise ValueError("更正初始只能选择书初")
        if value.operation == "replace" and not value.replaces:
            raise ValueError("替代预览必须选定原记录")
        if any(not identities or len(identities) != len(set(identities)) for identities in value.resolves.values()):
            raise ValueError("解除失效必须列出不重复原记录")
        return self


class CharacterFactReferenceReadV1(StrictResponseModel):
    """人工引用冻结实际物理身份及业务版本，不仅保存可能重绑的业务号。"""

    reference: ChapterRecordEntityRefV1
    entity_id: ObjectIdString
    version: FactVersion

    @model_validator(mode="after")
    def validate_state_identity(self) -> "CharacterFactReferenceReadV1":
        """卷状态本身使用物理 ID，其引用和冻结身份必须相同。"""
        if self.reference.entity_type.endswith("_volume_state") and self.reference.entity_id != self.entity_id:
            raise ValueError("卷状态引用必须与冻结物理身份一致")
        return self


class _CharacterFactLegacySparseV1(StrictResponseModel):
    """HTTP 响应也保留旧原文的缺项，不能把默认 None 伪造为作者看过的 null。"""

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict[str, str | list[str] | None]:
        """四种稀疏 raw/notes 共用相同的缺项保留规则。"""
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class CharacterFactLegacyProfileRawV1(_CharacterFactLegacySparseV1):
    """主档保存文字只作作者参考，保留缺项、null、空值和原空白。"""

    gender: str | None = None
    age_group: str | None = None
    race: str | None = None
    identity: str | None = None
    appearance: str | None = None
    personality: str | None = None
    core_desire: str | None = None
    core_fear: str | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    abilities: list[str] | None = None


class CharacterFactLegacyProfileNotesV1(_CharacterFactLegacySparseV1):
    """主档初始状态原文不是已确定剧情时点的事实。"""

    initial_state: str | None = None


class CharacterFactLegacyStateRawV1(_CharacterFactLegacySparseV1):
    """卷状态保存文字；current_goal 保持旧计划名，不映射实际目标。"""

    psychological_state: str | None = None
    public_state: str | None = None
    hidden_state: str | None = None
    current_goal: str | None = None


class CharacterFactLegacyStateNotesV1(_CharacterFactLegacySparseV1):
    """卷起始状态原文只供作者核对。"""

    start_state: str | None = None


class CharacterFactLegacyVolumeV1(StrictResponseModel):
    """原预览时卷的可读名称、版本和回收状态。"""

    title: str
    version: FactVersion
    is_deleted: bool


class CharacterFactLegacyProfileSourceV1(StrictResponseModel):
    """每个已有人物预览都冻结同一主档身份及所选原文字段。"""

    kind: Literal["profile"]
    entity_id: ObjectIdString
    character_id: CharacterId
    version: FactVersion
    raw: CharacterFactLegacyProfileRawV1
    notes: CharacterFactLegacyProfileNotesV1


class CharacterFactLegacyStateSourceV1(StrictResponseModel):
    """卷状态原文包括回收记录，不暗示这些文字生效的位置。"""

    kind: Literal["volume_state"]
    state_id: ObjectIdString
    character_id: CharacterId
    version: FactVersion
    is_deleted: bool
    volume_id: ObjectIdString
    volume: CharacterFactLegacyVolumeV1 | None
    raw: CharacterFactLegacyStateRawV1
    notes: CharacterFactLegacyStateNotesV1


CharacterFactLegacySourceV1 = Annotated[
    CharacterFactLegacyProfileSourceV1 | CharacterFactLegacyStateSourceV1,
    Field(discriminator="kind"),
]


class CharacterFactBasisV1(StrictResponseModel):
    """作者实际预览的固定身份、位置、前值、处置对象和读取依据。"""

    schema_version: FactSchemaVersion
    operation: CharacterFactOperation
    kind: Literal["start", "change"]
    target: CharacterFactTargetV1
    position: CharacterFactPositionV1
    source: CharacterFactSourceV1
    fields: FactFields
    before: CharacterFactBeforeV1
    previous: dict[CharacterFactField, ObjectIdString | None]
    replaces: dict[CharacterFactField, ObjectIdString]
    resolves: dict[CharacterFactField, list[ObjectIdString]]
    void_targets: dict[CharacterFactField, ObjectIdString]
    targets: list[CharacterFactRecordV1]
    blockers: dict[CharacterFactField, list[ObjectIdString]]
    field_sources: list[CharacterFactRecordV1]
    references: list[ChapterRecordEntityRefV1] = Field(max_length=50)
    reference_reads: list[CharacterFactReferenceReadV1] = Field(max_length=50)
    legacy_sources: list[CharacterFactLegacySourceV1]
    reads: list[CharacterFactReadV1] = Field(min_length=1)
    protected_sources: list[CharacterFactProtectedSourceV1] = Field(min_length=1, max_length=5)
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_basis(self) -> "CharacterFactBasisV1":
        """只核冻结内容自洽；来源是否仍有效留给确认事务重读。"""
        _validate_protected_sources(self.target.novel_id, self.position, self.protected_sources)
        fields = set(self.fields)
        if (len(fields) != len(self.fields) or fields != self.before.values.model_fields_set | self.before.unknown.keys()
                or fields != self.previous.keys() or not self.replaces.keys() <= fields or not self.resolves.keys() <= fields):
            raise ValueError("预览字段、前值和处置对象不一致")
        if (any(self.previous[field] is None for field in self.before.values.model_fields_set)
                or any(self.previous[field] is not None for field in self.before.unknown)):
            raise ValueError("previous 只承载已知前值依据，未知前值必须为 null")
        required_blockers = {field for field, reason in self.before.unknown.items()
                             if reason in {"voided", "needs_review", "unresolved_reference"}}
        if self.blockers.keys() != required_blockers or any(
            not identities or len(identities) != len(set(identities)) for identities in self.blockers.values()
        ):
            raise ValueError("未知阻断必须逐字段保留不重复的原记录来源")
        field_sources = {row.history_id: row for row in self.field_sources}
        source_ids = {identity for identity in self.previous.values() if identity is not None} | {
            identity for identities in self.blockers.values() for identity in identities
        }
        if len(field_sources) != len(self.field_sources) or field_sources.keys() != source_ids or any(
            row.novel_id != self.target.novel_id or row.entity_id != self.target.entity_id for row in self.field_sources
        ):
            raise ValueError("字段来源必须精确冻结同人物前值及阻断记录")
        for field in fields:
            identities = ([self.previous[field]] if self.previous[field] is not None else []) + self.blockers.get(field, [])
            if any(field not in field_sources[identity].after.model_fields_set for identity in identities):
                raise ValueError("字段来源记录必须包含对应字段")
            if self.previous[field] is not None and getattr(self.before.values, field) != getattr(field_sources[self.previous[field]].after, field):
                raise ValueError("已知前值必须等于冻结来源字段值")
        if (self.operation == "create") != (self.target.kind == "new"):
            raise ValueError("新建与已有人物目标不能混用")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("起点预览不能声明为章后变化")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("变化命令必须预览章后变化")
        if self.operation == "create" and (self.before.values.model_fields_set
                or set(self.before.unknown.values()) != {"nonexistent"} or any(self.previous.values())
                or self.replaces or self.resolves or self.targets):
            raise ValueError("新建预览不能伪造已经存在的前值或历史")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("起点预览必须是人工来源")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("变化预览必须是有章后证据的变化")
        if self.position.intent == "book_start" and self.position.target_id != self.target.novel_id:
            raise ValueError("书初预览必须属于目标小说")
        if self.source.kind == "chapter" and self.source.evidence.chapter_id != self.position.target_id:
            raise ValueError("预览引文必须来自生效章节")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("初始更正预览只能选择书初")
        targets = {record.history_id: record for record in self.targets}
        if len(targets) != len(self.targets) or any(
            row.novel_id != self.target.novel_id or row.entity_id != self.target.entity_id for row in self.targets
        ):
            raise ValueError("处置记录必须是不重复的同书同人物记录")
        if self.operation == "void":
            if self.void_targets.keys() != fields or self.replaces or self.resolves:
                raise ValueError("作废预览必须逐字段冻结唯一目标，不能混入替代或解除")
            for field, identity in self.void_targets.items():
                row = targets.get(identity)
                if (row is None or field not in row.after.model_fields_set or row.validity[field].state != "active"
                        or row.position != self.position or row.kind != self.kind or row.source != self.source):
                    raise ValueError("作废目标必须是同位置、同类型及同来源的原活动字段")
        elif self.void_targets:
            raise ValueError("非作废预览不能携带作废目标")
        for field, identity in self.replaces.items():
            row = targets.get(identity)
            if (row is None or field not in row.after.model_fields_set or row.validity[field].state != "active"
                    or row.position != self.position or row.kind != self.kind):
                raise ValueError("替代对象必须是该位置同类型的活动字段")
        for field, identities in self.resolves.items():
            if not identities or len(identities) != len(set(identities)) or any(
                identity not in targets or field not in targets[identity].after.model_fields_set for identity in identities
            ):
                raise ValueError("解除失效必须冻结对应字段的原记录")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("替代预览必须选择原记录")
        if self.target.kind == "new":
            if self.legacy_sources:
                raise ValueError("新建人物不能夹带旧主档或卷状态")
        else:
            if not self.legacy_sources or self.legacy_sources[0].kind != "profile":
                raise ValueError("已有人物预览必须先冻结主档保存文字")
            profile = self.legacy_sources[0]
            if (ObjectId(profile.entity_id) != ObjectId(self.target.entity_id) or profile.character_id != self.target.character_id
                    or profile.version != self.target.version or not profile.raw.model_fields_set <= fields & CHARACTER_FACT_PROFILE_FIELDS):
                raise ValueError("主档原文的身份、版本和字段必须等于所选人物")
            situation_fields = fields & CHARACTER_FACT_SITUATION_FIELDS
            if not situation_fields and (profile.notes.model_fields_set or len(self.legacy_sources) != 1):
                raise ValueError("未选择处境字段时不能夹带旧初始说明或卷状态")
            state_raw_fields = (situation_fields - {"actual_goal"}) | ({"current_goal"} if "actual_goal" in fields else set())
            state_ids, volumes = [], {}
            for state in self.legacy_sources[1:]:
                if (state.kind != "volume_state" or state.character_id != self.target.character_id
                        or not state.raw.model_fields_set <= state_raw_fields):
                    raise ValueError("卷状态原文必须属于所选人物且只含所选处境字段")
                state_ids.append(ObjectId(state.state_id))
                volume_id = ObjectId(state.volume_id)
                if volume_id in volumes and volumes[volume_id] != state.volume:
                    raise ValueError("同一卷在原预览中不能保存矛盾快照")
                volumes[volume_id] = state.volume
            if state_ids != sorted(set(state_ids)):
                raise ValueError("卷状态原文必须按不重复物理身份排序")
        reference_keys = [(ref.entity_type, ref.entity_id) for ref in self.references]
        observed_keys = [(read.reference.entity_type, read.reference.entity_id) for read in self.reference_reads]
        if (len(reference_keys) != len(set(reference_keys)) or len(observed_keys) != len(set(observed_keys))
                or set(reference_keys) != set(observed_keys)):
            raise ValueError("引用依据必须逐项冻结唯一实际身份和业务版本")
        observations = {}
        for read in self.reads:
            if read.novel_id != self.target.novel_id:
                raise ValueError("预览读取不能跨小说")
            if self.target.kind == "new":
                if read.character_ids or read.identities or read.history:
                    raise ValueError("新建预览必须冻结人物尚不存在的空读取")
            else:
                expected_identity = {"entity_id": self.target.entity_id, "character_id": self.target.character_id,
                                     "name": self.target.name, "is_deleted": False}
                if read.character_ids != [self.target.character_id] or [row.model_dump() for row in read.identities] != [expected_identity]:
                    raise ValueError("预览目标必须等于原读取的活动人物身份")
            for observation in read.history:
                previous_observation = observations.setdefault(observation.history_id, observation)
                if observation != previous_observation:
                    raise ValueError("同一原读取记录不能保存矛盾观察")
        snapshots = {}
        for row in [*self.targets, *self.field_sources]:
            previous_snapshot = snapshots.setdefault(row.history_id, row)
            observation = observations.get(row.history_id)
            immutable = row.model_dump(exclude={"validity"}, exclude_unset=True)
            if (row != previous_snapshot or observation is None or observation.entity_id != row.entity_id
                    or observation.validity != row.validity
                    or canonical_request_hash(immutable) != observation.immutable_fingerprint
                    or self.target.kind != "existing" or row.character_id != self.target.character_id):
                raise ValueError("预览来源和处置快照必须精确绑定原读取的同人物记录观察")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"}, exclude_unset=True)) != self.fingerprint:
            raise ValueError("预览摘要与冻结内容不一致")
        return self


class CharacterFactPreviewV1(StrictResponseModel):
    """预览原依据和所选字段结果，不能只返回不可解释的摘要。"""

    basis: CharacterFactBasisV1
    values: CharacterFactBeforeV1

    @model_validator(mode="after")
    def validate_values(self) -> "CharacterFactPreviewV1":
        """显示给作者的原值必须就是冻结依据里的原值。"""
        if self.values != self.basis.before:
            raise ValueError("预览显示与冻结原值不一致")
        return self


class CharacterFactCreateConfirmV1(StrictRequestModel):
    """新建确认不接受旧版本或另一个创建候选。"""

    operation: Literal["create"]
    basis: CharacterFactBasisV1
    after: CharacterFactValuesV1
    confirmed: FactConfirmed


class CharacterFactExistingConfirmV1(StrictRequestModel):
    """作者可改 after 值，目标、来源和原依据始终冻结。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    basis: CharacterFactBasisV1
    expected_version: FactVersion
    after: CharacterFactValuesV1
    confirmed: FactConfirmed


class CharacterFactVoidConfirmV1(StrictRequestModel):
    """作废只选择原记录字段并说明原因，不接收 after。"""

    operation: Literal["void"]
    basis: CharacterFactBasisV1
    expected_version: FactVersion
    targets: dict[CharacterFactField, ObjectIdString]
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: FactConfirmed


class CharacterFactConfirmV1(RootModel[Annotated[
    CharacterFactCreateConfirmV1 | CharacterFactExistingConfirmV1 | CharacterFactVoidConfirmV1,
    Field(discriminator="operation"),
]]):
    """按实际动作严格区分新建、已存在实体确认和作废。"""

    @model_validator(mode="after")
    def validate_command(self) -> "CharacterFactConfirmV1":
        """确认必须使用作者预览的同一操作、字段和版本。"""
        command = self.root
        basis = command.basis
        if command.operation != basis.operation:
            raise ValueError("确认动作与原预览不一致")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("确认版本与原预览不一致")
        if command.operation == "void":
            targets = {row.history_id: row for row in basis.targets}
            if command.targets != basis.void_targets:
                raise ValueError("作废目标与原预览不一致")
            for field, identity in command.targets.items():
                row = targets.get(identity)
                if row is None or field not in row.after.model_fields_set or row.validity[field].state != "active":
                    raise ValueError("只能作废原预览中明确选定的活动字段")
        elif command.after.model_fields_set != set(basis.fields):
            raise ValueError("确认值必须精确对应原预览字段")
        return self


class CharacterFactValidityChangeV1(StrictResponseModel):
    """一次命令对原记录单个字段的实际单向处置。"""

    history_id: ObjectIdString
    field: CharacterFactField
    before: CharacterFactActiveV1
    after: Annotated[CharacterFactReplacedV1 | CharacterFactVoidedV1, Field(discriminator="state")]


class CharacterFactResultV1(StrictResponseModel):
    """首次完整成功结果；重放不能改成后来查询到的当前值。"""

    schema_version: FactSchemaVersion
    operation: CharacterFactOperation
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    character_id: CharacterId
    character_name: str = Field(min_length=1, max_length=80)
    before_version: FactVersion | None
    after_version: FactVersion
    record: CharacterFactRecordV1 | None
    validity_changes: list[CharacterFactValidityChangeV1]
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_result(self) -> "CharacterFactResultV1":
        """只有原子新建从不存在变为版本一，作废不制造变化行。"""
        if self.operation == "create":
            if self.before_version is not None or self.after_version != 1:
                raise ValueError("新建结果必须使用真实创建版本一")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("确认结果只能增加一个人物版本")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("只有作废结果没有新事实记录")
        if self.record is not None:
            for field in ("operation", "novel_id", "entity_id", "character_id", "character_name", "before_version", "after_version", "confirmed_at"):
                if getattr(self.record, field) != getattr(self, field):
                    raise ValueError("确认结果和新记录身份、版本或时间不一致")
            if any(state.state != "active" for state in self.record.validity.values()):
                raise ValueError("首次成功记录的字段必须是当时 active 快照")
        keys = [(row.history_id, row.field) for row in self.validity_changes]
        if len(keys) != len(set(keys)):
            raise ValueError("同一记录字段不能在一个命令中重复处置")
        return self


class CharacterFactReceiptRequestV1(StrictResponseModel):
    """回执保留用于幂等摘要的完整原请求外壳。"""

    operation: CharacterFactOperation
    novel_id: ObjectIdString
    target_id: ObjectIdString
    data: CharacterFactConfirmV1


class CharacterFactReceiptV1(StrictResponseModel):
    """独立于旧章后回执的严格人物事实回执。"""

    schema_id: Literal["character.fact.receipt"]
    schema_version: FactSchemaVersion
    receipt_id: ObjectIdString
    novel_id: ObjectIdString
    operation: CharacterFactOperation
    idempotency_key_hash: FactHash
    request_hash: FactHash
    request: CharacterFactReceiptRequestV1
    result: CharacterFactResultV1
    position: CharacterFactPositionV1
    source: CharacterFactSourceV1
    protected_sources: list[CharacterFactProtectedSourceV1] = Field(min_length=1, max_length=5)
    created_at: FactTimestamp

    @model_validator(mode="after")
    def validate_receipt(self) -> "CharacterFactReceiptV1":
        """核对原请求与原成功结果，不要求冻结目录成员今天仍存在。"""
        command = self.request.data.root
        basis = command.basis
        result = self.result
        if (self.operation != self.request.operation or self.operation != command.operation or self.operation != result.operation
                or self.novel_id != self.request.novel_id or self.novel_id != basis.target.novel_id or self.novel_id != result.novel_id
                or self.request.target_id != basis.target.entity_id or result.entity_id != basis.target.entity_id
                or self.position != basis.position or self.source != basis.source or self.protected_sources != basis.protected_sources):
            raise ValueError("人物事实回执的动作、身份或来源与原请求不一致")
        if canonical_request_hash(self.request.model_dump(exclude_unset=True)) != self.request_hash:
            raise ValueError("人物事实回执请求摘要不一致")
        if basis.target.kind == "existing" and (result.character_id != basis.target.character_id
                or result.character_name != basis.target.name or result.before_version != basis.target.version):
            raise ValueError("人物事实回执必须保存原目标和版本")
        if basis.target.kind == "new" and result.character_name != basis.target.candidate.name:
            raise ValueError("新建结果名称必须来自原预览候选")
        if result.record is not None:
            record = result.record
            if (record.kind != basis.kind or record.position != basis.position or record.source != basis.source
                    or record.before != basis.before or record.previous != basis.previous
                    or record.replaces != basis.replaces or record.resolves != basis.resolves
                    or record.protected_sources != basis.protected_sources
                    or record.after.model_dump(exclude_unset=True) != command.after.model_dump(exclude_unset=True)):
                raise ValueError("确认记录必须与原预览及作者 after 一致")
            expected_changes = {(identity, field, "replaced", record.history_id) for field, identity in basis.replaces.items()}
        else:
            expected_changes = {(identity, field, "voided", self.idempotency_key_hash) for field, identity in command.targets.items()}
        actual_changes = {
            (row.history_id, row.field, row.after.state,
             row.after.by_history_id if row.after.state == "replaced" else row.after.by_receipt_key_hash)
            for row in result.validity_changes
        }
        if actual_changes != expected_changes:
            raise ValueError("回执逐字段有效性结果与原处置请求不一致")
        return self


def validate_character_fact_receipt(document: dict) -> dict:
    """核验原 BSON 人物事实回执后返回原 result，不重算旧来源。

    Args:
        document: 已从回执集合读出的原 BSON 文档。
    Returns:
        首次成功保存的原结果副本；合同错误抛出 ValueError。
    """
    if (not isinstance(document.get("_id"), ObjectId) or not isinstance(document.get("novel_id"), ObjectId)
            or "receipt_id" in document):
        raise ValueError("人物事实回执必须保存 BSON 身份")
    if not isinstance(document.get("created_at"), datetime):
        raise ValueError("人物事实回执创建时间必须保存为 BSON datetime")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("人物事实回执摘要必须对应保存的原请求")
    payload = {**document, "receipt_id": str(document["_id"]), "novel_id": str(document["novel_id"])}
    del payload["_id"]
    CharacterFactReceiptV1.model_validate(payload)
    return deepcopy(document["result"])


def parse_character_fact_record(document: dict) -> dict:
    """把原 BSON 三个身份字段映射成公开记录，拒绝其他额外字段。

    Args:
        document: entity_state_history 中带精确新版标记的原 BSON 文档。
    Returns:
        保留原文、日期和稀疏字段的严格记录字典。
    """
    if "history_id" in document or any(not isinstance(document.get(field), ObjectId) for field in ("_id", "novel_id", "entity_id")):
        raise ValueError("人物事实记录必须保存唯一的 BSON 身份")
    if not isinstance(document.get("confirmed_at"), datetime):
        raise ValueError("人物事实记录确认时间必须保存为 BSON datetime")
    payload = {**document, "history_id": str(document["_id"]),
               "novel_id": str(document["novel_id"]), "entity_id": str(document["entity_id"])}
    del payload["_id"]
    return CharacterFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)


def character_fact_record_document(record: dict) -> dict:
    """将严格公开记录保存成既有集合的 BSON 形状，不添加其他审计字段。

    Args:
        record: 已完成业务核验的新版人物事实记录。
    Returns:
        _id 在首位，只有三个顶层身份转换成 ObjectId 的文档。
    """
    fields = CharacterFactRecordV1.model_validate(record).model_dump(exclude_unset=True)
    identity = ObjectId(fields.pop("history_id"))
    fields["novel_id"] = ObjectId(fields["novel_id"])
    fields["entity_id"] = ObjectId(fields["entity_id"])
    return {"_id": identity, **fields}


class CharacterFactQueryV1(StrictRequestModel):
    """人物详情按明确锚读取；省略位置时由服务端解析一次最新位置。"""

    character_ids: list[CharacterId] = Field(max_length=200)
    position: CharacterFactPositionV1 | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "CharacterFactQueryV1":
        """保留空选择，拒绝重复人物，避免显示和读取依据数量不一致。"""
        if len(self.character_ids) != len(set(self.character_ids)):
            raise ValueError("人物查询不能重复选择同一人物")
        return self
