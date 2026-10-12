"""单卷按需地点普通与 POST SSE 候选预览 API。"""

from __future__ import annotations
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.api.contracts import ObjectIdString
from backend.llm.schemas.location_pydantic import VolumeLocationsPreviewV1


router = APIRouter(prefix="/api/llm", tags=["volume-location-generation"])


@router.post(
    "/novels/{novel_id}/volumes/{volume_id}/locations",
    response_model=VolumeLocationsPreviewV1,
)
async def generate_volume_locations(
    novel_id: ObjectIdString,
    volume_id: ObjectIdString,
    request: GraphRunRequest,
) -> VolumeLocationsPreviewV1:
    """生成目标正式卷所缺的新地点候选，不写正式地点。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        volume_id: 路径中的目标活动卷 ObjectId 字符串。
        request: 目标数量、既有地点选择和公共生成参数。

    Returns:
        已通过严格 Schema、业务后验并带 basis 的候选预览。
    """
    return await generate_task_flow('create_locations_for_volume_by_ai', request, scope={'novel_id': novel_id, 'volume_id': volume_id}, stream=False)


@router.post("/novels/{novel_id}/volumes/{volume_id}/locations/stream")
async def generate_volume_locations_stream(
    novel_id: ObjectIdString,
    volume_id: ObjectIdString,
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 生成目标正式卷所缺的新地点候选。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        volume_id: 路径中的目标活动卷 ObjectId 字符串。
        request: 目标数量、既有地点选择和公共生成参数。

    Returns:
        只包含 progress、单一 done 或单一 error 的 SSE 响应。
    """
    return await generate_task_flow('create_locations_for_volume_by_ai', request, scope={'novel_id': novel_id, 'volume_id': volume_id}, stream=True)


__all__ = ["router"]
