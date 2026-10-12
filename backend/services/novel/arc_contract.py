"""篇章规划、局部编辑和回收站的公开契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel, is_business_id


class ArcPlanningV1(StrictRequestModel):
    """篇章目标、起止状态、节拍和当前小说的实体引用。"""

    goal: str = Field(default="", max_length=2000)
    start_state: str = Field(default="", max_length=2000)
    end_state: str = Field(default="", max_length=2000)
    key_beats: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=30)
    continuity_notes: str = Field(default="", max_length=2000)
    target_chapter_count: int | None = Field(default=None, gt=0)
    target_word_count: int | None = Field(default=None, gt=0)
    character_ids: list[str] = Field(default_factory=list, max_length=50)
    faction_ids: list[str] = Field(default_factory=list, max_length=50)
    location_ids: list[str] = Field(default_factory=list, max_length=50)
    item_ids: list[str] = Field(default_factory=list, max_length=50)
    rule_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("character_ids", "faction_ids", "location_ids", "item_ids", "rule_ids")
    @classmethod
    def validate_reference_ids(cls, value: list[str], info: ValidationInfo) -> list[str]:
        """要求引用使用对应实体的业务 ID。

        Args:
            value: 当前类别的引用数组。
            info: 正在校验的字段信息。

        Returns:
            校验通过的原数组。
        """
        entity_type = "world_rule" if info.field_name == "rule_ids" else info.field_name.removesuffix("_ids")
        if any(not is_business_id(entity_type, item) for item in value):
            raise ValueError(f"{info.field_name} 必须填写对应实体的业务 ID")
        return value


class ArcCreateV1(StrictRequestModel):
    """卷下创建篇章时允许提交的内容。"""

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2000)
    planning: ArcPlanningV1 = Field(default_factory=ArcPlanningV1)
    plot: str = Field(default="", max_length=40000)


class ArcUpdateV1(StrictRequestModel):
    """省略字段保留原值；提供 planning 时完整替换规划。"""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    planning: ArcPlanningV1 | None = None
    plot: str | None = Field(default=None, max_length=40000)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "ArcUpdateV1":
        """拒绝空更新和显式 null，清空规划应提交空对象。

        Args:
            无。

        Returns:
            已通过局部更新检查的请求。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("篇章更新至少需要一个内容字段")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能设为 null")
        return self


class ArcVersionV1(StrictRequestModel):
    """篇章恢复时必须携带的已读版本。"""

    expected_version: int = Field(ge=1)


class ArcReadV1(StrictResponseModel):
    """篇章完整内容、归属、统计和当前版本。"""

    arc_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(max_length=2000)
    planning: ArcPlanningV1
    plot: str = Field(default="", max_length=40000)
    plot_source_fingerprint: str | None = None
    order_index: int = Field(ge=1)
    scenes_count: int = Field(ge=0)
    chapter_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArcListV1(StrictResponseModel):
    """按卷内顺序排列的篇章。"""

    data: list[ArcReadV1]


class ArcHardDeleteV1(StrictResponseModel):
    """永久删除完成后的篇章标识。"""

    arc_id: ObjectIdString
    deleted: bool


class ArcReorderItemV1(StrictRequestModel):
    """一个活动篇章的新序号和已读版本。"""

    arc_id: ObjectIdString
    expected_version: int = Field(ge=1)
    order_index: int = Field(ge=1)


class ArcReorderV1(StrictRequestModel):
    """当前卷完整的活动篇章排序。"""

    items: list[ArcReorderItemV1] = Field(min_length=1, max_length=10000)


class ArcDeleteImpactV1(StrictResponseModel):
    """篇章删除前实际存在的场景和章节数量。"""

    arc_id: ObjectIdString
    foreshadowings: int = Field(default=0, ge=0)
    chapter_records: int = Field(default=0, ge=0)
    scenes: int = Field(ge=0)
    active_scenes: int = Field(ge=0)
    deleted_scenes: int = Field(ge=0)
    chapters: int = Field(ge=0)
    active_chapters: int = Field(ge=0)
    deleted_chapters: int = Field(ge=0)
    total: int = Field(ge=0)
    has_blockers: bool


def serialize_arc(document: dict[str, Any]) -> dict[str, Any]:
    """只返回篇章公开字段，隐藏创建幂等信息。

    Args:
        document: 从数据库读取的完整篇章。

    Returns:
        可由 ArcReadV1 验证的公开数据。
    """
    result = {name: document[name] for name in ArcReadV1.model_fields if name not in {"arc_id", "novel_id", "volume_id"} and name in document}
    result.update(arc_id=str(document["_id"]), novel_id=str(document["novel_id"]), volume_id=str(document["volume_id"]))
    return result
