"""四类逐级规划与章节写作任务的输入和候选。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel
from backend.services.novel.arc_contract import ArcCreateV1, ArcPlanningV1
from backend.services.novel.scene_contract import SceneCreateV1
from backend.services.novel.chapter_contract import ChapterPlanV2


WRITING_TASKS = {
    "plan_arcs_by_ai": ("volume", "arcs"),
    "plan_scenes_by_ai": ("arc", "scenes"),
    "plan_chapters_by_ai": ("scene", "chapters"),
    "write_chapter_by_ai": ("chapter", "content"),
}
WRITING_SCOPE_FIELDS = {"target_type", "target_id", "mode", "expected_version", "selected_entities", "reading_intent", "reading_version"}


class WritingSelectionV1(StrictRequestModel):
    """作者选中的资料；不提供任意数据库读取参数。"""

    character_ids: list[str] = Field(default_factory=list, max_length=50)
    faction_ids: list[str] = Field(default_factory=list, max_length=50)
    location_ids: list[str] = Field(default_factory=list, max_length=50)
    item_ids: list[str] = Field(default_factory=list, max_length=50)
    rule_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_entities(self) -> "WritingSelectionV1":
        """沿用领域的五类业务 ID 校验。"""
        ArcPlanningV1.model_validate(self.model_dump())
        return self


class WritingGenerateInputV1(StrictRequestModel):
    """服务端固定操作位置，开始表单只收集创作要求。"""

    novel_id: ObjectIdString
    target_type: Literal["volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    mode: Literal["append"] = "append"
    reading_intent: Literal["chapter_before", "chapter_after", "append", "replan"] | None = None
    reading_version: Literal[1] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    selected_entities: WritingSelectionV1 = Field(default_factory=WritingSelectionV1)
    count_mode: Literal["auto", "fixed"] = Field(default="fixed", title="数量方式")
    count: int = Field(default=2, ge=0, le=20, title="生成数量")
    user_guidance: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(default="", max_length=5000, title="作者要求")
    target_word_count: int | None = Field(default=None, ge=1, le=100000, title="目标字数")
    search_text: str = Field(default="", max_length=100, title="检索文字")
    search_scope: Literal["novel", "current_part"] = Field(default="current_part", title="检索范围")

    @model_validator(mode="after")
    def validate_target(self) -> "WritingGenerateInputV1":
        """规划只追加，正文必须绑定已读章节版本。"""
        if self.target_type == "chapter":
            if self.expected_version is None:
                raise ValueError("生成正文必须提供当前章版本")
        elif self.expected_version is not None:
            raise ValueError("追加规划不接受旧父级版本")
        return self


class ArcPlansResultV1(StrictRequestModel):
    """仅提供篇章可编辑内容，不包含正式 ID 或统计。"""

    arcs: list[ArcCreateV1] = Field(max_length=20)


class ChapterContentResultV1(StrictRequestModel):
    """章节正文候选；保留作者与模型的换行和首尾空白。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    content: str = Field(min_length=1, max_length=100000)

    @model_validator(mode="after")
    def require_text(self) -> "ChapterContentResultV1":
        """拒绝没有实际文字的正文候选。"""
        if not self.content.strip():
            raise ValueError("正文不能为空白")
        return self


class ScenePlansResultV1(StrictRequestModel):
    """场景候选不包含正文。"""

    scenes: list[SceneCreateV1] = Field(max_length=20)


class ChapterPlanCandidateV1(StrictRequestModel):
    """章计划生成只提供规划，正式新章正文由服务置空。"""

    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=2000)
    planning: ChapterPlanV2 = Field(default_factory=ChapterPlanV2)


class ChapterPlansResultV1(StrictRequestModel):
    """场景内有序的章计划候选。"""

    chapters: list[ChapterPlanCandidateV1] = Field(max_length=20)


WRITING_RESULTS = {
    "plan_arcs_by_ai": ArcPlansResultV1,
    "plan_scenes_by_ai": ScenePlansResultV1,
    "plan_chapters_by_ai": ChapterPlansResultV1,
    "write_chapter_by_ai": ChapterContentResultV1,
}
