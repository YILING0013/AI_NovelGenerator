"""作者管理书内伏笔；生成工作流只有读取权限。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path, Query

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.foreshadowing_contract import (
    FORESHADOWING_ID_PATTERN, ForeshadowingCreateV1, ForeshadowingReadV1,
    ForeshadowingRecordV1, ForeshadowingStatus, ForeshadowingUpdateV1,
    ForeshadowingVersionV1, serialize_foreshadowing,
)
from backend.services.novel.foreshadowing_service import ForeshadowingService


router = APIRouter(prefix="/api/foreshadowings", tags=["foreshadowings"])
ForeshadowingId = Annotated[str, Path(pattern=FORESHADOWING_ID_PATTERN)]


@router.post("/novel/{novel_id}", response_model=ForeshadowingReadV1)
async def create_foreshadowing(novel_id: ObjectIdString, req: ForeshadowingCreateV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """幂等创建一条伏笔计划。

    Args:
        novel_id: 小说 ID。
        req: 计划内容。
        idempotency_key: 固定创建键。
    Returns:
        新计划或原成功快照。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.create(novel_id.lower(), req, idempotency_key=idempotency_key))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.get("/novel/{novel_id}", response_model=list[ForeshadowingReadV1])
async def list_foreshadowings(novel_id: ObjectIdString, deleted: bool = False, include_deleted_novel: bool = False, q: Annotated[str | None, Query(min_length=1, max_length=200)] = None, status: ForeshadowingStatus | None = None, position_kind: Literal["volume", "arc", "scene"] | None = None, position_id: ObjectIdString | None = None) -> list[dict]:
    """读取本书活动或回收站伏笔，可按文字、状态和计划位置筛选。

    Args:
        novel_id: 小说 ID。
        deleted: 只读取回收站，允许已删小说。
        include_deleted_novel: 明确读取已删小说的未回收伏笔，以便逐条清理。
        q: 普通检索文字。
        status: 作者状态。
        position_kind: 计划位置类别。
        position_id: 对应位置 ID。
    Returns:
        伏笔列表。
    """
    try:
        rows = await ForeshadowingService.list(novel_id.lower(), deleted=deleted, include_deleted_novel=include_deleted_novel, q=q, status=status, position_kind=position_kind, position_id=position_id)
        return [serialize_foreshadowing(row) for row in rows]
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.get("/novel/{novel_id}/{identity}", response_model=ForeshadowingReadV1)
async def get_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, include_deleted: bool = False) -> dict:
    """读取当前书内伏笔及证据复核标记。

    Args:
        novel_id: 小说 ID。
        identity: 伏笔业务 ID。
        include_deleted: 明确读取回收站。
    Returns:
        伏笔详情。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.get(novel_id.lower(), identity, include_deleted=include_deleted))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.patch("/novel/{novel_id}/{identity}", response_model=ForeshadowingReadV1)
async def update_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, req: ForeshadowingUpdateV1) -> dict:
    """按作者已读版本局部更新计划。

    Args:
        novel_id: 小说 ID。
        identity: 伏笔业务 ID。
        req: 原版本和修改字段。
    Returns:
        保存后的伏笔。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.update(novel_id.lower(), identity, req))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.post("/novel/{novel_id}/{identity}/records", response_model=ForeshadowingReadV1)
async def record_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, req: ForeshadowingRecordV1) -> dict:
    """作者明确记录埋设、回收、放弃或重新计划。

    Args:
        novel_id: 小说 ID。
        identity: 伏笔业务 ID。
        req: 已读版本、目标状态和原文证据。
    Returns:
        保存后的状态与证据。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.record(novel_id.lower(), identity, req))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.post("/novel/{novel_id}/{identity}/delete", response_model=ForeshadowingReadV1)
async def delete_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, req: ForeshadowingVersionV1) -> dict:
    """逐条移入回收站，已删小说也可以清理其伏笔。

    Args:
        novel_id: 小说 ID。
        identity: 伏笔业务 ID。
        req: 已读版本。
    Returns:
        回收后的记录。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.set_deleted(novel_id.lower(), identity, expected_version=req.expected_version, deleted=True))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.post("/novel/{novel_id}/{identity}/restore", response_model=ForeshadowingReadV1)
async def restore_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, req: ForeshadowingVersionV1) -> dict:
    """恢复伏笔前重查同书活动计划位置及不可变证据。

    Args:
        novel_id: 小说 ID。
        identity: 回收站伏笔业务 ID。
        req: 已读版本。
    Returns:
        恢复后的记录。
    """
    try:
        return serialize_foreshadowing(await ForeshadowingService.set_deleted(novel_id.lower(), identity, expected_version=req.expected_version, deleted=False))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")


@router.post("/novel/{novel_id}/{identity}/hard-delete")
async def hard_delete_foreshadowing(novel_id: ObjectIdString, identity: ForeshadowingId, req: ForeshadowingVersionV1) -> dict:
    """永久删除这一条回收站伏笔并解除来源保护。

    Args:
        novel_id: 小说 ID。
        identity: 回收站伏笔业务 ID。
        req: 已读版本。
    Returns:
        已删除的伏笔 ID。
    """
    try:
        await ForeshadowingService.hard_delete(novel_id.lower(), identity, expected_version=req.expected_version)
        return {"foreshadowing_id": identity, "deleted": True}
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="FORESHADOWING", label="伏笔")
