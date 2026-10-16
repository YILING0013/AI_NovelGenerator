"""仅在 Provider 设置页测试期间收集参数和推理证据，不保留响应正文。"""

from contextvars import ContextVar
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr


class ProviderProbeDetails(BaseModel):
    """单项测试的实际生成参数及原生推理证据。"""

    sent_parameters: dict[str, str | int | float | bool] = Field(default_factory=dict)
    parameters_adjusted: bool = False
    reasoning_status: Literal["not_sent", "sent", "rejected", "unknown"] = "not_sent"
    reasoning_tokens: int | None = None
    reasoning_evidence: list[Literal["usage", "native_block", "signature"]] = Field(default_factory=list)
    _send_count: int = PrivateAttr(default=0)
    _http_status: int | None = PrivateAttr(default=None)
    _token_counts: dict[int, int] = PrivateAttr(default_factory=dict)
    _incomplete: bool = PrivateAttr(default=False)


active_provider_probe: ContextVar[ProviderProbeDetails | None] = ContextVar("provider_probe", default=None)

# 只读取 SDK 已生成的请求体；不重建参数，也不复制消息、Schema、地址或认证信息。
_PARAMETER_PATHS = (
    "temperature", "top_p", "presence_penalty", "frequency_penalty",
    "max_tokens", "max_completion_tokens", "max_output_tokens", "reasoning_effort", "verbosity",
    "reasoning.effort", "reasoning.mode", "reasoning.summary", "text.verbosity",
    "thinking.type", "thinking.budget_tokens", "thinking.display", "output_config.effort",
    "generation_config.temperature", "generation_config.top_p", "generation_config.max_output_tokens",
    "generation_config.presence_penalty", "generation_config.frequency_penalty",
    "generation_config.thinking_level", "generation_config.thinking_summaries",
    "generationConfig.temperature", "generationConfig.topP", "generationConfig.maxOutputTokens",
    "generationConfig.presencePenalty", "generationConfig.frequencyPenalty",
    "generationConfig.thinkingConfig.thinkingLevel", "generationConfig.thinkingConfig.thinkingBudget",
    "generationConfig.thinkingConfig.includeThoughts",
    "generationConfig.thinkingConfig.thinking_level", "generationConfig.thinkingConfig.thinking_budget",
    "generationConfig.thinkingConfig.include_thoughts",
)


def observe_provider_request(payload: dict[str, Any]) -> None:
    """从实际请求体取出允许展示的生成参数，重试后保留最后一次。

    Args:
        payload: SDK 即将发送的 JSON 请求体。
    Returns:
        无；测试之外不收集。
    """
    probe = active_provider_probe.get()
    if probe is None:
        return
    parameters = {}
    for path in _PARAMETER_PATHS:
        value = payload
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (str, int, float, bool)):
            parameters[path] = value
    probe.parameters_adjusted |= bool(probe._send_count and probe.sent_parameters != parameters)
    probe.sent_parameters = parameters
    probe._send_count += 1
    probe._http_status = None
    probe.reasoning_status = "unknown" if any(
        "reasoning" in key or "thinking" in key.lower() or key == "output_config.effort"
        for key in parameters
    ) else "not_sent"


def observe_provider_response(response: Any, api_mode: str) -> None:
    """在现有 SDK 响应解析处只记录原生计数及证据类型。

    Args:
        response: 当前客户端正在解析的 SDK 响应或流式事件。
        api_mode: 当前实际使用的接口。
    Returns:
        无；不保存思考正文、签名或加密状态内容。
    """
    probe = active_provider_probe.get()
    if probe is None:
        return
    tokens = None
    native_block = False
    signature = False
    if api_mode == "chat_completions":
        usage = getattr(response, "usage", None)
        tokens = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None)
        for choice in getattr(response, "choices", []):
            message = getattr(choice, "message", None) or getattr(choice, "delta", None)
            native_block |= bool(getattr(message, "reasoning_content", None))
            probe._incomplete |= choice.finish_reason == "length"
    elif api_mode == "responses":
        event_type = getattr(response, "type", "")
        native_block = event_type in {"response.reasoning_text.delta", "response.reasoning_summary_text.delta"}
        item = getattr(response, "item", None)
        response = getattr(response, "response", None) or response
        tokens = getattr(getattr(getattr(response, "usage", None), "output_tokens_details", None), "reasoning_tokens", None)
        for block in [*getattr(response, "output", []), *([item] if item is not None else [])]:
            if block.type == "reasoning":
                native_block = True
                signature |= bool(getattr(block, "encrypted_content", None))
        probe._incomplete |= getattr(response, "status", None) == "incomplete"
    elif api_mode == "messages":
        block = getattr(response, "content_block", None)
        delta = getattr(response, "delta", None)
        for block in [*getattr(response, "content", []), *([block] if block is not None else [])]:
            native_block |= block.type in {"thinking", "redacted_thinking"}
            signature |= bool(getattr(block, "signature", None)) or block.type == "redacted_thinking"
        native_block |= getattr(delta, "type", None) == "thinking_delta"
        signature |= getattr(delta, "type", None) == "signature_delta"
        probe._incomplete |= (getattr(response, "stop_reason", None) or getattr(delta, "stop_reason", None)) == "max_tokens"
    elif api_mode == "generate_content":
        tokens = getattr(getattr(response, "usage_metadata", None), "thoughts_token_count", None)
        for candidate in response.candidates or []:
            probe._incomplete |= candidate.finish_reason == "MAX_TOKENS"
            for part in candidate.content.parts if candidate.content else []:
                native_block |= bool(part.thought)
                signature |= bool(part.thought_signature)
    elif api_mode == "interactions":
        delta = getattr(response, "delta", None)
        native_block = getattr(delta, "type", None) == "thought_summary"
        signature = getattr(delta, "type", None) == "thought_signature"
        step = getattr(response, "step", None)
        response = getattr(response, "interaction", None) or response
        tokens = getattr(getattr(response, "usage", None), "total_thought_tokens", None)
        for step in [*(getattr(response, "steps", None) or []), *([step] if step is not None else [])]:
            if step.type == "thought":
                native_block = True
                signature |= bool(getattr(step, "signature", None))
        probe._incomplete |= getattr(response, "status", None) == "incomplete"
    if tokens is not None:
        # 流式用量通常是累计值，同一请求覆盖；工具两轮则按请求求和。
        probe._token_counts[probe._send_count] = tokens
        probe.reasoning_tokens = sum(probe._token_counts.values())
    for observed, evidence in ((tokens is not None and tokens > 0, "usage"), (native_block, "native_block"), (signature, "signature")):
        if observed and evidence not in probe.reasoning_evidence:
            probe.reasoning_evidence.append(evidence)
