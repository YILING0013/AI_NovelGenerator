"""阵营关系人工维护与正式响应的严格 Pydantic 契约。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import BeforeValidator, Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.llm.schemas.character_pydantic import (
    FACTION_BUSINESS_ID_PATTERN,
    StrictSchemaModel,
)
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


_OBJECT_ID_PATTERN = r"^[0-9a-f]{24}$"
_RELATION_ID_PATTERN = r"^fr_[0-9]{6,}$"
_RELATION_REF_PATTERN = r"^relation_[0-9]{3}$"

FACTION_RELATIONS_RESULT_SCHEMA_ID = "faction.relation_generation.result"
FACTION_RELATIONS_RESULT_SCHEMA_VERSION = 1


FactionRelationType: TypeAlias = Literal[
    "hostile",
    "allied",
    "cold_war",
    "dependent",
    "subordinate",
    "trade_partner",
    "secret_cooperation",
    "historical_enemy",
]

SYMMETRIC_FACTION_RELATION_TYPES: frozenset[str] = frozenset(
    {
        "hostile",
        "allied",
        "cold_war",
        "trade_partner",
        "secret_cooperation",
        "historical_enemy",
    }
)


def _normalize_identifier_list(value: object) -> object:
    """清理 ID 数组并按首次出现顺序去重。

    Args:
        value: Pydantic 字段收到的原始 ID 数组。

    Returns:
        去除空白、空项和重复项后的数组；非数组值保持原样。
    """
    if not isinstance(value, list):
        return value

    normalized: list[object] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            normalized.append(item)
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return normalized


def _normalize_optional_guidance(value: object) -> object:
    """规范化可空的阵营关系生成指导文本。

    Args:
        value: 原始用户指导文本。

    Returns:
        去除首尾空白后的文本、null 或原始非字符串值。
    """
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    return cleaned or None


def build_faction_relation_semantic_key(
    source_faction_id: str,
    target_faction_id: str,
    relation_type: FactionRelationType | str,
) -> tuple[str, str, str]:
    """按关系方向规则构造稳定的阵营关系语义键。

    Args:
        source_faction_id: 来源阵营业务 ID。
        target_faction_id: 目标阵营业务 ID。
        relation_type: 阵营关系类型。

    Returns:
        规范化来源、规范化目标和关系类型组成的三元组。
    """
    if relation_type in SYMMETRIC_FACTION_RELATION_TYPES:
        source_faction_id, target_faction_id = sorted(
            (source_faction_id, target_faction_id)
        )
    return source_faction_id, target_faction_id, str(relation_type)


class FactionRelationCreateRequestV1(StrictSchemaModel):
    """人工创建阵营关系时允许写入的字段。"""

    source_faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    target_faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    relation_type: FactionRelationType
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(default="", max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "FactionRelationCreateRequestV1":
        """拒绝阵营关系自引用。

        Args:
            无。

        Returns:
            校验通过后的创建请求。
        """
        if self.source_faction_id == self.target_faction_id:
            raise ValueError("阵营关系不能指向自身")
        return self


class FactionRelationUpdateRequestV1(StrictSchemaModel):
    """更新阵营关系内容时允许写入的完整字段集合。"""

    expected_version: int = Field(ge=1, strict=True)
    relation_type: FactionRelationType
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(default="", max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)


class FactionRelationActiveRequestV1(StrictSchemaModel):
    """显式变更阵营关系用户启停意图的请求。"""

    expected_version: int = Field(ge=1, strict=True)
    is_active: bool


class FactionRelationVersionRequestV1(StrictSchemaModel):
    """仅携带乐观锁版本的阵营关系生命周期请求。"""

    expected_version: int = Field(ge=1, strict=True)


class FactionRelationResponseV1(StrictSchemaModel):
    """阵营关系当前事实的完整公开响应。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    relation_id: str = Field(pattern=_RELATION_ID_PATTERN)
    source_faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    target_faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    source_faction_name: str | None = Field(default=None, min_length=1)
    target_faction_name: str | None = Field(default=None, min_length=1)
    relation_type: FactionRelationType
    current_state: str = Field(default="", max_length=2000)
    core_conflict: str = Field(default="", max_length=2000)
    hidden_tension: str = Field(default="", max_length=2000)
    possible_change: str = Field(default="", max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)
    user_is_active: bool = True
    is_active: bool
    sort_order: int = Field(default=0, ge=0, strict=True)
    version: int = Field(ge=1, strict=True)
    is_deleted: bool
    deleted_at: datetime | None = None
    deletion_sources: list[str] = Field(default_factory=list)
    disabled_by_faction_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("deletion_sources", "disabled_by_faction_ids", mode="before")
    @classmethod
    def normalize_source_lists(cls, value: object) -> object:
        """清理删除来源和自动阻断来源数组。

        Args:
            value: Repository 返回的原始数组。

        Returns:
            去空、去重并保持首次出现顺序的数组。
        """
        if not isinstance(value, list):
            return value
        normalized: list[object] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                normalized.append(item)
                continue
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "FactionRelationResponseV1":
        """保证正式响应不包含自引用关系。

        Args:
            无。

        Returns:
            校验通过后的响应。
        """
        if self.source_faction_id == self.target_faction_id:
            raise ValueError("阵营关系不能指向自身")
        return self


class FactionRelationsAppendResponseV1(StrictSchemaModel):
    """阵营关系批量追加的严格公开响应。"""

    faction_relations: list[FactionRelationResponseV1]
    relation_ref_map: dict[
        Annotated[str, Field(pattern=_RELATION_REF_PATTERN)],
        Annotated[str, Field(pattern=_RELATION_ID_PATTERN)],
    ] = Field(max_length=500)

    @field_validator("relation_ref_map", mode="before")
    @classmethod
    def validate_raw_relation_ref_map(cls, value: object) -> object:
        """在类型转换前拒绝非字符串映射和重复正式 ID。

        Args:
            value: Service 返回的候选引用到正式关系 ID 映射。

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


class FactionRelationHardDeleteResponseV1(StrictSchemaModel):
    """阵营关系硬删除公开响应。"""

    deleted: bool
    relation_id: str = Field(pattern=_RELATION_ID_PATTERN)


class FactionRelationsGenerationInputV1(ReasoningOptions, StrictSchemaModel):
    """确认阶段允许回传并重算指纹的阵营关系生成输入。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    faction_ids: list[str] = Field(min_length=2, max_length=100)
    allow_isolated_factions: bool = False
    relation_count_limit: int | None = Field(default=None, ge=1, le=500, strict=True)
    user_guidance: str | None = Field(default=None, max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, strict=True)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @field_validator("faction_ids", mode="before")
    @classmethod
    def normalize_faction_ids(cls, value: object) -> object:
        """清理并去重关系生成请求中的阵营业务 ID。

        Args:
            value: 原始阵营 ID 数组。

        Returns:
            保持首次出现顺序的规范化阵营 ID 数组。
        """
        return _normalize_identifier_list(value)

    @field_validator("faction_ids")
    @classmethod
    def validate_faction_ids(cls, value: list[str]) -> list[str]:
        """校验关系生成只引用稳定阵营业务 ID。

        Args:
            value: 去重后的阵营 ID 数组。

        Returns:
            校验通过的原数组。
        """
        if any(re.fullmatch(FACTION_BUSINESS_ID_PATTERN, item) is None for item in value):
            raise ValueError("faction_ids 只能包含 fac_ 开头的稳定阵营业务 ID")
        return value

    @field_validator("user_guidance", mode="before")
    @classmethod
    def normalize_user_guidance(cls, value: object) -> object:
        """清理指导文本并把纯空白转换为 null。

        Args:
            value: 原始用户指导文本。

        Returns:
            规范化后的用户指导文本。
        """
        return _normalize_optional_guidance(value)

    @model_validator(mode="after")
    def validate_relation_count_limit(self) -> "FactionRelationsGenerationInputV1":
        """校验关系上限可由所选阵营形成且可满足覆盖要求。

        Args:
            无。

        Returns:
            校验通过后的阵营关系生成请求。
        """
        if self.relation_count_limit is None:
            return self

        faction_count = len(self.faction_ids)
        maximum_edge_count = faction_count * (faction_count - 1)
        if self.relation_count_limit > maximum_edge_count:
            raise ValueError("relation_count_limit 不能超过所选阵营可形成的有向边数量")

        minimum_cover_count = (faction_count + 1) // 2
        if (
            not self.allow_isolated_factions
            and self.relation_count_limit < minimum_cover_count
        ):
            raise ValueError("relation_count_limit 不足以覆盖全部所选阵营")
        return self


class FactionRelationsGenerateRequestV1(FactionRelationsGenerationInputV1):
    """阵营关系生成 HTTP 请求，在业务输入外增加传输模式。"""

    use_stream: bool = True


class FactionRelationCandidateV1(StrictSchemaModel):
    """模型输出或用户编辑后的单条阵营关系候选。"""

    relation_ref: str = Field(
        pattern=_RELATION_REF_PATTERN,
        description="仅在本次候选中使用的稳定引用，例如 relation_001。",
    )
    source_faction_id: str = Field(
        pattern=FACTION_BUSINESS_ID_PATTERN,
        description="关系来源阵营业务 ID，必须来自本次输入阵营。",
    )
    target_faction_id: str = Field(
        pattern=FACTION_BUSINESS_ID_PATTERN,
        description="关系目标阵营业务 ID，必须来自本次输入阵营。",
    )
    relation_type: FactionRelationType = Field(description="阵营关系类型。")
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)
    is_active: bool = Field(
        ...,
        strict=True,
        description="新生成关系固定为 true。",
    )

    @field_validator("is_active")
    @classmethod
    def validate_is_active_true(cls, value: bool) -> bool:
        """强制新生成的阵营关系处于活动状态。

        Args:
            value: Provider 返回的严格布尔值。

        Returns:
            值为 true 时返回原值。
        """
        if value is not True:
            raise ValueError("新生成阵营关系的 is_active 必须为 true")
        return value

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "FactionRelationCandidateV1":
        """拒绝模型候选中的阵营自引用。

        Args:
            无。

        Returns:
            校验通过后的阵营关系候选。
        """
        if self.source_faction_id == self.target_faction_id:
            raise ValueError("阵营关系候选不能指向自身")
        return self


class FactionRelationsResultSchemaV1(StrictSchemaModel):
    """Provider 返回的阵营关系候选数组。"""

    relations: list[FactionRelationCandidateV1] = Field(
        min_length=1,
        max_length=500,
        description="仅追加到当前小说的阵营关系候选列表。",
    )

    @model_validator(mode="after")
    def validate_unique_relations(self) -> "FactionRelationsResultSchemaV1":
        """校验局部引用与规范化语义边唯一性。

        Args:
            无。

        Returns:
            校验通过后的阵营关系生成结果。
        """
        relation_refs = [relation.relation_ref for relation in self.relations]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("relations 中的 relation_ref 不能重复")

        semantic_keys = [
            build_faction_relation_semantic_key(
                relation.source_faction_id,
                relation.target_faction_id,
                relation.relation_type,
            )
            for relation in self.relations
        ]
        if len(semantic_keys) != len(set(semantic_keys)):
            raise ValueError("relations 中不能包含重复或反向重复的同类型语义边")
        return self


class FactionRelationsManualAppendRequestV1(StrictSchemaModel):
    """人工批量追加阵营关系的严格请求。"""

    request_type: Literal["manual"] = "manual"
    relations: list[FactionRelationCreateRequestV1] = Field(
        min_length=1,
        max_length=500,
    )


class FactionRelationsAIConfirmationRequestV1(StrictSchemaModel):
    """AI 阵营关系候选显式确认请求。"""

    request_type: Literal["ai_confirmation"]
    candidate: FactionRelationsResultSchemaV1
    selected_faction_refs: list[str] = Field(min_length=2, max_length=100)
    selected_relation_refs: list[str] = Field(min_length=1, max_length=500)
    basis: CandidateBasisV1
    generation_input: FactionRelationsGenerationInputV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator(
        "selected_faction_refs",
        "selected_relation_refs",
        mode="before",
    )
    @classmethod
    def normalize_selected_refs(cls, value: object) -> object:
        """清理并去重客户端显式选择的本地引用。

        Args:
            value: 原始选择数组。

        Returns:
            保持首次出现顺序的非空引用数组。
        """
        return _normalize_identifier_list(value)

    @model_validator(mode="after")
    def validate_confirmation_selection(
        self,
    ) -> "FactionRelationsAIConfirmationRequestV1":
        """校验候选选择、小说作用域和依据版本映射相互一致。

        Args:
            无。

        Returns:
            可交给领域 Service 重读正式事实的确认请求。
        """
        if self.basis.novel_id != self.generation_input.novel_id:
            raise ValueError("basis 与 generation_input 的 novel_id 不一致")
        if (
            self.basis.workflow != "create_faction_relations_by_ai"
            or self.basis.step != "create_faction_relations"
            or self.basis.schema_id != FACTION_RELATIONS_RESULT_SCHEMA_ID
            or self.basis.schema_version != FACTION_RELATIONS_RESULT_SCHEMA_VERSION
        ):
            raise ValueError("阵营关系确认的 workflow/step/schema 契约不匹配")
        candidate_by_ref = {
            relation.relation_ref: relation for relation in self.candidate.relations
        }
        if any(ref not in candidate_by_ref for ref in self.selected_relation_refs):
            raise ValueError("selected_relation_refs 包含候选中不存在的引用")
        if any(
            re.fullmatch(FACTION_BUSINESS_ID_PATTERN, ref) is None
            for ref in self.selected_faction_refs
        ):
            raise ValueError("selected_faction_refs 必须使用正式 fac_* 业务 ID")
        if set(self.selected_faction_refs) != set(self.generation_input.faction_ids):
            raise ValueError("selected_faction_refs 必须精确匹配生成时锁定的势力")
        selected_factions = set(self.selected_faction_refs)
        for relation_ref in self.selected_relation_refs:
            relation = candidate_by_ref[relation_ref]
            if (
                relation.source_faction_id not in selected_factions
                or relation.target_faction_id not in selected_factions
            ):
                raise ValueError("所选关系端点超出 selected_faction_refs")
        expected_from_basis = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected_from_basis:
            raise ValueError("expected_versions 必须精确匹配 basis.source_refs")
        if any(
            isinstance(version, bool) or not isinstance(version, int) or version < 1
            for version in self.expected_versions.values()
        ):
            raise ValueError("expected_versions 必须使用正整数版本")
        return self


def _default_manual_request_type(value: object) -> object:
    """为未显式携带判别字段的既有人工批量请求补上 manual。"""
    if isinstance(value, Mapping) and "request_type" not in value:
        return {**value, "request_type": "manual"}
    return value


_FactionRelationsDiscriminatedAppendRequestV1: TypeAlias = Annotated[
    FactionRelationsManualAppendRequestV1
    | FactionRelationsAIConfirmationRequestV1,
    Field(discriminator="request_type"),
]
FactionRelationsAppendRequestV1: TypeAlias = Annotated[
    _FactionRelationsDiscriminatedAppendRequestV1,
    BeforeValidator(_default_manual_request_type),
]


__all__ = [
    "FACTION_RELATIONS_RESULT_SCHEMA_ID",
    "FACTION_RELATIONS_RESULT_SCHEMA_VERSION",
    "FactionRelationActiveRequestV1",
    "FactionRelationCandidateV1",
    "FactionRelationCreateRequestV1",
    "FactionRelationHardDeleteResponseV1",
    "FactionRelationResponseV1",
    "FactionRelationsAppendResponseV1",
    "FactionRelationType",
    "FactionRelationUpdateRequestV1",
    "FactionRelationVersionRequestV1",
    "FactionRelationsAIConfirmationRequestV1",
    "FactionRelationsAppendRequestV1",
    "FactionRelationsGenerateRequestV1",
    "FactionRelationsGenerationInputV1",
    "FactionRelationsManualAppendRequestV1",
    "FactionRelationsResultSchemaV1",
    "SYMMETRIC_FACTION_RELATION_TYPES",
    "build_faction_relation_semantic_key",
]
