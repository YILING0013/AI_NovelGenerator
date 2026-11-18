"""全书级正式物品的严格请求与响应契约。"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.api.contracts import (
    ObjectIdString,
    StrictRequestModel,
    StrictResponseModel,
)
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


ITEM_ID_PATTERN = r"^item_[0-9]{6,}$"
CHARACTER_ID_PATTERN = r"^char_[0-9]{6,}$"
LOCATION_ID_PATTERN = r"^loc_[0-9]{6,}$"
ITEMS_RESULT_SCHEMA_ID = "item.generation.result"
ITEMS_RESULT_SCHEMA_VERSION = 1

ItemId = Annotated[str, Field(pattern=ITEM_ID_PATTERN)]
ItemCandidateRef = Annotated[str, Field(pattern=r"^item_candidate_[0-9]+$")]
CharacterId = Annotated[str, Field(pattern=CHARACTER_ID_PATTERN)]
FactionId = Annotated[str, Field(pattern=FACTION_BUSINESS_ID_PATTERN)]
LocationId = Annotated[str, Field(pattern=LOCATION_ID_PATTERN)]
NonBlankText = Annotated[str, Field(min_length=1)]
LongListText = Annotated[str, Field(min_length=1, max_length=500)]
ItemLifecycleStatus: TypeAlias = Literal[
    "available",
    "held",
    "lost",
    "destroyed",
    "consumed",
]


def normalize_item_text(value: str) -> str:
    """生成物品名称、别名和标签的规范比较键。

    Args:
        value: 需要比较的物品业务文本。

    Returns:
        完成 NFKC、首尾清理、空白折叠和小写转换的文本。
    """
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", value).strip(),
    ).lower()


def _validate_unique_texts(
    name: str,
    aliases: list[str],
    abilities: list[str],
    limitations: list[str],
    costs: list[str],
    tags: list[str],
) -> None:
    """校验物品内容中需要规范唯一的字符串数组。"""
    normalized_aliases = [normalize_item_text(item) for item in aliases]
    if any(not item for item in normalized_aliases):
        raise ValueError("aliases không được chứa phần tử trống")
    if len(normalized_aliases) != len(set(normalized_aliases)):
        raise ValueError("aliases phải chuẩn hóa và duy nhất")
    if normalize_item_text(name) in set(normalized_aliases):
        raise ValueError("aliases không được trùng với tên chính thức")
    for field, values in (
        ("abilities", abilities),
        ("limitations", limitations),
        ("costs", costs),
        ("tags", tags),
    ):
        normalized = [normalize_item_text(item) for item in values]
        if any(not item for item in normalized):
            raise ValueError(f"{field} không được chứa mục trống")
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{field} không được chứa mục trùng lặp")


class ItemCreateV1(StrictRequestModel):
    "Yêu cầu nghiêm ngặt để tạo thủ công một vật phẩm chính thức cấp toàn sách."

    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(default_factory=list, max_length=10)
    item_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=2000)
    appearance: str = Field(default="", max_length=1000)
    origin: str = Field(default="", max_length=1000)
    abilities: list[LongListText] = Field(default_factory=list, max_length=20)
    limitations: list[LongListText] = Field(default_factory=list, max_length=20)
    costs: list[LongListText] = Field(default_factory=list, max_length=20)
    owner_character_id: CharacterId | None = None
    controlling_faction_id: FactionId | None = None
    current_location_id: LocationId | None = None
    lifecycle_status: ItemLifecycleStatus = "available"
    story_function: str = Field(default="", max_length=1000)
    tags: list[NonBlankText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_item_content(self) -> "ItemCreateV1":
        """校验数组唯一性和创建时的生命周期组合。"""
        _validate_unique_texts(
            self.name,
            self.aliases,
            self.abilities,
            self.limitations,
            self.costs,
            self.tags,
        )
        if self.lifecycle_status == "held" and not (
            self.owner_character_id or self.controlling_faction_id
        ):
            raise ValueError("Vật phẩm held phải có chủ sở hữu là nhân vật hoặc thế lực kiểm soát")
        if self.lifecycle_status in {"destroyed", "consumed"} and any(
            (
                self.owner_character_id,
                self.controlling_faction_id,
                self.current_location_id,
            )
        ):
            raise ValueError("Vật phẩm destroyed/consumed không được giữ chủ sở hữu hoặc địa điểm hiện tại")
        return self


class ItemsGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    "Yêu cầu xem trước ứng viên vật phẩm của tiểu thuyết, không nhận bản sao dữ kiện chính thức."

    item_count: int | None = Field(default=6, ge=1, le=20)
    allow_incremental: bool = True
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)
    use_stream: bool = True


class ItemsGenerationInputV1(ReasoningOptions, StrictRequestModel):
    "Đầu vào tạo vật phẩm gửi lại cùng basis và dùng để tính lại khi xác nhận."

    novel_id: ObjectIdString
    item_count: int | None = Field(ge=1, le=20)
    allow_incremental: bool
    user_guidance: str = Field(max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)


class ItemCandidateV1(StrictRequestModel):
    "Một ứng viên vật phẩm do mô hình xuất và người dùng có thể sửa."

    candidate_ref: ItemCandidateRef
    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(max_length=10)
    item_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=2000)
    appearance: str = Field(max_length=1000)
    origin: str = Field(max_length=1000)
    abilities: list[LongListText] = Field(max_length=20)
    limitations: list[LongListText] = Field(max_length=20)
    costs: list[LongListText] = Field(max_length=20)
    owner_character_id: CharacterId | None
    controlling_faction_id: FactionId | None
    current_location_id: LocationId | None
    lifecycle_status: ItemLifecycleStatus
    story_function: str = Field(min_length=1, max_length=1000)
    tags: list[NonBlankText] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_item_candidate(self) -> "ItemCandidateV1":
        """校验候选数组唯一性和状态引用组合。"""
        _validate_unique_texts(
            self.name,
            self.aliases,
            self.abilities,
            self.limitations,
            self.costs,
            self.tags,
        )
        if self.lifecycle_status == "held" and not (
            self.owner_character_id or self.controlling_faction_id
        ):
            raise ValueError("Vật phẩm held phải có chủ sở hữu là nhân vật hoặc thế lực kiểm soát")
        if self.lifecycle_status in {"destroyed", "consumed"} and any(
            (
                self.owner_character_id,
                self.controlling_faction_id,
                self.current_location_id,
            )
        ):
            raise ValueError("Vật phẩm destroyed/consumed không được giữ chủ sở hữu hoặc địa điểm hiện tại")
        return self


class ItemsResultV1(StrictRequestModel):
    "Đối tượng gốc của ứng viên vật phẩm mà Provider phải trả về đầy đủ."

    items: list[ItemCandidateV1] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_candidate_refs(self) -> "ItemsResultV1":
        """拒绝一批候选使用重复的临时引用。"""
        refs = [item.candidate_ref for item in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("candidate_ref không được trùng lặp")
        return self


class ItemsBasisV1(CandidateBasisV1):
    "Căn cứ ứng viên vật phẩm bao gồm phần nhập sinh gốc."

    generation_input: ItemsGenerationInputV1

    @model_validator(mode="after")
    def validate_items_contract(self) -> "ItemsBasisV1":
        """确保 basis 元数据和小说属于物品生成工作流。"""
        if (
            self.workflow != "create_items_by_ai"
            or self.step != "create_items"
            or self.schema_id != ITEMS_RESULT_SCHEMA_ID
            or self.schema_version != ITEMS_RESULT_SCHEMA_VERSION
            or self.novel_id != self.generation_input.novel_id
        ):
            raise ValueError("Hợp đồng basis của vật phẩm không khớp")
        novel_sources = [
            source
            for source in self.source_refs
            if source.resource_type == "novel" and source.id == self.novel_id
        ]
        if len(novel_sources) != 1:
            raise ValueError("basis của vật phẩm phải bao gồm chính xác nguồn của tiểu thuyết hiện tại")
        return self


class ItemsPreviewV1(StrictResponseModel):
    "Bao ứng viên vật phẩm, dùng chung cho phản hồi thường và done.result của SSE."

    workflow: Literal["create_items_by_ai"]
    step: Literal["create_items"]
    schema_id: Literal["item.generation.result"]
    schema_version: Literal[1]
    candidate: ItemsResultV1
    basis: ItemsBasisV1


class ItemBulkGeneratedRequestV1(StrictRequestModel):
    "Phong bì nghiêm ngặt để xác nhận cả loạt ứng viên AI của vật phẩm."

    candidates: list[ItemCandidateV1] = Field(min_length=1, max_length=20)
    basis: ItemsBasisV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在类型转换前拒绝空键、字符串或布尔版本。"""
        if not isinstance(value, dict) or any(
            not isinstance(key, str)
            or not key.strip()
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            for key, version in value.items()
        ):
            raise ValueError("expected_versions phải dùng khóa tài nguyên không rỗng và phiên bản là số nguyên dương")
        return value

    @model_validator(mode="after")
    def validate_confirmation(self) -> "ItemBulkGeneratedRequestV1":
        """要求确认版本精确匹配 basis 并保持候选引用唯一。"""
        expected = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected:
            raise ValueError("expected_versions phải khớp chính xác basis.source_refs")
        refs = [item.candidate_ref for item in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("candidate_ref không được trùng lặp")
        return self


class ItemUpdateV1(StrictRequestModel):
    "Cập nhật cục bộ nội dung vật phẩm theo phiên bản công khai, không được bỏ qua các lệnh trạng thái chuyên dụng."

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    aliases: list[NonBlankText] | None = Field(default=None, max_length=10)
    item_type: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    appearance: str | None = Field(default=None, max_length=1000)
    origin: str | None = Field(default=None, max_length=1000)
    abilities: list[LongListText] | None = Field(default=None, max_length=20)
    limitations: list[LongListText] | None = Field(default=None, max_length=20)
    costs: list[LongListText] | None = Field(default=None, max_length=20)
    owner_character_id: CharacterId | None = None
    controlling_faction_id: FactionId | None = None
    current_location_id: LocationId | None = None
    story_function: str | None = Field(default=None, max_length=1000)
    tags: list[NonBlankText] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "ItemUpdateV1":
        """拒绝空更新以及除三个引用外的显式 null。"""
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Cập nhật vật phẩm cần ít nhất một trường nghiệp vụ")
        reference_fields = {
            "owner_character_id",
            "controlling_faction_id",
            "current_location_id",
        }
        for field in fields - reference_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt tường minh thành null")
        return self


class ItemReorderItemV1(StrictRequestModel):
    "Một mục phiên bản vật phẩm trong đợt sắp xếp lại đầy đủ của tập đang hoạt động."

    item_id: ItemId
    order_index: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class ItemReorderRequestV1(StrictRequestModel):
    "Yêu cầu sắp xếp lại, gửi đầy đủ toàn bộ vật phẩm đang hoạt động trong tiểu thuyết."

    items: list[ItemReorderItemV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> "ItemReorderRequestV1":
        """要求重排 ID 唯一且目标顺序恰为 1..N。"""
        ids = [item.item_id for item in self.items]
        orders = [item.order_index for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item_id sắp xếp lại không được trùng lặp")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("order_index khi sắp xếp phải liên tục đầy đủ 1..N")
        return self


class ItemVersionRequestV1(StrictRequestModel):
    "Phiên bản công khai dùng cho lệnh trạng thái vật phẩm và lệnh khôi phục."

    expected_version: int = Field(ge=1)


class ItemReadV1(StrictResponseModel):
    "Phản chiếu công khai đầy đủ của vật phẩm chính thức."

    item_id: ItemId
    novel_id: ObjectIdString
    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(max_length=10)
    item_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=2000)
    appearance: str = Field(max_length=1000)
    origin: str = Field(max_length=1000)
    abilities: list[LongListText] = Field(max_length=20)
    limitations: list[LongListText] = Field(max_length=20)
    costs: list[LongListText] = Field(max_length=20)
    owner_character_id: CharacterId | None
    controlling_faction_id: FactionId | None
    current_location_id: LocationId | None
    lifecycle_status: ItemLifecycleStatus
    story_function: str = Field(max_length=1000)
    tags: list[NonBlankText] = Field(max_length=20)
    order_index: int = Field(ge=1)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle_projection(self) -> "ItemReadV1":
        """拒绝把不满足正式状态组合的数据库记录投影给客户端。"""
        if self.lifecycle_status == "held" and not (
            self.owner_character_id or self.controlling_faction_id
        ):
            raise ValueError("Vật phẩm held phải có chủ sở hữu là nhân vật hoặc thế lực kiểm soát")
        if self.lifecycle_status in {"destroyed", "consumed"} and any(
            (
                self.owner_character_id,
                self.controlling_faction_id,
                self.current_location_id,
            )
        ):
            raise ValueError("Vật phẩm destroyed/consumed không được giữ chủ sở hữu hoặc địa điểm hiện tại")
        return self


class ItemBulkGeneratedResponseV1(StrictResponseModel):
    "Ánh xạ ứng viên vật phẩm và ảnh chụp nhanh vật phẩm chính thức sau khi ghi."

    candidate_ref_map: dict[ItemCandidateRef, ItemId]
    items: list[ItemReadV1] = Field(min_length=1, max_length=20)


class ItemDeleteImpactV1(StrictResponseModel):
    "Tác động lên các bên dùng chính thức trước khi xoá vĩnh viễn vật phẩm."

    item_id: ItemId
    arcs: int = Field(ge=0)
    chapters: int = Field(ge=0)
    scenes: int = Field(ge=0)
    foreshadowings: int = Field(ge=0)
    total_protected_references: int = Field(ge=0)
    has_protected_references: bool


class ItemHardDeleteResponseV1(StrictResponseModel):
    "Kết quả xoá vĩnh viễn vật phẩm và tác động cuối cùng."

    message: Literal["Hard deleted successfully"]
    item_id: ItemId
    impact: ItemDeleteImpactV1


__all__ = [
    "CHARACTER_ID_PATTERN",
    "ITEM_ID_PATTERN",
    "ITEMS_RESULT_SCHEMA_ID",
    "ITEMS_RESULT_SCHEMA_VERSION",
    "LOCATION_ID_PATTERN",
    "ItemBulkGeneratedRequestV1",
    "ItemBulkGeneratedResponseV1",
    "ItemCandidateV1",
    "ItemCreateV1",
    "ItemDeleteImpactV1",
    "ItemHardDeleteResponseV1",
    "ItemLifecycleStatus",
    "ItemReadV1",
    "ItemReorderItemV1",
    "ItemReorderRequestV1",
    "ItemUpdateV1",
    "ItemVersionRequestV1",
    "ItemsBasisV1",
    "ItemsGenerateRequestV1",
    "ItemsGenerationInputV1",
    "ItemsPreviewV1",
    "ItemsResultV1",
    "normalize_item_text",
]
