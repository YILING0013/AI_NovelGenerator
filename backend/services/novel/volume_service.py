"""卷正式聚合、排序、生命周期与批量规划确认服务。"""

from __future__ import annotations

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any

from bson import ObjectId
from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_command_receipt_repository import (
    volume_command_receipt_repo,
)
from backend.db.repositories.volume_repository import volume_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    validate_expected_version,
)
from backend.llm.schemas.volume_planning_pydantic import (
    VOLUME_SKELETON_RESULT_SCHEMA_ID,
    VOLUME_SKELETON_RESULT_SCHEMA_VERSION,
    VolumeLaunchBasisV1,
    VolumeLaunchConfirmV1,
    VolumeSkeletonBasisV1,
    normalize_volume_text,
)
from backend.services.llm.volume_planning_context import load_volume_planning_context
from backend.services.llm.volume_planning_contract import (
    VOLUME_SKELETON_STEP,
    VOLUME_SKELETON_WORKFLOW,
    compute_volume_launch_input_fingerprint,
    compute_volume_skeleton_input_fingerprint,
    validate_volume_skeleton_candidate_set,
)
from backend.services.novel.character_volume_state_service import (
    CharacterVolumeStateService,
    StateSourceCompensationError,
    acquire_state_write_lock,
    compensate_state_changes,
    release_state_write_lock,
)
from backend.services.novel.faction_volume_state_service import (
    FactionStateSourceCompensationError,
    FactionVolumeStateService,
    compensate_state_changes as compensate_faction_state_changes,
)

VOLUME_STATUSES = frozenset({"draft", "planned", "active", "completed", "archived"})
VOLUME_SKELETON_SCHEMA_ID = VOLUME_SKELETON_RESULT_SCHEMA_ID
VOLUME_SKELETON_SCHEMA_VERSION = VOLUME_SKELETON_RESULT_SCHEMA_VERSION


def _plain_dict(value: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    """把严格 DTO 或映射转换为不共享引用的普通字典。

    Args:
        value: Pydantic 模型或映射。
        exclude_unset: 对 Pydantic 模型是否排除未显式字段。

    Returns:
        可供领域流程修改的独立字典。
    """
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_unset=exclude_unset)
    return deepcopy(dict(value))


def _volume_error(
    code: str,
    message: str,
    *,
    status_code: int = 422,
    details: Mapping[str, Any] | None = None,
) -> DomainApiError:
    """构造带稳定代码的卷领域错误。

    Args:
        code: 稳定业务错误码。
        message: 面向用户的错误说明。
        status_code: HTTP 状态码，默认为请求字段错误 422。
        details: 可选的结构化冲突或影响详情。

    Returns:
        可交给公共错误协议的 DomainApiError。
    """
    return DomainApiError(
        code,
        message,
        status_code=status_code,
        details=details,
    )


def _normalize_volume_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """清理卷正式字段并拒绝 Service 绕过 DTO 的明显非法值。

    Args:
        payload: 创建、人工更新或候选确认字段。

    Returns:
        只包含卷可编辑字段的规范字典。
    """
    allowed = {
        "title",
        "subtitle",
        "summary",
        "goal",
        "theme",
        "status",
        "planning",
        "plot",
        "order_index",
    }
    fields = {key: deepcopy(value) for key, value in payload.items() if key in allowed}
    for name in ("title", "subtitle", "summary", "goal", "theme"):
        if name in fields:
            if not isinstance(fields[name], str):
                raise _volume_error("VOLUME_FIELD_INVALID", f"{name} 必须是字符串")
            fields[name] = fields[name].strip()
    if "title" in fields and not fields["title"]:
        raise _volume_error("VOLUME_TITLE_REQUIRED", "卷标题不能为空")
    if "plot" in fields and (not isinstance(fields["plot"], str) or len(fields["plot"]) > 40000):
        raise _volume_error("VOLUME_PLOT_INVALID", "详细剧情必须是 40000 字以内的文字")
    if "status" in fields and fields["status"] not in VOLUME_STATUSES:
        raise _volume_error("VOLUME_STATUS_INVALID", "卷状态不合法")
    if "order_index" in fields:
        order = fields["order_index"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise _volume_error("VOLUME_ORDER_INVALID", "卷序号必须为 1-based 正整数")
    return fields


def _receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """复制不可变收据中的原始命令结果。

    Args:
        receipt: 已按小说和幂等键命中的成功收据。

    Returns:
        不与收据 BSON 共享引用的映射和卷快照。
    """
    return {
        "candidate_ref_map": deepcopy(receipt.get("candidate_ref_map") or {}),
        "volumes": deepcopy(receipt.get("volumes") or []),
    }


def _mongo_write_time() -> datetime:
    """生成可经 BSON 毫秒精度往返后精确比较的 UTC 时间。

    Args:
        无。

    Returns:
        已截断到毫秒且与 MongoDB 默认解码一致的 UTC datetime。
    """
    now = get_utc_now()
    return now.replace(
        tzinfo=None,
        microsecond=(now.microsecond // 1000) * 1000,
    )


async def _compensate_volume_changes(
    changes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> None:
    """以两阶段安全序号精确恢复 standalone 卷镜像。

    Args:
        changes: 当前命令的卷写前/写后镜像序列。

    Returns:
        无；任一步未精确恢复时显式抛出 503。
    """
    if not changes:
        return
    latest: dict[Any, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for before, after in changes:
        latest[before["_id"]] = (before, after)
    minimum = await volume_repo.collection.find_one(
        {},
        projection={"order_index": 1},
        sort=[("order_index", 1)],
    )
    lowest = int(minimum["order_index"]) if minimum is not None else 0
    temporary_start = min(-1_000_000, lowest - len(latest) - 1)
    temporary_changes: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    # 先把本命令所有写后镜像移到互不冲突的临时序号，避免交换恢复碰唯一索引。
    for offset, (before, after) in enumerate(latest.values()):
        temporary_order = temporary_start - offset
        write_time = _mongo_write_time()
        try:
            temporary = await volume_repo.update_from_snapshot(
                after,
                {"order_index": temporary_order},
                increment_version=False,
                write_time=write_time,
            )
        except Exception:
            current = await volume_repo.get_volume_by_id(
                str(after["_id"]),
                include_deleted=True,
            )
            temporary = (
                current
                if int(current["version"]) == int(after["version"])
                and int(current["order_index"]) == temporary_order
                and current.get("updated_at") == write_time
                else None
            )
        if temporary is None:
            raise _volume_error(
                "VOLUME_COMPENSATION_FAILED",
                "卷写入失败，且安全序号补偿未完整完成",
                status_code=503,
            )
        temporary_changes.append((before, temporary))
    for before, temporary in reversed(temporary_changes):
        try:
            restored = await volume_repo.restore_snapshot(temporary, before)
        except Exception:
            current = await volume_repo.get_volume_by_id(
                str(before["_id"]),
                include_deleted=True,
            )
            restored = current == dict(before)
        if not restored:
            raise _volume_error(
                "VOLUME_COMPENSATION_FAILED",
                "卷写入失败，且数据库补偿未完整完成",
                status_code=503,
            )


async def _restore_novel_snapshot(
    before: Mapping[str, Any],
    after: Mapping[str, Any] | None,
) -> None:
    """精确恢复当前卷命令更新过的小说统计与版本。

    Args:
        before: 当前命令抢占父级前的小说镜像。
        after: 父级 CAS 写后镜像；未写入时为 None。

    Returns:
        无；精确补偿未完成时显式抛出 503。
    """
    if after is None:
        return
    try:
        restored = await novel_repo.restore_snapshot_exact(before, after)
    except Exception:
        current = await novel_repo.get_novel_by_id(
            str(before["_id"]),
            include_deleted=True,
        )
        restored = all(
            current.get(field) == before.get(field)
            for field in (
                "version",
                "current_volume_count",
                "current_chapter_count",
                "current_word_count",
                "updated_at",
            )
        )
    if not restored:
        raise _volume_error(
            "VOLUME_COMPENSATION_FAILED",
            "卷写入失败，且小说统计补偿未完整完成",
            status_code=503,
        )


async def _update_novel_from_snapshot(
    snapshot: Mapping[str, Any],
    deltas: Mapping[str, int],
    *,
    session: Any,
    conflict_message: str,
) -> dict[str, Any]:
    """执行父级统计 CAS，并在 standalone 未知确认时核对精确写后镜像。

    Args:
        snapshot: 当前写入单元开始时的小说镜像。
        deltas: 卷数、章数或字数的精确增量。
        session: 可选 MongoDB 事务会话。
        conflict_message: 父级 CAS 未命中时的业务说明。

    Returns:
        父级 CAS 的精确写后小说镜像。
    """
    write_time = _mongo_write_time()
    try:
        updated = await novel_repo.update_stats_from_snapshot(
            snapshot,
            deltas,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is None:
            current = await novel_repo.get_novel_by_id(str(snapshot["_id"]))
            expected_stats = {
                field: int(snapshot.get(field, 0)) + int(deltas.get(field, 0))
                for field in (
                    "current_volume_count",
                    "current_chapter_count",
                    "current_word_count",
                )
            }
            if (
                int(current.get("version", 0)) == int(snapshot["version"]) + 1
                and current.get("updated_at") == write_time
                and all(int(current.get(field, 0)) == value for field, value in expected_stats.items())
            ):
                return current
        raise
    if updated is None:
        raise _volume_error(
            "VOLUME_PARENT_CONFLICT",
            conflict_message,
            status_code=409,
        )
    return updated


async def _remove_created_volumes(document_ids: Sequence[Any]) -> None:
    """删除当前命令预分配的卷 ID，并以最终不存在证明补偿完整。

    Args:
        document_ids: 当前命令在发起 insert 前预分配的 ObjectId。

    Returns:
        无；任一目标仍存在时显式抛出 503。
    """
    if not document_ids:
        return
    try:
        await volume_repo.hard_delete_created_batch(document_ids)
    except Exception:
        # 删除成功后网络中断时仍以这些预分配 ID 最终不存在作为精确补偿证据。
        pass
    remaining = await volume_repo.collection.count_documents(
        {"_id": {"$in": list(document_ids)}}
    )
    if remaining:
        raise _volume_error(
            "VOLUME_COMPENSATION_FAILED",
            "卷写入失败，且新卷补偿未完整完成",
            status_code=503,
        )


async def _apply_volume_change(
    snapshot: Mapping[str, Any],
    fields: Mapping[str, Any],
    *,
    increment_version: bool,
    changes: list[tuple[dict[str, Any], dict[str, Any]]],
    session: Any,
    conflict_message: str,
    compensation_before: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """执行卷 CAS，并在 standalone 未知确认时重读精确写后字段。

    Args:
        snapshot: 卷写入前的完整镜像。
        fields: 当前命令要更新的精确字段。
        increment_version: 该步是否递增唯一公开版本。
        changes: 用于 standalone 补偿的当前命令写集。
        session: 可选 MongoDB 事务会话。
        conflict_message: CAS 未命中时的业务说明。
        compensation_before: 多阶段写时对应的原始补偿镜像。

    Returns:
        精确写后卷镜像。
    """
    write_time = _mongo_write_time()
    try:
        updated = await volume_repo.update_from_snapshot(
            snapshot,
            fields,
            increment_version=increment_version,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is None:
            current = await volume_repo.get_volume_by_id(
                str(snapshot["_id"]),
                include_deleted=True,
            )
            expected_version = int(snapshot["version"]) + int(increment_version)
            if (
                int(current["version"]) == expected_version
                and current.get("updated_at") == write_time
                and all(current.get(field) == value for field, value in fields.items())
            ):
                updated = current
            else:
                raise
        else:
            raise
    if updated is None:
        raise _volume_error(
            "VOLUME_VERSION_CONFLICT",
            conflict_message,
            status_code=409,
        )
    before = dict(compensation_before or snapshot)
    after = dict(updated)
    changes.append((before, after))
    return after


async def _load_volume_skeleton_context_versions(
    novel_id: str,
    *,
    session: Any,
) -> dict[tuple[str, str], int]:
    """重建卷骨架生成所读取的完整活动事实版本集。

    Args:
        novel_id: 当前小说 ObjectId 字符串。
        session: 当前 MongoDB 写入单元会话。

    Returns:
        以资源类型和稳定 ID 为键的完整版本集。
    """
    context = await load_volume_planning_context(
        novel_id,
        session=session,
    )
    return {
        (source.resource_type, source.id): int(source.version)
        for source in context["source_refs"]
    }


class VolumeService:
    """以直接数据流实现卷唯一事实源的正式写入。"""

    @staticmethod
    async def _load_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
        *,
        session: Any = None,
    ) -> dict[str, Any] | None:
        """读取并验证不可变卷命令收据。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始幂等键的 SHA-256。
            request_hash: 当前规范命令载荷的摘要。
            session: 可选 MongoDB 事务会话。

        Returns:
            同键同载荷的成功收据；键未使用时返回 None。
        """
        receipt = await volume_command_receipt_repo.find_receipt(
            novel_id,
            key_hash,
            session=session,
        )
        if receipt is None:
            return None
        if receipt.get("request_hash") != request_hash:
            raise _volume_error(
                "IDEMPOTENCY_KEY_REUSED",
                "同一 Idempotency-Key 已用于不同的卷命令",
                status_code=409,
            )
        return receipt

    @staticmethod
    async def _wait_for_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        """仅在同键并发窗口内短暂等待不可变成功收据。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始幂等键的 SHA-256。
            request_hash: 当前规范命令载荷的摘要。

        Returns:
            一秒内可见的同请求成功收据；超时返回 None。
        """
        for _ in range(20):
            receipt = await VolumeService._load_receipt(
                novel_id,
                key_hash,
                request_hash,
            )
            if receipt is not None:
                return receipt
            await asyncio.sleep(0.05)
        return None

    @staticmethod
    async def _get_versioned_volume(
        volume_id: str,
        expected_version: int,
        *,
        deleted: bool,
        novel_id: str | None = None,
        session: Any = None,
    ) -> dict[str, Any]:
        """读取指定生命周期卷并验证小说归属和公开版本。

        Args:
            volume_id: 卷 ObjectId 字符串。
            expected_version: 请求基于的唯一公开版本。
            deleted: 当前命令要求的软删除状态。
            novel_id: 可选的小说作用域。
            session: 可选 MongoDB 事务会话。

        Returns:
            生命周期、归属和版本都一致的完整卷镜像。
        """
        expected = validate_expected_version(expected_version)
        volume = await volume_repo.get_volume_by_id(
            volume_id,
            include_deleted=True,
            session=session,
        )
        if bool(volume.get("is_deleted")) is not deleted:
            raise NotFoundError(f"卷 {volume_id} 不存在于当前生命周期视图")
        if novel_id is not None and str(volume["novel_id"]) != novel_id:
            raise NotFoundError(f"卷 {volume_id} 不属于小说 {novel_id}")
        current = int(volume["version"])
        if current != expected:
            raise _volume_error(
                "VOLUME_VERSION_CONFLICT",
                f"卷版本冲突：当前版本为 {current}，请求版本为 {expected}",
                status_code=409,
                details={"expected_version": expected, "actual_version": current},
            )
        return volume

    @staticmethod
    async def create_volume(data: Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """幂等创建一卷并保持小说活动卷统计一致。

        Args:
            data: 含 novel_id 和卷人工字段的严格请求。
            idempotency_key: 创建命令必填幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新建或同键重放的原始完整卷文档。
        """
        payload = _plain_dict(data)
        novel_id = str(payload.pop("novel_id", ""))
        if not novel_id:
            raise _volume_error("NOVEL_ID_REQUIRED", "novel_id 不能为空")
        # 未指定位置时追加到活动卷末尾。
        if payload.get("order_index") is None:
            payload.pop("order_index", None)
        fields = _normalize_volume_fields(payload)
        fields.setdefault("subtitle", "")
        fields.setdefault("summary", "")
        fields.setdefault("goal", "")
        fields.setdefault("theme", "")
        fields.setdefault("status", "draft")
        fields.setdefault("planning", None)
        fingerprint = build_idempotency_fingerprint(
            idempotency_key,
            {"operation": "create", "novel_id": novel_id, "volume": fields},
        )

        replay = (await VolumeService._load_receipt(
            novel_id,
            fingerprint.key_hash,
            fingerprint.request_hash,
        )) if session is None else None
        if replay is not None:
            return _receipt_result(replay)["volumes"][0]

        async def create(session: Any) -> dict[str, Any]:
            novel_snapshot = await novel_repo.get_novel_by_id(
                novel_id,
                session=session,
            )
            replay_in_unit = await VolumeService._load_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
                session=session,
            )
            if replay_in_unit is not None:
                return _receipt_result(replay_in_unit)["volumes"][0]

            order_index = fields.get("order_index")
            next_order_index = await volume_repo.get_next_order_index(
                novel_id,
                session=session,
            )
            if order_index is None:
                order_index = next_order_index
            elif order_index != next_order_index:
                raise _volume_error(
                    "VOLUME_ORDER_INVALID",
                    "人工创建只能连续追加到当前活动卷末尾",
                )
            attempted_id = ObjectId()
            created: dict[str, Any] | None = None
            novel_after: dict[str, Any] | None = None
            receipt_attempted = False
            try:
                # 小说 CAS 先取得本书卷命令权，败方不会触碰任何卷序号或统计。
                novel_after = await _update_novel_from_snapshot(
                    novel_snapshot,
                    {"current_volume_count": 1},
                    session=session,
                    conflict_message="小说在卷创建期间已发生变化",
                )
                created = await volume_repo.create_volume(
                    {
                        **fields,
                        "_id": attempted_id,
                        "novel_id": novel_id,
                        "order_index": order_index,
                    },
                    session=session,
                )
                receipt_attempted = True
                await volume_command_receipt_repo.create_receipt(
                    {
                        "novel_id": novel_id,
                        "idempotency_key_hash": fingerprint.key_hash,
                        "request_hash": fingerprint.request_hash,
                        "operation": "create",
                        "candidate_ref_map": {},
                        "volumes": [deepcopy(created)],
                    },
                    session=session,
                )
                return created
            except Exception as exc:
                if session is None:
                    if receipt_attempted:
                        published = await volume_command_receipt_repo.find_receipt(
                            novel_id,
                            fingerprint.key_hash,
                        )
                        if published is not None and published.get("request_hash") == fingerprint.request_hash:
                            published_volume = _receipt_result(published)["volumes"][0]
                            if str(published_volume.get("_id")) == str(attempted_id):
                                # 收据是最后一步；自己的结果可见即表示此前父级 CAS 已成功。
                                return published_volume
                            # 同键竞争者先发布时，撤销本请求额外创建的卷和父级统计。
                            await _remove_created_volumes([attempted_id])
                            await _restore_novel_snapshot(novel_snapshot, novel_after)
                            return published_volume
                    try:
                        await _remove_created_volumes([attempted_id])
                        await _restore_novel_snapshot(novel_snapshot, novel_after)
                    except DomainApiError:
                        raise
                if isinstance(exc, DuplicateKeyError):
                    winner = await VolumeService._wait_for_receipt(
                        novel_id,
                        fingerprint.key_hash,
                        fingerprint.request_hash,
                    )
                    if winner is not None:
                        return _receipt_result(winner)["volumes"][0]
                raise

        if session is not None:
            return await create(session)

        try:
            return await run_mongo_write_unit(create, "create_volume")
        except DuplicateKeyError as exc:
            replay_after_conflict = await VolumeService._wait_for_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
            )
            if replay_after_conflict is not None:
                return _receipt_result(replay_after_conflict)["volumes"][0]
            raise _volume_error(
                "VOLUME_ORDER_CONFLICT",
                "卷序号已被并发请求占用，请刷新后重试",
                status_code=409,
            ) from exc
        except DomainApiError as exc:
            if exc.code == "VOLUME_PARENT_CONFLICT":
                replay_after_conflict = await VolumeService._wait_for_receipt(
                    novel_id,
                    fingerprint.key_hash,
                    fingerprint.request_hash,
                )
                if replay_after_conflict is not None:
                    return _receipt_result(replay_after_conflict)["volumes"][0]
            raise

    @staticmethod
    async def get_volumes_by_novel(
        novel_id: str,
        *,
        deleted: bool = False,
    ) -> list[dict[str, Any]]:
        """读取小说活动卷或回收站列表。

        Args:
            novel_id: 小说 ObjectId 字符串。
            deleted: True 读回收站，False 读活动卷。

        Returns:
            按当前视图稳定排序的完整卷文档。
        """
        await novel_repo.get_novel_by_id(novel_id)
        return await volume_repo.get_volumes_by_novel(novel_id, deleted=deleted)

    @staticmethod
    async def get_volume_by_id(
        volume_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any]:
        """读取一个卷，可指定包含回收站。

        Args:
            volume_id: 卷 ObjectId 字符串。
            include_deleted: 是否允许返回回收站卷。

        Returns:
            小说仍存在时的完整卷文档。
        """
        volume = await volume_repo.get_volume_by_id(
            volume_id,
            include_deleted=include_deleted,
        )
        await novel_repo.get_novel_by_id(str(volume["novel_id"]))
        return volume

    @staticmethod
    async def update_volume_info(
        volume_id: str,
        update_data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """按 expected_version 更新活动卷人工字段。

        Args:
            volume_id: 卷 ObjectId 字符串。
            update_data: 含 expected_version 的严格字段白名单。
            session: 调用方事务；提供时不另开事务。

        Returns:
            版本恰好递增一次的写后卷。
        """
        payload = _plain_dict(update_data, exclude_unset=True)
        expected_version = payload.pop("expected_version")
        if "order_index" in payload:
            raise _volume_error(
                "VOLUME_REORDER_REQUIRED",
                "V2 卷顺序只能通过完整重排接口修改",
            )
        fields = _normalize_volume_fields(payload)
        if not fields:
            raise _volume_error("VOLUME_UPDATE_EMPTY", "卷更新至少需要一个业务字段")
        if "plot" in fields:
            from backend.services.novel.plot_service import stamp_manual_plot
            from backend.db.transaction import run_mongo_write_unit

            async def save_plot(session):
                snapshot = await VolumeService._get_versioned_volume(volume_id, expected_version, deleted=False, session=session)
                await stamp_manual_plot(str(snapshot["novel_id"]), "volume", volume_id, fields, session=session)
                return await _apply_volume_change(snapshot, fields, increment_version=True, changes=[], session=session, conflict_message="卷在更新期间已发生变化")

            if session is not None:
                return await save_plot(session)
            return await run_mongo_write_unit(save_plot, "update_volume_plot", require_transaction=True)
        snapshot = await VolumeService._get_versioned_volume(
            volume_id,
            expected_version,
            deleted=False,
            session=session,
        )
        updated = await _apply_volume_change(
            snapshot,
            fields,
            increment_version=True,
            changes=[],
            session=session,
            conflict_message="卷在更新期间已发生变化",
        )
        return updated

    @staticmethod
    async def confirm_launch_package(volume_id: str, request: VolumeLaunchConfirmV1 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """复验启动包 basis 并幂等更新同一个正式卷。

        Args:
            volume_id: 既有 PUT 路径中的目标活动卷 ObjectId 字符串。
            request: 编辑后完整启动包、basis 与目标公开版本。
            idempotency_key: AI 启动包确认必填的领域幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            首次成功或同键重放的单个目标卷写后快照。
        """
        volume_id = volume_id.lower()
        confirmed = VolumeLaunchConfirmV1.model_validate(
            request.model_dump(mode="json")
            if isinstance(request, VolumeLaunchConfirmV1)
            else dict(request)
        )
        basis: VolumeLaunchBasisV1 = confirmed.basis
        generation_input = basis.generation_input
        novel_id = generation_input.novel_id
        if generation_input.volume_id != volume_id:
            raise _volume_error(
                "VOLUME_BASIS_INVALID",
                "启动包 basis 与 PUT 路径中的目标卷不一致",
            )
        package = {
            "title": confirmed.title,
            "subtitle": confirmed.subtitle,
            "summary": confirmed.summary,
            "goal": confirmed.goal,
            "theme": confirmed.theme,
            "planning": confirmed.planning.model_dump(mode="json"),
        }
        fields = _normalize_volume_fields(package)
        fingerprint = build_idempotency_fingerprint(
            idempotency_key,
            {
                "operation": "launch-package",
                "novel_id": novel_id,
                "volume_id": volume_id,
                "expected_version": confirmed.expected_version,
                "package": fields,
                "basis": basis.model_dump(mode="json"),
            },
        )
        replay = (await VolumeService._load_receipt(
            novel_id,
            fingerprint.key_hash,
            fingerprint.request_hash,
        )) if session is None else None
        if replay is not None:
            return _receipt_result(replay)["volumes"][0]

        async def confirm(session: Any) -> dict[str, Any]:
            replay_in_unit = await VolumeService._load_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
                session=session,
            )
            if replay_in_unit is not None:
                return _receipt_result(replay_in_unit)["volumes"][0]
            execution = basis.flow_snapshot["execution"]
            if "character_fact_reads" not in execution:
                raise _volume_error("CHARACTER_FACT_CONTRACT_REQUIRED", "原启动包未保存人物事实依据，请保留候选并重新生成", status_code=409)
            if (execution.get("relation_reading_contract") != "character_relation_facts_v1"
                    or "character_relation_fact_reads" not in execution):
                raise _volume_error("CHARACTER_RELATION_FACT_CONTRACT_REQUIRED", "原启动包未保存关系事实依据，请保留候选并重新生成", status_code=409)
            from backend.services.novel.writing_context import revalidate_position_fact_reads
            if execution.get("faction_reading_contract") != "faction_facts_v1" or "faction_fact_reads" not in execution:
                raise _volume_error("FACTION_FACT_CONTRACT_REQUIRED", "原启动包未保存势力事实依据，请保留候选并重新生成", status_code=409)
            original_reads = [*execution["character_fact_reads"], *execution["character_relation_fact_reads"],
                              *execution.get("item_fact_reads", []), *execution["faction_fact_reads"]]
            await revalidate_position_fact_reads(original_reads, session=session, protect=True)
            context = await load_volume_planning_context(
                novel_id,
                target_volume_id=volume_id,
                session=session,
            )
            if any(read not in original_reads for read in context["fact_reads"]):
                raise _volume_error("VOLUME_BASIS_CONFLICT", "启动包缺少当前人物或关系查询的原依据，请保留候选并重新生成", status_code=409)
            current_sources = {
                (source.resource_type, source.id): int(source.version)
                for source in context["source_refs"]
            }
            submitted_sources = {
                (source.resource_type, source.id): int(source.version)
                for source in basis.source_refs
            }
            allowed_source_types = {
                "novel",
                "volume",
                "world_rule",
                "character",
                "faction",
                "character_relation",
                "faction_relation",
                "character_faction_binding",
            }
            for identity, submitted_version in submitted_sources.items():
                resource_type, resource_id = identity
                if resource_type not in allowed_source_types:
                    raise _volume_error(
                        "VOLUME_BASIS_SOURCE_INVALID",
                        f"启动包 basis 不支持来源类型 {resource_type}",
                    )
                current_version = current_sources.get(identity)
                if current_version is None:
                    raise _volume_error(
                        "VOLUME_BASIS_SOURCE_NOT_FOUND",
                        "启动包依据中的正式资源已不存在或不再可用",
                        status_code=404,
                        details={"resource_type": resource_type, "id": resource_id},
                    )
                if current_version != submitted_version:
                    raise _volume_error(
                        "VOLUME_BASIS_CONFLICT",
                        "启动包依据中的正式资源版本已变化",
                        status_code=409,
                        details={
                            "resource_type": resource_type,
                            "id": resource_id,
                            "expected_version": submitted_version,
                            "actual_version": current_version,
                        },
                    )
            if set(submitted_sources) != set(current_sources):
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "启动包正式输入集合已变化，请重新生成",
                    status_code=409,
                )
            try:
                current_fingerprint = compute_volume_launch_input_fingerprint(
                    generation_input,
                    context["source_refs"],
                    flow_snapshot=basis.flow_snapshot,
                )
            except (KeyError, ValueError) as exc:
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "启动包的生成方案或输入已变化，请重新生成",
                    status_code=409,
                ) from exc
            if basis.input_fingerprint != current_fingerprint:
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "启动包 Prompt、Schema、执行配置或生成输入已变化",
                    status_code=409,
                )

            volumes = context["volumes"]
            target_index = next(
                index
                for index, item in enumerate(volumes)
                if str(item["_id"]) == volume_id
            )
            target = volumes[target_index]
            if int(target["version"]) != confirmed.expected_version:
                raise _volume_error(
                    "VOLUME_VERSION_CONFLICT",
                    "目标卷版本已变化，请刷新后重试",
                    status_code=409,
                )
            previous = volumes[target_index - 1] if target_index > 0 else None
            next_volume = (
                volumes[target_index + 1]
                if target_index + 1 < len(volumes)
                else None
            )
            target_planning = target.get("planning")
            chapter_count = generation_input.target_chapter_count
            word_count = generation_input.target_word_count
            if chapter_count is None:
                if target_planning is None:
                    raise _volume_error(
                        "VOLUME_BASIS_CONFLICT",
                        "目标卷预算来源已失效，请重新生成启动包",
                        status_code=409,
                    )
                chapter_count = int(target_planning["target_chapter_count"])
            if word_count is None:
                if target_planning is None:
                    raise _volume_error(
                        "VOLUME_BASIS_CONFLICT",
                        "目标卷预算来源已失效，请重新生成启动包",
                        status_code=409,
                    )
                word_count = int(target_planning["target_word_count"])
            if (
                int(fields["planning"]["target_chapter_count"]) != chapter_count
                or int(fields["planning"]["target_word_count"]) != word_count
            ):
                raise _volume_error(
                    "VOLUME_BUDGET_INVALID",
                    "启动包确认预算必须与生成期锁定预算一致",
                )
            previous_planning = (
                previous.get("planning") if previous is not None else None
            )
            if previous_planning is not None and normalize_volume_text(
                str(previous_planning["end_state"])
            ) != normalize_volume_text(str(fields["planning"]["start_state"])):
                raise _volume_error(
                    "VOLUME_STATE_BOUNDARY_INVALID",
                    "启动包起点必须与当前上一卷终点衔接",
                )
            impact = await VolumeService.get_delete_impact(
                volume_id,
                session=session,
            )
            if impact["total"] - impact["chapter_records"]:
                raise _volume_error(
                    "VOLUME_LAUNCH_BLOCKED",
                    "目标卷已有下级结构，不能静默覆盖启动包",
                    status_code=409,
                    details={"impact": impact},
                )
            # 右邻差异只影响预览提示；确认仍只写目标卷，绝不改写相邻卷。
            next_planning = (
                next_volume.get("planning") if next_volume is not None else None
            )
            next_start_state_conflict = bool(
                next_planning is not None
                and normalize_volume_text(str(fields["planning"]["end_state"]))
                != normalize_volume_text(str(next_planning["start_state"]))
            )

            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            updated: dict[str, Any] | None = None
            receipt_attempted = False
            try:
                updated = await _apply_volume_change(
                    target,
                    fields,
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="目标卷在启动包确认期间已发生变化",
                )
                if session is None:
                    # standalone 没有快照隔离：目标 CAS 后再次复验所有非目标来源，
                    # 避免角色、规则或相邻卷在首检后漂移却仍发布成功收据。
                    after_context = await load_volume_planning_context(
                        novel_id,
                        target_volume_id=volume_id,
                    )
                    after_sources = {
                        (source.resource_type, source.id): int(source.version)
                        for source in after_context["source_refs"]
                    }
                    missing = set(submitted_sources) - set(after_sources)
                    if missing:
                        resource_type, resource_id = sorted(missing)[0]
                        raise _volume_error(
                            "VOLUME_BASIS_SOURCE_NOT_FOUND",
                            "启动包依据中的正式资源在确认期间已不存在或不再可用",
                            status_code=404,
                            details={
                                "resource_type": resource_type,
                                "id": resource_id,
                            },
                        )
                    if set(after_sources) != set(submitted_sources):
                        raise _volume_error(
                            "VOLUME_BASIS_CONFLICT",
                            "启动包正式输入集合在确认期间发生变化",
                            status_code=409,
                        )
                    for identity, submitted_version in submitted_sources.items():
                        if identity == ("volume", volume_id):
                            continue
                        if after_sources[identity] != submitted_version:
                            raise _volume_error(
                                "VOLUME_BASIS_CONFLICT",
                                "启动包正式输入版本在确认期间发生变化",
                                status_code=409,
                                details={
                                    "resource_type": identity[0],
                                    "id": identity[1],
                                },
                            )
                    after_target = next(
                        item
                        for item in after_context["volumes"]
                        if str(item["_id"]) == volume_id
                    )
                    if (
                        int(after_target["version"]) != int(updated["version"])
                        or after_target["updated_at"] != updated["updated_at"]
                        or any(after_target.get(key) != value for key, value in fields.items())
                    ):
                        raise _volume_error(
                            "VOLUME_VERSION_CONFLICT",
                            "目标卷在启动包确认期间再次发生变化",
                            status_code=409,
                        )
                receipt_attempted = True
                await volume_command_receipt_repo.create_receipt(
                    {
                        "novel_id": novel_id,
                        "idempotency_key_hash": fingerprint.key_hash,
                        "request_hash": fingerprint.request_hash,
                        "operation": "launch-package",
                        "candidate_ref_map": {},
                        "volumes": [deepcopy(updated)],
                        "next_start_state_conflict": next_start_state_conflict,
                    },
                    session=session,
                )
                return updated
            except Exception:
                if session is None:
                    published = None
                    if receipt_attempted:
                        published = await volume_command_receipt_repo.find_receipt(
                            novel_id,
                            fingerprint.key_hash,
                        )
                    if (
                        published is not None
                        and published.get("request_hash") == fingerprint.request_hash
                    ):
                        published_volume = _receipt_result(published)["volumes"][0]
                        if (
                            updated is not None
                            and str(updated["_id"]) == str(published_volume["_id"])
                            and int(updated["version"])
                            == int(published_volume["version"])
                            and updated["updated_at"] == published_volume["updated_at"]
                        ):
                            return published_volume
                    await _compensate_volume_changes(changes)
                    if (
                        published is not None
                        and published.get("request_hash") == fingerprint.request_hash
                    ):
                        return _receipt_result(published)["volumes"][0]
                raise

        if session is not None:
            return await confirm(session)

        try:
            return await run_mongo_write_unit(confirm, "confirm_volume_launch_package", require_transaction=True)
        except (DuplicateKeyError, OperationFailure) as exc:
            if isinstance(exc, OperationFailure) and not (
                exc.code == 112 and exc.has_error_label("TransientTransactionError")
            ):
                raise
            # 事务已退出，才能用新读取判断原请求是否已有成功回执。
            winner = await VolumeService._wait_for_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
            )
            if winner is not None:
                return _receipt_result(winner)["volumes"][0]
            raise _volume_error(
                "VOLUME_LAUNCH_CONFLICT",
                "启动包确认发生并发冲突",
                status_code=409,
            ) from exc
        except DomainApiError as exc:
            if exc.code in {
                "VOLUME_BASIS_CONFLICT",
                "VOLUME_VERSION_CONFLICT",
            }:
                winner = await VolumeService._wait_for_receipt(
                    novel_id,
                    fingerprint.key_hash,
                    fingerprint.request_hash,
                )
                if winner is not None:
                    return _receipt_result(winner)["volumes"][0]
            raise

    @staticmethod
    async def reorder_volumes(novel_id: str, items: Sequence[Mapping[str, Any]], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """以完整活动兄弟集合执行 1-based CAS 重排。

        Args:
            novel_id: 小说 ObjectId 字符串。
            items: 完整卷 ID、新序号与逐项 expected_version。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            按新顺序排列且每卷版本加一的完整文档。
        """
        await novel_repo.get_novel_by_id(novel_id, session=session)
        requested = [_plain_dict(item) for item in items]
        if not requested:
            raise _volume_error("VOLUME_REORDER_EMPTY", "重排必须提交完整活动卷集合")
        ids = [str(item.get("volume_id") or "") for item in requested]
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            raise _volume_error("VOLUME_REORDER_DUPLICATE", "重排卷 ID 不能为空或重复")
        orders = [item.get("order_index") for item in requested]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in orders):
            raise _volume_error("VOLUME_ORDER_INVALID", "重排序号必须为整数")
        if sorted(orders) != list(range(1, len(requested) + 1)):
            raise _volume_error(
                "VOLUME_REORDER_NOT_CONTIGUOUS",
                "重排序号必须完整且连续为 1..N",
            )

        current = await volume_repo.get_volumes_by_novel(novel_id, session=session)
        if set(ids) != {str(item["_id"]) for item in current}:
            # 先逐项作用域读取，确保跨小说或已删除 ID 保持统一 404。
            for volume_id in ids:
                volume = await volume_repo.get_volume_by_id(volume_id, session=session)
                if str(volume["novel_id"]) != novel_id:
                    raise NotFoundError(f"卷 {volume_id} 不属于小说 {novel_id}")
            raise _volume_error(
                "VOLUME_REORDER_INCOMPLETE",
                "重排必须提交当前全部活动卷",
            )
        by_id = {str(item["_id"]): item for item in current}
        for item in requested:
            validate_expected_version(item.get("expected_version"))
            actual = int(by_id[item["volume_id"]]["version"])
            if actual != item["expected_version"]:
                raise _volume_error(
                    "VOLUME_VERSION_CONFLICT",
                    "重排依据的卷版本已变化",
                    status_code=409,
                    details={
                        "volume_id": item["volume_id"],
                        "expected_version": item["expected_version"],
                        "actual_version": actual,
                    },
                )

        async def reorder(session: Any) -> list[dict[str, Any]]:
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                # 初始化上一卷状态也持有此锁；锁内重读确保来源卷与重排顺序不能交错。
                novel_snapshot = await novel_repo.get_novel_by_id(
                    novel_id,
                    session=session,
                )
                unit_current = await volume_repo.get_volumes_by_novel(
                    novel_id,
                    session=session,
                )
                unit_by_id = {str(item["_id"]): item for item in unit_current}
                if set(unit_by_id) != set(ids):
                    raise _volume_error(
                        "VOLUME_REORDER_INCOMPLETE",
                        "重排期间活动卷集合已变化",
                        status_code=409,
                    )
                for item in requested:
                    if int(unit_by_id[item["volume_id"]]["version"]) != int(
                        item["expected_version"]
                    ):
                        raise _volume_error(
                            "VOLUME_VERSION_CONFLICT",
                            "重排期间卷版本已变化",
                            status_code=409,
                        )
                writes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                novel_after: dict[str, Any] | None = None
                try:
                    novel_after = await _update_novel_from_snapshot(
                        novel_snapshot,
                        {},
                        session=session,
                        conflict_message="小说在卷重排期间已发生变化",
                    )
                    # 先移到负序号，避免交换时触发活动唯一索引；临时写不递增公开版本。
                    for position, item in enumerate(requested, start=1):
                        snapshot = unit_by_id[item["volume_id"]]
                        await _apply_volume_change(
                            snapshot,
                            {"order_index": -position},
                            increment_version=False,
                            changes=writes,
                            session=session,
                            conflict_message="卷在重排期间已发生变化",
                        )
                    result: list[dict[str, Any]] = []
                    for item in sorted(
                        requested,
                        key=lambda value: value["order_index"],
                    ):
                        snapshot = unit_by_id[item["volume_id"]]
                        temporary = next(
                            current_write
                            for original, current_write in writes
                            if original["_id"] == snapshot["_id"]
                        )
                        updated = await _apply_volume_change(
                            temporary,
                            {"order_index": item["order_index"]},
                            increment_version=True,
                            changes=writes,
                            session=session,
                            conflict_message="卷在重排期间已发生变化",
                            compensation_before=snapshot,
                        )
                        result.append(updated)
                    return result
                except Exception:
                    if session is None:
                        latest: dict[Any, tuple[dict[str, Any], dict[str, Any]]] = {}
                        for original, written in writes:
                            latest[original["_id"]] = (original, written)
                        try:
                            await _compensate_volume_changes(list(latest.values()))
                            await _restore_novel_snapshot(novel_snapshot, novel_after)
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            raise RuntimeError(
                                "卷重排失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await reorder(session)

        return await run_mongo_write_unit(reorder, "reorder_volumes")

    @staticmethod
    async def get_delete_impact(
        volume_id: str,
        *,
        session: Any = None,
    ) -> dict[str, Any]:
        """统计当前源码中真实存在的卷下游引用。

        Args:
            volume_id: 活动或回收站卷 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            arcs、势力、角色和归属关系的精确数量与汇总。
        """
        volume = await volume_repo.get_volume_by_id(
            volume_id,
            include_deleted=True,
            session=session,
        )
        obj_id = volume["_id"]
        identity_values = [obj_id, str(obj_id)]
        counts = {
            "arcs": await BaseRepository("arcs").collection.count_documents(
                {"volume_id": {"$in": identity_values}},
                session=session,
            ),
            "scenes": await BaseRepository("scenes").collection.count_documents(
                {"volume_id": {"$in": identity_values}}, session=session,
            ),
            "chapters": await BaseRepository("chapters").collection.count_documents(
                {"volume_id": {"$in": identity_values}}, session=session,
            ),
            "factions": await BaseRepository("factions").collection.count_documents(
                {"volume_id": {"$in": identity_values}},
                session=session,
            ),
            "character_volume_states": await BaseRepository(
                "character_volume_states"
            ).collection.count_documents(
                {"volume_id": {"$in": identity_values}},
                session=session,
            ),
            "faction_volume_states": await BaseRepository(
                "faction_volume_states"
            ).collection.count_documents(
                {"volume_id": {"$in": identity_values}},
                session=session,
            ),
            "character_first_appearances": await BaseRepository(
                "characters"
            ).collection.count_documents(
                {"first_appearance_volume_id": {"$in": identity_values}},
                session=session,
            ),
            "faction_first_appearances": await BaseRepository(
                "factions"
            ).collection.count_documents(
                {"first_appearance_volume_id": {"$in": identity_values}},
                session=session,
            ),
            "character_faction_binding_boundaries": await BaseRepository(
                "character_faction_bindings"
            ).collection.count_documents(
                {
                    "$or": [
                        {"joined_volume_id": {"$in": identity_values}},
                        {"left_volume_id": {"$in": identity_values}},
                    ]
                },
                session=session,
            ),
        }
        from backend.services.novel.foreshadowing_service import count_foreshadowing_references
        counts["foreshadowings"] = await count_foreshadowing_references(volume["novel_id"], "volume", obj_id, session=session)
        from backend.services.novel.chapter_record_source import count_chapter_record_references
        counts["chapter_records"] = await count_chapter_record_references(volume["novel_id"], "volume", obj_id, session=session)
        total = sum(int(value) for value in counts.values())
        return {
            "volume_id": str(obj_id),
            **counts,
            "total": total,
            "has_blockers": total > 0,
        }

    @staticmethod
    async def soft_delete_volume(volume_id: str, expected_version: int, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """无下游引用时按 CAS 将卷移入回收站并收紧活动顺序。

        Args:
            volume_id: 目标活动卷 ObjectId 字符串。
            expected_version: 请求基于的唯一公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            软删成功后的目标卷镜像。
        """
        async def delete(session: Any) -> dict[str, Any]:
            snapshot = await VolumeService._get_versioned_volume(
                volume_id,
                expected_version,
                deleted=False,
                session=session,
            )
            novel_id = str(snapshot["novel_id"])
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                # 取得共享互斥后重新读取，避免锁等待期间沿用过期卷快照。
                snapshot = await VolumeService._get_versioned_volume(
                    volume_id,
                    expected_version,
                    deleted=False,
                    session=session,
                )
                novel_snapshot = await novel_repo.get_novel_by_id(
                    novel_id,
                    session=session,
                )
                impact = await VolumeService.get_delete_impact(
                    volume_id,
                    session=session,
                )
                blocking_total = (
                    int(impact["total"])
                    - int(impact["character_volume_states"])
                    - int(impact["faction_volume_states"])
                    - int(impact["chapter_records"])
                )
                if blocking_total:
                    raise _volume_error(
                        "VOLUME_DELETE_BLOCKED",
                        "卷仍有除角色/势力卷状态外的下级或受保护引用，不能删除",
                        status_code=409,
                        details={"impact": impact},
                    )
                siblings = await volume_repo.get_volumes_by_novel(
                    novel_id,
                    session=session,
                )
                writes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                faction_state_changes: list[
                    tuple[dict[str, Any], dict[str, Any]]
                ] = []
                novel_after: dict[str, Any] | None = None
                try:
                    deltas = {"current_volume_count": -1}
                    if int(snapshot.get("word_count", 0)):
                        deltas["current_word_count"] = -int(snapshot["word_count"])
                    novel_after = await _update_novel_from_snapshot(
                        novel_snapshot,
                        deltas,
                        session=session,
                        conflict_message="小说在卷删除期间已发生变化",
                    )
                    deleted = await _apply_volume_change(
                        snapshot,
                        {"is_deleted": True, "deleted_at": _mongo_write_time()},
                        increment_version=True,
                        changes=writes,
                        session=session,
                        conflict_message="卷在删除期间已发生变化",
                    )
                    for sibling in siblings:
                        if int(sibling["order_index"]) <= int(snapshot["order_index"]):
                            continue
                        await _apply_volume_change(
                            sibling,
                            {"order_index": int(sibling["order_index"]) - 1},
                            increment_version=True,
                            changes=writes,
                            session=session,
                            conflict_message="兄弟卷在删除收序期间已变化",
                        )
                    state_changes = (
                        await CharacterVolumeStateService.add_volume_deletion_source(
                            novel_id,
                            volume_id,
                            session=session,
                        )
                    )
                    faction_state_changes = (
                        await FactionVolumeStateService.add_volume_deletion_source(
                            novel_id,
                            volume_id,
                            session=session,
                        )
                    )
                    return deleted
                except Exception as exc:
                    if isinstance(
                        exc,
                        (StateSourceCompensationError, FactionStateSourceCompensationError),
                    ):
                        state_lock_releasable = False
                    if session is None:
                        try:
                            if faction_state_changes:
                                await compensate_faction_state_changes(
                                    faction_state_changes
                                )
                            if state_changes:
                                await compensate_state_changes(state_changes)
                            await _compensate_volume_changes(writes)
                            await _restore_novel_snapshot(novel_snapshot, novel_after)
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            raise RuntimeError(
                                "卷软删除失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await delete(session)

        return await run_mongo_write_unit(delete, "soft_delete_volume")

    @staticmethod
    async def restore_volume(volume_id: str, expected_version: int, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """按 CAS 把回收站卷追加恢复到活动卷末尾。

        Args:
            volume_id: 目标回收站卷 ObjectId 字符串。
            expected_version: 请求基于的唯一公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            恢复到活动末尾后的目标卷镜像。
        """
        async def restore(session: Any) -> dict[str, Any]:
            snapshot = await VolumeService._get_versioned_volume(
                volume_id,
                expected_version,
                deleted=True,
                session=session,
            )
            novel_id = str(snapshot["novel_id"])
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                snapshot = await VolumeService._get_versioned_volume(
                    volume_id,
                    expected_version,
                    deleted=True,
                    session=session,
                )
                novel_snapshot = await novel_repo.get_novel_by_id(
                    novel_id,
                    session=session,
                )
                order_index = await volume_repo.get_next_order_index(
                    novel_id,
                    session=session,
                )
                changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                state_changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
                faction_state_changes: list[
                    tuple[dict[str, Any], dict[str, Any]]
                ] = []
                novel_after: dict[str, Any] | None = None
                try:
                    deltas = {"current_volume_count": 1}
                    if int(snapshot.get("word_count", 0)):
                        deltas["current_word_count"] = int(snapshot["word_count"])
                    novel_after = await _update_novel_from_snapshot(
                        novel_snapshot,
                        deltas,
                        session=session,
                        conflict_message="小说在卷恢复期间已发生变化",
                    )
                    restored = await _apply_volume_change(
                        snapshot,
                        {
                            "is_deleted": False,
                            "deleted_at": None,
                            "order_index": order_index,
                        },
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="卷在恢复期间已发生变化",
                    )
                    state_changes = (
                        await CharacterVolumeStateService.remove_volume_deletion_source(
                            novel_id,
                            volume_id,
                            session=session,
                        )
                    )
                    faction_state_changes = (
                        await FactionVolumeStateService.remove_volume_deletion_source(
                            novel_id,
                            volume_id,
                            session=session,
                        )
                    )
                    return restored
                except Exception as exc:
                    if isinstance(
                        exc,
                        (StateSourceCompensationError, FactionStateSourceCompensationError),
                    ):
                        state_lock_releasable = False
                    if session is None:
                        try:
                            if faction_state_changes:
                                await compensate_faction_state_changes(
                                    faction_state_changes
                                )
                            if state_changes:
                                await compensate_state_changes(state_changes)
                            await _compensate_volume_changes(changes)
                            await _restore_novel_snapshot(novel_snapshot, novel_after)
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            raise RuntimeError(
                                "卷恢复失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        if session is not None:
            return await restore(session)

        try:
            return await run_mongo_write_unit(restore, "restore_volume")
        except DuplicateKeyError as exc:
            raise _volume_error(
                "VOLUME_ORDER_CONFLICT",
                "卷恢复时末尾序号发生并发冲突，请重试",
                status_code=409,
            ) from exc

    @staticmethod
    async def hard_delete_volume(
        volume_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        """永久删除没有任何真实下游引用的回收站卷。

        Args:
            volume_id: 目标回收站卷 ObjectId 字符串。
            expected_version: 请求基于的唯一公开版本。

        Returns:
            保留旧计数字段的删除统计和影响快照。
        """
        async def delete(session: Any) -> dict[str, Any]:
            snapshot = await VolumeService._get_versioned_volume(
                volume_id,
                expected_version,
                deleted=True,
                session=session,
            )
            novel_id = str(snapshot["novel_id"])
            state_lock = await acquire_state_write_lock(novel_id, session=session)
            state_lock_releasable = True
            try:
                snapshot = await VolumeService._get_versioned_volume(
                    volume_id,
                    expected_version,
                    deleted=True,
                    session=session,
                )
                novel_snapshot = await novel_repo.get_novel_by_id(
                    novel_id,
                    session=session,
                )
                impact = await VolumeService.get_delete_impact(
                    volume_id,
                    session=session,
                )
                if impact["chapter_records"]:
                    raise _volume_error("VOLUME_CHAPTER_RECORD_DELETE_BLOCKED", "卷仍是章后确认记录的来源，如需全部清理请删除整部作品", status_code=409, details={"impact": impact})
                if impact["has_blockers"]:
                    raise _volume_error(
                        "VOLUME_HARD_DELETE_BLOCKED",
                        "回收站卷仍有受保护引用，不能永久删除",
                        status_code=409,
                        details={"impact": impact},
                    )
                receipt_query = {
                    "novel_id": snapshot["novel_id"],
                    "$or": [
                        {"source_volume_id": snapshot["_id"]},
                        {"target_volume_id": snapshot["_id"]},
                    ],
                }
                character_receipts = BaseRepository(
                    "character_volume_state_initialization_receipts"
                ).collection
                faction_receipts = BaseRepository(
                    "faction_volume_state_initialization_receipts"
                ).collection
                character_receipt_snapshots = await character_receipts.find(
                    receipt_query,
                    session=session,
                ).to_list(length=None)
                faction_receipt_snapshots = await faction_receipts.find(
                    receipt_query,
                    session=session,
                ).to_list(length=None)
                novel_after: dict[str, Any] | None = None
                safe_to_compensate = True
                try:
                    novel_after = await _update_novel_from_snapshot(
                        novel_snapshot,
                        {},
                        session=session,
                        conflict_message="小说在卷永久删除期间已发生变化",
                    )
                    character_deleted = await character_receipts.delete_many(
                        receipt_query,
                        session=session,
                    )
                    faction_deleted = await faction_receipts.delete_many(
                        receipt_query,
                        session=session,
                    )
                    if (
                        character_deleted.deleted_count
                        != len(character_receipt_snapshots)
                        or faction_deleted.deleted_count
                        != len(faction_receipt_snapshots)
                    ):
                        raise RuntimeError("卷初始化回执在永久删除期间发生并发变化")
                    try:
                        deleted = await volume_repo.hard_delete_volume(
                            snapshot,
                            session=session,
                        )
                    except Exception:
                        if session is None:
                            # 未知确认只在目标精确消失时视为当前删除已成功。
                            try:
                                await volume_repo.get_volume_by_id(
                                    volume_id,
                                    include_deleted=True,
                                )
                            except NotFoundError:
                                return {
                                    "stats": {"arcs_deleted": 0, "volume_deleted": 1},
                                    "impact": impact,
                                }
                            except Exception:
                                # 无法确认卷是否已消失时不能补回可能悬空的回执。
                                safe_to_compensate = False
                                raise
                        raise
                    if not deleted:
                        raise _volume_error(
                            "VOLUME_VERSION_CONFLICT",
                            "卷在永久删除期间已发生变化",
                            status_code=409,
                        )
                    return {
                        "stats": {"arcs_deleted": 0, "volume_deleted": 1},
                        "impact": impact,
                    }
                except Exception:
                    if session is None:
                        if not safe_to_compensate:
                            state_lock_releasable = False
                            raise
                        try:
                            # 回执不可变；删除结果不确定时先重读，只补回确实消失的精确预镜像。
                            for collection, receipt_snapshots in (
                                (character_receipts, character_receipt_snapshots),
                                (faction_receipts, faction_receipt_snapshots),
                            ):
                                for receipt_snapshot in receipt_snapshots:
                                    current = await collection.find_one(
                                        {"_id": receipt_snapshot["_id"]}
                                    )
                                    if current == receipt_snapshot:
                                        continue
                                    if current is not None:
                                        raise RuntimeError(
                                            "卷初始化回执补偿失败：同一回执已发生变化"
                                        )
                                    try:
                                        await collection.insert_one(
                                            dict(receipt_snapshot)
                                        )
                                    except Exception:
                                        current = await collection.find_one(
                                            {"_id": receipt_snapshot["_id"]}
                                        )
                                        if current != receipt_snapshot:
                                            raise
                            await _restore_novel_snapshot(novel_snapshot, novel_after)
                        except Exception as compensation_exc:
                            state_lock_releasable = False
                            raise RuntimeError(
                                "卷永久删除失败，且 standalone 补偿未完成"
                            ) from compensation_exc
                    raise
            finally:
                if state_lock_releasable:
                    await release_state_write_lock(
                        novel_id,
                        state_lock,
                        session=session,
                    )

        return await run_mongo_write_unit(delete, "hard_delete_volume")

    @staticmethod
    async def bulk_plan_volumes(novel_id: str, request: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """复验 basis 后幂等确认整批卷骨架到同一 volumes 集合。

        Args:
            novel_id: 小说 ObjectId 字符串。
            request: 候选、生成输入、basis 与精确来源版本。
            idempotency_key: 批量确认必填幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            candidate_ref 到 ObjectId 的映射与原始正式卷快照。
        """
        novel_id = novel_id.lower()
        payload = _plain_dict(request)
        candidates = list(payload["candidates"])
        basis = VolumeSkeletonBasisV1.model_validate(payload["basis"])
        generation_input = basis.generation_input.model_dump(mode="json")
        mode = generation_input["mode"]
        expected_versions = dict(payload["expected_versions"])
        fingerprint = build_idempotency_fingerprint(
            idempotency_key,
            {
                "operation": "bulk-plan",
                "novel_id": novel_id,
                "candidates": candidates,
                "generation_input": generation_input,
                "basis": basis.model_dump(mode="json"),
                "expected_versions": expected_versions,
            },
        )
        replay = (await VolumeService._load_receipt(
            novel_id,
            fingerprint.key_hash,
            fingerprint.request_hash,
        )) if session is None else None
        if replay is not None:
            return _receipt_result(replay)
        if (
            basis.novel_id != novel_id
            or basis.workflow != VOLUME_SKELETON_WORKFLOW
            or basis.step != VOLUME_SKELETON_STEP
            or basis.schema_id != VOLUME_SKELETON_SCHEMA_ID
            or basis.schema_version != VOLUME_SKELETON_SCHEMA_VERSION
        ):
            raise _volume_error("VOLUME_BASIS_INVALID", "卷骨架 basis 与当前工作流不匹配")

        prepared = [
            {**_normalize_volume_fields(item), "candidate_ref": item["candidate_ref"]}
            for item in candidates
        ]
        refs = [str(item["candidate_ref"]) for item in prepared]
        if len(refs) != len(set(refs)):
            raise _volume_error("VOLUME_CANDIDATE_DUPLICATE", "candidate_ref 不能重复")
        try:
            validate_volume_skeleton_candidate_set(
                prepared,
                generation_input,
                require_generated_count=False,
            )
        except ValueError as exc:
            raise _volume_error("VOLUME_PLAN_INVALID", str(exc)) from exc
        orders = [int(item["order_index"]) for item in prepared]
        normalized_titles = [normalize_volume_text(item["title"]) for item in prepared]
        target_range = generation_input.get("target_order_range")
        if mode == "replan" and target_range is not None:
            range_orders = list(range(int(target_range["start"]), int(target_range["end"]) + 1))
            if sorted(orders) != range_orders:
                raise _volume_error(
                    "VOLUME_ORDER_INVALID",
                    "候选卷顺序必须与 target_order_range 完全一致",
                )
        elif mode == "replan":
            raise _volume_error(
                "VOLUME_ORDER_RANGE_REQUIRED",
                "replan 必须声明连续 target_order_range",
            )

        async def confirm(session: Any) -> dict[str, Any]:
            replay_in_unit = await VolumeService._load_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
                session=session,
            )
            if replay_in_unit is not None:
                return _receipt_result(replay_in_unit)
            novel_snapshot = await novel_repo.get_novel_by_id(
                novel_id,
                session=session,
            )
            active = await volume_repo.get_volumes_by_novel(
                novel_id,
                session=session,
            )
            planning_context = await load_volume_planning_context(
                novel_id,
                session=session,
            )
            current_sources = {
                (source.resource_type, source.id): int(source.version)
                for source in planning_context["source_refs"]
            }
            submitted_sources = {
                (item.resource_type, item.id): int(item.version)
                for item in basis.source_refs
            }
            submitted_expected = {
                f"{kind}:{resource_id}": version
                for (kind, resource_id), version in submitted_sources.items()
            }
            if ("novel", novel_id) not in submitted_sources:
                raise _volume_error("VOLUME_BASIS_INVALID", "卷骨架 basis 必须引用当前小说")
            allowed_source_types = {
                "novel",
                "volume",
                "world_rule",
                "character",
                "faction",
                "character_relation",
                "faction_relation",
                "character_faction_binding",
            }
            for identity, submitted_version in submitted_sources.items():
                resource_type, resource_id = identity
                if resource_type not in allowed_source_types:
                    raise _volume_error(
                        "VOLUME_BASIS_SOURCE_INVALID",
                        f"卷骨架 basis 不支持来源类型 {resource_type}",
                    )
                current_version = current_sources.get(identity)
                if current_version is None:
                    raise _volume_error(
                        "VOLUME_BASIS_SOURCE_NOT_FOUND",
                        "卷骨架依据中的正式资源已不存在或不再可用",
                        status_code=404,
                        details={
                            "resource_type": resource_type,
                            "id": resource_id,
                        },
                    )
                if current_version != submitted_version:
                    raise _volume_error(
                        "VOLUME_BASIS_CONFLICT",
                        "卷骨架依据中的正式资源版本已变化",
                        status_code=409,
                        details={
                            "resource_type": resource_type,
                            "id": resource_id,
                            "expected_version": submitted_version,
                            "actual_version": current_version,
                        },
                    )
            if (
                set(submitted_sources) != set(current_sources)
                or expected_versions != submitted_expected
                or int(generation_input["novel_expected_version"])
                != int(novel_snapshot["version"])
            ):
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "卷骨架 basis 或 expected_versions 已过期",
                    status_code=409,
                )
            try:
                current_fingerprint = compute_volume_skeleton_input_fingerprint(
                    novel_id,
                    basis.generation_input,
                    planning_context["source_refs"],
                    flow_snapshot=basis.flow_snapshot,
                )
            except (KeyError, ValueError) as exc:
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "卷骨架的生成方案或输入已变化，请重新生成",
                    status_code=409,
                ) from exc
            if basis.input_fingerprint != current_fingerprint:
                raise _volume_error(
                    "VOLUME_BASIS_CONFLICT",
                    "卷骨架输入指纹已变化",
                    status_code=409,
                )

            active_by_order = {int(item["order_index"]): item for item in active}
            active_titles = {normalize_volume_text(str(item["title"])) for item in active}
            ordered_prepared = sorted(prepared, key=lambda item: int(item["order_index"]))
            target_by_order: dict[int, dict[str, Any]] = {}
            if mode == "create":
                if active:
                    raise _volume_error(
                        "VOLUME_MODE_CONFLICT",
                        "create 模式要求当前小说没有活动卷",
                        status_code=409,
                    )
                if sorted(orders) != list(range(1, len(prepared) + 1)):
                    raise _volume_error("VOLUME_ORDER_INVALID", "create 候选必须从 1 连续编号")
            elif mode == "append":
                required_start = len(active) + 1
                if sorted(orders) != list(range(required_start, required_start + len(prepared))):
                    raise _volume_error(
                        "VOLUME_ORDER_CONFLICT",
                        "append 候选必须从当前末尾连续追加",
                        status_code=409,
                    )
                if active_titles & set(normalized_titles):
                    raise _volume_error(
                        "VOLUME_TITLE_CONFLICT",
                        "append 候选标题与活动卷冲突",
                        status_code=409,
                    )
                previous_planning = active[-1].get("planning") if active else None
                if previous_planning is not None and normalize_volume_text(
                    str(previous_planning["end_state"])
                ) != normalize_volume_text(
                    str(ordered_prepared[0]["planning"]["start_state"])
                ):
                    raise _volume_error(
                        "VOLUME_STATE_BOUNDARY_INVALID",
                        "append 首卷起始状态必须与当前末卷结束状态衔接",
                    )
            else:
                if any(order not in active_by_order for order in orders):
                    raise _volume_error(
                        "VOLUME_REPLAN_RANGE_CONFLICT",
                        "replan 目标区间已不再对应活动卷",
                        status_code=409,
                    )
                target_by_order = {order: active_by_order[order] for order in orders}
                required_volume_sources = {
                    ("volume", str(item["_id"])): int(item["version"])
                    for item in target_by_order.values()
                }
                if any(
                    submitted_sources.get(identity) != version
                    for identity, version in required_volume_sources.items()
                ):
                    raise _volume_error(
                        "VOLUME_BASIS_CONFLICT",
                        "replan basis 未携带目标区间卷的精确版本",
                        status_code=409,
                    )
                non_target_titles = {
                    normalize_volume_text(str(item["title"]))
                    for order, item in active_by_order.items()
                    if order not in target_by_order
                }
                if non_target_titles & set(normalized_titles):
                    raise _volume_error(
                        "VOLUME_TITLE_CONFLICT",
                        "replan 候选标题与区间外活动卷冲突",
                        status_code=409,
                    )
                first_order = min(orders)
                last_order = max(orders)
                previous_planning = (
                    active_by_order[first_order - 1].get("planning")
                    if first_order - 1 in active_by_order
                    else None
                )
                next_planning = (
                    active_by_order[last_order + 1].get("planning")
                    if last_order + 1 in active_by_order
                    else None
                )
                if previous_planning is not None and normalize_volume_text(
                    str(previous_planning["end_state"])
                ) != normalize_volume_text(
                    str(ordered_prepared[0]["planning"]["start_state"])
                ):
                    raise _volume_error(
                        "VOLUME_STATE_BOUNDARY_INVALID",
                        "replan 首卷起始状态必须与左侧相邻卷结束状态衔接",
                    )
                if next_planning is not None and normalize_volume_text(
                    str(ordered_prepared[-1]["planning"]["end_state"])
                ) != normalize_volume_text(str(next_planning["start_state"])):
                    raise _volume_error(
                        "VOLUME_STATE_BOUNDARY_INVALID",
                        "replan 末卷结束状态必须与右侧相邻卷起始状态衔接",
                    )
                for target in target_by_order.values():
                    impact = await VolumeService.get_delete_impact(
                        str(target["_id"]),
                        session=session,
                    )
                    if impact["total"] - impact["chapter_records"]:
                        raise _volume_error(
                            "VOLUME_REPLAN_BLOCKED",
                            "已有下级的卷不能被静默重规划",
                            status_code=409,
                            details={"impact": impact},
                        )

            attempted_ids = (
                [ObjectId() for _ in prepared]
                if mode in {"create", "append"}
                else []
            )
            result_volumes: list[dict[str, Any]] = []
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            novel_after: dict[str, Any] | None = None
            receipt_attempted = False
            mapping: dict[str, str] = {}
            try:
                novel_after = await _update_novel_from_snapshot(
                    novel_snapshot,
                    (
                        {"current_volume_count": len(prepared)}
                        if mode in {"create", "append"}
                        else {}
                    ),
                    session=session,
                    conflict_message="小说在卷骨架确认期间已发生变化",
                )
                if mode in {"create", "append"}:
                    for item, document_id in zip(
                        sorted(prepared, key=lambda value: value["order_index"]),
                        attempted_ids,
                        strict=True,
                    ):
                        created = await volume_repo.create_volume(
                            {
                                key: value
                                for key, value in item.items()
                                if key != "candidate_ref"
                            }
                            | {
                                "_id": document_id,
                                "novel_id": novel_id,
                                "status": "planned",
                            },
                            session=session,
                        )
                        result_volumes.append(created)
                        mapping[item["candidate_ref"]] = str(created["_id"])
                else:
                    for item in sorted(prepared, key=lambda value: value["order_index"]):
                        before = target_by_order[item["order_index"]]
                        updated = await _apply_volume_change(
                            before,
                            {
                                key: value
                                for key, value in item.items()
                                if key not in {"candidate_ref", "order_index"}
                            },
                            increment_version=True,
                            changes=changes,
                            session=session,
                            conflict_message="replan 写入期间卷已变化",
                        )
                        result_volumes.append(updated)
                        mapping[item["candidate_ref"]] = str(updated["_id"])
                if session is None:
                    # standalone 中父级 CAS 只串行化卷命令，不能阻止角色、规则等
                    # 输入在首检后变化；发布收据前必须用同一 loader 再次精确复验。
                    after_context = await load_volume_planning_context(novel_id)
                    after_sources = {
                        (source.resource_type, source.id): int(source.version)
                        for source in after_context["source_refs"]
                    }
                    expected_after_sources = dict(submitted_sources)
                    assert novel_after is not None
                    expected_after_sources[("novel", novel_id)] = int(
                        novel_after["version"]
                    )
                    for result_volume in result_volumes:
                        expected_after_sources[
                            ("volume", str(result_volume["_id"]))
                        ] = int(result_volume["version"])
                    missing = set(expected_after_sources) - set(after_sources)
                    if missing:
                        resource_type, resource_id = sorted(missing)[0]
                        raise _volume_error(
                            "VOLUME_BASIS_SOURCE_NOT_FOUND",
                            "卷骨架正式输入在确认期间已不存在或不再可用",
                            status_code=404,
                            details={
                                "resource_type": resource_type,
                                "id": resource_id,
                            },
                        )
                    if set(after_sources) != set(expected_after_sources):
                        raise _volume_error(
                            "VOLUME_BASIS_CONFLICT",
                            "卷骨架正式输入集合在确认期间发生变化",
                            status_code=409,
                        )
                    if any(
                        after_sources[identity] != version
                        for identity, version in expected_after_sources.items()
                    ):
                        raise _volume_error(
                            "VOLUME_BASIS_CONFLICT",
                            "卷骨架正式输入版本在确认期间发生变化",
                            status_code=409,
                        )
                    after_novel = after_context["novel"]
                    if any(
                        after_novel.get(field) != novel_after.get(field)
                        for field in (
                            "version",
                            "updated_at",
                            "current_volume_count",
                            "current_chapter_count",
                            "current_word_count",
                        )
                    ):
                        raise _volume_error(
                            "VOLUME_PARENT_CONFLICT",
                            "小说统计在卷骨架确认期间发生变化",
                            status_code=409,
                        )
                    after_volumes = {
                        str(item["_id"]): item for item in after_context["volumes"]
                    }
                    if any(
                        after_volumes.get(str(item["_id"])) != item
                        for item in result_volumes
                    ):
                        raise _volume_error(
                            "VOLUME_VERSION_CONFLICT",
                            "本批卷在骨架确认期间再次发生变化",
                            status_code=409,
                        )
                receipt_attempted = True
                await volume_command_receipt_repo.create_receipt(
                    {
                        "novel_id": novel_id,
                        "idempotency_key_hash": fingerprint.key_hash,
                        "request_hash": fingerprint.request_hash,
                        "operation": "bulk-plan",
                        "candidate_ref_map": mapping,
                        "volumes": deepcopy(result_volumes),
                    },
                    session=session,
                )
                return {"candidate_ref_map": mapping, "volumes": result_volumes}
            except Exception as exc:
                if session is None:
                    published_result: dict[str, Any] | None = None
                    own_published = False
                    if receipt_attempted:
                        published = await volume_command_receipt_repo.find_receipt(
                            novel_id,
                            fingerprint.key_hash,
                        )
                        if published is not None and published.get("request_hash") == fingerprint.request_hash:
                            published_result = _receipt_result(published)
                            own_signature = [
                                (str(item["_id"]), int(item["version"]), item["updated_at"])
                                for item in result_volumes
                            ]
                            published_signature = [
                                (str(item["_id"]), int(item["version"]), item["updated_at"])
                                for item in published_result["volumes"]
                            ]
                            own_published = own_signature == published_signature
                    if own_published:
                        return published_result  # type: ignore[return-value]
                    await _compensate_volume_changes(changes)
                    await _remove_created_volumes(attempted_ids)
                    await _restore_novel_snapshot(novel_snapshot, novel_after)
                    if published_result is not None:
                        return published_result
                raise

        if session is not None:
            return await confirm(session)

        try:
            return await run_mongo_write_unit(confirm, "bulk_plan_volumes")
        except DuplicateKeyError as exc:
            winner = await VolumeService._wait_for_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
            )
            if winner is not None:
                return _receipt_result(winner)
            raise _volume_error(
                "VOLUME_BATCH_CONFLICT",
                "卷骨架确认发生顺序或并发冲突",
                status_code=409,
            ) from exc
        except DomainApiError as exc:
            if exc.code in {
                "VOLUME_PARENT_CONFLICT",
                "VOLUME_BASIS_CONFLICT",
                "VOLUME_VERSION_CONFLICT",
                "VOLUME_REPLAN_RANGE_CONFLICT",
            }:
                winner = await VolumeService._wait_for_receipt(
                    novel_id,
                    fingerprint.key_hash,
                    fingerprint.request_hash,
                )
                if winner is not None:
                    return _receipt_result(winner)
            raise


__all__ = [
    "VOLUME_SKELETON_SCHEMA_ID",
    "VOLUME_SKELETON_SCHEMA_VERSION",
    "VOLUME_SKELETON_STEP",
    "VOLUME_SKELETON_WORKFLOW",
    "VOLUME_STATUSES",
    "VolumeService",
]
