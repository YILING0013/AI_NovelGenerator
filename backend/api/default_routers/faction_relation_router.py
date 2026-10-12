"""阵营关系创建、查询和完整生命周期 API。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query
from pydantic import ValidationError

from backend.api.error_protocol import relation_http_exception
from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError
from backend.llm.schemas.faction_relation_pydantic import (
    FactionRelationActiveRequestV1,
    FactionRelationCreateRequestV1,
    FactionRelationHardDeleteResponseV1,
    FactionRelationResponseV1,
    FactionRelationUpdateRequestV1,
    FactionRelationVersionRequestV1,
    FactionRelationsAppendResponseV1,
    FactionRelationsAppendRequestV1,
)
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.faction_relation_service import (
    FactionRelationService,
)

router = APIRouter(prefix="/api/faction-relations", tags=["faction-relations"])
FactionRelationIdPath = Annotated[str, Path(pattern=r"^fr_[0-9]{6,}$")]
FactionIdPath = Annotated[str, Path(pattern=FACTION_BUSINESS_ID_PATTERN)]


def serialize_faction_relation(relation: dict[str, Any]) -> FactionRelationResponseV1:
    """把阵营关系 BSON 文档转换为严格公开响应。

    Args:
        relation: MongoDB 阵营关系文档。

    Returns:
        不含 MongoDB ``_id`` 和内部幂等字段的公开响应。
    """
    public_fields = set(FactionRelationResponseV1.model_fields)
    payload = {key: value for key, value in relation.items() if key in public_fields}
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])
    return FactionRelationResponseV1.model_validate(payload)


@router.post("/novel/{novel_id}", response_model=FactionRelationResponseV1)
async def create_faction_relation(
    novel_id: str,
    request: FactionRelationCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FactionRelationResponseV1:
    """人工创建一条正式阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        request: 只使用稳定 faction_id 的严格创建请求。
        idempotency_key: 必填创建幂等请求头。

    Returns:
        新建或幂等回放的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.create_relation(
            novel_id,
            request,
            idempotency_key=idempotency_key,
        )
        return serialize_faction_relation(relation)
    except (
        GenerationDomainError,
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.post(
    "/novel/{novel_id}/bulk-append",
    response_model=FactionRelationsAppendResponseV1,
)
async def bulk_append_faction_relations(
    novel_id: str,
    request: FactionRelationsAppendRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FactionRelationsAppendResponseV1:
    """把用户选择并编辑后的候选追加为正式阵营关系。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        request: 已由 FastAPI 判别并严格校验的人工批次或 AI 确认信封。
        idempotency_key: 必填的批量追加幂等请求头。

    Returns:
        新创建的正式阵营关系列表。
    """
    try:
        result = await FactionRelationService.bulk_append_relations(
            novel_id,
            request,
            idempotency_key=idempotency_key,
        )
        return FactionRelationsAppendResponseV1(
            faction_relations=[
                serialize_faction_relation(relation)
                for relation in result["faction_relations"]
            ],
            relation_ref_map=result["relation_ref_map"],
        )
    except (
        GenerationDomainError,
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        ValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.get(
    "/novel/{novel_id}",
    response_model=dict[str, list[FactionRelationResponseV1]],
)
async def get_relations_by_novel(
    novel_id: str,
    is_active: bool | None = None,
) -> dict[str, list[FactionRelationResponseV1]]:
    """获取指定小说下阵营关系，可按有效态筛选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        is_active: True/False 分别筛选有效/无效，None 返回全部未删除关系。

    Returns:
        阵营关系列表响应。
    """
    try:
        relations = await FactionRelationService.get_relations_by_novel(
            novel_id,
            active_only=is_active,
        )
        return {"data": [serialize_faction_relation(item) for item in relations]}
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise relation_http_exception(exc) from exc


@router.get(
    "/novel/{novel_id}/faction/{faction_id}",
    response_model=dict[str, list[FactionRelationResponseV1]],
)
async def get_relations_by_faction(
    novel_id: str,
    faction_id: FactionIdPath,
    is_active: bool | None = None,
) -> dict[str, list[FactionRelationResponseV1]]:
    """获取某个阵营参与的当前有效关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        is_active: True/False 分别筛选有效/无效，None 返回全部未删除关系。

    Returns:
        阵营关系列表响应。
    """
    try:
        relations = await FactionRelationService.get_relations_by_faction(
            novel_id,
            faction_id,
            active_only=is_active,
        )
        return {"data": [serialize_faction_relation(item) for item in relations]}
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise relation_http_exception(exc) from exc


@router.get(
    "/novel/{novel_id}/trash",
    response_model=dict[str, list[FactionRelationResponseV1]],
)
async def list_deleted_faction_relations(
    novel_id: str,
) -> dict[str, list[FactionRelationResponseV1]]:
    """列出小说阵营关系回收站。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        包含已软删除阵营关系的 ``data`` 响应。
    """
    try:
        relations = await FactionRelationService.list_deleted_relations(novel_id)
        return {"data": [serialize_faction_relation(item) for item in relations]}
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise relation_http_exception(exc) from exc


@router.get(
    "/novel/{novel_id}/{relation_id}",
    response_model=FactionRelationResponseV1,
)
async def get_faction_relation(
    novel_id: str,
    relation_id: FactionRelationIdPath,
) -> FactionRelationResponseV1:
    """获取一条阵营关系详情。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。

    Returns:
        匹配的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.get_relation(novel_id, relation_id)
        return serialize_faction_relation(relation)
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise relation_http_exception(exc) from exc


@router.put(
    "/novel/{novel_id}/{relation_id}",
    response_model=FactionRelationResponseV1,
)
async def update_faction_relation(
    novel_id: str,
    relation_id: FactionRelationIdPath,
    request: FactionRelationUpdateRequestV1,
) -> FactionRelationResponseV1:
    """更新阵营关系内容，端点保持不可变。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。
        request: 内容字段与 expected_version。

    Returns:
        更新后的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.update_relation(
            novel_id,
            relation_id,
            request,
        )
        return serialize_faction_relation(relation)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.put(
    "/novel/{novel_id}/{relation_id}/active",
    response_model=FactionRelationResponseV1,
)
async def set_faction_relation_active(
    novel_id: str,
    relation_id: FactionRelationIdPath,
    request: FactionRelationActiveRequestV1,
) -> FactionRelationResponseV1:
    """修改阵营关系的用户启停意图。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。
        request: 目标状态与 expected_version。

    Returns:
        更新后的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.set_relation_active(
            novel_id,
            relation_id,
            expected_version=request.expected_version,
            is_active=request.is_active,
        )
        return serialize_faction_relation(relation)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.delete(
    "/novel/{novel_id}/{relation_id}",
    response_model=FactionRelationResponseV1,
)
async def delete_faction_relation(
    novel_id: str,
    relation_id: FactionRelationIdPath,
    expected_version: int = Query(..., ge=1),
) -> FactionRelationResponseV1:
    """将阵营关系软删除到回收站。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。
        expected_version: 调用方持有的乐观锁版本。

    Returns:
        软删除后的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.soft_delete_relation(
            novel_id,
            relation_id,
            expected_version=expected_version,
        )
        return serialize_faction_relation(relation)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.post(
    "/novel/{novel_id}/{relation_id}/restore",
    response_model=FactionRelationResponseV1,
)
async def restore_faction_relation(
    novel_id: str,
    relation_id: FactionRelationIdPath,
    request: FactionRelationVersionRequestV1,
) -> FactionRelationResponseV1:
    """恢复回收站中的阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。
        request: 携带 expected_version 的恢复请求。

    Returns:
        恢复后的完整阵营关系。
    """
    try:
        relation = await FactionRelationService.restore_relation(
            novel_id,
            relation_id,
            expected_version=request.expected_version,
        )
        return serialize_faction_relation(relation)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


@router.delete(
    "/novel/{novel_id}/{relation_id}/hard",
    response_model=FactionRelationHardDeleteResponseV1,
)
async def hard_delete_faction_relation(
    novel_id: str,
    relation_id: FactionRelationIdPath,
    expected_version: int = Query(..., ge=1),
) -> FactionRelationHardDeleteResponseV1:
    """物理删除回收站中的阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        relation_id: 稳定阵营关系业务 ID。
        expected_version: 调用方持有的乐观锁版本。

    Returns:
        包含删除结果和稳定关系 ID 的响应。
    """
    try:
        deleted = await FactionRelationService.hard_delete_relation(
            novel_id,
            relation_id,
            expected_version=expected_version,
        )
        return FactionRelationHardDeleteResponseV1(
            deleted=deleted,
            relation_id=relation_id,
        )
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise relation_http_exception(exc) from exc


__all__ = ["router", "serialize_faction_relation"]
