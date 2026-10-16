"""读取人物在明确位置的事实，并保护作者实际使用过的读取依据。"""

from __future__ import annotations

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
from backend.services.novel.character_fact_contract import (
    CHARACTER_FACT_FIELDS, CHARACTER_FACT_PROFILE_FIELDS, CHARACTER_FACT_SITUATION_FIELDS,
    CharacterFactReadResultV1, CharacterFactReadV1,
    CharacterFactPreviewInputV1, CharacterFactPreviewV1, CharacterFactConfirmV1,
    CharacterFactRecordV1, CharacterFactResultV1, CharacterFactReceiptV1,
    CharacterFactQueryV1,
    character_fact_record_document, parse_character_fact_record,
)
from backend.services.novel.character_fact_reader import evaluate_character_facts
from backend.services.novel.chapter_record_source import (
    RELATED_ENTITIES, load_chapter_record_source_in_session, protect_chapter_record_sources, load_fact_source_observations,
)
from backend.services.novel.writing_context import (
    COLLECTIONS, PARENTS, load_writing_parents, resolve_writing_position, writing_order,
)


async def _load_character_fact_snapshot(novel_id, character_ids, position_scope, *, session):
    """一次读取只使用同一份目录、人物身份、确认记录及正文来源。"""
    novel_key = ObjectId(novel_id)
    parents = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    novel = parents[0][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("CHARACTER_FACT_PARENT_BUSY", "小说正在永久删除，请稍后读取", status_code=409)
    directories = {}
    for kind in PARENTS:
        documents = await BaseRepository(COLLECTIONS[kind]).collection.find(
            {"novel_id": novel_key, "is_deleted": False}, {"content": 0}, session=session,
        ).limit(10001).to_list(length=10001)
        if len(documents) > 10000:
            raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "目录超过单次读取范围，请先整理目录", status_code=409)
        directories[kind] = {document["_id"]: document for document in documents}
    position = resolve_writing_position({**position_scope, "novel_id": novel_id}, directories)
    characters = await BaseRepository("characters").collection.find(
        {"novel_id": novel_key, "character_id": {"$in": character_ids}}, session=session,
    ).sort("character_id", 1).to_list(length=None)
    records = []
    # 同时按实体物理身份和业务身份读取，错误标记或错误归属不能被当成空结果。
    documents = await BaseRepository("entity_state_history").collection.find({
        "novel_id": novel_key,
        "$or": [{"entity_id": {"$in": [row["_id"] for row in characters]}},
                {"character_id": {"$in": character_ids}}],
    }, session=session).sort("_id", 1).to_list(length=None)
    for document in documents:
        if "schema_id" not in document and "schema_version" not in document:
            continue  # 旧 A 审计没有人物起点，不能升级成完整事实。
        try:
            record = parse_character_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物确认记录格式不正确，请检查记录", status_code=409) from exc
        if record["character_id"] not in character_ids or any(
            row["character_id"] == record["character_id"] and str(row["_id"]) != record["entity_id"]
            for row in characters
        ):
            raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物确认记录的身份不一致，请检查记录", status_code=409)
        records.append(record)

    sources, source_validity, source_guards = await load_fact_source_observations(novel_key, records, directories, session=session)
    guards = {("novels", novel_id): novel}
    for character in characters:
        guards[("characters", str(character["_id"]))] = character
    guards.update(source_guards)

    directory = [{"resource_type": kind, "id": str(row["_id"]),
                  "parent_id": str(row[f"{PARENTS[kind]}_id"]), "order_index": row["order_index"]}
                 for kind, rows in directories.items() for row in rows.values()]
    directory.sort(key=lambda row: (row["resource_type"], row["id"]))
    read = {
        "kind": "character_facts", "novel_id": novel_id, "character_ids": character_ids,
        "position": position, "directory": directory,
        "identities": [{"entity_id": str(row["_id"]), "character_id": row["character_id"],
                        "name": row["name"], "is_deleted": row["is_deleted"]} for row in characters],
        "history": [{"history_id": row["history_id"], "entity_id": row["entity_id"],
                     "immutable_fingerprint": canonical_request_hash({key: value for key, value in row.items() if key != "validity"}),
                     "validity": row["validity"]} for row in records],
        "sources": sources,
    }
    read["fingerprint"] = canonical_request_hash(read)
    active = [row for row in characters if not row["is_deleted"]]
    result = {
        "novel_id": novel_id, "position": position,
        "characters": [evaluate_character_facts(
            row, [record for record in records if record["entity_id"] == str(row["_id"])],
            position, directories, source_validity,
        ) for row in active],
        "missing_character_ids": sorted(set(character_ids) - {row["character_id"] for row in active}),
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
    return CharacterFactReadResultV1.model_validate(result).model_dump(exclude_unset=True), guards


async def read_character_facts(
    novel_id: str, character_ids: list[str], position_scope: dict[str, Any], *,
    session: AsyncClientSession | None = None,
) -> dict:
    """共享读取人物在书初、章前后或父级边界的已确认事实。

    Args:
        novel_id: 当前小说身份。
        character_ids: 实际选择的稳定人物 ID；空列表仍冻结空查询。
        position_scope: P1 的 target_type、target_id、reading_intent、reading_version。
        session: 确认事务使用调用方会话；普通读取返回前重读原依据。
    Returns:
        完整十五字段的值或未知原因、来源及可原样复验的 reads。
    """
    selected = sorted(set(character_ids))
    result, _ = await _load_character_fact_snapshot(novel_id, selected, position_scope, session=session)
    if session is None or not session.in_transaction:
        checked, _ = await _load_character_fact_snapshot(novel_id, selected, position_scope, session=session)
        if checked["reads"] != result["reads"]:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物事实或目录正在变化，请重新读取", status_code=409)
    return result


async def revalidate_character_fact_reads(
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
        raise RuntimeError("人物事实保护必须在调用方事务内执行")
    for original in reads:
        read = CharacterFactReadV1.model_validate(original).model_dump()
        position = read["position"]
        scope = {"target_type": position["target_type"], "target_id": position["target_id"],
                 "reading_intent": position["intent"], "reading_version": position["version"]}
        current, guards = await _load_character_fact_snapshot(
            read["novel_id"], read["character_ids"], scope, session=session,
        )
        if session is None or not session.in_transaction:
            checked, _ = await _load_character_fact_snapshot(
                read["novel_id"], read["character_ids"], scope, session=session,
            )
            if checked["reads"] != current["reads"]:
                raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物事实或目录正在变化，请重新读取", status_code=409)
        if current["reads"][0] != read:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物事实、来源或目录已变化，请保留原稿并重新预览", status_code=409)
        if protect:
            await protect_chapter_record_sources(guards, session=session)


async def ensure_character_fields_unmanaged(
    novel_id: str, character_ids: list[str], fields: list[str], *,
    session: AsyncClientSession | None = None, protect: bool = True,
) -> None:
    """旧写口只可修改未被作者认领的字段，空查询同样保护小说。

    Args:
        novel_id: 当前小说身份。
        character_ids: 本次涉及的人物稳定 ID。
        fields: 原请求实际包含的人物事实字段；仅参与和计划保存可为空。
        session: 保存时必须是尚未取得卷状态锁的外层事务。
        protect: 保存默认保护小说；候选准备和编辑显式传 False，只读检查且不写 guard。
    Returns:
        无；作废或替代的记录仍保留其字段认领，命中则明确拒绝。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("人物字段保护必须在调用方事务内执行")
    requested = set(fields)
    if not requested <= CHARACTER_FACT_FIELDS:
        raise ValueError("人物字段保护只能接收固定事实字段")
    chain = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    documents = await BaseRepository("entity_state_history").collection.find({
        "novel_id": ObjectId(novel_id), "character_id": {"$in": character_ids},
        "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}],
    }, session=session).to_list(length=None)
    managed = set()
    for document in documents:
        try:
            record = parse_character_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物确认记录格式不正确，请检查记录", status_code=409) from exc
        managed.update(requested & record["after"].keys())
    if managed:
        raise DomainApiError("CHARACTER_FACT_MANAGED_FIELDS", "这些字段已有明确剧情位置，请从人物事实中更正：" + "、".join(sorted(managed)), status_code=409)
    if protect:
        await protect_chapter_record_sources({("novels", novel_id): chain[0][1]}, session=session)


async def get_character_fact_history(novel_id: str, history_id: str, *, session=None) -> dict:
    """读取一条严格人物事实记录，人物或来源回收后仍可查看。

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
        raise NotFoundError("人物事实记录不存在")
    try:
        return parse_character_fact_record(document)
    except (ValueError, TypeError) as exc:
        raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物确认记录格式不正确，请检查记录", status_code=409) from exc


async def list_character_fact_history(
    novel_id: str, entity_id: str, *, before_version: int | None = None, limit: int = 100, session=None,
) -> list[dict]:
    """按人物真实动作版本列出原记录，不要求人物今天仍存在。

    Args:
        novel_id: 记录所属小说。
        entity_id: 人物物理身份，不能按名称重新绑定。
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
        return [parse_character_fact_record(row) for row in rows]
    except (ValueError, TypeError) as exc:
        raise DomainApiError("CHARACTER_FACT_RECORD_INVALID", "人物确认记录格式不正确，请检查记录", status_code=409) from exc


async def resolve_latest_character_fact_position(novel_id: str, *, session=None) -> dict:
    """把最新资料解析为最后活动非空正文章后或书初，再交给共同位置读取。

    Args:
        novel_id: 当前小说。
        session: 可选调用方事务。
    Returns:
        P1 的明确位置；后续确认保存该结果，不重新解释“最新”。
    """
    async def resolve():
        await load_writing_parents(novel_id, "novel", novel_id, session=session)
        directories = {}
        for kind in PARENTS:
            rows = await BaseRepository(COLLECTIONS[kind]).collection.find({
                "novel_id": ObjectId(novel_id), "is_deleted": False,
            }, session=session).limit(10001).to_list(length=10001)
            if len(rows) > 10000:
                raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "目录超过单次读取范围，请先整理目录", status_code=409)
            directories[kind] = {row["_id"]: row for row in rows}
        chapters = [(writing_order("chapter", row, directories), row) for row in directories["chapter"].values() if row["content"].strip()]
        chapters = [(order, row) for order, row in chapters if order is not None]
        latest = max(chapters, key=lambda pair: pair[0])[1] if chapters else None
        return resolve_writing_position({
            "novel_id": novel_id, "target_type": "chapter" if latest else "novel",
            "target_id": str(latest["_id"]) if latest else novel_id,
            "reading_intent": "chapter_after" if latest else "book_start", "reading_version": 1,
        }, directories)

    result = await resolve()
    if session is None or not session.in_transaction:
        if await resolve() != result:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "最新位置正在变化，请重新读取", status_code=409)
    return result


async def query_character_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """在同一只读事务内解析查询位置并读取人物，最新位置不成为第二套时间。

    Args:
        novel_id: 当前小说。
        data: 最多 200 个稳定人物 ID 及可选书初或章前后位置。
        session: 可选调用方事务；没有时只开启一个必需事务。
    Returns:
        共同读取的完整结果，包含实际解析位置及原依据。
    """
    query = CharacterFactQueryV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("人物事实查询必须使用同一读取事务")
        position = (await resolve_latest_character_fact_position(novel_id, session=current_session)
                    if query.position is None else query.position.model_dump())
        scope = {"target_type": position["target_type"], "target_id": str(ObjectId(position["target_id"])),
                 "reading_intent": position["intent"], "reading_version": position["version"]}
        return await read_character_facts(novel_id, query.character_ids, scope, session=current_session)

    return await read(session) if session is not None else await run_mongo_write_unit(read, "query_character_facts", require_transaction=True)


async def _build_character_fact_preview(novel_id, fields, *, new_entity_id, session):
    """预览与确认重读同一份作者依据，不保存任何文档或预占业务号。"""
    from backend.services.novel.character_name import normalize_character_name

    novel_key = ObjectId(novel_id)
    operation = fields["operation"]
    existing = None
    if operation == "create":
        candidate = deepcopy(fields["target"]["candidate"])
        candidate["name"], normalized_name = normalize_character_name(candidate["name"])
        found_id = await BaseRepository("characters").collection.find_one({"_id": ObjectId(new_entity_id)}, session=session)
        name_matches = await BaseRepository("characters").collection.find({
            "novel_id": novel_key, "normalized_name": normalized_name, "is_deleted": False,
        }, {"_id": 1}, session=session).to_list(length=None)
        if found_id is not None or name_matches:
            raise DomainApiError("CHARACTER_FACT_CREATE_CONFLICT", "人物身份或名称已有记录，请保留原稿并重新预览", status_code=409)
        target = {"kind": "new", "novel_id": novel_id, "entity_id": new_entity_id,
                  "normalized_name": normalized_name, "candidate": candidate,
                  "entity_exists": False, "name_matches": []}
    else:
        supplied = fields["target"]
        existing = await BaseRepository("characters").collection.find_one({
            "_id": ObjectId(supplied["entity_id"]), "novel_id": novel_key,
            "character_id": supplied["character_id"], "is_deleted": False,
        }, session=session)
        if existing is None:
            raise NotFoundError("人物不存在、已回收或不属于当前小说")
        if existing["version"] != supplied["expected_version"]:
            raise VersionConflictError("人物已变化，请保留原稿并重新预览")
        target = {"kind": "existing", "novel_id": novel_id, "entity_id": str(existing["_id"]),
                  "character_id": existing["character_id"], "name": existing["name"], "version": existing["version"]}

    target_ids = set(fields.get("targets", {}).values()) | set(fields.get("replaces", {}).values()) | {
        identity for identities in fields.get("resolves", {}).values() for identity in identities
    }
    targets = [await get_character_fact_history(novel_id, identity, session=session) for identity in sorted(target_ids)]
    if any(row["entity_id"] != target["entity_id"] for row in targets):
        raise DomainApiError("CHARACTER_FACT_TARGET_INVALID", "不能处置其他人物的确认记录", status_code=409)
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
    result, guards = await _load_character_fact_snapshot(
        novel_id, [existing["character_id"]] if existing else [], scope, session=session,
    )
    if existing:
        current = result["characters"][0]
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
    field_sources = [await get_character_fact_history(novel_id, identity, session=session) for identity in sorted(source_ids)]
    if operation != "void":
        for name, identities in fields.get("resolves", {}).items():
            if not set(identities) <= set(blockers.get(name, [])):
                raise DomainApiError("CHARACTER_FACT_RESOLUTION_INVALID", "只能明确处置该字段当前列出的阻断记录", status_code=409)
        # 同一边界的已有结果必须由作者逐字段选择替代，不能后写者偷偷覆盖。
        rows = await BaseRepository("entity_state_history").collection.find({
            "novel_id": novel_key, "entity_id": ObjectId(target["entity_id"]),
            "position.intent": position["intent"], "position.target_id": position["target_id"],
            "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}],
        }, session=session).to_list(length=None)
        for document in rows:
            row = parse_character_fact_record(document)
            for name in selected:
                if name in row["after"] and row["validity"][name]["state"] == "active" and fields.get("replaces", {}).get(name) != row["history_id"]:
                    raise DomainApiError("CHARACTER_FACT_POSITION_CONFLICT", "这个位置已有该字段的确认，请明确替代原记录", status_code=409)
        if source["kind"] == "chapter":
            checked = await load_chapter_record_source_in_session(novel_id, source["evidence"], session=session)
            if checked["needs_review"]:
                raise DomainApiError("CHARACTER_FACT_SOURCE_OUTDATED", "来源正文已经变化，请重新选择当前正文证据", status_code=409)
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
                raise DomainApiError("CHARACTER_FACT_SOURCE_MISSING", "原确认的位置或父级已永久缺失，请先检查并恢复来源", status_code=409)
            if resource != "novel" and str(document[f"{PARENTS[resource]}_id"]) != reference["parent_id"]:
                raise DomainApiError("CHARACTER_FACT_SOURCE_CHANGED", "原确认来源的父级归属已变化，请检查记录", status_code=409)
            guards[(COLLECTIONS[resource], reference["id"])] = document

    references = sorted(fields.get("references", []), key=lambda row: (row["entity_type"], row["entity_id"]))
    reference_reads = []
    for reference in references:
        collection, identity_field = RELATED_ENTITIES[reference["entity_type"]]
        identity = ObjectId(reference["entity_id"]) if identity_field == "_id" else reference["entity_id"]
        row = await BaseRepository(collection).collection.find_one({
            "novel_id": novel_key, identity_field: identity, "is_deleted": False,
        }, session=session)
        if (row is None or row.get("is_active") is False or row.get("status") == "inactive"
                or row.get("active_status") == "inactive"):
            raise DomainApiError("CHARACTER_FACT_REFERENCE_UNAVAILABLE", "引用的资料不存在、已回收或已停用", status_code=409)
        if row.get("volume_id") is not None:
            chain = await load_writing_parents(novel_id, "volume", str(row["volume_id"]), session=session)
            guards.update({(COLLECTIONS[item_kind], str(parent["_id"])): parent for item_kind, parent in chain})
        guards[(collection, str(row["_id"]))] = row
        reference_reads.append({"reference": reference, "entity_id": str(row["_id"]), "version": row["version"]})

    legacy_sources = []
    if existing is not None:
        situation_fields = set(selected) & CHARACTER_FACT_SITUATION_FIELDS
        legacy_sources.append({"kind": "profile", "entity_id": target["entity_id"],
            "character_id": target["character_id"], "version": target["version"],
            "raw": {name: deepcopy(existing[name]) for name in selected if name in CHARACTER_FACT_PROFILE_FIELDS and name in existing},
            "notes": {"initial_state": existing["initial_state"]} if situation_fields and "initial_state" in existing else {}})
        if situation_fields:
            # 全部保留状态都是待作者核对的原文；回收状态也不能悄悄省略。
            state_fields = (situation_fields - {"actual_goal"}) | ({"current_goal"} if "actual_goal" in selected else set())
            states = await BaseRepository("character_volume_states").collection.find({
                "novel_id": novel_key, "character_id": target["character_id"],
            }, session=session).sort("_id", 1).to_list(length=None)
            for state in states:
                if state.get("state_id") != state["_id"]:
                    raise DomainApiError("CHARACTER_FACT_LEGACY_SOURCE_INVALID", "卷状态身份不一致，请检查原资料", status_code=409)
                volume = await BaseRepository("volumes").collection.find_one({"_id": state["volume_id"]}, session=session)
                if volume is not None and volume["novel_id"] != novel_key:
                    raise DomainApiError("CHARACTER_FACT_LEGACY_SOURCE_INVALID", "卷状态所属卷不属于当前小说", status_code=409)
                legacy_sources.append({"kind": "volume_state", "state_id": str(state["_id"]),
                    "character_id": state["character_id"], "version": state["version"], "is_deleted": state["is_deleted"],
                    "volume_id": str(state["volume_id"]),
                    "volume": {name: volume[name] for name in ("title", "version", "is_deleted")} if volume is not None else None,
                    "raw": {name: deepcopy(state[name]) for name in sorted(state_fields) if name in state},
                    "notes": {"start_state": state["start_state"]} if "start_state" in state else {}})
                guards[("character_volume_states", str(state["_id"]))] = state
                if volume is not None:
                    guards[("volumes", str(volume["_id"]))] = volume

    basis = {"schema_version": 1, "operation": operation, "kind": kind, "target": target,
             "position": position, "source": source, "fields": selected, "before": before,
             "previous": previous, "replaces": fields.get("replaces", {}), "resolves": fields.get("resolves", {}),
             "void_targets": fields.get("targets", {}), "targets": targets, "blockers": blockers,
             "field_sources": field_sources, "references": references, "reference_reads": reference_reads,
             "legacy_sources": legacy_sources, "reads": result["reads"], "protected_sources": protected}
    basis["fingerprint"] = canonical_request_hash(basis)
    preview = CharacterFactPreviewV1.model_validate({"basis": basis, "values": before}).model_dump(mode="json", exclude_unset=True)
    return preview, guards


async def preview_character_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """冻结作者看到的人物身份、位置、字段原值和引用，不保存任何业务资料。

    Args:
        novel_id: 当前小说。
        data: 严格人工预览请求。
        session: 可选调用方事务；没有时使用只读事务取得一致快照。
    Returns:
        可直接保存为草稿的完整 JSON 预览。
    """
    fields = CharacterFactPreviewInputV1.model_validate(data).model_dump(exclude_unset=True)
    novel_id = str(ObjectId(novel_id))
    new_entity_id = str(ObjectId()) if fields["operation"] == "create" else None

    async def read(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("人物事实预览必须使用同一读取事务")
        preview, _ = await _build_character_fact_preview(novel_id, fields, new_entity_id=new_entity_id, session=current_session)
        return preview

    return await read(session) if session is not None else await run_mongo_write_unit(read, "preview_character_facts", require_transaction=True)


async def confirm_character_facts(novel_id: str, data: dict, *, idempotency_key: str, session=None) -> dict:
    """按原预览一次确认人物字段，记录、初始镜像及完整回执全成或全败。

    Args:
        novel_id: 当前小说；同键原成功优先于今天的可用性检查。
        data: 作者首次派发时冻结的严格确认命令。
        idempotency_key: 原请求键；冲突不能换键重试。
        session: 可选外层必需事务，有值时直接加入，不另开事务。
    Returns:
        首次完整成功 JSON 结果；重放不改为今天的字段值。
    """
    from backend.db.repositories.character_repository import character_repo
    from backend.db.repositories.id_sequence_repository import id_sequence_repo
    from backend.services.novel.chapter_record_service import _replay
    from backend.services.novel.character_service import _build_character_document

    command = CharacterFactConfirmV1.model_validate(data).model_dump(mode="json", exclude_unset=True)
    novel_id = str(ObjectId(novel_id))
    basis = command["basis"]
    request = {"operation": command["operation"], "novel_id": novel_id,
               "target_id": basis["target"]["entity_id"], "data": command}
    fingerprint = build_idempotency_fingerprint(idempotency_key, request)

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("人物事实确认必须使用调用方事务")
        replay = await _replay(novel_id, fingerprint, expected_operation=command["operation"], session=current_session, expected_receipt_schema="character.fact.receipt")
        if replay is not None:
            return replay
        if basis["target"]["novel_id"] != novel_id:
            raise DomainApiError("CHARACTER_FACT_TARGET_INVALID", "人物预览不属于当前小说", status_code=409)
        target = basis["target"]
        if command["operation"] == "create":
            preview_input = {"operation": "create", "target": {"candidate": target["candidate"]},
                             "position": basis["position"], "source": basis["source"],
                             "fields": basis["fields"], "references": basis["references"]}
        else:
            preview_input = {"operation": command["operation"], "target": {
                "entity_id": target["entity_id"], "character_id": target["character_id"], "expected_version": target["version"]},
                "references": basis["references"]}
            if command["operation"] == "void":
                preview_input["targets"] = command["targets"]
            else:
                preview_input.update({name: basis[name] for name in ("kind", "position", "source", "fields", "replaces", "resolves")})
        preview, guards = await _build_character_fact_preview(
            novel_id, preview_input, new_entity_id=target["entity_id"] if target["kind"] == "new" else None, session=current_session,
        )
        if preview["basis"] != basis:
            raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "原预览的人物、字段或来源已变化，请保留原稿并重新预览", status_code=409)
        await revalidate_character_fact_reads(basis["reads"], session=current_session)
        # builder 已合并共同读取、原处置来源和人工引用；统一保护一次，再进入实体 CAS。
        await protect_chapter_record_sources(guards, session=current_session)
        now = get_utc_now()
        now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
        initial_fields = CHARACTER_FACT_FIELDS - {"psychological_state", "public_state", "hidden_state", "actual_goal"}
        mirror = ({name: value for name, value in command.get("after", {}).items() if name in initial_fields}
                  if basis["kind"] == "start" and basis["position"]["intent"] == "book_start" else {})
        if target["kind"] == "new":
            [character_id] = await id_sequence_repo.allocate_many(novel_id, "character", "char", 1, session=current_session)
            candidate = target["candidate"]
            document = _build_character_document({**candidate, **mirror}, novel_id=novel_id, character_id=character_id,
                sort_order=candidate.get("sort_order", 0), is_core_character=candidate.get("is_core_character", False))
            document["_id"] = ObjectId(target["entity_id"])
            await character_repo.create_character(document, session=current_session)
            before_version, after_version, character_name = None, 1, candidate["name"]
        else:
            character_id, character_name = target["character_id"], target["name"]
            before_version, after_version = target["version"], target["version"] + 1
            updated = await BaseRepository("characters").collection.update_one({
                "_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(novel_id),
                "character_id": character_id, "version": before_version, "is_deleted": False,
            }, {"$inc": {"version": 1}, "$set": {**mirror, "updated_at": now}}, session=current_session)
            if updated.matched_count != 1:
                raise VersionConflictError("人物在确认期间已变化，请保留原稿并重新预览")
        record = None
        if command["operation"] != "void":
            record = CharacterFactRecordV1.model_validate({
                "schema_id": "character.fact", "schema_version": 1, "history_id": str(ObjectId()),
                "novel_id": novel_id, "entity_type": "character", "entity_id": target["entity_id"],
                "character_id": character_id, "character_name": character_name, "operation": command["operation"],
                "kind": basis["kind"], "position": basis["position"], "source": basis["source"],
                "before_version": before_version, "after_version": after_version, "before": basis["before"],
                "after": command["after"], "previous": basis["previous"], "replaces": basis["replaces"],
                "resolves": basis["resolves"], "validity": {name: {"state": "active"} for name in basis["fields"]},
                "protected_sources": basis["protected_sources"], "confirmed_at": now,
            }).model_dump(mode="json", exclude_unset=True)
            await BaseRepository("entity_state_history").collection.insert_one(character_fact_record_document(record), session=current_session)
        changes = []
        disposed = command["targets"] if command["operation"] == "void" else basis["replaces"]
        for name, identity in sorted(disposed.items()):
            validity = ({"state": "voided", "by_receipt_key_hash": fingerprint.key_hash} if record is None
                        else {"state": "replaced", "by_history_id": record["history_id"]})
            changed = await BaseRepository("entity_state_history").collection.update_one({
                "_id": ObjectId(identity), "novel_id": ObjectId(novel_id), "entity_id": ObjectId(target["entity_id"]),
                "schema_id": "character.fact", "schema_version": 1, f"validity.{name}": {"state": "active"},
            }, {"$set": {f"validity.{name}": validity}}, session=current_session)
            if changed.matched_count != 1:
                raise VersionConflictError("待处置字段已被替代或作废，请保留原稿并重新预览")
            changes.append({"history_id": identity, "field": name, "before": {"state": "active"}, "after": validity})
        result = CharacterFactResultV1.model_validate({
            "schema_version": 1, "operation": command["operation"], "novel_id": novel_id,
            "entity_id": target["entity_id"], "character_id": character_id, "character_name": character_name,
            "before_version": before_version, "after_version": after_version, "record": record,
            "validity_changes": changes, "confirmed_at": now,
        }).model_dump(mode="json", exclude_unset=True)
        receipt_id = ObjectId()
        receipt = CharacterFactReceiptV1.model_validate({
            "schema_id": "character.fact.receipt", "schema_version": 1, "receipt_id": str(receipt_id),
            "novel_id": novel_id, "operation": command["operation"], "idempotency_key_hash": fingerprint.key_hash,
            "request_hash": fingerprint.request_hash, "request": request, "result": result,
            "position": basis["position"], "source": basis["source"],
            "protected_sources": basis["protected_sources"], "created_at": now,
        }).model_dump(exclude_unset=True)
        receipt.update(_id=receipt_id, novel_id=ObjectId(novel_id), request=request, result=result)
        del receipt["receipt_id"]
        await BaseRepository("chapter_record_confirmation_receipts").collection.insert_one(receipt, session=current_session)
        return result

    return await save(session) if session is not None else await run_mongo_write_unit(save, "confirm_character_facts", require_transaction=True)
