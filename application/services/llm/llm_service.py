"""LLM 高层服务封装，提供简洁的文本/结构化/流式生成接口。"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from pydantic import BaseModel

from application.llm.factory import create_llm_client
from application.llm.models import LLMRequest, LLMResponse


class LLMService:
    """面向业务层的 LLM 能力封装。

    将底层客户端的请求构造、日志记录等细节隐藏，
    对外暴露 generate_text / generate_structured / stream_text 三个简洁方法。
    """

    def __init__(self, provider_name: str | None = None) -> None:
        self._client = create_llm_client(provider_name)

    def _make_request(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> LLMRequest:
        """将简单参数组装为 LLMRequest。"""
        messages = [{"role": "user", "content": prompt}]
        return LLMRequest(
            messages=messages,
            system_prompt=system_prompt,
            **kwargs,
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> str:
        """普通文本生成，返回纯文本内容。"""
        request = self._make_request(prompt, system_prompt, **kwargs)
        response: LLMResponse = await self._client.text_generate(request)
        return response.content

    async def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        system_prompt: str = "",
        **kwargs: Any,
    ) -> BaseModel:
        """结构化生成，返回解析后的 Pydantic 模型实例。"""
        request = self._make_request(prompt, system_prompt, **kwargs)
        response: LLMResponse = await self._client.schema_generate(request, schema)
        return schema.model_validate(json.loads(response.content))

    async def stream_text(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """流式文本生成，逐块 yield 文本片段。"""
        request = self._make_request(prompt, system_prompt, **kwargs)
        async for chunk in self._client.stream_text(request):
            yield chunk
