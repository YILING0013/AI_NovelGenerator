"""读取正式小说事实并生成核心世界规则浏览器本地候选。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.world_rule_repository import (
    normalize_world_rule_name,
    world_rule_repo,
)
from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesGenerationInputV1, CoreWorldRulesResultV1
from backend.services.llm.candidate_contract import MAX_CANDIDATE_SOURCE_REFS
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.llm.world_rule_generation_contract import build_core_world_rules_source_refs
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.writing_context import character_design_content


CORE_WORLD_RULE_INPUT_MAX_CHARS = 200_000

NOVEL_SUMMARY_FIELDS = (
    "title",
    "subtitle",
    "genre",
    "tags",
    "summary",
    "core_seed",
    "worldview",
    "writing_style",
    "narrative_pov",
    "era_background",
)
CHARACTER_PROMPT_FIELDS = (
    "character_id",
    "name",
    "role_type",
    "identity",
    "core_desire",
    "core_fear",
    "story_function",
    "status",
)
FACTION_PROMPT_FIELDS = (
    "faction_id",
    "name",
    "positioning",
    "core_goal",
    "conflict_with_mainline",
    "active_status",
    "level_type",
)
FACTION_RELATION_PROMPT_FIELDS = (
    "relation_id",
    "source_faction_id",
    "target_faction_id",
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "intensity",
    "is_active",
)
WORLD_RULE_PROMPT_FIELDS = (
    "rule_id",
    "name",
    "category",
    "statement",
    "scope_type",
    "scope_entity_ids",
    "enforcement",
    "exceptions",
    "costs_and_consequences",
    "priority",
    "tags",
    "status",
)


def _project(document: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """提取允许进入核心规则 Prompt 的正式字段。"""
    return {field: document.get(field) for field in fields}


def _normalize_statement(value: str) -> str:
    """生成规则陈述的 NFKC、空白折叠和大小写唯一键。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).strip()).casefold()


class WorldRuleGenerationService:
    """核心世界规则候选的正式输入、生成和业务后验入口。"""

    @staticmethod
    async def load_context(
        generation_input: CoreWorldRulesGenerationInputV1,
        *,
        session: AsyncClientSession | None = None,
        require_readiness: bool = True,
    ) -> dict[str, Any]:
        """读取生成与确认共同依赖的当前正式世界事实。

        Args:
            generation_input: 包含小说 ID 与原始生成参数的严格输入。
            session: 确认写入单元可复用的 MongoDB 会话。
            require_readiness: 是否要求当前已有活动核心势力和主角。

        Returns:
            Prompt 投影、引用白名单、去重集合与稳定来源版本。
        """
        novel_id = generation_input.novel_id
        novel = await novel_repo.get_novel_by_id(novel_id, session=session)
        characters = [
            item
            for item in await character_repo.get_characters_by_novel(
                novel_id,
                session=session,
            )
            if item.get("status") == "active"
        ]
        protagonists = [
            item for item in characters if item.get("role_type") == "protagonist"
        ]
        factions = await faction_repo.get_active_core_factions(
            novel_id,
            session=session,
        )
        faction_ids = {str(item["faction_id"]) for item in factions}
        faction_relations = [
            item
            for item in await faction_relation_repo.get_relations_by_novel(
                novel_id,
                active_only=True,
                session=session,
            )
            if item.get("source_faction_id") in faction_ids
            and item.get("target_faction_id") in faction_ids
        ]
        world_rules = await world_rule_repo.list_world_rules(
            novel_id,
            status="active",
            session=session,
        )
        if require_readiness and (not factions or not protagonists):
            raise GenerationDomainError(
                "WORLD_RULE_READINESS_REQUIRED",
                "生成核心世界规则前必须已有活动核心势力和活动主角",
                status_code=422,
            )

        source_refs = build_core_world_rules_source_refs(
            novel,
            characters,
            factions,
            faction_relations,
            world_rules,
        )
        if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
            raise GenerationDomainError(
                "WORLD_RULE_GENERATION_SOURCE_BUDGET_EXCEEDED",
                "核心世界规则生成正式来源版本超过 2000 项，禁止静默截断",
                status_code=422,
            )

        prompt_input = {
            "novel_summary": _project(novel, NOVEL_SUMMARY_FIELDS),
            "protagonists": [
                character_design_content(item, CHARACTER_PROMPT_FIELDS) for item in protagonists
            ],
            "characters": [
                character_design_content(item, CHARACTER_PROMPT_FIELDS) for item in characters
            ],
            "factions": [_project(item, FACTION_PROMPT_FIELDS) for item in factions],
            "faction_relations": [
                _project(item, FACTION_RELATION_PROMPT_FIELDS)
                for item in faction_relations
            ],
            "existing_world_rules": [
                _project(item, WORLD_RULE_PROMPT_FIELDS) for item in world_rules
            ],
            "core_rule_count": generation_input.core_rule_count,
            "allow_incremental": generation_input.allow_incremental,
            "user_guidance": generation_input.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=CORE_WORLD_RULE_INPUT_MAX_CHARS,
            code="WORLD_RULE_GENERATION_INPUT_BUDGET_EXCEEDED",
            label="核心世界规则生成输入",
        )
        return {
            "prompt_input": prompt_input,
            "source_refs": source_refs,
            "allowed_character_ids": {
                str(item["character_id"]) for item in characters
            },
            "allowed_faction_ids": faction_ids,
            "existing_normalized_names": {
                str(item["normalized_name"]) for item in world_rules
            },
            "existing_normalized_statements": {
                _normalize_statement(str(item["statement"])) for item in world_rules
            },
        }


    @staticmethod
    def validate_result(
        result: CoreWorldRulesResultV1,
        generation_input: CoreWorldRulesGenerationInputV1,
        context: dict[str, Any],
    ) -> None:
        """执行数量、规范名、语义陈述和作用域引用业务后验。

        Args:
            result: 已通过严格 Pydantic Schema 的模型结果。
            generation_input: 当前请求的严格生成输入。
            context: 生成前读取的正式事实与引用白名单。

        Returns:
            全部业务约束通过时返回 None。
        """
        errors: list[str] = []
        if len(result.core_world_rules) != generation_input.core_rule_count:
            errors.append(
                f"候选数量必须严格等于 {generation_input.core_rule_count}"
            )
        normalized_names = [
            normalize_world_rule_name(item.name)[1]
            for item in result.core_world_rules
        ]
        if len(normalized_names) != len(set(normalized_names)):
            errors.append("候选规则名称在 Unicode 规范化后重复")
        if set(normalized_names) & context["existing_normalized_names"]:
            errors.append("候选规则与已有活动规则重名")

        normalized_statements = [
            _normalize_statement(item.statement) for item in result.core_world_rules
        ]
        if len(normalized_statements) != len(set(normalized_statements)):
            errors.append("候选规则陈述在规范化后重复")
        if set(normalized_statements) & context["existing_normalized_statements"]:
            errors.append("候选规则与已有活动规则陈述重复")

        for item in result.core_world_rules:
            if item.scope_type == "faction":
                invalid_ids = sorted(
                    set(item.scope_entity_ids) - context["allowed_faction_ids"]
                )
            elif item.scope_type == "character":
                invalid_ids = sorted(
                    set(item.scope_entity_ids) - context["allowed_character_ids"]
                )
            else:
                invalid_ids = []
            if invalid_ids:
                errors.append(
                    f"{item.candidate_ref} 引用了输入白名单外实体: {', '.join(invalid_ids)}"
                )
        if errors:
            raise GenerationDomainError(
                "WORLD_RULE_GENERATION_OUTPUT_INVALID",
                "; ".join(errors),
                status_code=502,
            )


__all__ = [
    "CORE_WORLD_RULE_INPUT_MAX_CHARS",
    "WorldRuleGenerationService",
]
