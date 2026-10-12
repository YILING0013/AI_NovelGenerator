from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query
from pymongo.errors import PyMongoError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.db.errors import (
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
)
from backend.llm.schemas.novel_pydantic import (
    CORE_FACTION_RELATION_REF_PATTERN,
    CoreFactionsAIConfirmationRequestV2,
)
from backend.llm.schemas.faction_relation_pydantic import FactionRelationResponseV1
from backend.llm.schemas.character_pydantic import (
    FACTION_BUSINESS_ID_PATTERN,
    _validate_bson_safe_extra,
)
from backend.llm.schemas.faction_creation_pydantic import FactionCreateRequestV1
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.faction_service import FactionService
from backend.db.repositories.faction_repository import normalize_faction_name

router = APIRouter(prefix="/api/factions", tags=["factions"])

FactionIdPath = Annotated[str, Path(pattern=FACTION_BUSINESS_ID_PATTERN)]
_FACTION_RELATION_ID_PATTERN = r"^fr_[0-9]{6,}$"
_EXPECTED_FACTION_ERRORS = (
    GenerationDomainError,
    DomainApiError,
    NotFoundError,
    DuplicateKeyError,
    InvalidIdError,
    TransactionNotSupportedError,
    PyMongoError,
    ValidationError,
    TypeError,
    ValueError,
)


class FactionUpdateRequestV1(BaseModel):
    """阶段 1 核心势力内容更新请求。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    expected_version: int = Field(ge=1, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    alias: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=10)
    faction_type: str | None = Field(default=None, max_length=80)
    parent_faction_id: str | None = Field(
        default=None,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    )
    positioning: str | None = Field(default=None, max_length=500)
    public_stance: str | None = Field(default=None, max_length=500)
    core_goal: str | None = Field(default=None, max_length=500)
    hidden_goal: str | None = Field(default=None, max_length=500)
    resources_and_advantages: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] | None = Field(default=None, max_length=6)
    organization_style: str | None = Field(default=None, max_length=300)
    core_values: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] | None = Field(default=None, max_length=6)
    conflict_with_mainline: str | None = Field(default=None, max_length=600)
    is_public: bool | None = None
    influence_scope: str | None = Field(default=None, max_length=80)
    active_status: Literal["active", "inactive"] | None = None
    expandability: str | None = Field(default=None, max_length=500)
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] | None = Field(default=None, max_length=8)
    first_appearance_volume_id: str | None = Field(default=None, max_length=100)
    first_appearance_chapter_id: str | None = Field(default=None, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, strict=True)
    extra: dict[str, JsonValue] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        """在 DTO 层拒绝显式 null 或仅含空白的更新名称。

        Args:
            value: 更新请求中的可选势力名称。

        Returns:
            首尾空白已清理的非空名称。
        """
        if value is None:
            raise ValueError("势力名称不能为空")
        return normalize_faction_name(value)[0]

    @field_validator("extra")
    @classmethod
    def validate_extra_bson(
        cls,
        value: dict[str, JsonValue] | None,
    ) -> dict[str, JsonValue] | None:
        """校验更新后的势力扩展 JSON 可安全编码为受限 BSON。"""
        return None if value is None else _validate_bson_safe_extra(value)

    @model_validator(mode="after")
    def require_content_field(self) -> "FactionUpdateRequestV1":
        """拒绝只提交 expected_version 的空更新。

        Args:
            无。

        Returns:
            至少显式提交一个内容字段的请求。
        """
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("势力更新至少需要一个可修改字段")
        return self


class RestoreFactionRequest(BaseModel):
    """使用乐观锁恢复回收站势力的请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)


class FactionSortItemV1(BaseModel):
    """单个核心势力排序 CAS 条目。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    expected_version: int = Field(ge=1, strict=True)
    sort_order: int = Field(ge=0, strict=True)


class BatchUpdateSortOrderRequest(BaseModel):
    """完整活动核心势力排序请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[FactionSortItemV1] = Field(min_length=1)


class FactionResponseV1(BaseModel):
    """势力主档严格公开响应。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    alias: list[str] = Field(default_factory=list)
    faction_type: str | None = ""
    level_type: Literal["core", "volume", "local"]
    parent_faction_id: str | None = Field(
        default=None,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    )
    volume_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    positioning: str | None = ""
    public_stance: str | None = ""
    core_goal: str | None = ""
    hidden_goal: str | None = ""
    resources_and_advantages: list[str] = Field(default_factory=list)
    organization_style: str | None = ""
    core_values: list[str] = Field(default_factory=list)
    conflict_with_mainline: str | None = ""
    is_public: bool = True
    influence_scope: str | None = ""
    active_status: Literal["active", "inactive"]
    expandability: str | None = ""
    tags: list[str] = Field(default_factory=list)
    first_appearance_volume_id: str | None = None
    first_appearance_chapter_id: str | None = None
    sort_order: int = Field(ge=0, strict=True)
    extra: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(ge=1, strict=True)
    is_deleted: bool
    deleted_at: datetime | None = None
    deletion_sources: list[Literal["user"]] = Field(default_factory=list, max_length=1)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "alias",
        "resources_and_advantages",
        "core_values",
        "tags",
        mode="before",
    )
    @classmethod
    def normalize_string_lists(cls, value: object) -> list[str]:
        """把历史空值清理为稳定字符串数组。

        Args:
            value: Repository 返回的原始字段。

        Returns:
            去空、去重并保持首次出现顺序的字符串数组。
        """
        if not isinstance(value, list):
            return []
        return list(
            dict.fromkeys(
                item.strip()
                for item in value
                if isinstance(item, str) and item.strip()
            )
        )

    @model_validator(mode="after")
    def validate_scope_and_lifecycle(self) -> "FactionResponseV1":
        """校验公开主档的归属卷与删除审计组合。

        Returns:
            层级、归属卷和删除审计相互一致的公开主档。
        """
        if self.level_type == "core" and self.volume_id is not None:
            raise ValueError("core 势力不能设置 volume_id")
        if self.level_type in {"volume", "local"} and self.volume_id is None:
            raise ValueError("volume/local 势力必须设置 volume_id")
        has_source = bool(self.deletion_sources)
        if self.is_deleted != has_source:
            raise ValueError("is_deleted 必须与 deletion_sources 一致")
        if has_source != (self.deleted_at is not None):
            raise ValueError("deleted_at 必须与 deletion_sources 一致")
        return self


class FactionHardDeleteStatsV1(BaseModel):
    """势力硬删除的明确消费者统计。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    faction_deleted: int = Field(ge=0, strict=True)
    children_unlinked: int = Field(ge=0, strict=True)
    relations_deleted: int = Field(ge=0, strict=True)
    bindings_deleted: int = Field(ge=0, strict=True)


class FactionHardDeleteResponseV1(BaseModel):
    """势力硬删除公开响应。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    message: Literal["Hard deleted successfully"]
    stats: FactionHardDeleteStatsV1


class FactionBulkCoreResponseV1(BaseModel):
    """核心势力与关系正式写入的严格公开响应。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    factions: list[FactionResponseV1]
    faction_relations: list[FactionRelationResponseV1]
    faction_ref_map: dict[str, str]
    relation_ref_map: dict[
        Annotated[str, Field(pattern=CORE_FACTION_RELATION_REF_PATTERN)],
        Annotated[str, Field(pattern=_FACTION_RELATION_ID_PATTERN)],
    ] = Field(max_length=500)

    @field_validator("relation_ref_map", mode="before")
    @classmethod
    def validate_raw_relation_ref_map(cls, value: object) -> object:
        """在类型转换前拒绝非字符串映射和重复正式 ID。

        Args:
            value: Service 返回的候选关系 ref 到正式 ID 映射。

        Returns:
            仅含严格字符串键值且正式 ID 唯一的原映射。
        """
        if not isinstance(value, dict) or any(
            not isinstance(relation_ref, str)
            or not isinstance(relation_id, str)
            for relation_ref, relation_id in value.items()
        ):
            raise ValueError("relation_ref_map 必须是字符串到字符串的映射")
        if len(value.values()) != len(set(value.values())):
            raise ValueError("relation_ref_map 中的正式关系 ID 不能重复")
        return value


def _serialize_faction(faction: dict) -> FactionResponseV1:
    """按公开字段白名单序列化阵营并过滤内部并发护栏。

    Args:
        faction: MongoDB 阵营文档。

    Returns:
        不含 MongoDB ``_id`` 和内部并发、幂等字段的严格公开响应。
    """
    public_fields = set(FactionResponseV1.model_fields)
    serialized = {
        field: value
        for field, value in faction.items()
        if field in public_fields
    }
    if "novel_id" in serialized:
        serialized["novel_id"] = str(serialized["novel_id"])
    if serialized.get("volume_id") is not None:
        serialized["volume_id"] = str(serialized["volume_id"])
    return FactionResponseV1.model_validate(serialized)


def _serialize_factions(factions: list[dict[str, Any]]) -> list[FactionResponseV1]:
    """批量序列化阵营列表。

    Args:
        factions: MongoDB 阵营文档列表。

    Returns:
        可 JSON 序列化的阵营文档列表。
    """
    return [_serialize_faction(faction) for faction in factions]


def _serialize_relation(relation: dict[str, Any]) -> FactionRelationResponseV1:
    """将阵营关系文档中的 ObjectId 转为字符串。

    Args:
        relation: MongoDB 阵营关系文档。

    Returns:
        不含内部字段的严格阵营关系公开响应。
    """
    public_fields = set(FactionRelationResponseV1.model_fields)
    payload = {field: value for field, value in relation.items() if field in public_fields}
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])
    return FactionRelationResponseV1.model_validate(payload)


def _serialize_relations(
    relations: list[dict[str, Any]],
) -> list[FactionRelationResponseV1]:
    """批量序列化阵营关系列表。

    Args:
        relations: MongoDB 阵营关系文档列表。

    Returns:
        可 JSON 序列化的阵营关系文档列表。
    """
    return [_serialize_relation(relation) for relation in relations]


def _translate_domain_error(exc: Exception) -> HTTPException:
    """把势力领域异常转换为公共 HTTP 错误结构。

    Args:
        exc: Repository、Service 或幂等校验抛出的异常。

    Returns:
        可由路由直接抛出的 HTTPException。
    """
    if isinstance(exc, (TransactionNotSupportedError, PyMongoError)):
        return HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "势力数据库暂时不可用，请稍后重试",
            },
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
    if isinstance(exc, DomainApiError):
        detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.details is not None:
            detail["details"] = sanitize_json_value(exc.details)
        return HTTPException(status_code=exc.status_code, detail=detail)
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "FACTION_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, DuplicateKeyError):
        message = str(exc)
        code = "VERSION_CONFLICT" if "版本冲突" in message else "FACTION_CONFLICT"
        return HTTPException(status_code=409, detail={"code": code, "message": message})
    return HTTPException(
        status_code=422,
        detail={"code": "FACTION_VALIDATION_FAILED", "message": str(exc)},
    )


@router.post(
    "/novel/{novel_id}/create",
    response_model=FactionResponseV1,
)
async def create_faction(
    novel_id: str,
    req: FactionCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FactionResponseV1:
    """创建一个新阵营，挂载到指定小说下。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 阵营创建请求。
        idempotency_key: 必填的人工创建幂等请求头。

    Returns:
        不含 MongoDB ``_id`` 的完整新势力公开响应。
    """
    try:
        faction = await FactionService.create_faction(
            novel_id,
            req.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
        return _serialize_faction(faction)
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.post(
    "/novel/{novel_id}/bulk-core-with-relations",
    response_model=FactionBulkCoreResponseV1,
)
async def bulk_create_core_factions_with_relations(
    novel_id: str,
    req: CoreFactionsAIConfirmationRequestV2,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FactionBulkCoreResponseV1:
    """批量创建全书核心阵营和阵营关系。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 已由 FastAPI 严格校验的核心势力 AI 确认信封。
        idempotency_key: 必填的确认幂等请求头。

    Returns:
        新创建的核心阵营与阵营关系。
    """
    try:
        result = await FactionService.bulk_create_core_factions_with_relations(
            novel_id,
            req,
            idempotency_key=idempotency_key,
        )
        return FactionBulkCoreResponseV1(
            factions=_serialize_factions(result["factions"]),
            faction_relations=_serialize_relations(result["faction_relations"]),
            faction_ref_map=result["faction_ref_map"],
            relation_ref_map=result["relation_ref_map"],
        )
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}",
    response_model=dict[str, list[FactionResponseV1]],
)
async def get_factions_by_novel(
    novel_id: str,
) -> dict[str, list[FactionResponseV1]]:
    """获取指定小说下的所有阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        阵营列表响应。
    """
    try:
        factions = await FactionService.get_factions_by_novel(novel_id)
        return {"data": _serialize_factions(factions)}
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/level/{level_type}",
    response_model=dict[str, list[FactionResponseV1]],
)
async def get_factions_by_level_type(
    novel_id: str,
    level_type: str,
) -> dict[str, list[FactionResponseV1]]:
    """获取指定小说下特定层级类型的阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。
        level_type: 阵营层级类型。

    Returns:
        阵营列表响应。
    """
    try:
        factions = await FactionService.get_factions_by_level_type(novel_id, level_type)
        return {"data": _serialize_factions(factions)}
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/trash",
    response_model=dict[str, list[FactionResponseV1]],
)
async def get_deleted_factions(
    novel_id: str,
    level_type: str | None = None,
) -> dict[str, list[FactionResponseV1]]:
    """获取指定小说下已软删除的阵营列表。

    Args:
        novel_id: 小说 ObjectId 字符串。
        level_type: 可选阵营层级类型。

    Returns:
        已软删除阵营列表响应。
    """
    try:
        factions = await FactionService.get_deleted_factions_by_level_type(novel_id, level_type)
        return {"data": _serialize_factions(factions)}
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/children/{parent_faction_id}",
    response_model=dict[str, list[FactionResponseV1]],
)
async def get_child_factions(
    novel_id: str,
    parent_faction_id: FactionIdPath,
) -> dict[str, list[FactionResponseV1]]:
    """获取指定父级阵营的所有直接子阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        parent_faction_id: 父级业务阵营 ID。

    Returns:
        子阵营列表响应。
    """
    try:
        factions = await FactionService.get_child_factions(novel_id, parent_faction_id)
        return {"data": _serialize_factions(factions)}
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.patch(
    "/novel/{novel_id}/batch-sort",
    response_model=dict[str, list[FactionResponseV1]],
)
async def batch_update_sort_order(
    novel_id: str,
    req: BatchUpdateSortOrderRequest,
) -> dict[str, list[FactionResponseV1]]:
    """批量更新阵营的排序权重。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 批量排序更新请求。

    Returns:
        按请求顺序排列的更新后完整势力列表。
    """
    try:
        updated = await FactionService.batch_update_sort_order(
            novel_id,
            [item.model_dump(mode="json") for item in req.items],
        )
        return {"data": _serialize_factions(updated)}
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/{faction_id}",
    response_model=FactionResponseV1,
)
async def get_faction(
    novel_id: str,
    faction_id: FactionIdPath,
) -> FactionResponseV1:
    """根据 novel_id + faction_id 获取单个阵营详情。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。

    Returns:
        阵营详情。
    """
    try:
        faction = await FactionService.get_faction(novel_id, faction_id)
        return _serialize_faction(faction)
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{faction_id}",
    response_model=FactionResponseV1,
)
async def update_faction(
    novel_id: str,
    faction_id: FactionIdPath,
    req: FactionUpdateRequestV1,
) -> FactionResponseV1:
    """更新阵营的基础信息。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        req: 含 expected_version 的阵营更新请求。

    Returns:
        更新并递增版本后的完整势力。
    """
    try:
        faction = await FactionService.update_faction_info(
            novel_id,
            faction_id,
            req.model_dump(exclude_unset=True),
        )
        return _serialize_faction(faction)
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.delete(
    "/novel/{novel_id}/{faction_id}",
    response_model=FactionResponseV1,
)
async def soft_delete_faction(
    novel_id: str,
    faction_id: FactionIdPath,
    expected_version: int = Query(..., ge=1),
) -> FactionResponseV1:
    """软删除指定阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        expected_version: 客户端基于的势力版本。

    Returns:
        软删除并递增版本后的完整势力。
    """
    try:
        faction = await FactionService.soft_delete_faction(
            novel_id,
            faction_id,
            expected_version=expected_version,
        )
        return _serialize_faction(faction)
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.post(
    "/novel/{novel_id}/{faction_id}/restore",
    response_model=FactionResponseV1,
)
async def restore_faction(
    novel_id: str,
    faction_id: FactionIdPath,
    req: RestoreFactionRequest,
) -> FactionResponseV1:
    """恢复已软删除的阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        req: 含 expected_version 的恢复请求。

    Returns:
        恢复并递增版本后的完整势力。
    """
    try:
        faction = await FactionService.restore_faction(
            novel_id,
            faction_id,
            expected_version=req.expected_version,
        )
        return _serialize_faction(faction)
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc


@router.delete(
    "/novel/{novel_id}/{faction_id}/hard",
    response_model=FactionHardDeleteResponseV1,
)
async def hard_delete_faction(
    novel_id: str,
    faction_id: FactionIdPath,
    expected_version: int = Query(..., ge=1),
) -> FactionHardDeleteResponseV1:
    """彻底物理删除指定阵营。

    Args:
        novel_id: 小说 ObjectId 字符串。
        faction_id: 业务层阵营 ID。
        expected_version: 客户端基于的势力版本。

    Returns:
        删除统计。
    """
    try:
        stats = await FactionService.hard_delete_faction(
            novel_id,
            faction_id,
            expected_version=expected_version,
        )
        return FactionHardDeleteResponseV1(
            message="Hard deleted successfully",
            stats=FactionHardDeleteStatsV1.model_validate(stats),
        )
    except _EXPECTED_FACTION_ERRORS as exc:
        raise _translate_domain_error(exc) from exc
