"""全书级正式地点、层级顺序与批量确认领域服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any

from bson import ObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.endpoint_guard import (
    touch_dependency_endpoint_guards,
)
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    InvalidIdError,
    NotFoundError,
)
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.character_volume_state_repository import (
    character_volume_state_repo,
)
from backend.db.repositories.faction_volume_state_repository import (
    faction_volume_state_repo,
)
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.confirmation_receipt_repository import (
    location_confirmation_receipt_repo,
)
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.volume_repository import volume_repo
from backend.db.repositories.world_rule_repository import world_rule_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.llm.schemas.location_pydantic import (
    GeneratedLocationCandidateV1,
    LocationBulkGeneratedRequestV1,
    LocationCreateV1,
    LocationUpdateV1,
    normalize_location_text,
)
from backend.services.llm.volume_location_generation_context import (
    load_volume_location_generation_context,
)
from backend.services.llm.volume_location_generation_contract import (
    compute_volume_locations_input_fingerprint,
    validate_volume_location_candidates,
)
from backend.services.novel.item_service import (
    acquire_item_write_lock,
    release_item_write_lock,
)


_LOCATION_CONFIRMATION_REPLAY_WAIT_SECONDS = 5.0


def _location_error(
    code: str,
    message: str,
    *,
    status_code: int = 422,
    field_errors: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> DomainApiError:
    """构造地点领域稳定错误。

    Args:
        code: 稳定错误码。
        message: 面向用户的错误说明。
        status_code: HTTP 状态码。
        field_errors: 可选字段错误映射。
        details: 可选结构化冲突详情。

    Returns:
        可由 Router 交给公共错误协议的领域异常。
    """
    return DomainApiError(
        code,
        message,
        status_code=status_code,
        field_errors=field_errors,
        details=details,
    )


def _mongo_write_time() -> datetime:
    """生成可经 BSON 往返后精确比较的毫秒时间。

    Args:
        无。

    Returns:
        去除时区且截断到毫秒的 UTC 时间。
    """
    now = get_utc_now()
    return now.replace(
        tzinfo=None,
        microsecond=(now.microsecond // 1000) * 1000,
    )


def _validation_details(exc: ValidationError) -> dict[str, list[str]]:
    """把 Pydantic 错误压平为公共字段路径映射。

    Args:
        exc: 严格地点 DTO 抛出的校验错误。

    Returns:
        以点分字段路径为键的错误消息数组。
    """
    result: dict[str, list[str]] = {}
    for error in exc.errors():
        path = ".".join(str(part) for part in error.get("loc", ())) or "$"
        message = str(error.get("msg") or "请求字段不合法")
        if message not in result.setdefault(path, []):
            result[path].append(message)
    return result


def _normalize_display_text(value: str) -> str:
    """把用户文本规范为保存用的 NFKC 首尾清理结果。

    Args:
        value: DTO 已保证为字符串的业务文本。

    Returns:
        NFKC 且首尾空白已清理的显示文本。
    """
    import unicodedata

    return unicodedata.normalize("NFKC", value).strip()


def _prepare_location_content(value: Any) -> dict[str, Any]:
    """校验并清理一条完整正式地点内容。

    Args:
        value: LocationCreateV1 或可解析为该 DTO 的映射。

    Returns:
        只含正式业务字段和规范名键的独立字典。
    """
    try:
        model = value if isinstance(value, LocationCreateV1) else LocationCreateV1.model_validate(value)
    except ValidationError as exc:
        raise _location_error(
            "LOCATION_VALIDATION_FAILED",
            "地点创建字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    content = model.model_dump(mode="json")
    for field in (
        "name",
        "location_type",
        "description",
        "environment",
        "atmosphere",
        "geography",
        "story_function",
    ):
        content[field] = _normalize_display_text(content[field])
    for field in ("aliases", "rules_and_constraints", "tags"):
        content[field] = [_normalize_display_text(item) for item in content[field]]
    try:
        content = LocationCreateV1.model_validate(content).model_dump(mode="json")
    except ValidationError as exc:
        raise _location_error(
            "LOCATION_VALIDATION_FAILED",
            "地点规范化后的字段长度或组合不合法",
            field_errors=_validation_details(exc),
        ) from exc
    content["normalized_name"] = normalize_location_text(content["name"])
    return content


def _prepare_location_update(value: Any) -> tuple[int, dict[str, Any]]:
    """校验地点局部更新并保留显式父级 null 语义。

    Args:
        value: LocationUpdateV1 或可解析为该 DTO 的映射。

    Returns:
        expected_version 与显式业务字段组成的二元组。
    """
    try:
        model = value if isinstance(value, LocationUpdateV1) else LocationUpdateV1.model_validate(value)
    except ValidationError as exc:
        raise _location_error(
            "LOCATION_VALIDATION_FAILED",
            "地点更新字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    fields = model.model_dump(mode="json", exclude_unset=True)
    expected = int(fields.pop("expected_version"))
    for field in (
        "name",
        "location_type",
        "description",
        "environment",
        "atmosphere",
        "geography",
        "story_function",
    ):
        if field in fields:
            fields[field] = _normalize_display_text(fields[field])
    for field in ("aliases", "rules_and_constraints", "tags"):
        if field in fields:
            fields[field] = [_normalize_display_text(item) for item in fields[field]]
    if "name" in fields:
        fields["normalized_name"] = normalize_location_text(fields["name"])
    return expected, fields


def _receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """复制不可变地点收据中的正式响应。

    Args:
        receipt: 同书同幂等键命中的成功回执。

    Returns:
        不与 BSON 收据共享引用的候选映射和地点快照。
    """
    return {
        "candidate_ref_map": deepcopy(receipt["candidate_ref_map"]),
        "locations": deepcopy(receipt["locations"]),
    }


async def _finish_stored_novel_write_lock(
    novel_id: str,
    stored: Mapping[str, Any],
    *,
    session: AsyncClientSession | None,
) -> None:
    """幂等释放人工创建文档或批量回执保存的小说级互斥。

    Args:
        novel_id: 小说 ObjectId 字符串。
        stored: 含内部 token 与 revision 的正式结果或回执。
        session: 可选 MongoDB 会话。

    Returns:
        没有遗留互斥或互斥已精确释放时返回 None。
    """
    lock = stored.get("novel_write_lock")
    if not isinstance(lock, Mapping):
        token = stored.get("location_creation_lock_token")
        revision = stored.get("location_creation_lock_revision")
        if not isinstance(token, str) or not isinstance(revision, int):
            return
        lock = {
            "location_write_lock_token": token,
            "location_write_lock_revision": revision,
        }
    await _release_novel_write_lock(
        novel_id,
        lock,
        session=session,
    )


async def _apply_location_change(
    snapshot: Mapping[str, Any],
    fields: Mapping[str, Any],
    *,
    increment_version: bool,
    changes: list[tuple[dict[str, Any], dict[str, Any]]],
    session: AsyncClientSession | None,
    conflict_message: str,
    compensation_before: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """执行地点精确 CAS，并识别 standalone 写成功后驱动抛错。

    Args:
        snapshot: 当前步骤写入前的完整地点镜像。
        fields: 本步骤要写入的精确字段。
        increment_version: 是否递增唯一公开版本。
        changes: 当前命令的 standalone 补偿写集。
        session: 可选 MongoDB 会话。
        conflict_message: CAS 未命中时的业务说明。
        compensation_before: 多阶段写对应的最初补偿镜像。

    Returns:
        精确写后地点镜像。
    """
    write_time = _mongo_write_time()
    try:
        updated = await location_repo.update_from_snapshot(
            snapshot,
            fields,
            increment_version=increment_version,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await location_repo.collection.find_one({"_id": snapshot["_id"]})
        expected_version = int(snapshot["version"]) + int(increment_version)
        if (
            current is None
            or int(current["version"]) != expected_version
            or current.get("updated_at") != write_time
            or any(current.get(field) != value for field, value in fields.items())
        ):
            raise
        updated = current
    if updated is None:
        raise _location_error(
            "LOCATION_VERSION_CONFLICT",
            conflict_message,
            status_code=409,
        )
    changes.append((dict(compensation_before or snapshot), dict(updated)))
    return updated


async def _publish_created_location(
    document: Mapping[str, Any],
    pending_token: str,
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """精确移除新地点的内部未发布标记并处理未知确认。

    Args:
        document: 仍为本命令初始版本的新地点镜像。
        pending_token: 创建时写入的内部命令标记。
        session: 可选 MongoDB 会话。

    Returns:
        未发布标记已清除的精确地点镜像。
    """
    try:
        published = await location_repo.publish_created_exact(
            document,
            pending_token,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await location_repo.collection.find_one({"_id": document["_id"]})
        published = (
            current
            if current is not None
            and current.get("version") == document.get("version")
            and current.get("dependency_guard_revision")
            == document.get("dependency_guard_revision")
            and current.get("location_order_pending_token") is None
            and current.get("is_deleted") is False
            else None
        )
    if published is None:
        raise _location_error(
            "LOCATION_ORDER_CONFLICT",
            "地点创建发布期间发生并发变化",
            status_code=409,
        )
    return published


async def _compensate_location_changes(
    changes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> None:
    """以两阶段安全顺序精确恢复 standalone 地点镜像。

    Args:
        changes: 当前命令逐步记录的写前/写后地点镜像。

    Returns:
        无；任一步无法精确恢复时显式抛出 503。
    """
    if not changes:
        return
    latest: dict[Any, tuple[dict[str, Any], dict[str, Any]]] = {}
    for before, after in changes:
        latest[before["_id"]] = (dict(before), dict(after))
    minimum = await location_repo.collection.find_one(
        {}, projection={"order_index": 1}, sort=[("order_index", 1)]
    )
    lowest = int(minimum["order_index"]) if minimum is not None else 0
    start = min(-1_000_000, lowest - len(latest) - 1)
    temporary: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for offset, (before, after) in enumerate(latest.values()):
        temp_order = start - offset
        write_time = _mongo_write_time()
        try:
            moved = await location_repo.update_from_snapshot(
                after,
                {"order_index": temp_order},
                increment_version=False,
                write_time=write_time,
            )
        except Exception:
            current = await location_repo.collection.find_one({"_id": after["_id"]})
            moved = (
                current
                if current is not None
                and int(current["version"]) == int(after["version"])
                and current.get("order_index") == temp_order
                and current.get("updated_at") == write_time
                else None
            )
        if moved is None:
            raise _location_error(
                "LOCATION_COMPENSATION_FAILED",
                "地点写入失败，且安全顺序补偿未完整完成",
                status_code=503,
            )
        temporary.append((before, dict(moved)))
    for before, moved in reversed(temporary):
        try:
            restored = await location_repo.restore_snapshot_exact(moved, before)
        except Exception:
            current = await location_repo.collection.find_one({"_id": before["_id"]})
            restored = current == before
        if not restored:
            raise _location_error(
                "LOCATION_COMPENSATION_FAILED",
                "地点写入失败，且数据库补偿未完整完成",
                status_code=503,
            )


async def _remove_generated_locations(
    document_ids: Sequence[ObjectId],
    *,
    key_hash: str,
    request_hash: str,
    pending_token: str,
) -> None:
    """精确清理本批尚处初始状态的生成地点。

    Args:
        document_ids: 插入前预分配的本批 MongoDB ObjectId。
        key_hash: 当前幂等键哈希。
        request_hash: 当前规范请求哈希。
        pending_token: 本批地点尚未公开时持有的内部命令标记。

    Returns:
        无；任一预分配文档仍存在时显式抛出 503。
    """
    if not document_ids:
        return
    try:
        await location_repo.delete_created_exact(
            document_ids,
            key_hash=key_hash,
            request_hash=request_hash,
            pending_token=pending_token,
        )
    except Exception:
        pass
    remaining = await location_repo.collection.count_documents(
        {"_id": {"$in": list(document_ids)}}
    )
    if remaining:
        raise _location_error(
            "LOCATION_COMPENSATION_FAILED",
            "地点批量确认失败，且新地点补偿未完整完成",
            status_code=503,
        )


async def _assert_sibling_group(
    novel_id: str,
    parent_location_id: str | None,
    expected: Sequence[tuple[str, int, int]],
    *,
    session: AsyncClientSession | None,
) -> None:
    """在释放小说级写互斥前核对活动兄弟身份与连续顺序。

    Args:
        novel_id: 小说 ObjectId 字符串。
        parent_location_id: 父地点 ID；根级为 None。
        expected: 本命令计算的稳定 ID、1-based 顺序与公开版本。
        session: 可选 MongoDB 会话。

    Returns:
        数据库兄弟集合与期望完全一致时返回 None。
    """
    actual = await location_repo.list_siblings(
        novel_id,
        parent_location_id,
        session=session,
    )
    projection = [
        (
            str(item["location_id"]),
            int(item["order_index"]),
            int(item["version"]),
        )
        for item in actual
    ]
    if projection != list(expected):
        raise _location_error(
            "LOCATION_ORDER_CONFLICT",
            "地点兄弟集合或连续顺序在写入期间发生变化",
            status_code=409,
        )


async def _acquire_novel_write_lock(
    novel_id: str,
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """取得小说级地点写互斥，阻断整书生命周期越过地点命令。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        session: 可选 MongoDB 会话。

    Returns:
        含唯一 token 与单调 revision 的小说写后镜像。
    """
    command_token = str(ObjectId())
    try:
        locked = await novel_repo.acquire_location_write_lock(
            novel_id,
            command_token,
            session=session,
        )
    except asyncio.CancelledError:
        if session is None:
            current = await novel_repo.collection.find_one(
                {"_id": to_object_id(novel_id)}
            )
            if (
                current is not None
                and current.get("is_deleted") is False
                and current.get("hard_delete_claim") is None
                and current.get("location_write_lock_token") == command_token
            ):
                # 驱动可能已完成加锁再收到取消；调用方尚未拿到镜像，只能在这里精确解锁。
                await _release_novel_write_lock(
                    novel_id,
                    current,
                    session=None,
                )
        raise
    except Exception as exc:
        if session is not None:
            # 事务写冲突已由 Mongo 整体回滚；这里只返回 409，不自动重跑业务回调。
            if (
                isinstance(exc, OperationFailure)
                and exc.code == 112
                and exc.has_error_label("TransientTransactionError")
            ):
                raise _location_error(
                    "LOCATION_WRITE_CONFLICT",
                    "当前小说正由另一个地点或生命周期命令修改，请刷新后重试",
                    status_code=409,
                ) from exc
            raise
        current = await novel_repo.collection.find_one(
            {"_id": to_object_id(novel_id)}
        )
        if (
            current is not None
            and current.get("is_deleted") is False
            and current.get("hard_delete_claim") is None
            and current.get("location_write_lock_token") == command_token
        ):
            return current
        raise
    if locked is not None:
        return locked
    current = await novel_repo.collection.find_one({"_id": to_object_id(novel_id)})
    if current is None or current.get("is_deleted") is True:
        raise _location_error(
            "NOVEL_NOT_FOUND",
            "小说不存在或已删除",
            status_code=404,
        )
    raise _location_error(
        "LOCATION_WRITE_CONFLICT",
        "当前小说正由另一个地点或生命周期命令修改，请刷新后重试",
        status_code=409,
    )


async def _release_novel_write_lock(
    novel_id: str,
    lock: Mapping[str, Any],
    *,
    session: AsyncClientSession | None,
) -> None:
    """精确释放当前地点命令持有的小说级内部互斥。

    Args:
        novel_id: 小说 ObjectId 字符串。
        lock: `_acquire_novel_write_lock` 返回的写后镜像。
        session: 可选 MongoDB 会话。

    Returns:
        互斥已释放或已发生可证明的后继线性化时返回 None。
    """
    token = str(lock["location_write_lock_token"])
    revision = int(lock["location_write_lock_revision"])
    release_error: Exception | None = None
    try:
        released = await novel_repo.release_location_write_lock(
            novel_id,
            token,
            revision,
            session=session,
        )
    except Exception as exc:
        if session is not None:
            raise
        released = False
        release_error = exc
    if released:
        return
    current = await novel_repo.collection.find_one(
        {"_id": to_object_id(novel_id)},
        session=session,
    )
    if current is None:
        return
    current_revision = int(current.get("location_write_lock_revision", 0))
    if (
        current_revision == revision
        and current.get("location_write_lock_token") is None
    ) or current_revision > revision:
        return

    if (
        current_revision == revision
        and current.get("location_write_lock_token") == token
    ):
        # 未知确认或瞬态 false 只在仍能证明由当前命令持锁时精确重试一次。
        try:
            released = await novel_repo.release_location_write_lock(
                novel_id,
                token,
                revision,
                session=session,
            )
        except Exception as exc:
            if session is not None:
                raise
            released = False
            release_error = exc
        if released:
            return
        current = await novel_repo.collection.find_one(
            {"_id": to_object_id(novel_id)},
            session=session,
        )
        if current is None:
            return
        current_revision = int(current.get("location_write_lock_revision", 0))
        if (
            current_revision == revision
            and current.get("location_write_lock_token") is None
        ) or current_revision > revision:
            return

    raise _location_error(
        "LOCATION_WRITE_GUARD_UNAVAILABLE",
        "地点写入已完成，但小说级内部互斥无法精确释放",
        status_code=503,
    ) from release_error


async def _assert_sibling_groups(
    novel_id: str,
    expected_groups: Mapping[str | None, Sequence[tuple[str, int, int]]],
    *,
    session: AsyncClientSession | None,
) -> None:
    """核对当前命令涉及的全部兄弟组精确后态。

    Args:
        novel_id: 小说 ObjectId 字符串。
        expected_groups: 各组精确的稳定 ID、顺序与公开版本后态。
        session: 可选 MongoDB 会话。

    Returns:
        全部兄弟组后态精确匹配时返回 None。
    """
    for parent_location_id in sorted(
        expected_groups,
        key=lambda value: "" if value is None else value,
    ):
        await _assert_sibling_group(
            novel_id,
            parent_location_id,
            expected_groups[parent_location_id],
            session=session,
        )


async def _assert_reorder_members(
    novel_id: str,
    parent_location_id: str | None,
    requested_ids: Sequence[str],
    siblings: Sequence[Mapping[str, Any]],
    *,
    session: AsyncClientSession | None,
) -> None:
    """区分重排中的不可用外部 ID 与同父集合不完整。

    Args:
        novel_id: 当前小说 ObjectId 字符串。
        parent_location_id: 本次要求的共同父级。
        requested_ids: 调用方提交的全部地点 ID。
        siblings: 当前同父活动地点集合。
        session: 可选 MongoDB 会话。

    Returns:
        提交集合与当前同父集合完全一致时返回 None。
    """
    sibling_ids = {str(item["location_id"]) for item in siblings}
    for location_id in sorted(set(requested_ids) - sibling_ids):
        try:
            location = await location_repo.get_location(
                novel_id,
                location_id,
                session=session,
            )
        except (NotFoundError, InvalidIdError) as exc:
            raise _location_error(
                "LOCATION_REFERENCE_NOT_FOUND",
                "重排地点不存在、已删除或不属于当前小说",
                status_code=404,
                details={"location_id": location_id},
            ) from exc
        if location.get("location_order_pending_token") is not None:
            raise _location_error(
                "LOCATION_REFERENCE_NOT_FOUND",
                "重排地点当前不可用",
                status_code=404,
                details={"location_id": location_id},
            )
        # 同书活动地点存在但父级不同仍属于“完整同父集合”冲突，而不是缺失引用。
        if location.get("parent_location_id") == parent_location_id:
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点兄弟集合在重排期间发生变化",
                status_code=409,
            )
    if set(requested_ids) != sibling_ids:
        raise _location_error(
            "LOCATION_REORDER_INCOMPLETE",
            "地点重排必须提交当前同父全部未删除兄弟",
            status_code=409,
        )


def _ensure_sibling_group_ready(
    siblings: Sequence[Mapping[str, Any]],
) -> None:
    """拒绝读取到仍由另一创建命令收口中的兄弟成员。

    Args:
        siblings: 当前票据取得后读取的完整活动兄弟集合。

    Returns:
        全部兄弟均已正式发布时返回 None。
    """
    if any(item.get("location_order_pending_token") for item in siblings):
        raise _location_error(
            "LOCATION_ORDER_CONFLICT",
            "地点兄弟组仍有创建命令正在完成，请刷新后重试",
            status_code=409,
        )


class LocationService:
    """地点唯一事实源的直接业务写入口。"""

    @staticmethod
    async def _get_novel(
        novel_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取活动小说并统一小说作用域错误。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话。

        Returns:
            匹配的活动小说完整文档。
        """
        try:
            return await novel_repo.get_novel_by_id(novel_id, session=session)
        except InvalidIdError as exc:
            raise _location_error(
                "INVALID_OBJECT_ID",
                "novel_id 不是有效 ObjectId",
                field_errors={"novel_id": "不是有效 ObjectId"},
            ) from exc
        except NotFoundError as exc:
            raise _location_error(
                "NOVEL_NOT_FOUND",
                str(exc),
                status_code=404,
            ) from exc

    @staticmethod
    async def _check_public_read_fence(
        novel_id: str,
        *,
        expected_revision: int | None = None,
    ) -> int:
        """确认公共地点读取没有跨越小说级地点写命令。

        Args:
            novel_id: 小说 ObjectId 字符串。
            expected_revision: 首次读取到的内部修订号；首次检查时为 None。

        Returns:
            当前小说级地点写修订号。
        """
        novel = await LocationService._get_novel(novel_id, session=None)
        revision = int(novel.get("location_write_lock_revision", 0))
        if novel.get("location_write_lock_token") is not None or (
            expected_revision is not None and revision != expected_revision
        ):
            raise _location_error(
                "LOCATION_READ_CONFLICT",
                "地点正在更新，请刷新后重试",
                status_code=409,
            )
        return revision

    @staticmethod
    async def _get_location(
        novel_id: str,
        location_id: str,
        *,
        deleted: bool,
        expected_version: int | None,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取指定生命周期地点并可选验证公开版本。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            deleted: 是否要求目标位于回收站。
            expected_version: 可选调用方版本。
            session: 可选 MongoDB 会话。

        Returns:
            生命周期和版本均符合命令要求的地点镜像。
        """
        try:
            location = (
                await location_repo.get_deleted_location(
                    novel_id,
                    location_id,
                    session=session,
                )
                if deleted
                else await location_repo.get_location(
                    novel_id,
                    location_id,
                    session=session,
                )
            )
        except (NotFoundError, InvalidIdError) as exc:
            raise _location_error(
                "LOCATION_NOT_FOUND",
                "地点不存在、已删除或不属于当前小说",
                status_code=404,
                details={"location_id": location_id},
            ) from exc
        if expected_version is not None:
            expected = validate_expected_version(expected_version)
            actual = int(location["version"])
            if actual != expected:
                raise _location_error(
                    "LOCATION_VERSION_CONFLICT",
                    f"地点 {location_id} 版本冲突",
                    status_code=409,
                    details={
                        "expected_version": expected,
                        "actual_version": actual,
                    },
                )
        if location.get("location_order_pending_token"):
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点仍由创建命令收口中，请刷新后重试",
                status_code=409,
            )
        return location

    @staticmethod
    async def _ensure_name_available(
        novel_id: str,
        parent_location_id: str | None,
        normalized_name: str,
        *,
        exclude_location_id: str | None,
        session: AsyncClientSession | None,
    ) -> None:
        """保证同父未删除地点不存在相同规范名。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 父地点 ID；根级为 None。
            normalized_name: 名称规范键。
            exclude_location_id: 更新时排除的目标地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            名称可用时返回 None。
        """
        existing = await location_repo.find_active_by_parent_and_name(
            novel_id,
            parent_location_id,
            normalized_name,
            session=session,
        )
        if existing is not None and existing["location_id"] != exclude_location_id:
            raise _location_error(
                "LOCATION_NAME_CONFLICT",
                "同一父级下已存在规范同名地点",
                status_code=409,
                details={"existing_location_id": existing["location_id"]},
            )

    @staticmethod
    async def _load_dependencies(
        novel_id: str,
        *,
        parent_location_id: str | None,
        rule_ids: Sequence[str],
        faction_ids: Sequence[str],
        session: AsyncClientSession | None,
    ) -> tuple[
        dict[str, Any] | None,
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """读取并验证地点即将引用的父级、规则和势力。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 可选父地点稳定 ID。
            rule_ids: 地点引用的活动规则 ID。
            faction_ids: 地点关联的活动势力 ID。
            session: 可选 MongoDB 会话。

        Returns:
            父级、规则和势力的可用业务预镜像。
        """
        parent: dict[str, Any] | None = None
        rules: list[dict[str, Any]] = []
        factions: list[dict[str, Any]] = []
        try:
            if parent_location_id is not None:
                parent = await location_repo.get_location(
                    novel_id,
                    parent_location_id,
                    session=session,
                )
                if (
                    parent.get("status") != "active"
                    or parent.get("location_order_pending_token") is not None
                ):
                    raise NotFoundError("父地点当前不可用")
            for rule_id in rule_ids:
                rule = await world_rule_repo.get_world_rule(
                    novel_id,
                    rule_id,
                    session=session,
                )
                if rule.get("status") != "active":
                    raise NotFoundError(f"规则 {rule_id} 当前不可用")
                rules.append(rule)
            for faction_id in faction_ids:
                faction = await faction_repo.get_faction(
                    novel_id,
                    faction_id,
                    session=session,
                )
                if faction.get("active_status") != "active":
                    raise NotFoundError(f"势力 {faction_id} 当前不可用")
                factions.append(faction)
        except (NotFoundError, InvalidIdError) as exc:
            raise _location_error(
                "LOCATION_REFERENCE_NOT_FOUND",
                "父地点、规则或势力引用不存在、已删除、不可用或跨小说",
                status_code=404,
            ) from exc

        return parent, rules, factions

    @staticmethod
    async def _touch_dependency_documents(
        rules: Sequence[Mapping[str, Any]],
        factions: Sequence[Mapping[str, Any]],
        *,
        session: AsyncClientSession | None,
    ) -> None:
        """在地点事实落库后单调推进依赖端点护栏。

        Args:
            rules: 活动规则预镜像。
            factions: 活动势力预镜像。
            session: 可选 MongoDB 会话。

        Returns:
            全部依赖仍与预镜像一致并完成 guard 推进时返回 None。
        """
        try:
            if rules:
                await touch_dependency_endpoint_guards(
                    world_rule_repo.collection,
                    [
                        {
                            "_id": rule["_id"],
                            "novel_id": rule["novel_id"],
                            "rule_id": rule["rule_id"],
                            "version": rule["version"],
                            "status": "active",
                            "is_deleted": False,
                        }
                        for rule in rules
                    ],
                    session=session,
                    rollback_on_error=False,
                )
            if factions:
                await touch_dependency_endpoint_guards(
                    faction_repo.collection,
                    [
                        {
                            "_id": faction["_id"],
                            "novel_id": faction["novel_id"],
                            "faction_id": faction["faction_id"],
                            "version": faction["version"],
                            "active_status": "active",
                            "is_deleted": False,
                        }
                        for faction in factions
                    ],
                    session=session,
                    rollback_on_error=False,
                )
        except Exception as exc:
            if isinstance(exc, DuplicateKeyError):
                raise _location_error(
                    "LOCATION_REFERENCE_CONFLICT",
                    "地点依赖在写入期间发生变化，请刷新后重试",
                    status_code=409,
                ) from exc
            raise

    @staticmethod
    async def _ensure_no_cycle(
        novel_id: str,
        target_location_id: str,
        parent: Mapping[str, Any] | None,
        *,
        session: AsyncClientSession | None,
    ) -> None:
        """沿父链验证目标地点不会形成自引用或环。

        Args:
            novel_id: 小说 ObjectId 字符串。
            target_location_id: 当前被修改的地点 ID。
            parent: 已验证可用的新父地点。
            session: 可选 MongoDB 会话。

        Returns:
            新父链不包含目标时返回 None。
        """
        cursor = dict(parent) if parent is not None else None
        visited: set[str] = set()
        while cursor is not None:
            cursor_id = str(cursor["location_id"])
            if cursor_id == target_location_id or cursor_id in visited:
                raise _location_error(
                    "LOCATION_HIERARCHY_INVALID",
                    "地点父级不能自引用或形成环",
                    field_errors={"parent_location_id": "父级形成环"},
                )
            visited.add(cursor_id)
            next_parent_id = cursor.get("parent_location_id")
            if next_parent_id is None:
                return
            try:
                cursor = await location_repo.get_location(
                    novel_id,
                    str(next_parent_id),
                    session=session,
                )
            except (NotFoundError, InvalidIdError) as exc:
                raise _location_error(
                    "LOCATION_REFERENCE_NOT_FOUND",
                    "地点父链包含不存在、已删除或跨小说地点",
                    status_code=404,
                ) from exc
            if cursor.get("status") != "active":
                raise _location_error(
                    "LOCATION_REFERENCE_NOT_FOUND",
                    "地点父链包含已停用地点",
                    status_code=404,
                )

    @staticmethod
    async def _get_delete_impact(
        novel_id: str,
        location_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """在同一读取上下文统计直接子级和正式消费者。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 待删除地点 ID。
            session: 可选 MongoDB 会话。

        Returns:
            可直接序列化为 LocationDeleteImpactV1 的影响清单。
        """
        active_children = [
            item
            for item in await location_repo.list_direct_children(
                novel_id,
                location_id,
                session=session,
            )
            if item.get("location_order_pending_token") is None
        ]
        all_children = [
            item
            for item in await location_repo.list_direct_children(
                novel_id,
                location_id,
                include_deleted=True,
                session=session,
            )
            if item.get("location_order_pending_token") is None
        ]
        deleted_count = sum(bool(item["is_deleted"]) for item in all_children)
        references = await location_repo.count_protected_references(
            novel_id,
            location_id,
            session=session,
        )
        total = int(references.pop("total"))
        return {
            "location_id": location_id,
            "direct_child_location_ids": [
                str(item["location_id"]) for item in active_children
            ],
            "active_direct_children": len(active_children),
            "deleted_direct_children": deleted_count,
            **references,
            "total_protected_references": total,
            "has_children": bool(active_children or deleted_count),
            "has_protected_references": total > 0,
        }

    @staticmethod
    async def list_locations(
        novel_id: str,
        *,
        q: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        parent_location_id: str | None = None,
        associated_faction_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按小说及筛选读取全部未删除地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选搜索词。
            location_type: 可选地点类型。
            status: 可选 active|inactive。
            parent_location_id: 可选父地点 ID；空字符串表示根级。
            associated_faction_id: 可选关联势力 ID。

        Returns:
            符合筛选条件的未删除地点列表。
        """
        read_revision = await LocationService._check_public_read_fence(novel_id)
        locations = await location_repo.list_locations(
            novel_id,
            q=q,
            location_type=location_type,
            status=status,
            parent_location_id=parent_location_id,
            associated_faction_id=associated_faction_id,
        )
        # standalone 创建先写正式文档再完成顺序核验，公共列表不得泄露该短暂中间态。
        result = [
            item
            for item in locations
            if not item.get("location_order_pending_token")
        ]
        await LocationService._check_public_read_fence(
            novel_id,
            expected_revision=read_revision,
        )
        return result

    @staticmethod
    async def list_deleted_locations(
        novel_id: str,
        *,
        q: str | None = None,
        location_type: str | None = None,
        status: str | None = None,
        parent_location_id: str | None = None,
        associated_faction_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按小说及筛选读取地点回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选搜索词。
            location_type: 可选地点类型。
            status: 可选正式状态。
            parent_location_id: 可选原父地点 ID。
            associated_faction_id: 可选关联势力 ID。

        Returns:
            符合筛选条件的回收站地点列表。
        """
        read_revision = await LocationService._check_public_read_fence(novel_id)
        result = await location_repo.list_deleted_locations(
            novel_id,
            q=q,
            location_type=location_type,
            status=status,
            parent_location_id=parent_location_id,
            associated_faction_id=associated_faction_id,
        )
        await LocationService._check_public_read_fence(
            novel_id,
            expected_revision=read_revision,
        )
        return result

    @staticmethod
    async def get_location(novel_id: str, location_id: str) -> dict[str, Any]:
        """读取小说内一条未删除地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。

        Returns:
            匹配的完整正式地点。
        """
        read_revision = await LocationService._check_public_read_fence(novel_id)
        result = await LocationService._get_location(
            novel_id,
            location_id,
            deleted=False,
            expected_version=None,
            session=None,
        )
        await LocationService._check_public_read_fence(
            novel_id,
            expected_revision=read_revision,
        )
        return result

    @staticmethod
    async def get_delete_impact(
        novel_id: str,
        location_id: str,
    ) -> dict[str, Any]:
        """读取地点软删或永久删除前的当前影响。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。

        Returns:
            子级和正式消费者的精确分项统计。
        """
        read_revision = await LocationService._check_public_read_fence(novel_id)
        try:
            location = await location_repo.get_location(
                novel_id,
                location_id,
                include_deleted=True,
            )
        except (NotFoundError, InvalidIdError) as exc:
            raise _location_error(
                "LOCATION_NOT_FOUND",
                "地点不存在或不属于当前小说",
                status_code=404,
                details={"location_id": location_id},
            ) from exc
        if location.get("location_order_pending_token"):
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点仍由创建命令收口中，请刷新后重试",
                status_code=409,
            )
        result = await LocationService._get_delete_impact(
            novel_id,
            location_id,
            session=None,
        )
        await LocationService._check_public_read_fence(
            novel_id,
            expected_revision=read_revision,
        )
        return result

    @staticmethod
    async def create_location(novel_id: str, data: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """幂等创建一条地点并自动追加到同父末尾。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: LocationCreateV1 或同结构映射。
            idempotency_key: 必填人工创建幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新建或同键重放的完整地点。
        """
        content = _prepare_location_content(data)
        try:
            fingerprint = build_idempotency_fingerprint(
                idempotency_key,
                {"novel_id": novel_id, "location": content},
            )
        except (TypeError, ValueError) as exc:
            raise _location_error(
                "LOCATION_VALIDATION_FAILED",
                str(exc),
                field_errors={"Idempotency-Key": str(exc)},
            ) from exc

        existing = (await location_repo.find_by_creation_idempotency(
            novel_id,
            fingerprint.key_hash,
        )) if session is None else None
        try:
            replay = resolve_idempotent_replay(
                existing,
                fingerprint.request_hash,
                label="地点创建",
            )
        except IdempotencyConflictError as exc:
            raise _location_error(
                "IDEMPOTENCY_KEY_REUSED",
                str(exc),
                status_code=409,
            ) from exc
        if replay is not None:
            await LocationService._get_novel(novel_id, session=None)
            await _finish_stored_novel_write_lock(
                novel_id,
                replay,
                session=None,
            )
            return replay

        document_id = ObjectId()

        async def create(session: AsyncClientSession | None) -> dict[str, Any]:
            await LocationService._get_novel(novel_id, session=session)
            replay_in_unit = await location_repo.find_by_creation_idempotency(
                novel_id,
                fingerprint.key_hash,
                session=session,
            )
            try:
                resolved = resolve_idempotent_replay(
                    replay_in_unit,
                    fingerprint.request_hash,
                    label="地点创建",
                )
            except IdempotencyConflictError as exc:
                raise _location_error(
                    "IDEMPOTENCY_KEY_REUSED",
                    str(exc),
                    status_code=409,
                ) from exc
            if resolved is not None:
                await _finish_stored_novel_write_lock(
                    novel_id,
                    resolved,
                    session=session,
                )
                return resolved

            parent, rules, factions = await LocationService._load_dependencies(
                novel_id,
                parent_location_id=content["parent_location_id"],
                rule_ids=content["applicable_rule_ids"],
                faction_ids=content["associated_faction_ids"],
                session=session,
            )
            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )
            created: dict[str, Any] | None = None
            committed = False
            try:
                # 互斥取得后重新读取依赖，避免把锁前的父级可用性当作写入事实。
                parent, rules, factions = await LocationService._load_dependencies(
                    novel_id,
                    parent_location_id=content["parent_location_id"],
                    rule_ids=content["applicable_rule_ids"],
                    faction_ids=content["associated_faction_ids"],
                    session=session,
                )
                await LocationService._ensure_name_available(
                    novel_id,
                    content["parent_location_id"],
                    content["normalized_name"],
                    exclude_location_id=None,
                    session=session,
                )
                siblings = await location_repo.list_siblings(
                    novel_id,
                    content["parent_location_id"],
                    session=session,
                )
                _ensure_sibling_group_ready(siblings)
                pending_token = str(novel_lock["location_write_lock_token"])
                now = _mongo_write_time()
                document = {
                    **content,
                    "_id": document_id,
                    "novel_id": novel_id,
                    "location_id": (
                        await id_sequence_repo.allocate_many(
                            novel_id,
                            "location",
                            "loc",
                            1,
                            session=session,
                        )
                    )[0],
                    "order_index": len(siblings) + 1,
                    "created_at": now,
                    "updated_at": now,
                    "location_order_pending_token": pending_token,
                    "location_creation_lock_token": pending_token,
                    "location_creation_lock_revision": int(
                        novel_lock["location_write_lock_revision"]
                    ),
                    **fingerprint.as_creation_fields(),
                }
                try:
                    created = await location_repo.create_location(document, session=session)
                except Exception:
                    if session is None:
                        current = await location_repo.collection.find_one(
                            {"_id": document_id}
                        )
                        expected = {
                            **document,
                            "novel_id": to_object_id(novel_id),
                            "version": 1,
                            "dependency_guard_revision": 0,
                            "location_order_pending_token": pending_token,
                            "is_deleted": False,
                            "deleted_at": None,
                            "detached_parent_location_id": None,
                        }
                        if current == expected:
                            created = current
                        else:
                            raise
                    else:
                        raise
                await LocationService._touch_dependency_documents(
                    rules,
                    factions,
                    session=session,
                )
                if created is None:
                    raise RuntimeError("地点创建未返回正式写后镜像")
                await LocationService._get_novel(novel_id, session=session)
                await _assert_sibling_groups(
                    novel_id,
                    {
                        content["parent_location_id"]: [
                            *[
                                (
                                    str(item["location_id"]),
                                    int(item["order_index"]),
                                    int(item["version"]),
                                )
                                for item in siblings
                            ],
                            (
                                str(created["location_id"]),
                                int(created["order_index"]),
                                int(created["version"]),
                            ),
                        ]
                    },
                    session=session,
                )
                published = await _publish_created_location(
                    created,
                    pending_token,
                    session=session,
                )
                created = published
                await _assert_sibling_groups(
                    novel_id,
                    {
                        content["parent_location_id"]: [
                            *[
                                (
                                    str(item["location_id"]),
                                    int(item["order_index"]),
                                    int(item["version"]),
                                )
                                for item in siblings
                            ],
                            (
                                str(created["location_id"]),
                                int(created["order_index"]),
                                int(created["version"]),
                            ),
                        ]
                    },
                    session=session,
                )
                committed = True
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                return created
            except Exception:
                if session is None and not committed:
                    if created is not None:
                        try:
                            await location_repo.delete_manual_created_exact(
                                document_id,
                                key_hash=fingerprint.key_hash,
                                request_hash=fingerprint.request_hash,
                                pending_token=pending_token,
                            )
                        except Exception:
                            pass
                        if await location_repo.collection.count_documents(
                            {"_id": document_id}
                        ):
                            raise _location_error(
                                "LOCATION_COMPENSATION_FAILED",
                                "地点创建失败，且新地点补偿未完整完成",
                                status_code=503,
                            )
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                raise

        if session is not None:
            return await create(session)

        try:
            return await run_mongo_write_unit(create, "create_location")
        except DuplicateKeyError as exc:
            winner = await location_repo.find_by_creation_idempotency(
                novel_id,
                fingerprint.key_hash,
            )
            try:
                replay = resolve_idempotent_replay(
                    winner,
                    fingerprint.request_hash,
                    label="地点创建",
                )
            except IdempotencyConflictError as conflict:
                raise _location_error(
                    "IDEMPOTENCY_KEY_REUSED",
                    str(conflict),
                    status_code=409,
                ) from conflict
            if replay is not None:
                await LocationService._get_novel(novel_id, session=None)
                await _finish_stored_novel_write_lock(
                    novel_id,
                    replay,
                    session=None,
                )
                return replay
            same_name = await location_repo.find_active_by_parent_and_name(
                novel_id,
                content["parent_location_id"],
                content["normalized_name"],
            )
            if same_name is not None:
                raise _location_error(
                    "LOCATION_NAME_CONFLICT",
                    "同一父级下已存在规范同名地点",
                    status_code=409,
                ) from exc
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点自动追加发生并发顺序冲突，请刷新后重试",
                status_code=409,
            ) from exc

    @staticmethod
    async def update_location(novel_id: str, location_id: str, data: Any, *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """以 CAS 更新地点内容，并在改父时维护两组连续顺序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            data: 含 expected_version 的 LocationUpdateV1 或映射。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            目标地点递增一次版本后的完整镜像。
        """
        expected, fields = _prepare_location_update(data)

        async def update(session: AsyncClientSession | None) -> dict[str, Any]:
            await LocationService._get_novel(novel_id, session=session)
            current = await LocationService._get_location(
                novel_id,
                location_id,
                deleted=False,
                expected_version=expected,
                session=session,
            )
            merged = {
                field: deepcopy(fields.get(field, current[field]))
                for field in LocationCreateV1.model_fields
            }
            # 复用完整创建 DTO 对更新后的最终聚合做一次业务组合校验。
            normalized = _prepare_location_content(merged)
            next_parent_id = normalized["parent_location_id"]
            parent, rules, factions = await LocationService._load_dependencies(
                novel_id,
                parent_location_id=next_parent_id,
                rule_ids=normalized["applicable_rule_ids"],
                faction_ids=normalized["associated_faction_ids"],
                session=session,
            )
            await LocationService._ensure_no_cycle(
                novel_id,
                location_id,
                parent,
                session=session,
            )
            await LocationService._ensure_name_available(
                novel_id,
                next_parent_id,
                normalized["normalized_name"],
                exclude_location_id=location_id,
                session=session,
            )
            children = await location_repo.list_direct_children(
                novel_id,
                location_id,
                session=session,
            )
            _ensure_sibling_group_ready(children)
            if (
                normalized["status"] == "inactive"
                and current["status"] != "inactive"
                and children
            ):
                impact = await LocationService._get_delete_impact(
                    novel_id,
                    location_id,
                    session=session,
                )
                raise _location_error(
                    "LOCATION_CHILDREN_CONFLICT",
                    "存在活动直接子地点时不能停用父地点",
                    status_code=409,
                    details={"impact": impact},
                )

            parent_changed = next_parent_id != current.get("parent_location_id")
            affected_groups: list[str | None] = []
            if parent_changed:
                affected_groups.extend(
                    [current.get("parent_location_id"), next_parent_id]
                )
            if normalized["status"] == "inactive" and current["status"] != "inactive":
                affected_groups.append(location_id)
            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                # 小说级互斥取得后，目标和依赖仍须以当前 CAS 镜像重新验证。
                current = await LocationService._get_location(
                    novel_id,
                    location_id,
                    deleted=False,
                    expected_version=expected,
                    session=session,
                )
                parent, rules, factions = await LocationService._load_dependencies(
                    novel_id,
                    parent_location_id=next_parent_id,
                    rule_ids=normalized["applicable_rule_ids"],
                    faction_ids=normalized["associated_faction_ids"],
                    session=session,
                )
                await LocationService._ensure_no_cycle(
                    novel_id,
                    location_id,
                    parent,
                    session=session,
                )
                await LocationService._ensure_name_available(
                    novel_id,
                    next_parent_id,
                    normalized["normalized_name"],
                    exclude_location_id=location_id,
                    session=session,
                )
                children = await location_repo.list_direct_children(
                    novel_id,
                    location_id,
                    session=session,
                )
                _ensure_sibling_group_ready(children)
                if (
                    normalized["status"] == "inactive"
                    and current["status"] != "inactive"
                    and children
                ):
                    impact = await LocationService._get_delete_impact(
                        novel_id,
                        location_id,
                        session=session,
                    )
                    raise _location_error(
                        "LOCATION_CHILDREN_CONFLICT",
                        "存在活动直接子地点时不能停用父地点",
                        status_code=409,
                        details={"impact": impact},
                    )

                update_fields = {
                    key: value
                    for key, value in normalized.items()
                    if key in fields
                    or (key == "normalized_name" and "name" in fields)
                }
                if "parent_location_id" in fields:
                    update_fields["detached_parent_location_id"] = None
                expected_groups: dict[
                    str | None,
                    list[tuple[str, int, int]],
                ] = {}
                if not parent_changed:
                    result = await _apply_location_change(
                        current,
                        update_fields,
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="地点更新期间已被其他请求修改",
                    )
                    if location_id in affected_groups:
                        expected_groups[location_id] = [
                            (
                                str(child["location_id"]),
                                int(child["order_index"]),
                                int(child["version"]),
                            )
                            for child in children
                        ]
                else:
                    old_siblings = await location_repo.list_siblings(
                        novel_id,
                        current.get("parent_location_id"),
                        session=session,
                    )
                    new_siblings = await location_repo.list_siblings(
                        novel_id,
                        next_parent_id,
                        session=session,
                    )
                    _ensure_sibling_group_ready(old_siblings)
                    _ensure_sibling_group_ready(new_siblings)
                    staged = await _apply_location_change(
                        current,
                        {"order_index": -1},
                        increment_version=False,
                        changes=changes,
                        session=session,
                        conflict_message="地点改父期间目标已变化",
                        compensation_before=current,
                    )
                    compacted_by_id: dict[str, dict[str, Any]] = {}
                    for sibling in old_siblings:
                        if int(sibling["order_index"]) <= int(current["order_index"]):
                            continue
                        compacted = await _apply_location_change(
                            sibling,
                            {"order_index": int(sibling["order_index"]) - 1},
                            increment_version=True,
                            changes=changes,
                            session=session,
                            conflict_message="地点改父期间原兄弟集合已变化",
                        )
                        compacted_by_id[str(compacted["location_id"])] = compacted
                        if (
                            parent is not None
                            and parent["location_id"] == compacted["location_id"]
                        ):
                            parent = compacted
                    result = await _apply_location_change(
                        staged,
                        {
                            **update_fields,
                            "parent_location_id": next_parent_id,
                            "order_index": len(new_siblings) + 1,
                            "detached_parent_location_id": None,
                        },
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="地点改父期间新兄弟集合已变化",
                        compensation_before=current,
                    )
                    expected_groups[current.get("parent_location_id")] = [
                        (
                            str(sibling["location_id"]),
                            int(
                                compacted_by_id.get(
                                    str(sibling["location_id"]),
                                    sibling,
                                )["order_index"]
                            ),
                            int(
                                compacted_by_id.get(
                                    str(sibling["location_id"]),
                                    sibling,
                                )["version"]
                            ),
                        )
                        for sibling in old_siblings
                        if sibling["location_id"] != location_id
                    ]
                    expected_groups[next_parent_id] = [
                        *[
                            (
                                str(sibling["location_id"]),
                                int(sibling["order_index"]),
                                int(sibling["version"]),
                            )
                            for sibling in new_siblings
                        ],
                        (
                            str(result["location_id"]),
                            int(result["order_index"]),
                            int(result["version"]),
                        ),
                    ]
                if location_id in affected_groups:
                    expected_groups[location_id] = [
                        (
                            str(child["location_id"]),
                            int(child["order_index"]),
                            int(child["version"]),
                        )
                        for child in children
                    ]
                await LocationService._touch_dependency_documents(
                    rules,
                    factions,
                    session=session,
                )
                await LocationService._get_novel(novel_id, session=session)
                if expected_groups:
                    await _assert_sibling_groups(
                        novel_id,
                        expected_groups,
                        session=session,
                    )
                committed = True
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                return result
            except Exception:
                if session is None and not committed:
                    await _compensate_location_changes(changes)
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                raise

        if session is not None:
            return await update(session)

        try:
            return await run_mongo_write_unit(update, "update_location")
        except DuplicateKeyError as exc:
            raise _location_error(
                "LOCATION_NAME_OR_ORDER_CONFLICT",
                "地点更新与同父规范名或顺序冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def reorder_locations(novel_id: str, parent_location_id: str | None, items: Sequence[Mapping[str, Any]], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """提交完整同父活动集合并执行 1-based CAS 重排。

        Args:
            novel_id: 小说 ObjectId 字符串。
            parent_location_id: 本次重排父级；根级为 None。
            items: 含 location_id、order_index、expected_version 的完整集合。

            session: 调用方事务；提供时不另开事务。

        Returns:
            按新顺序排列且每条恰好递增一次版本的完整兄弟集合。
        """
        requested_ids = [str(item["location_id"]) for item in items]
        requested_orders = [int(item["order_index"]) for item in items]
        if (
            not items
            or len(requested_ids) != len(set(requested_ids))
            or sorted(requested_orders) != list(range(1, len(items) + 1))
        ):
            raise _location_error(
                "LOCATION_REORDER_INVALID",
                "地点重排必须提交 ID 唯一且顺序完整的 1..N 集合",
            )
        await LocationService._get_novel(novel_id, session=session)
        if parent_location_id is not None:
            try:
                parent = await location_repo.get_location(novel_id, parent_location_id, session=session)
            except (NotFoundError, InvalidIdError) as exc:
                raise _location_error(
                    "LOCATION_REFERENCE_NOT_FOUND",
                    "重排父地点不存在、已删除或跨小说",
                    status_code=404,
                ) from exc
            if parent.get("status") != "active":
                raise _location_error(
                    "LOCATION_REFERENCE_NOT_FOUND",
                    "重排父地点当前不可用",
                    status_code=404,
                )
            if parent.get("location_order_pending_token") is not None:
                raise _location_error(
                    "LOCATION_REFERENCE_NOT_FOUND",
                    "重排父地点当前不可用",
                    status_code=404,
                )
        initial = await location_repo.list_siblings(novel_id, parent_location_id, session=session)
        _ensure_sibling_group_ready(initial)
        await _assert_reorder_members(
            novel_id,
            parent_location_id,
            requested_ids,
            initial,
            session=session,
        )

        async def reorder(session: AsyncClientSession | None) -> list[dict[str, Any]]:
            await LocationService._get_novel(novel_id, session=session)
            if parent_location_id is not None:
                try:
                    parent = await location_repo.get_location(
                        novel_id,
                        parent_location_id,
                        session=session,
                    )
                except (NotFoundError, InvalidIdError) as exc:
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "重排父地点不存在、已删除或跨小说",
                        status_code=404,
                    ) from exc
                if (
                    parent.get("status") != "active"
                    or parent.get("location_order_pending_token") is not None
                ):
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "重排父地点当前不可用",
                        status_code=404,
                    )
            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            staged: dict[str, dict[str, Any]] = {}
            try:
                siblings = await location_repo.list_siblings(
                    novel_id,
                    parent_location_id,
                    session=session,
                )
                _ensure_sibling_group_ready(siblings)
                await _assert_reorder_members(
                    novel_id,
                    parent_location_id,
                    requested_ids,
                    siblings,
                    session=session,
                )
                by_id = {item["location_id"]: item for item in siblings}
                for item in items:
                    current = by_id[str(item["location_id"])]
                    if int(current["version"]) != validate_expected_version(
                        item["expected_version"]
                    ):
                        raise _location_error(
                            "LOCATION_VERSION_CONFLICT",
                            f"地点 {item['location_id']} 版本冲突",
                            status_code=409,
                        )
                for offset, location_id in enumerate(requested_ids):
                    current = by_id[location_id]
                    staged[location_id] = await _apply_location_change(
                        current,
                        {"order_index": -1_000_000 - offset},
                        increment_version=False,
                        changes=changes,
                        session=session,
                        conflict_message="地点重排期间兄弟已变化",
                        compensation_before=current,
                    )
                updated: list[dict[str, Any]] = []
                for item in sorted(items, key=lambda value: int(value["order_index"])):
                    location_id = str(item["location_id"])
                    updated.append(
                        await _apply_location_change(
                            staged[location_id],
                            {"order_index": int(item["order_index"])},
                            increment_version=True,
                            changes=changes,
                            session=session,
                            conflict_message="地点重排写回期间兄弟已变化",
                            compensation_before=by_id[location_id],
                        )
                    )
                await LocationService._get_novel(novel_id, session=session)
                await _assert_sibling_groups(
                    novel_id,
                    {
                        parent_location_id: [
                            (
                                str(item["location_id"]),
                                int(item["order_index"]),
                                int(item["version"]),
                            )
                            for item in updated
                        ]
                    },
                    session=session,
                )
                committed = True
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                return updated
            except Exception:
                if session is None and not committed:
                    await _compensate_location_changes(changes)
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                raise

        if session is not None:
            return await reorder(session)

        try:
            return await run_mongo_write_unit(reorder, "reorder_locations")
        except DuplicateKeyError as exc:
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点重排发生顺序或并发冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def soft_delete_location(novel_id: str, location_id: str, *, expected_version: int, detach_children: bool, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """软删除地点，并仅在明确确认时断开直接活动子级。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            expected_version: 调用方持有的公开版本。
            detach_children: 是否明确把直接活动子级移动到根级。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已进入回收站且递增一次版本的目标地点。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession | None) -> dict[str, Any]:
            await LocationService._get_novel(novel_id, session=session)
            current = await LocationService._get_location(
                novel_id,
                location_id,
                deleted=False,
                expected_version=expected,
                session=session,
            )
            impact = await LocationService._get_delete_impact(
                novel_id,
                location_id,
                session=session,
            )
            if impact["active_direct_children"] and not detach_children:
                raise _location_error(
                    "LOCATION_CHILDREN_CONFLICT",
                    "父地点仍有直接子级；只有明确确认后才能断开子级并删除",
                    status_code=409,
                    details={"impact": impact},
                )
            siblings = await location_repo.list_siblings(
                novel_id,
                current.get("parent_location_id"),
                session=session,
            )
            children = await location_repo.list_direct_children(
                novel_id,
                location_id,
                session=session,
            )
            root_siblings = await location_repo.list_siblings(
                novel_id,
                None,
                session=session,
            )
            _ensure_sibling_group_ready(siblings)
            _ensure_sibling_group_ready(children)
            _ensure_sibling_group_ready(root_siblings)
            if children:
                surviving_root = [
                    item
                    for item in root_siblings
                    if item["location_id"] != location_id
                ]
                root_names = {item["normalized_name"] for item in surviving_root}
                child_names = [item["normalized_name"] for item in children]
                if root_names & set(child_names) or len(child_names) != len(set(child_names)):
                    raise _location_error(
                        "LOCATION_NAME_CONFLICT",
                        "断开子级后会与根级地点规范名冲突",
                        status_code=409,
                    )

            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )

            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                current = await LocationService._get_location(
                    novel_id,
                    location_id,
                    deleted=False,
                    expected_version=expected,
                    session=session,
                )
                impact = await LocationService._get_delete_impact(
                    novel_id,
                    location_id,
                    session=session,
                )
                if impact["active_direct_children"] and not detach_children:
                    raise _location_error(
                        "LOCATION_CHILDREN_CONFLICT",
                        "父地点仍有直接子级；只有明确确认后才能断开子级并删除",
                        status_code=409,
                        details={"impact": impact},
                    )
                siblings = await location_repo.list_siblings(
                    novel_id,
                    current.get("parent_location_id"),
                    session=session,
                )
                children = await location_repo.list_direct_children(
                    novel_id,
                    location_id,
                    session=session,
                )
                root_siblings = await location_repo.list_siblings(
                    novel_id,
                    None,
                    session=session,
                )
                _ensure_sibling_group_ready(siblings)
                _ensure_sibling_group_ready(children)
                _ensure_sibling_group_ready(root_siblings)
                if children:
                    surviving_root = [
                        item
                        for item in root_siblings
                        if item["location_id"] != location_id
                    ]
                    root_names = {
                        item["normalized_name"] for item in surviving_root
                    }
                    child_names = [item["normalized_name"] for item in children]
                    if root_names & set(child_names) or len(child_names) != len(
                        set(child_names)
                    ):
                        raise _location_error(
                            "LOCATION_NAME_CONFLICT",
                            "断开子级后会与根级地点规范名冲突",
                            status_code=409,
                        )
                deleted = await _apply_location_change(
                    current,
                    {"is_deleted": True, "deleted_at": _mongo_write_time()},
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="地点删除期间已被其他请求修改或新增依赖",
                )
                compacted_by_id: dict[str, dict[str, Any]] = {}
                for sibling in siblings:
                    if int(sibling["order_index"]) <= int(current["order_index"]):
                        continue
                    compacted = await _apply_location_change(
                        sibling,
                        {"order_index": int(sibling["order_index"]) - 1},
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="地点删除期间原兄弟集合已变化",
                    )
                    compacted_by_id[str(compacted["location_id"])] = compacted
                # 根级目标删除后自身不再占用顺序；子级应接在其余根地点之后。
                root_tail = len(
                    [
                        item
                        for item in root_siblings
                        if item["location_id"] != location_id
                    ]
                )
                moved_children: list[dict[str, Any]] = []
                for offset, child in enumerate(children, start=1):
                    moved_children.append(await _apply_location_change(
                        child,
                        {
                            "parent_location_id": None,
                            "detached_parent_location_id": location_id,
                            "order_index": root_tail + offset,
                        },
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="断开直接子地点期间子级已变化",
                    ))
                surviving_old = [
                    compacted_by_id.get(str(item["location_id"]), item)
                    for item in siblings
                    if item["location_id"] != location_id
                ]
                expected_groups: dict[
                    str | None,
                    list[tuple[str, int, int]],
                ] = {
                    current.get("parent_location_id"): [
                        (
                            str(item["location_id"]),
                            int(item["order_index"]),
                            int(item["version"]),
                        )
                        for item in surviving_old
                    ],
                    location_id: [],
                }
                if children:
                    if current.get("parent_location_id") is None:
                        root_after = [*surviving_old, *moved_children]
                    else:
                        root_after = [*root_siblings, *moved_children]
                    expected_groups[None] = [
                        (
                            str(item["location_id"]),
                            int(item["order_index"]),
                            int(item["version"]),
                        )
                        for item in root_after
                    ]
                await LocationService._get_novel(novel_id, session=session)
                await _assert_sibling_groups(
                    novel_id,
                    expected_groups,
                    session=session,
                )
                committed = True
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                return deleted
            except Exception:
                if session is None and not committed:
                    await _compensate_location_changes(changes)
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                raise

        if session is not None:
            return await delete(session)

        try:
            return await run_mongo_write_unit(delete, "soft_delete_location")
        except DuplicateKeyError as exc:
            raise _location_error(
                "LOCATION_ORDER_CONFLICT",
                "地点删除或子级断开发生名称、顺序或并发冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def restore_location(novel_id: str, location_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """恢复回收站地点并追加到其当前父级末尾。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            expected_version: 调用方持有的回收站版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已恢复且递增一次版本的目标地点；不会重新挂接历史子级。
        """
        expected = validate_expected_version(expected_version)

        async def restore(session: AsyncClientSession | None) -> dict[str, Any]:
            await LocationService._get_novel(novel_id, session=session)
            current = await LocationService._get_location(
                novel_id,
                location_id,
                deleted=True,
                expected_version=expected,
                session=session,
            )
            parent, rules, factions = await LocationService._load_dependencies(
                novel_id,
                parent_location_id=current.get("parent_location_id"),
                rule_ids=current["applicable_rule_ids"],
                faction_ids=current["associated_faction_ids"],
                session=session,
            )
            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                current = await LocationService._get_location(
                    novel_id,
                    location_id,
                    deleted=True,
                    expected_version=expected,
                    session=session,
                )
                parent, rules, factions = await LocationService._load_dependencies(
                    novel_id,
                    parent_location_id=current.get("parent_location_id"),
                    rule_ids=current["applicable_rule_ids"],
                    faction_ids=current["associated_faction_ids"],
                    session=session,
                )
                await LocationService._ensure_no_cycle(
                    novel_id,
                    location_id,
                    parent,
                    session=session,
                )
                await LocationService._ensure_name_available(
                    novel_id,
                    current.get("parent_location_id"),
                    current["normalized_name"],
                    exclude_location_id=location_id,
                    session=session,
                )
                siblings = await location_repo.list_siblings(
                    novel_id,
                    current.get("parent_location_id"),
                    session=session,
                )
                _ensure_sibling_group_ready(siblings)
                restored = await _apply_location_change(
                    current,
                    {
                        "is_deleted": False,
                        "deleted_at": None,
                        "order_index": len(siblings) + 1,
                    },
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="地点恢复期间已被其他请求修改",
                )
                await LocationService._touch_dependency_documents(
                    rules,
                    factions,
                    session=session,
                )
                await LocationService._get_novel(novel_id, session=session)
                await _assert_sibling_groups(
                    novel_id,
                    {
                        current.get("parent_location_id"): [
                            *[
                                (
                                    str(item["location_id"]),
                                    int(item["order_index"]),
                                    int(item["version"]),
                                )
                                for item in siblings
                            ],
                            (
                                str(restored["location_id"]),
                                int(restored["order_index"]),
                                int(restored["version"]),
                            ),
                        ]
                    },
                    session=session,
                )
                committed = True
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                return restored
            except Exception:
                if session is None and not committed:
                    await _compensate_location_changes(changes)
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                raise

        if session is not None:
            return await restore(session)

        try:
            return await run_mongo_write_unit(restore, "restore_location")
        except DuplicateKeyError as exc:
            raise _location_error(
                "LOCATION_RESTORE_CONFLICT",
                "地点恢复与同父规范名或顺序冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def hard_delete_location(
        novel_id: str,
        location_id: str,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        """永久删除没有任何子级或活动正式消费者的回收站地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            location_id: 稳定地点 ID。
            expected_version: 调用方持有的回收站版本。

        Returns:
            被删除地点 ID 和最终全零影响清单。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession | None) -> dict[str, Any]:
            # 同时涉及两类互斥时固定先取得物品锁，避免与物品来源校验交叉等待。
            item_lock = await acquire_item_write_lock(novel_id, session=session)
            try:
                novel_lock = await _acquire_novel_write_lock(
                    novel_id,
                    session=session,
                )
                committed = False
                try:
                    current = await LocationService._get_location(
                        novel_id,
                        location_id,
                        deleted=True,
                        expected_version=expected,
                        session=session,
                    )
                    if await location_repo.count_pending_item_references(
                        novel_id,
                        location_id,
                        session=session,
                    ):
                        # 待发布物品不是公开事实，只阻断删除而不计入公开影响。
                        raise _location_error(
                            "LOCATION_ITEM_WRITE_CONFLICT",
                            "物品写入正在使用该地点，请稍后重试",
                            status_code=409,
                        )
                    impact = await LocationService._get_delete_impact(
                        novel_id,
                        location_id,
                        session=session,
                    )
                    if impact["has_children"] or impact["has_protected_references"]:
                        raise _location_error(
                            "LOCATION_REFERENCE_PROTECTED",
                            "地点仍有子级或活动正式消费者，不能永久删除",
                            status_code=409,
                            details={"impact": impact},
                        )
                    try:
                        deleted = await location_repo.hard_delete_location(
                            current,
                            session=session,
                        )
                    except Exception:
                        if session is None:
                            still_exists = await location_repo.collection.find_one(
                                {"_id": current["_id"]}
                            )
                            if still_exists is None:
                                deleted = True
                            else:
                                raise
                        else:
                            raise
                    if not deleted:
                        raise _location_error(
                            "LOCATION_VERSION_CONFLICT",
                            "地点永久删除期间已被其他请求修改或新增依赖",
                            status_code=409,
                        )
                    committed = True
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=session,
                    )
                    return {"location_id": location_id, "impact": impact}
                except Exception:
                    if session is None and not committed:
                        await _release_novel_write_lock(
                            novel_id,
                            novel_lock,
                            session=None,
                        )
                    raise
            finally:
                await release_item_write_lock(
                    novel_id,
                    item_lock,
                    session=session,
                )

        return await run_mongo_write_unit(delete, "hard_delete_location")

    @staticmethod
    async def _validate_bulk_basis_sources(
        novel_id: str,
        request: LocationBulkGeneratedRequestV1,
        *,
        session: AsyncClientSession | None,
    ) -> None:
        """重读地点确认 basis 来源，并复核 WLD-05 专属输入指纹。

        Args:
            novel_id: 当前小说 ObjectId 字符串。
            request: 严格批量确认请求。
            session: 可选 MongoDB 会话。

        Returns:
            所有来源仍存在、同书且版本一致时返回 None。
        """
        await LocationService._get_novel(novel_id, session=session)
        if request.basis.novel_id != novel_id:
            raise _location_error(
                "LOCATION_BASIS_CONFLICT",
                "地点 basis 不属于当前小说",
                status_code=409,
            )
        novel_sources = [
            source
            for source in request.basis.source_refs
            if source.resource_type == "novel" and source.id == novel_id
        ]
        if len(novel_sources) != 1:
            raise _location_error(
                "LOCATION_BASIS_CONFLICT",
                "地点 basis 必须精确包含当前小说来源",
                status_code=409,
            )
        business_sources = {
            "world_rule": ("world_rules", "rule_id"),
            "location": ("locations", "location_id"),
            "character": ("characters", "character_id"),
            "faction": ("factions", "faction_id"),
            "character_relation": ("character_relations", "relation_id"),
            "faction_relation": ("faction_relations", "relation_id"),
            "character_faction_binding": (
                "character_faction_bindings",
                "binding_id",
            ),
        }
        for source in request.basis.source_refs:
            identity = f"{source.resource_type}:{source.id}"
            if request.expected_versions.get(identity) != source.version:
                raise _location_error(
                    "LOCATION_BASIS_CONFLICT",
                    "expected_versions 与地点 basis 不一致",
                    status_code=409,
                )
            if session is not None:
                # 下方完整卷资料会重读这些来源，并核对集合与内容；不再逐条多读一遍。
                continue
            document: dict[str, Any] | None
            try:
                if source.resource_type == "novel":
                    document = await novel_repo.get_novel_by_id(
                        source.id,
                        session=session,
                    )
                    if source.id != novel_id:
                        document = None
                elif source.resource_type == "volume":
                    document = await volume_repo.get_volume_by_id(
                        source.id,
                        session=session,
                    )
                    if str(document["novel_id"]) != novel_id:
                        document = None
                elif source.resource_type == "character_volume_state":
                    document = await character_volume_state_repo.get_state(
                        novel_id,
                        source.id,
                        session=session,
                    )
                elif source.resource_type == "faction_volume_state":
                    document = await faction_volume_state_repo.get_state(
                        novel_id,
                        source.id,
                        session=session,
                    )
                elif source.resource_type in business_sources:
                    collection_name, id_field = business_sources[source.resource_type]
                    document = await BaseRepository(collection_name).find_one(
                        {
                            "novel_id": to_object_id(novel_id),
                            id_field: source.id,
                        },
                        session=session,
                    )
                    if (
                        source.resource_type == "location"
                        and document is not None
                        and document.get("location_order_pending_token") is not None
                    ):
                        document = None
                else:
                    raise _location_error(
                        "LOCATION_BASIS_SOURCE_INVALID",
                        f"地点 basis 不支持来源类型 {source.resource_type}",
                    )
            except (NotFoundError, InvalidIdError):
                document = None
            if document is None:
                raise _location_error(
                    "LOCATION_BASIS_SOURCE_NOT_FOUND",
                    "地点 basis 中的正式来源已不存在、已删除或跨小说",
                    status_code=404,
                    details={
                        "resource_type": source.resource_type,
                        "id": source.id,
                    },
                )
            auto_preparation = request.basis.generation_input.selection_mode == "auto"
            if not auto_preparation and int(document.get("version", 0)) != int(source.version):
                raise _location_error(
                    "LOCATION_BASIS_CONFLICT",
                    "地点 basis 中的正式来源版本已变化",
                    status_code=409,
                    details={
                        "resource_type": source.resource_type,
                        "id": source.id,
                        "expected_version": source.version,
                        "actual_version": document.get("version"),
                    },
                )

        basis = request.basis
        generation_input = basis.generation_input
        if (
            generation_input.novel_id != novel_id
            or basis.novel_id != novel_id
        ):
            raise _location_error(
                "LOCATION_BASIS_SOURCE_NOT_FOUND",
                "单卷地点候选不属于当前小说",
                status_code=404,
            )
        current_context = await load_volume_location_generation_context(
            generation_input,
            session=session,
        )
        execution = basis.flow_snapshot["execution"]
        original_reads = [*execution["character_fact_reads"], *execution["faction_fact_reads"]]
        if any(read not in original_reads for read in current_context["fact_reads"]):
            raise _location_error("LOCATION_BASIS_CONFLICT", "地点候选缺少当前人物或势力查询的原依据，请保留候选并重新生成", status_code=409)
        submitted_identities = {
            (source.resource_type, source.id) for source in basis.source_refs
        }
        current_identities = {
            (source.resource_type, source.id)
            for source in current_context["source_refs"]
        }
        missing_identities = submitted_identities - current_identities
        if missing_identities:
            resource_type, resource_id = sorted(missing_identities)[0]
            raise _location_error(
                "LOCATION_BASIS_SOURCE_NOT_FOUND",
                "单卷地点生成使用的正式来源已不存在、已删除或不可用",
                status_code=404,
                details={"resource_type": resource_type, "id": resource_id},
            )
        if current_identities - submitted_identities:
            raise _location_error(
                "LOCATION_BASIS_CONFLICT",
                "单卷地点生成使用的正式输入集合已变化，请重新生成",
                status_code=409,
            )
        try:
            if generation_input.selection_mode == "auto":
                from backend.services.task_flows.candidate import compute_preparation_fingerprint
                current_fingerprint = compute_preparation_fingerprint("create_locations_for_volume_by_ai", generation_input, current_context["content_fingerprint"], basis.flow_snapshot)
                if current_context["content_fingerprint"] != basis.content_fingerprint:
                    raise ValueError("地点准备内容已变化")
            else:
                current_fingerprint = compute_volume_locations_input_fingerprint(
                    generation_input,
                    current_context["source_refs"],
                    flow_snapshot=basis.flow_snapshot,
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise _location_error(
                "LOCATION_BASIS_CONFLICT",
                "单卷地点候选的 Prompt、Schema 或执行配置已变化",
                status_code=409,
            ) from exc
        if basis.input_fingerprint != current_fingerprint:
            raise _location_error(
                "LOCATION_BASIS_CONFLICT",
                "单卷地点候选输入已变化，请重新生成",
                status_code=409,
            )

        allowed_location_ids = current_context["allowed_location_ids"]
        allowed_rule_ids = current_context["allowed_rule_ids"]
        allowed_faction_ids = current_context["allowed_faction_ids"]
        for candidate in request.candidates:
            if (
                candidate.parent_location_id is not None
                and candidate.parent_location_id not in allowed_location_ids
            ):
                try:
                    parent = await location_repo.get_location(
                        novel_id,
                        candidate.parent_location_id,
                        session=session,
                    )
                except (NotFoundError, InvalidIdError) as exc:
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选父地点不存在、已删除或不属于当前小说",
                        status_code=404,
                    ) from exc
                if (
                    parent.get("status") != "active"
                    or parent.get("location_order_pending_token") is not None
                ):
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选父地点当前不可用",
                        status_code=404,
                    )
                raise _location_error(
                    "LOCATION_REFERENCE_INVALID",
                    "候选父地点不在生成输入白名单中",
                )
            for rule_id in set(candidate.applicable_rule_ids) - allowed_rule_ids:
                try:
                    rule = await world_rule_repo.get_world_rule(
                        novel_id,
                        rule_id,
                        session=session,
                    )
                except (NotFoundError, InvalidIdError) as exc:
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选规则不存在、已删除或不属于当前小说",
                        status_code=404,
                    ) from exc
                if rule.get("status") != "active":
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选规则当前不可用",
                        status_code=404,
                    )
                raise _location_error(
                    "LOCATION_REFERENCE_INVALID",
                    "候选规则不在生成输入白名单中",
                )
            for faction_id in (
                set(candidate.associated_faction_ids) - allowed_faction_ids
            ):
                try:
                    faction = await faction_repo.get_faction(
                        novel_id,
                        faction_id,
                        session=session,
                    )
                except (NotFoundError, InvalidIdError) as exc:
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选势力不存在、已删除或不属于当前小说",
                        status_code=404,
                    ) from exc
                if faction.get("active_status") != "active":
                    raise _location_error(
                        "LOCATION_REFERENCE_NOT_FOUND",
                        "候选势力当前不可用",
                        status_code=404,
                    )
                raise _location_error(
                    "LOCATION_REFERENCE_INVALID",
                    "候选势力没有进入目标卷的正式参与状态",
                )
        try:
            validate_volume_location_candidates(
                [candidate.model_dump(mode="json") for candidate in request.candidates],
                generation_input,
                current_context,
                require_generated_count=False,
            )
        except ValueError as exc:
            raise _location_error(
                "LOCATION_NAME_CONFLICT",
                str(exc),
                status_code=409,
            ) from exc

    @staticmethod
    async def _load_confirmation_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取并验证地点批量确认不可变回执。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 哈希。
            request_hash: 当前规范请求哈希。
            session: 可选 MongoDB 会话。

        Returns:
            同键同载荷成功回执；该键未使用时返回 None。
        """
        receipt = await location_confirmation_receipt_repo.find_receipt(
            novel_id,
            key_hash,
            session=session,
        )
        if receipt is None:
            return None
        if receipt.get("request_hash") != request_hash:
            raise _location_error(
                "IDEMPOTENCY_KEY_REUSED",
                "同一 Idempotency-Key 已用于不同的地点批量确认",
                status_code=409,
            )
        return receipt

    @staticmethod
    async def _wait_for_confirmation_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        """在同键并发可见窗口内短暂等待成功回执。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: 原始 Idempotency-Key 哈希。
            request_hash: 当前规范请求哈希。

        Returns:
            五秒内可见的同请求回执；超时返回 None。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _LOCATION_CONFIRMATION_REPLAY_WAIT_SECONDS
        while True:
            # 先读后判断截止时间，保证等待结束时还会做最后一次精确读取。
            receipt = await LocationService._load_confirmation_receipt(
                novel_id,
                key_hash,
                request_hash,
            )
            if receipt is not None:
                await LocationService._get_novel(novel_id, session=None)
                await _finish_stored_novel_write_lock(
                    novel_id,
                    receipt,
                    session=None,
                )
                return receipt
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.05, remaining))

    @staticmethod
    async def bulk_create_generated_locations(novel_id: str, request_value: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """按候选拓扑幂等创建一批正式地点。

        Args:
            novel_id: 小说 ObjectId 字符串。
            request_value: LocationBulkGeneratedRequestV1 或同结构映射。
            idempotency_key: 批量确认必填幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            完整 candidate_ref 到 location_id 映射及正式地点快照。
        """
        try:
            request = (
                request_value
                if isinstance(request_value, LocationBulkGeneratedRequestV1)
                else LocationBulkGeneratedRequestV1.model_validate(request_value)
            )
        except ValidationError as exc:
            raise _location_error(
                "LOCATION_VALIDATION_FAILED",
                "地点批量确认字段校验失败",
                field_errors=_validation_details(exc),
            ) from exc
        canonical_request = request.model_dump(mode="json")
        try:
            fingerprint = build_idempotency_fingerprint(
                idempotency_key,
                {"novel_id": novel_id, **canonical_request},
            )
        except (TypeError, ValueError) as exc:
            raise _location_error(
                "LOCATION_VALIDATION_FAILED",
                str(exc),
                field_errors={"Idempotency-Key": str(exc)},
            ) from exc
        replay = (await LocationService._load_confirmation_receipt(
            novel_id,
            fingerprint.key_hash,
            fingerprint.request_hash,
        )) if session is None else None
        if replay is not None:
            await LocationService._get_novel(novel_id, session=None)
            await _finish_stored_novel_write_lock(
                novel_id,
                replay,
                session=None,
            )
            return _receipt_result(replay)

        attempted_ids = [ObjectId() for _ in request.candidates]

        async def confirm(session: AsyncClientSession | None) -> dict[str, Any]:
            replay_in_unit = await LocationService._load_confirmation_receipt(
                novel_id,
                fingerprint.key_hash,
                fingerprint.request_hash,
                session=session,
            )
            if replay_in_unit is not None:
                await LocationService._get_novel(novel_id, session=session)
                await _finish_stored_novel_write_lock(
                    novel_id,
                    replay_in_unit,
                    session=session,
                )
                return _receipt_result(replay_in_unit)
            execution = request.basis.flow_snapshot["execution"]
            if "character_fact_reads" not in execution:
                raise _location_error("CHARACTER_FACT_CONTRACT_REQUIRED", "原地点候选未保存人物事实依据，请保留候选并重新生成", status_code=409)
            if execution.get("faction_reading_contract") != "faction_facts_v1" or "faction_fact_reads" not in execution:
                raise _location_error("FACTION_FACT_CONTRACT_REQUIRED", "原地点候选未保存势力事实依据，请保留候选并重新生成", status_code=409)
            from backend.services.novel.writing_context import revalidate_position_fact_reads
            await revalidate_position_fact_reads([
                *execution["character_fact_reads"], *execution["faction_fact_reads"],
                *execution.get("character_relation_fact_reads", []), *execution.get("item_fact_reads", []),
            ], session=session, protect=True)
            # 同事务先完整复查，再取地点锁；共享人物读取不能越过自己的写锁。
            await LocationService._validate_bulk_basis_sources(novel_id, request, session=session)
            # Agent 检查会拒绝地点写锁；仍在设置自己的锁前重放，全部操作使用同一事务。
            if request.basis.flow_snapshot["execution"].get("agent_reads"):
                from backend.services.task_flows.book_tools import replay_book_reads
                await replay_book_reads(request.basis.flow_snapshot["scope"], request.basis.flow_snapshot["execution"]["agent_reads"], session=session, protect=True)

            candidate_rows: list[dict[str, Any]] = []
            active_locations = (
                await location_repo.list_locations(novel_id, session=session)
                if session is None else []
            )
            existing_names = {
                (item.get("parent_location_id"), item["normalized_name"])
                for item in active_locations
            }
            batch_names: set[tuple[str | None, str]] = set()
            dependency_contexts: list[
                tuple[
                    dict[str, Any] | None,
                    list[dict[str, Any]],
                    list[dict[str, Any]],
                    str | None,
                ]
            ] = []
            for candidate in request.candidates:
                row = candidate.model_dump(mode="json")
                for field in (
                    "name",
                    "location_type",
                    "description",
                    "environment",
                    "atmosphere",
                    "geography",
                    "story_function",
                ):
                    row[field] = _normalize_display_text(row[field])
                for field in ("aliases", "rules_and_constraints", "tags"):
                    row[field] = [
                        _normalize_display_text(item) for item in row[field]
                    ]
                try:
                    row = GeneratedLocationCandidateV1.model_validate(row).model_dump(
                        mode="json"
                    )
                except ValidationError as exc:
                    raise _location_error(
                        "LOCATION_VALIDATION_FAILED",
                        "地点候选规范化后的字段长度或组合不合法",
                        field_errors=_validation_details(exc),
                    ) from exc
                row["normalized_name"] = normalize_location_text(row["name"])
                group_parent = (
                    f"candidate:{row['parent_location_ref']}"
                    if row["parent_location_ref"] is not None
                    else row["parent_location_id"]
                )
                name_key = (group_parent, row["normalized_name"])
                if name_key in batch_names:
                    raise _location_error(
                        "LOCATION_NAME_CONFLICT",
                        "同一父级下的地点候选规范名必须唯一",
                        status_code=409,
                    )
                batch_names.add(name_key)
                if row["parent_location_ref"] is None and (
                    row["parent_location_id"], row["normalized_name"]
                ) in existing_names:
                    raise _location_error(
                        "LOCATION_NAME_CONFLICT",
                        "地点候选与同父现有地点规范名冲突",
                        status_code=409,
                    )
                candidate_rows.append(row)

            if session is None:
                for row in candidate_rows:
                    parent, rules, factions = await LocationService._load_dependencies(
                        novel_id,
                        parent_location_id=(
                            row["parent_location_id"]
                            if row["parent_location_ref"] is None
                            else None
                        ),
                        rule_ids=row["applicable_rule_ids"],
                        faction_ids=row["associated_faction_ids"],
                        session=session,
                    )
                    dependency_contexts.append(
                        (parent, rules, factions, row["parent_location_ref"])
                    )

                # 无事务时，等待写锁期间资料可能变化，仍保留原来的锁前后复查。
                await LocationService._validate_bulk_basis_sources(
                    novel_id,
                    request,
                    session=session,
                )
            novel_lock = await _acquire_novel_write_lock(
                novel_id,
                session=session,
            )
            pending_token = str(novel_lock["location_write_lock_token"])
            created: list[dict[str, Any]] = []
            created_by_ref: dict[str, dict[str, Any]] = {}
            receipt_attempted = False
            committed = False
            try:
                if session is None:
                    await LocationService._get_novel(novel_id, session=session)
                active_locations = await location_repo.list_locations(
                    novel_id,
                    session=session,
                )
                location_ids = await id_sequence_repo.allocate_many(
                    novel_id,
                    "location",
                    "loc",
                    len(candidate_rows),
                    session=session,
                )
                ref_to_id = {
                    row["candidate_ref"]: location_id
                    for row, location_id in zip(
                        candidate_rows,
                        location_ids,
                        strict=True,
                    )
                }
                resolved_parent_ids = [
                    (
                        ref_to_id[row["parent_location_ref"]]
                        if row["parent_location_ref"] is not None
                        else row["parent_location_id"]
                    )
                    for row in candidate_rows
                ]
                affected_group_set = set(resolved_parent_ids)
                _ensure_sibling_group_ready(
                    [
                        item
                        for item in active_locations
                        if item.get("parent_location_id") in affected_group_set
                    ]
                )
                existing_names = {
                    (item.get("parent_location_id"), item["normalized_name"])
                    for item in active_locations
                }
                for row, parent_id in zip(
                    candidate_rows,
                    resolved_parent_ids,
                    strict=True,
                ):
                    if row["parent_location_ref"] is None and (
                        parent_id,
                        row["normalized_name"],
                    ) in existing_names:
                        raise _location_error(
                            "LOCATION_NAME_CONFLICT",
                            "地点候选与同父现有地点规范名冲突",
                            status_code=409,
                        )
                dependency_contexts = []
                if session is not None:
                    # 多个候选常引用同一规则和势力，只读取一次，仍逐一验证其可用性。
                    _, rules, factions = await LocationService._load_dependencies(
                        novel_id,
                        parent_location_id=None,
                        rule_ids=sorted({
                            identity for row in candidate_rows
                            for identity in row["applicable_rule_ids"]
                        }),
                        faction_ids=sorted({
                            identity for row in candidate_rows
                            for identity in row["associated_faction_ids"]
                        }),
                        session=session,
                    )
                    rules_by_id = {item["rule_id"]: item for item in rules}
                    factions_by_id = {item["faction_id"]: item for item in factions}
                    parents_by_id = {None: None}
                    for parent_id in sorted({
                        row["parent_location_id"] for row in candidate_rows
                        if row["parent_location_id"] is not None
                        and row["parent_location_ref"] is None
                    }):
                        parent, _, _ = await LocationService._load_dependencies(
                            novel_id,
                            parent_location_id=parent_id,
                            rule_ids=[],
                            faction_ids=[],
                            session=session,
                        )
                        parents_by_id[parent_id] = parent
                    for row in candidate_rows:
                        dependency_contexts.append((
                            parents_by_id[row["parent_location_id"]]
                            if row["parent_location_ref"] is None else None,
                            [rules_by_id[identity] for identity in row["applicable_rule_ids"]],
                            [factions_by_id[identity] for identity in row["associated_faction_ids"]],
                            row["parent_location_ref"],
                        ))
                else:
                    for row in candidate_rows:
                        parent, rules, factions = await LocationService._load_dependencies(
                            novel_id,
                            parent_location_id=(
                                row["parent_location_id"]
                                if row["parent_location_ref"] is None
                                else None
                            ),
                            rule_ids=row["applicable_rule_ids"],
                            faction_ids=row["associated_faction_ids"],
                            session=session,
                        )
                        dependency_contexts.append(
                            (parent, rules, factions, row["parent_location_ref"])
                        )
                sibling_tails = {}
                for item in active_locations:
                    parent_id = item.get("parent_location_id")
                    sibling_tails[parent_id] = max(
                        sibling_tails.get(parent_id, 0),
                        int(item["order_index"]),
                    )
                for index, (row, document_id, resolved_parent_id) in enumerate(
                    zip(
                        candidate_rows,
                        attempted_ids,
                        resolved_parent_ids,
                        strict=True,
                    )
                ):
                    row = dict(row)
                    row.pop("parent_location_ref")
                    row.pop("parent_location_id")
                    parent_id = resolved_parent_id
                    sibling_tails[parent_id] = sibling_tails.get(parent_id, 0) + 1
                    now = _mongo_write_time()
                    document = {
                        **row,
                        "_id": document_id,
                        "novel_id": novel_id,
                        "location_id": ref_to_id[row["candidate_ref"]],
                        "parent_location_id": parent_id,
                        "status": "active",
                        "order_index": sibling_tails[parent_id],
                        "created_at": now,
                        "updated_at": now,
                        "location_order_pending_token": pending_token,
                        "generation_idempotency_key_hash": fingerprint.key_hash,
                        "generation_request_hash": fingerprint.request_hash,
                        "generation_candidate_ref": row["candidate_ref"],
                    }
                    document.pop("candidate_ref")
                    try:
                        saved = await location_repo.create_location(
                            document,
                            session=session,
                        )
                    except Exception:
                        if session is not None:
                            raise
                        current = await location_repo.collection.find_one(
                            {"_id": document_id}
                        )
                        expected_document = {
                            **document,
                            "novel_id": to_object_id(novel_id),
                            "version": 1,
                            "dependency_guard_revision": 0,
                            "location_order_pending_token": pending_token,
                            "is_deleted": False,
                            "deleted_at": None,
                            "detached_parent_location_id": None,
                        }
                        if current != expected_document:
                            raise
                        saved = current
                    created.append(saved)
                    created_by_ref[request.candidates[index].candidate_ref] = saved

                for parent, rules, factions, parent_ref in dependency_contexts:
                    if parent_ref is not None:
                        internal_parent = created_by_ref[parent_ref]
                        if (
                            internal_parent.get("status") != "active"
                            or internal_parent.get("is_deleted") is not False
                            or internal_parent.get("location_order_pending_token")
                            != pending_token
                        ):
                            raise _location_error(
                                "LOCATION_REFERENCE_CONFLICT",
                                "本批候选父级在地点写入期间发生变化",
                                status_code=409,
                            )
                    if session is None:
                        await LocationService._touch_dependency_documents(
                            rules,
                            factions,
                            session=session,
                        )
                if session is not None:
                    # 同一事务对每个依赖推进一次保护即可产生并发冲突，不按引用次数重复写。
                    await LocationService._touch_dependency_documents(
                        list(rules_by_id.values()),
                        list(factions_by_id.values()),
                        session=session,
                    )
                else:
                    await LocationService._validate_bulk_basis_sources(
                        novel_id,
                        request,
                        session=session,
                    )
                    await LocationService._get_novel(novel_id, session=session)
                expected_groups: dict[
                    str | None,
                    list[tuple[str, int, int]],
                ] = {
                    parent_id: [
                        (
                            str(item["location_id"]),
                            int(item["order_index"]),
                            int(item["version"]),
                        )
                        for item in active_locations
                        if item.get("parent_location_id") == parent_id
                    ]
                    for parent_id in affected_group_set
                }
                for item in created:
                    expected_groups[item.get("parent_location_id")].append(
                        (
                            str(item["location_id"]),
                            int(item["order_index"]),
                            int(item["version"]),
                        )
                    )
                for group in expected_groups.values():
                    group.sort(key=lambda item: (item[1], item[0]))
                await _assert_sibling_groups(
                    novel_id,
                    expected_groups,
                    session=session,
                )

                published_created: list[dict[str, Any]] = []
                for item in created:
                    published_created.append(
                        await _publish_created_location(
                            item,
                            pending_token,
                            session=session,
                        )
                    )
                created = published_created
                created_by_ref = {
                    str(item["generation_candidate_ref"]): item for item in created
                }
                await _assert_sibling_groups(
                    novel_id,
                    expected_groups,
                    session=session,
                )
                mapping = {
                    candidate.candidate_ref: str(
                        created_by_ref[candidate.candidate_ref]["location_id"]
                    )
                    for candidate in request.candidates
                }
                if request.basis.generation_input.selection_mode == "auto":
                    from backend.services.novel.plot_service import record_preparation
                    inputs = request.basis.generation_input
                    await record_preparation(novel_id, inputs.volume_id, "locations", session=session, location_ids=list(dict.fromkeys([*inputs.selected_existing_location_ids, *mapping.values()])), allow_write_lock=True)
                receipt_attempted = True
                await location_confirmation_receipt_repo.create_receipt(
                    {
                        "novel_id": novel_id,
                        "idempotency_key_hash": fingerprint.key_hash,
                        "request_hash": fingerprint.request_hash,
                        "candidate_ref_map": mapping,
                        "locations": deepcopy(created),
                        "novel_write_lock": {
                            "location_write_lock_token": pending_token,
                            "location_write_lock_revision": int(
                                novel_lock["location_write_lock_revision"]
                            ),
                        },
                    },
                    session=session,
                )
                await _release_novel_write_lock(
                    novel_id,
                    novel_lock,
                    session=session,
                )
                committed = True
                return {"candidate_ref_map": mapping, "locations": created}
            except BaseException as exc:
                if session is None and not committed:
                    replay_result: dict[str, Any] | None = None
                    reused_key = False
                    if receipt_attempted:
                        published = await location_confirmation_receipt_repo.find_receipt(
                            novel_id,
                            fingerprint.key_hash,
                        )
                        if published is not None:
                            if published.get("request_hash") == fingerprint.request_hash:
                                replay_result = _receipt_result(published)
                                own = [
                                    (str(item["_id"]), item["version"], item["updated_at"])
                                    for item in created
                                ]
                                replayed = [
                                    (str(item["_id"]), item["version"], item["updated_at"])
                                    for item in replay_result["locations"]
                                ]
                                if own == replayed:
                                    await _release_novel_write_lock(
                                        novel_id,
                                        novel_lock,
                                        session=None,
                                    )
                                    if isinstance(exc, asyncio.CancelledError):
                                        raise
                                    return replay_result
                            else:
                                reused_key = True
                    await _remove_generated_locations(
                        attempted_ids,
                        key_hash=fingerprint.key_hash,
                        request_hash=fingerprint.request_hash,
                        pending_token=pending_token,
                    )
                    await _release_novel_write_lock(
                        novel_id,
                        novel_lock,
                        session=None,
                    )
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    if replay_result is not None:
                        return replay_result
                    if reused_key:
                        raise _location_error(
                            "IDEMPOTENCY_KEY_REUSED",
                            "同一 Idempotency-Key 已用于不同的地点批量确认",
                            status_code=409,
                        )
                raise

        if session is not None:
            return await confirm(session)

        try:
            return await run_mongo_write_unit(
                confirm,
                "bulk_create_generated_locations",
                require_transaction=True,
            )
        except (DuplicateKeyError, DomainApiError, OperationFailure) as exc:
            if isinstance(exc, OperationFailure) and not (
                exc.code == 112 and exc.has_error_label("TransientTransactionError")
            ):
                raise
            if isinstance(exc, DomainApiError) and exc.code == "IDEMPOTENCY_KEY_REUSED":
                raise
            if isinstance(exc, DuplicateKeyError):
                # 唯一键也可能来自普通名称或顺序冲突；只做一次回执判定，不能统一等待。
                winner = await LocationService._load_confirmation_receipt(
                    novel_id,
                    fingerprint.key_hash,
                    fingerprint.request_hash,
                )
                if winner is not None:
                    await LocationService._get_novel(novel_id, session=None)
                    await _finish_stored_novel_write_lock(
                        novel_id,
                        winner,
                        session=None,
                    )
                    return _receipt_result(winner)
            elif isinstance(exc, OperationFailure) or exc.code == "LOCATION_WRITE_CONFLICT":
                # 已中止的事务不能继续读取；在事务外等待原键、原指纹的回执。
                winner = await LocationService._wait_for_confirmation_receipt(
                    novel_id,
                    fingerprint.key_hash,
                    fingerprint.request_hash,
                )
                if winner is not None:
                    return _receipt_result(winner)
            if isinstance(exc, DomainApiError):
                raise
            raise _location_error(
                "LOCATION_BATCH_CONFLICT",
                "地点批量确认发生规范名、顺序或并发冲突",
                status_code=409,
            ) from exc


__all__ = ["LocationService"]
