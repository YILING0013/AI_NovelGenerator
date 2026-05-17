from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=80, description="阵营名称")
    faction_type: str = Field(..., min_length=1, max_length=80, description="阵营类型")
    positioning: str = Field(..., min_length=10, max_length=500, description="阵营在世界结构中的定位")
    public_stance: str = Field(..., min_length=5, max_length=500, description="阵营公开对外立场")
    core_goal: str = Field(..., min_length=5, max_length=500, description="阵营真实核心目标")
    hidden_goal: str = Field(default="", max_length=500, description="阵营隐藏目标")
    resources_and_advantages: list[str] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="阵营主要资源或优势",
    )
    organization_style: str = Field(..., min_length=5, max_length=300, description="组织气质或行动风格")
    core_values: list[str] = Field(..., min_length=1, max_length=6, description="核心价值观")
    conflict_with_mainline: str = Field(..., min_length=10, max_length=600, description="与主线冲突的关系")
    is_public: bool = Field(default=True, description="阵营是否公开存在")
    influence_scope: str = Field(..., min_length=2, max_length=80, description="影响范围")
    expandability: str = Field(..., min_length=5, max_length=500, description="后续可扩展方向")
    tags: list[str] = Field(default_factory=list, max_length=8, description="阵营标签")


class CoreFactionRelationSchema(BaseModel):
    """
    AI 生成阶段使用阵营名称引用的阵营关系。
    """
    model_config = ConfigDict(extra="forbid")

    source_faction_name: str = Field(..., min_length=1, max_length=80, description="关系发起方阵营名称")
    target_faction_name: str = Field(..., min_length=1, max_length=80, description="关系目标方阵营名称")
    relation_type: FactionRelationType = Field(..., description="阵营关系类型")
    current_state: str = Field(..., min_length=5, max_length=500, description="当前关系状态")
    core_conflict: str = Field(..., min_length=5, max_length=600, description="关系中的核心矛盾")
    hidden_tension: str = Field(default="", max_length=500, description="尚未爆发的深层张力")
    possible_change: str = Field(..., min_length=5, max_length=500, description="后续可能变化")
    intensity: int = Field(..., ge=1, le=5, description="关系强度，1到5")
    is_active: bool = Field(default=True, description="关系是否当前有效")


class CoreFactionsResultSchema(BaseModel):
    """
    全书核心阵营和阵营关系的完整生成结果。
    """
    model_config = ConfigDict(extra="forbid")

    core_factions: list[CoreFactionSchema] = Field(
        ...,
        min_length=2,
        max_length=6,
        description="全书级核心阵营列表",
    )
    faction_relations: list[CoreFactionRelationSchema] = Field(
        ...,
        min_length=1,
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
            ValueError: 阵营名称重复、关系引用不存在或缺少关键关系类型时抛出。
        """
        faction_names = [faction.name for faction in self.core_factions]
        if len(faction_names) != len(set(faction_names)):
            raise ValueError("核心阵营名称不能重复")

        faction_name_set = set(faction_names)
        relation_types = {relation.relation_type for relation in self.faction_relations}
        complex_types = {"cold_war", "secret_cooperation", "historical_enemy", "dependent"}

        for relation in self.faction_relations:
            if relation.source_faction_name not in faction_name_set:
                raise ValueError(f"关系发起方阵营不存在: {relation.source_faction_name}")
            if relation.target_faction_name not in faction_name_set:
                raise ValueError(f"关系目标方阵营不存在: {relation.target_faction_name}")
            if relation.source_faction_name == relation.target_faction_name:
                raise ValueError("阵营关系不能指向自身")

        if "hostile" not in relation_types and "historical_enemy" not in relation_types:
            raise ValueError("核心阵营关系至少需要一组对立或历史敌对关系")
        if relation_types.isdisjoint(complex_types):
            raise ValueError("核心阵营关系至少需要一组复杂关系")

        return self
