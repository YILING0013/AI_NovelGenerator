"""任务方案的读取、版本化编辑和默认选择接口。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from pydantic import Field, ValidationError

from backend.api.error_protocol import DomainApiError
from backend.services.task_flows.contracts import Flow, FlowConflictError, FlowModel, FlowRef, FlowValidationError, PreviewRequest
from backend.services.task_flows.defaults import builtin_flow
from backend.services.task_flows import store as task_flow_store
from backend.services.task_flows.registry import TASKS, validate_task_definition
from backend.services.task_flows.preview import preview_task_flow


router = APIRouter(prefix="/api/task-flows", tags=["task-flows"])


class CreateFlow(FlowModel):
    """复制当前或内置方案，创建独立方案 ID。"""
    task: str
    name: str = Field(min_length=1, max_length=200)
    definition: Flow | None = None
    copy_from: FlowRef | None = None


class SaveFlow(FlowModel):
    """编辑时读到的修订与待保存图。"""
    expected_revision: int = Field(ge=1)
    definition: Flow


class ValidateFlow(FlowModel):
    """允许编辑器提交尚未通过检查的图。"""
    definition: dict[str, Any]


class DefaultFlow(FlowModel):
    """锁定默认方案修改时的目录版本。"""
    flow_ref: FlowRef
    expected_version: int = Field(ge=0)


def _error(exc: Exception) -> DomainApiError:
    if isinstance(exc, FlowConflictError):
        return DomainApiError("TASK_FLOW_VERSION_CONFLICT", str(exc), status_code=409)
    if isinstance(exc, KeyError):
        return DomainApiError("TASK_FLOW_NOT_FOUND", "任务或方案修订不存在", status_code=404)
    return DomainApiError("TASK_FLOW_INVALID", "流程定义有误", details={"errors": [str(exc)]})


@router.get("/tasks")
async def task_contracts():
    """列出业务任务的结果契约及默认方案引用。

    Returns:
        任务名称、业务输入输出 Schema 和默认方案修订。
    """
    tasks = []
    for task, spec in TASKS.items():
        flow = task_flow_store.flow_store().get_default(task)
        tasks.append({"task": task, "label": spec.label, "input_schema": spec.request_model.model_json_schema(), "output_schema": spec.result_model.model_json_schema(), "default_ref": {"id": flow.id, "revision": flow.revision}})
    return {"tasks": tasks}


@router.get("")
async def list_task_flows(task: str):
    """列出指定任务的方案和默认选择。

    Args:
        task: 原业务任务标识。
    Returns:
        方案摘要、默认引用和目录版本。
    """
    try:
        task_flow_store.flow_store().get_default(task)
        result = task_flow_store.flow_store().list_flows(task)
        return {"flows": result["flows"], "default_ref": result["defaults"].get(task), "version": result["version"]}
    except (KeyError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/builtin/{task}")
async def get_builtin_flow(task: str):
    """读取随程序发布的图，恢复操作由编辑器保存为新修订。

    Args:
        task: 原业务任务标识。
    Returns:
        未写入用户配置的内置方案。
    """
    try:
        return builtin_flow(task)
    except KeyError as exc:
        raise _error(exc) from exc


@router.post("/validate")
async def validate_task_flow(request: ValidateFlow):
    """返回可在属性面板就地显示的流程检查结果。

    Args:
        request: 尚未保存的图定义。
    Returns:
        valid 和错误数组，不写文件。
    """
    try:
        flow = validate_task_definition(request.definition)
        return {"valid": True, "errors": []}
    except (FlowValidationError, ValidationError, ValueError) as exc:
        return {"valid": False, "errors": [{"message": value} for value in (exc.errors if isinstance(exc, FlowValidationError) else [str(exc)])]}


@router.post("")
async def create_task_flow(request: CreateFlow):
    """复制方案为新的独立方案，不改变任务默认选择。

    Args:
        request: 任务、名称以及复制来源或完整定义。
    Returns:
        新方案的首个修订。
    """
    try:
        if request.task not in TASKS:
            raise KeyError(request.task)
        if request.definition:
            flow = request.definition
        elif request.copy_from:
            flow = task_flow_store.flow_store().get(request.copy_from.id, request.copy_from.revision)
        else:
            flow = task_flow_store.flow_store().get_default(request.task)
        if flow.task != request.task:
            raise ValueError("复制来源必须属于当前任务")
        validate_task_definition(flow)
        return task_flow_store.flow_store().save(flow.model_copy(update={"id": f"flow_{uuid4().hex}", "name": request.name, "revision": 1}, deep=True), 0)
    except (KeyError, ValueError) as exc:
        raise _error(exc) from exc


@router.post("/preview")
async def preview_task_flow_definition(request: PreviewRequest):
    """读取小说资料并模拟当前草稿，不调用模型或保存任何内容。

    Args:
        request: 流程草稿、资料范围和本次临时示例。
    Returns:
        节点端口资料、执行步骤及模拟错误；不影响保存检查。
    """
    return await preview_task_flow(request.definition, request.scope,
                                   [item.model_dump(mode="json") for item in request.overrides])


@router.put("/default/{task}")
async def set_default_flow(task: str, request: DefaultFlow):
    """使用目录版本检查修改默认方案。

    Args:
        task: 当前业务任务。
        request: 明确方案修订与已读取的目录版本。
    Returns:
        保存后的默认引用和目录版本。
    """
    try:
        result = task_flow_store.flow_store().set_default(task, request.flow_ref.id, request.flow_ref.revision, request.expected_version)
        return {"default_ref": result["flow_ref"], "version": result["version"]}
    except (KeyError, ValueError) as exc:
        raise _error(exc) from exc


@router.get("/{flow_id}")
async def get_task_flow(flow_id: str, revision: int | None = None):
    """读取最新或指定的不可变方案修订。

    Args:
        flow_id: 方案 ID。
        revision: 指定历史修订；为空时取最新。
    Returns:
        完整流程定义。
    """
    try:
        return task_flow_store.flow_store().get(flow_id, revision)
    except (KeyError, ValueError) as exc:
        raise _error(exc) from exc


@router.put("/{flow_id}")
async def save_task_flow(flow_id: str, request: SaveFlow):
    """在原修订未变化时保存新修订，历史内容保持不变。

    Args:
        flow_id: 正在编辑的方案 ID。
        request: 完整定义与编辑时的最新修订号。
    Returns:
        带新修订号的方案。
    """
    try:
        if flow_id != request.definition.id:
            raise ValueError("路径和定义中的方案 ID 不一致")
        validate_task_definition(request.definition)
        return task_flow_store.flow_store().save(request.definition, request.expected_revision)
    except (KeyError, ValueError) as exc:
        raise _error(exc) from exc
