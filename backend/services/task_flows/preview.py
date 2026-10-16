"""编辑器的只读模拟：真实资料、临时示例和逐步查看的数据。"""

from __future__ import annotations

from contextlib import aclosing
from copy import deepcopy
import json
from typing import Any

from pydantic import ValidationError

from backend.api.error_protocol import DomainApiError
from backend.config import get_config_read_model
from backend.llm.base_client import apply_request_defaults, build_request_messages
from backend.llm.config import LLMProviderConfig
from backend.llm.openai_client import build_openai_parameters
from backend.llm.claude_client import build_claude_parameters
from backend.llm.gemini_client import build_gemini_generation_config
from backend.llm.gemini_interactions_client import build_interaction_parameters
from backend.llm.generation_options import REASONING_FIELDS
from .agent import build_agent_request
from .agent_contract import AgentNodeConfigV1
from .book_tools import normalize_agent_scope
from .contracts import Flow, FlowValidationError, Node
from .engine import execute_flow
from .graph import _field_schema, _validate_value, canonical_hash, compile_output_model, flow_fingerprint, port_schema, validate_values
from .llm import build_flow_request
from .preview_examples import example_value, missing_example
from .registry import validate_task_definition


def _source(value: Any, kind: str, instance: str, port: str, *, note: str | None = None,
            json_encoded: bool = False) -> dict[str, Any]:
    origin = {"path": [], "kind": kind, "editable": kind in {"user_example", "ai_example", "missing_example"},
              "source_instance_path": instance, "source_port": port, "source_path": []}
    if note:
        origin["note"] = note
    origins = [origin]
    if kind == "actual":
        pending = [(json.loads(value) if json_encoded else value, [])]
        while pending:
            item, location = pending.pop()
            if location and (item is None or item == []):
                origins.append({**origin, "path": location, "source_path": location})
            elif isinstance(item, dict):
                pending.extend((child, [*location, key]) for key, child in item.items())
            elif isinstance(item, list):
                pending.extend((child, [*location, str(index)]) for index, child in enumerate(item))
    return {"value": deepcopy(value), "origins": origins, "json_encoded": json_encoded}


def _read(value: Any, path: list[str]) -> Any:
    for part in path:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _replace(value: Any, path: list[str], replacement: Any) -> Any:
    if not path:
        return deepcopy(replacement)
    result = deepcopy(value)
    parent = result
    for part in path[:-1]:
        if isinstance(parent, list):
            parent = parent[int(part)]
        else:
            if parent.get(part) is None:
                parent[part] = {}
            parent = parent.setdefault(part, {})
    if isinstance(parent, list):
        position = int(path[-1])
        if position == len(parent):
            parent.append(deepcopy(replacement))
        else:
            parent[position] = deepcopy(replacement)
    else:
        parent[path[-1]] = deepcopy(replacement)
    return result


def _select(source: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """连线取子字段时保留来源地址，且让细字段来源覆盖父级标记。"""
    result = {"value": deepcopy(_read(source["value"], path)), "origins": [],
              "json_encoded": bool(source.get("json_encoded") and not path)}
    ancestors = [item for item in source["origins"] if path[:len(item["path"])] == item["path"]]
    nearest = max((len(item["path"]) for item in ancestors), default=-1)
    for item in source["origins"]:
        location = item["path"]
        if path[:len(location)] == location and len(location) == nearest:
            result["origins"].append({**deepcopy(item), "path": [],
                                      "source_path": [*item["source_path"], *path[len(location):]]})
        elif location[:len(path)] == path and len(location) > len(path):
            result["origins"].append({**deepcopy(item), "path": location[len(path):]})
    return result


def _combine(value: Any, parts: list[tuple[list[str], dict[str, Any]]], instance: str, port: str) -> dict[str, Any]:
    result = _source(value, "computed", instance, port)
    origins = [{**deepcopy(origin), "path": [*prefix, *origin["path"]]}
               for prefix, part in parts for origin in part["origins"]]
    if origins:
        result["origins"] = origins
    return result


def _example_shape(value: Any) -> dict[str, Any]:
    """保留 JSON 示例已有的对象和数组形状，避免把整份资料改成一句话。"""
    if isinstance(value, dict):
        return {"type": "object", "properties": {key: _example_shape(item) for key, item in value.items()}, "required": list(value)}
    if isinstance(value, list):
        shapes = {_key: shape for item in value for shape in [_example_shape(item)] for _key in [canonical_hash(shape)]}
        return {"type": "array", "items": {"anyOf": list(shapes.values())} if shapes else {}}
    if value is None:
        return {}
    return {"type": "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "number" if isinstance(value, float) else "string"}


def _apply_overrides(ports: dict[str, Any], instance: str, overrides: list[dict[str, Any]],
                     used: set[int]) -> None:
    for index, override in enumerate(overrides):
        if override["instance_path"] != instance:
            continue
        name, path = override["port"], override.get("path", [])
        if name not in ports:
            raise DomainApiError("TASK_FLOW_PREVIEW_VALUE_INVALID", "临时示例的端口不存在", details={"port": name, "path": path})
        field = ports[name]
        content = json.loads(field["value"]) if field.get("json_encoded") else field["value"]
        try:
            current = _read(content, path)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DomainApiError("TASK_FLOW_PREVIEW_VALUE_INVALID", "临时示例的字段路径不存在", details={"port": name, "path": path}) from exc
        ancestors = [item for item in field["origins"] if path[:len(item["path"])] == item["path"]]
        origin = max(ancestors, key=lambda item: len(item["path"]))
        protected_children = any((not item["editable"] or item["source_instance_path"] != instance or item["source_port"] != name)
                                 and item["path"][:len(path)] == path and len(item["path"]) > len(path) for item in field["origins"])
        empty_demo = current is None or current == []
        if origin["editable"] and (origin["source_instance_path"] != instance or origin["source_port"] != name):
            raise DomainApiError("TASK_FLOW_PREVIEW_READ_ONLY", "请在此字段的源节点修改示例", details={"port": name, "path": path})
        if (not origin["editable"] or protected_children) and not empty_demo:
            raise DomainApiError("TASK_FLOW_PREVIEW_READ_ONLY", "此字段包含只读内容，请修改可编辑的示例字段", details={"port": name, "path": path})
        if field.get("json_encoded"):
            shape = _example_shape(current)
            try:
                _validate_value(shape, override["value"], shape, name)
            except FlowValidationError as exc:
                raise DomainApiError("TASK_FLOW_PREVIEW_VALUE_INVALID", str(exc), details={"port": name, "path": path}) from exc
        content = _replace(content, path, override["value"])
        field["value"] = json.dumps(content, ensure_ascii=False, sort_keys=True) if field.get("json_encoded") else content
        field["origins"] = [item for item in field["origins"] if not (item["path"][:len(path)] == path)]
        field["origins"].append({"path": path, "kind": origin["kind"] if origin["editable"] else "missing_example",
                                 "editable": True, "source_instance_path": instance, "source_port": name,
                                 "source_path": path, "note": "本次临时示例" if origin["editable"] else "用假设值演示原本为空的资料"})
        used.add(index)


async def preview_task_flow(definition: dict[str, Any], scope: dict[str, Any],
                            overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """用已有小说资料和明确标记的示例模拟草稿，不访问模型或保存数据。

    Args:
        definition: 当前编辑中的完整图，可尚未保存。
        scope: 小说及卷、篇章、场景、章节等明确的资料范围。
        overrides: 按节点实例、端口和 JSON 路径指定的本次示例。
    Returns:
        静态检查结果、端口资料、可播放步骤及准确的错误位置。
    """
    response: dict[str, Any] = {"valid": False, "status": "error", "errors": [], "definition_hash": "",
                                "source_refs": [], "steps": [], "nodes": []}
    try:
        flow = validate_task_definition(definition)
    except (FlowValidationError, ValidationError, ValueError) as exc:
        response["errors"] = [{"message": value} for value in (exc.errors if isinstance(exc, FlowValidationError) else [str(exc)])]
        return response
    response.update(valid=True, status="ready", definition_hash=flow_fingerprint(flow))
    scope = dict(scope)
    chapter_version = next((node.config.get("chapter_context_version") for node in flow.nodes if node.type == "agent" and node.config.get("chapter_context_version")), None)
    scope.pop("chapter_context_version", None)
    if chapter_version:
        scope["chapter_context_version"] = chapter_version
    graphs: dict[tuple[str, ...], Flow] = {}
    node_views: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}
    records: dict[str, dict[str, Any]] = {}
    used_overrides: set[int] = set()
    refs: dict[tuple[str, str], dict[str, Any]] = {}
    context_reads: dict[str, dict[str, Any]] = {}
    llm_settings: dict[str, Any] | None = None
    root_input = next(node for node in flow.nodes if node.type == "input")

    pending = [(flow, [], flow.id)]
    while pending:
        graph, graph_path, prefix = pending.pop()
        graphs[tuple(graph_path)] = graph
        for node in graph.nodes:
            view = {"node_id": node.id, "graph_path": graph_path, "inputs": {}, "outputs": {}}
            # 未经过的分支也可查看格式，但绝不把这些例子冒充执行结果。
            for direction in ("inputs", "outputs"):
                root = port_schema(node, output=direction == "outputs")
                for name, schema in getattr(node, direction).items():
                    try:
                        value = node.values[name] if name in node.values else example_value(schema, root, name=name)
                        note = "本次未经过该节点，先显示字段格式示例"
                    except FlowValidationError as exc:
                        value, note = None, str(exc)
                    kind = "computed"
                    if direction == "outputs":
                        kind = "ai_example" if node.type == "llm" else "user_example" if node.type == "input" and not graph_path else "missing_example" if node.type == "context" else "constant" if node.type == "constant" else "computed"
                    view[direction][name] = _source(value, kind, f"{prefix}/{node.id}", name, note=note)
            node_views[(tuple(graph_path), node.id)] = view
        for child_id, child in graph.subflows.items():
            caller = next((node for node in graph.nodes if node.config.get("subflow_id") == child_id), None)
            child_prefix = f"{prefix}/{caller.id}" if caller else f"{prefix}/{child_id}"
            if caller and caller.type == "foreach":
                child_prefix += "[0]"
            pending.append((child, [*graph_path, child_id], child_prefix))

    def publish(record: dict[str, Any], state: str) -> None:
        step = {key: deepcopy(record[key]) for key in ("node_id", "graph_path", "instance_path", "inputs", "outputs", "used_edges", "active_control_ports")}
        if "ai_request" in record:
            step["ai_request"] = deepcopy(record["ai_request"])
        step["state"] = state
        response["steps"].append(step)
        if state != "skipped":
            node_views[(tuple(step["graph_path"]), step["node_id"])] = {key: deepcopy(step[key]) for key in ("node_id", "graph_path", "inputs", "outputs")}
            if "ai_request" in step:
                node_views[(tuple(step["graph_path"]), step["node_id"])]["ai_request"] = deepcopy(step["ai_request"])

    async def source_outputs(node: Node, inputs: dict[str, Any], instance: str) -> dict[str, Any]:
        nonlocal llm_settings
        record = records[instance]
        ports: dict[str, Any] = {}
        content_schemas: list[tuple[str, list[str], dict[str, Any]]] = []
        root = port_schema(node, output=True)
        agent_config = AgentNodeConfigV1.model_validate(node.config) if node.type == "agent" else None
        agent_preview = agent_config is not None and (
            (agent_config.index_structural_context and flow.task in {"plan_arcs_by_ai", "plan_scenes_by_ai", "plan_chapters_by_ai"})
            or (agent_config.index_plot_children and flow.task in {"generate_volume_plot_by_ai", "generate_arc_plot_by_ai"})
            or agent_config.chapter_context_version == 1
        )
        if (node.type == "llm" or agent_preview) and llm_settings is None:
            # 现有读取接口已去掉密钥；这里只保留提示词和决定请求形式的字段。
            public = get_config_read_model().get("llm", {})
            safe_fields = {*REASONING_FIELDS, "api_mode", "structured_output_mode", "type", "default_model", "enabled", "supports_streaming", "supports_json_schema", "supports_json_output",
                           "system_prompt", "temperature", "top_p", "max_tokens", "presence_penalty", "frequency_penalty"}
            llm_settings = {"default_provider": public.get("default_provider"), "providers": {
                name: {**{key: value for key, value in config.items() if key in safe_fields},
                       "api_mode": LLMProviderConfig.model_validate({key: value for key, value in config.items() if key in safe_fields | {"base_url"}}).resolved_api_mode if config.get("type") != "claude" else "auto"}
                for name, config in public.get("providers", {}).items()
            }}
        if node.type == "input":
            parent_path = record.get("parent_instance_path")
            for name, value in inputs.items():
                if parent_path is None:
                    ports[name] = _source(value, "user_example", instance, name, note="作者输入的假设值")
                else:
                    parent = records[parent_path]
                    parent_node = parent["node"]
                    item_name, index_name = parent_node.config.get("item_input", "item"), parent_node.config.get("index_input", "index")
                    if parent_node.type == "foreach" and name == item_name:
                        ports[name] = _select(parent["inputs"][parent_node.config.get("items_input", "items")], [str(record["iteration"])])
                    elif parent_node.type == "foreach" and name == index_name:
                        ports[name] = _source(value, "computed", instance, name, note="本轮从 0 开始的序号")
                    elif name in parent["inputs"]:
                        ports[name] = deepcopy(parent["inputs"][name])
                    else:
                        ports[name] = _source(value, "constant", instance, name)
        elif node.type == "agent":
            if agent_preview:
                cfg = agent_config
                target_type = {"plan_arcs_by_ai": "volume", "plan_scenes_by_ai": "arc", "plan_chapters_by_ai": "scene",
                               "generate_volume_plot_by_ai": "volume", "generate_arc_plot_by_ai": "arc", "write_chapter_by_ai": "chapter"}[flow.task]
                request_scope = {key: value for key, value in {
                    "novel_id": scope.get("novel_id"), "target_type": target_type,
                    "target_id": scope.get("target_id") or scope.get(f"{target_type}_id"),
                }.items() if value is not None}
                if request_scope.get("novel_id") and request_scope.get("target_id"):
                    request_scope = normalize_agent_scope(request_scope, task=flow.task)
                request, full_inputs = build_agent_request(cfg, inputs, task=flow.task, scope=request_scope, parameters={})
                graph = graphs[tuple(record["graph_path"])]
                provider = ((full_inputs.get(cfg.provider_input) if cfg.provider_input else None)
                            or cfg.provider or graph.default_provider or llm_settings["default_provider"])
                saved_config = llm_settings["providers"].get(provider)
                config = LLMProviderConfig.model_validate(saved_config or {})
                request = apply_request_defaults(request, config)
                notes = ["agent_initial_request"]
                if saved_config is None:
                    notes.append("agent_provider_unconfigured")
                elif not config.enabled:
                    notes.append("provider_disabled")
                # 这里只展示共用构造器生成的首轮消息，不假装已运行工具或组装完整 HTTP。
                record["ai_request"] = {
                    "messages": build_request_messages(request), "mode": "json", "execution_mode": "tool_call",
                    "provider": provider or None, "model": request.model or config.default_model or None,
                    "parameters": request.model_dump(exclude_none=True, exclude={"model", "messages", "system_prompt", "stream", "json_output_schema", "metadata"}),
                    "response_format": None, "output_schema": None, "notes": notes,
                }
            for name, schema in node.outputs.items():
                value = example_value(schema, root, name=name)
                if name == "prepared_context":
                    value.update(suggested_count=2, remaining=True, coverage="示例：根据当前剧情拆分未覆盖部分", boundaries="示例：承接当前部分已定起止")
                    if agent_preview and request_scope.get("reading_version") == 1:
                        value["target"] = deepcopy(request_scope)
                    if chapter_version == 1:
                        context = inputs["writing_context"]
                        context = json.loads(context) if isinstance(context, str) else context
                        value["selected_entities"] = context.get("required_entities", {})
                        value["chapter_sources"] = {"parent_excerpts": [], "previous_chapter_ids": [], "relation_ids": []}
                ports[name] = _source(value, "ai_example", instance, name, note="资料整理的假设示例，没有调用模型或工具")
        elif node.type == "llm":
            cfg = node.config
            graph = graphs[tuple(record["graph_path"])]
            provider = ((inputs.get(cfg["provider_input"]) if cfg.get("provider_input") else None)
                        or cfg.get("provider") or graph.default_provider or llm_settings["default_provider"])
            saved_config = llm_settings["providers"].get(provider)
            config = LLMProviderConfig.model_validate(saved_config or {})
            schema_model = compile_output_model(node)
            request, stream, native = build_flow_request(
                node, inputs, schema_model, {}, use_stream=saved_config is not None,
                supports_streaming=config.supports_streaming,
                supports_json_schema=config.supports_json_schema and config.resolved_structured_output_mode != "json_object",
            )
            request = apply_request_defaults(request, config)
            messages = build_request_messages(request)
            response_format = None
            api_parameters = {}
            api_mode = config.resolved_api_mode
            if config.type in {"openai", "deepseek"}:
                actual = build_openai_parameters(request, config, schema=schema_model if native else None)
                messages = actual.get("messages", actual.get("input", messages))
                response_format = actual.get("text", {}).get("format") if api_mode == "responses" else actual.get("response_format")
                api_parameters = {key: value for key, value in actual.items() if key not in {"model", "input", "messages", "response_format"}}
            elif config.type == "claude":
                actual = build_claude_parameters(request, config)
                if native and config.structured_output_mode == "tool_call":
                    response_format = {"tools": [{"name": "structured_output", "description": f"按照 {schema_model.__name__} 结构输出结果",
                                                   "input_schema": schema_model.model_json_schema()}],
                                       "tool_choice": {"type": "tool", "name": "structured_output"}}
                else:
                    response_format = actual.get("output_config", {}).get("format")
                api_parameters = {key: value for key, value in actual.items() if key not in {"model", "messages", "system"}}
            elif api_mode == "interactions":
                actual = build_interaction_parameters(request, request.model or config.default_model,
                                                      schema_model if config.supports_json_schema and request.json_output_schema else None)
                response_format = actual.get("response_format")
                api_parameters = actual["generation_config"]
            else:
                api_parameters = build_gemini_generation_config(request, request.model or config.default_model)
                if request.json_output_schema is not None and config.supports_json_schema:
                    response_format = {"response_mime_type": "application/json", "response_json_schema": request.json_output_schema}
            notes = ["default_streaming"] if saved_config is not None else ["provider_unconfigured"]
            if saved_config is not None and not config.enabled:
                notes.append("provider_disabled")
            record["ai_request"] = {
                "messages": messages, "mode": cfg.get("mode", "json"),
                "execution_mode": "stream" if stream else "native_schema" if native else "text",
                "provider": provider or None, "model": request.model or config.default_model or None,
                "api_mode": api_mode, "api_parameters": api_parameters,
                "parameters": request.model_dump(exclude_none=True, exclude={"model", "messages", "system_prompt", "stream", "json_output_schema", "metadata"}),
                "response_format": response_format, "output_schema": request.json_output_schema, "notes": notes,
            }
            for name, schema in node.outputs.items():
                whole = next((item for item in reversed(overrides) if item["instance_path"] == instance and item["port"] == name and not item.get("path")), None)
                try:
                    value = whole["value"] if whole else example_value(schema, root, name=name)
                except FlowValidationError as exc:
                    ports[name] = _source(None, "ai_example", instance, name, note=str(exc))
                    record["outputs"] = ports
                    raise DomainApiError("TASK_FLOW_PREVIEW_EXAMPLE_REQUIRED", str(exc), details={"port": name, "path": []}) from exc
                ports[name] = _source(value, "ai_example", instance, name, note="AI 输出的假设示例，没有调用模型")
        else:
            from .preview_context import load_preview_context
            key = canonical_hash(inputs)
            if key not in context_reads:
                context_reads[key] = await load_preview_context(flow.task, inputs, scope)
            loaded = deepcopy(context_reads[key])
            for ref in loaded["source_refs"]:
                data = ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref
                refs[(data["resource_type"], data["id"])] = data
            missing = loaded.get("missing", [])
            for name, schema in node.outputs.items():
                encoded = name in loaded.get("json_ports", [])
                if name in loaded["ports"]:
                    value = loaded["ports"][name]
                    ports[name] = _source(value, "actual", instance, name, json_encoded=encoded)
                else:
                    value = missing_example(name) if encoded else example_value(schema, root, name=name)
                    ports[name] = _source(json.dumps(value, ensure_ascii=False, sort_keys=True) if encoded else value,
                                          "missing_example", instance, name, json_encoded=encoded, note="当前范围没有这项资料")
                for item in missing:
                    if item["port"] != name:
                        continue
                    location = item.get("path", [])
                    content = json.loads(ports[name]["value"]) if encoded else ports[name]["value"]
                    sample_name = location[-1] if location else name
                    sample = item.get("example", missing_example(sample_name))
                    if item.get("schema"):
                        sample = example_value(item["schema"], name=sample_name)
                        content_schemas.append((name, location, item["schema"]))
                    if not location and not encoded and "example" not in item and "schema" not in item:
                        sample = example_value(schema, root, name=name)
                    content = _replace(content, location, sample)
                    ports[name]["value"] = json.dumps(content, ensure_ascii=False, sort_keys=True) if encoded else content
                    ports[name]["origins"] = [origin for origin in ports[name]["origins"] if not (origin["path"][:len(location)] == location)]
                    ports[name]["origins"].append({"path": location, "kind": "missing_example", "editable": True,
                                                   "source_instance_path": instance, "source_port": name, "source_path": location,
                                                   "note": item.get("note", "缺少必需资料，本次使用示例")})
                # 整份资料采用示例时，作者参数仍应指回开始节点，不能被根缺项标记覆盖。
                for origin in loaded.get("origins", {}).get(name, []):
                    location = origin.get("path", [])
                    parameter = origin.get("parameter") or (location[-1] if location else name)
                    if origin.get("origin") == "user_input" and parameter in record["inputs"]:
                        inherited = record["inputs"][parameter]
                        ports[name]["origins"] = [item for item in ports[name]["origins"] if not (item["path"][:len(location)] == location)]
                        ports[name]["origins"].extend({**deepcopy(item), "path": [*location, *item["path"]]} for item in inherited["origins"])
                # 整体缺资料的示例中若混有开始输入，单独暴露其他缺项，避免只能编辑整个对象。
                origins = ports[name]["origins"]
                protected = [item["path"] for item in origins if not item["editable"] or item["source_instance_path"] != instance or item["source_port"] != name]
                known_paths = {tuple(item["path"]) for item in origins}
                for origin in list(origins):
                    base = origin["path"]
                    descendants = [path for path in protected if path[:len(base)] == base and len(path) > len(base)]
                    if origin["kind"] != "missing_example" or origin["source_instance_path"] != instance or origin["source_port"] != name or not descendants:
                        continue
                    content = json.loads(ports[name]["value"]) if encoded else ports[name]["value"]
                    pending_fields = [(base, _read(content, base))]
                    while pending_fields:
                        location, value = pending_fields.pop()
                        if any(location[:len(path)] == path for path in descendants):
                            continue
                        if any(path[:len(location)] == location for path in descendants):
                            children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else []
                            pending_fields.extend(([*location, str(key)], item) for key, item in children)
                        elif tuple(location) not in known_paths:
                            origins.append({**deepcopy(origin), "path": location,
                                            "source_path": [*origin["source_path"], *location[len(base):]]})
                            known_paths.add(tuple(location))
        record["outputs"] = ports
        # 继承的用户输入只能在原源节点修改，不能在下游重新覆盖真实传递。
        if node.type != "input" or record.get("parent_instance_path") is None:
            _apply_overrides(ports, instance, overrides, used_overrides)
        for name, location, schema in content_schemas:
            content = json.loads(ports[name]["value"]) if ports[name].get("json_encoded") else ports[name]["value"]
            value = _read(content, location)
            try:
                _validate_value(schema, value, schema, name)
            except FlowValidationError as exc:
                error_path = location
                for override in overrides:
                    path = override.get("path", [])
                    if override["instance_path"] != instance or override["port"] != name or path[:len(location)] != location:
                        continue
                    try:
                        child = _field_schema(schema, path[len(location):], schema)
                        _validate_value(child, _read(content, path), schema, name)
                    except (FlowValidationError, KeyError, IndexError, TypeError, ValueError):
                        error_path = path
                        break
                raise DomainApiError("TASK_FLOW_PREVIEW_VALUE_INVALID", str(exc), details={"port": name, "path": error_path}) from exc
        values = {name: field["value"] for name, field in ports.items()}
        try:
            return validate_values(node.outputs, values, node.label or node.id, root=root)
        except FlowValidationError as exc:
            for name, value in values.items():
                try:
                    validate_values({name: node.outputs[name]}, {name: value}, node.label or node.id, root=root)
                except FlowValidationError:
                    location = []
                    for override in overrides:
                        if override["instance_path"] != instance or override["port"] != name:
                            continue
                        candidate_path = override.get("path", [])
                        try:
                            field_schema = _field_schema(node.outputs[name], candidate_path, root)
                            _validate_value(field_schema, _read(value, candidate_path), root, name)
                        except (FlowValidationError, KeyError, IndexError, TypeError, ValueError):
                            location = candidate_path
                            break
                    raise DomainApiError("TASK_FLOW_PREVIEW_VALUE_INVALID", str(exc), details={"port": name, "path": location}) from exc
            raise

    initial = {}
    initial_path = f"{flow.id}/{root_input.id}"
    root = port_schema(root_input, output=True)
    selected_fields = {"character_ids": "selected_character_ids", "faction_ids": "selected_faction_ids",
                       "selected_existing_location_ids": "selected_location_ids"}
    if flow.task in {"create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai"}:
        selected_fields["selected_existing_ids"] = "selected_character_ids" if flow.task == "create_characters_for_volume_by_ai" else "selected_faction_ids"
    for name, schema in root_input.outputs.items():
        try:
            whole = next((item for item in reversed(overrides) if item["instance_path"] == initial_path and item["port"] == name and not item.get("path")), None)
            selection = selected_fields.get(name)
            if whole:
                initial[name] = deepcopy(whole["value"])
            elif selection in scope:
                initial[name] = list(scope[selection])
                for index in range(len(initial[name]), schema.get("minItems", 0)):
                    sample = example_value(schema["items"], root, name=name, index=index)
                    attempts = 0
                    while sample in initial[name] and attempts <= len(initial[name]):
                        index += 1
                        attempts += 1
                        sample = example_value(schema["items"], root, name=name, index=index)
                    if sample in initial[name]:
                        raise FlowValidationError(f"{name} 无法自动补齐不同的示例，请临时填写")
                    initial[name].append(sample)
            else:
                initial[name] = deepcopy(root_input.values[name] if name in root_input.values else example_value(schema, root, name=name))
            node_views[((), root_input.id)]["outputs"][name] = _source(initial[name], "user_example", initial_path, name)
            # 逐项校验，避免把前面字段的问题误指向循环中的最后一个字段。
            validate_values({name: schema}, {name: initial[name]}, root_input.label or root_input.id, root=root)
        except FlowValidationError as exc:
            response["status"] = "error"
            response["errors"].append({"message": str(exc), "node_id": root_input.id, "instance_path": initial_path, "port": name, "path": []})
            response["nodes"] = list(node_views.values())
            return response

    async with aclosing(execute_flow(flow, initial, trace=True, preview_node=source_outputs)) as events:
        async for event in events:
            data = event["data"]
            if event["event"] == "error":
                response["status"] = "error"
                response["errors"].append({"message": data.get("message", "模拟失败"), "node_id": data.get("node_id"),
                                            "instance_path": data.get("instance_path"), **{key: value for key, value in data.get("details", {}).items() if key in {"port", "path"}}})
                failed = records.get(data.get("instance_path"))
                if failed:
                    publish(failed, "error")
                continue
            if event["event"] != "step":
                continue
            instance = data["instance_path"]
            graph_path = data["graph_path"]
            graph = graphs[tuple(graph_path)]
            node = next(item for item in graph.nodes if item.id == data["node_id"])
            if data["state"] in {"running", "skipped"}:
                record = {**data, "node": node, "inputs": {}, "outputs": {}}
                for name, value in data["inputs"].items():
                    link = next((edge for edge in data["used_edges"] if edge["target_port"] == name), None)
                    record["inputs"][name] = _select(records[link["source_instance_path"]]["outputs"][link["source_port"]], link["source_path"]) if link else _source(value, "constant", instance, name)
                records[instance] = record
                if data["state"] == "skipped":
                    publish(record, "skipped")
                continue
            record = records[instance]
            record["active_control_ports"] = data["active_control_ports"]
            if node.type not in {"input", "context", "llm", "agent"}:
                fields = record["inputs"]
                for name, value in data["outputs"].items():
                    parts: list[tuple[list[str], dict[str, Any]]] = []
                    if node.type in {"compose", "output"}:
                        mapping = node.config.get("fields" if node.type == "compose" else "output_fields")
                        mapping = mapping if mapping is not None else {key: key for key in fields}
                        wrapper = node.config.get("output_port") if node.type == "compose" else None
                        if wrapper:
                            parts = [([target], fields[source]) for target, source in mapping.items() if source in fields]
                        elif mapping.get(name) in fields:
                            parts = [([], fields[mapping[name]])]
                    elif node.type == "merge":
                        mode = node.config.get("mode", "selected")
                        ordered = [(key, fields[key]) for key in node.inputs if key in fields]
                        parts = [([] if mode == "selected" else [str(index)] if mode == "array" else [key], field)
                                 for index, (key, field) in enumerate(ordered)]
                    elif node.type == "condition" and name in fields:
                        parts = [([], fields[name])]
                    elif node.type in {"subflow", "foreach"}:
                        child = graph.subflows[node.config["subflow_id"]]
                        end = next(item for item in child.nodes if item.type == "output")
                        if node.type == "subflow":
                            child_record = records[f"{instance}/{end.id}"]
                            if name in child_record["outputs"]:
                                parts = [([], child_record["outputs"][name])]
                        else:
                            for index in range(len(value)):
                                child_record = records[f"{instance}[{index}]/{end.id}"]
                                parts.extend(([str(index), port], field) for port, field in child_record["outputs"].items())
                    if parts:
                        output = _combine(value, parts, instance, name)
                        if len(parts) == 1 and parts[0][0] == []:
                            output["json_encoded"] = parts[0][1].get("json_encoded", False)
                    else:
                        output = _source(value, "constant" if node.type == "constant" else "computed", instance, name)
                        if node.type in {"template", "condition"}:
                            output["origins"].extend({**deepcopy(origin), "path": []} for field in fields.values() for origin in field["origins"])
                    record["outputs"][name] = output
            publish(record, "done")
    response["source_refs"] = list(refs.values())
    response["nodes"] = list(node_views.values())
    response["unused_overrides"] = [item for index, item in enumerate(overrides) if index not in used_overrides]
    return response
