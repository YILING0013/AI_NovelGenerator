"""阵营关系 AI 候选的输入指纹和统一响应契约。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.faction_relation_pydantic import FactionRelationsGenerateRequestV1
from backend.services.llm.candidate_contract import CandidateSourceRefV1


FACTION_RELATION_WORKFLOW = "create_faction_relations_by_ai"
FACTION_RELATION_GENERATION_STEP = "create_faction_relations"
_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)
_UNSET = object()


def extract_faction_relation_generation_input(
    request: FactionRelationsGenerateRequestV1 | Mapping[str, Any],
) -> dict[str, Any]:
    """提取去除传输态的阵营关系严格生成输入。

    Args:
        request: HTTP 生成请求或确认阶段回传的业务输入。

    Returns:
        不包含 ``use_stream`` 的稳定业务白名单。
    """
    model = (
        request
        if isinstance(request, FactionRelationsGenerateRequestV1)
        else FactionRelationsGenerateRequestV1.model_validate(request)
    )
    return model.model_dump(mode="json", exclude={"use_stream"})


def compute_faction_relation_input_fingerprint(
    request: FactionRelationsGenerateRequestV1 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时方案重算阵营关系候选输入指纹。

    Args:
        request: 确认阶段回传的严格生成输入。
        source_refs: 生成时读取并在确认时重读的正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        绑定输入、来源和执行契约的 SHA-256 十六进制摘要。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_faction_relations_by_ai', request, source_refs, flow_snapshot)


__all__ = [
    "FACTION_RELATION_GENERATION_STEP",
    "FACTION_RELATION_WORKFLOW",
    "compute_faction_relation_input_fingerprint",
    "extract_faction_relation_generation_input",
]
