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
    "Điểm khởi đầu vật phẩm do tác giả minh thị xác nhận; phần giải thích bổ sung có thể để trống, không viết thay lời tác giả."

    kind: Literal["author"]
    note: str = Field(default="", max_length=2000)


FactSourceV1 = Annotated[FactAuthorSourceV1 | CharacterFactChapterSourceV1, Field(discriminator="kind")]


class ItemFactValuesV1(StrictResponseModel):
    "Bốn trường phải cung cấp đồng thời; tham chiếu null là minh thị không có tham chiếu, không biểu thị chưa biết."

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
            raise ValueError("vật phẩm held phải có chủ sở hữu hoặc thế lực kiểm soát")
        if self.lifecycle_status in {"destroyed", "consumed"} and any(value is not None for value in (
            self.owner_character_id, self.controlling_faction_id, self.current_location_id,
        )):
            raise ValueError("vật phẩm destroyed/consumed không được giữ chủ sở hữu, thế lực kiểm soát hoặc địa điểm")
        return self


ITEM_FACT_FIELDS = frozenset({"lifecycle_status", "owner_character_id", "controlling_faction_id", "current_location_id"})
ItemFactOperation = Literal["create", "establish", "correct_initial", "change", "replace", "void"]


class ItemFactBeforeV1(StrictResponseModel):
    "Cả nhóm đã biết hoặc cả nhóm chưa biết, cấm giữ lại các trường vật phẩm chỉ đáng tin một phần."

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
            raise ValueError("Bốn trường của vật phẩm phải biết đầy đủ cả nhóm hoặc không biết cả nhóm")
        return self


class ItemFactRecordV1(StrictResponseModel):
    "Một lượt xác nhận vật phẩm chỉ tiến một phiên bản thực thể; giá trị trước và cách xử lý đều nhấm cả nhóm."

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
            raise ValueError("Dữ kiện vật phẩm phải lưu chuỗi cha đầy đủ từ cuốn sách này đến neo vị trí")
        if (self.before.values is None) != (self.previous is None):
            raise ValueError("Giá trị trước đã biết của vật phẩm phải có nguồn cho cả nhóm; previous của giá trị trước chưa biết phải là null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1
                    or self.before.unknown != "nonexistent" or self.replaces is not None or self.resolves):
                raise ValueError("Điểm khởi đầu vật phẩm tạo mới phải dùng phiên bản thật số một và giá trị trước không tồn tại")
        else:
            if self.before_version is None or self.after_version != self.before_version + 1:
                raise ValueError("Với vật phẩm đã có, mỗi lần xác nhận chỉ được tăng một phiên bản thật")
            if self.before.unknown == "nonexistent":
                raise ValueError("Vật phẩm đã có không được khai báo đích không tồn tại")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("Lệnh điểm khởi đầu vật phẩm phải lưu điểm khởi đầu thủ công")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("Lệnh thay đổi vật phẩm phải lưu thay đổi sau chương")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("Điểm khởi đầu thủ công của vật phẩm phải dùng ghi chú của tác giả")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("Thay đổi sau chương của vật phẩm phải có vị trí sau chương và bằng chứng văn bản gốc")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("Bằng chứng thay đổi vật phẩm phải đến từ chương đã hiệu lực")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("Hiệu chỉnh khởi tạo vật phẩm chỉ áp dụng cho bản ghi đầu sách")
        if self.operation == "replace" and self.replaces is None:
            raise ValueError("Thay thế vật phẩm phải chỉ rõ cả nhóm bản ghi gốc")
        if any(ObjectId(identity) == ObjectId(self.history_id)
               for identity in [self.previous, self.replaces, *self.resolves] if identity is not None):
            raise ValueError("Dữ kiện vật phẩm không được tham chiếu chính nó làm giá trị trước hoặc đối tượng xử lý")
        if len(self.resolves) != len({ObjectId(identity) for identity in self.resolves}):
            raise ValueError("Gỡ hết hiệu lực dữ kiện vật phẩm không được chỉ định lặp bản ghi gốc")
        if self.validity.state == "replaced" and ObjectId(self.validity.by_history_id) == ObjectId(self.history_id):
            raise ValueError("Dữ kiện vật phẩm không được thay thế bởi chính nó")
        return self


class ItemFactsAtPositionV1(ItemFactBeforeV1):
    "Toàn bộ nhóm của một vật phẩm tại vị trí minh thị; nguồn, trạng thái chặn và trạng thái nhận cũng trả theo nhóm."

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
            raise ValueError("Giá trị đã biết của vật phẩm phải có một nguồn duy nhất cho cả nhóm")
        blocked = self.unknown in {"voided", "needs_review", "unresolved_reference"}
        if bool(self.blockers) != blocked or len(self.blockers) != len({ObjectId(identity) for identity in self.blockers}):
            raise ValueError("Vật phẩm chờ xem xét lại hoặc vô hiệu hoá phải liệt kê các bản ghi chặn không trùng lặp")
        if self.unknown == "nonexistent" or self.claimed != (self.unknown != "unclaimed"):
            raise ValueError("Trạng thái được thừa nhận của vật phẩm hiện có phải nhất quán với kết quả đọc của cả nhóm")
        return self


class ItemFactIdentityV1(StrictResponseModel):
    "Chỉ đóng băng danh tính và phiên bản vật phẩm, không coi trạng thái trần là lịch sử."

    entity_id: ObjectIdString
    item_id: ItemId
    name: str = Field(min_length=1, max_length=80)
    version: FactVersion
    is_deleted: bool


class ItemFactReferenceV1(StrictResponseModel):
    "Ghi nhận một tham chiếu thực tế đã tồn tại hay còn thiếu vào thời điểm đó, giữ danh tính vật lý để tái kiểm tra."

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
            raise ValueError("Loại tham chiếu vật phẩm không nhất quán với ID nghiệp vụ")
        if self.entity_id is None:
            if any(value is not None for value in (self.version, self.is_deleted, self.status)) or self.available:
                raise ValueError("Tham chiếu bị thiếu không được mang trạng thái thực thể")
        elif self.version is None or self.is_deleted is None or self.status is None:
            raise ValueError("Tham chiếu đã tồn tại phải đóng băng đầy đủ danh tính và trạng thái")
        if self.available and (self.is_deleted or self.status != "active"):
            raise ValueError("Tham chiếu khả dụng phải chưa bị thu hồi và đang hoạt động")
        return self


class ItemFactReferenceSelectionV1(StrictResponseModel):
    "Nêu minh thị ba loại tham chiếu sẽ dùng khi xem trước; null nghĩa là lần này không chọn tham chiếu đó."

    owner_character_id: CharacterId | None
    controlling_faction_id: FactionId | None
    current_location_id: LocationId | None


class ItemFactReadV1(StrictResponseModel):
    "Mục lục, bản ghi đầy đủ và tham chiếu thật trong cùng một giao dịch; chọn rỗng vẫn lưu phạm vi gốc."

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
            raise ValueError("Danh tính đọc vật phẩm phải tương ứng với các lựa chọn gốc không trùng lặp")
        if len({ObjectId(row.history_id) for row in self.records}) != len(self.records):
            raise ValueError("Đọc vật phẩm không được lặp lại danh tính lịch sử")
        for row in self.records:
            target = identities.get(row.item_id)
            if (target is None or ObjectId(row.entity_id) != ObjectId(target.entity_id)
                    or ObjectId(row.novel_id) != ObjectId(self.novel_id) or row.after_version > target.version):
                raise ValueError("Bản ghi vật phẩm không nhất quán với danh tính vật lý, tiểu thuyết hoặc phiên bản gốc")
        directory = {(row.resource_type, ObjectId(row.id)): row for row in self.directory}
        parents = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}
        if len(directory) != len(self.directory):
            raise ValueError("Thư mục đọc vật phẩm không được trùng lặp")
        for row in self.directory:
            kind = parents[row.resource_type]
            if (kind == "novel" and ObjectId(row.parent_id) != ObjectId(self.novel_id)
                    or kind != "novel" and (kind, ObjectId(row.parent_id)) not in directory):
                raise ValueError("Thư mục đọc vật phẩm phải là chuỗi cha đầy đủ trong cùng cuốn sách")
        if self.position.target_type == "novel":
            if ObjectId(self.position.target_id) != ObjectId(self.novel_id):
                raise ValueError("Bản ghi đầu sách phải chỉ tiểu thuyết hiện tại")
        else:
            row = directory.get((self.position.target_type, ObjectId(self.position.target_id)))
            if row is None:
                raise ValueError("Neo đọc vật phẩm phải tồn tại trong thư mục đã đóng băng")
            order = [row.order_index]
            while row.resource_type != "volume":
                row = directory[parents[row.resource_type], ObjectId(row.parent_id)]
                order.append(row.order_index)
            if list(reversed(order)) != self.position.order:
                raise ValueError("Thứ tự đọc vật phẩm phải đến từ thư mục đầy đủ")
        expected_refs = {(kind, getattr(values, field)) for record in self.records
                         for values in (record.before.values, record.after) if values is not None
                         for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                             ("location", "current_location_id")) if getattr(values, field) is not None}
        if (len({(r.resource_type, r.business_id) for r in self.references}) != len(self.references)
                or {(r.resource_type, r.business_id) for r in self.references} != expected_refs):
            raise ValueError("Quan sát tham chiếu vật phẩm phải bao phủ đầy đủ giá trị trước và sau của bản ghi")
        expected_sources = {(ObjectId(r.source.evidence.chapter_id), ObjectId(r.source.evidence.revision_id))
                            for r in self.records if r.source.kind == "chapter"}
        if (any(s.revision_id is None for s in self.sources)
                or len({(ObjectId(s.chapter_id), ObjectId(s.revision_id)) for s in self.sources}) != len(self.sources)
                or {(ObjectId(s.chapter_id), ObjectId(s.revision_id)) for s in self.sources} != expected_sources):
            raise ValueError("Quan sát nội dung vật phẩm phải bao phủ đầy đủ nguồn của bản ghi gốc")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("Tóm tắt đọc vật phẩm không nhất quán với nội dung đã đóng băng")
        return self


class ItemFactCreateDataV1(StrictResponseModel):
    "Vật phẩm mới chỉ cung cấp trường thiết kế; sự kiện bốn trường được cung cấp riêng trong after của bước xác nhận."

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
            raise ValueError("Tên, loại và mô tả vật phẩm không được để trống")
        return self


class ItemFactExistingTargetV1(ItemFactIdentityV1):
    "Danh tính vật lý gốc, số nghiệp vụ và phiên bản biên tập của vật phẩm đã có."

    kind: Literal["existing"]
    novel_id: ObjectIdString


class ItemFactNewTargetV1(StrictResponseModel):
    "Tạo mới chỉ đóng băng ID vật lý chờ dùng, không giữ chỗ số nghiệp vụ hay thứ tự sắp xếp."

    kind: Literal["new"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    candidate: ItemFactCreateDataV1


class ItemFactPreviewTargetV1(StrictRequestModel):
    "Xem trước cho đối tượng đã có chỉ nhận danh tính vật lý, ID nghiệp vụ và phiên bản gốc."

    entity_id: ObjectIdString
    item_id: ItemId
    expected_version: FactVersion


class ItemFactCreatePreviewV1(StrictRequestModel):
    "Tác giả chọn rõ khởi điểm cho vật phẩm mới."

    operation: Literal["create"]
    candidate: ItemFactCreateDataV1
    position: FactPositionV1
    source: FactAuthorSourceV1
    reference_selection: ItemFactReferenceSelectionV1


class ItemFactExistingPreviewV1(StrictRequestModel):
    "Điểm khởi đầu, thay đổi và thay thế đều chỉ được thao tác trên nguyên nhóm nghiệp vụ."

    operation: Literal["establish", "correct_initial", "change", "replace"]
    target: ItemFactPreviewTargetV1
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    reference_selection: ItemFactReferenceSelectionV1
    replaces: ObjectIdString | None = None
    resolves: list[ObjectIdString] = Field(default_factory=list)


class ItemFactVoidPreviewV1(StrictRequestModel):
    "Vô hiệu hóa chỉ chọn một bản ghi nguyên nhóm; nguồn do dịch vụ đọc."

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
        raise ValueError("Điểm khởi đầu vật phẩm phải có ghi chú của tác giả, thay đổi sau chương phải có bằng chứng của chương gốc")
    if source.kind == "chapter" and ObjectId(source.evidence.chapter_id) != ObjectId(position.target_id):
        raise ValueError("Bằng chứng thay đổi vật phẩm phải đến từ chương đã hiệu lực")
    if operation == "correct_initial" and position.intent != "book_start":
        raise ValueError("Hiệu chỉnh khởi tạo chỉ áp dụng cho bản ghi đầu sách")
    if operation == "replace" and replaces is None:
        raise ValueError("Thay thế phải chỉ rõ cả nhóm bản ghi gốc")
    if len(resolves) != len({ObjectId(value) for value in resolves}):
        raise ValueError("Gỡ hết hiệu lực không được chọn lặp bản ghi gốc")


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
    "Nguyên bộ giá trị gốc, bản ghi gốc và lượt đọc gốc mà tác giả thực sự xem trước, không được tráo khi xác nhận."

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
            raise ValueError("Hành động xem trước vật phẩm không nhất quán với tiểu thuyết và loại đích")
        if (self.operation == "void") != (self.reference_selection is None):
            raise ValueError("Xem trước lưu vật phẩm phải chọn rõ ba loại tham chiếu; vô hiệu hoá không chọn tham chiếu mới")
        expected_refs = {(kind, getattr(values, field)) for values in (self.legacy_values, self.reference_selection)
                         if values is not None
                         for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                             ("location", "current_location_id")) if getattr(values, field) is not None}
        references = {(row.resource_type, row.business_id): row for row in self.preview_references}
        if len(references) != len(self.preview_references) or references.keys() != expected_refs:
            raise ValueError("Bản xem trước vật phẩm phải đối chiếu đầy đủ các trường cũ và các tham chiếu đã chọn lần này")
        for row in read.references:
            if (row.resource_type, row.business_id) in references and references[row.resource_type, row.business_id] != row:
                raise ValueError("Bản xem trước vật phẩm và lần đọc lịch sử phải dùng cùng một bộ tài liệu tham chiếu")
        if (self.before.values is None) != (self.previous is None):
            raise ValueError("Giá trị trước đã biết của vật phẩm phải có một bản ghi gốc duy nhất")
        if (bool(self.blockers) != (self.before.unknown in {"voided", "needs_review", "unresolved_reference"})
                or len(self.blockers) != len({ObjectId(v) for v in self.blockers})):
            raise ValueError("Bản ghi chặn vật phẩm phải nhất quán với lý do không biết của cả nhóm")
        records = {ObjectId(r.history_id): r for r in read.records}
        if target.kind == "new":
            if (self.before.unknown != "nonexistent" or read.item_ids or read.identities or read.records
                    or self.legacy_values is not None or self.replaces is not None or self.resolves):
                raise ValueError("Vật phẩm mới phải lưu căn cứ gốc không tồn tại")
        elif (read.item_ids != [target.item_id] or len(read.identities) != 1 or target.is_deleted
              or read.identities[0].model_dump() != target.model_dump(exclude={"kind", "novel_id"})
              or self.legacy_values is None or self.before.unknown == "nonexistent"):
            raise ValueError("Bản xem trước vật phẩm phải liên kết với vật phẩm hoạt động gốc, phiên bản và giá trị cũ")
        if self.previous is not None:
            previous = records.get(ObjectId(self.previous))
            if previous is None or previous.validity.state != "active" or previous.after != self.before.values:
                raise ValueError("Giá trị trước của vật phẩm phải bằng toàn bộ giá trị sau của nguồn đang hoạt động")
        if any(ObjectId(v) not in records for v in self.blockers):
            raise ValueError("Bản ghi chặn vật phẩm phải xuất phát từ lần đọc gốc")
        if not {ObjectId(v) for v in self.resolves} <= {ObjectId(v) for v in self.blockers}:
            raise ValueError("Chỉ được giải toả rõ ràng các bản chặn vật phẩm đã liệt kê lần này")
        if self.operation == "void":
            if self.void_target is None or self.replaces is not None or self.resolves:
                raise ValueError("Vô hiệu hoá chỉ được chọn cả nhóm bản ghi gốc")
        elif self.void_target is not None:
            raise ValueError("Lệnh không vô hiệu hoá không được kèm đích vô hiệu hoá")
        for identity in (self.replaces, self.void_target):
            if identity is None:
                continue
            row = records.get(ObjectId(identity))
            if row is None or row.validity.state != "active" or row.kind != self.kind or row.position != self.position:
                raise ValueError("Thay thế hoặc vô hiệu hoá phải là cả nhóm bản ghi hoạt động cùng vị trí và cùng loại")
            if self.operation == "void" and (row.source != self.source or row.protected_sources != self.protected_sources):
                raise ValueError("Vô hiệu hoá phải giữ nguyên nguồn gốc")
        intent = "chapter_before" if self.kind == "change" and self.operation != "void" else self.position.intent
        missing_anchor = (self.operation == "void" and self.position.target_type in {"chapter", "volume"}
                          and not any(r.resource_type == self.position.target_type and ObjectId(r.id) == ObjectId(self.position.target_id) for r in read.directory)
                          and read.position.intent == "book_start")
        if not missing_anchor and (read.position.intent != intent or read.position.target_type != self.position.target_type
                                   or ObjectId(read.position.target_id) != ObjectId(self.position.target_id)):
            raise ValueError("Bản xem trước vật phẩm phải đọc điểm khởi đầu gốc hoặc vị trí trước chương")
        if self.position.target_type in {"chapter", "volume"} and not missing_anchor:
            directory = {(r.resource_type, ObjectId(r.id)): r for r in read.directory}
            if any((ref.resource_type, ObjectId(ref.id)) not in directory
                   or ObjectId(directory[ref.resource_type, ObjectId(ref.id)].parent_id) != ObjectId(ref.parent_id)
                   for ref in self.protected_sources[1:]):
                raise ValueError("Chuỗi cha của nguồn xem trước vật phẩm phải bằng thư mục đọc gốc")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"})) != self.fingerprint:
            raise ValueError("Tóm tắt xem trước vật phẩm không khớp với nội dung đã đóng băng gốc")
        return self


class ItemFactPreviewV1(StrictResponseModel):
    "Giá trị hiển thị chính là giá trị toàn nhóm gốc do tác giả đóng băng."

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
            raise ValueError("Giá trị trước hiển thị của vật phẩm không khớp với căn cứ đã đóng băng")
        return self


class ItemFactCreateConfirmV1(StrictRequestModel):
    "Tạo mới không nhận phiên bản cũ hư cấu; tác giả cung cấp after đầy đủ trong một lần."

    operation: Literal["create"]
    basis: ItemFactBasisV1
    after: ItemFactValuesV1
    confirmed: FactConfirmed


class ItemFactExistingConfirmV1(StrictRequestModel):
    "Phiên bản gốc của vật phẩm đã có và giá trị sau của toàn nhóm."

    operation: Literal["establish", "correct_initial", "change", "replace"]
    basis: ItemFactBasisV1
    expected_version: FactVersion
    after: ItemFactValuesV1
    confirmed: FactConfirmed


class ItemFactVoidConfirmV1(StrictRequestModel):
    "Hủy bỏ không nhận after và không thực thi ngược before gốc."

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
            raise ValueError("Hành động xác nhận vật phẩm không khớp với bản xem trước")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("Phiên bản xác nhận vật phẩm không khớp với bản xem trước")
        if command.operation == "void" and command.history_id != basis.void_target:
            raise ValueError("Đối tượng vô hiệu hoá vật phẩm không khớp với bản xem trước")
        if command.operation != "void":
            checked = {(row.resource_type, row.business_id) for row in [*basis.read.references, *basis.preview_references]}
            for kind, field in (("character", "owner_character_id"), ("faction", "controlling_faction_id"),
                                ("location", "current_location_id")):
                identity = getattr(command.after, field)
                if identity is not None and (kind, identity) not in checked:
                    raise ValueError("Tham chiếu vật phẩm đã chọn lần này chưa được đối chiếu trong bản xem trước gốc, hãy giữ bản nháp và xem trước lại")
        return self


class ItemFactValidityChangeV1(StrictResponseModel):
    "Một hành động chỉ xử lý một nhóm vật phẩm hoàn chỉnh."

    history_id: ObjectIdString
    before: FactActiveV1
    after: Annotated[FactReplacedV1 | FactVoidedV1, Field(discriminator="state")]


class ItemFactResultV1(StrictResponseModel):
    "Kết quả thành công đầy đủ lần đầu; các lần phát lại sau không truy vấn thực thể của hôm nay."

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
                raise ValueError("Vật phẩm mới phải dùng phiên bản thật số một")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("Xác nhận vật phẩm chỉ được tăng một phiên bản")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("Chỉ vô hiệu hoá, không thêm dòng dữ kiện vật phẩm")
        if self.record is not None:
            for key in ("novel_id", "entity_id", "item_id", "item_name", "operation", "before_version", "after_version", "confirmed_at"):
                if getattr(self, key) != getattr(self.record, key):
                    raise ValueError("Kết quả đầu tiên của vật phẩm không nhất quán với danh tính, hành động hoặc phiên bản bản ghi")
            if self.record.validity.state != "active":
                raise ValueError("Bản ghi thành công đầu tiên phải là active")
        return self


class ItemFactReceiptRequestV1(StrictResponseModel):
    "Vỏ yêu cầu xác nhận thủ công cho vật phẩm gốc, không mang theo B cũ."

    operation: ItemFactOperation
    novel_id: ObjectIdString
    target_id: ObjectIdString
    data: ItemFactConfirmV1


class ItemFactReceiptV1(StrictResponseModel):
    "Biên nhận vật phẩm độc lập giữ lại yêu cầu gốc và kết quả lần đầu."

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
            raise ValueError("Danh tính, hành động, thời gian hoặc nguồn của biên nhận vật phẩm không nhất quán")
        if canonical_request_hash(self.request.model_dump()) != self.request_hash:
            raise ValueError("Tóm tắt biên nhận vật phẩm không khớp với yêu cầu gốc")
        if target.kind == "existing":
            if (result.item_id != target.item_id or result.before_version != target.version or result.item_name != target.name):
                raise ValueError("Biên nhận vật phẩm phải giữ danh tính và phiên bản đích gốc")
        elif result.item_name != target.candidate.name:
            raise ValueError("Kết quả vật phẩm mới phải giữ tên gốc")
        if result.record is not None:
            record = result.record
            if any(getattr(record, key) != getattr(basis, key) for key in (
                "kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources",
            )) or record.after != command.after:
                raise ValueError("Bản ghi vật phẩm mới phải khớp chính xác với căn cứ gốc và giá trị sau của tác giả")
            expected = ([] if basis.replaces is None else [{"history_id": basis.replaces, "before": {"state": "active"},
                        "after": {"state": "replaced", "by_history_id": record.history_id}}])
        else:
            expected = [{"history_id": command.history_id, "before": {"state": "active"},
                         "after": {"state": "voided", "by_receipt_key_hash": self.idempotency_key_hash}}]
        if [row.model_dump() for row in result.validity_changes] != expected:
            raise ValueError("Xử lý biên nhận vật phẩm phải bằng chính xác yêu cầu thay thế hoặc vô hiệu hoá gốc")
        return self


def parse_item_fact_record(document: dict) -> dict:
    """解析物品原 BSON 记录，不接受旧 B 或未知 schema。

    Args:
        document: entity_state_history 中的原始文档。
    Returns:
        严格记录，顶层三个物理身份转为字符串。
    """
    if "history_id" in document or any(not isinstance(document.get(k), ObjectId) for k in ("_id", "novel_id", "entity_id")):
        raise ValueError("Dữ kiện vật phẩm phải lưu danh tính BSON duy nhất")
    if not isinstance(document.get("confirmed_at"), datetime):
        raise ValueError("Thời gian của dữ kiện vật phẩm phải là BSON datetime")
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
        raise ValueError("Biên nhận vật phẩm phải lưu danh tính BSON và thời gian duy nhất")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("Tóm tắt biên nhận vật phẩm phải tương ứng với yêu cầu gốc đã lưu")
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
