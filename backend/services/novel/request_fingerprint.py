"""小说请求的稳定序列化与幂等指纹。"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

from bson import ObjectId

from backend.db.write_contracts import IDEMPOTENCY_KEY_RE
from backend.services.novel.errors import GenerationDomainError


def _json_safe(value: Any) -> Any:
    """把 BSON 和时间对象递归转换成规范 JSON 可编码值。

    Args:
        value: 任意待规范化或哈希的数据。

    Returns:
        只包含 JSON 基础类型的等价数据。
    """
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """使用固定参数生成可稳定比较的 JSON 文本。

    Args:
        value: 待规范化对象。

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


def checksum(value: Any) -> str:
    """计算规范化对象的 SHA-256。

    Args:
        value: 待哈希对象。

    Returns:
        十六进制 SHA-256 字符串。
    """
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def hash_idempotency_key(raw_key: str) -> str:
    """校验并哈希原始 Idempotency-Key，避免原文落库。

    Args:
        raw_key: HTTP 请求头中的原始幂等键。

    Returns:
        原始键的 SHA-256。
    """
    if not IDEMPOTENCY_KEY_RE.fullmatch(raw_key or ""):
        raise GenerationDomainError(
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key 必须为 16 到 128 位，只能包含 ASCII 字母、数字和 -_.:",
            status_code=422,
        )
    return hashlib.sha256(raw_key.encode("ascii")).hexdigest()


__all__ = ["canonical_json", "checksum", "hash_idempotency_key"]
