"""卷骨架的全书设计资料与启动包的卷前资料。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.repositories.character_faction_binding_repository import (
    character_faction_binding_repo,
)
from backend.db.repositories.character_relation_repository import character_relation_repo
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateSourceRefV1,
)
from backend.services.novel.world_rule_service import WorldRuleService
from backend.services.novel.writing_context import (
    character_design_content, character_position_content, character_relation_design_content, character_relation_position_content,
    position_content, read_character_relation_context, resolve_writing_position,
    faction_design_content, faction_position_content,
)


NOVEL_PROMPT_FIELDS = (
    "title",
    "subtitle",
    "genre",
    "tags",
    "summary",
    "plot",
    "core_idea",
    "tone",
    "core_seed",
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
CHARACTER_RELATION_PROMPT_FIELDS = (
    "relation_id",
    "source_character_id",
    "target_character_id",
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "intensity",
    "is_active",
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
BINDING_PROMPT_FIELDS = (
    "binding_id",
    "character_id",
    "faction_id",
    "membership_type",
    "role_title",
    "public_status",
    "notes",
    "loyalty_level",
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
VOLUME_PROMPT_FIELDS = (
    "title",
    "subtitle",
    "summary",
    "goal",
    "theme",
    "order_index",
    "status",
    "planning",
    "version",
)


async def load_volume_planning_context(
    novel_id: str,
    *,
    target_volume_id: str | None = None,
    session: AsyncClientSession | None = None,
) -> dict[str, Any]:
    """读取卷骨架设计资料；指定目标卷时省略没有适用位置的旧叙述。

    Args:
        novel_id: 当前小说 ObjectId 字符串。
        target_volume_id: 启动包目标卷；提供时只把目标及直接相邻卷纳入输入。
        session: 可选 MongoDB 会话；确认流程用它保持同一写入快照。

    Returns:
        Prompt 投影、活动实体白名单、卷文档和精确来源版本。
    """
    novel_id = novel_id.lower()
    if target_volume_id is not None:
        target_volume_id = target_volume_id.lower()
    novel = await novel_repo.get_novel_by_id(novel_id, session=session)
    characters = [
        item
        for item in await character_repo.get_characters_by_novel(
            novel_id,
            session=session,
        )
        if item.get("status") == "active"
    ]
    character_ids = {str(item["character_id"]) for item in characters}
    protagonists = [
        item for item in characters if item.get("role_type") == "protagonist"
    ]
    factions = await faction_repo.get_active_core_factions(
        novel_id,
        session=session,
    )
    faction_ids = {str(item["faction_id"]) for item in factions}
    character_relations = [
        item
        for item in await character_relation_repo.list_relations(
            novel_id,
            is_active=True,
            session=session,
        )
        if str(item.get("source_character_id")) in character_ids
        and str(item.get("target_character_id")) in character_ids
    ]
    faction_relations = [
        item
        for item in await faction_relation_repo.get_relations_by_novel(
            novel_id,
            active_only=True,
            session=session,
        )
        if str(item.get("source_faction_id")) in faction_ids
        and str(item.get("target_faction_id")) in faction_ids
    ]
    bindings = [
        item
        for item in await character_faction_binding_repo.list_bindings(
            novel_id,
            is_active=True,
            session=session,
        )
        if str(item.get("character_id")) in character_ids
        and str(item.get("faction_id")) in faction_ids
    ]
    all_volumes = await volume_repo.get_volumes_by_novel(
        novel_id,
        session=session,
    )
    volumes = all_volumes
    if target_volume_id is not None:
        target_index = next(
            (
                index
                for index, item in enumerate(all_volumes)
                if str(item["_id"]) == target_volume_id
            ),
            None,
        )
        if target_index is None:
            raise DomainApiError(
                "VOLUME_NOT_FOUND",
                "目标卷不存在于当前小说或不在活动集合中",
                status_code=404,
            )
        volumes = all_volumes[
            max(0, target_index - 1) : min(len(all_volumes), target_index + 2)
        ]
    rule_context = await WorldRuleService.get_world_rule_context(
        novel_id,
        session=session,
    )
    world_rules = list(rule_context["active_rules"])

    source_refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=novel_id,
            version=int(novel["version"]),
        )
    ]
    for resource_type, documents, id_field in (
        ("volume", volumes, "_id"),
        ("world_rule", world_rules, "rule_id"),
        ("character", characters, "character_id"),
        ("faction", factions, "faction_id"),
        ("character_relation", character_relations, "relation_id"),
        ("faction_relation", faction_relations, "relation_id"),
        ("character_faction_binding", bindings, "binding_id"),
    ):
        source_refs.extend(
            CandidateSourceRefV1(
                resource_type=resource_type,
                id=str(document[id_field]),
                version=int(document["version"]),
            )
            for document in documents
        )
    source_refs.sort(key=lambda item: (item.resource_type, item.id))
    if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
        raise DomainApiError(
            "VOLUME_PLANNING_SOURCE_BUDGET_EXCEEDED",
            "卷规划正式来源超过 2000 项，禁止静默截断",
            status_code=422,
        )

    position = None
    fact_reads = []
    character_facts = {}
    relation_facts = {}
    faction_facts = {}
    if target_volume_id is not None:
        position = resolve_writing_position(
            {"target_type": "volume", "target_id": target_volume_id, "reading_intent": "replan", "reading_version": 1},
            {"volume": {item["_id"]: item for item in volumes}},
        )
        from backend.services.novel.character_fact_service import read_character_facts
        facts = await read_character_facts(novel_id, sorted(character_ids), {
            "target_type": "volume", "target_id": target_volume_id,
            "reading_intent": "replan", "reading_version": 1,
        }, session=session)
        if facts["position"] != position:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
        fact_reads = facts["reads"]
        character_facts = {row["character_id"]: row for row in facts["characters"]}
        relation_facts, relation_reads, relation_position = await read_character_relation_context(
            novel_id, sorted(item["relation_id"] for item in character_relations), {
                "target_type": "volume", "target_id": target_volume_id,
                "reading_intent": "replan", "reading_version": 1,
            }, session=session,
        )
        if relation_position != position:
            raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
        fact_reads = [*fact_reads, *relation_reads]
        from backend.services.novel.faction_fact_service import read_faction_facts
        faction_result = await read_faction_facts(novel_id, sorted(faction_ids), {
            "target_type": "volume", "target_id": target_volume_id,
            "reading_intent": "replan", "reading_version": 1,
        }, session=session)
        if faction_result["position"] != position:
            raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
        faction_facts = {row["faction_id"]: row for row in faction_result["factions"]}
        if faction_ids != faction_facts.keys():
            raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力在读取期间已变化，请重新读取", status_code=409)
        fact_reads.extend(faction_result["reads"])

    def project(document: dict[str, Any], kind: str, fields: Sequence[str]) -> dict[str, Any]:
        """启动包共用位置投影；骨架允许全书设计资料，但不称为章前事实。"""
        if position is not None:
            if kind == "character":
                facts = character_facts.get(document["character_id"])
                if facts is None:
                    raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物在读取期间已变化，请重新读取", status_code=409)
                result = character_position_content(document, facts)
            elif kind == "character_relation":
                result = character_relation_position_content(document, relation_facts[document["relation_id"]])
            elif kind == "faction":
                result = faction_position_content(document, faction_facts[document["faction_id"]])
            else:
                result = position_content(document, kind)
            # 原提示词以这些业务 ID 引用资料，安全投影不改变引用名称。
            id_field = {"character": "character_id", "faction": "faction_id", "world_rule": "rule_id"}.get(kind)
            if id_field is not None:
                result[id_field] = document[id_field]
            return result
        if kind == "character":
            return character_design_content(document, fields)
        if kind == "character_relation":
            return character_relation_design_content(document, fields)
        if kind == "faction":
            return faction_design_content(document, fields)
        return {**{field: document.get(field) for field in fields}, "content_semantics": "whole_book_design"}

    prompt_facts = {
        "novel_profile": {
            **project(novel, "novel", NOVEL_PROMPT_FIELDS),
            "reading_semantics": "position" if position is not None else "whole_book_design",
            "position": position,
        },
        "worldview_summary": rule_context["worldview_summary"],
        "active_world_rules": [
            project(item, "world_rule", WORLD_RULE_PROMPT_FIELDS) for item in world_rules
        ],
        "protagonists": [
            project(item, "character", CHARACTER_PROMPT_FIELDS) for item in protagonists
        ],
        "characters": [
            project(item, "character", CHARACTER_PROMPT_FIELDS) for item in characters
        ],
        "factions_and_relations": {
            "factions": [project(item, "faction", FACTION_PROMPT_FIELDS) for item in factions],
            "faction_relations": [
                project(item, "faction_relation", FACTION_RELATION_PROMPT_FIELDS)
                for item in faction_relations
            ],
            "character_relations": [
                project(item, "character_relation", CHARACTER_RELATION_PROMPT_FIELDS)
                for item in character_relations
            ],
            "character_faction_bindings": [
                project(item, "character_faction_binding", BINDING_PROMPT_FIELDS) for item in bindings
            ],
        },
        "existing_volumes": [
            {"volume_id": str(item["_id"]), **project(item, "volume", VOLUME_PROMPT_FIELDS)}
            for item in volumes
        ],
    }
    return {
        "novel": novel,
        "characters": characters,
        "protagonists": protagonists,
        "factions": factions,
        "character_relations": character_relations,
        "faction_relations": faction_relations,
        "bindings": bindings,
        "world_rules": world_rules,
        "volumes": volumes,
        "source_refs": source_refs,
        "prompt_facts": prompt_facts,
        "world_rule_diagnostics": rule_context["diagnostics"],
        "position": position,
        "fact_reads": fact_reads,
    }


def project_volume_launch_context(context: dict[str, Any], target_volume_id: str) -> dict[str, Any]:
    """将原启动读取结果缩成表单提醒，不再读库或返回提示词与确认依据。

    Args:
        context: 指定目标卷后 load_volume_planning_context 的实际结果。
        target_volume_id: 本次启动的卷 ID。
    Returns:
        目标卷、实际读取位置、范围计数及按实体归纳的未知原因。
    """
    target = next(row for row in context["volumes"] if str(row["_id"]) == target_volume_id)
    prompt = context["prompt_facts"]
    names = {row["character_id"]: row["name"] for row in context["characters"]}
    entities = []
    for kind, rows, id_field in (
        ("character", prompt["characters"], "character_id"),
        ("faction", prompt["factions_and_relations"]["factions"], "faction_id"),
        ("character_relation", prompt["factions_and_relations"]["character_relations"], "relation_id"),
    ):
        for row in rows:
            facts = row["facts"]
            name = (f'{names[row["source_character_id"]]} ↔ {names[row["target_character_id"]]}'
                    if kind == "character_relation" else row["name"])
            entities.append({"entity_type": kind, "entity_id": row[id_field], "name": name,
                "source_ids": sorted(set(facts["origins"].values())),
                "issues": [{"field": field, "reason": reason,
                    "blocking_source_ids": facts["blockers"].get(field, [])}
                    for field, reason in facts["unknown"].items()]})
    return {"novel_id": str(context["novel"]["_id"]), "volume_id": target_volume_id,
        "volume_title": target["title"], "position": context["position"],
        "counts": {key: len(context[key]) for key in (
            "characters", "factions", "character_relations", "faction_relations", "bindings", "world_rules", "volumes")},
        "entities": entities}


__all__ = ["load_volume_planning_context", "project_volume_launch_context"]
