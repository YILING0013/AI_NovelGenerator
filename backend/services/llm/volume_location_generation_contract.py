"""单卷按需地点候选的确定性输入、后验与 basis 契约。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.location_pydantic import LocationCandidateV1, VolumeLocationsGenerateRequestV1, VolumeLocationsGenerationInputV1, normalize_location_text
from backend.services.llm.candidate_contract import CandidateSourceRefV1


VOLUME_LOCATIONS_WORKFLOW = "create_locations_for_volume_by_ai"
VOLUME_LOCATIONS_STEP = "create_locations_for_volume"

_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def build_volume_locations_generation_input(
    novel_id: str,
    volume_id: str,
    request: VolumeLocationsGenerateRequestV1 | Mapping[str, Any],
) -> VolumeLocationsGenerationInputV1:
    """合并路径 ID 并移除仅用于入口选择的 use_stream。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        volume_id: 路径中的目标卷 ObjectId 字符串。
        request: 单卷地点预览请求或等价映射。

    Returns:
        绑定小说与目标卷的严格确定性生成输入。
    """
    payload = (
        request.model_dump(mode="json", exclude={"use_stream"})
        if isinstance(request, VolumeLocationsGenerateRequestV1)
        else {key: value for key, value in dict(request).items() if key != "use_stream"}
    )
    payload.update({"novel_id": novel_id.lower(), "volume_id": volume_id.lower()})
    return VolumeLocationsGenerationInputV1.model_validate(payload)


def compute_volume_locations_input_fingerprint(
    generation_input: VolumeLocationsGenerationInputV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时任务图重算单卷地点输入指纹。

    Args:
        generation_input: 预览时锁定的单卷地点输入。
        source_refs: 当前完整正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_locations_for_volume_by_ai', generation_input, source_refs, flow_snapshot)


def validate_volume_location_candidates(
    candidates: Sequence[LocationCandidateV1 | Mapping[str, Any]],
    generation_input: VolumeLocationsGenerationInputV1 | Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    require_generated_count: bool,
) -> None:
    """复验数量、全局名称、拓扑和正式引用白名单。

    Args:
        candidates: 模型结果或用户编辑后的地点候选。
        generation_input: 生成期锁定的目标数量与正式选择。
        context: 当前正式地点、规则、势力及其引用白名单。
        require_generated_count: 是否要求候选数严格等于模型目标数。

    Returns:
        全部候选业务后验有效时返回 None。
    """
    normalized_input = VolumeLocationsGenerationInputV1.model_validate(
        generation_input.model_dump(mode="json")
        if isinstance(generation_input, VolumeLocationsGenerationInputV1)
        else dict(generation_input)
    )
    normalized_candidates = [
        item
        if isinstance(item, LocationCandidateV1)
        else LocationCandidateV1.model_validate(item)
        for item in candidates
    ]
    if (
        require_generated_count
        and len(normalized_candidates) != normalized_input.location_count
    ):
        raise ValueError(
            f"模型地点数量必须严格等于 {normalized_input.location_count}"
        )

    existing_tokens = set(context["existing_location_tokens"])
    candidate_tokens: set[str] = set()
    seen_refs: set[str] = set()
    allowed_location_ids = set(context["allowed_location_ids"])
    allowed_rule_ids = set(context["allowed_rule_ids"])
    allowed_faction_ids = set(context["allowed_faction_ids"])
    for candidate in normalized_candidates:
        if candidate.candidate_ref in seen_refs:
            raise ValueError("candidate_ref 不能重复")
        if (
            candidate.parent_location_ref is not None
            and candidate.parent_location_ref not in seen_refs
        ):
            raise ValueError("候选父级只能引用本批中排在前面的 candidate_ref")
        seen_refs.add(candidate.candidate_ref)

        tokens = {
            normalize_location_text(value)
            for value in [candidate.name, *candidate.aliases]
        }
        if tokens & candidate_tokens:
            raise ValueError("候选地点名称或别名在规范化后互相重复")
        if tokens & existing_tokens:
            raise ValueError("候选地点名称或别名与已有活动地点重复")
        candidate_tokens.update(tokens)

        if (
            candidate.parent_location_id is not None
            and candidate.parent_location_id not in allowed_location_ids
        ):
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外的父地点"
            )
        invalid_rule_ids = sorted(
            set(candidate.applicable_rule_ids) - allowed_rule_ids
        )
        if invalid_rule_ids:
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外规则: "
                + ", ".join(invalid_rule_ids)
            )
        invalid_faction_ids = sorted(
            set(candidate.associated_faction_ids) - allowed_faction_ids
        )
        if invalid_faction_ids:
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外势力: "
                + ", ".join(invalid_faction_ids)
            )


__all__ = [
    "VOLUME_LOCATIONS_STEP",
    "VOLUME_LOCATIONS_WORKFLOW",
    "build_volume_locations_generation_input",
    "compute_volume_locations_input_fingerprint",
    "validate_volume_location_candidates",
]
