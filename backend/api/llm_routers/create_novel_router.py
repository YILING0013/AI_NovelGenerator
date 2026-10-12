"""通过当前任务图生成小说资料、字段改写和核心势力候选。"""

from __future__ import annotations

from fastapi import APIRouter

from backend.services.llm.candidate_contract import CandidateGenerationEnvelopeV1
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post(
    "/generate-core-factions",
    response_model=CandidateGenerationEnvelopeV1,
)
async def generate_core_factions(
    req: GraphRunRequest,
) -> CandidateGenerationEnvelopeV1:
    """基于已保存小说信息生成核心阵营预览，不写入数据库。

    Args:
        req: 生成核心阵营的请求参数。

    Returns:
        包含 core_factions 与 faction_relations 的预览结果。
    """
    return await generate_task_flow('create_factions_by_ai', req, scope={}, stream=False)


@router.post("/generate-core-factions/stream")
async def generate_core_factions_stream(req: GraphRunRequest):
    """通过 SSE 生成核心阵营预览，支持 Provider 流式保活。
    Args:
        req: 核心阵营生成请求，use_stream 为 true 且 Provider 支持时启用流式接口。
    Returns:
        SSE 响应；progress 事件只表示保活进度，done 事件返回最终结构化结果。
    """
    return await generate_task_flow('create_factions_by_ai', req, scope={}, stream=True)


@router.post(
    "/rewrite-novel-field",
    response_model=CandidateGenerationEnvelopeV1,
)
async def rewrite_novel_field(
    req: GraphRunRequest,
) -> CandidateGenerationEnvelopeV1:
    """使用指定 Provider 改写创建态小说信息中的单个字段。

    Args:
        req: 前端提交的字段改写请求。

    Returns:
        包含目标字段和改写后字段值的响应字典。
    """
    return await generate_task_flow('rewrite_novel_field_by_ai', req, scope={}, stream=False)


@router.post("/rewrite-novel-field/stream")
async def rewrite_novel_field_stream(req: GraphRunRequest):
    """通过 SSE 改写创建态小说字段，支持 Provider 流式保活。
    Args:
        req: 字段改写请求，use_stream 为 true 且 Provider 支持时启用流式接口。
    Returns:
        SSE 响应；progress 事件只表示保活进度，done 事件返回最终字段改写结果。
    """
    return await generate_task_flow('rewrite_novel_field_by_ai', req, scope={}, stream=True)


@router.post("/create-novel-by-ai")
async def create_novel_by_ai(req: GraphRunRequest):
    """执行选定的建书任务图，并通过 SSE 返回节点进度和小说候选。

    Args:
        req: 当前任务图、作者输入和可复用的节点结果。

    Returns:
        SSE 响应；每一步通过 step 事件推送，结束时通过 done 事件返回结果或部分结果。
    """
    return await generate_task_flow('create_novel_by_ai', req, scope={}, stream=True)
