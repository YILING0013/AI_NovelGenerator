from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ExtractIdeaSchema(BaseModel):
    """
    从用户创意中提炼出的故事构思要素
    """
    model_config = ConfigDict(extra="forbid")

    plot: str = Field(
        ...,
        min_length=50,
        max_length=300,
        description="故事剧情概括，简短描绘主要情节走向和核心冲突"
    )
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
        max_length=100,
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
    summary: str = Field(
        ...,
        min_length=100,
        max_length=300,
        description="小说简介，100-300字，需清晰呈现主线冲突与悬念"
    )
    worldview: str = Field(
        ...,
        min_length=100,
        max_length=1000,
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