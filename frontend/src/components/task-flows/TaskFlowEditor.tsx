"use client";

import {
  FLOW_NODE_TYPES,
  AGENT_TOOLS,
  type AgentSkill,
  resolveTaskFlowSchema,
  type FlowNode,
  type FlowNodeType,
  type JsonSchema,
  type TaskFlow,
} from "@/types/taskFlow";
import { Button } from "@heroui/react";
import { type Connection, type XYPosition } from "@xyflow/react";
import { useTranslations } from "next-intl";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type {
  FlowPreviewFocus,
  FlowPreviewOverride,
  TaskFlowPreviewResult,
} from "@/types/taskFlowPreview";
import { ReasoningControls } from "@/components/shared/ReasoningControls";
import type { ReasoningOptions } from "@/types/generation";
import { TooltipHint } from "@/components/shared/TooltipHint";
import { TaskFlowCanvas, controlPorts } from "./TaskFlowCanvas";
import { TaskFlowPortPreview } from "./TaskFlowPortPreview";
import { TaskFlowAIRequestPreview } from "./TaskFlowAIRequestPreview";
import { FLOW_INPUT_CLASS } from "./TaskFlowForm";
import {
  FlowPromptEditor,
  FlowJsonEditor,
  FlowJsonSuffixEditor,
} from "./FlowCodeEditors";

type FlowCondition = {
  port: string;
  input: string;
  operator: string;
  value?: unknown;
  compare_input?: string;
};
const ROOT_GRAPH_PATH: string[] = [];

/** 功能：展开并聚焦仍有错误的 JSON 草稿。Args: 无。Returns: 是否有错误需要先修正。 */
export function focusInvalidFlowJson(): boolean {
  const field = document.querySelector<HTMLElement>(
    "[data-flow-json-editor='true'][aria-invalid='true'], textarea:not([data-flow-preview-field='true'])[aria-invalid='true']",
  );
  if (!field) return false;
  for (let parent = field.parentElement; parent; parent = parent.parentElement)
    if (parent.tagName === "DETAILS") parent.setAttribute("open", "");
  field.focus();
  return true;
}

function isJsonObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isSchemaObject(value: unknown): value is JsonSchema {
  if (!isJsonObject(value)) return false;
  return (
    ["properties", "$defs"].every(
      (key) =>
        value[key] === undefined ||
        (isJsonObject(value[key]) &&
          Object.values(value[key]).every(isSchemaObject)),
    ) &&
    (value.items === undefined || isSchemaObject(value.items)) &&
    ["anyOf", "oneOf"].every(
      (key) =>
        value[key] === undefined ||
        (Array.isArray(value[key]) && value[key].every(isSchemaObject)),
    )
  );
}

/** 功能：在 JSON 进入编辑器前检查可显示的基本结构。Args: value 导入或直接编辑的值。Returns: 是否可以安全显示；业务规则仍由保存校验。 */
export function isTaskFlowDraft(value: unknown): value is TaskFlow {
  if (
    !isJsonObject(value) ||
    value.format_version !== 1 ||
    !["id", "task", "name", "default_provider"].every(
      (key) => typeof value[key] === "string",
    ) ||
    typeof value.revision !== "number" ||
    typeof value.max_node_executions !== "number" ||
    !Array.isArray(value.nodes) ||
    !Array.isArray(value.edges) ||
    !Array.isArray(value.control_edges) ||
    !isJsonObject(value.editor) ||
    !isJsonObject(value.subflows)
  )
    return false;
  const positions = value.editor.positions;
  return (
    (positions === undefined ||
      (isJsonObject(positions) &&
        Object.values(positions).every(
          (position) =>
            isJsonObject(position) &&
            typeof position.x === "number" &&
            typeof position.y === "number",
        ))) &&
    value.nodes.every(
      (node) =>
        isJsonObject(node) &&
        typeof node.id === "string" &&
        typeof node.label === "string" &&
        FLOW_NODE_TYPES.includes(node.type as FlowNodeType) &&
        ["inputs", "outputs"].every(
          (key) =>
            isJsonObject(node[key]) &&
            Object.values(node[key]).every(isSchemaObject),
        ) &&
        isJsonObject(node.values) &&
        isJsonObject(node.config) &&
        (node.config.cases === undefined ||
          (Array.isArray(node.config.cases) &&
            node.config.cases.every(
              (condition) =>
                isJsonObject(condition) &&
                ["port", "input", "operator"].every(
                  (key) => typeof condition[key] === "string",
                ),
            ))),
    ) &&
    value.edges.every(
      (edge) =>
        isJsonObject(edge) &&
        ["id", "source", "source_port", "target", "target_port"].every(
          (key) => typeof edge[key] === "string",
        ) &&
        (edge.source_path === undefined ||
          (Array.isArray(edge.source_path) &&
            edge.source_path.every((part) => typeof part === "string"))),
    ) &&
    value.control_edges.every(
      (edge) =>
        isJsonObject(edge) &&
        ["id", "source", "source_port", "target"].every(
          (key) => typeof edge[key] === "string",
        ),
    ) &&
    Object.values(value.subflows).every(isTaskFlowDraft)
  );
}

/** 功能：编辑并校对 JSON 配置。Args: 与 FlowJsonEditor 相同。Returns: 代码编辑器字段。 */
export const FlowJsonField = FlowJsonEditor;

function NamedField({
  name,
  onRename,
}: {
  name: string;
  onRename: (name: string) => void;
}) {
  const t = useTranslations("taskFlows");
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <label className="grid min-w-0 gap-2 text-xs text-muted">
      {t("portName")}
      <input
        className={FLOW_INPUT_CLASS}
        value={draft ?? name}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = draft?.trim();
          if (next && next !== name) onRename(next);
          setDraft(null);
        }}
      />
    </label>
  );
}

function SchemaEditor({
  schema: rawSchema,
  onChange: onSchemaChange,
  onValidityChange,
}: {
  schema: JsonSchema;
  onChange: (schema: JsonSchema) => void;
  onValidityChange: (valid: boolean) => void;
}) {
  const t = useTranslations("taskFlows");
  const schema = resolveTaskFlowSchema(rawSchema);
  const resolved = schema;
  const type = Array.isArray(resolved.type)
    ? resolved.type.find((item) => item !== "null")
    : (resolved.type ?? "string");
  const required = Array.isArray(schema.required) ? schema.required : [];
  const onChange = (next: JsonSchema) =>
    onSchemaChange(
      typeof rawSchema.required === "boolean" && Array.isArray(next.required)
        ? {
            required: rawSchema.required,
            anyOf: [next],
            $defs: next.$defs,
            ...(Object.hasOwn(next, "default")
              ? { default: next.default }
              : {}),
            title: next.title,
          }
        : next,
    );
  return (
    <div className="min-w-0 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <label className="grid min-w-0 gap-2 text-xs text-muted">
          {t("portType")}
          <select
            className={FLOW_INPUT_CLASS}
            value={type}
            onChange={(event) => {
              const next = event.target.value;
              onChange({
                ...schema,
                type: next,
                ...(next === "object"
                  ? {
                      properties: schema.properties ?? {},
                      additionalProperties: false,
                    }
                  : {}),
                ...(next === "array"
                  ? { items: schema.items ?? { type: "string" } }
                  : {}),
              });
            }}
          >
            {[
              "string",
              "integer",
              "number",
              "boolean",
              "object",
              "array",
              "null",
            ].map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label className="grid min-w-0 gap-2 text-xs text-muted">
          {t("portTitle")}
          <input
            className={FLOW_INPUT_CLASS}
            value={schema.title ?? ""}
            onChange={(event) =>
              onChange({ ...schema, title: event.target.value })
            }
          />
        </label>
      </div>
      {type === "object" && (
        <div className="space-y-3 border-l border-border pl-3">
          {Object.entries(schema.properties ?? {}).map(([name, field]) => (
            <details key={name} className="min-w-0">
              <summary className="min-h-11 cursor-pointer py-3 text-sm">
                {name}
              </summary>
              <div className="space-y-3 pb-3">
                <NamedField
                  name={name}
                  onRename={(next) => {
                    if (schema.properties?.[next]) return;
                    const properties = Object.fromEntries(
                      Object.entries(schema.properties ?? {}).map(
                        ([key, item]) => [key === name ? next : key, item],
                      ),
                    );
                    onChange({
                      ...schema,
                      properties,
                      required: required.map((key) =>
                        key === name ? next : key,
                      ),
                    });
                  }}
                />
                <SchemaEditor
                  schema={field}
                  onChange={(next) =>
                    onChange({
                      ...schema,
                      properties: { ...schema.properties, [name]: next },
                    })
                  }
                  onValidityChange={onValidityChange}
                />
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={required.includes(name)}
                    onChange={(event) =>
                      onChange({
                        ...schema,
                        required: event.target.checked
                          ? [...required, name]
                          : required.filter((key) => key !== name),
                      })
                    }
                  />
                  {t("required")}
                </label>
                <Button
                  size="sm"
                  variant="ghost"
                  onPress={() =>
                    onChange({
                      ...schema,
                      properties: Object.fromEntries(
                        Object.entries(schema.properties ?? {}).filter(
                          ([key]) => key !== name,
                        ),
                      ),
                      required: required.filter((key) => key !== name),
                    })
                  }
                >
                  {t("remove")}
                </Button>
              </div>
            </details>
          ))}
          <Button
            size="sm"
            variant="outline"
            onPress={() => {
              let index = 1;
              while (schema.properties?.[`field_${index}`]) index += 1;
              onChange({
                ...schema,
                properties: {
                  ...schema.properties,
                  [`field_${index}`]: { type: "string" },
                },
              });
            }}
          >
            {t("addPort")}
          </Button>
        </div>
      )}
      {type === "array" && (
        <div className="border-l border-border pl-3">
          <SchemaEditor
            schema={schema.items ?? { type: "string" }}
            onChange={(items) => onChange({ ...schema, items })}
            onValidityChange={onValidityChange}
          />
        </div>
      )}
      <details>
        <summary className="min-h-11 cursor-pointer py-3 text-xs text-muted">
          {t("portSchema")}
        </summary>
        <FlowJsonField
          label={t("portSchema")}
          value={schema}
          onChange={(value) => {
            if (!isSchemaObject(value)) throw new Error(t("invalidJsonObject"));
            onChange(value);
          }}
          onValidityChange={onValidityChange}
        />
      </details>
    </div>
  );
}

function outputChoices(graph: TaskFlow, exceptNode: string) {
  const choices: { value: string; label: string }[] = [];
  for (const node of graph.nodes) {
    if (node.id === exceptNode) continue;
    for (const [port, schema] of Object.entries(node.outputs)) {
      const append = (field: JsonSchema, path: string[]) => {
        choices.push({
          value: JSON.stringify([node.id, port, path]),
          label: `${node.label} · ${[port, ...path].join(".")}`,
        });
        for (const [name, child] of Object.entries(
          resolveTaskFlowSchema(field).properties ?? {},
        ))
          append(child, [...path, name]);
      };
      append(schema, []);
    }
  }
  return choices;
}

/** 功能：编辑同一任务图的节点、端口和连线。Args: graph 当前图；onChange 写回图定义。Returns: 画布、可访问列表与属性面板。 */
export function TaskFlowEditor({
  graph,
  onChange,
  providers,
  outputSchema,
  onEnterSubflow,
  onValidityChange,
  schemePanel,
  diagnosticsPanel,
  diagnosticsSignal = 0,
  onDiagnosticsOpen,
  graphPath = ROOT_GRAPH_PATH,
  preview,
  previewIndex = -1,
  previewBusy = false,
  previewSessionKey = "",
  previewOverrides,
  onPreviewOverride,
  onResetPreviewOverride,
  previewFocus,
  onPreviewFocus,
}: {
  graph: TaskFlow;
  onChange: (graph: TaskFlow, record?: boolean) => void;
  providers: string[];
  outputSchema: JsonSchema;
  onEnterSubflow: (id: string) => void;
  onValidityChange: (valid: boolean) => void;
  schemePanel?: ReactNode;
  diagnosticsPanel?: ReactNode;
  diagnosticsSignal?: number;
  onDiagnosticsOpen?: () => void;
  graphPath?: string[];
  preview?: TaskFlowPreviewResult | null;
  previewIndex?: number;
  previewBusy?: boolean;
  previewSessionKey?: string;
  previewOverrides?: FlowPreviewOverride[];
  onPreviewOverride?: (override: FlowPreviewOverride) => void;
  onResetPreviewOverride?: (override: FlowPreviewOverride) => void;
  previewFocus?: FlowPreviewFocus;
  onPreviewFocus?: (instancePath: string, port?: string) => void;
}) {
  const t = useTranslations("taskFlows");
  const [selectedId, setSelectedId] = useState(graph.nodes[0]?.id ?? "");
  const [selectedEdgeId, setSelectedEdgeId] = useState("");
  const [view, setView] = useState<"list" | "canvas">("canvas");
  const [panel, setPanel] = useState<
    "canvas" | "library" | "scheme" | "properties" | "diagnostics"
  >("canvas");
  const [leftTab, setLeftTab] = useState<"library" | "scheme">("library");
  const [rightTab, setRightTab] = useState<"properties" | "diagnostics">(
    "properties",
  );
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [propertiesExpanded, setPropertiesExpanded] = useState(false);
  const [seenDiagnostics, setSeenDiagnostics] = useState(diagnosticsSignal);
  const [seenPreviewFocus, setSeenPreviewFocus] = useState<number>();
  const [previewInstance, setPreviewInstance] = useState("");
  const propertiesRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const sizeButtonRef = useRef<HTMLButtonElement>(null);
  const sizeOriginRef = useRef<HTMLElement | null>(null);
  const [placing, setPlacing] = useState<FlowNodeType | null>(null);
  const tabId = useId();
  // 检查请求只切换面板，不重建画布，也不改变缩放与位置。
  if (diagnosticsSignal !== seenDiagnostics) {
    setSeenDiagnostics(diagnosticsSignal);
    setRightTab("diagnostics");
    setRightOpen(true);
    setPanel("diagnostics");
    setPropertiesExpanded(false);
  }
  if (previewFocus && previewFocus.signal !== seenPreviewFocus) {
    const step =
      preview?.steps.find(
        (item) => item.instance_path === previewFocus.instance_path,
      ) ??
      preview?.nodes.find(
        (item) =>
          item.node_id === previewFocus.instance_path.split("/").at(-1) &&
          Object.values(item.outputs).some((field) =>
            field.origins.some(
              (origin) =>
                origin.source_instance_path === previewFocus.instance_path,
            ),
          ),
      );
    if (step && JSON.stringify(step.graph_path) === JSON.stringify(graphPath)) {
      setSeenPreviewFocus(previewFocus.signal);
      setPreviewInstance(previewFocus.instance_path);
      setSelectedId(step.node_id);
      setSelectedEdgeId("");
      setRightTab("properties");
      setRightOpen(true);
      setPanel("properties");
    }
  }
  useEffect(() => {
    const element = editorRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      // 小屏属性已经占满工作区，不留下桌面放大模式的遮挡或键盘禁用状态。
      if (entry.contentRect.width < 1080) setPropertiesExpanded(false);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const restoreProperties = () => {
    setPropertiesExpanded(false);
    requestAnimationFrame(() => {
      const target = sizeOriginRef.current;
      if (target?.isConnected) target.focus({ preventScroll: true });
      else sizeButtonRef.current?.focus({ preventScroll: true });
    });
  };
  useEffect(() => {
    if (!previewFocus || seenPreviewFocus !== previewFocus.signal) return;
    const details = Array.from(
      propertiesRef.current?.querySelectorAll<HTMLDetailsElement>(
        "details[data-preview-port]",
      ) ?? [],
    );
    const target =
      details.find(
        (item) =>
          item.dataset.previewPort === previewFocus.port &&
          item.dataset.previewDirection === "outputs",
      ) ??
      details.find((item) => item.dataset.previewPort === previewFocus.port);
    if (target) {
      target.open = true;
      target.querySelector("summary")?.focus();
      target.scrollIntoView?.({ block: "nearest" });
    } else propertiesRef.current?.focus();
  }, [previewFocus, seenPreviewFocus]);
  const selectNode = useCallback((id: string) => {
    if (focusInvalidFlowJson()) return;
    setSelectedId(id);
    setSelectedEdgeId("");
    setPanel("canvas");
    setRightTab("properties");
    setRightOpen(true);
  }, []);
  const selectEdge = useCallback((id: string) => {
    if (focusInvalidFlowJson()) return;
    setSelectedEdgeId(id);
    setSelectedId("");
  }, []);
  const clearSelection = useCallback(() => {
    if (focusInvalidFlowJson()) return;
    setSelectedId("");
    setSelectedEdgeId("");
  }, []);
  const cancelPlacement = useCallback(() => setPlacing(null), []);
  const showPanel = (next: typeof panel | "list") => {
    if (next === "properties" || focusInvalidFlowJson()) {
      setPanel("properties");
      setRightTab("properties");
      setRightOpen(true);
      // 先显示错误字段所在的面板，再把焦点交回编辑器。
      requestAnimationFrame(() => focusInvalidFlowJson());
      return;
    }
    setPropertiesExpanded(false);
    setPanel(next === "list" ? "canvas" : next);
    if (next === "canvas" || next === "list") setView(next);
    if (next === "library" || next === "scheme") {
      setLeftTab(next);
      setLeftOpen(true);
    }
    if (next === "diagnostics") {
      onDiagnosticsOpen?.();
      setRightTab(next);
      setRightOpen(true);
    }
  };
  const selected = graph.nodes.find((node) => node.id === selectedId);
  const graphSteps = useMemo(
    () =>
      preview?.steps.filter(
        (step) => JSON.stringify(step.graph_path) === JSON.stringify(graphPath),
      ) ?? [],
    [preview, graphPath],
  );
  const visibleSteps = useMemo(
    () =>
      preview?.steps.filter(
        (step, index) =>
          (previewIndex < 0 || index <= previewIndex) &&
          JSON.stringify(step.graph_path) === JSON.stringify(graphPath),
      ) ?? [],
    [preview, previewIndex, graphPath],
  );
  const currentStep =
    previewIndex >= 0 ? preview?.steps[previewIndex] : undefined;
  const previewStates = useMemo(
    () =>
      preview
        ? Object.fromEntries(
            graph.nodes.map((node) => {
              const step = visibleSteps.findLast(
                (item) => item.node_id === node.id,
              );
              const currentInChild =
                currentStep &&
                currentStep.graph_path.length > graphPath.length &&
                graphPath.every(
                  (part, index) => currentStep.graph_path[index] === part,
                );
              const activeParent = currentInChild
                ? currentStep.instance_path
                    .split("/")
                    [graphPath.length + 1]?.replace(/\[\d+\]$/, "")
                : undefined;
              const isCurrent =
                (currentStep?.node_id === node.id &&
                  JSON.stringify(currentStep.graph_path) ===
                    JSON.stringify(graphPath)) ||
                activeParent === node.id;
              return [
                node.id,
                isCurrent
                  ? ("current" as const)
                  : (step?.state ??
                    (preview.errors.some((issue) => issue.node_id === node.id)
                      ? ("error" as const)
                      : graphSteps.some((item) => item.node_id === node.id)
                        ? ("pending" as const)
                        : ("skipped" as const))),
              ];
            }),
          )
        : undefined,
    [preview, graph.nodes, visibleSteps, currentStep, graphPath, graphSteps],
  );
  const previewEdgeIds = useMemo(
    () =>
      preview
        ? [
            ...new Set(
              visibleSteps.flatMap((step) => [
                ...step.used_edges.map((edge) => edge.id),
                ...graph.control_edges
                  .filter(
                    (edge) =>
                      edge.source === step.node_id &&
                      step.active_control_ports.includes(edge.source_port),
                  )
                  .map((edge) => edge.id),
              ]),
            ),
          ]
        : undefined,
    [preview, visibleSteps, graph.control_edges],
  );
  const selectedSteps = graphSteps.filter(
    (step) => step.node_id === selectedId,
  );
  const selectedStep =
    selectedSteps.find((step) => step.instance_path === previewInstance) ??
    visibleSteps.findLast((step) => step.node_id === selectedId) ??
    selectedSteps[0];
  const stepVisible = selectedStep && visibleSteps.includes(selectedStep);
  const formatPreview = preview?.nodes.find(
    (node) =>
      node.node_id === selectedId &&
      JSON.stringify(node.graph_path) === JSON.stringify(graphPath),
  );
  const executedPreview =
    stepVisible && selectedStep.state !== "skipped" ? selectedStep : undefined;
  // 未经过的节点仍展示格式；失败节点保留已得到的值，同时补出尚未产出的字段。
  const selectedPreview = executedPreview
    ? {
        ...executedPreview,
        inputs: { ...formatPreview?.inputs, ...executedPreview.inputs },
        outputs: { ...formatPreview?.outputs, ...executedPreview.outputs },
      }
    : formatPreview;
  const sourceAddresses = Object.entries(formatPreview?.outputs ?? {}).flatMap(
    ([name, field]) =>
      field.origins
        .filter(
          (origin) =>
            origin.source_port === name &&
            origin.source_instance_path?.endsWith(`/${selectedId}`),
        )
        .map((origin) => origin.source_instance_path!),
  );
  const sourceError = preview?.errors.find(
    (issue) =>
      issue.node_id === selectedId ||
      (issue.instance_path && sourceAddresses.includes(issue.instance_path)),
  );
  const previewInstancePath =
    executedPreview?.instance_path ??
    (selected &&
    ["input", "context", "llm"].includes(selected.type) &&
    selectedStep?.state !== "skipped" &&
    sourceError
      ? (sourceError.instance_path ?? sourceAddresses[0])
      : undefined);
  const choices = outputChoices(graph, selectedId);
  const resultMappingKey = outputSchema.properties
    ? "candidate_fields"
    : "output_fields";
  const updateNode = (patch: Partial<FlowNode>) =>
    onChange({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === selectedId ? { ...node, ...patch } : node,
      ),
    });
  const updateConfig = (key: string, value: unknown) =>
    selected && updateNode({ config: { ...selected.config, [key]: value } });
  const removeNode = (id: string) => {
    if (focusInvalidFlowJson()) return;
    onChange({
      ...graph,
      nodes: graph.nodes.filter((node) => node.id !== id),
      edges: graph.edges.filter(
        (edge) => edge.source !== id && edge.target !== id,
      ),
      control_edges: graph.control_edges.filter(
        (edge) => edge.source !== id && edge.target !== id,
      ),
    });
    if (selectedId === id) {
      setSelectedId("");
      setPropertiesExpanded(false);
    }
  };
  const removeEdge = (id: string) => {
    onChange({
      ...graph,
      edges: graph.edges.filter((edge) => edge.id !== id),
      control_edges: graph.control_edges.filter((edge) => edge.id !== id),
    });
    setSelectedEdgeId("");
  };
  const copyNode = (nodeId: string) => {
    if (focusInvalidFlowJson()) return;
    const original = graph.nodes.find((node) => node.id === nodeId)!;
    if (original.type === "input" || original.type === "output") return;
    const id = `${original.type}_${crypto.randomUUID().slice(0, 8)}`;
    const index = graph.nodes.indexOf(original);
    const position = graph.editor.positions?.[nodeId] ?? {
      x: (index % 3) * 340,
      y: Math.floor(index / 3) * 280,
    };
    onChange({
      ...graph,
      nodes: [
        ...graph.nodes,
        {
          ...structuredClone(original),
          id,
          label: t("newCopyName", { name: original.label }),
        },
      ],
      editor: {
        ...graph.editor,
        positions: {
          ...graph.editor.positions,
          [id]: { x: position.x + 40, y: position.y + 40 },
        },
      },
    });
    selectNode(id);
  };
  const addNode = (type: FlowNodeType, position: XYPosition) => {
    if (focusInvalidFlowJson()) return;
    const id = `${type}_${crypto.randomUUID().slice(0, 8)}`;
    const node: FlowNode = {
      id,
      type,
      label: t(`types.${type}`),
      inputs: {},
      outputs: {},
      values: {},
      config: {},
    };
    if (type === "agent") {
      node.inputs = { context: { type: "object" } };
      node.outputs = { prepared_context: { type: "object" } };
      node.config = { prompt: "{context}", system_prompt: "", tools: [...AGENT_TOOLS], max_rounds: 8, max_tool_calls: 24, skills: [] };
    }
    if (type === "llm") {
      node.inputs = { input: { type: "string" } };
      node.outputs = { text: { type: "string" } };
      node.config = {
        prompt: "{input}",
        schema_prompt: "",
        text_prompt: "",
        mode: "text",
      };
    }
    if (type === "template") {
      node.inputs = { input: { type: "string" } };
      node.outputs = { text: { type: "string" } };
      node.config = { template: "{input}", output_port: "text" };
    }
    if (type === "constant") {
      node.outputs = { value: { type: "string" } };
      node.values = { value: "" };
    }
    if (type === "condition") {
      node.inputs = { value: { type: "boolean" } };
      node.config = {
        cases: [{ port: "yes", input: "value", operator: "truthy" }],
        else_port: "else",
      };
    }
    if (type === "merge") {
      node.inputs = { first: { type: "string" }, second: { type: "string" } };
      node.outputs = { value: { type: "string" } };
      node.config = { mode: "selected", output_port: "value" };
    }
    if (type === "output")
      node.config = { candidate_fields: {}, parameter_fields: {} };
    if (type === "foreach") {
      node.inputs = { items: { type: "array", items: { type: "object" } } };
      node.outputs = { items: { type: "array", items: { type: "object" } } };
      node.config = {
        subflow_id: "",
        items_input: "items",
        item_input: "item",
        index_input: "index",
        output_port: "items",
      };
    }
    onChange({
      ...graph,
      nodes: [...graph.nodes, node],
      editor: {
        ...graph.editor,
        positions: {
          ...graph.editor.positions,
          [id]: position,
        },
      },
    });
    selectNode(id);
    setPlacing(null);
    setPanel("canvas");
  };
  const connect = (connection: Connection) => {
    if (
      !connection.source ||
      !connection.target ||
      connection.source === connection.target
    )
      return;
    const id = crypto.randomUUID();
    if (
      connection.sourceHandle?.startsWith("exec:") &&
      connection.targetHandle === "exec"
    ) {
      const edge = {
        id,
        source: connection.source,
        source_port: connection.sourceHandle.slice(5),
        target: connection.target,
      };
      if (
        !graph.control_edges.some(
          (item) =>
            item.source === edge.source &&
            item.source_port === edge.source_port &&
            item.target === edge.target,
        )
      )
        onChange({ ...graph, control_edges: [...graph.control_edges, edge] });
    } else if (
      connection.sourceHandle?.startsWith("out:") &&
      connection.targetHandle?.startsWith("in:")
    ) {
      const targetPort = connection.targetHandle.slice(3);
      onChange({
        ...graph,
        edges: [
          ...graph.edges.filter(
            (edge) =>
              edge.target !== connection.target ||
              edge.target_port !== targetPort,
          ),
          {
            id,
            source: connection.source,
            source_port: connection.sourceHandle.slice(4),
            target: connection.target,
            target_port: targetPort,
          },
        ],
      });
    }
  };
  return (
    <div
      ref={editorRef}
      className="@container/flow-editor flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
      onKeyDown={(event) => {
        if (
          event.key !== "Escape" ||
          event.defaultPrevented ||
          !propertiesExpanded
        )
          return;
        event.preventDefault();
        event.stopPropagation();
        restoreProperties();
      }}
    >
      <div
        className="workspace-scrollbar flex min-h-11 shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-2"
        role="tablist"
        aria-label={t("canvasHelp.panels")}
        onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
            return;
          const tabs = Array.from(
            event.currentTarget.querySelectorAll<HTMLButtonElement>(
              "[role='tab']",
            ),
          );
          const index = tabs.indexOf(
            document.activeElement as HTMLButtonElement,
          );
          event.preventDefault();
          const next =
            event.key === "Home"
              ? 0
              : event.key === "End"
                ? tabs.length - 1
                : (index +
                    (event.key === "ArrowRight" ? 1 : -1) +
                    tabs.length) %
                  tabs.length;
          tabs[next]?.focus();
          tabs[next]?.click();
        }}
      >
        {(
          [
            "canvas",
            "list",
            "library",
            ...(schemePanel ? ["scheme" as const] : []),
            "properties",
            ...(diagnosticsPanel ? ["diagnostics" as const] : []),
          ] as const
        ).map((item) => (
          <button
            type="button"
            key={item}
            id={`${tabId}-${item}-tab`}
            role="tab"
            aria-selected={(panel === "canvas" ? view : panel) === item}
            aria-controls={`${tabId}-${item === "list" ? "canvas" : item}-panel`}
            tabIndex={(panel === "canvas" ? view : panel) === item ? 0 : -1}
            className={`min-h-11 shrink-0 rounded-lg px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${(panel === "canvas" ? view : panel) === item ? "bg-selected" : "hover:bg-surface-secondary"}`}
            onClick={() => showPanel(item)}
          >
            {t(
              item === "list"
                ? "nodeList"
                : item === "library"
                  ? "nodeLibrary"
                  : item === "scheme"
                    ? "canvasHelp.scheme"
                    : item === "diagnostics"
                      ? "canvasHelp.diagnostics"
                      : item,
            )}
          </button>
        ))}
        <div className="ml-auto hidden shrink-0 items-center gap-1 @min-[1080px]/flow-editor:flex">
          <TooltipHint text={t("canvasHelp.toggleLibrary")}>
            <Button
              size="sm"
              variant="ghost"
              aria-label={t("canvasHelp.toggleLibrary")}
              aria-expanded={leftOpen}
              aria-controls={`${tabId}-left`}
              onPress={() => setLeftOpen(!leftOpen)}
            >
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <path d="M9 4v16" />
              </svg>
            </Button>
          </TooltipHint>
          <TooltipHint text={t("canvasHelp.toggleProperties")}>
            <Button
              size="sm"
              variant="ghost"
              aria-label={t("canvasHelp.toggleProperties")}
              aria-expanded={rightOpen}
              aria-controls={`${tabId}-right`}
              onPress={() => {
                setPropertiesExpanded(false);
                setRightOpen(!rightOpen);
              }}
            >
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <rect x="3" y="4" width="18" height="16" rx="2" />
                <path d="M15 4v16" />
              </svg>
            </Button>
          </TooltipHint>
        </div>
      </div>
      <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <aside
          id={`${tabId}-left`}
          aria-label={t("nodeLibrary")}
          inert={propertiesExpanded}
          className={`${panel === "library" || panel === "scheme" ? "flex" : "hidden"} min-h-0 min-w-0 flex-1 flex-col border-r border-border @min-[1080px]/flow-editor:w-56 @min-[1080px]/flow-editor:flex-none ${leftOpen ? "@min-[1080px]/flow-editor:flex" : "@min-[1080px]/flow-editor:hidden"}`}
        >
          <div
            id={`${tabId}-library-panel`}
            role="tabpanel"
            aria-labelledby={`${tabId}-library-tab`}
            className={`${leftTab === "library" ? "flex" : "hidden"} min-h-0 flex-1 flex-col`}
          >
            <div className="flex min-h-11 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
              <h2 className="text-sm font-semibold">{t("nodeLibrary")}</h2>
              <TooltipHint text={t("canvasHelp.library")} />
            </div>
            <div
              className="workspace-scrollbar min-h-0 flex-1 overflow-auto p-2"
              tabIndex={0}
              aria-label={t("nodeLibrary")}
            >
              {FLOW_NODE_TYPES.map((type) => (
                <div
                  key={type}
                  className={`mb-1 flex min-h-11 items-center rounded-lg border ${placing === type ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}
                >
                  <button
                    type="button"
                    draggable
                    aria-pressed={placing === type}
                    className="min-h-11 min-w-0 flex-1 cursor-grab px-3 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent active:cursor-grabbing"
                    onDragStart={(event) => {
                      event.dataTransfer.setData(
                        "application/task-flow-node",
                        type,
                      );
                      event.dataTransfer.effectAllowed = "copy";
                    }}
                    onClick={() => {
                      if (focusInvalidFlowJson()) return;
                      setPlacing(type);
                      setPanel("canvas");
                      setView("canvas");
                    }}
                  >
                    {t(`types.${type}`)}
                  </button>
                  <TooltipHint
                    text={t(`nodeHelp.${type}`)}
                    className="mr-2 shrink-0"
                  />
                </div>
              ))}
            </div>
          </div>
          {schemePanel && (
            <div
              id={`${tabId}-scheme-panel`}
              role="tabpanel"
              aria-labelledby={`${tabId}-scheme-tab`}
              className={`${leftTab === "scheme" ? "block" : "hidden"} workspace-scrollbar min-h-0 min-w-0 flex-1 overflow-auto p-3`}
              tabIndex={0}
            >
              {schemePanel}
            </div>
          )}
        </aside>
        <section
          id={`${tabId}-canvas-panel`}
          role="tabpanel"
          aria-labelledby={`${tabId}-${view}-tab`}
          inert={propertiesExpanded}
          className={`${panel === "canvas" ? "flex" : "hidden"} min-h-0 min-w-0 flex-1 flex-col @min-[1080px]/flow-editor:flex`}
        >
          <div
            className={`${view === "canvas" ? "flex" : "hidden"} min-h-0 min-w-0 flex-1`}
          >
            <TaskFlowCanvas
              graph={graph}
              previewStates={previewStates}
              previewEdgeIds={previewEdgeIds}
              selectedId={selectedId}
              selectedEdgeId={selectedEdgeId}
              placing={placing}
              onSelectNode={selectNode}
              onSelectEdge={selectEdge}
              onClearSelection={clearSelection}
              onPlace={addNode}
              onCancelPlace={cancelPlacement}
              onCopyNode={copyNode}
              onRemoveNode={removeNode}
              onRemoveEdge={removeEdge}
              onChange={onChange}
              onConnect={connect}
              onOpenProperties={(id) => {
                selectNode(id);
                setPanel("properties");
              }}
            />
          </div>
          {view === "list" && (
            <div
              className="workspace-scrollbar min-h-0 flex-1 overflow-auto"
              tabIndex={0}
              aria-label={t("nodeList")}
            >
              <ul>
                {graph.nodes.map((node) => (
                  <li key={node.id}>
                    <button
                      type="button"
                      className={`flex min-h-11 w-full items-center justify-between gap-3 border-l-2 px-4 py-3 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${selectedId === node.id ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}
                      onClick={() => {
                        if (focusInvalidFlowJson()) return;
                        selectNode(node.id);
                        setPanel("properties");
                      }}
                      aria-current={selectedId === node.id ? "true" : undefined}
                    >
                      <span className="min-w-0 truncate">{node.label}</span>
                      <span className="shrink-0 text-xs text-muted">
                        {t(`types.${node.type}`)}
                        {previewStates?.[node.id] && (
                          <span className="ml-2">
                            {t(`preview.${previewStates[node.id]}`)}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="border-t border-border px-3 py-2 text-xs font-semibold">
                {t("canvasHelp.connections")}
              </div>
              <ul>
                {[
                  ...graph.edges.map((edge) => ({
                    ...edge,
                    source_path: edge.source_path ?? [],
                  })),
                  ...graph.control_edges.map((edge) => ({
                    ...edge,
                    source_path: [],
                    target_port: t("control"),
                  })),
                ].map((edge) => (
                  <li key={edge.id}>
                    <button
                      type="button"
                      className={`min-h-11 w-full break-all border-l-2 px-4 py-3 text-left text-xs focus-visible:ring-2 focus-visible:ring-accent ${selectedEdgeId === edge.id ? "border-accent bg-selected font-semibold" : "border-transparent"}`}
                      onClick={() => {
                        selectEdge(edge.id);
                        setView("canvas");
                        setPanel("canvas");
                      }}
                    >
                      {
                        graph.nodes.find((node) => node.id === edge.source)
                          ?.label
                      }
                      .{[edge.source_port, ...edge.source_path].join(".")} →{" "}
                      {
                        graph.nodes.find((node) => node.id === edge.target)
                          ?.label
                      }
                      .{edge.target_port}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
        <aside
          id={`${tabId}-right`}
          aria-label={t("properties")}
          className={`${panel === "properties" || panel === "diagnostics" ? "flex" : "hidden"} min-h-0 min-w-0 flex-1 flex-col border-l border-border @min-[1080px]/flow-editor:w-[336px] @min-[1080px]/flow-editor:flex-none ${rightOpen ? "@min-[1080px]/flow-editor:flex" : "@min-[1080px]/flow-editor:hidden"}`}
        >
          {diagnosticsPanel && (
            <div
              id={`${tabId}-diagnostics-panel`}
              role="tabpanel"
              aria-labelledby={`${tabId}-diagnostics-tab`}
              className={`${rightTab === "diagnostics" ? "block" : "hidden"} workspace-scrollbar min-h-0 flex-1 overflow-auto p-4`}
              tabIndex={0}
            >
              {diagnosticsPanel}
            </div>
          )}
          <div
            ref={propertiesRef}
            id={`${tabId}-properties-panel`}
            role="tabpanel"
            aria-labelledby={`${tabId}-properties-tab`}
            className={`${rightTab === "properties" ? "block" : "hidden"} ${propertiesExpanded ? "absolute inset-0 z-20 bg-surface" : ""} workspace-scrollbar min-h-0 min-w-0 flex-1 overflow-auto p-4`}
            tabIndex={0}
          >
            {!selected && (
              <p className="text-sm text-muted">{t("canvasHelp.chooseNode")}</p>
            )}
            {selected && (
              <div key={selected.id} className="space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="mr-auto text-sm font-semibold">
                    {t("properties")}
                  </h2>
                  <div className="hidden @min-[1080px]/flow-editor:block">
                    <TooltipHint
                      text={t(
                        propertiesExpanded
                          ? "canvasHelp.restoreProperties"
                          : "canvasHelp.expandProperties",
                      )}
                    >
                      <Button
                        ref={sizeButtonRef}
                        isIconOnly
                        size="sm"
                        variant="ghost"
                        type="button"
                        aria-label={t(
                          propertiesExpanded
                            ? "canvasHelp.restoreProperties"
                            : "canvasHelp.expandProperties",
                        )}
                        aria-expanded={propertiesExpanded}
                        aria-controls={`${tabId}-properties-panel`}
                        className="flex size-11 shrink-0 items-center justify-center rounded-lg hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                        onPointerDown={() => {
                          if (!propertiesExpanded)
                            sizeOriginRef.current =
                              document.activeElement as HTMLElement;
                        }}
                        onClick={(event) => {
                          if (propertiesExpanded) {
                            restoreProperties();
                            return;
                          }
                          if (event.detail === 0)
                            sizeOriginRef.current = sizeButtonRef.current;
                          setPanel("properties");
                          setPropertiesExpanded(true);
                          requestAnimationFrame(() =>
                            sizeOriginRef.current?.focus({
                              preventScroll: true,
                            }),
                          );
                        }}
                      >
                        <svg
                          aria-hidden="true"
                          width="18"
                          height="18"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                        >
                          <path
                            d={
                              propertiesExpanded
                                ? "M9 3v6H3m18 6h-6v6M9 9 3 3m12 12 6 6"
                                : "M3 9V3h6m6 18h6v-6M3 3l6 6m6 6 6 6"
                            }
                          />
                        </svg>
                      </Button>
                    </TooltipHint>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    isDisabled={
                      selected.type === "input" || selected.type === "output"
                    }
                    onPress={() => copyNode(selected.id)}
                  >
                    {t("copyNode")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onPress={() => removeNode(selected.id)}
                  >
                    {t("deleteNode")}
                  </Button>
                </div>
                <label className="grid gap-2 text-xs text-muted">
                  {t("label")}
                  <input
                    className={FLOW_INPUT_CLASS}
                    value={selected.label}
                    onChange={(event) =>
                      updateNode({ label: event.target.value })
                    }
                  />
                </label>
                {selectedSteps.length > 0 && (
                  <label className="grid gap-2 text-xs text-muted">
                    {t("preview.instance")}
                    <select
                      className={FLOW_INPUT_CLASS}
                      value={selectedStep?.instance_path ?? ""}
                      onChange={(event) =>
                        setPreviewInstance(event.target.value)
                      }
                    >
                      {selectedSteps.map((step) => (
                        <option
                          key={step.instance_path}
                          value={step.instance_path}
                        >
                          {step.instance_path}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {selectedPreview && (
                  <p className="text-xs text-muted">
                    {t(
                      `preview.${stepVisible ? selectedStep.state : sourceError ? "error" : selectedSteps.length ? "pending" : "skipped"}`,
                    )}
                  </p>
                )}
                {["llm", "agent"].includes(selected.type) && executedPreview?.ai_request && (
                  <TaskFlowAIRequestPreview
                    request={executedPreview.ai_request}
                    busy={previewBusy}
                    containsExamples={Object.values(
                      executedPreview.inputs,
                    ).some((field) =>
                      field.origins.some((origin) =>
                        origin.kind.endsWith("_example"),
                      ),
                    )}
                  />
                )}
                {(["inputs", "outputs"] as const).map((direction) => (
                  <section
                    key={direction}
                    className="space-y-3 border-t border-border pt-4"
                  >
                    <h3 className="text-sm font-semibold">
                      {t(direction === "inputs" ? "inputPorts" : "outputPorts")}{" "}
                      <TooltipHint text={t("propertyHelp.ports")} />
                    </h3>
                    {Object.entries(selected[direction]).map(
                      ([name, schema]) => (
                        <details
                          key={name}
                          data-preview-port={name}
                          data-preview-direction={direction}
                          className="min-w-0 border-b border-border"
                        >
                          <summary className="min-h-11 cursor-pointer py-3 text-sm">
                            {name}
                          </summary>
                          <div className="space-y-3 pb-4">
                            {selectedPreview?.[direction][name] && (
                              <TaskFlowPortPreview
                                key={`${previewSessionKey}:${previewInstancePath ?? "format"}`}
                                port={name}
                                schema={schema}
                                data={selectedPreview[direction][name]}
                                instancePath={previewInstancePath}
                                output={direction === "outputs"}
                                busy={previewBusy}
                                overrides={previewOverrides}
                                errors={preview?.errors}
                                onOverride={onPreviewOverride}
                                onResetOverride={onResetPreviewOverride}
                                onFocus={onPreviewFocus}
                              />
                            )}
                            <NamedField
                              name={name}
                              onRename={(next) => {
                                if (selected[direction][next]) return;
                                const ports = Object.fromEntries(
                                  Object.entries(selected[direction]).map(
                                    ([key, item]) => [
                                      key === name ? next : key,
                                      item,
                                    ],
                                  ),
                                );
                                onChange({
                                  ...graph,
                                  nodes: graph.nodes.map((node) =>
                                    node.id === selected.id
                                      ? {
                                          ...node,
                                          [direction]: ports,
                                          values: Object.fromEntries(
                                            Object.entries(node.values).map(
                                              ([key, value]) => [
                                                key === name ? next : key,
                                                value,
                                              ],
                                            ),
                                          ),
                                        }
                                      : node,
                                  ),
                                  edges: graph.edges.map((edge) =>
                                    direction === "inputs" &&
                                    edge.target === selected.id &&
                                    edge.target_port === name
                                      ? { ...edge, target_port: next }
                                      : direction === "outputs" &&
                                          edge.source === selected.id &&
                                          edge.source_port === name
                                        ? { ...edge, source_port: next }
                                        : edge,
                                  ),
                                });
                              }}
                            />
                            <label className="flex min-h-11 items-center gap-2 text-sm">
                              <input
                                type="checkbox"
                                checked={schema.required !== false}
                                onChange={(event) =>
                                  updateNode({
                                    [direction]: {
                                      ...selected[direction],
                                      [name]: Array.isArray(schema.required)
                                        ? {
                                            anyOf: [schema],
                                            required: event.target.checked,
                                            $defs: schema.$defs,
                                            ...(Object.hasOwn(schema, "default")
                                              ? { default: schema.default }
                                              : {}),
                                          }
                                        : {
                                            ...schema,
                                            required: event.target.checked,
                                          },
                                    },
                                  })
                                }
                              />
                              {t("required")}
                            </label>
                            <SchemaEditor
                              schema={schema}
                              onChange={(next) =>
                                updateNode({
                                  [direction]: {
                                    ...selected[direction],
                                    [name]: next,
                                  },
                                })
                              }
                              onValidityChange={onValidityChange}
                            />
                            {direction === "inputs" && (
                              <>
                                <label className="grid min-w-0 gap-2 text-xs text-muted">
                                  <span className="inline-flex items-center gap-1">
                                    {t("source")}
                                    <TooltipHint
                                      text={t("propertyHelp.source")}
                                    />
                                  </span>
                                  <select
                                    aria-label={t("source")}
                                    className={FLOW_INPUT_CLASS}
                                    value={(() => {
                                      const edge = graph.edges.find(
                                        (item) =>
                                          item.target === selected.id &&
                                          item.target_port === name,
                                      );
                                      return edge
                                        ? JSON.stringify([
                                            edge.source,
                                            edge.source_port,
                                            edge.source_path ?? [],
                                          ])
                                        : "";
                                    })()}
                                    onChange={(event) => {
                                      const remaining = graph.edges.filter(
                                        (edge) =>
                                          edge.target !== selected.id ||
                                          edge.target_port !== name,
                                      );
                                      if (!event.target.value) {
                                        onChange({
                                          ...graph,
                                          edges: remaining,
                                        });
                                        return;
                                      }
                                      const [source, sourcePort, sourcePath] =
                                        JSON.parse(event.target.value) as [
                                          string,
                                          string,
                                          string[],
                                        ];
                                      onChange({
                                        ...graph,
                                        edges: [
                                          ...remaining,
                                          {
                                            id: crypto.randomUUID(),
                                            source,
                                            source_port: sourcePort,
                                            source_path: sourcePath,
                                            target: selected.id,
                                            target_port: name,
                                          },
                                        ],
                                      });
                                    }}
                                  >
                                    <option value="">
                                      {t("noConnection")}
                                    </option>
                                    {choices.map((choice) => (
                                      <option
                                        key={choice.value}
                                        value={choice.value}
                                      >
                                        {choice.label}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <FlowJsonField
                                  label={t("value")}
                                  value={
                                    Object.hasOwn(selected.values, name)
                                      ? selected.values[name]
                                      : (schema.default ?? null)
                                  }
                                  onChange={(value) =>
                                    updateNode({
                                      values: {
                                        ...selected.values,
                                        [name]: value,
                                      },
                                    })
                                  }
                                  onValidityChange={onValidityChange}
                                />
                              </>
                            )}
                            {direction === "outputs" &&
                              (selected.type === "input" ||
                                selected.type === "constant") && (
                                <FlowJsonField
                                  label={t("defaultValue")}
                                  value={
                                    Object.hasOwn(selected.values, name)
                                      ? selected.values[name]
                                      : (schema.default ?? null)
                                  }
                                  onChange={(value) =>
                                    updateNode({
                                      outputs: {
                                        ...selected.outputs,
                                        [name]: { ...schema, default: value },
                                      },
                                      values: {
                                        ...selected.values,
                                        [name]: value,
                                      },
                                    })
                                  }
                                  onValidityChange={onValidityChange}
                                />
                              )}
                            <Button
                              size="sm"
                              variant="ghost"
                              onPress={() =>
                                onChange({
                                  ...graph,
                                  nodes: graph.nodes.map((node) =>
                                    node.id === selected.id
                                      ? {
                                          ...node,
                                          [direction]: Object.fromEntries(
                                            Object.entries(
                                              node[direction],
                                            ).filter(([key]) => key !== name),
                                          ),
                                        }
                                      : node,
                                  ),
                                  edges: graph.edges.filter((edge) =>
                                    direction === "inputs"
                                      ? edge.target !== selected.id ||
                                        edge.target_port !== name
                                      : edge.source !== selected.id ||
                                        edge.source_port !== name,
                                  ),
                                })
                              }
                            >
                              {t("remove")}
                            </Button>
                          </div>
                        </details>
                      ),
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      isDisabled={
                        direction === "inputs" && selected.type === "input"
                      }
                      onPress={() => {
                        let index = 1;
                        while (selected[direction][`field_${index}`])
                          index += 1;
                        updateNode({
                          [direction]: {
                            ...selected[direction],
                            [`field_${index}`]: { type: "string" },
                          },
                        });
                      }}
                    >
                      {t("addPort")}
                    </Button>
                  </section>
                ))}
                {selected.type === "agent" && <section className="space-y-4 border-t border-border pt-4">
                  <FlowPromptEditor label={t("prompt")} value={String(selected.config.prompt ?? "")} ports={selected.inputs} onChange={(value) => updateConfig("prompt", value)} />
                  <FlowPromptEditor label={t("systemPrompt")} value={String(selected.config.system_prompt ?? "")} ports={selected.inputs} onChange={(value) => updateConfig("system_prompt", value)} />
                  <label className="grid gap-2 text-xs text-muted">{t("provider")}<select className={FLOW_INPUT_CLASS} value={String(selected.config.provider ?? "")} onChange={(event) => updateConfig("provider", event.target.value)}><option value="">{t("inherit")}</option>{providers.map((provider) => <option key={provider}>{provider}</option>)}</select></label>
                  <label className="grid gap-2 text-xs text-muted">{t("model")}<input className={FLOW_INPUT_CLASS} value={String(selected.config.model ?? "")} onChange={(event) => updateConfig("model", event.target.value)} /></label>
                  {(["max_rounds", "max_tool_calls"] as const).map((field) => <label key={field} className="grid gap-2 text-xs text-muted">{t(`agent.${field}`)}<input className={FLOW_INPUT_CLASS} type="number" min={1} max={field === "max_rounds" ? 8 : 24} value={Number(selected.config[field] ?? (field === "max_rounds" ? 8 : 24))} onChange={(event) => updateConfig(field, Number(event.target.value))} /></label>)}
                  <fieldset><legend className="mb-2 text-sm font-medium">{t("agent.tools")}</legend><div className="grid gap-1">{AGENT_TOOLS.map((tool) => <label key={tool} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={((selected.config.tools ?? []) as string[]).includes(tool)} onChange={(event) => updateConfig("tools", event.target.checked ? [...((selected.config.tools ?? []) as string[]), tool] : ((selected.config.tools ?? []) as string[]).filter((name) => name !== tool))} />{t(`agent.toolNames.${tool}`)}</label>)}</div></fieldset>
                  <section className="space-y-3 border-t border-border pt-4"><h3 className="text-sm font-semibold">{t("agent.skills")}</h3>
                    {((selected.config.skills ?? []) as AgentSkill[]).map((skill, index, skills) => <details key={skill.id} className="border-b border-border pb-3"><summary className="min-h-11 cursor-pointer py-2 text-sm">{skill.name || t("agent.untitledSkill")}</summary><div className="space-y-3">
                      {(["name", "description"] as const).map((field) => <label key={field} className="grid gap-2 text-xs text-muted">{t(`agent.${field}`)}<input className={FLOW_INPUT_CLASS} value={skill[field]} onChange={(event) => updateConfig("skills", skills.map((item, position) => position === index ? { ...item, [field]: event.target.value } : item))} /></label>)}
                      <FlowPromptEditor label={t("agent.instructions")} value={skill.instructions} ports={selected.inputs} onChange={(value) => updateConfig("skills", skills.map((item, position) => position === index ? { ...item, instructions: value } : item))} />
                      <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onPress={() => updateConfig("skills", [...skills, { ...skill, id: `skill_${crypto.randomUUID().slice(0, 8)}`, name: t("newCopyName", { name: skill.name }) }])}>{t("copy")}</Button><Button size="sm" variant="ghost" onPress={() => updateConfig("skills", skills.filter((item) => item.id !== skill.id))}>{t("remove")}</Button></div>
                    </div></details>)}
                    <Button size="sm" variant="outline" onPress={() => updateConfig("skills", [...((selected.config.skills ?? []) as AgentSkill[]), { id: `skill_${crypto.randomUUID().slice(0, 8)}`, name: t("agent.untitledSkill"), description: "", instructions: "" }])}>{t("agent.addSkill")}</Button>
                  </section>
                  <ReasoningControls value={(selected.config.parameters ?? {}) as ReasoningOptions} onChange={(patch) => updateConfig("parameters", { ...(selected.config.parameters as object ?? {}), ...patch })} />
                  <FlowJsonField label={t("parameters")} value={selected.config.parameters ?? {}} onChange={(value) => updateConfig("parameters", value)} onValidityChange={onValidityChange} />
                </section>}
                {selected.type === "llm" && (
                  <section className="space-y-4 border-t border-border pt-4">
                    <FlowPromptEditor
                      label={t("prompt")}
                      value={String(selected.config.prompt ?? "")}
                      ports={selected.inputs}
                      requiredPorts={Object.keys(selected.inputs).filter(
                        (name) =>
                          name !== selected.config.provider_input &&
                          selected.inputs[name].required !== false,
                      )}
                      relatedPrompts={[
                        String(selected.config.system_prompt ?? ""),
                        ...(selected.config.format_suffix
                          ? ["schema_prompt", "text_prompt"].map((key) => String(selected.config[key] ?? ""))
                          : []),
                      ]}
                      onChange={(value) => updateConfig("prompt", value)}
                    />
                    <FlowPromptEditor
                      label={t("schemaPrompt")}
                      value={String(selected.config.schema_prompt ?? "")}
                      ports={selected.inputs}
                      formatInputs={Boolean(selected.config.format_suffix)}
                      onChange={(value) => updateConfig("schema_prompt", value)}
                    />
                    <FlowJsonSuffixEditor
                      label={t("textPrompt")}
                      value={String(selected.config.text_prompt ?? "")}
                      ports={selected.inputs}
                      formatSuffix={Boolean(selected.config.format_suffix)}
                      onChange={(value) => updateConfig("text_prompt", value)}
                      onValidityChange={onValidityChange}
                    />
                    <FlowPromptEditor
                      label={t("systemPrompt")}
                      value={String(selected.config.system_prompt ?? "")}
                      ports={selected.inputs}
                      onChange={(value) => updateConfig("system_prompt", value)}
                    />
                    <label className="grid gap-2 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        {t("provider")}
                        <TooltipHint text={t("propertyHelp.provider")} />
                      </span>
                      <select
                        aria-label={t("provider")}
                        className={FLOW_INPUT_CLASS}
                        value={String(selected.config.provider ?? "")}
                        onChange={(event) =>
                          updateConfig("provider", event.target.value)
                        }
                      >
                        <option value="">{t("inherit")}</option>
                        {providers.map((provider) => (
                          <option key={provider}>{provider}</option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-2 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        {t("model")}
                        <TooltipHint text={t("propertyHelp.model")} />
                      </span>
                      <input
                        aria-label={t("model")}
                        className={FLOW_INPUT_CLASS}
                        value={String(selected.config.model ?? "")}
                        onChange={(event) =>
                          updateConfig("model", event.target.value)
                        }
                      />
                    </label>
                    <label className="grid gap-2 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        {t("outputMode")}
                        <TooltipHint text={t("propertyHelp.outputMode")} />
                      </span>
                      <select
                        aria-label={t("outputMode")}
                        className={FLOW_INPUT_CLASS}
                        value={String(selected.config.mode ?? "json")}
                        onChange={(event) =>
                          updateConfig("mode", event.target.value)
                        }
                      >
                        <option value="json">{t("structured")}</option>
                        <option value="text">{t("text")}</option>
                      </select>
                    </label>
                    <label className="grid gap-2 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        {t("timeout")}
                        <TooltipHint text={t("propertyHelp.timeout")} />
                      </span>
                      <input
                        aria-label={t("timeout")}
                        className={FLOW_INPUT_CLASS}
                        type="number"
                        min={1}
                        value={
                          typeof selected.config.timeout_seconds === "number"
                            ? selected.config.timeout_seconds
                            : ""
                        }
                        onChange={(event) =>
                          updateConfig(
                            "timeout_seconds",
                            event.target.value
                              ? Number(event.target.value)
                              : null,
                          )
                        }
                      />
                    </label>
                    <ReasoningControls value={(selected.config.parameters ?? {}) as ReasoningOptions} onChange={(patch) => updateConfig("parameters", { ...(selected.config.parameters as object ?? {}), ...patch })} />
                    <FlowJsonField
                      label={t("parameters")}
                      value={selected.config.parameters ?? {}}
                      onChange={(value) => updateConfig("parameters", value)}
                      onValidityChange={onValidityChange}
                    />
                  </section>
                )}
                {selected.type === "template" && (
                  <FlowPromptEditor
                    label={t("prompt")}
                    value={String(selected.config.template ?? "")}
                    ports={selected.inputs}
                    requiredPorts={Object.keys(selected.inputs).filter(
                      (name) => selected.inputs[name].required !== false,
                    )}
                    onChange={(value) => updateConfig("template", value)}
                  />
                )}
                {selected.type === "condition" && (
                  <section className="space-y-4 border-t border-border pt-4">
                    <h3 className="flex items-center gap-1 text-sm font-semibold">
                      {t("conditions")}
                      <TooltipHint text={t("propertyHelp.conditions")} />
                    </h3>
                    {((selected.config.cases ?? []) as FlowCondition[]).map(
                      (condition, index, cases) => (
                        <div
                          key={index}
                          className="space-y-3 border-b border-border pb-4"
                        >
                          {(["port", "input", "operator"] as const).map(
                            (key) => (
                              <label
                                key={key}
                                className="grid gap-2 text-xs text-muted"
                              >
                                {t(
                                  {
                                    port: "controlPort",
                                    input: "conditionInput",
                                    operator: "operator",
                                  }[key],
                                )}
                                {key === "port" ? (
                                  <input
                                    className={FLOW_INPUT_CLASS}
                                    value={condition[key]}
                                    onChange={(event) =>
                                      updateConfig(
                                        "cases",
                                        cases.map((item, i) =>
                                          i === index
                                            ? {
                                                ...item,
                                                [key]: event.target.value,
                                              }
                                            : item,
                                        ),
                                      )
                                    }
                                  />
                                ) : (
                                  <select
                                    className={FLOW_INPUT_CLASS}
                                    value={condition[key]}
                                    onChange={(event) =>
                                      updateConfig(
                                        "cases",
                                        cases.map((item, i) =>
                                          i === index
                                            ? {
                                                ...item,
                                                [key]: event.target.value,
                                              }
                                            : item,
                                        ),
                                      )
                                    }
                                  >
                                    {(key === "input"
                                      ? Object.keys(selected.inputs)
                                      : [
                                          "truthy",
                                          "exists",
                                          "eq",
                                          "ne",
                                          "gt",
                                          "gte",
                                          "lt",
                                          "lte",
                                          "contains",
                                        ]
                                    ).map((value) => (
                                      <option key={value} value={value}>
                                        {key === "operator"
                                          ? t(`operators.${value}`)
                                          : value}
                                      </option>
                                    ))}
                                  </select>
                                )}
                              </label>
                            ),
                          )}
                          {!["truthy", "exists"].includes(
                            condition.operator,
                          ) && (
                            <>
                              <label className="grid gap-2 text-xs text-muted">
                                {t("compareInput")}
                                <select
                                  className={FLOW_INPUT_CLASS}
                                  value={condition.compare_input ?? ""}
                                  onChange={(event) =>
                                    updateConfig(
                                      "cases",
                                      cases.map((item, i) =>
                                        i === index
                                          ? {
                                              ...item,
                                              compare_input: event.target.value,
                                            }
                                          : item,
                                      ),
                                    )
                                  }
                                >
                                  <option value="">{t("noConnection")}</option>
                                  {Object.keys(selected.inputs).map((name) => (
                                    <option key={name}>{name}</option>
                                  ))}
                                </select>
                              </label>
                              {!condition.compare_input && (
                                <FlowJsonField
                                  label={t("value")}
                                  value={condition.value ?? null}
                                  onChange={(value) =>
                                    updateConfig(
                                      "cases",
                                      cases.map((item, i) =>
                                        i === index ? { ...item, value } : item,
                                      ),
                                    )
                                  }
                                  onValidityChange={onValidityChange}
                                />
                              )}
                            </>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            onPress={() =>
                              updateConfig(
                                "cases",
                                cases.filter((_, i) => i !== index),
                              )
                            }
                          >
                            {t("remove")}
                          </Button>
                        </div>
                      ),
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onPress={() => {
                        const cases = (selected.config.cases ??
                          []) as FlowCondition[];
                        updateConfig("cases", [
                          ...cases,
                          {
                            port: `branch_${cases.length + 1}`,
                            input: Object.keys(selected.inputs)[0] ?? "",
                            operator: "truthy",
                          },
                        ]);
                      }}
                    >
                      {t("addCondition")}
                    </Button>
                    <label className="grid gap-2 text-xs text-muted">
                      {t("elsePort")}
                      <input
                        className={FLOW_INPUT_CLASS}
                        value={String(selected.config.else_port ?? "else")}
                        onChange={(event) =>
                          updateConfig("else_port", event.target.value)
                        }
                      />
                    </label>
                  </section>
                )}
                {selected.type === "merge" && (
                  <label className="grid gap-2 text-xs text-muted">
                    {t("mergeMode")}
                    <select
                      className={FLOW_INPUT_CLASS}
                      value={String(selected.config.mode ?? "selected")}
                      onChange={(event) =>
                        updateConfig("mode", event.target.value)
                      }
                    >
                      {["selected", "all", "array"].map((mode) => (
                        <option key={mode} value={mode}>
                          {t(`mergeModes.${mode}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {selected.type === "foreach" && (
                  <section className="space-y-3 border-t border-border pt-4">
                    {["items_input", "item_input", "index_input"].map((key) => (
                      <label
                        key={key}
                        className="grid gap-2 text-xs text-muted"
                      >
                        {t(`foreachFields.${key}`)}
                        <input
                          className={FLOW_INPUT_CLASS}
                          value={String(selected.config[key] ?? "")}
                          onChange={(event) =>
                            updateConfig(key, event.target.value)
                          }
                        />
                      </label>
                    ))}
                    <label className="grid gap-2 text-xs text-muted">
                      {t("maxItems")}
                      <input
                        type="number"
                        min={1}
                        max={1000}
                        className={FLOW_INPUT_CLASS}
                        value={Number(selected.config.max_items ?? 100)}
                        onChange={(event) =>
                          updateConfig("max_items", Number(event.target.value))
                        }
                      />
                    </label>
                  </section>
                )}
                {["template", "compose", "merge", "foreach"].includes(
                  selected.type,
                ) && (
                  <label className="grid gap-2 text-xs text-muted">
                    {t("resultPort")}
                    <select
                      className={FLOW_INPUT_CLASS}
                      value={String(selected.config.output_port ?? "")}
                      onChange={(event) =>
                        updateConfig("output_port", event.target.value)
                      }
                    >
                      <option value="">{t("choose")}</option>
                      {Object.keys(selected.outputs).map((name) => (
                        <option key={name}>{name}</option>
                      ))}
                    </select>
                  </label>
                )}
                {selected.type === "compose" && (
                  <FlowJsonField
                    label={t("composeMapping")}
                    value={
                      selected.config.fields ??
                      Object.fromEntries(
                        Object.keys(selected.inputs).map((name) => [
                          name,
                          name,
                        ]),
                      )
                    }
                    onChange={(value) => updateConfig("fields", value)}
                    onValidityChange={onValidityChange}
                  />
                )}
                {selected.type === "output" && (
                  <section className="space-y-3 border-t border-border pt-4">
                    <h3 className="flex items-center gap-1 text-sm font-semibold">
                      {t("fieldMapping")}
                      <TooltipHint text={t("propertyHelp.mapping")} />
                    </h3>
                    {Object.keys(
                      outputSchema.properties ?? selected.outputs,
                    ).map((field) => (
                      <label
                        key={field}
                        className="grid gap-2 text-xs text-muted"
                      >
                        {field}
                        <select
                          className={FLOW_INPUT_CLASS}
                          value={String(
                            (
                              selected.config[resultMappingKey] as
                                | Record<string, unknown>
                                | undefined
                            )?.[field] ?? "",
                          )}
                          onChange={(event) =>
                            updateConfig(resultMappingKey, {
                              ...((selected.config[resultMappingKey] as Record<
                                string,
                                unknown
                              >) ?? {}),
                              [field]: event.target.value,
                            })
                          }
                        >
                          <option value="">{t("choose")}</option>
                          {Object.keys(selected.inputs).map((input) => (
                            <option key={input}>{input}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                    {outputSchema.properties && (
                      <FlowJsonField
                        label={t("parameterMapping")}
                        value={selected.config.parameter_fields ?? {}}
                        onChange={(value) =>
                          updateConfig("parameter_fields", value)
                        }
                        onValidityChange={onValidityChange}
                      />
                    )}
                  </section>
                )}
                {(selected.type === "subflow" ||
                  selected.type === "foreach") && (
                  <section className="space-y-3 border-t border-border pt-4">
                    <select
                      aria-label={t("types.subflow")}
                      className={FLOW_INPUT_CLASS}
                      value={String(selected.config.subflow_id ?? "")}
                      onChange={(event) =>
                        updateConfig("subflow_id", event.target.value)
                      }
                    >
                      <option value="">{t("choose")}</option>
                      {Object.keys(graph.subflows).map((id) => (
                        <option key={id}>{id}</option>
                      ))}
                    </select>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        isDisabled={
                          !graph.subflows[String(selected.config.subflow_id)]
                        }
                        onPress={() =>
                          onEnterSubflow(String(selected.config.subflow_id))
                        }
                      >
                        {t("enterSubflow")}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onPress={() => {
                          const id = `subflow_${crypto.randomUUID().slice(0, 8)}`;
                          const child: TaskFlow = {
                            ...graph,
                            id,
                            name: t("types.subflow"),
                            nodes: [
                              {
                                id: "input",
                                type: "input",
                                label: t("types.input"),
                                inputs: {},
                                outputs:
                                  selected.type === "foreach"
                                    ? {
                                        ...Object.fromEntries(
                                          Object.entries(
                                            selected.inputs,
                                          ).filter(
                                            ([name]) =>
                                              name !==
                                              selected.config.items_input,
                                          ),
                                        ),
                                        [String(
                                          selected.config.item_input ?? "item",
                                        )]:
                                          selected.inputs[
                                            String(
                                              selected.config.items_input ??
                                                "items",
                                            )
                                          ]?.items ?? {},
                                        [String(
                                          selected.config.index_input ??
                                            "index",
                                        )]: { type: "integer" },
                                      }
                                    : { ...selected.inputs },
                                values: {},
                                config: {},
                              },
                              {
                                id: "output",
                                type: "output",
                                label: t("types.output"),
                                inputs: {},
                                outputs: {},
                                values: {},
                                config: { output_fields: {} },
                              },
                            ],
                            edges: [],
                            control_edges: [],
                            subflows: {},
                            editor: {},
                          };
                          onChange({
                            ...graph,
                            subflows: { ...graph.subflows, [id]: child },
                            nodes: graph.nodes.map((node) =>
                              node.id === selected.id
                                ? {
                                    ...node,
                                    config: { ...node.config, subflow_id: id },
                                  }
                                : node,
                            ),
                          });
                        }}
                      >
                        {t("newSubflow")}
                      </Button>
                    </div>
                  </section>
                )}
                <section className="space-y-3 border-t border-border pt-4">
                  <h3 className="flex items-center gap-1 text-sm font-semibold">
                    {t("control")}
                    <TooltipHint text={t("propertyHelp.control")} />
                  </h3>
                  {graph.control_edges
                    .filter((edge) => edge.source === selected.id)
                    .map((edge) => (
                      <div key={edge.id} className="space-y-2">
                        <label className="grid gap-2 text-xs text-muted">
                          {t("controlPort")}
                          <select
                            className={FLOW_INPUT_CLASS}
                            value={edge.source_port}
                            onChange={(event) =>
                              onChange({
                                ...graph,
                                control_edges: graph.control_edges.map(
                                  (item) =>
                                    item.id === edge.id
                                      ? {
                                          ...item,
                                          source_port: event.target.value,
                                        }
                                      : item,
                                ),
                              })
                            }
                          >
                            {controlPorts(selected).map((port) => (
                              <option key={port}>{port}</option>
                            ))}
                          </select>
                        </label>
                        <label className="grid gap-2 text-xs text-muted">
                          {t("target")}
                          <select
                            className={FLOW_INPUT_CLASS}
                            value={edge.target}
                            onChange={(event) =>
                              onChange({
                                ...graph,
                                control_edges: graph.control_edges.map(
                                  (item) =>
                                    item.id === edge.id
                                      ? { ...item, target: event.target.value }
                                      : item,
                                ),
                              })
                            }
                          >
                            {graph.nodes
                              .filter(
                                (node) =>
                                  node.id !== selected.id &&
                                  node.type !== "input",
                              )
                              .map((node) => (
                                <option key={node.id} value={node.id}>
                                  {node.label}
                                </option>
                              ))}
                          </select>
                        </label>
                        <Button
                          size="sm"
                          variant="ghost"
                          onPress={() =>
                            onChange({
                              ...graph,
                              control_edges: graph.control_edges.filter(
                                (item) => item.id !== edge.id,
                              ),
                            })
                          }
                        >
                          {t("deleteEdge")}
                        </Button>
                      </div>
                    ))}
                  <Button
                    size="sm"
                    variant="outline"
                    isDisabled={controlPorts(selected).length === 0}
                    onPress={() => {
                      const target = graph.nodes.find(
                        (node) =>
                          node.id !== selected.id && node.type !== "input",
                      );
                      if (target)
                        onChange({
                          ...graph,
                          control_edges: [
                            ...graph.control_edges,
                            {
                              id: crypto.randomUUID(),
                              source: selected.id,
                              source_port: controlPorts(selected)[0],
                              target: target.id,
                            },
                          ],
                        });
                    }}
                  >
                    {t("addControl")}
                  </Button>
                </section>
                <details className="border-t border-border pt-3">
                  <summary className="min-h-11 cursor-pointer py-3 text-sm">
                    {t("configuration")}
                  </summary>
                  <FlowJsonField
                    label={t("configuration")}
                    value={selected.config}
                    onChange={(value) => {
                      if (
                        !isJsonObject(value) ||
                        (value.cases !== undefined &&
                          (!Array.isArray(value.cases) ||
                            !value.cases.every(
                              (condition) =>
                                isJsonObject(condition) &&
                                ["port", "input", "operator"].every(
                                  (key) => typeof condition[key] === "string",
                                ),
                            )))
                      )
                        throw new Error(t("invalidJsonObject"));
                      updateNode({ config: value });
                    }}
                    onValidityChange={onValidityChange}
                  />
                </details>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
