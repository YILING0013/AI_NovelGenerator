"""单卷、单篇章剧情生成确认与卷资料阶段确认。"""

from typing import Literal

from fastapi import APIRouter, Header, Request

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.writing_router import EXPECTED_ERRORS, raise_writing_http_error
from backend.services.novel.plot_contract import PlotConfirmV1, PlotGenerationEnvelopeV1, VolumePreparationConfirmV1
from backend.services.novel.plot_service import confirm_plot, confirm_preparation
from backend.services.novel.writing_contract import WritingConfirmResultV1
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(prefix="/api", tags=["plot"])


@router.post("/llm/novels/{novel_id}/volumes/{target_id}/plot", response_model=PlotGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/volumes/{target_id}/plot/stream")
async def generate_volume_plot(novel_id: ObjectIdString, target_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """依据当前卷与相邻边界生成详细剧情，确认前不保存。

    Args:
        novel_id: 当前小说。
        target_id: 当前卷。
        req: 固定流程修订和生成输入。
        http_request: 用于识别流式路径。
    Returns:
        剧情候选或 SSE 事件。
    """
    try:
        return await generate_task_flow("generate_volume_plot_by_ai", req, scope={"novel_id": str(novel_id), "target_type": "volume", "target_id": str(target_id)}, stream=req.use_stream or http_request.url.path.endswith("/stream"))
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/llm/novels/{novel_id}/arcs/{target_id}/plot", response_model=PlotGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/arcs/{target_id}/plot/stream")
async def generate_arc_plot(novel_id: ObjectIdString, target_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """依据当前篇章及卷剧情生成详细剧情。

    Args:
        novel_id: 当前小说。
        target_id: 当前篇章。
        req: 固定流程修订和生成输入。
        http_request: 用于识别流式路径。
    Returns:
        剧情候选或 SSE 事件。
    """
    try:
        return await generate_task_flow("generate_arc_plot_by_ai", req, scope={"novel_id": str(novel_id), "target_type": "arc", "target_id": str(target_id)}, stream=req.use_stream or http_request.url.path.endswith("/stream"))
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/volumes/{target_id}/plot/confirm", response_model=WritingConfirmResultV1)
async def confirm_volume_plot(target_id: ObjectIdString, req: PlotConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    """在同一事务中确认当前卷剧情和允许调整的规划。

    Args:
        target_id: 当前卷。
        req: 审核结果和原始依据。
        idempotency_key: 本次确认的稳定重试键。
    Returns:
        正式卷。
    """
    try:
        return await confirm_plot("generate_volume_plot_by_ai", str(target_id), req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/arcs/{target_id}/plot/confirm", response_model=WritingConfirmResultV1)
async def confirm_arc_plot(target_id: ObjectIdString, req: PlotConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    """在同一事务中确认当前篇章剧情。

    Args:
        target_id: 当前篇章。
        req: 审核结果和原始依据。
        idempotency_key: 本次确认的稳定重试键。
    Returns:
        正式篇章。
    """
    try:
        return await confirm_plot("generate_arc_plot_by_ai", str(target_id), req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/novels/{novel_id}/volumes/{volume_id}/preparation/{kind}/confirm")
async def confirm_volume_preparation(novel_id: ObjectIdString, volume_id: ObjectIdString, kind: Literal["factions", "characters", "locations"], req: VolumePreparationConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    """作者检查当前已有资料后确认阶段，允许没有该类实体。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        kind: 当前资料类别。
        req: 已读版本及地点参与选择。
        idempotency_key: 本次确认的稳定重试键。
    Returns:
        带准备标记的正式卷。
    """
    try:
        return await confirm_preparation(str(novel_id), str(volume_id), kind, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)
