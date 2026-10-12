"""共用的目录顺序与事实生效位置判断，不读取数据库。"""

from __future__ import annotations

from typing import Any

from bson import ObjectId


PARENTS = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}


def writing_order(kind: str, document: dict[str, Any], directories: dict[str, dict[ObjectId, dict[str, Any]]]) -> tuple[int, ...] | None:
    """沿完整活动父链计算目录顺序，不用客户端章号或最后正文代替位置。

    Args:
        kind: 当前目录类别。
        document: 当前目录记录。
        directories: 本书四级活动目录。
    Returns:
        从卷到当前层级的顺序；父级已回收时为空。
    """
    if document.get("is_deleted"):
        return None
    values = [document["order_index"]]
    while kind != "volume":
        parent = PARENTS[kind]
        parent_document = directories[parent].get(document[f"{parent}_id"])
        if parent_document is None or parent_document.get("is_deleted"):
            return None
        if any(document.get(f"{ancestor}_id") != parent_document.get(f"{ancestor}_id")
               for ancestor in ("novel", "volume", "arc")
               if f"{ancestor}_id" in parent_document):
            return None
        document = parent_document
        values.append(document["order_index"])
        kind = parent
    return tuple(reversed(values))


def fact_position_visible(record_position: dict[str, Any], read_position: dict[str, Any], directories: dict[str, dict[ObjectId, dict[str, Any]]]) -> bool | None:
    """按同一活动目录判断事实是否已生效，保留同章的前后区别。

    Args:
        record_position: 已校验同书的书初、章前或章后记录锚，不使用缓存章号。
        read_position: resolve_writing_position 返回的同书读取位置。
        directories: 解析读取位置时使用的本书四级活动目录。
    Returns:
        True 为已生效，False 为尚未生效；None 表示来源无法定位，调用方须标为待复核。
    """
    if record_position["intent"] == "book_start":
        return True
    kind = record_position["target_type"]
    anchor = directories[kind].get(ObjectId(record_position["target_id"]))
    order = writing_order(kind, anchor, directories) if anchor is not None else None
    if order is None:
        # 回收章的旧序号可能已被兄弟占用，不能据此排除其对当前字段的影响。
        return None
    if read_position["intent"] == "book_start":
        return False
    boundary = tuple(read_position["order"])
    if record_position["intent"] == "volume_start":
        # 卷锚跟随真实卷身份和顺序；同卷所有读取均在本卷开始之后。
        return order <= boundary
    if read_position["intent"] == "append":
        return order[:len(boundary)] <= boundary
    if order != boundary:
        return order < boundary
    return record_position["intent"] == "chapter_before" or read_position["intent"] == "chapter_after"
