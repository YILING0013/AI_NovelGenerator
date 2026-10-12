"""章节修订的只读响应；正文仍由原章节接口返回。"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.services.novel.chapter_contract import ChapterPlanV2, ChapterReadV2


class ChapterRevisionSummaryV1(StrictResponseModel):
    """历史列表不加载长正文，修订由章节 ID 和业务版本定位。"""

    revision_id: ObjectIdString
    chapter_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    arc_id: ObjectIdString
    scene_id: ObjectIdString
    version: int = Field(ge=1)
    parent_version: int | None = Field(ge=1)
    title: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: Literal["baseline", "create", "edit", "writing", "assistant", "restore"]
    saved_at: datetime
    restored_from_version: int | None = Field(default=None, ge=1)


class ChapterRevisionReadV1(ChapterRevisionSummaryV1):
    """保留当时标题、摘要、计划与完整正文。"""

    summary: str
    planning: ChapterPlanV2
    content: str


class ChapterRevisionListV1(StrictResponseModel):
    """按版本倒序返回章节历史。"""

    data: list[ChapterRevisionSummaryV1]
    next_before_version: int | None = Field(ge=1)


class ChapterRevisionRestoreV1(StrictRequestModel):
    """明确按已读章节版本恢复整份旧稿。"""

    expected_version: int = Field(ge=1)


class ChapterRevisionCompareV1(StrictResponseModel):
    """同一读取中的旧稿和当前章，标出实际变化的字段。"""

    revision: ChapterRevisionReadV1
    current: ChapterReadV2
    changed_fields: list[Literal["title", "summary", "planning", "content"]]
    restore_normalizes_text: bool


class ChapterHistoryDeleteImpactV1(StrictResponseModel):
    """永久删除前显示并绑定作者确认的历史数量。"""

    chapter_id: ObjectIdString
    foreshadowings: int = Field(default=0, ge=0)
    chapter_records: int = Field(default=0, ge=0)
    version: int = Field(ge=1)
    revision_count: int = Field(ge=0)


def serialize_chapter_revision(document: dict, *, include_content: bool = True) -> dict:
    """公开修订内容并转换 BSON 身份，不公开内部字段。

    Args:
        document: 原始修订。
        include_content: 详情包含内容，列表只包含定位信息。
    Returns:
        可由响应模型验证的修订。
    """
    model = ChapterRevisionReadV1 if include_content else ChapterRevisionSummaryV1
    identities = {"chapter_id", "novel_id", "volume_id", "arc_id", "scene_id"}
    result = {name: document[name] for name in model.model_fields if name not in identities | {"revision_id", "restored_from_version"}}
    result["restored_from_version"] = document.get("restored_from_version")
    result.update(revision_id=str(document["_id"]), **{name: str(document[name]) for name in identities})
    return result
