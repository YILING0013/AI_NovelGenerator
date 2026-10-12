"""伏笔计划与章节证据；所有保存和来源保护在同一事务内完成。"""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Mapping

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import IdempotencyConflictError, NotFoundError, VersionConflictError
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, update_versioned_document, validate_expected_version
from backend.services.novel.foreshadowing_contract import (
    ForeshadowingCreateV1, ForeshadowingEvidenceInputV1, ForeshadowingRecordV1,
    ForeshadowingUpdateV1,
)
from backend.services.novel.writing_context import COLLECTIONS, load_writing_parents


foreshadowing_repo = BaseRepository("foreshadowings")
creation_receipt_repo = BaseRepository("foreshadowing_creation_receipts")
STATUS_TRANSITIONS = {
    "planned": {"planned", "planted", "abandoned"},
    "planted": {"planted", "planned", "resolved", "abandoned"},
    "resolved": {"resolved", "planted", "abandoned"},
    "abandoned": {"abandoned", "planned", "planted"},
}


async def protect_foreshadowing_sources(guards: dict[tuple[str, str], dict], *, session: AsyncClientSession) -> None:
    """触碰当前来源，让保存与并发删除争用同一文档，不改业务版本。

    Args:
        guards: 已在本事务内读到的小说及层级文档。
        session: 当前必需事务。
    Returns:
        无；任何来源变化都让事务回滚。
    """
    for (collection_name, _), document in guards.items():
        query = {"_id": document["_id"], "version": document["version"], "is_deleted": document["is_deleted"]}
        query.update({name: document[name] for name in ("novel_id", "volume_id", "arc_id", "scene_id") if name in document})
        if collection_name == "novels":
            query.update(hard_delete_claim={"$exists": False}, location_write_lock_token=None, item_write_lock_token=None, state_write_lock_token=None)
        # $inc 能从缺失字段开始；旧章没有 dependency_guard_revision，不能用实体主档的护栏。
        result = await BaseRepository(collection_name).collection.update_one(query, {"$inc": {"writing_guard_revision": 1}}, session=session)
        if result.matched_count != 1:
            raise VersionConflictError("伏笔引用或所属小说已变化，请保留稿件后重试")


async def count_foreshadowing_references(novel_id: ObjectId, kind: str, identity: ObjectId, *, session: AsyncClientSession | None = None) -> int:
    """统计仍占用来源的伏笔，包括回收站记录。

    Args:
        novel_id: 来源所属小说。
        kind: volume、arc、scene 或 chapter。
        identity: 来源的物理 ID。
        session: 可选事务。
    Returns:
        引用该位置或该章节证据的不同伏笔数量。
    """
    if kind == "chapter":
        references = [{f"{name}.chapter_id": str(identity)} for name in ("planted_evidence", "resolved_evidence")]
    else:
        references = [{f"{name}.kind": kind, f"{name}.id": str(identity)} for name in ("planting_position", "resolution_position")]
    return await foreshadowing_repo.collection.count_documents({"novel_id": novel_id, "$or": references}, session=session)


async def _validate_positions(fields: Mapping, novel_id: str, guards: dict, *, session: AsyncClientSession) -> None:
    """校验本次明确修改的位置，并保护其完整活动父链。"""
    for name in ("planting_position", "resolution_position"):
        position = fields.get(name)
        if position is None:
            continue
        chain = await load_writing_parents(novel_id, position["kind"], position["id"], session=session)
        guards.update({(COLLECTIONS[kind], str(row["_id"])): row for kind, row in chain})


async def _bind_evidence(value: ForeshadowingEvidenceInputV1 | None, novel_id: str, guards: dict, *, session: AsyncClientSession) -> dict | None:
    """把作者提交的原文位置绑定到已存在的不可变修订。"""
    if value is None:
        return None
    chain = await load_writing_parents(novel_id, "chapter", value.chapter_id, session=session)
    chapter = chain[-1][1]
    revision = await BaseRepository("chapter_revisions").collection.find_one({
        "chapter_id": chapter["_id"], "novel_id": chapter["novel_id"], "version": value.version,
        **{name: chapter[name] for name in ("volume_id", "arc_id", "scene_id")},
    }, session=session)
    if revision is None:
        raise DomainApiError("FORESHADOWING_REVISION_NOT_FOUND", "所选章节版本没有已保存修订，请选择历史中实际存在的版本", status_code=404)
    content = revision["content"]
    if content[value.start:value.start + len(value.quote)] != value.quote:
        raise DomainApiError("FORESHADOWING_QUOTE_MISMATCH", "原文片段与所选修订的位置不一致，请重新选择片段", field_errors={"quote": "片段不匹配"})
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != revision["content_hash"]:
        raise DomainApiError("FORESHADOWING_REVISION_INVALID", "所选修订的正文校验失败", status_code=409)
    guards.update({(COLLECTIONS[kind], str(row["_id"])): row for kind, row in chain})
    return {**value.model_dump(), "chapter_id": str(chapter["_id"]), "revision_id": str(revision["_id"]), "content_hash": revision["content_hash"]}


async def _with_review(document: dict, *, session: AsyncClientSession | None = None) -> dict:
    """只读比较当前正文；删章也提醒复核，元数据变化不误报。"""
    result = deepcopy(document)
    for name, flag in (("planted_evidence", "planted_needs_review"), ("resolved_evidence", "resolved_needs_review")):
        evidence = document[name]
        result[flag] = False
        if evidence is not None:
            chapter = await BaseRepository("chapters").collection.find_one({"_id": ObjectId(evidence["chapter_id"]), "novel_id": document["novel_id"]}, session=session)
            result[flag] = chapter is None or chapter["is_deleted"] or hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest() != evidence["content_hash"]
    return result


class ForeshadowingService:
    """小说内伏笔的明确保存流程，不被 AI 自动调用写入。"""

    @staticmethod
    async def create(novel_id: str, data: ForeshadowingCreateV1 | Mapping, *, idempotency_key: str) -> dict:
        """同键重放原创建结果，目标已硬删也不再创建。

        Args:
            novel_id: 小说范围。
            data: 完整伏笔计划。
            idempotency_key: 本次创建的固定请求键。
        Returns:
            新计划或原成功快照。
        """
        fields = ForeshadowingCreateV1.model_validate(data).model_dump()
        for name in ("planting_position", "resolution_position"):
            if fields[name] is not None:
                fields[name]["id"] = fields[name]["id"].lower()
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"novel_id": novel_id.lower(), "plan": fields})
        async def save(session):
            novel = await novel_repo.get_novel_by_id(novel_id, session=session)
            existing = await creation_receipt_repo.collection.find_one({"novel_id": novel["_id"], "idempotency_key_hash": fingerprint.key_hash}, session=session)
            if existing is not None:
                if existing["request_hash"] != fingerprint.request_hash:
                    raise IdempotencyConflictError("同一创建键已用于不同伏笔，请保留原稿并使用新键")
                return deepcopy(existing["result"])
            guards = {("novels", novel_id): novel}
            await _validate_positions(fields, novel_id, guards, session=session)
            await protect_foreshadowing_sources(guards, session=session)
            identity = (await id_sequence_repo.allocate_many(novel_id, "foreshadowing", "fo", 1, session=session))[0]
            now = get_utc_now()
            now = now.replace(tzinfo=None, microsecond=now.microsecond // 1000 * 1000)
            document = {"_id": ObjectId(), "novel_id": novel["_id"], "foreshadowing_id": identity, **fields,
                        "status": "planned", "planted_evidence": None, "resolved_evidence": None,
                        "version": 1, "is_deleted": False, "deleted_at": None, "created_at": now, "updated_at": now}
            await foreshadowing_repo.collection.insert_one(document, session=session)
            result = await _with_review(document, session=session)
            await creation_receipt_repo.collection.insert_one({"_id": ObjectId(), "novel_id": novel["_id"], "idempotency_key_hash": fingerprint.key_hash, "request_hash": fingerprint.request_hash, "result": result}, session=session)
            return result
        return await run_mongo_write_unit(save, "create_foreshadowing", require_transaction=True)

    @staticmethod
    async def get(novel_id: str, identity: str, *, include_deleted: bool = False, session: AsyncClientSession | None = None) -> dict:
        """按小说和业务 ID 读取；回收站读取也允许已删小说。

        Args:
            novel_id: 小说范围。
            identity: 伏笔业务 ID。
            include_deleted: 是否允许回收站及已删小说。
            session: 可选事务。
        Returns:
            原记录及只读复核标记。
        """
        await novel_repo.get_novel_by_id(novel_id, include_deleted=include_deleted, session=session)
        document = await foreshadowing_repo.find_one({"novel_id": to_object_id(novel_id), "foreshadowing_id": identity}, include_deleted=include_deleted, session=session)
        if document is None:
            raise NotFoundError("伏笔不存在于当前小说或已回收")
        return await _with_review(document, session=session)

    @staticmethod
    async def list(novel_id: str, *, deleted: bool = False, include_deleted_novel: bool = False, q: str | None = None, status: str | None = None, position_kind: str | None = None, position_id: str | None = None, session: AsyncClientSession | None = None) -> list[dict]:
        """检索计划内容及稳定位置，不改事实也不阻断写作。

        Args:
            novel_id: 小说范围。
            deleted: 是否只返回回收站记录；该模式允许已删小说。
            include_deleted_novel: 明确读取已删小说的未回收伏笔，用于逐条清理。
            q: 普通检索文字。
            status: 可选作者状态。
            position_kind: 可选计划层级。
            position_id: 与层级成对的物理 ID。
            session: 可选事务。
        Returns:
            按业务 ID 排列的伏笔。
        """
        await novel_repo.get_novel_by_id(novel_id, include_deleted=deleted or include_deleted_novel, session=session)
        if (position_kind is None) != (position_id is None):
            raise ValueError("位置类别和位置 ID 必须一起提供")
        query = {"novel_id": to_object_id(novel_id), "is_deleted": deleted}
        if status is not None:
            query["status"] = status
        conditions = []
        if q:
            conditions.append({"$or": [{name: {"$regex": re.escape(q), "$options": "i"}} for name in ("title", "content", "target_effect")]})
        if position_id is not None:
            conditions.append({"$or": [{f"{name}.kind": position_kind, f"{name}.id": position_id.lower()} for name in ("planting_position", "resolution_position")]})
        if conditions:
            query["$and"] = conditions
        rows = await foreshadowing_repo.find_many(query, include_deleted=True, sort=[("foreshadowing_id", 1)], session=session)
        return [await _with_review(row, session=session) for row in rows]

    @staticmethod
    async def update(novel_id: str, identity: str, data: ForeshadowingUpdateV1 | Mapping) -> dict:
        """只改明确提交的计划字段，旧证据和状态不变。

        Args:
            novel_id: 小说范围。
            identity: 伏笔业务 ID。
            data: 原版本和局部计划。
        Returns:
            保存后的记录。
        """
        fields = ForeshadowingUpdateV1.model_validate(data).model_dump(exclude_unset=True)
        expected = fields.pop("expected_version")
        async def save(session):
            current = await ForeshadowingService.get(novel_id, identity, session=session)
            if current["version"] != expected:
                raise VersionConflictError("伏笔版本已变化，请保留原稿并刷新后比较")
            guards = {("novels", novel_id): await novel_repo.get_novel_by_id(novel_id, session=session)}
            for name in ("planting_position", "resolution_position"):
                if fields.get(name) is not None:
                    fields[name]["id"] = fields[name]["id"].lower()
            await _validate_positions(fields, novel_id, guards, session=session)
            if all(current[name] == value for name, value in fields.items()):
                return current
            await protect_foreshadowing_sources(guards, session=session)
            changed = await update_versioned_document(foreshadowing_repo.collection, {"_id": current["_id"], "novel_id": current["novel_id"]}, expected, fields, is_deleted=False, session=session)
            if changed is None:
                raise VersionConflictError("伏笔在保存期间已变化，请保留原稿")
            return await _with_review(changed, session=session)
        return await run_mongo_write_unit(save, "update_foreshadowing", require_transaction=True)

    @staticmethod
    async def record(novel_id: str, identity: str, data: ForeshadowingRecordV1 | Mapping) -> dict:
        """作者明确改变状态；未提交的证据保持原值。

        Args:
            novel_id: 小说范围。
            identity: 伏笔业务 ID。
            data: 原版本、目标状态和明确修改的证据。
        Returns:
            同一事务保存后的记录。
        """
        model = ForeshadowingRecordV1.model_validate(data)
        async def save(session):
            current = await ForeshadowingService.get(novel_id, identity, session=session)
            if current["version"] != model.expected_version:
                raise VersionConflictError("伏笔版本已变化，请保留记录后刷新")
            if model.status not in STATUS_TRANSITIONS[current["status"]]:
                raise DomainApiError("FORESHADOWING_STATUS_CONFLICT", "不能直接跳到目标状态，请先确认埋设记录", status_code=409)
            guards = {("novels", novel_id): await novel_repo.get_novel_by_id(novel_id, session=session)}
            fields = {"status": model.status}
            for name in ("planted_evidence", "resolved_evidence"):
                if name in model.model_fields_set:
                    fields[name] = await _bind_evidence(getattr(model, name), novel_id, guards, session=session)
            resulting = {**current, **fields}
            if (model.status in {"planted", "resolved"} and resulting["planted_evidence"] is None) or (model.status == "resolved" and resulting["resolved_evidence"] is None):
                raise DomainApiError("FORESHADOWING_EVIDENCE_REQUIRED", "埋设需要章节证据，回收需要同时保留埋设和回收证据")
            if all(current[name] == value for name, value in fields.items()):
                return current
            await protect_foreshadowing_sources(guards, session=session)
            changed = await update_versioned_document(foreshadowing_repo.collection, {"_id": current["_id"], "novel_id": current["novel_id"]}, model.expected_version, fields, is_deleted=False, session=session)
            if changed is None:
                raise VersionConflictError("伏笔在记录期间已变化，请保留原稿")
            return await _with_review(changed, session=session)
        return await run_mongo_write_unit(save, "record_foreshadowing", require_transaction=True)

    @staticmethod
    async def set_deleted(novel_id: str, identity: str, *, expected_version: int, deleted: bool) -> dict:
        """回收或恢复伏笔，已删书仍可回收以逐条清理引用。

        Args:
            novel_id: 小说范围。
            identity: 伏笔业务 ID。
            expected_version: 已读版本。
            deleted: True 回收，False 恢复。
        Returns:
            状态改变后的记录。
        """
        expected = validate_expected_version(expected_version)
        async def save(session):
            current = await ForeshadowingService.get(novel_id, identity, include_deleted=True, session=session)
            if current["version"] != expected or current["is_deleted"] == deleted:
                raise VersionConflictError("伏笔版本或回收状态已变化，请刷新后重试")
            novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=deleted, session=session)
            guards = {("novels", novel_id): novel}
            if not deleted:
                await _validate_positions(current, novel_id, guards, session=session)
                for name in ("planted_evidence", "resolved_evidence"):
                    if current[name] is not None:
                        evidence = ForeshadowingEvidenceInputV1.model_validate({key: current[name][key] for key in ForeshadowingEvidenceInputV1.model_fields})
                        bound = await _bind_evidence(evidence, novel_id, guards, session=session)
                        if bound != current[name]:
                            raise VersionConflictError("伏笔证据修订不一致，不能恢复")
            await protect_foreshadowing_sources(guards, session=session)
            changed = await update_versioned_document(foreshadowing_repo.collection, {"_id": current["_id"], "novel_id": current["novel_id"]}, expected, {"is_deleted": deleted, "deleted_at": get_utc_now() if deleted else None}, is_deleted=not deleted, session=session)
            if changed is None:
                raise VersionConflictError("伏笔回收状态在保存期间已变化")
            return await _with_review(changed, session=session)
        return await run_mongo_write_unit(save, "change_foreshadowing_deleted", require_transaction=True)

    @staticmethod
    async def hard_delete(novel_id: str, identity: str, *, expected_version: int) -> None:
        """逐条永久删除回收站伏笔，创建成功回执保留防重复。

        Args:
            novel_id: 活动或已删小说范围。
            identity: 回收站伏笔业务 ID。
            expected_version: 作者已读版本。
        Returns:
            无；删除成功解除该伏笔的来源引用。
        """
        expected = validate_expected_version(expected_version)
        async def remove(session):
            current = await ForeshadowingService.get(novel_id, identity, include_deleted=True, session=session)
            if current["version"] != expected or not current["is_deleted"]:
                raise VersionConflictError("请先回收伏笔，并使用已读版本永久删除")
            novel = await novel_repo.get_novel_by_id(novel_id, include_deleted=True, session=session)
            await protect_foreshadowing_sources({("novels", novel_id): novel}, session=session)
            result = await foreshadowing_repo.collection.delete_one({"_id": current["_id"], "novel_id": current["novel_id"], "version": expected, "is_deleted": True}, session=session)
            if result.deleted_count != 1:
                raise VersionConflictError("伏笔在删除期间已变化")
        await run_mongo_write_unit(remove, "hard_delete_foreshadowing", require_transaction=True)
