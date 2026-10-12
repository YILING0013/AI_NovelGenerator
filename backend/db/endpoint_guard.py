"""依赖创建与主实体生命周期之间的事务写冲突护栏。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pymongo import UpdateOne
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection

from backend.db.errors import DuplicateKeyError


DEPENDENCY_GUARD_FIELD = "dependency_guard_revision"
DEPENDENCY_GUARD_INTEGER_TYPES = ["int", "long"]


@dataclass
class DependencyGuardContribution:
    """记录一次可且仅可回退一次的端点 guard 贡献。"""

    endpoint_id: Any
    rolled_back: bool = False


async def touch_dependency_endpoint_guards(
    collection: AsyncCollection,
    queries: Sequence[dict[str, Any]],
    *,
    session: AsyncClientSession | None,
    rollback_on_error: bool = True,
) -> list[DependencyGuardContribution]:
    """逐端点推进内部 guard，使并发生命周期写产生 CAS 冲突。

    Args:
        collection: 角色或势力主档集合。
        queries: 同时包含身份、版本和当前可用性条件的端点 CAS 查询。
        session: 可选 MongoDB 会话；standalone 写同样必须推进护栏。
        rollback_on_error: 失败时是否减回本次已完成贡献；依赖事实已经先落库时应为 False。

    Returns:
        每个成功 touch 对应的一次性贡献记录。

    Raises:
        DuplicateKeyError: 任一端点已变化，当前依赖写必须回滚或补偿时抛出。
    """
    if session is not None:
        if not queries:
            return []
        # 同一事务合并发送，仍逐条检查原版本和可用条件；任一失配必须整笔回滚。
        result = await collection.bulk_write([
            UpdateOne(
                {
                    **query,
                    DEPENDENCY_GUARD_FIELD: {
                        "$gte": 0,
                        "$type": DEPENDENCY_GUARD_INTEGER_TYPES,
                    },
                },
                {"$inc": {DEPENDENCY_GUARD_FIELD: 1}},
            )
            for query in queries
        ], ordered=True, session=session)
        if result.matched_count != len(queries):
            raise DuplicateKeyError("依赖写入期间端点已被并发修改，请重试")
        return [DependencyGuardContribution(endpoint_id=query["_id"]) for query in queries]

    contributions: list[DependencyGuardContribution] = []
    try:
        for query in queries:
            # 只推进有效贡献计数，避免并发补偿把计数减成负数。
            result = await collection.update_one(
                {
                    **query,
                    DEPENDENCY_GUARD_FIELD: {
                        "$gte": 0,
                        "$type": DEPENDENCY_GUARD_INTEGER_TYPES,
                    },
                },
                {"$inc": {DEPENDENCY_GUARD_FIELD: 1}},
                session=session,
            )
            if result.matched_count != 1:
                raise DuplicateKeyError("依赖写入期间端点已被并发修改，请重试")
            contributions.append(DependencyGuardContribution(endpoint_id=query["_id"]))
    except Exception:
        # standalone 中途失败时逐贡献减回；事务模式由事务整体回滚。
        if session is None and rollback_on_error and contributions:
            await rollback_dependency_endpoint_guards(
                collection,
                contributions,
            )
        raise
    return contributions


async def rollback_dependency_endpoint_guards(
    collection: AsyncCollection,
    touches: Sequence[DependencyGuardContribution],
    *,
    session: AsyncClientSession | None = None,
) -> None:
    """在依赖未落库时逐条原子减回本请求自己的 guard 贡献。

    Args:
        collection: 角色或势力主档集合。
        touches: touch 成功后返回的一次性贡献记录。
        session: 可选 MongoDB 会话。

    Returns:
        无；每条尚未消费的贡献恰好减一。

    Raises:
        RuntimeError: 端点不存在或计数已非正数，无法安全减回时抛出。
    """
    for contribution in reversed(list(touches)):
        if contribution.rolled_back:
            continue
        result = await collection.update_one(
            {
                "_id": contribution.endpoint_id,
                DEPENDENCY_GUARD_FIELD: {
                    "$gte": 1,
                    "$type": DEPENDENCY_GUARD_INTEGER_TYPES,
                },
            },
            {"$inc": {DEPENDENCY_GUARD_FIELD: -1}},
            session=session,
        )
        if result.matched_count != 1:
            raise RuntimeError(
                "依赖写入失败后的 guard 贡献无法安全减回"
            )
        contribution.rolled_back = True
