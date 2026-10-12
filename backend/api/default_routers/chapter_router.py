"""场景下章节规划与回收站 API。"""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Header, Path, Query
from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.chapter_contract import ChapterCreateV2, ChapterHardDeleteV2, ChapterListV2, ChapterReadV2, ChapterReorderV2, ChapterUpdateV2, ChapterVersionV2, serialize_chapter
from backend.services.novel.chapter_service import ChapterService, load_chapter_parent_chain
from backend.services.novel.chapter_revision_contract import ChapterHistoryDeleteImpactV1, ChapterRevisionCompareV1, ChapterRevisionListV1, ChapterRevisionReadV1, ChapterRevisionRestoreV1, serialize_chapter_revision
from backend.db.base import BaseRepository

router = APIRouter(prefix="/api/chapters", tags=["chapters"])


@router.get("/{chapter_id}/revisions/{version}/compare", response_model=ChapterRevisionCompareV1)
async def compare_chapter_revision(chapter_id: ObjectIdString, version: Annotated[int, Path(ge=1, le=2**63 - 1)], include_deleted: bool = False) -> dict:
    """比较历史与当前保存稿。

    Args:
        chapter_id: 章节 ID。
        version: 历史业务版本。
        include_deleted: 是否读取回收站章节。
    Returns:
        同次读取的两份稿和变化字段。
    """
    try:
        return await ChapterService.compare_revision(chapter_id, version, include_deleted=include_deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")


@router.post("/{chapter_id}/revisions/{version}/restore", response_model=ChapterReadV2)
async def restore_chapter_revision(chapter_id: ObjectIdString, version: Annotated[int, Path(ge=1, le=2**63 - 1)], req: ChapterRevisionRestoreV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """明确确认整稿恢复，以新版本保存。

    Args:
        chapter_id: 活动章节 ID。
        version: 旧稿业务版本。
        req: 已读当前版本。
        idempotency_key: 原请求重试使用的确认键。
    Returns:
        本次新保存的章节。
    """
    try:
        return await ChapterService.restore_revision(chapter_id, version, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")


@router.get("/{chapter_id}/revisions", response_model=ChapterRevisionListV1)
async def list_chapter_revisions(chapter_id: ObjectIdString, include_deleted: bool = False, limit: Annotated[int, Query(ge=1, le=100)] = 50, before_version: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None) -> dict:
    """只读分页历史目录。

    Args:
        chapter_id: 章节 ID。
        include_deleted: 是否允许回收站章节。
        limit: 每页数量，最多 100 条，不加载正文。
        before_version: 下一页使用上一页返回的版本游标。
    Returns:
        不含正文的版本目录。
    """
    try:
        page = await ChapterService.list_revisions(chapter_id, include_deleted=include_deleted, limit=limit, before_version=before_version)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return {"data": [serialize_chapter_revision(row, include_content=False) for row in page["data"]], "next_before_version": page["next_before_version"]}


@router.get("/{chapter_id}/revisions/{version}", response_model=ChapterRevisionReadV1)
async def get_chapter_revision(chapter_id: ObjectIdString, version: Annotated[int, Path(ge=1, le=2**63 - 1)], include_deleted: bool = False) -> dict:
    """读取一份不可变旧稿。

    Args:
        chapter_id: 章节 ID。
        version: 修订对应的业务版本。
        include_deleted: 是否允许回收站章节。
    Returns:
        完整历史修订。
    """
    try:
        revision = await ChapterService.get_revision(chapter_id, version, include_deleted=include_deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter_revision(revision)


@router.post("/scene/{scene_id}", response_model=ChapterReadV2)
async def create_chapter(scene_id: ObjectIdString, req: ChapterCreateV2, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """在场景末尾幂等创建章节。

    Args:
        scene_id: 父场景 ID。
        req: 章节标题和规划。
        idempotency_key: 稳定创建键。
    Returns:
        完整章节。
    """
    try:
        chapter = await ChapterService.create_chapter(scene_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter(chapter)


@router.get("/scene/{scene_id}", response_model=ChapterListV2)
async def list_chapters(scene_id: ObjectIdString, deleted: bool = False) -> dict:
    """读取章节目录或回收站。

    Args:
        scene_id: 父场景 ID。
        deleted: 是否查看回收站。
    Returns:
        章节目录。
    """
    try:
        novel, _, _, _ = await load_chapter_parent_chain(scene_id)
        rows = await ChapterService.list_chapters(str(novel["_id"]), scene_id=scene_id, deleted=deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return {"data": [serialize_chapter(row, include_content=False) for row in rows]}


@router.patch("/scene/{scene_id}/reorder", response_model=ChapterListV2)
async def reorder_chapters(scene_id: ObjectIdString, req: ChapterReorderV2) -> dict:
    """提交全部活动章节的版本和新顺序。

    Args:
        scene_id: 父场景 ID。
        req: 完整章节排序。
    Returns:
        新顺序目录。
    """
    try:
        rows = await ChapterService.reorder_chapters(scene_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return {"data": [serialize_chapter(row, include_content=False) for row in rows]}


@router.get("/{chapter_id}", response_model=ChapterReadV2)
async def get_chapter(chapter_id: ObjectIdString, include_deleted: bool = False) -> dict:
    """读取活动父链下的章节详情。

    Args:
        chapter_id: 章节 ID。
        include_deleted: 是否允许回收站详情。
    Returns:
        完整章节。
    """
    try:
        chapter = await ChapterService.get_chapter(chapter_id, include_deleted=include_deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter(chapter)


@router.put("/{chapter_id}", response_model=ChapterReadV2)
async def update_chapter(chapter_id: ObjectIdString, req: ChapterUpdateV2) -> dict:
    """按版本局部保存章节。

    Args:
        chapter_id: 章节 ID。
        req: 版本及修改字段。
    Returns:
        保存后的章节。
    """
    try:
        chapter = await ChapterService.update_chapter(chapter_id, req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter(chapter)


@router.delete("/{chapter_id}", response_model=ChapterReadV2)
async def delete_chapter(chapter_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)]) -> dict:
    """将章节移入回收站。

    Args:
        chapter_id: 章节 ID。
        expected_version: 已读版本。
    Returns:
        回收站章节。
    """
    try:
        chapter = await ChapterService.set_deleted(chapter_id, expected_version=expected_version, deleted=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter(chapter)


@router.post("/{chapter_id}/restore", response_model=ChapterReadV2)
async def restore_chapter(chapter_id: ObjectIdString, req: ChapterVersionV2) -> dict:
    """恢复章节到当前场景末尾。

    Args:
        chapter_id: 章节 ID。
        req: 已读版本。
    Returns:
        恢复后的章节。
    """
    try:
        chapter = await ChapterService.set_deleted(chapter_id, expected_version=req.expected_version, deleted=False)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return serialize_chapter(chapter)


@router.delete("/{chapter_id}/hard", response_model=ChapterHardDeleteV2)
async def hard_delete_chapter(chapter_id: ObjectIdString, expected_version: Annotated[int, Query(ge=1)], expected_revision_count: Annotated[int | None, Query(ge=0)] = None) -> dict:
    """永久删除回收站章节。

    Args:
        chapter_id: 章节 ID。
        expected_version: 已读版本。
        expected_revision_count: 明确确认删除的历史数量。
    Returns:
        删除结果。
    """
    try:
        await ChapterService.hard_delete_chapter(chapter_id, expected_version=expected_version, **({"expected_revision_count": expected_revision_count} if expected_revision_count is not None else {}))
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return {"chapter_id": chapter_id.lower(), "deleted": True}


@router.get("/{chapter_id}/delete-impact", response_model=ChapterHistoryDeleteImpactV1)
async def chapter_history_delete_impact(chapter_id: ObjectIdString) -> dict:
    """读取章节及一并永久丢失的历史数量。

    Args:
        chapter_id: 回收站章节 ID。
    Returns:
        章节版本和历史数量，删除时必须重新核对。
    """
    try:
        chapter = await ChapterService.get_chapter(chapter_id, include_deleted=True)
        count = await BaseRepository("chapter_revisions").collection.count_documents({"chapter_id": chapter["_id"]})
        from backend.services.novel.foreshadowing_service import count_foreshadowing_references
        references = await count_foreshadowing_references(chapter["novel_id"], "chapter", chapter["_id"])
        from backend.services.novel.chapter_record_source import count_chapter_record_references
        records = await count_chapter_record_references(chapter["novel_id"], "chapter", chapter["_id"])
        return {"chapter_id": chapter_id, "version": chapter["version"], "revision_count": count, "foreshadowings": references, "chapter_records": records}
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")


@router.get("/novel/{novel_id}", response_model=ChapterListV2)
async def list_novel_chapters(novel_id: ObjectIdString, volume_id: ObjectIdString | None = None, deleted: bool = False) -> dict:
    """读取全书或卷内的章节目录，章号遵循全书阅读顺序。

    Args:
        novel_id: 小说 ID。
        volume_id: 可选卷筛选。
        deleted: 是否查看章节回收站。
    Returns:
        无正文的章节目录。
    """
    try:
        rows = await ChapterService.list_chapters(novel_id, volume_id=volume_id, deleted=deleted)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER", label="章节")
    return {"data": [serialize_chapter(row, include_content=False) for row in rows]}
