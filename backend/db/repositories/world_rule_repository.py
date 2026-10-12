"""正式世界规则 MongoDB 仓储。"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as PyMongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import ensure_initial_version


def normalize_world_rule_name(value: str) -> tuple[str, str]:
    """规范化规则显示名并生成小说内活动唯一键。

    Args:
        value: 用户或已确认候选提交的规则名称。

    Returns:
        NFKC 清理后的显示名及其 casefold 唯一键。
    """
    if not isinstance(value, str):
        raise TypeError("规则名称必须是字符串")
    display_name = unicodedata.normalize("NFKC", value).strip()
    if not display_name:
        raise ValueError("规则名称不能为空")
    if len(display_name) > 80:
        raise ValueError("规则名称不能超过 80 个字符")
    return display_name, display_name.casefold()


def normalize_world_rule_category(value: str) -> str:
    """规范化规则分类显示文本。

    Args:
        value: 用户或已确认候选提交的分类。

    Returns:
        NFKC 清理后的非空分类。
    """
    if not isinstance(value, str):
        raise TypeError("规则分类必须是字符串")
    category = unicodedata.normalize("NFKC", value).strip()
    if not category:
        raise ValueError("规则分类不能为空")
    if len(category) > 40:
        raise ValueError("规则分类不能超过 40 个字符")
    return category


class WorldRuleRepository(BaseRepository):
    """封装小说作用域内世界规则的持久化原语。"""

    def __init__(self) -> None:
        """初始化 world_rules 集合仓储。"""
        super().__init__("world_rules")

    async def create_world_rule(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """插入已完成业务校验的新规则并返回完整预镜像。

        Args:
            data: 包含小说 ID、稳定规则 ID 和正式内容的文档。
            session: 可选 MongoDB 会话。

        Returns:
            含 MongoDB ``_id`` 和审计字段的完整新文档。
        """
        prepared = ensure_initial_version(data)
        if not prepared.get("novel_id") or not prepared.get("rule_id"):
            raise ValueError("世界规则缺少 novel_id 或 rule_id")
        if not str(prepared.get("normalized_name") or "").strip():
            raise ValueError("世界规则缺少 normalized_name")

        now = get_utc_now()
        prepared.update(
            {
                "_id": prepared.get("_id") or ObjectId(),
                "novel_id": to_object_id(prepared["novel_id"]),
                "is_deleted": False,
                "deleted_at": None,
                "created_at": prepared.get("created_at") or now,
                "updated_at": prepared.get("updated_at") or now,
            }
        )
        prepared.setdefault("dependency_guard_revision", 0)
        try:
            await self.collection.insert_one(prepared, session=session)
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("世界规则 ID、活动规范名、分类顺序或创建幂等键冲突") from exc
        return prepared

    async def find_by_creation_idempotency(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按小说与幂等键读取首次创建结果。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            同键创建的规则；该键尚未使用时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "creation_idempotency_key_hash": key_hash,
            },
            include_deleted=True,
            session=session,
        )

    async def delete_manual_created_exact(
        self,
        document_id: ObjectId,
        *,
        key_hash: str,
        request_hash: str,
    ) -> bool:
        """精确补偿地点作用域护栏失败前刚创建的世界规则。

        Args:
            document_id: 插入前预分配的 MongoDB ObjectId。
            key_hash: 人工创建幂等键哈希。
            request_hash: 人工创建规范请求哈希。

        Returns:
            规则仍是本次初始镜像并被删除时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": document_id,
                "version": 1,
                "dependency_guard_revision": 0,
                "is_deleted": False,
                "creation_idempotency_key_hash": key_hash,
                "creation_request_hash": request_hash,
            }
        )
        return result.deleted_count == 1

    async def delete_core_batch_exact(
        self,
        novel_id: str,
        rule_ids: list[str],
        *,
        key_hash: str,
        request_hash: str,
    ) -> int:
        """精确补偿当前 standalone 命令创建的核心规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_ids: 本次调用已确认写入成功的规则 ID。
            key_hash: 本批 Idempotency-Key 哈希。
            request_hash: 本批规范请求哈希。

        Returns:
            满足批次、版本与未删除守卫的实际删除数量。
        """
        if not rule_ids:
            return 0
        result = await self.collection.delete_many(
            {
                "novel_id": to_object_id(novel_id),
                "rule_id": {"$in": list(rule_ids)},
                "version": 1,
                "is_deleted": False,
                "core_batch_idempotency_key_hash": key_hash,
                "core_batch_request_hash": request_hash,
            }
        )
        return result.deleted_count

    async def find_active_by_normalized_name(
        self,
        novel_id: str,
        normalized_name: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """查询同小说下具有相同规范名的未删除规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            normalized_name: 已规范化的名称唯一键。
            session: 可选 MongoDB 会话。

        Returns:
            匹配规则；不存在时返回 None。
        """
        return await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "normalized_name": normalized_name,
            },
            session=session,
        )

    async def list_world_rules(
        self,
        novel_id: str,
        *,
        status: str | None = None,
        category: str | None = None,
        scope_type: str | None = None,
        q: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """按小说和可选筛选读取未删除规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            status: 可选规则状态。
            category: 可选精确分类。
            scope_type: 可选作用域类型。
            q: 可选名称、陈述、分类和标签搜索词。
            session: 可选 MongoDB 会话。

        Returns:
            按分类、1-based 顺序和稳定 ID 排列的规则。
        """
        query: dict[str, Any] = {"novel_id": to_object_id(novel_id)}
        if status is not None:
            query["status"] = status
        if category is not None:
            query["category"] = category
        if scope_type is not None:
            query["scope_type"] = scope_type
        if q is not None:
            pattern = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"category": {"$regex": pattern, "$options": "i"}},
                {"statement": {"$regex": pattern, "$options": "i"}},
                {"tags": {"$regex": pattern, "$options": "i"}},
            ]
        return await self.find_many(
            query,
            sort=[("category", 1), ("order_index", 1), ("rule_id", 1)],
            session=session,
        )

    async def list_deleted_world_rules(
        self,
        novel_id: str,
        *,
        category: str | None = None,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取小说回收站中的世界规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            category: 可选精确分类。
            session: 可选 MongoDB 会话。

        Returns:
            按删除时间倒序排列的回收站规则。
        """
        query: dict[str, Any] = {
            "novel_id": to_object_id(novel_id),
            "is_deleted": True,
        }
        if category is not None:
            query["category"] = category
        return await self.find_many(
            query,
            include_deleted=True,
            sort=[("deleted_at", -1), ("rule_id", 1)],
            session=session,
        )

    async def get_world_rule(
        self,
        novel_id: str,
        rule_id: str,
        *,
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按小说作用域和稳定 ID 读取规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            include_deleted: 是否允许返回回收站规则。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的完整 BSON 文档。
        """
        rule = await self.find_one(
            {"novel_id": to_object_id(novel_id), "rule_id": rule_id},
            include_deleted=include_deleted,
            session=session,
        )
        if rule is None:
            raise NotFoundError(f"规则 {rule_id} 不存在于小说 {novel_id}")
        return rule

    async def get_deleted_world_rule(
        self,
        novel_id: str,
        rule_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """读取小说回收站中的指定规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的已删除规则。
        """
        rule = await self.find_one(
            {
                "novel_id": to_object_id(novel_id),
                "rule_id": rule_id,
                "is_deleted": True,
            },
            include_deleted=True,
            session=session,
        )
        if rule is None:
            raise NotFoundError(f"规则 {rule_id} 不存在于小说 {novel_id} 的回收站")
        return rule

    async def get_category_rules(
        self,
        novel_id: str,
        category: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> list[dict[str, Any]]:
        """读取同分类全部未删除规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            category: 规则分类。
            session: 可选 MongoDB 会话。

        Returns:
            按连续顺序和稳定 ID 排列的同分类规则。
        """
        return await self.find_many(
            {"novel_id": to_object_id(novel_id), "category": category},
            sort=[("order_index", 1), ("rule_id", 1)],
            session=session,
        )

    async def get_max_order_index(
        self,
        novel_id: str,
        category: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """读取同分类未删除规则的最大顺序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            category: 规则分类。
            session: 可选 MongoDB 会话。

        Returns:
            当前最大 order_index；分类为空时返回 0。
        """
        rules = await self.find_many(
            {"novel_id": to_object_id(novel_id), "category": category},
            limit=1,
            sort=[("order_index", -1)],
            session=session,
        )
        return int(rules[0]["order_index"]) if rules else 0

    async def update_from_snapshot(
        self,
        snapshot: Mapping[str, Any],
        update_fields: Mapping[str, Any],
        *,
        increment_version: bool,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """按规则预镜像执行精确 CAS 更新。

        Args:
            snapshot: 本次写入前读取的完整规则。
            update_fields: 已由 Service 校验的字段变化。
            increment_version: 本次是否形成一次公开聚合版本。
            session: 可选 MongoDB 会话。

        Returns:
            写后的完整规则；预镜像被并发推进时返回 None。
        """
        identity = {
            "_id": snapshot["_id"],
            "novel_id": snapshot["novel_id"],
            "rule_id": snapshot["rule_id"],
            "version": snapshot["version"],
            "is_deleted": bool(snapshot.get("is_deleted")),
            "category": snapshot["category"],
            "order_index": snapshot["order_index"],
            "dependency_guard_revision": snapshot["dependency_guard_revision"],
        }
        update: dict[str, Any] = {
            "$set": {**update_fields, "updated_at": get_utc_now()}
        }
        if increment_version:
            update["$inc"] = {"version": 1}
        try:
            return await self.collection.find_one_and_update(
                identity,
                update,
                return_document=ReturnDocument.AFTER,
                session=session,
            )
        except PyMongoDuplicateKeyError as exc:
            raise DuplicateKeyError("世界规则活动规范名或分类顺序冲突") from exc

    async def restore_snapshot_exact(
        self,
        snapshot: Mapping[str, Any],
        written_document: Mapping[str, Any],
    ) -> None:
        """仅在文档仍处于本次写后状态时恢复预镜像。

        Args:
            snapshot: 本次写入前的完整文档。
            written_document: 本次写入成功后的完整文档。

        Returns:
            无。
        """
        query = {
            "_id": written_document["_id"],
            "novel_id": written_document["novel_id"],
            "rule_id": written_document["rule_id"],
            "version": written_document["version"],
            "is_deleted": bool(written_document.get("is_deleted")),
            "category": written_document["category"],
            "order_index": written_document["order_index"],
            "dependency_guard_revision": written_document[
                "dependency_guard_revision"
            ],
        }
        try:
            result = await self.collection.replace_one(query, dict(snapshot))
        except PyMongoDuplicateKeyError as exc:
            raise RuntimeError("standalone 世界规则补偿发生唯一键冲突，未覆盖并发数据") from exc
        if result.matched_count != 1:
            raise RuntimeError("standalone 世界规则补偿 CAS 失败，未覆盖并发数据")

    async def hard_delete_world_rule(
        self,
        snapshot: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """按回收站预镜像精确物理删除规则。

        Args:
            snapshot: 已校验的回收站规则预镜像。
            session: 可选 MongoDB 会话。

        Returns:
            精确删除成功时返回 True。
        """
        result = await self.collection.delete_one(
            {
                "_id": snapshot["_id"],
                "novel_id": snapshot["novel_id"],
                "rule_id": snapshot["rule_id"],
                "version": snapshot["version"],
                "dependency_guard_revision": snapshot[
                    "dependency_guard_revision"
                ],
                "is_deleted": True,
            },
            session=session,
        )
        return result.deleted_count == 1

    async def count_protected_references(
        self,
        novel_id: str,
        rule_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, int]:
        """统计规则引用；篇章包含回收站记录，避免恢复后引用失效。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 待永久删除的稳定规则 ID。
            session: 可选 MongoDB 会话。

        Returns:
            各受保护集合及总数的引用统计。
        """
        obj_id = to_object_id(novel_id)
        contracts = {
            "locations": ("applicable_rule_ids", BaseRepository("locations")),
            "arcs": ("planning.rule_ids", BaseRepository("arcs")),
            "scenes": ("planning.rule_ids", BaseRepository("scenes")),
            "foreshadowings": ("rule_ids", BaseRepository("foreshadowings")),
        }
        counts: dict[str, int] = {}
        for label, (field, repository) in contracts.items():
            query: dict[str, Any] = {"novel_id": obj_id, field: rule_id}
            if label == "locations":
                # 公开影响只展示正式地点；永久删除另以不泄露身份的内部查询阻断 pending。
                query["location_order_pending_token"] = None
            counts[label] = await repository.count_documents(
                query,
                include_deleted=label in {"arcs", "scenes"},
                session=session,
            )
        counts["total"] = sum(counts.values())
        return counts

    async def count_pending_location_references(
        self,
        novel_id: str,
        rule_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> int:
        """只判断待提交地点是否正在引用规则，不返回地点身份。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 待永久删除的稳定规则 ID。
            session: 可选 MongoDB 会话。

        Returns:
            当前待提交地点引用数量，仅供内部阻断永久删除。
        """
        return await BaseRepository("locations").count_documents(
            {
                "novel_id": to_object_id(novel_id),
                "applicable_rule_ids": rule_id,
                "location_order_pending_token": {"$type": "string"},
            },
            session=session,
        )


world_rule_repo = WorldRuleRepository()


__all__ = [
    "WorldRuleRepository",
    "normalize_world_rule_category",
    "normalize_world_rule_name",
    "world_rule_repo",
]
