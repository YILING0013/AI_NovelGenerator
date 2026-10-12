"use client";

import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button, Popover } from "@heroui/react";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import { useLocale, useTranslations } from "next-intl";
import ForceGraphViewport, { type ForceGraphViewportHandle } from "./ForceGraphViewport";
import {
  createDefaultRelationshipGraphFilters,
  filterRelationshipGraph,
} from "./graphModel";
import type {
  RelationshipGraphEdgeKind,
  RelationshipGraphEdgeV1,
  RelationshipGraphFactionLevel,
  RelationshipGraphFilters,
  RelationshipGraphNodeKind,
} from "./graphTypes";
import { useRelationshipGraphSnapshot } from "./useRelationshipGraphSnapshot";

interface EntityGraphWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
}

type WorkspaceView = "graph" | "list";

const NODE_KINDS: RelationshipGraphNodeKind[] = ["character", "faction"];
const FACTION_LEVELS: Array<Exclude<RelationshipGraphFactionLevel, "unknown">> = [
  "core",
  "volume",
  "local",
];
const CHARACTER_IMPORTANCE: Array<keyof RelationshipGraphFilters["characterImportance"]> = [
  "core",
  "major",
  "supporting",
  "background",
];
const EDGE_KINDS: RelationshipGraphEdgeKind[] = [
  "character_relation",
  "faction_relation",
  "membership",
  "faction_hierarchy",
];

function toggleButtonClass(active: boolean): string {
  return `h-11 shrink-0 whitespace-nowrap rounded-md border px-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45 sm:h-9 ${
    active
      ? "border-accent bg-accent/10 text-accent"
      : "border-border bg-surface text-muted hover:bg-surface-secondary hover:text-foreground"
  }`;
}

function getOtherNodeId(edge: RelationshipGraphEdgeV1, nodeId: string): string {
  return edge.source === nodeId ? edge.target : edge.source;
}

/**
 * 功能：读取四类关系边对应的稳定业务标识，供无障碍详情路径核对事实来源。
 * Args:
 *   edge: 当前正式关系边或只读层级边。
 * Returns:
 *   关系业务 ID；层级边返回确定性的子势力与父势力组合。
 */
function getEdgeBusinessId(edge: RelationshipGraphEdgeV1): string {
  if (edge.kind === "membership") return edge.bindingId;
  if (edge.kind === "faction_hierarchy") {
    return `${edge.childFactionId}:${edge.parentFactionId}`;
  }
  return edge.relationId;
}

/**
 * 功能：提供势力、角色及四类正式关系的只读关系探索工作台。
 * Args:
 *   mode: 小说创建或编辑模式；创建模式下提示先保存小说。
 *   novelId: 已保存小说的 ObjectId。
 * Returns:
 *   包含原子刷新、筛选、图谱/无障碍列表、图例和选择详情的响应式工作台。
 */
export default function EntityGraphWorkspace({ mode, novelId }: EntityGraphWorkspaceProps) {
  const t = useTranslations("writing.entityGraph");
  const locale = useLocale();
  const graphRef = useRef<ForceGraphViewportHandle | null>(null);
  const [view, setView] = useState<WorkspaceView>("graph");
  const [detailsCollapsed, setDetailsCollapsed] = useState(false);
  const [filters, setFilters] = useState<RelationshipGraphFilters>(() =>
    createDefaultRelationshipGraphFilters(),
  );
  const [selection, setSelection] = useState<{ novelId: string | undefined; nodeId: string } | null>(null);
  const [edgeSelection, setEdgeSelection] = useState<{
    novelId: string | undefined;
    edgeId: string;
  } | null>(null);
  const selectedNodeId = selection && selection.novelId === novelId ? selection.nodeId : null;
  const selectedEdgeId =
    edgeSelection && edgeSelection.novelId === novelId ? edgeSelection.edgeId : null;
  const { snapshot, status, error, isStale, refresh } = useRelationshipGraphSnapshot(novelId);

  const projection = useMemo(
    () => (snapshot ? filterRelationshipGraph(snapshot, filters) : null),
    [filters, snapshot],
  );
  const nodeById = useMemo(
    () => new Map(projection?.nodes.map((node) => [node.id, node]) ?? []),
    [projection],
  );
  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) ?? null : null;
  const selectedEdge = selectedEdgeId
    ? projection?.edges.find((edge) => edge.id === selectedEdgeId) ?? null
    : null;
  const selectedEdgeSource = selectedEdge ? nodeById.get(selectedEdge.source) ?? null : null;
  const selectedEdgeTarget = selectedEdge ? nodeById.get(selectedEdge.target) ?? null : null;
  const incidentEdges = useMemo(
    () =>
      selectedNode
        ? projection?.edges.filter(
            (edge) => edge.source === selectedNodeId || edge.target === selectedNodeId,
          ) ?? []
        : [],
    [projection, selectedNode, selectedNodeId],
  );
  const listedNodes = useMemo(() => {
    if (!projection) return [];
    if (!filters.query.trim()) return projection.nodes;
    return projection.nodes.filter((node) => projection.matchedNodeIds.has(node.id));
  }, [filters.query, projection]);

  const selectNode = useCallback((nodeId: string) => {
    setEdgeSelection(null);
    setSelection({ novelId, nodeId });
  }, [novelId]);

  const selectEdge = useCallback((edgeId: string | null) => {
    if (!edgeId) {
      setEdgeSelection(null);
      return;
    }
    setSelection(null);
    setEdgeSelection((current) =>
      current && current.novelId === novelId && current.edgeId === edgeId
        ? null
        : { novelId, edgeId },
    );
  }, [novelId]);

  const updateNodeKind = (kind: RelationshipGraphNodeKind) => {
    setEdgeSelection(null);
    setFilters((current) => ({
      ...current,
      nodeKinds: { ...current.nodeKinds, [kind]: !current.nodeKinds[kind] },
    }));
  };
  const updateFactionLevel = (level: Exclude<RelationshipGraphFactionLevel, "unknown">) => {
    setEdgeSelection(null);
    setFilters((current) => ({
      ...current,
      factionLevels: { ...current.factionLevels, [level]: !current.factionLevels[level] },
    }));
  };
  const updateCharacterImportance = (
    importance: keyof RelationshipGraphFilters["characterImportance"],
  ) => {
    setEdgeSelection(null);
    setFilters((current) => ({
      ...current,
      characterImportance: {
        ...current.characterImportance,
        [importance]: !current.characterImportance[importance],
      },
    }));
  };
  const updateEdgeKind = (kind: RelationshipGraphEdgeKind) => {
    // 筛选可能移除当前关系，先清空选择可避免重新启用图层时旧浮层意外复现。
    setEdgeSelection(null);
    setFilters((current) => ({
      ...current,
      edgeKinds: { ...current.edgeKinds, [kind]: !current.edgeKinds[kind] },
    }));
  };

  const focusFirstMatch = () => {
    const nodeId = listedNodes[0]?.id;
    if (!nodeId) return;
    selectNode(nodeId);
    setView("graph");
    // 先让图谱面板恢复挂载，再在下一帧读取保留位置并居中。
    window.requestAnimationFrame(() => graphRef.current?.focusNode(nodeId));
  };

  const formatEdgeLabel = (edge: RelationshipGraphEdgeV1): string => {
    if (edge.kind === "character_relation" || edge.kind === "faction_relation") {
      return t(`relationTypes.${edge.relationType}`);
    }
    if (edge.kind === "membership") return t(`membershipTypes.${edge.membershipType}`);
    return t("edgeKinds.faction_hierarchy");
  };

  const renderEdgeDetailRows = (edge: RelationshipGraphEdgeV1): ReactNode => (
    <>
      <dt className="text-muted">{t("details.relationBusinessId")}</dt>
      <dd className="break-all font-mono text-foreground">{getEdgeBusinessId(edge)}</dd>
      <dt className="text-muted">{t("details.relationStatus")}</dt>
      <dd className="text-foreground">
        {edge.isActive ? t("activity.active") : t("activity.inactive")}
      </dd>
      {edge.intensity !== null && edge.kind !== "membership" ? (
        <>
          <dt className="text-muted">{t("details.intensity")}</dt>
          <dd className="text-foreground">{edge.intensity}</dd>
        </>
      ) : null}
      {edge.kind === "character_relation" || edge.kind === "faction_relation" ? (
        <>
          <dt className="text-muted">{t("details.currentState")}</dt>
          <dd className="whitespace-pre-wrap text-foreground">
            {edge.currentState || t("common.none")}
          </dd>
          <dt className="text-muted">{t("details.coreConflict")}</dt>
          <dd className="whitespace-pre-wrap text-foreground">
            {edge.coreConflict || t("common.none")}
          </dd>
        </>
      ) : null}
      {edge.kind === "membership" ? (
        <>
          <dt className="text-muted">{t("details.roleTitle")}</dt>
          <dd className="whitespace-pre-wrap text-foreground">
            {edge.roleTitle || t("common.none")}
          </dd>
          <dt className="text-muted">{t("details.publicStatus")}</dt>
          <dd className="whitespace-pre-wrap text-foreground">
            {edge.publicStatus || t("common.none")}
          </dd>
          <dt className="text-muted">{t("details.loyaltyLevel")}</dt>
          <dd className="text-foreground">{edge.loyaltyLevel ?? t("common.none")}</dd>
          <dt className="text-muted">{t("details.notes")}</dt>
          <dd className="whitespace-pre-wrap text-foreground">
            {edge.notes || t("common.none")}
          </dd>
        </>
      ) : null}
    </>
  );

  const statusLabel = (() => {
    if (status === "loading") return t("status.loading");
    if (status === "refreshing") return t("status.refreshing");
    if (status === "stale") return t("status.stale");
    if (status === "error") return t("status.error");
    if (snapshot) {
      return t("status.updated", {
        time: new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
          new Date(snapshot.loadedAt),
        ),
      });
    }
    return t("status.idle");
  })();
  const hasSearchQuery = Boolean(filters.query.trim());
  const panelState = (() => {
    if (status === "loading" && !snapshot) return <GraphLoading label={t("states.loading")} />;
    if (status === "error" && !snapshot) {
      return (
        <GraphState
          title={t("states.errorTitle")}
          description={t("states.errorDescription")}
          actionLabel={t("actions.retry")}
          onAction={() => void refresh()}
        />
      );
    }
    if (snapshot && snapshot.nodes.length === 0) {
      return <GraphState title={t("states.emptyTitle")} />;
    }
    if (snapshot && snapshot.nodes.length > 0 && projection?.nodes.length === 0) {
      return (
        <GraphState
          title={t("states.filteredTitle")}
          actionLabel={t("actions.resetFilters")}
          onAction={() => setFilters(createDefaultRelationshipGraphFilters())}
        />
      );
    }
    return null;
  })();
  const searchHasNoMatches = Boolean(
    projection && projection.nodes.length > 0 && hasSearchQuery && listedNodes.length === 0,
  );

  if (mode === "create" || !novelId) {
    return (
      <section className="flex h-full min-h-0 min-w-0 items-center justify-center overflow-hidden bg-background p-6">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-surface-secondary text-accent">
            <GraphIcon />
          </div>
          <h2 className="text-lg font-semibold text-foreground">{t("unsaved.title")}</h2>
        </div>
      </section>
    );
  }

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b border-border bg-surface px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="text-accent" aria-hidden="true"><GraphIcon /></span>
            <h1 className="truncate text-base font-semibold text-foreground">{t("title")}</h1>
          </div>
          <div className="flex items-center gap-2">
            <span
              aria-live="polite"
              className={`text-xs ${isStale || status === "error" ? "text-accent" : "text-muted"}`}
            >
              {statusLabel}
            </span>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={status === "loading" || status === "refreshing"}
              className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-secondary disabled:cursor-wait disabled:opacity-55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45"
            >
              {t("actions.refresh")}
            </button>
          </div>
        </div>
      </header>

      {isStale && snapshot ? (
        <div className="shrink-0 border-b border-border bg-accent/10 px-4 py-2 text-xs text-foreground sm:px-6">
          <strong>{t("stale.title")}</strong> {t("stale.description")}
          {error ? <span className="sr-only"> {error}</span> : null}
        </div>
      ) : null}
      {snapshot && snapshot.diagnostics.length > 0 ? (
        <details className="shrink-0 border-b border-border bg-surface-secondary px-4 py-2 text-xs text-muted sm:px-6">
          <summary className="cursor-pointer font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45">
            {t("diagnostics.summary", { count: snapshot.diagnostics.length })}
          </summary>
          <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto pl-5">
            {snapshot.diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.code}:${diagnostic.entityId ?? "unknown"}:${index}`}>
                {t(`diagnostics.codes.${diagnostic.code}`)}
                {diagnostic.entityId ? ` · ${diagnostic.entityId}` : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className={`workspace-scrollbar flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto lg:grid lg:overflow-hidden lg:transition-[grid-template-columns] lg:duration-200 motion-reduce:transition-none ${detailsCollapsed ? "lg:grid-cols-[minmax(0,1fr)_0rem]" : "lg:grid-cols-[minmax(0,1fr)_20rem]"}`}>
        <main className="flex min-h-[34rem] min-w-0 flex-col border-border lg:min-h-0 lg:border-r">
          <div className="shrink-0 border-b border-border bg-surface px-3 py-2 sm:px-4">
            <div data-graph-toolbar className="flex min-w-0 flex-wrap items-center gap-1.5">
              <label className="relative min-w-0 flex-[1_1_12rem] sm:max-w-60">
                <span className="sr-only">{t("search.label")}</span>
                <SearchIcon />
                <input
                  value={filters.query}
                  onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") focusFirstMatch();
                  }}
                  placeholder={t("search.placeholder")}
                  className="h-11 w-full rounded-md border border-border bg-background pl-8 pr-2 text-xs text-foreground outline-none placeholder:text-muted focus:border-accent focus:ring-2 focus:ring-accent/20 sm:h-9"
                />
              </label>
              <button
                type="button"
                onClick={focusFirstMatch}
                disabled={listedNodes.length === 0 || !filters.query.trim()}
                className="h-11 shrink-0 whitespace-nowrap rounded-md border border-border bg-surface px-2 text-xs font-medium text-foreground hover:bg-surface-secondary disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45 sm:h-9"
              >
                {t("actions.focusMatch")}
              </button>
              <Button
                size="sm"
                variant="outline"
                aria-label={t("views.toggle", { current: t(`views.${view}`), next: t(`views.${view === "graph" ? "list" : "graph"}`) })}
                aria-controls={`entity-graph-panel-${view}`}
                onPress={() => setView(view === "graph" ? "list" : "graph")}
                className="h-11 min-h-11 shrink-0 gap-1 rounded-md px-2 text-xs sm:h-9 sm:min-h-9"
              >
                {t(`views.${view}`)}
                <svg aria-hidden="true" className="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4" /></svg>
              </Button>
              <div className="contents" role="group" aria-label={t("filters.label")}>
                {NODE_KINDS.map((kind) => (
                  <button key={kind} type="button" aria-pressed={filters.nodeKinds[kind]} onClick={() => updateNodeKind(kind)} className={toggleButtonClass(filters.nodeKinds[kind])}>
                    {t(`nodeKinds.${kind}`)}
                  </button>
                ))}
                <span className="mx-0.5 h-5 border-l border-border" aria-hidden="true" />
                {FACTION_LEVELS.map((level) => (
                  <button key={level} type="button" aria-pressed={filters.factionLevels[level]} onClick={() => updateFactionLevel(level)} className={toggleButtonClass(filters.factionLevels[level])}>
                    {t(`factionLevels.${level}`)}
                  </button>
                ))}
                <button
                  type="button"
                  aria-pressed={filters.showInactive}
                  onClick={() => {
                    setEdgeSelection(null);
                    setFilters((current) => ({ ...current, showInactive: !current.showInactive }));
                  }}
                  className={toggleButtonClass(filters.showInactive)}
                >
                  {t("filters.showInactive")}
                </button>
                <Popover>
                  <Button size="sm" variant="outline" className="h-11 min-h-11 shrink-0 rounded-md px-2 text-xs text-muted sm:h-9 sm:min-h-9">
                    {t("filters.characterImportance")}
                  </Button>
                  <Popover.Content placement="bottom end" className="w-44 max-w-[calc(100vw-2rem)] border border-border bg-surface-raised shadow-lg">
                    <Popover.Dialog aria-label={t("filters.characterImportance")} className="p-2">
                      {CHARACTER_IMPORTANCE.map((importance) => (
                        <label key={importance} className="flex min-h-11 cursor-pointer items-center gap-2 px-2 py-1.5 text-xs text-foreground sm:min-h-8">
                          <input type="checkbox" checked={filters.characterImportance[importance]} onChange={() => updateCharacterImportance(importance)} className="accent-accent" />
                          {t(`importance.${importance}`)}
                        </label>
                      ))}
                    </Popover.Dialog>
                  </Popover.Content>
                </Popover>
                <Popover>
                  <Button size="sm" variant="outline" className="h-11 min-h-11 shrink-0 rounded-md px-2 text-xs text-muted sm:h-9 sm:min-h-9">
                    {t("filters.edgeLayers")}
                  </Button>
                  <Popover.Content placement="bottom end" className="w-52 max-w-[calc(100vw-2rem)] border border-border bg-surface-raised shadow-lg">
                    <Popover.Dialog aria-label={t("filters.edgeLayers")} className="p-2">
                      {EDGE_KINDS.map((kind) => (
                        <label key={kind} className="flex min-h-11 cursor-pointer items-center gap-2 px-2 py-1.5 text-xs text-foreground sm:min-h-8">
                          <input type="checkbox" checked={filters.edgeKinds[kind]} onChange={() => updateEdgeKind(kind)} className="accent-accent" />
                          {t(`edgeKinds.${kind}`)}
                        </label>
                      ))}
                    </Popover.Dialog>
                  </Popover.Content>
                </Popover>
              </div>
            </div>

            <div className="mt-2 flex min-w-0 flex-wrap items-center justify-between gap-2 border-t border-border pt-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted" aria-label={t("legend.label")}>
                <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-full border border-accent bg-surface" />{t("nodeKinds.character")}</span>
                <span className="inline-flex items-center gap-1"><span className="h-3 w-5 rounded border border-border bg-surface-secondary" />{t("nodeKinds.faction")}</span>
                <span className="inline-flex items-center gap-1"><span className="w-5 border-t border-muted" />{t("legend.symmetric")}</span>
                <span className="inline-flex items-center gap-1"><span className="w-5 border-t border-dashed border-muted" />{t("legend.directed")}</span>
              </div>
              {view === "graph" ? (
                <div className="flex items-center gap-1" aria-label={t("controls.label")}>
                  <GraphControl label={t("controls.zoomIn")} onClick={() => graphRef.current?.zoomIn()}>＋</GraphControl>
                  <GraphControl label={t("controls.zoomOut")} onClick={() => graphRef.current?.zoomOut()}>−</GraphControl>
                  <GraphControl label={t("controls.fit")} onClick={() => graphRef.current?.fitAll()}>{t("controls.fitShort")}</GraphControl>
                  <GraphControl label={t("controls.reset")} onClick={() => graphRef.current?.resetLayout()}>{t("controls.resetShort")}</GraphControl>
                </div>
              ) : null}
            </div>
          </div>

          <div className="relative min-h-0 min-w-0 flex-1 bg-background">
            <div
              id="entity-graph-panel-graph"
              role="region"
              aria-label={t("views.graph")}
              hidden={view !== "graph"}
              className="relative h-full min-h-[24rem] lg:min-h-0"
            >
              {view === "graph" ? panelState : null}
              {!panelState && projection && projection.nodes.length > 0 ? (
                <ForceGraphViewport
                  ref={graphRef}
                  nodes={projection.nodes}
                  edges={projection.edges}
                  selectedNodeId={selectedNode?.id ?? null}
                  selectedEdgeId={selectedEdge?.id ?? null}
                  matchedNodeIds={projection.matchedNodeIds}
                  hasSearchQuery={hasSearchQuery}
                  ariaLabel={t("graph.ariaLabel", { nodes: projection.nodes.length, edges: projection.edges.length })}
                  emptyLabel={t("states.filteredTitle")}
                  onSelectNode={selectNode}
                  onSelectEdge={selectEdge}
                />
              ) : null}
              {!panelState && selectedEdge && selectedEdgeSource && selectedEdgeTarget ? (
                <GraphEdgeInspector
                  ariaLabel={t("edgeInspector.ariaLabel", {
                    relation: formatEdgeLabel(selectedEdge),
                    source: selectedEdgeSource.label,
                    target: selectedEdgeTarget.label,
                  })}
                  eyebrow={t("edgeInspector.eyebrow")}
                  kindLabel={t(`edgeKinds.${selectedEdge.kind}`)}
                  title={formatEdgeLabel(selectedEdge)}
                  sourceLabel={selectedEdgeSource.label}
                  targetLabel={selectedEdgeTarget.label}
                  directed={selectedEdge.directed}
                  directionLabel={selectedEdge.directed ? t("legend.directed") : t("legend.symmetric")}
                  closeLabel={t("edgeInspector.close")}
                  onClose={() => selectEdge(null)}
                >
                  {renderEdgeDetailRows(selectedEdge)}
                </GraphEdgeInspector>
              ) : null}
              {!panelState && searchHasNoMatches ? (
                <div
                  role="status"
                  className="pointer-events-none absolute left-1/2 top-4 z-10 w-[min(24rem,calc(100%-2rem))] -translate-x-1/2 rounded-lg border border-border bg-surface/95 px-4 py-3 text-center shadow-sm backdrop-blur"
                >
                  <p className="text-sm font-semibold text-foreground">{t("states.searchEmptyTitle")}</p>
                </div>
              ) : null}
            </div>
            <div
              id="entity-graph-panel-list"
              role="region"
              aria-label={t("views.list")}
              tabIndex={0}
              hidden={view !== "list"}
              className="workspace-scrollbar h-full min-h-[24rem] overflow-y-auto p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/45 sm:p-4 lg:min-h-0"
            >
              {view === "list" ? (
                panelState ?? (searchHasNoMatches ? (
                  <GraphState title={t("states.searchEmptyTitle")} />
                ) : null)
              ) : null}
              {!panelState && !searchHasNoMatches && projection && projection.nodes.length > 0 ? (
                <>
                <p className="mb-3 text-xs text-muted">{t("list.summary", { shown: listedNodes.length, total: projection.nodes.length })}</p>
                <ul className="divide-y divide-border border-y border-border">
                  {listedNodes.map((node) => (
                    <li key={node.id}>
                      <button
                        type="button"
                        onClick={() => selectNode(node.id)}
                        aria-current={selectedNodeId === node.id ? "true" : undefined}
                        className="flex w-full items-center justify-between gap-4 px-2 py-3 text-left hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/45"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium text-foreground">{node.label}</span>
                          <span className="mt-0.5 block text-xs text-muted">{node.kind === "character" ? t(`importance.${node.importanceLevel}`) : t(`factionLevels.${node.level}`)}</span>
                        </span>
                        <span className="shrink-0 text-xs text-muted">{node.isActive ? t("activity.active") : t("activity.inactive")}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                </>
              ) : null}
            </div>
          </div>
        </main>

        <div className="relative min-h-0 min-w-0">
          <aside id={`entity-graph-details-${novelId}`} aria-label={t("details.ariaLabel")} tabIndex={0} className={`workspace-scrollbar min-h-[18rem] min-w-0 overflow-y-auto bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/45 lg:h-full lg:min-h-0 ${detailsCollapsed ? "lg:invisible" : ""}`}>
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold text-foreground">{t("details.title")}</h2>
            </div>
            {!selectedNode ? (
              <div className="px-4 py-8 text-center text-sm leading-6 text-muted">{t("details.empty")}</div>
            ) : (
              <div className="divide-y divide-border">
                <section className="px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold tracking-normalr text-muted">{t(`nodeKinds.${selectedNode.kind}`)}</p>
                      <h3 className="mt-1 break-words text-base font-semibold text-foreground">{selectedNode.label}</h3>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${selectedNode.isActive ? "border-accent/40 bg-accent/10 text-accent" : "border-border text-muted"}`}>
                      {selectedNode.isActive ? t("activity.active") : t("activity.inactive")}
                    </span>
                  </div>
                  <dl className="mt-4 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
                    <dt className="text-muted">{t("details.businessId")}</dt><dd className="break-all font-mono text-foreground">{selectedNode.kind === "character" ? selectedNode.characterId : selectedNode.factionId}</dd>
                    {selectedNode.kind === "character" ? (
                      <>
                        <dt className="text-muted">{t("details.importance")}</dt><dd className="text-foreground">{t(`importance.${selectedNode.importanceLevel}`)}</dd>
                        <dt className="text-muted">{t("details.role")}</dt><dd className="text-foreground">{t(`roleTypes.${selectedNode.roleType}`)}</dd>
                        <dt className="text-muted">{t("details.identity")}</dt><dd className="whitespace-pre-wrap text-foreground">{selectedNode.identity || t("common.none")}</dd>
                      </>
                    ) : (
                      <>
                        <dt className="text-muted">{t("details.level")}</dt><dd className="text-foreground">{t(`factionLevels.${selectedNode.level}`)}</dd>
                        <dt className="text-muted">{t("details.type")}</dt><dd className="text-foreground">{selectedNode.factionType || t("common.none")}</dd>
                        <dt className="text-muted">{t("details.positioning")}</dt><dd className="whitespace-pre-wrap text-foreground">{selectedNode.positioning || t("common.none")}</dd>
                      </>
                    )}
                  </dl>
                </section>
                <section className="px-4 py-4">
                  <h3 className="text-xs font-semibold tracking-normalr text-muted">{t("details.relations", { count: incidentEdges.length })}</h3>
                  {incidentEdges.length === 0 ? (
                    <p className="mt-3 text-sm text-muted">{t("details.noRelations")}</p>
                  ) : (
                    <ul className="mt-2 divide-y divide-border">
                      {incidentEdges.map((edge) => {
                        const other = nodeById.get(getOtherNodeId(edge, selectedNode.id));
                        return (
                          <li key={edge.id} className="py-2.5">
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-xs font-medium text-foreground">{formatEdgeLabel(edge)}</span>
                              <span className="text-xs text-muted">{edge.directed ? t("legend.directed") : t("legend.symmetric")}</span>
                            </div>
                            <p className="mt-1 truncate text-xs text-muted">{other?.label ?? t("details.missingEndpoint")}</p>
                            <dl className="mt-2 grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-2 gap-y-1 text-xs leading-4">
                              {renderEdgeDetailRows(edge)}
                            </dl>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              </div>
            )}
          </aside>
          <SidebarEdgeHandle
            controls={`entity-graph-details-${novelId}`}
            side="left"
            className="hidden lg:flex"
            leftAction={detailsCollapsed ? { label: t("details.expand"), expanded: false, onPress: () => setDetailsCollapsed(false) } : undefined}
            rightAction={detailsCollapsed ? undefined : { label: t("details.collapse"), expanded: true, onPress: () => setDetailsCollapsed(true) }}
          />
        </div>
      </div>
    </section>
  );
}

interface GraphEdgeInspectorProps {
  ariaLabel: string;
  eyebrow: string;
  kindLabel: string;
  title: string;
  sourceLabel: string;
  targetLabel: string;
  directed: boolean;
  directionLabel: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
}

/**
 * 功能：在图谱表面展示当前选中连线的只读关系信息，并提供明确的关闭入口。
 * Args:
 *   props: 浮层无障碍名称、关系标题、端点、方向、详情字段和关闭回调。
 * Returns:
 *   位于 SVG 外部、可由辅助技术读取的非模态关系详情区域。
 */
function GraphEdgeInspector({
  ariaLabel,
  eyebrow,
  kindLabel,
  title,
  sourceLabel,
  targetLabel,
  directed,
  directionLabel,
  closeLabel,
  onClose,
  children,
}: GraphEdgeInspectorProps) {
  return (
    <section
      data-edge-inspector
      role="region"
      aria-label={ariaLabel}
      className="workspace-scrollbar absolute right-3 top-3 z-20 max-h-[calc(100%-1.5rem)] w-[min(21rem,calc(100%-1.5rem))] overflow-y-auto rounded-xl border border-accent/45 bg-surface/95 shadow-lg backdrop-blur-sm"
    >
      <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold tracking-normalr text-accent">
            {eyebrow} · {kindLabel}
          </p>
          <h3 className="mt-1 break-words text-sm font-semibold text-foreground">{title}</h3>
        </div>
        <button
          type="button"
          aria-label={closeLabel}
          title={closeLabel}
          onClick={onClose}
          className="-mr-2 -mt-2 flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-muted hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45"
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <div className="px-4 py-3">
        <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface-secondary px-3 py-2 text-xs font-medium text-foreground">
          <span className="min-w-0 flex-1 break-words text-right">{sourceLabel}</span>
          <span aria-hidden="true" className="shrink-0 text-accent">{directed ? "→" : "↔"}</span>
          <span className="min-w-0 flex-1 break-words">{targetLabel}</span>
        </div>
        <p className="mt-1.5 text-center text-xs text-muted">{directionLabel}</p>
        <dl className="mt-3 grid grid-cols-[6rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs leading-5">
          {children}
        </dl>
      </div>
    </section>
  );
}

/**
 * 功能：渲染关系图谱入口和页头共用的语义装饰图标。
 * Args:
 *   无。
 * Returns:
 *   对辅助技术隐藏的 SVG 图标。
 */
function GraphIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="5" cy="12" r="2.5" /><circle cx="18.5" cy="5.5" r="2.5" /><rect x="15.5" y="15.5" width="5" height="5" rx="1" /><path d="m7.3 10.9 8.9-4.3M7.4 13.2l8.2 3.8M18.5 8v7.5" />
    </svg>
  );
}

/**
 * 功能：渲染搜索输入框使用的装饰图标。
 * Args:
 *   无。
 * Returns:
 *   对辅助技术隐藏的 SVG 搜索图标。
 */
function SearchIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}

/**
 * 功能：渲染带可读名称的紧凑图谱视口控制按钮。
 * Args:
 *   label: 按钮的无障碍名称与提示文字。
 *   onClick: 触发的视口命令。
 *   children: 按钮内的短标签或符号。
 * Returns:
 *   统一尺寸和焦点样式的按钮。
 */
function GraphControl({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className="min-h-9 min-w-9 rounded-md border border-border bg-surface px-2 text-xs font-medium text-foreground hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45">
      {children}
    </button>
  );
}

/**
 * 功能：渲染首次构建图谱时的非持续动画加载状态。
 * Args:
 *   label: 本地化加载说明。
 * Returns:
 *   可由屏幕阅读器播报一次的加载区域。
 */
function GraphLoading({ label }: { label: string }) {
  return (
    <div className="flex h-full min-h-[24rem] items-center justify-center" aria-label={label} role="status">
      <div className="text-center">
        <div className="mx-auto h-8 w-8 animate-pulse rounded-full border-2 border-border border-t-accent motion-reduce:animate-none" />
        <p className="mt-3 text-sm text-muted">{label}</p>
      </div>
    </div>
  );
}

/**
 * 功能：统一渲染空数据、筛选无结果与首次错误状态。
 * Args:
 *   title: 状态标题。
 *   description: 状态解释。
 *   actionLabel: 可选动作名称。
 *   onAction: 可选动作回调。
 * Returns:
 *   平面化状态内容及可选操作按钮。
 */
function GraphState({ title, description, actionLabel, onAction }: { title: string; description?: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <div className="flex h-full min-h-[24rem] items-center justify-center px-6 text-center">
      <div className="max-w-sm">
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
        {description && <p className="mt-2 text-sm leading-6 text-muted">{description}</p>}
        {actionLabel && onAction ? (
          <button type="button" onClick={onAction} className="mt-4 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/45">
            {actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
