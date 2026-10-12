"""读取小说正式资料并生成浏览器本地物品候选。"""

from __future__ import annotations

from typing import Any

from backend.llm.schemas.item_pydantic import ItemsResultV1
from backend.services.llm.item_generation_contract import validate_item_candidates
from backend.services.novel.errors import GenerationDomainError


class ItemGenerationService:
    """小说物品候选的正式输入、生成和业务校验入口。"""


    @staticmethod
    def validate_result(
        result: ItemsResultV1,
        generation_input: Any,
        context: dict[str, Any],
    ) -> None:
        """把物品候选业务后验失败统一映射为模型结果错误。"""
        try:
            validate_item_candidates(
                result.items,
                generation_input,
                context,
                require_generated_count=True,
            )
        except ValueError as exc:
            raise GenerationDomainError(
                "ITEM_GENERATION_OUTPUT_INVALID",
                str(exc),
                status_code=502,
            ) from exc


__all__ = ["ItemGenerationService"]
