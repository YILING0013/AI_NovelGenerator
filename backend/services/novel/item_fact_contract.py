"""物品整组事实、人工预览与成功回执的内部严格合同。"""

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Literal

from bson import ObjectId
from pydantic import Field, RootModel, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel, is_business_id
from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.item_pydantic import ItemCreateV1, LongListText, NonBlankText
from backend.llm.schemas.item_pydantic import CharacterId, FactionId, ItemId, ItemLifecycleStatus, LocationId
from backend.services.novel.character_fact_contract import (
    FactSchemaVersion, FactTimestamp, FactVersion, FactHash, FactConfirmed,
    CharacterFactReadPositionV1 as FactReadPositionV1,
    CharacterFactDirectoryEntryV1 as FactDirectoryEntryV1,
    CharacterFactSourceObservationV1 as FactSourceObservationV1,
    CharacterFactChapterSourceV1,
    CharacterFactActiveV1 as FactActiveV1,
    CharacterFactReplacedV1 as FactReplacedV1,
    CharacterFactVoidedV1 as FactVoidedV1,
    _validate_protected_sources,
    CharacterFactPositionV1 as FactPositionV1,
    CharacterFactProtectedSourceV1 as FactProtectedSourceV1,
    CharacterFactUnknownReason as FactUnknownReason,
    CharacterFactValidityV1 as FactValidityV1,
)


class FactAuthorSourceV1(StrictResponseModel):
    """物品起点由作者明确确认；补充说明可留空，不代填作者的话。"""

    kind: Literal["author"]
    note: str = Field(default="", max_length=2000)


FactSourceV1 = Annotated[FactAuthorSourceV1 | CharacterFactChapterSourceV1, Field(discriminator="kind")]


class ItemFactValuesV1(StrictResponseModel):
    """四字段必须同时提供；引用的 null 是明确无引用，不表示未知。"""

    lifecycle_status: ItemLifecycleStatus
    owner_character_id: CharacterId | None
    controlling_faction_id: FactionId | None
    current_location_id: LocationId | None

    @model_validator(mode="after")
    def validate_group(self) -> "ItemFactValuesV1":
        """沿用现有物品组合规则，不要求人物和势力互斥。

        Args:
            无。
        Returns:
            完整且合法的物品状态。
        """
        if self.lifecycle_status == "held" and self.owner_character_id is None and self.controlling_faction_id is None:
            raise ValueError("held 物品必须有持有人或控制势力")
        if self.lifecycle_status in {"destroyed", "consumed"} and any(value is not None for value in (
            self.owner_character_id, self.controlling_faction_id, self.current_location_id,
        )):
            raise ValueError("destroyed/consumed 物品不能保留持有人、控制势力或地点")
        return self


ITEM_FACT_FIELDS = frozenset({"lifecycle_status", "owner_character_id", "controlling_faction_id", "current_location_id"})
ItemFactOperation = Literal["create", "establish", "correct_initial", "change", "replace", "void"]


class ItemFactBeforeV1(StrictResponseModel):
    """整组已知或整组未知，禁止保留部分可信的物品字段。"""

    values: ItemFactValuesV1 | None
    unknown: FactUnknownReason | None

    @model_validator(mode="after")
    def validate_partition(self) -> "ItemFactBeforeV1":
        """已知值和未知原因必须二选一。

        Args:
            无。
        Returns:
            没有部分值或重复状态的物品组。
        """
        if (self.values is None) == (self.unknown is None):
            raise ValueError("物品四字段必须整组已知或整组未知")
        return self


class ItemFactRecordV1(StrictResponseModel):
    """一次物品确认只推进一个实体版本，前值和处置均指向整个组。"""

    schema_id: Literal["item.fact"]
    schema_version: FactSchemaVersion
    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["item"]
    entity_id: ObjectIdString
    item_id: ItemId
    item_name: str = Field(min_length=1, max_length=80)
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    before_version: FactVersion | None
    after_version: FactVersion
    before: ItemFactBeforeV1
    after: ItemFactValuesV1
    previous: ObjectIdString | None
    replaces: ObjectIdString | None
    resolves: list[ObjectIdString]
    validity: FactValidityV1
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_record(self) -> "ItemFactRecordV1":
        """核对来源、整组前值、记录引用和一次真实版本推进。

        Args:
            无。
        Returns:
            可交给纯求值器的内部物品记录，不授权持久写入。
        """
        kinds = ["novel"] if self.position.intent == "book_start" else ["novel", "volume"] if self.position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
        sources = self.protected_sources
        if ([row.resource_type for row in sources] != kinds
                or ObjectId(sources[0].id) != ObjectId(self.novel_id)
                or ObjectId(sources[-1].id) != ObjectId(self.position.target_id)
                or any(ObjectId(row.parent_id) != ObjectId(sources[index - 1].id)
                       for index, row in enumerate(sources) if index)):
            raise ValueError("物品事实必须保存从本书到位置锚的完整父链")
        if (self.before.values is None) != (self.previous is None):
            raise ValueError("物品已知前值须有整组来源，未知前值的 previous 必须为 null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1
                    or self.before.unknown != "nonexistent" or self.replaces is not None or self.resolves):
                raise ValueError("新建物品起点必须使用真实版本一和不存在的前值")
        else:
            if self.before_version is None or self.after_version != self.before_version + 1:
                raise ValueError("已有物品一次确认只能增加一个真实版本")
            if self.before.unknown == "nonexistent":
                raise ValueError("已有物品不能声明目标不存在")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("物品起点命令必须保存人工起点")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("物品变化命令必须保存章后变化")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("物品人工起点必须使用作者说明")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("物品章后变化必须有章后位置和原文证据")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("物品变化证据必须来自生效章节")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("物品初始更正只能作用于书初")
        if self.operation == "replace" and self.replaces is None:
            raise ValueError("物品替代必须明确原整组记录")
        if any(ObjectId(identity) == ObjectId(self.history_id)
               for identity in [self.previous, self.replaces, *self.resolves] if identity is not None):
            raise ValueError("物品事实不能引用自己作为前值或处置对象")
        if len(self.resolves) != len({ObjectId(identity) for identity in self.resolves}):
            raise ValueError("解除物品事实失效不能重复指定原记录")
        if self.validity.state == "replaced" and ObjectId(self.validity.by_history_id) == ObjectId(self.history_id):
            raise ValueError("物品事实不能被自己替代")
        return self


class ItemFactsAtPositionV1(ItemFactBeforeV1):
    """物品在明确位置的完整组，来源、阻断和认领状态也按组返回。"""

    entity_id: ObjectIdString
    item_id: ItemId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion
    origin: ObjectIdString | None
    blockers: list[ObjectIdString]
    claimed: bool

    @model_validator(mode="after")
    def validate_result(self) -> "ItemFactsAtPositionV1":
        """未知组不带部分值；作废、失效不解除认领。

        Args:
            无。
        Returns:
            来源、阻断与整组已知或未知状态相符的结果。
        """
        if (self.values is None) != (self.origin is None):
            raise ValueError("物品已知值必须有唯一整组来源")
        blocked = self.unknown in {"voided", "needs_review", "unresolved_reference"}
        if bool(self.blockers) != blocked or len(self.blockers) != len({ObjectId(identity) for identity in self.blockers}):
            raise ValueError("物品待复核或作废须列出不重复的阻断记录")
        if self.unknown == "nonexistent" or self.claimed != (self.unknown != "unclaimed"):
            raise ValueError("现存物品的认领状态必须与整组读取结果一致")
        return self


class ItemFactIdentityV1(StrictResponseModel):
    """只冻结物品身份与版本，不把裸状态当作历史。"""

    entity_id: ObjectIdString
    item_id: ItemId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion
    is_deleted: bool


class ItemFactReferenceV1(StrictResponseModel):
    """某个实际引用当时存在或缺失，保留物理身份供复验。"""

    resource_type: Literal["character", "faction", "location"]
    business_id: CharacterId | FactionId | LocationId
    entity_id: ObjectIdString | None
    version: FactVersion | None
    is_deleted: bool | None
    status: str | None
    available: bool

    @model_validator(mode="after")
    def validate_reference(self) -> "ItemFactReferenceV1":
        """缺失引用不能冒充活动实体，同类 ID 不能互换。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        if not is_business_id(self.resource_type, self.business_id):
            raise ValueError("物品引用类别与业务 ID 不一致")
        if self.entity_id is None:
            if any(value is not None for value in (self.version, self.is_deleted, self.status)) or self.available:
                raise ValueError("缺失引用不能携带实体状态")
        elif self.version is None or self.is_deleted is None or self.status is None:
            raise ValueError("存在的引用必须冻结完整身份和状态")
        if self.available and (self.is_deleted or self.status != "active"):
            raise ValueError("可用引用必须未回收且活动")
        return self


class ItemFactReferenceSelectionV1(StrictResponseModel):
    """预览时明确要使用的三类引用，null 表示本次不选该引用。"""

    owner_character_id: CharacterId | None
    controlling_faction_id: FactionId | None
    current_location_id: LocationId | None


class ItemFactReadV1(StrictResponseModel):
    """同一事务的目录、完整记录与真实引用；空选择也保存原范围。"""

    kind: Literal["item_facts"]
    novel_id: ObjectIdString
    item_ids: list[ItemId] = Field(max_length=200)
    position: FactReadPositionV1
    directory: list[FactDirectoryEntryV1]
    identities: list[ItemFactIdentityV1]
    records: list[ItemFactRecordV1]
    sources: list[FactSourceObservationV1]
    references: list[ItemFactReferenceV1]
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_read(self) -> "ItemFactReadV1":
        """验证原选择、目录父链及记录身份，不查询今天的数据库。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        identities = {row.item_id: row for row in self.identities}
        if (len(self.item_ids) != len(set(self.item_ids)) or len(identities) != len(self.identities)
                or not identities.keys() <= set(self.item_ids)
                or len({ObjectId(row.entity_id) for row in self.identities}) != len(self.identities)):
            raise ValueError("物品读取身份必须对应不重复的原选择")
        if len({ObjectId(row.history_id) for row in self.records}) != len(self.records):
            raise ValueError("物品读取不能重复历史身份")
        for row in self.records:
            target = identities.get(row.item_id)
            if (target is None or ObjectId(row.entity_id) != ObjectId(target.entity_id)
                    or ObjectId(row.novel_id) != ObjectId(self.novel_id) or row.after_version > target.version):
                raise ValueError("物品记录与原物理身份、小说或版本不一致")
        directory = {(row.resource_type, ObjectId(row.id)): row for row in self.directory}
        parents = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}
        if len(directory) != len(self.directory):
            raise ValueError("物品读取目录不能重复")
        for row in self.directory:
            kind = parents[row.resource_type]
            if (kind == "novel" and ObjectId(row.parent_id) != ObjectId(self.novel_id)
                    or kind != "novel" and (kind, ObjectId(row.parent_id)) not in directory):
                raise ValueError("物品读取目录必须是同书完整父链")
        if self.position.target_type == "novel":
            if ObjectId(self.position.target_id) != ObjectId(self.novel_id):
                raise ValueError("书初必须指向当前小说")
        else:
            row = directory.get((self.position.target_type, ObjectId(self.position.target_id)))
            if row is None:
                raise ValueError("物品读取锚必须存在于冻结目录")
            order = [row.order_index]
            while row.resource_type != "volume":
                row = directory[parents[row.resource_type], ObjectId(row.parent_id)]
                order.append(row.order_index)
            if list(reversed(order)) != self.position.order:
                raise ValueError("物品读取顺序必须来自完整目录")
        expected_refs = {(kind, getattr(values, field)) for record in self.records
                         for values in (record.before.values, record.after) if values is not None
                         for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                             ("location", "current_location_id")) if getattr(values, field) is not None}
        if (len({(r.resource_type, r.business_id) for r in self.references}) != len(self.references)
                or {(r.resource_type, r.business_id) for r in self.references} != expected_refs):
            raise ValueError("物品引用观察必须完整覆盖记录的前后值")
        expected_sources = {(ObjectId(r.source.evidence.chapter_id), ObjectId(r.source.evidence.revision_id))
                            for r in self.records if r.source.kind == "chapter"}
        if (any(s.revision_id is None for s in self.sources)
                or len({(ObjectId(s.chapter_id), ObjectId(s.revision_id)) for s in self.sources}) != len(self.sources)
                or {(ObjectId(s.chapter_id), ObjectId(s.revision_id)) for s in self.sources} != expected_sources):
            raise ValueError("物品正文观察必须完整覆盖原记录来源")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("物品读取摘要与冻结内容不一致")
        return self


class ItemFactCreateDataV1(StrictResponseModel):
    """新物品只提供设计字段，四字段事实由确认 after 单独提供。"""

    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(default_factory=list, max_length=10)
    item_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=2000)
    appearance: str = Field(default="", max_length=1000)
    origin: str = Field(default="", max_length=1000)
    abilities: list[LongListText] = Field(default_factory=list, max_length=20)
    limitations: list[LongListText] = Field(default_factory=list, max_length=20)
    costs: list[LongListText] = Field(default_factory=list, max_length=20)
    story_function: str = Field(default="", max_length=1000)
    tags: list[NonBlankText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_design(self) -> "ItemFactCreateDataV1":
        """沿用现有设计字段长度及数组唯一规则。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        ItemCreateV1.model_validate(self.model_dump())
        if not all(getattr(self, key).strip() for key in ("name", "item_type", "description")):
            raise ValueError("物品名称、类型和描述不能空白")
        return self


class ItemFactExistingTargetV1(ItemFactIdentityV1):
    """已有物品的原物理身份、业务号和编辑版本。"""

    kind: Literal["existing"]
    novel_id: ObjectIdString


class ItemFactNewTargetV1(StrictResponseModel):
    """新建只冻结待用物理 ID，不预占业务号和排序。"""

    kind: Literal["new"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    candidate: ItemFactCreateDataV1


class ItemFactPreviewTargetV1(StrictRequestModel):
    """既有预览只接受物理身份、业务 ID 与原版本。"""

    entity_id: ObjectIdString
    item_id: ItemId
    expected_version: FactVersion


class ItemFactCreatePreviewV1(StrictRequestModel):
    """作者为新物品明确选择起点。"""

    operation: Literal["create"]
    candidate: ItemFactCreateDataV1
    position: FactPositionV1
    source: FactAuthorSourceV1
    reference_selection: ItemFactReferenceSelectionV1


class ItemFactExistingPreviewV1(StrictRequestModel):
    """起点、变化和替代都只能操作完整业务组。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    target: ItemFactPreviewTargetV1
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    reference_selection: ItemFactReferenceSelectionV1
    replaces: ObjectIdString | None = None
    resolves: list[ObjectIdString] = Field(default_factory=list)


class ItemFactVoidPreviewV1(StrictRequestModel):
    """作废只选一条整组记录，来源由服务读取。"""

    operation: Literal["void"]
    target: ItemFactPreviewTargetV1
    history_id: ObjectIdString


def _validate_item_operation(operation, kind, position, source, replaces, resolves):
    """人工请求和冻结依据共同校验动作与位置，不查询数据库。

    Args:
        operation: 六个固定动作之一。
        kind: 人工起点或章后变化。
        position: 固定生效位置。
        source: 作者说明或章节证据。
        replaces: 明确替代的原整组记录。
        resolves: 明确解除的阻断记录。
    Returns:
        无；不合法的组合直接拒绝。
    """
    if operation == "void":
        return
    if ((operation in {"create", "establish", "correct_initial"} and kind != "start")
            or (operation == "change" and kind != "change")
            or (kind == "start" and source.kind != "author")
            or (kind == "change" and (position.intent != "chapter_after" or source.kind != "chapter"))):
        raise ValueError("物品起点必须有作者说明，章后变化必须有原章证据")
    if source.kind == "chapter" and ObjectId(source.evidence.chapter_id) != ObjectId(position.target_id):
        raise ValueError("物品变化证据必须来自生效章节")
    if operation == "correct_initial" and position.intent != "book_start":
        raise ValueError("更正初始只能作用于书初")
    if operation == "replace" and replaces is None:
        raise ValueError("替代必须明确原整组记录")
    if len(resolves) != len({ObjectId(value) for value in resolves}):
        raise ValueError("解除失效不能重复选择原记录")


class ItemFactPreviewInputV1(RootModel[Annotated[
    ItemFactCreatePreviewV1 | ItemFactExistingPreviewV1 | ItemFactVoidPreviewV1, Field(discriminator="operation"),
]]):
    """按六动作严格分派，不接受旧 B 或逐字段命令。"""

    @model_validator(mode="after")
    def validate_operation(self) -> "ItemFactPreviewInputV1":
        """查询前拒绝动作错位和重复解除对象。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        value = self.root
        if value.operation not in {"create", "void"}:
            _validate_item_operation(value.operation, value.kind, value.position, value.source, value.replaces, value.resolves)
        return self


class ItemFactBasisV1(StrictResponseModel):
    """作者实际预览的整组原值、原记录及原读取，不能在确认时偷换。"""

    schema_version: FactSchemaVersion
    operation: ItemFactOperation
    kind: Literal["start", "change"]
    target: Annotated[ItemFactExistingTargetV1 | ItemFactNewTargetV1, Field(discriminator="kind")]
    position: FactPositionV1
    source: FactSourceV1
    before: ItemFactBeforeV1
    previous: ObjectIdString | None
    blockers: list[ObjectIdString]
    replaces: ObjectIdString | None
    resolves: list[ObjectIdString]
    void_target: ObjectIdString | None
    legacy_values: ItemFactValuesV1 | None
    reference_selection: ItemFactReferenceSelectionV1 | None
    preview_references: list[ItemFactReferenceV1] = Field(max_length=6)
    read: ItemFactReadV1
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_basis(self) -> "ItemFactBasisV1":
        """核对原依据自身完整，当前数据由确认事务重新比较。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        target, read = self.target, self.read
        _validate_item_operation(self.operation, self.kind, self.position, self.source, self.replaces, self.resolves)
        _validate_protected_sources(target.novel_id, self.position, self.protected_sources)
        if (self.operation == "create") != (target.kind == "new") or ObjectId(read.novel_id) != ObjectId(target.novel_id):
            raise ValueError("物品预览动作与小说、目标类别不一致")
        if (self.operation == "void") != (self.reference_selection is None):
            raise ValueError("物品保存预览必须明确三类引用选择，作废不选择新引用")
        expected_refs = {(kind, getattr(values, field)) for values in (self.legacy_values, self.reference_selection)
                         if values is not None
                         for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                             ("location", "current_location_id")) if getattr(values, field) is not None}
        references = {(row.resource_type, row.business_id): row for row in self.preview_references}
        if len(references) != len(self.preview_references) or references.keys() != expected_refs:
            raise ValueError("物品预览必须完整核对旧字段和本次选择的引用")
        for row in read.references:
            if (row.resource_type, row.business_id) in references and references[row.resource_type, row.business_id] != row:
                raise ValueError("物品预览和历史读取必须使用同一份引用资料")
        if (self.before.values is None) != (self.previous is None):
            raise ValueError("物品已知前值必须有唯一原记录")
        if (bool(self.blockers) != (self.before.unknown in {"voided", "needs_review", "unresolved_reference"})
                or len(self.blockers) != len({ObjectId(v) for v in self.blockers})):
            raise ValueError("物品阻断记录必须与整组未知原因一致")
        records = {ObjectId(r.history_id): r for r in read.records}
        if target.kind == "new":
            if (self.before.unknown != "nonexistent" or read.item_ids or read.identities or read.records
                    or self.legacy_values is not None or self.replaces is not None or self.resolves):
                raise ValueError("新物品必须保存不存在的原依据")
        elif (read.item_ids != [target.item_id] or len(read.identities) != 1 or target.is_deleted
              or read.identities[0].model_dump() != target.model_dump(exclude={"kind", "novel_id"})
              or self.legacy_values is None or self.before.unknown == "nonexistent"):
            raise ValueError("物品预览必须绑定原活动物品、版本与旧值")
        if self.previous is not None:
            previous = records.get(ObjectId(self.previous))
            if previous is None or previous.validity.state != "active" or previous.after != self.before.values:
                raise ValueError("物品前值必须等于活动来源的完整后值")
        if any(ObjectId(v) not in records for v in self.blockers):
            raise ValueError("物品阻断记录必须出自原读取")
        if not {ObjectId(v) for v in self.resolves} <= {ObjectId(v) for v in self.blockers}:
            raise ValueError("只能明确解除本次列出的物品阻断")
        if self.operation == "void":
            if self.void_target is None or self.replaces is not None or self.resolves:
                raise ValueError("作废必须只选择原整组记录")
        elif self.void_target is not None:
            raise ValueError("非作废命令不能带作废目标")
        for identity in (self.replaces, self.void_target):
            if identity is None:
                continue
            row = records.get(ObjectId(identity))
            if row is None or row.validity.state != "active" or row.kind != self.kind or row.position != self.position:
                raise ValueError("替代或作废必须是同位置同类型的活动整组记录")
            if self.operation == "void" and (row.source != self.source or row.protected_sources != self.protected_sources):
                raise ValueError("作废必须保留原来源")
        intent = "chapter_before" if self.kind == "change" and self.operation != "void" else self.position.intent
        missing_anchor = (self.operation == "void" and self.position.target_type in {"chapter", "volume"}
                          and not any(r.resource_type == self.position.target_type and ObjectId(r.id) == ObjectId(self.position.target_id) for r in read.directory)
                          and read.position.intent == "book_start")
        if not missing_anchor and (read.position.intent != intent or read.position.target_type != self.position.target_type
                                   or ObjectId(read.position.target_id) != ObjectId(self.position.target_id)):
            raise ValueError("物品预览必须读取原起点或章前位置")
        if self.position.target_type in {"chapter", "volume"} and not missing_anchor:
            directory = {(r.resource_type, ObjectId(r.id)): r for r in read.directory}
            if any((ref.resource_type, ObjectId(ref.id)) not in directory
                   or ObjectId(directory[ref.resource_type, ObjectId(ref.id)].parent_id) != ObjectId(ref.parent_id)
                   for ref in self.protected_sources[1:]):
                raise ValueError("物品预览来源父链必须等于原读取目录")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("物品预览摘要与原冻结内容不一致")
        return self


class ItemFactPreviewV1(StrictResponseModel):
    """显示值就是作者冻结的原整组值。"""

    basis: ItemFactBasisV1
    values: ItemFactBeforeV1

    @model_validator(mode="after")
    def validate_values(self) -> "ItemFactPreviewV1":
        """不能显示一种前值却提交另一种依据。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        if self.values != self.basis.before:
            raise ValueError("物品显示前值与冻结依据不一致")
        return self


class ItemFactCreateConfirmV1(StrictRequestModel):
    """新建不接受虚构旧版本，作者一次提供完整 after。"""

    operation: Literal["create"]
    basis: ItemFactBasisV1
    after: ItemFactValuesV1
    confirmed: FactConfirmed


class ItemFactExistingConfirmV1(StrictRequestModel):
    """已有物品的原版本与完整整组后值。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    basis: ItemFactBasisV1
    expected_version: FactVersion
    after: ItemFactValuesV1
    confirmed: FactConfirmed


class ItemFactVoidConfirmV1(StrictRequestModel):
    """作废不接收 after，不反向执行原 before。"""

    operation: Literal["void"]
    basis: ItemFactBasisV1
    expected_version: FactVersion
    history_id: ObjectIdString
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: FactConfirmed


class ItemFactConfirmV1(RootModel[Annotated[
    ItemFactCreateConfirmV1 | ItemFactExistingConfirmV1 | ItemFactVoidConfirmV1, Field(discriminator="operation"),
]]):
    """只能编辑后值，动作、身份、版本和处置仍来自原预览。"""

    @model_validator(mode="after")
    def validate_command(self) -> "ItemFactConfirmV1":
        """确认必须使用原动作、原版本和原作废对象。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        command, basis = self.root, self.root.basis
        if command.operation != basis.operation:
            raise ValueError("物品确认动作与预览不一致")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("物品确认版本与预览不一致")
        if command.operation == "void" and command.history_id != basis.void_target:
            raise ValueError("物品作废对象与预览不一致")
        if command.operation != "void":
            checked = {(row.resource_type, row.business_id) for row in [*basis.read.references, *basis.preview_references]}
            for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                ("location", "current_location_id")):
                identity = getattr(command.after, field)
                if identity is not None and (kind, identity) not in checked:
                    raise ValueError("这次选择的物品引用未在原预览核对，请保留草稿并重新预览")
        return self


class ItemFactValidityChangeV1(StrictResponseModel):
    """一次动作只处置一条完整物品组。"""

    history_id: ObjectIdString
    before: FactActiveV1
    after: Annotated[FactReplacedV1 | FactVoidedV1, Field(discriminator="state")]


class ItemFactResultV1(StrictResponseModel):
    """首次完整成功结果，后续回放不查询今天的实体。"""

    schema_version: FactSchemaVersion
    operation: ItemFactOperation
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    item_id: ItemId
    item_name: str = Field(min_length=1, max_length=80)
    before_version: FactVersion | None
    after_version: FactVersion
    record: ItemFactRecordV1 | None
    validity_changes: list[ItemFactValidityChangeV1] = Field(max_length=1)
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_result(self) -> "ItemFactResultV1":
        """核对一次真实版本推进和新记录的同一身份。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        if self.operation == "create":
            if self.before_version is not None or self.after_version != 1:
                raise ValueError("新物品必须使用真实版本一")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("物品确认只能增加一个版本")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("只有作废不新增物品事实行")
        if self.record is not None:
            for key in ("novel_id", "entity_id", "item_id", "item_name", "operation", "before_version", "after_version", "confirmed_at"):
                if getattr(self, key) != getattr(self.record, key):
                    raise ValueError("物品首次结果与记录身份、动作或版本不一致")
            if self.record.validity.state != "active":
                raise ValueError("首次成功记录必须为 active")
        return self


class ItemFactReceiptRequestV1(StrictResponseModel):
    """原物品人工确认请求外壳，不承载旧 B。"""

    operation: ItemFactOperation
    novel_id: ObjectIdString
    target_id: ObjectIdString
    data: ItemFactConfirmV1


class ItemFactReceiptV1(StrictResponseModel):
    """保留原请求和首次结果的独立物品回执。"""

    schema_id: Literal["item.fact.receipt"]
    schema_version: FactSchemaVersion
    receipt_id: ObjectIdString
    novel_id: ObjectIdString
    operation: ItemFactOperation
    idempotency_key_hash: FactHash
    request_hash: FactHash
    request: ItemFactReceiptRequestV1
    result: ItemFactResultV1
    position: FactPositionV1
    source: FactSourceV1
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    created_at: FactTimestamp

    @model_validator(mode="after")
    def validate_receipt(self) -> "ItemFactReceiptV1":
        """只核对首次请求、结果及实际处置，不依赖今天的资料。

        Args:
            无；校验当前模型。
        Returns:
            通过核验的当前模型。
        """
        command, result = self.request.data.root, self.result
        basis, target = command.basis, command.basis.target
        if (self.operation != self.request.operation or self.operation != command.operation or self.operation != result.operation
                or any(ObjectId(value) != ObjectId(self.novel_id) for value in (self.request.novel_id, target.novel_id, result.novel_id))
                or ObjectId(self.request.target_id) != ObjectId(target.entity_id) or ObjectId(result.entity_id) != ObjectId(target.entity_id)
                or self.position != basis.position or self.source != basis.source or self.protected_sources != basis.protected_sources
                or self.created_at != result.confirmed_at):
            raise ValueError("物品回执身份、动作、时间或来源不一致")
        if canonical_request_hash(self.request.model_dump()) != self.request_hash:
            raise ValueError("物品回执摘要与原请求不一致")
        if target.kind == "existing":
            if (result.item_id != target.item_id or result.before_version != target.version or result.item_name != target.name):
                raise ValueError("物品回执必须保留原目标身份和版本")
        elif result.item_name != target.candidate.name:
            raise ValueError("新物品结果必须保留原名称")
        if result.record is not None:
            record = result.record
            if any(getattr(record, key) != getattr(basis, key) for key in (
                "kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources",
            )) or record.after != command.after:
                raise ValueError("新物品记录必须精确对应原依据与作者后值")
            expected = ([] if basis.replaces is None else [{"history_id": basis.replaces, "before": {"state": "active"},
                        "after": {"state": "replaced", "by_history_id": record.history_id}}])
        else:
            expected = [{"history_id": command.history_id, "before": {"state": "active"},
                         "after": {"state": "voided", "by_receipt_key_hash": self.idempotency_key_hash}}]
        if [row.model_dump() for row in result.validity_changes] != expected:
            raise ValueError("物品回执处置必须精确等于原替代或作废请求")
        return self


def parse_item_fact_record(document: dict) -> dict:
    """解析物品原 BSON 记录，不接受旧 B 或未知 schema。

    Args:
        document: entity_state_history 中的原始文档。
    Returns:
        严格记录，顶层三个物理身份转为字符串。
    """
    if "history_id" in document or any(not isinstance(document.get(k), ObjectId) for k in ("_id", "novel_id", "entity_id")):
        raise ValueError("物品事实必须保存唯一 BSON 身份")
    if not isinstance(document.get("confirmed_at"), datetime):
        raise ValueError("物品事实时间必须是 BSON datetime")
    payload = {**document, "history_id": str(document["_id"]), "novel_id": str(document["novel_id"]), "entity_id": str(document["entity_id"])}
    del payload["_id"]
    return ItemFactRecordV1.model_validate(payload).model_dump()


def item_fact_record_document(record: dict) -> dict:
    """把严格记录转换为现有历史集合的 BSON 形状。

    Args:
        record: 完整公开物品记录。
    Returns:
        不修改输入的 BSON 文档。
    """
    fields = ItemFactRecordV1.model_validate(record).model_dump()
    identity = ObjectId(fields.pop("history_id"))
    fields["novel_id"], fields["entity_id"] = ObjectId(fields["novel_id"]), ObjectId(fields["entity_id"])
    return {"_id": identity, **fields}


def validate_item_fact_receipt(document: dict) -> dict:
    """核验原 BSON 回执并返回首次成功结果，不读当前实体或来源。

    Args:
        document: 回执集合中的原 BSON 文档。
    Returns:
        原 result 的独立副本。
    """
    if ("receipt_id" in document or not isinstance(document.get("_id"), ObjectId)
            or not isinstance(document.get("novel_id"), ObjectId) or not isinstance(document.get("created_at"), datetime)):
        raise ValueError("物品回执必须保存唯一 BSON 身份和时间")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("物品回执摘要必须对应保存的原请求")
    payload = {**document, "receipt_id": str(document["_id"]), "novel_id": str(document["novel_id"])}
    del payload["_id"]
    ItemFactReceiptV1.model_validate(payload)
    return deepcopy(document["result"])


def item_fact_receipt_document(receipt: dict) -> dict:
    """转换首次成功回执，原请求和原结果不重新清理。

    Args:
        receipt: 完整公开回执。
    Returns:
        可插入既有回执集合的 BSON 文档。
    """
    fields = ItemFactReceiptV1.model_validate(receipt).model_dump()
    identity = ObjectId(fields.pop("receipt_id"))
    fields["novel_id"] = ObjectId(fields["novel_id"])
    fields["request"], fields["result"] = deepcopy(receipt["request"]), deepcopy(receipt["result"])
    document = {"_id": identity, **fields}
    validate_item_fact_receipt(document)
    return document
