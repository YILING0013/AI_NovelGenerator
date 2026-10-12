"""小说物品候选的确定性输入、后验与 basis 契约。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.prompts.prompt_selector import ITEMS_PROMPT_NAME
from backend.llm.schemas.item_pydantic import ItemCandidateV1, ItemsGenerateRequestV1, ItemsGenerationInputV1, normalize_item_text
from backend.services.llm.candidate_contract import CandidateSourceRefV1


ITEMS_WORKFLOW = "create_items_by_ai"
ITEMS_STEP = "create_items"

_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def build_items_generation_input(
    novel_id: str,
    request: ItemsGenerateRequestV1 | Mapping[str, Any],
) -> ItemsGenerationInputV1:
    """合并路径小说 ID 并移除入口选择字段。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 物品候选预览请求或等价映射。

    Returns:
        可随 basis 返回并重算的严格生成输入。
    """
    payload = (
        request.model_dump(mode="json", exclude={"use_stream"})
        if isinstance(request, ItemsGenerateRequestV1)
        else {key: value for key, value in dict(request).items() if key != "use_stream"}
    )
    payload["novel_id"] = novel_id.lower()
    return ItemsGenerationInputV1.model_validate(payload)


def compute_items_input_fingerprint(
    generation_input: ItemsGenerationInputV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按当前提示词与执行配置重算物品输入指纹。

    Args:
        generation_input: 预览时锁定的物品生成输入。
        source_refs: 当前完整正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_items_by_ai', generation_input, source_refs, flow_snapshot)


def validate_item_candidates(
    candidates: Sequence[ItemCandidateV1 | Mapping[str, Any]],
    generation_input: ItemsGenerationInputV1 | Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    require_generated_count: bool,
) -> None:
    """校验候选数量、名称与正式引用白名单。

    Args:
        candidates: 模型返回或用户编辑后的物品候选。
        generation_input: 当前生成输入。
        context: 当前正式物品和三类引用白名单。
        require_generated_count: 是否要求数量严格等于生成目标。

    Returns:
        所有业务后验通过时不返回内容。
    """
    normalized_input = ItemsGenerationInputV1.model_validate(
        generation_input.model_dump(mode="json")
        if isinstance(generation_input, ItemsGenerationInputV1)
        else dict(generation_input)
    )
    normalized_candidates = [
        item
        if isinstance(item, ItemCandidateV1)
        else ItemCandidateV1.model_validate(item)
        for item in candidates
    ]
    if require_generated_count and len(normalized_candidates) != normalized_input.item_count:
        raise ValueError(f"模型物品数量必须严格等于 {normalized_input.item_count}")

    used_tokens = set(context["existing_item_tokens"])
    allowed_character_ids = set(context["allowed_character_ids"])
    allowed_faction_ids = set(context["allowed_faction_ids"])
    allowed_location_ids = set(context["allowed_location_ids"])
    for candidate in normalized_candidates:
        tokens = {
            normalize_item_text(value)
            for value in [candidate.name, *candidate.aliases]
        }
        if tokens & used_tokens:
            raise ValueError("物品候选名称或别名与已有物品或本批候选重复")
        used_tokens.update(tokens)
        if (
            candidate.owner_character_id is not None
            and candidate.owner_character_id not in allowed_character_ids
        ):
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外的角色所有者"
            )
        if (
            candidate.controlling_faction_id is not None
            and candidate.controlling_faction_id not in allowed_faction_ids
        ):
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外的控制势力"
            )
        if (
            candidate.current_location_id is not None
            and candidate.current_location_id not in allowed_location_ids
        ):
            raise ValueError(
                f"{candidate.candidate_ref} 引用了输入白名单外的当前地点"
            )


__all__ = [
    "ITEMS_PROMPT_NAME",
    "ITEMS_STEP",
    "ITEMS_WORKFLOW",
    "build_items_generation_input",
    "compute_items_input_fingerprint",
    "validate_item_candidates",
]
