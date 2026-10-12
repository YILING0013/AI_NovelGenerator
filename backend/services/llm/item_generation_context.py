"""物品 AI 生成与确认共用的确定性正式输入。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.item_repository import item_repo
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.llm.schemas.item_pydantic import ItemsGenerationInputV1, normalize_item_text
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateSourceRefV1,
)
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.novel.writing_context import character_design_content


ITEM_GENERATION_INPUT_MAX_CHARS = 200_000

NOVEL_PROMPT_FIELDS = (
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
)
CHARACTER_PROMPT_FIELDS = (
    "character_id",
    "name",
    "role_type",
    "identity",
    "appearance",
    "personality",
    "abilities",
    "story_function",
)
FACTION_PROMPT_FIELDS = (
    "faction_id",
    "name",
    "level_type",
    "volume_id",
    "positioning",
    "core_goal",
    "resources_and_advantages",
    "conflict_with_mainline",
)
LOCATION_PROMPT_FIELDS = (
    "location_id",
    "name",
    "aliases",
    "location_type",
    "parent_location_id",
    "description",
    "environment",
    "atmosphere",
    "geography",
    "story_function",
)
ITEM_PROMPT_FIELDS = (
    "item_id",
    "name",
    "aliases",
    "item_type",
    "description",
    "appearance",
    "origin",
    "abilities",
    "limitations",
    "costs",
    "owner_character_id",
    "controlling_faction_id",
    "current_location_id",
    "lifecycle_status",
    "story_function",
    "tags",
)


def _project(document: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """只保留允许进入物品提示词的正式字段。"""
    return {
        field: str(value) if isinstance(value := document.get(field), ObjectId) else value
        for field in fields
    }


async def load_item_generation_context(
    generation_input: ItemsGenerationInputV1,
    *,
    session: AsyncClientSession | None = None,
    allow_item_write_lock: bool = False,
) -> dict[str, Any]:
    """读取物品生成与确认共用的当前小说事实。

    Args:
        generation_input: 绑定小说和生成参数的严格输入。
        session: 可选 MongoDB 会话。
        allow_item_write_lock: 确认已持有当前小说物品写锁时允许继续读取。

    Returns:
        Prompt 数据、引用白名单、名称去重键与完整来源版本。
    """
    # WorldRuleService 会经地点领域反向引用物品服务，延迟导入可避免模块初始化成环。
    from backend.services.novel.world_rule_service import WorldRuleService

    novel_id = generation_input.novel_id
    novel = await novel_repo.get_novel_by_id(novel_id, session=session)
    if novel.get("item_write_lock_token") is not None and not allow_item_write_lock:
        raise DomainApiError(
            "ITEM_READ_CONFLICT",
            "物品正在更新，请稍后重试",
            status_code=409,
        )

    characters = [
        item
        for item in await character_repo.get_characters_by_novel(
            novel_id,
            session=session,
        )
        if item.get("status") == "active"
    ]
    factions = sorted(
        (
            item
            for item in await faction_repo.get_factions_by_novel(
                novel_id,
                session=session,
            )
            if item.get("active_status") == "active"
        ),
        key=lambda item: (int(item["sort_order"]), str(item["faction_id"])),
    )
    locations = [
        item
        for item in await location_repo.list_locations(
            novel_id,
            session=session,
        )
        if item.get("status") == "active"
        and item.get("location_order_pending_token") is None
    ]
    rule_context = await WorldRuleService.get_world_rule_context(
        novel_id,
        session=session,
    )
    world_rules = list(rule_context["active_rules"])
    items = await item_repo.list_items(novel_id, session=session)

    source_refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=novel_id,
            version=int(novel["version"]),
        )
    ]
    for resource_type, documents, id_field in (
        ("character", characters, "character_id"),
        ("faction", factions, "faction_id"),
        ("item", items, "item_id"),
        ("location", locations, "location_id"),
        ("world_rule", world_rules, "rule_id"),
    ):
        source_refs.extend(
            CandidateSourceRefV1(
                resource_type=resource_type,
                id=str(document[id_field]),
                version=int(document["version"]),
            )
            for document in documents
        )
    source_refs.sort(key=lambda source: (source.resource_type, source.id))
    if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
        raise DomainApiError(
            "ITEM_GENERATION_SOURCE_BUDGET_EXCEEDED",
            "物品生成使用的资料超过 2000 项，请先减少内容",
            status_code=422,
        )

    prompt_input = {
        "novel_profile": _project(novel, NOVEL_PROMPT_FIELDS),
        "active_world_rules": [
            _project(item, WORLD_RULE_PROMPT_FIELDS) for item in world_rules
        ],
        "characters": [character_design_content(item, CHARACTER_PROMPT_FIELDS) for item in characters],
        "factions": [_project(item, FACTION_PROMPT_FIELDS) for item in factions],
        "locations": [_project(item, LOCATION_PROMPT_FIELDS) for item in locations],
        "existing_items": [_project(item, ITEM_PROMPT_FIELDS) for item in items],
        "item_count": generation_input.item_count,
        "allow_incremental": generation_input.allow_incremental,
        "user_guidance": generation_input.user_guidance,
    }
    ensure_text_budget(
        prompt_input,
        max_chars=ITEM_GENERATION_INPUT_MAX_CHARS,
        code="ITEM_GENERATION_INPUT_BUDGET_EXCEEDED",
        label="物品生成输入",
    )
    return {
        "prompt_input": prompt_input,
        "source_refs": source_refs,
        "allowed_character_ids": {
            str(item["character_id"]) for item in characters
        },
        "allowed_faction_ids": {str(item["faction_id"]) for item in factions},
        "allowed_location_ids": {
            str(item["location_id"]) for item in locations
        },
        "existing_item_tokens": {
            normalize_item_text(value)
            for item in items
            for value in [str(item["name"]), *item.get("aliases", [])]
        },
    }


__all__ = [
    "ITEM_GENERATION_INPUT_MAX_CHARS",
    "load_item_generation_context",
]
