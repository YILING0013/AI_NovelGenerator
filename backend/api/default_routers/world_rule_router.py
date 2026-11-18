"""正式世界规则 HTTP Router 与严格 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Header, Path, Query
from pymongo.errors import PyMongoError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.error_protocol import api_http_exception
from backend.db.errors import TransactionNotSupportedError
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesConfirmV1
from backend.services.novel.world_rule_service import WorldRuleService


router = APIRouter(prefix="/api/world-rules", tags=["world-rules"])

RULE_ID_PATTERN = r"^rule_[0-9]{6,}$"
SCOPE_ENTITY_ID_PATTERN = (
    rf"(?:{FACTION_BUSINESS_ID_PATTERN}|^char_[0-9]{{6,}}$|^loc_[0-9]{{6,}}$)"
)
RuleIdPath = Annotated[str, Path(pattern=RULE_ID_PATTERN)]
CandidateRuleRef = Annotated[str, Field(pattern=r"^rule_candidate_[0-9]+$")]
FormalRuleId = Annotated[str, Field(pattern=RULE_ID_PATTERN)]
ScopeEntityId = Annotated[str, Field(pattern=SCOPE_ENTITY_ID_PATTERN)]
ShortString = Annotated[str, Field(min_length=1)]
CostString = Annotated[str, Field(min_length=1, max_length=500)]


class WorldRuleExceptionV1(BaseModel):
    "Một điều kiện ngoại lệ và kết quả khi áp dụng."

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    condition: str = Field(min_length=1, max_length=500)
    effect: str = Field(min_length=1, max_length=500)


class WorldRuleCreateV1(BaseModel):
    "Yêu cầu nghiêm ngặt tạo thủ công quy tắc thế giới chính thức."

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=2000)
    scope_type: Literal["global", "faction", "character", "location"] = "global"
    scope_entity_ids: list[ScopeEntityId] = Field(default_factory=list, max_length=100)
    enforcement: str = Field(default="", max_length=1000)
    exceptions: list[WorldRuleExceptionV1] = Field(default_factory=list, max_length=20)
    costs_and_consequences: list[CostString] = Field(default_factory=list, max_length=20)
    priority: int = Field(default=0, ge=0, le=100, strict=True)
    status: Literal["draft", "active", "retired"] = "draft"
    tags: list[ShortString] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_scope_combination(self) -> "WorldRuleCreateV1":
        """拒绝 global 带引用及实体作用域无引用的组合。

        Args:
            self: 已完成字段级校验的创建请求。

        Returns:
            作用域组合有效的原创建请求。
        """
        if self.scope_type == "global" and self.scope_entity_ids:
            raise ValueError("Phạm vi global không được mang theo ID thực thể")
        if self.scope_type != "global" and not self.scope_entity_ids:
            raise ValueError(f"{self.scope_type} phạm vi cần ít nhất một ID thực thể")
        if len(self.scope_entity_ids) != len(set(self.scope_entity_ids)):
            raise ValueError("scope_entity_ids không được chứa ID trùng lặp")
        return self


class WorldRuleUpdateV1(BaseModel):
    "Yêu cầu nghiêm ngặt cập nhật quy tắc thế giới chính thức bằng phiên bản công khai."

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    expected_version: int = Field(ge=1, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    statement: str | None = Field(default=None, min_length=1, max_length=2000)
    scope_type: Literal["global", "faction", "character", "location"] | None = None
    scope_entity_ids: list[ScopeEntityId] | None = Field(default=None, max_length=100)
    enforcement: str | None = Field(default=None, max_length=1000)
    exceptions: list[WorldRuleExceptionV1] | None = Field(default=None, max_length=20)
    costs_and_consequences: list[CostString] | None = Field(default=None, max_length=20)
    priority: int | None = Field(default=None, ge=0, le=100, strict=True)
    status: Literal["draft", "active", "retired"] | None = None
    tags: list[ShortString] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def validate_update_fields(self) -> "WorldRuleUpdateV1":
        """拒绝空更新、显式 null 和明显矛盾的完整作用域组合。

        Args:
            self: 已完成字段级校验的更新请求。

        Returns:
            至少包含一个合法业务字段的原更新请求。
        """
        content_fields = self.model_fields_set - {"expected_version"}
        if not content_fields:
            raise ValueError("Cập nhật quy tắc thế giới cần ít nhất một trường có thể sửa")
        for field in content_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} không được đặt tường minh thành null")
        if "scope_entity_ids" in content_fields:
            ids = self.scope_entity_ids or []
            if len(ids) != len(set(ids)):
                raise ValueError("scope_entity_ids không được chứa ID trùng lặp")
        if {"scope_type", "scope_entity_ids"}.issubset(content_fields):
            if self.scope_type == "global" and self.scope_entity_ids:
                raise ValueError("Phạm vi global không được mang theo ID thực thể")
            if self.scope_type != "global" and not self.scope_entity_ids:
                raise ValueError(f"{self.scope_type} phạm vi cần ít nhất một ID thực thể")
        return self


class WorldRuleReadV1(BaseModel):
    "Phản hồi công khai nghiêm ngặt của quy tắc thế giới chính thức."

    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=2000)
    scope_type: Literal["global", "faction", "character", "location"]
    scope_entity_ids: list[ScopeEntityId] = Field(max_length=100)
    enforcement: str = Field(max_length=1000)
    exceptions: list[WorldRuleExceptionV1] = Field(max_length=20)
    costs_and_consequences: list[CostString] = Field(max_length=20)
    priority: int = Field(ge=0, le=100, strict=True)
    status: Literal["draft", "active", "retired"]
    tags: list[ShortString] = Field(max_length=20)
    order_index: int = Field(ge=1, strict=True)
    version: int = Field(ge=1, strict=True)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorldRuleReorderItemV1(BaseModel):
    "Một mục CAS của đợt sắp xếp lại đầy đủ trong cùng phân loại."

    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    order_index: int = Field(ge=1, strict=True)
    expected_version: int = Field(ge=1, strict=True)


class WorldRuleReorderRequestV1(BaseModel):
    "Yêu cầu sắp xếp lại đầy đủ các quy tắc cùng phân loại."

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[WorldRuleReorderItemV1] = Field(min_length=1)


class WorldRuleRestoreRequestV1(BaseModel):
    "Yêu cầu CAS khôi phục quy tắc trong thùng rác."

    model_config = ConfigDict(extra="forbid", strict=True)

    expected_version: int = Field(ge=1, strict=True)


class WorldRuleReferenceCountsV1(BaseModel):
    "Thống kê các tham chiếu chính thức được bảo vệ trước khi xóa vĩnh viễn quy tắc."

    model_config = ConfigDict(extra="forbid", strict=True)

    locations: int = Field(ge=0, strict=True)
    arcs: int = Field(ge=0, strict=True)
    scenes: int = Field(ge=0, strict=True)
    foreshadowings: int = Field(ge=0, strict=True)
    total: int = Field(ge=0, strict=True)


class WorldRuleHardDeleteResponseV1(BaseModel):
    "Kết quả xoá vĩnh viễn quy tắc thế giới."

    model_config = ConfigDict(extra="forbid", strict=True)

    message: Literal["Hard deleted successfully"]
    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    references: WorldRuleReferenceCountsV1


class WorldRuleContextDiagnosticV1(BaseModel):
    "Chẩn đoán chỉ đọc về các quy tắc đang hoạt động bị loại ra vì tham chiếu thực thể không dùng được."

    model_config = ConfigDict(extra="forbid", strict=True)

    rule_id: str = Field(pattern=RULE_ID_PATTERN)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    message: str = Field(min_length=1, max_length=2000)
    scope_type: str = Field(min_length=1, max_length=40)
    scope_entity_ids: list[str] = Field(max_length=100)


class WorldRuleContextV1(BaseModel):
    "Bản chiếu chỉ đọc theo từng nguồn của tóm tắt thế giới quan và các quy tắc chính thức đang khả dụng."

    model_config = ConfigDict(extra="forbid", strict=True)

    worldview_summary: str
    active_rules: list[WorldRuleReadV1]
    diagnostics: list[WorldRuleContextDiagnosticV1]


class CoreWorldRulesConfirmResponseV1(BaseModel):
    "Ánh xạ chính thức cùng các quy tắc đầy đủ sau khi xác nhận hàng loạt quy tắc thế giới cốt lõi."

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_ref_map: dict[CandidateRuleRef, FormalRuleId]
    world_rules: list[WorldRuleReadV1] = Field(min_length=1, max_length=20)


def _serialize_world_rule(rule: dict) -> WorldRuleReadV1:
    """过滤 MongoDB 与领域内部字段并生成严格公开规则。

    Args:
        rule: Repository 或 Service 返回的完整 BSON 文档。

    Returns:
        不含 ``_id``、规范名和幂等摘要的公开 DTO。
    """
    public_fields = set(WorldRuleReadV1.model_fields)
    payload = {field: value for field, value in rule.items() if field in public_fields}
    if "novel_id" in payload:
        payload["novel_id"] = str(payload["novel_id"])
    return WorldRuleReadV1.model_validate(payload)


def _serialize_world_rules(rules: list[dict]) -> list[WorldRuleReadV1]:
    """批量序列化正式世界规则列表。"""
    return [_serialize_world_rule(rule) for rule in rules]


def _raise_world_rule_database_error(exc: Exception) -> NoReturn:
    """把正式世界规则边界的数据库故障统一转换为 503。

    Args:
        exc: PyMongo 或事务能力检查抛出的数据库异常。

    Returns:
        不返回；始终抛出遵循公共协议的 HTTPException。
    """
    raise api_http_exception(
        status_code=503,
        code="DATABASE_UNAVAILABLE",
        message="Cơ sở dữ liệu quy tắc thế giới tạm thời không khả dụng, vui lòng thử lại sau",
    ) from exc


@router.post("/novel/{novel_id}", response_model=WorldRuleReadV1)
async def create_world_rule(
    novel_id: str,
    req: WorldRuleCreateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> WorldRuleReadV1:
    """幂等创建小说内一条正式世界规则。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 已通过严格 DTO 校验的规则内容。
        idempotency_key: 必填的人工创建幂等键。

    Returns:
        新建或同键重放的完整公开规则。
    """
    try:
        rule = await WorldRuleService.create_world_rule(
            novel_id,
            req.model_dump(mode="json"),
            idempotency_key=idempotency_key,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rule(rule)


@router.get("/novel/{novel_id}", response_model=list[WorldRuleReadV1])
async def list_world_rules(
    novel_id: str,
    status: Literal["draft", "active", "retired"] | None = None,
    category: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    scope_type: Literal["global", "faction", "character", "location"] | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> list[WorldRuleReadV1]:
    """按状态、分类、作用域和搜索词读取正式规则。

    Args:
        novel_id: 小说 ObjectId 字符串。
        status: 可选规则状态。
        category: 可选精确分类。
        scope_type: 可选作用域类型。
        q: 可选搜索词。

    Returns:
        符合筛选条件的严格公开规则列表。
    """
    try:
        rules = await WorldRuleService.list_world_rules(
            novel_id,
            status=status,
            category=category,
            scope_type=scope_type,
            q=q,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rules(rules)


@router.get("/novel/{novel_id}/trash", response_model=list[WorldRuleReadV1])
async def list_deleted_world_rules(
    novel_id: str,
    category: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
) -> list[WorldRuleReadV1]:
    """读取小说规则回收站，可按分类筛选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        category: 可选精确分类。

    Returns:
        回收站中的严格公开规则列表。
    """
    try:
        rules = await WorldRuleService.list_deleted_world_rules(
            novel_id,
            category=category,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rules(rules)


@router.get("/novel/{novel_id}/context", response_model=WorldRuleContextV1)
async def get_world_rule_context(novel_id: str) -> WorldRuleContextV1:
    """联合读取摘要、可用活动规则与不可用引用诊断。

    Args:
        novel_id: 小说 ObjectId 字符串。

    Returns:
        摘要与正式规则保持分来源的只读投影。
    """
    try:
        result = await WorldRuleService.get_world_rule_context(novel_id)
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return WorldRuleContextV1(
        worldview_summary=result["worldview_summary"],
        active_rules=_serialize_world_rules(result["active_rules"]),
        diagnostics=[
            WorldRuleContextDiagnosticV1.model_validate(item)
            for item in result["diagnostics"]
        ],
    )


@router.post(
    "/novel/{novel_id}/bulk-core",
    response_model=CoreWorldRulesConfirmResponseV1,
)
async def bulk_create_core_world_rules(
    novel_id: str,
    req: CoreWorldRulesConfirmV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CoreWorldRulesConfirmResponseV1:
    """幂等确认编辑后的核心世界规则候选。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 候选、不透明 basis 与精确来源版本。
        idempotency_key: 批量确认必填的幂等键。

    Returns:
        完整 candidate_ref 到 rule_id 映射及正式规则。
    """
    try:
        result = await WorldRuleService.bulk_create_core_world_rules(
            novel_id,
            req,
            idempotency_key=idempotency_key,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return CoreWorldRulesConfirmResponseV1(
        candidate_ref_map=result["candidate_ref_map"],
        world_rules=_serialize_world_rules(result["world_rules"]),
    )


@router.patch("/novel/{novel_id}/reorder", response_model=list[WorldRuleReadV1])
async def reorder_world_rules(
    novel_id: str,
    req: WorldRuleReorderRequestV1,
) -> list[WorldRuleReadV1]:
    """提交完整同分类活动兄弟集合并执行 1-based 重排。

    Args:
        novel_id: 小说 ObjectId 字符串。
        req: 完整同分类规则及逐项版本。

    Returns:
        按新顺序排列的完整公开规则。
    """
    try:
        rules = await WorldRuleService.reorder_world_rules(
            novel_id,
            [item.model_dump(mode="json") for item in req.items],
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rules(rules)


@router.get("/novel/{novel_id}/{rule_id}", response_model=WorldRuleReadV1)
async def get_world_rule(
    novel_id: str,
    rule_id: RuleIdPath,
) -> WorldRuleReadV1:
    """读取小说内一条未删除世界规则。

    Args:
        novel_id: 小说 ObjectId 字符串。
        rule_id: 稳定规则业务 ID。

    Returns:
        匹配的完整公开规则。
    """
    try:
        rule = await WorldRuleService.get_world_rule(novel_id, rule_id)
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rule(rule)


@router.put("/novel/{novel_id}/{rule_id}", response_model=WorldRuleReadV1)
async def update_world_rule(
    novel_id: str,
    rule_id: RuleIdPath,
    req: WorldRuleUpdateV1,
) -> WorldRuleReadV1:
    """使用 expected_version 更新一条正式世界规则。

    Args:
        novel_id: 小说 ObjectId 字符串。
        rule_id: 稳定规则业务 ID。
        req: 含 expected_version 的更新白名单字段。

    Returns:
        更新并递增版本后的完整公开规则。
    """
    try:
        rule = await WorldRuleService.update_world_rule(
            novel_id,
            rule_id,
            req.model_dump(mode="json", exclude_unset=True),
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rule(rule)


@router.delete("/novel/{novel_id}/{rule_id}", response_model=WorldRuleReadV1)
async def soft_delete_world_rule(
    novel_id: str,
    rule_id: RuleIdPath,
    expected_version: int = Query(..., ge=1),
) -> WorldRuleReadV1:
    """使用 expected_version 软删除规则并收紧分类顺序。

    Args:
        novel_id: 小说 ObjectId 字符串。
        rule_id: 稳定规则业务 ID。
        expected_version: 调用方持有的规则版本。

    Returns:
        已进入回收站的完整公开规则。
    """
    try:
        rule = await WorldRuleService.soft_delete_world_rule(
            novel_id,
            rule_id,
            expected_version=expected_version,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rule(rule)


@router.post("/novel/{novel_id}/{rule_id}/restore", response_model=WorldRuleReadV1)
async def restore_world_rule(
    novel_id: str,
    rule_id: RuleIdPath,
    req: WorldRuleRestoreRequestV1,
) -> WorldRuleReadV1:
    """恢复回收站规则并追加到当前分类末尾。

    Args:
        novel_id: 小说 ObjectId 字符串。
        rule_id: 稳定规则业务 ID。
        req: 含 expected_version 的恢复请求。

    Returns:
        已恢复的完整公开规则。
    """
    try:
        rule = await WorldRuleService.restore_world_rule(
            novel_id,
            rule_id,
            expected_version=req.expected_version,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return _serialize_world_rule(rule)


@router.delete(
    "/novel/{novel_id}/{rule_id}/hard",
    response_model=WorldRuleHardDeleteResponseV1,
)
async def hard_delete_world_rule(
    novel_id: str,
    rule_id: RuleIdPath,
    expected_version: int = Query(..., ge=1),
) -> WorldRuleHardDeleteResponseV1:
    """永久删除没有受保护正式引用的回收站规则。

    Args:
        novel_id: 小说 ObjectId 字符串。
        rule_id: 稳定规则业务 ID。
        expected_version: 调用方持有的回收站规则版本。

    Returns:
        被删除规则 ID 和受保护引用统计。
    """
    try:
        result = await WorldRuleService.hard_delete_world_rule(
            novel_id,
            rule_id,
            expected_version=expected_version,
        )
    except (TransactionNotSupportedError, PyMongoError) as exc:
        _raise_world_rule_database_error(exc)
    return WorldRuleHardDeleteResponseV1(
        message="Hard deleted successfully",
        rule_id=result["rule_id"],
        references=WorldRuleReferenceCountsV1.model_validate(result["references"]),
    )


__all__ = [
    "CoreWorldRulesConfirmResponseV1",
    "WorldRuleContextDiagnosticV1",
    "WorldRuleContextV1",
    "WorldRuleCreateV1",
    "WorldRuleExceptionV1",
    "WorldRuleHardDeleteResponseV1",
    "WorldRuleReadV1",
    "WorldRuleReferenceCountsV1",
    "WorldRuleReorderItemV1",
    "WorldRuleReorderRequestV1",
    "WorldRuleRestoreRequestV1",
    "WorldRuleUpdateV1",
    "router",
]
