"""小说正式领域的严格 HTTP 契约。"""

from __future__ import annotations

from backend.services.task_flows.contracts import GraphRunRequest

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import Field, model_validator
from pymongo.errors import PyMongoError

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.api.error_protocol import (
    DomainApiError,
    api_http_exception,
    exception_to_error,
)
from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError, TransactionNotSupportedError
from backend.db.base import BaseRepository
from backend.db.repositories.novel_repository import novel_repo
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.llm.novel_generation_contract import (
    NovelCreateFieldsV1,
    NovelFieldRewriteCandidateV1,
    NovelFieldRewriteGenerationInputV1,
    NovelTag,
)
from backend.services.novel.cover_asset import read_and_encode_cover
from backend.services.novel.novel_service import NovelService
from backend.services.novel.chapter_record_contract import ChapterRecordDeleteCountsV1
from backend.services.novel.chapter_record_source import count_novel_chapter_records


router = APIRouter(prefix="/api/novels", tags=["novels"])

NovelStatus = Literal["draft", "ongoing", "completed", "archived"]


class NovelManualCreateRequestV1(NovelCreateFieldsV1):
    """人工创建小说命令。"""

    request_type: Literal["manual"] = "manual"


class NovelAIConfirmationRequestV1(StrictRequestModel):
    """浏览器显式确认 AI 新书候选的严格信封。"""

    request_type: Literal["ai_confirmation"]
    candidate: NovelCreateFieldsV1
    basis: CandidateBasisV1
    generation_input: GraphRunRequest
    expected_versions: dict[str, int] = Field(default_factory=dict, max_length=0)


NovelCreateRequestV1 = NovelManualCreateRequestV1 | NovelAIConfirmationRequestV1


class NovelAIFieldConfirmationRequestV1(StrictRequestModel):
    """保存态小说字段候选的显式确认命令。"""

    request_type: Literal["ai_field_confirmation"]
    candidate: NovelFieldRewriteCandidateV1
    basis: CandidateBasisV1
    generation_input: NovelFieldRewriteGenerationInputV1
    expected_versions: dict[str, int] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_expected_versions(self) -> "NovelAIFieldConfirmationRequestV1":
        """要求唯一版本值为排除布尔值的正整数。"""
        if any(
            isinstance(version, bool) or version < 1
            for version in self.expected_versions.values()
        ):
            raise ValueError("expected_versions 必须使用正整数版本")
        return self


class NovelUpdateRequestV1(StrictRequestModel):
    """活动小说资料的人工 CAS 更新命令。"""

    request_type: Literal["manual"] = "manual"
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=500)
    genre: str | None = Field(default=None, min_length=1, max_length=100)
    tags: list[NovelTag] | None = Field(default=None, max_length=30)
    introduction: str | None = Field(default=None, max_length=20_000)
    summary: str | None = Field(default=None, max_length=20_000)
    core_seed: str | None = Field(default=None, max_length=20_000)
    worldview: str | None = Field(default=None, max_length=20_000)
    writing_style: str | None = Field(default=None, max_length=10_000)
    narrative_pov: str | None = Field(default=None, max_length=200)
    era_background: str | None = Field(default=None, max_length=10_000)
    plot: str | None = Field(default=None, max_length=40_000)
    tone: str | None = Field(default=None, max_length=500)
    target_audience: str | None = Field(default=None, max_length=1000)
    core_idea: str | None = Field(default=None, max_length=20_000)
    number_of_chapters: int | None = Field(default=None, ge=1, le=10_000)
    words_per_chapter: int | None = Field(default=None, ge=1, le=100_000)

    @model_validator(mode="after")
    def validate_has_update(self) -> "NovelUpdateRequestV1":
        """要求每个 CAS 命令至少包含一个显式业务字段。"""
        fields = self.model_fields_set - {"request_type", "expected_version"}
        if not fields:
            raise ValueError("小说更新至少需要一个业务字段")
        for required_field in ("title", "genre", "tags"):
            if required_field in fields and getattr(self, required_field) is None:
                raise ValueError(f"{required_field} 不能为 null")
        if self.tags is not None and len(self.tags) != len(set(self.tags)):
            raise ValueError("tags 不能包含重复项")
        return self


NovelUpdateCommandV1 = NovelUpdateRequestV1 | NovelAIFieldConfirmationRequestV1


class NovelStatusUpdateRequestV1(StrictRequestModel):
    """小说状态 CAS 更新命令。"""

    status: NovelStatus
    expected_version: int = Field(ge=1)


class NovelVersionRequestV1(StrictRequestModel):
    """只需乐观锁版本的小说生命周期命令。"""

    expected_version: int = Field(ge=1)


class NovelStatsV1(StrictResponseModel):
    """书架显示的章节数和总字数。"""

    chapter_count: int = Field(ge=0)
    total_word_count: int = Field(ge=0)


class NovelResponseV1(StrictResponseModel):
    """不泄露 Mongo _id 和内部幂等字段的小说公开响应。"""

    id: ObjectIdString
    version: int = Field(ge=1)
    title: str
    subtitle: str | None = None
    genre: str
    tags: list[str]
    introduction: str | None = None
    summary: str | None = None
    core_seed: str | None = None
    worldview: str | None = None
    writing_style: str | None = None
    narrative_pov: str | None = None
    era_background: str | None = None
    cover_image: str | None = None
    plot: str | None = None
    tone: str | None = None
    target_audience: str | None = None
    core_idea: str | None = None
    number_of_chapters: int | None = Field(default=None, ge=1)
    words_per_chapter: int | None = Field(default=None, ge=1)
    status: NovelStatus
    current_volume_count: int = Field(ge=0)
    current_chapter_count: int = Field(ge=0)
    current_word_count: int = Field(ge=0)
    stats: NovelStatsV1
    is_deleted: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class NovelCreateResponseV1(StrictResponseModel):
    """小说创建及幂等回放的最小响应。"""

    id: ObjectIdString
    version: int = Field(ge=1)


class NovelListResponseV1(StrictResponseModel):
    """小说书架或回收站列表响应。"""

    data: list[NovelResponseV1]


class NovelHardDeleteStatsV1(StrictResponseModel):
    """小说物理删除当前真实消费者的精确计数。"""

    volumes_deleted: int = Field(ge=0)
    arcs_deleted: int = Field(ge=0)
    scenes_deleted: int = Field(ge=0)
    chapters_deleted: int = Field(ge=0)
    chapter_revisions_deleted: int = Field(default=0, ge=0)
    foreshadowing_creation_receipts_deleted: int = Field(default=0, ge=0)
    events_deleted: int = Field(default=0, ge=0)
    chapter_reports_deleted: int = Field(default=0, ge=0)
    entity_state_history_deleted: int = Field(default=0, ge=0)
    chapter_record_confirmation_receipts_deleted: int = Field(default=0, ge=0)
    writing_confirmation_receipts_deleted: int = Field(ge=0)
    factions_deleted: int = Field(ge=0)
    faction_relations_deleted: int = Field(ge=0)
    characters_deleted: int = Field(ge=0)
    character_relations_deleted: int = Field(ge=0)
    character_faction_bindings_deleted: int = Field(ge=0)
    character_volume_states_deleted: int = Field(ge=0)
    character_volume_state_initialization_receipts_deleted: int = Field(
        ge=0,
    )
    faction_volume_states_deleted: int = Field(ge=0)
    faction_volume_state_initialization_receipts_deleted: int = Field(ge=0)
    world_rules_deleted: int = Field(ge=0)
    world_rule_core_confirmation_receipts_deleted: int = Field(ge=0)
    locations_deleted: int = Field(ge=0)
    items_deleted: int = Field(ge=0)
    item_generation_confirmation_receipts_deleted: int = Field(ge=0)
    location_generation_confirmation_receipts_deleted: int = Field(ge=0)
    volume_command_receipts_deleted: int = Field(ge=0)
    character_creation_batch_receipts_deleted: int = Field(default=0, ge=0)
    id_sequences_deleted: int = Field(ge=0)
    novel_deleted: Literal[1]
    cover_asset_deleted: Literal[0, 1]


class NovelHardDeleteResponseV1(StrictResponseModel):
    """不可恢复的小说物理删除响应。"""

    stats: NovelHardDeleteStatsV1


def serialize_novel(document: dict[str, Any]) -> NovelResponseV1:
    """把小说 BSON 文档过滤为唯一公开响应。

    Args:
        document: NovelRepository 返回的小说 BSON 文档。

    Returns:
        使用 id、version 且不含任何内部字段的严格 DTO。
    """
    chapter_count = int(document.get("current_chapter_count") or 0)
    word_count = int(document.get("current_word_count") or 0)
    return NovelResponseV1.model_validate(
        {
            "id": str(document["_id"]),
            "version": int(document["version"]),
            "title": str(document.get("title") or ""),
            "subtitle": document.get("subtitle"),
            "genre": str(document.get("genre") or "unclassified"),
            "tags": list(document.get("tags") or []),
            "introduction": document.get("introduction"),
            "summary": document.get("summary"),
            "core_seed": document.get("core_seed"),
            "worldview": document.get("worldview"),
            "writing_style": document.get("writing_style"),
            "narrative_pov": document.get("narrative_pov"),
            "era_background": document.get("era_background"),
            "cover_image": document.get("cover_image"),
            "plot": document.get("plot"),
            "tone": document.get("tone"),
            "target_audience": document.get("target_audience"),
            "core_idea": document.get("core_idea"),
            "number_of_chapters": document.get("number_of_chapters"),
            "words_per_chapter": document.get("words_per_chapter"),
            "status": document.get("status", "draft"),
            "current_volume_count": int(document.get("current_volume_count") or 0),
            "current_chapter_count": chapter_count,
            "current_word_count": word_count,
            "stats": {
                "chapter_count": chapter_count,
                "total_word_count": word_count,
            },
            "is_deleted": bool(document.get("is_deleted", False)),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
            "deleted_at": document.get("deleted_at"),
        }
    )


def _novel_http_exception(exc: Exception) -> HTTPException:
    """把小说领域预期异常转换为公共 HTTP 错误协议。"""
    if isinstance(exc, TransactionNotSupportedError):
        return api_http_exception(status_code=503, code="NOVEL_TRANSACTION_REQUIRED", message="永久删除章后记录需要启用 MongoDB 事务并连接副本集")
    status, code, message, field_errors, details = exception_to_error(exc)
    return api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    )


_EXPECTED_NOVEL_ERRORS = (
    DomainApiError,
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
    TypeError,
    ValueError,
)


@router.post("/create", response_model=NovelCreateResponseV1)
async def create_novel(
    req: NovelCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> NovelCreateResponseV1:
    """人工创建或显式确认 AI 新书候选。

    Args:
        req: 可判别的人工创建或 AI 确认命令。
        idempotency_key: 必填的创建幂等键。

    Returns:
        新小说或幂等回放结果的公开 ID 与版本。
    """
    try:
        if isinstance(req, NovelAIConfirmationRequestV1):
            novel = await NovelService.create_ai_novel(
                req,
                idempotency_key=idempotency_key,
            )
        else:
            novel = await NovelService.create_manual_novel(
                req,
                idempotency_key=idempotency_key,
            )
        return NovelCreateResponseV1(
            id=str(novel["_id"]),
            version=int(novel["version"]),
        )
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.get("/list", response_model=NovelListResponseV1)
async def get_all_novels() -> NovelListResponseV1:
    """读取活动书架列表。

    Returns:
        不含内部字段的活动小说列表。
    """
    novels = await NovelService.list_novels()
    return NovelListResponseV1(data=[serialize_novel(item) for item in novels])


@router.get("/deleted/list", response_model=NovelListResponseV1)
async def get_deleted_novels() -> NovelListResponseV1:
    """读取小说回收站列表。

    Returns:
        不含内部字段的回收站小说列表。
    """
    novels = await NovelService.list_novels(deleted=True)
    return NovelListResponseV1(data=[serialize_novel(item) for item in novels])


@router.get("/{novel_id}", response_model=NovelResponseV1)
async def get_novel(novel_id: ObjectIdString) -> NovelResponseV1:
    """读取一个活动小说的完整公开资料。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        严格小说公开响应。
    """
    try:
        return serialize_novel(await NovelService.get_novel(novel_id))
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.put("/{novel_id}", response_model=NovelResponseV1)
async def update_novel(
    novel_id: ObjectIdString,
    req: NovelUpdateCommandV1,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> NovelResponseV1:
    """人工 CAS 更新或显式确认一个 AI 字段候选。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        req: 可判别的人工 CAS 或 AI 字段确认命令。
        idempotency_key: AI 字段确认必填的幂等键；人工更新忽略。

    Returns:
        版本递增一次的写后小说。
    """
    try:
        if isinstance(req, NovelAIFieldConfirmationRequestV1):
            if not idempotency_key:
                raise ValueError("AI 字段确认必须携带 Idempotency-Key")
            novel = await NovelService.confirm_ai_field(
                novel_id,
                req,
                idempotency_key=idempotency_key,
            )
        else:
            novel = await NovelService.update_novel(novel_id, req)
        return serialize_novel(novel)
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.patch("/{novel_id}/status", response_model=NovelResponseV1)
async def update_status(
    novel_id: ObjectIdString,
    req: NovelStatusUpdateRequestV1,
) -> NovelResponseV1:
    """按 expected_version 更新小说状态。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        req: 目标状态与调用方版本。

    Returns:
        状态更新后的小说。
    """
    try:
        novel = await NovelService.update_status(
            novel_id,
            req.status,
            req.expected_version,
        )
        return serialize_novel(novel)
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.delete("/{novel_id}", response_model=NovelResponseV1)
async def soft_delete(
    novel_id: ObjectIdString,
    expected_version: int = Query(..., ge=1),
) -> NovelResponseV1:
    """按 query 中的 expected_version 将小说移入回收站。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        expected_version: 调用方基于的小说版本。

    Returns:
        已进入回收站的小说。
    """
    try:
        return serialize_novel(
            await NovelService.soft_delete_novel(novel_id, expected_version)
        )
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.post("/{novel_id}/restore", response_model=NovelResponseV1)
async def restore_novel(
    novel_id: ObjectIdString,
    req: NovelVersionRequestV1,
) -> NovelResponseV1:
    """按 body 中的 expected_version 恢复回收站小说。

    Args:
        novel_id: 回收站小说 ObjectId 字符串。
        req: 调用方版本命令。

    Returns:
        已恢复为活动状态的小说。
    """
    try:
        return serialize_novel(
            await NovelService.restore_novel(novel_id, req.expected_version)
        )
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.delete("/{novel_id}/hard", response_model=NovelHardDeleteResponseV1)
async def hard_delete(
    novel_id: ObjectIdString,
    expected_version: int = Query(..., ge=1),
    expected_revision_count: int | None = Query(None, ge=0),
    expected_chapter_record_counts: ChapterRecordDeleteCountsV1 | None = Body(None),
) -> NovelHardDeleteResponseV1:
    """按 query 中的 expected_version 物理删除回收站小说。

    Args:
        novel_id: 回收站小说 ObjectId 字符串。
        expected_version: 调用方确认的小说版本。
        expected_revision_count: 明确确认一并删除的历史数量。
        expected_chapter_record_counts: 明确确认一并删除的全部章后记录数量；已导出的备份文件不随之删除。

    Returns:
        当前真实消费者和封面的精确删除统计。
    """
    try:
        stats = await NovelService.hard_delete_novel(
            novel_id, expected_version,
            **({"expected_revision_count": expected_revision_count} if expected_revision_count is not None else {}),
            **({"expected_chapter_record_counts": expected_chapter_record_counts} if expected_chapter_record_counts is not None else {}),
        )
        return NovelHardDeleteResponseV1(
            stats=NovelHardDeleteStatsV1.model_validate(stats)
        )
    except PyMongoError as exc:
        if exc.has_error_label("UnknownTransactionCommitResult"):
            raise api_http_exception(status_code=503, code="NOVEL_DELETE_OUTCOME_UNKNOWN", message="删除结果暂时无法确认，请重新查看作品；作品已不存在也不能证明本次请求成功") from exc
        if exc.has_error_label("TransientTransactionError") or getattr(exc, "code", None) == 112:
            raise api_http_exception(status_code=409, code="NOVEL_WRITE_CONFLICT", message="作品正在被其他操作修改，请重新查看删除影响") from exc
        raise api_http_exception(status_code=503, code="DATABASE_UNAVAILABLE", message="数据库暂时不可用，请保留原删除确认后重试") from exc
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


class NovelHistoryDeleteImpactV1(StrictResponseModel):
    """作品永久删除前的历史数量与已读版本。"""

    novel_id: ObjectIdString
    foreshadowings: int = Field(default=0, ge=0)
    version: int = Field(ge=1)
    revision_count: int = Field(ge=0)
    chapter_records: ChapterRecordDeleteCountsV1


@router.get("/{novel_id}/delete-impact", response_model=NovelHistoryDeleteImpactV1)
async def novel_history_delete_impact(novel_id: ObjectIdString) -> dict:
    """读取永久删除会丢失的章节历史数量。

    Args:
        novel_id: 回收站小说 ID。
    Returns:
        小说版本和历史数量，提交删除时重新核对。
    """
    try:
        novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True)
        count = novel["hard_delete_history_count"] if novel.get("hard_delete_claim") and "hard_delete_history_count" in novel else await BaseRepository("chapter_revisions").collection.count_documents({"novel_id": novel["_id"]})
        references = await BaseRepository("foreshadowings").collection.count_documents({"novel_id": novel["_id"]})
        records = await count_novel_chapter_records(novel["_id"])
        return {"novel_id": novel_id, "version": novel["version"], "revision_count": count, "foreshadowings": references, "chapter_records": records}
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.put("/{novel_id}/cover", response_model=NovelResponseV1)
async def upload_cover(
    novel_id: ObjectIdString,
    file: UploadFile = File(...),
    expected_version: int = Form(..., ge=1),
) -> NovelResponseV1:
    """校验、重编码并以小说 CAS 绑定一张封面。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        file: 待完整解码的上传文件。
        expected_version: multipart 中的调用方版本。

    Returns:
        封面更新后的小说。
    """
    try:
        asset = await read_and_encode_cover(file)
        return serialize_novel(
            await NovelService.set_cover(novel_id, expected_version, asset)
        )
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


@router.delete("/{novel_id}/cover", response_model=NovelResponseV1)
async def delete_cover(
    novel_id: ObjectIdString,
    req: NovelVersionRequestV1,
) -> NovelResponseV1:
    """按 expected_version 解除小说封面并清理无引用安全文件。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        req: 调用方版本命令。

    Returns:
        封面字段已清空的小说。
    """
    try:
        return serialize_novel(
            await NovelService.clear_cover(novel_id, req.expected_version)
        )
    except _EXPECTED_NOVEL_ERRORS as exc:
        raise _novel_http_exception(exc) from exc


__all__ = [
    "NovelAIConfirmationRequestV1",
    "NovelAIFieldConfirmationRequestV1",
    "NovelCreateFieldsV1",
    "NovelCreateRequestV1",
    "NovelCreateResponseV1",
    "NovelHardDeleteResponseV1",
    "NovelListResponseV1",
    "NovelManualCreateRequestV1",
    "NovelResponseV1",
    "NovelStatusUpdateRequestV1",
    "NovelUpdateRequestV1",
    "NovelUpdateCommandV1",
    "NovelVersionRequestV1",
    "router",
    "serialize_novel",
]
