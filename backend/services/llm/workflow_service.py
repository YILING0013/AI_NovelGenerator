"""生成资料的输入预算检查。"""

from typing import Any

from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import canonical_json


def ensure_text_budget(
    value: Any,
    *,
    max_chars: int,
    code: str,
    label: str,
) -> None:
    """在调用模型前执行不可截断的字符预算检查。

    Args:
        value: 将进入提示词的规范化对象。
        max_chars: 允许的规范 JSON 最大字符数。
        code: 超限时返回的稳定错误码。
        label: 用户可读的输入名称。

    Returns:
        校验通过时不返回内容。
    """
    actual_chars = len(canonical_json(value))
    if actual_chars > max_chars:
        raise GenerationDomainError(
            code,
            f"{label}超出输入预算：{actual_chars} > {max_chars} 字符",
            status_code=422,
        )
