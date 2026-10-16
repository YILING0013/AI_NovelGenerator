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


class LLMConnectionError(LLMResponseError):
    """连接中断或响应流未结束；已收到片段不能用作完整结果。"""


def network_retry_delay(error: Exception, attempt: int) -> float | None:
    """只识别明确的网络和服务暂时故障，并尊重服务端等待时间。

    Args:
        error: 客户端包装后的异常；沿显式原因读取 SDK 的状态和响应头。
        attempt: 从零开始的本次重试次数。
    Returns:
        等待秒数；鉴权、格式、业务校验或未知故障返回空。
    """
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime
    import math
    import httpx2
    import openai
    import anthropic
    from google.genai.errors import APIError
    from google.genai._gaos.lib.compat_errors import APIStatusError as InteractionStatusError

    if isinstance(error, (LLMAuthError, LLMSchemaError)):
        return None
    current = error.__cause__ or error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (openai.APIStatusError, anthropic.APIStatusError, APIError, InteractionStatusError)):
            status = getattr(current, "status_code", None) or getattr(current, "code", None)
            if status not in {408, 409, 429, 500, 502, 503, 504, 529}:
                return None
            headers = getattr(getattr(current, "response", None), "headers", {}) or {}
            if headers.get("x-should-retry") == "false":
                return None
            value = headers.get("retry-after")
            if value:
                try:
                    delay = float(value)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 0
                if math.isfinite(delay) and delay > 0:
                    return delay
            return float(2 ** attempt)
        if isinstance(current, (openai.APIConnectionError, anthropic.APIConnectionError,
                                httpx2.NetworkError, httpx2.TimeoutException, httpx2.RemoteProtocolError,
                                LLMConnectionError, LLMTimeoutError)):
            return float(2 ** attempt)
        current = current.__cause__
    return None
