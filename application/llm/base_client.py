"""LLM 客户端抽象基类，定义统一的生成接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from pydantic import BaseModel

from application.llm.config import LLMProviderConfig
from application.llm.models import LLMRequest, LLMResponse


class BaseLLMClient(ABC):
    """所有 LLM 服务商客户端的抽象基类。

    子类需实现 text_generate / schema_generate / stream_text 三个核心方法。
    """

    def __init__(self, config: LLMProviderConfig, provider_name: str = "") -> None:
        self.config = config
        self.provider_name = provider_name

    def _resolve_model(self, request: LLMRequest) -> str:
        """确定实际使用的模型名称，请求未指定时回退到服务商默认模型。"""
        return request.model or self.config.default_model

    def _apply_defaults(self, request: LLMRequest) -> LLMRequest:
        """将服务商配置中的生成参数默认值合并到请求中（请求级别优先）。"""
        cfg = self.config
        overrides: dict = {}
        if request.temperature is None and cfg.temperature is not None:
            overrides["temperature"] = cfg.temperature
        if request.top_p is None and cfg.top_p is not None:
            overrides["top_p"] = cfg.top_p
        if request.max_tokens is None and cfg.max_tokens is not None:
            overrides["max_tokens"] = cfg.max_tokens
        if request.presence_penalty is None and cfg.presence_penalty is not None:
            overrides["presence_penalty"] = cfg.presence_penalty
        if request.frequency_penalty is None and cfg.frequency_penalty is not None:
            overrides["frequency_penalty"] = cfg.frequency_penalty
        if not request.system_prompt and cfg.system_prompt:
            overrides["system_prompt"] = cfg.system_prompt
        if not overrides:
            return request
        return request.model_copy(update=overrides)

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """将 system_prompt 与 messages 合并为完整消息列表。"""
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)
        return messages

    @abstractmethod
    async def text_generate(self, request: LLMRequest) -> LLMResponse:
        """普通文本生成。"""

    @abstractmethod
    async def schema_generate(
        self, request: LLMRequest, schema: type[BaseModel]
    ) -> LLMResponse:
        """结构化 JSON 输出，按 Pydantic Schema 约束生成。"""

    @abstractmethod
    async def stream_text(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        """流式文本输出，逐块 yield 生成内容。"""
