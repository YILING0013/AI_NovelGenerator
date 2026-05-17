import logging
from typing import Any, Dict, List, Tuple

from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import to_object_id

logger = logging.getLogger(__name__)


class FactionService:
    """
    阵营（Faction）服务层，编排跨集合的业务逻辑。
    纯集合内操作由 FactionRepository 负责，跨集合联动由此处编排。
    """

    @staticmethod
    def _next_business_ids(first_id: str, prefix: str, count: int) -> list[str]:
        """根据首个业务 ID 生成连续 ID 列表。

        Args:
            first_id: 已解析出的首个业务 ID，例如 fac_000001。
            prefix: 业务 ID 前缀，例如 fac 或 fr。
            count: 需要生成的 ID 数量。

        Returns:
            连续业务 ID 列表。
        """
        try:
            start = int(first_id.split("_", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Invalid {prefix} sequence id: {first_id}") from exc
        return [f"{prefix}_{start + offset:06d}" for offset in range(count)]

    @staticmethod
    def _normalize_generated_core_faction(data: Dict[str, Any], *, faction_id: str, sort_order: int) -> Dict[str, Any]:
        """将 AI 生成的核心阵营转换为 factions 集合可写入文档。

        Args:
            data: 单个核心阵营生成结果。
            faction_id: 后端分配的业务阵营 ID。
            sort_order: 阵营排序权重。

        Returns:
            可写入 factions 集合的阵营文档片段。
        """
        payload = dict(data)
        payload["faction_id"] = faction_id
        payload["level_type"] = "core"
        payload["parent_faction_id"] = None
        payload["active_status"] = "active"
        payload["sort_order"] = sort_order
        payload.setdefault("alias", [])
        payload.setdefault("first_appearance_volume_id", None)
        payload.setdefault("first_appearance_chapter_id", None)
        payload.setdefault("extra", {})
        return payload

    @staticmethod
    def _normalize_generated_relation(
        data: Dict[str, Any],
        *,
        relation_id: str,
        name_to_faction_id: Dict[str, str],
    ) -> Dict[str, Any]:
        """将 AI 生成的阵营名称关系映射为 faction_id 关系。

        Args:
            data: 单条 AI 生成关系，使用阵营名称引用端点。
            relation_id: 后端分配的业务关系 ID。
            name_to_faction_id: 阵营名称到业务阵营 ID 的映射。

        Returns:
            可写入 faction_relations 集合的关系文档片段。
        """
        source_name = str(data.get("source_faction_name", "")).strip()
        target_name = str(data.get("target_faction_name", "")).strip()
        if source_name not in name_to_faction_id:
            raise ValueError(f"关系发起方阵营不存在: {source_name}")
        if target_name not in name_to_faction_id:
            raise ValueError(f"关系目标方阵营不存在: {target_name}")

        # AI 阶段用名称便于阅读，落库阶段必须统一转换为稳定业务 ID。
        payload = {
            "relation_id": relation_id,
            "source_faction_id": name_to_faction_id[source_name],
            "target_faction_id": name_to_faction_id[target_name],
            "source_faction_name": source_name,
            "target_faction_name": target_name,
            "relation_type": data.get("relation_type"),
            "current_state": data.get("current_state", ""),
            "core_conflict": data.get("core_conflict", ""),
            "hidden_tension": data.get("hidden_tension", ""),
            "possible_change": data.get("possible_change", ""),
            "intensity": data.get("intensity", 3),
            "is_active": data.get("is_active", True),
        }
        return payload

    @staticmethod
    async def _ensure_unique_active_name(
        novel_id: str,
        level_type: str,
        name: str,
        *,
        exclude_faction_id: str | None = None,
        session=None,
    ) -> None:
        """校验同一小说同一层级下未删除阵营名称不重复。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 阵营层级类型。
            name: 待校验阵营名称。
            exclude_faction_id: 更新时需要排除的当前阵营 ID。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            无。

        Raises:
            DuplicateKeyError: 已存在同名未删除阵营时抛出。
        """
        query: Dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "level_type": level_type,
            "name": name,
        }
        if exclude_faction_id:
            query["faction_id"] = {"$ne": exclude_faction_id}
        existing = await faction_repo.find_one(query, session=session)
        if existing:
            raise DuplicateKeyError(f"同一小说同一势力层级下已存在同名阵营: {name}")

    @staticmethod
    async def has_core_factions_initialized(novel_id: str, *, session=None) -> bool:
        """判断小说是否已经存在核心阵营初始化记录。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            存在未删除或已软删除核心阵营时返回 True。
        """
        count = await faction_repo.count_factions_by_level_type(
            novel_id,
            "core",
            include_deleted=True,
            session=session,
        )
        return count > 0

    @staticmethod
    async def create_faction(novel_id: str, data: Dict[str, Any]) -> Tuple[str, str]:
        """创建新阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 阵营基础字段，不包含 novel_id。

        Returns:
            (MongoDB ObjectId 字符串, 业务 faction_id)。
        """
        requested_faction_id = data.get("faction_id")

        async def _create(session):
            """在同一个写入单元内校验小说、生成业务 ID 并插入阵营。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            payload = dict(data)
            payload["name"] = str(payload.get("name", "")).strip()
            payload["level_type"] = str(payload.get("level_type") or "core").strip() or "core"
            await FactionService._ensure_unique_active_name(
                novel_id,
                payload["level_type"],
                payload["name"],
                session=session,
            )
            payload["novel_id"] = novel_id
            if not requested_faction_id:
                payload["faction_id"] = await faction_repo._get_next_faction_id(novel_id, session=session)
            if "sort_order" not in payload:
                # 手动创建不限制核心阵营数量，但仍按当前层级尾部追加，保证列表稳定可读。
                sibling_count = await faction_repo.count_factions_by_level_type(
                    novel_id,
                    payload["level_type"],
                    session=session,
                )
                payload["sort_order"] = (sibling_count + 1) * 10
            faction_oid = await faction_repo.create_faction(payload, session=session)
            return faction_oid, payload["faction_id"]

        try:
            return await run_mongo_write_unit(_create, "create_faction")
        except DuplicateKeyError:
            if requested_faction_id:
                raise
            # 自动编号遇并发冲突时重新读取 active 最大编号并重试一次。
            return await run_mongo_write_unit(_create, "create_faction_retry")

    @staticmethod
    async def bulk_create_core_factions_with_relations(
        novel_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """批量创建全书核心阵营及其阵营关系。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 包含 core_factions 与 faction_relations 的生成结果。

        Returns:
            已创建的阵营和阵营关系文档列表。
        """
        core_factions = list(data.get("core_factions") or [])
        faction_relations = list(data.get("faction_relations") or [])
        if len(core_factions) < 2 or len(core_factions) > 6:
            raise ValueError("核心阵营数量必须为 2 到 6 个")

        incoming_names = [str(item.get("name", "")).strip() for item in core_factions]
        if len(incoming_names) != len(set(incoming_names)):
            raise ValueError("核心阵营名称不能重复")

        async def _create(session):
            """在同一个写入单元内保存核心阵营，并把关系名称映射为业务 ID。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            if await FactionService.has_core_factions_initialized(novel_id, session=session):
                raise DuplicateKeyError("核心阵营已初始化，请改用手动新增或先清空核心势力与垃圾桶")
            existing_core_factions = await faction_repo.get_factions_by_level_type(
                novel_id,
                "core",
                session=session,
            )
            if len(existing_core_factions) + len(core_factions) > 6:
                raise ValueError("同一小说下核心阵营总数不能超过 6 个")

            existing_names = {str(item.get("name", "")).strip() for item in existing_core_factions}
            duplicated_names = sorted(name for name in incoming_names if name in existing_names)
            if duplicated_names:
                raise ValueError(f"同一小说下已存在同名核心阵营: {', '.join(duplicated_names)}")

            first_faction_id = await faction_repo._get_next_faction_id(novel_id, session=session)
            faction_ids = FactionService._next_business_ids(first_faction_id, "fac", len(core_factions))
            name_to_faction_id = {
                faction["name"]: faction_id
                for faction, faction_id in zip(core_factions, faction_ids)
            }

            created_factions: list[Dict[str, Any]] = []
            for index, (faction, faction_id) in enumerate(zip(core_factions, faction_ids), start=1):
                payload = FactionService._normalize_generated_core_faction(
                    faction,
                    faction_id=faction_id,
                    sort_order=(len(existing_core_factions) + index) * 10,
                )
                payload["novel_id"] = novel_id
                await faction_repo.create_faction(payload, session=session)
                created_factions.append(await faction_repo.get_faction(novel_id, faction_id, session=session))

            first_relation_id = await faction_relation_repo._get_next_relation_id(novel_id, session=session)
            relation_ids = FactionService._next_business_ids(first_relation_id, "fr", len(faction_relations))
            created_relations: list[Dict[str, Any]] = []
            for relation, relation_id in zip(faction_relations, relation_ids):
                payload = FactionService._normalize_generated_relation(
                    relation,
                    relation_id=relation_id,
                    name_to_faction_id=name_to_faction_id,
                )
                payload["novel_id"] = novel_id
                await faction_relation_repo.create_relation(payload, session=session)
                created_relations.append(
                    await faction_relation_repo.get_relation(novel_id, relation_id, session=session)
                )

            return {
                "factions": created_factions,
                "faction_relations": created_relations,
            }

        return await run_mongo_write_unit(_create, "bulk_create_core_factions_with_relations")

    @staticmethod
    async def get_factions_by_novel(novel_id: str) -> List[Dict[str, Any]]:
        """获取指定小说下所有阵营列表。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_factions_by_novel(novel_id)

    @staticmethod
    async def get_faction(novel_id: str, faction_id: str) -> Dict[str, Any]:
        """获取指定小说下的单个阵营详情。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            阵营文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_faction(novel_id, faction_id)

    @staticmethod
    async def get_factions_by_level_type(novel_id: str, level_type: str) -> List[Dict[str, Any]]:
        """获取指定小说下特定层级类型的阵营列表。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 阵营层级类型。

        Returns:
            阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_factions_by_level_type(novel_id, level_type)

    @staticmethod
    async def get_deleted_factions_by_level_type(
        novel_id: str,
        level_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        """获取指定小说下已软删除阵营列表，可按层级过滤。

        Args:
            novel_id: 小说 ObjectId 字符串。
            level_type: 可选阵营层级类型。

        Returns:
            已软删除阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_deleted_factions_by_level_type(novel_id, level_type)

    @staticmethod
    async def get_child_factions(novel_id: str, parent_faction_id: str) -> List[Dict[str, Any]]:
        """获取指定父级阵营的所有直接子阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_faction_id: 父级业务阵营 ID。

        Returns:
            子阵营文档列表。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await faction_repo.get_child_factions(novel_id, parent_faction_id)

    @staticmethod
    async def update_faction_info(novel_id: str, faction_id: str, update_data: Dict[str, Any]) -> bool:
        """更新阵营基础信息。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。
            update_data: 待更新字段。

        Returns:
            实际修改成功时返回 True。
        """
        async def _update(session):
            """在同一个写入单元内更新阵营，并维护关系冗余显示名。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            current = await faction_repo.get_faction(novel_id, faction_id, session=session)
            next_data = dict(update_data)
            next_name = str(next_data.get("name", current.get("name", ""))).strip()
            next_level_type = str(next_data.get("level_type", current.get("level_type") or "core")).strip() or "core"
            if "name" in next_data:
                next_data["name"] = next_name
            if "level_type" in next_data:
                next_data["level_type"] = next_level_type
            if next_name:
                await FactionService._ensure_unique_active_name(
                    novel_id,
                    next_level_type,
                    next_name,
                    exclude_faction_id=faction_id,
                    session=session,
                )

            success = await faction_repo.update_faction_info(novel_id, faction_id, next_data, session=session)
            if success and "name" in next_data and next_name != current.get("name"):
                await faction_relation_repo.update_faction_name_references(
                    novel_id,
                    faction_id,
                    next_name,
                    session=session,
                )
            return success

        return await run_mongo_write_unit(_update, "update_faction_info")

    @staticmethod
    async def batch_update_sort_order(novel_id: str, sort_map: Dict[str, int]) -> int:
        """批量更新阵营排序权重。

        Args:
            novel_id: 小说 ObjectId 字符串。
            sort_map: {faction_id: new_sort_order} 映射。

        Returns:
            被实际修改的阵营数量。
        """
        async def _update(session):
            """在同一个写入单元内批量更新同一小说下的阵营排序。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            return await faction_repo.batch_update_sort_order(novel_id, sort_map, session=session)

        return await run_mongo_write_unit(_update, "batch_update_faction_sort_order")

    @staticmethod
    async def soft_delete_faction(novel_id: str, faction_id: str) -> bool:
        """软删除阵营，并解除同小说下子阵营挂靠。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            实际软删除成功时返回 True。
        """
        async def _delete(session):
            """在同一个写入单元内按作用域软删除阵营。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            success = await faction_repo.soft_delete_faction(novel_id, faction_id, session=session)
            if success:
                await faction_relation_repo.deactivate_relations_for_faction_delete(
                    novel_id,
                    faction_id,
                    session=session,
                )
                logger.info(f"软删除阵营 {faction_id} 完成")
            return success

        return await run_mongo_write_unit(_delete, "soft_delete_faction")

    @staticmethod
    async def restore_faction(novel_id: str, faction_id: str) -> bool:
        """恢复已软删除的阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            实际恢复成功时返回 True。
        """
        async def _restore(session):
            """在同一个写入单元内按作用域恢复阵营。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            deleted_faction = await faction_repo.get_deleted_faction(novel_id, faction_id, session=session)
            await FactionService._ensure_unique_active_name(
                novel_id,
                str(deleted_faction.get("level_type") or "core"),
                str(deleted_faction.get("name", "")).strip(),
                session=session,
            )
            success = await faction_repo.restore_faction(novel_id, faction_id, session=session)
            if success:
                await faction_relation_repo.restore_relations_for_faction(
                    novel_id,
                    faction_id,
                    session=session,
                )
                logger.info(f"恢复阵营 {faction_id} 完成")
            return success

        return await run_mongo_write_unit(_restore, "restore_faction")

    @staticmethod
    async def hard_delete_faction(novel_id: str, faction_id: str) -> Dict[str, Any]:
        """物理删除已软删除的阵营。

        Args:
            novel_id: 小说 ObjectId 字符串。
            faction_id: 业务层阵营 ID。

        Returns:
            删除统计。
        """
        async def _delete(session):
            """在同一个写入单元内按作用域物理删除阵营。"""
            await novel_repo.get_novel_by_id(novel_id, session=session)
            try:
                deleted_faction = await faction_repo.get_deleted_faction(novel_id, faction_id, session=session)
            except NotFoundError:
                active_exists = await faction_repo.exists(
                    {"novel_id": to_object_id(novel_id), "faction_id": faction_id},
                    session=session,
                )
                if active_exists:
                    raise ValueError("Only soft-deleted factions can be permanently deleted")
                raise
            active_exists = await faction_repo.exists(
                {"novel_id": deleted_faction["novel_id"], "faction_id": faction_id},
                session=session,
            )
            if active_exists:
                children_count = 0
                relations_deleted = 0
            else:
                children = await faction_repo.find_many(
                    {"novel_id": deleted_faction["novel_id"], "parent_faction_id": faction_id},
                    include_deleted=False,
                    session=session,
                )
                children_count = len(children)
                relations_deleted = await faction_relation_repo.hard_delete_relations_by_faction(
                    novel_id,
                    faction_id,
                    session=session,
                )
            deleted = await faction_repo.hard_delete_faction(novel_id, faction_id, session=session)
            stats = {
                "faction_deleted": 1 if deleted else 0,
                "children_unlinked": children_count,
                "relations_deleted": relations_deleted,
            }
            logger.info(f"硬删除阵营 {faction_id} 完成: {stats}")
            return stats

        return await run_mongo_write_unit(_delete, "hard_delete_faction")
