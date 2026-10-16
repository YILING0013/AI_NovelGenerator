"""全书级角色主档与核心角色生成的 Pydantic 契约。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import math
from typing import Literal, TypeAlias

from bson import BSON
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from backend.llm.generation_options import ReasoningOptions
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


CORE_CHARACTERS_RESULT_SCHEMA_ID = "character.core_generation.result"
CORE_CHARACTERS_RESULT_SCHEMA_VERSION = 1

FACTION_BUSINESS_ID_PATTERN = r"^fac_[0-9]{6,}$"

FACTION_BUSINESS_ID_MIN_LENGTH = 5
FACTION_BUSINESS_ID_MAX_LENGTH = 100

_OBJECT_ID_PATTERN = r"^[0-9a-f]{24}$"
_CHARACTER_ID_PATTERN = r"^char_[0-9]{6,}$"
_CHARACTER_REF_PATTERN = r"^character_[0-9]{2,3}$"
_SORT_ORDER_MAX = 2_147_483_647
_EXTRA_BSON_MAX_BYTES = 1024 * 1024


CharacterRoleType: TypeAlias = Literal[
    "protagonist",
    "deuteragonist",
    "antagonist",
    "supporting",
    "minor",
]
CharacterImportanceLevel: TypeAlias = Literal[
    "core",
    "major",
    "supporting",
    "background",
]
CharacterStatus: TypeAlias = Literal["active", "inactive"]
CharacterFactionMembershipType: TypeAlias = Literal["primary", "secondary", "covert"]


class StrictSchemaModel(BaseModel):
    """禁止额外字段并统一清理字符串首尾空白的角色契约基础模型。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _normalize_text_list(value: object) -> object:
    """清理字符串数组中的空项并按原顺序去重。

    Args:
        value: Pydantic 字段收到的原始数组值。

    Returns:
        清理后的数组；非数组值交回 Pydantic 继续报告类型错误。
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
    """把可选指导文本的纯空白输入规范化为 null。

    Args:
        value: 原始指导文本。

    Returns:
        去除首尾空白后的文本、null 或原始非字符串值。
    """
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    return cleaned or None


def _validate_bson_safe_extra(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """校验角色扩展 JSON 可安全编码为受限 BSON。

    Args:
        value: 已通过 JsonValue 类型校验的扩展字段。

    Returns:
        校验通过的原字典。

    Raises:
        ValueError: 包含非法键、非有限浮点数、超出 int64 或体积过大。
    """
    stack: list[object] = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if "\x00" in key or key.startswith("$") or "." in key:
                    raise ValueError("extra 的键不能包含 NUL、点号或以 $ 开头")
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, int) and not -(2**63) <= current <= 2**63 - 1:
            raise ValueError("extra 中的整数必须位于 BSON int64 范围内")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("extra 中的浮点数必须是有限值")
    try:
        encoded_size = len(BSON.encode({"extra": value}))
    except Exception as exc:
        raise ValueError("extra 无法安全编码为 BSON") from exc
    if encoded_size > _EXTRA_BSON_MAX_BYTES:
        raise ValueError("extra 的 BSON 编码不能超过 1 MiB")
    return value


class CharacterCreateRequestV1(StrictSchemaModel):
    """人工创建全书级角色时允许写入的业务字段。"""

    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    role_type: CharacterRoleType
    importance_level: CharacterImportanceLevel
    gender: str = Field(min_length=1, max_length=80)
    age_group: str = Field(min_length=1, max_length=80)
    race: str = Field(min_length=1, max_length=80)
    identity: str = Field(min_length=1, max_length=500)
    appearance: str = Field(min_length=1, max_length=1000)
    personality: str = Field(min_length=1, max_length=1000)
    core_desire: str = Field(min_length=1, max_length=1000)
    core_fear: str = Field(min_length=1, max_length=1000)
    strengths: list[str] = Field(default_factory=list, max_length=12)
    weaknesses: list[str] = Field(default_factory=list, max_length=12)
    abilities: list[str] = Field(default_factory=list, max_length=12)
    conflict_with_mainline: str = Field(min_length=1, max_length=1000)
    relationship_with_protagonist: str = Field(min_length=1, max_length=1000)
    initial_state: str = Field(min_length=1, max_length=1000)
    growth_direction: str = Field(min_length=1, max_length=1000)
    story_function: str = Field(min_length=1, max_length=1000)
    arc_seed: str = Field(min_length=1, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    sort_order: int = Field(default=0, ge=0, le=_SORT_ORDER_MAX, strict=True)
    extra: dict[str, JsonValue] = Field(default_factory=dict)
    is_core_character: bool = Field(default=False, strict=True)

    @field_validator(
        "aliases",
        "strengths",
        "weaknesses",
        "abilities",
        "tags",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> object:
        """规范化角色创建请求中的字符串数组。

        Args:
            value: 原始数组值。

        Returns:
            去空、去重并保持原顺序的数组。
        """
        return _normalize_text_list(value)

    @field_validator("extra")
    @classmethod
    def validate_extra_bson(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """拒绝无法持久化或可能造成 Mongo 键注入的扩展 JSON。

        Args:
            value: 已解析的角色扩展字段。

        Returns:
            BSON 安全的原字典。
        """
        return _validate_bson_safe_extra(value)

    @field_validator("aliases", "strengths", "weaknesses", "abilities", "tags")
    @classmethod
    def validate_list_item_lengths(cls, value: list[str]) -> list[str]:
        """校验角色数组元素的长度上限。

        Args:
            value: 已完成去空和去重的字符串数组。

        Returns:
            校验通过的原数组。

        Raises:
            ValueError: 任一元素长度超过 80 字符时抛出。
        """
        if any(len(item) > 80 for item in value):
            raise ValueError("角色列表字段的每个元素长度必须为 1 至 80 字符")
        return value


class CharacterUpdateRequestV1(StrictSchemaModel):
    """使用乐观锁更新角色档案的可编辑业务字段。"""

    expected_version: int = Field(ge=1, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    aliases: list[str] | None = Field(default=None, max_length=10)
    role_type: CharacterRoleType | None = None
    importance_level: CharacterImportanceLevel | None = None
    gender: str | None = Field(default=None, min_length=1, max_length=80)
    age_group: str | None = Field(default=None, min_length=1, max_length=80)
    race: str | None = Field(default=None, min_length=1, max_length=80)
    identity: str | None = Field(default=None, min_length=1, max_length=500)
    appearance: str | None = Field(default=None, min_length=1, max_length=1000)
    personality: str | None = Field(default=None, min_length=1, max_length=1000)
    core_desire: str | None = Field(default=None, min_length=1, max_length=1000)
    core_fear: str | None = Field(default=None, min_length=1, max_length=1000)
    strengths: list[str] | None = Field(default=None, max_length=12)
    weaknesses: list[str] | None = Field(default=None, max_length=12)
    abilities: list[str] | None = Field(default=None, max_length=12)
    conflict_with_mainline: str | None = Field(default=None, min_length=1, max_length=1000)
    relationship_with_protagonist: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )
    initial_state: str | None = Field(default=None, min_length=1, max_length=1000)
    growth_direction: str | None = Field(default=None, min_length=1, max_length=1000)
    story_function: str | None = Field(default=None, min_length=1, max_length=1000)
    arc_seed: str | None = Field(default=None, min_length=1, max_length=1000)
    tags: list[str] | None = Field(default=None, max_length=10)
    extra: dict[str, JsonValue] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_empty_or_null_updates(cls, value: object) -> object:
        """拒绝空更新及显式 null，避免意外擦除正式角色字段。

        Args:
            value: Pydantic 收到的原始更新映射。

        Returns:
            通过结构预检的原始映射。
        """
        if not isinstance(value, Mapping):
            return value
        editable_items = {
            key: item for key, item in value.items() if key != "expected_version"
        }
        if not editable_items:
            raise ValueError("角色更新至少需要提供一个可编辑字段")
        null_fields = sorted(key for key, item in editable_items.items() if item is None)
        if null_fields:
            raise ValueError(f"角色更新字段不能为 null: {', '.join(null_fields)}")
        return value

    @field_validator(
        "aliases",
        "strengths",
        "weaknesses",
        "abilities",
        "tags",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> object:
        """规范化角色更新中的标签类数组。

        Args:
            value: 原始数组或字段缺省值。

        Returns:
            去空、去重并保持原顺序的数组。
        """
        return _normalize_text_list(value)

    @field_validator("aliases", "strengths", "weaknesses", "abilities", "tags")
    @classmethod
    def validate_list_item_lengths(cls, value: list[str] | None) -> list[str] | None:
        """校验更新请求中数组元素的长度上限。

        Args:
            value: 已规范化数组，字段未提供时为 None。

        Returns:
            校验通过的原数组或 None。
        """
        if value is not None and any(len(item) > 80 for item in value):
            raise ValueError("角色列表字段的每个元素长度必须为 1 至 80 字符")
        return value

    @field_validator("extra")
    @classmethod
    def validate_extra_bson(
        cls,
        value: dict[str, JsonValue] | None,
    ) -> dict[str, JsonValue] | None:
        """校验更新后的扩展 JSON 能安全持久化为 BSON。

        Args:
            value: 更新请求中的扩展 JSON。

        Returns:
            BSON 安全的扩展 JSON 或字段缺省值。
        """
        return None if value is None else _validate_bson_safe_extra(value)


class CharacterStatusUpdateRequestV1(StrictSchemaModel):
    """使用乐观锁切换角色可用状态。"""

    expected_version: int = Field(ge=1, strict=True)
    status: CharacterStatus


class CharacterRestoreRequestV1(StrictSchemaModel):
    """使用乐观锁恢复回收站角色。"""

    expected_version: int = Field(ge=1, strict=True)


class CharacterResponseV1(StrictSchemaModel):
    """角色主档的完整公开响应，不暴露 Mongo ``_id``。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    character_id: str = Field(pattern=_CHARACTER_ID_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=10)
    role_type: CharacterRoleType
    importance_level: CharacterImportanceLevel
    # 历史角色主档允许叙述字段为空；新建请求仍维持非空约束。
    gender: str = Field(default="", max_length=80)
    age_group: str = Field(default="", max_length=80)
    race: str = Field(default="", max_length=80)
    identity: str = Field(default="", max_length=500)
    appearance: str = Field(default="", max_length=1000)
    personality: str = Field(default="", max_length=1000)
    core_desire: str = Field(default="", max_length=1000)
    core_fear: str = Field(default="", max_length=1000)
    strengths: list[str] = Field(default_factory=list, max_length=12)
    weaknesses: list[str] = Field(default_factory=list, max_length=12)
    abilities: list[str] = Field(default_factory=list, max_length=12)
    conflict_with_mainline: str = Field(default="", max_length=1000)
    relationship_with_protagonist: str = Field(default="", max_length=1000)
    initial_state: str = Field(default="", max_length=1000)
    growth_direction: str = Field(default="", max_length=1000)
    story_function: str = Field(default="", max_length=1000)
    arc_seed: str = Field(default="", max_length=1000)
    status: CharacterStatus
    is_core_character: bool
    first_appearance_volume_id: str | None = Field(
        default=None,
        pattern=_OBJECT_ID_PATTERN,
    )
    first_appearance_chapter_id: str | None = Field(
        default=None,
        pattern=_OBJECT_ID_PATTERN,
    )
    tags: list[str] = Field(default_factory=list, max_length=10)
    sort_order: int = Field(ge=0, strict=True)
    extra: dict[str, JsonValue] = Field(default_factory=dict)
    version: int = Field(ge=1, strict=True)
    is_deleted: bool
    deleted_at: datetime | None = None
    deletion_sources: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "aliases",
        "strengths",
        "weaknesses",
        "abilities",
        "tags",
        "deletion_sources",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> object:
        """规范化角色响应中的字符串数组。

        Args:
            value: Repository 序列化后的数组值。

        Returns:
            去空、去重并保持原顺序的数组。
        """
        return _normalize_text_list(value)

    @field_validator("aliases", "strengths", "weaknesses", "abilities", "tags")
    @classmethod
    def validate_list_item_lengths(cls, value: list[str]) -> list[str]:
        """校验角色响应数组元素的长度上限。

        Args:
            value: 已规范化的字符串数组。

        Returns:
            校验通过的原数组。

        Raises:
            ValueError: 任一业务数组元素超过 80 字符时抛出。
        """
        if any(len(item) > 80 for item in value):
            raise ValueError("角色列表字段的每个元素长度必须为 1 至 80 字符")
        return value


class CoreCharactersGenerationInputV1(ReasoningOptions, StrictSchemaModel):
    """核心角色候选确认可重算的严格业务输入。"""

    novel_id: str = Field(pattern=_OBJECT_ID_PATTERN)
    character_count: int | None = Field(ge=1, le=50, strict=True)
    user_guidance: str | None = Field(default=None, max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, strict=True)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @field_validator("user_guidance", mode="before")
    @classmethod
    def normalize_user_guidance(cls, value: object) -> object:
        """清理用户指导文本并把纯空白转换为 null。

        Args:
            value: 原始用户指导文本。

        Returns:
            规范化后的用户指导文本。
        """
        return _normalize_optional_guidance(value)


class CoreCharactersGenerateRequestV1(CoreCharactersGenerationInputV1):
    """直接生成全书核心角色预览的请求。"""

    use_stream: bool = True


class CoreCharacterCandidateV1(StrictSchemaModel):
    """模型输出的单个全书核心角色候选。"""

    character_ref: str = Field(
        pattern=_CHARACTER_REF_PATTERN,
        description="仅在本次候选中使用的稳定引用，如 character_01。",
    )
    name: str = Field(min_length=1, max_length=80, description="角色正式显示名。")
    aliases: list[str] = Field(max_length=10, description="角色别名数组，可为空数组。")
    role_type: CharacterRoleType = Field(description="角色在全书叙事中的类型。")
    importance_level: CharacterImportanceLevel = Field(description="角色的重要程度。")
    gender: str = Field(min_length=1, max_length=80, description="角色性别描述。")
    age_group: str = Field(min_length=1, max_length=80, description="角色年龄阶段。")
    race: str = Field(min_length=1, max_length=80, description="角色种族或物种。")
    identity: str = Field(min_length=1, max_length=500, description="角色身份与社会位置。")
    appearance: str = Field(min_length=1, max_length=1000, description="角色外貌特征。")
    personality: str = Field(min_length=1, max_length=1000, description="角色核心性格。")
    core_desire: str = Field(min_length=1, max_length=1000, description="角色核心欲望。")
    core_fear: str = Field(min_length=1, max_length=1000, description="角色核心恐惧。")
    strengths: list[str] = Field(max_length=12, description="角色优势数组，可为空数组。")
    weaknesses: list[str] = Field(max_length=12, description="角色弱点数组，可为空数组。")
    abilities: list[str] = Field(max_length=12, description="角色能力数组，可为空数组。")
    conflict_with_mainline: str = Field(
        min_length=1,
        max_length=1000,
        description="角色与全书主线的核心冲突。",
    )
    relationship_with_protagonist: str = Field(
        min_length=1,
        max_length=1000,
        description="角色与主角的初始关系。",
    )
    initial_state: str = Field(min_length=1, max_length=1000, description="故事开始时的角色状态。")
    growth_direction: str = Field(
        min_length=1,
        max_length=1000,
        description="跨全书的成长或堕落方向。",
    )
    story_function: str = Field(
        min_length=1,
        max_length=1000,
        description="角色推动主线的叙事功能。",
    )
    arc_seed: str = Field(min_length=1, max_length=1000, description="可跨卷展开的角色弧种子。")
    tags: list[str] = Field(max_length=10, description="角色标签数组，可为空数组。")

    @field_validator(
        "aliases",
        "strengths",
        "weaknesses",
        "abilities",
        "tags",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> object:
        """规范化候选中的字符串数组。

        Args:
            value: 模型输出的原始数组。

        Returns:
            去空、去重并保持模型顺序的数组。
        """
        return _normalize_text_list(value)

    @field_validator("aliases", "strengths", "weaknesses", "abilities", "tags")
    @classmethod
    def validate_list_item_lengths(cls, value: list[str]) -> list[str]:
        """校验候选数组元素长度。

        Args:
            value: 已规范化的字符串数组。

        Returns:
            校验通过的原数组。

        Raises:
            ValueError: 任一元素不在 1 至 80 字符范围内时抛出。
        """
        if any(not 1 <= len(item) <= 80 for item in value):
            raise ValueError("角色候选列表字段的每个元素长度必须为 1 至 80 字符")
        return value


class CharacterFactionBindingCandidateV1(StrictSchemaModel):
    """核心角色候选对应的全书级势力绑定候选。"""

    character_ref: str = Field(
        pattern=_CHARACTER_REF_PATTERN,
        description="必须引用 core_characters 中恰好一个 character_ref。",
    )
    faction_id: str | None = Field(
        ...,
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
        description="核心势力业务 ID；角色无势力归属时必须为 null。",
    )
    membership_type: CharacterFactionMembershipType | None = Field(
        ...,
        description="成员关系；faction_id 非空时必填，否则必须为 null。",
    )
    role_title: str | None = Field(
        ...,
        min_length=1,
        max_length=100,
        description="角色在势力中的称谓；允许为 null。",
    )
    public_status: str | None = Field(
        ...,
        min_length=1,
        max_length=200,
        description="公开身份；faction_id 非空时必填，否则必须为 null。",
    )
    loyalty_level: int | None = Field(
        ...,
        ge=1,
        le=5,
        strict=True,
        description="忠诚度 1 至 5；faction_id 非空时必填，否则必须为 null。",
    )
    reason: str | None = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="归属原因；faction_id 非空时必填，否则必须为 null。",
    )

    @model_validator(mode="after")
    def validate_nullable_binding(self) -> "CharacterFactionBindingCandidateV1":
        """校验“无势力”全空条件和非空势力的必填字段。

        Args:
            无。

        Returns:
            校验通过后的当前绑定候选。

        Raises:
            ValueError: 势力为空时夹带绑定字段，或势力非空时缺少必填字段。
        """
        binding_values = (
            self.membership_type,
            self.role_title,
            self.public_status,
            self.loyalty_level,
            self.reason,
        )
        if self.faction_id is None:
            # 无势力是明确业务选择，不允许留下无法落库的半条绑定。
            if any(value is not None for value in binding_values):
                raise ValueError("faction_id 为空时其余绑定业务字段必须全部为 null")
            return self

        required_values = (
            self.membership_type,
            self.public_status,
            self.loyalty_level,
            self.reason,
        )
        if any(value is None for value in required_values):
            raise ValueError(
                "faction_id 非空时 membership_type、public_status、loyalty_level 和 reason 必填"
            )
        return self


class CoreCharactersResultSchemaV1(StrictSchemaModel):
    """全书核心角色与势力绑定候选的完整模型输出。"""

    core_characters: list[CoreCharacterCandidateV1] = Field(
        min_length=1,
        max_length=50,
        description="全书级核心角色候选列表。",
    )
    binding_candidates: list[CharacterFactionBindingCandidateV1] = Field(
        min_length=1,
        max_length=50,
        description="与核心角色候选一一对应的势力绑定决策列表。",
    )

    @model_validator(mode="after")
    def validate_unique_and_complete_references(self) -> "CoreCharactersResultSchemaV1":
        """校验候选引用、名称唯一性和绑定一一覆盖。

        Args:
            无。

        Returns:
            校验通过后的完整核心角色结果。

        Raises:
            ValueError: 引用或名称重复，或绑定未一一覆盖角色候选。
        """
        character_refs = [candidate.character_ref for candidate in self.core_characters]
        character_names = [candidate.name for candidate in self.core_characters]
        binding_refs = [candidate.character_ref for candidate in self.binding_candidates]

        if len(character_refs) != len(set(character_refs)):
            raise ValueError("core_characters 中的 character_ref 不能重复")
        if len(character_names) != len(set(character_names)):
            raise ValueError("core_characters 中的角色名称不能重复")
        if len(binding_refs) != len(set(binding_refs)):
            raise ValueError("binding_candidates 中的 character_ref 不能重复")

        # 两侧集合完全相等且各自唯一，才能保证每名角色恰好拥有一条绑定决策。
        if set(character_refs) != set(binding_refs):
            raise ValueError("binding_candidates 必须按 character_ref 一一完整覆盖角色候选")
        return self


class CoreCharactersAIConfirmationRequestV1(StrictSchemaModel):
    """核心角色及可选势力绑定候选的严格确认请求。"""

    request_type: Literal["ai_confirmation"]
    candidate: CoreCharactersResultSchemaV1
    selected_character_refs: list[str] = Field(min_length=1, max_length=50)
    basis: CandidateBasisV1
    generation_input: CoreCharactersGenerationInputV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator("selected_character_refs", mode="before")
    @classmethod
    def normalize_selected_refs(cls, value: object) -> object:
        """清理并按首次出现顺序去重所选角色局部引用。

        Args:
            value: 浏览器提交的原始选择数组。

        Returns:
            去空、去重且保持原顺序的引用数组。
        """
        return _normalize_text_list(value)

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在 Pydantic 类型转换前拒绝布尔值、字符串或非正版本。

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
    ) -> "CoreCharactersAIConfirmationRequestV1":
        """校验选择、候选依据和精确版本映射。

        Args:
            无。

        Returns:
            可交由领域服务重读正式事实的确认请求。
        """
        if (
            self.basis.novel_id != self.generation_input.novel_id
            or self.basis.workflow != "create_characters_by_ai"
            or self.basis.step != "create_core_characters"
            or self.basis.schema_id != CORE_CHARACTERS_RESULT_SCHEMA_ID
            or self.basis.schema_version != CORE_CHARACTERS_RESULT_SCHEMA_VERSION
        ):
            raise ValueError("核心角色确认的 basis 契约不匹配")

        candidate_refs = {
            character.character_ref for character in self.candidate.core_characters
        }
        if any(ref not in candidate_refs for ref in self.selected_character_refs):
            raise ValueError("selected_character_refs 包含候选中不存在的引用")
        if self.generation_input.character_count is not None and len(self.candidate.core_characters) != self.generation_input.character_count:
            raise ValueError("核心角色候选数量必须匹配原始 generation_input")

        basis_faction_ids = {
            source.id
            for source in self.basis.source_refs
            if source.resource_type == "faction"
        }
        selected_refs = set(self.selected_character_refs)
        for binding in self.candidate.binding_candidates:
            if binding.character_ref not in selected_refs or binding.faction_id is None:
                continue
            if binding.faction_id not in basis_faction_ids:
                raise ValueError("所选角色绑定引用了候选依据之外的核心势力")

        expected_from_basis = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected_from_basis:
            raise ValueError("expected_versions 必须精确匹配 basis.source_refs")
        return self


__all__ = [
    "CORE_CHARACTERS_RESULT_SCHEMA_ID",
    "CORE_CHARACTERS_RESULT_SCHEMA_VERSION",
    "FACTION_BUSINESS_ID_MAX_LENGTH",
    "FACTION_BUSINESS_ID_MIN_LENGTH",
    "FACTION_BUSINESS_ID_PATTERN",
    "StrictSchemaModel",
    "CharacterCreateRequestV1",
    "CoreCharactersAIConfirmationRequestV1",
    "CoreCharactersGenerationInputV1",
    "CharacterRestoreRequestV1",
    "CharacterFactionBindingCandidateV1",
    "CharacterFactionMembershipType",
    "CharacterImportanceLevel",
    "CharacterResponseV1",
    "CharacterRoleType",
    "CharacterStatus",
    "CharacterStatusUpdateRequestV1",
    "CharacterUpdateRequestV1",
    "CoreCharacterCandidateV1",
    "CoreCharactersGenerateRequestV1",
    "CoreCharactersResultSchemaV1",
]
