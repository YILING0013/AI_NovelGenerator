"""物品整组事实读取、人工预览与必需事务保存。"""

import hashlib
from copy import deepcopy

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError, VersionConflictError
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint, canonical_request_hash
from backend.services.novel.item_fact_contract import (
    ITEM_FACT_FIELDS, ItemFactReadV1, ItemFactPreviewInputV1, ItemFactPreviewV1,
    ItemFactConfirmV1, ItemFactRecordV1, ItemFactResultV1, ItemFactCreateDataV1,
    parse_item_fact_record, item_fact_record_document, item_fact_receipt_document,
)
from backend.services.novel.item_fact_reader import evaluate_item_facts
from backend.services.novel.chapter_record_source import RELATED_ENTITIES, load_chapter_record_source_in_session, protect_chapter_record_sources
from backend.services.novel.writing_context import COLLECTIONS, PARENTS, load_writing_parents, resolve_writing_position, writing_order


REFERENCES = (("character", "characters", "character_id", "owner_character_id", "status"),
              ("faction", "factions", "faction_id", "controlling_faction_id", "active_status"),
              ("location", "locations", "location_id", "current_location_id", "status"))


async def ensure_item_fields_unmanaged(novel_id: str, item_ids: list[str], *, session=None, protect: bool = True) -> None:
    """旧状态只允许在从未认领时修改，作废或来源失效不解除认领。

    Args:
        novel_id: 当前小说。
        item_ids: 实际修改四项状态的物品编号。
        session: 写入时的原事务。
        protect: 写入时保护空查询，候选准备只读时传 False。
    Returns:
        无；已有整组记录时拒绝旧写入。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("物品状态保护必须使用原保存事务")
    chain = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    items = await BaseRepository("items").collection.find({
        "novel_id": ObjectId(novel_id), "item_id": {"$in": item_ids},
    }, session=session).to_list(length=None)
    by_id = {row["item_id"]: row for row in items}
    records = await BaseRepository("entity_state_history").collection.find({"$and": [
        {"$or": [{"entity_id": {"$in": [row["_id"] for row in items]}},
                  {"novel_id": ObjectId(novel_id), "item_id": {"$in": item_ids}}]},
        {"$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]},
    ]}, session=session).to_list(length=None)
    for document in records:
        try:
            record = parse_item_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品状态记录格式不正确，请检查记录", status_code=409) from exc
        item = by_id.get(record["item_id"])
        if item is None or ObjectId(record["entity_id"]) != item["_id"] or ObjectId(record["novel_id"]) != ObjectId(novel_id):
            raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品状态记录的身份或所属小说不一致", status_code=409)
    if records:
        raise DomainApiError("ITEM_FACT_MANAGED_FIELDS", "物品状态已有明确位置，请从按章状态中记录变化或更正", status_code=409)
    if protect:
        await protect_chapter_record_sources({("novels", novel_id): chain[0][1]}, session=session)


async def query_item_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """页面查询复用原读取器，最新位置与人物使用同一解析方法。

    Args:
        novel_id: 当前小说。
        data: 物品编号及可省略的位置。
        session: 可选调用方事务。
    Returns:
        实际位置和每件物品的完整状态或未知原因。
    """
    from backend.services.novel.item_fact_api_contract import ItemFactQueryV1
    from backend.services.novel.character_fact_service import resolve_latest_character_fact_position

    query = ItemFactQueryV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))

    async def read(current_session):
        position = (await resolve_latest_character_fact_position(novel_id, session=current_session)
                    if query.position is None else query.position.model_dump())
        return await read_item_facts(novel_id, query.item_ids, {"target_type": position["target_type"],
            "target_id": str(ObjectId(position["target_id"])), "reading_intent": position["intent"], "reading_version": 1}, session=current_session)

    return await read(session) if session is not None else await run_mongo_write_unit(read, "query_item_facts", require_transaction=True)


async def list_item_fact_history(novel_id: str, entity_id: str | None = None, *, chapter_id: str | None = None, before_version: int | None = None, before_id: str | None = None, limit: int = 100) -> list[dict]:
    """按原物理身份分页查看状态记录，不按名称绑定后来新建的物品。

    Args:
        novel_id: 原所属小说。
        entity_id: 物品物理身份。
        chapter_id: 按章查看时的来源章，包含回收后的历史。
        before_version: 可选向前翻页版本。
        before_id: 按章翻页的原记录身份。
        limit: 本页最多100项。
    Returns:
        原记录的版本倒序列表。
    """
    query = {"novel_id": ObjectId(novel_id), "entity_type": "item",
             "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]}
    if entity_id is not None:
        query["entity_id"] = ObjectId(entity_id)
    else:
        query["position.target_type"] = "chapter"
    if chapter_id is not None:
        query["position.target_type"] = "chapter"
        query["position.target_id"] = str(ObjectId(chapter_id))
    if before_id is not None:
        query["_id"] = {"$lt": ObjectId(before_id)}
    if before_version is not None:
        query["after_version"] = {"$lt": before_version}
    rows = await BaseRepository("entity_state_history").collection.find(query).sort("after_version" if entity_id else "_id", -1).limit(limit).to_list(length=limit)
    try:
        return [parse_item_fact_record(row) for row in rows]
    except (ValueError, TypeError) as exc:
        raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品状态记录格式不正确，请检查记录", status_code=409) from exc


async def _load_item_fact_snapshot(novel_id, item_ids, position_scope, *, session):
    """在一个快照内读取活动目录、全部物品记录和真实引用，空范围也保留。

    Args:
        novel_id: 当前小说的规范物理 ID。
        item_ids: 本次实际选择的物品业务 ID。
        position_scope: 交给现有位置解析器的读取意图。
        session: 同一个已开启事务。
    Returns:
        完整读取结果，以及确认时要保护的实际来源文档。
    """
    novel_key = ObjectId(novel_id)
    parents = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    novel = parents[0][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("ITEM_FACT_PARENT_BUSY", "小说正在永久删除，请稍后读取", status_code=409)
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
    items = await BaseRepository("items").collection.find(
        {"novel_id": novel_key, "item_id": {"$in": item_ids}, "item_write_pending_token": None}, session=session,
    ).sort("item_id", 1).to_list(length=None)
    documents = await BaseRepository("entity_state_history").collection.find({"$or": [
        {"entity_type": "item", "entity_id": {"$in": [row["_id"] for row in items]}},
        {"novel_id": novel_key, "item_id": {"$in": item_ids}},
    ]}, session=session).sort("_id", 1).to_list(length=None)
    records = []
    by_id = {row["item_id"]: row for row in items}
    for document in documents:
        if "schema_id" not in document and "schema_version" not in document:
            continue  # 旧 B 只保留原审计身份，不替作者认领四字段。
        try:
            record = parse_item_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品事实记录格式不正确，请检查记录", status_code=409) from exc
        item = by_id.get(record["item_id"])
        if item is None or ObjectId(record["novel_id"]) != novel_key or ObjectId(record["entity_id"]) != item["_id"]:
            raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品事实的业务身份、物理身份或小说不一致", status_code=409)
        records.append(record)

    sources, source_validity = {}, {}
    guards = {("novels", novel_id): novel}
    guards.update({("items", str(row["_id"])): row for row in items})
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
    references, reference_validity = [], {}
    available = {}
    for kind, collection, key, field, status in REFERENCES:
        selected = sorted({values[field] for row in records for values in (row["before"]["values"], row["after"])
                           if values is not None and values[field] is not None})
        for identity in selected:
            row = await BaseRepository(collection).collection.find_one({"novel_id": novel_key, key: identity}, session=session)
            usable = bool(row is not None and not row["is_deleted"] and row[status] == "active"
                          and (kind != "location" or row.get("location_order_pending_token") is None))
            references.append({"resource_type": kind, "business_id": identity,
                               "entity_id": str(row["_id"]) if row else None, "version": row["version"] if row else None,
                               "is_deleted": row["is_deleted"] if row else None, "status": row[status] if row else None,
                               "available": usable})
            available[kind, identity] = usable
            if row is not None:
                guards[collection, str(row["_id"])] = row
    for row in records:
        reference_validity[row["history_id"]] = all(
            row["after"][field] is None or available[kind, row["after"][field]]
            for kind, _, _, field, _ in REFERENCES)
    read = {"kind": "item_facts", "novel_id": novel_id, "item_ids": item_ids, "position": position,
            "directory": directory, "identities": [{"entity_id": str(row["_id"]),
                **{name: row[name] for name in ("item_id", "name", "version", "is_deleted")}} for row in items],
            "records": records, "sources": [sources[key][0] for key in sorted(sources)], "references": references}
    read["fingerprint"] = canonical_request_hash(read)
    read = ItemFactReadV1.model_validate(read).model_dump(mode="json")
    values = [evaluate_item_facts(row, [record for record in records if ObjectId(record["entity_id"]) == row["_id"]],
                                 position, directories, source_validity, reference_validity)
              for row in items if not row["is_deleted"]]
    # 目录成员及空查询由小说 guard 保护；实际锚父链也参加同事务竞争。
    anchors = [(position["target_type"], position["target_id"])]
    anchors.extend((row["position"]["target_type"], row["position"]["target_id"]) for row in records)
    for kind, identity in anchors:
        while kind != "novel":
            row = directories[kind].get(ObjectId(identity))
            if row is None:
                break
            guards[COLLECTIONS[kind], str(row["_id"])] = row
            identity, kind = str(row[f"{PARENTS[kind]}_id"]), PARENTS[kind]
    return {"novel_id": novel_id, "position": position, "items": values,
            "missing_item_ids": sorted(set(item_ids) - {row["item_id"] for row in values}), "read": read}, guards


async def read_item_facts(novel_id: str, item_ids: list[str], position_scope: dict, *, session=None) -> dict:
    """在明确位置读取完整物品组，不以裸最新状态兜底。

    Args:
        novel_id: 当前小说。
        item_ids: 实际选择的业务 ID，空列表仍保留空查询。
        position_scope: 现有写作位置合同的目标和读取意图。
        session: 可选的同一必需事务。
    Returns:
        该位置的完整值或未知、缺失物品及固定读取依据。
    """
    from pydantic import TypeAdapter
    from backend.llm.schemas.item_pydantic import ItemId

    selected = TypeAdapter(list[ItemId]).validate_python(item_ids, strict=True)
    if len(selected) > 200 or len(selected) != len(set(selected)):
        raise ValueError("物品读取最多选择 200 个不重复 ID")
    novel_id = str(ObjectId(novel_id))

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("物品事实读取必须使用同一事务")
        result, _ = await _load_item_fact_snapshot(novel_id, sorted(selected), position_scope, session=current_session)
        return result

    return await read(session) if session is not None else await run_mongo_write_unit(read, "read_item_facts", require_transaction=True)


async def revalidate_item_fact_reads(reads: list[dict], *, session=None, protect: bool = False) -> None:
    """发送或确认前比较原物品读取，包含没有记录的原范围。

    Args:
        reads: 原读取留下的完整依据，不能用后来读取替换。
        session: 确认保存时使用的同一事务。
        protect: 比较后保护小说、物品和实际来源，必须在调用方事务中执行。
    Returns:
        无；依据变化时拒绝发送或保存，保留原稿。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("物品事实保护必须在调用方事务内执行")
    if session is None:
        return await run_mongo_write_unit(
            lambda current_session: revalidate_item_fact_reads(reads, session=current_session),
            "revalidate_item_fact_reads", require_transaction=True,
        )
    if not session.in_transaction:
        raise RuntimeError("物品事实复验必须使用同一读取事务")
    for original in reads:
        read = ItemFactReadV1.model_validate(original).model_dump(mode="json")
        position = read["position"]
        scope = {"target_type": position["target_type"], "target_id": position["target_id"],
                 "reading_intent": position["intent"], "reading_version": position["version"]}
        current, guards = await _load_item_fact_snapshot(read["novel_id"], read["item_ids"], scope, session=session)
        if current["read"] != read:
            raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品事实、来源、引用或目录已变化，请保留原稿并重新读取", status_code=409)
        if protect:
            await protect_chapter_record_sources(guards, session=session)


async def get_item_fact_history(novel_id: str, history_id: str, *, session=None) -> dict:
    """读取原物品事实，包括已回收实体及已替代、作废记录。

    Args:
        novel_id: 原所属小说。
        history_id: 原物理记录 ID。
        session: 可选调用方事务。
    Returns:
        严格原记录；未知 schema 和旧 B 不伪装新版。
    """
    document = await BaseRepository("entity_state_history").collection.find_one(
        {"_id": ObjectId(history_id), "novel_id": ObjectId(novel_id)}, session=session)
    if document is None:
        raise NotFoundError("物品事实记录不存在")
    try:
        return parse_item_fact_record(document)
    except (ValueError, TypeError) as exc:
        raise DomainApiError("ITEM_FACT_RECORD_INVALID", "物品事实记录格式不正确", status_code=409) from exc


async def _build_item_fact_preview(novel_id, fields, *, new_entity_id, session):
    """预览与确认使用同一只读流程，固定当时实际读取的依据。

    Args:
        novel_id: 当前小说的规范物理 ID。
        fields: 严格预览请求。
        new_entity_id: 新建预览待用的物理 ID；已有物品传 None。
        session: 同一个已开启事务。
    Returns:
        作者冻结预览，以及确认时要保护的实际来源文档。
    """
    from backend.services.novel.item_service import ItemService, _prepare_item_content

    novel_key, operation = ObjectId(novel_id), fields["operation"]
    existing = None
    if operation == "create":
        content = _prepare_item_content(fields["candidate"])
        candidate = ItemFactCreateDataV1.model_validate({k: v for k, v in content.items()
                                                       if k not in ITEM_FACT_FIELDS | {"normalized_name"}}).model_dump()
        if await BaseRepository("items").collection.find_one({"_id": ObjectId(new_entity_id)}, session=session):
            raise DomainApiError("ITEM_FACT_CREATE_CONFLICT", "物品身份已存在，请保留原稿并重新预览", status_code=409)
        await ItemService._ensure_name_available(novel_id, content["normalized_name"], exclude_item_id=None, session=session)
        target = {"kind": "new", "novel_id": novel_id, "entity_id": new_entity_id, "candidate": candidate}
    else:
        supplied = fields["target"]
        existing = await BaseRepository("items").collection.find_one({
            "_id": ObjectId(supplied["entity_id"]), "novel_id": novel_key, "item_id": supplied["item_id"],
            "is_deleted": False, "item_write_pending_token": None,
        }, session=session)
        if existing is None:
            raise NotFoundError("物品不存在、已回收或不属于当前小说")
        if existing["version"] != supplied["expected_version"]:
            raise VersionConflictError("物品已变化，请保留原稿并重新预览")
        target = {"kind": "existing", "novel_id": novel_id, "entity_id": str(existing["_id"]),
                  **{key: existing[key] for key in ("item_id", "name", "version", "is_deleted")}}

    if operation == "void":
        original = await get_item_fact_history(novel_id, fields["history_id"], session=session)
        if ObjectId(original["entity_id"]) != ObjectId(target["entity_id"]) or original["item_id"] != target["item_id"]:
            raise DomainApiError("ITEM_FACT_TARGET_INVALID", "不能作废其他物品的记录", status_code=409)
        position, source, kind, protected = (deepcopy(original[k]) for k in ("position", "source", "kind", "protected_sources"))
    else:
        position, source, kind = deepcopy(fields["position"]), deepcopy(fields["source"]), fields.get("kind", "start")
        position["target_id"] = str(ObjectId(position["target_id"]))
        chain = await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        protected = [{"resource_type": kind, "id": str(row["_id"]),
                      "parent_id": str(row[f"{PARENTS[kind]}_id"]) if kind != "novel" else None} for kind, row in chain]
    scope = {"target_type": position["target_type"], "target_id": position["target_id"],
             "reading_intent": "chapter_before" if kind == "change" and operation != "void" else position["intent"], "reading_version": 1}
    if operation == "void" and position["target_type"] in {"chapter", "volume"}:
        try:
            await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        except DomainApiError as exc:
            if exc.code != "WRITING_TARGET_NOT_FOUND":
                raise
            scope = {"target_type": "novel", "target_id": novel_id, "reading_intent": "book_start", "reading_version": 1}
    result, guards = await _load_item_fact_snapshot(novel_id, [existing["item_id"]] if existing else [], scope, session=session)
    if existing:
        current = result["items"][0]
        before = {key: current[key] for key in ("values", "unknown")}
        previous, blockers = current["origin"], current["blockers"]
    else:
        before, previous, blockers = {"values": None, "unknown": "nonexistent"}, None, []
    if operation != "void":
        guards.update({(COLLECTIONS[k], str(row["_id"])): row for k, row in chain})
        for row in result["read"]["records"]:
            if (row["position"]["intent"] == position["intent"] and ObjectId(row["position"]["target_id"]) == ObjectId(position["target_id"])
                    and row["validity"]["state"] == "active"
                    and (fields.get("replaces") is None or ObjectId(fields["replaces"]) != ObjectId(row["history_id"]))):
                raise DomainApiError("ITEM_FACT_POSITION_CONFLICT", "这个位置已有完整物品状态，请明确替代原记录", status_code=409)
        if source["kind"] == "chapter":
            checked = await load_chapter_record_source_in_session(novel_id, source["evidence"], session=session)
            if checked["needs_review"]:
                raise DomainApiError("ITEM_FACT_SOURCE_OUTDATED", "来源正文已变化，请重新选择当前证据", status_code=409)
            source["evidence"] = checked["evidence"]
            guards.update(checked["guards"])
    selected = {ObjectId(v) for v in [previous, fields.get("replaces"), fields.get("history_id"), *blockers, *fields.get("resolves", [])] if v is not None}
    for row in result["read"]["records"]:
        if ObjectId(row["history_id"]) not in selected:
            continue
        # 回收来源仍可作废，但不允许丢失原父链后凭旧顺序猜位置。
        for ref in row["protected_sources"]:
            resource = ref["resource_type"]
            query = {"_id": ObjectId(ref["id"])}
            if resource != "novel":
                query["novel_id"] = novel_key
            document = await BaseRepository(COLLECTIONS[resource]).collection.find_one(query, session=session)
            if document is None:
                raise DomainApiError("ITEM_FACT_SOURCE_MISSING", "原记录的位置或父级已缺失，请先恢复来源", status_code=409)
            if resource != "novel" and document[f"{PARENTS[resource]}_id"] != ObjectId(ref["parent_id"]):
                raise DomainApiError("ITEM_FACT_SOURCE_CHANGED", "原来源的父级归属已变化，请检查记录", status_code=409)
            guards[COLLECTIONS[resource], ref["id"]] = document
    legacy_values = {key: existing[key] for key in ITEM_FACT_FIELDS} if existing else None
    reference_selection = fields.get("reference_selection")
    preview_references = []
    # 旧字段没有历史时仍需核对；准备换入的新引用也必须先让作者看到原版本。
    for reference_kind, collection, key, field, status in REFERENCES:
        identities = sorted({values[field] for values in (legacy_values, reference_selection)
                             if values is not None and values[field] is not None})
        for identity in identities:
            row = await BaseRepository(collection).collection.find_one({"novel_id": novel_key, key: identity}, session=session)
            preview_references.append({"resource_type": reference_kind, "business_id": identity,
                "entity_id": str(row["_id"]) if row else None, "version": row["version"] if row else None,
                "is_deleted": row["is_deleted"] if row else None, "status": row[status] if row else None,
                "available": bool(row is not None and not row["is_deleted"] and row[status] == "active"
                                  and (reference_kind != "location" or row.get("location_order_pending_token") is None))})
            if row is not None:
                guards[collection, str(row["_id"])] = row
    basis = {"schema_version": 1, "operation": operation, "kind": kind, "target": target,
             "position": position, "source": source, "before": before, "previous": previous, "blockers": blockers,
             "replaces": fields.get("replaces"), "resolves": fields.get("resolves", []),
             "void_target": fields.get("history_id"),
             "legacy_values": legacy_values, "reference_selection": reference_selection, "preview_references": preview_references,
             "read": result["read"], "protected_sources": protected}
    basis["fingerprint"] = canonical_request_hash(basis)
    return ItemFactPreviewV1.model_validate({"basis": basis, "values": before}).model_dump(mode="json"), guards


async def preview_item_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """只读冻结人工确认所见原依据，不写 guard、不占序号。

    Args:
        novel_id: 当前小说。
        data: 六动作之一的严格预览请求。
        session: 可选外层必需事务。
    Returns:
        可原样保留为草稿的 JSON 预览。
    """
    fields = ItemFactPreviewInputV1.model_validate(data).model_dump()
    novel_id = str(ObjectId(novel_id))
    new_id = str(ObjectId()) if fields["operation"] == "create" else None

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("物品事实预览必须使用同一事务")
        preview, _ = await _build_item_fact_preview(novel_id, fields, new_entity_id=new_id, session=current_session)
        return preview

    return await read(session) if session is not None else await run_mongo_write_unit(read, "preview_item_facts", require_transaction=True)


async def confirm_item_facts(novel_id: str, data: dict, *, idempotency_key: str, session=None) -> dict:
    """先回放原成功，再同事务复验、保护来源、CAS 和保存整组记录。

    Args:
        novel_id: 原所属小说，旧成功优先于今天的可用性。
        data: 首次派发时冻结的严格确认命令。
        idempotency_key: 原确认键，同键不同内容拒绝。
        session: 可选外层必需事务。
    Returns:
        首次完整成功 JSON；失败不留下局部字段或回执。
    """
    from backend.db.repositories.id_sequence_repository import id_sequence_repo
    from backend.db.repositories.item_repository import item_repo
    from backend.services.novel.chapter_record_service import _replay
    from backend.services.novel.item_service import ItemService, _prepare_item_content

    command = ItemFactConfirmV1.model_validate(data).model_dump(mode="json")
    novel_id, basis = str(ObjectId(novel_id)), command["basis"]
    request = {"operation": command["operation"], "novel_id": novel_id, "target_id": basis["target"]["entity_id"], "data": command}
    fingerprint = build_idempotency_fingerprint(idempotency_key, request)

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("物品事实确认必须使用同一事务")
        replay = await _replay(novel_id, fingerprint, expected_operation=command["operation"],
                               expected_receipt_schema="item.fact.receipt", session=current_session)
        if replay is not None:
            return replay
        target = basis["target"]
        if ObjectId(target["novel_id"]) != ObjectId(novel_id):
            raise DomainApiError("ITEM_FACT_TARGET_INVALID", "物品预览不属于当前小说", status_code=409)
        if command["operation"] == "create":
            preview_input = {"operation": "create", "candidate": target["candidate"], "position": basis["position"],
                             "source": basis["source"], "reference_selection": basis["reference_selection"]}
        else:
            preview_input = {"operation": command["operation"], "target": {"entity_id": target["entity_id"],
                             "item_id": target["item_id"], "expected_version": target["version"]}}
            if command["operation"] == "void":
                preview_input["history_id"] = command["history_id"]
            else:
                preview_input.update({key: basis[key] for key in ("kind", "position", "source", "replaces", "resolves", "reference_selection")})
        preview, guards = await _build_item_fact_preview(novel_id, preview_input,
            new_entity_id=target["entity_id"] if target["kind"] == "new" else None, session=current_session)
        if preview["basis"] != basis:
            raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "原物品、来源、引用或目录已变化，请保留原稿并重新预览", status_code=409)
        if command["operation"] != "void":
            references = {(row["resource_type"], row["business_id"]): row
                          for row in [*basis["read"]["references"], *basis["preview_references"]]}
            if any(command["after"][field] is not None and not references[kind, command["after"][field]]["available"]
                   for kind, _, _, field, _ in REFERENCES):
                raise DomainApiError("ITEM_REFERENCE_NOT_FOUND", "原预览中的物品引用不可用，请保留草稿并重新预览", status_code=409)
            dependencies = await ItemService._load_dependencies(novel_id,
                **{field: command["after"][field] for _, _, _, field, _ in REFERENCES}, session=current_session)
            guards.update({(collection, str(row["_id"])): row for (_, collection, _, _, _), row in zip(REFERENCES, dependencies) if row is not None})
        await protect_chapter_record_sources(guards, session=current_session)
        now = get_utc_now()
        now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
        if target["kind"] == "new":
            siblings = await item_repo.list_active_items(novel_id, session=current_session)
            ItemService._ensure_active_order(siblings)
            [item_id] = await id_sequence_repo.allocate_many(novel_id, "item", "item", 1, session=current_session)
            await item_repo.create_item({**_prepare_item_content({**target["candidate"], **command["after"]}),
                "_id": ObjectId(target["entity_id"]), "novel_id": novel_id, "item_id": item_id,
                "order_index": len(siblings) + 1, "created_at": now, "updated_at": now}, session=current_session)
            before_version, after_version, name = None, 1, target["candidate"]["name"]
        else:
            item_id, name = target["item_id"], target["name"]
            before_version, after_version = target["version"], target["version"] + 1
            # 只维护更正书初的兼容值；旧章 after 绝不回写为最新终态快照。
            mirror = command["after"] if command["operation"] == "correct_initial" else {}
            changed = await BaseRepository("items").collection.update_one({
                "_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(novel_id), "item_id": item_id,
                "version": before_version, "is_deleted": False, "item_write_pending_token": None,
            }, {"$inc": {"version": 1}, "$set": {**mirror, "updated_at": now}}, session=current_session)
            if changed.matched_count != 1:
                raise VersionConflictError("物品在确认期间已变化，请保留原稿并重新预览")
        identities = {"novel_id": novel_id, "entity_id": target["entity_id"], "item_id": item_id, "item_name": name}
        record = None
        if command["operation"] != "void":
            record = ItemFactRecordV1.model_validate({
                "schema_id": "item.fact", "schema_version": 1, "history_id": str(ObjectId()), "entity_type": "item",
                **identities, "operation": command["operation"], "before_version": before_version, "after_version": after_version,
                **{key: basis[key] for key in ("kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources")},
                "after": command["after"], "validity": {"state": "active"}, "confirmed_at": now,
            }).model_dump(mode="json")
            await BaseRepository("entity_state_history").collection.insert_one(item_fact_record_document(record), session=current_session)
        disposition = command["history_id"] if command["operation"] == "void" else basis["replaces"]
        changes = []
        if disposition is not None:
            validity = ({"state": "voided", "by_receipt_key_hash": fingerprint.key_hash} if record is None
                        else {"state": "replaced", "by_history_id": record["history_id"]})
            changed = await BaseRepository("entity_state_history").collection.update_one({
                "_id": ObjectId(disposition), "novel_id": ObjectId(novel_id), "entity_id": ObjectId(target["entity_id"]),
                "item_id": item_id, "schema_id": "item.fact", "schema_version": 1, "validity": {"state": "active"},
            }, {"$set": {"validity": validity}}, session=current_session)
            if changed.matched_count != 1:
                raise VersionConflictError("原物品记录已被替代或作废，请重新预览")
            changes = [{"history_id": disposition, "before": {"state": "active"}, "after": validity}]
        result = ItemFactResultV1.model_validate({"schema_version": 1, "operation": command["operation"], **identities,
            "before_version": before_version, "after_version": after_version, "record": record,
            "validity_changes": changes, "confirmed_at": now}).model_dump(mode="json")
        receipt = item_fact_receipt_document({"schema_id": "item.fact.receipt", "schema_version": 1,
            "receipt_id": str(ObjectId()), "novel_id": novel_id, "operation": command["operation"],
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash, "request": request,
            "result": result, **{key: basis[key] for key in ("position", "source", "protected_sources")}, "created_at": now})
        await BaseRepository("chapter_record_confirmation_receipts").collection.insert_one(receipt, session=current_session)
        return result

    return await save(session) if session is not None else await run_mongo_write_unit(save, "confirm_item_facts", require_transaction=True)


async def preview_item_fact_batch(novel_id: str, data: dict) -> dict:
    """为原AI整批候选准备明确起点，不保存任何一件物品。

    Args:
        novel_id: 当前小说。
        data: 原批次与作者共同选择的位置和说明。
    Returns:
        原批次及逐项完整预览，最终仍一次确认整批。
    """
    from backend.services.novel.item_fact_api_contract import ItemFactBatchPreviewInputV1
    from backend.services.novel.item_service import ItemService, _prepare_item_content
    from backend.services.llm.item_generation_contract import validate_item_candidates

    request = ItemFactBatchPreviewInputV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))

    async def prepare(session):
        context = await ItemService._validate_bulk_basis_sources(novel_id, request.generation, session=session, allow_item_write_lock=False)
        validate_item_candidates(request.generation.candidates, request.generation.basis.generation_input, context, require_generated_count=False)
        entries = []
        for candidate in request.generation.candidates:
            content = _prepare_item_content(candidate.model_dump(exclude={"candidate_ref"}))
            after = {field: content[field] for field in ITEM_FACT_FIELDS}
            preview = await preview_item_facts(novel_id, {
                "operation": "create", "candidate": {key: value for key, value in content.items() if key not in ITEM_FACT_FIELDS | {"normalized_name"}},
                "position": request.position.model_dump(), "source": {"kind": "author", "note": request.note},
                "reference_selection": {field: after[field] for _, _, _, field, _ in REFERENCES},
            }, session=session)
            entries.append({"candidate_ref": candidate.candidate_ref, "preview": preview, "after": after})
        return {"generation": request.generation.model_dump(mode="json"), "entries": entries}

    return await run_mongo_write_unit(prepare, "preview_item_fact_batch", require_transaction=True)


async def confirm_item_fact_batch(novel_id: str, data: dict, *, idempotency_key: str, session=None) -> dict:
    """同一事务保存整批物品及起点，沿用原批次映射和成功快照格式。

    Args:
        novel_id: 当前小说。
        data: 原完整批次及所有冻结的创建请求。
        idempotency_key: 整批首次派发时保留的原键。
        session: 可选调用方事务。
    Returns:
        整批首次成功的映射与快照，重试先回放且不重新检查来源。
    """
    from backend.db.repositories.confirmation_receipt_repository import item_confirmation_receipt_repo
    from backend.services.novel.item_fact_api_contract import ItemFactBatchConfirmV1
    from backend.services.novel.item_service import ItemService, _prepare_item_content
    from backend.services.llm.item_generation_contract import validate_item_candidates

    request = ItemFactBatchConfirmV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))
    fingerprint = build_idempotency_fingerprint(idempotency_key, {"novel_id": novel_id, **request.model_dump(mode="json")})

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("物品整批确认必须使用同一事务")
        replay = await ItemService._load_confirmation_receipt(novel_id, fingerprint.key_hash, fingerprint.request_hash, session=current_session)
        if replay is not None:
            return ItemService._confirmation_receipt_result(replay)
        context = await ItemService._validate_bulk_basis_sources(novel_id, request.generation, session=current_session, allow_item_write_lock=False)
        validate_item_candidates(request.generation.candidates, request.generation.basis.generation_input, context, require_generated_count=False)
        # 整批生成读过的资料也参加原事务保护，不能只保护候选实际选中的三个引用。
        guards = {}
        for ref in request.generation.basis.source_refs:
            collection, identity_field = ("novels", "_id") if ref.resource_type == "novel" else RELATED_ENTITIES[ref.resource_type]
            query = {identity_field: ObjectId(ref.id) if identity_field == "_id" else ref.id, "version": ref.version}
            if identity_field != "_id":
                query["novel_id"] = ObjectId(novel_id)
            row = await BaseRepository(collection).collection.find_one(query, session=current_session)
            if row is None:
                raise DomainApiError("ITEM_BASIS_CONFLICT", "物品批次所用资料已变化，请保留原批次", status_code=409)
            guards[collection, str(row["_id"])] = row
        await protect_chapter_record_sources(guards, session=current_session)
        created, mapping = [], {}
        for candidate, entry in zip(request.generation.candidates, request.entries, strict=True):
            content = _prepare_item_content(candidate.model_dump(exclude={"candidate_ref"}))
            command = entry.command.model_dump(mode="json")
            design = {key: value for key, value in content.items() if key not in ITEM_FACT_FIELDS | {"normalized_name"}}
            if command["basis"]["target"]["candidate"] != design or command["after"] != {field: content[field] for field in ITEM_FACT_FIELDS}:
                raise DomainApiError("ITEM_BASIS_CONFLICT", "候选与起点预览不同，请保留整批并重新预览", status_code=409)
            saved = await confirm_item_facts(novel_id, command,
                idempotency_key=f"item-batch:{fingerprint.key_hash}:{entry.candidate_ref}", session=current_session)
            row = await BaseRepository("items").collection.find_one({"_id": ObjectId(saved["entity_id"])}, session=current_session)
            created.append(row)
            mapping[entry.candidate_ref] = saved["item_id"]
        await item_confirmation_receipt_repo.create_receipt({"novel_id": novel_id,
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash,
            "candidate_ref_map": mapping, "items_snapshot": deepcopy(created)}, session=current_session)
        return {"candidate_ref_map": mapping, "items": created}

    return await save(session) if session is not None else await run_mongo_write_unit(save, "confirm_item_fact_batch", require_transaction=True)
