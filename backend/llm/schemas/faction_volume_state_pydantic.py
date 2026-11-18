"""势力卷级参与状态的严格请求与公开响应契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel


FACTION_ID_PATTERN = r"^fac_[0-9]{6,}$"

FactionId = Annotated[str, Field(pattern=FACTION_ID_PATTERN)]
ParticipationScope: TypeAlias = Literal["primary", "secondary", "background"]
FactionStateStatus: TypeAlias = Literal["active", "dormant", "dissolved"]
DeletionSource: TypeAlias = Literal["user", "volume", "faction"]
ResourceText = Annotated[str, Field(min_length=1)]


class FactionVolumeStateFieldsV1(StrictRequestModel):
    "Các trường nghiệp vụ đầy đủ của thế lực trong một quyển mà con người có thể bảo trì."

    participation_scope: ParticipationScope
    current_goal: str = Field(min_length=1, max_length=1000)
    start_state: str = Field(min_length=1, max_length=2000)
    planned_end_state: str = Field(default="", max_length=2000)
    power_level: int = Field(ge=1, le=5)
    resources: list[ResourceText] = Field(default_factory=list, max_length=20)
    public_stance: str = Field(default="", max_length=1000)
    hidden_agenda: str = Field(default="", max_length=1000)
    influence_scope: str = Field(default="", max_length=1000)
    active_status: FactionStateStatus = "active"

    @model_validator(mode="after")
    def validate_resources(self) -> "FactionVolumeStateFieldsV1":
        """拒绝重复资源条目。

        Args:
            无。

        Returns:
            资源条目唯一的完整业务字段。
        """
        if len(self.resources) != len(set(self.resources)):
            raise ValueError("resources không được trùng lặp")
        return self


class FactionVolumeStateUpsertV1(FactionVolumeStateFieldsV1):
    "Yêu cầu tạo mới hoặc cập nhật đầy đủ trạng thái theo đường dẫn phức hợp quyển và thế lực."

    expected_version: int | None = Field(default=None, ge=1)


class FactionVolumeStateUpdateV1(StrictRequestModel):
    "Yêu cầu cập nhật cục bộ các trường nghiệp vụ theo ObjectId trạng thái."

    expected_version: int = Field(ge=1)
    participation_scope: ParticipationScope | None = None
    current_goal: str | None = Field(default=None, min_length=1, max_length=1000)
    start_state: str | None = Field(default=None, min_length=1, max_length=2000)
    planned_end_state: str | None = Field(default=None, max_length=2000)
    power_level: int | None = Field(default=None, ge=1, le=5)
    resources: list[ResourceText] | None = Field(default=None, max_length=20)
    public_stance: str | None = Field(default=None, max_length=1000)
    hidden_agenda: str | None = Field(default=None, max_length=1000)
    influence_scope: str | None = Field(default=None, max_length=1000)
    active_status: FactionStateStatus | None = None

    @model_validator(mode="after")
    def validate_update_fields(self) -> "FactionVolumeStateUpdateV1":
        """拒绝空更新、显式 null 和重复资源条目。

        Args:
            无。

        Returns:
            校验通过的局部更新请求。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Cập nhật trạng thái quyển của thế lực cần ít nhất một trường nghiệp vụ")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt tường minh thành null")
        if self.resources is not None and len(self.resources) != len(set(self.resources)):
            raise ValueError("resources không được trùng lặp")
        return self


class FactionVolumeStateVersionRequestV1(StrictRequestModel):
    "Yêu cầu phiên bản cho lệnh vòng đời trạng thái thế lực theo quyển."

    expected_version: int = Field(ge=1)


class FactionVolumeStateInitializeV1(StrictRequestModel):
    "Yêu cầu khởi tạo hàng loạt các thế lực đã chọn từ quyển chính thức trước đó."

    faction_ids: list[FactionId] = Field(min_length=1, max_length=500)
    skip_existing: Literal[False] = False

    @model_validator(mode="after")
    def validate_unique_faction_ids(self) -> "FactionVolumeStateInitializeV1":
        """要求初始化势力 ID 唯一并采用目标冲突零写策略。

        Args:
            无。

        Returns:
            校验通过的初始化请求。
        """
        if len(self.faction_ids) != len(set(self.faction_ids)):
            raise ValueError("faction_ids không được trùng lặp")
        return self


class FactionVolumeStateReadV1(StrictResponseModel):
    "Bản chiếu công khai đầy đủ của một trạng thái tham gia cấp quyển của thế lực."

    state_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    faction_id: FactionId
    participation_scope: ParticipationScope
    current_goal: str = Field(min_length=1, max_length=1000)
    start_state: str = Field(min_length=1, max_length=2000)
    planned_end_state: str = Field(max_length=2000)
    power_level: int = Field(ge=1, le=5)
    resources: list[ResourceText] = Field(max_length=20)
    # 旧未定位原文只读保留，不能用新写入长度拦住名册与无关计划修改。
    public_stance: str
    hidden_agenda: str = Field(max_length=1000)
    influence_scope: str
    active_status: FactionStateStatus
    source_state_id: ObjectIdString | None
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    deletion_sources: list[DeletionSource] = Field(max_length=3)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_lifecycle_projection(self) -> "FactionVolumeStateReadV1":
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


class FactionVolumePlanFieldsV1(StrictRequestModel):
    "Thiết kế tham gia quyển chỉ lưu kế hoạch, không bổ sung thực lực, tài nguyên hay trạng thái cốt truyện."

    participation_scope: ParticipationScope
    current_goal: str = Field(min_length=1, max_length=1000)
    start_state: str = Field(min_length=1, max_length=2000)
    planned_end_state: str = Field(default="", max_length=2000)
    hidden_agenda: str = Field(default="", max_length=1000)


class FactionVolumePlanUpdateV1(StrictRequestModel):
    "Chỉnh sửa kế hoạch quyển thông thường chỉ gửi các trường kế hoạch thực sự thay đổi."

    expected_version: int = Field(ge=1)
    participation_scope: ParticipationScope | None = None
    current_goal: str | None = Field(default=None, min_length=1, max_length=1000)
    start_state: str | None = Field(default=None, min_length=1, max_length=2000)
    planned_end_state: str | None = Field(default=None, max_length=2000)
    hidden_agenda: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_changes(self) -> "FactionVolumePlanUpdateV1":
        """拒绝空提交及显式 null；未提交旧原文不重新校验。"""
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, name) is None for name in fields):
            raise ValueError("Kế hoạch tham gia quyển cần ít nhất một thay đổi thực tế không null")
        return self


class FactionVolumePlanReadV1(FactionVolumeStateReadV1):
    "Kế hoạch tập mới đánh dấu rõ sự vắng mặt của dữ kiện; hợp đồng phản hồi trạng thái đầy đủ cũ giữ nguyên."

    content_contract: Literal["participation_plan_v1"]
    power_level: None = None
    resources: None = None
    public_stance: None = None
    influence_scope: None = None
    active_status: None = None


FactionVolumeReadV1: TypeAlias = FactionVolumeStateReadV1 | FactionVolumePlanReadV1


class FactionVolumeStateListV1(StrictResponseModel):
    "Vỏ phản hồi nghiêm ngặt dùng chung cho danh sách quyển và lịch sử thế lực."

    data: list[FactionVolumeStateReadV1 | FactionVolumePlanReadV1]


class FactionVolumeStateInitializeResultV1(StrictResponseModel):
    "Kết quả nghiêm ngặt sau khi khởi tạo thành công từ quyển trước."

    source_volume_id: ObjectIdString
    target_volume_id: ObjectIdString
    states: list[FactionVolumeStateReadV1 | FactionVolumePlanReadV1]


class FactionVolumeStateHardDeleteV1(StrictResponseModel):
    "Kết quả xoá vĩnh viễn trạng thái thế lực theo quyển."

    deleted: Literal[True]
    state_id: ObjectIdString


__all__ = [
    "FACTION_ID_PATTERN",
    "DeletionSource",
    "FactionStateStatus",
    "FactionVolumeStateFieldsV1",
    "FactionVolumeStateHardDeleteV1",
    "FactionVolumeStateInitializeResultV1",
    "FactionVolumeStateInitializeV1",
    "FactionVolumeStateListV1",
    "FactionVolumeStateReadV1",
    "FactionVolumeStateUpdateV1",
    "FactionVolumeStateUpsertV1",
    "FactionVolumeStateVersionRequestV1",
    "ParticipationScope",
]
