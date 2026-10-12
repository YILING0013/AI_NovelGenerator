"""全书级正式物品 HTTP Router。"""

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
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.llm.schemas.item_pydantic import (
    CHARACTER_ID_PATTERN,
    ITEM_ID_PATTERN,
    LOCATION_ID_PATTERN,
    ItemBulkGeneratedRequestV1,
    ItemBulkGeneratedResponseV1,
    ItemCreateV1,
    ItemDeleteImpactV1,
    ItemHardDeleteResponseV1,
    ItemLifecycleStatus,
    ItemReadV1,
    ItemReorderRequestV1,
    ItemUpdateV1,
    ItemVersionRequestV1,
)
from backend.services.novel.item_service import ItemService


router = APIRouter(prefix="/api/items", tags=["items"])

NovelIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
ItemIdPath = Annotated[str, Path(pattern=ITEM_ID_PATTERN)]
EXPECTED_ITEM_ERRORS = (
    DomainApiError,
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
    PyMongoError,
    TypeError,
    ValueError,
)


def _serialize_item(item: dict) -> ItemReadV1:
    """过滤物品内部字段并构造严格公开响应。

    Args:
        item: Repository 或 Service 返回的完整 BSON 物品。

    Returns:
        不含 MongoDB ID、规范名、guard、幂等摘要与内部标记的公开物品。
    """
    public_fields = set(ItemReadV1.model_fields)
    payload = {field: value for field, value in item.items() if field in public_fields}
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])
    return ItemReadV1.model_validate(payload)


def _serialize_items(items: list[dict]) -> list[ItemReadV1]:
    """批量构造与领域顺序一致的严格公开物品列表。"""
    return [_serialize_item(item) for item in items]


def _raise_item_http_error(exc: Exception) -> NoReturn:
    """把物品边界的数据库与领域异常转换为公共 HTTP 错误。"""
    if isinstance(exc, (TransactionNotSupportedError, PyMongoError)):
        raise api_http_exception(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="物品数据库暂时不可用，请稍后重试",
        ) from exc
    status, code, message, field_errors, details = exception_to_error(
        exc,
        fallback_message="物品请求处理失败",
    )
    raise api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    ) from exc


@router.post("/novel/{novel_id}", response_model=ItemReadV1)
async def create_item(
    novel_id: NovelIdPath,
    req: ItemCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> ItemReadV1:
    """幂等创建小说内一个正式物品。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        req: 已通过严格校验的物品创建请求。
        idempotency_key: 调用方提供的创建幂等键。

    Returns:
        新建或同键同载荷重放的完整公开物品。
    """
    try:
        item = await ItemService.create_item(
            novel_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.get("/novel/{novel_id}", response_model=list[ItemReadV1])
async def list_items(
    novel_id: NovelIdPath,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    item_type: Annotated[
        str | None,
        Query(alias="type", min_length=1, max_length=40),
    ] = None,
    lifecycle_status: Annotated[
        ItemLifecycleStatus | None,
        Query(alias="status"),
    ] = None,
    owner_character_id: Annotated[
        str | None,
        Query(alias="owner", pattern=CHARACTER_ID_PATTERN),
    ] = None,
    controlling_faction_id: Annotated[
        str | None,
        Query(alias="faction", pattern=FACTION_BUSINESS_ID_PATTERN),
    ] = None,
    current_location_id: Annotated[
        str | None,
        Query(alias="location", pattern=LOCATION_ID_PATTERN),
    ] = None,
) -> list[ItemReadV1]:
    """按内容、类型、状态和三个当前引用筛选活动物品。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        q: 可选内容搜索词。
        item_type: 可选物品类型筛选值。
        lifecycle_status: 可选生命周期状态筛选值。
        owner_character_id: 可选当前持有角色 ID。
        controlling_faction_id: 可选当前控制势力 ID。
        current_location_id: 可选当前地点 ID。

    Returns:
        符合筛选条件且按正式顺序排列的活动物品。
    """
    try:
        items = await ItemService.list_items(
            novel_id.lower(),
            q=q,
            item_type=item_type,
            lifecycle_status=lifecycle_status,
            owner_character_id=owner_character_id,
            controlling_faction_id=controlling_faction_id,
            current_location_id=current_location_id,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_items(items)


@router.get("/novel/{novel_id}/trash", response_model=list[ItemReadV1])
async def list_deleted_items(
    novel_id: NovelIdPath,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    item_type: Annotated[
        str | None,
        Query(alias="type", min_length=1, max_length=40),
    ] = None,
    lifecycle_status: Annotated[
        ItemLifecycleStatus | None,
        Query(alias="status"),
    ] = None,
    owner_character_id: Annotated[
        str | None,
        Query(alias="owner", pattern=CHARACTER_ID_PATTERN),
    ] = None,
    controlling_faction_id: Annotated[
        str | None,
        Query(alias="faction", pattern=FACTION_BUSINESS_ID_PATTERN),
    ] = None,
    current_location_id: Annotated[
        str | None,
        Query(alias="location", pattern=LOCATION_ID_PATTERN),
    ] = None,
) -> list[ItemReadV1]:
    """读取物品回收站并应用与活动列表一致的筛选。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        q: 可选内容搜索词。
        item_type: 可选物品类型筛选值。
        lifecycle_status: 可选生命周期状态筛选值。
        owner_character_id: 可选删除前持有角色 ID。
        controlling_faction_id: 可选删除前控制势力 ID。
        current_location_id: 可选删除前所在地点 ID。

    Returns:
        符合筛选条件的回收站物品。
    """
    try:
        items = await ItemService.list_deleted_items(
            novel_id.lower(),
            q=q,
            item_type=item_type,
            lifecycle_status=lifecycle_status,
            owner_character_id=owner_character_id,
            controlling_faction_id=controlling_faction_id,
            current_location_id=current_location_id,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_items(items)


@router.patch("/novel/{novel_id}/reorder", response_model=list[ItemReadV1])
async def reorder_items(
    novel_id: NovelIdPath,
    req: ItemReorderRequestV1,
) -> list[ItemReadV1]:
    """以完整活动集合执行 1-based CAS 重排。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        req: 含全部活动物品 ID、目标顺序和预期版本的重排请求。

    Returns:
        按新顺序排列并带写后版本的完整活动物品。
    """
    try:
        items = await ItemService.reorder_items(
            novel_id.lower(),
            [item.model_dump(mode="json") for item in req.items],
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_items(items)


@router.post(
    "/novel/{novel_id}/bulk-generated",
    response_model=ItemBulkGeneratedResponseV1,
)
async def bulk_create_generated_items(
    novel_id: NovelIdPath,
    req: ItemBulkGeneratedRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> ItemBulkGeneratedResponseV1:
    """把一批 AI 物品候选幂等写入正式集合。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        req: 候选、可重算 basis 与精确来源版本。
        idempotency_key: 批量确认必填幂等键。

    Returns:
        临时候选引用到正式物品 ID 的映射及写后物品。
    """
    try:
        result = await ItemService.bulk_create_generated_items(
            novel_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return ItemBulkGeneratedResponseV1(
        candidate_ref_map=result["candidate_ref_map"],
        items=_serialize_items(result["items"]),
    )


@router.get(
    "/novel/{novel_id}/{item_id}/delete-impact",
    response_model=ItemDeleteImpactV1,
)
async def get_item_delete_impact(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
) -> ItemDeleteImpactV1:
    """读取活动或回收站物品的永久删除影响。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。

    Returns:
        各正式消费者的引用数量和总数。
    """
    try:
        impact = await ItemService.get_delete_impact(novel_id.lower(), item_id)
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return ItemDeleteImpactV1.model_validate(impact)


@router.get("/novel/{novel_id}/{item_id}", response_model=ItemReadV1)
async def get_item(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
) -> ItemReadV1:
    """读取小说内一条未删除物品。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。

    Returns:
        指定的未删除公开物品。
    """
    try:
        item = await ItemService.get_item(novel_id.lower(), item_id)
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.put("/novel/{novel_id}/{item_id}", response_model=ItemReadV1)
async def update_item(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
    req: ItemUpdateV1,
) -> ItemReadV1:
    """使用预期版本更新物品内容与当前引用。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。
        req: 含预期版本和显式更新字段的严格请求。

    Returns:
        更新成功后的完整公开物品。
    """
    try:
        item = await ItemService.update_item(novel_id.lower(), item_id, req)
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.post(
    "/novel/{novel_id}/{item_id}/transitions/{target_status}",
    response_model=ItemReadV1,
)
async def transition_item_status(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
    target_status: ItemLifecycleStatus,
    req: ItemVersionRequestV1,
) -> ItemReadV1:
    """执行物品专用状态转换并原子处理终态引用。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。
        target_status: 目标生命周期状态。
        req: 含当前预期版本的状态转换请求。

    Returns:
        状态转换后的完整公开物品。
    """
    try:
        item = await ItemService.transition_item_status(
            novel_id.lower(),
            item_id,
            target_status=target_status,
            expected_version=req.expected_version,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.delete("/novel/{novel_id}/{item_id}", response_model=ItemReadV1)
async def soft_delete_item(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
    expected_version: int = Query(..., ge=1),
) -> ItemReadV1:
    """软删除物品并收紧活动集合顺序。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。
        expected_version: 调用方持有的物品版本。

    Returns:
        已进入回收站的完整公开物品。
    """
    try:
        item = await ItemService.soft_delete_item(
            novel_id.lower(),
            item_id,
            expected_version=expected_version,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.post("/novel/{novel_id}/{item_id}/restore", response_model=ItemReadV1)
async def restore_item(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
    req: ItemVersionRequestV1,
) -> ItemReadV1:
    """恢复回收站物品并追加到活动集合末尾。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。
        req: 含当前预期版本的恢复请求。

    Returns:
        恢复后的完整公开物品。
    """
    try:
        item = await ItemService.restore_item(
            novel_id.lower(),
            item_id,
            expected_version=req.expected_version,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return _serialize_item(item)


@router.delete(
    "/novel/{novel_id}/{item_id}/hard",
    response_model=ItemHardDeleteResponseV1,
)
async def hard_delete_item(
    novel_id: NovelIdPath,
    item_id: ItemIdPath,
    expected_version: int = Query(..., ge=1),
) -> ItemHardDeleteResponseV1:
    """永久删除没有正式消费者引用的回收站物品。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        item_id: 稳定物品 ID 路径参数。
        expected_version: 调用方持有的回收站物品版本。

    Returns:
        被删除物品 ID 和删除时复核的消费者影响。
    """
    try:
        result = await ItemService.hard_delete_item(
            novel_id.lower(),
            item_id,
            expected_version=expected_version,
        )
    except EXPECTED_ITEM_ERRORS as exc:
        _raise_item_http_error(exc)
    return ItemHardDeleteResponseV1(
        message="Hard deleted successfully",
        item_id=result["item_id"],
        impact=ItemDeleteImpactV1.model_validate(result["impact"]),
    )


__all__ = ["router"]
