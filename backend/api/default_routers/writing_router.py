"""当前位置的逐级生成、只读就绪检查和审核确认。"""

from __future__ import annotations

from typing import Literal, NoReturn

from fastapi import APIRouter, Header, Request
from pymongo.errors import ConnectionFailure, PyMongoError

from backend.api.contracts import ObjectIdString
from backend.api.error_protocol import DomainApiError, api_http_exception, exception_to_error
from backend.db.errors import DatabaseError, DuplicateKeyError, IdempotencyConflictError, TransactionNotSupportedError, VersionConflictError
from backend.services.novel.writing_contract import WritingConfirmV1, WritingConfirmResultV1, WritingGenerationEnvelopeV1, WritingReadinessV1
from backend.services.novel.writing_context import get_writing_readiness
from backend.services.novel.writing_generation import confirm_writing
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(prefix="/api", tags=["writing"])
EXPECTED_ERRORS = (DomainApiError, DatabaseError, PyMongoError, ValueError)


def raise_writing_http_error(exc: Exception) -> NoReturn:
    """把写作确认的实际失败转换为稳定错误，不暴露数据库消息。

    Args:
        exc: 领域、校验或数据库异常。
    Returns:
        不返回，抛出公开 HTTP 异常。
    """
    if isinstance(exc, TransactionNotSupportedError):
        raise api_http_exception(status_code=503, code="WRITING_TRANSACTION_REQUIRED", message="确认保存需要启用 MongoDB 事务并连接副本集") from exc
    if isinstance(exc, ConnectionFailure):
        raise api_http_exception(status_code=503, code="DATABASE_UNAVAILABLE", message="数据库连接暂时不可用，请保留候选并使用原请求重试") from exc
    if isinstance(exc, PyMongoError):
        if exc.has_error_label("UnknownTransactionCommitResult"):
            raise api_http_exception(status_code=503, code="DATABASE_UNAVAILABLE", message="数据库暂时无法确认保存结果，请保留候选并使用原请求重试") from exc
        if exc.has_error_label("TransientTransactionError") or getattr(exc, "code", None) in {11000, 112}:
            raise api_http_exception(status_code=409, code="WRITING_WRITE_CONFLICT", message="资料正在被修改，请保留候选并使用原请求重试") from exc
        raise api_http_exception(status_code=503, code="DATABASE_UNAVAILABLE", message="数据库暂时不可用") from exc
    status, code, message, fields, details = exception_to_error(exc, fallback_message="写作请求失败")
    if isinstance(exc, VersionConflictError):
        code = "WRITING_VERSION_CONFLICT"
    elif isinstance(exc, IdempotencyConflictError):
        code = "WRITING_IDEMPOTENCY_CONFLICT"
    elif isinstance(exc, DuplicateKeyError):
        code = "WRITING_WRITE_CONFLICT"
    raise api_http_exception(status_code=status, code=code, message=message, field_errors=fields, details=details) from exc


@router.get("/novels/{novel_id}/planning-readiness", response_model=WritingReadinessV1)
async def writing_readiness(novel_id: ObjectIdString, target_type: Literal["volume", "arc", "scene", "chapter"], target_id: ObjectIdString) -> dict:
    """只读查询当前部分的局部缺项，不调用模型或保存进度。

    Args:
        novel_id: 当前小说。
        target_type: 当前部分类型。
        target_id: 当前部分 ID。
    Returns:
        当前可执行动作、缺项和父链。
    """
    try:
        return await get_writing_readiness(novel_id, target_type, target_id)
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


async def _generate(task: str, novel_id: str, target_type: str, target_id: str, req: GraphRunRequest, http_request: Request):
    """让四个生成入口共用响应和错误处理，不把保存放进图。

    Args:
        task: 路由固定的任务。
        novel_id: 当前小说。
        target_type: 当前对象类型。
        target_id: 当前对象 ID。
        req: 图请求。
        http_request: 当前 HTTP 请求。
    Returns:
        候选信封或流式响应。
    """
    try:
        return await generate_task_flow(task, req, scope={"novel_id": str(novel_id).lower(), "target_type": target_type, "target_id": str(target_id).lower()}, stream=req.use_stream or http_request.url.path.endswith("/stream"))
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/planning/arcs", response_model=WritingGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/volumes/{volume_id}/planning/arcs/stream")
async def generate_arc_plans(novel_id: ObjectIdString, volume_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """读取当前卷并生成篇章候选，审核确认前不写业务数据。

    Args:
        novel_id: 当前小说。
        volume_id: 当前卷。
        req: 固定图版本与开始输入。
        http_request: 用于识别显式流式入口。
    Returns:
        普通候选信封或 SSE 响应。
    """
    return await _generate("plan_arcs_by_ai", novel_id, "volume", volume_id, req, http_request)


@router.post("/llm/novels/{novel_id}/arcs/{arc_id}/planning/scenes", response_model=WritingGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/arcs/{arc_id}/planning/scenes/stream")
async def generate_scene_plans(novel_id: ObjectIdString, arc_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """生成当前篇章内的场景候选。

    Args:
        novel_id: 当前小说。
        arc_id: 当前篇章。
        req: 固定图版本与开始输入。
        http_request: 当前 HTTP 请求。
    Returns:
        候选信封或 SSE 响应。
    """
    return await _generate("plan_scenes_by_ai", novel_id, "arc", arc_id, req, http_request)


@router.post("/llm/novels/{novel_id}/scenes/{scene_id}/planning/chapters", response_model=WritingGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/scenes/{scene_id}/planning/chapters/stream")
async def generate_chapter_plans(novel_id: ObjectIdString, scene_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """生成当前场景内的章计划，正文仍为空。

    Args:
        novel_id: 当前小说。
        scene_id: 当前场景。
        req: 固定图版本与开始输入。
        http_request: 当前 HTTP 请求。
    Returns:
        候选信封或 SSE 响应。
    """
    return await _generate("plan_chapters_by_ai", novel_id, "scene", scene_id, req, http_request)


@router.post("/llm/novels/{novel_id}/chapters/{chapter_id}/writing", response_model=WritingGenerationEnvelopeV1)
@router.post("/llm/novels/{novel_id}/chapters/{chapter_id}/writing/stream")
async def generate_chapter_content(novel_id: ObjectIdString, chapter_id: ObjectIdString, req: GraphRunRequest, http_request: Request):
    """生成已选章节的正文，绑定其生成时版本。

    Args:
        novel_id: 当前小说。
        chapter_id: 当前章节。
        req: 固定图版本、目标版本与开始输入。
        http_request: 当前 HTTP 请求。
    Returns:
        可审核的正文候选或 SSE 响应。
    """
    return await _generate("write_chapter_by_ai", novel_id, "chapter", chapter_id, req, http_request)


async def _confirm(task: str, target_id: str, req: WritingConfirmV1, idempotency_key: str) -> dict:
    """统一四个确认入口的事务和公开错误边界。

    Args:
        task: 确认任务。
        target_id: 路径中的目标。
        req: 审核候选。
        idempotency_key: 本次确认键。
    Returns:
        正式对象与稳定 ID。
    """
    try:
        return await confirm_writing(task, str(target_id).lower(), req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_writing_http_error(exc)


@router.post("/arcs/volume/{volume_id}/confirm", response_model=WritingConfirmResultV1)
async def confirm_arc_plans(volume_id: ObjectIdString, req: WritingConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """一次事务保存卷下审核后的篇章批次。

    Args:
        volume_id: 当前卷。
        req: 审核候选及原依据。
        idempotency_key: 重试时保持不变的确认键。
    Returns:
        正式篇章和稳定 ID。
    """
    return await _confirm("plan_arcs_by_ai", volume_id, req, idempotency_key)


@router.post("/scenes/arc/{arc_id}/confirm", response_model=WritingConfirmResultV1)
async def confirm_scene_plans(arc_id: ObjectIdString, req: WritingConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """一次事务保存篇章下审核后的场景批次。

    Args:
        arc_id: 当前篇章。
        req: 审核候选及原依据。
        idempotency_key: 本次确认键。
    Returns:
        正式场景和稳定 ID。
    """
    return await _confirm("plan_scenes_by_ai", arc_id, req, idempotency_key)


@router.post("/chapters/scene/{scene_id}/confirm", response_model=WritingConfirmResultV1)
async def confirm_chapter_plans(scene_id: ObjectIdString, req: WritingConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """一次事务保存空正文的章计划批次。

    Args:
        scene_id: 当前场景。
        req: 审核候选及原依据。
        idempotency_key: 本次确认键。
    Returns:
        正式章节和稳定 ID。
    """
    return await _confirm("plan_chapters_by_ai", scene_id, req, idempotency_key)


@router.post("/chapters/{chapter_id}/content/confirm", response_model=WritingConfirmResultV1)
async def confirm_chapter_content(chapter_id: ObjectIdString, req: WritingConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """按生成时的目标版本确认正文，冲突不覆盖手工稿。

    Args:
        chapter_id: 当前章。
        req: 审核正文、原依据与相同目标版本。
        idempotency_key: 本次确认键。
    Returns:
        已保存正文的章节。
    """
    return await _confirm("write_chapter_by_ai", chapter_id, req, idempotency_key)
