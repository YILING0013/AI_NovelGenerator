"""AI 创建小说路由：通过 3 步 LLM 管道从用户创意生成完整小说设定。"""

from __future__ import annotations

import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from application.services.llm.workflow_service import get_llm_service_for_step
from pydantic_definitions.novel_pydantic import (
    ExtractIdeaSchema,
    CoreSeedSchema,
    NovelMetaSchema,
)

router = APIRouter(prefix="/api/llm", tags=["llm"])

PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompt_definitions" / "prompt_default.yaml"
WORKFLOW_NAME = "create_novel_by_ai"


def _load_prompts() -> dict:
    """读取 prompt 定义文件。"""
    with PROMPT_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class AICreateNovelRequest(BaseModel):
    user_idea: str
    number_of_chapters: int = 100
    words_per_chapter: int = 3000


@router.post("/create-novel-by-ai")
async def create_novel_by_ai(req: AICreateNovelRequest):
    """3 步 LLM 管道：extract_idea → core_seed → novel_meta。"""
    prompts = _load_prompts().get("writing", {})

    # Step 1: Extract Idea
    try:
        svc1 = get_llm_service_for_step(WORKFLOW_NAME, "extract_idea")
        prompt1 = (
            prompts["extract_idea_prompt_base"].format(user_idea=req.user_idea)
            + "\n"
            + prompts["extract_idea_prompt_with_schema_suffix"]
        )
        idea: ExtractIdeaSchema = await svc1.generate_structured(prompt1, ExtractIdeaSchema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"extract_idea failed: {e}")

    # Step 2: Core Seed
    try:
        svc2 = get_llm_service_for_step(WORKFLOW_NAME, "core_seed")
        prompt2 = (
            prompts["core_seed_prompt_base"].format(
                plot=idea.plot,
                genre=idea.genre,
                tone=idea.tone,
                target_audience=idea.target_audience,
                core_idea=idea.core_idea,
                number_of_chapters=req.number_of_chapters,
                words_per_chapter=req.words_per_chapter,
            )
            + "\n"
            + prompts["core_seed_prompt_with_schema_suffix"]
        )
        seed: CoreSeedSchema = await svc2.generate_structured(prompt2, CoreSeedSchema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"core_seed failed: {e}")

    # Step 3: Novel Meta
    try:
        svc3 = get_llm_service_for_step(WORKFLOW_NAME, "novel_meta")
        prompt3 = (
            prompts["novel_meta_prompt_base"].format(
                plot=idea.plot,
                genre=idea.genre,
                tone=idea.tone,
                target_audience=idea.target_audience,
                core_idea=idea.core_idea,
                number_of_chapters=req.number_of_chapters,
                words_per_chapter=req.words_per_chapter,
                core_seed=seed.core_seed,
            )
            + "\n"
            + prompts["novel_meta_prompt_with_schema_suffix"]
        )
        meta: NovelMetaSchema = await svc3.generate_structured(prompt3, NovelMetaSchema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"novel_meta failed: {e}")

    return {
        "extract_idea": idea.model_dump(),
        "core_seed": seed.model_dump(),
        "novel_meta": meta.model_dump(),
    }
