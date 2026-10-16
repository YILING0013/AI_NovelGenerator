from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


CORE_FACTIONS_RESULT_SCHEMA_ID = "faction.core_generation.result"
CORE_FACTIONS_RESULT_SCHEMA_VERSION = 2
CORE_FACTION_REF_PATTERN = r"^faction_[0-9]{3}$"
CORE_FACTION_RELATION_REF_PATTERN = r"^relation_[0-9]{3}$"


class ExpandIdeaSchema(BaseModel):
    """
    将用户创意扩写为完整长篇小说压缩故事
    """
    model_config = ConfigDict(extra="forbid")

    plot: str = Field(
        ...,
        min_length=200,
        max_length=5000,
        description="完整的约3000字长篇压缩故事正文"
    )


class ExtractIdeaSchema(BaseModel):
    """
    从扩展剧情中提炼出的故事构思要素
    """
    model_config = ConfigDict(extra="forbid")

    genre: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="小说类型，如玄幻、科幻、都市、悬疑、历史、仙侠等"
    )
    tone: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="整体基调，如热血、黑暗、轻松、搞笑、治愈、压抑等"
    )
    target_audience: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="目标读者群体，如男频、女频、青少年、泛幻想读者等"
    )
    core_idea: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="用1-2句话描述故事的核心设想"
    )


class CoreSeedSchema(BaseModel):
    """
    雪花写作法第一步生成的故事核心公式
    """
    model_config = ConfigDict(extra="forbid")

    core_seed: str = Field(
        ...,
        min_length=30,
        max_length=150,
        description="故事核心公式，需包含显性冲突、潜在危机、人物核心驱动力与世界观关键矛盾暗示，长度30-100字"
    )


class NovelMetaSchema(BaseModel):
    """
    小说整体设定
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="小说主标题，具有吸引力和传播性，符合类型读者审美"
    )
    subtitle: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="副标题，补充核心冲突或主题，具有一定文学感或商业感"
    )
    introduction: str = Field(
        ...,
        min_length=100,
        max_length=300,
        description="小说引言，100-300字，引入故事，吸引读者阅读兴趣"
    )
    summary: str = Field(
        ...,
        min_length=100,
        max_length=500,
        description="小说简介，100-500字，需清晰呈现主线冲突与悬念"
    )
    worldview: str = Field(
        ...,
        min_length=100,
        max_length=800,
        description="世界观设定，说明世界规则、力量体系、社会结构等，不少于100字"
    )
    writing_style: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="创作风格，如偏黑暗现实、轻快幽默、史诗宏大等"
    )
    narrative_pov: Literal["第一人称", "第三人称有限视角", "全知视角"] = Field(
        ...,
        description="叙事视角，只能为第一人称、第三人称有限视角、全知视角之一"
    )
    era_background: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="时代背景，如架空古代、未来星际、现代都市、末世废土等"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="小说标签，3-5个，概括小说核心元素，如硬科幻、冒险、爱情等"
    )


FactionRelationType = Literal[
    "hostile",
    "allied",
    "cold_war",
    "dependent",
    "subordinate",
    "trade_partner",
    "secret_cooperation",
    "historical_enemy",
]


class CoreFactionSchema(BaseModel):
    """
    全书级核心阵营生成结果。
    """
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    faction_ref: str = Field(
        ...,
        pattern=CORE_FACTION_REF_PATTERN,
        description="本次候选内稳定引用，例如 faction_001",
    )
    name: str = Field(..., min_length=1, max_length=80, description="阵营名称")
    faction_type: str = Field(..., min_length=1, max_length=80, description="阵营类型")
    positioning: str = Field(..., min_length=10, max_length=500, description="阵营在世界结构中的定位")
    public_stance: str = Field(..., min_length=5, max_length=500, description="阵营公开对外立场")
    core_goal: str = Field(..., min_length=5, max_length=500, description="阵营真实核心目标")
    hidden_goal: str = Field(default="", max_length=500, description="阵营隐藏目标")
    resources_and_advantages: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="阵营主要资源或优势",
    )
    organization_style: str = Field(..., min_length=5, max_length=300, description="组织气质或行动风格")
    core_values: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(..., min_length=1, max_length=6, description="核心价值观")
    conflict_with_mainline: str = Field(..., min_length=10, max_length=600, description="与主线冲突的关系")
    is_public: bool = Field(default=True, description="阵营是否公开存在")
    influence_scope: str = Field(..., min_length=2, max_length=80, description="影响范围")
    expandability: str = Field(..., min_length=5, max_length=500, description="后续可扩展方向")
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=8,
        description="阵营标签",
    )


class CandidateFactionEndpointV2(BaseModel):
    """引用本次尚未落库势力的关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["candidate"]
    faction_ref: str = Field(pattern=CORE_FACTION_REF_PATTERN)


class ExistingFactionEndpointV2(BaseModel):
    """引用已有正式势力的关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["existing"]
    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)


CoreFactionRelationEndpointV2: TypeAlias = Annotated[
    CandidateFactionEndpointV2 | ExistingFactionEndpointV2,
    Field(discriminator="kind"),
]


class CoreFactionRelationSchema(BaseModel):
    """
    AI 生成阶段只使用候选 ref 或正式 ID 引用端点的阵营关系。
    """
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    relation_ref: str = Field(pattern=CORE_FACTION_RELATION_REF_PATTERN)
    source: CoreFactionRelationEndpointV2
    target: CoreFactionRelationEndpointV2
    relation_type: FactionRelationType = Field(..., description="阵营关系类型")
    current_state: str = Field(..., min_length=5, max_length=500, description="当前关系状态")
    core_conflict: str = Field(..., min_length=5, max_length=600, description="关系中的核心矛盾")
    hidden_tension: str = Field(default="", max_length=500, description="尚未爆发的深层张力")
    possible_change: str = Field(..., min_length=5, max_length=500, description="后续可能变化")
    intensity: int = Field(..., ge=1, le=5, description="关系强度，1到5")
    is_active: bool = Field(default=True, description="关系是否当前有效")

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "CoreFactionRelationSchema":
        """拒绝候选 ref 或正式 ID 的自引用关系。"""
        source_identity = (
            f"candidate:{self.source.faction_ref}"
            if self.source.kind == "candidate"
            else f"existing:{self.source.faction_id}"
        )
        target_identity = (
            f"candidate:{self.target.faction_ref}"
            if self.target.kind == "candidate"
            else f"existing:{self.target.faction_id}"
        )
        if source_identity == target_identity:
            raise ValueError("阵营关系不能指向自身")
        return self


class CoreFactionsResultSchema(BaseModel):
    """
    全书核心阵营和阵营关系的完整生成结果。
    """
    model_config = ConfigDict(extra="forbid", strict=True)

    core_factions: list[CoreFactionSchema] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="全书级核心阵营列表",
    )
    faction_relations: list[CoreFactionRelationSchema] = Field(
        default_factory=list,
        max_length=20,
        description="核心阵营之间的关系列表",
    )

    @model_validator(mode="after")
    def validate_faction_relation_references(self) -> "CoreFactionsResultSchema":
        """校验阵营数量、名称唯一性和关系引用。

        Args:
            无。

        Returns:
            校验通过后的当前模型。

        Raises:
            ValueError: 阵营名称重复或关系自引用时抛出。
        """
        faction_refs = [faction.faction_ref for faction in self.core_factions]
        if len(faction_refs) != len(set(faction_refs)):
            raise ValueError("核心阵营 faction_ref 不能重复")

        faction_names = [faction.name for faction in self.core_factions]
        if len(faction_names) != len(set(faction_names)):
            raise ValueError("核心阵营名称不能重复")

        relation_refs = [relation.relation_ref for relation in self.faction_relations]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("阵营关系 relation_ref 不能重复")

        candidate_ref_set = set(faction_refs)
        semantic_keys: list[tuple[str, str, str]] = []
        for relation in self.faction_relations:
            endpoints = (relation.source, relation.target)
            for endpoint in endpoints:
                if (
                    endpoint.kind == "candidate"
                    and endpoint.faction_ref not in candidate_ref_set
                ):
                    raise ValueError("阵营关系引用了不存在的 faction_ref")
            source_identity = (
                f"candidate:{relation.source.faction_ref}"
                if relation.source.kind == "candidate"
                else f"existing:{relation.source.faction_id}"
            )
            target_identity = (
                f"candidate:{relation.target.faction_ref}"
                if relation.target.kind == "candidate"
                else f"existing:{relation.target.faction_id}"
            )
            if relation.relation_type in {
                "hostile",
                "allied",
                "cold_war",
                "trade_partner",
                "secret_cooperation",
                "historical_enemy",
            }:
                source_identity, target_identity = sorted(
                    (source_identity, target_identity)
                )
            semantic_keys.append(
                (source_identity, target_identity, relation.relation_type)
            )

        if len(semantic_keys) != len(set(semantic_keys)):
            raise ValueError("阵营关系不能包含重复或反向重复的同类型语义边")

        return self


class ExistingFactionRelationTargetV2(BaseModel):
    """核心势力生成时用户指定的已有正式关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    relation_score: int = Field(ge=0, le=10)


class CoreFactionsGenerationInputV2(ReasoningOptions, BaseModel):
    """确认阶段允许回传并重算指纹的核心势力生成输入。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    faction_count: int | None = Field(default=3, ge=1, le=6)
    independent_faction_count: int = Field(default=0, ge=0, le=6)
    user_guidance: str = Field(default="", max_length=2000)
    single_faction_integrity_score: int | None = Field(default=None, ge=0, le=10)
    connect_to_existing: bool = False
    existing_relation_targets: list[ExistingFactionRelationTargetV2] = Field(
        default_factory=list,
        max_length=12,
    )
    existing_relation_score: int | None = Field(default=None, ge=0, le=10)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @model_validator(mode="after")
    def validate_generation_counts(self) -> "CoreFactionsGenerationInputV2":
        """校验数量约束并拒绝重复的正式关系目标。"""
        if self.faction_count is not None and self.independent_faction_count > self.faction_count:
            raise ValueError("本批不建立直接关系的势力数量不能大于本次创建势力数量")
        target_ids = [target.faction_id for target in self.existing_relation_targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("需要产生联系的已有阵营不能重复")
        return self


class GenerateCoreFactionsRequestV2(CoreFactionsGenerationInputV2):
    """核心势力生成 HTTP 请求，在业务输入外增加传输模式。"""

    use_stream: bool = True


class CoreFactionsAIConfirmationRequestV2(BaseModel):
    """核心势力及关系候选显式确认的严格请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_type: Literal["ai_confirmation"]
    candidate: CoreFactionsResultSchema
    selected_faction_refs: list[str] = Field(min_length=1, max_length=6)
    selected_relation_refs: list[str] = Field(default_factory=list, max_length=20)
    basis: CandidateBasisV1
    generation_input: CoreFactionsGenerationInputV2
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
        """清理并按首次出现顺序去重候选选择引用。"""
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
    def validate_confirmation_selection(self) -> "CoreFactionsAIConfirmationRequestV2":
        """校验候选选择、依据契约和精确版本映射。"""
        if (
            self.basis.novel_id != self.generation_input.novel_id
            or self.basis.workflow != "create_factions_by_ai"
            or self.basis.step != "create_core_factions"
            or self.basis.schema_id != CORE_FACTIONS_RESULT_SCHEMA_ID
            or self.basis.schema_version != CORE_FACTIONS_RESULT_SCHEMA_VERSION
        ):
            raise ValueError("核心势力确认的 basis 契约不匹配")

        candidate_faction_refs = {
            faction.faction_ref for faction in self.candidate.core_factions
        }
        if any(ref not in candidate_faction_refs for ref in self.selected_faction_refs):
            raise ValueError("selected_faction_refs 包含候选中不存在的引用")

        relation_by_ref = {
            relation.relation_ref: relation
            for relation in self.candidate.faction_relations
        }
        if any(ref not in relation_by_ref for ref in self.selected_relation_refs):
            raise ValueError("selected_relation_refs 包含候选中不存在的引用")
        selected_factions = set(self.selected_faction_refs)
        for relation_ref in self.selected_relation_refs:
            relation = relation_by_ref[relation_ref]
            for endpoint in (relation.source, relation.target):
                if (
                    endpoint.kind == "candidate"
                    and endpoint.faction_ref not in selected_factions
                ):
                    raise ValueError("所选关系引用了未选择的新势力")

        expected_from_basis = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected_from_basis:
            raise ValueError("expected_versions 必须精确匹配 basis.source_refs")
        return self


__all__ = [
    "CORE_FACTIONS_RESULT_SCHEMA_ID",
    "CORE_FACTIONS_RESULT_SCHEMA_VERSION",
    "CandidateFactionEndpointV2",
    "CoreFactionRelationEndpointV2",
    "CoreFactionRelationSchema",
    "CoreFactionSchema",
    "CoreFactionsGenerationInputV2",
    "CoreFactionsAIConfirmationRequestV2",
    "CoreFactionsResultSchema",
    "ExistingFactionEndpointV2",
    "ExistingFactionRelationTargetV2",
    "GenerateCoreFactionsRequestV2",
]
