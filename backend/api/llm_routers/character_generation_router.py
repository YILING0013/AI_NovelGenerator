"""全书级核心角色与人物关系的直接生成预览 API。"""

from __future__ import annotations
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.services.llm.candidate_contract import CandidateGenerationEnvelopeV1


router = APIRouter(prefix="/api/llm", tags=["character-generation"])


@router.post(
    "/generate-core-characters",
    response_model=CandidateGenerationEnvelopeV1,
)
async def generate_core_characters(
    request: GraphRunRequest,
) -> CandidateGenerationEnvelopeV1:
    """直接生成全书级核心角色和势力绑定候选，不写数据库。

    Args:
        request: 小说 ID、角色数量、指导文本和扁平七项生成参数。

    Returns:
        已通过结构与当前小说事实校验的候选结果。
    """
    return await generate_task_flow('create_characters_by_ai', request, scope={}, stream=False)


@router.post("/generate-core-characters/stream")
async def generate_core_characters_stream(
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 直接生成全书级核心角色候选。

    Args:
        request: 小说 ID、角色数量、指导文本和扁平七项生成参数。

    Returns:
        仅包含 progress、done 或 error 的 SSE 响应。
    """
    return await generate_task_flow('create_characters_by_ai', request, scope={}, stream=True)


@router.post(
    "/generate-character-relations",
    response_model=CandidateGenerationEnvelopeV1,
)
async def generate_character_relations(
    request: GraphRunRequest,
) -> CandidateGenerationEnvelopeV1:
    """直接生成仅追加的全书级角色关系候选，不写数据库。

    Args:
        request: 小说 ID、角色白名单、关系约束和扁平七项生成参数。

    Returns:
        已通过结构、端点和现有关系冲突校验的候选结果。
    """
    return await generate_task_flow('create_character_relations_by_ai', request, scope={}, stream=False)


@router.post("/generate-character-relations/stream")
async def generate_character_relations_stream(
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 直接生成仅追加的全书级角色关系候选。

    Args:
        request: 小说 ID、角色白名单、关系约束和扁平七项生成参数。

    Returns:
        仅包含 progress、done 或 error 的 SSE 响应。
    """
    return await generate_task_flow('create_character_relations_by_ai', request, scope={}, stream=True)


@router.post(
    "/generate-faction-relations",
    response_model=CandidateGenerationEnvelopeV1,
)
async def generate_faction_relations(
    request: GraphRunRequest,
) -> CandidateGenerationEnvelopeV1:
    """直接生成仅追加的阵营关系候选，不写数据库。

    Args:
        request: 小说 ID、阵营白名单、关系约束和扁平七项生成参数。

    Returns:
        已通过结构、端点和现有关系冲突校验的候选结果。
    """
    return await generate_task_flow('create_faction_relations_by_ai', request, scope={}, stream=False)


@router.post("/generate-faction-relations/stream")
async def generate_faction_relations_stream(
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 直接生成仅追加的阵营关系候选。

    Args:
        request: 小说 ID、阵营白名单、关系约束和扁平七项生成参数。

    Returns:
        仅包含 progress、done 或 error 的 SSE 响应。
    """
    return await generate_task_flow('create_faction_relations_by_ai', request, scope={}, stream=True)


__all__ = ["router"]
