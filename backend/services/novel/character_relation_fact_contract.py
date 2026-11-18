"""人物关系状态、人工确认和原成功回执的严格合同。"""

from copy import deepcopy
from datetime import datetime
from typing import Annotated, Literal

from bson import ObjectId
from pydantic import ConfigDict, Field, RootModel, SerializerFunctionWrapHandler, model_serializer, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.character_relation_pydantic import CharacterRelationType, SYMMETRIC_CHARACTER_RELATION_TYPES
from backend.services.novel.character_fact_contract import (
    CharacterId, FactConfirmed, FactHash, FactSchemaVersion, FactTimestamp, FactVersion,
    CharacterFactAuthorSourceV1 as FactAuthorSourceV1,
    CharacterFactDirectoryEntryV1 as FactDirectoryEntryV1,
    CharacterFactReadPositionV1 as FactReadPositionV1,
    CharacterFactSourceObservationV1 as FactSourceObservationV1,
    CharacterFactActiveV1 as FactActiveV1,
    CharacterFactReplacedV1 as FactReplacedV1,
    CharacterFactVoidedV1 as FactVoidedV1,
    CharacterFactPositionV1 as FactPositionV1,
    CharacterFactProtectedSourceV1 as FactProtectedSourceV1,
    CharacterFactSourceV1 as FactSourceV1,
    CharacterFactUnknownReason as FactUnknownReason,
    CharacterFactValidityV1 as FactValidityV1,
)


CharacterRelationFactField = Literal["current_state"]
CHARACTER_RELATION_FACT_FIELDS = frozenset({"current_state"})
CharacterRelationId = Annotated[str, Field(pattern=r"^cr_[0-9]{6,19}$")]
CharacterRelationFactOperation = Literal["create", "establish", "correct_initial", "change", "replace", "void"]
RelationFactFields = Annotated[list[CharacterRelationFactField], Field(min_length=1, max_length=1)]


def _validate_protected_sources(novel_id, position, sources) -> None:
    """记录和预览共用原位置父链检查，不查询今天的目录。"""
    kinds = ["novel"] if position.intent == "book_start" else ["novel", "volume"] if position.intent == "volume_start" else ["novel", "volume", "arc", "scene", "chapter"]
    if ([row.resource_type for row in sources] != kinds
            or ObjectId(sources[0].id) != ObjectId(novel_id)
            or ObjectId(sources[-1].id) != ObjectId(position.target_id)
            or any(ObjectId(row.parent_id) != ObjectId(sources[index - 1].id)
                   for index, row in enumerate(sources) if index)):
        raise ValueError("Sự kiện quan hệ phải lưu chuỗi cha đầy đủ từ cuốn sách này đến neo vị trí")


def _validate_operation(operation, kind, position, source, replaces) -> None:
    """人工预览和冻结依据共用动作边界，替代可作用于起点或变化。"""
    if operation in {"create", "establish", "correct_initial"} and kind != "start":
        raise ValueError("Lệnh điểm khởi đầu quan hệ phải chọn điểm khởi đầu thủ công")
    if operation == "change" and kind != "change":
        raise ValueError("Lệnh thay đổi quan hệ phải chọn thay đổi sau chương")
    if kind == "start" and source.kind != "author":
        raise ValueError("Điểm khởi đầu quan hệ phải dùng mô tả của tác giả")
    if kind == "change" and (source.kind != "chapter" or position.intent != "chapter_after"):
        raise ValueError("Thay đổi quan hệ phải có vị trí sau chương và bằng chứng theo chương")
    if source.kind == "chapter" and ObjectId(source.evidence.chapter_id) != ObjectId(position.target_id):
        raise ValueError("Bằng chứng quan hệ phải đến từ chương đang hiệu lực")
    if operation == "correct_initial" and position.intent != "book_start":
        raise ValueError("Hiệu chỉnh khởi tạo quan hệ chỉ được chọn đầu sách")
    if operation == "replace" and not replaces:
        raise ValueError("Thay thế quan hệ phải chỉ rõ bản ghi gốc")


class CharacterRelationFactValuesV1(StrictRequestModel):
    """关系状态保留作者原文；缺键为未知，不能用 null 或空白代替。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    current_state: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_value(self) -> "CharacterRelationFactValuesV1":
        """只校验实际提供的状态，不给缺键补值。

        Args:
            无。
        Returns:
            非空已知值或空的稀疏对象。
        """
        if "current_state" in self.model_fields_set and (self.current_state is None or not self.current_state.strip()):
            raise ValueError("Trạng thái sự kiện quan hệ phải là văn bản không rỗng; nếu chưa biết hãy để trống mục này")
        return self

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict[str, str]:
        """嵌套序列化也保留缺键，不能自动补 null。

        Args:
            handler: Pydantic 的原序列化函数。
        Returns:
            仅含实际提供字段的字典。
        """
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class CharacterRelationFactStoredValuesV1(CharacterRelationFactValuesV1):
    """已保存的原文不再 trim；仍拒绝空串、纯空白与 null。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)


class CharacterRelationFactBeforeV1(StrictResponseModel):
    """原状态的已知值与未知原因分别保存。"""

    values: CharacterRelationFactStoredValuesV1
    unknown: dict[CharacterRelationFactField, FactUnknownReason]

    @model_validator(mode="after")
    def validate_partition(self) -> "CharacterRelationFactBeforeV1":
        """同一状态不能同时已知和未知。

        Args:
            无。
        Returns:
            不含重叠字段的原状态。
        """
        if self.values.model_fields_set & self.unknown.keys():
            raise ValueError("Trạng thái quan hệ không thể vừa đã biết vừa chưa biết")
        return self


class CharacterRelationFactRecordV1(StrictResponseModel):
    """一次关系状态确认，保存两端物理身份和当时名称，拒绝人物或旧 D 形状。"""

    schema_id: Literal["character_relation.fact"]
    schema_version: FactSchemaVersion
    history_id: ObjectIdString
    novel_id: ObjectIdString
    entity_type: Literal["character_relation"]
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    source_character_id: CharacterId
    source_character_entity_id: ObjectIdString
    source_character_name: str = Field(min_length=1, max_length=80)
    target_character_id: CharacterId
    target_character_entity_id: ObjectIdString
    target_character_name: str = Field(min_length=1, max_length=80)
    operation: Literal["create", "establish", "correct_initial", "change", "replace"]
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    before_version: FactVersion | None
    after_version: FactVersion
    before: CharacterRelationFactBeforeV1
    after: CharacterRelationFactStoredValuesV1
    previous: dict[CharacterRelationFactField, ObjectIdString | None]
    replaces: dict[CharacterRelationFactField, ObjectIdString]
    resolves: dict[CharacterRelationFactField, list[ObjectIdString]]
    validity: dict[CharacterRelationFactField, FactValidityV1]
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_record(self) -> "CharacterRelationFactRecordV1":
        """核对固定字段、完整来源、端点身份和一次真实版本推进。

        Args:
            无。
        Returns:
            可以交给纯求值器的严格关系记录。
        """
        if (self.source_character_id == self.target_character_id
                or ObjectId(self.source_character_entity_id) == ObjectId(self.target_character_entity_id)):
            raise ValueError("Hai đầu quan hệ phải là hai danh tính nhân vật khác nhau")
        _validate_protected_sources(self.novel_id, self.position, self.protected_sources)
        fields = CHARACTER_RELATION_FACT_FIELDS
        if (self.after.model_fields_set != fields
                or self.before.values.model_fields_set | self.before.unknown.keys() != fields
                or self.previous.keys() != fields or self.validity.keys() != fields):
            raise ValueError("Giá trị trước/sau, căn cứ giá trị trước và tính hiệu lực của sự kiện quan hệ phải tương ứng đầy đủ với current_state")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("Giá trị trước đã biết phải có nguồn; previous của giá trị trước chưa biết phải là null")
        if self.operation == "create":
            if (self.before_version is not None or self.after_version != 1 or self.before.values.model_fields_set
                    or self.before.unknown != {"current_state": "nonexistent"} or self.replaces or self.resolves):
                raise ValueError("Điểm khởi đầu quan hệ mới phải dùng phiên bản thật 1 và before không tồn tại")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("Mỗi lần xác nhận quan hệ đã có chỉ được tăng thêm một phiên bản thật")
        if self.operation in {"create", "establish", "correct_initial"} and self.kind != "start":
            raise ValueError("Lệnh điểm khởi đầu quan hệ không được lưu thành thay đổi sau chương")
        if self.operation == "change" and self.kind != "change":
            raise ValueError("Lệnh thay đổi quan hệ sau chương phải lưu bản ghi thay đổi")
        if self.kind == "start" and self.source.kind != "author":
            raise ValueError("Điểm khởi đầu thủ công của quan hệ phải dùng mô tả của tác giả")
        if self.kind == "change" and (self.source.kind != "chapter" or self.position.intent != "chapter_after"):
            raise ValueError("Thay đổi quan hệ sau chương phải có vị trí sau chương và bằng chứng văn bản gốc")
        if self.source.kind == "chapter" and ObjectId(self.source.evidence.chapter_id) != ObjectId(self.position.target_id):
            raise ValueError("Bằng chứng thay đổi quan hệ phải đến từ chương đang hiệu lực")
        if self.operation == "correct_initial" and self.position.intent != "book_start":
            raise ValueError("Hiệu chỉnh khởi tạo quan hệ chỉ áp dụng cho đầu sách")
        if self.operation == "replace" and not self.replaces:
            raise ValueError("Lệnh thay thế quan hệ phải chỉ rõ bản ghi gốc")
        references = [*self.previous.values(), *self.replaces.values(),
                      *(identity for values in self.resolves.values() for identity in values)]
        if any(ObjectId(identity) == ObjectId(self.history_id) for identity in references if identity is not None):
            raise ValueError("Sự kiện quan hệ không được tự tham chiếu làm giá trị trước hoặc đối tượng xử lý")
        for identities in self.resolves.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("Gỡ làm mất hiệu lực sự kiện quan hệ phải liệt kê các bản ghi gốc không trùng lặp")
        for state in self.validity.values():
            if state.state == "replaced" and ObjectId(state.by_history_id) == ObjectId(self.history_id):
                raise ValueError("Sự kiện quan hệ không thể được thay thế bởi chính nó")
        return self


class CharacterRelationFactsAtPositionV1(StrictResponseModel):
    """关系在一个明确位置的值或未知；不夹带计划和裸主档状态。"""

    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    source_character_id: CharacterId
    target_character_id: CharacterId
    version: FactVersion
    values: CharacterRelationFactStoredValuesV1
    unknown: dict[CharacterRelationFactField, FactUnknownReason]
    blockers: dict[CharacterRelationFactField, list[ObjectIdString]]
    origins: dict[CharacterRelationFactField, ObjectIdString]
    claimed_fields: list[CharacterRelationFactField] = Field(max_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> "CharacterRelationFactsAtPositionV1":
        """关系状态只输出一次；未知不能携带可用值。

        Args:
            无。
        Returns:
            已知/未知完整分区且来源对应的读取结果。
        """
        known = self.values.model_fields_set
        if known & self.unknown.keys() or known | self.unknown.keys() != CHARACTER_RELATION_FACT_FIELDS:
            raise ValueError("Đọc phải xác định rõ trạng thái quan hệ đã biết hay chưa biết")
        if (self.origins.keys() != known or self.blockers.keys() != {
                name for name, reason in self.unknown.items() if reason in {"voided", "needs_review", "unresolved_reference"}
        }):
            raise ValueError("Trạng thái quan hệ đã biết phải có nguồn; chờ kiểm tra lại không được kèm giá trị khả dụng")
        if "nonexistent" in self.unknown.values():
            raise ValueError("Kết quả đọc của quan hệ đang tồn tại không được tuyên bố đích không tồn tại")
        claimed = known | {name for name, reason in self.unknown.items() if reason != "unclaimed"}
        if set(self.claimed_fields) != claimed:
            raise ValueError("Trường tiếp nhận của quan hệ phải nhất quán với giá trị đã biết hoặc lý do chưa biết")
        for identities in self.blockers.values():
            if not identities or len(identities) != len({ObjectId(identity) for identity in identities}):
                raise ValueError("Chặn sự kiện quan hệ phải liệt kê các bản ghi gốc không trùng lặp")
        if self.source_character_id == self.target_character_id:
            raise ValueError("Hai đầu quan hệ không được trùng nhau")
        return self


class CharacterRelationFactEndpointReadV1(StrictResponseModel):
    """读取时的真实人物身份；管理停用不解释为剧情结束。"""

    entity_id: ObjectIdString
    character_id: CharacterId
    name: str = Field(min_length=1, max_length=80)
    status: Literal["active", "inactive"]
    is_deleted: bool


class CharacterRelationFactIdentityReadV1(StrictResponseModel):
    """关系的真实身份和管理状态，不带裸 current_state。"""

    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    source_character_id: CharacterId
    target_character_id: CharacterId
    is_active: bool
    is_deleted: bool

    @model_validator(mode="after")
    def validate_endpoints(self) -> "CharacterRelationFactIdentityReadV1":
        """关系的两个业务端点不能相同。"""
        if self.source_character_id == self.target_character_id:
            raise ValueError("Hai đầu quan hệ không được trùng nhau")
        return self


class CharacterRelationFactHistoryObservationV1(StrictResponseModel):
    """原记录摘要和有效性，不以摘要代替物理身份和动作版本。"""

    history_id: ObjectIdString
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    after_version: FactVersion
    immutable_fingerprint: FactHash
    validity: dict[CharacterRelationFactField, FactValidityV1] = Field(min_length=1)


class CharacterRelationFactReadV1(StrictResponseModel):
    """按原关系选择复验的读取；空选择不是空的全书搜索。"""

    kind: Literal["character_relation_facts"]
    novel_id: ObjectIdString
    relation_ids: list[CharacterRelationId]
    position: FactReadPositionV1
    directory: list[FactDirectoryEntryV1]
    identities: list[CharacterRelationFactIdentityReadV1]
    endpoints: list[CharacterRelationFactEndpointReadV1]
    history: list[CharacterRelationFactHistoryObservationV1]
    sources: list[FactSourceObservationV1]
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_read(self) -> "CharacterRelationFactReadV1":
        """检查当时目录、原选择和身份自洽，不访问今天的资料。"""
        if len(self.relation_ids) != len(set(self.relation_ids)):
            raise ValueError("Lựa chọn đọc quan hệ không được trùng lặp")
        identities = {row.relation_id: row for row in self.identities}
        if (len(identities) != len(self.identities) or not identities.keys() <= set(self.relation_ids)
                or len({ObjectId(row.entity_id) for row in self.identities}) != len(self.identities)):
            raise ValueError("Quan hệ được đọc phải là lựa chọn nghiệp vụ gốc và danh tính vật lý không trùng lặp")
        endpoint_ids = {identity for row in self.identities for identity in (row.source_character_id, row.target_character_id)}
        if (len({row.character_id for row in self.endpoints}) != len(self.endpoints)
                or len({ObjectId(row.entity_id) for row in self.endpoints}) != len(self.endpoints)
                or any(row.character_id not in endpoint_ids for row in self.endpoints)):
            raise ValueError("Nhân vật được đọc phải là điểm cuối thực tế của quan hệ, không trùng lặp")
        if len({ObjectId(row.history_id) for row in self.history}) != len(self.history):
            raise ValueError("Bản ghi đọc không được lặp lại danh tính vật lý")
        for row in self.history:
            identity = identities.get(row.relation_id)
            if identity is None or ObjectId(identity.entity_id) != ObjectId(row.entity_id):
                raise ValueError("Quan sát bản ghi phải thuộc danh tính vật lý của quan hệ được đọc lần này")
        # 目录按类别区分物理身份，不能把不同集合相同 ObjectId 混在一起。
        directory = {(row.resource_type, ObjectId(row.id)): row for row in self.directory}
        if len(directory) != len(self.directory):
            raise ValueError("Danh mục đóng băng không được lặp lại danh tính vật lý cùng loại")
        parents = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}
        for row in self.directory:
            parent_kind = parents[row.resource_type]
            if (parent_kind == "novel" and ObjectId(row.parent_id) != ObjectId(self.novel_id)
                    or parent_kind != "novel" and (parent_kind, ObjectId(row.parent_id)) not in directory):
                raise ValueError("Danh mục đóng băng phải lưu chuỗi cha đầy đủ bên trong cuốn sách này")
        position = self.position
        if position.target_type == "novel":
            if ObjectId(position.target_id) != ObjectId(self.novel_id):
                raise ValueError("Đọc đầu sách phải trỏ tới cuốn sách này")
        else:
            row = directory.get((position.target_type, ObjectId(position.target_id)))
            if row is None:
                raise ValueError("Neo đọc phải tồn tại trong danh mục đóng băng tại thời điểm đó")
            order = [row.order_index]
            while row.resource_type != "volume":
                row = directory[parents[row.resource_type], ObjectId(row.parent_id)]
                order.append(row.order_index)
            if list(reversed(order)) != position.order:
                raise ValueError("Thứ tự đọc phải bằng thứ tự chuỗi cha đầy đủ của danh mục đóng băng")
        source_keys = [(ObjectId(row.chapter_id), ObjectId(row.revision_id) if row.revision_id else None) for row in self.sources]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Cùng một bản chỉnh sửa chương không được lưu quan sát trùng lặp")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"}, exclude_unset=True)) != self.fingerprint:
            raise ValueError("Tóm tắt đọc quan hệ không khớp với nội dung đóng băng")
        return self


class CharacterRelationFactReadResultV1(StrictResponseModel):
    """明确区分位置结果、缺失关系和原读取依据。"""

    novel_id: ObjectIdString
    position: FactReadPositionV1
    relations: list[CharacterRelationFactsAtPositionV1]
    missing_relation_ids: list[CharacterRelationId]
    reads: list[CharacterRelationFactReadV1] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "CharacterRelationFactReadResultV1":
        """返回结果只能来自同一次原选择，不能省略缺失项。"""
        read = self.reads[0]
        if ObjectId(read.novel_id) != ObjectId(self.novel_id) or read.position != self.position:
            raise ValueError("Vị trí và tiểu thuyết của kết quả quan hệ phải bằng lần đọc gốc")
        identities = {row.relation_id: row for row in read.identities if not row.is_deleted}
        if (len({row.relation_id for row in self.relations}) != len(self.relations)
                or {row.relation_id for row in self.relations} != identities.keys()
                or len(self.missing_relation_ids) != len(set(self.missing_relation_ids))
                or set(self.missing_relation_ids) != set(read.relation_ids) - identities.keys()):
            raise ValueError("Kết quả quan hệ và các quan hệ thiếu phải bao phủ đầy đủ lựa chọn gốc")
        for row in self.relations:
            identity = identities[row.relation_id]
            if (ObjectId(row.entity_id) != ObjectId(identity.entity_id)
                    or (row.source_character_id, row.target_character_id) != (identity.source_character_id, identity.target_character_id)):
                raise ValueError("Kết quả quan hệ không được thay thế danh tính vật lý gốc hoặc nhân vật hai đầu")
            history = {ObjectId(item.history_id): item for item in read.history if item.relation_id == row.relation_id}
            sources = [*row.origins.values(), *(identity for ids in row.blockers.values() for identity in ids)]
            if (bool(row.claimed_fields) != bool(history) or any(ObjectId(value) not in history for value in sources)
                    or any(item.after_version > row.version for item in history.values())):
                raise ValueError("Việc tiếp nhận, phiên bản và nguồn của kết quả quan hệ phải tương ứng với quan sát bản ghi gốc")
            if any(history[ObjectId(origin)].validity[name].state != "active" for name, origin in row.origins.items()):
                raise ValueError("Nguồn của giá trị quan hệ đã biết phải vẫn là active")
        return self


class CharacterRelationFactQueryV1(StrictRequestModel):
    """按明确 ID 读取；省略位置由服务端解析一次最新位置。"""

    relation_ids: list[CharacterRelationId] = Field(max_length=200)
    position: FactPositionV1 | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "CharacterRelationFactQueryV1":
        """空选择合法，但不能借重复 ID 扩大或改变范围。"""
        if len(self.relation_ids) != len(set(self.relation_ids)):
            raise ValueError("Truy vấn quan hệ không được chọn lại cùng một quan hệ")
        return self


class CharacterRelationFactEndpointV1(CharacterRelationFactEndpointReadV1):
    """人工确认冻结端点的真实版本，不重新按名称绑定。"""

    version: FactVersion


def _validate_available_endpoints(source, target) -> None:
    """新建和既有预览使用同一端点可用性规则。"""
    if source.character_id == target.character_id or ObjectId(source.entity_id) == ObjectId(target.entity_id):
        raise ValueError("Quan hệ phải liên kết với hai nhân vật khác nhau")
    if any(row.is_deleted or row.status != "active" for row in (source, target)):
        raise ValueError("Xác nhận quan hệ mới cần hai nhân vật đang hoạt động và chưa bị thu hồi")


class CharacterRelationFactCreateDataV1(StrictResponseModel):
    """新关系的端点与设计；current_state 只在作者 after 中提供。"""

    source_character_id: CharacterId
    target_character_id: CharacterId
    relation_type: CharacterRelationType
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(min_length=1, max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    story_value: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5)
    sort_order: int = Field(default=0, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def validate_candidate(self) -> "CharacterRelationFactCreateDataV1":
        """设计不接受空白或自指；对称关系由服务端在冻结前排序。"""
        if self.source_character_id == self.target_character_id:
            raise ValueError("Quan hệ không được trỏ tới cùng một nhân vật")
        if any(not getattr(self, name).strip() for name in ("core_conflict", "hidden_tension", "possible_change", "story_value")):
            raise ValueError("Văn bản thiết kế quan hệ không được để trống")
        return self

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler: SerializerFunctionWrapHandler) -> dict:
        """保留原候选字段，不补默认值改变预览摘要。"""
        return {name: value for name, value in handler(self).items() if name in self.model_fields_set}


class CharacterRelationFactExistingTargetV1(StrictResponseModel):
    """既有关系及两个端点的原物理身份、名称和版本。"""

    kind: Literal["existing"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    version: FactVersion
    source_character: CharacterRelationFactEndpointV1
    target_character: CharacterRelationFactEndpointV1

    @model_validator(mode="after")
    def validate_endpoints(self) -> "CharacterRelationFactExistingTargetV1":
        """冻结两个真实可用端点，历史读取不使用这个确认目标类型。"""
        _validate_available_endpoints(self.source_character, self.target_character)
        return self


class CharacterRelationFactNewTargetV1(StrictResponseModel):
    """新建只冻结待用物理身份和空语义查询，不预占关系业务号。"""

    kind: Literal["new"]
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    candidate: CharacterRelationFactCreateDataV1
    source_character: CharacterRelationFactEndpointV1
    target_character: CharacterRelationFactEndpointV1
    entity_exists: Literal[False]
    semantic_matches: list[ObjectIdString] = Field(max_length=0)

    @model_validator(mode="before")
    @classmethod
    def require_absence(cls, value: object) -> object:
        """不存在必须是布尔 false，不能用整数零冒充。"""
        if isinstance(value, dict) and value.get("entity_exists") is not False:
            raise ValueError("Xem trước tạo mới phải xác nhận danh tính vật lý chưa tồn tại")
        return value

    @model_validator(mode="after")
    def validate_endpoints(self) -> "CharacterRelationFactNewTargetV1":
        """冻结候选与端点必须一致，对称关系保持原业务规范顺序。"""
        _validate_available_endpoints(self.source_character, self.target_character)
        ids = (self.source_character.character_id, self.target_character.character_id)
        if ids != (self.candidate.source_character_id, self.candidate.target_character_id):
            raise ValueError("Ứng viên quan hệ mới không khớp với điểm cuối đóng băng")
        if self.candidate.relation_type in SYMMETRIC_CHARACTER_RELATION_TYPES and ids != tuple(sorted(ids)):
            raise ValueError("Quan hệ đối xứng mới phải chốt trước thứ tự điểm cuối theo quy chuẩn")
        return self


CharacterRelationFactTargetV1 = Annotated[
    CharacterRelationFactExistingTargetV1 | CharacterRelationFactNewTargetV1, Field(discriminator="kind"),
]


class CharacterRelationFactPreviewExistingTargetV1(StrictRequestModel):
    """已有关系预览只接受正式身份和原版本，不接受客户端端点替换。"""

    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    expected_version: FactVersion


class CharacterRelationFactPreviewNewTargetV1(StrictRequestModel):
    """新建预览尚未提供关系物理或业务身份。"""

    candidate: CharacterRelationFactCreateDataV1


class CharacterRelationFactCreatePreviewInputV1(StrictRequestModel):
    """作者明确选择新关系状态的起点，不提交虚构 before。"""

    operation: Literal["create"]
    target: CharacterRelationFactPreviewNewTargetV1
    position: FactPositionV1
    source: FactAuthorSourceV1
    fields: RelationFactFields


class CharacterRelationFactExistingPreviewInputV1(StrictRequestModel):
    """已有关系选择起点或变化和明确的原记录处置。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    target: CharacterRelationFactPreviewExistingTargetV1
    kind: Literal["start", "change"]
    position: FactPositionV1
    source: FactSourceV1
    fields: RelationFactFields
    replaces: dict[CharacterRelationFactField, ObjectIdString] = Field(default_factory=dict)
    resolves: dict[CharacterRelationFactField, list[ObjectIdString]] = Field(default_factory=dict)


class CharacterRelationFactVoidPreviewInputV1(StrictRequestModel):
    """作废位置和来源取自原记录，客户端只明确选中记录。"""

    operation: Literal["void"]
    target: CharacterRelationFactPreviewExistingTargetV1
    targets: dict[CharacterRelationFactField, ObjectIdString] = Field(min_length=1)


class CharacterRelationFactPreviewInputV1(RootModel[Annotated[
    CharacterRelationFactCreatePreviewInputV1 | CharacterRelationFactExistingPreviewInputV1 | CharacterRelationFactVoidPreviewInputV1,
    Field(discriminator="operation"),
]]):
    """按实际动作解析人工请求，不自动升级旧 D 或人物请求。"""

    @model_validator(mode="after")
    def validate_operation(self) -> "CharacterRelationFactPreviewInputV1":
        """在读取数据库前拒绝错位动作及重复处置对象。"""
        value = self.root
        if value.operation not in {"create", "void"}:
            _validate_operation(value.operation, value.kind, value.position, value.source, value.replaces)
            if any(not ids or len(ids) != len({ObjectId(identity) for identity in ids}) for ids in value.resolves.values()):
                raise ValueError("Gỡ mất hiệu lực phải chỉ rõ các bản ghi gốc không trùng lặp")
        return self


class CharacterRelationFactBasisV1(StrictResponseModel):
    """作者实际看过的关系、端点、前值及原读取；旧裸值单独保留。"""

    schema_version: FactSchemaVersion
    operation: CharacterRelationFactOperation
    kind: Literal["start", "change"]
    target: CharacterRelationFactTargetV1
    position: FactPositionV1
    source: FactSourceV1
    fields: RelationFactFields
    before: CharacterRelationFactBeforeV1
    previous: dict[CharacterRelationFactField, ObjectIdString | None]
    replaces: dict[CharacterRelationFactField, ObjectIdString]
    resolves: dict[CharacterRelationFactField, list[ObjectIdString]]
    void_targets: dict[CharacterRelationFactField, ObjectIdString]
    targets: list[CharacterRelationFactRecordV1]
    blockers: dict[CharacterRelationFactField, list[ObjectIdString]]
    field_sources: list[CharacterRelationFactRecordV1]
    legacy_values: CharacterRelationFactStoredValuesV1
    reads: list[CharacterRelationFactReadV1] = Field(min_length=1, max_length=1)
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    fingerprint: FactHash

    @model_validator(mode="after")
    def validate_basis(self) -> "CharacterRelationFactBasisV1":
        """仅核对冻结内容自洽；当前可用性与实际前值由确认事务复验。"""
        target, read = self.target, self.reads[0]
        fields = CHARACTER_RELATION_FACT_FIELDS
        _validate_operation(self.operation, self.kind, self.position, self.source, self.replaces)
        _validate_protected_sources(target.novel_id, self.position, self.protected_sources)
        if (self.before.values.model_fields_set | self.before.unknown.keys() != fields
                or self.previous.keys() != fields):
            raise ValueError("Giá trị trước và căn cứ giá trị trước trong xem trước quan hệ phải tương ứng đầy đủ với current_state")
        if (any(self.previous[name] is None for name in self.before.values.model_fields_set)
                or any(self.previous[name] is not None for name in self.before.unknown)):
            raise ValueError("Giá trị trước đã biết của quan hệ phải có nguồn; giá trị trước chưa biết không được giả mạo previous")
        required_blockers = {name for name, reason in self.before.unknown.items()
                             if reason in {"voided", "needs_review", "unresolved_reference"}}
        if self.blockers.keys() != required_blockers or any(
                not ids or len(ids) != len({ObjectId(identity) for identity in ids}) for ids in self.blockers.values()):
            raise ValueError("Chặn do chưa biết về quan hệ phải giữ đầy đủ các bản ghi gốc không trùng lặp")
        if (self.operation == "create") != (target.kind == "new"):
            raise ValueError("Đích tạo mới và đích đã có của quan hệ không được dùng lẫn")
        if ObjectId(read.novel_id) != ObjectId(target.novel_id):
            raise ValueError("Đọc xem trước quan hệ không được vượt sang cuốn sách khác")
        if target.kind == "new":
            if (self.before.unknown != {"current_state": "nonexistent"} or self.before.values.model_fields_set
                    or self.replaces or self.resolves or self.targets or self.legacy_values.model_fields_set
                    or read.relation_ids or read.identities or read.endpoints or read.history):
                raise ValueError("Quan hệ mới phải đóng băng kết quả đọc trống khi chưa tồn tại, không được kèm trạng thái hoặc lịch sử cũ")
        else:
            expected_identity = {"entity_id": target.entity_id, "relation_id": target.relation_id,
                                 "source_character_id": target.source_character.character_id,
                                 "target_character_id": target.target_character.character_id,
                                 "is_active": True, "is_deleted": False}
            if (read.relation_ids != [target.relation_id] or len(read.identities) != 1
                    or ObjectId(read.identities[0].entity_id) != ObjectId(target.entity_id)
                    or read.identities[0].model_dump(exclude={"entity_id"}) != {name: value for name, value in expected_identity.items() if name != "entity_id"}
                    or self.legacy_values.model_fields_set != fields or "nonexistent" in self.before.unknown.values()):
                raise ValueError("Xem trước quan hệ đã có phải liên kết với quan hệ active gốc và văn bản hồ sơ chính cũ")
            endpoints = {row.character_id: row for row in read.endpoints}
            if set(endpoints) != {target.source_character.character_id, target.target_character.character_id}:
                raise ValueError("Xem trước quan hệ phải đọc đầy đủ nhân vật hai đầu")
            for endpoint in (target.source_character, target.target_character):
                observed = endpoints[endpoint.character_id]
                if (ObjectId(observed.entity_id) != ObjectId(endpoint.entity_id)
                        or observed.model_dump(exclude={"entity_id"}) != endpoint.model_dump(exclude={"entity_id", "version"})):
                    raise ValueError("Nhân vật xem trước không được thay thế danh tính, tên hoặc trạng thái quản lý của lần đọc gốc")
            if any(row.after_version > target.version for row in read.history):
                raise ValueError("Lần đọc gốc của quan hệ không được chứa hành động sau phiên bản xem trước")
            reason = self.before.unknown.get("current_state")
            if (reason == "unclaimed" and read.history) or (reason == "before_start" and not read.history):
                raise ValueError("Trạng thái chưa tiếp nhận hoặc trước điểm khởi đầu phải nhất quán với sự tồn tại của bản ghi gốc")

        directory = {(row.resource_type, ObjectId(row.id)): row for row in read.directory}
        expected_intent = "chapter_before" if self.kind == "change" and self.operation != "void" else self.position.intent
        same_anchor = (read.position.intent == expected_intent and read.position.target_type == self.position.target_type
                       and ObjectId(read.position.target_id) == ObjectId(self.position.target_id))
        missing_void_anchor = (self.operation == "void" and self.position.target_type in {"chapter", "volume"}
                               and (self.position.target_type, ObjectId(self.position.target_id)) not in directory
                               and read.position.intent == "book_start")
        if not same_anchor and not missing_void_anchor:
            raise ValueError("Xem trước quan hệ phải đọc trước thời điểm xảy ra điểm khởi đầu đã chọn hoặc thay đổi; chỉ khi vô hiệu mà thiếu neo mới được quay về đầu sách")
        if self.position.target_type in {"chapter", "volume"} and not missing_void_anchor:
            for reference in self.protected_sources[1:]:
                row = directory.get((reference.resource_type, ObjectId(reference.id)))
                if row is None or ObjectId(row.parent_id) != ObjectId(reference.parent_id):
                    raise ValueError("Chuỗi cha nguồn thực sự của xem trước phải bằng danh mục đóng băng lần này")

        observations = {ObjectId(row.history_id): row for row in read.history}
        snapshots = {}
        for row in [*self.targets, *self.field_sources]:
            identity = ObjectId(row.history_id)
            observation = observations.get(identity)
            prior = snapshots.setdefault(identity, row)
            if (target.kind != "existing" or prior != row or observation is None
                    or ObjectId(row.novel_id) != ObjectId(target.novel_id)
                    or ObjectId(row.entity_id) != ObjectId(target.entity_id) or row.relation_id != target.relation_id
                    or ObjectId(observation.entity_id) != ObjectId(row.entity_id) or observation.relation_id != row.relation_id
                    or observation.after_version != row.after_version or observation.validity != row.validity
                    or canonical_request_hash(row.model_dump(exclude={"validity"}, exclude_unset=True)) != observation.immutable_fingerprint):
                raise ValueError("Ảnh chụp nguồn quan hệ phải tương ứng với bản ghi bất biến và tính hiệu lực của cùng quan hệ trong lần đọc gốc")
            for side in ("source", "target"):
                endpoint = getattr(target, f"{side}_character")
                if (getattr(row, f"{side}_character_id") != endpoint.character_id
                        or ObjectId(getattr(row, f"{side}_character_entity_id")) != ObjectId(endpoint.entity_id)):
                    raise ValueError("Lịch sử không được đổi liên kết danh tính nghiệp vụ hoặc vật lý của hai đầu quan hệ")

        field_sources = {ObjectId(row.history_id): row for row in self.field_sources}
        source_ids = {ObjectId(identity) for identity in self.previous.values() if identity is not None} | {
            ObjectId(identity) for ids in self.blockers.values() for identity in ids
        }
        if len(field_sources) != len(self.field_sources) or field_sources.keys() != source_ids:
            raise ValueError("Nguồn trường quan hệ phải bao phủ vừa đủ giá trị trước và các bản ghi bị chặn")
        previous = self.previous["current_state"]
        if previous is not None:
            row = field_sources[ObjectId(previous)]
            if self.before.values != row.after or row.validity["current_state"].state != "active":
                raise ValueError("Giá trị trước đã biết của quan hệ phải bằng giá trị nguồn gốc vẫn đang hoạt động")
        targets = {ObjectId(row.history_id): row for row in self.targets}
        target_ids = {ObjectId(identity) for identity in [*self.replaces.values(), *self.void_targets.values(),
                      *(identity for ids in self.resolves.values() for identity in ids)]}
        if len(targets) != len(self.targets) or targets.keys() != target_ids:
            raise ValueError("Ảnh chụp xử lý quan hệ phải bao phủ chính xác các bản ghi gốc đã chọn")
        if self.operation == "void":
            if self.void_targets.keys() != fields or self.replaces or self.resolves:
                raise ValueError("Vô hiệu quan hệ không được lẫn với thay thế hoặc gỡ bỏ")
        elif self.void_targets:
            raise ValueError("Xem trước quan hệ không vô hiệu không được mang đích vô hiệu")
        for name, identity in {**self.replaces, **self.void_targets}.items():
            row = targets[ObjectId(identity)]
            if (row.validity[name].state != "active" or row.kind != self.kind or row.position != self.position
                    or self.operation == "void" and (row.source != self.source or row.protected_sources != self.protected_sources)):
                raise ValueError("Thay thế hoặc vô hiệu phải chọn bản ghi gốc đang hoạt động cùng vị trí cùng loại; vô hiệu giữ nguồn gốc")
        for name, ids in self.resolves.items():
            selected = {ObjectId(identity) for identity in ids}
            if not ids or len(selected) != len(ids) or not selected <= {ObjectId(identity) for identity in self.blockers.get(name, [])}:
                raise ValueError("Chỉ được gỡ rõ ràng các bản ghi bị chặn không trùng lặp đã nêu trong giá trị trước gốc lần này")
        if canonical_request_hash(self.model_dump(exclude={"fingerprint"}, exclude_unset=True)) != self.fingerprint:
            raise ValueError("Tóm tắt xem trước quan hệ không khớp với nội dung đóng băng gốc")
        return self


class CharacterRelationFactPreviewV1(StrictResponseModel):
    """作者看到的前值必须就是冻结依据中的前值。"""

    basis: CharacterRelationFactBasisV1
    values: CharacterRelationFactBeforeV1

    @model_validator(mode="after")
    def validate_values(self) -> "CharacterRelationFactPreviewV1":
        """不能显示一种前值却确认另一种原依据。"""
        if self.values != self.basis.before:
            raise ValueError("Màn hình xem trước quan hệ không khớp với giá trị trước đóng băng")
        return self


class CharacterRelationFactCreateConfirmV1(StrictRequestModel):
    """作者状态只提供一次，新建不接受伪造的旧版本。"""

    operation: Literal["create"]
    basis: CharacterRelationFactBasisV1
    after: CharacterRelationFactValuesV1
    confirmed: FactConfirmed


class CharacterRelationFactExistingConfirmV1(StrictRequestModel):
    """确认已有关系的一个真实动作，保持目标和原读取不变。"""

    operation: Literal["establish", "correct_initial", "change", "replace"]
    basis: CharacterRelationFactBasisV1
    expected_version: FactVersion
    after: CharacterRelationFactValuesV1
    confirmed: FactConfirmed


class CharacterRelationFactVoidConfirmV1(StrictRequestModel):
    """作废只处置选中记录，不提交 after 或反向恢复 before。"""

    operation: Literal["void"]
    basis: CharacterRelationFactBasisV1
    expected_version: FactVersion
    targets: dict[CharacterRelationFactField, ObjectIdString]
    reason: str = Field(min_length=1, max_length=2000)
    confirmed: FactConfirmed


class CharacterRelationFactConfirmV1(RootModel[Annotated[
    CharacterRelationFactCreateConfirmV1 | CharacterRelationFactExistingConfirmV1 | CharacterRelationFactVoidConfirmV1,
    Field(discriminator="operation"),
]]):
    """确认只可编辑 after，不能替换原预览的操作或版本。"""

    @model_validator(mode="after")
    def validate_command(self) -> "CharacterRelationFactConfirmV1":
        """按动作核对唯一原目标及严格作者确认。"""
        command, basis = self.root, self.root.basis
        if command.operation != basis.operation:
            raise ValueError("Hành động xác nhận quan hệ không khớp với xem trước gốc")
        if command.operation != "create" and command.expected_version != basis.target.version:
            raise ValueError("Phiên bản xác nhận quan hệ không khớp với xem trước gốc")
        if command.operation == "void":
            if command.targets != basis.void_targets:
                raise ValueError("Đích vô hiệu quan hệ không khớp với xem trước gốc")
        elif command.after.model_fields_set != CHARACTER_RELATION_FACT_FIELDS:
            raise ValueError("Xác nhận quan hệ phải nêu rõ current_state, không được xác nhận bằng giá trị mặc định")
        return self


class CharacterRelationFactValidityChangeV1(StrictResponseModel):
    """一个关系动作对原状态记录的实际单向处置。"""

    history_id: ObjectIdString
    field: CharacterRelationFactField
    before: FactActiveV1
    after: Annotated[FactReplacedV1 | FactVoidedV1, Field(discriminator="state")]


class CharacterRelationFactResultV1(StrictResponseModel):
    """首次成功的完整关系结果；后来改名、回收不改写这份快照。"""

    schema_version: FactSchemaVersion
    operation: CharacterRelationFactOperation
    novel_id: ObjectIdString
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    source_character_id: CharacterId
    source_character_entity_id: ObjectIdString
    source_character_name: str = Field(min_length=1, max_length=80)
    target_character_id: CharacterId
    target_character_entity_id: ObjectIdString
    target_character_name: str = Field(min_length=1, max_length=80)
    before_version: FactVersion | None
    after_version: FactVersion
    record: CharacterRelationFactRecordV1 | None
    validity_changes: list[CharacterRelationFactValidityChangeV1]
    confirmed_at: FactTimestamp

    @model_validator(mode="after")
    def validate_result(self) -> "CharacterRelationFactResultV1":
        """一次关系动作只推进一个真实版本，作废没有新事实行。"""
        if (self.source_character_id == self.target_character_id
                or ObjectId(self.source_character_entity_id) == ObjectId(self.target_character_entity_id)):
            raise ValueError("Kết quả quan hệ phải lưu hai danh tính nhân vật khác nhau")
        if self.operation == "create":
            if self.before_version is not None or self.after_version != 1:
                raise ValueError("Kết quả quan hệ mới phải dùng phiên bản thật bằng 1")
        elif self.before_version is None or self.after_version != self.before_version + 1:
            raise ValueError("Kết quả quan hệ đã có chỉ được tăng thêm một phiên bản thật")
        if (self.operation == "void") != (self.record is None):
            raise ValueError("Chỉ kết quả vô hiệu quan hệ là không có bản ghi sự kiện mới")
        if self.record is not None:
            for name in ("novel_id", "entity_id", "source_character_entity_id", "target_character_entity_id"):
                if ObjectId(getattr(self, name)) != ObjectId(getattr(self.record, name)):
                    raise ValueError("Kết quả quan hệ không khớp danh tính vật lý của bản ghi mới")
            for name in ("operation", "relation_id", "source_character_id", "source_character_name", "target_character_id",
                         "target_character_name", "before_version", "after_version", "confirmed_at"):
                if getattr(self, name) != getattr(self.record, name):
                    raise ValueError("Kết quả quan hệ không khớp hành động, danh tính, phiên bản hoặc thời gian của bản ghi mới")
            if any(value.state != "active" for value in self.record.validity.values()):
                raise ValueError("Bản ghi thành công đầu tiên phải giữ trạng thái active lúc đó")
        keys = [(ObjectId(row.history_id), row.field) for row in self.validity_changes]
        if len(keys) != len(set(keys)):
            raise ValueError("Trường của cùng một bản ghi quan hệ không được xử lý lặp")
        return self


class CharacterRelationFactReceiptRequestV1(StrictResponseModel):
    """原请求外壳与新关系确认绑定，不能承载旧 D 请求。"""

    operation: CharacterRelationFactOperation
    novel_id: ObjectIdString
    target_id: ObjectIdString
    data: CharacterRelationFactConfirmV1


class CharacterRelationFactReceiptV1(StrictResponseModel):
    """新关系事实的独立成功回执，不放宽旧 D 或人物 schema。"""

    schema_id: Literal["character_relation.fact.receipt"]
    schema_version: FactSchemaVersion
    receipt_id: ObjectIdString
    novel_id: ObjectIdString
    operation: CharacterRelationFactOperation
    idempotency_key_hash: FactHash
    request_hash: FactHash
    request: CharacterRelationFactReceiptRequestV1
    result: CharacterRelationFactResultV1
    position: FactPositionV1
    source: FactSourceV1
    protected_sources: list[FactProtectedSourceV1] = Field(min_length=1, max_length=5)
    created_at: FactTimestamp

    @model_validator(mode="after")
    def validate_receipt(self) -> "CharacterRelationFactReceiptV1":
        """核对原请求及首次结果，不检查今天的关系或来源。"""
        command, result = self.request.data.root, self.result
        basis, target = command.basis, command.basis.target
        if (self.operation != self.request.operation or self.operation != command.operation or self.operation != result.operation
                or any(ObjectId(value) != ObjectId(self.novel_id) for value in (self.request.novel_id, target.novel_id, result.novel_id))
                or ObjectId(self.request.target_id) != ObjectId(target.entity_id) or ObjectId(result.entity_id) != ObjectId(target.entity_id)
                or self.position != basis.position or self.source != basis.source or self.protected_sources != basis.protected_sources
                or self.created_at != result.confirmed_at):
            raise ValueError("Biên nhận quan hệ không khớp hành động, danh tính, thời gian hoặc nguồn với yêu cầu gốc")
        if canonical_request_hash(self.request.model_dump(exclude_unset=True)) != self.request_hash:
            raise ValueError("Tóm tắt biên nhận quan hệ không khớp yêu cầu gốc")
        if target.kind == "existing" and (result.relation_id != target.relation_id or result.before_version != target.version):
            raise ValueError("Biên nhận quan hệ phải lưu số nghiệp vụ và phiên bản của đích gốc")
        for side in ("source", "target"):
            endpoint = getattr(target, f"{side}_character")
            if (getattr(result, f"{side}_character_id") != endpoint.character_id
                    or ObjectId(getattr(result, f"{side}_character_entity_id")) != ObjectId(endpoint.entity_id)
                    or getattr(result, f"{side}_character_name") != endpoint.name):
                raise ValueError("Kết quả thành công phải lưu danh tính nhân vật hai đầu và tên lúc đó của xem trước gốc")
        if result.record is not None:
            record = result.record
            if (record.kind != basis.kind or record.position != basis.position or record.source != basis.source
                    or record.before != basis.before or record.previous != basis.previous or record.replaces != basis.replaces
                    or record.resolves != basis.resolves or record.protected_sources != basis.protected_sources
                    or record.after.model_dump(exclude_unset=True) != command.after.model_dump(exclude_unset=True)):
                raise ValueError("Bản ghi quan hệ mới phải tương ứng chính xác với xem trước gốc và after của tác giả")
            expected = {(ObjectId(identity), name, "replaced", ObjectId(record.history_id)) for name, identity in basis.replaces.items()}
        else:
            expected = {(ObjectId(identity), name, "voided", self.idempotency_key_hash) for name, identity in command.targets.items()}
        actual = {(ObjectId(row.history_id), row.field, row.after.state,
                   ObjectId(row.after.by_history_id) if row.after.state == "replaced" else row.after.by_receipt_key_hash)
                  for row in result.validity_changes}
        if actual != expected:
            raise ValueError("Việc xử lý thực tế trong biên nhận quan hệ phải bằng đúng yêu cầu thay thế hoặc vô hiệu gốc")
        return self


def parse_character_relation_fact_record(document: dict) -> dict:
    """解析原 BSON 关系事实，保留端点字符串和原文。

    Args:
        document: 历史集合中的原 BSON 文档；时间不能用字符串冒充。
    Returns:
        严格公开记录，只有三个顶层物理身份转换成字符串。
    """
    if "history_id" in document or any(not isinstance(document.get(name), ObjectId) for name in ("_id", "novel_id", "entity_id")):
        raise ValueError("Bản ghi sự kiện quan hệ phải lưu danh tính BSON duy nhất")
    if not isinstance(document.get("confirmed_at"), datetime):
        raise ValueError("Thời gian xác nhận sự kiện quan hệ phải lưu dạng BSON datetime")
    payload = {**document, "history_id": str(document["_id"]), "novel_id": str(document["novel_id"]), "entity_id": str(document["entity_id"])}
    del payload["_id"]
    return CharacterRelationFactRecordV1.model_validate(payload).model_dump(exclude_unset=True)


def character_relation_fact_record_document(record: dict) -> dict:
    """把公开关系记录转换为固定 BSON 形状，不改裸主档镜像。

    Args:
        record: 严格公开记录，端点物理身份保持公开字符串。
    Returns:
        BSON 身份与毫秒 datetime 的新文档，不修改输入。
    """
    fields = CharacterRelationFactRecordV1.model_validate(record).model_dump(exclude_unset=True)
    identity = ObjectId(fields.pop("history_id"))
    fields["novel_id"], fields["entity_id"] = ObjectId(fields["novel_id"]), ObjectId(fields["entity_id"])
    return {"_id": identity, **fields}


def validate_character_relation_fact_receipt(document: dict) -> dict:
    """核验原 BSON 回执并返回原成功结果，不重算今天的任何资料。

    Args:
        document: 回执集合的原 BSON 文档，request/result 是首次保存的公开快照。
    Returns:
        首次 result 的独立副本；错误形状、身份、时间或摘要立即拒绝。
    """
    if ("receipt_id" in document or not isinstance(document.get("_id"), ObjectId)
            or not isinstance(document.get("novel_id"), ObjectId)):
        raise ValueError("Biên nhận sự kiện quan hệ phải lưu danh tính BSON duy nhất")
    if not isinstance(document.get("created_at"), datetime):
        raise ValueError("Thời gian biên nhận sự kiện quan hệ phải lưu dạng BSON datetime")
    if canonical_request_hash(document.get("request")) != document.get("request_hash"):
        raise ValueError("Tóm tắt biên nhận quan hệ phải tương ứng với yêu cầu gốc đã lưu")
    payload = {**document, "receipt_id": str(document["_id"]), "novel_id": str(document["novel_id"])}
    del payload["_id"]
    CharacterRelationFactReceiptV1.model_validate(payload)
    return deepcopy(document["result"])


def character_relation_fact_receipt_document(receipt: dict) -> dict:
    """把首次成功公开回执转为 BSON，原 request/result 不重新清理。

    Args:
        receipt: 含完整原请求与原成功结果的严格公开回执。
    Returns:
        可插入既有回执集合的固定 BSON 文档，不修改输入。
    """
    parsed = CharacterRelationFactReceiptV1.model_validate(receipt)
    fields = parsed.model_dump(exclude_unset=True)
    identity = ObjectId(fields.pop("receipt_id"))
    fields["novel_id"] = ObjectId(fields["novel_id"])
    fields["request"], fields["result"] = deepcopy(receipt["request"]), deepcopy(receipt["result"])
    document = {"_id": identity, **fields}
    validate_character_relation_fact_receipt(document)
    return document
