"""场景下章计划、正文、目录和祖先统计。"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import touch_dependency_endpoint_guards
from backend.db.errors import DuplicateKeyError, IdempotencyConflictError, NotFoundError, VersionConflictError
from backend.db.repositories.chapter_repository import chapter_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.scene_repository import scene_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, resolve_idempotent_replay, update_versioned_document, validate_expected_version
from backend.services.novel.arc_service import validate_sibling_order, write_sibling_order
from backend.services.novel.chapter_contract import ChapterCreateV2, ChapterReadV2, ChapterReorderV2, ChapterUpdateV2, serialize_chapter
from backend.services.novel.chapter_revision_contract import ChapterRevisionRestoreV1, serialize_chapter_revision
from backend.services.novel.chapter_record_source import count_chapter_record_references
from backend.services.novel.scene_service import load_scene_parent_chain, update_scene_ancestors
from backend.services.novel.writing_context import require_volume_ready
from backend.services.novel.foreshadowing_service import count_foreshadowing_references


async def append_chapter_revision(chapter: dict, *, source: str, parent_version: int | None, session: AsyncClientSession, restored_from_version: int | None = None) -> None:
    """将实际保存的章节内容追加到历史，与正文共用调用方事务。

    Args:
        chapter: 已保存章节的完整快照。
        source: 基线、新建、编辑或写作来源。
        parent_version: 前一份修订的章节版本；第一份为 None。
        session: 当前必需事务。
        restored_from_version: 明确恢复时的来源旧稿版本。
    Returns:
        无；插入失败让整个保存回滚。
    """
    await BaseRepository("chapter_revisions").collection.insert_one({
        "_id": ObjectId(), "chapter_id": chapter["_id"],
        **{name: chapter[name] for name in ("novel_id", "volume_id", "arc_id", "scene_id", "version", "title", "summary", "planning", "content")},
        "content_hash": hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest(),
        "parent_version": parent_version, "source": source, "saved_at": chapter["updated_at"],
        **({"restored_from_version": restored_from_version} if restored_from_version is not None else {}),
    }, session=session)


async def load_chapter_parent_chain(scene_id: str, *, session: AsyncClientSession | None = None) -> tuple[dict, dict, dict, dict]:
    """读取章节的活动父链，并核对完整归属。

    Args:
        scene_id: 父场景 ID。
        session: 可选事务。
    Returns:
        从小说到场景的四个快照。
    """
    scene = await scene_repo.get_scene(scene_id, session=session)
    novel, volume, arc = await load_scene_parent_chain(str(scene["arc_id"]), session=session)
    if scene["novel_id"] != novel["_id"] or scene["volume_id"] != volume["_id"]:
        raise NotFoundError("场景不属于当前父篇章")
    return novel, volume, arc, scene


async def update_chapter_ancestors(novel: dict, volume: dict, arc: dict, scene: dict, *, chapter_delta: int = 0, word_delta: int = 0, session: AsyncClientSession) -> None:
    """按完整父链顺序保存活动章节数及正文实际字数。

    Args:
        novel: 小说快照。
        volume: 卷快照。
        arc: 篇章快照。
        scene: 场景快照。
        chapter_delta: 活动章节数变化。
        word_delta: 活动正文字数变化。
        session: 调用方必需事务。
    Returns:
        无，失败由事务整体回滚。
    """
    fields = {"chapter_count": scene["chapter_count"] + chapter_delta, "word_count": scene["word_count"] + word_delta}
    if min(fields.values()) < 0:
        raise DomainApiError("CHAPTER_STATS_CONFLICT", "章节数量或字数不一致，请刷新后重试", status_code=409)
    await update_scene_ancestors(novel, volume, arc, chapter_delta=chapter_delta, word_delta=word_delta, session=session)
    changed = await update_versioned_document(scene_repo.collection, {"_id": scene["_id"], "arc_id": arc["_id"]}, scene["version"], fields, is_deleted=False, session=session)
    if changed is None:
        raise VersionConflictError("所属场景在保存期间已变化，请重试")


async def _validate_povs(plannings: list[Mapping[str, Any]], novel_id: ObjectId, *, session: AsyncClientSession) -> None:
    """一次检查本批视角人物，相同人物只读取和保护一次。

    Args:
        plannings: 本次保存的完整章计划。
        novel_id: 所属小说。
        session: 当前必需事务。
    Returns:
        无。
    """
    identities = list(dict.fromkeys(plan["pov_character_id"] for plan in plannings if plan["pov_character_id"] is not None))
    if not identities:
        return
    collection = BaseRepository("characters").collection
    query = {"novel_id": novel_id, "is_deleted": False, "status": "active"}
    characters = await collection.find({**query, "character_id": {"$in": identities}}, session=session).to_list(length=None)
    by_identity = {character["character_id"]: character for character in characters}
    if any(identity not in by_identity for identity in identities):
        raise DomainApiError("CHAPTER_REFERENCE_NOT_FOUND", "视角人物不存在、已回收、已停用或不属于当前小说", status_code=404, field_errors={"planning.pov_character_id": "人物不可用"})
    try:
        await touch_dependency_endpoint_guards(collection, [
            {**query, "character_id": identity, "_id": by_identity[identity]["_id"], "version": by_identity[identity]["version"]}
            for identity in identities
        ], session=session)
    except DuplicateKeyError as exc:
        raise DomainApiError("CHAPTER_REFERENCE_CONFLICT", "视角人物在保存期间已变化，请重试", status_code=409) from exc


async def _check_first_appearances(chapter: dict, *, session: AsyncClientSession) -> None:
    """保留人物和势力首次出场章节的有效归属。

    Args:
        chapter: 准备删除的章节。
        session: 当前必需事务。
    Returns:
        无，存在引用时阻止删除。
    """
    query = {"novel_id": chapter["novel_id"], "first_appearance_chapter_id": {"$in": [chapter["_id"], str(chapter["_id"])]}}
    for name in ("characters", "factions"):
        if await BaseRepository(name).collection.find_one(query, {"_id": 1}, session=session):
            raise DomainApiError("CHAPTER_DELETE_BLOCKED", "章节仍被人物或势力标为首次出场，请先修改引用", status_code=409)


class ChapterService:
    """章计划与正文共用版本，目录章号由当前父链顺序生成。"""

    @staticmethod
    async def create_chapter(scene_id: str, data: ChapterCreateV2 | Mapping[str, Any], *, idempotency_key: str) -> dict:
        """在场景末尾创建章节。

        Args:
            scene_id: 父场景 ID。
            data: 标题、章计划及可选正文。
            idempotency_key: 稳定创建键。
        Returns:
            新章节或原请求结果。
        """
        async def create(session: AsyncClientSession) -> dict:
            return await ChapterService.create_chapter_in_session(scene_id, data, idempotency_key=idempotency_key, session=session)
        return await run_mongo_write_unit(create, "create_chapter", require_transaction=True)

    @staticmethod
    async def create_chapter_in_session(scene_id: str, data: ChapterCreateV2 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession) -> dict:
        """在审核批次的事务中创建章节，不另开事务。

        Args:
            scene_id: 父场景 ID。
            data: 标题、章计划和正文。
            idempotency_key: 当前场景内的稳定创建键。
            session: 调用方必需事务。
        Returns:
            完整数据库章节。
        """
        return (await ChapterService.create_chapters_in_session(scene_id, [(data, idempotency_key)], session=session))[0]

    @staticmethod
    async def create_chapters_in_session(scene_id: str, chapters: list[tuple[ChapterCreateV2 | Mapping[str, Any], str]], *, session: AsyncClientSession) -> list[dict]:
        """在同一事务追加一批章节，共用父链、顺序和祖先统计。

        Args:
            scene_id: 父场景 ID。
            chapters: 按顺序排列的章节内容及各自稳定创建键。
            session: 调用方必需事务。
        Returns:
            按输入顺序返回新章节或对应创建键的原结果。
        """
        if not chapters:
            return []
        scene_id = str(to_object_id(scene_id))
        prepared = []
        for data, idempotency_key in chapters:
            fields = (data if isinstance(data, ChapterCreateV2) else ChapterCreateV2.model_validate(data)).model_dump()
            prepared.append((fields, build_idempotency_fingerprint(idempotency_key, {"scene_id": scene_id, **fields})))
        novel, volume, arc, scene = await load_chapter_parent_chain(scene_id, session=session)
        existing = await chapter_repo.collection.find({
            "scene_id": scene["_id"], "creation_idempotency_key_hash": {"$in": [fingerprint.key_hash for _, fingerprint in prepared]},
        }, session=session).to_list(length=None)
        by_key = {document["creation_idempotency_key_hash"]: document for document in existing}
        documents = []
        pending = []
        for fields, fingerprint in prepared:
            replay = resolve_idempotent_replay(by_key.get(fingerprint.key_hash), fingerprint.request_hash, label="章节创建")
            documents.append(replay)
            if replay is None:
                pending.append((len(documents) - 1, fields, fingerprint))
        if not pending:
            return documents
        require_volume_ready(volume)
        word_counts = [sum(not char.isspace() for char in fields["content"]) for _, fields, _ in pending]
        # 本批只改变一次每级统计和版本；任一章节或引用失败仍由原事务整体回滚。
        await update_chapter_ancestors(novel, volume, arc, scene, chapter_delta=len(pending), word_delta=sum(word_counts), session=session)
        await _validate_povs([fields["planning"] for _, fields, _ in pending], novel["_id"], session=session)
        last = await chapter_repo.collection.find_one({"scene_id": scene["_id"], "is_deleted": False}, {"order_index": 1}, sort=[("order_index", -1)], session=session)
        first_order = 1 if last is None else last["order_index"] + 1
        now = get_utc_now().replace(tzinfo=None)
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        new_documents = []
        for offset, ((index, fields, fingerprint), word_count) in enumerate(zip(pending, word_counts)):
            chapter = {"_id": ObjectId(), "novel_id": novel["_id"], "volume_id": volume["_id"], "arc_id": arc["_id"], "scene_id": scene["_id"], **fields, "order_index": first_order + offset, "word_count": word_count, "version": 1, "is_deleted": False, "deleted_at": None, "created_at": now, "updated_at": now, **fingerprint.as_creation_fields()}
            documents[index] = chapter
            new_documents.append(chapter)
        await chapter_repo.collection.insert_many(new_documents, ordered=True, session=session)
        for chapter in new_documents:
            await append_chapter_revision(chapter, source="create", parent_version=None, session=session)
        return documents

    @staticmethod
    async def get_chapter(chapter_id: str, *, include_deleted: bool = False, novel_id: str | None = None, session: AsyncClientSession | None = None) -> dict:
        """读取完整章节，并隐藏不再活动的父级内容。

        Args:
            chapter_id: 章节 ID。
            include_deleted: 是否允许章节回收站。
            novel_id: 可选小说范围。
            session: 可选事务。
        Returns:
            章计划与正文。
        """
        chapter = await chapter_repo.get_chapter(chapter_id, include_deleted=include_deleted, session=session)
        novel, volume, arc, _ = await load_chapter_parent_chain(str(chapter["scene_id"]), session=session)
        if any(chapter[name] != parent["_id"] for name, parent in (("novel_id", novel), ("volume_id", volume), ("arc_id", arc))) or (novel_id is not None and to_object_id(novel_id) != novel["_id"]):
            raise NotFoundError("章节不属于当前小说或父场景")
        return chapter

    @staticmethod
    async def list_chapters(novel_id: str, *, volume_id: str | None = None, scene_id: str | None = None, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict]:
        """读取无正文目录，先排全书章号，再应用卷或场景筛选。

        Args:
            novel_id: 小说 ID。
            volume_id: 可选卷筛选。
            scene_id: 可选场景筛选。
            deleted: 是否查看章节回收站。
            session: 可选事务。
        Returns:
            按卷、篇章、场景、章节顺序排列的目录。
        """
        novel = await novel_repo.get_novel_by_id(novel_id, session=session)
        parent_maps = {}
        for name in ("volumes", "arcs", "scenes"):
            docs = await BaseRepository(name).collection.find({"novel_id": novel["_id"], "is_deleted": False}, {"_id": 1, "volume_id": 1, "arc_id": 1, "order_index": 1}, session=session).to_list(length=None)
            parent_maps[name] = {doc["_id"]: doc for doc in docs}
        volumes, arcs, scenes = (parent_maps[name] for name in ("volumes", "arcs", "scenes"))
        volume_oid = to_object_id(volume_id) if volume_id is not None else None
        scene_oid = to_object_id(scene_id) if scene_id is not None else None
        if volume_oid is not None and volume_oid not in volumes:
            raise NotFoundError("卷不属于当前活动小说")
        if scene_oid is not None:
            chain = await load_chapter_parent_chain(str(scene_oid), session=session)
            if chain[0]["_id"] != novel["_id"] or (volume_oid is not None and chain[1]["_id"] != volume_oid):
                raise NotFoundError("场景不属于当前范围")
        rows = await chapter_repo.collection.find({"novel_id": novel["_id"], "is_deleted": deleted}, {"content": 0, "creation_idempotency_key_hash": 0, "creation_request_hash": 0}, session=session).to_list(length=None)
        rows = [row for row in rows if row["volume_id"] in volumes and row["arc_id"] in arcs and row["scene_id"] in scenes and arcs[row["arc_id"]]["volume_id"] == row["volume_id"] and scenes[row["scene_id"]]["arc_id"] == row["arc_id"] and scenes[row["scene_id"]]["volume_id"] == row["volume_id"]]
        rows.sort(key=lambda row: (volumes[row["volume_id"]]["order_index"], arcs[row["arc_id"]]["order_index"], scenes[row["scene_id"]]["order_index"], row["order_index"], str(row["_id"])))
        for number, row in enumerate(rows, 1):
            row["chapter_number"] = None if deleted else number
        current = await novel_repo.get_novel_by_id(novel_id, session=session)
        if current["version"] != novel["version"]:
            raise DomainApiError("CHAPTER_DIRECTORY_CHANGED", "章节目录正在更新，请刷新后重试", status_code=409)
        return [row for row in rows if (volume_oid is None or row["volume_id"] == volume_oid) and (scene_oid is None or row["scene_id"] == scene_oid)]

    @staticmethod
    async def update_chapter(chapter_id: str, data: ChapterUpdateV2 | Mapping[str, Any]) -> dict:
        """按同一个版本局部保存章计划或正文。

        Args:
            chapter_id: 章节 ID。
            data: 已读版本与明确修改字段。
        Returns:
            保存后的章节。
        """
        async def update(session: AsyncClientSession) -> dict:
            return await ChapterService.update_chapter_in_session(chapter_id, data, session=session)
        return await run_mongo_write_unit(update, "update_chapter", require_transaction=True)

    @staticmethod
    async def update_chapter_in_session(chapter_id: str, data: ChapterUpdateV2 | Mapping[str, Any], *, session: AsyncClientSession, source: str = "edit") -> dict:
        """在确认事务中保存章计划或正文，原样提交不改版本或统计。

        Args:
            chapter_id: 章节 ID。
            data: 版本与局部内容。
            session: 调用方必需事务。
            source: 服务端保存来源，不接受客户端提供。
        Returns:
            完整章节文档。
        """
        return await ChapterService._save_chapter_in_session(chapter_id, data, session=session, source=source)

    @staticmethod
    async def _save_chapter_in_session(chapter_id: str, data: ChapterUpdateV2 | Mapping[str, Any], *, session: AsyncClientSession, source: str, restored_from_version: int | None = None) -> dict:
        """普通保存和恢复共用校验及写入，只有恢复来源明确时强制新版本。

        Args:
            chapter_id: 当前章。
            data: 四内容字段的更新与原版本。
            session: 同一事务。
            source: 保存来源。
            restored_from_version: 恢复专用来源版本，普通保存不传。
        Returns:
            完整已保存章节。
        """
        request = data if isinstance(data, ChapterUpdateV2) else ChapterUpdateV2.model_validate(data)
        fields = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if "planning" in fields:
            fields["planning"] = request.planning.model_dump()
        chapter = await ChapterService.get_chapter(chapter_id, session=session)
        if chapter["version"] != request.expected_version:
            raise VersionConflictError("章节已被修改，请保留草稿并刷新后比较")
        if restored_from_version is None and all(chapter[key] == value for key, value in fields.items()):
            return chapter
        previous = await BaseRepository("chapter_revisions").collection.find_one({"chapter_id": chapter["_id"]}, sort=[("version", -1)], session=session)
        # 旧章节第一次修改前先留原稿；排序或回收产生的版本空号不补造历史。
        if previous is None:
            await append_chapter_revision(chapter, source="baseline", parent_version=None, session=session)
        parent_version = chapter["version"] if previous is None else previous["version"]
        word_delta = 0
        if "content" in fields:
            fields["word_count"] = sum(not char.isspace() for char in fields["content"])
            word_delta = fields["word_count"] - chapter["word_count"]
        parents = await load_chapter_parent_chain(str(chapter["scene_id"]), session=session)
        await update_chapter_ancestors(*parents, word_delta=word_delta, session=session)
        if "planning" in fields:
            await _validate_povs([fields["planning"]], chapter["novel_id"], session=session)
        changed = await update_versioned_document(chapter_repo.collection, {"_id": chapter["_id"], "scene_id": chapter["scene_id"]}, request.expected_version, fields, is_deleted=False, session=session)
        if changed is None:
            raise VersionConflictError("章节保存期间已变化，请重试")
        await append_chapter_revision(changed, source=source, parent_version=parent_version, session=session, restored_from_version=restored_from_version)
        return changed

    @staticmethod
    async def list_revisions(chapter_id: str, *, include_deleted: bool = False, limit: int = 50, before_version: int | None = None) -> dict:
        """只读分页历史；未修改的旧章返回空列表。

        Args:
            chapter_id: 章节 ID。
            include_deleted: 是否允许活动父链下的回收站章节。
            limit: 每页修订数量，由 HTTP 入口限制为 1 至 100。
            before_version: 只读取比该版本更早的历史。
        Returns:
            不含正文与计划的倒序列表，以及下一页的版本游标。
        """
        async def read(session: AsyncClientSession) -> dict:
            chapter = await ChapterService.get_chapter(chapter_id, include_deleted=include_deleted, session=session)
            collection = BaseRepository("chapter_revisions").collection
            query = {"chapter_id": chapter["_id"]}
            if before_version is not None:
                query["version"] = {"$lt": before_version}
            rows = await collection.find(query, {"content": 0, "summary": 0, "planning": 0}, session=session).sort("version", -1).limit(limit + 1).to_list(length=limit + 1)
            return {"data": rows[:limit], "next_before_version": rows[limit - 1]["version"] if len(rows) > limit else None}
        return await run_mongo_write_unit(read, "list_chapter_revisions", require_transaction=True)

    @staticmethod
    async def get_revision(chapter_id: str, version: int, *, include_deleted: bool = False) -> dict:
        """按章节和修订版本读取旧稿，并检查当前章节父链可用。

        Args:
            chapter_id: 章节 ID。
            version: 修订保存时的章节业务版本。
            include_deleted: 是否允许回收站章节。
        Returns:
            完整修订；不存在的版本返回找不到。
        """
        async def read(session: AsyncClientSession) -> dict:
            chapter = await ChapterService.get_chapter(chapter_id, include_deleted=include_deleted, session=session)
            revision = await BaseRepository("chapter_revisions").collection.find_one({"chapter_id": chapter["_id"], "version": validate_expected_version(version)}, session=session)
            if revision is None:
                raise NotFoundError("章节修订不存在")
            return revision
        return await run_mongo_write_unit(read, "get_chapter_revision", require_transaction=True)

    @staticmethod
    async def compare_revision(chapter_id: str, version: int, *, include_deleted: bool = False) -> dict:
        """同一事务内比较旧稿与当前章，避免两次读取混用版本。

        Args:
            chapter_id: 当前章节。
            version: 要比较的历史版本。
            include_deleted: 是否允许回收站章节。
        Returns:
            完整旧稿、当前章及变化字段。
        """
        async def read(session: AsyncClientSession) -> dict:
            chapter = await ChapterService.get_chapter(chapter_id, include_deleted=include_deleted, session=session)
            revision = await BaseRepository("chapter_revisions").collection.find_one({"chapter_id": chapter["_id"], "version": validate_expected_version(version)}, session=session)
            if revision is None:
                raise NotFoundError("章节修订不存在")
            normalized = ChapterUpdateV2.model_validate({"expected_version": chapter["version"], **{name: revision[name] for name in ("title", "summary", "planning", "content")}}).model_dump()
            return {"revision": serialize_chapter_revision(revision), "current": serialize_chapter(chapter),
                    "changed_fields": [name for name in ("title", "summary", "planning", "content") if revision[name] != chapter[name]],
                    "restore_normalizes_text": any(revision[name] != normalized[name] for name in ("title", "summary", "planning", "content"))}
        return await run_mongo_write_unit(read, "compare_chapter_revision", require_transaction=True)

    @staticmethod
    async def restore_revision(chapter_id: str, version: int, data: ChapterRevisionRestoreV1 | Mapping[str, Any], *, idempotency_key: str) -> dict:
        """将整份旧稿作为新保存，原请求重试返回原成功回执。

        Args:
            chapter_id: 活动章节。
            version: 要恢复的旧稿版本。
            data: 恢复前明确读取的章节版本。
            idempotency_key: 本次确认键，断响应重试时保持不变。
        Returns:
            本次保存的公开章节快照，不回退业务版本。
        """
        request = data if isinstance(data, ChapterRevisionRestoreV1) else ChapterRevisionRestoreV1.model_validate(data)
        revision_version = validate_expected_version(version)
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"chapter_id": chapter_id.lower(), "revision_version": revision_version, **request.model_dump()})
        receipts = BaseRepository("writing_confirmation_receipts").collection
        async def save(session: AsyncClientSession) -> dict:
            # 重放仍检查当前父链；回收或已删除来源不能靠旧键重新出现。
            chapter = await ChapterService.get_chapter(chapter_id, session=session)
            query = {"novel_id": chapter["novel_id"], "operation": "restore_chapter_revision", "idempotency_key_hash": fingerprint.key_hash}
            receipt = await receipts.find_one(query, session=session)
            if receipt is not None:
                if receipt["request_hash"] != fingerprint.request_hash:
                    raise IdempotencyConflictError("同一恢复键不能用于不同章节、旧稿或版本")
                return receipt["result"]["data"][0]
            if chapter["version"] != request.expected_version:
                raise VersionConflictError("章节已被修改，请保留草稿并重新比较")
            revision = await BaseRepository("chapter_revisions").collection.find_one({"chapter_id": chapter["_id"], "version": revision_version}, session=session)
            if revision is None:
                raise NotFoundError("章节修订不存在")
            changed = await ChapterService._save_chapter_in_session(chapter_id, {"expected_version": request.expected_version, **{name: revision[name] for name in ("title", "summary", "planning", "content")}}, session=session, source="restore", restored_from_version=revision_version)
            result = ChapterReadV2.model_validate(serialize_chapter(changed)).model_dump()
            await receipts.insert_one({**query, "request_hash": fingerprint.request_hash, "result": {"operation": query["operation"], "ids": [chapter_id.lower()], "data": [result]}, "created_at": get_utc_now()}, session=session)
            return result
        return await run_mongo_write_unit(save, "restore_chapter_revision", require_transaction=True)

    @staticmethod
    async def set_deleted(chapter_id: str, *, expected_version: int, deleted: bool, session: AsyncClientSession | None=None) -> dict:
        """回收章节并扣实际统计，恢复时重新检查视角并追加到场景末尾。

        Args:
            chapter_id: 章节 ID。
            expected_version: 已读版本。
            deleted: True 回收，False 恢复。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            改变状态后的章节。
        """
        expected = validate_expected_version(expected_version)
        async def change(session: AsyncClientSession) -> dict:
            chapter = await ChapterService.get_chapter(chapter_id, include_deleted=True, session=session)
            if chapter["version"] != expected:
                raise VersionConflictError("章节版本已变化，请刷新后重试")
            if chapter["is_deleted"] == deleted:
                raise DomainApiError("CHAPTER_STATE_CONFLICT", "章节已经处于目标状态", status_code=409)
            if deleted:
                await _check_first_appearances(chapter, session=session)
            parents = await load_chapter_parent_chain(str(chapter["scene_id"]), session=session)
            direction = -1 if deleted else 1
            await update_chapter_ancestors(*parents, chapter_delta=direction, word_delta=direction * chapter["word_count"], session=session)
            if not deleted:
                await _validate_povs([chapter["planning"]], chapter["novel_id"], session=session)
            siblings = await chapter_repo.list_in_scene(str(chapter["scene_id"]), session=session)
            fields = {"is_deleted": deleted, "deleted_at": get_utc_now() if deleted else None}
            if not deleted:
                fields["order_index"] = max((row["order_index"] for row in siblings), default=0) + 1
            changed = await update_versioned_document(chapter_repo.collection, {"_id": chapter["_id"]}, expected, fields, is_deleted=not deleted, session=session)
            if changed is None:
                raise VersionConflictError("章节状态在保存期间已变化")
            if deleted:
                for sibling in siblings:
                    if sibling["order_index"] > chapter["order_index"]:
                        moved = await update_versioned_document(chapter_repo.collection, {"_id": sibling["_id"]}, sibling["version"], {"order_index": sibling["order_index"] - 1}, is_deleted=False, session=session)
                        if moved is None:
                            raise VersionConflictError("章节顺序已变化，请重试")
            return changed
        if session is not None:
            return await change(session)

        return await run_mongo_write_unit(change, "change_chapter_deleted", require_transaction=True)

    @staticmethod
    async def hard_delete_chapter(chapter_id: str, *, expected_version: int, expected_revision_count: int | None = None) -> None:
        """永久删除回收站章节，保留仍被首次出场引用的章节。

        Args:
            chapter_id: 章节 ID。
            expected_version: 已读版本。
            expected_revision_count: 作者明确确认要一并删除的历史数量。
        Returns:
            无。
        """
        expected = validate_expected_version(expected_version)
        async def delete(session: AsyncClientSession) -> None:
            chapter = await ChapterService.get_chapter(chapter_id, include_deleted=True, session=session)
            if chapter["version"] != expected:
                raise VersionConflictError("章节版本已变化，请刷新后重试")
            if not chapter["is_deleted"]:
                raise DomainApiError("CHAPTER_DELETE_BLOCKED", "请先将章节移入回收站", status_code=409)
            foreshadowings = await count_foreshadowing_references(chapter["novel_id"], "chapter", chapter["_id"], session=session)
            if foreshadowings:
                raise DomainApiError("CHAPTER_FORESHADOWING_DELETE_BLOCKED", "章节仍被伏笔证据引用，请先在伏笔回收站逐条处理", status_code=409, details={"foreshadowings": foreshadowings})
            records = await count_chapter_record_references(chapter["novel_id"], "chapter", chapter["_id"], session=session)
            if records:
                raise DomainApiError("CHAPTER_RECORD_DELETE_BLOCKED", "章节仍是章后确认记录的来源；作废不会清除原文，如需全部清理请删除整部作品", status_code=409, details={"chapter_records": records})
            revisions = BaseRepository("chapter_revisions").collection
            count = await revisions.count_documents({"chapter_id": chapter["_id"]}, session=session)
            if count and expected_revision_count is None:
                raise DomainApiError("CHAPTER_HISTORY_DELETE_BLOCKED", "章节有历史版本，请先查看删除影响并明确确认", status_code=409)
            if expected_revision_count is not None and expected_revision_count != count:
                raise VersionConflictError("章节历史数量已变化，请重新查看删除影响")
            await _check_first_appearances(chapter, session=session)
            parents = await load_chapter_parent_chain(str(chapter["scene_id"]), session=session)
            await update_chapter_ancestors(*parents, session=session)
            result = await chapter_repo.collection.delete_one({"_id": chapter["_id"], "is_deleted": True, "version": expected}, session=session)
            if result.deleted_count != 1:
                raise VersionConflictError("章节删除期间已变化")
            await revisions.delete_many({"chapter_id": chapter["_id"]}, session=session)
        await run_mongo_write_unit(delete, "hard_delete_chapter", require_transaction=True)

    @staticmethod
    async def reorder_chapters(scene_id: str, data: ChapterReorderV2 | Mapping[str, Any], *, session: AsyncClientSession | None=None) -> list[dict]:
        """完整重排同一场景下的活动章节。

        Args:
            scene_id: 父场景 ID。
            data: 全部章节的版本与目标序号。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新顺序下的章节，不含正文。
        """
        request = data if isinstance(data, ChapterReorderV2) else ChapterReorderV2.model_validate(data)
        async def reorder(session: AsyncClientSession) -> list[dict]:
            parents = await load_chapter_parent_chain(scene_id, session=session)
            current = await chapter_repo.list_in_scene(scene_id, session=session)
            ordered = validate_sibling_order(current, request.model_dump()["items"], id_field="chapter_id")
            if any(before["order_index"] != order for before, order in ordered):
                await update_chapter_ancestors(*parents, session=session)
                await write_sibling_order(chapter_repo.collection, ordered, session=session)
            return await ChapterService.list_chapters(str(parents[0]["_id"]), scene_id=scene_id, session=session)
        if session is not None:
            return await reorder(session)

        return await run_mongo_write_unit(reorder, "reorder_chapters", require_transaction=True)
