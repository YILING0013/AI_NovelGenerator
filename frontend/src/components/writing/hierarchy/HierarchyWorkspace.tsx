"use client";
import { useAssistantRefresh, useAssistantResource } from "../assistant/AssistantContext";

import { Button } from "@heroui/react";
import { useCallback, useContext, useEffect, useRef, useState, type RefObject } from "react";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { useTranslations } from "next-intl";
import { apiDelete, apiGet, apiPatch, apiPost, ApiRequestError } from "@/lib/api";
import { readWritingDraft } from "@/lib/writingDrafts";
import { ConfirmActionModal, RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import DocumentSection from "@/components/shared/DocumentSection";
import SectionEditButton from "@/components/shared/SectionEditButton";
import { TooltipHint } from "@/components/shared/TooltipHint";
import { CHILD_KIND, hierarchyChildrenUrl, hierarchyLocation, hierarchyNode, type EntityChoices, type HierarchyKind, type HierarchyLocation, type HierarchyNode, type HierarchyRecord, type PlanningReadiness, type PlanningKind } from "@/types/hierarchy";
import ChapterBodyEditor from "./ChapterBodyEditor";
import PlanningEditor from "./PlanningEditor";
import HierarchyGeneration from "./HierarchyGeneration";
import ChapterContinuation, { type SavedChapterBatch } from "./ChapterContinuation";
import { registerSavedChapterBatch } from "./chapterPlanBatches";
import { readChapterPlanConfirmations } from "./chapterPlanConfirmations";
import PlotSection from "./PlotSection";
import ChapterRecords from "../chapter-records/ChapterRecords";
import { PlanningReadout, PLANNING_SECTIONS, type PlanningSection } from "./PlanningFields";

const EMPTY_CHOICES: EntityChoices = { character_ids: [], faction_ids: [], location_ids: [], item_ids: [], rule_ids: [] };
const KIND_ORDER: HierarchyKind[] = ["volume", "arc", "scene", "chapter"];

/** 功能：分别管理篇章规划与章节写作，父级只用于选择位置。Args: props 小说、管理范围、当前父链和导航。Returns: 按当前分支加载的工作台。 */
export default function HierarchyWorkspace({ novelId, location, scope = "chapters", onNavigate, onVolume, onArc, onNavigateItem, chapterReviewId, onDirtyChange, onBusyChange, beforeLeaveRef, bodyView = false, focusPlot = false }: {
  novelId: string; location: HierarchyLocation; scope?: "arcs" | "chapters"; bodyView?: boolean; focusPlot?: boolean;
  onNavigate: (location: HierarchyLocation, replace?: boolean) => void;
  onVolume: (volumeId: string) => void;
  onArc?: (location: HierarchyLocation) => void;
  onNavigateItem?: (itemId: string, chapterId: string, reviewId: string) => void;
  chapterReviewId?: string | null;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.hierarchy");
  const plotT = useTranslations("writing.plot");
  const recordsT = useTranslations("writing.chapterRecords");
  const active = useContext(RetainedViewActive);
  const [volumes, setVolumes] = useState<HierarchyNode[]>([]);
  const [arcs, setArcs] = useState<HierarchyNode[]>([]);
  const [branches, setBranches] = useState<Record<string, HierarchyNode[]>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<HierarchyNode | null>(null);
  const [ancestors, setAncestors] = useState<HierarchyNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savedReadFailed, setSavedReadFailed] = useState(false);
  const [choicesError, setChoicesError] = useState("");
  const [choices, setChoices] = useState<EntityChoices>(EMPTY_CHOICES);
  const [readinessById, setReadinessById] = useState<Record<string, PlanningReadiness>>({});
  const [readinessErrors, setReadinessErrors] = useState<Record<string, string>>({});
  const [showTrash, setShowTrash] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(Boolean(scope === "arcs" ? location.arc_id : location.scene_id || location.chapter_id));
  useEffect(() => {
    if (active && focusPlot && scope === "arcs" && location.arc_id) setMobileDetail(true);
  }, [active, focusPlot, scope, location.arc_id]);
  const [bodyTab, setBodyTab] = useState(bodyView);
  const [recordsTab, setRecordsTab] = useState(false);
  const [recordsDirty, setRecordsDirty] = useState(false);
  const [recordsSaving, setRecordsSaving] = useState(false);
  const recordsBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const [bodyDirty, setBodyDirty] = useState(false);
  const [planDirty, setPlanDirty] = useState(false);
  const [planSaving, setPlanSaving] = useState(false);
  const [bodySaving, setBodySaving] = useState(false);
  const [plotBusy, setPlotBusy] = useState(false);
  const [plotRunning, setPlotRunning] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useAssistantRefresh(novelId, () => { setRefresh((value) => value + 1); });
  useAssistantResource(selected ? { resource_type: selected.kind, id: selected.id, name: selected.record.title, version: selected.record.version } : null);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<{ kind: PlanningKind; parent: HierarchyNode; source: HierarchyNode | null; section?: PlanningSection } | null>(null);
  const [generationNode, setGenerationNode] = useState<HierarchyNode | null>(null);
  const [generationPage, setGenerationPage] = useState(false);
  const generationOrigin = useRef<string | null>(null);
  const [continuationScope, setContinuationScope] = useState<"scene" | "arc">("scene");
  const [continuation, setContinuation] = useState<{ scene: HierarchyNode; arc: HierarchyNode; scope: "scene" | "arc"; batch?: SavedChapterBatch; locationKey: string; open: boolean } | null>(null);
  const continuationRef = useRef(continuation); continuationRef.current = continuation;
  const [batches, setBatches] = useState<{ sceneId: string; items: SavedChapterBatch[] }>({ sceneId: "", items: [] });
  const [batchId, setBatchId] = useState("");
  const [batchError, setBatchError] = useState("");
  const [planRecovery, setPlanRecovery] = useState(false);
  const batchRead = useRef(0);
  const [intent, setIntent] = useState<"delete" | "restore" | "hard" | null>(null);
  const [intentError, setIntentError] = useState("");
  const [impact, setImpact] = useState<Record<string, unknown> | null>(null);
  const [pendingNavigation, setPendingNavigation] = useState<HierarchyNode | null>(null);
  const requestId = useRef(0);
  const detailRef = useRef<HTMLElement>(null);
  const selectedKey = `${location.volume_id ?? ""}:${location.arc_id ?? ""}:${location.scene_id ?? ""}:${location.chapter_id ?? ""}`;
  const viewTarget = useRef("");
  const confirmedTarget = useRef<string | null>(null);
  const navigateRef = useRef(onNavigate); navigateRef.current = onNavigate;
  const selectedIdRef = useRef(selected?.id); selectedIdRef.current = selected?.id;
  const scopeRef = useRef({ active, novelId, scope, bodyTab, key: selectedKey, id: selectedKey.split(":").findLast(Boolean) });
  scopeRef.current = { active, novelId, scope, bodyTab, key: selectedKey, id: selectedKey.split(":").findLast(Boolean) };
  const editorFocusTarget = useRef<{ id: string; section: PlanningSection } | null>(null);
  const requestedHistory = useRef<string | null>(null);
  const requestedReview = useRef<string | null>(null);

  useEffect(() => {
    const target = active && location.chapter_id && chapterReviewId ? `${location.chapter_id}:${chapterReviewId}` : null;
    if (!target) { requestedReview.current = null; return; }
    if (requestedReview.current === target || recordsDirty || recordsSaving) return;
    // 地址只定位章后记录，继续审核仍由作者点击原入口。
    requestedReview.current = target; setRecordsTab(true); setBodyTab(false);
  }, [active, location.chapter_id, chapterReviewId, recordsDirty, recordsSaving]);

  useEffect(() => {
    const target = active && !chapterReviewId && location.revision_version ? `${selectedKey}:${location.revision_version}` : null;
    if (!target) { requestedHistory.current = null; return; }
    if (requestedHistory.current === target || recordsDirty || recordsSaving) return;
    // 明确的历史定位回到正文页签；普通记录刷新不改变作者选择。
    requestedHistory.current = target; setRecordsTab(false); setBodyTab(true);
  }, [active, selectedKey, location.revision_version, chapterReviewId, recordsDirty, recordsSaving]);

  useEffect(() => { setIntent(null); setImpact(null); }, [selectedKey]);

  useEffect(() => {
    if (!active || !bodyTab || recordsTab || continuation?.locationKey !== selectedKey) {
      setContinuation((current) => current?.open ? { ...current, open: false } : current);
    }
  }, [active, bodyTab, recordsTab, selectedKey, continuation?.locationKey]);

  useEffect(() => {
    if (!active || scope !== "chapters" || !location.scene_id) return;
    let current = true;
    const revision = ++batchRead.current;
    const sceneId = location.scene_id;
    setBatchError(""); setPlanRecovery(false);
    Promise.all([
      readWritingDraft<SavedChapterBatch[]>(`${novelId}:scene:${sceneId}:chapter-plan-batches`, 0),
      readWritingDraft<{ command?: unknown; saved?: unknown }>(`${novelId}:scene:${sceneId}:generation`),
      readChapterPlanConfirmations(`${novelId}:scene:${sceneId}:generation`),
    ]).then(([stored, generation, confirmations]) => {
      if (!current || revision !== batchRead.current) return;
      setBatches({ sceneId, items: stored?.value ?? [] });
      setPlanRecovery(Boolean(confirmations.some((item) => item.value.preview || item.value.command || item.value.saved) || generation?.value.command || generation?.value.saved));
    }).catch(() => { if (current && revision === batchRead.current) setBatchError(t("draftFailed")); });
    return () => { current = false; };
  }, [active, scope, novelId, location.scene_id, refresh, generationNode, t]);

  useEffect(() => {
    onDirtyChange?.(active && (bodyDirty || planDirty || planSaving || bodySaving || plotBusy && !plotRunning || recordsDirty || recordsSaving));
    return () => onDirtyChange?.(false);
  }, [active, bodyDirty, planDirty, planSaving, bodySaving, plotBusy, plotRunning, recordsDirty, recordsSaving, onDirtyChange]);
  useEffect(() => { if (active) onBusyChange?.(recordsSaving); return () => onBusyChange?.(false); }, [active, recordsSaving, onBusyChange]);
  useEffect(() => {
    if (!active || !beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { await recordsBeforeLeave.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef]);

  useEffect(() => {
    if (!active) { editorFocusTarget.current = null; return; }
    if (loading || editor) return;
    const target = editorFocusTarget.current;
    if (!target || selected?.id !== target.id) return;
    const frame = requestAnimationFrame(() => {
      if (scopeRef.current.active && scopeRef.current.id === target.id) document.getElementById(`planning-${target.id}-${target.section}-edit`)?.focus();
      editorFocusTarget.current = null;
    });
    return () => cancelAnimationFrame(frame);
  }, [active, editor, loading, selected?.id]);

  const loadChildren = useCallback(async (node: HierarchyNode, signal?: AbortSignal) => {
    if (node.kind === "chapter" || (scope === "arcs" && node.kind === "arc") || node.record.is_deleted) return [];
    const url = hierarchyChildrenUrl(node);
    const results = await Promise.all([
      apiGet<{ data: HierarchyRecord[] }>(url, { signal }),
      ...(showTrash && (scope === "arcs" ? node.kind === "volume" : node.kind !== "volume") ? [apiGet<{ data: HierarchyRecord[] }>(`${url}?deleted=true`, { signal })] : []),
    ]);
    return results.flatMap((result) => result.data).map((record) => hierarchyNode(CHILD_KIND[node.kind as "volume" | "arc" | "scene"], record));
  }, [scope, showTrash]);

  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); const current = ++requestId.current;
    const target = `${novelId}:${scope}:${selectedKey}`;
    // 详情等读取结束再换，避免取消历史导航时卸载正文、丢掉有草稿的状态。
    if (viewTarget.current !== target) {
      confirmedTarget.current = null; setSavedReadFailed(false);
    }
    viewTarget.current = target;
    setLoading(true); setError(""); setReadinessById({}); setReadinessErrors({});
    const ids = selectedKey.split(":");
    const load = async () => {
      try {
        const list = await apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal: abort.signal });
        if (abort.signal.aborted || current !== requestId.current) return;
        const roots = list.data.map((record) => hierarchyNode("volume", record));
        const arcLists = scope === "chapters" ? await Promise.all(roots.map((root) => loadChildren(root, abort.signal))) : [];
        if (abort.signal.aborted || current !== requestId.current) return;
        const arcOptions = arcLists.flat();
        const last = ids.findLastIndex(Boolean);
        if (last < 0) {
          setVolumes(roots); setArcs(arcOptions);
          const first = scope === "chapters" ? arcOptions[0] ?? roots[0] : roots[0];
          if (first) navigateRef.current(hierarchyLocation(first), true);
          else { setSelected(null); setAncestors([]); setBranches({}); }
          return;
        }
        if (ids.some((id) => id && !/^[a-f0-9]{24}$/i.test(id))) throw new Error(t("invalidLocation"));
        const kind = KIND_ORDER[last];
        const record = kind === "volume" ? roots.find((root) => root.id === ids[last])?.record
          : await apiGet<HierarchyRecord>(`/api/${kind}s/${ids[last]}?include_deleted=true`, { signal: abort.signal });
        if (!record || record.novel_id !== novelId) throw new Error(t("notFound"));
        if (scope === "chapters" && kind === "volume") {
          const first = arcOptions.find((arc) => arc.record.volume_id === record.volume_id);
          if (first) { navigateRef.current(hierarchyLocation(first), true); return; }
        }
        const node = hierarchyNode(kind, record);
        const parentNodes: HierarchyNode[] = [];
        for (const parentKind of KIND_ORDER.slice(0, last)) {
          const id = record[`${parentKind}_id`]!;
          const parentRecord = parentKind === "volume" ? roots.find((root) => root.id === id)?.record
            : await apiGet<HierarchyRecord>(`/api/${parentKind}s/${id}`, { signal: abort.signal });
          if (!parentRecord) throw new Error(t("notFound"));
          parentNodes.push(hierarchyNode(parentKind, parentRecord));
        }
        const branchParents = [...parentNodes, node].filter((item) => item.kind !== "chapter" && !item.record.is_deleted && (scope === "arcs" ? item.kind === "volume" : item.kind !== "volume"));
        const loaded = await Promise.all(branchParents.map(async (item) => [item.id, await loadChildren(item, abort.signal)] as const));
        if (abort.signal.aborted || current !== requestId.current) return;
        // 整条父链和目录读完再替换，半途失败不拆散刚确认的结果。
        setVolumes(roots); setArcs(arcOptions);
        setBranches((existing) => ({ ...existing, ...Object.fromEntries(loaded) }));
        setExpanded((existing) => new Set([...existing, ...parentNodes.map((item) => item.id)]));
        setAncestors(parentNodes); setSelected(node);
        confirmedTarget.current = null; setSavedReadFailed(false);
        if (bodyView && node.kind === "chapter" && selectedIdRef.current !== node.id) setBodyTab(true);
        const actual = { ...hierarchyLocation(node), ...(node.kind === "chapter" && location.revision_version ? { revision_version: location.revision_version } : {}) };
        if (KIND_ORDER.some((item, index) => (actual[`${item}_id`] ?? "") !== ids[index])) navigateRef.current(actual, true);
        if (node.record.is_deleted) setShowTrash(true);
        // 顶部父级动作和当前场景／正文分别检查所需资料，不把父级编辑器放回详情。
        const checks = [...parentNodes, node].filter((item) => !item.record.is_deleted && (scope === "arcs" ? item.kind === "volume" : item.kind === "arc" || item.id === node.id && item.kind !== "volume"));
        await Promise.all(checks.map(async (item) => {
          try {
            const result = await apiGet<PlanningReadiness>(`/api/novels/${novelId}/planning-readiness?target_type=${item.kind}&target_id=${item.id}`, { signal: abort.signal });
            if (!abort.signal.aborted && current === requestId.current) setReadinessById((existing) => ({ ...existing, [item.id]: result }));
          } catch (failure) {
            if (!abort.signal.aborted && current === requestId.current) setReadinessErrors((existing) => ({ ...existing, [item.id]: failure instanceof Error ? failure.message : t("loadFailed") }));
          }
        }));
      } catch (failure) {
        if (abort.signal.aborted || current !== requestId.current) return;
        const temporary = failure instanceof TypeError || failure instanceof ApiRequestError && failure.status >= 500;
        const keepSaved = temporary && confirmedTarget.current === target;
        setSavedReadFailed(keepSaved);
        if (!keepSaved) {
          confirmedTarget.current = null;
          setSelected(null); setAncestors([]); setBranches({});
        }
        setError(failure instanceof Error ? failure.message : t("loadFailed"));
      } finally { if (!abort.signal.aborted && current === requestId.current) setLoading(false); }
    };
    void load();
    return () => abort.abort();
  }, [novelId, selectedKey, location.revision_version, refresh, loadChildren, t, bodyView, active, scope]);

  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    const resources = [["character_ids", "characters", "character_id"], ["faction_ids", "factions", "faction_id"], ["location_ids", "locations", "location_id"], ["item_ids", "items", "item_id"], ["rule_ids", "world-rules", "rule_id"]] as const;
    Promise.all(resources.map(async ([field, route, id]) => {
      const response = await apiGet<Record<string, string>[] | { data: Record<string, string>[] }>(`/api/${route}/novel/${novelId}`, { signal: abort.signal });
      const records = Array.isArray(response) ? response : response.data;
      return [field, records.map((item) => ({ id: item[id], name: item.name ?? item.title }))] as const;
    })).then((entries) => { if (!abort.signal.aborted) { setChoices(Object.fromEntries(entries) as EntityChoices); setChoicesError(""); } })
      .catch((failure) => { if (!abort.signal.aborted) setChoicesError(failure instanceof Error ? failure.message : t("loadFailed")); });
    return () => abort.abort();
  }, [novelId, refresh, t, active]);

  const choose = (node: HierarchyNode) => {
    if (planSaving || bodySaving || plotBusy || recordsSaving) return;
    if (bodyDirty || planDirty || recordsDirty) { setPendingNavigation(node); return; }
    setEditor(null); onNavigate(hierarchyLocation(node)); setMobileDetail(node.kind !== (scope === "arcs" ? "volume" : "arc"));
    requestAnimationFrame(() => { if (detailRef.current && getComputedStyle(detailRef.current.previousElementSibling!).display === "none") detailRef.current.focus(); });
  };

  const expand = async (node: HierarchyNode) => {
    if (expanded.has(node.id)) { setExpanded((set) => { const next = new Set(set); next.delete(node.id); return next; }); return; }
    if (node.kind === "scene" && !showTrash && node.record.chapter_count === 0 && !branches[node.id]?.some((child) => !child.record.is_deleted)) return;
    try {
      const children = branches[node.id] ?? await loadChildren(node);
      setBranches((current) => ({ ...current, [node.id]: children }));
      if (children.some((child) => showTrash || !child.record.is_deleted)) setExpanded((set) => new Set([...set, node.id]));
    } catch (failure) { setError(failure instanceof Error ? failure.message : t("loadFailed")); }
  };

  const visible: { node: HierarchyNode; level: number; parent: HierarchyNode | null }[] = [];
  const appendVisible = (nodes: HierarchyNode[], level: number, parent: HierarchyNode | null) => {
    for (const node of nodes) {
      if (!showTrash && node.record.is_deleted) continue;
      visible.push({ node, level, parent });
      if (expanded.has(node.id)) appendVisible(branches[node.id] ?? [], level + 1, node);
    }
  };
  const workspaceParent = [selected, ...ancestors].find((node) => node?.kind === (scope === "arcs" ? "volume" : "arc")) ?? null;
  appendVisible(workspaceParent ? branches[workspaceParent.id] ?? [] : [], 1, null);
  const parent = ancestors.at(-1) ?? null;
  const siblings = parent ? (branches[parent.id] ?? []).filter((node) => !node.record.is_deleted) : [];
  const index = siblings.findIndex((node) => node.id === selected?.id);

  const saved = (records: HierarchyRecord[], kind: HierarchyKind) => {
    // 保存回应可以迟到，但不能把已离开的节点或小说重新带回页面。
    const current = scopeRef.current;
    if (!current.active || current.novelId !== novelId || current.scope !== scope || current.key !== selectedKey) return;
    const record = records[0];
    const nodes = records.map((item) => hierarchyNode(kind, item));
    const node = nodes[0];
    const parents = KIND_ORDER.slice(0, KIND_ORDER.indexOf(kind)).map((parentKind) =>
      [...ancestors, selected, generationNode, editor?.parent].find((item) => item?.kind === parentKind && item.id === record[`${parentKind}_id`])!);
    const savedParent = parents.at(-1)!;
    const nextKey = KIND_ORDER.map((item) => record[`${item}_id`] ?? "").join(":");
    confirmedTarget.current = `${novelId}:${scope}:${nextKey}`;
    viewTarget.current = confirmedTarget.current;
    requestId.current += 1;
    setEditor(null); setGenerationNode(null); setBodyDirty(false); setPlanDirty(false);
    setError(""); setSavedReadFailed(false); setReadinessById({}); setReadinessErrors({});
    setBranches((current) => ({ ...current, [savedParent.id]: [
      ...(current[savedParent.id] ?? []).filter((item) => !nodes.some((savedNode) => savedNode.id === item.id)), ...nodes,
    ].sort((a, b) => a.record.order_index - b.record.order_index) }));
    setAncestors(parents); setExpanded((current) => new Set([...current, ...parents.map((item) => item.id)]));
    setSelected(node); setMobileDetail(true);
    // 新节点等待导航到正式 ID 后读取，避免旧位置的刷新先清掉新结果。
    if (nextKey === selectedKey) setRefresh((value) => value + 1);
    onNavigate(hierarchyLocation(node));
  };

  const reorder = async (direction: number) => {
    if (!selected || !parent) return;
    const next = [...siblings]; [next[index], next[index + direction]] = [next[index + direction], next[index]];
    setBusy(true); setError("");
    try {
      const response = await apiPatch<{ data: HierarchyRecord[] }>(`${hierarchyChildrenUrl(parent)}/reorder`, { items: next.map((item, order) => ({ [`${item.kind}_id`]: item.id, expected_version: item.record.version, order_index: order + 1 })) });
      setBranches((current) => ({ ...current, [parent.id]: response.data.map((record) => hierarchyNode(selected.kind, record)) }));
      setRefresh((value) => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : t("saveFailed")); }
    finally { setBusy(false); }
  };

  const openIntent = async (action: "delete" | "restore" | "hard") => {
    if (!selected) return;
    setIntent(action); setIntentError(""); setImpact(null);
    if (action !== "restore" && (selected.kind === "arc" || selected.kind === "scene" || selected.kind === "chapter" && action === "hard")) {
      setBusy(true);
      try {
        const result = await apiGet<Record<string, unknown>>(`/api/${selected.kind}s/${selected.id}/delete-impact`);
        if (selected.kind === "chapter" && result.version !== selected.record.version) throw new Error(t("conflict"));
        if (scopeRef.current.active && scopeRef.current.id === selected.id) setImpact(result);
      }
      catch (failure) { if (scopeRef.current.active && scopeRef.current.id === selected.id) setIntentError(failure instanceof Error ? failure.message : t("loadFailed")); }
      finally { setBusy(false); }
    }
  };

  const lifecycle = async () => {
    if (!selected || !intent || busy) return;
    setBusy(true); setIntentError("");
    try {
      if (intent === "restore") await apiPost(`/api/${selected.kind}s/${selected.id}/restore`, { expected_version: selected.record.version });
      else await apiDelete(`/api/${selected.kind}s/${selected.id}${intent === "hard" ? "/hard" : ""}?expected_version=${selected.record.version}${intent === "hard" && selected.kind === "chapter" ? `&expected_revision_count=${impact!.revision_count}` : ""}`);
      setIntent(null); setRefresh((value) => value + 1);
      if (parent) onNavigate(hierarchyLocation(parent));
    } catch (failure) { setIntentError(failure instanceof Error ? failure.message : t("saveFailed")); }
    finally { setBusy(false); }
  };

  const inlineEditor = editor?.source?.id === selected?.id ? editor : null;
  const chapterRecordCount = Number(impact?.chapter_records ?? 0);
  // 章后记录允许来源移入回收站，但仍阻止永久删除；章节影响没有 has_blockers 字段。
  const hasBlockingImpact = Boolean(impact && (intent === "hard"
    ? Boolean(impact.has_blockers) || chapterRecordCount > 0
    : Number(impact.total) - chapterRecordCount > 0)) || Number(impact?.foreshadowings) > 0;
  const actionsDisabled = busy || loading || planSaving || bodySaving || recordsSaving || plotBusy || savedReadFailed || Boolean(inlineEditor);
  const ownsSelected = Boolean(selected && (scope === "arcs" ? selected.kind === "arc" : selected.kind === "scene" || selected.kind === "chapter"));
  const readiness = selected ? readinessById[selected.id] : undefined;
  const canGenerate = Boolean(readiness && (selected?.kind === "chapter" ? readiness.can_write : readiness.can_refine));
  const readingBody = selected?.kind === "chapter" && bodyTab && !recordsTab;
  const creationParents = selected?.kind === "chapter" ? [] : [...(workspaceParent && !workspaceParent.record.is_deleted ? [workspaceParent] : []), ...(scope === "chapters" && selected?.kind === "scene" && !selected.record.is_deleted ? [selected] : [])];
  const blockedNode = [...creationParents, ...(readingBody && selected && !selected.record.is_deleted ? [selected] : [])].find((node) => readinessErrors[node.id] || readinessById[node.id] && !(node.kind === "chapter" ? readinessById[node.id].can_write : readinessById[node.id].can_create_child && readinessById[node.id].can_refine));
  const blockedReadiness = blockedNode ? readinessById[blockedNode.id] : undefined;
  const creationBlocked = blockedNode?.kind !== "chapter" && blockedReadiness?.can_create_child === false;
  const missingFields = (creationBlocked ? blockedReadiness?.create_missing_fields : blockedReadiness?.missing_fields) ?? [];
  const blockers = creationBlocked ? [] : blockedReadiness?.blockers ?? [];
  const needsVolumePlan = blockedNode?.kind === "volume" || missingFields.some((item) => item.field.startsWith("volume."));
  const batchScene = [selected, ...ancestors].find((node) => node?.kind === "scene") ?? null;
  const sceneBatches = batches.sceneId === batchScene?.id ? batches.items : [];
  const chosenBatch = sceneBatches.find((batch) => batch.confirmationKey === batchId) ?? sceneBatches.at(-1);
  const nodeActions = selected && <div className="ml-auto flex flex-wrap gap-2">
    {selected.record.is_deleted ? <>
      <Button size="sm" variant="outline" isDisabled={actionsDisabled} onPress={() => void openIntent("restore")}>{t("restore")}</Button><Button size="sm" variant="ghost" className="text-danger" isDisabled={actionsDisabled} onPress={() => void openIntent("hard")}>{t("hardDelete")}</Button>
    </> : <>
      <TooltipHint text={t("moveUp")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("moveUp")} className="size-11 shrink-0 text-muted sm:size-9" isDisabled={actionsDisabled || index <= 0 || bodyDirty} onPress={() => void reorder(-1)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="m6 10 6-6 6 6M12 4v16" /></svg></Button></TooltipHint>
      <TooltipHint text={t("moveDown")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("moveDown")} className="size-11 shrink-0 text-muted sm:size-9" isDisabled={actionsDisabled || index < 0 || index >= siblings.length - 1 || bodyDirty} onPress={() => void reorder(1)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="m6 14 6 6 6-6M12 4v16" /></svg></Button></TooltipHint>
      <TooltipHint text={t("delete")}><Button isIconOnly size="sm" variant="ghost" aria-label={t("delete")} className="size-11 shrink-0 text-danger sm:size-9" isDisabled={actionsDisabled || bodyDirty} onPress={() => void openIntent("delete")}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg></Button></TooltipHint>
    </>}
  </div>;
  const chapterTabs = selected?.kind === "chapter" && <div role="tablist" aria-label={t("chapterViews")} className="flex min-w-0 max-w-full gap-3 overflow-x-auto">
    {(["plan", "body", "records"] as const).map((tab, index) => {
      const selectedTab = recordsTab ? "records" : bodyTab ? "body" : "plan";
      const tabId = tab === "records" ? "records" : String(tab === "body");
      return <button key={tab} id={`chapter-${selected.id}-tab-${tabId}`} type="button" role="tab" disabled={Boolean(inlineEditor) || bodySaving || recordsSaving || recordsDirty} aria-selected={selectedTab === tab} aria-controls={`hierarchy-${scope}-${selected.id}-panel`} tabIndex={selectedTab === tab ? 0 : -1} className={`min-h-11 shrink-0 border-b-2 px-2 text-sm focus-visible:outline-2 focus-visible:outline-accent ${selectedTab === tab ? "border-accent text-accent" : "border-transparent"}`} onClick={() => { setRecordsTab(tab === "records"); if (tab !== "records") setBodyTab(tab === "body"); }} onKeyDown={(event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault(); const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? 2 : (index + (event.key === "ArrowRight" ? 1 : 2)) % 3;
        setRecordsTab(nextIndex === 2); if (nextIndex !== 2) setBodyTab(nextIndex === 1);
        document.getElementById(`chapter-${selected.id}-tab-${nextIndex === 2 ? "records" : String(nextIndex === 1)}`)?.focus();
      }}>{tab === "records" ? recordsT("title") : t(tab)}</button>;
    })}
  </div>;
  return <div className="@container/hierarchy flex h-full min-h-0 flex-col overflow-hidden">
    <h1 className="sr-only">{t(scope === "arcs" ? "arcTitle" : "chapterTitle")}</h1>
    {/* 窄屏写正文时目录操作留在目录，返回目录仍可选篇章和新建场景。 */}
    <header className={`workspace-toolbar ${generationPage ? "hidden" : mobileDetail && selected?.kind === "chapter" ? "hidden @min-[800px]/hierarchy:flex" : "flex"} shrink-0 flex-wrap items-end gap-3 border-b border-border px-4 py-3 sm:px-6`}>
      <label className="min-w-0 flex-1 basis-52 text-xs text-muted">{t(scope === "arcs" ? "selectVolume" : "selectArc")}
        <select value={workspaceParent?.id ?? ""} disabled={busy || loading || planSaving || bodySaving || recordsSaving || plotBusy} onChange={(event) => { const node = (scope === "arcs" ? volumes : arcs).find((item) => item.id === event.target.value); if (node) choose(node); }} className="mt-1 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground">
          {scope === "arcs" ? volumes.map((node) => <option key={node.id} value={node.id}>{node.record.title}</option>) : <>
            {!arcs.length && <option value="">{t("noArcs")}</option>}
            {arcs.map((node) => <option key={node.id} value={node.id}>{volumes.find((volume) => volume.id === node.record.volume_id)?.record.title} · {node.record.title}</option>)}
          </>}
        </select>
      </label>
      {creationParents.filter((node) => node.kind !== "scene").map((node) => <div key={node.id} className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" isDisabled={actionsDisabled || bodyDirty || !readinessById[node.id]?.can_create_child} onPress={() => setEditor({ kind: CHILD_KIND[node.kind as "volume" | "arc" | "scene"], parent: node, source: null })}>{t("createKind", { kind: t(`kinds.${CHILD_KIND[node.kind as "volume" | "arc" | "scene"]}`) })}</Button>
        <Button size="sm" variant="primary" isDisabled={actionsDisabled || bodyDirty || Boolean(generationNode || continuation?.open) || !readinessById[node.id]?.can_refine} onPress={() => { generationOrigin.current = selectedKey; setGenerationNode(node); }}>{t(`generate.${node.kind}`)}</Button>
      </div>)}
      {scope === "chapters" && !arcs.length && !loading && volumes.length > 0 && <Button size="sm" variant="outline" isDisabled={actionsDisabled} onPress={() => onArc?.({ volume_id: selected?.record.volume_id ?? volumes[0].id })}>{t("openArcPlanning")}</Button>}
      <TooltipHint text={t("showTrash")}>
        <Button isIconOnly size="sm" variant="ghost" aria-label={t("showTrash")} aria-pressed={showTrash} className={`size-11 shrink-0 sm:size-10 ${showTrash ? "border border-accent bg-selected text-accent" : "text-muted"}`} isDisabled={planSaving || bodySaving || recordsSaving} onPress={() => { setShowTrash(!showTrash); if (showTrash && selected?.record.is_deleted && workspaceParent) choose(workspaceParent); }}>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" /></svg>
        </Button>
      </TooltipHint>
      <TooltipHint text={t(savedReadFailed ? "retryRead" : "refresh")}>
        <Button isIconOnly size="sm" variant="ghost" aria-label={t(savedReadFailed ? "retryRead" : "refresh")} className="size-11 shrink-0 text-muted sm:size-10" isDisabled={busy || loading || planSaving || bodySaving || recordsSaving} onPress={() => setRefresh((v) => v + 1)}>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.6-1L20 9M4 15l2.3 3A7 7 0 0 0 17.9 17" /></svg>
        </Button>
      </TooltipHint>
    </header>
    {error && <RelationEditorErrorSummary message={savedReadFailed ? `${t("savedReadFailed")} ${error}` : error} />}
    {blockedNode && <div className="shrink-0 border-b border-border px-4 py-2 sm:px-6">
      {readinessErrors[blockedNode.id] ? <RelationEditorErrorSummary message={readinessErrors[blockedNode.id]} /> : blockedReadiness && <div className="flex flex-wrap items-center gap-2 border-l-2 border-amber-500 px-3 text-sm" role="status">
        <div><p className="font-medium">{t(creationBlocked ? "createBlocked" : "generationBlocked")}</p>{[...missingFields.map((item) => item.message), ...blockers.map((item) => item.message)].map((message) => <p key={message}>{message}</p>)}</div>
        <Button size="sm" variant="ghost" isDisabled={actionsDisabled} onPress={() => {
          if (needsVolumePlan) onVolume(blockedNode.record.volume_id);
          else if (blockedNode.kind === "arc" || missingFields.some((item) => item.field.startsWith("arc."))) onArc?.({ volume_id: blockedNode.record.volume_id, arc_id: blockedNode.record.arc_id });
          else {
            const section = !missingFields.length && blockers.some((blocker) => blocker.code === "WRITING_REFERENCE_UNAVAILABLE") ? "references" : "planning";
            setBodyTab(false); setEditor({ kind: blockedNode.kind as PlanningKind, parent: parent!, source: blockedNode, section });
          }
        }}>{t(needsVolumePlan ? "completeVolume" : "fillMissing")}</Button>
      </div>}
    </div>}
    {bodyDirty && <p className="px-4 py-2 text-sm text-muted sm:px-6">{t("saveBeforeGenerate")}</p>}
    {!volumes.length && !loading && !error && <div className="m-5 border-y border-dashed border-border py-12 text-center"><p>{t("noVolumes")}</p><Button className="mt-4" variant="primary" onPress={() => onVolume("")}>{t("openVolumes")}</Button></div>}
    {loading && !selected && <p className="px-5 py-4" role="status">{t("loading")}</p>}
    <div className={`${generationPage ? "hidden" : "grid"} min-h-0 flex-1 overflow-hidden @min-[800px]/hierarchy:grid-cols-[minmax(240px,280px)_minmax(0,1fr)]`}>
      <aside aria-label={t("tree")} className={`${mobileDetail ? "hidden @min-[800px]/hierarchy:block" : "block"} workspace-scrollbar min-h-0 overflow-y-auto border-r border-border`}>
        <ul role="tree" aria-label={t("tree")} className="py-2">
          {visible.map(({ node, level, parent: treeParent }, position) => {
            const emptyScene = node.kind === "scene" && (branches[node.id] ? !branches[node.id].some((child) => showTrash || !child.record.is_deleted) : !showTrash && node.record.chapter_count === 0);
            const isExpanded = expanded.has(node.id) && !emptyScene;
            return <li key={`${node.kind}:${node.id}`} role="none">
            <div className={`flex min-w-0 items-center border-l-2 ${selected?.id === node.id ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`} style={{ paddingLeft: (level - 1) * 16 }}>
              {node.kind !== "chapter" && !(scope === "arcs" && node.kind === "arc") && !node.record.is_deleted ? <button type="button" tabIndex={-1} disabled={emptyScene} title={emptyScene ? t("noChaptersToExpand") : undefined} aria-label={t(isExpanded ? "collapse" : "expand", { title: node.record.title })} onClick={() => void expand(node)} className="min-h-11 w-8 shrink-0 text-accent disabled:cursor-not-allowed disabled:text-muted disabled:opacity-40">{isExpanded ? "−" : "+"}</button> : <span className="w-8 shrink-0" />}
              <button id={`hierarchy-${scope}-${node.id}`} type="button" role="treeitem" disabled={planSaving || bodySaving || recordsSaving} aria-level={level} aria-selected={selected?.id === node.id} aria-expanded={node.kind !== "chapter" && !(scope === "arcs" && node.kind === "arc") && !node.record.is_deleted ? isExpanded : undefined} tabIndex={selected?.id === node.id || (!visible.some((item) => item.node.id === selected?.id) && position === 0) ? 0 : -1} className="min-h-14 min-w-0 flex-1 px-2 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" onClick={() => choose(node)} onKeyDown={(event) => {
                let target: HierarchyNode | undefined;
                if (event.key === "ArrowDown") target = visible[position + 1]?.node;
                if (event.key === "ArrowUp") target = visible[position - 1]?.node;
                if (event.key === "Home") target = visible[0]?.node;
                if (event.key === "End") target = visible.at(-1)?.node;
                if (event.key === "ArrowRight" && node.kind !== "chapter" && !(scope === "arcs" && node.kind === "arc")) { event.preventDefault(); if (!emptyScene) { if (!isExpanded) void expand(node); else target = visible[position + 1]?.node; } }
                if (event.key === "ArrowLeft") { event.preventDefault(); if (expanded.has(node.id)) void expand(node); else target = treeParent ?? undefined; }
                if (target) { event.preventDefault(); document.getElementById(`hierarchy-${scope}-${target.id}`)?.focus(); }
              }}>
                <span className="block text-sm font-medium [overflow-wrap:anywhere]">{node.record.title}</span>
                <span className="text-xs text-muted">{t(`kinds.${node.kind}`)} {node.kind === "chapter" ? node.record.chapter_number ?? node.record.order_index : node.record.order_index}{node.record.is_deleted ? ` · ${t("trashed")}` : ""}</span>
              </button>
            </div>
          </li>; })}
        </ul>
      </aside>
      <article ref={detailRef} tabIndex={-1} aria-label={t("detail")} className={`${mobileDetail ? "flex" : "hidden @min-[800px]/hierarchy:flex"} workspace-scrollbar min-h-0 min-w-0 flex-col overflow-y-auto px-5 py-3 outline-none sm:px-7`}>
        <Button size="sm" variant="ghost" isDisabled={planSaving || bodySaving || recordsSaving} className="mb-1 self-start @min-[800px]/hierarchy:hidden" onPress={() => { setMobileDetail(false); if (focusPlot && scope === "arcs") onNavigate(location, true); requestAnimationFrame(() => document.getElementById(`hierarchy-${scope}-${selected?.id}`)?.focus()); }}>{t("backToTree")}</Button>
        {selected ? <>
          {ownsSelected && selected.kind !== "chapter" && <header className="mb-3 flex shrink-0 flex-wrap items-center gap-3 border-b border-border pb-2">
            {selected.kind === "arc" && <Button size="sm" variant="ghost" className="text-accent" onPress={() => { const target = document.getElementById(`plot-section-arc-${selected.id}`); target?.focus({ preventScroll: true }); target?.scrollIntoView({ block: "start" }); }}><span aria-hidden="true">↓</span>{plotT("jumpToPlot")}</Button>}
            <p className="text-xs leading-4 tabular-nums text-muted">{t("version", { version: selected.record.version })}{selected.record.is_deleted ? ` · ${t("trashed")}` : ""}</p>
            {selected.kind === "scene" && !selected.record.is_deleted && <section aria-label={t("sceneChapters")} className="workspace-toolbar flex min-w-0 flex-wrap items-center gap-3">
              <h2 className="shrink-0 text-base font-semibold">{t("sceneChapters")}</h2>
              <div className="flex min-w-0 flex-wrap gap-2">
                <Button size="sm" variant="outline" isDisabled={actionsDisabled || !readiness?.can_create_child} onPress={() => setEditor({ kind: "chapter", parent: selected, source: null })}>{t("createKind", { kind: t("kinds.chapter") })}</Button>
                <Button size="sm" variant="primary" isDisabled={actionsDisabled || Boolean(generationNode || continuation?.open) || !readiness?.can_refine} onPress={() => { generationOrigin.current = selectedKey; setGenerationNode(selected); }}>{t("generate.scene")}</Button>
              </div>
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <label className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted">{t("continuation.scope")}
                  <select value={continuationScope} disabled={actionsDisabled || bodyDirty || planDirty} onChange={(event) => setContinuationScope(event.target.value as "scene" | "arc")} className="min-h-11 max-w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-accent">
                    <option value="scene">{t("continuation.scopeScene")}</option>
                    <option value="arc">{t("continuation.scopeArc")}</option>
                  </select>
                </label>
                <Button id={`chapter-continuation-${selected.id}`} size="sm" variant="outline" isDisabled={actionsDisabled || bodyDirty || planDirty || Boolean(generationNode)} onPress={() => {
                  const scene = selected;
                  const arc = ancestors.find((node) => node.kind === "arc");
                  setRecordsTab(false); setBodyTab(true);
                  if (scene && arc) setContinuation({ scene, arc, scope: continuationScope, locationKey: selectedKey, open: true });
                }}>{t("continuation.title")}</Button>
              </div>
            </section>}
            {nodeActions}
          </header>}

          {batchScene && !batchScene.record.is_deleted && selected.kind === "scene" && <>
            {batchError && <div className="mb-3"><RelationEditorErrorSummary message={batchError} /><Button size="sm" variant="outline" onPress={() => setRefresh((value) => value + 1)}>{t("retryRead")}</Button></div>}
            {planRecovery && <Button size="sm" variant="outline" className="mb-3 self-start" isDisabled={Boolean(generationNode) || planSaving || bodyDirty || planDirty} onPress={() => { generationOrigin.current = selectedKey; setGenerationNode(batchScene); }}>{t("continuation.recoverPlanSave")}</Button>}
            {chosenBatch && <section aria-label={t("continuation.savedPlans")} className="mb-4 border-b border-border pb-4">
              <h2 className="mb-3 text-sm font-semibold">{t("continuation.savedPlans")}</h2>
              <div className="workspace-toolbar flex min-w-0 flex-wrap items-end gap-3">
                <label className="min-w-0 flex-1 basis-52 text-xs text-muted">{t("continuation.batch")}
                  <select value={chosenBatch.confirmationKey} disabled={actionsDisabled || bodyDirty || planDirty} onChange={(event) => setBatchId(event.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground">
                    {sceneBatches.map((batch) => <option key={batch.confirmationKey} value={batch.confirmationKey}>{t("continuation.batchOption", { title: batch.records[0].title, count: batch.ids.length })}</option>)}
                  </select>
                </label>
                <Button id={`chapter-batch-${chosenBatch.confirmationKey}`} size="sm" variant="outline" isDisabled={actionsDisabled || bodyDirty || planDirty || Boolean(batchError) || Boolean(generationNode)} onPress={() => {
                  if (!scopeRef.current.active || continuationRef.current?.open && continuationRef.current.locationKey === selectedKey && scopeRef.current.bodyTab) return;
                  setRecordsTab(false); setBodyTab(true);
                  setContinuation({ scene: chosenBatch.scene, arc: chosenBatch.arc, scope: "scene", batch: chosenBatch, locationKey: selectedKey, open: true });
                }}>{t("continuation.chooseBatch")}</Button>
              </div>
            </section>}
          </>}

          {selected.kind === "chapter" && <ChapterBodyEditor key={selected.id} navigation={chapterTabs} bodyActive={readingBody} inactiveActions={nodeActions} panelId={`hierarchy-${scope}-${selected.id}-panel`} node={selected} choices={choices} requestedVersion={location.revision_version} onBusy={setBodySaving} onSaved={(record) => saved([record], "chapter")} onHistorySaved={(record) => {
            const current = scopeRef.current;
            if (!current.active || current.key !== selectedKey || current.id !== record.chapter_id || record.version < selected.record.version) return;
            // 历史恢复只刷新正式资料；草稿、编辑器和脏稿状态仍归原编辑器管理。
            requestId.current += 1;
            confirmedTarget.current = `${novelId}:${scope}:${selectedKey}`;
            setSelected((previous) => previous && previous.id === record.chapter_id && previous.record.version <= record.version ? hierarchyNode("chapter", record) : previous);
            setBranches((previous) => previous[record.scene_id!] ? { ...previous, [record.scene_id!]: previous[record.scene_id!].map((node) => node.id === record.chapter_id && node.record.version <= record.version ? hierarchyNode("chapter", record) : node) } : previous);
            setRefresh((value) => value + 1);
          }} onDirty={setBodyDirty} generationAction={selected.record.is_deleted ? readingBody && nodeActions : bodyTab && <>
            <Button size="sm" variant="outline" isDisabled={actionsDisabled || !canGenerate || bodyDirty || Boolean(generationNode || continuation?.open)} onPress={() => { generationOrigin.current = selectedKey; setGenerationNode(selected); }}>{t("generate.chapter")}</Button>
            {batchScene && <Button size="sm" variant="ghost" isDisabled={actionsDisabled} onPress={() => choose(batchScene)}>{t("openScene")}</Button>}
          </>} />}
          <div id={!readingBody ? `hierarchy-${scope}-${selected.id}-panel` : undefined} role={selected.kind === "chapter" && !readingBody ? "tabpanel" : undefined} aria-labelledby={selected.kind === "chapter" ? `chapter-${selected.id}-tab-${recordsTab ? "records" : bodyTab}` : undefined} className={readingBody ? "hidden" : "flex min-h-0 flex-1 flex-col"}>
            {selected.kind === "chapter" && <div className={recordsTab ? "block" : "hidden"}><RetainedViewActive.Provider value={active && recordsTab}><ChapterRecords key={selected.id} novelId={novelId} chapterId={selected.id} chapter={selected.record} choices={choices} chapterReviewId={chapterReviewId} onNavigateItem={onNavigateItem} refreshToken={refresh} showRefresh={mobileDetail} refreshClassName="@min-[800px]/hierarchy:hidden" onBusy={setRecordsSaving} onDirty={setRecordsDirty} beforeLeaveRef={recordsBeforeLeave} relationCheckVersion={2} /></RetainedViewActive.Provider></div>}

            {ownsSelected && (selected.kind !== "chapter" || !bodyTab && !recordsTab) && <div>
              <div className="space-y-4">
                {PLANNING_SECTIONS.filter((section) => selected.kind !== "volume" || section !== "references").map((section, sectionIndex) => inlineEditor?.section === section
                  ? <PlanningEditor key={`${selected.id}:${section}`} {...inlineEditor} choices={choices} choicesError={choicesError} onDirty={setPlanDirty} onSavingChange={setPlanSaving} onClose={() => { editorFocusTarget.current = { id: selected.id, section }; setEditor(null); }} onSaved={(record) => {
                    // 外层工作区允许作者保留草稿后离开，迟到的保存结果不能抢回页面。
                    if (!scopeRef.current.active || scopeRef.current.id !== selected.id) { setEditor((current) => current?.source?.id === selected.id ? null : current); return; }
                    editorFocusTarget.current = { id: selected.id, section }; saved([record], inlineEditor.kind);
                  }} />
                  : <DocumentSection key={section} number={String(sectionIndex + 1).padStart(2, "0")} title={t(`sections.${section}`)} actions={selected.kind !== "volume" && !selected.record.is_deleted && <SectionEditButton id={`planning-${selected.id}-${section}-edit`} isDisabled={actionsDisabled || bodyDirty} onPress={() => setEditor({ kind: selected.kind as PlanningKind, parent: parent!, source: selected, section })} label={t("sectionEdit", { section: t(`sections.${section}`) })} />}>
                    <PlanningReadout record={selected.record} choices={choices} section={section} />
                  </DocumentSection>)}
                {selected.kind === "arc" && <PlotSection focusPlot={focusPlot && mobileDetail} key={`plot-${selected.id}`} kind="arc" record={selected.record} choices={choices} disabled={busy || loading || planSaving || savedReadFailed || Boolean(inlineEditor)} onBusyChange={setPlotBusy} onRunningChange={setPlotRunning} onSaved={(record) => saved([record as HierarchyRecord], "arc")} />}
              </div>
            </div>}
            {workspaceParent && !visible.length && !loading && <p className="mt-4 border-y border-dashed border-border py-4 text-sm text-muted">{t("emptyChildren", { kind: t(`kinds.${CHILD_KIND[workspaceParent.kind as "volume" | "arc"]}`) })}</p>}
          </div>
        </> : !loading && <p className="py-8 text-sm text-muted">{t("selectNode")}</p>}
      </article>
    </div>
    {editor && !editor.source && <PlanningEditor key={`${editor.kind}:${editor.parent.id}`} {...editor} choices={choices} choicesError={choicesError} onClose={() => setEditor(null)} onSaved={(record) => saved([record], editor.kind)} />}
    {generationNode && <RetainedViewActive.Provider value={active && selectedKey === generationOrigin.current}>
      <HierarchyGeneration onPageChange={setGenerationPage} key={generationNode.id} node={generationNode} choices={choices} choicesError={choicesError}
        planOrigin={generationNode.kind === "scene" ? { scene: generationNode, arc: ancestors.find((node) => node.kind === "arc")!, volume: ancestors.find((node) => node.kind === "volume")! } : undefined}
        onClose={() => setGenerationNode(null)} onSaved={async (records, kind, confirmationKey, confirmedIds, origin) => {
          if (generationNode.kind !== "scene" || kind !== "chapter" || !confirmedIds?.length || !origin) {
            if (records[0] && scopeRef.current.key === generationOrigin.current) saved(records, kind);
            return;
          }
          const batch: SavedChapterBatch = { confirmationKey, ids: confirmedIds, records, ...origin };
          // 成功回执交付前先保存正式批次。失败留给原弹窗恢复，不重发已成功规划。
          const items = await registerSavedChapterBatch(batch, { conflict: t("invalidResult"), failed: t("draftFailed") });
          const current = scopeRef.current;
          if (!current.active || current.novelId !== novelId || current.scope !== scope || current.key !== generationOrigin.current) return;
          batchRead.current += 1;
          setBatches({ sceneId: origin.scene.id, items }); setBatchId(confirmationKey); setBatchError(""); setPlanRecovery(false);
          const nodes = records.map((record) => hierarchyNode("chapter", record));
          setBranches((current) => ({ ...current, [origin.scene.id]: [...(current[origin.scene.id] ?? []).filter((node) => !confirmedIds.includes(node.id)), ...nodes].sort((a, b) => a.record.order_index - b.record.order_index) }));
          setExpanded((current) => new Set([...current, origin.scene.id]));
          confirmedTarget.current = `${novelId}:${scope}:${selectedKey}`;
          requestId.current += 1;
          setRefresh((value) => value + 1);
        }} />
    </RetainedViewActive.Provider>}
    {continuation && <ChapterContinuation onGenerationPageChange={setGenerationPage} key={`${novelId}:${continuation.scope}:${continuation.scope === "arc" ? continuation.arc.id : continuation.scene.id}:${continuation.batch?.confirmationKey ?? "existing"}`} scene={continuation.scene} arc={continuation.arc} scope={continuation.scope} batch={continuation.batch} open={continuation.open && continuation.locationKey === selectedKey && bodyTab} dirty={bodyDirty || planDirty || planSaving || bodySaving} readBlocked={Boolean(error) || savedReadFailed || loading || Boolean(continuation.batch && batchError)} readError={error && savedReadFailed ? `${t("savedReadFailed")} ${error}` : error || (continuation.batch ? batchError : "")} onRetryRead={() => setRefresh((value) => value + 1)} choices={choices} choicesError={choicesError}
      onClose={() => {
        setContinuation((current) => current ? { ...current, open: false } : null);
        requestAnimationFrame(() => { if (scopeRef.current.active && scopeRef.current.key === continuation.locationKey) document.getElementById(continuation.batch ? `chapter-batch-${continuation.batch.confirmationKey}` : `chapter-continuation-${scopeRef.current.id}`)?.focus(); });
      }} onSaved={(record) => {
        if (!scopeRef.current.active || !scopeRef.current.bodyTab || scopeRef.current.key !== continuation.locationKey || continuationRef.current !== continuation || !continuation.open) return;
        requestId.current += 1;
        confirmedTarget.current = `${novelId}:${scope}:${selectedKey}`;
        if (record.chapter_id === selected?.id) {
          setSelected(hierarchyNode("chapter", record));
        }
        // 跨场景保存只更新返回记录所属的已加载目录，不把它塞进启动场景。
        setBranches((current) => current[record.scene_id!] ? ({ ...current, [record.scene_id!]: current[record.scene_id!].map((node) => node.id === record.chapter_id ? hierarchyNode("chapter", record) : node) }) : current);
        setRefresh((value) => value + 1);
      }} />}
    {intent && selected && <ConfirmActionModal title={t(intent === "hard" ? "hardDelete" : intent)} message={<><p>{t(intent === "restore" ? "restoreMessage" : "deleteMessage", { title: selected.record.title })}</p>{intent === "hard" && selected.kind === "chapter" ? <p className="mt-2">{impact ? t("history.deleteImpact", { count: Number(impact.revision_count) }) : t("loading")}</p> : impact && <p className="mt-2">{t("impactCounts", { scenes: Number(impact.scenes ?? 0), chapters: Number(impact.chapters ?? 0) })}</p>}{Number(impact?.foreshadowings) > 0 && <p className="mt-2">{t("foreshadowingDeleteBlocked", { count: Number(impact!.foreshadowings) })}</p>}{chapterRecordCount > 0 && <p className="mt-2">{t(intent === "hard" ? "chapterRecordsDeleteBlocked" : "chapterRecordsPreserved", { count: chapterRecordCount })}</p>}{hasBlockingImpact && !(intent === "hard" && chapterRecordCount > 0) && <p className="mt-2">{t("deleteBlocked")}</p>}</>} confirmText={t(intent === "hard" ? "hardDelete" : intent)} cancelText={t("cancel")} isLoading={busy} isConfirmDisabled={intent !== "restore" && (selected.kind === "arc" || selected.kind === "scene" || selected.kind === "chapter" && intent === "hard") && (!impact || hasBlockingImpact)} danger={intent !== "restore"} error={intentError} onCancel={() => setIntent(null)} onConfirm={() => void lifecycle()} />}
    {pendingNavigation && <ConfirmActionModal title={t("leaveTitle")} message={t("leaveMessage")} confirmText={t("leaveKeepDraft")} cancelText={t("stay")} error={error} isLoading={planSaving || bodySaving || recordsSaving} isConfirmDisabled={planSaving || bodySaving || recordsSaving} onCancel={() => setPendingNavigation(null)} onConfirm={async () => { if (planSaving || bodySaving || recordsSaving) return; try { await recordsBeforeLeave.current?.(); } catch (failure) { setError((failure as Error).message); return; } setEditor(null); onNavigate(hierarchyLocation(pendingNavigation)); setMobileDetail(pendingNavigation.kind !== (scope === "arcs" ? "volume" : "arc")); setPendingNavigation(null); }} />}
  </div>;
}
