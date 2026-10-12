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
    """势力在一卷内可人工维护的完整业务字段。"""

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
            raise ValueError("resources 不能重复")
        return self


class FactionVolumeStateUpsertV1(FactionVolumeStateFieldsV1):
    """按卷与势力复合路径创建或完整更新状态的请求。"""

    expected_version: int | None = Field(default=None, ge=1)


class FactionVolumeStateUpdateV1(StrictRequestModel):
    """按状态 ObjectId 局部更新业务字段的请求。"""

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
            raise ValueError("势力卷状态更新至少需要一个业务字段")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能显式设为 null")
        if self.resources is not None and len(self.resources) != len(set(self.resources)):
            raise ValueError("resources 不能重复")
        return self


class FactionVolumeStateVersionRequestV1(StrictRequestModel):
    """势力卷状态生命周期命令的版本请求。"""

    expected_version: int = Field(ge=1)


class FactionVolumeStateInitializeV1(StrictRequestModel):
    """从上一正式卷批量初始化选中势力的请求。"""

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
            raise ValueError("faction_ids 不能重复")
        return self


class FactionVolumeStateReadV1(StrictResponseModel):
    """一条势力卷级参与状态的完整公开投影。"""

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
    public_stance: str = Field(max_length=1000)
    hidden_agenda: str = Field(max_length=1000)
    influence_scope: str = Field(max_length=1000)
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
            raise ValueError("deletion_sources 不能重复")
        if self.is_deleted != bool(self.deletion_sources):
            raise ValueError("is_deleted 必须与 deletion_sources 一致")
        if self.is_deleted != (self.deleted_at is not None):
            raise ValueError("deleted_at 必须与删除态一致")
        return self


class FactionVolumeStateListV1(StrictResponseModel):
    """卷列表和势力历史共用的严格响应外壳。"""

    data: list[FactionVolumeStateReadV1]


class FactionVolumeStateInitializeResultV1(StrictResponseModel):
    """从上一卷初始化成功后的严格结果。"""

    source_volume_id: ObjectIdString
    target_volume_id: ObjectIdString
    states: list[FactionVolumeStateReadV1]


class FactionVolumeStateHardDeleteV1(StrictResponseModel):
    """势力卷状态永久删除结果。"""

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
