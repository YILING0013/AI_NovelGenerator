"""在当前请求中按连线执行任务图，沿用页面取消和本地结果续跑。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from contextlib import aclosing
from copy import deepcopy
import json
import logging
import re
import time
from typing import Any

from backend.api.error_protocol import DomainApiError, sse_error_payload
from backend.runtime import bind_log_context

from .contracts import FOREACH_DEFAULT_MAX_ITEMS, CachedNode, Flow, FlowValidationError, Node
from .graph import canonical_hash, flow_fingerprint, port_schema, template_fields, validate_flow, validate_values


logger = logging.getLogger(__name__)

ContextCallback = Callable[[Node, dict[str, Any]], Awaitable[dict[str, Any]]]
LLMCallback = Callable[[Node, dict[str, Any], str], AsyncIterator[dict[str, Any]]]
AgentCallback = Callable[[Node, dict[str, Any], str], AsyncIterator[dict[str, Any]]]
PreviewCallback = Callable[[Node, dict[str, Any], str], Awaitable[dict[str, Any]]]
CandidateCheckCallback = Callable[[Node, dict[str, Any]], Awaitable[bool]]
ReviewEvidenceCallback = Callable[[Node, dict[str, Any], dict[str, Any]], dict[str, Any]]


def render_template(template: str, inputs: Mapping[str, Any]) -> str:
    """渲染节点输入，结构值使用稳定 JSON 而不是 Python 字典文字。

    Args:
        template: 使用普通花括号字段名的模板。
        inputs: 节点的有效输入。

    Returns:
        可直接发送给模型的文字。
    """
    required = template_fields(template)
    missing = required - set(inputs)
    if missing:
        raise FlowValidationError(f"模板缺少输入：{', '.join(sorted(missing))}")
    values = {
        name: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value
        for name, value in inputs.items()
    }
    return re.sub(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})",
                  lambda match: str(values[match.group(1)]), template)


async def execute_flow(
    flow: Flow | dict[str, Any], inputs: dict[str, Any], *,
    context: ContextCallback | None = None, llm: LLMCallback | None = None,
    agent: AgentCallback | None = None,
    cached_nodes: list[CachedNode | dict[str, Any]] | tuple[()] = (),
    resumed_nodes: list[CachedNode] | tuple[()] = (),
    execution_context: Mapping[str, Any] | None = None,
    trace: bool = False, preview_node: PreviewCallback | None = None,
    candidate_check: CandidateCheckCallback | None = None,
    review_evidence: ReviewEvidenceCallback | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """在当前异步请求内执行完整图并产出 SSE 可直接使用的事件。

    Args:
        flow: 已保存或即将预览的完整方案。
        inputs: 仅包含开始节点声明的作者输入。
        context: 读取当前任务资料的异步回调，核心执行器不读数据库。
        llm: 已锁定 Provider 配置的模型回调，最后产出 outputs。
        agent: 读取当前小说的工具对话回调，结果不使用节点缓存。
        cached_nodes: 浏览器草稿缓存，按实例路径和实际依赖输入重新检查。
        resumed_nodes: 服务端续跑记录中已完成的节点；输入变化时拒绝续跑，不重新付费运行。
        execution_context: 纳入指纹的当前资料版本和有效模型参数快照。
        trace: 预览时记录实际输入、经过的连线及选中的控制端口。
        preview_node: 仅供编辑器替换开始、资料和 AI 节点，不影响其他节点算法。
        candidate_check: 按节点声明复查实际候选；不通过时审核意见为空，末端仍复查来源并报告错误。
        review_evidence: 对新审核契约的实际输入逐字核对，缓存和续跑同样重新计算。

    Returns:
        异步事件生成器。

    Yields:
        event/data 对象；正常结束唯一 done，失败唯一 error，取消直接向外传递。
    """
    completed: dict[str, dict[str, Any]] = {}
    current: dict[str, str] = {"node_id": "", "instance_path": ""}
    flow_id = ""
    terminal_emitted = False
    executions = 0
    cache = {
        item.instance_path: item
        for raw in cached_nodes
        for item in [raw if isinstance(raw, CachedNode) else CachedNode.model_validate(raw)]
    }
    resume_cache = {item.instance_path: item for item in resumed_nodes}

    async def run_graph(graph: Flow, start: dict[str, Any], prefix: str, graph_path: list[str],
                        parent_path: str | None = None, iteration: int | None = None) -> AsyncGenerator[dict[str, Any], None]:
        nonlocal executions
        nodes = {node.id: node for node in graph.nodes}
        input_node = next(node for node in graph.nodes if node.type == "input")
        start = validate_values(input_node.outputs, {**input_node.values, **start},
                                input_node.label or input_node.id, root=port_schema(input_node, output=True))
        output_node = next(node for node in graph.nodes if node.type == "output")
        data_edges = {node.id: [edge for edge in graph.edges if edge.target == node.id] for node in graph.nodes}
        controls = {node.id: [edge for edge in graph.control_edges if edge.target == node.id] for node in graph.nodes}
        dependencies = {
            node.id: {edge.source for edge in [*data_edges[node.id], *controls[node.id]]}
            for node in graph.nodes
        }
        needed = {output_node.id}
        frontier = [output_node.id]
        while frontier:
            for dependency in dependencies[frontier.pop()]:
                if dependency not in needed:
                    needed.add(dependency)
                    frontier.append(dependency)
        states: dict[str, str] = {}
        results: dict[str, dict[str, Any]] = {}
        active_ports: dict[str, set[str]] = {}
        pending = [node.id for node in graph.nodes if node.id in needed]
        while pending:
            node_id = next((name for name in pending if dependencies[name] <= states.keys()), None)
            if node_id is None:
                raise FlowValidationError("流程无法继续，请检查节点依赖")
            pending.remove(node_id)
            node = nodes[node_id]
            path = f"{prefix}/{node.id}"
            current.update(node_id=node.id, instance_path=path)
            with bind_log_context(flow_id=flow.id, node_id=node.id, instance_path=path):
                node_started = time.perf_counter()
                metadata = {"node_id": node.id, "instance_path": path, "label": node.label or node.id}
                if trace:
                    metadata.update(graph_path=graph_path, parent_instance_path=parent_path, iteration=iteration,
                                    inputs={}, used_edges=[], active_control_ports=[])
                skipped_data = any(states[edge.source] == "skipped" for edge in data_edges[node_id])
                selected_control = not controls[node_id] or any(
                    edge.source_port in active_ports.get(edge.source, set()) for edge in controls[node_id]
                )
                if not selected_control or (skipped_data and node.type != "merge"):
                    states[node_id] = "skipped"
                    active_ports[node_id] = set()
                    logger.info("[节点跳过] label=%s", metadata["label"])
                    yield {"event": "step", "data": {**metadata, "state": "skipped", "elapsed_ms": 0}}
                    continue
                executions += 1
                if executions > flow.max_node_executions:
                    raise FlowValidationError(f"本次运行超过 {flow.max_node_executions} 个节点实例，请缩小批次")
                node_inputs = {name: deepcopy(value) for name, value in node.values.items() if name in node.inputs}
                used_edges = []
                for edge in data_edges[node_id]:
                    if states[edge.source] == "skipped":
                        continue
                    if edge.source_port not in results[edge.source]:
                        continue
                    value = results[edge.source][edge.source_port]
                    try:
                        for part in edge.source_path:
                            value = value[int(part)] if isinstance(value, list) else value[part]
                    except (KeyError, IndexError, TypeError, ValueError) as exc:
                        raise FlowValidationError(f"{node.label or node.id} 无法读取连线 {edge.id} 的字段路径") from exc
                    node_inputs[edge.target_port] = deepcopy(value)
                    if trace:
                        used_edges.append({"id": edge.id, "source_instance_path": f"{prefix}/{edge.source}",
                                           "source_port": edge.source_port, "source_path": list(edge.source_path),
                                           "target_port": edge.target_port})
                node_inputs = validate_values(node.inputs, node_inputs, node.label or node.id,
                                              allow_missing=node.type == "merge", root=port_schema(node, output=False))
                if trace:
                    metadata.update(inputs=deepcopy(node_inputs), used_edges=used_edges)
                review_allowed = True
                if node.config.get("candidate_check") and preview_node is None:
                    if candidate_check is None:
                        raise FlowValidationError("当前任务没有提供候选检查能力")
                    # 缓存和服务端续跑也必须用本次实际输入检查，不能只在模型回调中检查。
                    review_allowed = await candidate_check(node, node_inputs)
                signature: dict[str, Any] = {
                    "flow_ref": {"id": flow.id, "revision": flow.revision},
                    "definition_hash": definition_hash,
                    "node": node.model_dump(mode="json", exclude={"label"}),
                    "inputs": start if node.type == "input" else node_inputs,
                    # 资料回调会补入本次实际读取的版本，后继缓存必须看到这些版本。
                    "execution_context": deepcopy(dict(execution_context or {})),
                    "default_provider": graph.default_provider,
                }
                if node.type in {"subflow", "foreach"}:
                    signature["subflow"] = flow_fingerprint(graph.subflows[node.config["subflow_id"]])
                fingerprint = canonical_hash(signature)
                metadata["input_fingerprint"] = fingerprint
                trusted = resume_cache.get(path)
                old = trusted or cache.get(path)
                cacheable = node.type not in {"input", "context", "agent", "condition", "subflow", "foreach", "output"}
                if trusted is not None and cacheable and (trusted.node_id != node.id or trusted.input_fingerprint != fingerprint):
                    raise DomainApiError("AGENT_CONTINUATION_CHANGED", f"已完成节点 {node.label or node.id} 的输入已变化，请重新整理", status_code=409)
                if review_allowed and cacheable and old is not None and old.node_id == node.id and old.input_fingerprint == fingerprint:
                    outputs = validate_values(node.outputs, old.outputs, node.label or node.id,
                                              root=port_schema(node, output=True))
                    if node.config.get("review_evidence") and preview_node is None:
                        if review_evidence is None:
                            raise FlowValidationError("当前任务没有提供审核原句核对能力")
                        outputs = review_evidence(node, node_inputs, outputs)
                    results[node_id] = outputs
                    states[node_id] = "done"
                    active_ports[node_id] = {"next"}
                    completed[path] = outputs
                    logger.info("[节点命中缓存] label=%s", metadata["label"])
                    yield {"event": "step", "data": {**metadata, "state": "done", "cached": True, "outputs": outputs, "elapsed_ms": 0}}
                    continue
                logger.info("[节点开始] label=%s type=%s", metadata["label"], node.type)
                yield {"event": "step", "data": {**metadata, "state": "running", "elapsed_ms": 0}}
                outputs: dict[str, Any]
                ports = {"next"}
                if not review_allowed:
                    outputs = {"review": None}
                    metadata["review_skipped"] = True
                elif preview_node is not None and node.type in {"input", "context", "llm", "agent"}:
                    outputs = await preview_node(node, deepcopy(start if node.type == "input" else node_inputs), path)
                elif node.type == "input":
                    defaults = {key: deepcopy(value) for key, value in node.values.items() if key in node.outputs}
                    outputs = {**defaults, **start}
                elif node.type == "constant":
                    outputs = {key: deepcopy(value) for key, value in node.values.items() if key in node.outputs}
                elif node.type == "context":
                    if context is None:
                        raise FlowValidationError("当前任务没有提供资料读取能力")
                    outputs = await context(node, node_inputs)
                elif node.type == "template":
                    output_port = node.config.get("output_port", next(iter(node.outputs), "text"))
                    outputs = {output_port: render_template(node.config.get("template", ""), node_inputs)}
                elif node.type == "compose":
                    fields = node.config.get("fields")
                    outputs = {name: node_inputs[source] for name, source in fields.items() if source in node_inputs} if fields is not None else dict(node_inputs)
                    if node.config.get("output_port"):
                        outputs = {node.config["output_port"]: outputs}
                elif node.type in {"llm", "agent"}:
                    callback = agent if node.type == "agent" else llm
                    if callback is None:
                        raise FlowValidationError("当前任务没有提供资料整理能力" if node.type == "agent" else "当前任务没有提供模型调用能力")
                    outputs = None  # type: ignore[assignment]
                    async with aclosing(callback(node, node_inputs, path)) as events:
                        async for event in events:
                            data = event.get("data", event)
                            status = data.get("status", data.get("state", event.get("event")))
                            if status == "done" or "outputs" in data:
                                outputs = data["outputs"]
                                metadata.update({key: data[key] for key in ("usage", "model_calls", "usage_complete") if key in data})
                            else:
                                yield {"event": "progress", "data": {**data, **metadata, "state": "running"}}
                    if outputs is None:
                        raise FlowValidationError(f"{node.label or node.id} 没有返回完成结果")
                elif node.type == "condition":
                    selected_port = node.config.get("else_port", "else")
                    matched = False
                    for case in node.config["cases"]:
                        left = node_inputs.get(case["input"])
                        right = node_inputs.get(case["compare_input"]) if case.get("compare_input") else case.get("value")
                        operator = case.get("operator", "truthy")
                        try:
                            match = (
                                bool(left) if operator == "truthy" else left is not None if operator == "exists"
                                else left == right if operator == "eq" else left != right if operator == "ne"
                                else left > right if operator == "gt" else left >= right if operator == "gte"
                                else left < right if operator == "lt" else left <= right if operator == "lte"
                                else right in left
                            )
                        except TypeError as exc:
                            raise FlowValidationError(f"{node.label or node.id} 的条件两侧无法比较") from exc
                        if match:
                            selected_port, matched = case["port"], True
                            break
                    values = {**node_inputs, "selected_port": selected_port, "matched": matched}
                    outputs = {name: values[name] for name in node.outputs if name in values}
                    ports = {selected_port}
                elif node.type == "merge":
                    mode = node.config.get("mode", "selected")
                    ordered = {name: node_inputs[name] for name in node.inputs if name in node_inputs}
                    if mode == "selected":
                        if not ordered:
                            raise FlowValidationError(f"{node.label or node.id} 没有活动分支可以汇合")
                        if len(ordered) != 1:
                            raise FlowValidationError(f"{node.label or node.id} 只能选择一个活动分支，请检查条件或改用全部汇合")
                        value = next(iter(ordered.values()))
                    elif mode == "array":
                        value = list(ordered.values())
                    else:
                        value = ordered
                    output_port = node.config.get("output_port", next(iter(node.outputs), "value"))
                    outputs = {output_port: value}
                elif node.type in {"subflow", "foreach"}:
                    child = graph.subflows[node.config["subflow_id"]]
                    collection: list[dict[str, Any]] = []
                    child_result: dict[str, Any] | None = None
                    items_name = node.config.get("items_input", "items")
                    items = node_inputs[items_name] if node.type == "foreach" else [None]
                    if node.type == "foreach" and len(items) > node.config.get("max_items", FOREACH_DEFAULT_MAX_ITEMS):
                        raise FlowValidationError(f"{node.label or node.id} 本批共有 {len(items)} 项，超过 {node.config.get('max_items', FOREACH_DEFAULT_MAX_ITEMS)} 项上限")
                    for index, item in enumerate(items):
                        await asyncio.sleep(0)
                        child_start = dict(node_inputs)
                        child_prefix = path
                        if node.type == "foreach":
                            child_start.pop(items_name)
                            child_start[node.config.get("item_input", "item")] = item
                            child_start[node.config.get("index_input", "index")] = index
                            child_prefix = f"{path}[{index}]"
                        async with aclosing(run_graph(child, child_start, child_prefix,
                                                      [*graph_path, node.config["subflow_id"]], path,
                                                      index if node.type == "foreach" else None)) as events:
                            async for event in events:
                                if event["event"] == "_result":
                                    child_result = event["data"]
                                else:
                                    yield event
                        if child_result is None:
                            raise FlowValidationError(f"{node.label or node.id} 的子流程没有输出")
                        collection.append(child_result["outputs"])
                    current.update(node_id=node.id, instance_path=path)
                    if node.type == "foreach":
                        output_port = node.config.get("output_port", next(iter(node.outputs), "items"))
                        outputs = {output_port: collection}
                    else:
                        outputs = collection[0]
                else:
                    output_fields = node.config.get("output_fields")
                    outputs = {name: node_inputs[source] for name, source in output_fields.items() if source in node_inputs} if output_fields is not None else dict(node_inputs)
                if node.type != "output" or node.outputs:
                    try:
                        outputs = validate_values(node.outputs, outputs, node.label or node.id, root=port_schema(node, output=True))
                    except FlowValidationError:
                        # 超长等格式错误仍保留已生成文字，但不发出完成事件或写入节点缓存。
                        if node.type == "llm":
                            completed[path] = outputs
                        raise
                if node.config.get("review_evidence") and preview_node is None:
                    if review_evidence is None:
                        raise FlowValidationError("当前任务没有提供审核原句核对能力")
                    outputs = review_evidence(node, node_inputs, outputs)
                results[node_id] = outputs
                states[node_id] = "done"
                active_ports[node_id] = ports
                completed[path] = outputs
                if trace:
                    metadata["active_control_ports"] = sorted(ports)
                logger.info("[节点完成] label=%s duration=%dms", metadata["label"], int((time.perf_counter() - node_started) * 1000))
                yield {"event": "step", "data": {**metadata, "state": "done", "cached": False, "outputs": outputs,
                                                    "elapsed_ms": int((time.perf_counter() - node_started) * 1000)}}
                if node.type == "output":
                    candidate_fields = node.config.get("candidate_fields")
                    candidate = {name: node_inputs[source] for name, source in candidate_fields.items() if source in node_inputs} if candidate_fields is not None else dict(node_inputs)
                    business_inputs = {name: node_inputs[source] for name, source in node.config.get("parameter_fields", {}).items() if source in node_inputs}
                    yield {"event": "_result", "data": {"outputs": outputs, "candidate": candidate, "business_inputs": business_inputs}}
        if states.get(output_node.id) != "done":
            raise FlowValidationError("当前条件分支没有连接到任务结果")

    try:
        flow = validate_flow(flow)
        flow_id = flow.id
        logger.info("[流程开始] flow_id=%s revision=%s", flow.id, flow.revision)
        definition_hash = flow_fingerprint(flow)
        result = None
        async with aclosing(run_graph(flow, inputs, flow.id, [])) as events:
            async for event in events:
                if event["event"] == "_result":
                    result = event["data"]
                else:
                    yield event
        if result is None:
            raise FlowValidationError("流程没有返回任务结果")
        logger.info("[流程节点执行完成] flow_id=%s", flow.id)
        terminal_emitted = True
        yield {"event": "done", "data": {"result": {
            "candidate": result["candidate"], "business_inputs": result["business_inputs"],
        }}}
    except (asyncio.CancelledError, GeneratorExit):
        if not terminal_emitted:
            with bind_log_context(flow_id=flow_id, **current):
                logger.info("[流程取消]")
        raise
    except Exception as exc:
        if isinstance(exc, DomainApiError) and "agent_progress" in exc.details:
            completed[current["instance_path"]] = {"collected_context": exc.details.pop("agent_progress")}
        if isinstance(exc, FlowValidationError):
            mapped = DomainApiError("TASK_FLOW_EXECUTION_FAILED", str(exc), status_code=422)
            mapped.__cause__ = exc
            exc = mapped
        with bind_log_context(flow_id=flow_id, **current):
            terminal_emitted = True
            yield {"event": "error", "data": {
                **sse_error_payload(exc, fallback_message="节点运行失败"),
                **current, "state": "failed",
                "partial_outputs": completed,
            }}
