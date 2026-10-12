"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { drag, type D3DragEvent } from "d3-drag";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import type { RelationshipGraphEdgeV1, RelationshipGraphNodeV1 } from "./graphTypes";

interface LayoutNode extends SimulationNodeDatum {
  id: string;
  kind: RelationshipGraphNodeV1["kind"];
}

interface LayoutEdge extends SimulationLinkDatum<LayoutNode> {
  id: string;
  source: string | LayoutNode;
  target: string | LayoutNode;
  curveOffset: number;
  normalSign: 1 | -1;
}

interface CachedPosition {
  x: number;
  y: number;
  fx: number | null;
  fy: number | null;
}

export interface ForceGraphViewportHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitAll: () => void;
  resetLayout: () => void;
  reheat: () => void;
  focusNode: (nodeId: string) => void;
}

export interface ForceGraphViewportProps {
  nodes: RelationshipGraphNodeV1[];
  edges: RelationshipGraphEdgeV1[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  matchedNodeIds: Set<string>;
  hasSearchQuery: boolean;
  ariaLabel: string;
  emptyLabel: string;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string | null) => void;
}

function createCurvedEdges(edges: RelationshipGraphEdgeV1[]): LayoutEdge[] {
  const grouped = new Map<
    string,
    {
      canonicalSource: string;
      edges: RelationshipGraphEdgeV1[];
    }
  >();
  for (const edge of edges) {
    const [canonicalSource, canonicalTarget] = [edge.source, edge.target].sort();
    const key = `${canonicalSource}\u0000${canonicalTarget}`;
    const group = grouped.get(key) ?? { canonicalSource, edges: [] };
    group.edges.push(edge);
    grouped.set(key, group);
  }

  const curvedById = new Map<string, LayoutEdge>();
  for (const group of grouped.values()) {
    // 统一按规范端点方向和业务 ID 排序，保证刷新及反向边的曲线侧向稳定。
    const siblings = group.edges.sort((left, right) => {
      const leftDirection = left.source === group.canonicalSource ? 0 : 1;
      const rightDirection = right.source === group.canonicalSource ? 0 : 1;
      return leftDirection - rightDirection || left.id.localeCompare(right.id);
    });
    siblings.forEach((edge, index) => {
      curvedById.set(edge.id, {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        curveOffset: (index - (siblings.length - 1) / 2) * 22,
        normalSign: edge.source === group.canonicalSource ? 1 : -1,
      });
    });
  }
  return edges.map((edge) => curvedById.get(edge.id)!);
}

function edgePath(edge: LayoutEdge): string {
  if (typeof edge.source === "string" || typeof edge.target === "string") return "";
  const sourceX = edge.source.x ?? 0;
  const sourceY = edge.source.y ?? 0;
  const targetX = edge.target.x ?? 0;
  const targetY = edge.target.y ?? 0;
  const deltaX = targetX - sourceX;
  const deltaY = targetY - sourceY;
  const length = Math.max(Math.hypot(deltaX, deltaY), 1);
  const targetPadding = edge.target.kind === "faction" ? 54 : 21;
  const endX = targetX - (deltaX / length) * targetPadding;
  const endY = targetY - (deltaY / length) * targetPadding;
  const canonicalOffset = edge.curveOffset * edge.normalSign;
  const middleX = (sourceX + targetX) / 2 - (deltaY / length) * canonicalOffset;
  const middleY = (sourceY + targetY) / 2 + (deltaX / length) * canonicalOffset;
  return `M ${sourceX} ${sourceY} Q ${middleX} ${middleY} ${endX} ${endY}`;
}

function edgeDashArray(kind: RelationshipGraphEdgeV1["kind"]): string | undefined {
  if (kind === "faction_relation") return "8 4";
  if (kind === "membership") return "2 5";
  if (kind === "faction_hierarchy") return "10 4 2 4";
  return undefined;
}

function edgeWidth(edge: RelationshipGraphEdgeV1): number {
  if (edge.intensity === null) return 1.4;
  return 1.25 + Math.min(Math.max(edge.intensity, 0), 10) * 0.14;
}

/**
 * 功能：渲染由 React 管理 SVG 结构、D3 管理可变布局副本的势力与角色力导向图。
 * Args:
 *   props: 图谱节点、边、搜索/节点与连线选择状态、无障碍标签及选择回调。
 *   ref: 提供缩放、适配、重排和节点聚焦命令的视口句柄。
 * Returns:
 *   支持平移、缩放、拖拽固定和多重边曲线的 SVG 图谱区域。
 */
const ForceGraphViewport = forwardRef<ForceGraphViewportHandle, ForceGraphViewportProps>(
  function ForceGraphViewport(
    {
      nodes,
      edges,
      selectedNodeId,
      selectedEdgeId,
      matchedNodeIds,
      hasSearchQuery,
      ariaLabel,
      emptyLabel,
      onSelectNode,
      onSelectEdge,
    },
    ref,
  ) {
    const markerId = `entity-graph-arrow-${useId().replace(/:/g, "")}`;
    const containerRef = useRef<HTMLDivElement | null>(null);
    const svgRef = useRef<SVGSVGElement | null>(null);
    const graphGroupRef = useRef<SVGGElement | null>(null);
    const nodeElementsRef = useRef(new Map<string, SVGGElement>());
    const edgeElementsRef = useRef(new Map<string, SVGPathElement>());
    const edgeHitElementsRef = useRef(new Map<string, SVGPathElement>());
    const positionsRef = useRef(new Map<string, CachedPosition>());
    const layoutNodesRef = useRef(new Map<string, LayoutNode>());
    const layoutEdgesRef = useRef(new Map<string, LayoutEdge>());
    const simulationRef = useRef<Simulation<LayoutNode, LayoutEdge> | null>(null);
    const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
    const zoomTransformRef = useRef<ZoomTransform>(zoomIdentity);
    const rafRef = useRef<number | null>(null);
    const autoFitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const hasAutoFittedRef = useRef(false);
    const [size, setSize] = useState({ width: 800, height: 520 });
    const [hasMeasuredSize, setHasMeasuredSize] = useState(false);
    const [layoutRevision, setLayoutRevision] = useState(0);
    const [reducedMotion, setReducedMotion] = useState(false);

    const topologyKey = useMemo(
      () =>
        `${nodes.map((node) => node.id).sort().join(",")}::${edges
          .map((edge) => `${edge.id}:${edge.kind}:${edge.source}:${edge.target}`)
          .sort()
          .join(",")}`,
      [edges, nodes],
    );

    const adjacentNodeIds = useMemo(() => {
      const adjacent = new Set<string>();
      if (!selectedNodeId) return adjacent;
      adjacent.add(selectedNodeId);
      for (const edge of edges) {
        if (edge.source === selectedNodeId) adjacent.add(edge.target);
        if (edge.target === selectedNodeId) adjacent.add(edge.source);
      }
      return adjacent;
    }, [edges, selectedNodeId]);

    const selectedEdgeNodeIds = useMemo(() => {
      const endpoints = new Set<string>();
      const selectedEdge = selectedEdgeId
        ? edges.find((edge) => edge.id === selectedEdgeId)
        : undefined;
      if (selectedEdge) {
        endpoints.add(selectedEdge.source);
        endpoints.add(selectedEdge.target);
      }
      return endpoints;
    }, [edges, selectedEdgeId]);

    const drawFrame = useCallback(() => {
      for (const [id, node] of layoutNodesRef.current) {
        const x = node.x ?? 0;
        const y = node.y ?? 0;
        nodeElementsRef.current.get(id)?.setAttribute("transform", `translate(${x} ${y})`);
        positionsRef.current.set(id, {
          x,
          y,
          fx: node.fx ?? null,
          fy: node.fy ?? null,
        });
      }
      for (const [id, edge] of layoutEdgesRef.current) {
        const path = edgePath(edge);
        edgeElementsRef.current.get(id)?.setAttribute("d", path);
        edgeHitElementsRef.current.get(id)?.setAttribute("d", path);
      }
    }, []);

    const scheduleDraw = useCallback(() => {
      if (rafRef.current !== null) return;
      rafRef.current = window.requestAnimationFrame(() => {
        rafRef.current = null;
        drawFrame();
      });
    }, [drawFrame]);

    const settleSimulation = useCallback(
      (simulation: Simulation<LayoutNode, LayoutEdge>, alpha: number, ticks: number) => {
        // reduced-motion 交互只执行有限同步 tick，并确保内部计时器保持停止。
        simulation.alphaTarget(0).alpha(alpha).stop();
        simulation.tick(ticks);
        drawFrame();
      },
      [drawFrame],
    );

    const applyTransform = useCallback((transform: ZoomTransform) => {
      const svg = svgRef.current;
      const behavior = zoomRef.current;
      if (!svg || !behavior) return;
      select(svg).call(behavior.transform, transform);
    }, []);

    const fitAll = useCallback(() => {
      if (layoutNodesRef.current.size === 0) return;
      const layoutNodes = [...layoutNodesRef.current.values()];
      const xs = layoutNodes.map((node) => node.x ?? 0);
      const ys = layoutNodes.map((node) => node.y ?? 0);
      const minX = Math.min(...xs) - 70;
      const maxX = Math.max(...xs) + 70;
      const minY = Math.min(...ys) - 55;
      const maxY = Math.max(...ys) + 55;
      const contentWidth = Math.max(maxX - minX, 1);
      const contentHeight = Math.max(maxY - minY, 1);
      const scale = Math.min(2, Math.max(0.2, 0.9 / Math.max(contentWidth / size.width, contentHeight / size.height)));
      const translateX = size.width / 2 - ((minX + maxX) / 2) * scale;
      const translateY = size.height / 2 - ((minY + maxY) / 2) * scale;
      applyTransform(zoomIdentity.translate(translateX, translateY).scale(scale));
    }, [applyTransform, size.height, size.width]);

    useImperativeHandle(
      ref,
      () => ({
        zoomIn: () => {
          if (svgRef.current && zoomRef.current) select(svgRef.current).call(zoomRef.current.scaleBy, 1.25);
        },
        zoomOut: () => {
          if (svgRef.current && zoomRef.current) select(svgRef.current).call(zoomRef.current.scaleBy, 0.8);
        },
        fitAll,
        resetLayout: () => {
          positionsRef.current.clear();
          hasAutoFittedRef.current = false;
          setLayoutRevision((value) => value + 1);
        },
        reheat: () => {
          const simulation = simulationRef.current;
          if (!simulation) return;
          if (reducedMotion) settleSimulation(simulation, 0.7, 80);
          else simulation.alpha(0.7).restart();
        },
        focusNode: (nodeId: string) => {
          const node = layoutNodesRef.current.get(nodeId);
          if (!node) return;
          const scale = Math.max(1.35, zoomTransformRef.current.k);
          applyTransform(
            zoomIdentity.translate(size.width / 2, size.height / 2).scale(scale).translate(-(node.x ?? 0), -(node.y ?? 0)),
          );
        },
      }),
      [applyTransform, fitAll, reducedMotion, settleSimulation, size.height, size.width],
    );

    useEffect(() => {
      const media = window.matchMedia("(prefers-reduced-motion: reduce)");
      const update = () => setReducedMotion(media.matches);
      update();
      media.addEventListener("change", update);
      return () => media.removeEventListener("change", update);
    }, []);

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      const updateSize = () => {
        const rect = container.getBoundingClientRect();
        // 折叠布局在首次测量时可能为零，保留上一次有效尺寸避免仿真坍缩。
        if (rect.width > 0 && rect.height > 0) {
          setHasMeasuredSize(true);
          setSize((previous) =>
            previous.width === rect.width && previous.height === rect.height
              ? previous
              : { width: rect.width, height: rect.height },
          );
        }
      };
      updateSize();
      const observer = new ResizeObserver(updateSize);
      observer.observe(container);
      return () => observer.disconnect();
    }, []);

    const hasNodes = nodes.length > 0;

    useEffect(() => {
      const svg = svgRef.current;
      const group = graphGroupRef.current;
      if (!svg || !group) return;
      const behavior = zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.15, 4])
        .duration(reducedMotion ? 0 : 250)
        // 容忍轻微手抖；真正的平移会由 D3 抑制后续 click，纯点击才会选择连线。
        .clickDistance(5)
        .on("zoom", (event) => {
          zoomTransformRef.current = event.transform;
          group.setAttribute("transform", event.transform.toString());
        });
      zoomRef.current = behavior;
      select(svg).call(behavior);
      // 节点双击用于解除固定；移除 D3 会截断冒泡的默认双击缩放，避免两种语义冲突。
      select(svg).on("dblclick.zoom", null);
      return () => {
        select(svg).on(".zoom", null);
        if (zoomRef.current === behavior) zoomRef.current = null;
      };
    }, [hasNodes, reducedMotion]);

    useEffect(() => {
      if (!selectedEdgeId) return;
      const handleEscape = (event: globalThis.KeyboardEvent) => {
        if (event.key === "Escape") onSelectEdge(null);
      };
      window.addEventListener("keydown", handleEscape);
      return () => window.removeEventListener("keydown", handleEscape);
    }, [onSelectEdge, selectedEdgeId]);

    useEffect(() => {
      if (!hasMeasuredSize || nodes.length === 0) {
        layoutNodesRef.current.clear();
        layoutEdgesRef.current.clear();
        return;
      }
      const previousPositions = positionsRef.current;
      const orderedNodes = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
      const layoutNodes: LayoutNode[] = orderedNodes.map((node, index) => {
        const cached = previousPositions.get(node.id);
        const angle = index * 2.399963229728653;
        const radius = 38 * Math.sqrt(index + 1);
        return {
          id: node.id,
          kind: node.kind,
          x: cached?.x ?? size.width / 2 + Math.cos(angle) * radius,
          y: cached?.y ?? size.height / 2 + Math.sin(angle) * radius,
          fx: cached?.fx ?? null,
          fy: cached?.fy ?? null,
        };
      });
      const layoutEdges = createCurvedEdges(edges);
      const domainEdgeById = new Map(edges.map((edge) => [edge.id, edge]));
      layoutNodesRef.current = new Map(layoutNodes.map((node) => [node.id, node]));
      layoutEdgesRef.current = new Map(layoutEdges.map((edge) => [edge.id, edge]));

      const simulation = forceSimulation<LayoutNode>(layoutNodes)
        .force("charge", forceManyBody<LayoutNode>().strength(-310).distanceMax(800))
        .force(
          "link",
          forceLink<LayoutNode, LayoutEdge>(layoutEdges)
            .id((node) => node.id)
            .distance((edge) => {
              const domainEdge = domainEdgeById.get(edge.id);
              return domainEdge?.kind === "membership" ? 105 : 135;
            })
            .strength(0.16),
        )
        .force("center", forceCenter(size.width / 2, size.height / 2))
        // 轻微的轴向回拉让孤立节点仍处于可读范围，同时不破坏关系簇的自然展开。
        .force("x", forceX<LayoutNode>(size.width / 2).strength(0.035))
        .force("y", forceY<LayoutNode>(size.height / 2).strength(0.035))
        .force("collision", forceCollide<LayoutNode>().radius((node) => (node.kind === "faction" ? 62 : 34)).iterations(2))
        .alphaDecay(0.045)
        .velocityDecay(0.42)
        .on("tick", scheduleDraw)
        .on("end", scheduleDraw);
      simulationRef.current = simulation;

      if (reducedMotion) {
        // 减少动态效果时同步执行有限静态 tick，只绘制最终结果，不启动持续计时器。
        settleSimulation(simulation, 1, 180);
      }

      const nodeSelection = select(graphGroupRef.current)
        .selectAll<SVGGElement, unknown>("[data-graph-node]")
        .call(
          drag<SVGGElement, unknown>()
            .on("start", function handleStart(event: D3DragEvent<SVGGElement, unknown, unknown>) {
              const id = this.dataset.nodeId;
              const node = id ? layoutNodesRef.current.get(id) : undefined;
              if (!node) return;
              if (!event.active && !reducedMotion) simulation.alphaTarget(0.22).restart();
              node.fx = node.x;
              node.fy = node.y;
            })
            .on("drag", function handleDrag(event: D3DragEvent<SVGGElement, unknown, unknown>) {
              const id = this.dataset.nodeId;
              const node = id ? layoutNodesRef.current.get(id) : undefined;
              if (!node) return;
              // d3-drag 已按父级 SVG 逆变换给出图坐标增量，这里不得再次除以缩放倍率。
              node.fx = (node.fx ?? node.x ?? 0) + event.dx;
              node.fy = (node.fy ?? node.y ?? 0) + event.dy;
              if (reducedMotion) drawFrame();
            })
            .on("end", function handleEnd(event: D3DragEvent<SVGGElement, unknown, unknown>) {
              if (!event.active && !reducedMotion) simulation.alphaTarget(0);
              scheduleDraw();
            }),
        );

      drawFrame();
      if (!hasAutoFittedRef.current && layoutNodes.length > 0) {
        autoFitTimerRef.current = setTimeout(() => {
          autoFitTimerRef.current = null;
          hasAutoFittedRef.current = true;
          fitAll();
        }, reducedMotion ? 0 : 420);
      }

      return () => {
        simulation.stop();
        simulation.on("tick", null).on("end", null);
        nodeSelection.on(".drag", null);
        if (simulationRef.current === simulation) simulationRef.current = null;
        if (rafRef.current !== null) {
          window.cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
        if (autoFitTimerRef.current !== null) {
          clearTimeout(autoFitTimerRef.current);
          autoFitTimerRef.current = null;
        }
      };
      // topologyKey 明确限定仿真只在拓扑、尺寸、动态偏好或显式重排变化时重建。
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [drawFrame, fitAll, hasMeasuredSize, layoutRevision, reducedMotion, scheduleDraw, settleSimulation, size.height, size.width, topologyKey]);

    return (
      <div
        ref={containerRef}
        role="region"
        aria-label={ariaLabel}
        className="relative h-full min-h-[22rem] min-w-0 overflow-hidden bg-background"
      >
        {nodes.length === 0 ? (
          <div className="flex h-full min-h-[22rem] items-center justify-center px-6 text-center text-sm text-muted">
            {emptyLabel}
          </div>
        ) : (
          <svg
            ref={svgRef}
            className="block h-full w-full touch-none"
            viewBox={`0 0 ${size.width} ${size.height}`}
            aria-hidden="true"
            onClick={() => onSelectEdge(null)}
          >
            <defs>
              <marker
                id={markerId}
                viewBox="0 -5 10 10"
                refX="9"
                refY="0"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                {/* 箭头继承所属连线的颜色；连线整体 opacity 会同步弱化箭头，避免箭头悬浮在淡线之上。 */}
                <path d="M0,-5L10,0L0,5" fill="context-stroke" />
              </marker>
            </defs>
            <g ref={graphGroupRef}>
              <g data-graph-edges>
                {edges.map((edge) => {
                  const isSelectedEdge = edge.id === selectedEdgeId;
                  const hasVisualFocus = Boolean(selectedNodeId || selectedEdgeId) || hasSearchQuery;
                  const connectedToSelection =
                    Boolean(selectedNodeId) && (edge.source === selectedNodeId || edge.target === selectedNodeId);
                  const matchesSearch =
                    hasSearchQuery && (matchedNodeIds.has(edge.source) || matchedNodeIds.has(edge.target));
                  // 选择邻域与搜索结果取并集，保证已选实体不会因后续搜索而被误弱化。
                  const isEmphasized =
                    !hasVisualFocus || isSelectedEdge || connectedToSelection || matchesSearch;
                  const isMuted = hasVisualFocus && !isEmphasized;
                  // 聚焦关系使用强调色，背景关系保持可读的 muted 色；不再把背景边压到近乎不可见。
                  const stroke = isSelectedEdge
                    ? "var(--color-accent)"
                    : hasVisualFocus
                    ? isMuted
                      ? "var(--color-muted)"
                      : "var(--color-accent)"
                    : edge.kind === "membership"
                      ? "var(--color-accent)"
                      : "var(--color-muted)";
                  const opacity = isSelectedEdge
                    ? 1
                    : isMuted
                    ? edge.isActive
                      ? 0.34
                      : 0.24
                    : edge.isActive
                      ? hasVisualFocus
                        ? 0.82
                        : 0.62
                      : hasVisualFocus
                        ? 0.48
                        : 0.34;
                  return (
                    <path
                      key={edge.id}
                      ref={(element) => {
                        if (element) edgeElementsRef.current.set(edge.id, element);
                        else edgeElementsRef.current.delete(edge.id);
                      }}
                      data-edge-id={edge.id}
                      data-selected={isSelectedEdge ? "true" : undefined}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={edgeWidth(edge) + (isSelectedEdge ? 1.8 : 0)}
                      strokeDasharray={edgeDashArray(edge.kind)}
                      opacity={opacity}
                      markerEnd={edge.directed ? `url(#${markerId})` : undefined}
                      vectorEffect="non-scaling-stroke"
                      pointerEvents="none"
                      className="transition-[opacity,stroke-width]"
                    />
                  );
                })}
              </g>
              <g data-graph-edge-hits>
                {edges.map((edge) => (
                  <path
                    key={edge.id}
                    ref={(element) => {
                      if (element) edgeHitElementsRef.current.set(edge.id, element);
                      else edgeHitElementsRef.current.delete(edge.id);
                    }}
                    data-graph-edge-hit
                    data-edge-id={edge.id}
                    fill="none"
                    stroke="transparent"
                    strokeWidth="14"
                    pointerEvents="stroke"
                    vectorEffect="non-scaling-stroke"
                    className="cursor-pointer"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelectEdge(edge.id);
                    }}
                  />
                ))}
              </g>
              <g data-graph-nodes>
                {nodes.map((node) => {
                  const isSelected = node.id === selectedNodeId;
                  const isSelectedEdgeEndpoint = selectedEdgeNodeIds.has(node.id);
                  const hasVisualFocus = Boolean(selectedNodeId || selectedEdgeId) || hasSearchQuery;
                  const selectionVisible =
                    (Boolean(selectedNodeId) && adjacentNodeIds.has(node.id)) ||
                    isSelectedEdgeEndpoint;
                  const searchVisible = hasSearchQuery && matchedNodeIds.has(node.id);
                  const isMuted = hasVisualFocus && !(selectionVisible || searchVisible);
                  // 未命中的节点仍保留足够轮廓和文字对比度，选中节点则通过强调色表面明确区分。
                  const opacity =
                    isSelected || isSelectedEdgeEndpoint
                      ? 1
                      : isMuted
                        ? node.isActive
                          ? 0.56
                          : 0.42
                        : node.isActive
                          ? 1
                          : 0.68;
                  const selectedFill =
                    node.kind === "character"
                      ? "color-mix(in srgb, var(--color-accent) 16%, var(--color-surface))"
                      : "color-mix(in srgb, var(--color-accent) 16%, var(--color-surface-secondary))";
                  const endpointFill =
                    node.kind === "character"
                      ? "color-mix(in srgb, var(--color-accent) 8%, var(--color-surface))"
                      : "color-mix(in srgb, var(--color-accent) 8%, var(--color-surface-secondary))";
                  const nodeStroke = isSelected || isSelectedEdgeEndpoint
                    ? "var(--color-accent)"
                    : isMuted
                      ? "var(--color-muted)"
                      : "var(--color-border)";
                  return (
                    <g
                      key={node.id}
                      ref={(element) => {
                        if (element) nodeElementsRef.current.set(node.id, element);
                        else nodeElementsRef.current.delete(node.id);
                      }}
                      data-graph-node
                      data-node-id={node.id}
                      opacity={opacity}
                      className="cursor-grab transition-opacity active:cursor-grabbing"
                      onClick={(event) => {
                        event.stopPropagation();
                        onSelectNode(node.id);
                      }}
                      onDoubleClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        const layoutNode = layoutNodesRef.current.get(node.id);
                        if (!layoutNode) return;
                        layoutNode.fx = null;
                        layoutNode.fy = null;
                        const simulation = simulationRef.current;
                        if (!simulation) return;
                        if (reducedMotion) settleSimulation(simulation, 0.45, 60);
                        else simulation.alpha(0.45).restart();
                      }}
                    >
                      {node.kind === "character" ? (
                        <circle
                          r="18"
                          fill={isSelected ? selectedFill : isSelectedEdgeEndpoint ? endpointFill : "var(--color-surface)"}
                          stroke={nodeStroke}
                          strokeWidth={isSelected ? 3 : isSelectedEdgeEndpoint ? 2.25 : 1.5}
                          vectorEffect="non-scaling-stroke"
                        />
                      ) : (
                        <rect
                          x="-52"
                          y="-19"
                          width="104"
                          height="38"
                          rx="10"
                          fill={isSelected ? selectedFill : isSelectedEdgeEndpoint ? endpointFill : "var(--color-surface-secondary)"}
                          stroke={nodeStroke}
                          strokeWidth={isSelected ? 3 : isSelectedEdgeEndpoint ? 2.25 : 1.5}
                          vectorEffect="non-scaling-stroke"
                        />
                      )}
                      <text
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fill="var(--foreground)"
                        fontSize={node.kind === "character" ? 10 : 11}
                        fontWeight={isSelected || isSelectedEdgeEndpoint ? 700 : 600}
                        className="pointer-events-none select-none"
                      >
                        {node.label.length > 12 ? `${node.label.slice(0, 11)}…` : node.label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </g>
          </svg>
        )}
      </div>
    );
  },
);

ForceGraphViewport.displayName = "ForceGraphViewport";

export default ForceGraphViewport;
