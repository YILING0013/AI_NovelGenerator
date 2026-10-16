"""核对章后记录的不可变正文来源；不建立修订、不保存确认记录。"""

import hashlib
from collections.abc import Mapping

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import VersionConflictError
from backend.services.novel.chapter_record_contract import ChapterRecordEvidenceV1
from backend.services.novel.writing_context import COLLECTIONS, load_writing_parents, writing_order


RECORD_COLLECTIONS = ("events", "chapter_reports", "entity_state_history", "chapter_record_confirmation_receipts")
RELATED_ENTITIES = {
    "character": ("characters", "character_id"),
    "faction": ("factions", "faction_id"),
    "character_relation": ("character_relations", "relation_id"),
    "faction_relation": ("faction_relations", "relation_id"),
    "character_faction_binding": ("character_faction_bindings", "binding_id"),
    "item": ("items", "item_id"),
    "location": ("locations", "location_id"),
    "world_rule": ("world_rules", "rule_id"),
    "character_volume_state": ("character_volume_states", "_id"),
    "faction_volume_state": ("faction_volume_states", "_id"),
}


async def load_chapter_record_source_in_session(
    novel_id: str,
    evidence: ChapterRecordEvidenceV1 | Mapping,
    *,
    session: AsyncClientSession,
) -> dict:
    """在调用方事务内核对来源，供事件、报告和真实实体变化记录共同使用。

    Args:
        novel_id: 当前小说 ID。
        evidence: 已选章修订的身份、hash、码点位置与原样引文。
        session: 调用方已经开启的事务；本函数不会开启或提交事务。
    Returns:
        规范小写身份的 evidence、当前正文 needs_review 和完整父链 guards。
        本函数只读；确认写入者仍须在同一事务保护 guards 后才保存记录。
        旧修订可以核验成功，needs_review 只说明当前正文已变化。
    """
    if session is None or not session.in_transaction:
        raise RuntimeError("章节记录来源核验必须在调用方事务内执行")
    source = ChapterRecordEvidenceV1.model_validate(evidence)
    chain = await load_writing_parents(novel_id, "chapter", source.chapter_id, session=session)
    novel, chapter = chain[0][1], chain[-1][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("CHAPTER_RECORD_PARENT_BUSY", "小说正在永久删除，不能使用章节来源", status_code=409)
    revision = await BaseRepository("chapter_revisions").collection.find_one({
        "_id": ObjectId(source.revision_id), "chapter_id": chapter["_id"],
        "version": source.version,
        **{name: chapter[name] for name in ("novel_id", "volume_id", "arc_id", "scene_id")},
    }, session=session)
    if revision is None:
        raise DomainApiError("CHAPTER_RECORD_REVISION_NOT_FOUND", "所选修订不存在或不属于当前章节，请重新选择历史版本", status_code=404)
    content = revision["content"]
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if content_hash != revision["content_hash"]:
        raise DomainApiError("CHAPTER_RECORD_REVISION_INVALID", "所选修订的正文校验失败", status_code=409)
    if source.content_hash != content_hash:
        raise DomainApiError("CHAPTER_RECORD_SOURCE_CHANGED", "正文 hash 与所选修订不一致，请重新读取历史版本", status_code=409)
    if content[source.start:source.start + len(source.quote)] != source.quote:
        raise DomainApiError("CHAPTER_RECORD_QUOTE_MISMATCH", "原文片段与所选修订的位置不一致，请重新选择片段", field_errors={"evidence.quote": "片段不匹配"})
    bound = source.model_dump()
    bound.update(chapter_id=str(chapter["_id"]), revision_id=str(revision["_id"]), content_hash=content_hash)
    return {
        "evidence": bound,
        "needs_review": hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest() != content_hash,
        "guards": {(COLLECTIONS[kind], str(row["_id"])): row for kind, row in chain},
    }


async def protect_chapter_record_sources(guards: dict, *, session: AsyncClientSession) -> None:
    """同事务保护完整来源及相关实体，不递增业务版本。

    Args:
        guards: 在本事务读到的来源及实体 BSON 文档。
        session: 必需事务；必须先于原实体更新调用。
    Returns:
        无；任一来源变化则回滚整个确认。
    """
    for (name, _), document in guards.items():
        query = {"_id": document["_id"], "version": document["version"], "is_deleted": document["is_deleted"]}
        query.update({field: document[field] for field in ("novel_id", "volume_id", "arc_id", "scene_id") if field in document})
        if name == "novels":
            query.update(hard_delete_claim={"$exists": False}, location_write_lock_token=None, item_write_lock_token=None, state_write_lock_token=None)
        result = await BaseRepository(name).collection.update_one(query, {"$inc": {"writing_guard_revision": 1}}, session=session)
        if result.matched_count != 1:
            raise VersionConflictError("章节来源、相关实体或小说已变化，请保留原稿后重试")


async def count_chapter_record_references(novel_id: ObjectId, kind: str, identity: ObjectId, *, session: AsyncClientSession | None = None) -> int:
    """统计实际来源引用，包括人工起点、旧报告、作废和无变化成功回执。

    Args:
        novel_id: 来源小说。
        kind: chapter、scene、arc 或 volume。
        identity: 来源物理 ID。
        session: 可选事务。
    Returns:
        仍保留该来源的记录和回执数量。
    """
    field = "chapter_id" if kind == "chapter" else f"source_parents.{kind}_id"
    total = 0
    for name in RECORD_COLLECTIONS:
        reference = {field: identity}
        if name in {"entity_state_history", "chapter_record_confirmation_receipts"}:
            reference = {"$or": [reference, {"protected_sources": {"$elemMatch": {
                "resource_type": kind, "id": str(identity),
            }}}]}
        total += await BaseRepository(name).collection.count_documents({"novel_id": novel_id, **reference}, session=session)
    if kind == "chapter":
        total += await BaseRepository("chapters").collection.count_documents({"_id": identity, "novel_id": novel_id, "chapter_report_head": {"$exists": True}}, session=session)
    return total


async def count_novel_chapter_records(novel_id: ObjectId, *, session: AsyncClientSession | None = None) -> dict:
    """整书删除核对所有确认记录及报告头，不能只数有效记录。

    Args:
        novel_id: 小说 BSON ID。
        session: 删除时使用同一事务。
    Returns:
        固定五项精确数量。
    """
    counts = {}
    for name in RECORD_COLLECTIONS:
        counts[name] = await BaseRepository(name).collection.count_documents({"novel_id": novel_id}, session=session)
    counts["report_heads"] = await BaseRepository("chapters").collection.count_documents({"novel_id": novel_id, "chapter_report_head": {"$exists": True}}, session=session)
    return counts


async def load_fact_source_observations(novel_key: ObjectId, records: list[dict], directories: dict, *, session) -> tuple[list[dict], dict, dict]:
    """核验人物和势力记录共用的当前正文及原修订，不改变记录或建立修订。

    Args:
        novel_key: 本书物理身份。
        records: 已通过各自严格合同的记录。
        directories: 本次完整活动目录。
        session: 调用方读取或确认会话。
    Returns:
        原来源观察、逐记录有效性和实际章节保护对象。
    """
    sources, source_validity, guards = {}, {}, {}
    for record in records:
        source = record["source"]
        if source["kind"] == "author":
            source_validity[record["history_id"]] = True
            continue
        evidence = source["evidence"]
        source_key = (evidence["chapter_id"], evidence["revision_id"])
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
    return [sources[key][0] for key in sorted(sources)], source_validity, guards
