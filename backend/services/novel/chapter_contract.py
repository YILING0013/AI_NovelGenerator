"""场景下章计划、正文、目录与保存请求。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel, is_business_id


class ChapterPlanV2(StrictRequestModel):
    """当前章节计划；正文单独保存，人物视角可暂不选择。"""

    goal: str = Field(default="", max_length=2000)
    start_state: str = Field(default="", max_length=2000)
    end_state: str = Field(default="", max_length=2000)
    beats: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=30)
    pov_character_id: str | None = None
    must_include: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=30)
    must_avoid: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=30)
    target_word_count: int | None = Field(default=None, gt=0)

    @field_validator("pov_character_id")
    @classmethod
    def validate_pov(cls, value: str | None) -> str | None:
        """要求视角人物使用正式人物 ID。

        Args:
            value: 人物业务 ID 或未选择。
        Returns:
            已校验的原值。
        """
        if value is not None and not is_business_id("character", value):
            raise ValueError("pov_character_id 必须填写人物业务 ID")
        return value


class ChapterCreateV2(StrictRequestModel):
    """场景下的标题、章计划和可选正文。"""

    # 正文缩进和首尾空行属于作品内容，不沿用请求基类的 strip。
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2000)
    planning: ChapterPlanV2 = Field(default_factory=ChapterPlanV2)
    content: str = Field(default="", max_length=100000)

    @field_validator("title", mode="before")
    @classmethod
    def clean_title(cls, value: Any) -> Any:
        """只清理标题，保留正文空白。

        Args:
            value: 请求中的标题。
        Returns:
            去除首尾空白的标题，其余类型交给严格校验。
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("summary", "content", mode="before")
    @classmethod
    def normalize_newlines(cls, value: Any) -> Any:
        """统一换行而不清理段落和缩进。

        Args:
            value: 请求文本。
        Returns:
            统一使用换行符的原文。
        """
        return value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else value


class ChapterUpdateV2(ChapterCreateV2):
    """章计划和正文共用一个版本，省略字段不改变原值。"""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    planning: ChapterPlanV2 | None = None
    content: str | None = Field(default=None, max_length=100000)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "ChapterUpdateV2":
        """拒绝空更新和含糊的 null，清空正文须提交空字符串。

        Args:
            无。
        Returns:
            已校验的局部更新。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("章节更新至少需要一个内容字段")
        for field in fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能设为 null")
        return self


class ChapterVersionV2(StrictRequestModel):
    """章节回收站操作使用的版本。"""

    expected_version: int = Field(ge=1)


class ChapterSummaryV2(StrictResponseModel):
    """不含正文的章节目录；显示章号由当前阅读顺序计算。"""

    chapter_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    arc_id: ObjectIdString
    scene_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(max_length=2000)
    planning: ChapterPlanV2
    order_index: int = Field(ge=1)
    chapter_number: int | None = Field(default=None, ge=1)
    word_count: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChapterReadV2(StrictResponseModel):
    """当前章计划和正文。"""

    chapter_id: ObjectIdString
    novel_id: ObjectIdString
    volume_id: ObjectIdString
    arc_id: ObjectIdString
    scene_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(max_length=2000)
    planning: ChapterPlanV2
    content: str = Field(max_length=100000)
    order_index: int = Field(ge=1)
    word_count: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ChapterListV2(StrictResponseModel):
    """按父链顺序排列的章节目录。"""

    data: list[ChapterSummaryV2]


class ChapterHardDeleteV2(StrictResponseModel):
    """永久删除完成的章节标识。"""

    chapter_id: ObjectIdString
    deleted: bool


class ChapterReorderItemV2(StrictRequestModel):
    """一章的新场景内序号和已读版本。"""

    chapter_id: ObjectIdString
    expected_version: int = Field(ge=1)
    order_index: int = Field(ge=1)


class ChapterReorderV2(StrictRequestModel):
    """完整提交当前场景的活动章节排序。"""

    items: list[ChapterReorderItemV2] = Field(min_length=1, max_length=10000)


def serialize_chapter(document: dict[str, Any], *, include_content: bool = True) -> dict[str, Any]:
    """区分章节目录和详情，隐藏内部幂等字段。

    Args:
        document: 数据库文档或带派生章号的目录行。
        include_content: 详情包含正文，目录不包含。
    Returns:
        章节公开响应。
    """
    fields = ChapterReadV2.model_fields if include_content else ChapterSummaryV2.model_fields
    identities = {"chapter_id", "novel_id", "volume_id", "arc_id", "scene_id"}
    result = {name: document[name] for name in fields if name not in identities and name != "chapter_number"}
    if "chapter_number" in fields:
        result["chapter_number"] = document.get("chapter_number")
    result.update(chapter_id=str(document["_id"]), **{name: str(document[name]) for name in identities - {"chapter_id"}})
    return result
