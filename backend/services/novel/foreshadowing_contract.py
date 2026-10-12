"""伏笔计划、作者确认的章节证据和回收站接口。"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel


ForeshadowingStatus = Literal["planned", "planted", "resolved", "abandoned"]
FORESHADOWING_ID_PATTERN = r"^fo_[0-9]{6,}$"


class ForeshadowingPositionV1(StrictRequestModel):
    """计划只指向稳定位置；未细化的卷也可以使用。"""

    kind: Literal["volume", "arc", "scene"]
    id: ObjectIdString


class ForeshadowingEvidenceInputV1(StrictRequestModel):
    """引用已保存修订中的原文，start 从零按 Unicode 码点计算。"""

    # 原文空白也是证据，不能沿用普通表单的首尾清理。
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    chapter_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    start: int = Field(ge=0, le=2**31 - 1, description="从零开始的 Unicode 码点位置；JS 应先用 Array.from(content) 转为码点数组。")
    quote: str = Field(min_length=1, max_length=10000)


class ForeshadowingEvidenceV1(ForeshadowingEvidenceInputV1):
    """服务端绑定修订和正文摘要，不随当前正文变化。"""

    revision_id: ObjectIdString
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ForeshadowingCreateV1(StrictRequestModel):
    """人工创建计划，状态固定为尚未埋设。"""

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    target_effect: str = Field(default="", max_length=12000)
    planting_position: ForeshadowingPositionV1 | None = None
    resolution_position: ForeshadowingPositionV1 | None = None


class ForeshadowingUpdateV1(StrictRequestModel):
    """局部改计划；状态和实际证据只走作者确认接口。"""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    target_effect: str | None = Field(default=None, max_length=12000)
    planting_position: ForeshadowingPositionV1 | None = None
    resolution_position: ForeshadowingPositionV1 | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "ForeshadowingUpdateV1":
        """拒绝空更新和文本 null，位置 null 表示明确清除。

        Args:
            无。
        Returns:
            校验通过的局部计划。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, name) is None for name in fields & {"title", "content", "target_effect"}):
            raise ValueError("至少修改一个计划字段，文本不能设为 null")
        return self


class ForeshadowingRecordV1(StrictRequestModel):
    """作者明确选择状态，可同时替换或清除两份实际证据。"""

    expected_version: int = Field(ge=1)
    status: ForeshadowingStatus
    planted_evidence: ForeshadowingEvidenceInputV1 | None = None
    resolved_evidence: ForeshadowingEvidenceInputV1 | None = None


class ForeshadowingVersionV1(StrictRequestModel):
    """回收、恢复和永久删除使用作者已读版本。"""

    expected_version: int = Field(ge=1)


class ForeshadowingReadV1(StrictResponseModel):
    """伏笔详情及本次只读计算的复核状态。"""

    foreshadowing_id: str = Field(pattern=FORESHADOWING_ID_PATTERN)
    novel_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    target_effect: str = Field(max_length=12000)
    planting_position: ForeshadowingPositionV1 | None
    resolution_position: ForeshadowingPositionV1 | None
    status: ForeshadowingStatus
    planted_evidence: ForeshadowingEvidenceV1 | None
    resolved_evidence: ForeshadowingEvidenceV1 | None
    planted_needs_review: bool
    resolved_needs_review: bool
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


def serialize_foreshadowing(document: dict) -> dict:
    """只公开伏笔字段，不公开幂等键和数据库内部标记。

    Args:
        document: 已计算复核标记的伏笔文档。
    Returns:
        可由严格响应模型校验的数据。
    """
    result = {name: document[name] for name in ForeshadowingReadV1.model_fields}
    result["novel_id"] = str(result["novel_id"])
    return result
