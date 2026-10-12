"""核心世界规则 AI 候选、依据与确认的严格 Pydantic 契约。"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.api.contracts import StrictRequestModel, StrictResponseModel
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


CORE_WORLD_RULES_RESULT_SCHEMA_ID = "world_rule.core_generation.result"
CORE_WORLD_RULES_RESULT_SCHEMA_VERSION = 1

WorldRuleScopeType = Literal["global", "faction", "character"]
ScopeEntityId = Annotated[
    str,
    Field(min_length=1),
]
NonEmptyShortText = Annotated[str, Field(min_length=1, max_length=500)]
WorldRuleTag = Annotated[str, Field(min_length=1)]


class CoreWorldRulesGenerateRequestV1(ReasoningOptions, StrictRequestModel):
    """核心世界规则候选预览请求，不接收任何正式事实副本。"""

    core_rule_count: int = Field(default=6, ge=1, le=20)
    allow_incremental: bool = False
    user_guidance: str = Field(default="", max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)
    use_stream: bool = True


class CoreWorldRulesGenerationInputV1(ReasoningOptions, StrictRequestModel):
    """随 basis 原样回传、用于确认时重算指纹的生成输入。"""

    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    core_rule_count: int = Field(ge=1, le=20)
    allow_incremental: bool
    user_guidance: str = Field(max_length=2000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)


class WorldRuleCandidateExceptionV1(StrictRequestModel):
    """一条候选规则的例外条件及生效结果。"""

    condition: str = Field(min_length=1, max_length=500)
    effect: str = Field(min_length=1, max_length=500)


class WorldRuleCandidateV1(StrictRequestModel):
    """模型可输出且用户可编辑的一条世界规则候选。"""

    candidate_ref: str = Field(pattern=r"^rule_candidate_[0-9]+$")
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=2000)
    scope_type: WorldRuleScopeType
    scope_entity_ids: list[ScopeEntityId] = Field(max_length=100)
    enforcement: str = Field(max_length=1000)
    exceptions: list[WorldRuleCandidateExceptionV1] = Field(max_length=20)
    costs_and_consequences: list[NonEmptyShortText] = Field(max_length=20)
    priority: int = Field(ge=0, le=100)
    tags: list[WorldRuleTag] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_scope_combination(self) -> "WorldRuleCandidateV1":
        """校验作用域类型、实体 ID 类型和数组唯一性。

        Args:
            self: 已通过字段级校验的候选。

        Returns:
            作用域组合有效的原候选。
        """
        ids = list(self.scope_entity_ids)
        if len(ids) != len(set(ids)):
            raise ValueError("scope_entity_ids 不能包含重复 ID")
        if self.scope_type == "global":
            if ids:
                raise ValueError("global 作用域不能携带实体 ID")
            return self
        if not ids:
            raise ValueError(f"{self.scope_type} 作用域至少需要一个实体 ID")
        if self.scope_type == "faction":
            invalid = any(
                re.fullmatch(FACTION_BUSINESS_ID_PATTERN, item) is None
                for item in ids
            )
        else:
            invalid = any(re.fullmatch(r"^char_[0-9]{6,}$", item) is None for item in ids)
        if invalid:
            raise ValueError("scope_entity_ids 的 ID 类型必须匹配 scope_type")
        return self

class CoreWorldRulesResultV1(StrictRequestModel):
    """Provider 必须完整返回的核心规则候选根对象。"""

    core_world_rules: list[WorldRuleCandidateV1] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_unique_candidate_refs(self) -> "CoreWorldRulesResultV1":
        """拒绝本批重复候选引用。

        Args:
            self: 已完成嵌套结构校验的结果。

        Returns:
            候选引用唯一的原结果。
        """
        refs = [item.candidate_ref for item in self.core_world_rules]
        if len(refs) != len(set(refs)):
            raise ValueError("candidate_ref 不能重复")
        return self


class CoreWorldRulesBasisV1(CandidateBasisV1):
    """包含原始严格生成输入的核心规则不透明候选依据。"""

    generation_input: CoreWorldRulesGenerationInputV1

    @model_validator(mode="after")
    def validate_world_rule_contract(self) -> "CoreWorldRulesBasisV1":
        """确保 basis 元数据、小说和生成输入属于同一工作流。

        Args:
            self: 已通过公共 basis 校验的依据。

        Returns:
            契约一致的原依据。
        """
        if (
            self.workflow != "create_world_rules_by_ai"
            or self.step != "create_core_world_rules"
            or self.schema_id != CORE_WORLD_RULES_RESULT_SCHEMA_ID
            or self.schema_version != CORE_WORLD_RULES_RESULT_SCHEMA_VERSION
            or self.novel_id != self.generation_input.novel_id
        ):
            raise ValueError("核心世界规则 basis 契约不匹配")
        return self


class CoreWorldRulesPreviewV1(StrictResponseModel):
    """普通预览与 SSE done.result 共用的核心规则候选信封。"""

    workflow: Literal["create_world_rules_by_ai"]
    step: Literal["create_core_world_rules"]
    schema_id: Literal["world_rule.core_generation.result"]
    schema_version: Literal[1]
    candidate: CoreWorldRulesResultV1
    basis: CoreWorldRulesBasisV1


class CoreWorldRulesConfirmV1(StrictRequestModel):
    """核心规则候选整批确认请求。"""

    candidates: list[WorldRuleCandidateV1] = Field(min_length=1, max_length=20)
    basis: CoreWorldRulesBasisV1
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator("expected_versions", mode="before")
    @classmethod
    def validate_raw_expected_versions(cls, value: object) -> object:
        """在类型转换前拒绝布尔值、字符串版本和空键。

        Args:
            value: 客户端提交的原始版本映射。

        Returns:
            仅含正整数版本的原映射。
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
    def validate_confirmation(self) -> "CoreWorldRulesConfirmV1":
        """校验候选引用和版本映射与 basis 完全一致。

        Args:
            self: 已完成字段级校验的确认请求。

        Returns:
            可交由领域服务重读正式事实的原请求。
        """
        refs = [item.candidate_ref for item in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("确认候选 candidate_ref 不能重复")
        expected = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected:
            raise ValueError("expected_versions 必须精确匹配 basis.source_refs")
        if len(self.candidates) > self.basis.generation_input.core_rule_count:
            raise ValueError("确认候选数量不能超过原始生成数量")
        return self


__all__ = [
    "CORE_WORLD_RULES_RESULT_SCHEMA_ID",
    "CORE_WORLD_RULES_RESULT_SCHEMA_VERSION",
    "CoreWorldRulesBasisV1",
    "CoreWorldRulesConfirmV1",
    "CoreWorldRulesGenerateRequestV1",
    "CoreWorldRulesGenerationInputV1",
    "CoreWorldRulesPreviewV1",
    "CoreWorldRulesResultV1",
    "WorldRuleCandidateExceptionV1",
    "WorldRuleCandidateV1",
]
