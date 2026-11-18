"""全书卷骨架与单卷启动包 AI 候选的严格契约。"""

from __future__ import annotations

import re
from typing import Any, Literal
import unicodedata

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.services.novel.character_fact_contract import CharacterFactReadPositionV1
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


class VolumeLaunchContextIssueV1(StrictResponseModel):
    "Lý do cụ thể khiến một tài liệu chưa được biết khi bắt đầu quyển này."

    field: str
    reason: Literal["nonexistent", "unclaimed", "before_start", "voided", "needs_review", "unresolved_reference"]
    blocking_source_ids: list[ObjectIdString]


class VolumeLaunchContextEntityV1(StrictResponseModel):
    "Chỉ để biểu mẫu khởi động nhận diện đối tượng, câu hỏi và nguồn; không chứa nội dung tư liệu."

    entity_type: Literal["character", "faction", "character_relation"]
    entity_id: str
    name: str
    issues: list[VolumeLaunchContextIssueV1]
    source_ids: list[ObjectIdString]


class VolumeLaunchContextCountsV1(StrictResponseModel):
    "Số tài liệu thực tế tham gia vào lần đọc này."

    characters: int = Field(ge=0)
    factions: int = Field(ge=0)
    character_relations: int = Field(ge=0)
    faction_relations: int = Field(ge=0)
    bindings: int = Field(ge=0)
    world_rules: int = Field(ge=0)
    volumes: int = Field(ge=1)


class VolumeLaunchContextV1(StrictResponseModel):
    "Nhắc nhở tài liệu khởi động quyển; không được dùng cho việc sinh hay xác nhận chấp nhận."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    volume_title: str
    position: CharacterFactReadPositionV1
    counts: VolumeLaunchContextCountsV1
    entities: list[VolumeLaunchContextEntityV1]


class VolumePlanningV1(StrictRequestModel):
    "Một trường thuộc quy hoạch chính thức duy nhất của một quyển hoặc gói khởi động."

    premise: str = Field(max_length=1000)
    major_conflict: str = Field(max_length=2000)
    key_turning_points: list[str] = Field(max_length=20)
    start_state: str = Field(max_length=2000)
    end_state: str = Field(max_length=2000)
    target_chapter_count: int = Field(ge=1, le=1000)
    target_word_count: int = Field(ge=1, le=10_000_000)


class VolumeOrderRangeV1(StrictRequestModel):
    "Phạm vi thứ tự liên tục 1-based của các đích tạo khung skeleton quyển."

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
            raise ValueError("target_order_range.end không được nhỏ hơn start")
        return self


class VolumeSkeletonGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    "Yêu cầu xem trước ứng viên khung xương quyển của toàn sách."

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
                raise ValueError("replan phải cung cấp target_order_range")
            if self.target_volume_count != (
                self.target_order_range.end - self.target_order_range.start + 1
            ):
                raise ValueError(
                    "target_volume_count của replan phải bằng độ dài của target_order_range"
                )
        return self


class VolumeSkeletonGenerationInputV1(ReasoningOptions, StrictRequestModel):
    "Đầu vào khung skeleton quyển gửi lại cùng basis, dùng để tính lại vân tay khi xác nhận."

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
                raise ValueError("replan phải cung cấp target_order_range")
            if self.target_volume_count != (
                self.target_order_range.end - self.target_order_range.start + 1
            ):
                raise ValueError(
                    "target_volume_count của replan phải bằng độ dài của target_order_range"
                )
        return self


class VolumeSkeletonCandidateV1(StrictRequestModel):
    "Một ứng viên khung quyển mà mô hình có thể xuất và người dùng có thể sửa."

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
            raise ValueError("key_turning_points của khung quyển do AI tạo phải chứa 1..20 bước ngoặt không được để trống")
        if len(normalized) != len(set(normalized)):
            raise ValueError("key_turning_points của khung quyển do AI tạo phải duy nhất sau chuẩn hóa")
        return self


class VolumeSkeletonResultV1(StrictRequestModel):
    "Đối tượng gốc của khung quyển mà Provider phải trả về đầy đủ."

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
            raise ValueError("candidate_ref không được trùng lặp")
        return self


class VolumeSkeletonBasisV1(CandidateBasisV1):
    "Căn cứ opaque của khung xương tập, bao gồm phần nhập sinh nghiêm ngặt gốc."

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
            raise ValueError("Hợp đồng basis của khung quyển không khớp")
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
            raise ValueError("basis của khung quyển phải chứa phiên bản chính xác của tiểu thuyết hiện tại")
        return self


class VolumeBulkPlanRequestV1(StrictRequestModel):
    "Phong bì xác nhận hàng loạt nghiêm ngặt cho các ứng viên khung xương quyển của toàn sách."

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
            raise ValueError("expected_versions phải dùng khoá tài nguyên không trống và phiên bản là số nguyên dương")
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
            raise ValueError("expected_versions phải khớp chính xác với basis.source_refs")
        generation_input = self.basis.generation_input
        if generation_input.mode == "replan":
            target_range = generation_input.target_order_range
            if target_range is None or len(self.candidates) != (
                target_range.end - target_range.start + 1
            ):
                raise ValueError("Các ứng viên replan phải bao phủ đầy đủ target_order_range")
        return self


class VolumeDownstreamImpactV1(StrictResponseModel):
    "Tham chiếu downstream thực tế đã tồn tại của một quyển chính thức."

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
    "Bao ứng viên khung skeleton quyển, dùng chung cho bản xem trước thường và done.result của SSE."

    workflow: Literal["create_volume_skeleton_by_ai"]
    step: Literal["create_volume_skeleton"]
    schema_id: Literal["volume_skeleton_result"]
    schema_version: Literal[1]
    candidate: VolumeSkeletonResultV1
    basis: VolumeSkeletonBasisV1
    impacts: list[VolumeDownstreamImpactV1] = Field(default_factory=list, max_length=30)


class VolumeLaunchGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    "Yêu cầu xem trước ứng viên gói khởi động cho một quyển."

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
    "Đầu vào gói khởi động gửi lại cùng basis, dùng để tính lại vân tay khi xác nhận."

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
    "Gói khởi động một quyển do mô hình xuất ra và người dùng có thể chỉnh sửa."

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
            raise ValueError("key_turning_points của gói khởi động phải chứa 1..20 bước ngoặt không được để trống")
        if len(normalized) != len(set(normalized)):
            raise ValueError("key_turning_points của gói khởi động phải duy nhất sau chuẩn hóa")
        return self


class VolumeLaunchPackageResultV1(StrictRequestModel):
    "Đối tượng gốc của gói khởi động mà Provider phải trả về đầy đủ."

    launch_package: VolumeLaunchPackageV1


class VolumeLaunchBasisV1(CandidateBasisV1):
    "Căn cứ gói khởi động bao gồm tập đích và phần nhập sinh gốc."

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
            raise ValueError("Hợp đồng basis của gói khởi động không khớp")
        novel_refs = [
            source
            for source in self.source_refs
            if source.resource_type == "novel"
        ]
        if len(novel_refs) != 1 or novel_refs[0].id != self.novel_id:
            raise ValueError("basis của gói khởi động chỉ được chứa nguồn của tiểu thuyết hiện tại")
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
            raise ValueError("basis của gói khởi động phải chứa phiên bản chính xác của quyển đích")
        return self


class VolumeLaunchImpactV1(StrictResponseModel):
    "Tác động của gói khởi động đối với hạ lưu của quyển đích và ranh giới các quyển kề bên."

    target_volume_id: ObjectIdString
    previous_volume_id: ObjectIdString | None
    next_volume_id: ObjectIdString | None
    downstream: VolumeDownstreamImpactV1
    next_start_state_conflict: bool
    has_blockers: bool


class VolumeLaunchPreviewV1(StrictResponseModel):
    "Bao ứng viên gói khởi động, dùng chung cho bản xem trước thường và done.result của SSE."

    workflow: Literal["plan_volume_launch_by_ai"]
    step: Literal["create_volume_launch_package"]
    schema_id: Literal["volume_launch_package_result"]
    schema_version: Literal[1]
    candidate: VolumeLaunchPackageResultV1
    basis: VolumeLaunchBasisV1
    impact: VolumeLaunchImpactV1


class VolumeLaunchConfirmV1(StrictRequestModel):
    "Nội dung xác nhận gói khởi động được gửi qua đường dẫn PUT Volume hiện có."

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
            raise ValueError("key_turning_points của gói khởi động phải chứa 1..20 bước ngoặt không được để trống")
        if len(normalized) != len(set(normalized)):
            raise ValueError("key_turning_points của gói khởi động phải duy nhất sau chuẩn hóa")
        if self.expected_version != self.basis.generation_input.volume_expected_version:
            raise ValueError("expected_version phải bằng phiên bản quyển đích trong basis của gói khởi động")
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
