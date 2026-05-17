"""AI 创建小说路由：通过 4 步 LLM 管道从用户创意生成完整小说设定（SSE 流式状态推送）。"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.db.errors import InvalidIdError, NotFoundError
from backend.db.repositories.novel_repository import novel_repo
from backend.llm.config import get_llm_config, get_provider_config
from backend.services.llm.workflow_service import (
    get_llm_service_for_step,
    resolve_provider_for_step,
    resolve_timeout_for_step,
)
from backend.services.llm.llm_service import LLMService
from backend.services.llm.format_review_service import validate_and_fix_format
from backend.services.novel.faction_service import FactionService
from backend.llm.prompts.prompt_selector import (
    CORE_FACTIONS_PROMPT_NAME,
    REWRITE_NOVEL_FIELD_PROMPT_NAME,
    load_prompt_config,
)
from backend.llm.schemas.novel_pydantic import (
    ExpandIdeaSchema,
    ExtractIdeaSchema,
    CoreSeedSchema,
    CoreFactionsResultSchema,
    NovelMetaSchema,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

WORKFLOW_NAME = "create_novel_by_ai"
FACTIONS_WORKFLOW_NAME = "create_factions_by_ai"
CREATE_CORE_FACTIONS_STEP_NAME = "create_core_factions"
logger = logging.getLogger(__name__)

NovelRewriteFieldKey = Literal[
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

REWRITABLE_NOVEL_FIELDS: set[str] = {
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
}

REWRITE_CONTEXT_FIELDS: tuple[str, ...] = (
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

FIELD_LABELS: dict[str, str] = {
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

NARRATIVE_POV_VALUES: set[str] = {"第一人称", "第三人称有限视角", "全知视角"}
TAG_SPLIT_RE = re.compile(r"[\n,，、;；]+")


def _load_prompts() -> dict:
    """读取当前生效的 prompt 定义文件。"""
    return load_prompt_config()


def _check_json_schema_support(step_name: str, workflow_name: str = WORKFLOW_NAME) -> bool:
    """检查指定步骤对应的 Provider 是否支持 JSON Schema 输出。"""
    provider = resolve_provider_for_step(workflow_name, step_name)
    if not provider:
        return False
    return get_provider_config(provider).supports_json_schema


def _sse_event(event: str, data: dict) -> str:
    """格式化一条 SSE 事件。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _log_workflow_event(request_id: str, step: str, status: str, **details: object) -> None:
    logger.info(
        "[create_novel_by_ai] request_id=%s step=%s status=%s details=%s",
        request_id,
        step,
        status,
        details or {},
    )


AI_CREATE_STEP_ORDER: tuple[str, ...] = ("expand_idea", "extract_idea", "core_seed", "novel_meta")


class AICreateCachedSteps(BaseModel):
    """AI 创建小说流程的可复用步骤缓存。

    Args:
        expand_idea: 已完成的扩写完整剧情结果。
        extract_idea: 已完成的提炼创意结果。
        core_seed: 已完成的故事核心结果。
        novel_meta: 已完成的小说设定结果。

    Returns:
        请求体中的缓存步骤会被 Pydantic 校验为对应 schema 实例。
    """

    expand_idea: ExpandIdeaSchema | None = None
    extract_idea: ExtractIdeaSchema | None = None
    core_seed: CoreSeedSchema | None = None
    novel_meta: NovelMetaSchema | None = None


def _model_dump_or_none(model: BaseModel | None) -> dict[str, Any] | None:
    """把 Pydantic 模型转换为可序列化字典。

    Args:
        model: 可能为空的 Pydantic 模型实例。

    Returns:
        模型字典；为空时返回 None。
    """
    return model.model_dump() if model is not None else None


def _build_ai_create_result(
    expanded: ExpandIdeaSchema | None = None,
    idea: ExtractIdeaSchema | None = None,
    seed: CoreSeedSchema | None = None,
    meta: NovelMetaSchema | None = None,
) -> dict[str, Any]:
    """汇总 AI 创建小说流程中已经完成的步骤结果。

    Args:
        expanded: 扩写完整剧情步骤结果。
        idea: 提炼创意步骤结果。
        seed: 生成故事核心步骤结果。
        meta: 生成小说设定步骤结果。

    Returns:
        只包含非空步骤的结果字典，可作为 partial_result 或最终 result。
    """
    result: dict[str, Any] = {}
    if dumped := _model_dump_or_none(expanded):
        result["expand_idea"] = dumped
    if dumped := _model_dump_or_none(idea):
        result["extract_idea"] = dumped
    if dumped := _model_dump_or_none(seed):
        result["core_seed"] = dumped
    if dumped := _model_dump_or_none(meta):
        result["novel_meta"] = dumped
    return result


def _get_contiguous_cached_steps(cached_steps: AICreateCachedSteps | None) -> dict[str, BaseModel]:
    """读取从第一步开始连续存在的缓存步骤。

    Args:
        cached_steps: 前端传入的可选缓存步骤。

    Returns:
        只包含连续前缀的缓存字典；中间断档后的缓存会被忽略，避免错误续跑。
    """
    if cached_steps is None:
        return {}

    prefix: dict[str, BaseModel] = {}
    for step_name in AI_CREATE_STEP_ORDER:
        cached_value = getattr(cached_steps, step_name)
        if cached_value is None:
            break
        # 只信任连续前缀，后续步骤即使传入也会从断点重新生成。
        prefix[step_name] = cached_value
    return prefix


class AICreateNovelRequest(BaseModel):
    user_idea: str
    number_of_chapters: int = 100
    words_per_chapter: int = 3000
    cached_steps: AICreateCachedSteps | None = None
    # 可选生成参数，前端传入时覆盖 provider 级别默认值
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None)


def _build_gen_kwargs(req: Any) -> dict:
    """从请求中提取非空的生成参数，用于传入 LLMService。"""
    kwargs: dict = {}
    for key in ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "system_prompt"):
        val = getattr(req, key)
        if val is not None:
            kwargs[key] = val
    return kwargs


class NovelRewriteChatMessage(BaseModel):
    """单条创建态字段改写对话消息。"""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)


class NovelFieldRewriteRequest(BaseModel):
    """创建态字段改写请求。"""

    provider: str = Field(..., min_length=1)
    target_field: NovelRewriteFieldKey
    instruction: str = Field(..., min_length=1, max_length=4000)
    current_value: str | list[str] = ""
    context: dict[str, Any] = Field(default_factory=dict)
    chat_history: list[NovelRewriteChatMessage] = Field(default_factory=list)


class NovelFieldRewriteResult(BaseModel):
    """创建态字段改写结果。"""

    target_field: NovelRewriteFieldKey
    value: str | list[str]


class GenerateCoreFactionsRequest(BaseModel):
    """基于已保存小说生成核心阵营预览的请求。"""

    novel_id: str = Field(..., min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None)


def _validate_rewrite_provider(provider: str):
    """校验指定 Provider 能否用于创建态字段改写。

    Args:
        provider: 前端选择的 Provider 别名。

    Returns:
        已解析的 Provider 配置。

    Raises:
        HTTPException: Provider 不存在或未启用时抛出 400。
    """
    alias = provider.strip()
    llm_cfg = get_llm_config()
    if alias not in llm_cfg.providers:
        raise HTTPException(status_code=400, detail=f"Provider 不存在: {alias}")

    provider_config = get_provider_config(alias)
    if not provider_config.enabled:
        raise HTTPException(status_code=400, detail=f"Provider 未启用: {alias}")

    return provider_config


def _format_rewrite_value(value: str | list[str]) -> str:
    """将字段值格式化为提示词中的可读文本。

    Args:
        value: 当前字段值，标签字段可能是字符串列表。

    Returns:
        可直接放入提示词的文本。
    """
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _compact_rewrite_context(context: dict[str, Any], target_field: str) -> dict[str, Any]:
    """过滤创建草稿上下文，只保留用户可见且非目标字段的小说创建字段。

    Args:
        context: 前端提交的完整创建草稿上下文。
        target_field: 当前正在改写的目标字段。

    Returns:
        供 LLM 参考的上下文字典。
    """
    compact: dict[str, Any] = {}
    for field in REWRITE_CONTEXT_FIELDS:
        # 目标字段已经通过 current_value 独立传入，避免同一长文本在 prompt 中重复出现。
        if field != target_field and field in context:
            compact[field] = context[field]
    return compact


def _format_rewrite_history(history: list[NovelRewriteChatMessage]) -> str:
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


def _build_rewrite_prompt(req: NovelFieldRewriteRequest, *, use_json_schema: bool) -> str:
    """构造创建态字段改写提示词。

    Args:
        req: 字段改写请求模型。
        use_json_schema: 当前 Provider 是否支持结构化输出。

    Returns:
        发送给 LLM 的完整提示词。
    """
    prompts = _load_prompts().get(REWRITE_NOVEL_FIELD_PROMPT_NAME, {})
    field_label = FIELD_LABELS[req.target_field]
    context_json = json.dumps(
        _compact_rewrite_context(req.context, req.target_field),
        ensure_ascii=False,
        indent=2,
    )
    current_value = _format_rewrite_value(req.current_value)
    history_text = _format_rewrite_history(req.chat_history)
    suffix_key = (
        "rewrite_novel_field_prompt_with_schema_suffix"
        if use_json_schema
        else "rewrite_novel_field_prompt_without_schema_suffix"
    )

    prompt_base = prompts["rewrite_novel_field_prompt_base"].format(
        target_field_label=field_label,
        target_field=req.target_field,
        instruction=req.instruction.strip(),
        current_value=current_value or "无",
        context_json=context_json,
        history_text=history_text,
    )
    prompt_suffix = prompts[suffix_key].format(target_field=req.target_field)
    return f"{prompt_base}\n{prompt_suffix}".strip()


def _normalize_rewrite_value(target_field: NovelRewriteFieldKey, value: str | list[str]) -> str | list[str]:
    """归一化 LLM 返回的字段值。

    Args:
        target_field: 当前改写目标字段。
        value: LLM 返回的原始字段值。

    Returns:
        可直接返回给前端并写入表单的字段值。

    Raises:
        ValueError: 返回值为空或不满足字段约束时抛出。
    """
    if target_field not in REWRITABLE_NOVEL_FIELDS:
        raise ValueError(f"不支持改写字段: {target_field}")

    if target_field == "tags":
        raw_items = value if isinstance(value, list) else TAG_SPLIT_RE.split(str(value))
        tags: list[str] = []
        for item in raw_items:
            tag = str(item).strip()
            if tag and tag not in tags:
                tags.append(tag)
        if not tags:
            raise ValueError("标签改写结果不能为空")
        return tags[:8]

    if isinstance(value, list):
        text = "\n".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value).strip()

    if not text:
        raise ValueError(f"{FIELD_LABELS[target_field]}改写结果不能为空")

    if target_field == "narrative_pov" and text not in NARRATIVE_POV_VALUES:
        allowed = "、".join(sorted(NARRATIVE_POV_VALUES))
        raise ValueError(f"叙事视角只能为: {allowed}")

    return text


def _normalize_rewrite_result(
    target_field: NovelRewriteFieldKey,
    result: NovelFieldRewriteResult,
) -> NovelFieldRewriteResult:
    """校验并归一化完整改写结果。

    Args:
        target_field: 请求中的目标字段。
        result: LLM 返回并解析后的改写结果。

    Returns:
        字段一致且值已归一化的改写结果。

    Raises:
        ValueError: 字段不一致或字段值非法时抛出。
    """
    if result.target_field != target_field:
        raise ValueError(f"AI 返回字段不一致: {result.target_field}")

    return NovelFieldRewriteResult(
        target_field=target_field,
        value=_normalize_rewrite_value(target_field, result.value),
    )


def _safe_novel_text(novel: dict[str, Any], field: str, fallback: str = "未提供") -> str:
    """读取小说字段并转换为适合提示词的文本。

    Args:
        novel: 已落库小说文档。
        field: 字段名。
        fallback: 字段为空时使用的占位文本。

    Returns:
        可放入提示词的字符串。
    """
    value = novel.get(field)
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip()) or fallback
    text = str(value or "").strip()
    return text or fallback


def _build_core_factions_prompt(novel: dict[str, Any], *, use_json_schema: bool) -> str:
    """构造全书核心阵营生成提示词。

    Args:
        novel: 已落库小说文档。
        use_json_schema: 当前 Provider 是否支持结构化输出。

    Returns:
        发送给 LLM 的完整提示词。
    """
    prompts = _load_prompts().get(CORE_FACTIONS_PROMPT_NAME, {})
    suffix_key = (
        "create_core_factions_prompt_with_schema_suffix"
        if use_json_schema
        else "create_core_factions_prompt_without_schema_suffix"
    )
    tags = novel.get("tags") if isinstance(novel.get("tags"), list) else []
    prompt_base = prompts["create_core_factions_prompt_base"].format(
        plot=_safe_novel_text(novel, "plot"),
        genre=_safe_novel_text(novel, "genre", "未分类"),
        tone=_safe_novel_text(novel, "tone"),
        target_audience=_safe_novel_text(novel, "target_audience"),
        core_idea=_safe_novel_text(novel, "core_idea"),
        number_of_chapters=novel.get("number_of_chapters") or 100,
        words_per_chapter=novel.get("words_per_chapter") or 3000,
        core_seed=_safe_novel_text(novel, "core_seed"),
        title=_safe_novel_text(novel, "title"),
        summary=_safe_novel_text(novel, "summary"),
        worldview=_safe_novel_text(novel, "worldview"),
        writing_style=_safe_novel_text(novel, "writing_style"),
        narrative_pov=_safe_novel_text(novel, "narrative_pov"),
        era_background=_safe_novel_text(novel, "era_background"),
        tags_json=json.dumps(tags, ensure_ascii=False),
    )
    return f"{prompt_base}\n{prompts[suffix_key]}".strip()


@router.post("/generate-core-factions")
async def generate_core_factions(req: GenerateCoreFactionsRequest):
    """基于已保存小说信息生成核心阵营预览，不写入数据库。

    Args:
        req: 生成核心阵营的请求参数。

    Returns:
        包含 core_factions 与 faction_relations 的预览结果。
    """
    request_id = uuid4().hex[:8]
    try:
        novel = await novel_repo.get_novel_by_id(req.novel_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if await FactionService.has_core_factions_initialized(req.novel_id):
        raise HTTPException(status_code=409, detail="核心阵营已初始化，请改用手动新增或先清空核心势力与垃圾桶")

    step_name = CREATE_CORE_FACTIONS_STEP_NAME
    provider = resolve_provider_for_step(FACTIONS_WORKFLOW_NAME, step_name) or ""
    timeout_seconds = resolve_timeout_for_step(FACTIONS_WORKFLOW_NAME, step_name)
    use_json_schema = _check_json_schema_support(step_name, FACTIONS_WORKFLOW_NAME)
    gen_kwargs = _build_gen_kwargs(req)
    prompt = _build_core_factions_prompt(novel, use_json_schema=use_json_schema)

    logger.info(
        "[generate_core_factions] request_id=%s novel_id=%s provider=%s json_schema=%s",
        request_id,
        req.novel_id,
        provider or "unresolved",
        use_json_schema,
    )

    try:
        service = get_llm_service_for_step(FACTIONS_WORKFLOW_NAME, step_name)
        if use_json_schema:
            raw_result = await service.generate_structured(prompt, CoreFactionsResultSchema, **gen_kwargs)
        else:
            raw_text = await service.generate_text(prompt, **gen_kwargs)
            raw_result = await validate_and_fix_format(raw_text, CoreFactionsResultSchema, step_name)
        parsed_result = CoreFactionsResultSchema.model_validate(raw_result.model_dump())
        return parsed_result.model_dump()
    except ValueError as exc:
        logger.warning(
            "[generate_core_factions] request_id=%s invalid_result=%s",
            request_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "[generate_core_factions] request_id=%s failed provider=%s timeout=%s",
            request_id,
            provider or "unresolved",
            timeout_seconds,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/rewrite-novel-field")
async def rewrite_novel_field(req: NovelFieldRewriteRequest):
    """使用指定 Provider 改写创建态小说信息中的单个字段。

    Args:
        req: 前端提交的字段改写请求。

    Returns:
        包含目标字段和改写后字段值的响应字典。
    """
    provider_config = _validate_rewrite_provider(req.provider)
    prompt = _build_rewrite_prompt(req, use_json_schema=provider_config.supports_json_schema)
    request_id = uuid4().hex[:8]
    logger.info(
        "[rewrite_novel_field] request_id=%s provider=%s field=%s json_schema=%s",
        request_id,
        req.provider,
        req.target_field,
        provider_config.supports_json_schema,
    )

    try:
        service = LLMService(provider_name=req.provider)
        if provider_config.supports_json_schema:
            raw_result = await service.generate_structured(prompt, NovelFieldRewriteResult)
        else:
            raw_text = await service.generate_text(prompt)
            raw_result = await validate_and_fix_format(
                raw_text,
                NovelFieldRewriteResult,
                "rewrite_novel_field",
            )

        parsed_result = NovelFieldRewriteResult.model_validate(raw_result.model_dump())
        normalized_result = _normalize_rewrite_result(req.target_field, parsed_result)
        return normalized_result.model_dump()
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning(
            "[rewrite_novel_field] request_id=%s invalid_result=%s",
            request_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(
            "[rewrite_novel_field] request_id=%s failed provider=%s field=%s",
            request_id,
            req.provider,
            req.target_field,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/create-novel-by-ai")
async def create_novel_by_ai(req: AICreateNovelRequest):
    """4 步 LLM 管道（SSE 流式）：expand_idea → extract_idea → core_seed → novel_meta。

    Args:
        req: AI 创建小说请求，允许携带从第一步开始连续完成的 cached_steps。

    Returns:
        SSE 响应；每一步通过 step 事件推送，结束时通过 done 事件返回结果或部分结果。
    """

    async def event_stream() -> AsyncGenerator[str, None]:
        request_id = uuid4().hex[:8]
        workflow_start = time.perf_counter()
        prompts = _load_prompts().get("create_novel_by_ai", {})
        gen_kwargs = _build_gen_kwargs(req)
        cached_prefix = _get_contiguous_cached_steps(req.cached_steps)
        expanded: ExpandIdeaSchema | None = None
        idea: ExtractIdeaSchema | None = None
        seed: CoreSeedSchema | None = None
        meta: NovelMetaSchema | None = None
        _log_workflow_event(
            request_id,
            "workflow",
            "started",
            idea_chars=len(req.user_idea),
            number_of_chapters=req.number_of_chapters,
            words_per_chapter=req.words_per_chapter,
            cached_steps=list(cached_prefix.keys()),
            overrides=sorted(gen_kwargs.keys()),
        )

        # Step 1: Expand Idea to Full Novel Story
        if cached_expanded := cached_prefix.get("expand_idea"):
            expanded = cached_expanded  # type: ignore[assignment]
            _log_workflow_event(request_id, "expand_idea", "cached")
            yield _sse_event("step", {"step": "expand_idea", "status": "done", "cached": True, "data": expanded.model_dump()})
        else:
            yield _sse_event("step", {"step": "expand_idea", "status": "running"})
            step_started_at = time.perf_counter()
            provider0 = resolve_provider_for_step(WORKFLOW_NAME, "expand_idea_to_full_novel_story") or ""
            timeout0 = resolve_timeout_for_step(WORKFLOW_NAME, "expand_idea_to_full_novel_story")
            use_schema0 = _check_json_schema_support("expand_idea_to_full_novel_story")
            _log_workflow_event(
                request_id,
                "expand_idea",
                "running",
                provider=provider0 or "unresolved",
                timeout_seconds=timeout0,
                json_schema=use_schema0,
            )
            try:
                svc0 = get_llm_service_for_step(WORKFLOW_NAME, "expand_idea_to_full_novel_story")
                suffix0 = "expand_idea_to_full_novel_story_prompt_with_schema_suffix" if use_schema0 else "expand_idea_to_full_novel_story_prompt_without_schema_suffix"
                prompt0 = (
                    prompts["expand_idea_to_full_novel_story_prompt_base"].format(
                        user_idea=req.user_idea,
                    )
                    + "\n"
                    + prompts[suffix0]
                )
                if use_schema0:
                    expanded = await svc0.generate_structured(prompt0, ExpandIdeaSchema, **gen_kwargs)
                else:
                    raw0 = await svc0.generate_text(prompt0, **gen_kwargs)
                    expanded = await validate_and_fix_format(raw0, ExpandIdeaSchema, "expand_idea_to_full_novel_story")
                _log_workflow_event(
                    request_id,
                    "expand_idea",
                    "done",
                    provider=provider0 or "unresolved",
                    elapsed_ms=int((time.perf_counter() - step_started_at) * 1000),
                )
                yield _sse_event("step", {"step": "expand_idea", "status": "done", "data": expanded.model_dump()})
            except Exception as e:
                logger.exception(
                    "[create_novel_by_ai] request_id=%s step=%s failed provider=%s",
                    request_id,
                    "expand_idea",
                    provider0 or "unresolved",
                )
                yield _sse_event("step", {"step": "expand_idea", "status": "error", "error": str(e)})
                yield _sse_event("done", {"success": False, "failed_step": "expand_idea", "partial_result": _build_ai_create_result(expanded, idea, seed, meta)})
                return

        # Step 2: Extract Idea
        if cached_idea := cached_prefix.get("extract_idea"):
            idea = cached_idea  # type: ignore[assignment]
            _log_workflow_event(request_id, "extract_idea", "cached")
            yield _sse_event("step", {"step": "extract_idea", "status": "done", "cached": True, "data": idea.model_dump()})
        else:
            yield _sse_event("step", {"step": "extract_idea", "status": "running"})
            step_started_at = time.perf_counter()
            provider1 = resolve_provider_for_step(WORKFLOW_NAME, "extract_idea") or ""
            timeout1 = resolve_timeout_for_step(WORKFLOW_NAME, "extract_idea")
            use_schema1 = _check_json_schema_support("extract_idea")
            _log_workflow_event(
                request_id,
                "extract_idea",
                "running",
                provider=provider1 or "unresolved",
                timeout_seconds=timeout1,
                json_schema=use_schema1,
            )
            try:
                svc1 = get_llm_service_for_step(WORKFLOW_NAME, "extract_idea")
                suffix1 = "extract_idea_prompt_with_schema_suffix" if use_schema1 else "extract_idea_prompt_without_schema_suffix"
                prompt1 = (
                    prompts["extract_idea_prompt_base"].format(
                        plot=expanded.plot,
                    )
                    + "\n"
                    + prompts[suffix1]
                )
                if use_schema1:
                    idea = await svc1.generate_structured(prompt1, ExtractIdeaSchema, **gen_kwargs)
                else:
                    raw1 = await svc1.generate_text(prompt1, **gen_kwargs)
                    idea = await validate_and_fix_format(raw1, ExtractIdeaSchema, "extract_idea")
                _log_workflow_event(
                    request_id,
                    "extract_idea",
                    "done",
                    provider=provider1 or "unresolved",
                    elapsed_ms=int((time.perf_counter() - step_started_at) * 1000),
                )
                yield _sse_event("step", {"step": "extract_idea", "status": "done", "data": idea.model_dump()})
            except Exception as e:
                logger.exception(
                    "[create_novel_by_ai] request_id=%s step=%s failed provider=%s",
                    request_id,
                    "extract_idea",
                    provider1 or "unresolved",
                )
                yield _sse_event("step", {"step": "extract_idea", "status": "error", "error": str(e)})
                yield _sse_event("done", {"success": False, "failed_step": "extract_idea", "partial_result": _build_ai_create_result(expanded, idea, seed, meta)})
                return

        # Step 3: Core Seed
        if cached_seed := cached_prefix.get("core_seed"):
            seed = cached_seed  # type: ignore[assignment]
            _log_workflow_event(request_id, "core_seed", "cached")
            yield _sse_event("step", {"step": "core_seed", "status": "done", "cached": True, "data": seed.model_dump()})
        else:
            yield _sse_event("step", {"step": "core_seed", "status": "running"})
            step_started_at = time.perf_counter()
            provider2 = resolve_provider_for_step(WORKFLOW_NAME, "core_seed") or ""
            timeout2 = resolve_timeout_for_step(WORKFLOW_NAME, "core_seed")
            use_schema2 = _check_json_schema_support("core_seed")
            _log_workflow_event(
                request_id,
                "core_seed",
                "running",
                provider=provider2 or "unresolved",
                timeout_seconds=timeout2,
                json_schema=use_schema2,
            )
            try:
                svc2 = get_llm_service_for_step(WORKFLOW_NAME, "core_seed")
                suffix2 = "core_seed_prompt_with_schema_suffix" if use_schema2 else "core_seed_prompt_without_schema_suffix"
                prompt2 = (
                    prompts["core_seed_prompt_base"].format(
                        plot=expanded.plot,
                        genre=idea.genre,
                        tone=idea.tone,
                        target_audience=idea.target_audience,
                        core_idea=idea.core_idea,
                        number_of_chapters=req.number_of_chapters,
                        words_per_chapter=req.words_per_chapter,
                    )
                    + "\n"
                    + prompts[suffix2]
                )
                if use_schema2:
                    seed = await svc2.generate_structured(prompt2, CoreSeedSchema, **gen_kwargs)
                else:
                    raw2 = await svc2.generate_text(prompt2, **gen_kwargs)
                    seed = await validate_and_fix_format(raw2, CoreSeedSchema, "core_seed")
                _log_workflow_event(
                    request_id,
                    "core_seed",
                    "done",
                    provider=provider2 or "unresolved",
                    elapsed_ms=int((time.perf_counter() - step_started_at) * 1000),
                )
                yield _sse_event("step", {"step": "core_seed", "status": "done", "data": seed.model_dump()})
            except Exception as e:
                logger.exception(
                    "[create_novel_by_ai] request_id=%s step=%s failed provider=%s",
                    request_id,
                    "core_seed",
                    provider2 or "unresolved",
                )
                yield _sse_event("step", {"step": "core_seed", "status": "error", "error": str(e)})
                yield _sse_event("done", {"success": False, "failed_step": "core_seed", "partial_result": _build_ai_create_result(expanded, idea, seed, meta)})
                return

        # Step 4: Novel Meta
        if cached_meta := cached_prefix.get("novel_meta"):
            meta = cached_meta  # type: ignore[assignment]
            _log_workflow_event(request_id, "novel_meta", "cached")
            yield _sse_event("step", {"step": "novel_meta", "status": "done", "cached": True, "data": meta.model_dump()})
        else:
            yield _sse_event("step", {"step": "novel_meta", "status": "running"})
            step_started_at = time.perf_counter()
            provider3 = resolve_provider_for_step(WORKFLOW_NAME, "novel_meta") or ""
            timeout3 = resolve_timeout_for_step(WORKFLOW_NAME, "novel_meta")
            use_schema3 = _check_json_schema_support("novel_meta")
            _log_workflow_event(
                request_id,
                "novel_meta",
                "running",
                provider=provider3 or "unresolved",
                timeout_seconds=timeout3,
                json_schema=use_schema3,
            )
            try:
                svc3 = get_llm_service_for_step(WORKFLOW_NAME, "novel_meta")
                suffix3 = "novel_meta_prompt_with_schema_suffix" if use_schema3 else "novel_meta_prompt_without_schema_suffix"
                prompt3 = (
                    prompts["novel_meta_prompt_base"].format(
                        plot=expanded.plot,
                        genre=idea.genre,
                        tone=idea.tone,
                        target_audience=idea.target_audience,
                        core_idea=idea.core_idea,
                        number_of_chapters=req.number_of_chapters,
                        words_per_chapter=req.words_per_chapter,
                        core_seed=seed.core_seed,
                    )
                    + "\n"
                    + prompts[suffix3]
                )
                if use_schema3:
                    meta = await svc3.generate_structured(prompt3, NovelMetaSchema, **gen_kwargs)
                else:
                    raw3 = await svc3.generate_text(prompt3, **gen_kwargs)
                    meta = await validate_and_fix_format(raw3, NovelMetaSchema, "novel_meta")
                _log_workflow_event(
                    request_id,
                    "novel_meta",
                    "done",
                    provider=provider3 or "unresolved",
                    elapsed_ms=int((time.perf_counter() - step_started_at) * 1000),
                )
                yield _sse_event("step", {"step": "novel_meta", "status": "done", "data": meta.model_dump()})
            except Exception as e:
                logger.exception(
                    "[create_novel_by_ai] request_id=%s step=%s failed provider=%s",
                    request_id,
                    "novel_meta",
                    provider3 or "unresolved",
                )
                yield _sse_event("step", {"step": "novel_meta", "status": "error", "error": str(e)})
                yield _sse_event("done", {"success": False, "failed_step": "novel_meta", "partial_result": _build_ai_create_result(expanded, idea, seed, meta)})
                return

        # All steps completed
        final_result = _build_ai_create_result(expanded, idea, seed, meta)
        _log_workflow_event(
            request_id,
            "workflow",
            "done",
            total_elapsed_ms=int((time.perf_counter() - workflow_start) * 1000),
        )
        yield _sse_event("done", {
            "success": True,
            "result": final_result,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
