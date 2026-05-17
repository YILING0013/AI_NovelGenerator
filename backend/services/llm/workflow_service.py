"""LLM 工作流服务：支持多步骤 LLM 管道调用，具备 Provider 与超时回退逻辑。"""

from __future__ import annotations

from backend.config import get_config_value
from backend.llm.config import get_llm_config
from backend.services.llm.llm_service import LLMService


def _get_workflow_step_config(workflow_name: str, step_name: str) -> dict:
    """读取工作流步骤配置，缺失或结构异常时返回空配置。"""
    workflows = get_config_value("llm", {}).get("workflows", {})
    workflow = workflows.get(workflow_name, {})
    steps = workflow.get("steps", {}) if isinstance(workflow, dict) else {}
    step_cfg = steps.get(step_name, {}) if isinstance(steps, dict) else {}
    return step_cfg if isinstance(step_cfg, dict) else {}


def _coerce_positive_timeout(value: object) -> int | None:
    """将步骤级超时配置转成正整数秒，空值表示继承 Provider 默认值。"""
    if value in (None, ""):
        return None
    try:
        timeout_seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return timeout_seconds if timeout_seconds > 0 else None


def resolve_provider_for_step(workflow_name: str, step_name: str) -> str | None:
    """按优先级解析步骤应使用的 Provider 别名。

    回退链: step.provider → workflow.default_provider → llm.default_provider
    """
    llm_cfg = get_llm_config()
    workflows = get_config_value("llm", {}).get("workflows", {})
    workflow = workflows.get(workflow_name, {})

    # 1. 步骤级别
    step_cfg = _get_workflow_step_config(workflow_name, step_name)
    step_provider = step_cfg.get("provider", "")
    if step_provider:
        # 检查是否存在且启用
        if step_provider in llm_cfg.providers and llm_cfg.providers[step_provider].enabled:
            return step_provider

    # 2. 工作流默认
    wf_default = workflow.get("default_provider", "")
    if wf_default:
        if wf_default in llm_cfg.providers and llm_cfg.providers[wf_default].enabled:
            return wf_default

    # 3. 全局默认
    global_default = llm_cfg.default_provider
    if global_default in llm_cfg.providers and llm_cfg.providers[global_default].enabled:
        return global_default

    return None


def resolve_timeout_for_step(workflow_name: str, step_name: str) -> int | None:
    """解析步骤级 LLM 请求超时；未配置时返回 None 以继承 Provider 超时。"""
    step_cfg = _get_workflow_step_config(workflow_name, step_name)
    return _coerce_positive_timeout(step_cfg.get("timeout_seconds"))


def get_llm_service_for_step(workflow_name: str, step_name: str) -> LLMService:
    """创建一个用于指定工作流步骤的 LLMService 实例。"""
    provider = resolve_provider_for_step(workflow_name, step_name)
    if not provider:
        raise ValueError(
            f"无法为工作流 '{workflow_name}' 的步骤 '{step_name}' 找到可用的 Provider，"
            "请检查配置中是否有已启用的 Provider。"
        )
    return LLMService(
        provider_name=provider,
        timeout_seconds=resolve_timeout_for_step(workflow_name, step_name),
    )
