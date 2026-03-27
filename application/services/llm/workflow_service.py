"""LLM 工作流服务：支持多步骤 LLM 管道调用，具备 3 级 Provider 回退逻辑。"""

from __future__ import annotations

from application.config import get_config_value
from application.llm.config import get_llm_config
from application.services.llm.llm_service import LLMService


def resolve_provider_for_step(workflow_name: str, step_name: str) -> str | None:
    """按优先级解析步骤应使用的 Provider 别名。

    回退链: step.provider → workflow.default_provider → llm.default_provider
    """
    llm_cfg = get_llm_config()
    workflows = get_config_value("llm", {}).get("workflows", {})
    workflow = workflows.get(workflow_name, {})

    # 1. 步骤级别
    step_cfg = workflow.get("steps", {}).get(step_name, {})
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


def get_llm_service_for_step(workflow_name: str, step_name: str) -> LLMService:
    """创建一个用于指定工作流步骤的 LLMService 实例。"""
    provider = resolve_provider_for_step(workflow_name, step_name)
    if not provider:
        raise ValueError(
            f"无法为工作流 '{workflow_name}' 的步骤 '{step_name}' 找到可用的 Provider，"
            "请检查配置中是否有已启用的 Provider。"
        )
    return LLMService(provider_name=provider)
