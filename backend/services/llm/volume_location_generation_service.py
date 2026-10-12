"""读取正式单卷事实并生成按需地点本地候选。"""

from __future__ import annotations

from typing import Any

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.location_pydantic import VolumeLocationsGenerateRequestV1, VolumeLocationsResultV1
from backend.services.llm.volume_location_generation_context import (
    load_volume_location_generation_context,
)
from backend.services.llm.volume_location_generation_contract import build_volume_locations_generation_input, validate_volume_location_candidates
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.novel.errors import GenerationDomainError


VOLUME_LOCATION_INPUT_MAX_CHARS = 500_000
_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)


class VolumeLocationGenerationService:
    """单卷地点候选的正式输入、Provider 调用与业务后验入口。"""

    @staticmethod
    async def load_context(
        novel_id: str,
        volume_id: str,
        request: VolumeLocationsGenerateRequestV1,
    ) -> tuple[Any, dict[str, Any]]:
        """在 Provider 前读取并校验目标卷及全部正式输入。"""
        generation_input = build_volume_locations_generation_input(
            novel_id,
            volume_id,
            request,
        )
        context = await load_volume_location_generation_context(generation_input)
        ensure_text_budget(
            context["prompt_input"],
            max_chars=VOLUME_LOCATION_INPUT_MAX_CHARS,
            code="VOLUME_LOCATION_INPUT_BUDGET_EXCEEDED",
            label="单卷地点生成输入",
        )
        return generation_input, context


    @staticmethod
    def validate_result(
        result: VolumeLocationsResultV1,
        generation_input: Any,
        context: dict[str, Any],
    ) -> None:
        """复验数量、名称/别名、拓扑和规则/势力/父级白名单。"""
        try:
            validate_volume_location_candidates(
                result.locations,
                generation_input,
                context,
                require_generated_count=True,
            )
        except ValueError as exc:
            raise GenerationDomainError(
                "VOLUME_LOCATION_OUTPUT_INVALID",
                str(exc),
                status_code=502,
            ) from exc


__all__ = [
    "VOLUME_LOCATION_INPUT_MAX_CHARS",
    "VolumeLocationGenerationService",
]
