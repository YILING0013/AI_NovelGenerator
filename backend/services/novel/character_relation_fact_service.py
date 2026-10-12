"""读取关系在明确位置的事实，并保护作者实际使用过的读取依据。"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError, VersionConflictError
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint, canonical_request_hash
from backend.services.novel.character_relation_fact_contract import (
    CharacterRelationFactReadResultV1, CharacterRelationFactReadV1,
    CharacterRelationFactPreviewInputV1, CharacterRelationFactPreviewV1, CharacterRelationFactConfirmV1,
    CharacterRelationFactRecordV1, CharacterRelationFactResultV1,
    CharacterRelationFactQueryV1,
    character_relation_fact_record_document, parse_character_relation_fact_record,
    character_relation_fact_receipt_document,
)
from backend.services.novel.character_relation_fact_reader import evaluate_character_relation_facts
from backend.services.novel.chapter_record_source import (
    load_chapter_record_source_in_session, protect_chapter_record_sources,
)
from backend.services.novel.writing_context import (
    COLLECTIONS, PARENTS, load_writing_parents, resolve_writing_position, writing_order,
)


async def _load_character_relation_fact_snapshot(novel_id, relation_ids, position_scope, *, session):
    """用同一快照读取目录、全部关系历史及真实端点，不按 schema 藏掉坏记录。"""
    novel_key = ObjectId(novel_id)
    parents = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    novel = parents[0][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("CHARACTER_RELATION_FACT_PARENT_BUSY", "小说正在永久删除，请稍后读取", status_code=409)
    directories = {}
    for kind in PARENTS:
        documents = await BaseRepository(COLLECTIONS[kind]).collection.find(
            {"novel_id": novel_key, "is_deleted": False}, {"content": 0}, session=session,
        ).limit(10001).to_list(length=10001)
        if len(documents) > 10000:
            raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "目录超过单次读取范围，请先整理目录", status_code=409)
        directories[kind] = {row["_id"]: row for row in documents}
        # 回收父级下的残留子目录不成为活动位置，原历史仍全部核验。
        directories[kind] = {key: row for key, row in directories[kind].items()
                             if writing_order(kind, row, directories) is not None}
    position = resolve_writing_position({**position_scope, "novel_id": novel_id}, directories)
    relations = await BaseRepository("character_relations").collection.find(
        {"novel_id": novel_key, "relation_id": {"$in": relation_ids}}, session=session,
    ).sort("relation_id", 1).to_list(length=None)
    endpoint_ids = sorted({row[name] for row in relations for name in ("source_character_id", "target_character_id")})
    characters = await BaseRepository("characters").collection.find(
        {"novel_id": novel_key, "character_id": {"$in": endpoint_ids}}, session=session,
    ).sort("character_id", 1).to_list(length=None)
    records = []
    documents = await BaseRepository("entity_state_history").collection.find({"$or": [
        {"entity_id": {"$in": [row["_id"] for row in relations]}},
        {"novel_id": novel_key, "relation_id": {"$in": relation_ids}},
    ]}, session=session).sort("_id", 1).to_list(length=None)
    by_id = {row["relation_id"]: row for row in relations}
    for document in documents:
        if "schema_id" not in document and "schema_version" not in document:
            continue  # 旧 D 只有审计信息，不能替作者认领状态起点。
        try:
            record = parse_character_relation_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录格式不正确，请检查记录", status_code=409) from exc
        relation = by_id.get(record["relation_id"])
        if (relation is None or ObjectId(record["novel_id"]) != novel_key
                or ObjectId(record["entity_id"]) != relation["_id"]):
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录的身份或所属小说不一致，请检查记录", status_code=409)
        records.append(record)

    sources = {}
    source_validity = {}
    guards = {("novels", novel_id): novel}
    for row in characters:
        guards[("characters", str(row["_id"]))] = row
    for row in relations:
        guards[("character_relations", str(row["_id"]))] = row
    for record in records:
        source = record["source"]
        if source["kind"] == "author":
            source_validity[record["history_id"]] = True
            continue
        evidence = source["evidence"]
        source_key = (str(ObjectId(evidence["chapter_id"])), str(ObjectId(evidence["revision_id"])))
        if source_key not in sources:
            chapter = await BaseRepository("chapters").collection.find_one({
                "_id": ObjectId(evidence["chapter_id"]), "novel_id": novel_key,
            }, session=session)
            revision = await BaseRepository("chapter_revisions").collection.find_one({
                "_id": ObjectId(evidence["revision_id"]), "novel_id": novel_key,
            }, session=session)
            current_hash = hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest() if chapter else None
            revision_hash = hashlib.sha256(revision["content"].encode("utf-8")).hexdigest() if revision else None
            parents_active = bool(chapter is not None and not chapter["is_deleted"]
                                  and writing_order("chapter", chapter, directories) is not None)
            revision_valid = bool(revision is not None and chapter is not None
                                  and revision_hash == revision["content_hash"]
                                  and revision["chapter_id"] == chapter["_id"]
                                  and all(revision[field] == chapter[field]
                                          for field in ("novel_id", "volume_id", "arc_id", "scene_id")))
            sources[source_key] = ({
                "chapter_id": evidence["chapter_id"], "exists": chapter is not None,
                "content_hash": current_hash, "is_deleted": chapter["is_deleted"] if chapter else None,
                "parents_active": parents_active, "revision_id": evidence["revision_id"],
                "revision_hash": revision_hash, "revision_version": revision["version"] if revision else None,
                "revision_valid": revision_valid,
            }, revision)
            if chapter is not None:
                guards[("chapters", str(chapter["_id"]))] = chapter
        observation, revision = sources[source_key]
        source_validity[record["history_id"]] = bool(
            observation["parents_active"] and observation["revision_valid"]
            and observation["content_hash"] == evidence["content_hash"] == observation["revision_hash"]
            and revision["version"] == evidence["version"]
            and revision["content"][evidence["start"]:evidence["start"] + len(evidence["quote"])] == evidence["quote"]
        )

    directory = [{"resource_type": kind, "id": str(row["_id"]),
                  "parent_id": str(row[f"{PARENTS[kind]}_id"]), "order_index": row["order_index"]}
                 for kind, rows in directories.items() for row in rows.values()]
    directory.sort(key=lambda row: (row["resource_type"], row["id"]))
    read = {
        "kind": "character_relation_facts", "novel_id": novel_id, "relation_ids": relation_ids,
        "position": position, "directory": directory,
        "identities": [{"entity_id": str(row["_id"]), **{name: row[name] for name in
                       ("relation_id", "source_character_id", "target_character_id", "is_active", "is_deleted")}}
                       for row in relations],
        "endpoints": [{"entity_id": str(row["_id"]), **{name: row[name] for name in
                      ("character_id", "name", "status", "is_deleted")}} for row in characters],
        "history": [{"history_id": row["history_id"], "entity_id": row["entity_id"],
                     "relation_id": row["relation_id"], "after_version": row["after_version"],
                     "immutable_fingerprint": canonical_request_hash({key: value for key, value in row.items() if key != "validity"}),
                     "validity": row["validity"]} for row in records],
        "sources": [sources[key][0] for key in sorted(sources)],
    }
    read["fingerprint"] = canonical_request_hash(read)
    # 停用只是管理状态；回收关系不提供活动值，历史接口仍可查看。
    evaluated = [evaluate_character_relation_facts(
        row, [character for character in characters if character["character_id"] in
              {row["source_character_id"], row["target_character_id"]}],
        [record for record in records if ObjectId(record["entity_id"]) == row["_id"]],
        position, directories, source_validity,
    ) for row in relations]
    active = [value for row, value in zip(relations, evaluated) if not row["is_deleted"]]
    result = {
        "novel_id": novel_id, "position": position, "relations": active,
        "missing_relation_ids": sorted(set(relation_ids) - {row["relation_id"] for row in active}),
        "reads": [read],
    }
    # 全目录进入比较；只写实际位置和来源父链的 guard，目录空查询由同一小说 guard 保护。
    anchors = [(position["target_type"], position["target_id"])]
    anchors.extend((row["position"]["target_type"], row["position"]["target_id"]) for row in records)
    for kind, identity in anchors:
        while kind != "novel":
            document = directories[kind].get(ObjectId(identity))
            if document is None:
                break
            guards[(COLLECTIONS[kind], str(document["_id"]))] = document
            identity = str(document[f"{PARENTS[kind]}_id"])
            kind = PARENTS[kind]
    return CharacterRelationFactReadResultV1.model_validate(result).model_dump(exclude_unset=True), guards


async def read_character_relation_facts(
    novel_id: str, relation_ids: list[str], position_scope: dict[str, Any], *,
    session: AsyncClientSession | None = None,
) -> dict:
    """共享读取关系在书初、章前后或父级边界的已确认事实。

    Args:
        novel_id: 当前小说身份。
        relation_ids: 实际选择的稳定关系 ID；空列表仍冻结空查询。
        position_scope: P1 的 target_type、target_id、reading_intent、reading_version。
        session: 调用方事务；省略时开启必需的只读事务。
    Returns:
        状态值或未知原因、来源及可原样复验的 reads。
    """
    novel_id = str(ObjectId(novel_id))
    selected = sorted(CharacterRelationFactQueryV1.model_validate({"relation_ids": relation_ids}).relation_ids)

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("关系事实读取必须使用同一读取事务")
        result, _ = await _load_character_relation_fact_snapshot(novel_id, selected, position_scope, session=current_session)
        return result

    return await read(session) if session is not None else await run_mongo_write_unit(read, "read_character_relation_facts", require_transaction=True)


async def revalidate_character_relation_fact_reads(
    reads: list[dict], *, session: AsyncClientSession | None = None, protect: bool = False,
) -> None:
    """每次发送或确认前复验原累计读取，不把新查询替换进旧依据。

    Args:
        reads: 原读取函数留下的固定依据，包括空查询。
        session: 写入时必须是调用方开启的同一个事务。
        protect: 确认写入时保护小说和实际来源；必须在状态锁之前调用。
    Returns:
        无；任何依据变化立即拒绝本次操作。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("关系事实保护必须在调用方事务内执行")
    if session is None:
        return await run_mongo_write_unit(
            lambda current_session: revalidate_character_relation_fact_reads(reads, session=current_session),
            "revalidate_character_relation_fact_reads", require_transaction=True,
        )
    if not session.in_transaction:
        raise RuntimeError("关系事实复验必须使用同一读取事务")
    for original in reads:
        read = CharacterRelationFactReadV1.model_validate(original).model_dump()
        position = read["position"]
        scope = {"target_type": position["target_type"], "target_id": position["target_id"],
                 "reading_intent": position["intent"], "reading_version": position["version"]}
        current, guards = await _load_character_relation_fact_snapshot(
            read["novel_id"], read["relation_ids"], scope, session=session,
        )
        if current["reads"][0] != read:
            raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系事实、来源或目录已变化，请保留原稿并重新预览", status_code=409)
        if protect:
            await protect_chapter_record_sources(guards, session=session)


async def ensure_character_relation_state_unmanaged(
    novel_id: str, relation_ids: list[str], *,
    session: AsyncClientSession | None = None, protect: bool = True,
) -> None:
    """旧原文只可在关系状态从未认领时编辑，空查询同样保护小说。

    Args:
        novel_id: 当前小说身份。
        relation_ids: 本次实际修改 current_state 的关系稳定 ID。
        session: 保存时使用调用方的必需事务。
        protect: 保存时保护空查询；候选准备和编辑传 False，只读检查。
    Returns:
        无；作废、替代或来源失效都不会撤销曾经的认领。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("关系状态保护必须在调用方事务内执行")
    novel_key = ObjectId(novel_id)
    chain = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    relations = await BaseRepository("character_relations").collection.find({
        "novel_id": novel_key, "relation_id": {"$in": relation_ids},
    }, session=session).to_list(length=None)
    by_id = {row["relation_id"]: row for row in relations}
    # 物理身份和业务身份都查，避免损坏的所属小说或关系编号藏掉原认领。
    documents = await BaseRepository("entity_state_history").collection.find({"$and": [
        {"$or": [{"entity_id": {"$in": [row["_id"] for row in relations]}},
                 {"novel_id": novel_key, "relation_id": {"$in": relation_ids}}]},
        {"$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]},
    ]}, session=session).to_list(length=None)
    for document in documents:
        try:
            record = parse_character_relation_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录格式不正确，请检查记录", status_code=409) from exc
        relation = by_id.get(record["relation_id"])
        if (relation is None or ObjectId(record["novel_id"]) != novel_key
                or ObjectId(record["entity_id"]) != relation["_id"]):
            raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录的身份或所属小说不一致，请检查记录", status_code=409)
    if documents:
        raise DomainApiError("CHARACTER_RELATION_FACT_MANAGED_FIELDS", "关系状态已有明确剧情位置，请从关系事实中更正", status_code=409)
    if protect:
        await protect_chapter_record_sources({("novels", novel_id): chain[0][1]}, session=session)


async def get_character_relation_fact_history(novel_id: str, history_id: str, *, session=None) -> dict:
    """读取一条严格关系事实记录，关系或来源回收后仍可查看。

    Args:
        novel_id: 记录所属小说。
        history_id: 记录物理 ID。
        session: 可选调用方事务。
    Returns:
        原记录及当前逐字段有效性，不重新解释原文或前值。
    """
    document = await BaseRepository("entity_state_history").collection.find_one({
        "_id": ObjectId(history_id), "novel_id": ObjectId(novel_id),
    }, session=session)
    if document is None or ("schema_id" not in document and "schema_version" not in document):
        raise NotFoundError("关系事实记录不存在")
    try:
        return parse_character_relation_fact_record(document)
    except (ValueError, TypeError) as exc:
        raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录格式不正确，请检查记录", status_code=409) from exc


async def list_character_relation_fact_history(
    novel_id: str, entity_id: str, *, before_version: int | None = None, limit: int = 100, session=None,
) -> list[dict]:
    """按关系真实动作版本列出原记录，不要求关系今天仍存在。

    Args:
        novel_id: 记录所属小说。
        entity_id: 关系物理身份，不能按名称重新绑定。
        before_version: 只读取小于该版本的记录，供向前翻页。
        limit: 本页数量，范围为 1 至 100。
        session: 可选调用方事务。
    Returns:
        版本倒序的严格记录；作废由记录中的原回执键追溯。
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("历史数量须为 1 至 100 的整数")
    query = {"novel_id": ObjectId(novel_id), "entity_id": ObjectId(entity_id),
             "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]}
    if before_version is not None:
        if type(before_version) is not int or before_version < 1:
            raise ValueError("历史分页版本须为正整数")
        query["after_version"] = {"$lt": before_version}
    rows = await BaseRepository("entity_state_history").collection.find(query, session=session).sort("after_version", -1).limit(limit).to_list(length=limit)
    try:
        return [parse_character_relation_fact_record(row) for row in rows]
    except (ValueError, TypeError) as exc:
        raise DomainApiError("CHARACTER_RELATION_FACT_RECORD_INVALID", "关系确认记录格式不正确，请检查记录", status_code=409) from exc


async def query_character_relation_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """在同一只读事务内解析查询位置并读取关系，最新位置不成为第二套时间。

    Args:
        novel_id: 当前小说。
        data: 最多 200 个稳定关系 ID 及可选书初或章前后位置。
        session: 可选调用方事务；没有时只开启一个必需事务。
    Returns:
        共同读取的完整结果，包含实际解析位置及原依据。
    """
    from backend.services.novel.character_fact_service import resolve_latest_character_fact_position

    query = CharacterRelationFactQueryV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("关系事实查询必须使用同一读取事务")
        position = (await resolve_latest_character_fact_position(novel_id, session=current_session)
                    if query.position is None else query.position.model_dump())
        scope = {"target_type": position["target_type"], "target_id": str(ObjectId(position["target_id"])),
                 "reading_intent": position["intent"], "reading_version": position["version"]}
        return await read_character_relation_facts(novel_id, query.relation_ids, scope, session=current_session)

    return await read(session) if session is not None else await run_mongo_write_unit(read, "query_character_relation_facts", require_transaction=True)


async def _build_character_relation_fact_preview(novel_id, fields, *, new_entity_id, session):
    """预览与确认重建相同依据，不写文档或预占关系序号。"""
    from backend.services.novel.character_relation_service import normalize_relation_endpoints

    novel_key = ObjectId(novel_id)
    operation = fields["operation"]
    existing = None
    if operation == "create":
        candidate = deepcopy(fields["target"]["candidate"])
        source_id, target_id = normalize_relation_endpoints(
            candidate["source_character_id"], candidate["target_character_id"], candidate["relation_type"],
        )
        candidate.update(source_character_id=source_id, target_character_id=target_id)
        found_id = await BaseRepository("character_relations").collection.find_one({"_id": ObjectId(new_entity_id)}, session=session)
        matches = await BaseRepository("character_relations").collection.find({
            "novel_id": novel_key, "normalized_source_character_id": source_id,
            "normalized_target_character_id": target_id, "relation_type": candidate["relation_type"],
            "is_active": True, "is_deleted": False,
        }, {"_id": 1}, session=session).to_list(length=None)
        if found_id is not None or matches:
            raise DomainApiError("CHARACTER_RELATION_FACT_CREATE_CONFLICT", "关系身份或同类型关系已存在，请保留原稿并重新预览", status_code=409)
        target = {"kind": "new", "novel_id": novel_id, "entity_id": new_entity_id,
                  "candidate": candidate, "entity_exists": False, "semantic_matches": []}
    else:
        supplied = fields["target"]
        existing = await BaseRepository("character_relations").collection.find_one({
            "_id": ObjectId(supplied["entity_id"]), "novel_id": novel_key,
            "relation_id": supplied["relation_id"], "is_deleted": False,
        }, session=session)
        if existing is None:
            raise NotFoundError("关系不存在、已回收或不属于当前小说")
        if not existing["is_active"]:
            raise DomainApiError("CHARACTER_RELATION_FACT_TARGET_UNAVAILABLE", "关系已停用，请先恢复后再确认", status_code=409)
        if existing["version"] != supplied["expected_version"]:
            raise VersionConflictError("关系已变化，请保留原稿并重新预览")
        source_id, target_id = existing["source_character_id"], existing["target_character_id"]
        target = {"kind": "existing", "novel_id": novel_id, "entity_id": str(existing["_id"]),
                  "relation_id": existing["relation_id"], "version": existing["version"]}
    endpoints = {}
    for side, identity in (("source", source_id), ("target", target_id)):
        endpoint = await BaseRepository("characters").collection.find_one({
            "novel_id": novel_key, "character_id": identity,
        }, session=session)
        if endpoint is None or endpoint["is_deleted"] or endpoint["status"] != "active":
            raise DomainApiError("CHARACTER_RELATION_FACT_ENDPOINT_UNAVAILABLE", "关系人物不存在、已回收或已停用，请先处理人物", status_code=409)
        endpoints[("characters", str(endpoint["_id"]))] = endpoint
        target[f"{side}_character"] = {"entity_id": str(endpoint["_id"]), **{
            name: endpoint[name] for name in ("character_id", "name", "status", "is_deleted", "version")}}

    target_ids = {ObjectId(identity) for identity in [*fields.get("targets", {}).values(), *fields.get("replaces", {}).values(),
                  *(identity for identities in fields.get("resolves", {}).values() for identity in identities)]
    }
    targets = [await get_character_relation_fact_history(novel_id, str(identity), session=session) for identity in sorted(target_ids)]
    if any(ObjectId(row["entity_id"]) != ObjectId(target["entity_id"]) for row in targets):
        raise DomainApiError("CHARACTER_RELATION_FACT_TARGET_INVALID", "不能处置其他关系的确认记录", status_code=409)
    if operation == "void":
        position, source, kind = (deepcopy(targets[0][name]) for name in ("position", "source", "kind"))
        selected = sorted(fields["targets"])
        protected = deepcopy(targets[0]["protected_sources"])
    else:
        position, source = deepcopy(fields["position"]), deepcopy(fields["source"])
        kind = fields.get("kind", "start")
        selected = sorted(fields["fields"])
        chain = await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        protected = [{"resource_type": item_kind, "id": str(row["_id"]),
                      "parent_id": str(row[f"{PARENTS[item_kind]}_id"]) if item_kind != "novel" else None}
                     for item_kind, row in chain]

    scope = {"target_type": position["target_type"], "target_id": position["target_id"],
             "reading_intent": "chapter_before" if kind == "change" and operation != "void" else position["intent"],
             "reading_version": 1}
    if operation == "void" and position["target_type"] in {"chapter", "volume"}:
        try:
            await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        except DomainApiError as exc:
            if exc.code != "WRITING_TARGET_NOT_FOUND":
                raise
            # 已回收卷或章没有可靠顺序；只回退读取，原记录的位置和来源仍保留。
            scope = {"target_type": "novel", "target_id": novel_id, "reading_intent": "book_start", "reading_version": 1}
    result, guards = await _load_character_relation_fact_snapshot(
        novel_id, [existing["relation_id"]] if existing else [], scope, session=session,
    )
    if operation != "void":
        guards.update({(COLLECTIONS[item_kind], str(row["_id"])): row for item_kind, row in chain})
    if existing:
        current = result["relations"][0]
        before = {"values": {name: current["values"][name] for name in selected if name in current["values"]},
                  "unknown": {name: current["unknown"][name] for name in selected if name in current["unknown"]}}
        previous = {name: current["origins"].get(name) for name in selected}
        blockers = {name: current["blockers"][name] for name in selected if name in current["blockers"]}
    else:
        before = {"values": {}, "unknown": {name: "nonexistent" for name in selected}}
        previous, blockers = {name: None for name in selected}, {}

    source_ids = {identity for identity in previous.values() if identity is not None} | {
        identity for identities in blockers.values() for identity in identities
    }
    field_sources = [await get_character_relation_fact_history(novel_id, identity, session=session) for identity in sorted(source_ids)]
    if operation != "void":
        for name, identities in fields.get("resolves", {}).items():
            if not {ObjectId(identity) for identity in identities} <= {ObjectId(identity) for identity in blockers.get(name, [])}:
                raise DomainApiError("CHARACTER_RELATION_FACT_RESOLUTION_INVALID", "只能明确处置该字段当前列出的阻断记录", status_code=409)
        # 同一边界的已有结果必须由作者逐字段选择替代，不能后写者偷偷覆盖。
        rows = await BaseRepository("entity_state_history").collection.find({
            "novel_id": novel_key, "entity_id": ObjectId(target["entity_id"]),
            "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}],
        }, session=session).to_list(length=None)
        for document in rows:
            row = parse_character_relation_fact_record(document)
            if (row["position"]["intent"] != position["intent"]
                    or ObjectId(row["position"]["target_id"]) != ObjectId(position["target_id"])):
                continue
            for name in selected:
                replaces = fields.get("replaces", {}).get(name)
                if (row["validity"][name]["state"] == "active"
                        and (replaces is None or ObjectId(replaces) != ObjectId(row["history_id"]))):
                    raise DomainApiError("CHARACTER_RELATION_FACT_POSITION_CONFLICT", "这个位置已有该字段的确认，请明确替代原记录", status_code=409)
        if source["kind"] == "chapter":
            checked = await load_chapter_record_source_in_session(novel_id, source["evidence"], session=session)
            if checked["needs_review"]:
                raise DomainApiError("CHARACTER_RELATION_FACT_SOURCE_OUTDATED", "来源正文已经变化，请重新选择当前正文证据", status_code=409)
            source["evidence"] = checked["evidence"]
            guards.update(checked["guards"])

    # 原目标可能已经回收；处置旧确认仍保护现存原父链，不要求其恢复活动。
    for row in [*targets, *field_sources]:
        for reference in row["protected_sources"]:
            resource = reference["resource_type"]
            query = {"_id": ObjectId(reference["id"])}
            if resource != "novel":
                query["novel_id"] = novel_key
            document = await BaseRepository(COLLECTIONS[resource]).collection.find_one(query, session=session)
            if document is None:
                raise DomainApiError("CHARACTER_RELATION_FACT_SOURCE_MISSING", "原确认的位置或父级已永久缺失，请先检查并恢复来源", status_code=409)
            if resource != "novel" and document[f"{PARENTS[resource]}_id"] != ObjectId(reference["parent_id"]):
                raise DomainApiError("CHARACTER_RELATION_FACT_SOURCE_CHANGED", "原确认来源的父级归属已变化，请检查记录", status_code=409)
            guards[(COLLECTIONS[resource], reference["id"])] = document

    guards.update(endpoints)
    if existing is not None:
        # 新确认不能把同一业务号重新绑定到后来替换的人物物理身份。
        for observation in result["reads"][0]["history"]:
            row = await get_character_relation_fact_history(novel_id, observation["history_id"], session=session)
            if any(ObjectId(row[f"{side}_character_entity_id"]) != ObjectId(target[f"{side}_character"]["entity_id"])
                   for side in ("source", "target")):
                raise DomainApiError("CHARACTER_RELATION_FACT_ENDPOINT_CHANGED", "原关系人物的物理身份已改变，请检查历史", status_code=409)

    basis = {"schema_version": 1, "operation": operation, "kind": kind, "target": target,
             "position": position, "source": source, "fields": selected, "before": before,
             "previous": previous, "replaces": fields.get("replaces", {}), "resolves": fields.get("resolves", {}),
             "void_targets": fields.get("targets", {}), "targets": targets, "blockers": blockers,
             "field_sources": field_sources,
             "legacy_values": {"current_state": existing["current_state"]} if existing else {}, "reads": result["reads"], "protected_sources": protected}
    basis["fingerprint"] = canonical_request_hash(basis)
    preview = CharacterRelationFactPreviewV1.model_validate({"basis": basis, "values": before}).model_dump(mode="json", exclude_unset=True)
    return preview, guards


async def preview_character_relation_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """冻结作者看到的关系身份、位置、字段原值和引用，不保存任何业务资料。

    Args:
        novel_id: 当前小说。
        data: 严格人工预览请求。
        session: 可选调用方事务；没有时使用只读事务取得一致快照。
    Returns:
        可直接保存为草稿的完整 JSON 预览。
    """
    fields = CharacterRelationFactPreviewInputV1.model_validate(data).model_dump(exclude_unset=True)
    novel_id = str(ObjectId(novel_id))
    new_entity_id = str(ObjectId()) if fields["operation"] == "create" else None

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("关系事实预览必须使用同一读取事务")
        preview, _ = await _build_character_relation_fact_preview(novel_id, fields, new_entity_id=new_entity_id, session=current_session)
        return preview

    return await read(session) if session is not None else await run_mongo_write_unit(read, "preview_character_relation_facts", require_transaction=True)


async def confirm_character_relation_facts(novel_id: str, data: dict, *, idempotency_key: str, session=None) -> dict:
    """按原预览确认关系，业务版本、历史、序号、保护和完整回执同事务全成或全败。

    Args:
        novel_id: 当前小说；原成功优先于今天的可用性检查。
        data: 作者首次派发时冻结的严格确认命令。
        idempotency_key: 原请求键；冲突不能换键重试。
        session: 可选外层必需事务。
    Returns:
        首次完整成功 JSON 结果，不改为今天的状态。
    """
    from backend.db.repositories.id_sequence_repository import id_sequence_repo
    from backend.services.novel.chapter_record_service import _replay

    command = CharacterRelationFactConfirmV1.model_validate(data).model_dump(mode="json", exclude_unset=True)
    novel_id = str(ObjectId(novel_id))
    basis = command["basis"]
    request = {"operation": command["operation"], "novel_id": novel_id,
               "target_id": basis["target"]["entity_id"], "data": command}
    fingerprint = build_idempotency_fingerprint(idempotency_key, request)

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("关系事实确认必须使用调用方事务")
        replay = await _replay(novel_id, fingerprint, expected_operation=command["operation"],
                               expected_receipt_schema="character_relation.fact.receipt", session=current_session)
        if replay is not None:
            return replay
        if ObjectId(basis["target"]["novel_id"]) != ObjectId(novel_id):
            raise DomainApiError("CHARACTER_RELATION_FACT_TARGET_INVALID", "关系预览不属于当前小说", status_code=409)
        target = basis["target"]
        if command["operation"] == "create":
            preview_input = {"operation": "create", "target": {"candidate": target["candidate"]},
                             "position": basis["position"], "source": basis["source"], "fields": basis["fields"]}
        else:
            preview_input = {"operation": command["operation"], "target": {
                "entity_id": target["entity_id"], "relation_id": target["relation_id"], "expected_version": target["version"]}}
            if command["operation"] == "void":
                preview_input["targets"] = command["targets"]
            else:
                preview_input.update({name: basis[name] for name in ("kind", "position", "source", "fields", "replaces", "resolves")})
        preview, guards = await _build_character_relation_fact_preview(
            novel_id, preview_input, new_entity_id=target["entity_id"] if target["kind"] == "new" else None, session=current_session,
        )
        if preview["basis"] != basis:
            raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "原预览的关系、人物或来源已变化，请保留原稿并重新预览", status_code=409)
        await revalidate_character_relation_fact_reads(basis["reads"], session=current_session)
        await protect_chapter_record_sources(guards, session=current_session)
        now = get_utc_now()
        now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
        if target["kind"] == "new":
            [relation_id] = await id_sequence_repo.allocate_many(novel_id, "character_relation", "cr", 1, session=current_session)
            candidate = target["candidate"]
            document = {**candidate, "_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(novel_id),
                        "relation_id": relation_id, "current_state": command["after"]["current_state"],
                        "normalized_source_character_id": candidate["source_character_id"],
                        "normalized_target_character_id": candidate["target_character_id"],
                        "semantic_key": f"{candidate['source_character_id']}:{candidate['target_character_id']}:{candidate['relation_type']}",
                        "user_is_active": True, "disabled_by_character_ids": [], "is_active": True,
                        "sort_order": candidate.get("sort_order", int(relation_id.rsplit("_", 1)[-1]) * 10),
                        "version": 1, "is_deleted": False, "deleted_at": None, "deletion_sources": [],
                        "created_at": now, "updated_at": now}
            # 旧批量仓储会重新生成 _id；这里必须保存原预览中待用的物理身份。
            await BaseRepository("character_relations").collection.insert_one(document, session=current_session)
            before_version, after_version = None, 1
        else:
            relation_id = target["relation_id"]
            before_version, after_version = target["version"], target["version"] + 1
            mirror = command["after"] if command["operation"] == "correct_initial" else {}
            updated = await BaseRepository("character_relations").collection.update_one({
                "_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(novel_id),
                "relation_id": relation_id, "version": before_version, "is_deleted": False, "is_active": True,
                "source_character_id": target["source_character"]["character_id"],
                "target_character_id": target["target_character"]["character_id"],
            }, {"$inc": {"version": 1}, "$set": {**mirror, "updated_at": now}}, session=current_session)
            if updated.matched_count != 1:
                raise VersionConflictError("关系在确认期间已变化，请保留原稿并重新预览")
        identities = {"novel_id": novel_id, "entity_id": target["entity_id"], "relation_id": relation_id}
        for side in ("source", "target"):
            endpoint = target[f"{side}_character"]
            identities.update({f"{side}_character_id": endpoint["character_id"],
                               f"{side}_character_entity_id": endpoint["entity_id"],
                               f"{side}_character_name": endpoint["name"]})
        record = None
        if command["operation"] != "void":
            record = CharacterRelationFactRecordV1.model_validate({
                "schema_id": "character_relation.fact", "schema_version": 1, "history_id": str(ObjectId()),
                **identities, "entity_type": "character_relation", "operation": command["operation"],
                "kind": basis["kind"], "position": basis["position"], "source": basis["source"],
                "before_version": before_version, "after_version": after_version, "before": basis["before"],
                "after": command["after"], "previous": basis["previous"], "replaces": basis["replaces"],
                "resolves": basis["resolves"], "validity": {"current_state": {"state": "active"}},
                "protected_sources": basis["protected_sources"], "confirmed_at": now,
            }).model_dump(mode="json", exclude_unset=True)
            await BaseRepository("entity_state_history").collection.insert_one(
                character_relation_fact_record_document(record), session=current_session,
            )
        changes = []
        dispositions = command["targets"] if command["operation"] == "void" else basis["replaces"]
        for name, identity in dispositions.items():
            validity = ({"state": "voided", "by_receipt_key_hash": fingerprint.key_hash}
                        if command["operation"] == "void" else {"state": "replaced", "by_history_id": record["history_id"]})
            changed = await BaseRepository("entity_state_history").collection.update_one({
                "_id": ObjectId(identity), "novel_id": ObjectId(novel_id), "entity_id": ObjectId(target["entity_id"]),
                "schema_id": "character_relation.fact", "schema_version": 1, f"validity.{name}": {"state": "active"},
            }, {"$set": {f"validity.{name}": validity}}, session=current_session)
            if changed.matched_count != 1:
                raise VersionConflictError("待处置状态已被替代或作废，请保留原稿并重新预览")
            changes.append({"history_id": identity, "field": name, "before": {"state": "active"}, "after": validity})
        result = CharacterRelationFactResultV1.model_validate({
            "schema_version": 1, "operation": command["operation"], **identities,
            "before_version": before_version, "after_version": after_version, "record": record,
            "validity_changes": changes, "confirmed_at": now,
        }).model_dump(mode="json", exclude_unset=True)
        receipt = character_relation_fact_receipt_document({
            "schema_id": "character_relation.fact.receipt", "schema_version": 1, "receipt_id": str(ObjectId()),
            "novel_id": novel_id, "operation": command["operation"], "idempotency_key_hash": fingerprint.key_hash,
            "request_hash": fingerprint.request_hash, "request": request, "result": result,
            "position": basis["position"], "source": basis["source"],
            "protected_sources": basis["protected_sources"], "created_at": now,
        })
        await BaseRepository("chapter_record_confirmation_receipts").collection.insert_one(receipt, session=current_session)
        return result

    return await save(session) if session is not None else await run_mongo_write_unit(save, "confirm_character_relation_facts", require_transaction=True)
