"""任务流程的文件、接口与节点缓存格式。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.services.llm.candidate_contract import CandidateSourceRefV1, MAX_CANDIDATE_SOURCE_REFS
from .agent_continuation import AgentContinuation


JSONSchema = dict[str, Any]
FOREACH_DEFAULT_MAX_ITEMS = 100
FOREACH_MAX_ITEMS = 1000
NodeType = Literal[
    "input", "context", "constant", "template", "compose", "llm", "agent",
    "condition", "merge", "subflow", "foreach", "output",
]


class FlowModel(BaseModel):
    """拒绝未声明的文件字段，保留提示词中的原始空白。"""

    model_config = ConfigDict(extra="forbid")


class Node(FlowModel):
    """一个节点及其输入输出端口。"""

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    type: NodeType
    label: str = Field(default="", max_length=200)
    inputs: dict[str, JSONSchema] = Field(default_factory=dict)
    outputs: dict[str, JSONSchema] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(FlowModel):
    """把一个输出字段连接到另一个节点的输入。"""

    id: str = Field(min_length=1, max_length=200)
    source: str
    source_port: str
    target: str
    target_port: str
    source_path: list[str] = Field(default_factory=list)


class ControlEdge(FlowModel):
    """指定执行顺序或条件节点的 true/false 分支。"""

    id: str = Field(min_length=1, max_length=200)
    source: str
    source_port: str = "next"
    target: str


class Flow(FlowModel):
    """一个任务方案的完整修订，包含其引用的子流程。"""

    format_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    task: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]+$")
    revision: int = Field(default=1, ge=1)
    name: str = Field(min_length=1, max_length=200)
    default_provider: str = ""
    nodes: list[Node] = Field(min_length=2, max_length=500)
    edges: list[Edge] = Field(default_factory=list, max_length=5000)
    control_edges: list[ControlEdge] = Field(default_factory=list, max_length=5000)
    subflows: dict[str, "Flow"] = Field(default_factory=dict)
    editor: dict[str, Any] = Field(default_factory=dict)
    max_node_executions: int = Field(default=1000, ge=1, le=10000)


class FlowRef(FlowModel):
    """锁定方案 ID 和修订，避免续跑时换成另一份默认方案。"""

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)


class CachedNode(FlowModel):
    """浏览器保存的一个节点实例结果，续跑时必须重算输入指纹。"""

    node_id: str
    instance_path: str = Field(min_length=1, max_length=2000)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    outputs: dict[str, Any]


class RepairFlowSnapshot(FlowModel):
    """修复时仍须核对原流程、业务输入与读取过的资料。"""

    flow_ref: FlowRef
    definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    flow_inputs: dict[str, Any]
    scope: dict[str, Any]
    business_input: dict[str, Any]
    execution: dict[str, Any]


class GraphResultRepair(FlowModel):
    """保留校验失败的完整候选，供作者主动发起一次 AI 修复。"""

    candidate: dict[str, Any]
    business_inputs: dict[str, Any]
    source_refs: list[CandidateSourceRefV1] = Field(max_length=MAX_CANDIDATE_SOURCE_REFS)
    flow_snapshot: RepairFlowSnapshot


class GraphRunRequest(FlowModel):
    """任务图运行请求，包含作者输入、模型参数和操作位置。"""

    request_mode: Literal["task_flow"] = "task_flow"
    flow_ref: FlowRef | None = None
    flow_inputs: dict[str, Any] = Field(default_factory=dict)
    cached_nodes: list[CachedNode] = Field(default_factory=list, max_length=10000)
    scope: dict[str, Any] = Field(default_factory=dict)
    generation_params: dict[str, Any] = Field(default_factory=dict)
    use_stream: bool = True
    repair: GraphResultRepair | None = Field(default=None, exclude_if=lambda value: value is None)
    agent_continuation: AgentContinuation | None = Field(default=None, exclude_if=lambda value: value is None)


class PreviewOverride(FlowModel):
    """仅本次模拟使用的源字段内容，不写入流程或小说。"""

    instance_path: str = Field(min_length=1, max_length=2000)
    port: str = Field(min_length=1, max_length=200)
    path: list[str] = Field(default_factory=list, max_length=64)
    value: Any


class PreviewRequest(FlowModel):
    """编辑器提交当前草稿、资料范围和临时示例。"""

    definition: dict[str, Any]
    scope: dict[str, Any] = Field(default_factory=dict)
    overrides: list[PreviewOverride] = Field(default_factory=list, max_length=1000)


class PreviewOrigin(FlowModel):
    """字段的真实或假设来源；地址始终指向可查看的源端口。"""

    path: list[str] = Field(default_factory=list)
    kind: Literal["actual", "user_example", "ai_example", "missing_example", "constant", "computed"]
    editable: bool
    source_instance_path: str
    source_port: str
    source_path: list[str] = Field(default_factory=list)
    note: str | None = None


class PreviewPort(FlowModel):
    """保持原运行类型的端口值，JSON 字符串另标记内容格式。"""

    value: Any
    origins: list[PreviewOrigin] = Field(default_factory=list)
    json_encoded: bool = False


class PreviewAIRequest(FlowModel):
    """本轮预期发送的完整提示词与格式约束，不含模型凭据。"""

    messages: list[dict[str, str]]
    mode: Literal["text", "json"]
    execution_mode: Literal["text", "stream", "native_schema", "tool_call"]
    provider: str | None = None
    model: str | None = None
    api_mode: str | None = None
    api_parameters: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    response_format: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)


class PreviewNode(FlowModel):
    """编辑器某一层图中的节点资料。"""

    node_id: str
    graph_path: list[str] = Field(default_factory=list)
    inputs: dict[str, PreviewPort] = Field(default_factory=dict)
    outputs: dict[str, PreviewPort] = Field(default_factory=dict)
    ai_request: PreviewAIRequest | None = None


class PreviewStep(PreviewNode):
    """一次真实经过或跳过的节点实例，可供浏览器逐步播放。"""

    instance_path: str
    state: Literal["done", "skipped", "error"]
    used_edges: list[dict[str, Any]] = Field(default_factory=list)
    active_control_ports: list[str] = Field(default_factory=list)


class FlowValidationError(ValueError):
    """可直接显示在编辑器中的流程错误。"""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else errors
        super().__init__("；".join(self.errors))


class FlowConflictError(ValueError):
    """方案或默认选择已被其他页面修改。"""


Flow.model_rebuild()
