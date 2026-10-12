"""可变聚合 CAS 与目标文档内领域幂等公共原语。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection

from backend.db.errors import IdempotencyConflictError
from backend.db.utils import get_utc_now


IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")


def validate_expected_version(value: Any) -> int:
    """功能：校验正式可变聚合使用的 expected_version。

    Args:
        value: API 或领域服务传入的版本值。

    Returns:
        大于等于 1 且排除布尔值的整数版本。

    Raises:
        ValueError: 版本不是正整数。
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("expected_version 必须为大于等于 1 的整数")
    return value


def ensure_initial_version(document: Mapping[str, Any]) -> dict[str, Any]:
    """功能：复制待创建聚合并补齐唯一初始版本 1。

    Args:
        document: 已完成领域预校验、尚未持久化的文档。

    Returns:
        带 ``version=1`` 的新字典。

    Raises:
        ValueError: 调用方显式提供了非 1 初始版本。
    """
    prepared = dict(document)
    version = prepared.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ValueError("新建正式聚合的初始 version 必须为 1")
    prepared["version"] = 1
    return prepared


def build_snapshot_version_filter(document: Mapping[str, Any]) -> dict[str, Any]:
    """按文档的当前版本构造精确查询条件。

    Args:
        document: 写入前读取的正式文档。

    Returns:
        精确匹配当前版本的查询条件。
    """
    return {"version": validate_expected_version(document["version"])}


def build_versioned_cas_filter(
    identity: Mapping[str, Any],
    expected_version: int,
    *,
    is_deleted: bool | None = None,
) -> dict[str, Any]:
    """功能：构造带版本和可选软删除状态的 CAS 查询。

    Args:
        identity: ``_id``、novel_id 与稳定业务 ID 等精确身份条件。
        expected_version: 调用方读取到的正式版本。
        is_deleted: 是否额外锁定活动/回收站状态；None 表示不限制。

    Returns:
        可直接用于 MongoDB 条件写入的查询字典。
    """
    if not identity:
        raise ValueError("CAS identity 不能为空")
    query = {**identity, "version": validate_expected_version(expected_version)}
    if is_deleted is not None:
        query["is_deleted"] = bool(is_deleted)
    return query


def build_versioned_cas_update(
    update_fields: Mapping[str, Any],
    *,
    unset_fields: Sequence[str] = (),
) -> dict[str, Any]:
    """功能：构造每次成功只递增一次版本的 MongoDB 更新文档。

    Args:
        update_fields: 已通过领域白名单过滤的待更新字段。
        unset_fields: 需要显式移除的旧字段名称。

    Returns:
        包含 ``$set``、``$inc`` 和可选 ``$unset`` 的更新文档。

    Raises:
        ValueError: 调用方尝试直接覆盖 version 或没有任何业务变化。
    """
    if "version" in update_fields:
        raise ValueError("CAS 更新不得直接覆盖 version")
    if not update_fields and not unset_fields:
        raise ValueError("CAS 更新至少需要一个业务字段变化")
    update: dict[str, Any] = {
        "$set": {**update_fields, "updated_at": get_utc_now()},
        "$inc": {"version": 1},
    }
    if unset_fields:
        update["$unset"] = {field: "" for field in dict.fromkeys(unset_fields)}
    return update


async def update_versioned_document(
    collection: AsyncCollection,
    identity: Mapping[str, Any],
    expected_version: int,
    update_fields: Mapping[str, Any],
    *,
    is_deleted: bool | None = None,
    unset_fields: Sequence[str] = (),
    session: AsyncClientSession | None = None,
) -> dict[str, Any] | None:
    """功能：执行一次通用 CAS 更新并返回写后的正式文档。

    Args:
        collection: 目标 MongoDB 集合。
        identity: 小说作用域和稳定业务 ID 等精确身份条件。
        expected_version: 调用方持有的版本。
        update_fields: 已由领域服务完整预校验的更新字段。
        is_deleted: 可选活动/回收站状态条件。
        unset_fields: 需要移除的旧字段名称。
        session: 可选 MongoDB 会话。

    Returns:
        CAS 成功后的完整文档；版本或状态未命中时返回 None。
    """
    return await collection.find_one_and_update(
        build_versioned_cas_filter(
            identity,
            expected_version,
            is_deleted=is_deleted,
        ),
        build_versioned_cas_update(update_fields, unset_fields=unset_fields),
        return_document=ReturnDocument.AFTER,
        session=session,
    )


def validate_versioned_batch(
    items: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
) -> list[tuple[str, int]]:
    """功能：预检批量重排等命令中的稳定 ID 与逐项版本。

    Args:
        items: 每项至少包含稳定业务 ID 和 expected_version 的请求序列。
        id_field: 当前领域稳定业务 ID 的字段名。

    Returns:
        保持请求顺序的 ``(business_id, expected_version)`` 列表。

    Raises:
        ValueError: ID 缺失、重复或任一版本非法。
    """
    normalized: list[tuple[str, int]] = []
    seen: set[str] = set()
    for item in items:
        business_id = str(item.get(id_field) or "").strip()
        if not business_id:
            raise ValueError(f"批量项必须提供 {id_field}")
        if business_id in seen:
            raise ValueError(f"批量项不能重复使用 {id_field}: {business_id}")
        seen.add(business_id)
        normalized.append(
            (business_id, validate_expected_version(item.get("expected_version")))
        )
    return normalized


def _json_safe(value: Any) -> Any:
    """功能：把 BSON 与时间对象递归转换为规范 JSON 值。

    Args:
        value: 任意待生成请求摘要的数据。

    Returns:
        只包含 JSON 基础类型的等价值。
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def canonical_request_json(value: Any) -> str:
    """功能：使用固定参数生成可稳定比较的规范 JSON 文本。

    Args:
        value: 待规范化的 BSON、时间或普通 Python 对象。

    Returns:
        键排序、无多余空白的 UTF-8 JSON 文本。
    """
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_request_hash(value: Any) -> str:
    """功能：对规范 JSON 请求载荷计算稳定 SHA-256 摘要。

    Args:
        value: 小说作用域、候选依据与正式确认载荷等请求事实。

    Returns:
        64 位十六进制 SHA-256 字符串。
    """
    serialized = canonical_request_json(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyFingerprint:
    """可安全持久化到目标正式文档的幂等指纹。"""

    key_hash: str
    request_hash: str

    def as_creation_fields(self) -> dict[str, str]:
        """功能：转换为当前目标文档使用的创建幂等字段。

        Args:
            无。

        Returns:
            ``creation_idempotency_key_hash`` 与 ``creation_request_hash``。
        """
        return {
            "creation_idempotency_key_hash": self.key_hash,
            "creation_request_hash": self.request_hash,
        }


def build_idempotency_fingerprint(raw_key: str, request: Any) -> IdempotencyFingerprint:
    """功能：校验原始幂等键并为目标文档生成双摘要。

    Args:
        raw_key: HTTP ``Idempotency-Key`` 原文。
        request: 包含小说作用域、basis、版本和正式载荷的规范请求。

    Returns:
        不包含原始密钥的目标文档幂等指纹。

    Raises:
        ValueError: 幂等键格式非法或请求无法规范 JSON 编码。
    """
    if IDEMPOTENCY_KEY_RE.fullmatch(raw_key or "") is None:
        raise ValueError(
            "Idempotency-Key 必须为 16 到 128 位，只能包含 ASCII 字母、数字和 -_.:"
        )
    return IdempotencyFingerprint(
        key_hash=hashlib.sha256(raw_key.encode("ascii")).hexdigest(),
        request_hash=canonical_request_hash(request),
    )


def resolve_idempotent_replay(
    existing: Mapping[str, Any] | None,
    request_hash: str,
    *,
    label: str,
) -> dict[str, Any] | None:
    """功能：判断目标文档内幂等记录应回放还是返回 409 冲突。

    Args:
        existing: 按小说作用域和幂等键哈希读取的既有正式文档。
        request_hash: 当前规范请求摘要。
        label: 错误信息中的领域对象名称。

    Returns:
        同键同载荷时返回既有文档；无既有文档时返回 None。

    Raises:
        IdempotencyConflictError: 同一幂等键已绑定不同请求摘要。
    """
    if existing is None:
        return None
    if existing.get("creation_request_hash") != request_hash:
        raise IdempotencyConflictError(
            f"同一 Idempotency-Key 已用于不同的{label}请求"
        )
    return dict(existing)


__all__ = [
    "IDEMPOTENCY_KEY_RE",
    "IdempotencyFingerprint",
    "build_idempotency_fingerprint",
    "build_snapshot_version_filter",
    "build_versioned_cas_filter",
    "build_versioned_cas_update",
    "canonical_request_json",
    "canonical_request_hash",
    "ensure_initial_version",
    "resolve_idempotent_replay",
    "update_versioned_document",
    "validate_expected_version",
    "validate_versioned_batch",
]
