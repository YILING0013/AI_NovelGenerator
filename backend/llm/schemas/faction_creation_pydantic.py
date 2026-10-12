"""人工创建势力与卷内 AI 候选共用的档案字段。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN, _validate_bson_safe_extra
from backend.db.repositories.faction_repository import normalize_faction_name


class FactionCreateRequestV1(BaseModel):
    """人工势力创建请求，层级归属由 Service 做同书校验。"""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1, max_length=80)
    alias: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=10,
    )
    faction_type: str = Field(default="", max_length=80)
    level_type: Literal["core", "volume", "local"] = "core"
    parent_faction_id: str | None = Field(
        default=None,
        pattern=FACTION_BUSINESS_ID_PATTERN,
    )
    volume_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{24}$")
    positioning: str = Field(default="", max_length=500)
    public_stance: str = Field(default="", max_length=500)
    core_goal: str = Field(default="", max_length=500)
    hidden_goal: str = Field(default="", max_length=500)
    resources_and_advantages: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(default_factory=list, max_length=6)
    organization_style: str = Field(default="", max_length=300)
    core_values: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=6,
    )
    conflict_with_mainline: str = Field(default="", max_length=600)
    is_public: bool = True
    influence_scope: str = Field(default="", max_length=80)
    expandability: str = Field(default="", max_length=500)
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=8,
    )
    first_appearance_volume_id: str | None = Field(default=None, max_length=100)
    first_appearance_chapter_id: str | None = Field(default=None, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, strict=True)
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """拒绝空白势力名称并返回去除首尾空白的值。

        Args:
            value: 调用方提交的势力名称。

        Returns:
            首尾空白已清理的非空名称。
        """
        return normalize_faction_name(value)[0]

    @field_validator("extra")
    @classmethod
    def validate_extra_bson(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """拒绝无法安全持久化或超过 1 MiB 的势力扩展 JSON。"""
        return _validate_bson_safe_extra(value)

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "FactionCreateRequestV1":
        """拒绝无法表达正式归属的层级与卷组合。

        Args:
            无。

        Returns:
            core 无归属卷，volume/local 有归属卷的请求。
        """
        if self.level_type == "core" and self.volume_id is not None:
            raise ValueError("core 势力不能设置 volume_id")
        if self.level_type in {"volume", "local"} and self.volume_id is None:
            raise ValueError("volume/local 势力必须设置 volume_id")
        return self


