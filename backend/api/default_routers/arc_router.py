"""卷下篇章规划与回收站 API。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, Query
from pymongo.errors import PyMongoError

from backend.api.contracts import ObjectIdString
from backend.api.error_protocol import DomainApiError, api_http_exception, exception_to_error
from backend.db.errors import DatabaseError, DuplicateKeyError, IdempotencyConflictError, NotFoundError, TransactionNotSupportedError, VersionConflictError
from backend.services.novel.arc_contract import ArcCreateV1, ArcDeleteImpactV1, ArcHardDeleteV1, ArcListV1, ArcReadV1, ArcReorderV1, ArcUpdateV1, ArcVersionV1, serialize_arc
from backend.services.novel.arc_service import ArcService


router = APIRouter(prefix="/api/arcs", tags=["arcs"])
EXPECTED_ERRORS = (DomainApiError, DatabaseError, PyMongoError, ValueError)


def raise_arc_http_error(exc: Exception, *, prefix: str = "ARC", label: str = "篇章") -> NoReturn:
    """将已知篇章错误转换成稳定、安全的公开响应。

    Args:
        exc: 已知业务、字段或数据库错误。
        prefix: 当前层级的错误码前缀。
        label: 当前层级的界面名称。

    Returns:
        不返回，抛出对应 HTTP 异常。
    """
    if isinstance(exc, TransactionNotSupportedError):
        raise api_http_exception(status_code=503, code=f"{prefix}_TRANSACTION_REQUIRED", message=f"{label}保存需要启用 MongoDB 事务并连接副本集") from exc
    if isinstance(exc, PyMongoError):
        if exc.has_error_label("TransientTransactionError") or getattr(exc, "code", None) in {11000, 112}:
            raise api_http_exception(status_code=409, code=f"{prefix}_WRITE_CONFLICT", message="资料正在被其他操作修改，请使用原请求重试") from exc
        raise api_http_exception(status_code=503, code="DATABASE_UNAVAILABLE", message="数据库暂时不可用，请稍后重试") from exc
    status, code, message, fields, details = exception_to_error(exc, fallback_message=f"{label}请求处理失败")
    if isinstance(exc, IdempotencyConflictError):
        code = f"{prefix}_IDEMPOTENCY_CONFLICT"
    elif isinstance(exc, VersionConflictError):
        code = f"{prefix}_VERSION_CONFLICT"
    elif isinstance(exc, DuplicateKeyError):
        code = f"{prefix}_WRITE_CONFLICT"
    elif isinstance(exc, NotFoundError):
        code = f"{prefix}_NOT_FOUND"
    raise api_http_exception(status_code=status, code=code, message=message, field_errors=fields, details=details) from exc


@router.post("/volume/{volume_id}", response_model=ArcReadV1)
async def create_arc(volume_id: ObjectIdString, req: ArcCreateV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """使用幂等键在卷末创建篇章。

    Args:
        volume_id: 所属卷 ID。
        req: 标题、摘要和规划。
        idempotency_key: 重试时保持不变的创建键。

    Returns:
        新篇章或原请求创建的篇章。
    """
    try:
        arc = await ArcService.create_arc(volume_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return serialize_arc(arc)


@router.get("/volume/{volume_id}", response_model=ArcListV1)
async def list_volume_arcs(volume_id: ObjectIdString, deleted: bool = False) -> dict:
    """读取卷下的活动篇章或篇章回收站。

    Args:
        volume_id: 所属卷 ID。
        deleted: 是否读取回收站。

    Returns:
        按卷内顺序排列的篇章。
    """
    try:
        arcs = await ArcService.list_arcs(volume_id, deleted=deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return {"data": [serialize_arc(arc) for arc in arcs]}


@router.get("/{arc_id}", response_model=ArcReadV1)
async def get_arc(arc_id: ObjectIdString, include_deleted: bool = False) -> dict:
    """读取篇章详情并检查活动父链。

    Args:
        arc_id: 篇章 ID。
        include_deleted: 是否允许回收站详情。

    Returns:
        完整篇章的公开字段。
    """
    try:
        arc = await ArcService.get_arc(arc_id, include_deleted=include_deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return serialize_arc(arc)


@router.patch("/volume/{volume_id}/reorder", response_model=ArcListV1)
async def reorder_arcs(volume_id: ObjectIdString, req: ArcReorderV1) -> dict:
    """完整重排当前卷的活动篇章。

    Args:
        volume_id: 父卷 ID。
        req: 全部篇章的版本和新序号。
    Returns:
        新顺序下的篇章目录。
    """
    try:
        arcs = await ArcService.reorder_arcs(volume_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return {"data": [serialize_arc(arc) for arc in arcs]}


@router.get("/{arc_id}/delete-impact", response_model=ArcDeleteImpactV1)
async def get_arc_delete_impact(arc_id: ObjectIdString) -> dict:
    """显示阻止篇章删除的活动和回收站下级数量。

    Args:
        arc_id: 篇章 ID。
    Returns:
        场景与章节数量。
    """
    try:
        return await ArcService.get_delete_impact(arc_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)


@router.put("/{arc_id}", response_model=ArcReadV1)
async def update_arc(arc_id: ObjectIdString, req: ArcUpdateV1) -> dict:
    """按版本局部修改篇章内容。

    Args:
        arc_id: 篇章 ID。
        req: 明确修改的字段和已读版本。

    Returns:
        保存后的完整篇章。
    """
    try:
        arc = await ArcService.update_arc(arc_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return serialize_arc(arc)


@router.delete("/{arc_id}", response_model=ArcReadV1)
async def delete_arc(arc_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)]) -> dict:
    """按版本将篇章移入回收站。

    Args:
        arc_id: 篇章 ID。
        expected_version: 已读取的篇章版本。

    Returns:
        回收站篇章的完整内容。
    """
    try:
        arc = await ArcService.set_deleted(arc_id, expected_version=expected_version, deleted=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return serialize_arc(arc)


@router.post("/{arc_id}/restore", response_model=ArcReadV1)
async def restore_arc(arc_id: ObjectIdString, req: ArcVersionV1) -> dict:
    """将回收站篇章恢复到所属卷末尾。

    Args:
        arc_id: 篇章 ID。
        req: 回收站篇章的版本。

    Returns:
        恢复后的完整篇章。
    """
    try:
        arc = await ArcService.set_deleted(arc_id, expected_version=req.expected_version, deleted=False)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return serialize_arc(arc)


@router.delete("/{arc_id}/hard", response_model=ArcHardDeleteV1)
async def hard_delete_arc(arc_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)]) -> dict:
    """永久删除已经没有下级记录的回收站篇章。

    Args:
        arc_id: 篇章 ID。
        expected_version: 已读取的篇章版本。

    Returns:
        已删除篇章的 ID 和成功标记。
    """
    try:
        await ArcService.hard_delete_arc(arc_id, expected_version=expected_version)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc)
    return {"arc_id": arc_id.lower(), "deleted": True}
