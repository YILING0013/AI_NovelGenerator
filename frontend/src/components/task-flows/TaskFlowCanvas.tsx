"use client";

import { TooltipHint } from "@/components/shared/TooltipHint";
import {
  FLOW_NODE_TYPES,
  type FlowNode,
  type FlowNodeType,
  type TaskFlow,
} from "@/types/taskFlow";
import { Button } from "@heroui/react";
import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
  type XYPosition,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";

type CanvasNode = Node<
  {
    node: FlowNode;
    typeLabel: string;
    executionLabel: string;
    controlPorts: string[];
    endpoint: boolean;
    previewState?: "pending" | "current" | "done" | "skipped" | "error";
    previewLabel?: string;
  },
  "taskNode"
>;

/** 功能：列出节点可连接的执行分支。Args: node 当前节点。Returns: 执行端口名称。 */
export function controlPorts(node: FlowNode): string[] {
  if (node.type === "output") return [];
  if (node.type !== "condition") return ["next"];
  return [
    ...((node.config.cases ?? []) as { port: string }[]).map(
      (item) => item.port,
    ),
    String(node.config.else_port ?? "else"),
  ];
}

const FlowCanvasNode = memo(function FlowCanvasNode({
  data,
  selected,
}: NodeProps<CanvasNode>) {
  return (
    <div
      className={`w-64 rounded-xl border px-4 py-3 text-foreground ${data.previewState === "current" ? "border-accent bg-selected ring-2 ring-accent" : `${data.previewState === "skipped" ? "border-dashed" : ""} bg-surface ${selected || data.endpoint ? "border-accent ring-2 ring-accent/30" : "border-border"}`}`}
      data-preview-state={data.previewState}
    >
      {data.node.type !== "input" && (
        <Handle
          type="target"
          position={Position.Top}
          id="exec"
          aria-label={data.executionLabel}
          className="!size-3 !border-border !bg-muted"
        />
      )}
      <div className="mb-3 min-w-0">
        <strong className="block truncate text-sm">{data.node.label}</strong>
        <span className="text-xs text-muted">{data.typeLabel}</span>
        {data.previewLabel && (
          <span className="mt-1 block text-xs font-medium text-muted">
            {data.previewLabel}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-5 text-xs">
        <div>
          {Object.keys(data.node.inputs).map((port) => (
            <div key={port} className="relative flex min-h-7 items-center">
              <Handle
                type="target"
                position={Position.Left}
                id={`in:${port}`}
                className="!size-2.5 !border-border !bg-accent"
                style={{ left: -20 }}
              />
              <span className="truncate">{port}</span>
            </div>
          ))}
        </div>
        <div>
          {Object.keys(data.node.outputs).map((port) => (
            <div
              key={port}
              className="relative flex min-h-7 items-center justify-end"
            >
              <span className="truncate">{port}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={`out:${port}`}
                className="!size-2.5 !border-border !bg-accent"
                style={{ right: -20 }}
              />
            </div>
          ))}
        </div>
      </div>
      {data.controlPorts.length > 0 && (
        <div className="mt-3 flex justify-around gap-2 border-t border-border pt-2 text-xs text-muted">
          {data.controlPorts.map((port) => (
            <div key={port} className="relative pb-1">
              {port}
              <Handle
                type="source"
                position={Position.Bottom}
                id={`exec:${port}`}
                aria-label={`${data.executionLabel}: ${port}`}
                className="!size-3 !border-border !bg-muted"
                style={{ bottom: -10 }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
const NODE_TYPES = { taskNode: FlowCanvasNode };
const FIT_OPTIONS = { padding: 0.18, maxZoom: 1 };

type CanvasMenu = {
  x: number;
  y: number;
  point: XYPosition;
  kind: "pane" | "node" | "edge";
  id?: string;
};

/** 功能：独立处理画布拖动和选择，拖动结束后才写回图。Args: graph 图定义及选中、放置回调。Returns: 保留视口的流程画布。 */
export const TaskFlowCanvas = memo(function TaskFlowCanvas({
  graph,
  selectedId,
  selectedEdgeId,
  placing,
  onSelectNode,
  onSelectEdge,
  onClearSelection,
  onPlace,
  onCancelPlace,
  onCopyNode,
  onRemoveNode,
  onRemoveEdge,
  onChange,
  onConnect,
  onOpenProperties,
  previewStates,
  previewEdgeIds,
}: {
  graph: TaskFlow;
  selectedId: string;
  selectedEdgeId: string;
  placing: FlowNodeType | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
  onClearSelection: () => void;
  onPlace: (type: FlowNodeType, position: XYPosition) => void;
  onCancelPlace: () => void;
  onCopyNode: (id: string) => void;
  onRemoveNode: (id: string) => void;
  onRemoveEdge: (id: string) => void;
  onChange: (graph: TaskFlow) => void;
  onConnect: (connection: Connection) => void;
  onOpenProperties: (id: string) => void;
  previewStates?: Record<
    string,
    "pending" | "current" | "done" | "skipped" | "error"
  >;
  previewEdgeIds?: string[];
}) {
  const t = useTranslations("taskFlows");
  const { resolvedTheme } = useTheme();
  const surface = useRef<HTMLDivElement>(null);
  const instance = useRef<ReactFlowInstance<CanvasNode>>(null);
  const dragging = useRef(false);
  const [moving, setMoving] = useState<Record<string, XYPosition>>({});
  const [measurements, setMeasurements] = useState<
    Record<string, { width: number; height: number }>
  >({});
  const [menu, setMenu] = useState<CanvasMenu | null>(null);
  const menuElement = useRef<HTMLDivElement>(null);
  const menuOrigin = useRef<HTMLElement | SVGElement | null>(null);
  const selectedEdge =
    graph.edges.find((edge) => edge.id === selectedEdgeId) ??
    graph.control_edges.find((edge) => edge.id === selectedEdgeId);
  const baseNodes = useMemo<CanvasNode[]>(
    () =>
      graph.nodes.map((node, index) => ({
        id: node.id,
        type: "taskNode",
        measured: measurements[node.id],
        position: graph.editor.positions?.[node.id] ?? {
          x: (index % 3) * 340,
          y: Math.floor(index / 3) * 280,
        },
        selected: node.id === selectedId,
        data: {
          node,
          typeLabel: t(`types.${node.type}`),
          executionLabel: t("control"),
          previewState: previewStates?.[node.id],
          previewLabel: previewStates?.[node.id]
            ? t(`preview.${previewStates[node.id]}`)
            : undefined,
          controlPorts: controlPorts(node),
          endpoint:
            !!selectedEdge &&
            (node.id === selectedEdge.source ||
              node.id === selectedEdge.target),
        },
      })),
    [
      graph.nodes,
      graph.editor.positions,
      selectedId,
      selectedEdge,
      measurements,
      previewStates,
      t,
    ],
  );
  // 每帧只替换正在移动的节点；侧栏、撤销记录和 IndexedDB 不参与拖动。
  const nodes = useMemo(
    () =>
      baseNodes.map((node) =>
        moving[node.id] ? { ...node, position: moving[node.id] } : node,
      ),
    [baseNodes, moving],
  );
  const edges = useMemo<Edge[]>(
    () =>
      [
        ...graph.edges.map((edge) => ({
          ...edge,
          sourceHandle: `out:${edge.source_port}`,
          targetHandle: `in:${edge.target_port}`,
          label: edge.source_path?.join("."),
          execution: false,
        })),
        ...graph.control_edges.map((edge) => ({
          ...edge,
          sourceHandle: `exec:${edge.source_port}`,
          targetHandle: "exec",
          label: edge.source_port,
          execution: true,
        })),
      ].map((edge) => {
        const selected = edge.id === selectedEdgeId;
        const dimmed = Boolean(selectedEdgeId) && !selected;
        const traced = previewEdgeIds?.includes(edge.id);
        // 手动选线优先于执行轨迹，避免其他经过的连线抢走注意力。
        const active = selectedEdgeId
          ? selected
          : traced ||
            (!!selectedId &&
              (edge.source === selectedId || edge.target === selectedId));
        return {
          ...edge,
          selected,
          ariaLabel: `${t(edge.execution ? "control" : "canvasHelp.dataEdge")}: ${graph.nodes.find((node) => node.id === edge.source)?.label ?? edge.source}.${edge.source_port} → ${graph.nodes.find((node) => node.id === edge.target)?.label ?? edge.target}${previewEdgeIds?.includes(edge.id) ? ` · ${t("preview.done")}` : ""}`,
          interactionWidth: 24,
          zIndex: selected ? 3 : active ? 2 : 0,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: active ? "var(--color-accent)" : "var(--color-muted)",
          },
          style: {
            stroke: active ? "var(--color-accent)" : "var(--color-muted)",
            strokeWidth: dimmed
              ? 1.5
              : selected || traced
                ? 4
                : active
                  ? 3
                  : 1.5,
            opacity: dimmed ? 0.25 : 1,
            ...(edge.execution ? { strokeDasharray: "6 4" } : {}),
          },
          labelStyle: {
            fill: "var(--color-foreground)",
            fontWeight: active ? 700 : 400,
            opacity: dimmed ? 0.25 : 1,
          },
          labelBgStyle: {
            fill: "var(--color-surface)",
            opacity: dimmed ? 0.25 : 1,
          },
        };
      }),
    [
      graph.edges,
      graph.control_edges,
      graph.nodes,
      selectedId,
      selectedEdgeId,
      previewEdgeIds,
      t,
    ],
  );
  const onInit = useCallback((value: ReactFlowInstance<CanvasNode>) => {
    instance.current = value;
  }, []);
  const onNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      const positions: Record<string, XYPosition> = {};
      // React Flow 在节点对象变化后重新读取 measured，遗漏它会让拖动暂时丢失节点尺寸。
      // 尺寸只用于本地画布，不进入图定义、撤销或草稿持久化。
      const measuredChanges = changes.filter(
        (change) => change.type === "dimensions",
      );
      if (measuredChanges.length)
        setMeasurements((previous) => {
          let next = previous;
          for (const change of measuredChanges) {
            if (!change.dimensions) continue;
            const current = previous[change.id];
            if (
              current?.width === change.dimensions.width &&
              current?.height === change.dimensions.height
            )
              continue;
            if (next === previous) next = { ...previous };
            next[change.id] = change.dimensions;
          }
          return next;
        });
      for (const change of changes) {
        if (change.type === "position" && change.position)
          positions[change.id] = change.position;
        if (change.type === "select" && change.selected)
          onSelectNode(change.id);
      }
      if (!Object.keys(positions).length) return;
      if (dragging.current)
        setMoving((previous) => ({ ...previous, ...positions }));
      else
        onChange({
          ...graph,
          editor: {
            ...graph.editor,
            positions: { ...graph.editor.positions, ...positions },
          },
        });
    },
    [graph, onChange, onSelectNode],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes)
        if (change.type === "select" && change.selected)
          onSelectEdge(change.id);
    },
    [onSelectEdge],
  );
  const onDragStart = useCallback(() => {
    dragging.current = true;
    setMenu(null);
  }, []);
  const onDragStop = useCallback(
    (_: unknown, node: CanvasNode, movedNodes: CanvasNode[]) => {
      const positions = { ...graph.editor.positions };
      let changed = false;
      for (const moved of movedNodes.length ? movedNodes : [node]) {
        const original = baseNodes.find(
          (item) => item.id === moved.id,
        )?.position;
        if (
          original?.x !== moved.position.x ||
          original?.y !== moved.position.y
        ) {
          positions[moved.id] = moved.position;
          changed = true;
        }
      }
      dragging.current = false;
      setMoving({});
      if (changed)
        onChange({ ...graph, editor: { ...graph.editor, positions } });
    },
    [baseNodes, graph, onChange],
  );
  const closeMenu = useCallback((restore = false) => {
    setMenu(null);
    if (restore)
      (menuOrigin.current?.isConnected
        ? menuOrigin.current
        : surface.current
      )?.focus();
  }, []);
  useEffect(() => {
    if (placing) surface.current?.focus();
  }, [placing]);
  useEffect(() => {
    if (!menu) return;
    menuElement.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus();
    const outside = (event: PointerEvent) => {
      if (!menuElement.current?.contains(event.target as globalThis.Node))
        closeMenu();
    };
    window.addEventListener("pointerdown", outside);
    return () => window.removeEventListener("pointerdown", outside);
  }, [menu, closeMenu]);
  const openMenu = useCallback(
    (
      clientX: number,
      clientY: number,
      kind: CanvasMenu["kind"],
      id?: string,
    ) => {
      const bounds = surface.current!.getBoundingClientRect();
      menuOrigin.current = document.activeElement as HTMLElement | SVGElement;
      setMenu({
        kind,
        id,
        x: Math.max(4, Math.min(clientX - bounds.left, bounds.width - 228)),
        y: Math.max(4, Math.min(clientY - bounds.top, bounds.height - 280)),
        point: instance.current!.screenToFlowPosition({
          x: clientX,
          y: clientY,
        }),
      });
    },
    [],
  );
  const locateNode = useCallback(
    (id: string) => {
      onSelectNode(id);
      void instance.current?.fitView({
        nodes: [{ id }],
        padding: 0.8,
        maxZoom: 1,
      });
      surface.current?.focus();
    },
    [onSelectNode],
  );
  const onPaneClick = useCallback(
    (event: MouseEvent) => {
      closeMenu();
      if (placing)
        onPlace(
          placing,
          instance.current!.screenToFlowPosition({
            x: event.clientX,
            y: event.clientY,
          }),
        );
      else onClearSelection();
    },
    [closeMenu, placing, onPlace, onClearSelection],
  );
  const onNodeClick = useCallback(
    (_: MouseEvent, node: CanvasNode) => {
      closeMenu();
      onSelectNode(node.id);
    },
    [closeMenu, onSelectNode],
  );
  const onEdgeClick = useCallback(
    (_: MouseEvent, edge: Edge) => {
      closeMenu();
      onSelectEdge(edge.id);
    },
    [closeMenu, onSelectEdge],
  );
  const onNodeContextMenu = useCallback(
    (event: MouseEvent, node: CanvasNode) => {
      event.preventDefault();
      event.stopPropagation();
      onSelectNode(node.id);
      openMenu(event.clientX, event.clientY, "node", node.id);
    },
    [openMenu, onSelectNode],
  );
  const onEdgeContextMenu = useCallback(
    (event: MouseEvent, edge: Edge) => {
      event.preventDefault();
      event.stopPropagation();
      onSelectEdge(edge.id);
      openMenu(event.clientX, event.clientY, "edge", edge.id);
    },
    [openMenu, onSelectEdge],
  );
  const onPaneContextMenu = useCallback(
    (event: MouseEvent | globalThis.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      openMenu(event.clientX, event.clientY, "pane");
    },
    [openMenu],
  );
  const edgeSource =
    selectedEdge &&
    `${graph.nodes.find((node) => node.id === selectedEdge.source)?.label ?? selectedEdge.source}.${[selectedEdge.source_port, ...(graph.edges.find((edge) => edge.id === selectedEdge.id)?.source_path ?? [])].join(".")}`;
  const edgeTarget =
    selectedEdge &&
    `${graph.nodes.find((node) => node.id === selectedEdge.target)?.label ?? selectedEdge.target}.${"target_port" in selectedEdge ? selectedEdge.target_port : t("control")}`;
  const menuNode = graph.nodes.find((node) => node.id === menu?.id);
  const menuEdge =
    graph.edges.find((edge) => edge.id === menu?.id) ??
    graph.control_edges.find((edge) => edge.id === menu?.id);

  return (
    <div
      ref={surface}
      className={`task-flow-canvas relative h-full min-h-0 min-w-0 flex-1 bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${placing ? "cursor-crosshair" : ""}`}
      role="region"
      aria-label={t("canvas")}
      tabIndex={0}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(event) => {
        event.preventDefault();
        const type = event.dataTransfer.getData(
          "application/task-flow-node",
        ) as FlowNodeType;
        if (FLOW_NODE_TYPES.includes(type))
          onPlace(
            type,
            instance.current!.screenToFlowPosition({
              x: event.clientX,
              y: event.clientY,
            }),
          );
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          closeMenu(Boolean(menu));
          onCancelPlace();
          onClearSelection();
          return;
        }
        if (
          event.target instanceof Element &&
          event.target.closest(
            "input, textarea, select, [contenteditable='true'], [role='menu']",
          )
        )
          return;
        if (
          event.key === "ContextMenu" ||
          (event.shiftKey && event.key === "F10")
        ) {
          event.preventDefault();
          event.stopPropagation();
          const target = event.target as Element;
          const nodeId = target
            .closest(".react-flow__node")
            ?.getAttribute("data-id");
          const edgeId = target
            .closest(".react-flow__edge")
            ?.getAttribute("data-id");
          const bounds = target.getBoundingClientRect();
          openMenu(
            bounds.left + bounds.width / 2,
            bounds.top + Math.min(bounds.height / 2, 100),
            nodeId ? "node" : edgeId ? "edge" : "pane",
            nodeId ?? edgeId ?? undefined,
          );
        }
        if (
          event.target === surface.current &&
          placing &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          const bounds = surface.current.getBoundingClientRect();
          onPlace(
            placing,
            instance.current!.screenToFlowPosition({
              x: bounds.left + bounds.width / 2,
              y: bounds.top + bounds.height / 2,
            }),
          );
        }
        if (event.key === "Delete" || event.key === "Backspace") {
          const target = event.target as Element;
          const nodeId = target
            .closest(".react-flow__node")
            ?.getAttribute("data-id");
          const edgeId = target
            .closest(".react-flow__edge")
            ?.getAttribute("data-id");
          if (target !== surface.current && !nodeId && !edgeId) return;
          event.preventDefault();
          if (edgeId || selectedEdgeId) onRemoveEdge(edgeId || selectedEdgeId);
          else if (nodeId || selectedId) onRemoveNode(nodeId || selectedId);
        }
      }}
    >
      <ReactFlow<CanvasNode>
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onInit={onInit}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStart={onDragStart}
        onNodeDragStop={onDragStop}
        onNodeContextMenu={onNodeContextMenu}
        onEdgeContextMenu={onEdgeContextMenu}
        onPaneContextMenu={onPaneContextMenu}
        onConnect={onConnect}
        fitView
        fitViewOptions={FIT_OPTIONS}
        minZoom={0.1}
        maxZoom={2}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        deleteKeyCode={null}
      >
        <Background color="var(--color-border)" gap={24} size={1} />
      </ReactFlow>
      <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-1 rounded-lg border border-border bg-surface-raised p-1">
        <TooltipHint text={t("canvasHelp.zoomIn")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("canvasHelp.zoomIn")}
            onPress={() => {
              void instance.current?.zoomIn();
            }}
          >
            +
          </Button>
        </TooltipHint>
        <TooltipHint text={t("canvasHelp.zoomOut")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("canvasHelp.zoomOut")}
            onPress={() => {
              void instance.current?.zoomOut();
            }}
          >
            −
          </Button>
        </TooltipHint>
        <TooltipHint text={t("canvasHelp.fitView")}>
          <Button
            size="sm"
            variant="ghost"
            aria-label={t("canvasHelp.fitView")}
            onPress={() => {
              void instance.current?.fitView(FIT_OPTIONS);
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
              <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />
            </svg>
          </Button>
        </TooltipHint>
      </div>
      <div className="absolute right-3 top-3 z-10 flex items-center gap-2 rounded-lg border border-border bg-surface-raised px-2 py-1 text-xs">
        <span
          className="inline-block w-5 border-t-2 border-muted"
          aria-hidden="true"
        />
        {t("canvasHelp.dataEdge")}
        <span
          className="inline-block w-5 border-t-2 border-dashed border-muted"
          aria-hidden="true"
        />
        {t("control")}
        <TooltipHint
          text={`${t("canvasHelp.navigation")} ${t("canvasHelp.selection")}`}
        />
      </div>
      {placing && (
        <div
          className="absolute inset-x-3 top-14 z-10 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent bg-surface-raised px-3 py-2 text-sm"
          role="status"
        >
          <span>
            {t("canvasHelp.placing", { type: t(`types.${placing}`) })}
          </span>
          <Button size="sm" variant="ghost" onPress={onCancelPlace}>
            {t("canvasHelp.cancelPlacement")}
          </Button>
        </div>
      )}
      {selectedEdge && (
        <section
          className="absolute bottom-3 right-3 z-10 max-w-[calc(100%-4.5rem)] rounded-xl border-2 border-accent bg-surface-raised p-3 shadow-md"
          aria-label={t("canvasHelp.selectedEdge")}
        >
          <div className="mb-1 flex items-center justify-between gap-2 text-xs font-semibold">
            <span>{t("canvasHelp.selectedEdge")}</span>
            <Button
              size="sm"
              variant="ghost"
              aria-label={t("canvasHelp.clearSelection")}
              onPress={onClearSelection}
            >
              ×
            </Button>
          </div>
          <div className="break-all text-xs leading-5">
            <span>{edgeSource}</span>
            <span aria-hidden="true"> → </span>
            <span>{edgeTarget}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Button
              size="sm"
              variant="ghost"
              onPress={() => locateNode(selectedEdge.source)}
            >
              {t("canvasHelp.sourceNode")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onPress={() => locateNode(selectedEdge.target)}
            >
              {t("canvasHelp.targetNode")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onPress={() => onRemoveEdge(selectedEdge.id)}
            >
              {t("deleteEdge")}
            </Button>
          </div>
        </section>
      )}
      {menu && (
        <div
          ref={menuElement}
          role="menu"
          aria-label={t("canvasHelp.menu")}
          className="absolute z-50 w-56 max-w-[calc(100%-8px)] rounded-xl border border-border bg-surface-raised p-1 shadow-lg"
          style={{ left: menu.x, top: menu.y }}
          onKeyDown={(event) => {
            const items = Array.from(
              menuElement.current!.querySelectorAll<HTMLButtonElement>(
                "button:not(:disabled)",
              ),
            );
            const index = items.indexOf(
              document.activeElement as HTMLButtonElement,
            );
            if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
              event.preventDefault();
              items[
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? items.length - 1
                    : (index +
                        (event.key === "ArrowDown" ? 1 : -1) +
                        items.length) %
                      items.length
              ]?.focus();
            } else if (event.key === "Tab") closeMenu();
          }}
        >
          {menu.kind === "pane" && (
            <>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  void instance.current?.fitView(FIT_OPTIONS);
                  closeMenu(true);
                }}
              >
                {t("canvasHelp.fitView")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  void instance.current?.zoomTo(1);
                  closeMenu(true);
                }}
              >
                {t("canvasHelp.actualSize")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!placing}
                onClick={() => {
                  if (placing) onPlace(placing, menu.point);
                  closeMenu(true);
                }}
              >
                {t("canvasHelp.placeHere")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  onCancelPlace();
                  onClearSelection();
                  closeMenu(true);
                }}
              >
                {t("canvasHelp.clearSelection")}
              </button>
            </>
          )}
          {menuNode && (
            <>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  onOpenProperties(menuNode.id);
                  closeMenu();
                }}
              >
                {t("properties")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  locateNode(menuNode.id);
                  closeMenu();
                }}
              >
                {t("canvasHelp.focusNode")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={
                  menuNode.type === "input" || menuNode.type === "output"
                }
                onClick={() => {
                  onCopyNode(menuNode.id);
                  closeMenu(true);
                }}
              >
                {t("copyNode")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  onRemoveNode(menuNode.id);
                  closeMenu(true);
                }}
              >
                {t("deleteNode")}
              </button>
            </>
          )}
          {menuEdge && (
            <>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  locateNode(menuEdge.source);
                  closeMenu();
                }}
              >
                {t("canvasHelp.sourceNode")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  locateNode(menuEdge.target);
                  closeMenu();
                }}
              >
                {t("canvasHelp.targetNode")}
              </button>
              <button
                type="button"
                role="menuitem"
                className="min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => {
                  onRemoveEdge(menuEdge.id);
                  closeMenu(true);
                }}
              >
                {t("deleteEdge")}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
});
