"""篇章规划、局部编辑和回收站的公开契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, ValidationInfo, field_validator, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel, is_business_id


class ArcPlanningV1(StrictRequestModel):
    "Mục tiêu vòng truyện, trạng thái đầu và cuối, nhịp truyện cùng các tham chiếu thực thể của tiểu thuyết hiện tại."

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
            raise ValueError(f"{info.field_name} phải là ID nghiệp vụ của thực thể tương ứng")
        return value


class ArcCreateV1(StrictRequestModel):
    "Nội dung được phép gửi khi tạo vòng truyện dưới một quyển."

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2000)
    planning: ArcPlanningV1 = Field(default_factory=ArcPlanningV1)
    plot: str = Field(default="", max_length=40000)


class ArcUpdateV1(StrictRequestModel):
    "Trường bị lược giữ nguyên giá trị cũ; nếu cung cấp planning thì thay thế toàn bộ kế hoạch."

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
            raise ValueError("Cập nhật vòng truyện cần ít nhất một trường nội dung")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt thành null")
        return self


class ArcVersionV1(StrictRequestModel):
    "Phiên bản đã đọc phải kèm theo khi khôi phục vòng truyện."

    expected_version: int = Field(ge=1)


class ArcReadV1(StrictResponseModel):
    "Nội dung đầy đủ, thông tin trực thuộc, thống kê và phiên bản hiện tại của vòng truyện."

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
    "Các vòng truyện sắp xếp theo thứ tự trong quyển."

    data: list[ArcReadV1]


class ArcHardDeleteV1(StrictResponseModel):
    "Định danh vòng truyện sau khi hoàn tất xoá vĩnh viễn."

    arc_id: ObjectIdString
    deleted: bool


class ArcReorderItemV1(StrictRequestModel):
    "Số thứ tự mới của một vòng truyện đang hoạt động và phiên bản đã đọc."

    arc_id: ObjectIdString
    expected_version: int = Field(ge=1)
    order_index: int = Field(ge=1)


class ArcReorderV1(StrictRequestModel):
    "Toàn bộ thứ tự vòng truyện đang hoạt động của quyển hiện tại."

    items: list[ArcReorderItemV1] = Field(min_length=1, max_length=10000)


class ArcDeleteImpactV1(StrictResponseModel):
    "Số cảnh và số chương thực tế tồn tại trước khi xoá vòng truyện."

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
