"""AI 创建小说路由：通过 4 步 LLM 管道从用户创意生成完整小说设定（SSE 流式状态推送）。"""

from __future__ import annotations

import json
import logging
import time
import yaml
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.llm.config import get_provider_config
from application.services.llm.workflow_service import get_llm_service_for_step, resolve_provider_for_step
from application.services.llm.format_review_service import validate_and_fix_format
from pydantic_definitions.novel_pydantic import (
    ExpandIdeaSchema,
    ExtractIdeaSchema,
    CoreSeedSchema,
    NovelMetaSchema,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompt_definitions" / "prompt_default.yaml"
WORKFLOW_NAME = "create_novel_by_ai"
logger = logging.getLogger(__name__)


def _load_prompts() -> dict:
    """读取 prompt 定义文件。"""
    with PROMPT_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _check_json_schema_support(step_name: str) -> bool:
    """检查指定步骤对应的 Provider 是否支持 JSON Schema 输出。"""
    provider = resolve_provider_for_step(WORKFLOW_NAME, step_name)
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


class AICreateNovelRequest(BaseModel):
    user_idea: str
    number_of_chapters: int = 100
    words_per_chapter: int = 3000
    # 可选生成参数，前端传入时覆盖 provider 级别默认值
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None)


def _build_gen_kwargs(req: AICreateNovelRequest) -> dict:
    """从请求中提取非空的生成参数，用于传入 LLMService。"""
    kwargs: dict = {}
    for key in ("temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty", "system_prompt"):
        val = getattr(req, key)
        if val is not None:
            kwargs[key] = val
    return kwargs


@router.post("/create-novel-by-ai")
async def create_novel_by_ai(req: AICreateNovelRequest):
    """4 步 LLM 管道（SSE 流式）：expand_idea → extract_idea → core_seed → novel_meta。"""

    async def event_stream() -> AsyncGenerator[str, None]:
        request_id = uuid4().hex[:8]
        workflow_start = time.perf_counter()
        prompts = _load_prompts().get("create_novel_by_ai", {})
        gen_kwargs = _build_gen_kwargs(req)
        _log_workflow_event(
            request_id,
            "workflow",
            "started",
            idea_chars=len(req.user_idea),
            number_of_chapters=req.number_of_chapters,
            words_per_chapter=req.words_per_chapter,
            overrides=sorted(gen_kwargs.keys()),
        )

        # Step 1: Expand Idea to Full Novel Story
        yield _sse_event("step", {"step": "expand_idea", "status": "running"})
        step_started_at = time.perf_counter()
        provider0 = resolve_provider_for_step(WORKFLOW_NAME, "expand_idea_to_full_novel_story") or ""
        use_schema0 = _check_json_schema_support("expand_idea_to_full_novel_story")
        _log_workflow_event(
            request_id,
            "expand_idea",
            "running",
            provider=provider0 or "unresolved",
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
                expanded: ExpandIdeaSchema = await svc0.generate_structured(prompt0, ExpandIdeaSchema, **gen_kwargs)
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
            yield _sse_event("done", {"success": False})
            return

        # Step 2: Extract Idea
        yield _sse_event("step", {"step": "extract_idea", "status": "running"})
        step_started_at = time.perf_counter()
        provider1 = resolve_provider_for_step(WORKFLOW_NAME, "extract_idea") or ""
        use_schema1 = _check_json_schema_support("extract_idea")
        _log_workflow_event(
            request_id,
            "extract_idea",
            "running",
            provider=provider1 or "unresolved",
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
                idea: ExtractIdeaSchema = await svc1.generate_structured(prompt1, ExtractIdeaSchema, **gen_kwargs)
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
            yield _sse_event("done", {"success": False})
            return

        # Step 3: Core Seed
        yield _sse_event("step", {"step": "core_seed", "status": "running"})
        step_started_at = time.perf_counter()
        provider2 = resolve_provider_for_step(WORKFLOW_NAME, "core_seed") or ""
        use_schema2 = _check_json_schema_support("core_seed")
        _log_workflow_event(
            request_id,
            "core_seed",
            "running",
            provider=provider2 or "unresolved",
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
                seed: CoreSeedSchema = await svc2.generate_structured(prompt2, CoreSeedSchema, **gen_kwargs)
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
            yield _sse_event("done", {"success": False})
            return

        # Step 4: Novel Meta
        yield _sse_event("step", {"step": "novel_meta", "status": "running"})
        step_started_at = time.perf_counter()
        provider3 = resolve_provider_for_step(WORKFLOW_NAME, "novel_meta") or ""
        use_schema3 = _check_json_schema_support("novel_meta")
        _log_workflow_event(
            request_id,
            "novel_meta",
            "running",
            provider=provider3 or "unresolved",
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
                meta: NovelMetaSchema = await svc3.generate_structured(prompt3, NovelMetaSchema, **gen_kwargs)
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
            yield _sse_event("done", {"success": False})
            return

        # All steps completed
        _log_workflow_event(
            request_id,
            "workflow",
            "done",
            total_elapsed_ms=int((time.perf_counter() - workflow_start) * 1000),
        )
        yield _sse_event("done", {
            "success": True,
            "result": {
                "expand_idea": expanded.model_dump(),
                "extract_idea": idea.model_dump(),
                "core_seed": seed.model_dump(),
                "novel_meta": meta.model_dump(),
            },
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
