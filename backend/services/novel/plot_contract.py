"""单卷、单篇章详细剧情的生成、审核与准备确认。"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StringConstraints

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.arc_contract import ArcPlanningV1
from backend.llm.schemas.volume_planning_pydantic import VolumePlanningV1
from backend.services.novel.writing_contract import WritingContextBasisV1


PLOT_TASKS = {"generate_volume_plot_by_ai": "volume", "generate_arc_plot_by_ai": "arc"}


class PlotGenerateInputV1(StrictRequestModel):
    """已有卷或篇章的剧情生成输入，目标版本用于防止覆盖手工稿。"""

    novel_id: ObjectIdString
    target_type: Literal["volume", "arc"]
    target_id: ObjectIdString
    expected_version: int = Field(ge=1)
    user_guidance: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(default="", max_length=5000, title="作者要求")


class PlotSourceReferenceV1(StrictRequestModel):
    """模型指出的保存来源；错误位置和空引用保留给作者核对。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    resource_type: str = Field(max_length=64)
    id: str = Field(max_length=100)
    field: str = Field(max_length=200)
    quote: str = Field(max_length=2000)


class PlotSourceConflictV1(StrictRequestModel):
    """正文与旧规划的一对疑似冲突，不替作者决定哪边正确。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    message: str = Field(max_length=1000)
    saved_text: PlotSourceReferenceV1
    old_plan: PlotSourceReferenceV1


class PlotSourceVerificationV1(StrictRequestModel):
    """引用匹配只表示原句出现在实际输入中，不代表语义判断正确。"""

    status: Literal["matched", "unverified"]
    source_truncated: bool | None


class PlotVerifiedSourceV1(PlotSourceReferenceV1):
    """服务器核对后的引用与实际输入截断状态。"""

    verification: PlotSourceVerificationV1


class PlotSourceConflictItemV1(StrictRequestModel):
    """带稳定编号的双来源报告；服务器没有自动判断冲突真伪。"""

    model_config = ConfigDict(str_strip_whitespace=False)

    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    message: str = Field(max_length=1000)
    saved_text: PlotVerifiedSourceV1
    old_plan: PlotVerifiedSourceV1
    semantic_check: Literal["not_performed"]


class PlotSourceConflictReportV1(StrictRequestModel):
    """区分未报告与报告为空，不把旧流程解释为已经检查无冲突。"""

    reported: bool
    items: list[PlotSourceConflictItemV1] = Field(max_length=12)


class PlotSourceConflictDecisionV1(StrictRequestModel):
    """作者确认核对过一对来源并批准本次候选，也可认为模型误报。"""

    conflict_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool
    note: str = Field(default="", max_length=500)


class PlotConfirmedContentV1(StrictRequestModel):
    """作者勾选确认时看到的实际保存内容，已有下级时不含规划。"""

    plot: str = Field(min_length=1, max_length=40000)
    planning: VolumePlanningV1 | ArcPlanningV1 | None = None


class PlotSourceConflictReviewV1(StrictRequestModel):
    """随本次确认提交的原报告与逐项作者决定。"""

    report: PlotSourceConflictReportV1
    decisions: list[PlotSourceConflictDecisionV1] = Field(max_length=12)
    confirmed_content: PlotConfirmedContentV1


class PlotResultV1(StrictRequestModel):
    """独立长剧情与建议完善的规划，覆盖说明只供审核。"""

    plot: str = Field(min_length=1, max_length=40000)
    planning: VolumePlanningV1 | ArcPlanningV1
    coverage_notes: str = Field(default="", max_length=5000)
    source_conflicts: list[PlotSourceConflictV1] | None = Field(default=None, max_length=12)


class VolumePlotResultV1(PlotResultV1):
    """卷剧情只能搭配卷规划；共同接口仍兼容已有两类候选。"""

    planning: VolumePlanningV1


class ArcPlotResultV1(PlotResultV1):
    """篇章剧情只能搭配篇章规划，不能接受卷规划字段。"""

    planning: ArcPlanningV1


class PlotCandidateBasisV1(CandidateBasisV1):
    """剧情候选绑定原流程、实际读取内容和目标版本。"""

    generation_input: PlotGenerateInputV1
    context_basis: WritingContextBasisV1


class PlotGenerationEnvelopeV1(StrictResponseModel):
    """普通请求与 SSE 完成事件共用的剧情候选。"""

    workflow: str
    step: str
    schema_id: str
    schema_version: int
    candidate: PlotResultV1
    basis: PlotCandidateBasisV1
    context: dict[str, Any] = Field(default_factory=dict)
    prepared_context: dict[str, Any] | None = None
    coverage_review: dict[str, Any] | None = None


class PlotConfirmV1(StrictRequestModel):
    """确认审核后的剧情，不修改其他部分的规划。"""

    candidate: PlotResultV1
    basis: PlotCandidateBasisV1
    expected_version: int = Field(ge=1)
    source_conflict_review: PlotSourceConflictReviewV1 | None = None


class VolumePreparationConfirmV1(StrictRequestModel):
    """手工检查已有资料后确认当前准备阶段，允许零参与。"""

    expected_version: int = Field(ge=1)
    location_ids: list[str] | None = Field(default=None, max_length=50)
