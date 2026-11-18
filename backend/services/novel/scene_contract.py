"""篇章下场景规划和回收站的公开字段。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.services.novel.arc_contract import ArcPlanningV1


class ScenePlanningV1(ArcPlanningV1):
    """场景沿用篇章规划字段，可关联多个地点，不保存正文。"""


class SceneCreateV1(StrictRequestModel):
    "Tạo một cảnh trong vòng truyện hiện tại."

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2000)
    planning: ScenePlanningV1 = Field(default_factory=ScenePlanningV1)


class SceneUpdateV1(StrictRequestModel):
    "Chỉ sửa các trường được minh thị gửi; khi có planning thì thay thế toàn bộ kế hoạch."

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    planning: ScenePlanningV1 | None = None

    @model_validator(mode="after")
    def validate_update_fields(self) -> "SceneUpdateV1":
        """拒绝空更新与显式 null。

        Args:
            无。
        Returns:
            已校验的局部更新。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Cập nhật cảnh cần ít nhất một trường nội dung")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt thành null")
        return self


class SceneVersionV1(StrictRequestModel):
    "Phiên bản đã đọc dùng cho thao tác thùng rác."

    expected_version: int = Field(ge=1)


class SceneReadV1(StrictResponseModel):
    "Kế hoạch cảnh, chuỗi cha đầy đủ, thống kê và phiên bản hiện tại."

    scene_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    arc_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(max_length=2000)
    planning: ScenePlanningV1
    order_index: int = Field(ge=1)
    chapter_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SceneListV1(StrictResponseModel):
    "Danh sách cảnh thuộc vòng truyện hiện tại."

    data: list[SceneReadV1]


class SceneHardDeleteV1(StrictResponseModel):
    "Định danh cảnh khi xoá vĩnh viễn thành công."

    scene_id: ObjectIdString
    deleted: bool


class SceneReorderItemV1(StrictRequestModel):
    "Thứ tự mới và phiên bản gốc của một cảnh đang hoạt động."

    scene_id: ObjectIdString
    expected_version: int = Field(ge=1)
    order_index: int = Field(ge=1)


class SceneReorderV1(StrictRequestModel):
    "Toàn bộ thứ tự cảnh đang hoạt động của vòng truyện hiện tại."

    items: list[SceneReorderItemV1] = Field(min_length=1, max_length=10000)


class SceneDeleteImpactV1(StrictResponseModel):
    "Số chương thực tế tồn tại trước khi xoá cảnh."

    scene_id: ObjectIdString
    foreshadowings: int = Field(default=0, ge=0)
    chapter_records: int = Field(default=0, ge=0)
    chapters: int = Field(ge=0)
    active_chapters: int = Field(ge=0)
    deleted_chapters: int = Field(ge=0)
    total: int = Field(ge=0)
    has_blockers: bool


def serialize_scene(document: dict[str, Any]) -> dict[str, Any]:
    """只返回场景公开字段。

    Args:
        document: 完整数据库文档。
    Returns:
        不含内部幂等字段的响应。
    """
    identities = {"scene_id", "novel_id", "volume_id", "arc_id"}
    result = {name: document[name] for name in SceneReadV1.model_fields if name not in identities}
    result.update(scene_id=str(document["_id"]), novel_id=str(document["novel_id"]), volume_id=str(document["volume_id"]), arc_id=str(document["arc_id"]))
    return result
