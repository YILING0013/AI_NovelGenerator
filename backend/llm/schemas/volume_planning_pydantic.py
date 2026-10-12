"""全书卷骨架与单卷启动包 AI 候选的严格契约。"""

from __future__ import annotations

import re
from typing import Any, Literal
import unicodedata

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.api.contracts import (
    LocalCandidateRef,
    ObjectIdString,
    StrictRequestModel,
    StrictResponseModel,
)
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


VOLUME_SKELETON_RESULT_SCHEMA_ID = "volume_skeleton_result"
VOLUME_SKELETON_RESULT_SCHEMA_VERSION = 1
VOLUME_LAUNCH_RESULT_SCHEMA_ID = "volume_launch_package_result"
VOLUME_LAUNCH_RESULT_SCHEMA_VERSION = 1


def normalize_volume_text(value: str) -> str:
    """生成卷标题、转折和状态衔接共用的规范比较键。

    Args:
        value: 需要比较的业务文本。

    Returns:
        完成 NFKC、空白折叠与跨 Python/JavaScript 一致的小写文本。
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).lower()


class VolumePlanningV1(StrictRequestModel):
    """一卷唯一正式规划或启动包字段。"""

    premise: str = Field(max_length=1000)
    major_conflict: str = Field(max_length=2000)
    key_turning_points: list[str] = Field(max_length=20)
    start_state: str = Field(max_length=2000)
    end_state: str = Field(max_length=2000)
    target_chapter_count: int = Field(ge=1, le=1000)
    target_word_count: int = Field(ge=1, le=10_000_000)


class VolumeOrderRangeV1(StrictRequestModel):
    """卷骨架生成目标的连续 1-based 顺序范围。"""

    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "VolumeOrderRangeV1":
        """要求结束序号不小于开始序号。

        Args:
            self: 当前已解析的顺序区间。

        Returns:
            通过起止边界校验的当前区间。
        """
        if self.end < self.start:
            raise ValueError("target_order_range.end 不能小于 start")
        return self


class VolumeSkeletonGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    """全书卷骨架候选预览请求。"""

    target_volume_count: int = Field(ge=1, le=30)
    total_chapter_budget: int = Field(ge=1, le=1000)
    total_word_budget: int = Field(ge=1, le=10_000_000)
    mode: Literal["create", "append", "replan"]
    target_order_range: VolumeOrderRangeV1 | None = None
    novel_expected_version: int = Field(ge=1)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)
    use_stream: bool = True

    @model_validator(mode="after")
    def validate_replan_target(self) -> "VolumeSkeletonGenerateRequestV1":
        """要求 replan 的目标数与闭区间长度一致。

        Args:
            self: 当前已解析的卷骨架预览请求。

        Returns:
            replan 目标自洽的当前请求。
        """
        if self.mode == "replan":
            if self.target_order_range is None:
                raise ValueError("replan 必须提供 target_order_range")
            if self.target_volume_count != (
                self.target_order_range.end - self.target_order_range.start + 1
            ):
                raise ValueError(
                    "replan target_volume_count 必须等于 target_order_range 长度"
                )
        return self


class VolumeSkeletonGenerationInputV1(ReasoningOptions, StrictRequestModel):
    """随 basis 回传、用于确认时重算指纹的卷骨架输入。"""

    novel_id: ObjectIdString
    target_volume_count: int = Field(ge=1, le=30)
    total_chapter_budget: int = Field(ge=1, le=1000)
    total_word_budget: int = Field(ge=1, le=10_000_000)
    mode: Literal["create", "append", "replan"]
    target_order_range: VolumeOrderRangeV1 | None = None
    novel_expected_version: int = Field(ge=1)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @model_validator(mode="after")
    def validate_replan_target(self) -> "VolumeSkeletonGenerationInputV1":
        """要求 replan 的原始目标数与闭区间长度一致。

        Args:
            self: 当前已解析的卷骨架生成输入。

        Returns:
            replan 目标自洽的当前生成输入。
        """
        if self.mode == "replan":
            if self.target_order_range is None:
                raise ValueError("replan 必须提供 target_order_range")
            if self.target_volume_count != (
                self.target_order_range.end - self.target_order_range.start + 1
            ):
                raise ValueError(
                    "replan target_volume_count 必须等于 target_order_range 长度"
                )
        return self


class VolumeSkeletonCandidateV1(StrictRequestModel):
    """模型可输出且用户可编辑的一条卷骨架候选。"""

    candidate_ref: LocalCandidateRef
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(max_length=120)
    order_index: int = Field(ge=1)
    summary: str = Field(max_length=2000)
    goal: str = Field(max_length=1000)
    theme: str = Field(max_length=500)
    planning: VolumePlanningV1

    @model_validator(mode="after")
    def validate_skeleton_turning_points(self) -> "VolumeSkeletonCandidateV1":
        """仅对 AI 卷骨架候选要求转折非空且规范唯一。

        Args:
            self: 当前已解析的 AI 卷骨架候选。

        Returns:
            通过卷骨架专属后验的当前候选。
        """
        normalized = [normalize_volume_text(item) for item in self.planning.key_turning_points]
        if not normalized or any(not item for item in normalized):
            raise ValueError("AI 卷骨架的 key_turning_points 必须包含 1..20 个非空转折")
        if len(normalized) != len(set(normalized)):
            raise ValueError("AI 卷骨架的 key_turning_points 必须规范唯一")
        return self


class VolumeSkeletonResultV1(StrictRequestModel):
    """Provider 必须完整返回的卷骨架根对象。"""

    volumes: list[VolumeSkeletonCandidateV1] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_unique_candidate_refs(self) -> "VolumeSkeletonResultV1":
        """拒绝本批重复候选引用。

        Args:
            self: 已完成嵌套结构校验的结果。

        Returns:
            候选引用唯一的原结果。
        """
        refs = [item.candidate_ref for item in self.volumes]
        if len(refs) != len(set(refs)):
            raise ValueError("candidate_ref 不能重复")
        return self


class VolumeSkeletonBasisV1(CandidateBasisV1):
    """包含原始严格生成输入的卷骨架不透明依据。"""

    generation_input: VolumeSkeletonGenerationInputV1

    @model_validator(mode="after")
    def validate_volume_skeleton_contract(self) -> "VolumeSkeletonBasisV1":
        """确保 basis 元数据属于卷骨架工作流。

        Args:
            self: 已通过公共 basis 校验的依据。

        Returns:
            契约一致的原依据。
        """
        if (
            self.workflow != "create_volume_skeleton_by_ai"
            or self.step != "create_volume_skeleton"
            or self.schema_id != VOLUME_SKELETON_RESULT_SCHEMA_ID
            or self.schema_version != VOLUME_SKELETON_RESULT_SCHEMA_VERSION
            or self.novel_id != self.generation_input.novel_id
        ):
            raise ValueError("卷骨架 basis 契约不匹配")
        novel_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "novel"
        ]
        if (
            self.novel_id is None
            or len(novel_refs) != 1
            or novel_refs[0].id != self.novel_id
            or novel_refs[0].version != self.generation_input.novel_expected_version
        ):
            raise ValueError("卷骨架 basis 必须包含当前小说的精确版本")
        return self


class VolumeBulkPlanRequestV1(StrictRequestModel):
    """全书卷骨架候选的严格批量确认信封。"""

    candidates: list[VolumeSkeletonCandidateV1] = Field(min_length=1, max_length=30)
    basis: VolumeSkeletonBasisV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在类型转换前拒绝布尔值、字符串版本和空键。

        Args:
            value: 客户端提交的原始版本映射。

        Returns:
            仅含正整数版本的原映射。
        """
        if not isinstance(value, dict) or any(
            not isinstance(key, str)
            or not key.strip()
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            for key, version in value.items()
        ):
            raise ValueError("expected_versions 必须使用非空资源键和正整数版本")
        return value

    @model_validator(mode="after")
    def validate_candidate_count_and_versions(self) -> "VolumeBulkPlanRequestV1":
        """要求 replan 完整映射目标区间且版本映射匹配 basis。

        Args:
            self: 当前已解析的批量确认信封。

        Returns:
            通过确认信封完整性验证的当前请求。
        """
        expected = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected:
            raise ValueError("expected_versions 必须精确匹配 basis.source_refs")
        generation_input = self.basis.generation_input
        if generation_input.mode == "replan":
            target_range = generation_input.target_order_range
            if target_range is None or len(self.candidates) != (
                target_range.end - target_range.start + 1
            ):
                raise ValueError("replan 候选必须完整覆盖 target_order_range")
        return self


class VolumeDownstreamImpactV1(StrictResponseModel):
    """一个正式卷已存在的真实下游引用。"""

    volume_id: ObjectIdString
    arcs: int = Field(ge=0)
    scenes: int = Field(ge=0)
    chapters: int = Field(ge=0)
    factions: int = Field(ge=0)
    character_volume_states: int = Field(ge=0)
    faction_volume_states: int = Field(ge=0)
    character_first_appearances: int = Field(ge=0)
    faction_first_appearances: int = Field(ge=0)
    character_faction_binding_boundaries: int = Field(ge=0)
    foreshadowings: int = Field(default=0, ge=0)
    chapter_records: int = Field(default=0, ge=0)
    total: int = Field(ge=0)
    has_blockers: bool


class VolumeSkeletonPreviewV1(StrictResponseModel):
    """普通预览与 SSE done.result 共用的卷骨架候选信封。"""

    workflow: Literal["create_volume_skeleton_by_ai"]
    step: Literal["create_volume_skeleton"]
    schema_id: Literal["volume_skeleton_result"]
    schema_version: Literal[1]
    candidate: VolumeSkeletonResultV1
    basis: VolumeSkeletonBasisV1
    impacts: list[VolumeDownstreamImpactV1] = Field(default_factory=list, max_length=30)


class VolumeLaunchGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    """单卷启动包候选预览请求。"""

    volume_expected_version: int = Field(ge=1)
    target_chapter_count: int | None = Field(default=None, ge=1, le=1000)
    target_word_count: int | None = Field(default=None, ge=1, le=10_000_000)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)
    use_stream: bool = True


class VolumeLaunchGenerationInputV1(ReasoningOptions, StrictRequestModel):
    """随 basis 回传、用于确认时重算指纹的启动包输入。"""

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    volume_expected_version: int = Field(ge=1)
    target_chapter_count: int | None = Field(default=None, ge=1, le=1000)
    target_word_count: int | None = Field(default=None, ge=1, le=10_000_000)
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)


class VolumeLaunchPackageV1(StrictRequestModel):
    """模型可输出且用户可编辑的单卷启动包。"""

    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(max_length=120)
    summary: str = Field(max_length=2000)
    goal: str = Field(max_length=1000)
    theme: str = Field(max_length=500)
    planning: VolumePlanningV1

    @model_validator(mode="after")
    def validate_turning_points(self) -> "VolumeLaunchPackageV1":
        """要求启动包转折非空且规范唯一。

        Args:
            self: 当前已解析的启动包。

        Returns:
            转折有效的当前启动包。
        """
        normalized = [normalize_volume_text(item) for item in self.planning.key_turning_points]
        if not normalized or any(not item for item in normalized):
            raise ValueError("启动包 key_turning_points 必须包含 1..20 个非空转折")
        if len(normalized) != len(set(normalized)):
            raise ValueError("启动包 key_turning_points 必须规范唯一")
        return self


class VolumeLaunchPackageResultV1(StrictRequestModel):
    """Provider 必须完整返回的启动包根对象。"""

    launch_package: VolumeLaunchPackageV1


class VolumeLaunchBasisV1(CandidateBasisV1):
    """包含目标卷和原始生成输入的启动包依据。"""

    generation_input: VolumeLaunchGenerationInputV1

    @model_validator(mode="after")
    def validate_volume_launch_contract(self) -> "VolumeLaunchBasisV1":
        """确保 basis 元数据、小说和目标卷属于启动包工作流。

        Args:
            self: 已通过公共 basis 校验的依据。

        Returns:
            契约一致的原依据。
        """
        if (
            self.workflow != "plan_volume_launch_by_ai"
            or self.step != "create_volume_launch_package"
            or self.schema_id != VOLUME_LAUNCH_RESULT_SCHEMA_ID
            or self.schema_version != VOLUME_LAUNCH_RESULT_SCHEMA_VERSION
            or self.novel_id != self.generation_input.novel_id
        ):
            raise ValueError("启动包 basis 契约不匹配")
        novel_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "novel"
        ]
        if len(novel_refs) != 1 or novel_refs[0].id != self.novel_id:
            raise ValueError("启动包 basis 必须只包含当前小说来源")
        target_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "volume"
            and source.id == self.generation_input.volume_id
        ]
        if (
            len(target_refs) != 1
            or target_refs[0].version
            != self.generation_input.volume_expected_version
        ):
            raise ValueError("启动包 basis 必须包含目标卷的精确版本")
        return self


class VolumeLaunchImpactV1(StrictResponseModel):
    """启动包对目标卷下游和相邻卷边界的影响。"""

    target_volume_id: ObjectIdString
    previous_volume_id: ObjectIdString | None
    next_volume_id: ObjectIdString | None
    downstream: VolumeDownstreamImpactV1
    next_start_state_conflict: bool
    has_blockers: bool


class VolumeLaunchPreviewV1(StrictResponseModel):
    """普通预览与 SSE done.result 共用的启动包候选信封。"""

    workflow: Literal["plan_volume_launch_by_ai"]
    step: Literal["create_volume_launch_package"]
    schema_id: Literal["volume_launch_package_result"]
    schema_version: Literal[1]
    candidate: VolumeLaunchPackageResultV1
    basis: VolumeLaunchBasisV1
    impact: VolumeLaunchImpactV1


class VolumeLaunchConfirmV1(StrictRequestModel):
    """通过既有 Volume PUT 路径提交的启动包确认内容。"""

    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(max_length=120)
    summary: str = Field(max_length=2000)
    goal: str = Field(max_length=1000)
    theme: str = Field(max_length=500)
    planning: VolumePlanningV1
    basis: VolumeLaunchBasisV1

    @model_validator(mode="after")
    def validate_turning_points(self) -> "VolumeLaunchConfirmV1":
        """要求确认的启动包转折非空且规范唯一。

        Args:
            self: 当前已解析的启动包确认请求。

        Returns:
            转折有效的当前确认请求。
        """
        normalized = [normalize_volume_text(item) for item in self.planning.key_turning_points]
        if not normalized or any(not item for item in normalized):
            raise ValueError("启动包 key_turning_points 必须包含 1..20 个非空转折")
        if len(normalized) != len(set(normalized)):
            raise ValueError("启动包 key_turning_points 必须规范唯一")
        if self.expected_version != self.basis.generation_input.volume_expected_version:
            raise ValueError("expected_version 必须等于启动包 basis 中的目标卷版本")
        return self


__all__ = [
    "VOLUME_LAUNCH_RESULT_SCHEMA_ID",
    "VOLUME_LAUNCH_RESULT_SCHEMA_VERSION",
    "VOLUME_SKELETON_RESULT_SCHEMA_ID",
    "VOLUME_SKELETON_RESULT_SCHEMA_VERSION",
    "normalize_volume_text",
    "VolumeBulkPlanRequestV1",
    "VolumeDownstreamImpactV1",
    "VolumeLaunchBasisV1",
    "VolumeLaunchConfirmV1",
    "VolumeLaunchGenerateRequestV1",
    "VolumeLaunchGenerationInputV1",
    "VolumeLaunchImpactV1",
    "VolumeLaunchPackageResultV1",
    "VolumeLaunchPackageV1",
    "VolumeLaunchPreviewV1",
    "VolumeOrderRangeV1",
    "VolumePlanningV1",
    "VolumeSkeletonBasisV1",
    "VolumeSkeletonCandidateV1",
    "VolumeSkeletonGenerateRequestV1",
    "VolumeSkeletonGenerationInputV1",
    "VolumeSkeletonPreviewV1",
    "VolumeSkeletonResultV1",
]
