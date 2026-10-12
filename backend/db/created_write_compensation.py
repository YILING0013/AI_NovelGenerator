"""standalone 批量创建失败时的并发安全补偿工具。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection

from backend.db.endpoint_guard import DEPENDENCY_GUARD_INTEGER_TYPES

async def delete_created_documents_cas(
    collection: AsyncCollection,
    documents: Sequence[Mapping[str, Any]],
    *,
    business_key_field: str,
    expected_dependency_guard_revision: int | None = None,
    session: AsyncClientSession | None = None,
) -> int:
    """逐文档删除仍停留在创建版本的本批记录。

    Args:
        collection: 保存本批新建文档的 MongoDB 集合。
        documents: 带 ``_id``、``novel_id``、业务键和创建版本的本批文档。
        business_key_field: 当前集合稳定业务 ID 的字段名。
        expected_dependency_guard_revision: 端点集合需匹配的内部贡献计数；普通依赖文档传 None。
        session: 可选 MongoDB 会话。

    Returns:
        实际删除的本批创建文档数量。

    Raises:
        RuntimeError: 文档缺少补偿身份，或任一命中文档已被并发推进而无法安全删除。
    """
    deleted_count = 0
    incomplete: list[str] = []
    if expected_dependency_guard_revision is not None and (
        isinstance(expected_dependency_guard_revision, bool)
        or not isinstance(expected_dependency_guard_revision, int)
        or expected_dependency_guard_revision < 0
    ):
        raise ValueError("expected_dependency_guard_revision 必须为非负整数或 None")
    for document in documents:
        missing = [
            field
            for field in ("_id", "novel_id", business_key_field)
            if document.get(field) is None
        ]
        if missing:
            raise RuntimeError(
                "standalone 创建补偿缺少精确身份字段: " + ", ".join(missing)
            )

        business_id = document[business_key_field]
        guard_query = (
            {
                "dependency_guard_revision": {
                    "$eq": expected_dependency_guard_revision,
                    "$type": DEPENDENCY_GUARD_INTEGER_TYPES,
                }
            }
            if expected_dependency_guard_revision is not None
            else {}
        )
        # 端点补偿同时锁定贡献计数 0；存在任何存活依赖时都拒绝删除。
        result = await collection.delete_one(
            {
                "_id": document["_id"],
                "novel_id": document["novel_id"],
                business_key_field: business_id,
                "version": {"$eq": 1, "$type": "number"},
                **guard_query,
            },
            session=session,
        )
        if result.deleted_count == 1:
            deleted_count += 1
            continue

        current = await collection.find_one(
            {"_id": document["_id"]},
            projection={
                "_id": 1,
                "novel_id": 1,
                business_key_field: 1,
                "version": 1,
                "dependency_guard_revision": 1,
            },
            session=session,
        )
        if current is not None:
            incomplete.append(
                f"_id={document['_id']}, {business_key_field}={business_id!r}, "
                f"actual_version={current.get('version')!r}, "
                "dependency_guard_revision="
                f"{current.get('dependency_guard_revision')!r}"
            )

    if incomplete:
        raise RuntimeError(
            "standalone 创建补偿 CAS 未完成：本批文档已被并发修改，未执行删除；"
            + "; ".join(incomplete)
        )
    return deleted_count
