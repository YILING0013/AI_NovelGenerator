"""在模型 JSON 转成字典前检查重复字段，结构校验仍交给原有 Schema。"""

from __future__ import annotations

import json
import re

from backend.llm.exceptions import LLMDuplicateKeyError


_THINK_BOUNDARY = re.compile(r"\s*(?:<think\b[^>]*>.*?</think>|</think>)\s*", re.IGNORECASE | re.DOTALL)


class _ObjectPairs(list):
    """保留对象内的全部键值对，并与 JSON 数组区分。"""


def reject_duplicate_json_keys(raw: str) -> None:
    """拒绝同一对象内的重复字段，不返回可被误用为候选的解析结果。

    Args:
        raw: 模型输出的原始 JSON 正文。
    Returns:
        无；重复字段抛出专用错误，非 JSON 仍由原来的解析流程处理。
    """
    # 只越过正文外的思考块；全局清洗会把 JSON 字符串中的重复字段一起删掉。
    start = 0
    while match := _THINK_BOUNDARY.match(raw, start):
        start = match.end()
    json_start = start + len(raw[start:]) - len(raw[start:].lstrip())
    try:
        # 只检查键；保留数字原文，避免改变原解析器的大数字处理方式。
        value, json_end = json.JSONDecoder(object_pairs_hook=_ObjectPairs, parse_int=str, parse_float=str).raw_decode(raw, json_start)
    except (json.JSONDecodeError, RecursionError):
        return
    if start or raw[json_end:].strip():
        # 诊断保留完整 JSON 证据，但不能向页面发送模型的思考内容。
        raw = raw[json_start:json_end]
    # 尾部即使不完整，主体中的重复字段也已确定，不能让后续清洗抹掉证据。
    pending = [(value, "$")]
    while pending:
        value, path = pending.pop()
        if isinstance(value, _ObjectPairs):
            seen = set()
            children = []
            for key, child in value:
                child_path = f"{path}[{json.dumps(key, ensure_ascii=True)}]"
                if key in seen:
                    raise LLMDuplicateKeyError(child_path, raw)
                seen.add(key)
                children.append((child, child_path))
            pending.extend(reversed(children))
        elif isinstance(value, list):
            pending.extend((child, f"{path}[{index}]") for index, child in reversed(list(enumerate(value))))
