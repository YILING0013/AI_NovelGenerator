"""卷骨架与单卷启动包普通、POST SSE 候选预览 API。"""

from __future__ import annotations
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.api.contracts import ObjectIdString
from backend.llm.schemas.volume_planning_pydantic import VolumeLaunchPreviewV1, VolumeSkeletonPreviewV1


router = APIRouter(prefix="/api/llm", tags=["volume-planning-generation"])


@router.post(
    "/novels/{novel_id}/planning/volume-skeleton",
    response_model=VolumeSkeletonPreviewV1,
)
async def generate_volume_skeleton(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> VolumeSkeletonPreviewV1:
    """生成当前小说的全书卷骨架候选，不写正式卷。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 目标卷数、预算、模式和公共生成参数。

    Returns:
        已通过严格 Schema 与业务后验的卷骨架预览。
    """
    return await generate_task_flow('create_volume_skeleton_by_ai', request, scope={'novel_id': novel_id}, stream=False)


@router.post("/novels/{novel_id}/planning/volume-skeleton/stream")
async def generate_volume_skeleton_stream(
    novel_id: ObjectIdString,
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 生成当前小说的全书卷骨架候选。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        request: 目标卷数、预算、模式和公共生成参数。

    Returns:
        只包含 progress、单一 done 或单一 error 的 SSE 响应。
    """
    return await generate_task_flow('create_volume_skeleton_by_ai', request, scope={'novel_id': novel_id}, stream=True)


@router.post(
    "/novels/{novel_id}/planning/volumes/{volume_id}/launch-package",
    response_model=VolumeLaunchPreviewV1,
)
async def generate_volume_launch_package(
    novel_id: ObjectIdString,
    volume_id: ObjectIdString,
    request: GraphRunRequest,
) -> VolumeLaunchPreviewV1:
    """生成一个正式卷的启动包候选，不写目标或相邻卷。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        volume_id: 路径中的目标活动卷 ObjectId 字符串。
        request: 目标版本、预算偏好和公共生成参数。

    Returns:
        已通过严格 Schema 与业务后验的启动包预览。
    """
    return await generate_task_flow('plan_volume_launch_by_ai', request, scope={'novel_id': novel_id, 'volume_id': volume_id}, stream=False)


@router.post(
    "/novels/{novel_id}/planning/volumes/{volume_id}/launch-package/stream"
)
async def generate_volume_launch_package_stream(
    novel_id: ObjectIdString,
    volume_id: ObjectIdString,
    request: GraphRunRequest,
) -> StreamingResponse:
    """通过 SSE 生成一个正式卷的启动包候选。

    Args:
        novel_id: 路径中的小说 ObjectId 字符串。
        volume_id: 路径中的目标活动卷 ObjectId 字符串。
        request: 目标版本、预算偏好和公共生成参数。

    Returns:
        只包含 progress、单一 done 或单一 error 的 SSE 响应。
    """
    return await generate_task_flow('plan_volume_launch_by_ai', request, scope={'novel_id': novel_id, 'volume_id': volume_id}, stream=True)


__all__ = ["router"]
