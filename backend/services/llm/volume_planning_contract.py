"""卷骨架和启动包候选的富指纹与公开信封契约。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.volume_planning_pydantic import VolumeLaunchGenerateRequestV1, VolumeLaunchGenerationInputV1, VolumeSkeletonGenerateRequestV1, VolumeSkeletonGenerationInputV1, normalize_volume_text
from backend.services.llm.candidate_contract import CandidateSourceRefV1


VOLUME_SKELETON_WORKFLOW = "create_volume_skeleton_by_ai"
VOLUME_SKELETON_STEP = "create_volume_skeleton"
VOLUME_LAUNCH_WORKFLOW = "plan_volume_launch_by_ai"
VOLUME_LAUNCH_STEP = "create_volume_launch_package"

_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def build_volume_skeleton_generation_input(
    novel_id: str,
    request: VolumeSkeletonGenerateRequestV1 | Mapping[str, Any],
) -> VolumeSkeletonGenerationInputV1:
    """移除入口选择字段并生成卷骨架确定性输入。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 卷骨架预览请求或等价映射。

    Returns:
        不含 use_stream 的严格生成输入。
    """
    payload = (
        request.model_dump(mode="json", exclude={"use_stream"})
        if isinstance(request, VolumeSkeletonGenerateRequestV1)
        else {key: value for key, value in dict(request).items() if key != "use_stream"}
    )
    payload["novel_id"] = novel_id.lower()
    return VolumeSkeletonGenerationInputV1.model_validate(payload)


def build_volume_launch_generation_input(
    novel_id: str,
    volume_id: str,
    request: VolumeLaunchGenerateRequestV1 | Mapping[str, Any],
) -> VolumeLaunchGenerationInputV1:
    """合并路径 ID 与启动包参数并生成确定性输入。

    Args:
        novel_id: 路径小说 ObjectId 字符串。
        volume_id: 路径目标卷 ObjectId 字符串。
        request: 启动包预览请求或等价映射。

    Returns:
        不含 use_stream 且绑定小说和目标卷的严格生成输入。
    """
    payload = (
        request.model_dump(mode="json", exclude={"use_stream"})
        if isinstance(request, VolumeLaunchGenerateRequestV1)
        else {key: value for key, value in dict(request).items() if key != "use_stream"}
    )
    payload.update({"novel_id": novel_id.lower(), "volume_id": volume_id.lower()})
    return VolumeLaunchGenerationInputV1.model_validate(payload)


def compute_volume_skeleton_input_fingerprint(
    novel_id: str,
    generation_input: VolumeSkeletonGenerationInputV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时任务图重算卷骨架输入指纹。

    Args:
        novel_id: 当前小说 ObjectId 字符串。
        generation_input: 预览时锁定的卷骨架输入。
        source_refs: 当前完整正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_volume_skeleton_by_ai', generation_input, source_refs, flow_snapshot)


def compute_volume_launch_input_fingerprint(
    generation_input: VolumeLaunchGenerationInputV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时任务图重算启动包输入指纹。

    Args:
        generation_input: 预览时锁定的启动包输入。
        source_refs: 当前完整正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('plan_volume_launch_by_ai', generation_input, source_refs, flow_snapshot)


def validate_volume_skeleton_candidate_set(
    candidates: Sequence[Mapping[str, Any]],
    generation_input: VolumeSkeletonGenerationInputV1 | Mapping[str, Any],
    *,
    require_generated_count: bool,
) -> None:
    """复验生成与确认共同遵守的卷骨架内部后验。

    Args:
        candidates: 当前模型结果或用户编辑后的候选列表。
        generation_input: 生成期锁定的目标预算与模式。
        require_generated_count: 是否要求数量仍等于原始模型目标数。

    Returns:
        全部数量、顺序、标题、预算和内部状态衔接有效时返回 None。
    """
    normalized_input = VolumeSkeletonGenerationInputV1.model_validate(
        generation_input.model_dump(mode="json")
        if isinstance(generation_input, VolumeSkeletonGenerationInputV1)
        else dict(generation_input)
    )
    ordered = sorted(candidates, key=lambda item: int(item["order_index"]))
    if require_generated_count and len(ordered) != normalized_input.target_volume_count:
        raise ValueError("模型卷数量必须严格等于 target_volume_count")
    orders = [int(item["order_index"]) for item in ordered]
    if orders != list(range(orders[0], orders[0] + len(orders))):
        raise ValueError("候选卷 order_index 必须连续")
    titles = [normalize_volume_text(str(item["title"])) for item in ordered]
    if any(not title for title in titles) or len(titles) != len(set(titles)):
        raise ValueError("候选卷标题必须规范唯一")
    if sum(int(item["planning"]["target_chapter_count"]) for item in ordered) != (
        normalized_input.total_chapter_budget
    ):
        raise ValueError("候选卷章节预算总和不匹配")
    if sum(int(item["planning"]["target_word_count"]) for item in ordered) != (
        normalized_input.total_word_budget
    ):
        raise ValueError("候选卷字数预算总和不匹配")
    for previous, current in zip(ordered, ordered[1:]):
        if normalize_volume_text(str(previous["planning"]["end_state"])) != (
            normalize_volume_text(str(current["planning"]["start_state"]))
        ):
            raise ValueError("上一卷结尾与下一卷开头未衔接，请重新生成或修改两卷衔接处")


__all__ = [
    "VOLUME_LAUNCH_STEP",
    "VOLUME_LAUNCH_WORKFLOW",
    "VOLUME_SKELETON_STEP",
    "VOLUME_SKELETON_WORKFLOW",
    "build_volume_launch_generation_input",
    "build_volume_skeleton_generation_input",
    "compute_volume_launch_input_fingerprint",
    "compute_volume_skeleton_input_fingerprint",
    "validate_volume_skeleton_candidate_set",
]
