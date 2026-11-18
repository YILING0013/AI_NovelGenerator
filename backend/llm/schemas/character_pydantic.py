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
            raise ValueError("Số nguyên trong extra phải nằm trong dải BSON int64")
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError("Số thực trong extra phải là giá trị hữu hạn")
    try:
        encoded_size = len(BSON.encode({"extra": value}))
    except Exception as exc:
        raise ValueError("Không thể mã hóa an toàn extra sang BSON") from exc
    if encoded_size > _EXTRA_BSON_MAX_BYTES:
        raise ValueError("Mã hóa BSON của extra không được vượt 1 MiB")
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
            raise ValueError("Mỗi phần tử của trường danh sách nhân vật phải dài từ 1 đến 80 ký tự")
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
            raise ValueError("Cập nhật nhân vật cần cung cấp ít nhất một trường có thể chỉnh sửa")
        null_fields = sorted(key for key, item in editable_items.items() if item is None)
        if null_fields:
            raise ValueError(f"Trường cập nhật nhân vật không được là null: {', '.join(null_fields)}")
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
            raise ValueError("Mỗi phần tử của trường danh sách nhân vật phải dài từ 1 đến 80 ký tự")
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
            raise ValueError("Mỗi phần tử của trường danh sách nhân vật phải dài từ 1 đến 80 ký tự")
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
        description="Tham chiếu ổn định chỉ dùng trong danh sách ứng viên lần này, ví dụ character_01.",
    )
    name: str = Field(min_length=1, max_length=80, description="Tên hiển thị chính thức của nhân vật.")
    aliases: list[str] = Field(max_length=10, description="Mảng biệt hiệu của nhân vật, có thể là mảng rỗng.")
    role_type: CharacterRoleType = Field(description="Kiểu nhân vật trong mạch tự sự của toàn sách.")
    importance_level: CharacterImportanceLevel = Field(description="Mức độ quan trọng của nhân vật.")
    gender: str = Field(min_length=1, max_length=80, description="Mô tả giới tính của nhân vật.")
    age_group: str = Field(min_length=1, max_length=80, description="Giai đoạn tuổi của nhân vật.")
    race: str = Field(min_length=1, max_length=80, description="Chủng tộc hoặc loài của nhân vật.")
    identity: str = Field(min_length=1, max_length=500, description="Thân phận và vị thế xã hội của nhân vật.")
    appearance: str = Field(min_length=1, max_length=1000, description="Đặc điểm ngoại hình của nhân vật.")
    personality: str = Field(min_length=1, max_length=1000, description="Tính cách cốt lõi của nhân vật.")
    core_desire: str = Field(min_length=1, max_length=1000, description="Khao khát cốt lõi của nhân vật.")
    core_fear: str = Field(min_length=1, max_length=1000, description="Nỗi sợ cốt lõi của nhân vật.")
    strengths: list[str] = Field(max_length=12, description="Mảng ưu điểm của nhân vật, có thể là mảng rỗng.")
    weaknesses: list[str] = Field(max_length=12, description="Mảng nhược điểm của nhân vật, có thể là mảng rỗng.")
    abilities: list[str] = Field(max_length=12, description="Mảng năng lực của nhân vật, có thể là mảng rỗng.")
    conflict_with_mainline: str = Field(
        min_length=1,
        max_length=1000,
        description="Xung đột cốt lõi giữa nhân vật và tuyến chính của toàn sách.",
    )
    relationship_with_protagonist: str = Field(
        min_length=1,
        max_length=1000,
        description="Quan hệ ban đầu giữa nhân vật và nhân vật chính.",
    )
    initial_state: str = Field(min_length=1, max_length=1000, description="Trạng thái nhân vật lúc câu chuyện bắt đầu.")
    growth_direction: str = Field(
        min_length=1,
        max_length=1000,
        description="Hướng trưởng thành hoặc sa ngã xuyên suốt toàn sách.",
    )
    story_function: str = Field(
        min_length=1,
        max_length=1000,
        description="Chức năng tự sự của nhân vật trong việc thúc đẩy tuyến chính.",
    )
    arc_seed: str = Field(min_length=1, max_length=1000, description="Hạt giống vòng cung nhân vật có thể triển khai qua nhiều quyển.")
    tags: list[str] = Field(max_length=10, description="Mảng thẻ của nhân vật, có thể là mảng rỗng.")

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
            raise ValueError("Mỗi phần tử của trường danh sách ứng viên nhân vật phải dài từ 1 đến 80 ký tự")
        return value


class CharacterFactionBindingCandidateV1(StrictSchemaModel):
    """核心角色候选对应的全书级势力绑定候选。"""

    character_ref: str = Field(
        pattern=_CHARACTER_REF_PATTERN,
        description="Phải tham chiếu đúng một character_ref trong core_characters.",
    )
    faction_id: str | None = Field(
        ...,
        min_length=FACTION_BUSINESS_ID_MIN_LENGTH,
        max_length=FACTION_BUSINESS_ID_MAX_LENGTH,
        pattern=FACTION_BUSINESS_ID_PATTERN,
        description="ID nghiệp vụ của thế lực cốt lõi; phải là null khi nhân vật không thuộc thế lực nào.",
    )
    membership_type: CharacterFactionMembershipType | None = Field(
        ...,
        description="Quan hệ thành viên; bắt buộc khi faction_id không trống, ngược lại phải là null.",
    )
    role_title: str | None = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Cách xưng hô của nhân vật trong thế lực; được phép là null.",
    )
    public_status: str | None = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Danh tính công khai; bắt buộc khi faction_id không trống, ngược lại phải là null.",
    )
    loyalty_level: int | None = Field(
        ...,
        ge=1,
        le=5,
        strict=True,
        description="Độ trung thành từ 1 đến 5; bắt buộc khi faction_id không trống, ngược lại phải là null.",
    )
    reason: str | None = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Lý do thuộc về; bắt buộc khi faction_id không trống, ngược lại phải là null.",
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
                raise ValueError("Khi faction_id trống, toàn bộ các trường nghiệp vụ gắn kết còn lại phải là null")
            return self

        required_values = (
            self.membership_type,
            self.public_status,
            self.loyalty_level,
            self.reason,
        )
        if any(value is None for value in required_values):
            raise ValueError(
                "Khi faction_id không trống, phải điền membership_type, public_status, loyalty_level và reason"
            )
        return self


class CoreCharactersResultSchemaV1(StrictSchemaModel):
    """全书核心角色与势力绑定候选的完整模型输出。"""

    core_characters: list[CoreCharacterCandidateV1] = Field(
        min_length=1,
        max_length=50,
        description="Danh sách ứng viên nhân vật cốt lõi cấp toàn sách.",
    )
    binding_candidates: list[CharacterFactionBindingCandidateV1] = Field(
        min_length=1,
        max_length=50,
        description="Danh sách quyết định gắn thế lực tương ứng một-một với ứng viên nhân vật cốt lõi.",
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
            raise ValueError("character_ref trong core_characters không được trùng lặp")
        if len(character_names) != len(set(character_names)):
            raise ValueError("Tên nhân vật trong core_characters không được trùng lặp")
        if len(binding_refs) != len(set(binding_refs)):
            raise ValueError("character_ref trong binding_candidates không được trùng lặp")

        # 两侧集合完全相等且各自唯一，才能保证每名角色恰好拥有一条绑定决策。
        if set(character_refs) != set(binding_refs):
            raise ValueError("binding_candidates phải bao phủ đầy đủ, một-một, danh sách ứng viên nhân vật theo character_ref")
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
            raise ValueError("expected_versions phải dùng khóa tài nguyên không trống và phiên bản là số nguyên dương")
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
            raise ValueError("Hợp đồng basis của xác nhận nhân vật cốt lõi không khớp")

        candidate_refs = {
            character.character_ref for character in self.candidate.core_characters
        }
        if any(ref not in candidate_refs for ref in self.selected_character_refs):
            raise ValueError("selected_character_refs chứa tham chiếu không có trong danh sách ứng viên")
        if self.generation_input.character_count is not None and len(self.candidate.core_characters) != self.generation_input.character_count:
            raise ValueError("Số ứng viên nhân vật cốt lõi phải khớp với generation_input gốc")

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
                raise ValueError("Việc gắn nhân vật đã chọn tham chiếu thế lực cốt lõi nằm ngoài căn cứ của danh sách ứng viên")

        expected_from_basis = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected_from_basis:
            raise ValueError("expected_versions phải khớp chính xác với basis.source_refs")
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
