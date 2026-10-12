"""小说物品普通与 POST SSE 候选预览 API。"""

from __future__ import annotations
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.api.contracts import ObjectIdString
from backend.llm.schemas.item_pydantic import ItemsPreviewV1


router = APIRouter(prefix="/api/llm", tags=["item-generation"])


@router.post(
    "/novels/{novel_id}/items",
    response_model=ItemsPreviewV1,
)
async def generate_items(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> ItemsPreviewV1:
    """生成当前小说的物品候选，不写正式物品。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 数量、增量开关和公共生成参数。

    Returns:
        已通过严格 Schema、业务后验并带 basis 的候选预览。
    """
    return await generate_task_flow('create_items_by_ai', request, scope={'novel_id': novel_id}, stream=False)


@router.post("/novels/{novel_id}/items/stream")
async def generate_items_stream(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 生成当前小说的物品候选。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 数量、增量开关和公共生成参数。

    Returns:
        只包含 progress、单一 done 或单一 error 的 SSE 响应。
    """
    return await generate_task_flow('create_items_by_ai', request, scope={'novel_id': novel_id}, stream=True)


__all__ = ["router"]
