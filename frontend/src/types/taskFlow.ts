/** 用户可编辑任务图与原业务入口共用的请求结构。 */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  required?: string[] | boolean;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  [key: string]: unknown;
}
export interface FlowRef {
  id: string;
  revision: number;
}
export const FLOW_NODE_TYPES = [
  "input",
  "context",
  "constant",
  "template",
  "compose",
  "llm",
  "agent",
  "condition",
  "merge",
  "subflow",
  "foreach",
  "output",
] as const;
export type FlowNodeType = (typeof FLOW_NODE_TYPES)[number];

/** 资料整理节点中随方案修订保存的技能。 */
export interface AgentSkill { id: string; name: string; description: string; instructions: string }
export const AGENT_TOOLS = ["get_scope", "list_directory", "search_entities", "search_book", "read_entity", "read_volume_state", "read_previous", "load_skill"] as const;
/** AI 本轮查阅资料后提交的可审阅结果，不包含模型私有续接内容。 */
export interface PreparedContextV1 {
  schema_version: 1;
  target: { novel_id: string; target_type: string; target_id: string };
  boundaries: string;
  selected_entities: Record<"character_ids" | "faction_ids" | "location_ids" | "item_ids" | "rule_ids", string[]>;
  selection_reasons: { resource_type: string; id: string; reason: string }[];
  entity_needs: { resource_type: string; role: string; reason: string }[];
  new_counts: Record<"character" | "faction" | "location" | "item" | "world_rule", number>;
  suggested_count: number;
  coverage: string;
  remaining: boolean;
  missing_required: { field: string; message: string }[];
}
export interface FlowNode {
  id: string;
  type: FlowNodeType;
  label: string;
  inputs: Record<string, JsonSchema>;
  outputs: Record<string, JsonSchema>;
  values: Record<string, unknown>;
  config: Record<string, unknown>;
}
export interface FlowEdge {
  id: string;
  source: string;
  source_port: string;
  target: string;
  target_port: string;
  source_path?: string[];
}
export interface FlowControlEdge {
  id: string;
  source: string;
  source_port: string;
  target: string;
}
export interface TaskFlow {
  format_version: 1;
  id: string;
  task: string;
  revision: number;
  name: string;
  default_provider: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  control_edges: FlowControlEdge[];
  subflows: Record<string, TaskFlow>;
  editor: {
    positions?: Record<string, { x: number; y: number }>;
    [key: string]: unknown;
  };
  max_node_executions: number;
}
export interface FlowSummary extends FlowRef {
  task: string;
  name: string;
}
export interface FlowTask {
  task: string;
  label: string;
  input_schema: JsonSchema;
  output_schema: JsonSchema;
  default_ref: FlowRef;
}
export interface FlowNodeEvent {
  node_id: string;
  instance_path: string;
  state: string;
  outputs?: Record<string, unknown>;
  input_fingerprint?: string;
  [key: string]: unknown;
}
export interface CachedFlowNode {
  node_id: string;
  instance_path: string;
  input_fingerprint: string;
  outputs: Record<string, unknown>;
}
/** 达到整理上限后，服务器暂存对话并返回的继续资格；仅保留在页面内存。 */
export interface AgentContinuation {
  token: string;
  instance_path: string;
  round: number;
  call_count: number;
  expires_at: string;
  last_error?: string | Record<string, unknown> | null;
  reason?: "budget" | "network";
  resume_rounds?: number;
  flow_recovery?: boolean;
  running?: boolean;
  result_ready?: boolean;
}
/** 原入口执行方式；只有显式选择继续时才发送续跑令牌。 */
export type TaskFlowRunMode = boolean | "repair" | { continuation: true; additionalRounds: number };
export interface TaskFlowRequest {
  request_mode: "task_flow";
  flow_ref: FlowRef;
  flow_inputs: Record<string, unknown>;
  cached_nodes: CachedFlowNode[];
  generation_params: Record<string, unknown>;
  use_stream: boolean;
  scope: Record<string, unknown>;
  repair?: Record<string, unknown>;
  agent_continuation?: { token: string; additional_rounds: number };
}

/** 功能：识别候选依据里的图输入。Args: value 待验证值。Returns: 是否为图请求。 */
export function isTaskFlowRequest(value: unknown): value is TaskFlowRequest {
  if (!value || typeof value !== "object") return false;
  const input = value as Partial<TaskFlowRequest>;
  return (
    input.request_mode === "task_flow" &&
    typeof input.flow_ref?.id === "string" &&
    Number.isInteger(input.flow_ref.revision) &&
    input.flow_ref.revision > 0 &&
    !!input.flow_inputs &&
    typeof input.flow_inputs === "object" &&
    !!input.scope &&
    typeof input.scope === "object"
  );
}

/** 功能：读取开始节点中的作者字段默认值。Args: flow 已选中的图。Returns: 只包含图定义字段的开始值。 */
export function taskFlowDefaultInputs(flow: TaskFlow): Record<string, unknown> {
  const initialValue = (raw: JsonSchema): unknown => {
    const schema = resolveTaskFlowSchema(raw);
    if (Object.hasOwn(schema, "default"))
      return structuredClone(schema.default);
    if (
      schema.type === "null" ||
      (Array.isArray(schema.type) && schema.type.includes("null")) ||
      (Array.isArray(schema.anyOf) &&
        schema.anyOf.some((item: JsonSchema) => item.type === "null"))
    )
      return null;
    if (schema.type === "boolean") return false;
    if (schema.type === "array") return [];
    if (schema.type === "object")
      return Object.fromEntries(
        Object.entries(schema.properties ?? {}).map(([name, child]) => [
          name,
          initialValue(child),
        ]),
      );
    return "";
  };
  return Object.fromEntries(
    flow.nodes
      .filter((node) => node.type === "input")
      .flatMap((node) =>
        Object.entries(node.outputs).map(([name, schema]) => [
          name,
          Object.hasOwn(node.values, name)
            ? structuredClone(node.values[name])
            : initialValue(schema),
        ]),
      ),
  );
}

/** 功能：展开当前字段的本地引用和可空结构，子字段保留定义供继续展开。Args: schema 端口字段结构。Returns: 可供表单读取的字段。 */
export function resolveTaskFlowSchema(schema: JsonSchema): JsonSchema {
  const definitions = (schema.$defs ?? {}) as Record<string, JsonSchema>;
  let current = schema;
  if (typeof current.$ref === "string" && current.$ref.startsWith("#/$defs/")) {
    const name = current.$ref.slice(8).replace(/~1/g, "/").replace(/~0/g, "~");
    const referenced = definitions[name];
    current = {
      ...referenced,
      ...current,
      ...(typeof current.required === "boolean" &&
      Array.isArray(referenced?.required)
        ? { required: referenced.required }
        : {}),
    };
    delete current.$ref;
  }
  if (Array.isArray(current.anyOf)) {
    const choices = current.anyOf as JsonSchema[];
    const nonNull = choices.find((choice) => choice.type !== "null");
    if (nonNull) {
      const resolved = resolveTaskFlowSchema({
        ...nonNull,
        $defs: definitions,
      });
      current = {
        ...resolved,
        ...current,
        ...(typeof current.required === "boolean" &&
        Array.isArray(resolved.required)
          ? { required: resolved.required }
          : {}),
        type:
          choices.some((choice) => choice.type === "null") &&
          typeof resolved.type === "string"
            ? [resolved.type, "null"]
            : resolved.type,
      };
      delete current.anyOf;
    }
  }
  return {
    ...current,
    ...(current.properties
      ? {
          properties: Object.fromEntries(
            Object.entries(current.properties).map(([name, child]) => [
              name,
              { ...child, $defs: definitions },
            ]),
          ),
        }
      : {}),
    ...(current.items
      ? { items: { ...current.items, $defs: definitions } }
      : {}),
  };
}
