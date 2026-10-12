"""资料整理节点、内嵌技能与固定报告格式。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString
from backend.llm.schemas.writing_pydantic import WritingSelectionV1


AGENT_TOOL_NAMES = ("get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous", "load_skill")
ENTITY_KINDS = ("character", "faction", "location", "item", "world_rule")
EntityKind = Literal["character", "faction", "location", "item", "world_rule"]


class AgentModel(BaseModel):
    """拒绝模型或浏览器提交未声明的整理字段。"""

    model_config = ConfigDict(extra="forbid")


class AgentSkillV1(AgentModel):
    """随流程修订保存的技能文字，不允许脚本或外部路径。"""

    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    instructions: str = Field(min_length=1, max_length=12000)


DEFAULT_AGENT_SKILLS = [
    {"id": "story_boundaries", "name": "剧情边界", "description": "核对主线、当前位置、上下部分与已保存下级。",
     "instructions": "先读取当前范围和目录。卷剧情承接全书剧情，篇章剧情承接本卷剧情；保留相邻已定起止。下级只补尚未覆盖的剧情，不重复已保存内容。没有下级正是本次需要生成，不是缺资料；标题与划分交给后续候选审核，不重复要求作者确认已给出的预算。末卷给出收束，不虚构下一卷。"},
    {"id": "people_factions", "name": "人物与势力", "description": "查找可复用人物、势力以及当前卷状态。",
     "instructions": "先查找再读详情，按剧情职责选择实际需要的角色与势力。卷目标和计划终点只是设计，未定位资料不能当作当前事实。每项选择说明作用；已有资料不能承担的职责才提出新增，未读详情的 ID 不得采用。"},
    {"id": "places_rules", "name": "地点与设定", "description": "核对场所、物品和世界规则。",
     "instructions": "查找并读取支撑行动的已有地点、物品与规则，核对距离、功能和限制；没有合适地点才建议新增。办公室、站厅、通道等可由已有地点承载时直接复用，不为可选的空间细化阻止生成。只有已核实且现有资料无法承担的必要实体缺口才报告补齐位置；不在正文中暗中建档。"},
    {"id": "continuity", "name": "前文衔接", "description": "读取当前位置以前的正文并检查衔接。",
     "instructions": "阅读已写前文，区分正式正文和规划；保持已发生事件、人物状态和因果。工具没有返回的正文不要编造。说明尚未覆盖的剧情与拆分建议。"},
]


class AgentNodeConfigV1(AgentModel):
    """资料整理节点可编辑的配置。"""

    prompt: str = ""
    system_prompt: str = ""
    provider: str = ""
    provider_input: str = ""
    model: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, gt=0)
    max_rounds: int = Field(default=8, ge=1, le=8)
    max_tool_calls: int = Field(default=24, ge=1, le=24)
    deduplicate_tool_budget: bool = False
    reference_unchanged_entities: bool = False
    index_structural_context: bool = False
    index_plot_children: bool = False
    tools: list[Literal["get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous", "load_skill"]] = Field(default_factory=lambda: list(AGENT_TOOL_NAMES), min_length=1, max_length=8)
    skills: list[AgentSkillV1] = Field(default_factory=lambda: [AgentSkillV1.model_validate(value) for value in DEFAULT_AGENT_SKILLS], max_length=20)
    schema_defs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_tools_and_skills(self) -> "AgentNodeConfigV1":
        """工具与技能使用唯一 ID，避免不同内容共用一个入口。"""
        if len(self.tools) != len(set(self.tools)) or len(self.skills) != len({skill.id for skill in self.skills}):
            raise ValueError("工具名和技能 ID 不能重复")
        if "get_scope" not in self.tools:
            raise ValueError("资料整理必须启用 get_scope")
        return self


class PreparedTargetV1(AgentModel):
    """由服务端固定的小说和操作位置。"""

    novel_id: ObjectIdString
    target_type: Literal["volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    reading_version: Literal[1] | None = None
    reading_intent: Literal["chapter_before", "chapter_after", "append", "replan"] | None = None


class EntitySelectionReasonV1(AgentModel):
    """采用已读实体的具体原因。"""

    resource_type: EntityKind
    id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


class EntityNeedV1(AgentModel):
    """当前资料无法承担的一项剧情职责。"""

    resource_type: EntityKind
    role: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)


class EntityNewCountsV1(AgentModel):
    """各类新实体建议数量，最终仍由相应领域上限校验。"""

    character: int = Field(default=0, ge=0, le=30)
    faction: int = Field(default=0, ge=0, le=30)
    location: int = Field(default=0, ge=0, le=30)
    item: int = Field(default=0, ge=0, le=30)
    world_rule: int = Field(default=0, ge=0, le=30)


class PreparationMissingV1(AgentModel):
    """已核实且现有资料无法承担、会阻止本次生成的缺项。"""

    field: str = Field(min_length=1, max_length=200, description="确实缺失的已有资料或必要实体位置，不是本次要生成的下级、标题或已给出的预算。")
    message: str = Field(min_length=1, max_length=2000, description="说明已查到什么、为何现有资料不能支撑本次生成，以及作者需补什么；可复用的地点细节或可选建议不属于缺项。")


class PreparedContextV1(AgentModel):
    """下一步生成需要的固定资料报告；正式详情由服务端填入。"""

    schema_version: Literal[1] = 1
    target: PreparedTargetV1
    boundaries: str = Field(min_length=1, max_length=12000)
    selected_entities: WritingSelectionV1 = Field(default_factory=WritingSelectionV1)
    selection_reasons: list[EntitySelectionReasonV1] = Field(default_factory=list, max_length=250)
    entity_needs: list[EntityNeedV1] = Field(default_factory=list, max_length=150)
    new_counts: EntityNewCountsV1 = Field(default_factory=EntityNewCountsV1)
    suggested_count: int = Field(ge=0, le=20, description="本次应新增的下级数量。仍有未覆盖剧情时为1至20；全部剧情已被现有下级覆盖时必须为0。遵守本次输入明确给定的固定数量，auto时自主估计。")
    coverage: str = Field(min_length=1, max_length=12000, description="分别说明已有下级已覆盖什么、还剩什么；当前没有下级时不能声称剧情已经覆盖。")
    remaining: bool = Field(strict=True, description="是否还有需要本次生成的未覆盖内容。true表示仍需生成，suggested_count必须大于0；false表示已有内容完整覆盖、无需新增，suggested_count必须为0。不是‘资料是否还需补齐’。")
    missing_required: list[PreparationMissingV1] = Field(default_factory=list, max_length=100, description="仅填写已核实且不补齐就无法生成的缺项，资料足够时填[]。本次待生成内容、已明确的作者参数、可沿用已有地点的办公室或通道、可选细化建议均不得放入。")
    entity_details: list[dict[str, Any]] = Field(default_factory=list, max_length=250)
    volume_states: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    relations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    previous_text: list[dict[str, Any]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def remaining_count(self) -> "PreparedContextV1":
        """生成数量必须与是否还有待生成内容一致。"""
        if self.remaining and self.suggested_count == 0:
            raise ValueError("仍有未规划剧情时，建议数量不能为零")
        if not self.remaining and self.suggested_count != 0:
            raise ValueError("声称剧情已全部覆盖时，建议数量必须为零；仍需新增内容请把 remaining 改为 true")
        return self


class BookReadV1(AgentModel):
    """可重放的固定工具读取，包含空结果和分页。"""

    tool: Literal["get_scope", "list_directory", "search_book", "search_entities", "read_entity", "read_volume_state", "read_previous"]
    arguments: dict[str, Any]
    scope: PreparedTargetV1
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
