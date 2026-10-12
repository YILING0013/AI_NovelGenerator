"""区分全书设计和目标卷开始前资料，生成卷骨架与启动包候选。"""

from __future__ import annotations

from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.volume_planning_pydantic import VolumeDownstreamImpactV1, VolumeLaunchGenerateRequestV1, VolumeLaunchImpactV1, VolumeLaunchPackageResultV1, VolumeSkeletonGenerateRequestV1, VolumeSkeletonResultV1, normalize_volume_text
from backend.services.llm.volume_planning_context import load_volume_planning_context
from backend.services.llm.volume_planning_contract import build_volume_launch_generation_input, build_volume_skeleton_generation_input, validate_volume_skeleton_candidate_set
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.volume_service import VolumeService


VOLUME_PLANNING_INPUT_MAX_CHARS = 300_000
_VOLUME_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def _volume_prompt_projection(volume: dict[str, Any] | None) -> dict[str, Any] | None:
    """投影一个相邻卷的公开 ID、版本和计划边界。

    Args:
        volume: 目标或相邻卷正式文档；不存在相邻卷时为 None。

    Returns:
        可进入启动包 Prompt 的相邻卷计划，或 None。
    """
    if volume is None:
        return None
    planning = volume.get("planning")
    return {
        "content_semantics": "design_plan",
        "volume_id": str(volume["_id"]),
        "version": int(volume["version"]),
        "order_index": int(volume["order_index"]),
        "title": volume["title"],
        "subtitle": volume["subtitle"],
        "summary": volume["summary"],
        "goal": volume["goal"],
        "theme": volume["theme"],
        "planning": planning,
        "start_state": planning["start_state"] if planning is not None else None,
        "end_state": planning["end_state"] if planning is not None else None,
    }


class VolumePlanningGenerationService:
    """两套卷规划候选的正式输入、Provider 调用与业务后验入口。"""

    @staticmethod
    async def load_skeleton_context(
        novel_id: str,
        request: VolumeSkeletonGenerateRequestV1,
    ) -> tuple[Any, dict[str, Any], list[VolumeDownstreamImpactV1]]:
        """在 Provider 前复验卷骨架模式、版本、readiness 和输入预算。"""
        generation_input = build_volume_skeleton_generation_input(novel_id, request)
        if (
            generation_input.total_chapter_budget < generation_input.target_volume_count
            or generation_input.total_word_budget < generation_input.target_volume_count
        ):
            raise GenerationDomainError(
                "VOLUME_BUDGET_INVALID",
                "章节和字数总预算都必须至少等于目标卷数",
                status_code=422,
            )
        context = await load_volume_planning_context(generation_input.novel_id)
        if int(context["novel"]["version"]) != generation_input.novel_expected_version:
            raise GenerationDomainError(
                "VOLUME_NOVEL_VERSION_CONFLICT",
                "小说版本已变化，请刷新后重新生成卷骨架",
                status_code=409,
            )
        if not context["protagonists"] or not context["factions"]:
            raise GenerationDomainError(
                "VOLUME_PLANNING_READINESS_REQUIRED",
                "生成卷规划前必须已有活动主角和活动核心势力",
                status_code=422,
            )
        volumes = context["volumes"]
        expected_orders: list[int]
        if generation_input.mode == "create":
            if volumes:
                raise GenerationDomainError(
                    "VOLUME_MODE_CONFLICT",
                    "create 模式要求当前小说没有活动卷",
                    status_code=409,
                )
            expected_orders = list(range(1, generation_input.target_volume_count + 1))
        elif generation_input.mode == "append":
            if not volumes:
                raise GenerationDomainError(
                    "VOLUME_MODE_CONFLICT",
                    "没有活动卷时应使用 create 模式",
                    status_code=409,
                )
            start = int(volumes[-1]["order_index"]) + 1
            expected_orders = list(range(start, start + generation_input.target_volume_count))
        else:
            target_range = generation_input.target_order_range
            assert target_range is not None
            expected_orders = list(range(target_range.start, target_range.end + 1))
            current_orders = {int(item["order_index"]) for item in volumes}
            if any(order not in current_orders for order in expected_orders):
                raise GenerationDomainError(
                    "VOLUME_REPLAN_RANGE_INVALID",
                    "replan 目标区间必须完整对应当前活动卷",
                    status_code=409,
                )
        if generation_input.target_order_range is not None and (
            list(
                range(
                    generation_input.target_order_range.start,
                    generation_input.target_order_range.end + 1,
                )
            )
            != expected_orders
        ):
            raise GenerationDomainError(
                "VOLUME_ORDER_RANGE_INVALID",
                "target_order_range 与当前模式的实际目标顺序不一致",
                status_code=409,
            )

        impacts: list[VolumeDownstreamImpactV1] = []
        if generation_input.mode == "replan":
            by_order = {int(item["order_index"]): item for item in volumes}
            for order in expected_orders:
                impacts.append(
                    VolumeDownstreamImpactV1.model_validate(
                        await VolumeService.get_delete_impact(str(by_order[order]["_id"]))
                    )
                )
        prompt_input = {
            **context["prompt_facts"],
            "target_volume_count": generation_input.target_volume_count,
            "total_chapter_budget": generation_input.total_chapter_budget,
            "total_word_budget": generation_input.total_word_budget,
            "mode": generation_input.mode,
            "target_order_range": (
                generation_input.target_order_range.model_dump(mode="json")
                if generation_input.target_order_range is not None
                else None
            ),
            "user_guidance": generation_input.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=VOLUME_PLANNING_INPUT_MAX_CHARS,
            code="VOLUME_PLANNING_INPUT_BUDGET_EXCEEDED",
            label="卷骨架生成输入",
        )
        context["prompt_input"] = prompt_input
        context["expected_orders"] = expected_orders
        return generation_input, context, impacts


    @staticmethod
    def validate_skeleton_result(
        result: VolumeSkeletonResultV1,
        generation_input: Any,
        context: dict[str, Any],
    ) -> None:
        """复验卷骨架数量、顺序、预算、标题和状态边界。"""
        # Provider 数组物理顺序不是业务事实；公开候选按 order_index 稳定输出。
        result.volumes.sort(key=lambda item: item.order_index)
        candidates = [item.model_dump(mode="json") for item in result.volumes]
        try:
            validate_volume_skeleton_candidate_set(
                candidates,
                generation_input,
                require_generated_count=True,
            )
            ordered = sorted(candidates, key=lambda item: int(item["order_index"]))
            if [int(item["order_index"]) for item in ordered] != context["expected_orders"]:
                raise ValueError("模型卷顺序与当前模式目标不一致")
            volumes = context["volumes"]
            existing_titles = {
                normalize_volume_text(str(item["title"])) for item in volumes
            }
            if generation_input.mode == "append":
                candidate_titles = {
                    normalize_volume_text(str(item["title"])) for item in ordered
                }
                if existing_titles & candidate_titles:
                    raise ValueError("append 候选标题与活动卷冲突")
                previous_planning = volumes[-1].get("planning")
                if previous_planning is not None and normalize_volume_text(
                    str(previous_planning["end_state"])
                ) != normalize_volume_text(str(ordered[0]["planning"]["start_state"])):
                    raise ValueError("append 首卷起点与当前末卷终点不衔接")
            elif generation_input.mode == "replan":
                target_orders = set(context["expected_orders"])
                non_target_titles = {
                    normalize_volume_text(str(item["title"]))
                    for item in volumes
                    if int(item["order_index"]) not in target_orders
                }
                candidate_titles = {
                    normalize_volume_text(str(item["title"])) for item in ordered
                }
                if non_target_titles & candidate_titles:
                    raise ValueError("replan 候选标题与区间外活动卷冲突")
                by_order = {int(item["order_index"]): item for item in volumes}
                first_order, last_order = min(target_orders), max(target_orders)
                previous_planning = (
                    by_order[first_order - 1].get("planning")
                    if first_order - 1 in by_order
                    else None
                )
                next_planning = (
                    by_order[last_order + 1].get("planning")
                    if last_order + 1 in by_order
                    else None
                )
                if previous_planning is not None and normalize_volume_text(
                    str(previous_planning["end_state"])
                ) != normalize_volume_text(str(ordered[0]["planning"]["start_state"])):
                    raise ValueError("replan 首卷起点与左侧相邻卷终点不衔接")
                if next_planning is not None and normalize_volume_text(
                    str(ordered[-1]["planning"]["end_state"])
                ) != normalize_volume_text(str(next_planning["start_state"])):
                    raise ValueError("replan 末卷终点与右侧相邻卷起点不衔接")
        except ValueError as exc:
            raise GenerationDomainError(
                "VOLUME_SKELETON_OUTPUT_INVALID",
                str(exc),
                status_code=502,
            ) from exc


    @staticmethod
    async def load_launch_context(
        novel_id: str,
        volume_id: str,
        request: VolumeLaunchGenerateRequestV1,
    ) -> tuple[Any, dict[str, Any], VolumeLaunchImpactV1]:
        """在 Provider 前复验启动包目标、预算、readiness 和下游影响。"""
        generation_input = build_volume_launch_generation_input(novel_id, volume_id, request)
        context = await load_volume_planning_context(
            generation_input.novel_id,
            target_volume_id=generation_input.volume_id,
        )
        if not context["protagonists"] or not context["factions"]:
            raise GenerationDomainError(
                "VOLUME_PLANNING_READINESS_REQUIRED",
                "生成卷启动包前必须已有活动主角和活动核心势力",
                status_code=422,
            )
        volumes = context["volumes"]
        target_index = next(
            index for index, item in enumerate(volumes) if str(item["_id"]) == generation_input.volume_id
        )
        target = volumes[target_index]
        if int(target["version"]) != generation_input.volume_expected_version:
            raise GenerationDomainError(
                "VOLUME_VERSION_CONFLICT",
                "目标卷版本已变化，请刷新后重新生成启动包",
                status_code=409,
            )
        previous = volumes[target_index - 1] if target_index > 0 else None
        next_volume = volumes[target_index + 1] if target_index + 1 < len(volumes) else None
        target_planning = target.get("planning")
        chapter_count = generation_input.target_chapter_count
        word_count = generation_input.target_word_count
        if chapter_count is None:
            if target_planning is None:
                raise GenerationDomainError(
                    "VOLUME_LAUNCH_BUDGET_REQUIRED",
                    "目标卷尚无规划时必须提供 target_chapter_count",
                    status_code=422,
                )
            chapter_count = int(target_planning["target_chapter_count"])
        if word_count is None:
            if target_planning is None:
                raise GenerationDomainError(
                    "VOLUME_LAUNCH_BUDGET_REQUIRED",
                    "目标卷尚无规划时必须提供 target_word_count",
                    status_code=422,
                )
            word_count = int(target_planning["target_word_count"])
        downstream = VolumeDownstreamImpactV1.model_validate(
            await VolumeService.get_delete_impact(generation_input.volume_id)
        )
        impact = VolumeLaunchImpactV1(
            target_volume_id=generation_input.volume_id,
            previous_volume_id=str(previous["_id"]) if previous is not None else None,
            next_volume_id=str(next_volume["_id"]) if next_volume is not None else None,
            downstream=downstream,
            next_start_state_conflict=False,
            has_blockers=downstream.has_blockers,
        )
        prompt_input = {
            **{key: value for key, value in context["prompt_facts"].items() if key != "existing_volumes"},
            "target_volume": _volume_prompt_projection(target),
            "previous_volume": _volume_prompt_projection(previous),
            "next_volume": _volume_prompt_projection(next_volume),
            "target_chapter_count": chapter_count,
            "target_word_count": word_count,
            "user_guidance": generation_input.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=VOLUME_PLANNING_INPUT_MAX_CHARS,
            code="VOLUME_PLANNING_INPUT_BUDGET_EXCEEDED",
            label="卷启动包生成输入",
        )
        context.update(
            {
                "prompt_input": prompt_input,
                "target": target,
                "previous": previous,
                "next": next_volume,
                "effective_chapter_count": chapter_count,
                "effective_word_count": word_count,
            }
        )
        return generation_input, context, impact


    @staticmethod
    def validate_launch_result(
        result: VolumeLaunchPackageResultV1,
        context: dict[str, Any],
    ) -> bool:
        """复验启动包预算和相邻状态，返回非阻断右邻冲突。"""
        planning = result.launch_package.planning
        errors: list[str] = []
        if planning.target_chapter_count != context["effective_chapter_count"]:
            errors.append("启动包章节预算与请求不一致")
        if planning.target_word_count != context["effective_word_count"]:
            errors.append("启动包字数预算与请求不一致")
        previous_planning = context["previous"].get("planning") if context["previous"] is not None else None
        if previous_planning is not None and normalize_volume_text(
            str(previous_planning["end_state"])
        ) != normalize_volume_text(planning.start_state):
            errors.append("启动包计划起点与上一卷计划终点不衔接")
        if errors:
            raise GenerationDomainError(
                "VOLUME_LAUNCH_OUTPUT_INVALID",
                "; ".join(errors),
                status_code=502,
            )
        next_planning = context["next"].get("planning") if context["next"] is not None else None
        return bool(
            next_planning is not None
            and normalize_volume_text(planning.end_state)
            != normalize_volume_text(str(next_planning["start_state"]))
        )


__all__ = ["VOLUME_PLANNING_INPUT_MAX_CHARS", "VolumePlanningGenerationService"]
