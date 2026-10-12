"""核心世界规则 AI 候选的正式来源、指纹与统一响应契约。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesGenerateRequestV1, CoreWorldRulesGenerationInputV1
from backend.services.llm.candidate_contract import CandidateSourceRefV1


CORE_WORLD_RULE_WORKFLOW = "create_world_rules_by_ai"
CORE_WORLD_RULE_GENERATION_STEP = "create_core_world_rules"

_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def build_core_world_rules_generation_input(
    novel_id: str,
    request: CoreWorldRulesGenerateRequestV1 | Mapping[str, Any],
) -> CoreWorldRulesGenerationInputV1:
    """把路径小说 ID 与预览参数合并为可重算的严格生成输入。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 不含正式事实副本的预览请求。

    Returns:
        排除 use_stream 且包含 novel_id 的确定性生成输入。
    """
    payload = (
        request.model_dump(mode="json", exclude={"use_stream"})
        if isinstance(request, CoreWorldRulesGenerateRequestV1)
        else {key: value for key, value in dict(request).items() if key != "use_stream"}
    )
    payload["novel_id"] = novel_id.lower()
    return CoreWorldRulesGenerationInputV1.model_validate(payload)


def build_core_world_rules_source_refs(
    novel: Mapping[str, Any],
    characters: Sequence[Mapping[str, Any]],
    factions: Sequence[Mapping[str, Any]],
    faction_relations: Sequence[Mapping[str, Any]],
    world_rules: Sequence[Mapping[str, Any]],
) -> list[CandidateSourceRefV1]:
    """把进入 Prompt 的全部正式事实转换为稳定来源版本。

    Args:
        novel: 当前小说正式文档。
        characters: 当前进入生成上下文的活动角色。
        factions: 当前进入生成上下文的活动核心势力。
        faction_relations: 当前进入生成上下文的活动势力关系。
        world_rules: 当前全部未删除世界规则。

    Returns:
        按资源类型与稳定 ID 排序的来源引用。
    """
    novel_id = str(novel.get("id") or novel.get("_id"))
    refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=novel_id,
            version=int(novel["version"]),
        )
    ]
    for resource_type, documents, id_field in (
        ("character", characters, "character_id"),
        ("faction", factions, "faction_id"),
        ("faction_relation", faction_relations, "relation_id"),
        ("world_rule", world_rules, "rule_id"),
    ):
        refs.extend(
            CandidateSourceRefV1(
                resource_type=resource_type,
                id=str(document[id_field]),
                version=int(document["version"]),
            )
            for document in sorted(documents, key=lambda item: str(item[id_field]))
        )
    return refs


def compute_core_world_rules_input_fingerprint(
    generation_input: CoreWorldRulesGenerationInputV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时方案重算核心世界规则候选输入指纹。

    Args:
        generation_input: 预览时随 basis 返回的严格生成输入。
        source_refs: 生成时读取的正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_world_rules_by_ai', generation_input, source_refs, flow_snapshot)


__all__ = [
    "CORE_WORLD_RULE_GENERATION_STEP",
    "CORE_WORLD_RULE_WORKFLOW",
    "build_core_world_rules_generation_input",
    "build_core_world_rules_source_refs",
    "compute_core_world_rules_input_fingerprint",
]
