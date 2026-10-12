"""全书级角色关系主档与直接生成预览的 Pydantic 契约。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.llm.schemas.character_pydantic import StrictSchemaModel
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


CHARACTER_RELATIONS_RESULT_SCHEMA_ID = "character.relation_generation.result"
CHARACTER_RELATIONS_RESULT_SCHEMA_VERSION = 1

_OBJECT_ID_PATTERN = r"^[0-9a-f]{24}$"
_CHARACTER_ID_PATTERN = r"^char_[0-9]{6,}$"
_RELATION_ID_PATTERN = r"^cr_[0-9]{6,}$"
_RELATION_REF_PATTERN = r"^relation_[0-9]{3}$"
_SORT_ORDER_MAX = 2_147_483_647


CharacterRelationType: TypeAlias = Literal[
    "friend",
    "romantic",
    "ally",
    "rival",
    "enemy",
    "parent_of",
    "mentor_of",
    "superior_of",
    "protector_of",
    "debtor_to",
]
SymmetricCharacterRelationType: TypeAlias = Literal[
    "friend",
    "romantic",
    "ally",
    "rival",
    "enemy",
]

SYMMETRIC_CHARACTER_RELATION_TYPES: frozenset[str] = frozenset(
    {"friend", "romantic", "ally", "rival", "enemy"}
)


def _normalize_identifier_list(value: object) -> object:
    """清理 ID 数组并按首次出现顺序去重。

    Args:
        value: Pydantic 字段收到的原始 ID 数组。

    Returns:
        清理空白、移除空项和重复项后的数组。
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
    """规范化可空的关系生成指导文本。

    Args:
        value: 原始用户指导文本。

    Returns:
        去除首尾空白后的文本、null 或原始非字符串值。
    """
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    return cleaned or None


def build_relation_semantic_key(
    source_character_id: str,
    target_character_id: str,
    relation_type: CharacterRelationType,
) -> tuple[str, str, str]:
    """构建可用于检测反向对称重复的关系语义键。

    Args:
        source_character_id: 关系源角色业务 ID。
        target_character_id: 关系目标角色业务 ID。
        relation_type: 角色关系类型。

    Returns:
        规范化源、规范化目标和关系类型组成的语义键。
    """
    if relation_type in SYMMETRIC_CHARACTER_RELATION_TYPES:
        source_character_id, target_character_id = sorted(
            (source_character_id, target_character_id)
        )
    return source_character_id, target_character_id, relation_type


class CharacterRelationCreateRequestV1(StrictSchemaModel):
    """人工创建全书级角色关系时允许写入的字段。"""

    source_character_id: str = Field(pattern=_CHARACTER_ID_PATTERN)
    target_character_id: str = Field(pattern=_CHARACTER_ID_PATTERN)
    relation_type: CharacterRelationType
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(min_length=1, max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    story_value: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=_SORT_ORDER_MAX, strict=True)

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "CharacterRelationCreateRequestV1":
        """拒绝人工创建的角色关系自引用。

        Args:
            无。

        Returns:
            校验通过后的创建请求。
        """
        if self.source_character_id == self.target_character_id:
            raise ValueError("角色关系不能指向自身")
        return self


class CharacterRelationUpdateRequestV1(StrictSchemaModel):
    """更新角色关系内容时允许写入的完整字段集合。"""

    expected_version: int = Field(ge=1, strict=True)
    relation_type: CharacterRelationType
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(min_length=1, max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    story_value: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)


class CharacterRelationDesignUpdateRequestV1(StrictSchemaModel):
    """只修改关系设计，不接收当前状态、端点或管理状态。"""

    expected_version: int = Field(ge=1, strict=True)
    relation_type: CharacterRelationType
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(min_length=1, max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    story_value: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)


class CharacterRelationActiveRequestV1(StrictSchemaModel):
    """显式变更角色关系用户启停意图的请求。"""

    expected_version: int = Field(ge=1, strict=True)
    is_active: bool


class CharacterRelationVersionRequestV1(StrictSchemaModel):
    """仅携带乐观锁版本的关系生命周期请求。"""

    expected_version: int = Field(ge=1, strict=True)


class CharacterRelationResponseV1(StrictSchemaModel):
    """角色关系主档的完整公开响应。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    relation_id: str = Field(pattern=_RELATION_ID_PATTERN)
    source_character_id: str = Field(pattern=_CHARACTER_ID_PATTERN)
    target_character_id: str = Field(pattern=_CHARACTER_ID_PATTERN)
    source_character_name: str | None = Field(default=None, min_length=1, max_length=80)
    target_character_name: str | None = Field(default=None, min_length=1, max_length=80)
    relation_type: CharacterRelationType
    current_state: str = Field(min_length=1, max_length=2000)
    core_conflict: str = Field(min_length=1, max_length=2000)
    hidden_tension: str = Field(min_length=1, max_length=2000)
    possible_change: str = Field(min_length=1, max_length=2000)
    story_value: str = Field(min_length=1, max_length=2000)
    intensity: int = Field(ge=1, le=5, strict=True)
    user_is_active: bool = True
    is_active: bool
    sort_order: int = Field(ge=0, strict=True)
    version: int = Field(ge=1, strict=True)
    is_deleted: bool
    deleted_at: datetime | None = None
    deletion_sources: list[str] = Field(default_factory=list)
    disabled_by_character_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("deletion_sources", "disabled_by_character_ids", mode="before")
    @classmethod
    def normalize_deletion_sources(cls, value: object) -> object:
        """清理关系删除来源数组。

        Args:
            value: Repository 返回的删除来源数组。

        Returns:
            去空、去重并保持原顺序的数组。
        """
        return _normalize_identifier_list(value)

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "CharacterRelationResponseV1":
        """保证持久化关系响应不包含自引用。

        Args:
            无。

        Returns:
            校验通过后的关系响应。
        """
        if self.source_character_id == self.target_character_id:
            raise ValueError("角色关系不能指向自身")
        return self


class CharacterRelationsAppendResponseV1(StrictSchemaModel):
    """角色关系批量追加的严格公开响应。"""

    character_relations: list[CharacterRelationResponseV1]
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


class CharacterRelationHardDeleteResponseV1(StrictSchemaModel):
    """角色关系硬删除公开响应。"""

    deleted: bool
    relation_id: str = Field(pattern=_RELATION_ID_PATTERN)


class CharacterRelationsGenerationInputV1(ReasoningOptions, StrictSchemaModel):
    """角色关系候选确认可重算的严格业务输入。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    character_ids: list[str] = Field(min_length=2, max_length=100)
    allow_isolated_characters: bool = False
    relation_count_limit: int | None = Field(default=None, ge=1, le=500, strict=True)
    user_guidance: str | None = Field(default=None, max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, strict=True)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @field_validator("character_ids", mode="before")
    @classmethod
    def normalize_character_ids(cls, value: object) -> object:
        """清理并去重关系生成请求中的角色业务 ID。

        Args:
            value: 原始角色 ID 数组。

        Returns:
            规范化后保持首次出现顺序的角色 ID 数组。
        """
        return _normalize_identifier_list(value)

    @field_validator("character_ids")
    @classmethod
    def validate_character_ids(cls, value: list[str]) -> list[str]:
        """校验关系生成只引用稳定角色业务 ID。

        Args:
            value: 去重后的角色 ID 数组。

        Returns:
            校验通过的原数组。
        """
        if any(re.fullmatch(_CHARACTER_ID_PATTERN, item) is None for item in value):
            raise ValueError("character_ids 只能包含 char_ 开头的稳定角色业务 ID")
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
    def validate_relation_count_limit(self) -> "CharacterRelationsGenerationInputV1":
        """校验关系数量不超过所选角色可形成的非自引用边。

        Args:
            无。

        Returns:
            校验通过后的关系生成请求。
        """
        if self.relation_count_limit is None:
            return self

        character_count = len(self.character_ids)
        maximum_edge_count = character_count * (character_count - 1)
        if self.relation_count_limit > maximum_edge_count:
            raise ValueError("relation_count_limit 不能超过所选角色可形成的有向边数量")

        minimum_cover_count = (character_count + 1) // 2
        if (
            not self.allow_isolated_characters
            and self.relation_count_limit < minimum_cover_count
        ):
            raise ValueError("relation_count_limit 不足以覆盖全部所选角色")
        return self


class CharacterRelationsGenerateRequestV1(CharacterRelationsGenerationInputV1):
    """直接生成全书级角色关系预览的请求。"""

    use_stream: bool = True


class CharacterRelationCandidateV1(StrictSchemaModel):
    """模型输出或用户编辑后的单条角色关系候选。"""

    relation_ref: str = Field(
        pattern=_RELATION_REF_PATTERN,
        description="仅在本次候选中使用的稳定引用，如 relation_001。",
    )
    source_character_id: str = Field(
        pattern=_CHARACTER_ID_PATTERN,
        description="关系源角色业务 ID，必须来自本次输入角色。",
    )
    target_character_id: str = Field(
        pattern=_CHARACTER_ID_PATTERN,
        description="关系目标角色业务 ID，必须来自本次输入角色。",
    )
    relation_type: CharacterRelationType = Field(description="关系类型。")
    current_state: str = Field(
        min_length=1,
        max_length=2000,
        description="故事开始时双方关系的当前状态。",
    )
    core_conflict: str = Field(
        min_length=1,
        max_length=2000,
        description="关系中的核心矛盾。",
    )
    hidden_tension: str = Field(
        min_length=1,
        max_length=2000,
        description="未公开或尚未爆发的深层张力。",
    )
    possible_change: str = Field(
        min_length=1,
        max_length=2000,
        description="跨全书可能发生的关系变化。",
    )
    story_value: str = Field(
        min_length=1,
        max_length=2000,
        description="该关系推动主线的叙事价值。",
    )
    intensity: int = Field(ge=1, le=5, strict=True, description="关系强度，1 至 5。")
    # google-genai 1.69.0 无法转换布尔 const；使用必填严格布尔值并在 Pydantic 层固定为 true。
    is_active: bool = Field(
        ...,
        strict=True,
        description="新生成关系固定为 true。",
    )

    @field_validator("is_active")
    @classmethod
    def validate_is_active_true(cls, value: bool) -> bool:
        """强制新生成的角色关系处于活动状态。

        Args:
            value: Provider 返回的严格布尔值。

        Returns:
            值为 true 时返回原值。
        """
        if value is not True:
            raise ValueError("新生成关系的 is_active 必须为 true")
        return value

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "CharacterRelationCandidateV1":
        """拒绝模型候选中的角色自引用。

        Args:
            无。

        Returns:
            校验通过后的关系候选。
        """
        if self.source_character_id == self.target_character_id:
            raise ValueError("角色关系候选不能指向自身")
        return self


class CharacterRelationsResultSchemaV1(StrictSchemaModel):
    """Provider 返回的角色关系候选数组。"""

    relations: list[CharacterRelationCandidateV1] = Field(
        min_length=1,
        max_length=500,
        description="仅追加到当前小说的全书级角色关系候选列表。",
    )

    @model_validator(mode="after")
    def validate_unique_relations(self) -> "CharacterRelationsResultSchemaV1":
        """校验局部引用和规范化语义边唯一性。

        Args:
            无。

        Returns:
            校验通过后的关系生成结果。
        """
        relation_refs = [relation.relation_ref for relation in self.relations]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("relations 中的 relation_ref 不能重复")

        semantic_keys = [
            build_relation_semantic_key(
                relation.source_character_id,
                relation.target_character_id,
                relation.relation_type,
            )
            for relation in self.relations
        ]
        if len(semantic_keys) != len(set(semantic_keys)):
            raise ValueError("relations 中不能包含重复或反向重复的同类型语义边")
        return self


class CharacterRelationsManualAppendRequestV1(StrictSchemaModel):
    """人工批量追加角色关系的严格请求。"""

    request_type: Literal["manual"] = "manual"
    relations: list[CharacterRelationCreateRequestV1] = Field(
        min_length=1,
        max_length=500,
    )


class CharacterRelationsAIConfirmationRequestV1(StrictSchemaModel):
    """AI 角色关系候选显式确认请求。"""

    request_type: Literal["ai_confirmation"]
    candidate: CharacterRelationsResultSchemaV1
    selected_character_refs: list[str] = Field(min_length=2, max_length=100)
    selected_relation_refs: list[str] = Field(min_length=1, max_length=500)
    basis: CandidateBasisV1
    generation_input: CharacterRelationsGenerationInputV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator(
        "selected_character_refs",
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

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在类型转换前拒绝布尔值、字符串或非正版本。

        Args:
            value: 客户端提交的原始版本映射。

        Returns:
            只含正整数版本的原映射。
        """
        if not isinstance(value, dict) or any(
            not isinstance(key, str)
            or not key.strip()
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            for key, version in value.items()
        ):
            raise ValueError("expected_versions 必须使用非空资源键和正整数版本")
        return value

    @model_validator(mode="after")
    def validate_confirmation_selection(
        self,
    ) -> "CharacterRelationsAIConfirmationRequestV1":
        """校验候选选择、小说作用域和依据版本映射相互一致。

        Args:
            无。

        Returns:
            可交给领域 Service 重读正式事实的确认请求。
        """
        if self.basis.novel_id != self.generation_input.novel_id:
            raise ValueError("basis 与 generation_input 的 novel_id 不一致")
        if (
            self.basis.workflow != "create_character_relations_by_ai"
            or self.basis.step != "create_character_relations"
            or self.basis.schema_id != CHARACTER_RELATIONS_RESULT_SCHEMA_ID
            or self.basis.schema_version != CHARACTER_RELATIONS_RESULT_SCHEMA_VERSION
        ):
            raise ValueError("角色关系确认的 basis 契约不匹配")
        candidate_by_ref = {
            relation.relation_ref: relation for relation in self.candidate.relations
        }
        if any(ref not in candidate_by_ref for ref in self.selected_relation_refs):
            raise ValueError("selected_relation_refs 包含候选中不存在的引用")
        if any(
            re.fullmatch(_CHARACTER_ID_PATTERN, ref) is None
            for ref in self.selected_character_refs
        ):
            raise ValueError("selected_character_refs 必须使用正式 char_* 业务 ID")
        if set(self.selected_character_refs) != set(
            self.generation_input.character_ids
        ):
            raise ValueError("selected_character_refs 必须精确匹配生成时锁定的角色")
        selected_characters = set(self.selected_character_refs)
        for relation_ref in self.selected_relation_refs:
            relation = candidate_by_ref[relation_ref]
            if (
                relation.source_character_id not in selected_characters
                or relation.target_character_id not in selected_characters
            ):
                raise ValueError("所选关系端点超出 selected_character_refs")
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


CharacterRelationsAppendRequestV1: TypeAlias = Annotated[
    CharacterRelationsManualAppendRequestV1
    | CharacterRelationsAIConfirmationRequestV1,
    Field(discriminator="request_type"),
]

__all__ = [
    "CHARACTER_RELATIONS_RESULT_SCHEMA_ID",
    "CHARACTER_RELATIONS_RESULT_SCHEMA_VERSION",
    "CharacterRelationActiveRequestV1",
    "CharacterRelationCandidateV1",
    "CharacterRelationCreateRequestV1",
    "CharacterRelationHardDeleteResponseV1",
    "CharacterRelationResponseV1",
    "CharacterRelationsAppendResponseV1",
    "CharacterRelationType",
    "CharacterRelationUpdateRequestV1",
    "CharacterRelationVersionRequestV1",
    "CharacterRelationsAIConfirmationRequestV1",
    "CharacterRelationsAppendRequestV1",
    "CharacterRelationsGenerateRequestV1",
    "CharacterRelationsGenerationInputV1",
    "CharacterRelationsManualAppendRequestV1",
    "CharacterRelationsResultSchemaV1",
    "SYMMETRIC_CHARACTER_RELATION_TYPES",
    "SymmetricCharacterRelationType",
    "build_relation_semantic_key",
]
