"""LLM 模块自定义异常体系。"""


class LLMError(Exception):
    """LLM 调用基础异常。"""

    def __init__(self, message: str = "", provider: str = "", model: str = ""):
        self.provider = provider
        self.model = model
        super().__init__(message)


class LLMAuthError(LLMError):
    """API Key 无效或权限不足。"""


class LLMRateLimitError(LLMError):
    """触发服务商速率限制。"""


class LLMTimeoutError(LLMError):
    """请求超时。"""


class LLMResponseError(LLMError):
    """响应内容无效，或模型明确报告输出未完成。"""

    def __init__(self, message: str = "", provider: str = "", model: str = "", *,
                 partial_text: str | None = None) -> None:
        """为明确截断的回复保留有限正文，不能用作生成结果。

        Args:
            message: 错误原因。
            provider: 模型服务名称。
            model: 模型名称。
            partial_text: 仅明确截断时传入模型正文，不含 HTTP 响应或配置。
        Returns:
            无。
        """
        self.partial_text = partial_text[:100_000] if partial_text is not None else None
        self.partial_text_length = len(partial_text) if partial_text is not None else 0
        self.partial_text_truncated = self.partial_text_length > 100_000
        super().__init__(message, provider=provider, model=model)


class LLMSchemaError(LLMError):
    """结构化输出（Schema）生成或解析失败。"""


class LLMDuplicateKeyError(LLMSchemaError):
    """模型 JSON 有重复字段；原文只供排错，不能当候选使用。"""

    def __init__(self, duplicate_path: str, raw_output: str) -> None:
        """限制字段路径和模型原文长度，不携带服务端配置。

        Args:
            duplicate_path: 用 JSON 字符串转义的完整字段路径。
            raw_output: 尚未转成字典的模型正文，不含 HTTP 响应外壳。
        Returns:
            无。
        """
        self.duplicate_path_length = len(duplicate_path)
        self.duplicate_path_truncated = len(duplicate_path) > 1024
        # 路径可能含整段超长键名；末尾标明截断，避免被当作完整字段位置。
        self.duplicate_path = duplicate_path[:1023] + "…" if self.duplicate_path_truncated else duplicate_path
        self.raw_output = raw_output[:100_000]
        self.raw_output_length = len(raw_output)
        self.raw_output_truncated = len(raw_output) > len(self.raw_output)
        super().__init__("模型 JSON 有重复字段，请查看原文并重新生成")
