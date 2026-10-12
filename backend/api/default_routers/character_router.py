"""角色主档公开 API。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, ValidationError
from pymongo.errors import PyMongoError

from backend.api.default_routers.character_faction_binding_router import (
    CharacterFactionBindingResponseV1,
    serialize_character_faction_binding,
)
from backend.api.error_protocol import api_http_exception, sanitize_json_value
from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError, TransactionNotSupportedError
from backend.llm.schemas.character_pydantic import (
    CharacterCreateRequestV1,
    CharacterRestoreRequestV1,
    CharacterResponseV1,
    CharacterStatusUpdateRequestV1,
    CharacterUpdateRequestV1,
    CoreCharactersAIConfirmationRequestV1,
)
from backend.services.novel.character_service import CharacterService
from backend.services.novel.errors import GenerationDomainError


router = APIRouter(prefix="/api/characters", tags=["characters"])
CharacterIdPath = Annotated[str, Path(pattern=r"^char_[0-9]{6,}$")]


class CoreCharactersConfirmationResponseV1(BaseModel):
    """核心角色及非空势力绑定确认的严格公开响应。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    character_ref_map: dict[str, str]
    characters: list[CharacterResponseV1]
    character_faction_bindings: list[CharacterFactionBindingResponseV1]


def serialize_character(character: dict[str, Any]) -> CharacterResponseV1:
    """把角色 BSON 文档转换为严格公开响应。

    Args:
        character: CharacterRepository 返回的角色 BSON 文档。

    Returns:
        不含 Mongo ``_id`` 和内部生成批次字段的 CharacterResponseV1。
    """
    public_fields = set(CharacterResponseV1.model_fields)
    payload = {key: value for key, value in character.items() if key in public_fields}
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])

    return CharacterResponseV1.model_validate(payload)


def _translate_character_error(exc: Exception) -> HTTPException:
    """把角色领域异常转换为稳定 HTTP 状态。

    Args:
        exc: Repository、Service 或领域校验抛出的异常。

    Returns:
        可由路由直接抛出的 HTTPException。
    """
    if isinstance(exc, TransactionNotSupportedError):
        return api_http_exception(
            status_code=503,
            code="CHARACTER_TRANSACTION_REQUIRED",
            message="更新人物资料需要启用 MongoDB 事务并连接副本集",
        )
    if isinstance(exc, ValidationError):
        field_errors: dict[str, list[str]] = {}
        for error in exc.errors():
            field = ".".join(str(part) for part in error.get("loc", ())) or "$"
            message = str(
                sanitize_json_value(error.get("msg", "请求字段不合法"))
            ).strip()
            if message and message not in field_errors.setdefault(field, []):
                field_errors[field].append(message)
        return HTTPException(
            status_code=422,
            detail={
                "code": "REQUEST_VALIDATION_FAILED",
                "message": "请求字段校验失败",
                "field_errors": field_errors,
            },
        )
    if isinstance(exc, GenerationDomainError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DuplicateKeyError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, InvalidIdError):
        return HTTPException(
            status_code=422,
            detail={"code": "INVALID_OBJECT_ID", "message": str(exc)},
        )
    return HTTPException(
        status_code=422,
        detail={"code": "CHARACTER_VALIDATION_FAILED", "message": str(exc)},
    )


@router.post("/novel/{novel_id}", response_model=CharacterResponseV1)
async def create_character(
    novel_id: str,
    req: CharacterCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CharacterResponseV1:
    """在指定小说中人工创建角色主档。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 已通过严格 Schema 校验的角色创建请求。
        idempotency_key: 必填的创建幂等请求头。

    Returns:
        已创建角色的完整公开响应。
    """
    try:
        character = await CharacterService.create_character(
            novel_id,
            req,
            idempotency_key=idempotency_key,
        )
        return serialize_character(character)
    except (
        GenerationDomainError,
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        ValidationError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.post(
    "/novel/{novel_id}/bulk-core-with-bindings",
    response_model=CoreCharactersConfirmationResponseV1,
)
async def bulk_create_core_characters_with_bindings(
    novel_id: str,
    req: CoreCharactersAIConfirmationRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CoreCharactersConfirmationResponseV1:
    """确认所选核心角色及其非空势力绑定候选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 严格候选、选择、basis 和可重算生成输入。
        idempotency_key: 必填的确认幂等请求头。

    Returns:
        稳定 ref 映射、新角色和所选非空绑定。
    """
    try:
        result = await CharacterService.bulk_create_core_with_bindings(
            novel_id,
            req,
            idempotency_key=idempotency_key,
        )
        return CoreCharactersConfirmationResponseV1(
            character_ref_map=result["character_ref_map"],
            characters=[
                serialize_character(character) for character in result["characters"]
            ],
            character_faction_bindings=[
                serialize_character_faction_binding(binding)
                for binding in result["character_faction_bindings"]
            ],
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
        raise _translate_character_error(exc) from exc


@router.get("/novel/{novel_id}", response_model=dict[str, list[CharacterResponseV1]])
async def get_characters_by_novel(novel_id: str) -> dict[str, list[CharacterResponseV1]]:
    """获取小说内全部未删除角色。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        包含稳定排序角色列表的 ``data`` 响应。
    """
    try:
        characters = await CharacterService.get_characters_by_novel(novel_id)
        return {"data": [serialize_character(character) for character in characters]}
    except (NotFoundError, InvalidIdError) as exc:
        raise _translate_character_error(exc) from exc
    except PyMongoError as exc:
        raise api_http_exception(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="角色数据库暂时不可用，请稍后重试",
        ) from exc


@router.get(
    "/novel/{novel_id}/trash",
    response_model=dict[str, list[CharacterResponseV1]],
)
async def get_deleted_characters(
    novel_id: str,
) -> dict[str, list[CharacterResponseV1]]:
    """获取小说角色回收站列表。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        包含软删除角色列表的 ``data`` 响应。
    """
    try:
        characters = await CharacterService.get_deleted_characters_by_novel(novel_id)
        return {"data": [serialize_character(character) for character in characters]}
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise _translate_character_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{character_id}",
    response_model=CharacterResponseV1,
)
async def update_character(
    novel_id: str,
    character_id: CharacterIdPath,
    request: CharacterUpdateRequestV1,
) -> CharacterResponseV1:
    """使用乐观锁更新角色档案白名单字段。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        request: 含 expected_version 的严格更新请求。

    Returns:
        更新后的完整角色公开响应。
    """
    try:
        character = await CharacterService.update_character(
            novel_id,
            character_id,
            request,
        )
        return serialize_character(character)
    except (
        TransactionNotSupportedError,
        GenerationDomainError,
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{character_id}/status",
    response_model=CharacterResponseV1,
)
async def update_character_status(
    novel_id: str,
    character_id: CharacterIdPath,
    request: CharacterStatusUpdateRequestV1,
) -> CharacterResponseV1:
    """切换角色活动状态并联动关系与势力绑定。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        request: 新状态与 expected_version。

    Returns:
        状态更新后的完整角色公开响应。
    """
    try:
        character = await CharacterService.update_character_status(
            novel_id,
            character_id,
            request.status,
            expected_version=request.expected_version,
        )
        return serialize_character(character)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.delete(
    "/novel/{novel_id}/{character_id}",
    response_model=CharacterResponseV1,
)
async def soft_delete_character(
    novel_id: str,
    character_id: CharacterIdPath,
    expected_version: int = Query(..., ge=1),
) -> CharacterResponseV1:
    """使用乐观锁把角色移入回收站。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        expected_version: 客户端基于的角色版本。

    Returns:
        已软删除的完整角色公开响应。
    """
    try:
        character = await CharacterService.soft_delete_character(
            novel_id,
            character_id,
            expected_version=expected_version,
        )
        return serialize_character(character)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.post(
    "/novel/{novel_id}/{character_id}/restore",
    response_model=CharacterResponseV1,
)
async def restore_character(
    novel_id: str,
    character_id: CharacterIdPath,
    request: CharacterRestoreRequestV1,
) -> CharacterResponseV1:
    """使用乐观锁恢复回收站角色。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        request: 含 expected_version 的恢复请求。

    Returns:
        恢复后的完整角色公开响应。
    """
    try:
        character = await CharacterService.restore_character(
            novel_id,
            character_id,
            expected_version=request.expected_version,
        )
        return serialize_character(character)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.delete("/novel/{novel_id}/{character_id}/hard")
async def hard_delete_character(
    novel_id: str,
    character_id: CharacterIdPath,
    expected_version: int = Query(..., ge=1),
) -> dict[str, dict[str, int]]:
    """永久删除回收站角色及其全部关系和势力绑定。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 稳定角色业务 ID。
        expected_version: 客户端基于的角色版本。

    Returns:
        三类文档的精确删除计数。
    """
    try:
        stats = await CharacterService.hard_delete_character(
            novel_id,
            character_id,
            expected_version=expected_version,
        )
        return {"stats": stats}
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_character_error(exc) from exc


@router.get("/novel/{novel_id}/{character_id}", response_model=CharacterResponseV1)
async def get_character(
    novel_id: str,
    character_id: CharacterIdPath,
) -> CharacterResponseV1:
    """获取小说内单个未删除角色详情。

    Args:
        novel_id: 小说 ObjectId 字符串。
        character_id: 小说内稳定角色业务 ID。

    Returns:
        匹配角色的完整公开响应。
    """
    try:
        character = await CharacterService.get_character(novel_id, character_id)
        return serialize_character(character)
    except (NotFoundError, InvalidIdError) as exc:
        raise _translate_character_error(exc) from exc


__all__ = [
    "CoreCharactersConfirmationResponseV1",
    "router",
    "serialize_character",
]
