"""全书初始化就绪投影的只读 MongoDB 仓储。"""

from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from backend.db.mongo import get_database
from backend.db.utils import to_object_id


class InitializationReadinessRepository:
    """从正式集合读取一次可重建的全书初始化投影。"""

    async def read_projection(
        self,
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """通过单次聚合读取小说及阶段 1 全部正式事实版本。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 snapshot 事务会话。

        Returns:
            小说不存在或已删除时返回 None；否则返回只含门禁所需字段的投影。
        """
        novel_object_id = to_object_id(novel_id)
        pipeline: list[dict[str, Any]] = [
            {"$match": {"_id": novel_object_id, "is_deleted": {"$ne": True}}},
            {
                "$lookup": {
                    "from": "factions",
                    "let": {"novel_id": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$novel_id", "$$novel_id"]}}},
                        {"$sort": {"faction_id": 1, "_id": 1}},
                        {
                            "$project": {
                                "_id": 0,
                                "faction_id": 1,
                                "version": 1,
                                "level_type": 1,
                                "active_status": 1,
                                "is_deleted": {"$eq": ["$is_deleted", True]},
                            }
                        },
                    ],
                    "as": "factions",
                }
            },
            {
                "$lookup": {
                    "from": "faction_relations",
                    "let": {"novel_id": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$novel_id", "$$novel_id"]}}},
                        {"$sort": {"relation_id": 1, "_id": 1}},
                        {
                            "$project": {
                                "_id": 0,
                                "relation_id": 1,
                                "version": 1,
                                "is_active": 1,
                                "is_deleted": {"$eq": ["$is_deleted", True]},
                            }
                        },
                    ],
                    "as": "faction_relations",
                }
            },
            {
                "$lookup": {
                    "from": "characters",
                    "let": {"novel_id": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$novel_id", "$$novel_id"]}}},
                        {"$sort": {"character_id": 1, "_id": 1}},
                        {
                            "$project": {
                                "_id": 0,
                                "character_id": 1,
                                "version": 1,
                                "role_type": 1,
                                "status": 1,
                                "is_core_character": 1,
                                "is_deleted": {"$eq": ["$is_deleted", True]},
                            }
                        },
                    ],
                    "as": "characters",
                }
            },
            {
                "$lookup": {
                    "from": "character_faction_bindings",
                    "let": {"novel_id": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$novel_id", "$$novel_id"]}}},
                        {"$sort": {"binding_id": 1, "_id": 1}},
                        {
                            "$project": {
                                "_id": 0,
                                "binding_id": 1,
                                "version": 1,
                                "is_active": 1,
                                "is_deleted": {"$eq": ["$is_deleted", True]},
                            }
                        },
                    ],
                    "as": "character_bindings",
                }
            },
            {
                "$lookup": {
                    "from": "character_relations",
                    "let": {"novel_id": "$_id"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$novel_id", "$$novel_id"]}}},
                        {"$sort": {"relation_id": 1, "_id": 1}},
                        {
                            "$project": {
                                "_id": 0,
                                "relation_id": 1,
                                "version": 1,
                                "is_active": 1,
                                "is_deleted": {"$eq": ["$is_deleted", True]},
                            }
                        },
                    ],
                    "as": "character_relations",
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "novel_id": {"$toString": "$_id"},
                    "novel_version": "$version",
                    "factions": 1,
                    "faction_relations": 1,
                    "characters": 1,
                    "character_bindings": 1,
                    "character_relations": 1,
                }
            },
        ]
        cursor = await get_database()["novels"].aggregate(
            pipeline,
            session=session,
            maxTimeMS=5000,
        )
        documents = await cursor.to_list(length=1)
        return documents[0] if documents else None


initialization_readiness_repo = InitializationReadinessRepository()
