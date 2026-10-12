"""角色与角色关系 AI 候选的来源版本、指纹和统一响应契约。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.character_pydantic import CoreCharactersGenerateRequestV1, CoreCharactersGenerationInputV1
from backend.llm.schemas.character_relation_pydantic import CharacterRelationsGenerateRequestV1, CharacterRelationsGenerationInputV1
from backend.services.llm.candidate_contract import CandidateSourceRefV1


CORE_CHARACTER_WORKFLOW = "create_characters_by_ai"
CORE_CHARACTER_GENERATION_STEP = "create_core_characters"
CHARACTER_RELATION_WORKFLOW = "create_character_relations_by_ai"
CHARACTER_RELATION_GENERATION_STEP = "create_character_relations"

_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


def extract_core_character_generation_input(
    request: CoreCharactersGenerateRequestV1
    | CoreCharactersGenerationInputV1
    | Mapping[str, Any],
) -> dict[str, Any]:
    """提取去除流式传输态的核心角色严格生成输入。

    Args:
        request: 生成请求、确认输入或等价映射。

    Returns:
        仅含核心角色业务输入白名单的 JSON 字典。
    """
    if isinstance(request, CoreCharactersGenerationInputV1):
        payload = request.model_dump(mode="json", exclude={"use_stream"})
    else:
        payload = dict(request)
    return CoreCharactersGenerationInputV1.model_validate(payload).model_dump(
        mode="json"
    )


def extract_character_relation_generation_input(
    request: CharacterRelationsGenerateRequestV1
    | CharacterRelationsGenerationInputV1
    | Mapping[str, Any],
) -> dict[str, Any]:
    """提取去除流式传输态的角色关系严格生成输入。

    Args:
        request: 生成请求、确认输入或等价映射。

    Returns:
        仅含角色关系业务输入白名单的 JSON 字典。
    """
    if isinstance(request, CharacterRelationsGenerationInputV1):
        payload = request.model_dump(mode="json", exclude={"use_stream"})
    else:
        payload = dict(request)
    return CharacterRelationsGenerationInputV1.model_validate(payload).model_dump(
        mode="json"
    )


def build_core_character_source_refs(
    novel: Mapping[str, Any],
    factions: Sequence[Mapping[str, Any]],
    characters: Sequence[Mapping[str, Any]],
) -> list[CandidateSourceRefV1]:
    """把核心角色生成读取的正式事实转换为稳定版本依据。

    Args:
        novel: 当前小说正式文档。
        factions: 进入生成白名单的活动核心势力。
        characters: 参与既有摘要或名称占用校验的正式角色。

    Returns:
        按资源类型和业务 ID 稳定排列的来源引用。
    """
    refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=str(novel.get("id") or novel.get("_id")),
            version=int(novel["version"]),
        )
    ]
    refs.extend(
        CandidateSourceRefV1(
            resource_type="faction",
            id=str(faction["faction_id"]),
            version=int(faction["version"]),
        )
        for faction in sorted(factions, key=lambda item: str(item["faction_id"]))
    )
    refs.extend(
        CandidateSourceRefV1(
            resource_type="character",
            id=str(character["character_id"]),
            version=int(character["version"]),
        )
        for character in sorted(
            characters,
            key=lambda item: str(item["character_id"]),
        )
    )
    return refs


def build_character_relation_source_refs(
    novel: Mapping[str, Any],
    characters: Sequence[Mapping[str, Any]],
    bindings: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
) -> list[CandidateSourceRefV1]:
    """把角色关系生成读取的角色、绑定和关系转换为版本依据。

    Args:
        novel: 当前小说正式文档。
        characters: 本次锁定的活动核心角色。
        bindings: 进入 Prompt 的活动角色—势力绑定。
        relations: 锁定角色之间进入 Prompt 的既有活动关系。

    Returns:
        包含可能影响主归属的绑定版本在内的稳定来源引用。
    """
    refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=str(novel.get("id") or novel.get("_id")),
            version=int(novel["version"]),
        )
    ]
    for resource_type, documents, id_field in (
        ("character", characters, "character_id"),
        ("character_faction_binding", bindings, "binding_id"),
        ("character_relation", relations, "relation_id"),
    ):
        refs.extend(
            CandidateSourceRefV1(
                resource_type=resource_type,
                id=str(document[id_field]),
                version=int(document["version"]),
            )
            for document in sorted(
                documents,
                key=lambda item: str(item[id_field]),
            )
        )
    return refs


def compute_core_character_input_fingerprint(
    request: CoreCharactersGenerateRequestV1
    | CoreCharactersGenerationInputV1
    | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时方案重算核心角色候选输入指纹。

    Args:
        request: 生成请求、确认输入或等价映射。
        source_refs: 生成时读取的正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_characters_by_ai', request, source_refs, flow_snapshot)


def compute_character_relation_input_fingerprint(
    request: CharacterRelationsGenerateRequestV1
    | CharacterRelationsGenerationInputV1
    | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时方案重算角色关系候选输入指纹。

    Args:
        request: 生成请求、确认输入或等价映射。
        source_refs: 生成时读取的正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        64 位小写十六进制输入指纹。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_character_relations_by_ai', request, source_refs, flow_snapshot)


__all__ = [
    "CHARACTER_RELATION_GENERATION_STEP",
    "CHARACTER_RELATION_WORKFLOW",
    "CORE_CHARACTER_GENERATION_STEP",
    "CORE_CHARACTER_WORKFLOW",
    "build_character_relation_source_refs",
    "build_core_character_source_refs",
    "compute_character_relation_input_fingerprint",
    "compute_core_character_input_fingerprint",
    "extract_character_relation_generation_input",
    "extract_core_character_generation_input",
]
