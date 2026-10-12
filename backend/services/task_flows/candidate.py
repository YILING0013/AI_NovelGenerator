"""按生成时的图修订复验候选，模型设置变化不会使完成的草稿失效。"""

from __future__ import annotations

from typing import Any, Mapping

from backend.api.error_protocol import DomainApiError
from backend.db.write_contracts import canonical_request_hash
from . import store as task_flow_store
from .graph import flow_fingerprint


def flow_fingerprint_inputs(task: str, generation_input: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """重读原图并核对业务输入，供各领域现有来源指纹复用。

    Args:
        task: 候选所属业务任务。
        generation_input: 领域确认使用的生成输入。
        snapshot: 生成时保存的图引用及非敏感执行快照。
    Returns:
        不依赖当前模型配置的稳定指纹输入。
    """
    from .registry import AGENT_TASKS
    if task in AGENT_TASKS | {"plan_volume_launch_by_ai"} and snapshot.get("execution", {}).get("reading_contract") != "position_v1":
        raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "旧候选未保存按位置读取依据，请保留草稿并重新生成", status_code=409)
    ref = snapshot["flow_ref"]
    flow = task_flow_store.flow_store().get(ref["id"], ref["revision"])
    if flow.task != task or flow_fingerprint(flow) != snapshot["definition_hash"]:
        raise ValueError("生成时的流程版本不存在或内容不一致")
    value = generation_input.model_dump(mode="json") if hasattr(generation_input, "model_dump") else dict(generation_input)
    value.pop("use_stream", None)
    scope = snapshot["scope"]
    if any(scope.get(key) != value[key] for key in ("novel_id", "volume_id", "target_type", "target_id") if key in value):
        raise ValueError("候选资料范围与当前小说或操作位置不一致")
    if task in AGENT_TASKS:
        from .book_tools import normalize_agent_scope
        # 防止在卷范围中额外塞入 target_id，改变资料工具实际采用的位置。
        if normalize_agent_scope(scope, task=task) != normalize_agent_scope(value, task=task):
            raise ValueError("候选资料范围与当前小说或操作位置不一致")
    expected = dict(snapshot["business_input"])
    expected.pop("use_stream", None)
    if canonical_request_hash(value) != canonical_request_hash(expected):
        raise ValueError("确认输入与生成时使用的业务参数不一致")
    return {"generation_input": value, "task_flow": dict(snapshot)}


def compute_flow_candidate_fingerprint(task: str, generation_input: Any, source_refs: Any, snapshot: Mapping[str, Any]) -> str:
    """将原图修订与当前正式来源交给现有候选指纹协议。

    Args:
        task: 业务任务标识。
        generation_input: 实际业务输入。
        source_refs: 确认时重读的完整来源。
        snapshot: 生成时的非敏感快照。
    Returns:
        保留业务 Schema 标识的候选指纹。
    """
    from backend.services.task_flows.registry import TASKS
    from backend.services.llm.candidate_contract import compute_candidate_input_fingerprint
    spec = TASKS[task]
    inputs = flow_fingerprint_inputs(task, generation_input, snapshot)
    return compute_candidate_input_fingerprint(novel_id=snapshot["scope"].get("novel_id"), workflow=task, step=spec.step, schema_id=spec.schema_id, schema_version=spec.schema_version, source_refs=list(source_refs), inputs=inputs)


def compute_preparation_fingerprint(task: str, generation_input: Any, content_fingerprint: str, snapshot: Mapping[str, Any]) -> str:
    """按实际资料确认自动卷准备，祖先的统计版本变化不使候选过期。

    Args:
        task: 当前势力、角色或地点准备任务。
        generation_input: 生成时保存的完整业务输入。
        content_fingerprint: 当前重读的公开资料内容摘要。
        snapshot: 原始图和工具读取快照，不能替换成当前设置。
    Returns:
        绑定原输入、图修订及实际内容的候选指纹。
    """
    return canonical_request_hash({"task": task, "inputs": flow_fingerprint_inputs(task, generation_input, snapshot), "content_fingerprint": content_fingerprint})
