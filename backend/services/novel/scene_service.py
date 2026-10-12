"""篇章下场景规划、生命周期和祖先统计。"""

from __future__ import annotations

from typing import Any, Mapping

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import NotFoundError, VersionConflictError
from backend.db.repositories.arc_repository import arc_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.scene_repository import scene_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, resolve_idempotent_replay, update_versioned_document, validate_expected_version
from backend.services.novel.arc_service import _load_parents, _validate_references, validate_sibling_order, write_sibling_order
from backend.services.novel.scene_contract import SceneCreateV1, SceneReorderV1, SceneUpdateV1
from backend.services.novel.writing_context import require_volume_ready


async def load_scene_parent_chain(arc_id: str, *, session: AsyncClientSession | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """读取场景需要的活动小说、卷和篇章。

    Args:
        arc_id: 父篇章 ID。
        session: 可选事务。
    Returns:
        从小说到篇章的三个完整快照。
    """
    arc = await arc_repo.get_arc(arc_id, session=session)
    novel, volume = await _load_parents(str(arc["volume_id"]), session=session)
    if arc["novel_id"] != novel["_id"]:
        raise NotFoundError("篇章不属于当前父卷")
    return novel, volume, arc


async def update_scene_ancestors(novel: dict[str, Any], volume: dict[str, Any], arc: dict[str, Any], *, scenes_delta: int = 0, chapter_delta: int = 0, word_delta: int = 0, session: AsyncClientSession) -> None:
    """按小说、卷、篇章顺序争用父级并维护实际数量与字数。

    Args:
        novel: 小说快照。
        volume: 卷快照。
        arc: 篇章快照。
        scenes_delta: 当前篇章活动场景数量变化。
        chapter_delta: 活动章节数量变化。
        word_delta: 活动章节正文字数变化。
        session: 调用方已开启的必需事务。
    Returns:
        无；失败时由调用方事务整体回滚。
    """
    volume_fields = {"chapter_count": int(volume["chapter_count"]) + chapter_delta, "word_count": int(volume["word_count"]) + word_delta}
    arc_fields = {"scenes_count": int(arc["scenes_count"]) + scenes_delta, "chapter_count": int(arc["chapter_count"]) + chapter_delta, "word_count": int(arc["word_count"]) + word_delta}
    if min(*volume_fields.values(), *arc_fields.values()) < 0:
        raise DomainApiError("SCENE_STATS_CONFLICT", "章节数量或字数不一致，请刷新后重试", status_code=409)
    changed_novel = await novel_repo.update_stats_from_snapshot(novel, {"current_chapter_count": chapter_delta, "current_word_count": word_delta}, write_time=get_utc_now(), session=session)
    if changed_novel is None:
        raise VersionConflictError("小说在保存期间已发生变化，请重试")
    changed_volume = await volume_repo.update_from_snapshot(volume, volume_fields, increment_version=True, session=session)
    if changed_volume is None:
        raise VersionConflictError("所属卷在保存期间已发生变化，请重试")
    changed_arc = await update_versioned_document(arc_repo.collection, {"_id": arc["_id"], "novel_id": novel["_id"], "volume_id": volume["_id"]}, arc["version"], arc_fields, is_deleted=False, session=session)
    if changed_arc is None:
        raise VersionConflictError("所属篇章在保存期间已发生变化，请重试")


class SceneService:
    """场景只保存规划，所有写入使用必需事务。"""

    @staticmethod
    async def create_scene(arc_id: str, data: SceneCreateV1 | Mapping[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        """在篇章末尾幂等创建场景。

        Args:
            arc_id: 父篇章 ID。
            data: 场景内容。
            idempotency_key: 稳定创建键。
        Returns:
            新场景或已有创建结果。
        """
        async def create(session: AsyncClientSession) -> dict[str, Any]:
            return await SceneService.create_scene_in_session(arc_id, data, idempotency_key=idempotency_key, session=session)
        return await run_mongo_write_unit(create, "create_scene", require_transaction=True)

    @staticmethod
    async def create_scene_in_session(arc_id: str, data: SceneCreateV1 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession) -> dict[str, Any]:
        """在调用方事务中创建场景，支持整批审核原子保存。

        Args:
            arc_id: 父篇章 ID。
            data: 场景内容。
            idempotency_key: 当前父级内的稳定创建键。
            session: 已开启的必需事务。
        Returns:
            完整数据库场景。
        """
        fields = (data if isinstance(data, SceneCreateV1) else SceneCreateV1.model_validate(data)).model_dump()
        arc_id = str(to_object_id(arc_id))
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"arc_id": arc_id, **fields})
        novel, volume, arc = await load_scene_parent_chain(arc_id, session=session)
        existing = await scene_repo.collection.find_one({"arc_id": arc["_id"], "creation_idempotency_key_hash": fingerprint.key_hash}, session=session)
        replay = resolve_idempotent_replay(existing, fingerprint.request_hash, label="场景创建")
        if replay is not None:
            return replay
        require_volume_ready(volume)
        await update_scene_ancestors(novel, volume, arc, scenes_delta=1, session=session)
        await _validate_references(fields["planning"], novel["_id"], volume_id=volume["_id"], session=session, error_prefix="SCENE", label="场景")
        last = await scene_repo.collection.find_one({"arc_id": arc["_id"], "is_deleted": False}, {"order_index": 1}, sort=[("order_index", -1)], session=session)
        now = get_utc_now().replace(tzinfo=None)
        now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
        scene = {"_id": ObjectId(), "novel_id": novel["_id"], "volume_id": volume["_id"], "arc_id": arc["_id"], **fields, "order_index": 1 if last is None else last["order_index"] + 1, "chapter_count": 0, "word_count": 0, "version": 1, "is_deleted": False, "deleted_at": None, "created_at": now, "updated_at": now, **fingerprint.as_creation_fields()}
        await scene_repo.collection.insert_one(scene, session=session)
        return scene

    @staticmethod
    async def get_scene(scene_id: str, *, include_deleted: bool = False, novel_id: str | None = None, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """读取场景并核对活动父链。

        Args:
            scene_id: 场景 ID。
            include_deleted: 是否允许回收站。
            novel_id: 可选小说范围。
            session: 可选事务。
        Returns:
            完整场景。
        """
        scene = await scene_repo.get_scene(scene_id, include_deleted=include_deleted, session=session)
        novel, volume, _ = await load_scene_parent_chain(str(scene["arc_id"]), session=session)
        if scene["novel_id"] != novel["_id"] or scene["volume_id"] != volume["_id"] or (novel_id is not None and to_object_id(novel_id) != novel["_id"]):
            raise NotFoundError("场景不属于当前小说或父篇章")
        return scene

    @staticmethod
    async def list_scenes(arc_id: str, *, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict[str, Any]]:
        """读取活动篇章下的场景目录或回收站。

        Args:
            arc_id: 父篇章 ID。
            deleted: 是否查看回收站。
            session: 可选事务。
        Returns:
            按篇章内顺序排列的场景。
        """
        novel, volume, arc = await load_scene_parent_chain(arc_id, session=session)
        scenes = await scene_repo.list_scenes(arc_id, deleted=deleted, session=session)
        if any(scene["novel_id"] != novel["_id"] or scene["volume_id"] != volume["_id"] for scene in scenes):
            raise NotFoundError("场景不属于当前父篇章")
        current = await load_scene_parent_chain(arc_id, session=session)
        if [item["version"] for item in current] != [novel["version"], volume["version"], arc["version"]]:
            raise DomainApiError("SCENE_DIRECTORY_CHANGED", "场景目录正在更新，请刷新后重试", status_code=409)
        return scenes

    @staticmethod
    async def update_scene(scene_id: str, data: SceneUpdateV1 | Mapping[str, Any]) -> dict[str, Any]:
        """按版本局部修改场景规划。

        Args:
            scene_id: 场景 ID。
            data: 局部内容和已读版本。
        Returns:
            保存后的完整场景。
        """
        async def update(session: AsyncClientSession) -> dict[str, Any]:
            return await SceneService.update_scene_in_session(scene_id, data, session=session)
        return await run_mongo_write_unit(update, "update_scene", require_transaction=True)

    @staticmethod
    async def update_scene_in_session(scene_id: str, data: SceneUpdateV1 | Mapping[str, Any], *, session: AsyncClientSession) -> dict[str, Any]:
        """在当前事务中更新场景，原样提交不写入。

        Args:
            scene_id: 场景 ID。
            data: 局部内容与已读版本。
            session: 已开启的必需事务。
        Returns:
            保存后的场景。
        """
        request = data if isinstance(data, SceneUpdateV1) else SceneUpdateV1.model_validate(data)
        fields = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
        if "planning" in fields:
            fields["planning"] = request.planning.model_dump()
        scene = await SceneService.get_scene(scene_id, session=session)
        if scene["version"] != request.expected_version:
            raise VersionConflictError("场景已被修改，请保留草稿并刷新后比较")
        if all(scene[key] == value for key, value in fields.items()):
            return scene
        novel, volume, arc = await load_scene_parent_chain(str(scene["arc_id"]), session=session)
        await update_scene_ancestors(novel, volume, arc, session=session)
        if "planning" in fields:
            await _validate_references(fields["planning"], novel["_id"], volume_id=volume["_id"], session=session, error_prefix="SCENE", label="场景")
        changed = await update_versioned_document(scene_repo.collection, {"_id": scene["_id"], "novel_id": novel["_id"], "arc_id": arc["_id"]}, request.expected_version, fields, is_deleted=False, session=session)
        if changed is None:
            raise VersionConflictError("场景保存期间已发生变化，请重试")
        return changed

    @staticmethod
    async def get_delete_impact(scene_id: str, *, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """统计场景下活动及回收站章节。

        Args:
            scene_id: 场景 ID。
            session: 可选事务。
        Returns:
            章节计数和删除保护标记。
        """
        scene = await SceneService.get_scene(scene_id, include_deleted=True, session=session)
        query = {"scene_id": {"$in": [scene["_id"], str(scene["_id"])]}}
        collection = BaseRepository("chapters").collection
        total = await collection.count_documents(query, session=session)
        deleted = await collection.count_documents({**query, "is_deleted": True}, session=session)
        from backend.services.novel.foreshadowing_service import count_foreshadowing_references
        foreshadowings = await count_foreshadowing_references(scene["novel_id"], "scene", scene["_id"], session=session)
        from backend.services.novel.chapter_record_source import count_chapter_record_references
        records = await count_chapter_record_references(scene["novel_id"], "scene", scene["_id"], session=session)
        return {"scene_id": str(scene["_id"]), "chapters": total, "active_chapters": total - deleted, "deleted_chapters": deleted, "foreshadowings": foreshadowings, "chapter_records": records, "total": total + foreshadowings + records, "has_blockers": total + foreshadowings + records > 0}

    @staticmethod
    async def set_deleted(scene_id: str, *, expected_version: int, deleted: bool, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """回收无下级场景，或校验引用后恢复到篇章末尾。

        Args:
            scene_id: 场景 ID。
            expected_version: 已读版本。
            deleted: True 回收，False 恢复。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            状态改变后的场景。
        """
        expected = validate_expected_version(expected_version)

        async def change(session: AsyncClientSession) -> dict[str, Any]:
            scene = await SceneService.get_scene(scene_id, include_deleted=True, session=session)
            if scene["version"] != expected:
                raise VersionConflictError("场景版本已变化，请刷新后重试")
            if scene["is_deleted"] == deleted:
                raise DomainApiError("SCENE_STATE_CONFLICT", "场景已经处于目标状态", status_code=409)
            novel, volume, arc = await load_scene_parent_chain(str(scene["arc_id"]), session=session)
            if deleted:
                impact = await SceneService.get_delete_impact(scene_id, session=session)
                if impact["total"] - impact["chapter_records"]:
                    raise DomainApiError("SCENE_DELETE_BLOCKED", "场景下还有章节，请先处理下级内容", status_code=409)
            await update_scene_ancestors(novel, volume, arc, scenes_delta=-1 if deleted else 1, session=session)
            if not deleted:
                await _validate_references(scene["planning"], novel["_id"], volume_id=volume["_id"], session=session, error_prefix="SCENE", label="场景")
            siblings = await scene_repo.list_scenes(str(arc["_id"]), session=session)
            fields = {"is_deleted": deleted, "deleted_at": get_utc_now() if deleted else None}
            if not deleted:
                fields["order_index"] = max((item["order_index"] for item in siblings), default=0) + 1
            changed = await update_versioned_document(scene_repo.collection, {"_id": scene["_id"]}, expected, fields, is_deleted=not deleted, session=session)
            if changed is None:
                raise VersionConflictError("场景状态在保存期间已变化")
            if deleted:
                for sibling in siblings:
                    if sibling["order_index"] > scene["order_index"]:
                        moved = await update_versioned_document(scene_repo.collection, {"_id": sibling["_id"]}, sibling["version"], {"order_index": sibling["order_index"] - 1}, is_deleted=False, session=session)
                        if moved is None:
                            raise VersionConflictError("场景顺序已变化，请重试")
            return changed
        if session is not None:
            return await change(session)

        return await run_mongo_write_unit(change, "change_scene_deleted", require_transaction=True)

    @staticmethod
    async def hard_delete_scene(scene_id: str, *, expected_version: int) -> None:
        """永久删除没有章节的回收站场景。

        Args:
            scene_id: 场景 ID。
            expected_version: 已读版本。
        Returns:
            无。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession) -> None:
            scene = await SceneService.get_scene(scene_id, include_deleted=True, session=session)
            if scene["version"] != expected:
                raise VersionConflictError("场景版本已变化，请刷新后重试")
            if not scene["is_deleted"]:
                raise DomainApiError("SCENE_DELETE_BLOCKED", "请先将场景移入回收站", status_code=409)
            impact = await SceneService.get_delete_impact(scene_id, session=session)
            if impact["chapter_records"]:
                raise DomainApiError("SCENE_CHAPTER_RECORD_DELETE_BLOCKED", "场景仍是章后确认记录的来源，如需全部清理请删除整部作品", status_code=409, details={"chapter_records": impact["chapter_records"]})
            if impact["has_blockers"]:
                raise DomainApiError("SCENE_DELETE_BLOCKED", "场景下还有章节，请先处理下级内容", status_code=409)
            novel, volume, arc = await load_scene_parent_chain(str(scene["arc_id"]), session=session)
            await update_scene_ancestors(novel, volume, arc, session=session)
            result = await scene_repo.collection.delete_one({"_id": scene["_id"], "version": expected, "is_deleted": True}, session=session)
            if result.deleted_count != 1:
                raise VersionConflictError("场景删除期间已发生变化")
        await run_mongo_write_unit(delete, "hard_delete_scene", require_transaction=True)

    @staticmethod
    async def reorder_scenes(arc_id: str, data: SceneReorderV1 | Mapping[str, Any], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """在同一篇章内按完整列表重排场景。

        Args:
            arc_id: 父篇章 ID。
            data: 全部活动场景的版本和目标序号。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新顺序下的场景列表。
        """
        request = data if isinstance(data, SceneReorderV1) else SceneReorderV1.model_validate(data)

        async def reorder(session: AsyncClientSession) -> list[dict[str, Any]]:
            novel, volume, arc = await load_scene_parent_chain(arc_id, session=session)
            current = await scene_repo.list_scenes(arc_id, session=session)
            ordered = validate_sibling_order(current, request.model_dump()["items"], id_field="scene_id")
            if all(before["order_index"] == order for before, order in ordered):
                return current
            await update_scene_ancestors(novel, volume, arc, session=session)
            return await write_sibling_order(scene_repo.collection, ordered, session=session)
        if session is not None:
            return await reorder(session)

        return await run_mongo_write_unit(reorder, "reorder_scenes", require_transaction=True)
