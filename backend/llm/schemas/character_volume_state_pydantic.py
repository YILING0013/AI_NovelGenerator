"""角色卷级参与状态的严格请求与公开响应契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel


CHARACTER_ID_PATTERN = r"^char_[0-9]{6,}$"
CHARACTER_RELATION_ID_PATTERN = r"^cr_[0-9]{6,}$"

CharacterId = Annotated[str, Field(pattern=CHARACTER_ID_PATTERN)]
CharacterRelationId = Annotated[str, Field(pattern=CHARACTER_RELATION_ID_PATTERN)]
ParticipationScope: TypeAlias = Literal["primary", "secondary", "background"]
DeletionSource: TypeAlias = Literal["user", "volume", "character"]


class CharacterVolumePlanFieldsV1(StrictRequestModel):
    "Bố trí và kế hoạch tham gia của nhân vật trong quyển này, không nhận hoàn cảnh thực tế."

    participation_scope: ParticipationScope
    current_goal: str = Field(min_length=1, max_length=1000)
    start_state: str = Field(min_length=1, max_length=2000)
    planned_end_state: str = Field(default="", max_length=2000)
    relationship_focus_ids: list[CharacterRelationId] = Field(
        default_factory=list,
        max_length=30,
    )
    arc_progress: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_relationship_focus_ids(self) -> "CharacterVolumePlanFieldsV1":
        """拒绝重复的关系焦点 ID。

        Args:
            无。

        Returns:
            校验通过的完整业务字段。
        """
        if len(self.relationship_focus_ids) != len(set(self.relationship_focus_ids)):
            raise ValueError("relationship_focus_ids không được trùng lặp")
        return self


class CharacterVolumePlanCreateV1(CharacterVolumePlanFieldsV1):
    """建立本卷参与与计划；实际处境仅由事实记录提供。"""


class CharacterVolumeStateFieldsV1(CharacterVolumePlanFieldsV1):
    "Các trường nghiệp vụ đầy đủ của trạng thái nhân vật theo quyển cũ, giữ nguyên hình dạng yêu cầu gốc."

    psychological_state: str = Field(default="", max_length=1000)
    public_state: str = Field(default="", max_length=1000)
    hidden_state: str = Field(default="", max_length=1000)


class CharacterVolumeStateUpsertV1(CharacterVolumeStateFieldsV1):
    "Yêu cầu tạo mới hoặc cập nhật đầy đủ trạng thái theo đường dẫn phức hợp quyển và nhân vật."

    expected_version: int | None = Field(default=None, ge=1)


class CharacterVolumePlanUpdateV1(StrictRequestModel):
    "Cập nhật cục bộ mức tham gia và kế hoạch trong quyển theo ObjectId trạng thái."

    expected_version: int = Field(ge=1)
    participation_scope: ParticipationScope | None = None
    current_goal: str | None = Field(default=None, min_length=1, max_length=1000)
    start_state: str | None = Field(default=None, min_length=1, max_length=2000)
    planned_end_state: str | None = Field(default=None, max_length=2000)
    relationship_focus_ids: list[CharacterRelationId] | None = Field(
        default=None,
        max_length=30,
    )
    arc_progress: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "CharacterVolumePlanUpdateV1":
        """拒绝空更新、显式 null 和重复关系焦点。

        Args:
            无。

        Returns:
            校验通过的局部更新请求。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Cập nhật trạng thái quyển của nhân vật cần ít nhất một trường nghiệp vụ")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt tường minh thành null")
        if self.relationship_focus_ids is not None and len(
            self.relationship_focus_ids
        ) != len(set(self.relationship_focus_ids)):
            raise ValueError("relationship_focus_ids không được trùng lặp")
        return self


class CharacterVolumeStateUpdateV1(CharacterVolumePlanUpdateV1):
    "Cập nhật cục bộ trạng thái nhân vật theo quyển cũ, giữ ba trường hoàn cảnh thực tế."

    psychological_state: str | None = Field(default=None, max_length=1000)
    public_state: str | None = Field(default=None, max_length=1000)
    hidden_state: str | None = Field(default=None, max_length=1000)


class CharacterVolumeStateVersionRequestV1(StrictRequestModel):
    "Yêu cầu phiên bản cho lệnh vòng đời trạng thái nhân vật theo quyển."

    expected_version: int = Field(ge=1)


class CharacterVolumeStateInitializeV1(StrictRequestModel):
    "Yêu cầu khởi tạo hàng loạt các nhân vật đã chọn từ quyển chính thức trước đó."

    character_ids: list[CharacterId] = Field(min_length=1, max_length=500)
    skip_existing: Literal[False] = False

    @model_validator(mode="after")
    def validate_unique_character_ids(self) -> "CharacterVolumeStateInitializeV1":
        """要求初始化角色 ID 唯一且采用目标冲突零写策略。

        Args:
            无。

        Returns:
            校验通过的初始化请求。
        """
        if len(self.character_ids) != len(set(self.character_ids)):
            raise ValueError("character_ids không được trùng lặp")
        return self


class CharacterVolumeStateReadV1(StrictResponseModel):
    "Bản chiếu công khai đầy đủ của một trạng thái tham gia cấp quyển của nhân vật."

    state_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    character_id: CharacterId
    participation_scope: ParticipationScope
    current_goal: str = Field(min_length=1, max_length=1000)
    start_state: str = Field(min_length=1, max_length=2000)
    planned_end_state: str = Field(max_length=2000)
    psychological_state: str = Field(max_length=1000)
    public_state: str = Field(max_length=1000)
    hidden_state: str = Field(max_length=1000)
    relationship_focus_ids: list[CharacterRelationId] = Field(max_length=30)
    arc_progress: int = Field(ge=0, le=100)
    source_state_id: ObjectIdString | None
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    deletion_sources: list[DeletionSource] = Field(max_length=3)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle_projection(self) -> "CharacterVolumeStateReadV1":
        """拒绝生命周期来源与删除审计互相矛盾的公开记录。

        Args:
            无。

        Returns:
            生命周期一致的公开状态。
        """
        if len(self.deletion_sources) != len(set(self.deletion_sources)):
            raise ValueError("deletion_sources không được trùng lặp")
        if self.is_deleted != bool(self.deletion_sources):
            raise ValueError("is_deleted phải nhất quán với deletion_sources")
        if self.is_deleted != (self.deleted_at is not None):
            raise ValueError("deleted_at phải nhất quán với trạng thái xóa")
        return self


class CharacterVolumeStateListV1(StrictResponseModel):
    "Vỏ phản hồi nghiêm ngặt dùng chung cho danh sách quyển và lịch sử nhân vật."

    data: list[CharacterVolumeStateReadV1]


class CharacterVolumeStateInitializeResultV1(StrictResponseModel):
    "Kết quả nghiêm ngặt sau khi khởi tạo thành công từ quyển trước."

    source_volume_id: ObjectIdString
    target_volume_id: ObjectIdString
    states: list[CharacterVolumeStateReadV1]


class CharacterVolumeStateHardDeleteV1(StrictResponseModel):
    "Kết quả xoá vĩnh viễn trạng thái nhân vật theo quyển."

    deleted: Literal[True]
    state_id: ObjectIdString


class CharacterVolumeArcReadinessV1(StrictResponseModel):
    "Kết quả cổng kiểm tra trạng thái nhân vật chính trước khi quyển bước vào kế hoạch vòng cung nhân vật."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    ready: bool
    active_protagonist_ids: list[CharacterId]
    protagonist_state_character_ids: list[CharacterId]


__all__ = [
    "CHARACTER_ID_PATTERN",
    "CHARACTER_RELATION_ID_PATTERN",
    "CharacterVolumeArcReadinessV1",
    "CharacterVolumePlanCreateV1",
    "CharacterVolumePlanFieldsV1",
    "CharacterVolumePlanUpdateV1",
    "CharacterVolumeStateFieldsV1",
    "CharacterVolumeStateHardDeleteV1",
    "CharacterVolumeStateInitializeResultV1",
    "CharacterVolumeStateInitializeV1",
    "CharacterVolumeStateListV1",
    "CharacterVolumeStateReadV1",
    "CharacterVolumeStateUpdateV1",
    "CharacterVolumeStateUpsertV1",
    "CharacterVolumeStateVersionRequestV1",
    "DeletionSource",
    "ParticipationScope",
]
