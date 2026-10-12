"""AI 小说初始化与字段改写共用的严格候选和指纹契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.api.contracts import ObjectIdString, StrictRequestModel


AI_CREATE_WORKFLOW = "create_novel_by_ai"
AI_CREATE_FINAL_STEP = "novel_meta"
AI_CREATE_SCHEMA_ID = "novel.create_candidate"
AI_CREATE_SCHEMA_VERSION = 1

NOVEL_REWRITE_WORKFLOW = "rewrite_novel_field_by_ai"
NOVEL_REWRITE_STEP = "novel_field"
NOVEL_REWRITE_SCHEMA_ID = "novel.field_rewrite_candidate"
NOVEL_REWRITE_SCHEMA_VERSION = 1
NOVEL_REWRITE_FIELDS = Literal[
    "title",
    "subtitle",
    "genre",
    "tags",
    "plot",
    "core_idea",
    "tone",
    "target_audience",
    "introduction",
    "summary",
    "core_seed",
    "worldview",
    "writing_style",
    "narrative_pov",
    "era_background",
]
NOVEL_REWRITE_FIELD_LABELS: dict[str, str] = {
    "title": "标题",
    "subtitle": "副标题",
    "genre": "类型",
    "tags": "标签",
    "plot": "主线剧情",
    "core_idea": "核心创意",
    "tone": "基调",
    "target_audience": "目标读者",
    "introduction": "引言",
    "summary": "简介",
    "core_seed": "核心种子",
    "worldview": "世界观",
    "writing_style": "写作风格",
    "narrative_pov": "叙事视角",
    "era_background": "时代背景",
}

NOVEL_REWRITE_CONTEXT_FIELDS: tuple[str, ...] = (
    "title",
    "subtitle",
    "genre",
    "tags",
    "tone",
    "target_audience",
    "core_idea",
    "core_seed",
    "writing_style",
    "narrative_pov",
    "era_background",
    "number_of_chapters",
    "words_per_chapter",
)
NOVEL_NARRATIVE_POV_VALUES = frozenset(
    {"第一人称", "第三人称有限视角", "全知视角"}
)
NOVEL_REWRITE_TEXT_LIMITS: dict[str, int] = {
    "title": 200,
    "subtitle": 500,
    "genre": 100,
    "plot": 40_000,
    "core_idea": 20_000,
    "tone": 500,
    "target_audience": 1000,
    "introduction": 20_000,
    "summary": 20_000,
    "core_seed": 20_000,
    "worldview": 20_000,
    "writing_style": 10_000,
    "narrative_pov": 200,
    "era_background": 10_000,
}

NovelTag = Annotated[str, Field(min_length=1, max_length=50)]


class NovelCreateFieldsV1(StrictRequestModel):
    """人工创建与 AI 新书确认共用的小说业务字段白名单。"""

    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=500)
    genre: str = Field(default="unclassified", min_length=1, max_length=100)
    tags: list[NovelTag] = Field(default_factory=list, max_length=30)
    introduction: str | None = Field(default=None, max_length=20_000)
    summary: str | None = Field(default=None, max_length=20_000)
    core_seed: str | None = Field(default=None, max_length=20_000)
    worldview: str | None = Field(default=None, max_length=20_000)
    writing_style: str | None = Field(default=None, max_length=10_000)
    narrative_pov: str | None = Field(default=None, max_length=200)
    era_background: str | None = Field(default=None, max_length=10_000)
    plot: str | None = Field(default=None, max_length=40_000)
    tone: str | None = Field(default=None, max_length=500)
    target_audience: str | None = Field(default=None, max_length=1000)
    core_idea: str | None = Field(default=None, max_length=20_000)
    number_of_chapters: int | None = Field(default=None, ge=1, le=10_000)
    words_per_chapter: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("tags")
    @classmethod
    def validate_unique_tags(cls, value: list[str]) -> list[str]:
        """拒绝去除空白后重复的小说标签。"""
        if len(value) != len(set(value)):
            raise ValueError("tags 不能包含重复项")
        return value


class AICreateGenerationInputV1(ReasoningOptions, StrictRequestModel):
    """四步 AI 建书指纹使用的业务输入和六项生成参数。"""

    user_idea: str = Field(min_length=1, max_length=20_000)
    number_of_chapters: int = Field(default=100, ge=1, le=10_000)
    words_per_chapter: int = Field(default=3000, ge=1, le=100_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)


class AICreateNovelRequestV1(AICreateGenerationInputV1):
    """四步 AI 建书 SSE 请求。"""

    use_stream: bool = True


class NovelRewriteChatMessageV1(StrictRequestModel):
    """字段改写的一条浏览器本地对话消息。"""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class NovelFieldRewriteGenerationInputV1(ReasoningOptions, StrictRequestModel):
    """字段候选生成和保存确认共用的严格输入白名单。"""

    provider: str = Field(min_length=1, max_length=100)
    novel_id: ObjectIdString | None = None
    target_field: NOVEL_REWRITE_FIELDS
    instruction: str = Field(min_length=1, max_length=4000)
    current_value: str | list[str] = ""
    context: dict[str, Any] = Field(default_factory=dict, max_length=100)
    chat_history: list[NovelRewriteChatMessageV1] = Field(
        default_factory=list,
        max_length=100,
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)


class NovelFieldRewriteRequestV1(NovelFieldRewriteGenerationInputV1):
    """字段改写普通或 SSE 预览请求。"""

    use_stream: bool = True


class NovelFieldRewriteCandidateV1(StrictRequestModel):
    """必须回显目标字段且值类型与目标一致的字段候选。"""

    target_field: NOVEL_REWRITE_FIELDS
    value: str | list[str]

    @model_validator(mode="after")
    def validate_target_value(self) -> "NovelFieldRewriteCandidateV1":
        """验证标签、普通文本和叙事视角的目标字段规则。"""
        if self.target_field == "tags":
            if not isinstance(self.value, list):
                raise ValueError("tags 改写结果必须为字符串数组")
            tags = [item.strip() for item in self.value if item.strip()]
            if not tags or len(tags) != len(set(tags)) or len(tags) > 30:
                raise ValueError("tags 改写结果必须为 1 到 30 个不重复非空标签")
            if any(len(item) > 50 for item in tags):
                raise ValueError("tags 单项不能超过 50 个字符")
            self.value = tags
            return self

        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("非 tags 字段的改写结果必须为非空字符串")
        value = self.value.strip()
        if len(value) > NOVEL_REWRITE_TEXT_LIMITS[self.target_field]:
            raise ValueError("字段改写结果超过目标字段长度限制")
        if (
            self.target_field == "narrative_pov"
            and value not in NOVEL_NARRATIVE_POV_VALUES
        ):
            raise ValueError("叙事视角改写结果不在允许枚举中")
        self.value = value
        return self


def extract_novel_rewrite_generation_input(
    value: Any,
) -> NovelFieldRewriteGenerationInputV1:
    """从字段改写请求提取不含传输状态的严格生成输入。

    Args:
        value: 普通/SSE 字段改写请求、确认输入或映射。

    Returns:
        不含 use_stream 的规范字段生成输入。
    """
    if isinstance(value, Mapping):
        source = dict(value)
    else:
        source = value.model_dump(mode="json")
    allowed = set(NovelFieldRewriteGenerationInputV1.model_fields)
    return NovelFieldRewriteGenerationInputV1.model_validate(
        {key: item for key, item in source.items() if key in allowed}
    )


def compute_ai_create_input_fingerprint(
    value: Any,
    *,
    flow_snapshot: Mapping[str, Any],
) -> str:
    """计算绑定建书输入、Prompt、Schema、Provider/model 与六参数的指纹。

    Args:
        value: 建书生成请求或确认时提交的 generation_input。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        生成与确认可独立重算的 64 位 SHA-256。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_novel_by_ai', value, [], flow_snapshot)


def format_rewrite_value(value: str | list[str]) -> str:
    """将字段值格式化为提示词中的可读文本。

    Args:
        value: 当前字段值，标签字段可能是字符串列表。

    Returns:
        可直接放入提示词的文本。
    """
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def compact_rewrite_context(context: dict[str, Any], target_field: str) -> dict[str, Any]:
    """过滤创建草稿上下文，只保留用户可见且非目标字段的小说创建字段。

    Args:
        context: 前端提交的完整创建草稿上下文。
        target_field: 当前正在改写的目标字段。

    Returns:
        供 LLM 参考的上下文字典。
    """
    compact: dict[str, Any] = {}
    for field in NOVEL_REWRITE_CONTEXT_FIELDS:
        # 目标字段已经通过 current_value 独立传入，避免同一长文本在 prompt 中重复出现。
        if field != target_field and field in context:
            compact[field] = context[field]
    return compact


def format_rewrite_history(history: list[NovelRewriteChatMessageV1]) -> str:
    """将字段历史对话压缩成提示词片段。

    Args:
        history: 当前目标字段的历史消息列表。

    Returns:
        可读的历史对话文本；无历史时返回占位说明。
    """
    if not history:
        return "无"

    lines: list[str] = []
    for message in history[-12:]:
        role_label = "用户" if message.role == "user" else "AI"
        lines.append(f"{role_label}: {message.content.strip()}")
    return "\n".join(lines)


def canonicalize_novel_rewrite_input(
    value: Any,
    *,
    novel: Mapping[str, Any] | None,
) -> NovelFieldRewriteGenerationInputV1:
    """将保存态改写输入替换为当前正式小说投影，创建态保持浏览器草稿。

    Args:
        value: 原始字段改写 generation_input。
        novel: 保存态当前小说文档；创建态必须为 None。

    Returns:
        与实际 Prompt 完全一致的有效字段改写输入。
    """
    generation_input = extract_novel_rewrite_generation_input(value)
    if novel is None:
        if generation_input.novel_id is not None:
            raise ValueError("保存态字段改写必须重读正式小说")
        return generation_input

    novel_id = str(novel.get("_id") or novel.get("id") or "")
    if generation_input.novel_id != novel_id:
        raise ValueError("字段改写 generation_input 与正式小说不匹配")
    context = {
        field: novel.get(field)
        for field in NOVEL_REWRITE_CONTEXT_FIELDS
        if field != generation_input.target_field and field in novel
    }
    current_value = novel.get(generation_input.target_field)
    if generation_input.target_field == "tags":
        effective_value: str | list[str] = list(current_value or [])
    else:
        effective_value = str(current_value or "")
    return generation_input.model_copy(
        update={"current_value": effective_value, "context": context}
    )


def compute_novel_rewrite_input_fingerprint(
    value: Any,
    *,
    novel: Mapping[str, Any] | None,
    flow_snapshot: Mapping[str, Any],
) -> str:
    """计算字段改写输入、正式小说版本、Prompt、Schema 与 Provider 的指纹。

    Args:
        value: 原始字段改写 generation_input。
        novel: 保存态当前小说文档；创建态为 None。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        生成与确认共用的 64 位 SHA-256。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('rewrite_novel_field_by_ai', value, [{"resource_type": "novel", "id": str(novel.get("_id") or novel.get("id")), "version": int(novel["version"])}] if novel else [], flow_snapshot)


__all__ = [
    "AI_CREATE_FINAL_STEP",
    "AI_CREATE_SCHEMA_ID",
    "AI_CREATE_SCHEMA_VERSION",
    "AI_CREATE_WORKFLOW",
    "AICreateGenerationInputV1",
    "AICreateNovelRequestV1",
    "NOVEL_NARRATIVE_POV_VALUES",
    "NOVEL_REWRITE_CONTEXT_FIELDS",
    "NOVEL_REWRITE_FIELDS",
    "NOVEL_REWRITE_FIELD_LABELS",
    "NOVEL_REWRITE_SCHEMA_ID",
    "NOVEL_REWRITE_SCHEMA_VERSION",
    "NOVEL_REWRITE_STEP",
    "NOVEL_REWRITE_WORKFLOW",
    "NovelCreateFieldsV1",
    "NovelFieldRewriteCandidateV1",
    "NovelFieldRewriteGenerationInputV1",
    "NovelFieldRewriteRequestV1",
    "NovelRewriteChatMessageV1",
    "NovelTag",
    "canonicalize_novel_rewrite_input",
    "compact_rewrite_context",
    "format_rewrite_history",
    "format_rewrite_value",
    "compute_ai_create_input_fingerprint",
    "compute_novel_rewrite_input_fingerprint",
    "extract_novel_rewrite_generation_input",
]
