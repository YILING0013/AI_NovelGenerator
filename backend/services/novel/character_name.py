"""角色显示名及名称唯一性比较键。"""

from __future__ import annotations

import unicodedata


def normalize_character_name(name: str) -> tuple[str, str]:
    """规范化角色显示名和唯一性比较键。

    Args:
        name: 用户、模型或历史角色文档提供的角色名称。

    Returns:
        NFKC 规范化后的显示名，以及继续执行 casefold 的唯一性比较键。

    Raises:
        ValueError: 名称为空，或 NFKC 规范化后超过 80 个字符。
    """
    display_name = unicodedata.normalize("NFKC", str(name or "")).strip()
    normalized_name = display_name.casefold()
    if not normalized_name:
        raise ValueError("角色名称不能为空")
    if len(display_name) > 80:
        # Schema 校验发生在 NFKC 之前；兼容字符展开后必须再次执行持久化长度约束。
        raise ValueError("角色名称经 Unicode NFKC 规范化后不能超过 80 个字符")
    return display_name, normalized_name


__all__ = ["normalize_character_name"]
