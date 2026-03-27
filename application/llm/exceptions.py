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
    """响应内容解析失败。"""


class LLMSchemaError(LLMError):
    """结构化输出（Schema）生成或解析失败。"""
