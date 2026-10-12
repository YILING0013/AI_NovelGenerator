"""卷的创建、编辑、重排与回收站 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import ConfigDict, Field, model_validator
from pymongo.errors import PyMongoError

from backend.api.contracts import (
    LocalCandidateRef,
    ObjectIdString,
    StrictRequestModel,
    StrictResponseModel,
)
from backend.api.error_protocol import (
    DomainApiError,
    api_http_exception,
    exception_to_error,
)
from backend.db.errors import (
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
)
from backend.llm.schemas.volume_planning_pydantic import (
    VolumeBulkPlanRequestV1,
    VolumeLaunchBasisV1,
    VolumeLaunchConfirmV1,
    VolumePlanningV1,
    VolumeSkeletonBasisV1,
    VolumeSkeletonCandidateV1,
    VolumeSkeletonGenerationInputV1,
)
from backend.services.novel.volume_service import VolumeService


router = APIRouter(prefix="/api/volumes", tags=["volumes"])

VolumeStatus = Literal["draft", "planned", "active", "completed", "archived"]


class VolumeCreateRequestV2(StrictRequestModel):
    """人工创建一卷的严格请求。"""

    novel_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=120)
    summary: str = Field(default="", max_length=2000)
    goal: str = Field(default="", max_length=1000)
    theme: str = Field(default="", max_length=500)
    order_index: int | None = Field(default=None, ge=1)
    status: VolumeStatus = "draft"
    planning: VolumePlanningV1 | None = None
    plot: str = Field(default="", max_length=40000)


class VolumeUpdateRequestV2(StrictRequestModel):
    """按预期版本更新卷。"""

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    subtitle: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    goal: str | None = Field(default=None, max_length=1000)
    theme: str | None = Field(default=None, max_length=500)
    status: VolumeStatus | None = None
    planning: VolumePlanningV1 | None = None
    plot: str | None = Field(default=None, max_length=40000)
    basis: VolumeLaunchBasisV1 | None = None

    @model_validator(mode="after")
    def validate_explicit_fields(self) -> "VolumeUpdateRequestV2":
        """拒绝显式 null 文本/状态，允许 planning=null 表示清空启动包。

        Args:
            self: 当前已解析的卷更新请求。

        Returns:
            通过显式字段校验的当前请求。
        """
        for field in self.model_fields_set - {"expected_version", "planning", "basis"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能显式设为 null")
        if "basis" in self.model_fields_set and self.basis is None:
            raise ValueError("basis 不能显式设为 null")
        if self.basis is not None:
            required = {
                "expected_version",
                "title",
                "subtitle",
                "summary",
                "goal",
                "theme",
                "planning",
                "basis",
            }
            if self.model_fields_set != required or self.planning is None:
                raise ValueError("启动包确认必须完整提交业务字段、basis 和 expected_version")
            VolumeLaunchConfirmV1.model_validate(
                self.model_dump(mode="json", exclude_unset=True)
            )
        return self


class VolumeVersionRequestV2(StrictRequestModel):
    """卷恢复等生命周期命令的公开版本。"""

    expected_version: int = Field(ge=1)


class VolumeReorderItemV2(StrictRequestModel):
    """完整活动卷重排中的一条 CAS 项。"""

    volume_id: ObjectIdString
    order_index: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class VolumeReorderRequestV2(StrictRequestModel):
    """必须提交全部活动兄弟的重排命令。"""

    items: list[VolumeReorderItemV2] = Field(min_length=1)


class VolumeReadV3(StrictResponseModel):
    """包含数据库 ID 和公开卷 ID 的完整响应。"""

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    mongo_id: ObjectIdString = Field(alias="_id", serialization_alias="_id")
    volume_id: ObjectIdString
    novel_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(max_length=120)
    summary: str = Field(max_length=2000)
    goal: str = Field(max_length=1000)
    theme: str = Field(max_length=500)
    order_index: int = Field(ge=1)
    status: VolumeStatus
    planning: VolumePlanningV1 | None
    plot: str = Field(default="", max_length=40000)
    plot_source_fingerprint: str | None = None
    location_ids: list[str] = Field(default_factory=list)
    preparation: dict[str, str] = Field(default_factory=dict)
    arcs_count: int = Field(ge=0)
    chapter_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VolumeListResponseV2(StrictResponseModel):
    """现有列表 envelope 中的完整卷数据。"""

    data: list[VolumeReadV3]


class VolumeCreateResponseV2(StrictResponseModel):
    """卷创建结果及完整卷。"""

    id: ObjectIdString
    message: Literal["Volume created"]
    data: VolumeReadV3


class VolumeMutationResponseV2(StrictResponseModel):
    """卷操作结果及写入后内容。"""

    success: bool
    data: VolumeReadV3


class VolumeDeleteImpactV2(StrictResponseModel):
    """卷删除前当前及阶段 2 正式消费者的分字段影响。"""

    volume_id: ObjectIdString
    foreshadowings: int = Field(default=0, ge=0)
    chapter_records: int = Field(default=0, ge=0)
    arcs: int = Field(ge=0)
    scenes: int = Field(ge=0)
    chapters: int = Field(ge=0)
    factions: int = Field(ge=0)
    character_volume_states: int = Field(ge=0)
    faction_volume_states: int = Field(ge=0)
    character_first_appearances: int = Field(ge=0)
    faction_first_appearances: int = Field(ge=0)
    character_faction_binding_boundaries: int = Field(ge=0)
    total: int = Field(ge=0)
    has_blockers: bool


class VolumeHardDeleteStatsV2(StrictResponseModel):
    """卷永久删除精确计数。"""

    arcs_deleted: Literal[0]
    volume_deleted: Literal[1]


class VolumeHardDeleteResponseV2(StrictResponseModel):
    """卷永久删除结果和引用检查。"""

    message: Literal["Hard deleted successfully"]
    stats: VolumeHardDeleteStatsV2
    impact: VolumeDeleteImpactV2


class VolumeBulkPlanResponseV1(StrictResponseModel):
    """卷骨架候选到正式 ObjectId 的映射和完整卷。"""

    candidate_ref_map: dict[LocalCandidateRef, ObjectIdString]
    volumes: list[VolumeReadV3] = Field(min_length=1, max_length=30)


def serialize_volume(document: dict[str, Any]) -> VolumeReadV3:
    """过滤卷 BSON 与幂等内部字段并生成严格公开响应。

    Args:
        document: Repository、Service 或不可变收据返回的卷文档。

    Returns:
        同时含 ``_id`` 和 ``volume_id`` 的 VolumeReadV3。
    """
    object_id = str(document.get("_id") or document.get("volume_id"))
    return VolumeReadV3.model_validate(
        {
            "_id": object_id,
            "volume_id": object_id,
            "novel_id": str(document["novel_id"]),
            "title": document["title"],
            "subtitle": document["subtitle"],
            "summary": document["summary"],
            "goal": document["goal"],
            "theme": document["theme"],
            "order_index": int(document["order_index"]),
            "status": document["status"],
            "planning": document["planning"],
            "plot": document.get("plot", ""),
            "plot_source_fingerprint": document.get("plot_source_fingerprint"),
            "location_ids": document.get("location_ids", []),
            "preparation": document.get("preparation", {}),
            "arcs_count": int(document["arcs_count"]),
            "chapter_count": int(document.get("chapter_count", 0)),
            "word_count": int(document["word_count"]),
            "version": int(document["version"]),
            "is_deleted": bool(document["is_deleted"]),
            "deleted_at": document["deleted_at"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
        }
    )


def _volume_http_exception(exc: Exception) -> HTTPException:
    """把卷领域预期异常转换为公共 HTTP 错误协议。

    Args:
        exc: Service、Repository 或 MongoDB 抛出的可预期异常。

    Returns:
        含稳定错误码和状态码的 HTTPException。
    """
    if isinstance(exc, (PyMongoError, TransactionNotSupportedError)):
        return api_http_exception(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="数据库暂时不可用，请稍后重试",
        )
    status, code, message, field_errors, details = exception_to_error(exc)
    return api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    )


_EXPECTED_VOLUME_ERRORS = (
    DomainApiError,
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TypeError,
    ValueError,
    PyMongoError,
    TransactionNotSupportedError,
)


@router.post("/create", response_model=VolumeCreateResponseV2)
async def create_volume(
    req: VolumeCreateRequestV2,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> VolumeCreateResponseV2:
    """使用请求幂等键创建一卷。

    Args:
        req: 人工创建卷的严格字段。
        idempotency_key: 客户端提交的创建幂等键。

    Returns:
        含卷 ID 和完整内容的创建响应。
    """
    try:
        volume = await VolumeService.create_volume(
            # 省略的 order_index 代表自动追加，不能把 Pydantic 默认的 null 传成显式序号。
            req.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
        )
        public = serialize_volume(volume)
        return VolumeCreateResponseV2(
            id=public.volume_id,
            message="Volume created",
            data=public,
        )
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.get("/novel/{novel_id}/trash", response_model=VolumeListResponseV2)
async def get_deleted_volumes(novel_id: ObjectIdString) -> VolumeListResponseV2:
    """读取小说卷回收站。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        按删除时间稳定排列的回收站卷列表。
    """
    try:
        volumes = await VolumeService.get_volumes_by_novel(novel_id, deleted=True)
        return VolumeListResponseV2(data=[serialize_volume(item) for item in volumes])
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.patch("/novel/{novel_id}/reorder", response_model=VolumeListResponseV2)
async def reorder_volumes(
    novel_id: ObjectIdString,
    req: VolumeReorderRequestV2,
) -> VolumeListResponseV2:
    """提交完整活动卷集合并执行 1-based CAS 重排。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 全部活动卷的目标序号与预期版本。

    Returns:
        按新顺序排列的完整卷列表。
    """
    try:
        volumes = await VolumeService.reorder_volumes(
            novel_id,
            [item.model_dump(mode="json") for item in req.items],
        )
        return VolumeListResponseV2(data=[serialize_volume(item) for item in volumes])
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.post("/novel/{novel_id}/bulk-plan", response_model=VolumeBulkPlanResponseV1)
async def bulk_plan_volumes(
    novel_id: ObjectIdString,
    req: VolumeBulkPlanRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> VolumeBulkPlanResponseV1:
    """复验 basis 并幂等确认一批编辑后卷骨架候选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 编辑后候选、不透明 basis 和正式版本集。
        idempotency_key: 批量确认必填幂等键。

    Returns:
        候选局部引用到正式 ObjectId 的映射和卷快照。
    """
    try:
        result = await VolumeService.bulk_plan_volumes(
            novel_id,
            req,
            idempotency_key=idempotency_key,
        )
        return VolumeBulkPlanResponseV1(
            candidate_ref_map=result["candidate_ref_map"],
            volumes=[serialize_volume(item) for item in result["volumes"]],
        )
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.get("/novel/{novel_id}", response_model=VolumeListResponseV2)
async def get_volumes_by_novel(novel_id: ObjectIdString) -> VolumeListResponseV2:
    """读取小说全部活动卷。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        按 1-based 序号排列的活动卷列表。
    """
    try:
        volumes = await VolumeService.get_volumes_by_novel(novel_id)
        return VolumeListResponseV2(data=[serialize_volume(item) for item in volumes])
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.get("/{volume_id}/delete-impact", response_model=VolumeDeleteImpactV2)
async def get_volume_delete_impact(volume_id: ObjectIdString) -> VolumeDeleteImpactV2:
    """读取卷软删或硬删前的真实消费者影响。

    Args:
        volume_id: 活动或回收站卷 ObjectId 字符串。

    Returns:
        七类消费者计数、总数和阻断标记。
    """
    try:
        return VolumeDeleteImpactV2.model_validate(
            await VolumeService.get_delete_impact(volume_id)
        )
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.get("/{volume_id}", response_model=VolumeReadV3)
async def get_volume(volume_id: ObjectIdString) -> VolumeReadV3:
    """读取一个活动卷详情。

    Args:
        volume_id: 卷 ObjectId 字符串。

    Returns:
        完整 VolumeReadV3 公开投影。
    """
    try:
        return serialize_volume(await VolumeService.get_volume_by_id(volume_id))
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.put("/{volume_id}", response_model=VolumeMutationResponseV2)
async def update_volume(
    volume_id: ObjectIdString,
    req: VolumeUpdateRequestV2,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> VolumeMutationResponseV2:
    """按版本更新人工内容或幂等确认启动包。

    Args:
        volume_id: 目标活动卷 ObjectId 字符串。
        req: 人工可编辑字段，或带 basis 的完整启动包确认。
        idempotency_key: AI 启动包确认必填的领域幂等键。

    Returns:
        保留 success 关键并携带写后卷的响应。
    """
    try:
        payload = req.model_dump(mode="json", exclude_unset=True)
        if req.basis is not None:
            if idempotency_key is None:
                raise DomainApiError(
                    "IDEMPOTENCY_KEY_REQUIRED",
                    "启动包确认必须提供 Idempotency-Key",
                    status_code=422,
                    field_errors={"Idempotency-Key": "该请求头为必填项"},
                )
            confirmed = await VolumeService.confirm_launch_package(
                volume_id,
                VolumeLaunchConfirmV1.model_validate(payload),
                idempotency_key=idempotency_key,
            )
            return VolumeMutationResponseV2(
                success=True,
                data=serialize_volume(confirmed),
            )
        if set(payload) == {"expected_version"}:
            current = await VolumeService._get_versioned_volume(
                volume_id, req.expected_version, deleted=False,
            )
            return VolumeMutationResponseV2(success=False, data=serialize_volume(current))
        updated = await VolumeService.update_volume_info(volume_id, payload)
        return VolumeMutationResponseV2(success=True, data=serialize_volume(updated))
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.delete("/{volume_id}", response_model=VolumeMutationResponseV2)
async def soft_delete_volume(
    volume_id: ObjectIdString,
    expected_version: int = Query(..., ge=1),
) -> VolumeMutationResponseV2:
    """按公开版本软删除无下游引用卷。

    Args:
        volume_id: 目标活动卷 ObjectId 字符串。
        expected_version: 请求基于的卷版本。

    Returns:
        携带软删写后镜像的响应。
    """
    try:
        deleted = await VolumeService.soft_delete_volume(volume_id, expected_version)
        return VolumeMutationResponseV2(success=True, data=serialize_volume(deleted))
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.post("/{volume_id}/restore", response_model=VolumeMutationResponseV2)
async def restore_volume(
    volume_id: ObjectIdString,
    req: VolumeVersionRequestV2,
) -> VolumeMutationResponseV2:
    """按公开版本恢复卷。

    Args:
        volume_id: 目标回收站卷 ObjectId 字符串。
        req: 含 expected_version 的恢复命令。

    Returns:
        携带追加到末尾后卷镜像的响应。
    """
    try:
        restored = await VolumeService.restore_volume(volume_id, req.expected_version)
        return VolumeMutationResponseV2(success=True, data=serialize_volume(restored))
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


@router.delete("/{volume_id}/hard", response_model=VolumeHardDeleteResponseV2)
async def hard_delete_volume(
    volume_id: ObjectIdString,
    expected_version: int = Query(..., ge=1),
) -> VolumeHardDeleteResponseV2:
    """按公开版本永久删除无引用回收站卷。

    Args:
        volume_id: 目标回收站卷 ObjectId 字符串。
        expected_version: 请求基于的卷版本。

    Returns:
        含删除计数和引用检查结果的响应。
    """
    try:
        result = await VolumeService.hard_delete_volume(volume_id, expected_version)
        return VolumeHardDeleteResponseV2(
            message="Hard deleted successfully",
            stats=VolumeHardDeleteStatsV2.model_validate(result["stats"]),
            impact=VolumeDeleteImpactV2.model_validate(result["impact"]),
        )
    except _EXPECTED_VOLUME_ERRORS as exc:
        raise _volume_http_exception(exc) from exc


__all__ = [
    "VolumeBulkPlanRequestV1",
    "VolumeBulkPlanResponseV1",
    "VolumeCreateRequestV2",
    "VolumeCreateResponseV2",
    "VolumeDeleteImpactV2",
    "VolumeHardDeleteResponseV2",
    "VolumeListResponseV2",
    "VolumeMutationResponseV2",
    "VolumePlanningV1",
    "VolumeReadV3",
    "VolumeReorderRequestV2",
    "VolumeSkeletonCandidateV1",
    "VolumeSkeletonBasisV1",
    "VolumeSkeletonGenerationInputV1",
    "VolumeUpdateRequestV2",
    "VolumeVersionRequestV2",
    "router",
    "serialize_volume",
]
