"""书内资料目录、字段定义、可重建摘要索引和按需原文读取。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bson import ObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel, UpdateOne

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.api.default_routers.novel_router import NovelUpdateRequestV1
from backend.api.default_routers.volume_router import VolumeCreateRequestV2, VolumeUpdateRequestV2
from backend.api.default_routers.faction_router import FactionUpdateRequestV1
from backend.api.default_routers.world_rule_router import WorldRuleCreateV1, WorldRuleUpdateV1
from backend.api.default_routers.character_faction_binding_router import CharacterFactionBindingCreateRequestV1, CharacterFactionBindingUpdateRequestV1
from backend.db.base import BaseRepository
from backend.db.utils import get_utc_now
from backend.db.write_contracts import canonical_request_hash
from backend.llm.schemas.character_pydantic import CharacterCreateRequestV1, CharacterUpdateRequestV1
from backend.llm.schemas.faction_creation_pydantic import FactionCreateRequestV1
from backend.llm.schemas.character_relation_pydantic import CharacterRelationCreateRequestV1, CharacterRelationUpdateRequestV1
from backend.llm.schemas.faction_relation_pydantic import FactionRelationCreateRequestV1, FactionRelationUpdateRequestV1
from backend.llm.schemas.location_pydantic import LocationCreateV1, LocationUpdateV1
from backend.llm.schemas.item_pydantic import ItemCreateV1, ItemUpdateV1
from backend.llm.schemas.character_volume_state_pydantic import CharacterVolumeStateUpsertV1, CharacterVolumeStateUpdateV1
from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumePlanFieldsV1, FactionVolumePlanUpdateV1
from backend.services.novel.arc_contract import ArcCreateV1, ArcUpdateV1
from backend.services.novel.scene_contract import SceneCreateV1, SceneUpdateV1
from backend.services.novel.chapter_contract import ChapterCreateV2, ChapterUpdateV2
from backend.services.novel.foreshadowing_contract import ForeshadowingReadV1
from backend.services.novel.foreshadowing_service import ForeshadowingService
from .contracts import ResourceRef


@dataclass(frozen=True)
class ResourceDefinition:
    """真实集合及原业务字段，供目录、工具和写入共同使用。"""

    collection: str
    identity: str
    label: str
    create: type[BaseModel] | None
    update: type[BaseModel]


RESOURCES = {
    "foreshadowing": ResourceDefinition("foreshadowings", "foreshadowing_id", "伏笔", None, ForeshadowingReadV1),
    "novel": ResourceDefinition("novels", "_id", "小说", None, NovelUpdateRequestV1),
    "volume": ResourceDefinition("volumes", "_id", "卷", VolumeCreateRequestV2, VolumeUpdateRequestV2),
    "arc": ResourceDefinition("arcs", "_id", "篇章", ArcCreateV1, ArcUpdateV1),
    "scene": ResourceDefinition("scenes", "_id", "场景", SceneCreateV1, SceneUpdateV1),
    "chapter": ResourceDefinition("chapters", "_id", "章节", ChapterCreateV2, ChapterUpdateV2),
    "character": ResourceDefinition("characters", "character_id", "角色", CharacterCreateRequestV1, CharacterUpdateRequestV1),
    "faction": ResourceDefinition("factions", "faction_id", "势力", FactionCreateRequestV1, FactionUpdateRequestV1),
    "location": ResourceDefinition("locations", "location_id", "地点", LocationCreateV1, LocationUpdateV1),
    "item": ResourceDefinition("items", "item_id", "物品", ItemCreateV1, ItemUpdateV1),
    "world_rule": ResourceDefinition("world_rules", "rule_id", "规则", WorldRuleCreateV1, WorldRuleUpdateV1),
    "character_relation": ResourceDefinition("character_relations", "relation_id", "人物关系", CharacterRelationCreateRequestV1, CharacterRelationUpdateRequestV1),
    "faction_relation": ResourceDefinition("faction_relations", "relation_id", "势力关系", FactionRelationCreateRequestV1, FactionRelationUpdateRequestV1),
    "character_faction_binding": ResourceDefinition("character_faction_bindings", "binding_id", "角色势力绑定", CharacterFactionBindingCreateRequestV1, CharacterFactionBindingUpdateRequestV1),
    "character_volume_state": ResourceDefinition("character_volume_states", "_id", "卷内角色状态", CharacterVolumeStateUpsertV1, CharacterVolumeStateUpdateV1),
    "faction_volume_state": ResourceDefinition("faction_volume_states", "_id", "卷内势力参与计划", FactionVolumePlanFieldsV1, FactionVolumePlanUpdateV1),
}
INTERNAL_INPUTS = {"expected_version", "request_type", "basis", "novel_id", "sort_order", "rule_order"}
POSITION_FIELDS = ("volume_id", "arc_id", "scene_id", "chapter_id", "character_id", "faction_id", "order_index")
READ_EXTRA_FIELDS = {"status", "active_status", "is_active", "sort_order", "preparation", "location_ids", "chapter_count", "word_count", "current_chapter_count", "current_word_count"}


def public_content(kind: str, document: dict) -> dict:
    """只读取业务字段，内部锁和生成回执不进入模型。

    Args:
        kind: 已登记的资料类型。
        document: 数据库原记录。
    Returns:
        JSON 可序列化的业务内容与稳定位置。
    """
    spec = RESOURCES[kind]
    fields = (set(spec.update.model_fields) | (set(spec.create.model_fields) if spec.create else set())) - INTERNAL_INPUTS
    fields |= READ_EXTRA_FIELDS | set(POSITION_FIELDS)
    result = {name: document[name] for name in fields if name in document}
    identity = document["state_id"] if kind.endswith("_volume_state") and "state_id" in document else document[spec.identity]
    result.update(resource_type=kind, id=str(identity), version=document["version"], is_deleted=document.get("is_deleted", False))
    return sanitize_json_value(result)


def content_fingerprint(content: dict) -> str:
    """计算内容依据，不把祖先字数统计变动当作剧情改动。

    Args:
        content: 白名单业务资料。
    Returns:
        可复验的内容指纹。
    """
    return canonical_request_hash({k: v for k, v in content.items() if k not in {"version", "chapter_count", "word_count", "current_chapter_count", "current_word_count"}})


async def get_resource(novel_id: str, ref: ResourceRef, *, session=None, include_deleted: bool = False) -> dict:
    """读取当前小说内的实际记录，所有入口共用归属校验。

    Args:
        novel_id: 路由或会话固定的小说。
        ref: 资料类型及稳定 ID。
        session: 可选保存事务。
        include_deleted: 明确读取回收站记录。
    Returns:
        数据库原文档；不存在或跨书时报告 404。
    """
    spec = RESOURCES[ref.resource_type]
    if ref.resource_type == "foreshadowing":
        return await ForeshadowingService.get(novel_id, ref.id, include_deleted=include_deleted, session=session)
    if spec.identity == "_id" and not ObjectId.is_valid(ref.id):
        raise DomainApiError("ASSISTANT_RESOURCE_INVALID", "资料 ID 不正确")
    query = {spec.identity: ObjectId(ref.id) if spec.identity == "_id" else ref.id}
    if ref.resource_type == "novel":
        if ref.id != novel_id:
            raise DomainApiError("ASSISTANT_RESOURCE_NOT_FOUND", "资料不属于当前小说", status_code=404)
    else:
        query["novel_id"] = ObjectId(novel_id)
    if not include_deleted:
        query["is_deleted"] = False
    doc = await BaseRepository(spec.collection).collection.find_one(query, session=session)
    if doc is None:
        raise DomainApiError("ASSISTANT_RESOURCE_NOT_FOUND", "资料不存在、已回收或不属于当前小说", status_code=404)
    return doc


def field_value(content: dict, path: str) -> Any:
    """按公开字段路径取值，不执行数据库路径表达式。

    Args:
        content: 已过滤的业务资料。
        path: 点号分隔的字典字段。
    Returns:
        原字段值；未知字段明确报错。
    """
    value: Any = content
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise DomainApiError("ASSISTANT_FIELD_UNKNOWN", f"资料没有字段：{path}")
        value = value[part]
    return value


def describe_resource(kind: str) -> dict:
    """提供原业务 Schema，模型先了解字段再准备修改。

    Args:
        kind: 已登记的资料类型。
    Returns:
        创建和更新 Schema，以及单独业务操作说明。
    """
    spec = RESOURCES[kind]
    if kind == "foreshadowing":
        return {"resource_type": kind, "label": spec.label, "schemas": {}, "read_only": True, "instructions": "只供读取伏笔计划、原文证据和复核标记；状态、回收和修改必须由作者在伏笔工作台操作。"}
    models = {"create": spec.create, "update": spec.update}
    schemas = {}
    for action, model in models.items():
        if model is None:
            continue
        schema = model.model_json_schema()
        for name in INTERNAL_INPUTS:
            schema["properties"].pop(name, None)
        schema["required"] = [name for name in schema.get("required", []) if name not in INTERNAL_INPUTS]
        schemas[action] = schema
    return {"resource_type": kind, "label": spec.label, "schemas": schemas,
            "instructions": "更新只提交改动字段；版本来自实际读取，不能自行设置。层级新建提供parent_id；卷状态新建提供volume_id与character_id/faction_id。新对象引用使用new_开头的临时ID。删除和恢复需要作者确认。"}


def build_index_record(novel_id: str, kind: str, document: dict) -> dict:
    """从原字段建立摘要目录；无摘要时明确标记摘录。

    Args:
        novel_id: 当前小说。
        kind: 资料类别。
        document: 当前完整记录。
    Returns:
        可重建的目录条目，不含完整章节正文。
    """
    content = public_content(kind, document)
    name = content.get("name") or content.get("title") or content["id"]
    parts = []
    for field in ("summary", "goal", "positioning", "current_goal", "statement", "description", "core_conflict", "current_state"):
        if isinstance(content.get(field), str) and content[field].strip():
            parts.append(f"{field}: {content[field][:180]}")
    excerpt = not parts
    if not parts:
        for field in ("plot", "content", "core_idea", "start_state"):
            if isinstance(content.get(field), str) and content[field].strip():
                parts.append(content[field][:400])
                break
    # 引用递归取自真实 ID 字段；用于查找，不把它当作正文一致性结论。
    references: set[str] = set()
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith(("_id", "_ids")):
                    references.update(str(v) for v in (item if isinstance(item, list) else [item]) if v is not None)
                if isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(content)
    if kind == "foreshadowing":
        references.update(content[field]["id"] for field in ("planting_position", "resolution_position") if content[field] is not None)
    return {"novel_id": ObjectId(novel_id), "resource_type": kind, "resource_id": content["id"],
            "name": str(name), "summary": "\n".join(parts)[:600], "summary_kind": "excerpt" if excerpt else "fields",
            "aliases": content.get("aliases", content.get("alias", [])), "tags": content.get("tags", []),
            "position": {key: content[key] for key in POSITION_FIELDS if key in content},
            "fields": sorted(set(content) - {"id", "resource_type", "version", "is_deleted"}),
            "references": sorted(references), "source_version": content["version"], "fingerprint": content_fingerprint(content),
            "is_deleted": content["is_deleted"], "updated_at": get_utc_now(),
            **({field: content[field] for field in ("status", "planted_needs_review", "resolved_needs_review")} if kind == "foreshadowing" else {})}


async def sync_index(novel_id: str) -> dict:
    """逐类核对真实版本，断线后只补缺失或变化的记录。

    Args:
        novel_id: 当前小说。
    Returns:
        每类当前记录数和本轮更新数。
    """
    await get_resource(novel_id, ResourceRef(resource_type="novel", id=novel_id), include_deleted=True)
    index = BaseRepository("assistant_resource_index").collection
    counts, updated = {}, 0
    for kind, spec in RESOURCES.items():
        query = {"_id": ObjectId(novel_id)} if kind == "novel" else {"novel_id": ObjectId(novel_id)}
        existing = {row["resource_id"]: row async for row in index.find({"novel_id": ObjectId(novel_id), "resource_type": kind}, {"resource_id": 1, "source_version": 1, "fingerprint": 1})}
        seen = set()
        counts[kind] = 0
        # 先扫描小型版本目录；正文只对确实变化的记录读取。
        async for meta in BaseRepository(spec.collection).collection.find(query, {spec.identity: 1, "version": 1, "is_deleted": 1}):
            identity = str(meta[spec.identity])
            seen.add(identity)
            counts[kind] += not meta.get("is_deleted", False)
            old = existing.get(identity)
            if old and old["source_version"] == meta["version"] and kind != "foreshadowing":
                continue
            ref = ResourceRef(resource_type=kind, id=identity)
            try:
                doc = await get_resource(novel_id, ref, include_deleted=True)
            except DomainApiError as exc:
                if exc.status_code == 404:
                    continue
                raise
            record = build_index_record(novel_id, kind, doc)
            key = {"novel_id": ObjectId(novel_id), "resource_type": kind, "resource_id": identity}
            update = {"$set": record}
            if old and old["fingerprint"] != record["fingerprint"]:
                update["$unset"] = {"ai_summary": "", "ai_summary_fingerprint": "", "ai_summary_model": ""}
            await index.update_one(key, update, upsert=True)
            updated += 1
        # 已被原回收站永久删除的记录只移除单个派生条目，不改原文。
        for identity in existing.keys() - seen:
            await index.delete_one({"novel_id": ObjectId(novel_id), "resource_type": kind, "resource_id": identity})
    return {"counts": counts, "updated": updated, "checked_at": get_utc_now().isoformat()}


async def list_resources(novel_id: str, *, kind: str | None = None, query: str = "", offset: int = 0, limit: int = 20, deleted: bool = False, reference_id: str | None = None) -> dict:
    """分页查询基础索引，不展开正文。

    Args:
        novel_id: 当前小说。
        kind: 可选类别。
        query: 普通搜索文字。
        offset: 已读条数。
        limit: 本页条数。
        deleted: 是否只查回收站。
        reference_id: 查找直接引用指定对象的资料。
    Returns:
        摘要条目、完整数量及后续分页位置。
    """
    filters: dict = {"novel_id": ObjectId(novel_id), "is_deleted": deleted}
    if kind:
        filters["resource_type"] = kind
    if reference_id:
        filters["references"] = reference_id
    if query:
        filters["$or"] = [{field: {"$regex": re.escape(query), "$options": "i"}} for field in ("name", "aliases", "summary", "tags", "ai_summary")]
    coll = BaseRepository("assistant_resource_index").collection
    rows = await coll.find(filters, {"_id": 0, "novel_id": 0}).sort([("resource_type", 1), ("position.order_index", 1), ("resource_id", 1)]).skip(offset).limit(limit).to_list(length=limit)
    total = await coll.count_documents(filters)
    return {"items": sanitize_json_value(rows), "total": total, "offset": offset, "has_more": offset + len(rows) < total}


async def search_text(novel_id: str, query: str, *, kind: str | None = None, offset: int = 0, limit: int = 20, session=None) -> dict:
    """检索真实业务字段中的普通文字，返回有来源的片段。

    Args:
        novel_id: 当前小说。
        query: 普通文字，不作为正则表达式执行。
        kind: 可选资料类别。
        offset: 命中对象分页起点。
        limit: 命中对象页数。
        session: 确认时复验同一查询所用的事务。
    Returns:
        命中字段、原文片段和是否还有下一页。
    """
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    items, matched = [], 0
    for resource_kind, spec in RESOURCES.items():
        if kind and kind != resource_kind:
            continue
        filters = {"_id": ObjectId(novel_id)} if resource_kind == "novel" else {"novel_id": ObjectId(novel_id)}
        filters["is_deleted"] = False
        allowed = (set(spec.update.model_fields) | (set(spec.create.model_fields) if spec.create else set())) - INTERNAL_INPUTS
        projection = {field: 1 for field in allowed | {spec.identity, "version", "is_deleted"} | set(POSITION_FIELDS)}
        async for document in BaseRepository(spec.collection).collection.find(filters, projection, session=session).sort("_id", 1):
            if resource_kind == "foreshadowing":
                document = await ForeshadowingService.get(novel_id, document[spec.identity], session=session)
            content = public_content(resource_kind, document)
            hits = []
            def visit(value, path):
                if isinstance(value, str):
                    match = pattern.search(value)
                    if match:
                        start = max(0, match.start() - 160)
                        hits.append({"field": path, "excerpt": value[start:start + 600], "start": start})
                elif isinstance(value, dict):
                    for field, item in value.items():
                        visit(item, f"{path}.{field}" if path else field)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        visit(item, f"{path}.{i}")
            for field in sorted(allowed):
                if field in content:
                    visit(content[field], field)
            if not hits:
                continue
            if matched >= offset:
                items.append({"resource_type": resource_kind, "id": content["id"], "version": content["version"], "name": content.get("name", content.get("title", content["id"])), "matches": hits[:5], "fingerprint": content_fingerprint(content)})
                if resource_kind == "foreshadowing":
                    items[-1].update({field: content[field] for field in ("status", "planted_evidence", "resolved_evidence", "planted_needs_review", "resolved_needs_review")})
            matched += 1
            if len(items) > limit:
                return {"items": items[:limit], "offset": offset, "has_more": True, "query": query}
    return {"items": items, "offset": offset, "has_more": False, "query": query}


async def init_assistant_indexes(db=None) -> None:
    """建立助手专用索引，不迁移或清理业务记录。

    Args:
        无。
    Returns:
        无。
    """
    definitions = {
        "assistant_sessions": [IndexModel([("novel_id", 1), ("updated_at", -1)])],
        "assistant_runs": [IndexModel([("novel_id", 1), ("session_id", 1), ("request_key", 1)], unique=True), IndexModel([("novel_id", 1), ("status", 1)])],
        "assistant_events": [IndexModel([("run_id", 1), ("seq", 1)], unique=True), IndexModel([("session_id", 1), ("created_at", 1)])],
        "assistant_messages": [IndexModel([("session_id", 1), ("created_at", 1)])],
        "assistant_checkpoints": [IndexModel([("checkpoint_id", 1), ("part", 1)], unique=True), IndexModel([("run_id", 1), ("created_at", 1)])],
        "assistant_changes": [IndexModel([("session_id", 1), ("created_at", 1)])],
        "assistant_receipts": [IndexModel([("novel_id", 1), ("change_id", 1), ("revision", 1)], unique=True)],
        "assistant_resource_index": [IndexModel([("novel_id", 1), ("resource_type", 1), ("resource_id", 1)], unique=True), IndexModel([("novel_id", 1), ("references", 1)]), IndexModel([("novel_id", 1), ("is_deleted", 1)])],
    }
    for name, indexes in definitions.items():
        collection = db[name] if db is not None else BaseRepository(name).collection
        await collection.create_indexes(indexes)
