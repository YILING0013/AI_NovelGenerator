"""势力事实的内部读取、人工预览和事务保存；尚未注册产品路由。"""

from copy import deepcopy

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError, VersionConflictError
from backend.db.repositories.faction_repository import faction_repo, normalize_faction_name
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import build_idempotency_fingerprint, canonical_request_hash
from backend.services.novel.chapter_record_source import (
    RELATED_ENTITIES, load_chapter_record_source_in_session,
    load_fact_source_observations, protect_chapter_record_sources,
)
from backend.services.novel.faction_fact_contract import (
    FACTION_FACT_PROFILE_FIELDS, FactionFactBasisV1, FactionFactConfirmV1,
    FactionFactPreviewInputV1, FactionFactReadResultV1, FactionFactReadV1,
    FactionFactRecordV1, FactionFactReceiptV1, FactionFactResultV1,
    faction_fact_record_document, faction_legacy_fields, parse_faction_fact_record,
)
from backend.services.novel.faction_fact_reader import evaluate_faction_facts
from backend.services.novel.faction_service import FactionService
from backend.services.novel.writing_context import COLLECTIONS, PARENTS, load_writing_parents, resolve_writing_position


async def ensure_faction_fields_unmanaged(novel_id, faction_ids, fields, *, session=None, protect=True):
    """旧写口只保留未认领原文；空历史也须在取得状态锁前保护小说。

    Args:
        novel_id: 当前作品。
        faction_ids: 本次涉及的稳定势力身份。
        fields: 原请求实际提交的事实字段。
        session: 保存时调用方的原事务。
        protect: 预检为 False；实际保存必须保护空范围。
    Returns:
        无；作废或更正不会解除认领，命中整次拒绝。
    """
    from backend.services.novel.faction_fact_contract import FACTION_FACT_FIELDS
    requested = set(fields)
    if not requested <= FACTION_FACT_FIELDS:
        raise ValueError("势力旧写口保护只能接收事实字段")
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("势力字段保护必须使用原保存事务")
    chain = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    records = await BaseRepository("entity_state_history").collection.find({"novel_id": ObjectId(novel_id),
        "faction_id": {"$in": faction_ids}, "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]}, session=session).to_list(length=None)
    for document in records:
        try:
            record = parse_faction_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力记录需要核对；原修改已保留", status_code=409) from exc
        if requested & record["after"].keys():
            raise DomainApiError("FACTION_FACT_MANAGED_FIELDS", "这些资料已有明确剧情位置，请在势力详情中按位置更正；原输入已保留", status_code=409)
    if protect:
        await protect_chapter_record_sources({("novels", novel_id): chain[0][1]}, session=session)


async def _load_snapshot(novel_id, faction_ids, scope, *, session):
    """一次读取完整目录、真实身份、事实和原修订，返回可复验依据。"""
    novel_key = ObjectId(novel_id)
    chain = await load_writing_parents(novel_id, "novel", novel_id, session=session)
    novel = chain[0][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("FACTION_FACT_PARENT_BUSY", "小说正在永久删除，请稍后读取", status_code=409)
    directories = {}
    for kind in PARENTS:
        rows = await BaseRepository(COLLECTIONS[kind]).collection.find(
            {"novel_id": novel_key, "is_deleted": False}, {"content": 0}, session=session,
        ).limit(10001).to_list(length=10001)
        if len(rows) > 10000:
            raise DomainApiError("WRITING_CONTEXT_TOO_LARGE", "目录超过单次读取范围，请先整理目录", status_code=409)
        directories[kind] = {row["_id"]: row for row in rows}
    position = resolve_writing_position({**scope, "novel_id": novel_id}, directories)
    factions = await faction_repo.collection.find({"novel_id": novel_key, "faction_id": {"$in": faction_ids}}, session=session).sort("faction_id", 1).to_list(length=None)
    raw = await BaseRepository("entity_state_history").collection.find({
        "novel_id": novel_key, "$or": [
            {"entity_id": {"$in": [row["_id"] for row in factions]}, "$or": [{"entity_type": "faction"}, {"schema_id": "faction.fact"}]},
            {"faction_id": {"$in": faction_ids}},
        ],
    }, session=session).sort("_id", 1).to_list(length=None)
    records = []
    for document in raw:
        if "schema_id" not in document and "schema_version" not in document:
            continue
        try:
            record = parse_faction_fact_record(document)
        except (ValueError, TypeError) as exc:
            raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力确认记录格式不正确，请检查记录", status_code=409) from exc
        if record["faction_id"] not in faction_ids or any(
                row["faction_id"] == record["faction_id"] and row["_id"] != ObjectId(record["entity_id"]) for row in factions):
            raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力确认记录的身份不一致", status_code=409)
        records.append(record)
    sources, validity, source_guards = await load_fact_source_observations(novel_key, records, directories, session=session)
    guards = {("novels", novel_id): novel}
    guards.update({("factions", str(row["_id"])): row for row in factions})
    guards.update(source_guards)
    directory = [{"resource_type": kind, "id": str(row["_id"]), "parent_id": str(row[f"{PARENTS[kind]}_id"]), "order_index": row["order_index"]}
                 for kind, rows in directories.items() for row in rows.values()]
    read = {
        "kind": "faction_facts", "novel_id": novel_id, "faction_ids": faction_ids, "position": position,
        "directory": sorted(directory, key=lambda row: (row["resource_type"], row["id"])),
        "identities": [{"entity_id": str(row["_id"]), "faction_id": row["faction_id"], "name": row["name"], "is_deleted": row["is_deleted"]} for row in factions],
        "history": [{"history_id": row["history_id"], "entity_id": row["entity_id"], "validity": row["validity"],
                     "immutable_fingerprint": canonical_request_hash({key: value for key, value in row.items() if key != "validity"})} for row in records],
        "sources": sources,
    }
    read["fingerprint"] = canonical_request_hash(read)
    active = [row for row in factions if not row["is_deleted"]]
    result = FactionFactReadResultV1.model_validate({
        "novel_id": novel_id, "position": position,
        "factions": [evaluate_faction_facts(row, [r for r in records if ObjectId(r["entity_id"]) == row["_id"]], position, directories, validity) for row in active],
        "missing_faction_ids": sorted(set(faction_ids) - {row["faction_id"] for row in active}), "reads": [read],
    }).model_dump(exclude_unset=True)
    # 全目录和空范围进入摘要；仅实际锚父链参加实体保护，其他变化由小说 guard 竞争。
    for anchor in [position, *(row["position"] for row in records)]:
        kind, identity = anchor["target_type"], anchor["target_id"]
        while kind != "novel":
            row = directories[kind].get(ObjectId(identity))
            if row is None:
                break
            guards[(COLLECTIONS[kind], str(row["_id"]))] = row
            identity, kind = str(row[f"{PARENTS[kind]}_id"]), PARENTS[kind]
    return result, guards, records


async def read_faction_facts(novel_id: str, faction_ids: list[str], position_scope: dict, *, session=None) -> dict:
    """读取指定位置的势力事实及原依据，未确认字段不读裸主档。

    Args:
        novel_id: 本书身份。
        faction_ids: 稳定势力选择；空选择仍冻结空范围。
        position_scope: P1 的稳定目标及读取操作。
        session: 可选调用方事务；普通读取返回前复读依据。
    Returns:
        严格位置结果和可复验读取。
    """
    novel_id, selected = str(ObjectId(novel_id)), sorted(set(faction_ids))
    result, _, _ = await _load_snapshot(novel_id, selected, position_scope, session=session)
    if session is None or not session.in_transaction:
        checked, _, _ = await _load_snapshot(novel_id, selected, position_scope, session=session)
        if checked["reads"] != result["reads"]:
            raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力资料或目录正在变化，请重新读取", status_code=409)
    return result


async def query_faction_facts(novel_id: str, data, *, session=None) -> dict:
    """页面查询沿用原位置解析器和势力读取器。

    Args:
        novel_id: 当前小说。
        data: 稳定势力编号及可省略的位置。
        session: 可选调用方事务。
    Returns:
        同一快照中的实际位置、资料和原读取依据。
    """
    from backend.services.novel.character_fact_service import resolve_latest_character_fact_position
    from backend.services.novel.faction_fact_api_contract import FactionFactQueryV1

    query = FactionFactQueryV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))

    async def read(current_session):
        position = (await resolve_latest_character_fact_position(novel_id, session=current_session)
                    if query.position is None else query.position.model_dump())
        return await read_faction_facts(novel_id, query.faction_ids, {
            "target_type": position["target_type"], "target_id": str(ObjectId(position["target_id"])),
            "reading_intent": position["intent"], "reading_version": 1,
        }, session=current_session)

    return await read(session) if session is not None else await run_mongo_write_unit(read, "query_faction_facts", require_transaction=True)


async def list_faction_fact_history(novel_id: str, entity_id: str, *, before_version: int | None = None, limit: int = 100) -> list[dict]:
    """按原物理身份分页读取历史，不要求今天的势力或来源仍活动。

    Args:
        novel_id: 原所属小说。
        entity_id: 原势力物理身份，不是名称或业务编号。
        before_version: 可选的向前翻页版本。
        limit: 本页最多一百项。
    Returns:
        原记录及逐字段处置，按保存版本倒序。
    """
    query = {"novel_id": ObjectId(novel_id), "entity_id": ObjectId(entity_id), "entity_type": "faction",
             "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}]}
    if before_version is not None:
        query["after_version"] = {"$lt": before_version}
    rows = await BaseRepository("entity_state_history").collection.find(query).sort("after_version", -1).limit(limit).to_list(length=limit)
    try:
        return [parse_faction_fact_record(row) for row in rows]
    except (ValueError, TypeError) as exc:
        raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力记录格式不正确，请保留原稿并检查记录", status_code=409) from exc


async def get_faction_fact_history(novel_id: str, history_id: str) -> dict:
    """读取同书的一条原势力记录，拒绝跨书和其他类型。

    Args:
        novel_id: 原所属小说。
        history_id: 原记录物理身份。
    Returns:
        严格势力记录，缺失时返回明确错误。
    """
    row = await BaseRepository("entity_state_history").collection.find_one({
        "_id": ObjectId(history_id), "novel_id": ObjectId(novel_id), "entity_type": "faction",
        "$or": [{"schema_id": {"$exists": True}}, {"schema_version": {"$exists": True}}],
    })
    if row is None:
        raise NotFoundError("势力记录不存在或不属于当前小说")
    try:
        return parse_faction_fact_record(row)
    except (ValueError, TypeError) as exc:
        raise DomainApiError("FACTION_FACT_RECORD_INVALID", "势力记录格式不正确，请保留原稿并检查记录", status_code=409) from exc


async def revalidate_faction_fact_reads(reads: list[dict], *, session=None, protect: bool = False) -> None:
    """复验原读取，不将今天的新依据替换进旧请求。

    Args:
        reads: 原位置读取，包括空查询。
        session: 保存时必须使用调用方同一事务。
        protect: 是否同时保护实际来源和小说空范围。
    Returns:
        无；任一变化立即拒绝。
    """
    if protect and (session is None or not session.in_transaction):
        raise RuntimeError("势力事实保护必须使用调用方事务")
    for original in reads:
        read = FactionFactReadV1.model_validate(original).model_dump()
        position = read["position"]
        scope = {"target_type": position["target_type"], "target_id": position["target_id"], "reading_intent": position["intent"], "reading_version": 1}
        current, guards, _ = await _load_snapshot(read["novel_id"], read["faction_ids"], scope, session=session)
        if session is None or not session.in_transaction:
            checked, _, _ = await _load_snapshot(read["novel_id"], read["faction_ids"], scope, session=session)
            if checked["reads"] != current["reads"]:
                raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力资料或目录正在变化，请重新读取", status_code=409)
        if current["reads"][0] != read:
            raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力事实、来源或目录已变化，请保留原稿并重新预览", status_code=409)
        if protect:
            await protect_chapter_record_sources(guards, session=session)


async def _build_preview(novel_id, data, *, new_entity_id, session):
    """预览和确认共用同一次重建，不写文档、不预占业务序列。"""
    novel_key, operation = ObjectId(novel_id), data["operation"]
    existing, scope_guards = None, {}
    references = deepcopy(data.get("references", []))
    if operation == "create":
        candidate = deepcopy(data["target"]["candidate"])
        candidate["name"], normalized = normalize_faction_name(candidate["name"])
        owned_volume = await FactionService._validate_scope_and_parent(novel_id, level_type=candidate.get("level_type", "core"),
            volume_id=candidate.get("volume_id"), parent_faction_id=candidate.get("parent_faction_id"), session=session)
        await FactionService._ensure_unique_active_name(novel_id, candidate["name"], level_type=candidate.get("level_type", "core"), volume_id=owned_volume, session=session)
        if await faction_repo.collection.find_one({"_id": ObjectId(new_entity_id)}, session=session) is not None:
            raise DomainApiError("FACTION_FACT_CREATE_CONFLICT", "势力物理身份已有记录，请重新预览", status_code=409)
        if owned_volume is not None:
            chain = await load_writing_parents(novel_id, "volume", str(owned_volume), session=session)
            scope_guards.update({(COLLECTIONS[kind], str(row["_id"])): row for kind, row in chain})
        parent = candidate.get("parent_faction_id")
        if parent is not None and {"entity_type": "faction", "entity_id": parent} not in references:
            references.append({"entity_type": "faction", "entity_id": parent})
        target = {"kind": "new", "novel_id": novel_id, "entity_id": new_entity_id, "candidate": candidate,
                  "normalized_name": normalized, "entity_exists": False, "name_matches": []}
    else:
        supplied = data["target"]
        existing = await faction_repo.collection.find_one({"_id": ObjectId(supplied["entity_id"]), "novel_id": novel_key,
            "faction_id": supplied["faction_id"], "is_deleted": False}, session=session)
        if existing is None:
            raise NotFoundError("势力不存在、已回收或不属于当前小说")
        if existing["version"] != supplied["expected_version"]:
            raise VersionConflictError("势力已变化，请保留原稿并重新预览")
        target = {"kind": "existing", "novel_id": novel_id, "entity_id": str(existing["_id"]),
                  "faction_id": existing["faction_id"], "name": existing["name"], "version": existing["version"]}
    disposition_ids = set(data.get("targets", {}).values()) | set(data.get("replaces", {}).values()) | {i for ids in data.get("resolves", {}).values() for i in ids}
    targets = []
    for identity in sorted(disposition_ids):
        raw = await BaseRepository("entity_state_history").collection.find_one({"_id": ObjectId(identity), "novel_id": novel_key}, session=session)
        if raw is None:
            raise NotFoundError("所选势力确认记录不存在")
        row = parse_faction_fact_record(raw)
        if ObjectId(row["entity_id"]) != ObjectId(target["entity_id"]):
            raise DomainApiError("FACTION_FACT_TARGET_INVALID", "不能处置其他势力的记录", status_code=409)
        targets.append(row)
    if operation == "void":
        position, source, kind = (deepcopy(targets[0][key]) for key in ("position", "source", "kind"))
        selected, protected = sorted(data["targets"]), deepcopy(targets[0]["protected_sources"])
    else:
        position, source, kind = deepcopy(data["position"]), deepcopy(data["source"]), data.get("kind", "start")
        position["target_id"] = str(ObjectId(position["target_id"]))
        position["version"] = 1
        selected = sorted(data["fields"])
        chain = await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        protected = [{"resource_type": kind, "id": str(row["_id"]), "parent_id": str(row[f"{PARENTS[kind]}_id"]) if kind != "novel" else None} for kind, row in chain]
    scope = {"target_type": position["target_type"], "target_id": position["target_id"], "reading_version": 1,
             "reading_intent": "chapter_before" if kind == "change" and operation != "void" else position["intent"]}
    if operation == "void" and position["target_type"] in {"chapter", "volume"}:
        try:
            await load_writing_parents(novel_id, position["target_type"], position["target_id"], session=session)
        except DomainApiError as exc:
            if exc.code != "WRITING_TARGET_NOT_FOUND":
                raise
            # 回收锚没有可靠顺序；只退回读取，原卷／章位置和来源保持不变。
            scope = {"target_type": "novel", "target_id": novel_id, "reading_version": 1, "reading_intent": "book_start"}
    result, guards, records = await _load_snapshot(novel_id, [existing["faction_id"]] if existing else [], scope, session=session)
    guards.update(scope_guards)
    if existing is None:
        before, previous, blockers = {"values": {}, "unknown": {name: "nonexistent" for name in selected}}, {name: None for name in selected}, {}
    else:
        current = result["factions"][0]
        before = {part: {name: current[part][name] for name in selected if name in current[part]} for part in ("values", "unknown")}
        previous = {name: current["origins"].get(name) for name in selected}
        blockers = {name: current["blockers"][name] for name in selected if name in current["blockers"]}
    source_ids = {i for i in previous.values() if i is not None} | {i for ids in blockers.values() for i in ids}
    field_sources = [row for row in records if row["history_id"] in source_ids]
    if operation != "void":
        for row in records:
            if row["position"] == position:
                for name in selected:
                    if name in row["after"] and row["validity"][name]["state"] == "active" and data.get("replaces", {}).get(name) != row["history_id"]:
                        raise DomainApiError("FACTION_FACT_POSITION_CONFLICT", "这个位置已有该字段，请明确替代原记录", status_code=409)
        if source["kind"] == "chapter":
            checked = await load_chapter_record_source_in_session(novel_id, source["evidence"], session=session)
            if checked["needs_review"]:
                raise DomainApiError("FACTION_FACT_SOURCE_OUTDATED", "来源正文已变化，请重新选择当前正文证据", status_code=409)
            source["evidence"] = checked["evidence"]
            guards.update(checked["guards"])
    for record in [*targets, *field_sources]:
        for ref in record["protected_sources"]:
            resource = ref["resource_type"]
            query = {"_id": ObjectId(ref["id"]), **({"novel_id": novel_key} if resource != "novel" else {})}
            row = await BaseRepository(COLLECTIONS[resource]).collection.find_one(query, session=session)
            if row is None:
                raise DomainApiError("FACTION_FACT_SOURCE_MISSING", "原确认的位置或父级永久缺失，请先检查来源", status_code=409)
            if resource != "novel" and row[f"{PARENTS[resource]}_id"] != ObjectId(ref["parent_id"]):
                raise DomainApiError("FACTION_FACT_SOURCE_CHANGED", "原确认来源的父级已变化，请检查记录", status_code=409)
            guards[(COLLECTIONS[resource], str(row["_id"]))] = row
    references.sort(key=lambda row: (row["entity_type"], row["entity_id"]))
    reference_reads = []
    for ref in references:
        collection, identity_field = RELATED_ENTITIES[ref["entity_type"]]
        row = await BaseRepository(collection).collection.find_one({"novel_id": novel_key, "is_deleted": False,
            identity_field: ObjectId(ref["entity_id"]) if identity_field == "_id" else ref["entity_id"]}, session=session)
        if row is None or row.get("is_active") is False or row.get("status") == "inactive" or row.get("active_status") == "inactive":
            raise DomainApiError("FACTION_FACT_REFERENCE_UNAVAILABLE", "引用资料不存在、已回收或已停用", status_code=409)
        if row.get("volume_id") is not None:
            chain = await load_writing_parents(novel_id, "volume", str(row["volume_id"]), session=session)
            guards.update({(COLLECTIONS[k], str(parent["_id"])): parent for k, parent in chain})
        guards[(collection, str(row["_id"]))] = row
        reference_reads.append({"reference": ref, "entity_id": str(row["_id"]), "version": row["version"]})
    legacy = []
    if existing is not None:
        profile_fields, state_fields = faction_legacy_fields(set(selected))
        legacy.append({"kind": "profile", "entity_id": target["entity_id"], "faction_id": target["faction_id"],
                       "version": target["version"], "raw": {name: deepcopy(existing[name]) for name in sorted(profile_fields) if name in existing}})
        if state_fields:
            states = await BaseRepository("faction_volume_states").collection.find({"novel_id": novel_key, "faction_id": target["faction_id"]}, session=session).sort("_id", 1).to_list(length=None)
            for state in states:
                if state.get("state_id") != state["_id"]:
                    raise DomainApiError("FACTION_FACT_LEGACY_SOURCE_INVALID", "旧势力卷状态的身份不一致", status_code=409)
                volume = await BaseRepository("volumes").collection.find_one({"_id": state["volume_id"]}, session=session)
                if volume is not None and volume["novel_id"] != novel_key:
                    raise DomainApiError("FACTION_FACT_LEGACY_SOURCE_INVALID", "旧势力卷状态不属于当前小说", status_code=409)
                legacy.append({"kind": "volume_state", "state_id": str(state["_id"]), "faction_id": state["faction_id"],
                    "version": state["version"], "is_deleted": state["is_deleted"], "volume_id": str(state["volume_id"]),
                    "volume": {key: volume[key] for key in ("title", "version", "is_deleted")} if volume else None,
                    "raw": {name: deepcopy(state[name]) for name in sorted(state_fields) if name in state},
                    "notes": {"start_state": state["start_state"]} if "start_state" in state else {}})
                guards[("faction_volume_states", str(state["_id"]))] = state
                if volume is not None:
                    guards[("volumes", str(volume["_id"]))] = volume
    basis = {"schema_version": 1, "operation": operation, "kind": kind, "target": target, "position": position, "source": source,
        "fields": selected, "before": before, "previous": previous, "blockers": blockers, "field_sources": field_sources,
        "replaces": data.get("replaces", {}), "resolves": data.get("resolves", {}), "void_targets": data.get("targets", {}), "targets": targets,
        "references": references, "reference_reads": reference_reads, "legacy_sources": legacy,
        "reads": result["reads"], "protected_sources": protected}
    basis["fingerprint"] = canonical_request_hash(basis)
    basis = FactionFactBasisV1.model_validate(basis).model_dump(mode="json", exclude_unset=True)
    return {"basis": basis, "values": basis["before"]}, guards


async def preview_faction_facts(novel_id: str, data: dict, *, session=None) -> dict:
    """在一致读取事务里准备人工确认，不写文档或占用业务编号。

    Args:
        novel_id: 当前小说。
        data: 严格预览输入。
        session: 可选调用方事务。
    Returns:
        可冻结保存的 JSON 依据及原值。
    """
    fields = FactionFactPreviewInputV1.model_validate(data).model_dump(exclude_unset=True)
    novel_id = str(ObjectId(novel_id))
    new_id = str(ObjectId()) if fields["operation"] == "create" else None

    async def preview(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("势力预览必须使用调用方事务")
        result, _ = await _build_preview(novel_id, fields, new_entity_id=new_id, session=current_session)
        return result

    return await preview(session) if session is not None else await run_mongo_write_unit(preview, "preview_faction_facts", require_transaction=True)


async def confirm_faction_facts(novel_id: str, data: dict, *, idempotency_key: str, session=None) -> dict:
    """同事务保存势力事实、主档版本、书初镜像和首次完整成功回执。

    Args:
        novel_id: 当前小说；同键成功优先于今日可用性检查。
        data: 作者冻结的严格确认命令。
        idempotency_key: 原请求键，未知结果不能换键。
        session: 可选外层必需事务，不建立嵌套事务或降级保存。
    Returns:
        首次完整 JSON 成功结果；重放不改为当前值。
    """
    from backend.services.novel.chapter_record_service import _replay

    command = FactionFactConfirmV1.model_validate(data).model_dump(mode="json", exclude_unset=True)
    novel_id, basis = str(ObjectId(novel_id)), command["basis"]
    request = {"operation": command["operation"], "novel_id": novel_id, "target_id": basis["target"]["entity_id"], "data": command}
    fingerprint = build_idempotency_fingerprint(idempotency_key, request)

    async def save(current_session):
        if current_session is None or not current_session.in_transaction:
            raise RuntimeError("势力确认必须使用调用方事务")
        replay = await _replay(novel_id, fingerprint, expected_operation=command["operation"], session=current_session, expected_receipt_schema="faction.fact.receipt")
        if replay is not None:
            return replay
        target = basis["target"]
        if target["novel_id"] != novel_id:
            raise DomainApiError("FACTION_FACT_TARGET_INVALID", "势力预览不属于当前小说", status_code=409)
        preview_input = {"operation": command["operation"], "references": basis["references"]}
        if command["operation"] == "create":
            preview_input.update(target={"candidate": target["candidate"]}, position=basis["position"], source=basis["source"], fields=basis["fields"])
        else:
            preview_input["target"] = {"entity_id": target["entity_id"], "faction_id": target["faction_id"], "expected_version": target["version"]}
            if command["operation"] == "void":
                preview_input["targets"] = command["targets"]
            else:
                preview_input.update({name: basis[name] for name in ("kind", "position", "source", "fields", "replaces", "resolves")})
        current, guards = await _build_preview(novel_id, preview_input, new_entity_id=target["entity_id"] if target["kind"] == "new" else None, session=current_session)
        if current["basis"] != basis:
            raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "原预览的势力、旧资料或来源已变化，请保留原稿并重新预览", status_code=409)
        # 同一事务已重建全部原读取；保护小说空范围和具体来源后才做主档 CAS。
        await protect_chapter_record_sources(guards, session=current_session)
        now = get_utc_now().replace(tzinfo=None)
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)
        mirror = ({name: value for name, value in command.get("after", {}).items() if name in FACTION_FACT_PROFILE_FIELDS}
                  if basis["kind"] == "start" and basis["position"]["intent"] == "book_start" else {})
        if target["kind"] == "new":
            [faction_id] = await id_sequence_repo.allocate_many(novel_id, "faction", "fac", 1, session=current_session)
            candidate = target["candidate"]
            sort_order = candidate.get("sort_order")
            if sort_order is None:
                count = await faction_repo.collection.count_documents({"novel_id": ObjectId(novel_id),
                    "level_type": candidate.get("level_type", "core"), "parent_faction_id": candidate.get("parent_faction_id"),
                    "volume_id": ObjectId(candidate["volume_id"]) if candidate.get("volume_id") is not None else None,
                    "is_deleted": False}, session=current_session)
                sort_order = (count + 1) * 10
            await faction_repo.create_faction({**candidate, **mirror, "_id": ObjectId(target["entity_id"]),
                "novel_id": novel_id, "faction_id": faction_id, "sort_order": sort_order}, session=current_session)
            before_version, after_version, name = None, 1, candidate["name"]
        else:
            faction_id, name = target["faction_id"], target["name"]
            before_version, after_version = target["version"], target["version"] + 1
            updated = await faction_repo.collection.update_one({"_id": ObjectId(target["entity_id"]), "novel_id": ObjectId(novel_id),
                "faction_id": faction_id, "version": before_version, "is_deleted": False},
                {"$inc": {"version": 1}, "$set": {**mirror, "updated_at": now}}, session=current_session)
            if updated.matched_count != 1:
                raise VersionConflictError("势力在确认期间已变化，请保留原稿并重新预览")
        record = None
        if command["operation"] != "void":
            record = FactionFactRecordV1.model_validate({
                "schema_id": "faction.fact", "schema_version": 1, "history_id": str(ObjectId()), "novel_id": novel_id,
                "entity_type": "faction", "entity_id": target["entity_id"], "faction_id": faction_id, "faction_name": name,
                "operation": command["operation"], "before_version": before_version, "after_version": after_version,
                **{key: basis[key] for key in ("kind", "position", "source", "before", "previous", "replaces", "resolves", "protected_sources")},
                "after": command["after"], "validity": {field: {"state": "active"} for field in basis["fields"]}, "confirmed_at": now,
            }).model_dump(mode="json", exclude_unset=True)
            await BaseRepository("entity_state_history").collection.insert_one(faction_fact_record_document(record), session=current_session)
        changes = []
        disposed = command["targets"] if record is None else basis["replaces"]
        for field, identity in sorted(disposed.items()):
            state = {"state": "voided", "by_receipt_key_hash": fingerprint.key_hash} if record is None else {"state": "replaced", "by_history_id": record["history_id"]}
            changed = await BaseRepository("entity_state_history").collection.update_one({"_id": ObjectId(identity),
                "novel_id": ObjectId(novel_id), "entity_id": ObjectId(target["entity_id"]), "schema_id": "faction.fact", "schema_version": 1,
                f"validity.{field}": {"state": "active"}}, {"$set": {f"validity.{field}": state}}, session=current_session)
            if changed.matched_count != 1:
                raise VersionConflictError("待处置势力字段已被替代或作废，请重新预览")
            changes.append({"history_id": identity, "field": field, "before": {"state": "active"}, "after": state})
        result = FactionFactResultV1.model_validate({"schema_version": 1, "operation": command["operation"], "novel_id": novel_id,
            "entity_id": target["entity_id"], "faction_id": faction_id, "faction_name": name, "before_version": before_version,
            "after_version": after_version, "record": record, "validity_changes": changes, "confirmed_at": now}).model_dump(mode="json", exclude_unset=True)
        receipt_id = ObjectId()
        receipt = FactionFactReceiptV1.model_validate({"schema_id": "faction.fact.receipt", "schema_version": 1,
            "receipt_id": str(receipt_id), "novel_id": novel_id, "operation": command["operation"],
            "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash, "request": request, "result": result,
            **{key: basis[key] for key in ("position", "source", "protected_sources")}, "created_at": now}).model_dump(exclude_unset=True)
        receipt.update(_id=receipt_id, novel_id=ObjectId(novel_id), request=request, result=result)
        del receipt["receipt_id"]
        await BaseRepository("chapter_record_confirmation_receipts").collection.insert_one(receipt, session=current_session)
        return result

    return await save(session) if session is not None else await run_mongo_write_unit(save, "confirm_faction_facts", require_transaction=True)
