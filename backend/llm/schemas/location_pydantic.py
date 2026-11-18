"""地点正式领域与后续 AI 批量确认共用的严格契约。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
import unicodedata

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


LOCATION_ID_PATTERN = r"^loc_[0-9]{6,}$"
RULE_ID_PATTERN = r"^rule_[0-9]{6,}$"
FACTION_ID_PATTERN = FACTION_BUSINESS_ID_PATTERN
VOLUME_LOCATIONS_RESULT_SCHEMA_ID = "volume_locations_result"
VOLUME_LOCATIONS_RESULT_SCHEMA_VERSION = 1
LocationId = Annotated[str, Field(pattern=LOCATION_ID_PATTERN)]
RuleId = Annotated[str, Field(pattern=RULE_ID_PATTERN)]
FactionId = Annotated[str, Field(pattern=FACTION_ID_PATTERN)]
LocationCandidateRef = Annotated[str, Field(min_length=1, max_length=64)]
NonBlankText = Annotated[str, Field(min_length=1)]


def normalize_location_text(value: str) -> str:
    """生成地点名称、别名和候选去重共用的规范比较键。

    Args:
        value: 需要比较的地点业务文本。

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
    rules_and_constraints: list[str],
    applicable_rule_ids: list[str],
    associated_faction_ids: list[str],
    tags: list[str],
) -> None:
    """校验地点内容中客户端可重复提交的各类数组。

    Args:
        name: 地点正式名称。
        aliases: 地点别名。
        rules_and_constraints: 地点自身规则说明。
        applicable_rule_ids: 正式规则 ID。
        associated_faction_ids: 正式势力 ID。
        tags: 地点标签。

    Returns:
        所有数组规范唯一时返回 None。
    """
    normalized_aliases = [normalize_location_text(item) for item in aliases]
    if any(not item for item in normalized_aliases):
        raise ValueError("aliases không được chứa phần tử trống")
    if len(normalized_aliases) != len(set(normalized_aliases)):
        raise ValueError("aliases phải chuẩn hóa và duy nhất")
    if normalize_location_text(name) in set(normalized_aliases):
        raise ValueError("aliases không được trùng với tên chính thức")
    for field, values in (
        ("rules_and_constraints", rules_and_constraints),
        ("applicable_rule_ids", applicable_rule_ids),
        ("associated_faction_ids", associated_faction_ids),
        ("tags", tags),
    ):
        normalized = [
            normalize_location_text(item) if isinstance(item, str) else item
            for item in values
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{field} không được chứa mục trùng lặp")


class LocationCreateV1(StrictRequestModel):
    "Yêu cầu nghiêm ngặt để tạo thủ công một địa điểm chính thức cấp toàn sách."

    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(default_factory=list, max_length=10)
    location_type: str = Field(min_length=1, max_length=40)
    parent_location_id: LocationId | None = None
    description: str = Field(min_length=1, max_length=2000)
    environment: str = Field(default="", max_length=1000)
    atmosphere: str = Field(default="", max_length=1000)
    geography: str = Field(default="", max_length=1000)
    rules_and_constraints: list[NonBlankText] = Field(
        default_factory=list,
        max_length=20,
    )
    applicable_rule_ids: list[RuleId] = Field(default_factory=list, max_length=50)
    associated_faction_ids: list[FactionId] = Field(
        default_factory=list,
        max_length=50,
    )
    story_function: str = Field(default="", max_length=1000)
    status: Literal["active", "inactive"] = "active"
    tags: list[NonBlankText] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_unique_arrays(self) -> "LocationCreateV1":
        """拒绝地点内容中的规范重复数组项。

        Args:
            self: 已完成字段级校验的创建请求。

        Returns:
            数组内容规范唯一的当前请求。
        """
        _validate_unique_texts(
            self.name,
            self.aliases,
            self.rules_and_constraints,
            self.applicable_rule_ids,
            self.associated_faction_ids,
            self.tags,
        )
        return self


class LocationUpdateV1(StrictRequestModel):
    "Cập nhật một phần một địa điểm chính thức theo phiên bản công khai."

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    aliases: list[NonBlankText] | None = Field(default=None, max_length=10)
    location_type: str | None = Field(default=None, min_length=1, max_length=40)
    parent_location_id: LocationId | None = None
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    environment: str | None = Field(default=None, max_length=1000)
    atmosphere: str | None = Field(default=None, max_length=1000)
    geography: str | None = Field(default=None, max_length=1000)
    rules_and_constraints: list[NonBlankText] | None = Field(
        default=None,
        max_length=20,
    )
    applicable_rule_ids: list[RuleId] | None = Field(default=None, max_length=50)
    associated_faction_ids: list[FactionId] | None = Field(
        default=None,
        max_length=50,
    )
    story_function: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "inactive"] | None = None
    tags: list[NonBlankText] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "LocationUpdateV1":
        """拒绝空更新与除父级外的显式 null。

        Args:
            self: 已完成字段级校验的更新请求。

        Returns:
            至少包含一个合法业务字段的当前请求。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Cập nhật địa điểm cần ít nhất một trường nghiệp vụ")
        for field in fields - {"parent_location_id"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt tường minh thành null")
        return self


class LocationReorderItemV1(StrictRequestModel):
    "Một mục phiên bản địa điểm trong lệnh sắp xếp lại đầy đủ cùng cha."

    location_id: LocationId
    order_index: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class LocationReorderRequestV1(StrictRequestModel):
    "Yêu cầu sắp xếp lại, gửi đầy đủ toàn bộ địa điểm hoạt động dưới một mục cha."

    parent_location_id: LocationId | None
    items: list[LocationReorderItemV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> "LocationReorderRequestV1":
        """要求重排 ID 唯一且目标顺序恰为 1..N。

        Args:
            self: 已完成字段级校验的重排请求。

        Returns:
            ID 和顺序均完整唯一的当前请求。
        """
        ids = [item.location_id for item in self.items]
        orders = [item.order_index for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("location_id sắp xếp lại không được trùng lặp")
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("order_index khi sắp xếp phải liên tục đầy đủ 1..N")
        return self


class LocationVersionRequestV1(StrictRequestModel):
    "Phiên bản công khai dùng cho các lệnh vòng đời như khôi phục địa điểm."

    expected_version: int = Field(ge=1)


class VolumeLocationsGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    "Yêu cầu xem trước ứng viên địa điểm theo nhu cầu cho một quyển."

    location_count: int = Field(ge=0, le=20)
    selection_mode: Literal["manual", "auto"] = "manual"
    volume_expected_version: int = Field(ge=1)
    allow_incremental: bool
    selected_existing_location_ids: list[LocationId] = Field(max_length=50)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)
    use_stream: bool = True

    @model_validator(mode="after")
    def validate_selected_locations(self) -> "VolumeLocationsGenerateRequestV1":
        """拒绝重复选择同一个既有地点。

        Args:
            self: 已完成字段级校验的预览请求。

        Returns:
            既有地点选择唯一的当前请求。
        """
        if self.selection_mode == "manual" and self.location_count == 0:
            raise ValueError("Số lượng địa điểm sinh thủ công phải ít nhất là 1")
        if len(self.selected_existing_location_ids) != len(
            set(self.selected_existing_location_ids)
        ):
            raise ValueError("selected_existing_location_ids không được trùng lặp")
        return self


class VolumeLocationsGenerationInputV1(ReasoningOptions, StrictRequestModel):
    "Đầu vào tạo địa điểm cho một quyển, gửi lại cùng basis và dùng để tính lại khi xác nhận."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    location_count: int = Field(ge=0, le=20)
    selection_mode: Literal["manual", "auto"] = "manual"
    volume_expected_version: int = Field(ge=1)
    allow_incremental: bool
    selected_existing_location_ids: list[LocationId] = Field(max_length=50)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @model_validator(mode="after")
    def validate_selected_locations(self) -> "VolumeLocationsGenerationInputV1":
        """确保 basis 中的既有地点选择仍保持唯一。

        Args:
            self: 当前严格生成输入。

        Returns:
            既有地点选择唯一的当前输入。
        """
        if self.selection_mode == "manual" and self.location_count == 0:
            raise ValueError("Số lượng địa điểm sinh thủ công phải ít nhất là 1")
        if len(self.selected_existing_location_ids) != len(
            set(self.selected_existing_location_ids)
        ):
            raise ValueError("selected_existing_location_ids không được trùng lặp")
        return self


class GeneratedLocationCandidateV1(StrictRequestModel):
    "Một ứng viên địa điểm có thể chỉnh sửa sau V2-WLD-05 rồi chuyển cho bước xác nhận domain chính thức."

    candidate_ref: LocationCandidateRef
    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(max_length=10)
    location_type: str = Field(min_length=1, max_length=40)
    parent_location_ref: LocationCandidateRef | None = None
    parent_location_id: LocationId | None = None
    description: str = Field(min_length=1, max_length=2000)
    environment: str = Field(max_length=1000)
    atmosphere: str = Field(max_length=1000)
    geography: str = Field(max_length=1000)
    rules_and_constraints: list[NonBlankText] = Field(max_length=20)
    applicable_rule_ids: list[RuleId] = Field(max_length=50)
    associated_faction_ids: list[FactionId] = Field(max_length=50)
    story_function: str = Field(min_length=1, max_length=1000)
    tags: list[NonBlankText] = Field(max_length=20)

    @field_validator("candidate_ref", "parent_location_ref")
    @classmethod
    def normalize_candidate_refs(cls, value: str | None) -> str | None:
        """清理候选临时引用两端空白。

        Args:
            value: 候选自身或候选父级的临时引用。

        Returns:
            清理后的临时引用；未提供父级时返回 None。
        """
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("candidate_ref không được chỉ chứa khoảng trắng")
        return normalized

    @model_validator(mode="after")
    def validate_candidate_references(self) -> "GeneratedLocationCandidateV1":
        """校验父级引用互斥以及候选内容数组唯一性。

        Args:
            self: 已完成字段级校验的地点候选。

        Returns:
            父级与数组组合合法的当前候选。
        """
        if self.parent_location_ref is not None and self.parent_location_id is not None:
            raise ValueError("Chỉ được cung cấp một trong parent_location_ref hoặc parent_location_id")
        if self.parent_location_ref == self.candidate_ref:
            raise ValueError("Địa điểm ứng viên không được lấy chính nó làm cấp cha")
        _validate_unique_texts(
            self.name,
            self.aliases,
            self.rules_and_constraints,
            self.applicable_rule_ids,
            self.associated_faction_ids,
            self.tags,
        )
        return self


class LocationCandidateV1(GeneratedLocationCandidateV1):
    """模型可输出且用户可编辑的一条单卷地点候选。"""


class VolumeLocationsResultV1(StrictRequestModel):
    "Đối tượng gốc của ứng viên địa điểm một quyển mà Provider phải trả về đầy đủ."

    locations: list[LocationCandidateV1] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_candidate_topology(self) -> "VolumeLocationsResultV1":
        """拒绝重复引用以及未在前文声明的候选父级。

        Args:
            self: 已通过候选字段校验的模型结果。

        Returns:
            候选引用唯一且父级按拓扑前向排列的当前结果。
        """
        seen: set[str] = set()
        for candidate in self.locations:
            if candidate.candidate_ref in seen:
                raise ValueError("candidate_ref không được trùng lặp")
            if (
                candidate.parent_location_ref is not None
                and candidate.parent_location_ref not in seen
            ):
                raise ValueError("parent_location_ref chỉ được tham chiếu ứng viên đứng trước trong lô này")
            seen.add(candidate.candidate_ref)
        return self


class VolumeLocationsBasisV1(CandidateBasisV1):
    "Căn cứ ứng viên địa điểm của một quyển, gồm quyển đích và yêu cầu gốc."

    generation_input: VolumeLocationsGenerationInputV1
    content_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_volume_locations_contract(self) -> "VolumeLocationsBasisV1":
        """确保 basis 元数据、小说和目标卷属于单卷地点工作流。

        Args:
            self: 已通过公共 basis 校验的依据。

        Returns:
            契约及关键来源一致的当前依据。
        """
        if (
            self.workflow != "create_locations_for_volume_by_ai"
            or self.step != "create_locations_for_volume"
            or self.schema_id != VOLUME_LOCATIONS_RESULT_SCHEMA_ID
            or self.schema_version != VOLUME_LOCATIONS_RESULT_SCHEMA_VERSION
            or self.novel_id != self.generation_input.novel_id
        ):
            raise ValueError("Hợp đồng basis của địa điểm theo từng quyển không khớp")
        novel_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "novel" and source.id == self.novel_id
        ]
        target_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "volume"
            and source.id == self.generation_input.volume_id
        ]
        if len(novel_refs) != 1:
            raise ValueError("basis địa điểm đơn quyển phải bao gồm chính xác nguồn của tiểu thuyết hiện tại")
        if (
            len(target_refs) != 1
            or (self.generation_input.selection_mode != "auto" and target_refs[0].version
            != self.generation_input.volume_expected_version)
        ):
            raise ValueError("basis địa điểm đơn quyển phải chứa phiên bản chính xác của quyển đích")
        location_source_ids = {
            source.id
            for source in self.source_refs
            if source.resource_type == "location"
        }
        if not set(self.generation_input.selected_existing_location_ids).issubset(
            location_source_ids
        ):
            raise ValueError("basis địa điểm đơn quyển thiếu nguồn địa điểm hiện có đã được chọn")
        return self


class VolumeLocationsPreviewV1(StrictResponseModel):
    "Bao ứng viên địa điểm của một quyển, dùng chung cho phản hồi thường và done.result của SSE."

    workflow: Literal["create_locations_for_volume_by_ai"]
    step: Literal["create_locations_for_volume"]
    schema_id: Literal["volume_locations_result"]
    schema_version: Literal[1]
    candidate: VolumeLocationsResultV1
    basis: VolumeLocationsBasisV1


class LocationBulkGeneratedRequestV1(StrictRequestModel):
    "Phong bì nghiêm ngặt để xác nhận cả loạt ứng viên AI của địa điểm."

    candidates: list[GeneratedLocationCandidateV1] = Field(max_length=20)
    basis: VolumeLocationsBasisV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在类型转换前拒绝空键、字符串或布尔版本。

        Args:
            value: 客户端提交的原始版本映射。

        Returns:
            仅含正整数版本的原映射。
        """
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
    def validate_confirmation(self) -> "LocationBulkGeneratedRequestV1":
        """校验拓扑前向引用、候选引用和版本映射完整性。

        Args:
            self: 已完成嵌套 DTO 校验的确认请求。

        Returns:
            可交给 Location Service 的严格确认请求。
        """
        if not self.candidates and self.basis.generation_input.selection_mode != "auto":
            raise ValueError("Xác nhận sinh thủ công cần ít nhất một ứng viên địa điểm")
        expected = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected:
            raise ValueError("expected_versions phải khớp chính xác basis.source_refs")
        seen: set[str] = set()
        for candidate in self.candidates:
            if candidate.candidate_ref in seen:
                raise ValueError("candidate_ref không được trùng lặp")
            if (
                candidate.parent_location_ref is not None
                and candidate.parent_location_ref not in seen
            ):
                raise ValueError("parent_location_ref chỉ được tham chiếu ứng viên đứng trước trong lô này")
            seen.add(candidate.candidate_ref)
        return self


class LocationReadV1(StrictResponseModel):
    "Phản chiếu công khai đầy đủ của địa điểm chính thức."

    location_id: LocationId
    novel_id: ObjectIdString
    name: str = Field(min_length=1, max_length=80)
    aliases: list[NonBlankText] = Field(max_length=10)
    location_type: str = Field(min_length=1, max_length=40)
    parent_location_id: LocationId | None
    description: str = Field(min_length=1, max_length=2000)
    environment: str = Field(max_length=1000)
    atmosphere: str = Field(max_length=1000)
    geography: str = Field(max_length=1000)
    rules_and_constraints: list[NonBlankText] = Field(max_length=20)
    applicable_rule_ids: list[RuleId] = Field(max_length=50)
    associated_faction_ids: list[FactionId] = Field(max_length=50)
    story_function: str = Field(max_length=1000)
    status: Literal["active", "inactive"]
    tags: list[NonBlankText] = Field(max_length=20)
    order_index: int = Field(ge=1)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocationDeleteImpactV1(StrictResponseModel):
    "Ảnh hưởng tới các con trực tiếp và các bên tiêu dùng được bảo vệ trước khi xóa địa điểm."

    location_id: LocationId
    direct_child_location_ids: list[LocationId]
    active_direct_children: int = Field(ge=0)
    deleted_direct_children: int = Field(ge=0)
    world_rules: int = Field(ge=0)
    volumes: int = Field(default=0, ge=0)
    arcs: int = Field(ge=0)
    chapters: int = Field(ge=0)
    scenes: int = Field(ge=0)
    items: int = Field(ge=0)
    foreshadowings: int = Field(ge=0)
    total_protected_references: int = Field(ge=0)
    has_children: bool
    has_protected_references: bool


class LocationHardDeleteResponseV1(StrictResponseModel):
    "Kết quả xoá vĩnh viễn địa điểm cùng tác động không còn tham chiếu ở bước cuối."

    message: Literal["Hard deleted successfully"]
    location_id: LocationId
    impact: LocationDeleteImpactV1


class LocationBulkGeneratedResponseV1(StrictResponseModel):
    "Ánh xạ ứng viên địa điểm và ảnh chụp nhanh địa điểm chính thức sau khi ghi."

    candidate_ref_map: dict[LocationCandidateRef, LocationId]
    locations: list[LocationReadV1] = Field(max_length=20)


__all__ = [
    "FACTION_ID_PATTERN",
    "LOCATION_ID_PATTERN",
    "RULE_ID_PATTERN",
    "VOLUME_LOCATIONS_RESULT_SCHEMA_ID",
    "VOLUME_LOCATIONS_RESULT_SCHEMA_VERSION",
    "GeneratedLocationCandidateV1",
    "LocationCandidateV1",
    "LocationBulkGeneratedRequestV1",
    "LocationBulkGeneratedResponseV1",
    "LocationCreateV1",
    "LocationDeleteImpactV1",
    "LocationHardDeleteResponseV1",
    "LocationReadV1",
    "LocationReorderItemV1",
    "LocationReorderRequestV1",
    "LocationUpdateV1",
    "LocationVersionRequestV1",
    "VolumeLocationsBasisV1",
    "VolumeLocationsGenerateRequestV1",
    "VolumeLocationsGenerationInputV1",
    "VolumeLocationsPreviewV1",
    "VolumeLocationsResultV1",
    "normalize_location_text",
]
