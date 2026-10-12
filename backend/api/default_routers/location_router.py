"""全书级正式地点 HTTP Router。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Header, Path, Query
from pymongo.errors import PyMongoError

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
from backend.llm.schemas.location_pydantic import (
    FACTION_ID_PATTERN,
    LOCATION_ID_PATTERN,
    LocationBulkGeneratedRequestV1,
    LocationBulkGeneratedResponseV1,
    LocationCreateV1,
    LocationDeleteImpactV1,
    LocationHardDeleteResponseV1,
    LocationReadV1,
    LocationReorderRequestV1,
    LocationUpdateV1,
    LocationVersionRequestV1,
)
from backend.services.novel.location_service import LocationService


router = APIRouter(prefix="/api/locations", tags=["locations"])

NovelIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
LocationIdPath = Annotated[str, Path(pattern=LOCATION_ID_PATTERN)]
EXPECTED_LOCATION_ERRORS = (
    DomainApiError,
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
    PyMongoError,
    TypeError,
    ValueError,
)


def _serialize_location(location: dict) -> LocationReadV1:
    """过滤地点内部字段并构造严格公开响应。

    Args:
        location: Repository 或 Service 返回的完整 BSON 地点。

    Returns:
        不含 MongoDB ID、规范名、guard 和幂等摘要的公开地点。
    """
    public_fields = set(LocationReadV1.model_fields)
    payload = {
        field: value
        for field, value in location.items()
        if field in public_fields
    }
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])
    return LocationReadV1.model_validate(payload)


def _serialize_locations(locations: list[dict]) -> list[LocationReadV1]:
    """批量构造严格公开地点列表。

    Args:
        locations: Service 返回的完整地点列表。

    Returns:
        与输入顺序一致的公开地点列表。
    """
    return [_serialize_location(location) for location in locations]


def _raise_location_http_error(exc: Exception) -> NoReturn:
    """把地点边界的数据库与领域异常转换为公共 HTTP 错误。

    Args:
        exc: Service 或 MongoDB 抛出的预期异常。

    Returns:
        不返回；始终抛出遵循公共协议的 HTTPException。
    """
    if isinstance(exc, (TransactionNotSupportedError, PyMongoError)):
        raise api_http_exception(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="地点数据库暂时不可用，请稍后重试",
        ) from exc
    status, code, message, field_errors, details = exception_to_error(
        exc,
        fallback_message="地点请求处理失败",
    )
    raise api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    ) from exc


@router.post("/novel/{novel_id}", response_model=LocationReadV1)
async def create_location(
    novel_id: NovelIdPath,
    req: LocationCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> LocationReadV1:
    """幂等创建小说内一个正式地点。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 已通过严格校验的地点内容。
        idempotency_key: 必填人工创建幂等键。

    Returns:
        新建或同键重放的完整公开地点。
    """
    try:
        location = await LocationService.create_location(
            novel_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_location(location)


@router.get("/novel/{novel_id}", response_model=list[LocationReadV1])
async def list_locations(
    novel_id: NovelIdPath,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    location_type: Annotated[
        str | None,
        Query(alias="type", min_length=1, max_length=40),
    ] = None,
    status: Annotated[str | None, Query(pattern=r"^(?:active|inactive)$")] = None,
    parent_id: Annotated[
        str | None,
        Query(pattern=r"^(?:loc_[0-9]{6,})?$"),
    ] = None,
    faction_id: Annotated[str | None, Query(pattern=FACTION_ID_PATTERN)] = None,
) -> list[LocationReadV1]:
    """按内容、类型、状态、父级和势力筛选未删除地点。

    Args:
        novel_id: 小说 ObjectId 字符串。
        q: 可选搜索词。
        location_type: 可选地点类型，对外 Query 键为 type。
        status: 可选 active 或 inactive。
        parent_id: 可选父地点 ID；空字符串表示根级。
        faction_id: 可选关联势力稳定 ID。

    Returns:
        保持领域排序的完整公开地点列表。
    """
    try:
        locations = await LocationService.list_locations(
            novel_id.lower(),
            q=q,
            location_type=location_type,
            status=status,
            parent_location_id=parent_id,
            associated_faction_id=faction_id,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_locations(locations)


@router.get("/novel/{novel_id}/trash", response_model=list[LocationReadV1])
async def list_deleted_locations(
    novel_id: NovelIdPath,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    location_type: Annotated[
        str | None,
        Query(alias="type", min_length=1, max_length=40),
    ] = None,
    status: Annotated[str | None, Query(pattern=r"^(?:active|inactive)$")] = None,
    parent_id: Annotated[
        str | None,
        Query(pattern=r"^(?:loc_[0-9]{6,})?$"),
    ] = None,
    faction_id: Annotated[str | None, Query(pattern=FACTION_ID_PATTERN)] = None,
) -> list[LocationReadV1]:
    """读取地点回收站并应用与活动列表一致的筛选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        q: 可选搜索词。
        location_type: 可选地点类型，对外 Query 键为 type。
        status: 可选地点业务状态。
        parent_id: 可选原父地点 ID；空字符串表示根级。
        faction_id: 可选关联势力稳定 ID。

    Returns:
        按删除时间倒序排列的公开地点列表。
    """
    try:
        locations = await LocationService.list_deleted_locations(
            novel_id.lower(),
            q=q,
            location_type=location_type,
            status=status,
            parent_location_id=parent_id,
            associated_faction_id=faction_id,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_locations(locations)


@router.patch("/novel/{novel_id}/reorder", response_model=list[LocationReadV1])
async def reorder_locations(
    novel_id: NovelIdPath,
    req: LocationReorderRequestV1,
) -> list[LocationReadV1]:
    """以完整同父兄弟集合执行 1-based CAS 重排。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 父级及全部兄弟的顺序和版本。

    Returns:
        按新顺序排列且每条版本递增一次的完整兄弟集合。
    """
    try:
        locations = await LocationService.reorder_locations(
            novel_id.lower(),
            req.parent_location_id,
            [item.model_dump(mode="json") for item in req.items],
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_locations(locations)


@router.post(
    "/novel/{novel_id}/bulk-generated",
    response_model=LocationBulkGeneratedResponseV1,
)
async def bulk_create_generated_locations(
    novel_id: NovelIdPath,
    req: LocationBulkGeneratedRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> LocationBulkGeneratedResponseV1:
    """幂等确认一批按拓扑排序的地点候选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 候选、严格 basis 与精确来源版本。
        idempotency_key: 批量确认必填幂等键。

    Returns:
        candidate_ref 到稳定地点 ID 的映射及完整地点。
    """
    try:
        result = await LocationService.bulk_create_generated_locations(
            novel_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return LocationBulkGeneratedResponseV1(
        candidate_ref_map=result["candidate_ref_map"],
        locations=_serialize_locations(result["locations"]),
    )


@router.get(
    "/novel/{novel_id}/{location_id}/delete-impact",
    response_model=LocationDeleteImpactV1,
)
async def get_location_delete_impact(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
) -> LocationDeleteImpactV1:
    """读取活动或回收站地点的删除影响。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。

    Returns:
        直接子级和活动正式消费者的精确分项影响。
    """
    try:
        impact = await LocationService.get_delete_impact(
            novel_id.lower(),
            location_id,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return LocationDeleteImpactV1.model_validate(impact)


@router.get("/novel/{novel_id}/{location_id}", response_model=LocationReadV1)
async def get_location(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
) -> LocationReadV1:
    """读取小说内一条未删除地点。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。

    Returns:
        匹配的完整公开地点。
    """
    try:
        location = await LocationService.get_location(
            novel_id.lower(),
            location_id,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_location(location)


@router.put("/novel/{novel_id}/{location_id}", response_model=LocationReadV1)
async def update_location(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
    req: LocationUpdateV1,
) -> LocationReadV1:
    """使用 expected_version 更新地点并维护层级顺序。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。
        req: 含 expected_version 的严格局部更新。

    Returns:
        更新并递增版本后的完整公开地点。
    """
    try:
        location = await LocationService.update_location(
            novel_id.lower(),
            location_id,
            req,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_location(location)


@router.delete("/novel/{novel_id}/{location_id}", response_model=LocationReadV1)
async def soft_delete_location(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
    expected_version: int = Query(..., ge=1),
    detach_children: bool = Query(False),
) -> LocationReadV1:
    """软删除地点，并仅在明确确认时断开直接活动子级。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。
        expected_version: 调用方持有的地点版本。
        detach_children: 是否明确把直接子级移动到根级。

    Returns:
        已进入回收站并递增版本的完整公开地点。
    """
    try:
        location = await LocationService.soft_delete_location(
            novel_id.lower(),
            location_id,
            expected_version=expected_version,
            detach_children=detach_children,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_location(location)


@router.post(
    "/novel/{novel_id}/{location_id}/restore",
    response_model=LocationReadV1,
)
async def restore_location(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
    req: LocationVersionRequestV1,
) -> LocationReadV1:
    """恢复回收站地点但不重新挂接曾被断开的子级。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。
        req: 含回收站 expected_version 的恢复请求。

    Returns:
        追加到当前父级末尾的完整公开地点。
    """
    try:
        location = await LocationService.restore_location(
            novel_id.lower(),
            location_id,
            expected_version=req.expected_version,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return _serialize_location(location)


@router.delete(
    "/novel/{novel_id}/{location_id}/hard",
    response_model=LocationHardDeleteResponseV1,
)
async def hard_delete_location(
    novel_id: NovelIdPath,
    location_id: LocationIdPath,
    expected_version: int = Query(..., ge=1),
) -> LocationHardDeleteResponseV1:
    """永久删除没有子级或活动正式消费者的回收站地点。

    Args:
        novel_id: 小说 ObjectId 字符串。
        location_id: 稳定地点 ID。
        expected_version: 调用方持有的回收站地点版本。

    Returns:
        被删除地点 ID 和最终全零影响。
    """
    try:
        result = await LocationService.hard_delete_location(
            novel_id.lower(),
            location_id,
            expected_version=expected_version,
        )
    except EXPECTED_LOCATION_ERRORS as exc:
        _raise_location_http_error(exc)
    return LocationHardDeleteResponseV1(
        message="Hard deleted successfully",
        location_id=result["location_id"],
        impact=LocationDeleteImpactV1.model_validate(result["impact"]),
    )


__all__ = ["router"]
