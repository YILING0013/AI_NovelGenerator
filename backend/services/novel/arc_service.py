"""卷下篇章规划、版本化保存和回收站操作。"""

from __future__ import annotations

from typing import Any, Mapping

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import touch_dependency_endpoint_guards
from backend.db.errors import DuplicateKeyError, NotFoundError, VersionConflictError
from backend.db.repositories.arc_repository import arc_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import build_idempotency_fingerprint, resolve_idempotent_replay, update_versioned_document, validate_expected_version
from backend.services.novel.arc_contract import ArcCreateV1, ArcReorderV1, ArcUpdateV1
from backend.services.novel.writing_context import require_volume_ready
from backend.services.novel.foreshadowing_service import count_foreshadowing_references


async def _load_parents(volume_id: str, *, session: AsyncClientSession | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """读取活动父卷与小说，避开尚未完成的资料保存。

    Args:
        volume_id: 所属卷 ID。
        session: 当前读取或写入使用的会话。

    Returns:
        活动小说和所属卷。
    """
    volume = await volume_repo.get_volume_by_id(volume_id, session=session)
    novel = await novel_repo.get_novel_by_id(str(volume["novel_id"]), session=session)
    if any(novel.get(name) is not None for name in ("location_write_lock_token", "item_write_lock_token", "state_write_lock_token")):
        raise DomainApiError("ARC_PARENT_BUSY", "Đang lưu tài liệu tiểu thuyết, hãy thử lại sau", status_code=409)
    return novel, volume


async def _update_parents(novel: dict[str, Any], volume: dict[str, Any], *, arcs_delta: int = 0, session: AsyncClientSession) -> None:
    """同一事务内维护篇章数，并阻止父级删除或重规划交错保存。

    Args:
        novel: 本次读取的小说快照。
        volume: 本次读取的父卷快照。
        arcs_delta: 活动篇章数量变化，编辑和硬删时为零。
        session: 当前必需事务的会话。

    Returns:
        无；父级版本已变或计数错误时抛出冲突。
    """
    arcs_count = int(volume["arcs_count"]) + arcs_delta
    if arcs_count < 0:
        raise DomainApiError("ARC_STATS_CONFLICT", "Số lượng vòng truyện không khớp, hãy làm mới rồi thử lại", status_code=409)
    changed = await novel_repo.update_stats_from_snapshot(
        novel, {}, write_time=get_utc_now(), session=session,
    )
    if changed is None:
        raise VersionConflictError("Tiểu thuyết đã thay đổi trong khi lưu vòng truyện, hãy thử lại")
    changed_volume = await volume_repo.update_from_snapshot(volume, {"arcs_count": arcs_count}, increment_version=True, session=session)
    if changed_volume is None:
        raise VersionConflictError("Quyển sở hữu đã thay đổi trong khi lưu vòng truyện, hãy thử lại")


async def _validate_references(planning: Mapping[str, Any], novel_id: ObjectId, *, volume_id: ObjectId, session: AsyncClientSession, error_prefix: str = "ARC", label: str = "篇章", protected_references: dict[str, set[str]] | None = None) -> None:
    """检查明确选择的引用，并与实体回收或删除产生写冲突。

    Args:
        planning: 已完成字段校验的篇章规划。
        novel_id: 所属小说的 ObjectId。
        volume_id: 所属卷的 ObjectId，用于检查局部势力。
        session: 当前必需事务的会话。
        error_prefix: 当前规划领域的错误码前缀。
        label: 当前规划的界面名称。
        protected_references: 仅本次同卷篇章创建批次已完成写保护的引用。

    Returns:
        无；不可用引用或并发变化时整笔保存失败。
    """
    endpoints: list[tuple[Any, list[dict[str, Any]]]] = []
    checked_references: dict[str, list[str]] = {}
    for field, collection_name, id_field, availability in (
        ("character_ids", "characters", "character_id", {"status": "active"}),
        ("faction_ids", "factions", "faction_id", {"active_status": "active"}),
        ("location_ids", "locations", "location_id", {"status": "active", "location_order_pending_token": None}),
        # 物品的持有、损毁等状态是故事内容；可引用性由是否回收决定。
        ("item_ids", "items", "item_id", {"item_write_pending_token": None}),
        ("rule_ids", "world_rules", "rule_id", {"status": "active"}),
    ):
        if not planning[field]:
            continue
        reference_ids = list(dict.fromkeys(planning[field]))
        if protected_references is not None:
            protected = protected_references.get(field, set())
            reference_ids = [identity for identity in reference_ids if identity not in protected]
        if not reference_ids:
            continue
        collection = BaseRepository(collection_name).collection
        query = {"novel_id": novel_id, "is_deleted": False, **availability}
        if field == "faction_ids":
            # 卷级和局部势力只能参与其归属卷，核心势力可参与任意卷。
            query["$or"] = [
                {"level_type": "core", "volume_id": None},
                {"level_type": {"$in": ["volume", "local"]}, "volume_id": volume_id},
            ]
        # 同类引用一次读取；后续仍按原顺序报告缺项，并逐条保留保护条件。
        documents = await collection.find(
            {**query, id_field: {"$in": reference_ids}}, session=session,
        ).to_list(length=None)
        by_id = {document[id_field]: document for document in documents}
        queries = []
        for reference_id in reference_ids:
            document = by_id.get(reference_id)
            if document is None:
                raise DomainApiError(
                    f"{error_prefix}_REFERENCE_NOT_FOUND", f"{label}tham chiếu không tồn tại, đã bị thu hồi, đã ngừng kích hoạt hoặc không thuộc tiểu thuyết hiện tại", status_code=404,
                    field_errors={f"planning.{field}": "引用不可用"}, details={"reference_id": reference_id},
                )
            queries.append({**query, id_field: reference_id, "_id": document["_id"], "version": document["version"]})
        endpoints.append((collection, queries))
        checked_references[field] = reference_ids
    try:
        for collection, queries in endpoints:
            await touch_dependency_endpoint_guards(collection, queries, session=session)
    except DuplicateKeyError as exc:
        raise DomainApiError(f"{error_prefix}_REFERENCE_CONFLICT", f"{label}tham chiếu đã thay đổi trong quá trình lưu, hãy làm mới rồi thử lại", status_code=409) from exc
    if protected_references is not None:
        # 只有实际写保护成功后才能复用；后续篇章仍按原顺序检查未见过的引用。
        for field, reference_ids in checked_references.items():
            protected_references.setdefault(field, set()).update(reference_ids)


def validate_sibling_order(current: list[dict[str, Any]], items: list[dict[str, Any]], *, id_field: str) -> list[tuple[dict[str, Any], int]]:
    """校验三层共用的完整兄弟排序，不允许静默漏项或跨父级移动。

    Args:
        current: 当前父级的全部活动子项。
        items: 请求的 ID、版本和目标序号。
        id_field: 对应领域的公开 ID 字段。
    Returns:
        按新顺序排列的原文档及目标序号。
    """
    ids = [to_object_id(item[id_field]) for item in items]
    orders = [item["order_index"] for item in items]
    if len(set(ids)) != len(ids) or sorted(orders) != list(range(1, len(items) + 1)):
        raise ValueError("Sắp xếp lại phải gồm các đối tượng không trùng và số thứ tự 1..N liên tục")
    by_id = {item["_id"]: item for item in current}
    if any(item_id not in by_id for item_id in ids):
        raise NotFoundError("Đối tượng sắp xếp không tồn tại, đã thu hồi hoặc không thuộc cha hiện tại")
    if set(ids) != set(by_id):
        raise VersionConflictError("Danh mục đã thay đổi, sắp xếp lại phải gửi toàn bộ anh em đang hoạt động")
    result = []
    for item_id, item in zip(ids, items, strict=True):
        before = by_id[item_id]
        if before["version"] != item["expected_version"]:
            raise VersionConflictError("Phiên bản danh mục đã thay đổi, hãy làm mới rồi sắp xếp lại")
        result.append((before, item["order_index"]))
    return sorted(result, key=lambda entry: entry[1])


async def write_sibling_order(collection: Any, ordered: list[tuple[dict[str, Any], int]], *, session: AsyncClientSession) -> list[dict[str, Any]]:
    """在父级已争用的事务内交换子项顺序，每项公开版本只增加一次。

    Args:
        collection: 篇章、场景或章节集合。
        ordered: 已校验的原文档和目标序号。
        session: 当前必需事务。
    Returns:
        按新顺序排列的写后文档。
    """
    for before, order in ordered:
        changed = await collection.update_one(
            {"_id": before["_id"], "version": before["version"], "is_deleted": False, "order_index": before["order_index"]},
            {"$set": {"order_index": -order}}, session=session,
        )
        if changed.matched_count != 1:
            raise VersionConflictError("Nội dung đã thay đổi trong khi sắp xếp lại, hãy thử lại")
    result = []
    for before, order in ordered:
        changed = await update_versioned_document(collection, {"_id": before["_id"], "order_index": -order}, before["version"], {"order_index": order}, is_deleted=False, session=session)
        if changed is None:
            raise VersionConflictError("Nội dung đã thay đổi trong khi sắp xếp lại, hãy thử lại")
        result.append(changed)
    return result


async def _check_children(arc: Mapping[str, Any], *, session: AsyncClientSession) -> None:
    """检查实际下级，避免删除父篇章后留下无归属数据。

    Args:
        arc: 将要回收或永久删除的篇章。
        session: 当前必需事务的会话。

    Returns:
        无；存在活动或回收站下级时抛出冲突。
    """
    query = {"arc_id": {"$in": [arc["_id"], str(arc["_id"])]}}
    for name in ("scenes", "chapters"):
        if await BaseRepository(name).collection.find_one(query, {"_id": 1}, session=session):
            raise DomainApiError("ARC_DELETE_BLOCKED", "Vòng truyện còn chứa cảnh hoặc chương, hãy xử lý nội dung cấp dưới trước", status_code=409)


class ArcService:
    """使用必需事务保存篇章及其父级统计。"""

    @staticmethod
    async def get_delete_impact(arc_id: str, *, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """统计篇章下活动及回收站的场景和章节。

        Args:
            arc_id: 当前篇章 ID。
            session: 可选事务。
        Returns:
            精确下级计数和是否阻止删除。
        """
        arc = await ArcService.get_arc(arc_id, include_deleted=True, session=session)
        query = {"arc_id": {"$in": [arc["_id"], str(arc["_id"])]}}
        result: dict[str, Any] = {"arc_id": str(arc["_id"])}
        for name in ("scenes", "chapters"):
            collection = BaseRepository(name).collection
            total = await collection.count_documents(query, session=session)
            deleted = await collection.count_documents({**query, "is_deleted": True}, session=session)
            result[name] = total
            result[f"active_{name}"] = total - deleted
            result[f"deleted_{name}"] = deleted
        result["foreshadowings"] = await count_foreshadowing_references(arc["novel_id"], "arc", arc["_id"], session=session)
        from backend.services.novel.chapter_record_source import count_chapter_record_references
        result["chapter_records"] = await count_chapter_record_references(arc["novel_id"], "arc", arc["_id"], session=session)
        result["total"] = result["scenes"] + result["chapters"] + result["foreshadowings"] + result["chapter_records"]
        result["has_blockers"] = result["total"] > 0
        return result

    @staticmethod
    async def reorder_arcs(volume_id: str, data: ArcReorderV1 | Mapping[str, Any], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """按完整活动兄弟集合重排当前卷的篇章。

        Args:
            volume_id: 父卷 ID。
            data: 全部篇章 ID、版本与目标序号。
            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            按新顺序排列的完整篇章。
        """
        request = data if isinstance(data, ArcReorderV1) else ArcReorderV1.model_validate(data)

        async def reorder(session: AsyncClientSession) -> list[dict[str, Any]]:
            novel, volume = await _load_parents(volume_id, session=session)
            current = await arc_repo.list_arcs(volume_id, session=session)
            ordered = validate_sibling_order(current, request.model_dump()["items"], id_field="arc_id")
            if all(before["order_index"] == order for before, order in ordered):
                return current
            await _update_parents(novel, volume, session=session)
            return await write_sibling_order(arc_repo.collection, ordered, session=session)

        if session is not None:
            return await reorder(session)

        return await run_mongo_write_unit(reorder, "reorder_arcs", require_transaction=True)

    @staticmethod
    async def create_arc(volume_id: str, data: ArcCreateV1 | Mapping[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        """在活动卷末尾创建篇章，同键同内容重试返回原对象。

        Args:
            volume_id: 所属卷 ObjectId 字符串。
            data: 篇章标题、摘要和规划。
            idempotency_key: 当前父卷范围内的创建幂等键。

        Returns:
            新篇章或原请求已经创建的篇章。
        """
        async def create(session: AsyncClientSession) -> dict[str, Any]:
            return await ArcService.create_arc_in_session(volume_id, data, idempotency_key=idempotency_key, session=session)

        return await run_mongo_write_unit(create, "create_arc", require_transaction=True)

    @staticmethod
    async def create_arc_in_session(volume_id: str, data: ArcCreateV1 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession) -> dict[str, Any]:
        """在调用方事务中保存篇章，供人工保存和整批确认共用。

        Args:
            volume_id: 当前操作的正式对象 ID。
            data: 已声明的篇章内容。
            idempotency_key: 本次创建的稳定请求键。
            session: 调用方已经开启的必需事务。
        Returns:
            新建、更新或重放的完整篇章。
        """
        return (await ArcService.create_arcs_in_session(volume_id, [(data, idempotency_key)], session=session))[0]

    @staticmethod
    async def create_arcs_in_session(volume_id: str, arcs: list[tuple[ArcCreateV1 | Mapping[str, Any], str]], *, session: AsyncClientSession) -> list[dict[str, Any]]:
        """在同一事务逐项追加篇章，共同引用只读取和保护一次。

        Args:
            volume_id: 所属卷 ID。
            arcs: 按保存顺序排列的篇章内容及各自稳定创建键。
            session: 调用方已经开启的必需事务。
        Returns:
            按输入顺序返回新篇章或对应创建键的原结果。
        """
        volume_id = str(to_object_id(volume_id))
        documents = []
        created = []
        protected_references: dict[str, set[str]] = {}
        # 保留逐项父级更新：只在实际新增篇章时增加一次父版本和篇章数。
        for data, idempotency_key in arcs:
            fields = (data if isinstance(data, ArcCreateV1) else ArcCreateV1.model_validate(data)).model_dump()
            fingerprint = build_idempotency_fingerprint(idempotency_key, {"volume_id": volume_id, **fields})

            novel, volume = await _load_parents(volume_id, session=session)
            existing = await arc_repo.collection.find_one({"volume_id": volume["_id"], "creation_idempotency_key_hash": fingerprint.key_hash}, session=session)
            replay = resolve_idempotent_replay(existing, fingerprint.request_hash, label="篇章创建")
            if replay is not None:
                documents.append(replay)
                continue
            require_volume_ready(volume)
            # 先写父级版本，再分配卷末序号；失败由同一事务回滚。
            await _update_parents(novel, volume, arcs_delta=1, session=session)
            await _validate_references(fields["planning"], novel["_id"], volume_id=volume["_id"], session=session, protected_references=protected_references)
            last = await arc_repo.collection.find_one({"volume_id": volume["_id"], "is_deleted": False}, {"order_index": 1}, sort=[("order_index", -1)], session=session)
            # BSON 只保存毫秒，首次响应与同键回放保持相同时间值。
            now = get_utc_now().replace(tzinfo=None)
            now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
            document = {
                "_id": ObjectId(), "novel_id": novel["_id"], "volume_id": volume["_id"], **fields,
                "order_index": 1 if last is None else int(last["order_index"]) + 1,
                "scenes_count": 0, "chapter_count": 0, "word_count": 0,
                "version": 1, "is_deleted": False, "deleted_at": None, "created_at": now, "updated_at": now,
                **fingerprint.as_creation_fields(),
            }
            await arc_repo.collection.insert_one(document, session=session)
            documents.append(document)
            created.append(document)
        # 整批插入后相邻篇章才完整；新剧情采用这一批最终规划，回放不重认旧剧情。
        from backend.services.novel.plot_service import stamp_manual_plot
        for document in created:
            if document.get("plot", "").strip():
                fields = {"plot": document["plot"]}
                await stamp_manual_plot(str(document["novel_id"]), "arc", str(document["_id"]), fields, session=session)
                await arc_repo.collection.update_one({"_id": document["_id"]}, {"$set": fields}, session=session)
                document.update(fields)
        return documents


    @staticmethod
    async def get_arc(arc_id: str, *, include_deleted: bool = False, novel_id: str | None = None, session: AsyncClientSession | None = None) -> dict[str, Any]:
        """读取篇章并核对当前活动父链与可选小说范围。

        Args:
            arc_id: 篇章 ObjectId 字符串。
            include_deleted: 是否允许回收站篇章。
            novel_id: 可选小说范围。
            session: 可选事务会话。

        Returns:
            归属正确且父链可用的完整篇章。
        """
        arc = await arc_repo.get_arc(arc_id, include_deleted=include_deleted, session=session)
        if novel_id is not None and arc["novel_id"] != to_object_id(novel_id):
            raise NotFoundError("Vòng truyện không thuộc tiểu thuyết hiện tại")
        novel, _ = await _load_parents(str(arc["volume_id"]), session=session)
        if arc["novel_id"] != novel["_id"]:
            raise NotFoundError("Vòng truyện không thuộc quyển cha hiện tại")
        return arc

    @staticmethod
    async def list_arcs(volume_id: str, *, deleted: bool = False, session: AsyncClientSession | None = None) -> list[dict[str, Any]]:
        """读取活动卷下的篇章或回收站。

        Args:
            volume_id: 所属卷 ObjectId 字符串。
            deleted: 是否只读取回收站。
            session: 可选事务会话。

        Returns:
            按卷内顺序排列的完整篇章列表。
        """
        novel, volume = await _load_parents(volume_id, session=session)
        arcs = await arc_repo.list_arcs(volume_id, deleted=deleted, session=session)
        if any(arc["novel_id"] != novel["_id"] for arc in arcs):
            raise NotFoundError("Vòng truyện không thuộc quyển cha hiện tại")
        current_novel, current_volume = await _load_parents(volume_id, session=session)
        if current_novel["version"] != novel["version"] or current_volume["version"] != volume["version"]:
            raise DomainApiError("ARC_DIRECTORY_CHANGED", "Danh mục vòng truyện đang cập nhật, hãy làm mới rồi thử lại", status_code=409)
        return arcs

    @staticmethod
    async def update_arc(arc_id: str, data: ArcUpdateV1 | Mapping[str, Any]) -> dict[str, Any]:
        """按版本更新明确提供的内容，省略字段保持原值。

        Args:
            arc_id: 目标篇章 ID。
            data: 局部内容和 expected_version。

        Returns:
            更新后的完整篇章。
        """
        async def update(session: AsyncClientSession) -> dict[str, Any]:
            return await ArcService.update_arc_in_session(arc_id, data, session=session)

        return await run_mongo_write_unit(update, "update_arc", require_transaction=True)

    @staticmethod
    async def update_arc_in_session(arc_id: str, data: ArcUpdateV1 | Mapping[str, Any], *, session: AsyncClientSession) -> dict[str, Any]:
        """在调用方事务中保存篇章，供人工保存和整批确认共用。

        Args:
            arc_id: 当前操作的正式对象 ID。
            data: 已声明的篇章内容。
            session: 调用方已经开启的必需事务。
        Returns:
            新建、更新或重放的完整篇章。
        """
        request = data if isinstance(data, ArcUpdateV1) else ArcUpdateV1.model_validate(data)
        fields = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
        # planning 是完整替换；其内部未填写字段仍必须保存默认空值。
        if "planning" in fields:
            fields["planning"] = request.planning.model_dump()
        expected = request.expected_version

        arc = await ArcService.get_arc(arc_id, session=session)
        if arc["version"] != expected:
            raise VersionConflictError("Vòng truyện đã bị thao tác khác sửa đổi, hãy giữ bản thảo, làm mới rồi so sánh")
        novel, volume = await _load_parents(str(arc["volume_id"]), session=session)
        if "plot" in fields:
            from backend.services.novel.plot_service import stamp_manual_plot
            await stamp_manual_plot(str(novel["_id"]), "arc", arc_id, fields, session=session)
        if all(arc.get(name) == value for name, value in fields.items()):
            return arc
        await _update_parents(novel, volume, session=session)
        if "planning" in fields:
            await _validate_references(fields["planning"], novel["_id"], volume_id=volume["_id"], session=session)
        changed = await update_versioned_document(arc_repo.collection, {"_id": arc["_id"], "novel_id": novel["_id"], "volume_id": volume["_id"]}, expected, fields, is_deleted=False, session=session)
        if changed is None:
            raise VersionConflictError("Vòng truyện đã thay đổi khi lưu, hãy thử lại")
        return changed


    @staticmethod
    async def set_deleted(arc_id: str, *, expected_version: int, deleted: bool, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """回收没有下级记录的篇章，或将篇章恢复到卷末。

        Args:
            arc_id: 目标篇章 ID。
            expected_version: 已读取的篇章版本。
            deleted: True 为回收，False 为恢复。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            状态变更后的完整篇章。
        """
        expected = validate_expected_version(expected_version)

        async def change(session: AsyncClientSession) -> dict[str, Any]:
            arc = await ArcService.get_arc(arc_id, include_deleted=True, session=session)
            if arc["version"] != expected:
                raise VersionConflictError("Phiên bản vòng truyện đã thay đổi, hãy làm mới rồi thử lại")
            if arc["is_deleted"] == deleted:
                raise DomainApiError("ARC_STATE_CONFLICT", "Vòng truyện đã ở trạng thái đích, hãy làm mới", status_code=409)
            novel, volume = await _load_parents(str(arc["volume_id"]), session=session)
            if deleted:
                await _check_children(arc, session=session)
            await _update_parents(novel, volume, arcs_delta=-1 if deleted else 1, session=session)
            if not deleted:
                await _validate_references(arc["planning"], novel["_id"], volume_id=volume["_id"], session=session)
            siblings = await arc_repo.list_arcs(str(volume["_id"]), session=session)
            fields = {"is_deleted": deleted, "deleted_at": get_utc_now() if deleted else None}
            if not deleted:
                fields["order_index"] = max((item["order_index"] for item in siblings), default=0) + 1
            changed = await update_versioned_document(arc_repo.collection, {"_id": arc["_id"]}, expected, fields, is_deleted=not deleted, session=session)
            if changed is None:
                raise VersionConflictError("Trạng thái vòng truyện đã thay đổi, hãy làm mới rồi thử lại")
            if deleted:
                for sibling in siblings:
                    if sibling["order_index"] > arc["order_index"]:
                        reordered = await update_versioned_document(arc_repo.collection, {"_id": sibling["_id"]}, sibling["version"], {"order_index": sibling["order_index"] - 1}, is_deleted=False, session=session)
                        if reordered is None:
                            raise VersionConflictError("Thứ tự vòng truyện đã thay đổi, hãy thử lại")
            return changed

        if session is not None:
            return await change(session)

        return await run_mongo_write_unit(change, "change_arc_deleted", require_transaction=True)

    @staticmethod
    async def hard_delete_arc(arc_id: str, *, expected_version: int) -> None:
        """永久删除没有任何下级记录的回收站篇章。

        Args:
            arc_id: 回收站篇章 ID。
            expected_version: 已读取的篇章版本。

        Returns:
            无；有下级或版本冲突时整笔操作不写入。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession) -> None:
            arc = await ArcService.get_arc(arc_id, include_deleted=True, session=session)
            if arc["version"] != expected:
                raise VersionConflictError("Phiên bản vòng truyện đã thay đổi, hãy làm mới rồi thử lại")
            if not arc["is_deleted"]:
                raise DomainApiError("ARC_DELETE_BLOCKED", "Hãy chuyển vòng truyện vào thùng rác trước", status_code=409)
            from backend.services.novel.chapter_record_source import count_chapter_record_references
            records = await count_chapter_record_references(arc["novel_id"], "arc", arc["_id"], session=session)
            if records:
                raise DomainApiError("ARC_CHAPTER_RECORD_DELETE_BLOCKED", "Vòng truyện vẫn là nguồn của bản ghi xác nhận sau chương; nếu cần dọn sạch hoàn toàn, hãy xóa toàn bộ tác phẩm", status_code=409, details={"chapter_records": records})
            novel, volume = await _load_parents(str(arc["volume_id"]), session=session)
            await _check_children(arc, session=session)
            await _update_parents(novel, volume, session=session)
            result = await arc_repo.collection.delete_one({"_id": arc["_id"], "version": expected, "is_deleted": True}, session=session)
            if result.deleted_count != 1:
                raise VersionConflictError("Vòng truyện đã thay đổi trong khi xóa, hãy thử lại")

        await run_mongo_write_unit(delete, "hard_delete_arc", require_transaction=True)
