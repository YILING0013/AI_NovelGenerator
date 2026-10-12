/** 流程预览只保留在编辑器会话，不写入方案或正式生成缓存。 */
export type FlowPreviewOriginKind =
  | "actual"
  | "user_example"
  | "ai_example"
  | "missing_example"
  | "constant"
  | "computed";

export interface FlowPreviewOrigin {
  path: string[];
  kind: FlowPreviewOriginKind;
  editable: boolean;
  source_instance_path?: string;
  source_port?: string;
  source_path?: string[];
  note?: string;
}

export interface FlowPreviewPort {
  value: unknown;
  origins: FlowPreviewOrigin[];
  json_encoded?: boolean;
}

/** 本次模拟输入组装出的完整 AI 请求，不含密钥或连接配置。 */
export interface FlowPreviewAIRequest {
  messages: { role: string; content: string }[];
  mode: "text" | "json";
  execution_mode: "text" | "stream" | "native_schema" | "tool_call";
  provider: string | null;
  model: string | null;
  api_mode?: string;
  api_parameters?: Record<string, unknown>;
  parameters: Record<string, unknown>;
  response_format: Record<string, unknown> | null;
  output_schema: Record<string, unknown> | null;
  notes: string[];
}

export interface FlowPreviewNode {
  node_id: string;
  graph_path: string[];
  inputs: Record<string, FlowPreviewPort>;
  outputs: Record<string, FlowPreviewPort>;
  ai_request?: FlowPreviewAIRequest;
}

export interface FlowPreviewStep extends FlowPreviewNode {
  instance_path: string;
  state: "done" | "skipped" | "error";
  used_edges: {
    id: string;
    source_instance_path: string;
    source_port: string;
    source_path: string[];
    target_port: string;
  }[];
  active_control_ports: string[];
}

export interface FlowPreviewIssue {
  message: string;
  node_id?: string;
  instance_path?: string;
  port?: string;
  path?: string[];
}

export interface TaskFlowPreviewResult {
  valid: boolean;
  status: "ready" | "error";
  errors: FlowPreviewIssue[];
  definition_hash: string;
  source_refs: { resource_type: string; id: string; version: number }[];
  steps: FlowPreviewStep[];
  nodes: FlowPreviewNode[];
  unused_overrides?: FlowPreviewOverride[];
}

export interface FlowPreviewOverride {
  instance_path: string;
  port: string;
  path: string[];
  value: unknown;
}

export interface FlowPreviewScope {
  novel_id?: string;
  volume_id?: string;
  target_type?: "volume" | "arc" | "scene" | "chapter";
  target_id?: string;
  target_field?: string;
  selected_character_ids?: string[];
  selected_faction_ids?: string[];
}

export interface FlowPreviewFocus {
  instance_path: string;
  port?: string;
  signal: number;
}
