"""单卷地点生成的卷前资料与确认来源。"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.write_contracts import canonical_request_hash
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.character_volume_state_repository import (
    character_volume_state_repo,
)
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.faction_volume_state_repository import (
    faction_volume_state_repo,
)
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.repositories.world_rule_repository import world_rule_repo
from backend.llm.schemas.location_pydantic import (
    VolumeLocationsGenerationInputV1,
    normalize_location_text,
)
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateSourceRefV1,
)
from backend.services.novel.writing_context import character_position_content, position_content, resolve_writing_position


NOVEL_SUMMARY_FIELDS = (
    "title",
    "subtitle",
    "genre",
    "tags",
    "summary",
    "plot",
    "core_idea",
    "tone",
    "core_seed",
    "worldview",
    "writing_style",
    "narrative_pov",
    "era_background",
)
WORLD_RULE_FIELDS = (
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
    "version",
)
LOCATION_FIELDS = (
    "location_id",
    "name",
    "aliases",
    "location_type",
    "parent_location_id",
    "description",
    "environment",
    "atmosphere",
    "geography",
    "rules_and_constraints",
    "applicable_rule_ids",
    "associated_faction_ids",
    "story_function",
    "tags",
    "order_index",
    "version",
)


async def load_volume_location_generation_context(
    generation_input: VolumeLocationsGenerationInputV1,
    *,
    session: AsyncClientSession | None = None,
    allow_location_write_lock: bool = False,
    require_planning: bool = True,
) -> dict[str, Any]:
    """读取目标卷开始前的设计资料，原始来源只用于确认复验。

    Args:
        generation_input: 绑定小说、目标卷和用户选择的严格生成输入。
        session: 可选 MongoDB 会话，确认时用于同一写入快照。
        allow_location_write_lock: 确认流程已持有地点写锁时是否直接读取规则。
        require_planning: 正式生成要求已有卷规划，流程查看允许显示缺项。

    Returns:
        Prompt 投影、引用白名单、全局名称集合和精确来源版本。
    """
    # WorldRuleService 反向复用地点写锁；延迟导入可避免领域模块初始化成环。
    from backend.services.novel.world_rule_service import WorldRuleService

    novel_id = generation_input.novel_id
    volume_id = generation_input.volume_id
    novel = await novel_repo.get_novel_by_id(novel_id, session=session)
    volume = await volume_repo.get_volume_by_id(volume_id, session=session)
    if generation_input.selection_mode == "auto" and require_planning:
        from backend.services.novel.plot_service import require_preparation_stage
        await require_preparation_stage(novel_id, volume_id, "locations", session=session, allow_write_lock=allow_location_write_lock)
    if str(volume["novel_id"]) != novel_id:
        raise DomainApiError(
            "VOLUME_LOCATION_SOURCE_NOT_FOUND",
            "目标卷不存在于当前小说",
            status_code=404,
        )
    if require_planning and volume.get("planning") is None:
        raise DomainApiError(
            "VOLUME_LAUNCH_PACKAGE_REQUIRED",
            "目标卷尚未确认启动包，不能生成按需地点",
            status_code=404,
        )
    if generation_input.selection_mode != "auto" and int(volume["version"]) != generation_input.volume_expected_version:
        raise DomainApiError(
            "VOLUME_VERSION_CONFLICT",
            "目标卷版本已变化，请刷新后重新生成地点",
            status_code=409,
        )

    character_states = await character_volume_state_repo.list_by_volume(
        novel_id,
        volume_id,
        session=session,
    )
    faction_states = await faction_volume_state_repo.list_by_volume(
        novel_id,
        volume_id,
        session=session,
    )
    characters = {
        str(item["character_id"]): item
        for item in await character_repo.get_characters_by_novel(
            novel_id,
            session=session,
        )
        if item.get("status") == "active"
    }
    factions = {
        str(item["faction_id"]): item
        for item in await faction_repo.get_factions_by_novel(
            novel_id,
            session=session,
        )
        if item.get("active_status") == "active"
    }
    missing_character_ids = sorted(
        {
            str(item["character_id"])
            for item in character_states
            if str(item["character_id"]) not in characters
        }
    )
    missing_faction_ids = sorted(
        {
            str(item["faction_id"])
            for item in faction_states
            if str(item["faction_id"]) not in factions
        }
    )
    if missing_character_ids or missing_faction_ids:
        raise DomainApiError(
            "VOLUME_LOCATION_STATE_SOURCE_NOT_FOUND",
            "卷级参与状态引用的角色或势力已不存在或不可用",
            status_code=404,
            details={
                "character_ids": missing_character_ids,
                "faction_ids": missing_faction_ids,
            },
        )

    if allow_location_write_lock:
        world_rules = []
        for rule in await world_rule_repo.list_world_rules(
            novel_id,
            status="active",
            session=session,
        ):
            try:
                # 确认已经持有地点互斥，可直接复验作用域而不把自己的锁误判为外部写入。
                await WorldRuleService._validate_scope(
                    novel_id,
                    rule["scope_type"],
                    rule.get("scope_entity_ids") or [],
                    session=session,
                )
            except DomainApiError:
                continue
            world_rules.append(rule)
    else:
        rule_context = await WorldRuleService.get_world_rule_context(
            novel_id,
            session=session,
        )
        world_rules = list(rule_context["active_rules"])
    locations = [
        item
        for item in await location_repo.list_locations(
            novel_id,
            session=session,
        )
        if item.get("status") == "active"
        and item.get("location_order_pending_token") is None
    ]
    locations_by_id = {str(item["location_id"]): item for item in locations}
    missing_selected = [
        location_id
        for location_id in generation_input.selected_existing_location_ids
        if location_id not in locations_by_id
    ]
    if missing_selected:
        raise DomainApiError(
            "SELECTED_LOCATION_NOT_FOUND",
            "所选既有地点不存在、已删除、不可用或不属于当前小说",
            status_code=404,
            details={"location_ids": missing_selected},
        )

    source_refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=novel_id,
            version=int(novel["version"]),
        ),
        CandidateSourceRefV1(
            resource_type="volume",
            id=volume_id,
            version=int(volume["version"]),
        ),
    ]
    for resource_type, documents, id_field in (
        ("world_rule", world_rules, "rule_id"),
        ("location", locations, "location_id"),
        ("character_volume_state", character_states, "state_id"),
        ("faction_volume_state", faction_states, "state_id"),
    ):
        source_refs.extend(
            CandidateSourceRefV1(
                resource_type=resource_type,
                id=str(document[id_field]),
                version=int(document["version"]),
            )
            for document in documents
        )
    for character_id in sorted({str(item["character_id"]) for item in character_states}):
        character = characters[character_id]
        source_refs.append(
            CandidateSourceRefV1(
                resource_type="character",
                id=character_id,
                version=int(character["version"]),
            )
        )
    for faction_id in sorted({str(item["faction_id"]) for item in faction_states}):
        faction = factions[faction_id]
        source_refs.append(
            CandidateSourceRefV1(
                resource_type="faction",
                id=faction_id,
                version=int(faction["version"]),
            )
        )
    source_refs.sort(key=lambda item: (item.resource_type, item.id))
    if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
        raise DomainApiError(
            "VOLUME_LOCATION_SOURCE_BUDGET_EXCEEDED",
            "单卷地点生成正式来源超过 2000 项，禁止静默截断",
            status_code=422,
        )

    from backend.services.novel.character_fact_service import read_character_facts
    facts = await read_character_facts(novel_id, sorted({str(state["character_id"]) for state in character_states}), {
        "target_type": "volume", "target_id": volume_id,
        "reading_intent": "replan", "reading_version": 1,
    }, session=session)
    character_facts = {row["character_id"]: row for row in facts["characters"]}
    character_state_input = []
    for state in character_states:
        character_id = str(state["character_id"])
        if character_id not in character_facts:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物在读取期间已变化，请重新读取", status_code=409)
        character_state_input.append(
            {
                "state_id": str(state["state_id"]),
                "character_name": characters[character_id]["name"],
                "version": state["version"],
                "character": character_position_content(characters[character_id], character_facts[character_id]),
                **position_content(state, "character_volume_state"),
            }
        )
    faction_state_input = []
    for state in faction_states:
        faction_id = str(state["faction_id"])
        faction_state_input.append(
            {
                "state_id": str(state["state_id"]),
                "faction_name": factions[faction_id]["name"],
                "level_type": factions[faction_id]["level_type"],
                "version": state["version"],
                **position_content(state, "faction_volume_state"),
            }
        )

    position = resolve_writing_position(
        {"target_type": "volume", "target_id": volume_id, "reading_intent": "replan", "reading_version": 1},
        {"volume": {volume["_id"]: volume}},
    )
    if facts["position"] != position:
        raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "卷顺序在读取期间已变化，请重新读取", status_code=409)
    location_input = {
        item["location_id"]: {"location_id": item["location_id"], "version": item["version"],
            "order_index": item["order_index"], **position_content(item, "location")}
        for item in locations
    }
    prompt_input = {
        "reading_semantics": "position",
        "position": position,
        "novel_summary": position_content(novel, "novel"),
        "volume_launch_package": {
            "volume_id": volume_id,
            "version": volume["version"],
            **position_content(volume, "volume"),
            "position": position,
        },
        "character_volume_states": character_state_input,
        "faction_volume_states": faction_state_input,
        "active_world_rules": [
            {"rule_id": item["rule_id"], **position_content(item, "world_rule")} for item in world_rules
        ],
        "existing_locations": list(location_input.values()),
        "selected_existing_locations": [
            location_input[location_id]
            for location_id in generation_input.selected_existing_location_ids
        ],
        "location_count": generation_input.location_count,
        "allow_incremental": generation_input.allow_incremental,
        "user_guidance": generation_input.user_guidance,
    }
    existing_location_tokens = {
        normalize_location_text(value)
        for item in locations
        for value in [str(item["name"]), *(item.get("aliases") or [])]
    }
    data = {
        "novel": novel,
        "volume": volume,
        "character_states": character_states,
        "faction_states": faction_states,
        "world_rules": world_rules,
        "locations": locations,
        "source_refs": source_refs,
        "prompt_input": prompt_input,
        "allowed_rule_ids": {str(item["rule_id"]) for item in world_rules},
        "allowed_faction_ids": {
            str(item["faction_id"]) for item in faction_states
        },
        "allowed_location_ids": set(locations_by_id),
        "existing_location_tokens": existing_location_tokens,
        "fact_reads": facts["reads"],
    }
    if require_planning and generation_input.selection_mode == "auto":
        from backend.services.novel.plot_service import preparation_content_fingerprint
        sources = [("novel", novel), ("volume", volume)]
        for kind, documents in (("world_rule", world_rules), ("location", locations), ("character_volume_state", character_states), ("faction_volume_state", faction_states)):
            sources.extend((kind, document) for document in documents)
        sources.extend(("character", characters[identity]) for identity in {str(state["character_id"]) for state in character_states})
        sources.extend(("faction", factions[identity]) for identity in {str(state["faction_id"]) for state in faction_states})
        data["content_fingerprint"] = canonical_request_hash({
            "reading_contract": "position_v1", "position": position,
            "source_content_fingerprint": preparation_content_fingerprint(
                sources, character_facts=list(character_facts.values()), fact_reads=facts["reads"],
            ),
        })
    return data


__all__ = ["load_volume_location_generation_context"]
