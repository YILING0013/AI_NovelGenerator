"""小说领域使用的错误码、错误文本和状态。"""

from __future__ import annotations


class GenerationDomainError(Exception):
    """携带稳定错误码与 HTTP 状态的小说业务错误。"""

    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        """初始化小说业务错误。

        Args:
            code: 供 API 与前端稳定判断的错误码。
            message: 可安全返回给用户的错误说明。
            status_code: 建议 HTTP 状态码。

        Returns:
            无。
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


__all__ = ["GenerationDomainError"]
