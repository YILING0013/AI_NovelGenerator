"""格式审校服务：原始响应校验失败时，调用支持结构化输出的模型修正格式。"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from backend.llm.config import LLMConfig, get_llm_config
from backend.llm.exceptions import LLMSchemaError
from backend.llm.json_guard import reject_duplicate_json_keys
from backend.llm.logger import log_parse_error
from backend.api.error_protocol import DomainApiError
from backend.services.llm.llm_service import LLMService

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
FORMAT_REVIEW_PROMPT_TEMPLATE = (
    "以下是另一个 AI 的原始输出，但格式不符合要求。\n"
    "请只修正不符合目标 Schema 的格式或字段，严格输出合法 JSON，不要输出任何额外内容。\n"
    "保留原文含义、事实和完整句子，不得编造内容，也不得删除与格式或字段限制无关的事实。\n"
    "字段超过长度限制时，在含义不变的前提下精炼措辞，并用完整句子收束；"
    "不得直接截取前 N 字或把句子截成半句。\n"
    "保留不需修正的字段和原文中的可疑字符，不要擅自删除、替换或猜测缺失的原字。\n\n"
    "原始输出:\n{raw_text}"
)


def resolve_format_review_provider(config: LLMConfig | None = None) -> str:
    """解析当前可用的结构化格式审校 Provider。

    Args:
        config: 本次请求固定的模型配置；未提供时读取当前设置。

    Returns:
        已启用且支持 JSON Schema 或 DeepSeek JSON Output 的 Provider 别名。
    """
    llm_cfg = config if config is not None else get_llm_config()

    # 1. 配置显式指定
    configured = llm_cfg.format_review_provider
    if configured:
        if configured in llm_cfg.providers:
            prov = llm_cfg.providers[configured]
            if prov.enabled and ((prov.supports_json_schema and prov.resolved_structured_output_mode != "json_object") or (prov.resolved_structured_output_mode == "json_object" and prov.json_output_enabled)):
                return configured
        logger.warning(
            "配置的 format_review_provider '%s' 不可用（不存在 / 未启用 / 不支持结构化输出），尝试自动查找",
            configured,
        )

    # 2. 自动查找
    for name, cfg in llm_cfg.providers.items():
        if cfg.enabled and ((cfg.supports_json_schema and cfg.resolved_structured_output_mode != "json_object") or (cfg.resolved_structured_output_mode == "json_object" and cfg.json_output_enabled)):
            return name

    raise DomainApiError(
        "FORMAT_REVIEW_PROVIDER_UNAVAILABLE",
        "无可用的结构化格式审校 Provider，请检查设置",
        status_code=503,
    )


async def validate_and_fix_format(
    raw_text: str,
    schema: type[T],
    step_label: str = "",
) -> T:
    """解析原始文本，并在结构失败时执行一次通用格式审校。

    Args:
        raw_text: LLM 返回的原始文本。
        schema: 目标 Pydantic Schema 类型。
        step_label: 用于日志的步骤标识。
    Returns:
        直接解析或经一次审校后的 Schema 实例。
    """
    # 空结果没有可修正的内容，不能交给审校模型重新编造。
    if not raw_text.strip():
        raise DomainApiError(
            "LLM_RESULT_EMPTY", "上游未返回生成结果，请重试或更换模型服务", status_code=502,
        )

    # 先尝试直接解析
    reject_duplicate_json_keys(raw_text)
    try:
        return schema.model_validate_json(raw_text)
    except (ValidationError, ValueError) as parse_err:
        log_parse_error(parse_err, content=raw_text, schema=schema, message=f"{step_label} 响应格式校验失败，准备格式审校")

    # 直接使用当前通用配置，不保存跨请求审校绑定或任务级重试状态。
    reviewer_provider = resolve_format_review_provider()
    logger.info(
        "%s 启用格式审校 provider=%s schema=%s",
        step_label or "unknown",
        reviewer_provider,
        schema.__name__,
    )
    reviewer = LLMService(provider_name=reviewer_provider)
    review_prompt = FORMAT_REVIEW_PROMPT_TEMPLATE.format(raw_text=raw_text)
    reviewed = await reviewer.generate_structured(review_prompt, schema)
    try:
        return schema.model_validate(reviewed)
    except (ValidationError, ValueError) as exc:
        log_parse_error(exc, content=reviewed.model_dump(), schema=schema, message=f"{step_label} 格式审校输出校验失败")
        raise LLMSchemaError("格式审校结果仍不符合目标 Schema") from exc
