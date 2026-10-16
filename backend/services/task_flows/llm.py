"""使用请求开始时固定的模型配置执行图中的 AI 节点。"""

from __future__ import annotations

import logging
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.api.error_protocol import DomainApiError
from backend.llm.config import LLMConfig
from backend.llm.exceptions import LLMSchemaError
from backend.llm.json_guard import reject_duplicate_json_keys
from backend.llm.logger import log_parse_error
from backend.runtime import bind_log_context
from backend.llm.factory import create_llm_client_from_config
from backend.llm.models import LLMRequest, TokenUsage
from backend.services.llm.format_review_service import FORMAT_REVIEW_PROMPT_TEMPLATE, resolve_format_review_provider
from backend.services.novel.chapter_check_contract import CHAPTER_WORLD_RULES_CHECK_TASK
from .contracts import Flow, Node
from .agent_continuation import FlowContinuationState, update_agent_continuation
from .engine import render_template
from .graph import canonical_hash, compile_output_model
from .registry import GENERATION_FIELDS

logger = logging.getLogger(__name__)


def build_flow_request(node: Node, inputs: dict[str, Any], schema: type[BaseModel],
                       parameters: dict[str, Any], *, use_stream: bool,
                       supports_streaming: bool, supports_json_schema: bool) -> tuple[LLMRequest, bool, bool]:
    """按本轮输入生成完整节点请求，供正式执行和编辑器模拟共同使用。

    Args:
        node: AI 节点及其提示词配置。
        inputs: 本次实例实际收到的输入。
        schema: 节点的输出模型。
        parameters: 本次业务请求的公共生成参数。
        use_stream: 本次请求是否启用流式。
        supports_streaming: 所选服务是否支持流式。
        supports_json_schema: 所选服务是否支持原生结构化输出。
    Returns:
        渲染后的请求、是否流式、是否使用原生结构化输出。
    """
    cfg = node.config
    options = {**parameters, **{key: value for key, value in cfg.get("parameters", {}).items() if value is not None}}
    if cfg.get("system_prompt") is not None:
        options["system_prompt"] = render_template(cfg["system_prompt"], inputs)
    if cfg.get("model"):
        options["model"] = cfg["model"]
    stream = bool(use_stream and supports_streaming)
    structured = cfg.get("mode", "json") == "json"
    native = structured and not stream and supports_json_schema
    base = cfg.get("prompt", "")
    prompt = render_template(base, inputs)
    suffix_key = "schema_prompt" if native and not cfg.get("force_text_prompt") else "text_prompt"
    suffix = cfg.get(suffix_key, "")
    if cfg.get("format_suffix"):
        suffix = render_template(suffix, inputs)
    if suffix:
        if not cfg.get("preserve_prompt_whitespace"):
            prompt, suffix = prompt.rstrip(), suffix.strip()
        prompt += cfg.get("prompt_separator", "\n\n") + suffix
    if cfg.get("strip_prompt"):
        prompt = prompt.strip()
    if structured:
        options["json_output_schema"] = schema.model_json_schema()
        if cfg.get("append_output_schema"):
            # 文本与原生输出共用本次编译的端口定义，避免提示词副本与协议漂移。
            prompt += "\n\nJSON Schema:\n" + json.dumps(options["json_output_schema"], ensure_ascii=False)
    return LLMRequest(messages=[{"role": "user", "content": prompt}], **options), stream, native


class FlowModels:
    """固定本次请求的 Provider、生成参数及格式审校配置。"""

    def __init__(self, flow: Flow, config: LLMConfig, parameters: dict[str, Any], use_stream: bool, *, repairing: bool = False) -> None:
        """复制配置并提前检查节点可用性。

        Args:
            flow: 本次执行的完整图。
            config: 请求开始时读取的模型配置。
            parameters: 原页面的公共生成参数。
            use_stream: 是否使用 Provider 的文本流接口。
            repairing: 是否只调用修复模型，无须检查原生成节点的 Provider。
        """
        self.config = config.model_copy(deep=True)
        self.task = flow.task
        self.parameters = {k: v for k, v in parameters.items() if k in GENERATION_FIELDS and v is not None}
        self.use_stream = use_stream
        self.before_send: Callable[..., Awaitable[dict[str, Any]]] | None = None
        self.recovery_state: FlowContinuationState | None = None
        self.recovery_token: str | None = None
        self.defaults: dict[int, str] = {}
        self.output_models: dict[int, type[BaseModel]] = {}
        pending = [] if repairing else [flow]
        while pending:
            graph = pending.pop()
            pending.extend(graph.subflows.values())
            for node in graph.nodes:
                if node.type not in {"llm", "agent"}:
                    continue
                self.defaults[id(node)] = graph.default_provider or config.default_provider
                provider = node.config.get("provider") or graph.default_provider or config.default_provider
                if not node.config.get("provider_input"):
                    provider_config = self._provider(provider)
                    if node.type == "agent" and not provider_config.supports_function_calling:
                        raise DomainApiError("AGENT_PROVIDER_UNSUPPORTED", f"节点 {node.label or node.id} 的模型服务不支持 Function Calling，请修改模型设置", status_code=422)
                options = {**self.parameters, **node.config.get("parameters", {})}
                if node.config.get("system_prompt") is not None:
                    options["system_prompt"] = node.config["system_prompt"]
                LLMRequest.model_validate(options)
                self.output_models[id(node)] = compile_output_model(node)
        self.snapshot = {
            "default_provider": self.config.default_provider,
            "format_review_provider": self.config.format_review_provider,
            "parameters": self.parameters,
            "use_stream": use_stream,
            # 不向浏览器发送密钥、接入地址或代理信息。
            "providers": {name: value.model_dump(exclude={"api_key", "base_url", "use_system_proxy"})
                          for name, value in self.config.providers.items()},
        }

    def _provider(self, name: str):
        value = self.config.providers.get(name)
        if value is None or not value.enabled or not value.api_key:
            raise DomainApiError("LLM_PROVIDER_UNAVAILABLE", f"模型服务 {name} 不可用，请检查节点和模型设置", status_code=503)
        return value

    def resolve_provider(self, node: Node, inputs: dict[str, Any]):
        """按节点实际输入选择本次快照中的模型，不自动切换到其他服务。

        Args:
            node: 当前 AI 或资料整理节点。
            inputs: 当前实例实际输入。
        Returns:
            服务名和已经验证可用的配置。
        """
        cfg = node.config
        name = (inputs.get(cfg["provider_input"]) if cfg.get("provider_input") else None) or cfg.get("provider") or self.defaults.get(id(node)) or self.config.default_provider
        return name, self._provider(name)

    async def repair_result(self, candidate: dict[str, Any], message: str, schema: type[BaseModel], context: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """用现有格式审校模型修复一次候选，不重新执行生成节点。

        Args:
            candidate: 仍需修复的完整响应。
            message: 后端重新校验得到的具体问题。
            schema: 原任务最终候选的结构。
            context: 原业务输入与当前已核对版本的资料。
        Yields:
            修复进度，以及尚待原业务规则复验的候选。
        """
        provider = resolve_format_review_provider(self.config)
        config = self._provider(provider)
        client = create_llm_client_from_config(config, provider_name=provider)
        client.before_send = self.before_send
        instructions = (
            "修复下面已有的核心势力响应。保留与校验错误无关的势力设定、名称、候选引用和字段，"
            "只修改解决校验错误所必需的内容，不要重新创作整份候选。\n"
            "independent_faction_count 指本批不建立直接关系的势力数量，即本批 faction_relations 的 source 和 target 都未引用的候选势力数量；"
            "与已有势力的关系也计入。这里只限制本批关系输出，不代表势力永久独立、不隶属其他势力或隐藏存在。"
            "严格满足原业务输入的势力总数和本批不建立直接关系的数量，不得修改请求数量或已有正式资料。\n"
        ) if self.task == "create_factions_by_ai" else (
            "修复下面已有的卷规划响应。保留原有故事、卷数、顺序、标题、候选引用和所有无关字段，"
            "只修改解决校验错误所必需的内容，不要重新创作整份规划。\n"
            "相邻候选卷按 order_index 排序后，前卷 planning.end_state 与后卷 planning.start_state "
            "必须逐字相同：保留前卷终点原文并复制给后卷起点，不得换成同义句。"
            "append 首卷起点必须复制已有末卷终点；replan 首末边界必须分别复制区间外相邻卷的状态，"
            "不得修改已有正式卷。单卷启动规划也必须遵守原始输入中锁定的状态与预算。\n"
        )
        prompt = (
            instructions
            + "返回符合所附 JSON Schema 的完整 JSON，不要只返回补丁、Markdown 代码块或解释。\n\n"
            f"校验错误：{message}\n\n"
            f"业务输入及参考资料：\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"待修复响应：\n{json.dumps(candidate, ensure_ascii=False)}\n\n"
            f"JSON Schema：\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        options = {key: value for key, value in self.parameters.items() if key != "system_prompt"}
        request = LLMRequest(messages=[{"role": "user", "content": prompt}], json_output_schema=schema.model_json_schema(), **options)
        yield {"status": "progress", "provider": provider, "model": config.default_model, "message": "正在修复响应"}
        if self.before_send is not None:
            await self.before_send()
        with bind_log_context(stage="response_repair"):
            response = await client.text_generate(request)
        reject_duplicate_json_keys(response.content)
        try:
            result = json.loads(response.content)
        except ValueError as exc:
            raise LLMSchemaError("修复响应不是合法 JSON，请再次修复") from exc
        if not isinstance(result, dict):
            raise LLMSchemaError("修复响应必须是 JSON 对象，请再次修复")
        # 结构和业务规则统一在末端复验，失败时也保留本次完整响应。
        yield {"status": "done", "candidate": result}

    async def execute(self, node: Node, inputs: dict[str, Any], instance_path: str) -> AsyncIterator[dict[str, Any]]:
        """执行节点生成和格式审校；恢复时复用服务端已完整返回的响应。

        Args:
            node: 正在运行的 AI 节点。
            inputs: 连线和常量计算出的实际输入。
            instance_path: 顶层、子流程或批次中的唯一实例位置。
        Yields:
            进度事件，以及最后含完整 outputs 的完成事件。
        """
        cfg = node.config
        provider, config = self.resolve_provider(node, inputs)
        structured = cfg.get("mode", "json") == "json"
        schema = self.output_models[id(node)]
        # JSON Output 不约束 Schema；普通请求沿文本入口遵守自身的能力开关。
        request, stream, native = build_flow_request(
            node, inputs, schema, self.parameters, use_stream=self.use_stream,
            supports_streaming=config.supports_streaming,
            supports_json_schema=config.supports_json_schema and config.resolved_structured_output_mode != "json_object",
        )
        checkpoint = self.recovery_state.model_call if self.recovery_state is not None else None
        if checkpoint is not None:
            fingerprint = canonical_hash({"request": request.model_dump(mode="json"), "provider": provider,
                "stream": stream, "native": native, "schema": schema.model_json_schema()})
            if checkpoint.get("request_fingerprint", fingerprint) != fingerprint:
                raise DomainApiError("AGENT_CONTINUATION_CHANGED", "未完成模型调用的请求已变化，请重新生成", status_code=409)
            checkpoint["request_fingerprint"] = fingerprint
        if checkpoint is None or "raw" not in checkpoint:
            client = create_llm_client_from_config(config, provider_name=provider, timeout_seconds=cfg.get("timeout_seconds"))
            client.before_send = self.before_send
        usage = TokenUsage()
        model_calls = 1
        usage_complete = False
        if self.before_send is not None:
            await self.before_send()
        if checkpoint is not None and "raw" in checkpoint:
            raw = checkpoint["raw"]
            usage = TokenUsage.model_validate(checkpoint["usage"])
            usage_complete = checkpoint["usage_complete"]
        elif stream:
            chunks = []
            characters = 0
            last_emit = 0.0
            async with aclosing(client.stream_text(request)) as stream_events:
                async for chunk in stream_events:
                    chunks.append(chunk)
                    characters += len(chunk)
                    now = perf_counter()
                    if len(chunks) == 1 or now - last_emit >= 1:
                        last_emit = now
                        yield {"status": "progress", "chunk_count": len(chunks), "characters": characters, "provider": provider, "model": request.model or config.default_model}
            raw = "".join(chunks).strip()
        elif native:
            response = await client.schema_generate(request, schema)
            raw, usage = response.content, response.usage
            usage_complete = usage.total_tokens > 0
        else:
            response = await client.text_generate(request)
            raw, usage = response.content, response.usage
            usage_complete = usage.total_tokens > 0
        if checkpoint is not None and "raw" not in checkpoint:
            # 只在 SDK 完整返回后保存；必须早于下一个 yield，断线也不能重付这次调用。
            checkpoint.update(raw=raw, usage=usage.model_dump(), usage_complete=usage_complete)
            update_agent_continuation(self.recovery_token, size=self.recovery_state.size())
        yield {"status": "progress", "usage": usage.model_dump(), "model_calls": model_calls, "usage_complete": usage_complete}
        # 空结果没有可修正的内容，不能交给审校模型重新编造。
        if not raw.strip():
            raise DomainApiError(
                "LLM_RESULT_EMPTY", "上游未返回生成结果，请重试或更换模型服务", status_code=502,
            )
        if not structured:
            output_port = cfg.get("output_port", next(iter(node.outputs)))
            yield {"status": "done", "outputs": {output_port: raw}, "usage": usage.model_dump(), "model_calls": model_calls, "usage_complete": usage_complete}
            return
        # 重复键会丢失内容，不能交给自动格式审校猜测该保留哪一份。
        reject_duplicate_json_keys(raw)
        try:
            result = schema.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            log_parse_error(exc, content=raw, schema=schema, message="节点输出校验失败" if native or self.task == CHAPTER_WORLD_RULES_CHECK_TASK else "节点输出校验失败，准备格式审校")
            if native:
                raise LLMSchemaError("Provider 原生结构化结果不符合节点输出") from exc
            if self.task == CHAPTER_WORLD_RULES_CHECK_TASK:
                # 缺失或非法的疑点不能由另一次模型调用补成“没有疑点”。
                raise LLMSchemaError("世界规则检查结果格式不正确，请重新检查") from exc
            # 沿用一次格式审校，使用请求开始时的配置，取消与错误直接向外传播。
            reviewer_name = resolve_format_review_provider(self.config)
            logger.info("[格式审校开始] provider=%s", reviewer_name)
            yield {"status": "progress", "review_state": "running", "message": "正在修正输出格式", "provider": reviewer_name}
            review_request = LLMRequest(messages=[{"role": "user", "content": FORMAT_REVIEW_PROMPT_TEMPLATE.format(raw_text=raw)}])
            if checkpoint is not None:
                fingerprint = canonical_hash({"request": review_request.model_dump(mode="json"), "provider": reviewer_name,
                    "schema": schema.model_json_schema()})
                if checkpoint.get("review_request_fingerprint", fingerprint) != fingerprint:
                    raise DomainApiError("AGENT_CONTINUATION_CHANGED", "未完成格式审校的请求已变化，请重新生成", status_code=409)
                checkpoint["review_request_fingerprint"] = fingerprint
            if self.before_send is not None:
                await self.before_send()
            if checkpoint is not None and "reviewed" in checkpoint:
                reviewed_raw = checkpoint["reviewed"]
                reviewed_usage = TokenUsage.model_validate(checkpoint["reviewed_usage"])
            else:
                reviewer = create_llm_client_from_config(self._provider(reviewer_name), provider_name=reviewer_name)
                reviewer.before_send = self.before_send
                with bind_log_context(stage="format_review"):
                    reviewed = await reviewer.schema_generate(review_request, schema)
                reviewed_raw, reviewed_usage = reviewed.content, reviewed.usage
                if checkpoint is not None:
                    checkpoint.update(reviewed=reviewed_raw, reviewed_usage=reviewed_usage.model_dump())
                    update_agent_continuation(self.recovery_token, size=self.recovery_state.size())
            model_calls += 1
            usage_complete = usage_complete and reviewed_usage.total_tokens > 0
            usage = TokenUsage(**{key: value + reviewed_usage.model_dump()[key] for key, value in usage.model_dump().items()})
            yield {"status": "progress", "usage": usage.model_dump(), "model_calls": model_calls, "usage_complete": usage_complete}
            reject_duplicate_json_keys(reviewed_raw)
            try:
                result = schema.model_validate_json(reviewed_raw)
            except (ValidationError, ValueError) as review_error:
                log_parse_error(review_error, content=reviewed_raw, schema=schema, message="格式审校输出校验失败")
                raise LLMSchemaError("格式审校结果仍不符合节点输出") from review_error
            logger.info("[格式审校完成] provider=%s", reviewer_name)
            yield {"status": "progress", "review_state": "done", "message": "输出格式已修正"}
        yield {"status": "done", "outputs": result.model_dump(mode="json"), "usage": usage.model_dump(), "model_calls": model_calls, "usage_complete": usage_complete}
