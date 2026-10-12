"""全书级正式物品、生命周期和连续顺序领域服务。"""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import Any

from bson import ObjectId
from pydantic import ValidationError
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import OperationFailure

from backend.api.error_protocol import DomainApiError
from backend.db.endpoint_guard import (
    rollback_dependency_endpoint_guards,
    touch_dependency_endpoint_guards,
)
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    InvalidIdError,
    NotFoundError,
)
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.confirmation_receipt_repository import (
    item_confirmation_receipt_repo,
)
from backend.db.repositories.item_repository import item_repo
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now, to_object_id
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.llm.schemas.item_pydantic import (
    ITEM_ID_PATTERN,
    ItemBulkGeneratedRequestV1,
    ItemCreateV1,
    ItemUpdateV1,
    normalize_item_text,
)
from backend.services.llm.candidate_contract import require_current_candidate_basis
from backend.services.llm.item_generation_context import load_item_generation_context
from backend.services.llm.item_generation_contract import (
    compute_items_input_fingerprint,
    validate_item_candidates,
)


logger = logging.getLogger(__name__)

ITEM_CONTENT_FIELDS = (
    "name",
    "aliases",
    "item_type",
    "description",
    "appearance",
    "origin",
    "abilities",
    "limitations",
    "costs",
    "owner_character_id",
    "controlling_faction_id",
    "current_location_id",
    "lifecycle_status",
    "story_function",
    "tags",
)
NON_TERMINAL_STATUSES = frozenset({"available", "held", "lost"})
TERMINAL_STATUSES = frozenset({"destroyed", "consumed"})
_ITEM_CONFIRMATION_REPLAY_WAIT_SECONDS = 5.0


def _item_error(
    code: str,
    message: str,
    *,
    status_code: int = 422,
    field_errors: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> DomainApiError:
    """构造遵循公共协议的物品领域错误。"""
    return DomainApiError(
        code,
        message,
        status_code=status_code,
        field_errors=field_errors,
        details=details,
    )


def _mongo_write_time() -> datetime:
    """生成可经 BSON 往返后精确比较的毫秒时间。"""
    now = get_utc_now()
    return now.replace(tzinfo=None, microsecond=(now.microsecond // 1000) * 1000)


def _validation_details(exc: ValidationError) -> dict[str, list[str]]:
    """把 Pydantic 错误压平为公共字段路径映射。"""
    result: dict[str, list[str]] = {}
    for error in exc.errors():
        path = ".".join(str(part) for part in error.get("loc", ())) or "$"
        message = str(error.get("msg") or "请求字段不合法")
        if message not in result.setdefault(path, []):
            result[path].append(message)
    return result


def _normalize_display_text(value: str) -> str:
    """把用户文本规范为保存用的 NFKC 首尾清理结果。"""
    return unicodedata.normalize("NFKC", value).strip()


def _prepare_item_content(value: Any) -> dict[str, Any]:
    """校验并清理一条完整正式物品内容。"""
    try:
        model = value if isinstance(value, ItemCreateV1) else ItemCreateV1.model_validate(value)
    except ValidationError as exc:
        raise _item_error(
            "ITEM_VALIDATION_FAILED",
            "物品字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    content = model.model_dump(mode="json")
    for field in (
        "name",
        "item_type",
        "description",
        "appearance",
        "origin",
        "story_function",
    ):
        content[field] = _normalize_display_text(content[field])
    for field in (
        "aliases",
        "abilities",
        "limitations",
        "costs",
        "tags",
    ):
        content[field] = [_normalize_display_text(item) for item in content[field]]
    try:
        content = ItemCreateV1.model_validate(content).model_dump(mode="json")
    except ValidationError as exc:
        raise _item_error(
            "ITEM_VALIDATION_FAILED",
            "物品规范化后的字段长度或组合不合法",
            field_errors=_validation_details(exc),
        ) from exc
    content["normalized_name"] = normalize_item_text(content["name"])
    return content


def _prepare_item_update(value: Any) -> tuple[int, dict[str, Any]]:
    """校验物品局部更新并保留三个引用的显式 null。"""
    try:
        model = value if isinstance(value, ItemUpdateV1) else ItemUpdateV1.model_validate(value)
    except ValidationError as exc:
        raise _item_error(
            "ITEM_VALIDATION_FAILED",
            "物品更新字段校验失败",
            field_errors=_validation_details(exc),
        ) from exc
    fields = model.model_dump(mode="json", exclude_unset=True)
    expected = int(fields.pop("expected_version"))
    for field in (
        "name",
        "item_type",
        "description",
        "appearance",
        "origin",
        "story_function",
    ):
        if field in fields:
            fields[field] = _normalize_display_text(fields[field])
    for field in (
        "aliases",
        "abilities",
        "limitations",
        "costs",
        "tags",
    ):
        if field in fields:
            fields[field] = [_normalize_display_text(item) for item in fields[field]]
    return expected, fields


async def acquire_item_write_lock(
    novel_id: str,
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """取得小说级物品写互斥，隔离物品写入与来源永久删除。

    Args:
        novel_id: 活动小说 ObjectId 字符串。
        session: 可选 MongoDB 会话。

    Returns:
        含本次锁标记和修订号的小说文档。
    """
    command_token = str(ObjectId())
    try:
        locked = await novel_repo.acquire_item_write_lock(
            novel_id,
            command_token,
            session=session,
        )
    except (Exception, asyncio.CancelledError) as exc:
        if session is not None:
            if (
                isinstance(exc, OperationFailure)
                and exc.code == 112
                and exc.has_error_label("TransientTransactionError")
            ):
                raise _item_error(
                    "ITEM_WRITE_CONFLICT",
                    "当前小说正由另一个物品或生命周期命令修改，请刷新后重试",
                    status_code=409,
                ) from exc
            raise
        current = await novel_repo.collection.find_one({"_id": to_object_id(novel_id)})
        if (
            current is not None
            and current.get("is_deleted") is False
            and current.get("hard_delete_claim") is None
            and current.get("item_write_lock_token") == command_token
        ):
            if isinstance(exc, asyncio.CancelledError):
                # standalone 更新已生效但调用被取消时，调用方尚未拿到锁，只能在这里精确释放。
                await release_item_write_lock(novel_id, current, session=None)
                raise
            return current
        raise
    if locked is not None:
        return locked
    current = await novel_repo.collection.find_one({"_id": to_object_id(novel_id)})
    if current is None or current.get("is_deleted") is True:
        raise _item_error("NOVEL_NOT_FOUND", "小说不存在或已删除", status_code=404)
    raise _item_error(
        "ITEM_WRITE_CONFLICT",
        "当前小说正由另一个物品或生命周期命令修改，请刷新后重试",
        status_code=409,
    )


async def release_item_write_lock(
    novel_id: str,
    lock: Mapping[str, Any],
    *,
    session: AsyncClientSession | None,
) -> None:
    """精确释放当前命令持有的小说级物品写互斥。

    Args:
        novel_id: 小说 ObjectId 字符串。
        lock: 取得互斥时返回的小说文档。
        session: 可选 MongoDB 会话。

    Returns:
        无。
    """
    token = str(lock["item_write_lock_token"])
    revision = int(lock["item_write_lock_revision"])
    release_error: Exception | None = None
    try:
        released = await novel_repo.release_item_write_lock(
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
    current_revision = int(current.get("item_write_lock_revision", 0))
    if (
        current_revision == revision
        and current.get("item_write_lock_token") is None
    ) or current_revision > revision:
        return
    if (
        current_revision == revision
        and current.get("item_write_lock_token") == token
    ):
        try:
            released = await novel_repo.release_item_write_lock(
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
        current_revision = int(current.get("item_write_lock_revision", 0))
        if (
            current_revision == revision
            and current.get("item_write_lock_token") is None
        ) or current_revision > revision:
            return
    raise _item_error(
        "ITEM_WRITE_GUARD_UNAVAILABLE",
        "物品写入已完成，但小说级内部互斥无法精确释放",
        status_code=503,
    ) from release_error


async def _apply_item_change(
    snapshot: Mapping[str, Any],
    fields: Mapping[str, Any],
    *,
    increment_version: bool,
    changes: list[tuple[dict[str, Any], dict[str, Any]]],
    session: AsyncClientSession | None,
    conflict_message: str,
) -> dict[str, Any]:
    """执行物品精确 CAS，并识别 standalone 写成功后的未知确认。"""
    write_time = _mongo_write_time()
    try:
        updated = await item_repo.update_from_snapshot(
            snapshot,
            fields,
            increment_version=increment_version,
            write_time=write_time,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await item_repo.collection.find_one({"_id": snapshot["_id"]})
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
        raise _item_error("ITEM_VERSION_CONFLICT", conflict_message, status_code=409)
    changes.append((dict(snapshot), dict(updated)))
    return updated


async def _publish_item(
    document: Mapping[str, Any],
    pending_token: str,
    *,
    session: AsyncClientSession | None,
) -> dict[str, Any]:
    """精确发布创建或恢复物品并处理 standalone 未知确认。"""
    try:
        published = await item_repo.publish_created_exact(
            document,
            pending_token,
            session=session,
        )
    except Exception:
        if session is not None:
            raise
        current = await item_repo.collection.find_one({"_id": document["_id"]})
        published = (
            current
            if current is not None
            and current.get("version") == document.get("version")
            and current.get("dependency_guard_revision")
            == document.get("dependency_guard_revision")
            and current.get("item_write_pending_token") is None
            and current.get("is_deleted") == document.get("is_deleted")
            else None
        )
    if published is None:
        raise _item_error(
            "ITEM_WRITE_CONFLICT",
            "物品发布期间发生并发变化",
            status_code=409,
        )
    return published


async def _compensate_item_changes(
    changes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> None:
    """以临时负顺序精确恢复 standalone 物品写前镜像。"""
    if not changes:
        return
    latest: dict[Any, tuple[dict[str, Any], dict[str, Any]]] = {}
    for before, after in changes:
        if before["_id"] in latest:
            original, _ = latest[before["_id"]]
            latest[before["_id"]] = (original, dict(after))
        else:
            latest[before["_id"]] = (dict(before), dict(after))
    minimum = await item_repo.collection.find_one(
        {},
        projection={"order_index": 1},
        sort=[("order_index", 1)],
    )
    lowest = int(minimum["order_index"]) if minimum is not None else 0
    start = min(-1_000_000, lowest - len(latest) - 1)
    temporary: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for offset, (before, after) in enumerate(latest.values()):
        write_time = _mongo_write_time()
        temp_order = start - offset
        try:
            moved = await item_repo.update_from_snapshot(
                after,
                {"order_index": temp_order},
                increment_version=False,
                write_time=write_time,
            )
        except Exception:
            current = await item_repo.collection.find_one({"_id": after["_id"]})
            moved = (
                current
                if current is not None
                and int(current["version"]) == int(after["version"])
                and current.get("order_index") == temp_order
                and current.get("updated_at") == write_time
                else None
            )
        if moved is None:
            raise _item_error(
                "ITEM_COMPENSATION_FAILED",
                "物品写入失败，且安全顺序补偿未完整完成",
                status_code=503,
            )
        temporary.append((before, dict(moved)))
    for before, moved in reversed(temporary):
        try:
            restored = await item_repo.restore_snapshot_exact(moved, before)
        except Exception:
            current = await item_repo.collection.find_one({"_id": before["_id"]})
            restored = current == before
        if not restored:
            raise _item_error(
                "ITEM_COMPENSATION_FAILED",
                "物品写入失败，且数据库补偿未完整完成",
                status_code=503,
            )


class ItemService:
    """物品唯一事实源的直接业务写入口。"""

    @staticmethod
    async def _get_novel(
        novel_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取活动小说并统一小说作用域错误。"""
        try:
            return await novel_repo.get_novel_by_id(novel_id, session=session)
        except InvalidIdError as exc:
            raise _item_error(
                "INVALID_OBJECT_ID",
                "novel_id 不是有效 ObjectId",
                field_errors={"novel_id": "不是有效 ObjectId"},
            ) from exc
        except NotFoundError as exc:
            raise _item_error("NOVEL_NOT_FOUND", str(exc), status_code=404) from exc

    @staticmethod
    async def _check_public_read_fence(
        novel_id: str,
        *,
        expected_revision: int | None = None,
    ) -> int:
        """确认公共物品读取没有跨越小说级物品写命令。"""
        novel = await ItemService._get_novel(novel_id, session=None)
        revision = int(novel.get("item_write_lock_revision", 0))
        if novel.get("item_write_lock_token") is not None or (
            expected_revision is not None and revision != expected_revision
        ):
            raise _item_error(
                "ITEM_READ_CONFLICT",
                "物品正在更新，请刷新后重试",
                status_code=409,
            )
        return revision

    @staticmethod
    async def _get_item(
        novel_id: str,
        item_id: str,
        *,
        deleted: bool,
        expected_version: int | None,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取指定生命周期物品并可选验证公开版本。"""
        try:
            item = (
                await item_repo.get_deleted_item(novel_id, item_id, session=session)
                if deleted
                else await item_repo.get_item(novel_id, item_id, session=session)
            )
        except (NotFoundError, InvalidIdError) as exc:
            raise _item_error(
                "ITEM_NOT_FOUND",
                "物品不存在、已删除或不属于当前小说",
                status_code=404,
                details={"item_id": item_id},
            ) from exc
        if expected_version is not None:
            expected = validate_expected_version(expected_version)
            actual = int(item["version"])
            if actual != expected:
                raise _item_error(
                    "ITEM_VERSION_CONFLICT",
                    f"物品 {item_id} 版本冲突",
                    status_code=409,
                    details={"expected_version": expected, "actual_version": actual},
                )
        return item

    @staticmethod
    async def _ensure_name_available(
        novel_id: str,
        normalized_name: str,
        *,
        exclude_item_id: str | None,
        session: AsyncClientSession | None,
    ) -> None:
        """保证同小说下不存在另一个同规范名活动物品。"""
        existing = await item_repo.find_active_by_normalized_name(
            novel_id,
            normalized_name,
            session=session,
        )
        if existing is not None and existing["item_id"] != exclude_item_id:
            raise _item_error(
                "ITEM_NAME_CONFLICT",
                "同一小说下已存在同名活动物品",
                status_code=409,
                details={"existing_item_id": existing.get("item_id")},
            )

    @staticmethod
    async def _load_dependencies(
        novel_id: str,
        *,
        owner_character_id: str | None,
        controlling_faction_id: str | None,
        current_location_id: str | None,
        session: AsyncClientSession | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        """解析同书活动角色、势力和地点引用。"""
        character: dict[str, Any] | None = None
        faction: dict[str, Any] | None = None
        location: dict[str, Any] | None = None
        if owner_character_id is not None:
            try:
                character = await character_repo.get_character(
                    novel_id,
                    owner_character_id,
                    session=session,
                )
                if character.get("status") != "active":
                    raise NotFoundError("角色已停用")
            except (NotFoundError, InvalidIdError) as exc:
                raise _item_error(
                    "ITEM_REFERENCE_NOT_FOUND",
                    "物品角色所有者不存在、已删除、已停用或不属于当前小说",
                    status_code=404,
                    field_errors={"owner_character_id": "引用不可用"},
                    details={"reference_id": owner_character_id},
                ) from exc
        if controlling_faction_id is not None:
            try:
                faction = await faction_repo.get_faction(
                    novel_id,
                    controlling_faction_id,
                    session=session,
                )
                if faction.get("active_status") != "active":
                    raise NotFoundError("势力已停用")
            except (NotFoundError, InvalidIdError) as exc:
                raise _item_error(
                    "ITEM_REFERENCE_NOT_FOUND",
                    "物品控制势力不存在、已删除、已停用或不属于当前小说",
                    status_code=404,
                    field_errors={"controlling_faction_id": "引用不可用"},
                    details={"reference_id": controlling_faction_id},
                ) from exc
        if current_location_id is not None:
            try:
                location = await location_repo.get_location(
                    novel_id,
                    current_location_id,
                    session=session,
                )
                if (
                    location.get("status") != "active"
                    or location.get("location_order_pending_token") is not None
                ):
                    raise NotFoundError("地点不可用")
            except (NotFoundError, InvalidIdError) as exc:
                raise _item_error(
                    "ITEM_REFERENCE_NOT_FOUND",
                    "物品当前地点不存在、已删除、已停用或不属于当前小说",
                    status_code=404,
                    field_errors={"current_location_id": "引用不可用"},
                    details={"reference_id": current_location_id},
                ) from exc
        return character, faction, location

    @staticmethod
    async def _touch_dependencies(
        dependencies: tuple[
            dict[str, Any] | None,
            dict[str, Any] | None,
            dict[str, Any] | None,
        ],
        *,
        session: AsyncClientSession | None,
    ) -> list[tuple[Any, list[Any]]]:
        """在物品事实落库后推进当前引用端点 guard。"""
        character, faction, location = dependencies
        applied: list[tuple[Any, list[Any]]] = []
        try:
            if character is not None:
                touches = await touch_dependency_endpoint_guards(
                    character_repo.collection,
                    [
                        {
                            "_id": character["_id"],
                            "novel_id": character["novel_id"],
                            "version": character["version"],
                            "status": "active",
                            "is_deleted": False,
                        }
                    ],
                    session=session,
                )
                applied.append((character_repo.collection, touches))
            if faction is not None:
                touches = await touch_dependency_endpoint_guards(
                    faction_repo.collection,
                    [
                        {
                            "_id": faction["_id"],
                            "novel_id": faction["novel_id"],
                            "version": faction["version"],
                            "active_status": "active",
                            "is_deleted": False,
                        }
                    ],
                    session=session,
                )
                applied.append((faction_repo.collection, touches))
            if location is not None:
                touches = await touch_dependency_endpoint_guards(
                    location_repo.collection,
                    [
                        {
                            "_id": location["_id"],
                            "novel_id": location["novel_id"],
                            "version": location["version"],
                            "status": "active",
                            "is_deleted": False,
                            "location_order_pending_token": None,
                        }
                    ],
                    session=session,
                )
                applied.append((location_repo.collection, touches))
        except (Exception, asyncio.CancelledError):
            if session is None:
                for collection, touches in reversed(applied):
                    await rollback_dependency_endpoint_guards(collection, touches)
            raise
        return applied

    @staticmethod
    async def _rollback_dependency_touches(
        applied: Sequence[tuple[Any, Sequence[Any]]],
    ) -> None:
        """精确减回 standalone 失败命令已完成的端点 guard 贡献。"""
        for collection, touches in reversed(list(applied)):
            await rollback_dependency_endpoint_guards(collection, touches)

    @staticmethod
    def _ensure_active_order(items: Sequence[Mapping[str, Any]]) -> None:
        """要求已发布活动物品顺序完整连续为 1..N。"""
        orders = [int(item["order_index"]) for item in items]
        if orders != list(range(1, len(items) + 1)):
            raise _item_error(
                "ITEM_ORDER_CONFLICT",
                "活动物品顺序不是完整连续的 1..N",
                status_code=409,
            )

    @staticmethod
    async def list_items(
        novel_id: str,
        *,
        q: str | None = None,
        item_type: str | None = None,
        lifecycle_status: str | None = None,
        owner_character_id: str | None = None,
        controlling_faction_id: str | None = None,
        current_location_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按小说和公开筛选读取活动物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选名称、别名、描述或标签搜索词。
            item_type: 可选物品类型。
            lifecycle_status: 可选生命周期状态。
            owner_character_id: 可选角色所有者 ID。
            controlling_faction_id: 可选控制势力 ID。
            current_location_id: 可选当前地点 ID。

        Returns:
            按 1-based 顺序排列的完整活动物品。
        """
        revision = await ItemService._check_public_read_fence(novel_id)
        items = await item_repo.list_items(
            novel_id,
            q=q,
            item_type=item_type,
            lifecycle_status=lifecycle_status,
            owner_character_id=owner_character_id,
            controlling_faction_id=controlling_faction_id,
            current_location_id=current_location_id,
        )
        await ItemService._check_public_read_fence(
            novel_id,
            expected_revision=revision,
        )
        return items

    @staticmethod
    async def list_deleted_items(
        novel_id: str,
        *,
        q: str | None = None,
        item_type: str | None = None,
        lifecycle_status: str | None = None,
        owner_character_id: str | None = None,
        controlling_faction_id: str | None = None,
        current_location_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按公开筛选读取小说物品回收站。

        Args:
            novel_id: 小说 ObjectId 字符串。
            q: 可选搜索词。
            item_type: 可选物品类型。
            lifecycle_status: 可选生命周期状态。
            owner_character_id: 可选角色所有者 ID。
            controlling_faction_id: 可选控制势力 ID。
            current_location_id: 可选当前地点 ID。

        Returns:
            按删除时间倒序排列的回收站物品。
        """
        revision = await ItemService._check_public_read_fence(novel_id)
        items = await item_repo.list_deleted_items(
            novel_id,
            q=q,
            item_type=item_type,
            lifecycle_status=lifecycle_status,
            owner_character_id=owner_character_id,
            controlling_faction_id=controlling_faction_id,
            current_location_id=current_location_id,
        )
        await ItemService._check_public_read_fence(
            novel_id,
            expected_revision=revision,
        )
        return items

    @staticmethod
    async def get_item(novel_id: str, item_id: str) -> dict[str, Any]:
        """读取小说内一条活动物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。

        Returns:
            匹配的完整物品文档。
        """
        revision = await ItemService._check_public_read_fence(novel_id)
        item = await ItemService._get_item(
            novel_id,
            item_id,
            deleted=False,
            expected_version=None,
            session=None,
        )
        await ItemService._check_public_read_fence(
            novel_id,
            expected_revision=revision,
        )
        return item

    @staticmethod
    async def get_delete_impact(novel_id: str, item_id: str) -> dict[str, Any]:
        """读取活动或回收站物品的永久删除影响。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。

        Returns:
            四类正式消费者的分项、总数与保护标记。
        """
        revision = await ItemService._check_public_read_fence(novel_id)
        try:
            await item_repo.get_item(novel_id, item_id, include_deleted=True)
        except (NotFoundError, InvalidIdError) as exc:
            raise _item_error(
                "ITEM_NOT_FOUND",
                "物品不存在或不属于当前小说",
                status_code=404,
            ) from exc
        references = await item_repo.count_protected_references(novel_id, item_id)
        await ItemService._check_public_read_fence(
            novel_id,
            expected_revision=revision,
        )
        return {
            "item_id": item_id,
            "arcs": references["arcs"],
            "chapters": references["chapters"],
            "scenes": references["scenes"],
            "foreshadowings": references["foreshadowings"],
            "total_protected_references": references["total"],
            "has_protected_references": references["total"] > 0,
        }

    @staticmethod
    async def create_item(novel_id: str, data: ItemCreateV1 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """只回放旧创建结果，新物品由作者确认明确起点。

        Args:
            novel_id: 当前小说。
            data: 原创建请求。
            idempotency_key: 原创建键。
            session: 可选调用方事务。
        Returns:
            原键对应的既有结果，不补建缺失物品。
        """
        content = _prepare_item_content(data)
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"novel_id": novel_id, "item": content})
        revision = await ItemService._check_public_read_fence(novel_id) if session is None else None
        existing = await item_repo.find_by_creation_idempotency(novel_id, fingerprint.key_hash, session=session)
        try:
            replay = resolve_idempotent_replay(existing, fingerprint.request_hash, label="物品创建")
        except IdempotencyConflictError as exc:
            raise _item_error("IDEMPOTENCY_KEY_REUSED", str(exc), status_code=409) from exc
        if replay is not None:
            if session is None:
                await ItemService._check_public_read_fence(novel_id, expected_revision=revision)
            return replay
        raise DomainApiError("ITEM_FACT_REQUIRED", "新物品请先选择明确起点再确认；旧请求没有成功记录，请保留原稿", status_code=409)

    @staticmethod
    async def update_item(novel_id: str, item_id: str, data: ItemUpdateV1 | Mapping[str, Any], *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """以 CAS 更新物品内容并重新校验完整生命周期组合。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            data: 含 expected_version 的严格局部更新。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            更新并递增版本后的完整物品。
        """
        expected, requested = _prepare_item_update(data)
        from backend.services.novel.item_fact_contract import ITEM_FACT_FIELDS
        from backend.services.novel.item_fact_service import ensure_item_fields_unmanaged
        state_changed = bool(ITEM_FACT_FIELDS & requested.keys())

        async def update(session: AsyncClientSession | None) -> dict[str, Any]:
            if state_changed:
                # 先保护空历史，再取本次物品锁，避免把自己的锁当成来源冲突。
                await ensure_item_fields_unmanaged(novel_id, [item_id], session=session)
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            dependency_touches: list[tuple[Any, list[Any]]] = []
            committed = False
            try:
                current = await ItemService._get_item(
                    novel_id,
                    item_id,
                    deleted=False,
                    expected_version=expected,
                    session=session,
                )
                complete = {field: current[field] for field in ITEM_CONTENT_FIELDS}
                complete.update(requested)
                # 设计保存不重新确认旧状态，也不因旧持有人回收而失败。
                validated = _prepare_item_content(complete if state_changed else {**complete,
                    "lifecycle_status": "available", "owner_character_id": None,
                    "controlling_faction_id": None, "current_location_id": None})
                fields = {field: validated[field] for field in requested}
                if "name" in requested:
                    fields["normalized_name"] = validated["normalized_name"]
                    await ItemService._ensure_name_available(
                        novel_id,
                        validated["normalized_name"],
                        exclude_item_id=item_id,
                        session=session,
                    )
                dependencies = await ItemService._load_dependencies(
                    novel_id,
                    owner_character_id=validated["owner_character_id"],
                    controlling_faction_id=validated["controlling_faction_id"],
                    current_location_id=validated["current_location_id"],
                    session=session,
                ) if state_changed else (None, None, None)
                updated = await _apply_item_change(
                    current,
                    fields,
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="物品更新期间已被其他请求修改或新增依赖",
                )
                dependency_touches = await ItemService._touch_dependencies(
                    dependencies,
                    session=session,
                )
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return updated
            except Exception:
                if session is None and not committed:
                    await _compensate_item_changes(changes)
                    await ItemService._rollback_dependency_touches(
                        dependency_touches
                    )
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        if session is not None:
            return await update(session)

        try:
            return await run_mongo_write_unit(update, "update_item", require_transaction=state_changed)
        except DuplicateKeyError as exc:
            raise _item_error(
                "ITEM_NAME_CONFLICT",
                "物品更新与活动规范名冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def transition_item_status(novel_id: str, item_id: str, target_status: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """执行显式物品状态转换并原子清空终态引用。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            target_status: 五种生命周期状态之一。
            expected_version: 调用方持有的公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            状态转换并递增版本后的完整物品。
        """
        expected = validate_expected_version(expected_version)
        if target_status not in NON_TERMINAL_STATUSES | TERMINAL_STATUSES:
            raise _item_error("ITEM_STATUS_INVALID", "目标物品状态不合法")

        async def transition(session: AsyncClientSession | None) -> dict[str, Any]:
            from backend.services.novel.item_fact_service import ensure_item_fields_unmanaged
            await ensure_item_fields_unmanaged(novel_id, [item_id], session=session)
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                current = await ItemService._get_item(
                    novel_id,
                    item_id,
                    deleted=False,
                    expected_version=expected,
                    session=session,
                )
                current_status = str(current["lifecycle_status"])
                if current_status in TERMINAL_STATUSES:
                    raise _item_error(
                        "ITEM_STATUS_TERMINAL",
                        "destroyed/consumed 为终态，不能继续转换",
                    )
                if current_status == target_status:
                    raise _item_error(
                        "ITEM_STATUS_UNCHANGED",
                        "目标状态必须与当前状态不同",
                    )
                if target_status == "held" and not (
                    current.get("owner_character_id")
                    or current.get("controlling_faction_id")
                ):
                    raise _item_error(
                        "ITEM_HELD_OWNER_REQUIRED",
                        "转入 held 前必须具有角色所有者或控制势力",
                        field_errors={"target_status": "缺少持有方"},
                    )
                fields: dict[str, Any] = {"lifecycle_status": target_status}
                if target_status in TERMINAL_STATUSES:
                    # 终态清理由这一个领域命令完成，前端不能拆成多个 patch。
                    fields.update(
                        {
                            "owner_character_id": None,
                            "controlling_faction_id": None,
                            "current_location_id": None,
                        }
                    )
                updated = await _apply_item_change(
                    current,
                    fields,
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="物品状态转换期间已被其他请求修改",
                )
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return updated
            except Exception:
                if session is None and not committed:
                    await _compensate_item_changes(changes)
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        if session is not None:
            return await transition(session)

        return await run_mongo_write_unit(transition, "transition_item_status", require_transaction=True)

    @staticmethod
    async def reorder_items(novel_id: str, items: Sequence[Mapping[str, Any]], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """以完整活动集合执行 1-based CAS 重排。

        Args:
            novel_id: 小说 ObjectId 字符串。
            items: item_id、order_index 和 expected_version 的完整集合。

            session: 调用方事务；提供时不另开事务。

        Returns:
            按新顺序排列且每条版本递增一次的活动物品。
        """
        if not items:
            raise _item_error("ITEM_VALIDATION_FAILED", "物品重排至少需要一个条目")
        normalized: list[dict[str, int | str]] = []
        seen_ids: set[str] = set()
        seen_orders: set[int] = set()
        import re

        for entry in items:
            item_id = entry.get("item_id")
            order_index = entry.get("order_index")
            try:
                expected = validate_expected_version(entry.get("expected_version"))
            except ValueError as exc:
                raise _item_error("ITEM_VALIDATION_FAILED", str(exc)) from exc
            if not isinstance(item_id, str) or re.fullmatch(ITEM_ID_PATTERN, item_id) is None:
                raise _item_error("ITEM_VALIDATION_FAILED", "物品重排包含非法 item_id")
            if isinstance(order_index, bool) or not isinstance(order_index, int) or order_index < 1:
                raise _item_error("ITEM_VALIDATION_FAILED", "order_index 必须从 1 开始")
            if item_id in seen_ids or order_index in seen_orders:
                raise _item_error(
                    "ITEM_VALIDATION_FAILED",
                    "重排 item_id 和 order_index 均不能重复",
                )
            seen_ids.add(item_id)
            seen_orders.add(order_index)
            normalized.append(
                {
                    "item_id": item_id,
                    "order_index": order_index,
                    "expected_version": expected,
                }
            )
        if seen_orders != set(range(1, len(normalized) + 1)):
            raise _item_error(
                "ITEM_ORDER_CONFLICT",
                "物品顺序必须完整覆盖 1..N",
                status_code=409,
            )

        async def reorder(session: AsyncClientSession | None) -> list[dict[str, Any]]:
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                active = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(active)
                if {str(item["item_id"]) for item in active} != seen_ids:
                    raise _item_error(
                        "ITEM_REORDER_INCOMPLETE",
                        "物品重排必须提交当前完整活动集合",
                        status_code=409,
                        details={
                            "expected_item_ids": [item["item_id"] for item in active],
                            "submitted_item_ids": sorted(seen_ids),
                        },
                    )
                by_id = {str(item["item_id"]): item for item in active}
                for entry in normalized:
                    current = by_id[str(entry["item_id"])]
                    if int(current["version"]) != int(entry["expected_version"]):
                        raise _item_error(
                            "ITEM_VERSION_CONFLICT",
                            f"物品 {entry['item_id']} 版本冲突",
                            status_code=409,
                        )
                staged: dict[str, dict[str, Any]] = {}
                for temp_index, current in enumerate(active, start=1):
                    staged[str(current["item_id"])] = await _apply_item_change(
                        current,
                        {"order_index": -temp_index},
                        increment_version=False,
                        changes=changes,
                        session=session,
                        conflict_message="物品重排期间活动集合已变化",
                    )
                updated: list[dict[str, Any]] = []
                for entry in sorted(normalized, key=lambda value: int(value["order_index"])):
                    updated.append(
                        await _apply_item_change(
                            staged[str(entry["item_id"])],
                            {"order_index": int(entry["order_index"])},
                            increment_version=True,
                            changes=changes,
                            session=session,
                            conflict_message="物品重排期间活动集合已变化",
                        )
                    )
                after = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(after)
                if [item["item_id"] for item in after] != [
                    item["item_id"] for item in updated
                ]:
                    raise _item_error(
                        "ITEM_ORDER_CONFLICT",
                        "物品重排写后集合与请求不一致",
                        status_code=409,
                    )
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return updated
            except Exception:
                if session is None and not committed:
                    await _compensate_item_changes(changes)
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        if session is not None:
            return await reorder(session)

        try:
            return await run_mongo_write_unit(reorder, "reorder_items")
        except DuplicateKeyError as exc:
            raise _item_error(
                "ITEM_ORDER_CONFLICT",
                "物品重排发生顺序或并发冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def soft_delete_item(novel_id: str, item_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """软删除物品并收紧活动集合顺序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            expected_version: 调用方持有的公开版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已进入回收站且递增版本的目标物品。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession | None) -> dict[str, Any]:
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            committed = False
            try:
                current = await ItemService._get_item(
                    novel_id,
                    item_id,
                    deleted=False,
                    expected_version=expected,
                    session=session,
                )
                siblings = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(siblings)
                deleted = await _apply_item_change(
                    current,
                    {"is_deleted": True, "deleted_at": _mongo_write_time()},
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="物品删除期间已被其他请求修改或新增依赖",
                )
                for sibling in siblings:
                    if int(sibling["order_index"]) <= int(current["order_index"]):
                        continue
                    await _apply_item_change(
                        sibling,
                        {"order_index": int(sibling["order_index"]) - 1},
                        increment_version=True,
                        changes=changes,
                        session=session,
                        conflict_message="物品删除期间活动集合已变化",
                    )
                after = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(after)
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return deleted
            except Exception:
                if session is None and not committed:
                    await _compensate_item_changes(changes)
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        if session is not None:
            return await delete(session)

        try:
            return await run_mongo_write_unit(delete, "soft_delete_item")
        except DuplicateKeyError as exc:
            raise _item_error(
                "ITEM_ORDER_CONFLICT",
                "物品删除与活动顺序发生并发冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def restore_item(novel_id: str, item_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """恢复回收站物品并追加到活动集合末尾。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            expected_version: 调用方持有的回收站版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已恢复、发布且递增版本的完整物品。
        """
        expected = validate_expected_version(expected_version)

        async def restore(session: AsyncClientSession | None) -> dict[str, Any]:
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            token = str(lock["item_write_lock_token"])
            changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
            dependency_touches: list[tuple[Any, list[Any]]] = []
            committed = False
            try:
                current = await ItemService._get_item(
                    novel_id,
                    item_id,
                    deleted=True,
                    expected_version=expected,
                    session=session,
                )
                complete = {field: current[field] for field in ITEM_CONTENT_FIELDS}
                validated = _prepare_item_content(complete)
                dependencies = await ItemService._load_dependencies(
                    novel_id,
                    owner_character_id=validated["owner_character_id"],
                    controlling_faction_id=validated["controlling_faction_id"],
                    current_location_id=validated["current_location_id"],
                    session=session,
                )
                await ItemService._ensure_name_available(
                    novel_id,
                    current["normalized_name"],
                    exclude_item_id=item_id,
                    session=session,
                )
                siblings = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(siblings)
                restored = await _apply_item_change(
                    current,
                    {
                        "is_deleted": False,
                        "deleted_at": None,
                        "order_index": len(siblings) + 1,
                        "item_write_pending_token": token,
                    },
                    increment_version=True,
                    changes=changes,
                    session=session,
                    conflict_message="物品恢复期间已被其他请求修改",
                )
                dependency_touches = await ItemService._touch_dependencies(
                    dependencies,
                    session=session,
                )
                published = await _publish_item(restored, token, session=session)
                # publish 改变内部标记，补偿必须绑定最新精确写后镜像。
                changes[-1] = (changes[-1][0], dict(published))
                after = await item_repo.list_active_items(novel_id, session=session)
                ItemService._ensure_active_order(after)
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return published
            except Exception:
                if session is None and not committed:
                    await _compensate_item_changes(changes)
                    await ItemService._rollback_dependency_touches(
                        dependency_touches
                    )
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        if session is not None:
            return await restore(session)

        try:
            return await run_mongo_write_unit(restore, "restore_item")
        except DuplicateKeyError as exc:
            raise _item_error(
                "ITEM_RESTORE_CONFLICT",
                "物品恢复与活动规范名或顺序冲突",
                status_code=409,
            ) from exc

    @staticmethod
    async def hard_delete_item(
        novel_id: str,
        item_id: str,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        """永久删除没有正式消费者引用的回收站物品。

        Args:
            novel_id: 小说 ObjectId 字符串。
            item_id: 稳定物品 ID。
            expected_version: 调用方持有的回收站版本。

        Returns:
            被删除物品 ID 与全部为零的最终影响。
        """
        expected = validate_expected_version(expected_version)

        async def delete(session: AsyncClientSession | None) -> dict[str, Any]:
            await ItemService._get_novel(novel_id, session=session)
            lock = await acquire_item_write_lock(novel_id, session=session)
            committed = False
            try:
                current = await ItemService._get_item(
                    novel_id,
                    item_id,
                    deleted=True,
                    expected_version=expected,
                    session=session,
                )
                references = await item_repo.count_protected_references(
                    novel_id,
                    item_id,
                    session=session,
                )
                impact = {
                    "item_id": item_id,
                    "arcs": references["arcs"],
                    "chapters": references["chapters"],
                    "scenes": references["scenes"],
                    "foreshadowings": references["foreshadowings"],
                    "total_protected_references": references["total"],
                    "has_protected_references": references["total"] > 0,
                }
                if references["total"] > 0:
                    raise _item_error(
                        "ITEM_REFERENCE_PROTECTED",
                        "物品仍被正式结构或伏笔引用，不能永久删除",
                        status_code=409,
                        details={"impact": impact},
                    )
                try:
                    deleted = await item_repo.hard_delete_item(current, session=session)
                except Exception:
                    if session is None:
                        still_exists = await item_repo.collection.find_one(
                            {"_id": current["_id"]}
                        )
                        if still_exists is None:
                            deleted = True
                        else:
                            raise
                    else:
                        raise
                if not deleted:
                    raise _item_error(
                        "ITEM_VERSION_CONFLICT",
                        "物品永久删除期间已被其他请求修改或新增依赖",
                        status_code=409,
                    )
                committed = True
                await release_item_write_lock(novel_id, lock, session=session)
                return {"item_id": item_id, "impact": impact}
            except Exception:
                if session is None and not committed:
                    await release_item_write_lock(novel_id, lock, session=None)
                raise

        return await run_mongo_write_unit(delete, "hard_delete_item")

    @staticmethod
    async def _validate_bulk_basis_sources(
        novel_id: str,
        request: ItemBulkGeneratedRequestV1,
        *,
        session: AsyncClientSession | None,
        allow_item_write_lock: bool,
    ) -> dict[str, Any]:
        """重读物品生成输入并确认 basis 仍然有效。

        Args:
            novel_id: 当前小说 ObjectId 字符串。
            request: 严格批量确认请求。
            session: 可选 MongoDB 会话。
            allow_item_write_lock: 当前命令已持有物品写锁时设为 True。

        Returns:
            与生成时字段和排序规则一致的当前上下文。
        """
        basis = request.basis
        generation_input = basis.generation_input
        if basis.novel_id != novel_id or generation_input.novel_id != novel_id:
            raise _item_error(
                "ITEM_BASIS_CONFLICT",
                "物品候选不属于当前小说",
                status_code=409,
            )
        current_context = await load_item_generation_context(
            generation_input,
            session=session,
            allow_item_write_lock=allow_item_write_lock,
        )
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
            raise _item_error(
                "CANDIDATE_SOURCE_NOT_FOUND",
                "物品候选依据中的正式资源已不存在、已删除或不可用",
                status_code=404,
                details={"resource_type": resource_type, "id": resource_id},
            )
        if current_identities - submitted_identities:
            raise _item_error(
                "ITEM_BASIS_CONFLICT",
                "物品生成使用的资料已经变化，请重新生成",
                status_code=409,
            )
        try:
            current_fingerprint = compute_items_input_fingerprint(
                generation_input,
                current_context["source_refs"],
                flow_snapshot=basis.flow_snapshot,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _item_error(
                "ITEM_BASIS_CONFLICT",
                "物品候选使用的提示词、Schema 或执行配置已经变化",
                status_code=409,
            ) from exc
        require_current_candidate_basis(
            basis,
            current_source_versions={
                (source.resource_type, source.id): source.version
                for source in current_context["source_refs"]
            },
            current_fingerprint=current_fingerprint,
        )
        return current_context

    @staticmethod
    def _confirmation_receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
        """从不可变回执复制批量确认的公开结果。"""
        return {
            "candidate_ref_map": deepcopy(receipt["candidate_ref_map"]),
            "items": deepcopy(receipt["items_snapshot"]),
        }

    @staticmethod
    async def _load_confirmation_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取同键成功回执并拒绝不同载荷。

        Args:
            novel_id: 当前小说 ObjectId 字符串。
            key_hash: Idempotency-Key 摘要。
            request_hash: 当前规范请求摘要。
            session: 可选 MongoDB 会话。

        Returns:
            同键同载荷的成功回执；尚未成功时返回 None。
        """
        receipt = await item_confirmation_receipt_repo.find_receipt(
            novel_id,
            key_hash,
            session=session,
        )
        if receipt is None:
            return None
        if receipt.get("request_hash") != request_hash:
            raise _item_error(
                "IDEMPOTENCY_KEY_REUSED",
                "同一 Idempotency-Key 已用于不同的物品批量确认",
                status_code=409,
            )
        return receipt

    @staticmethod
    async def _wait_for_confirmation_receipt(
        novel_id: str,
        key_hash: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        """短暂等待并发赢家提交物品确认回执。"""
        # Mongo 事务在提交前不会暴露锁或回执；给在途赢家完整的短等待窗口，
        # 避免正常但稍慢的同键请求被误报为并发冲突。
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _ITEM_CONFIRMATION_REPLAY_WAIT_SECONDS
        while True:
            receipt = await ItemService._load_confirmation_receipt(
                novel_id,
                key_hash,
                request_hash,
            )
            if receipt is not None:
                await ItemService._get_novel(novel_id, session=None)
                lock = receipt.get("novel_write_lock")
                if isinstance(lock, Mapping):
                    # 回执已经证明批次提交成功；迟到请求只需完成可能遗留的同一把锁。
                    await release_item_write_lock(novel_id, lock, session=None)
                return receipt
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            # 截止时刻后还会执行上面最后一次读取，避免错过刚提交的回执。
            await asyncio.sleep(min(0.05, remaining))

    @staticmethod
    async def bulk_create_generated_items(novel_id: str, request_value: Any, *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """旧批次只回放原成功，未决请求不拆批或补建。

        Args:
            novel_id: 当前小说。
            request_value: 原批次请求。
            idempotency_key: 原整批键。
            session: 可选调用方事务。
        Returns:
            原批次的映射与成功快照，调用方随后只读现状。
        """
        request = ItemBulkGeneratedRequestV1.model_validate(request_value)
        fingerprint = build_idempotency_fingerprint(idempotency_key, {"novel_id": novel_id, **request.model_dump(mode="json")})
        replay = await ItemService._load_confirmation_receipt(novel_id, fingerprint.key_hash, fingerprint.request_hash, session=session)
        if replay is not None:
            if session is None and replay.get("novel_write_lock"):
                await release_item_write_lock(novel_id, replay["novel_write_lock"], session=None)
            return ItemService._confirmation_receipt_result(replay)
        raise DomainApiError("ITEM_FACT_REQUIRED", "旧批次没有成功记录，请保留原请求；新批次请先确认完整起点", status_code=409)


__all__ = ["ItemService"]
