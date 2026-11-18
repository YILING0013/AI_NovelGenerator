"""校验端口、连线和子流程，并把输出结构交给现有模型客户端。"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math
import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from backend.llm.models import LLMRequest

from .contracts import FOREACH_DEFAULT_MAX_ITEMS, FOREACH_MAX_ITEMS, Flow, FlowValidationError, JSONSchema, Node


_SCHEMA_KEYS = {
    "$defs", "$ref", "type", "title", "description", "default", "examples",
    "enum", "const", "properties", "required", "additionalProperties", "items",
    "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties", "minLength", "maxLength", "pattern",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "anyOf", "oneOf", "discriminator",
}
_TYPES = {"string", "integer", "number", "boolean", "null", "object", "array"}
_OPERATORS = {"truthy", "eq", "ne", "gt", "gte", "lt", "lte", "contains", "exists"}
_TEMPLATE_EXPRESSION = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)([^{}]*)\}(?!\})")


def canonical_hash(value: Any) -> str:
    """计算 JSON 内容指纹，拒绝不能稳定保存的数值。

    Args:
        value: 由字典、数组和 JSON 基本值组成的内容。

    Returns:
        64 位 SHA-256 指纹。
    """
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def flow_fingerprint(flow: Flow) -> str:
    """计算执行定义指纹，移动节点和改标题不影响续跑。

    Args:
        flow: 已解析的任务方案。

    Returns:
        包含所有子流程执行定义的指纹。
    """
    payload = flow.model_dump(mode="json", exclude={"editor", "name", "revision"})
    for node in payload["nodes"]:
        node.pop("label", None)
    payload["subflows"] = {key: flow_fingerprint(child) for key, child in flow.subflows.items()}
    return canonical_hash(payload)


def port_schema(node: Node, *, output: bool) -> JSONSchema:
    """把节点端口合成完整对象结构，保留内部引用。

    Args:
        node: 待校验的节点。
        output: 为真时读取输出端口，否则读取输入端口。

    Returns:
        可用于结构校验和 Provider 的 JSON Schema。
    """
    ports = deepcopy(node.outputs if output else node.inputs)
    required = [name for name, item in ports.items()
                if (item["required"] if isinstance(item.get("required"), bool) else "default" not in item)]
    definitions = deepcopy(node.config.get("schema_defs", {}))
    for item in ports.values():
        if isinstance(item.get("required"), bool):
            item.pop("required")
        for name, definition in item.pop("$defs", {}).items():
            if name in definitions and definitions[name] != definition:
                raise FlowValidationError(f"{node.label or node.id} 的 $defs.{name} được khai báo trùng lặp nhưng nội dung không nhất quán")
            definitions[name] = definition
    schema: JSONSchema = {
        "type": "object", "properties": ports,
        "required": required,
        "additionalProperties": False,
    }
    if definitions:
        schema["$defs"] = deepcopy(definitions)
    # 旧方案冻结了标准目标的三字段结构；只扩展服务端读取元数据，不改原图或旧报告值。
    from .agent_contract import PreparedTargetV1
    target_schema = PreparedTargetV1.model_json_schema()
    old_names = {"novel_id", "target_type", "target_id"}
    old_properties = {name: target_schema["properties"][name] for name in old_names}
    pending = [schema]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if (item.get("title") == "PreparedTargetV1" and item.get("type") == "object"
                    and item.get("additionalProperties") is False and item.get("properties") == old_properties
                    and set(item.get("required", [])) == old_names):
                item["properties"].update({name: deepcopy(target_schema["properties"][name])
                                           for name in ("reading_version", "reading_intent")})
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return schema


def template_fields(template: str) -> set[str]:
    """读取简单占位符，普通 JSON 花括号保持原样。

    Args:
        template: 作者填写的提示词或文字模板。

    Returns:
        需要输入端口提供值的字段名集合。
    """
    fields = set()
    for match in _TEMPLATE_EXPRESSION.finditer(template):
        name, tail = match.groups()
        if tail and tail[0] in ".[:!":
            raise FlowValidationError("Template chỉ hỗ trợ { tên trường }, không hỗ trợ đường dẫn trường, định dạng hoặc biểu thức")
        if not tail:
            fields.add(name)
    return fields


def _resolve(schema: JSONSchema, root: JSONSchema, stack: tuple[str, ...] = ()) -> JSONSchema:
    if "$ref" not in schema:
        return {key: value for key, value in schema.items() if key != "required"} if isinstance(schema.get("required"), bool) else schema
    reference = schema["$ref"]
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise FlowValidationError("输出结构只支持当前结构内的 $ref 引用")
    if reference in stack:
        raise FlowValidationError("Cấu trúc đầu ra không được tham chiếu đệ quy tới chính nó")
    target: Any = root
    try:
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
    except (KeyError, TypeError) as exc:
        raise FlowValidationError(f"Tham chiếu cấu trúc đầu ra không tồn tại:{reference}") from exc
    if not isinstance(target, dict):
        raise FlowValidationError(f"Tham chiếu cấu trúc đầu ra không phải là đối tượng:{reference}")
    resolved = _resolve(target, root, (*stack, reference))
    return {**resolved, **{key: value for key, value in schema.items()
                          if key != "$ref" and not (key == "required" and isinstance(value, bool))}}


def _check_schema(schema: JSONSchema, root: JSONSchema, label: str, refs: tuple[str, ...] = ()) -> None:
    unknown = set(schema) - _SCHEMA_KEYS
    if unknown:
        raise FlowValidationError(f"{label} chứa các quy tắc cấu trúc không được hỗ trợ:{', '.join(sorted(unknown))}")
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference in refs:
            raise FlowValidationError(f"{label} không được tham chiếu đệ quy tới chính nó")
        refs = (*refs, reference)
    schema = _resolve(schema, root)
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        if not kinds or any(item not in _TYPES for item in kinds):
            raise FlowValidationError(f"{label} có type không được hỗ trợ")
    for combination in ("anyOf", "oneOf"):
        if combination in schema:
            choices = schema[combination]
            if not isinstance(choices, list) or not choices:
                raise FlowValidationError(f"{label}.{combination} phải chứa ít nhất một cấu trúc")
            for choice in choices:
                if not isinstance(choice, dict):
                    raise FlowValidationError(f"{label}.{combination} phải dùng đối tượng cấu trúc")
                _check_schema(choice, root, label, refs)
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise FlowValidationError(f"{label}.enum không được để trống")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or any(not isinstance(item, dict) for item in properties.values()):
        raise FlowValidationError(f"{label}.properties phải chứa cấu trúc trường")
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise FlowValidationError(f"{label}.required phải là mảng tên trường")
    if set(required) - set(properties):
        raise FlowValidationError(f"{label}.required tham chiếu trường không tồn tại")
    for name, item in properties.items():
        _check_schema(item, root, f"{label}.{name}", refs)
    if "items" in schema:
        if not isinstance(schema["items"], dict):
            raise FlowValidationError(f"{label}.items phải là đối tượng cấu trúc")
        _check_schema(schema["items"], root, f"{label}[]", refs)
    additional = schema.get("additionalProperties", True)
    if isinstance(additional, dict):
        _check_schema(additional, root, label, refs)
    elif not isinstance(additional, bool):
        raise FlowValidationError(f"{label}.additionalProperties phải là giá trị boolean hoặc cấu trúc")
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except (TypeError, re.error) as exc:
            raise FlowValidationError(f"{label} có biểu thức chính quy không hợp lệ") from exc
    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], (int, float)) or not math.isfinite(schema[key])):
            raise FlowValidationError(f"{label}.{key} phải là giá trị hữu hạn")
    for key in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"):
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], int) or schema[key] < 0):
            raise FlowValidationError(f"{label}.{key} phải là số nguyên không âm")
    if "multipleOf" in schema and schema["multipleOf"] <= 0:
        raise FlowValidationError(f"{label}.multipleOf phải lớn hơn không")
    if "default" in schema:
        _validate_value(schema, schema["default"], root, f"{label} giá trị mặc định")


def _validate_value(schema: JSONSchema, value: Any, root: JSONSchema, label: str) -> Any:
    schema = _resolve(schema, root)
    for combination in ("anyOf", "oneOf"):
        if combination in schema:
            matches = 0
            for choice in schema[combination]:
                try:
                    _validate_value(choice, value, root, label)
                    matches += 1
                except FlowValidationError:
                    pass
            if not matches or (combination == "oneOf" and matches != 1):
                raise FlowValidationError(f"{label} không đáp ứng {combination} trong các lựa chọn")
    if "const" in schema and canonical_hash(value) != canonical_hash(schema["const"]):
        raise FlowValidationError(f"{label} phải bằng hằng số được chỉ định")
    if "enum" in schema and canonical_hash(value) not in {canonical_hash(item) for item in schema["enum"]}:
        raise FlowValidationError(f"{label} không nằm trong các lựa chọn cho phép")
    actual = (
        "null" if value is None else "boolean" if isinstance(value, bool)
        else "integer" if isinstance(value, int) else "number" if isinstance(value, float)
        else "string" if isinstance(value, str) else "array" if isinstance(value, list)
        else "object" if isinstance(value, dict) else "invalid"
    )
    expected = schema.get("type")
    kinds = set(expected if isinstance(expected, list) else [expected]) if expected else _TYPES
    if actual not in kinds and not (actual == "integer" and "number" in kinds):
        raise FlowValidationError(f"{label} có kiểu giá trị phải là {'/'.join(sorted(kinds))}")
    if actual in {"integer", "number"}:
        if not math.isfinite(value):
            raise FlowValidationError(f"{label} phải là giá trị hữu hạn")
        for key, invalid in (("minimum", lambda bound: value < bound),
                             ("maximum", lambda bound: value > bound),
                             ("exclusiveMinimum", lambda bound: value <= bound),
                             ("exclusiveMaximum", lambda bound: value >= bound)):
            if key in schema and invalid(schema[key]):
                raise FlowValidationError(f"{label} không đáp ứng {key}={schema[key]}")
        if "multipleOf" in schema:
            divisor = schema["multipleOf"]
            if divisor <= 0 or not math.isclose(value / divisor, round(value / divisor), rel_tol=1e-9):
                raise FlowValidationError(f"{label} không thỏa multipleOf")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise FlowValidationError(f"{label} cần ít nhất {schema['minLength']} ký tự, hiện tại là {len(value)} ký tự")
        if len(value) > schema.get("maxLength", math.inf):
            raise FlowValidationError(f"{label} chỉ được tối đa {schema['maxLength']} ký tự, hiện tại là {len(value)} ký tự")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise FlowValidationError(f"{label} có định dạng văn bản không đáp ứng yêu cầu")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            raise FlowValidationError(f"{label} có số mục không đáp ứng yêu cầu")
        if schema.get("uniqueItems") and len({canonical_hash(item) for item in value}) != len(value):
            raise FlowValidationError(f"{label} không được chứa các mục trùng lặp")
        for index, item in enumerate(value):
            _validate_value(schema.get("items", {}), item, root, f"{label}[{index}]")
    if isinstance(value, dict):
        if len(value) < schema.get("minProperties", 0) or len(value) > schema.get("maxProperties", math.inf):
            raise FlowValidationError(f"{label} có số trường không đáp ứng yêu cầu")
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise FlowValidationError(f"{label} thiếu trường {name}")
        for name, item in value.items():
            if not isinstance(name, str):
                raise FlowValidationError(f"{label} có tên trường phải là văn bản")
            if name in properties:
                _validate_value(properties[name], item, root, f"{label}.{name}")
            elif schema.get("additionalProperties") is False:
                raise FlowValidationError(f"{label} chứa trường chưa được khai báo {name}")
            else:
                additional = schema.get("additionalProperties", {})
                _validate_value(additional if isinstance(additional, dict) else {}, item, root, f"{label}.{name}")
    return value


def validate_values(
    port_schemas: dict[str, JSONSchema], values: dict[str, Any], label: str,
    *, allow_missing: bool = False, root: JSONSchema | None = None,
) -> dict[str, Any]:
    """验证端口值并填入声明的默认值。

    Args:
        port_schemas: 输入或输出端口的结构。
        values: 当前实例实际得到的端口值。
        label: 错误消息中的节点名称。
        allow_missing: 汇合节点允许未执行分支没有值。
        root: 包含共享 $defs 的完整对象结构。

    Returns:
        通过校验并补入默认值的独立字典。
    """
    extra = set(values) - set(port_schemas)
    if extra:
        raise FlowValidationError(f"{label} chứa các cổng chưa được khai báo:{', '.join(sorted(extra))}")
    normalized = deepcopy(values)
    schema_root = root
    if schema_root is None:
        definitions: dict[str, Any] = {}
        for schema in port_schemas.values():
            for name, definition in schema.get("$defs", {}).items():
                if name in definitions and definitions[name] != definition:
                    raise FlowValidationError(f"{label} 的 $defs.{name} có định nghĩa không nhất quán")
                definitions[name] = definition
        schema_root = {"type": "object", "properties": port_schemas, "$defs": definitions}
    for name, schema in port_schemas.items():
        if name not in normalized:
            resolved = _resolve(schema, schema_root)
            if "default" in resolved:
                normalized[name] = deepcopy(resolved["default"])
            elif allow_missing or schema.get("required") is False:
                continue
            else:
                raise FlowValidationError(f"{label} thiếu cổng {name} tương ứng")
        effective_schema = schema_root.get("properties", {}).get(name, schema)
        _validate_value(effective_schema, normalized[name], schema_root, f"{label}.{name}")
    return normalized


class _StructuredOutput(BaseModel):
    "Kết nối cấu trúc JSON cho phép chỉnh sửa với giao diện Provider hiện tại vốn yêu cầu Pydantic."

    model_config = ConfigDict(extra="forbid", populate_by_name=False)
    declared_schema: ClassVar[JSONSchema] = {}

    @model_validator(mode="before")
    @classmethod
    def validate_declared_schema(cls, value: Any) -> Any:
        """在 Provider 结果进入流程前检查完整声明结构。"""
        return _validate_value(cls.declared_schema, value, cls.declared_schema, "模型输出")

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> JSONSchema:
        """返回编辑器声明的结构，供现有三个 Provider 使用。"""
        return deepcopy(cls.declared_schema)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """保留作者定义的输出字段名。"""
        kwargs.setdefault("by_alias", True)
        kwargs.setdefault("exclude_unset", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
        """让模型客户端返回 JSON 时也使用作者定义的端口名。"""
        kwargs.setdefault("by_alias", True)
        kwargs.setdefault("exclude_unset", True)
        return super().model_dump_json(*args, **kwargs)


def compile_output_model(node: Node) -> type[BaseModel]:
    """为 JSON 模型节点编译可直接传给 LLMService 的模型。

    Args:
        node: 输出端口已声明的模型节点。

    Returns:
        具有真实 JSON Schema 和严格结果校验的 Pydantic 模型类型。
    """
    schema = port_schema(node, output=True)
    _check_schema(schema, schema, node.label or node.id)
    fields = {
        f"port_{index}": (Any, Field(default=item.get("default", None if item.get("required") is False else ...), alias=name))
        for index, (name, item) in enumerate(node.outputs.items())
    }
    model = create_model(f"FlowOutput_{node.id.replace('-', '_')}", __base__=_StructuredOutput, **fields)
    model.declared_schema = schema
    return model


def _field_schema(schema: JSONSchema, path: list[str], root: JSONSchema) -> JSONSchema:
    schema = _resolve(schema, root)
    for part in path:
        if schema.get("type") == "array" and part.isdigit():
            schema = schema.get("items", {})
        elif part in schema.get("properties", {}):
            schema = schema["properties"][part]
        else:
            raise FlowValidationError(f"Không tồn tại đường dẫn trong cấu trúc đầu ra {'.'.join(path)}")
        schema = _resolve(schema, root)
    return schema


def _types(schema: JSONSchema, root: JSONSchema) -> set[str]:
    schema = _resolve(schema, root)
    if "anyOf" in schema or "oneOf" in schema:
        return set().union(*(_types(item, root) for item in schema.get("anyOf", schema.get("oneOf", []))))
    kind = schema.get("type")
    return set(kind if isinstance(kind, list) else [kind]) if kind else _TYPES


def port_types_compatible(
    source: JSONSchema, target: JSONSchema, *, source_root: JSONSchema, target_root: JSONSchema,
) -> bool:
    """判断输出可能产生的基础类型是否都能进入目标字段。

    Args:
        source: 上游端口或结果映射输入的结构。
        target: 下游端口或业务结果字段的结构。
        source_root: 含上游 $defs 的完整结构。
        target_root: 含下游 $defs 的完整结构。

    Returns:
        所有上游类型都可接受时为真；整数可以进入数值字段。
    """
    source_types = _types(source, source_root)
    target_types = _types(target, target_root)
    if "number" in target_types:
        target_types.add("integer")
    return source_types <= target_types


def validate_flow(flow: Flow | dict[str, Any], *, _depth: int = 0) -> Flow:
    """检查保存和执行所需的端口、依赖和子流程约束。

    Args:
        flow: 方案模型或 JSON 对象。
        _depth: 内部使用的子流程嵌套深度。

    Returns:
        完整通过检查的方案；错误包含可直接显示的节点名称。
    """
    flow = Flow.model_validate(flow) if not isinstance(flow, Flow) else flow
    if _depth > 8:
        raise FlowValidationError("Luồng con được lồng tối đa 8 cấp")
    nodes = {node.id: node for node in flow.nodes}
    if len(nodes) != len(flow.nodes):
        raise FlowValidationError("ID nút không được trùng lặp")
    for kind in ("input", "output"):
        if sum(node.type == kind for node in flow.nodes) != 1:
            raise FlowValidationError(f"Mỗi luồng phải có đúng một {kind} (nút)")
    ids = [edge.id for edge in [*flow.edges, *flow.control_edges]]
    if len(set(ids)) != len(ids):
        raise FlowValidationError("ID đường nối không được trùng lặp")
    incoming: dict[str, set[str]] = {name: set() for name in nodes}
    bound: set[tuple[str, str]] = set()
    for node in flow.nodes:
        label = node.label or node.id
        if "source_conflicts" in node.config:
            if node.config["source_conflicts"] != "plot_source_conflicts_v1":
                raise FlowValidationError(f"{label} không có hợp đồng báo cáo hai nguồn")
            if node.type != "llm" or node.config.get("mode", "json") != "json" or _depth:
                raise FlowValidationError(f"{label} có báo cáo hai nguồn chỉ dùng được cho nút mô hình JSON của luồng chính")
        if "review_evidence" in node.config:
            if node.config["review_evidence"] != "writing_review_v1" or node.config.get("candidate_check") != "writing_planning_v1":
                raise FlowValidationError(f"{label} không có hợp đồng câu gốc rà soát hoặc thiếu kiểm tra ứng viên")
        if "candidate_check" in node.config:
            if node.config["candidate_check"] != "writing_planning_v1":
                raise FlowValidationError(f"{label} không có hợp đồng kiểm tra ứng viên")
            if node.type != "llm" or node.config.get("mode", "json") != "json" or _depth:
                raise FlowValidationError(f"{label} có kiểm tra ứng viên chỉ dùng được cho nút mô hình JSON của luồng chính")
        if node.type in {"input", "constant"} and node.inputs:
            raise FlowValidationError(f"{label} không được khai báo cổng đầu vào")
        for output in (False, True):
            schema = port_schema(node, output=output)
            _check_schema(schema, schema, label)
        if node.type in {"template", "llm", "agent"}:
            templates = [node.config.get("template", "")] if node.type == "template" else [
                node.config.get(name, "") for name in ("prompt", "schema_prompt", "text_prompt", "system_prompt")
            ]
            for template in templates:
                if not isinstance(template, str):
                    raise FlowValidationError(f"{label} có câu lệnh phải là văn bản")
                names = template_fields(template)
                unknown = names - set(node.inputs)
                if unknown:
                    raise FlowValidationError(f"{label} có câu lệnh tham chiếu các đầu vào chưa khai báo:{', '.join(sorted(unknown))}")
        if node.type == "llm" and node.config.get("mode", "json") not in {"json", "text"}:
            raise FlowValidationError(f"{label} có chế độ đầu ra của mô hình không hợp lệ")
        if node.type == "llm" and node.config.get("mode", "json") == "text":
            if len(node.outputs) != 1:
                raise FlowValidationError(f"{label} ở chế độ văn bản phải khai báo đúng một cổng đầu ra duy nhất")
            output_port = node.config.get("output_port", next(iter(node.outputs)))
            if output_port not in node.outputs:
                raise FlowValidationError(f"{label} không có cổng đầu ra dạng văn bản")
            if not port_types_compatible({"type": "string"}, node.outputs[output_port],
                                         source_root={}, target_root=port_schema(node, output=True)):
                raise FlowValidationError(f"{label} ở cổng đầu ra văn bản phải nhận được chữ")
        if node.type == "agent":
            from .agent_contract import AgentNodeConfigV1
            AgentNodeConfigV1.model_validate(node.config)
            if set(node.outputs) != {"prepared_context"}:
                raise FlowValidationError(f"{label} phải và chỉ được xuất prepared_context")
            if not port_types_compatible({"type": "object"}, node.outputs["prepared_context"], source_root={}, target_root=port_schema(node, output=True)):
                raise FlowValidationError(f"{label}.prepared_context phải là một đối tượng")
            if "json_output_schema" in node.config.get("parameters", {}):
                raise FlowValidationError(f"{label} dùng lệnh gọi công cụ gốc, không nhận tham số chế độ đầu ra JSON")
        if node.type in {"llm", "agent"}:
            parameters = node.config.get("parameters", {})
            if not isinstance(parameters, dict) or set(parameters) - (LLMRequest.model_fields.keys() - {"messages", "metadata", "stream", "model"}):
                raise FlowValidationError(f"{label} có tham số mô hình chứa trường không xác định")
            LLMRequest.model_validate({key: value for key, value in parameters.items() if value is not None})
            provider_input = node.config.get("provider_input")
            if provider_input and provider_input not in node.inputs:
                raise FlowValidationError(f"{label} chưa khai báo cổng lựa chọn mô hình")
            timeout = node.config.get("timeout_seconds")
            if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0):
                raise FlowValidationError(f"{label} có số giây thời gian chờ phải là số nguyên dương")
        if node.type == "condition":
            cases = node.config.get("cases", [])
            if not isinstance(cases, list) or not cases:
                raise FlowValidationError(f"{label} cần ít nhất một điều kiện")
            ports: list[str] = []
            for case in cases:
                if not isinstance(case, dict) or not isinstance(case.get("port"), str):
                    raise FlowValidationError(f"{label} cần tên cổng điều khiển cho mỗi điều kiện")
                if case.get("input") not in node.inputs or case.get("operator", "truthy") not in _OPERATORS:
                    raise FlowValidationError(f"{label} có điều kiện đầu vào hoặc phép so sánh không hợp lệ")
                if case.get("compare_input") is not None and case["compare_input"] not in node.inputs:
                    raise FlowValidationError(f"{label} có đầu vào so sánh chưa được khai báo")
                ports.append(case["port"])
            ports.append(node.config.get("else_port", "else"))
            if len(set(ports)) != len(ports):
                raise FlowValidationError(f"{label} có các cổng điều khiển theo điều kiện không được trùng lặp")
        if node.type == "merge" and node.config.get("mode", "selected") not in {"selected", "all", "array"}:
            raise FlowValidationError(f"{label} có chế độ hợp nhất không hợp lệ")
        if node.type in {"subflow", "foreach"}:
            child_id = node.config.get("subflow_id")
            if child_id not in flow.subflows:
                raise FlowValidationError(f"{label} tham chiếu tới luồng con không tồn tại")
            child = validate_flow(flow.subflows[child_id], _depth=_depth + 1)
            child_input = next(item for item in child.nodes if item.type == "input")
            parent_schema = port_schema(node, output=False)
            child_schema = port_schema(child_input, output=True)
            supplied = dict(node.inputs)
            if node.type == "foreach":
                max_items = node.config.get("max_items", FOREACH_DEFAULT_MAX_ITEMS)
                if isinstance(max_items, bool) or not isinstance(max_items, int) or not 1 <= max_items <= FOREACH_MAX_ITEMS:
                    raise FlowValidationError(f"{label} có giới hạn mỗi lô phải từ 1 đến {FOREACH_MAX_ITEMS} (số nguyên)")
                items_input = node.config.get("items_input", "items")
                if items_input not in node.inputs or _types(node.inputs[items_input], parent_schema) != {"array"}:
                    raise FlowValidationError(f"{label} có đầu vào xử lý theo lô phải là mảng")
                item_schemas = []
                choices = [node.inputs[items_input]]
                while choices:
                    choice = _resolve(choices.pop(), parent_schema)
                    if "anyOf" in choice or "oneOf" in choice:
                        choices.extend(choice.get("anyOf", choice.get("oneOf", [])))
                    else:
                        item_schemas.append(choice.get("items", {}))
                supplied.pop(items_input)
                supplied[node.config.get("item_input", "item")] = {"anyOf": item_schemas}
                supplied[node.config.get("index_input", "index")] = {"type": "integer"}
            required = {key for key, schema in child_input.outputs.items()
                        if schema.get("required") is not False and "default" not in schema and key not in child_input.values}
            unknown = supplied.keys() - child_input.outputs.keys()
            if unknown:
                raise FlowValidationError(f"{label} đã truyền vào luồng con các đầu vào chưa được khai báo:{', '.join(sorted(unknown))}")
            if required - supplied.keys():
                raise FlowValidationError(f"{label} chưa cung cấp đầu vào cho luồng con:{', '.join(sorted(required - supplied.keys()))}")
            for name in supplied.keys() & child_input.outputs.keys():
                if not port_types_compatible(supplied[name], child_input.outputs[name],
                                             source_root=parent_schema, target_root=child_schema):
                    raise FlowValidationError(f"{label} có đầu vào luồng con {name} không nhất quán về kiểu")
        if node.type in {"compose", "output"}:
            mappings = ("fields",) if node.type == "compose" else ("candidate_fields", "parameter_fields", "output_fields")
            for key in mappings:
                mapping = node.config.get(key, {})
                if not isinstance(mapping, dict) or any(value not in node.inputs for value in mapping.values()):
                    raise FlowValidationError(f"{label}.{key} phải được ánh xạ tới cổng đầu vào đã khai báo")
    for edge in flow.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise FlowValidationError(f"Đường nối {edge.id} tham chiếu tới nút không tồn tại")
        source, target = nodes[edge.source], nodes[edge.target]
        if edge.source_port not in source.outputs or edge.target_port not in target.inputs:
            raise FlowValidationError(f"Đường nối {edge.id} tham chiếu tới cổng không tồn tại")
        identity = (edge.target, edge.target_port)
        if identity in bound:
            raise FlowValidationError(f"{target.label or target.id}.{edge.target_port} chỉ được nối một đầu ra")
        bound.add(identity)
        source_schema = _field_schema(source.outputs[edge.source_port], edge.source_path, port_schema(source, output=True))
        if not port_types_compatible(source_schema, target.inputs[edge.target_port],
                                     source_root=port_schema(source, output=True), target_root=port_schema(target, output=False)):
            raise FlowValidationError(f"Đường nối {edge.id} có kiểu hai đầu không nhất quán")
        incoming[edge.target].add(edge.source)
    for edge in flow.control_edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise FlowValidationError(f"Đường điều khiển {edge.id} tham chiếu tới nút không tồn tại")
        source = nodes[edge.source]
        allowed = {"next"} if source.type != "condition" else {
            *(case["port"] for case in source.config["cases"]), source.config.get("else_port", "else"),
        }
        if edge.source_port not in allowed or nodes[edge.target].type == "input":
            raise FlowValidationError(f"Đường điều khiển {edge.id} có cổng không hợp lệ")
        incoming[edge.target].add(edge.source)
    for node in flow.nodes:
        for name, schema in node.inputs.items():
            if (node.id, name) not in bound and name not in node.values and "default" not in schema and schema.get("required") is not False:
                raise FlowValidationError(f"{node.label or node.id}.{name} cần đường nối hoặc giá trị mặc định")
        values = {key: value for key, value in node.values.items() if key in node.inputs}
        if values:
            validate_values(node.inputs, values, node.label or node.id, allow_missing=True, root=port_schema(node, output=False))
    pending = {key: set(dependencies) for key, dependencies in incoming.items()}
    while pending:
        ready = {key for key, dependencies in pending.items() if not dependencies}
        if not ready:
            raise FlowValidationError("Luồng tồn tại kết nối vòng lặp; để lặp lại, hãy dùng nút xử lý theo từng mục")
        pending = {key: dependencies - ready for key, dependencies in pending.items() if key not in ready}
    return flow
