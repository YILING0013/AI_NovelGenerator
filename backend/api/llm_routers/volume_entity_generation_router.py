"""单卷人物与势力的普通／SSE 生成及审核确认接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pymongo.errors import PyMongoError

from backend.api.contracts import ObjectIdString
from backend.api.error_protocol import DomainApiError, exception_to_error
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.llm.schemas.volume_entity_pydantic import VolumeCharactersPreviewV1, VolumeFactionsPreviewV1, VolumeCharactersConfirmV1, VolumeCharactersPlanConfirmV1, VolumeCharactersInitialFactsConfirmV1, VolumeFactionsConfirmV1, VolumeFactionsPlanConfirmV1, VolumeCharactersConfirmedV1, VolumeFactionsConfirmedV1
from backend.services.llm.candidate_contract import CandidateIdempotencyKey
from backend.services.llm.volume_entity_generation_service import confirm_volume_entities
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(prefix="/api", tags=["volume-entity-generation"])


@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/characters", response_model=VolumeCharactersPreviewV1)
async def generate_volume_characters(novel_id: ObjectIdString, volume_id: ObjectIdString, request: GraphRunRequest):
    """生成当前卷人物档案及状态候选，不保存业务内容。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 任务图或普通作者输入。
    Returns:
        可编辑的人物候选和原始生成依据。
    """
    return await generate_task_flow("create_characters_for_volume_by_ai", request, scope={"novel_id": novel_id, "volume_id": volume_id})


@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/characters/stream")
async def stream_volume_characters(novel_id: ObjectIdString, volume_id: ObjectIdString, request: GraphRunRequest) -> StreamingResponse:
    """通过任务图 SSE 生成当前卷人物候选。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 任务图或普通作者输入。
    Returns:
        节点进度和唯一完成／失败事件。
    """
    return await generate_task_flow("create_characters_for_volume_by_ai", request, scope={"novel_id": novel_id, "volume_id": volume_id}, stream=True)


@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/factions", response_model=VolumeFactionsPreviewV1)
async def generate_volume_factions(novel_id: ObjectIdString, volume_id: ObjectIdString, request: GraphRunRequest):
    """生成当前卷势力档案及状态候选，不保存业务内容。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 任务图或普通作者输入。
    Returns:
        可编辑的势力候选和原始生成依据。
    """
    return await generate_task_flow("create_factions_for_volume_by_ai", request, scope={"novel_id": novel_id, "volume_id": volume_id})


@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/factions/stream")
async def stream_volume_factions(novel_id: ObjectIdString, volume_id: ObjectIdString, request: GraphRunRequest) -> StreamingResponse:
    """通过任务图 SSE 生成当前卷势力候选。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 任务图或普通作者输入。
    Returns:
        节点进度和唯一完成／失败事件。
    """
    return await generate_task_flow("create_factions_for_volume_by_ai", request, scope={"novel_id": novel_id, "volume_id": volume_id}, stream=True)


async def _confirm(task: str, novel_id: str, volume_id: str, request, key: str):
    """为两个确认入口统一保留业务错误与数据库不可用提示。

    Args:
        task: 当前卷内角色或势力任务。
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 审核后的候选及原始依据。
        key: 本次确认和重试共用的请求键。
    Returns:
        已保存的卷状态及正式档案 ID 映射。
    """
    try:
        return await confirm_volume_entities(task, novel_id, volume_id, request, idempotency_key=key)
    except PyMongoError as exc:
        raise DomainApiError("DATABASE_UNAVAILABLE", "数据库暂时不可用，请保留候选后重试", status_code=503) from exc
    except (NotFoundError, DuplicateKeyError, ValueError) as exc:
        status, code, message, fields, details = exception_to_error(exc)
        raise DomainApiError(code, message, status_code=status, field_errors=fields, details=details) from exc


@router.post("/novels/{novel_id}/volumes/{volume_id}/characters/confirm", response_model=VolumeCharactersConfirmedV1)
async def confirm_characters(novel_id: ObjectIdString, volume_id: ObjectIdString, request: VolumeCharactersInitialFactsConfirmV1 | VolumeCharactersPlanConfirmV1 | VolumeCharactersConfirmV1, idempotency_key: Annotated[CandidateIdempotencyKey, Header(alias="Idempotency-Key")]):
    """一次确认人物档案与当前卷状态，失败整体回滚。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 编辑后的候选与生成时依据。
        idempotency_key: 本次确认和重试保持不变的请求键。
    Returns:
        已保存卷状态和人物正式 ID 映射。
    """
    return await _confirm("create_characters_for_volume_by_ai", novel_id, volume_id, request, idempotency_key)


@router.post("/novels/{novel_id}/volumes/{volume_id}/factions/confirm", response_model=VolumeFactionsConfirmedV1)
async def confirm_factions(novel_id: ObjectIdString, volume_id: ObjectIdString, request: VolumeFactionsPlanConfirmV1 | VolumeFactionsConfirmV1, idempotency_key: Annotated[CandidateIdempotencyKey, Header(alias="Idempotency-Key")]):
    """一次确认势力档案与当前卷状态，失败整体回滚。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        request: 编辑后的候选与生成时依据。
        idempotency_key: 本次确认和重试保持不变的请求键。
    Returns:
        已保存卷状态和势力正式 ID 映射。
    """
    return await _confirm("create_factions_for_volume_by_ai", novel_id, volume_id, request, idempotency_key)
