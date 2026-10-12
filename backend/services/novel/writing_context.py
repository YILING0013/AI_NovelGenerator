"""读取当前部分的规划、实际前文和明确资料，不保存生成结果。"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from bson import ObjectId
from pydantic import ValidationError
from pymongo import UpdateOne
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import touch_dependency_endpoint_guards
from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.writing_pydantic import WRITING_TASKS, WritingGenerateInputV1
from backend.llm.schemas.volume_planning_pydantic import VolumePlanningV1, normalize_volume_text
from backend.llm.schemas.character_pydantic import CharacterCreateRequestV1
from backend.llm.schemas.location_pydantic import LocationCreateV1
from backend.llm.schemas.item_pydantic import ItemCreateV1
from backend.llm.schemas.novel_pydantic import CoreFactionSchema
from backend.llm.schemas.world_rule_pydantic import WorldRuleCandidateV1
from backend.llm.schemas.character_volume_state_pydantic import CharacterVolumeStateFieldsV1
from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumeStateFieldsV1
from backend.services.novel.writing_contract import WritingContextBasisV1, WritingReadinessV1
from backend.services.novel.character_fact_contract import CHARACTER_FACT_FIELDS, CharacterFactsAtPositionV1
from backend.services.novel.character_relation_fact_contract import CHARACTER_RELATION_FACT_FIELDS, CharacterRelationFactsAtPositionV1
from backend.services.novel.item_fact_contract import ITEM_FACT_FIELDS, ItemFactsAtPositionV1
from backend.services.novel.writing_position import PARENTS, fact_position_visible, writing_order


COLLECTIONS = {"novel": "novels", "volume": "volumes", "arc": "arcs", "scene": "scenes", "chapter": "chapters"}
ENTITY_FIELDS = {
    "character_ids": ("characters", "character", "character_id", "status"),
    "faction_ids": ("factions", "faction", "faction_id", "active_status"),
    "location_ids": ("locations", "location", "location_id", "status"),
    "item_ids": ("items", "item", "item_id", None),
    "rule_ids": ("world_rules", "world_rule", "rule_id", "status"),
}
PLAN_FIELDS = ("title", "subtitle", "summary", "goal", "theme", "planning", "plot")
NOVEL_FIELDS = ("title", "summary", "genre", "tags", "plot", "tone", "target_audience", "core_idea", "core_seed", "worldview", "writing_style", "narrative_pov", "era_background", "words_per_chapter")
# 只把作者能够编辑的资料送入模型；内部锁、统计和审计字段不属于内容依据。
ENTITY_CONTENT_FIELDS = {
    "character": set(CharacterCreateRequestV1.model_fields) - {"sort_order"} | {"status"},
    "faction": set(CoreFactionSchema.model_fields) - {"faction_ref"} | {"level_type", "volume_id", "active_status", "description", "faction_nature", "power_level", "geographical_scope", "parent_faction_id", "parent_faction_connection", "extra"},
    "location": set(LocationCreateV1.model_fields),
    "item": set(ItemCreateV1.model_fields),
    "world_rule": set(WorldRuleCandidateV1.model_fields) - {"rule_ref", "exceptions"} | {"rule_order", "status", "exceptions"},
    "character_volume_state": set(CharacterVolumeStateFieldsV1.model_fields) | {"volume_id", "character_id"},
    "faction_volume_state": set(FactionVolumeStateFieldsV1.model_fields) | {"volume_id", "faction_id"},
}
RESOURCE_COLLECTIONS = {**COLLECTIONS, **{kind: collection for collection, kind, _, _ in ENTITY_FIELDS.values()}, "character_volume_state": "character_volume_states", "faction_volume_state": "faction_volume_states", "character_relation": "character_relations"}
# 没有章节来源的旧叙述不当作当前位置的事实；只按字段职责保留索引和明确设计。
POSITION_INDEX_FIELDS = {
    "character": {"name", "aliases", "status", "importance_level", "is_core_character"},
    "faction": {"name", "level_type", "volume_id", "active_status"},
    "location": {"name", "aliases", "status"},
    "item": {"name", "aliases"},
    "world_rule": {"name", "category", "rule_order", "status"},
    "character_volume_state": {"volume_id", "character_id"},
    "faction_volume_state": {"volume_id", "faction_id"},
    "character_relation": {"relation_id", "source_character_id", "target_character_id", "relation_type", "is_active"},
    "faction_relation": {"relation_id", "source_faction_id", "target_faction_id", "relation_type", "is_active"},
    "character_faction_binding": {"binding_id", "character_id", "faction_id", "is_active"},
}
POSITION_PLAN_FIELDS = {
    "character": {"growth_direction", "arc_seed", "story_function", "conflict_with_mainline", "role_type"},
    "faction": {"expandability", "conflict_with_mainline"},
    "location": {"story_function", "rules_and_constraints", "applicable_rule_ids"},
    "item": {"story_function"},
    "world_rule": {"statement", "scope_type", "scope_entity_ids", "enforcement", "costs_and_consequences", "exceptions", "priority"},
    "character_volume_state": {"current_goal", "planned_end_state", "arc_progress", "participation_scope", "relationship_focus_ids"},
    "faction_volume_state": {"current_goal", "planned_end_state", "participation_scope"},
    "character_relation": {"possible_change", "story_value"},
    "faction_relation": {"possible_change", "story_value"},
    "character_faction_binding": set(),
}


def writing_content(document: dict[str, Any], kind: str) -> dict[str, Any]:
    """提取实际使用的白名单字段，排除整资源版本和派生统计。

    Args:
        document: 当前正式文档。
        kind: 小说、层级或实体类别。
    Returns:
        可稳定散列和展示的业务内容。
    """
    fields = NOVEL_FIELDS if kind == "novel" else PLAN_FIELDS if kind in COLLECTIONS else sorted(ENTITY_CONTENT_FIELDS[kind])
    result = {name: document[name] for name in fields if name in document}
    result.update(resource_type=kind, id=str(document["_id"]))
    if kind in PARENTS:
        result.update({name: str(document[name]) for name in ("novel_id", "volume_id", "arc_id", "scene_id") if name in document})
        result["order_index"] = document["order_index"]
    if kind == "volume":
        result["location_ids"] = document.get("location_ids", [])
    if kind not in COLLECTIONS:
        for _, (collection, entity_kind, id_field, _) in ENTITY_FIELDS.items():
            if entity_kind == kind:
                result["id"] = document[id_field]
    # 资料中的归属字段可能使用 BSON；统一为公开 JSON，不改变正文和数组顺序。
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


def position_content(document: dict[str, Any], kind: str) -> dict[str, Any]:
    """提供按位置生成可读的索引和设计，省略没有适用位置的旧叙述。

    Args:
        document: 已读取的正式资料；不会改写数据库。
        kind: 目录、实体、卷状态或关系类别。
    Returns:
        保留原字段形状并明确分类的资料，不把旧字段假定为初始事实。
    """
    if kind in COLLECTIONS:
        result = writing_content(document, kind)
        result["content_semantics"] = "design_plan"
        return result
    if kind == "character_faction_binding":
        all_fields = POSITION_INDEX_FIELDS[kind] | {"membership_type", "role_title", "public_status", "notes", "loyalty_level"}
        identity = document["binding_id"]
    elif kind in {"character_relation", "faction_relation"}:
        all_fields = {"relation_id", "source_character_id", "target_character_id", "source_faction_id", "target_faction_id", "relation_type", "current_state", "core_conflict", "hidden_tension", "possible_change", "story_value", "intensity", "description", "is_active"}
        identity = document["relation_id"]
    else:
        all_fields = ENTITY_CONTENT_FIELDS[kind]
        identity = next((document[field] for _, entity_kind, field, _ in ENTITY_FIELDS.values() if entity_kind == kind), str(document["_id"]))
    allowed = POSITION_INDEX_FIELDS[kind] | POSITION_PLAN_FIELDS[kind]
    result = {name: document[name] for name in sorted(allowed) if name in document}
    result.update(resource_type=kind, id=identity, content_semantics="design_plan",
                  design_plan_fields=sorted(POSITION_PLAN_FIELDS[kind] & document.keys()),
                  omitted_unlocated_fields=sorted((all_fields - allowed) & document.keys()))
    return json.loads(json.dumps(result, ensure_ascii=False, default=str))


def character_design_content(document: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """全书设计保留人物原文，但单列未指定位置的资料。

    Args:
        document: 当前人物主档，不据此推断任何剧情位置的事实。
        fields: 原消费者使用的字段白名单，不额外扩充模型输入。
    Returns:
        原索引和设计字段，以及明确未定位的主档参考原文。
    """
    result = {name: document.get(name) for name in fields if name not in CHARACTER_FACT_FIELDS}
    result["unlocated_profile"] = {name: document.get(name) for name in fields if name in CHARACTER_FACT_FIELDS}
    result["content_semantics"] = "whole_book_design_with_unlocated_profile"
    return result


def character_relation_design_content(document: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """全书设计保留关系原文，但单列没有剧情位置的状态。

    Args:
        document: 当前关系主档，不据此推断书初或最新关系事实。
        fields: 原消费者使用的字段白名单，不额外扩充模型输入。
    Returns:
        原索引和设计字段，以及明确未定位的关系状态原文。
    """
    result = {name: document.get(name) for name in fields if name not in CHARACTER_RELATION_FACT_FIELDS}
    result["unlocated_profile"] = {name: document.get(name) for name in fields if name in CHARACTER_RELATION_FACT_FIELDS}
    result["content_semantics"] = "whole_book_design_with_unlocated_profile"
    return result


def character_position_content(document: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """合并人物的明确位置事实与设计字段，保留未定位字段标记但不补裸值。

    Args:
        document: 当前人物主档，仅从中提取索引和明确设计。
        facts: 共享人物读取函数返回的该人物完整十五字段结果。
    Returns:
        可用于生成、检索和整理报告的同一份安全人物资料；不访问数据库。
    """
    parsed = CharacterFactsAtPositionV1.model_validate(facts)
    if (parsed.entity_id != str(document["_id"]) or parsed.character_id != document["character_id"]
            or parsed.name != document["name"]):
        raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物身份在读取期间已变化，请重新读取", status_code=409)
    value = position_content(document, "character")
    # 实体编辑版本供确认使用；模型事实依据不因无关编辑版本变化失效。
    value["facts"] = parsed.model_dump(exclude={"entity_id", "character_id", "name", "version"}, exclude_unset=True)
    value["content_semantics"] = "position_facts_and_design_plan"
    value["omitted_unlocated_fields"] = [name for name in value["omitted_unlocated_fields"] if name not in CHARACTER_FACT_FIELDS]
    return value


def character_relation_position_content(document: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """合并明确位置的关系状态和设计，未知时不补主档裸值。

    Args:
        document: 已读取的关系主档，只取身份和设计字段。
        facts: 关系事实服务返回的同一关系位置结果。
    Returns:
        普通上下文和工具共同使用的关系资料，不访问数据库。
    """
    parsed = CharacterRelationFactsAtPositionV1.model_validate(facts)
    if (parsed.entity_id != str(document["_id"]) or parsed.relation_id != document["relation_id"]
            or parsed.source_character_id != document["source_character_id"]
            or parsed.target_character_id != document["target_character_id"]):
        raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系身份在读取期间已变化，请重新读取", status_code=409)
    value = position_content(document, "character_relation")
    value["facts"] = parsed.model_dump(exclude={"entity_id", "relation_id", "source_character_id", "target_character_id", "version"}, exclude_unset=True)
    value["content_semantics"] = "position_facts_and_design_plan"
    value["omitted_unlocated_fields"] = [name for name in value["omitted_unlocated_fields"] if name != "current_state"]
    return value


def item_position_content(document: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """提供当前位置的完整物品组，未知或待复核时不补主档现值。

    Args:
        document: 当前物品主档，只使用身份与明确设计。
        facts: 共享读取服务返回的完整四字段或整组未知。
    Returns:
        写作、工具检索和摘要共用的安全资料，不访问数据库。
    """
    parsed = ItemFactsAtPositionV1.model_validate(facts)
    if (parsed.entity_id != str(document["_id"]) or parsed.item_id != document["item_id"]
            or parsed.name != document["name"] or parsed.version != document["version"]):
        raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品在读取期间已变化，请重新读取", status_code=409)
    value = position_content(document, "item")
    value["facts"] = parsed.model_dump(exclude={"entity_id", "item_id", "name", "version"})
    value["content_semantics"] = "position_facts_and_design_plan"
    value["omitted_unlocated_fields"] = [name for name in value["omitted_unlocated_fields"] if name not in ITEM_FACT_FIELDS]
    return value


async def read_item_context(novel_id: str, item_ids: list[str], scope: dict[str, Any], *, session: AsyncClientSession | None = None) -> tuple[dict, list, dict]:
    """分批读取原物品范围，检索分页前核对完整集合，空范围也保留。

    Args:
        novel_id: 当前小说。
        item_ids: 原选择或检索候选的业务 ID，缺失 ID 仍留在原读取中。
        scope: 服务端固定的明确位置。
        session: 可选调用方事务，各批使用同一事务。
    Returns:
        按业务 ID 的完整事实、各批原依据和共同位置。
    """
    from backend.services.novel.item_fact_service import read_item_facts

    facts, reads, position = {}, [], None
    for offset in range(0, max(1, len(item_ids)), 200):
        result = await read_item_facts(novel_id, item_ids[offset:offset + 200], scope,
            session=session if session is not None and session.in_transaction else None)
        if position is not None and position != result["position"]:
            raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品读取期间目录位置已变化，请重新读取", status_code=409)
        position = result["position"]
        facts.update((row["item_id"], row) for row in result["items"])
        reads.append(result["read"])
    return facts, reads, position


async def read_character_relation_context(novel_id: str, relation_ids: list[str], scope: dict[str, Any], *, session: AsyncClientSession | None = None) -> tuple[dict, list, dict]:
    """按服务的每批上限读取关系，空集合也保留一份原读取。

    Args:
        novel_id: 当前小说。
        relation_ids: 原关系查询的完整结果；调用方另行保存查询条件和分页。
        scope: 明确的章前后或父级位置。
        session: 可选的当前会话；有活动事务时各批复用同一事务。
    Returns:
        按关系 ID 的事实、所有批次原读取和共同位置。
    """
    from backend.services.novel.character_relation_fact_service import read_character_relation_facts

    facts, reads, position = {}, [], None
    for offset in range(0, max(1, len(relation_ids)), 200):
        result = await read_character_relation_facts(novel_id, relation_ids[offset:offset + 200], scope,
            session=session if session is not None and session.in_transaction else None)
        if position is not None and position != result["position"]:
            raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系读取期间目录位置已变化，请重新读取", status_code=409)
        position = result["position"]
        facts.update((row["relation_id"], row) for row in result["relations"])
        reads.extend(result["reads"])
    if set(relation_ids) != facts.keys():
        raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系在读取期间已变化，请重新读取", status_code=409)
    return facts, reads, position


async def revalidate_position_fact_reads(reads: list[dict[str, Any]], *, session: AsyncClientSession | None = None, protect: bool = False) -> None:
    """按人物、关系或物品种类复验原读取，拒绝未支持的事实种类。

    Args:
        reads: 原生成累计读取，不能用今天的新查询替换。
        session: 确认保存时的同一事务。
        protect: 保存时保护原来源和空查询；须在状态写锁之前执行。
    Returns:
        无；读取发生变化时保留原稿并报错。
    """
    characters, relations, items = [], [], []
    for read in reads:
        if read.get("kind") == "character_facts":
            characters.append(read)
        elif read.get("kind") == "character_relation_facts":
            relations.append(read)
        elif read.get("kind") == "item_facts":
            items.append(read)
        else:
            raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "事实读取种类不受支持，请保留草稿并重新读取", status_code=409)
    if characters:
        from backend.services.novel.character_fact_service import revalidate_character_fact_reads
        await revalidate_character_fact_reads(characters, session=session, protect=protect)
    if relations:
        from backend.services.novel.character_relation_fact_service import revalidate_character_relation_fact_reads
        await revalidate_character_relation_fact_reads(relations, session=session, protect=protect)
    if items:
        from backend.services.novel.item_fact_service import revalidate_item_fact_reads
        await revalidate_item_fact_reads(items, session=session, protect=protect)


def resolve_writing_position(scope: dict[str, Any], directories: dict[str, dict[ObjectId, dict[str, Any]]]) -> dict[str, Any]:
    """固定书初、章前后或父级起止位置，空父级仍使用其正式 ID。

    Args:
        scope: 服务端固定的目标及 reading_intent；缺省仅用于新的普通入口。
        directories: 本书四级活动目录。
    Returns:
        可保存进读取依据的明确位置和语义版本。
    """
    kind, identity = scope["target_type"], scope["target_id"]
    intent = scope.get("reading_intent") or ("chapter_before" if kind == "chapter" else "append")
    if kind == "novel":
        if (intent != "book_start" or scope.get("novel_id") is None
                or ObjectId(identity) != ObjectId(scope["novel_id"])):
            raise DomainApiError("WRITING_POSITION_INVALID", "书初位置必须指向当前小说", status_code=422)
        if type(scope.get("reading_version")) is not int or scope["reading_version"] != 1:
            raise DomainApiError("WRITING_POSITION_INVALID", "书初位置需要明确的读取版本", status_code=409)
        return {"version": 1, "intent": intent, "target_type": kind, "target_id": identity, "order": []}
    if intent not in ({"chapter_before", "chapter_after"} if kind == "chapter" else
                      {"volume_start", "append", "replan"} if kind == "volume" else {"append", "replan"}):
        raise DomainApiError("WRITING_POSITION_INVALID", "读取位置与当前操作不匹配", status_code=422)
    if scope.get("reading_version") not in (None, 1):
        raise DomainApiError("WRITING_POSITION_INVALID", "读取位置版本不支持，请重新生成", status_code=409)
    target = directories[kind].get(ObjectId(identity))
    order = writing_order(kind, target, directories) if target is not None else None
    if order is None:
        raise DomainApiError("WRITING_CONTEXT_CHANGED", "目录正在变化，请刷新当前部分", status_code=409)
    return {"version": 1, "intent": intent, "target_type": kind, "target_id": identity, "order": list(order)}


def chapter_visible_at_position(document: dict[str, Any], directories: dict[str, dict[ObjectId, dict[str, Any]]], position: dict[str, Any]) -> bool:
    """判断正文或实际证据是否在明确读取位置以内。

    Args:
        document: 证据或正文所属章节。
        directories: 本书完整活动目录。
        position: resolve_writing_position 返回的位置。
    Returns:
        章后包含当前章；追加包含父内已有章节；章前和重规划排除目标内正文。
    """
    if document.get("is_deleted") or document["_id"] not in directories["chapter"]:
        return False
    order = writing_order("chapter", document, directories)
    if order is None:
        return False
    boundary = tuple(position["order"])
    if position["intent"] == "append":
        return order[:len(boundary)] <= boundary
    return order <= boundary if position["intent"] == "chapter_after" else order < boundary


async def load_writing_parents(novel_id: str, target_type: str, target_id: str, *, session: AsyncClientSession | None = None, allow_write_lock: bool = False) -> list[tuple[str, dict[str, Any]]]:
    """按真实父指针读取活动父链，并校验每一级保存的祖先归属。

    Args:
        novel_id: 当前小说。
        target_type: 当前卷、篇章、场景或章节。
        target_id: 当前对象。
        session: 确认时使用同一个事务会话。
        allow_write_lock: 调用方已在同一事务持有资料写锁时允许继续读取。
    Returns:
        从小说到当前对象的完整 BSON 文档。
    """
    chain = []
    kind, identity = target_type, ObjectId(target_id)
    while True:
        query = {"_id": identity, "is_deleted": False}
        if kind != "novel":
            query["novel_id"] = ObjectId(novel_id)
        document = await BaseRepository(COLLECTIONS[kind]).collection.find_one(query, session=session)
        if document is None or (kind == "novel" and identity != ObjectId(novel_id)):
            raise DomainApiError("WRITING_TARGET_NOT_FOUND", "当前部分不存在、已回收或不属于当前小说", status_code=404)
        chain.append((kind, document))
        if kind == "novel":
            break
        kind = PARENTS[kind]
        identity = document[f"{kind}_id"]
    chain.reverse()
    if not allow_write_lock and any(chain[0][1].get(name) is not None for name in ("location_write_lock_token", "item_write_lock_token", "state_write_lock_token")):
        raise DomainApiError("WRITING_PARENT_BUSY", "当前小说资料正在保存，请稍后重试", status_code=409)
    ancestors = {kind: document["_id"] for kind, document in chain}
    for kind, document in chain:
        if any(document.get(f"{parent}_id") != identity for parent, identity in ancestors.items() if parent != kind and f"{parent}_id" in document):
            raise DomainApiError("WRITING_PARENT_MISMATCH", "当前部分的父级归属不一致", status_code=404)
    return chain


def volume_missing_fields(volume: dict[str, Any]) -> list[dict[str, str]]:
    """按已保存的卷内容列出开始下级规划前需要补齐的字段。

    Args:
        volume: 当前卷的数据库快照。
    Returns:
        沿用卷表单字段路径的缺项，不要求执行过 AI。
    """
    missing = {}
    if not isinstance(volume.get("goal"), str) or not volume["goal"].strip():
        missing["goal"] = "请填写当前卷的目标"
    planning = volume.get("planning") or {}
    labels = {"premise": "故事前提", "major_conflict": "主要冲突", "start_state": "起点", "end_state": "终点", "key_turning_points": "关键转折", "target_chapter_count": "目标章节数", "target_word_count": "目标字数"}
    try:
        VolumePlanningV1.model_validate(planning)
    except ValidationError as exc:
        for error in exc.errors():
            field = str(error["loc"][0])
            label = labels.get(field, field)
            context = error.get("ctx", {})
            message = f"请填写有效的{label}"
            if error["type"] == "string_too_long":
                message = f"{label}不能超过 {context['max_length']} 字"
            elif error["type"] == "too_long":
                message = f"{label}不能超过 {context['max_length']} 项"
            elif error["type"] == "greater_than_equal":
                message = f"{label}不能少于 {context['ge']}"
            elif error["type"] == "less_than_equal":
                message = f"{label}不能超过 {context['le']}"
            missing[f"planning.{field}"] = message
    for field in ("premise", "major_conflict", "start_state", "end_state"):
        path = f"planning.{field}"
        if path not in missing and not planning[field].strip():
            missing[path] = f"请填写当前卷的{labels[field]}"
    if "planning.key_turning_points" not in missing:
        points = [normalize_volume_text(value) for value in planning["key_turning_points"]]
        if not points or any(not value for value in points):
            missing["planning.key_turning_points"] = "请填写至少一个非空的关键转折"
        elif len(points) != len(set(points)):
            missing["planning.key_turning_points"] = "关键转折不能重复"
    return [{"field": field, "message": message} for field, message in missing.items()]


def require_volume_ready(volume: dict[str, Any]) -> None:
    """新建篇章、场景或章节前检查当前事务读到的卷内容。

    Args:
        volume: 与后续父级版本写入使用同一事务的卷快照。
    Returns:
        无；缺项时在业务写入前返回可定位的错误。
    """
    missing = volume_missing_fields(volume)
    if missing:
        raise DomainApiError("WRITING_NOT_READY", "请先补齐当前卷的规划", status_code=409, field_errors={item["field"]: item["message"] for item in missing})


def current_missing(chain: list[tuple[str, dict[str, Any]]]) -> list[dict[str, str]]:
    """新增下级检查当前卷和当前部分；已有章节正文不要求补做卷规划。

    Args:
        chain: 已验证的活动父链。
    Returns:
        当前缺项；上级卷字段以 volume. 开头，避免与当前表单混淆。
    """
    kind, target = chain[-1]
    if kind == "volume":
        return volume_missing_fields(target)
    missing = []
    if kind != "chapter":
        volume = next(document for part, document in chain if part == "volume")
        missing = [{**item, "field": f"volume.{item['field']}"} for item in volume_missing_fields(volume)]
    planning = target.get("planning") or {}
    required = {"planning.goal": planning.get("goal"), "planning.start_state": planning.get("start_state"), "planning.end_state": planning.get("end_state")}
    labels = {"planning.goal": "目标", "planning.start_state": "起点", "planning.end_state": "终点"}
    return missing + [{"field": field, "message": f"请填写当前部分的{labels[field]}"} for field, value in required.items() if not isinstance(value, str) or not value.strip()]


async def load_writing_context(task: str, parameters: dict[str, Any], scope: dict[str, Any], *, session: AsyncClientSession | None = None, check_ready: bool = True, parent_chain: list[tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    """构建四类任务共享的受控上下文，包含可复查的空查询。

    Args:
        task: 当前层级任务。
        parameters: 开始表单或图中传入的业务参数。
        scope: 路径固定的位置与显式选择。
        session: 确认事务会话；生成预览为空。
        check_ready: 是否阻断当前规划缺项；只读就绪接口为 False。
        parent_chain: 当前 session 的同一次活动事务中已校验且尚未修改的父链；位置相同才复用。
    Returns:
        输入、模型资料、来源说明、内容依据与事务写保护所需文档。
    """
    intent = scope.get("reading_intent") or ("chapter_before" if scope.get("target_type") == "chapter" else "append")
    # 模型和开始表单都不能把章前写作改成章后；剧情重规划由独立服务固定意图。
    if check_ready and task == "write_chapter_by_ai" and intent != "chapter_before":
        raise DomainApiError("WRITING_POSITION_INVALID", "章节写作必须读取本章开始前的资料", status_code=422)
    request = WritingGenerateInputV1.model_validate({**parameters, **scope, "reading_intent": intent, "reading_version": 1})
    if request.target_type != WRITING_TASKS[task][0]:
        raise DomainApiError("WRITING_TARGET_INVALID", "任务与当前部分不匹配", status_code=422)
    in_transaction = session is not None and session.in_transaction
    # 历史读取可能带有不同位置；只复用同一事务、同一目标的已校验父链。
    if (in_transaction and parent_chain
            and str(parent_chain[0][1]["_id"]) == request.novel_id
            and parent_chain[-1][0] == request.target_type
            and str(parent_chain[-1][1]["_id"]) == request.target_id):
        chain = parent_chain
    else:
        chain = await load_writing_parents(request.novel_id, request.target_type, request.target_id, session=session)
    missing = current_missing(chain)
    if check_ready and missing:
        raise DomainApiError("WRITING_NOT_READY", "请先补齐当前部分的规划", status_code=409, field_errors={item["field"]: item["message"] for item in missing})
    if check_ready and request.target_type != "chapter":
        plot_missing = await writing_plot_missing(chain, session=session)
        if plot_missing:
            raise DomainApiError("WRITING_PLOT_NOT_READY", "请先确认上级剧情和卷资料", status_code=409, field_errors={item["field"]: item["message"] for item in plot_missing})
    target = chain[-1][1]
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    guards: dict[tuple[str, str], dict[str, Any]] = {}
    reads = []
    character_facts = {}
    relation_facts = {}
    item_facts = {}

    def remember(kind: str, document: dict[str, Any]) -> dict[str, Any]:
        if kind == "character":
            facts = character_facts.get(document["character_id"])
            if facts is None:
                raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物在读取期间已变化，请重新读取", status_code=409)
            value = character_position_content(document, facts)
        elif kind == "character_relation":
            facts = relation_facts.get(document["relation_id"])
            if facts is None:
                raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系在读取期间已变化，请重新读取", status_code=409)
            value = character_relation_position_content(document, facts)
        elif kind == "item":
            facts = item_facts.get(document["item_id"])
            if facts is None:
                raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品在读取期间已变化，请重新读取", status_code=409)
            value = item_position_content(document, facts)
        else:
            value = position_content(document, kind)
        sources[(kind, value["id"])] = {"resource_type": kind, "id": value["id"], "version": document["version"]}
        guards[(RESOURCE_COLLECTIONS[kind], str(document["_id"]))] = document
        return value

    def observe(kind: str, query_scope: dict[str, Any], result: Any) -> None:
        reads.append({"kind": kind, "scope": query_scope, "fingerprint": canonical_request_hash(result)})

    plans = [remember(kind, document) for kind, document in chain]
    request = request.model_copy(update={"reading_intent": intent, "reading_version": 1})
    target_scope = {"novel_id": request.novel_id, "target_type": request.target_type, "target_id": request.target_id,
                    "reading_intent": intent, "reading_version": 1}
    observe("parent_chain", target_scope, plans)

    directories: dict[str, dict[ObjectId, dict[str, Any]]] = {}
    for kind in ("volume", "arc", "scene", "chapter"):
        # 目录不加载整书正文；只对选中的前章单独读取正文。
        cursor = BaseRepository(COLLECTIONS[kind]).collection.find({"novel_id": ObjectId(request.novel_id), "is_deleted": False}, {"content": 0}, session=session).limit(10001)
        documents = await cursor.to_list(length=10001)
        if len(documents) > 10000:
            raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "当前小说目录过大，请缩小写作范围", status_code=422)
        directories[kind] = {doc["_id"]: doc for doc in documents}

    position = resolve_writing_position(target_scope, directories)
    # 祖先重排和空目录新增同样会改变读取位置，不能仅冻结最后一章。
    directory_basis = [{"resource_type": kind, "id": str(document["_id"]),
                        "parent_id": str(document[f"{PARENTS[kind]}_id"]), "order_index": document["order_index"]}
                       for kind, documents in directories.items()
                       for document in sorted(documents.values(), key=lambda row: str(row["_id"]))]
    observe("reading_position", target_scope, {"position": position, "directory": directory_basis})
    parent_kind = PARENTS[request.target_type]
    siblings = sorted((doc for doc in directories[request.target_type].values() if doc[f"{parent_kind}_id"] == target[f"{parent_kind}_id"]), key=lambda doc: doc["order_index"])
    current_index = next((index for index, doc in enumerate(siblings) if doc["_id"] == target["_id"]), None)
    if current_index is None:
        raise DomainApiError("WRITING_CONTEXT_CHANGED", "目录正在变化，请刷新当前部分", status_code=409)
    neighbors = {"previous": remember(request.target_type, siblings[current_index - 1]) if current_index else None, "next": remember(request.target_type, siblings[current_index + 1]) if current_index + 1 < len(siblings) else None}
    observe("neighbors", target_scope, neighbors)
    child_kind = {"volume": "arc", "arc": "scene", "scene": "chapter"}.get(request.target_type)
    children = []
    if child_kind:
        children = [remember(child_kind, doc) for doc in sorted(directories[child_kind].values(), key=lambda doc: doc["order_index"]) if doc[f"{request.target_type}_id"] == target["_id"]]
    observe("children", {**target_scope, "child_type": child_kind}, children)

    visible_ids = [document["_id"] for document in directories["chapter"].values()
                   if chapter_visible_at_position(document, directories, position)]
    written = await BaseRepository("chapters").collection.find({"novel_id": ObjectId(request.novel_id), "_id": {"$in": visible_ids}, "is_deleted": False, "content": {"$regex": r"\S"}}, {"content": 0}, session=session).limit(10001).to_list(length=10001)
    prior = [(writing_order("chapter", doc, directories), doc) for doc in written
             if chapter_visible_at_position(doc, directories, position)]
    previous = None
    previous_basis = None
    if prior:
        key, document = max(prior, key=lambda item: item[0])
        document = await BaseRepository("chapters").collection.find_one({"_id": document["_id"], "is_deleted": False}, session=session)
        if document is None or not chapter_visible_at_position(document, directories, position):
            raise DomainApiError("WRITING_CONTEXT_CHANGED", "前章正在变化，请重试", status_code=409)
        value = remember("chapter", document)
        previous_basis = {"id": value["id"], "order": list(key), "summary": document.get("summary", ""), "content": document["content"]}
        previous = {"kind": "written_excerpt", "chapter_id": value["id"], "title": document["title"], "plan_summary": document.get("summary", ""), "excerpt": document["content"][-6000:], "truncated": len(document["content"]) > 6000}
    observe("previous_written", {**target_scope, "position": position}, previous_basis)

    edit_target = None
    if request.target_type == "chapter":
        edit_target = {**remember("chapter", target), "content": target["content"], "content_semantics": "edit_target"}
    if request.target_type == "chapter" and target["version"] != request.expected_version:
        raise DomainApiError("WRITING_VERSION_CONFLICT", "章节已修改，请保留草稿并刷新后比较", status_code=409)
    observe("edit_target", {"id": request.target_id if request.target_type == "chapter" else None}, edit_target)

    selected = request.selected_entities.model_dump()
    volume_id = next(document["_id"] for part, document in chain if part == "volume")
    volume = next(document for part, document in chain if part == "volume")
    participant_states = {}
    # 尚未给出局部选择时，以已确认的卷参与状态作为整理资料的起点。
    if not any(selected.values()):
        participants = []
        for kind, field in (("character_volume_state", "character_id"), ("faction_volume_state", "faction_id")):
            rows = await BaseRepository(RESOURCE_COLLECTIONS[kind]).collection.find({"novel_id": ObjectId(request.novel_id), "volume_id": volume_id, "is_deleted": False}, session=session).sort(field, 1).to_list(length=None)
            participant_states[kind] = rows
            selected[f"{field}s"] = list(dict.fromkeys(row[field] for row in rows))
            participants.extend(remember(kind, row) for row in rows)
        selected["location_ids"] = list(volume.get("location_ids", []))
        observe("volume_participants", {"novel_id": request.novel_id, "volume_id": str(volume_id)}, participants)
    # 上级已经明确选定的资料自然进入当前任务，不要求作者再次粘贴 ID。
    for _, document in chain:
        planning = document.get("planning") or {}
        for field in selected:
            selected[field] = list(dict.fromkeys([*selected[field], *planning.get(field, [])]))
        pov = planning.get("pov_character_id")
        if pov and pov not in selected["character_ids"]:
            selected["character_ids"].append(pov)
    from backend.services.novel.character_fact_service import read_character_facts
    fact_result = await read_character_facts(request.novel_id, selected["character_ids"], target_scope, session=session)
    character_facts = {row["character_id"]: row for row in fact_result["characters"]}
    # 原选择及卷参与查询仍各自冻结；明确空 IDs 不能冒充一次空的全书搜索。
    reads.extend(fact_result["reads"])
    item_facts, item_reads, _ = await read_item_context(request.novel_id, selected["item_ids"], target_scope, session=session)
    reads.extend(item_reads)
    entities = []
    for field, identities in selected.items():
        collection, kind, identity_field, status_field = ENTITY_FIELDS[field]
        if not identities:
            continue
        query = {"novel_id": ObjectId(request.novel_id), identity_field: {"$in": identities}, "is_deleted": False}
        if status_field:
            query[status_field] = "active"
        if kind == "location":
            query["location_order_pending_token"] = None
        elif kind == "item":
            query["item_write_pending_token"] = None
        if kind == "faction":
            query["$or"] = [{"level_type": "core", "volume_id": None}, {"level_type": {"$in": ["volume", "local"]}, "volume_id": volume_id}]
        documents = await BaseRepository(collection).collection.find(query, session=session).to_list(length=None)
        by_id = {document[identity_field]: document for document in documents}
        # 批量查询只减少往返，仍按作者选择顺序输出。
        for identity in identities:
            document = by_id.get(identity)
            if document is None:
                raise DomainApiError("WRITING_REFERENCE_UNAVAILABLE", "当前规划引用的资料不存在、已停用或不属于本卷", status_code=409, details={"resource_type": kind, "id": identity})
            entities.append(remember(kind, document))
    observe("selected_entities", {"novel_id": request.novel_id, "selected": selected}, entities)

    # 冻结人物相关的原关系集合，包括没有关系时的查询；ID 选择不能替代此范围。
    relation_query = {"novel_id": ObjectId(request.novel_id), "is_deleted": False, "is_active": True,
                      "$or": [{"source_character_id": {"$in": selected["character_ids"]}},
                              {"target_character_id": {"$in": selected["character_ids"]}}]}
    relation_docs = await BaseRepository("character_relations").collection.find(relation_query, session=session).sort([("relation_id", 1), ("_id", 1)]).limit(10001).to_list(length=10001)
    if len(relation_docs) > 10000:
        raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "相关关系过多，请缩小人物选择范围", status_code=422)
    relation_facts, relation_reads, _ = await read_character_relation_context(
        request.novel_id, [row["relation_id"] for row in relation_docs], target_scope, session=session)
    reads.extend(relation_reads)
    relations = [remember("character_relation", document) for document in relation_docs]
    observe("selected_relations", {"novel_id": request.novel_id, "character_ids": selected["character_ids"],
                                   "is_deleted": False, "is_active": True}, relations)

    volume_id = next(document["_id"] for part, document in chain if part == "volume")
    volume_states = []
    for kind, identity_field, identities in (("character_volume_state", "character_id", selected["character_ids"]), ("faction_volume_state", "faction_id", selected["faction_ids"])):
        query = {"novel_id": ObjectId(request.novel_id), "volume_id": volume_id, identity_field: {"$in": identities}, "is_deleted": False}
        if session is not None and kind in participant_states:
            # 确认事务已读过全部参与状态；非事务生成仍保留后一次读取。
            states = [row for row in participant_states[kind] if row[identity_field] in identities]
        else:
            states = await BaseRepository(RESOURCE_COLLECTIONS[kind]).collection.find(query, session=session).sort(identity_field, 1).to_list(length=None)
        values = [remember(kind, document) for document in states]
        volume_states.extend(values)
        observe("volume_states", {"novel_id": request.novel_id, "volume_id": str(volume_id), "resource_type": kind, "selected_ids": identities}, values)

    search_results = []
    if request.search_text:
        for kind in ("arc", "scene", "chapter"):
            candidates = [document for document in directories[kind].values()
                          if writing_order(kind, document, directories) is not None
                          and (request.search_scope == "novel" or document["_id"] == target["_id"]
                               or document.get(f"{request.target_type}_id") == target["_id"])]
            bodies = {}
            if kind == "chapter":
                chapter_ids = [document["_id"] for document in candidates
                               if chapter_visible_at_position(document, directories, position)]
                rows = await BaseRepository("chapters").collection.find({"novel_id": ObjectId(request.novel_id), "_id": {"$in": chapter_ids}, "is_deleted": False,
                    "content": {"$regex": re.escape(request.search_text), "$options": "i"}}, session=session).limit(31).to_list(length=31)
                bodies = {document["_id"]: document for document in rows if chapter_visible_at_position(document, directories, position)}
            found = []
            for document in sorted(candidates, key=lambda row: str(row["_id"])):
                value = position_content(document, kind)
                if document["_id"] in bodies:
                    value["content"] = bodies[document["_id"]].get("content", "")
                    value["content_semantics"] = "design_plan_with_prior_text"
                # 只用允许返回的字段匹配，再计算限额；未来正文不会造成命中或挤掉前文。
                if request.search_text.casefold() in json.dumps(value, ensure_ascii=False).casefold():
                    found.append((document, value))
            if len(found) > 30:
                raise DomainApiError("WRITING_SEARCH_TOO_LARGE", "检索结果过多，请缩小范围或增加检索文字", status_code=422)
            for document, value in found:
                remember(kind, bodies.get(document["_id"], document))
                search_results.append(value)
    observe("literal_search", {**target_scope, "text": request.search_text, "range": request.search_scope}, search_results)
    public = {"position": position, "plan": plans, "neighbors": neighbors, "existing_children": children, "previous_written": previous, "selected_entities": entities, "relations": relations, "volume_states": volume_states, "search_results": search_results, "edit_target": edit_target, "user_guidance": request.user_guidance, "count": request.count, "count_mode": request.count_mode, "target_word_count": request.target_word_count, "truncation": {"previous_excerpt_limit": 6000, "previous_truncated": bool(previous and previous["truncated"])}}
    if len(json.dumps(public, ensure_ascii=False)) > 200000:
        raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "所选规划和资料过长，请缩小范围；作者要求未被截断", status_code=422)
    # 目录和正文分开读取；其他祖先移动也可能让前文成为未来正文。
    if not in_transaction:
        order_fields = ("novel_id", "volume_id", "arc_id", "scene_id", "order_index")
        for kind, original in directories.items():
            current = await BaseRepository(COLLECTIONS[kind]).collection.find({"novel_id": ObjectId(request.novel_id), "is_deleted": False}, {"content": 0}, session=session).limit(10001).to_list(length=10001)
            before = {identity: tuple(document.get(field) for field in order_fields) for identity, document in original.items()}
            after = {document["_id"]: tuple(document.get(field) for field in order_fields) for document in current}
            if before != after:
                raise DomainApiError("WRITING_CONTEXT_CHANGED", "读取期间目录位置已变化，请重新生成", status_code=409)
        final_chain = await load_writing_parents(request.novel_id, request.target_type, request.target_id, session=session)
        if [position_content(kind_document, kind) for kind, kind_document in final_chain] != plans:
            raise DomainApiError("WRITING_CONTEXT_CHANGED", "读取期间当前规划或父链发生变化，请重试", status_code=409)
    return {"request": request, "context": public, "context_basis": WritingContextBasisV1.model_validate({"reads": reads}).model_dump(mode="json"), "source_refs": list(sources.values()), "guards": guards, "chain": chain, "siblings": siblings, "missing": missing}


async def protect_writing_sources(data: dict[str, Any], *, session: AsyncClientSession) -> None:
    """让确认与本次读到的资料修改产生事务写冲突。

    Args:
        data: 在同一事务内重读的写作上下文。
        session: 当前必需事务。
    Returns:
        无；变化会使整次确认回滚。
    """
    if data.get("fact_reads"):
        await revalidate_position_fact_reads(data["fact_reads"], session=session, protect=True)
    queries_by_collection: dict[str, list[dict[str, Any]]] = {}
    for (collection_name, _), document in data["guards"].items():
        queries_by_collection.setdefault(collection_name, []).append({
            "_id": document["_id"], "version": document["version"], "is_deleted": False,
        })
    for collection_name, queries in queries_by_collection.items():
        collection = BaseRepository(collection_name).collection
        if collection_name in COLLECTIONS.values() or collection_name == "character_relations":
            # 合并同集合的保护写入，保留每份资料原有的版本条件。
            result = await collection.bulk_write([
                UpdateOne(query, {"$inc": {"writing_guard_revision": 1}})
                for query in queries
            ], ordered=True, session=session)
            if result.matched_count != len(queries):
                raise DomainApiError("WRITING_SOURCE_CHANGED", "资料在确认期间发生变化，请保留候选并重试", status_code=409)
        else:
            await touch_dependency_endpoint_guards(collection, queries, session=session)


async def get_writing_readiness(novel_id: str, target_type: str, target_id: str) -> dict[str, Any]:
    """查询当前部分缺项和引用可用性，不调用模型或写数据库。

    Args:
        novel_id: 当前小说。
        target_type: 当前对象类别。
        target_id: 当前对象。
    Returns:
        当前动作可用性与可定位的缺项。
    """
    chain = await load_writing_parents(novel_id, target_type, target_id)
    task = next(name for name, (kind, _) in WRITING_TASKS.items() if kind == target_type)
    scope = {"novel_id": novel_id, "target_type": target_type, "target_id": target_id}
    if target_type == "chapter":
        scope["expected_version"] = chain[-1][1]["version"]
    blockers = []
    try:
        await load_writing_context(task, {}, scope, check_ready=False)
    except DomainApiError as exc:
        if exc.code != "WRITING_REFERENCE_UNAVAILABLE":
            raise
        blockers.append({"code": exc.code, "message": exc.message})
    missing = current_missing(chain)
    if target_type != "chapter":
        missing.extend(await writing_plot_missing(chain))
    ready = not missing and not blockers
    from backend.services.novel.plot_service import load_plot_sources, plot_hash
    plot_status = "missing"
    if target_type in {"volume", "arc"} and chain[-1][1].get("plot", "").strip():
        _, _, fingerprint = await load_plot_sources(novel_id, target_type, target_id)
        plot_status = "ready" if chain[-1][1].get("plot_source_fingerprint") == fingerprint else "stale"
    volume = next(doc for kind, doc in chain if kind == "volume")
    # 人工新建只沿用创建服务的卷规划检查；剧情、选材和当前规划完整度只限制 AI。
    create_missing = volume_missing_fields(volume) if target_type != "chapter" else []
    if target_type != "volume":
        create_missing = [{**item, "field": f"volume.{item['field']}"} for item in create_missing]
    prepared = {kind: bool(volume.get("plot", "").strip()) and volume.get("preparation", {}).get(kind) == plot_hash(volume.get("plot", "")) for kind in ("factions", "characters", "locations")}
    can_generate_plot = target_type == "volume" or (target_type == "arc" and not any(item["field"].startswith("volume.") for item in missing))
    return WritingReadinessV1.model_validate({
        "novel_id": novel_id, "target_type": target_type, "target_id": target_id,
        "can_create_child": target_type != "chapter" and not create_missing,
        "create_missing_fields": create_missing,
        "can_refine": ready and target_type != "chapter", "can_write": ready and target_type == "chapter",
        "can_generate_plot": can_generate_plot and not blockers, "plot_status": plot_status,
        "preparation": prepared, "missing_fields": missing, "blockers": blockers,
        "parent_chain": [{"resource_type": kind, "id": str(doc["_id"]), "title": doc["title"]} for kind, doc in chain],
        "expected_version": chain[-1][1]["version"],
    }).model_dump(mode="json")


async def writing_plot_missing(chain: list[tuple[str, dict[str, Any]]], *, session: AsyncClientSession | None = None) -> list[dict[str, str]]:
    """只对 AI 向下规划检查已保存剧情，人工编辑和已有正文不补做流程。

    Args:
        chain: 当前对象的活动父链。
        session: 确认时使用的事务。
    Returns:
        可定位到剧情或准备阶段的缺项。
    """
    from backend.services.novel.plot_service import load_plot_sources, plot_hash

    missing = []
    novel_id = str(chain[0][1]["_id"])
    for index, (kind, document) in enumerate(chain):
        if kind not in {"volume", "arc"}:
            continue
        label = "卷" if kind == "volume" else "篇章"
        if not document.get("plot", "").strip():
            missing.append({"field": f"{kind}.plot", "message": f"请先补齐{label}的详细剧情"})
        else:
            _, _, fingerprint = await load_plot_sources(novel_id, kind, str(document["_id"]), session=session, parent_chain=chain[:index + 1])
            if fingerprint != document.get("plot_source_fingerprint"):
                missing.append({"field": f"{kind}.plot", "message": f"{label}的上级规划已变化，请检查并确认剧情"})
        if kind == "volume":
            for stage, name in (("factions", "势力"), ("characters", "角色"), ("locations", "地点")):
                if not document.get("plot", "").strip() or document.get("preparation", {}).get(stage) != plot_hash(document.get("plot", "")):
                    missing.append({"field": f"volume.preparation.{stage}", "message": f"请先确认本卷{name}"})
    return missing
