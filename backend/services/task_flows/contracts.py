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
    "Từ chối trường tệp không khai báo, giữ nguyên khoảng trắng gốc trong câu lệnh."

    model_config = ConfigDict(extra="forbid")


class Node(FlowModel):
    "Một nút cùng các cổng đầu vào và đầu ra của nó."

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    type: NodeType
    label: str = Field(default="", max_length=200)
    inputs: dict[str, JSONSchema] = Field(default_factory=dict)
    outputs: dict[str, JSONSchema] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(FlowModel):
    "Kết nối một trường đầu ra vào đầu vào của một nút khác."

    id: str = Field(min_length=1, max_length=200)
    source: str
    source_port: str
    target: str
    target_port: str
    source_path: list[str] = Field(default_factory=list)


class ControlEdge(FlowModel):
    "Nhánh true/false của nút chỉ định thứ tự chạy hoặc nút điều kiện."

    id: str = Field(min_length=1, max_length=200)
    source: str
    source_port: str = "next"
    target: str


class Flow(FlowModel):
    "Bản chỉnh sửa đầy đủ của một phương án tác vụ, gồm cả các luồng con mà nó tham chiếu."

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
    "Khóa ID phương án và bản chỉnh sửa, tránh khi chạy tiếp bị đổi sang phương án mặc định khác."

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)


class CachedNode(FlowModel):
    "Kết quả một instance nút do trình duyệt lưu; khi chạy tiếp phải tính lại vân tay đầu vào."

    node_id: str
    instance_path: str = Field(min_length=1, max_length=2000)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    outputs: dict[str, Any]


class RepairFlowSnapshot(FlowModel):
    "Khi sửa vẫn phải đối chiếu luồng gốc, đầu vào nghiệp vụ và tài liệu đã đọc."

    flow_ref: FlowRef
    definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    flow_inputs: dict[str, Any]
    scope: dict[str, Any]
    business_input: dict[str, Any]
    execution: dict[str, Any]


class GraphResultRepair(FlowModel):
    "Giữ nguyên ứng viên đầy đủ khi hợp lệ hóa thất bại, để tác giả chủ động khởi chạy một lượt sửa bằng AI."

    candidate: dict[str, Any]
    business_inputs: dict[str, Any]
    source_refs: list[CandidateSourceRefV1] = Field(max_length=MAX_CANDIDATE_SOURCE_REFS)
    flow_snapshot: RepairFlowSnapshot


class GraphRunRequest(FlowModel):
    "Yêu cầu chạy đồ thị công việc, gồm đầu vào tác giả, tham số mô hình và vị trí thao tác."

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
    "Nội dung trường nguồn chỉ dùng cho lần mô phỏng này, không ghi vào luồng hay tiểu thuyết."

    instance_path: str = Field(min_length=1, max_length=2000)
    port: str = Field(min_length=1, max_length=200)
    path: list[str] = Field(default_factory=list, max_length=64)
    value: Any


class PreviewRequest(FlowModel):
    "Trình soạn thảo gửi bản nháp hiện tại, phạm vi tài liệu và ví dụ tạm thời."

    definition: dict[str, Any]
    scope: dict[str, Any] = Field(default_factory=dict)
    overrides: list[PreviewOverride] = Field(default_factory=list, max_length=1000)


class PreviewOrigin(FlowModel):
    "Nguồn thật hoặc giả định của một trường; địa chỉ luôn trỏ tới cổng nguồn có thể xem."

    path: list[str] = Field(default_factory=list)
    kind: Literal["actual", "user_example", "ai_example", "missing_example", "constant", "computed"]
    editable: bool
    source_instance_path: str
    source_port: str
    source_path: list[str] = Field(default_factory=list)
    note: str | None = None


class PreviewPort(FlowModel):
    "Giữ giá trị cổng theo kiểu chạy gốc; chuỗi JSON có cờ riêng đánh dấu định dạng nội dung."

    value: Any
    origins: list[PreviewOrigin] = Field(default_factory=list)
    json_encoded: bool = False


class PreviewAIRequest(FlowModel):
    "Toàn bộ câu lệnh và ràng buộc định dạng dự kiến gửi trong vòng này; không kèm credential của mô hình."

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
    "Dữ liệu của một nút trong một lớp đồ thị của trình soạn thảo."

    node_id: str
    graph_path: list[str] = Field(default_factory=list)
    inputs: dict[str, PreviewPort] = Field(default_factory=dict)
    outputs: dict[str, PreviewPort] = Field(default_factory=dict)
    ai_request: PreviewAIRequest | None = None


class PreviewStep(PreviewNode):
    "Một instance nút thực sự đã đi qua hoặc bị bỏ qua, để trình duyệt phát lại từng bước."

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
