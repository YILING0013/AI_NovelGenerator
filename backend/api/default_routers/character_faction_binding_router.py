"""全书级角色—势力绑定创建与查询 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.db.errors import DuplicateKeyError, InvalidIdError, NotFoundError
from backend.llm.schemas.character_pydantic import (
    FACTION_BUSINESS_ID_MAX_LENGTH,
    FACTION_BUSINESS_ID_MIN_LENGTH,
    FACTION_BUSINESS_ID_PATTERN,
)
from backend.services.novel.character_faction_binding_service import CharacterFactionBindingService
from backend.services.novel.errors import GenerationDomainError


router = APIRouter(prefix="/api/character-faction-bindings", tags=["character-faction-bindings"])


class CharacterFactionBindingCreateRequestV1(BaseModel):
    """全书级角色—势力初始绑定创建请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    character_id: str = Field(pattern=r"^char_[0-9]{6,}$")
    faction_id: str = Field(
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    )
    membership_type: Literal["secondary", "covert"]
    role_title: str | None = Field(default=None, max_length=100)
    public_status: str | None = Field(default=None, max_length=200)
    loyalty_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("role_title", "public_status", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """去除可选文本首尾空白并把空串规范化为 None。

        Args:
            value: 客户端提交的可选文本。

        Returns:
            去除首尾空白后的文本，或 None。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None


class CharacterFactionBindingUpdateRequestV1(BaseModel):
    """角色—势力绑定内容更新请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)
    membership_type: Literal["secondary", "covert"] | None = None
    role_title: str | None = Field(default=None, max_length=100)
    public_status: str | None = Field(default=None, max_length=200)
    loyalty_level: int | None = Field(default=None, ge=1, le=5, strict=True)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("role_title", "public_status", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        """去除更新文本首尾空白并把空串规范化为 None。

        Args:
            value: 客户端提交的可选文本。

        Returns:
            去除首尾空白后的文本，或 None。
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_content_field(self) -> "CharacterFactionBindingUpdateRequestV1":
        """拒绝只携带版本但没有任何内容变更的 PUT 请求。

        Args:
            无。

        Returns:
            至少显式提交一个内容字段的更新请求。
        """
        if not (
            self.model_fields_set
            & {
                "membership_type",
                "role_title",
                "public_status",
                "loyalty_level",
                "notes",
            }
        ):
            raise ValueError("绑定更新至少需要一个可修改字段")
        return self


class CharacterFactionBindingActiveRequestV1(BaseModel):
    """显式变更绑定用户启停意图的请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)
    is_active: bool


class CharacterFactionBindingVersionRequestV1(BaseModel):
    """仅携带绑定乐观锁版本的生命周期请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)


BindingVersion = Annotated[int, Field(ge=1, strict=True)]
CharacterIdPath = Annotated[str, Path(pattern=r"^char_[0-9]{6,}$")]
BindingIdPath = Annotated[str, Path(pattern=r"^cfb_[0-9]{6,}$")]


class CharacterFactionBindingPrimaryRequestV1(BaseModel):
    """把既有绑定切换为主归属的严格请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)
    replaced_expected_versions: dict[str, BindingVersion]

    @field_validator("replaced_expected_versions")
    @classmethod
    def validate_replaced_binding_ids(
        cls,
        value: dict[str, int],
    ) -> dict[str, int]:
        """校验被替换版本映射只使用稳定 binding_id。

        Args:
            value: binding_id 到调用方当前版本的映射。

        Returns:
            原顺序不变的合法版本映射。
        """
        invalid_ids = [
            binding_id
            for binding_id in value
            if not binding_id.startswith("cfb_")
            or not binding_id[4:].isdigit()
            or len(binding_id) < 10
        ]
        if invalid_ids:
            raise ValueError("replaced_expected_versions 包含非法 binding_id")
        return value


class CharacterFactionBindingResponseV1(BaseModel):
    """全书级角色—势力绑定公开响应。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    binding_id: str = Field(pattern=r"^cfb_[0-9]{6,}$")
    character_id: str = Field(pattern=r"^char_[0-9]{6,}$")
    faction_id: str = Field(
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    )
    membership_type: Literal["primary", "secondary", "covert"]
    role_title: str | None = Field(default=None, max_length=100)
    public_status: str | None = Field(default=None, max_length=200)
    loyalty_level: int | None = Field(default=None, ge=1, le=5)
    joined_volume_id: None = None
    left_volume_id: None = None
    user_is_active: bool = True
    is_active: bool
    notes: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(ge=0)
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None = None
    deletion_sources: list[str] = Field(default_factory=list)
    disabled_by_character_ids: list[str] = Field(default_factory=list)
    disabled_by_faction_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "deletion_sources",
        "disabled_by_character_ids",
        "disabled_by_faction_ids",
        mode="before",
    )
    @classmethod
    def normalize_identifier_lists(cls, value: object) -> list[str]:
        """清理公开响应中的删除来源和端点阻断数组。

        Args:
            value: Repository 返回的原始数组。

        Returns:
            去空、去重且保持首次出现顺序的字符串数组。
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


class CharacterFactionBindingPrimaryResponseV1(BaseModel):
    """主归属切换的公开结果。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    primary_binding: CharacterFactionBindingResponseV1
    affected_bindings: list[CharacterFactionBindingResponseV1]


class CharacterFactionBindingHardDeleteResponseV1(BaseModel):
    """绑定硬删除公开结果。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    deleted: bool
    binding_id: str = Field(pattern=r"^cfb_[0-9]{6,}$")


def serialize_character_faction_binding(
    binding: dict,
) -> CharacterFactionBindingResponseV1:
    """将 MongoDB 绑定文档转换为不暴露内部 _id 的公开字典。

    Args:
        binding: MongoDB 返回的角色—势力绑定文档。

    Returns:
        不含 MongoDB ``_id`` 和内部字段的严格公开响应。
    """
    public_fields = set(CharacterFactionBindingResponseV1.model_fields)
    serialized = {key: value for key, value in binding.items() if key in public_fields}
    if "novel_id" in serialized:
        serialized["novel_id"] = str(serialized["novel_id"])
    return CharacterFactionBindingResponseV1.model_validate(serialized)


def _translate_domain_error(exc: Exception) -> HTTPException:
    """把领域异常转换为稳定 HTTP 状态。

    Args:
        exc: Repository 或 Service 抛出的领域异常。

    Returns:
        可由路由直接抛出的 HTTPException。
    """
    if isinstance(exc, GenerationDomainError):
        return HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        )
    if isinstance(exc, NotFoundError):
        return HTTPException(
            status_code=404,
            detail={"code": "BINDING_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, DuplicateKeyError):
        message = str(exc)
        code = "VERSION_CONFLICT" if "版本冲突" in message else "BINDING_CONFLICT"
        return HTTPException(status_code=409, detail={"code": code, "message": message})
    if isinstance(exc, InvalidIdError):
        return HTTPException(
            status_code=422,
            detail={"code": "INVALID_OBJECT_ID", "message": str(exc)},
        )
    return HTTPException(
        status_code=422,
        detail={"code": "BINDING_VALIDATION_FAILED", "message": str(exc)},
    )


@router.post(
    "/novel/{novel_id}",
    response_model=CharacterFactionBindingResponseV1,
)
async def create_binding(
    novel_id: str,
    request: CharacterFactionBindingCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CharacterFactionBindingResponseV1:
    """创建一条全书级 active 核心角色—核心势力绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        request: 经严格 Schema 校验的绑定创建请求。
        idempotency_key: 必填的创建幂等请求头。

    Returns:
        新创建的公开绑定文档。
    """
    try:
        binding = await CharacterFactionBindingService.create_binding(
            novel_id,
            request,
            idempotency_key=idempotency_key,
        )
        return serialize_character_faction_binding(binding)
    except (GenerationDomainError, NotFoundError, DuplicateKeyError, InvalidIdError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}",
    response_model=dict[str, list[CharacterFactionBindingResponseV1]],
)
async def list_bindings(
    novel_id: str,
    character_id: str | None = Query(default=None, pattern=r"^char_[0-9]{6,}$"),
    faction_id: str | None = Query(
        default=None,
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    ),
    membership_type: Literal["primary", "secondary", "covert"] | None = None,
    is_active: bool | None = True,
) -> dict[str, list[CharacterFactionBindingResponseV1]]:
    """列出小说内全书级角色—势力绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        character_id: 可选角色业务 ID 过滤。
        faction_id: 可选势力业务 ID 过滤。
        membership_type: 可选成员类型过滤。
        is_active: 可选活动状态过滤。

    Returns:
        稳定排序的公开绑定文档列表。
    """
    try:
        bindings = await CharacterFactionBindingService.list_bindings(
            novel_id,
            character_id=character_id,
            faction_id=faction_id,
            membership_type=membership_type,
            is_active=is_active,
        )
        return {
            "data": [
                serialize_character_faction_binding(binding) for binding in bindings
            ]
        }
    except (NotFoundError, InvalidIdError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/character/{character_id}",
    response_model=dict[str, list[CharacterFactionBindingResponseV1]],
)
async def list_bindings_by_character(
    novel_id: str,
    character_id: CharacterIdPath,
) -> dict[str, list[CharacterFactionBindingResponseV1]]:
    """列出指定 active 核心角色的全书级势力绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        character_id: 稳定角色业务 ID。

    Returns:
        该角色的公开绑定文档列表。
    """
    try:
        bindings = await CharacterFactionBindingService.list_bindings(
            novel_id,
            character_id=character_id,
        )
        return {
            "data": [
                serialize_character_faction_binding(binding) for binding in bindings
            ]
        }
    except (NotFoundError, InvalidIdError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/faction/{faction_id}",
    response_model=dict[str, list[CharacterFactionBindingResponseV1]],
)
async def list_bindings_by_faction(
    novel_id: str,
    faction_id: str = Path(
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    ),
) -> dict[str, list[CharacterFactionBindingResponseV1]]:
    """列出指定 active 核心势力的全书级角色绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        faction_id: 稳定势力业务 ID。

    Returns:
        该势力的公开绑定文档列表。
    """
    try:
        bindings = await CharacterFactionBindingService.list_bindings(
            novel_id,
            faction_id=faction_id,
        )
        return {
            "data": [
                serialize_character_faction_binding(binding) for binding in bindings
            ]
        }
    except (NotFoundError, InvalidIdError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/trash",
    response_model=dict[str, list[CharacterFactionBindingResponseV1]],
)
async def list_deleted_bindings(
    novel_id: str,
) -> dict[str, list[CharacterFactionBindingResponseV1]]:
    """列出小说角色—势力绑定回收站。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。

    Returns:
        包含已软删除绑定的 ``data`` 响应。
    """
    try:
        bindings = await CharacterFactionBindingService.list_deleted_bindings(novel_id)
        return {
            "data": [
                serialize_character_faction_binding(binding) for binding in bindings
            ]
        }
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{binding_id}",
    response_model=CharacterFactionBindingResponseV1,
)
async def update_binding(
    novel_id: str,
    binding_id: BindingIdPath,
    request: CharacterFactionBindingUpdateRequestV1,
) -> CharacterFactionBindingResponseV1:
    """更新绑定内容，角色和势力端点保持不可变。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。
        request: 内容字段与 expected_version。

    Returns:
        更新后的完整公开绑定。
    """
    try:
        binding = await CharacterFactionBindingService.update_binding(
            novel_id,
            binding_id,
            request,
        )
        return serialize_character_faction_binding(binding)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{binding_id}/active",
    response_model=CharacterFactionBindingResponseV1,
)
async def set_binding_active(
    novel_id: str,
    binding_id: BindingIdPath,
    request: CharacterFactionBindingActiveRequestV1,
) -> CharacterFactionBindingResponseV1:
    """修改绑定的用户启停意图并返回实际有效态。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。
        request: 目标状态与 expected_version。

    Returns:
        更新后的完整公开绑定。
    """
    try:
        binding = await CharacterFactionBindingService.set_binding_active(
            novel_id,
            binding_id,
            expected_version=request.expected_version,
            is_active=request.is_active,
        )
        return serialize_character_faction_binding(binding)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.put(
    "/novel/{novel_id}/{binding_id}/primary",
    response_model=CharacterFactionBindingPrimaryResponseV1,
)
async def switch_primary_binding(
    novel_id: str,
    binding_id: BindingIdPath,
    request: CharacterFactionBindingPrimaryRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CharacterFactionBindingPrimaryResponseV1:
    """把既有绑定切换为角色的唯一活动主归属。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 将成为 primary 的既有绑定业务 ID。
        request: 目标版本和被替换 primary 的精确版本映射。
        idempotency_key: 必填的切换幂等请求头。

    Returns:
        新主归属与本次停用的旧主归属列表。
    """
    try:
        result = await CharacterFactionBindingService.switch_primary_binding(
            novel_id,
            binding_id,
            request,
            idempotency_key=idempotency_key,
        )
        return CharacterFactionBindingPrimaryResponseV1(
            primary_binding=serialize_character_faction_binding(
                result["primary_binding"]
            ),
            affected_bindings=[
                serialize_character_faction_binding(binding)
                for binding in result["affected_bindings"]
            ],
        )
    except (
        GenerationDomainError,
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.delete(
    "/novel/{novel_id}/{binding_id}",
    response_model=CharacterFactionBindingResponseV1,
)
async def delete_binding(
    novel_id: str,
    binding_id: BindingIdPath,
    expected_version: int = Query(..., ge=1),
) -> CharacterFactionBindingResponseV1:
    """将角色—势力绑定软删除到回收站。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。
        expected_version: 调用方持有的乐观锁版本。

    Returns:
        软删除后的完整公开绑定。
    """
    try:
        binding = await CharacterFactionBindingService.soft_delete_binding(
            novel_id,
            binding_id,
            expected_version=expected_version,
        )
        return serialize_character_faction_binding(binding)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.post(
    "/novel/{novel_id}/{binding_id}/restore",
    response_model=CharacterFactionBindingResponseV1,
)
async def restore_binding(
    novel_id: str,
    binding_id: BindingIdPath,
    request: CharacterFactionBindingVersionRequestV1,
) -> CharacterFactionBindingResponseV1:
    """恢复回收站中的角色—势力绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。
        request: 携带 expected_version 的恢复请求。

    Returns:
        恢复后的完整公开绑定。
    """
    try:
        binding = await CharacterFactionBindingService.restore_binding(
            novel_id,
            binding_id,
            expected_version=request.expected_version,
        )
        return serialize_character_faction_binding(binding)
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.delete(
    "/novel/{novel_id}/{binding_id}/hard",
    response_model=CharacterFactionBindingHardDeleteResponseV1,
)
async def hard_delete_binding(
    novel_id: str,
    binding_id: BindingIdPath,
    expected_version: int = Query(..., ge=1),
) -> CharacterFactionBindingHardDeleteResponseV1:
    """物理删除回收站中的角色—势力绑定。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。
        expected_version: 调用方持有的乐观锁版本。

    Returns:
        包含删除结果和稳定绑定 ID 的响应。
    """
    try:
        deleted = await CharacterFactionBindingService.hard_delete_binding(
            novel_id,
            binding_id,
            expected_version=expected_version,
        )
        return CharacterFactionBindingHardDeleteResponseV1(
            deleted=deleted,
            binding_id=binding_id,
        )
    except (
        NotFoundError,
        DuplicateKeyError,
        InvalidIdError,
        TypeError,
        ValueError,
    ) as exc:
        raise _translate_domain_error(exc) from exc


@router.get(
    "/novel/{novel_id}/{binding_id}",
    response_model=CharacterFactionBindingResponseV1,
)
async def get_binding(
    novel_id: str,
    binding_id: BindingIdPath,
) -> CharacterFactionBindingResponseV1:
    """获取一条全书级角色—势力绑定详情。

    Args:
        novel_id: 小说 MongoDB ObjectId 字符串。
        binding_id: 稳定绑定业务 ID。

    Returns:
        公开绑定文档。
    """
    try:
        binding = await CharacterFactionBindingService.get_binding(novel_id, binding_id)
        return serialize_character_faction_binding(binding)
    except (NotFoundError, InvalidIdError, TypeError, ValueError) as exc:
        raise _translate_domain_error(exc) from exc


__all__ = [
    "CharacterFactionBindingActiveRequestV1",
    "CharacterFactionBindingCreateRequestV1",
    "CharacterFactionBindingHardDeleteResponseV1",
    "CharacterFactionBindingPrimaryRequestV1",
    "CharacterFactionBindingPrimaryResponseV1",
    "CharacterFactionBindingResponseV1",
    "CharacterFactionBindingUpdateRequestV1",
    "CharacterFactionBindingVersionRequestV1",
    "router",
    "serialize_character_faction_binding",
]
