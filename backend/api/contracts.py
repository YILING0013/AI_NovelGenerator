"""API 层共享的严格 DTO 与稳定标识符契约。"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


OBJECT_ID_PATTERN = r"^[0-9a-fA-F]{24}$"
LOCAL_CANDIDATE_REF_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+){1,5}$"

_BUSINESS_ID_PATTERNS: dict[str, re.Pattern[str]] = {
    "faction": re.compile(r"^fac_[0-9]{6,}$"),
    "faction_relation": re.compile(r"^fr_[0-9]{6,}$"),
    "character": re.compile(r"^char_[0-9]{6,}$"),
    "character_relation": re.compile(r"^cr_[0-9]{6,}$"),
    "character_faction_binding": re.compile(r"^cfb_[0-9]{6,}$"),
    "world_rule": re.compile(r"^rule_[0-9]{6,}$"),
    "location": re.compile(r"^loc_[0-9]{6,}$"),
    "item": re.compile(r"^item_[0-9]{6,}$"),
    "foreshadowing": re.compile(r"^fo_[0-9]{6,}$"),
}


class FactKind(str, Enum):
    """创作链路中的事实与非事实分类。"""

    FORMAL_DOMAIN_FACT = "formal_domain_fact"
    FORMAL_STRUCTURE_PLAN = "formal_structure_plan"
    IMMUTABLE_RECORD = "immutable_record"
    IMMUTABLE_CONTENT_VERSION = "immutable_content_version"
    AI_CANDIDATE = "ai_candidate"
    STREAM_FRAGMENT = "stream_fragment"
    REBUILDABLE_PROJECTION = "rebuildable_projection"


FORMAL_FACT_KINDS: frozenset[FactKind] = frozenset(
    {
        FactKind.FORMAL_DOMAIN_FACT,
        FactKind.FORMAL_STRUCTURE_PLAN,
        FactKind.IMMUTABLE_RECORD,
        FactKind.IMMUTABLE_CONTENT_VERSION,
    }
)


ObjectIdString: TypeAlias = Annotated[
    str,
    Field(pattern=OBJECT_ID_PATTERN, min_length=24, max_length=24),
]
BusinessEntityType: TypeAlias = Literal[
    "faction",
    "faction_relation",
    "character",
    "character_relation",
    "character_faction_binding",
    "world_rule",
    "location",
    "item",
    "foreshadowing",
]


class StrictRequestModel(BaseModel):
    """禁止额外字段并清理字符串空白的请求 DTO 基类。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class StrictResponseModel(BaseModel):
    """禁止响应层静默携带内部字段的 DTO 基类。"""

    model_config = ConfigDict(extra="forbid", strict=True)


def is_formal_fact(kind: FactKind) -> bool:
    """判断指定分类是否可以作为后续创作的正式事实输入。

    Args:
        kind: 待判断的事实分类。

    Returns:
        属于正式事实、正式计划或正式不可变记录时返回 True。
    """
    return kind in FORMAL_FACT_KINDS


def is_object_id(value: str) -> bool:
    """判断字符串是否符合公开 ObjectId 十六进制格式。

    Args:
        value: 待检查的字符串。

    Returns:
        值为 24 位十六进制字符串时返回 True；正式响应仍由 BSON 序列化为小写。
    """
    return bool(re.fullmatch(OBJECT_ID_PATTERN, value or ""))


def is_business_id(entity_type: BusinessEntityType, value: str) -> bool:
    """按领域类型验证正式业务 ID，不接受名称或候选局部引用。

    Args:
        entity_type: 已登记的业务实体类型。
        value: 待检查的正式业务 ID。

    Returns:
        ID 前缀和至少六位序号均符合约定时返回 True。
    """
    return bool(_BUSINESS_ID_PATTERNS[entity_type].fullmatch(value or ""))


def is_local_candidate_ref(value: str) -> bool:
    """判断字符串是否可作为单次 AI 结果内的局部候选引用。

    Args:
        value: 待检查的局部候选引用。

    Returns:
        值只含安全的小写分段且不冒充正式业务 ID 时返回 True。
    """
    if not re.fullmatch(LOCAL_CANDIDATE_REF_PATTERN, value or ""):
        return False
    # 候选引用与正式业务 ID 必须是互斥命名空间，防止被误持久化为外键。
    return not any(pattern.fullmatch(value) for pattern in _BUSINESS_ID_PATTERNS.values())


def validate_local_candidate_ref(value: str) -> str:
    """校验并返回候选局部引用，拒绝正式业务 ID 命名空间。

    Args:
        value: Pydantic DTO 已完成字符串类型校验的候选引用。

    Returns:
        校验通过的原局部引用。

    Raises:
        ValueError: 引用格式非法或与正式业务 ID 命名空间重叠。
    """
    if not is_local_candidate_ref(value):
        raise ValueError("候选局部引用格式不合法或与正式业务 ID 冲突")
    return value


LocalCandidateRef: TypeAlias = Annotated[
    str,
    Field(pattern=LOCAL_CANDIDATE_REF_PATTERN, min_length=3, max_length=100),
    AfterValidator(validate_local_candidate_ref),
]


__all__ = [
    "BusinessEntityType",
    "FactKind",
    "FORMAL_FACT_KINDS",
    "LOCAL_CANDIDATE_REF_PATTERN",
    "LocalCandidateRef",
    "OBJECT_ID_PATTERN",
    "ObjectIdString",
    "StrictRequestModel",
    "StrictResponseModel",
    "is_business_id",
    "is_formal_fact",
    "is_local_candidate_ref",
    "is_object_id",
    "validate_local_candidate_ref",
]
