"""核心世界规则普通与 POST SSE 候选预览 API。"""

from __future__ import annotations
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.api.contracts import ObjectIdString
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesPreviewV1


router = APIRouter(prefix="/api/llm", tags=["world-rule-generation"])


@router.post(
    "/novels/{novel_id}/world-rules/core",
    response_model=CoreWorldRulesPreviewV1,
)
async def generate_core_world_rules(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> CoreWorldRulesPreviewV1:
    """生成当前小说核心世界规则候选，不写正式集合。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 数量、增量开关和公共生成参数。

    Returns:
        已通过严格 Schema 与业务后验的完整候选预览。
    """
    return await generate_task_flow('create_world_rules_by_ai', request, scope={'novel_id': novel_id}, stream=False)


@router.post("/novels/{novel_id}/world-rules/core/stream")
async def generate_core_world_rules_stream(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 生成当前小说核心世界规则候选。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 数量、增量开关和公共生成参数。

    Returns:
        只包含 progress、单一 done 或单一 error 的 SSE 响应。
    """
    return await generate_task_flow('create_world_rules_by_ai', request, scope={'novel_id': novel_id}, stream=True)


__all__ = ["router"]
