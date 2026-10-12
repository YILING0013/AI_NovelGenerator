"use client";

import dynamic from "next/dynamic";
import { useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { ConfirmActionModal } from "@/components/shared/RelationEditorPrimitives";
import { RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";
import type { WorkspaceHistoryTraversal } from "@/components/layout/WorkspacePages";

import { AssistantProvider } from "./assistant/AssistantContext";
import AssistantSidebar from "./assistant/AssistantSidebar";
import type { NavigationTarget } from "@/types/assistant";
import { apiGet } from "@/lib/api";
import { isBusinessId } from "@/types/contracts";
import type { InitializationReadinessResponseV1 } from "@/types/initialization";
import type { WritingSidebarItem } from "@/types/novel";
import type { HierarchyLocation } from "@/types/hierarchy";
import WritingSidebar from "./WritingSidebar";
import WritingFlowProgress, { type FlowNavigationProgress } from "./WritingFlowProgress";
import { useResourceRefresh } from "@/hooks/useResourceRefresh";
import WritingPlaceholder from "./WritingPlaceholder";
import NovelInfoWorkspace from "./novel-info/NovelInfoWorkspace";
import FactionCardsWorkspace from "./factions/FactionCardsWorkspace";
import CharacterCardsWorkspace from "./characters/CharacterCardsWorkspace";
import WorldRulesWorkspace from "./world-rules/WorldRulesWorkspace";
import VolumeWorkspace from "./volumes/VolumeWorkspace";
import LocationsWorkspace, {
  type LocationWorkspaceFilters,
} from "./locations/LocationsWorkspace";
import ItemsWorkspace, {
  type ItemWorkspaceFilters,
} from "./items/ItemsWorkspace";

// 图谱及 D3 依赖仅在用户进入独立关系探索入口时加载，避免扩大其他写作模块的首包。
const EntityGraphWorkspace = dynamic(() => import("./entity-graph/EntityGraphWorkspace"));
const HierarchyWorkspace = dynamic(() => import("./hierarchy/HierarchyWorkspace"));
const ForeshadowingsWorkspace = dynamic(() => import("./foreshadowings/ForeshadowingsWorkspace"));

const WRITING_ITEMS: readonly WritingSidebarItem[] = [
  "novel-info",
  "chapter-editor",
  "arc-planning",
  "volume-planning",
  "character-cards",
  "location-cards",
  "faction-cards",
  "item-cards",
  "rule-cards",
  "foreshadowings",
  "entity-graph",
];

function isWritingItem(value: string | null): value is WritingSidebarItem {
  return value !== null && WRITING_ITEMS.includes(value as WritingSidebarItem);
}

const FACTION_VIEWS = new Set(["profiles", "relations", "trash"]);
const CHARACTER_VIEWS = new Set(["profiles", "relations", "bindings", "trash"]);
const WORLD_RULE_VIEWS = new Set(["rules", "trash"]);
const VOLUME_VIEWS = new Set(["overview", "characters", "factions", "locations", "trash"]);
const LOCATION_VIEWS = new Set(["locations", "trash"]);
const ITEM_VIEWS = new Set(["items", "trash"]);

/** 将查询参数收口为当前工作台允许的 workspace/view 组合。 */
function resolveWritingLocation(
  requestedItem: string | null,
  requestedView: string | null,
): { item: WritingSidebarItem; view: string | null } {
  if (!isWritingItem(requestedItem)) return { item: "novel-info", view: null };
  if (requestedItem === "faction-cards") {
    if (requestedView === null) return { item: requestedItem, view: "profiles" };
    return FACTION_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "character-cards") {
    if (requestedView === null) return { item: requestedItem, view: "profiles" };
    return CHARACTER_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "rule-cards") {
    if (requestedView === null) return { item: requestedItem, view: "rules" };
    return WORLD_RULE_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "volume-planning") {
    if (requestedView === null) return { item: requestedItem, view: "overview" };
    return VOLUME_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "location-cards") {
    if (requestedView === null) return { item: requestedItem, view: "locations" };
    return LOCATION_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "item-cards") {
    if (requestedView === null) return { item: requestedItem, view: "items" };
    return ITEM_VIEWS.has(requestedView)
      ? { item: requestedItem, view: requestedView }
      : { item: "novel-info", view: null };
  }
  if (requestedItem === "foreshadowings") {
    return requestedView === null || requestedView === "active" || requestedView === "trash"
      ? { item: requestedItem, view: requestedView ?? "active" }
      : { item: "novel-info", view: null };
  }
  return requestedView === null
    ? { item: requestedItem, view: null }
    : { item: "novel-info", view: null };
}

/** 构造只含白名单工作区参数的站内相对查询串。 */
function buildWritingHref(
  item: WritingSidebarItem,
  view: string | null,
  volumeId: string | null = null,
): string {
  const params = new URLSearchParams({ workspace: item });
  if (view) params.set("view", view);
  if (volumeId) params.set("volume_id", volumeId);
  return `?${params.toString()}`;
}

interface WritingContentProps {
  mode: "create" | "edit";
  novelId?: string;
  query?: string;
  active?: boolean;
  historyTraversalRef?: RefObject<((event: PopStateEvent, traversal: WorkspaceHistoryTraversal | null) => void) | null>;
}

/**
 * 渲染小说创作页侧栏及当前选中的全书级写作工作台。
 *
 * Args:
 *   mode: 小说创建或编辑模式。
 *   novelId: 已保存小说的 ObjectId，创建模式下可为空。
 *   historyTraversalRef: 持久布局的历史监听器，只交给当前活动工作区处理。
 *
 * Returns:
 *   包含侧栏和当前模块内容区的 React 节点。
 */
export default function WritingContent({ mode, novelId, query, active = true, historyTraversalRef }: WritingContentProps) {
  const pageActive = useContext(RetainedViewActive) && active;
  const hierarchyT = useTranslations("writing.hierarchy");
  const foreshadowingT = useTranslations("writing.foreshadowings");
  const recordsT = useTranslations("writing.chapterRecords");
  const initializationT = useTranslations("writing.initialization");
  const [pendingAssistantHref, setPendingAssistantHref] = useState<string | null>(null);
  const pendingAssistantDecision = useRef<((accepted: boolean) => void) | null>(null);
  const [navigationError, setNavigationError] = useState("");
  const [bodyDirty, setBodyDirty] = useState(false);
  const [workspaceBusy, setWorkspaceBusy] = useState(false);
  const workspaceBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const characterBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const volumeBeforeLeave = useRef<(() => Promise<void>) | null>(null);
  const [pendingItem, setPendingItem] = useState<WritingSidebarItem | null>(null);
  const [pendingTraversal, setPendingTraversal] = useState<WorkspaceHistoryTraversal | null>(null);
  const traversalRequest = useRef<WorkspaceHistoryTraversal | null>(null);
  const restoringHistory = useRef<WorkspaceHistoryTraversal | null>(null);
  const approvedHistory = useRef<WorkspaceHistoryTraversal | null>(null);
  const routeSearchParams = useSearchParams();
  const searchParams = query === undefined ? routeSearchParams : new URLSearchParams(query);
  const requestedItem = searchParams.get("workspace");
  const requestedView = searchParams.get("view");
  const requestedVolumeId = searchParams.get("volume_id");
  const requestedArcId = searchParams.get("arc_id");
  const requestedSceneId = searchParams.get("scene_id");
  const requestedChapterId = searchParams.get("chapter_id");
  const requestedChapterReviewId = searchParams.get("chapter_review_id");
  const requestedRevisionVersion = searchParams.get("revision_version");
  const requestedForeshadowingId = isBusinessId("foreshadowing", searchParams.get("foreshadowing_id")) ? searchParams.get("foreshadowing_id") : null;
  const requestedLocationId = searchParams.get("location_id");
  const requestedLocationFilters: LocationWorkspaceFilters = {
    q: searchParams.get("q") ?? "",
    locationType: searchParams.get("location_type") ?? "all",
    status: searchParams.get("status") === "active" || searchParams.get("status") === "inactive"
      ? searchParams.get("status") as "active" | "inactive"
      : "all",
    parentId: searchParams.get("parent_id") ?? "all",
    factionId: searchParams.get("faction_id") ?? "all",
  };
  const rawRequestedItemId = searchParams.get("item_id");
  const rawItemOwnerId = searchParams.get("owner_id");
  const rawItemFactionId = searchParams.get("faction_id");
  const rawItemLocationId = searchParams.get("current_location_id");
  const requestedItemId = isBusinessId("item", rawRequestedItemId) ? rawRequestedItemId : null;
  const requestedItemFilters: ItemWorkspaceFilters = {
    q: searchParams.get("q") ?? "",
    itemType: searchParams.get("item_type") ?? "all",
    status: ["available", "held", "lost", "destroyed", "consumed"].includes(searchParams.get("status") ?? "")
      ? searchParams.get("status") as ItemWorkspaceFilters["status"]
      : "all",
    ownerId: isBusinessId("character", rawItemOwnerId) ? rawItemOwnerId : "all",
    factionId: isBusinessId("faction", rawItemFactionId) ? rawItemFactionId : "all",
    locationId: isBusinessId("location", rawItemLocationId) ? rawItemLocationId : "all",
  };
  const hasInvalidItemIds = (rawRequestedItemId !== null && !isBusinessId("item", rawRequestedItemId))
    || (rawItemOwnerId !== null && !isBusinessId("character", rawItemOwnerId))
    || (rawItemFactionId !== null && !isBusinessId("faction", rawItemFactionId))
    || (rawItemLocationId !== null && !isBusinessId("location", rawItemLocationId));
  const location = resolveWritingLocation(requestedItem, requestedView);
  const activeItem = location.item;
  const activeView = location.view;
  const inHierarchy = activeItem === "chapter-editor" || activeItem === "arc-planning";
  const [workspaceQueries, setWorkspaceQueries] = useState<Record<string, string>>({});
  const currentQuery = searchParams.toString();
  useEffect(() => {
    if (!pageActive || requestedItem !== "arc-planning" || !(requestedSceneId || requestedChapterId)) return;
    const params = new URLSearchParams(currentQuery);
    params.set("workspace", activeItem);
    params.delete("view");
    if (activeItem === "arc-planning") { params.delete("scene_id"); params.delete("chapter_id"); params.delete("chapter_review_id"); }
    window.history.replaceState({}, "", `?${params}`);
  }, [activeItem, currentQuery, pageActive, requestedChapterId, requestedItem, requestedSceneId, requestedView]);
  // 回到栏目时恢复完整位置，不能把正在生成的章或卷换成另一个目标。
  if (pageActive && workspaceQueries[activeItem] !== currentQuery) {
    setWorkspaceQueries({ ...workspaceQueries, [activeItem]: currentQuery });
  }
  const activeWorkspace = useRef({ pageActive, activeItem, inHierarchy });
  useLayoutEffect(() => {
    activeWorkspace.current = { pageActive, activeItem, inHierarchy };
  }, [pageActive, activeItem, inHierarchy]);

  const keepActiveFacts = useCallback(async () => {
    const current = activeWorkspace.current.activeItem;
    if (current === "character-cards") await characterBeforeLeave.current?.();
    if (current === "volume-planning") await volumeBeforeLeave.current?.();
  }, []);
  useLayoutEffect(() => {
    if (!historyTraversalRef || !pageActive) return;
    const workspacePathname = window.location.pathname;
    const onPop = (event: PopStateEvent, traversal: WorkspaceHistoryTraversal | null) => {
      const restoring = restoringHistory.current;
      if (restoring && traversal?.session === restoring.session && traversal.to === restoring.from) {
        restoringHistory.current = null;
        event.stopImmediatePropagation();
        if (activeItem === "character-cards" || activeItem === "volume-planning") {
          void keepActiveFacts().then(() => { approvedHistory.current = restoring; window.history.go(restoring.to - restoring.from); }).catch((error) => setNavigationError(error.message));
        } else setPendingTraversal(restoring);
        return;
      }
      const approved = approvedHistory.current;
      approvedHistory.current = null;
      if (approved && traversal?.session === approved.session && traversal.from === approved.from && traversal.to === approved.to) { traversalRequest.current = null; return; }
      // 只使用持久布局在本会话真实写入的历史位置，未知或旧会话条目没有可推算的距离。
      if (!traversal || traversal.from === traversal.to) return;
      const targetParams = new URLSearchParams(window.location.search);
      // 物品 dirty 只来自固定确认宿主；同列表内选择、筛选不会卸载它。
      const sameItemsView = window.location.pathname === workspacePathname && activeItem === "item-cards" && activeView === "items"
        && targetParams.get("workspace") === "item-cards" && (targetParams.get("view") ?? "items") === "items";
      if ((activeItem !== "character-cards" && activeItem !== "volume-planning") && (!bodyDirty || (!inHierarchy && activeItem !== "foreshadowings" && activeItem !== "item-cards"))) return;
      if (!restoring && sameItemsView) { traversalRequest.current = null; setPendingTraversal(null); return; }
      // 先恢复原历史项并阻止 Next 切换内容，用户确认后才执行同一次前进/后退。
      event.stopImmediatePropagation();
      // 连续后退也以仍显示的首次源位置恢复；用户最终确认最近一次目标。
      const retainedSource = restoring ?? traversalRequest.current;
      const from = retainedSource?.session === traversal.session ? retainedSource.from : traversal.from;
      restoringHistory.current = { ...traversal, from };
      traversalRequest.current = restoringHistory.current;
      setPendingTraversal(null);
      window.history.go(from - traversal.to);
    };
    historyTraversalRef.current = onPop;
    return () => { if (historyTraversalRef.current === onPop) historyTraversalRef.current = null; };
  }, [bodyDirty, inHierarchy, activeItem, activeView, pageActive, historyTraversalRef, keepActiveFacts]);
  const [readiness, setReadiness] = useState<InitializationReadinessResponseV1 | null>(null);
  const [flowProgress, setFlowProgress] = useState<FlowNavigationProgress | null>(null);
  const [readinessFailure, setReadinessFailure] = useState<{ novelId: string; message: string } | null>(null);
  const readinessError = readinessFailure && readinessFailure.novelId === novelId ? readinessFailure.message : null;
  const [readinessLoading, setReadinessLoading] = useState(false);
  const readinessRequestIdRef = useRef(0);

  const loadReadiness = useCallback(async (signal?: AbortSignal) => {
    if (mode !== "edit" || !novelId) return;
    const requestId = readinessRequestIdRef.current + 1;
    readinessRequestIdRef.current = requestId;
    setReadinessLoading(true);
    try {
      const result = await apiGet<InitializationReadinessResponseV1>(
        `/api/novels/${novelId}/initialization-readiness`,
        { signal },
      );
      if (requestId === readinessRequestIdRef.current) {
        setReadiness(result);
        setReadinessFailure(null);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (requestId === readinessRequestIdRef.current) {
        setReadinessFailure({ novelId, message: error instanceof Error ? error.message : initializationT("loadFailed") });
      }
    } finally {
      if (requestId === readinessRequestIdRef.current) setReadinessLoading(false);
    }
  }, [initializationT, mode, novelId]);
  const readinessRefreshAbort = useRef<AbortController | null>(null);
  useResourceRefresh(novelId, () => {
    readinessRefreshAbort.current?.abort();
    const controller = new AbortController(); readinessRefreshAbort.current = controller;
    return loadReadiness(controller.signal);
  }, pageActive);

  useEffect(() => () => { readinessRefreshAbort.current?.abort(); readinessRequestIdRef.current += 1; }, [novelId]);

  let activeHref = buildWritingHref(activeItem, activeView, requestedVolumeId);
  if (activeItem === "item-cards") {
    const params = new URLSearchParams({ workspace: "item-cards", view: activeView ?? "items" });
    if (requestedVolumeId) params.set("volume_id", requestedVolumeId);
    if (requestedItemId) params.set("item_id", requestedItemId);
    if (requestedItemId && requestedChapterId && requestedChapterReviewId) {
      params.set("chapter_id", requestedChapterId);
      params.set("chapter_review_id", requestedChapterReviewId);
    }
    if (requestedItemFilters.q.trim()) params.set("q", requestedItemFilters.q);
    if (requestedItemFilters.itemType !== "all") params.set("item_type", requestedItemFilters.itemType);
    if (requestedItemFilters.status !== "all") params.set("status", requestedItemFilters.status);
    if (requestedItemFilters.ownerId !== "all") params.set("owner_id", requestedItemFilters.ownerId);
    if (requestedItemFilters.factionId !== "all") params.set("faction_id", requestedItemFilters.factionId);
    if (requestedItemFilters.locationId !== "all") params.set("current_location_id", requestedItemFilters.locationId);
    activeHref = `?${params.toString()}`;
  } else if (activeItem === "location-cards") {
    const params = new URLSearchParams({ workspace: "location-cards", view: activeView ?? "locations" });
    if (requestedVolumeId) params.set("volume_id", requestedVolumeId);
    if (requestedLocationId) params.set("location_id", requestedLocationId);
    if (requestedLocationFilters.q.trim()) params.set("q", requestedLocationFilters.q);
    if (requestedLocationFilters.locationType !== "all") params.set("location_type", requestedLocationFilters.locationType);
    if (requestedLocationFilters.status !== "all") params.set("status", requestedLocationFilters.status);
    if (requestedLocationFilters.parentId !== "all") params.set("parent_id", requestedLocationFilters.parentId);
    if (requestedLocationFilters.factionId !== "all") params.set("faction_id", requestedLocationFilters.factionId);
    activeHref = `?${params.toString()}`;
  }

  useEffect(() => {
    if (pageActive && activeItem === "item-cards" && hasInvalidItemIds) {
      window.history.replaceState({}, "", activeHref);
    }
  }, [activeHref, activeItem, hasInvalidItemIds, pageActive]);

  const nextPhaseReady = Boolean(
    mode === "edit"
    && readiness?.novel_id === novelId
    && readiness?.ready_for_world_and_volume
    && !readinessError,
  );
  const requiresNextPhase = ["rule-cards", "volume-planning", "location-cards", "item-cards"].includes(activeItem);
  const readinessUnknown = mode === "edit" && Boolean(novelId) && (Boolean(readinessError) || readiness?.novel_id !== novelId);

  const navigateTo = useCallback((href: string) => {
    if (!activeWorkspace.current.pageActive) return;
    // 同页工作区切换使用 Next 16 支持的 History API，保留页面布局并让查询参数可深链接。
    const params = new URLSearchParams(href.startsWith("?") ? href.slice(1) : href);
    const next = resolveWritingLocation(params.get("workspace"), params.get("view"));
    const volumeId = params.get("volume_id") ?? requestedVolumeId;
    if (next.item === "arc-planning" || next.item === "chapter-editor") {
      params.set("workspace", next.item); params.delete("view");
      if (volumeId) params.set("volume_id", volumeId);
      if (next.item === "arc-planning") { params.delete("scene_id"); params.delete("chapter_id"); params.delete("chapter_review_id"); }
      window.history.pushState({}, "", `?${params}`);
      return;
    }
    const target = new URLSearchParams(buildWritingHref(next.item, next.view, volumeId).slice(1));
    if (next.item === "item-cards") {
      for (const key of ["item_id", "chapter_id", "chapter_review_id", "q", "item_type", "status", "owner_id", "faction_id", "current_location_id"]) {
        const value = params.get(key);
        if (value) target.set(key, value);
      }
    }
    window.history.pushState({}, "", `?${target}`);
  }, [requestedVolumeId, activeWorkspace]);

  const navigateAssistant = useCallback(async (target: NavigationTarget): Promise<boolean> => {
    if (!novelId) return false;
    return apiGet<{ params: Record<string, string> }>(`/api/novels/${novelId}/assistant/resources/${target.resource_type}/${encodeURIComponent(target.id)}/location`).then(async ({ params }) => {
      if (!activeWorkspace.current.pageActive) return false;
      const href = `?${new URLSearchParams(params)}`;
      setNavigationError("");
      if (bodyDirty) {
        pendingAssistantDecision.current?.(false);
        setPendingAssistantHref(href);
        return new Promise<boolean>((resolve) => { pendingAssistantDecision.current = resolve; });
      }
      await keepActiveFacts();
      window.history.pushState({}, "", href);
      return true;
    }).catch((reason) => { setNavigationError(String(reason)); return false; });
  }, [novelId, bodyDirty, keepActiveFacts]);

  const selectItem = useCallback((item: WritingSidebarItem) => {
    if (workspaceQueries[item] !== undefined) {
      window.history.pushState({}, "", `?${workspaceQueries[item]}`);
      return;
    }
    let defaultView: string | null = null;
    if (item === "volume-planning") defaultView = "overview";
    if (item === "location-cards") defaultView = "locations";
    if (item === "item-cards") defaultView = "items";
    if (item === "rule-cards") defaultView = "rules";
    if (item === "faction-cards" || item === "character-cards") defaultView = "profiles";
    if (item === "chapter-editor" || item === "arc-planning") {
      const params = new URLSearchParams({ workspace: item });
      for (const [key, value] of Object.entries({ volume_id: requestedVolumeId, arc_id: requestedArcId, ...(item === "chapter-editor" ? { scene_id: requestedSceneId, chapter_id: requestedChapterId } : {}) })) if (value) params.set(key, value);
      window.history.pushState({}, "", `?${params}`);
    } else navigateTo(buildWritingHref(item, defaultView, requestedVolumeId));
  }, [navigateTo, requestedVolumeId, requestedArcId, requestedSceneId, requestedChapterId, workspaceQueries]);

  const selectHierarchyLocation = useCallback((next: HierarchyLocation, replace = false) => {
    if (!activeWorkspace.current.pageActive || !activeWorkspace.current.inHierarchy || activeWorkspace.current.activeItem !== activeItem) return;
    const params = new URLSearchParams({ workspace: activeItem });
    for (const [key, value] of Object.entries(next)) if (value) params.set(key, value);
    if (activeItem === "chapter-editor" && next.chapter_id === requestedChapterId && requestedChapterReviewId) params.set("chapter_review_id", requestedChapterReviewId);
    // Next 会复制自己的历史字段；传回 __NA 会被当成内部调用而跳过 URL 同步。
    window.history[replace ? "replaceState" : "pushState"]({}, "", `?${params}`);
  }, [activeItem, activeWorkspace, requestedChapterId, requestedChapterReviewId]);

  const hierarchyDirtyChanged = useCallback((dirty: boolean) => {
    if (activeWorkspace.current.activeItem === activeItem) setBodyDirty(dirty);
  }, [activeItem]);
  const workspaceBusyChanged = useCallback((busy: boolean) => {
    if (activeWorkspace.current.activeItem === activeItem) setWorkspaceBusy(busy);
  }, [activeItem]);

  const selectView = useCallback((item: WritingSidebarItem, view: string) => {
    if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== item) return;
    const params = new URLSearchParams();
    params.set("workspace", item);
    params.set("view", view);
    if (requestedVolumeId) params.set("volume_id", requestedVolumeId);
    navigateTo(`?${params.toString()}`);
  }, [navigateTo, requestedVolumeId, activeWorkspace]);

  const selectVolumeId = useCallback((volumeId: string | null, replace = false) => {
    if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== activeItem) return;
    const href = buildWritingHref(activeItem, activeView, volumeId);
    if (replace) {
      window.history.replaceState({}, "", href);
    } else {
      window.history.pushState({}, "", href);
    }
  }, [activeItem, activeView, activeWorkspace]);

  const selectVolumeLocation = useCallback((
    view: "overview" | "characters" | "factions" | "locations" | "trash",
    volumeId: string | null,
    replace = false,
  ) => {
    if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "volume-planning" || activeWorkspace.current.inHierarchy) return;
    const href = buildWritingHref("volume-planning", view, volumeId);
    if (replace) {
      window.history.replaceState({}, "", href);
    } else {
      window.history.pushState({}, "", href);
    }
  }, [activeWorkspace]);

  const selectLocationWorkspaceLocation = useCallback((
    view: "locations" | "trash",
    locationId: string | null,
    filters: LocationWorkspaceFilters,
    replace = false,
  ) => {
    if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "location-cards") return;
    const params = new URLSearchParams({ workspace: "location-cards", view });
    if (requestedVolumeId) params.set("volume_id", requestedVolumeId);
    if (locationId) params.set("location_id", locationId);
    if (filters.q.trim()) params.set("q", filters.q);
    if (filters.locationType !== "all") params.set("location_type", filters.locationType);
    if (filters.status !== "all") params.set("status", filters.status);
    if (filters.parentId !== "all") params.set("parent_id", filters.parentId);
    if (filters.factionId !== "all") params.set("faction_id", filters.factionId);
    const href = `?${params.toString()}`;
    if (replace) window.history.replaceState({}, "", href);
    else window.history.pushState({}, "", href);
  }, [requestedVolumeId, activeWorkspace]);

  const selectItemWorkspaceLocation = useCallback((
    view: "items" | "trash",
    itemId: string | null,
    filters: ItemWorkspaceFilters,
    replace = false,
  ) => {
    if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "item-cards") return;
    const params = new URLSearchParams({ workspace: "item-cards", view });
    if (requestedVolumeId) params.set("volume_id", requestedVolumeId);
    if (itemId) params.set("item_id", itemId);
    // 筛选不能丢掉关联稿的固定物品；明确选了另一物品或回收站才清除旧关联。
    if (view === "items" && requestedItemId && requestedChapterId && requestedChapterReviewId && (!itemId || itemId === requestedItemId)) {
      params.set("item_id", requestedItemId);
      params.set("chapter_id", requestedChapterId);
      params.set("chapter_review_id", requestedChapterReviewId);
    }
    if (filters.q.trim()) params.set("q", filters.q);
    if (filters.itemType !== "all") params.set("item_type", filters.itemType);
    if (filters.status !== "all") params.set("status", filters.status);
    if (filters.ownerId !== "all") params.set("owner_id", filters.ownerId);
    if (filters.factionId !== "all") params.set("faction_id", filters.factionId);
    if (filters.locationId !== "all") params.set("current_location_id", filters.locationId);
    const href = `?${params.toString()}`;
    if (replace) window.history.replaceState({}, "", href);
    else window.history.pushState({}, "", href);
  }, [requestedVolumeId, requestedItemId, requestedChapterId, requestedChapterReviewId, activeWorkspace]);

  const renderMainArea = () => {
    if (requiresNextPhase && readinessUnknown) {
      return readinessError ? null : <p role="status" className="px-4 py-5 text-sm text-muted sm:px-6">{initializationT("loading")}</p>;
    }
    if (mode === "edit" && novelId && inHierarchy) {
      return <HierarchyWorkspace key={`${novelId}:${activeItem}`} novelId={novelId} scope={activeItem === "arc-planning" ? "arcs" : "chapters"} focusPlot={searchParams.get("focus") === "plot"} location={{ volume_id: requestedVolumeId, arc_id: requestedArcId, ...(activeItem === "chapter-editor" ? { scene_id: requestedSceneId, chapter_id: requestedChapterId, revision_version: requestedRevisionVersion } : {}) }} chapterReviewId={activeItem === "chapter-editor" ? requestedChapterReviewId : null} bodyView={activeItem === "chapter-editor"} onDirtyChange={hierarchyDirtyChanged} onBusyChange={workspaceBusyChanged} beforeLeaveRef={workspaceBeforeLeave} onNavigate={selectHierarchyLocation} onNavigateItem={(itemId, chapterId, reviewId) => {
        if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "chapter-editor") return;
        const href = `?${new URLSearchParams({ workspace: "item-cards", view: "items", item_id: itemId, chapter_id: chapterId, chapter_review_id: reviewId })}`;
        setNavigationError("");
        if (bodyDirty) { setPendingAssistantHref(href); return; }
        navigateTo(href);
      }} onVolume={(volumeId) => navigateTo(buildWritingHref("volume-planning", "overview", volumeId || null))} onArc={(next) => {
        const params = new URLSearchParams({ workspace: "arc-planning" });
        if (next.volume_id) params.set("volume_id", next.volume_id);
        if (next.arc_id) params.set("arc_id", next.arc_id);
        navigateTo(`?${params}`);
      }} />;
    }
    if (activeItem === "novel-info") {
      return (
        <NovelInfoWorkspace
          mode={mode}
          novelId={novelId}
          query={searchParams.toString()}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "faction-cards") {
      return (
        <FactionCardsWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "profiles") as "profiles" | "relations" | "trash"}
          requestedVolumeId={requestedVolumeId}
          onViewChange={(view) => selectView("faction-cards", view)}
          onVolumeIdChange={selectVolumeId}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "character-cards") {
      return (
        <CharacterCardsWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "profiles") as "profiles" | "relations" | "bindings" | "trash"}
          onBusyChange={workspaceBusyChanged}
          beforeLeaveRef={characterBeforeLeave}
          onViewChange={(view) => selectView("character-cards", view)}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "rule-cards" && nextPhaseReady) {
      return (
        <WorldRulesWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "rules") as "rules" | "trash"}
          onViewChange={(view) => selectView("rule-cards", view)}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "volume-planning" && nextPhaseReady) {
      return (
        <VolumeWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "overview") as "overview" | "characters" | "factions" | "locations" | "trash"}
          onBusyChange={workspaceBusyChanged}
          beforeLeaveRef={volumeBeforeLeave}
          requestedVolumeId={requestedVolumeId}
          focusPlot={searchParams.get("focus") === "plot"}
          onViewChange={(view) => selectView("volume-planning", view)}
          onVolumeIdChange={selectVolumeId}
          onLocationChange={selectVolumeLocation}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "location-cards" && nextPhaseReady) {
      return (
        <LocationsWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "locations") as "locations" | "trash"}
          requestedLocationId={requestedLocationId}
          initialFilters={requestedLocationFilters}
          onLocationChange={selectLocationWorkspaceLocation}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "item-cards" && nextPhaseReady) {
      return (
        <ItemsWorkspace
          mode={mode}
          novelId={novelId}
          initialView={(activeView ?? "items") as "items" | "trash"}
          requestedItemId={requestedItemId}
          chapterId={requestedChapterId}
          chapterReviewId={requestedChapterReviewId}
          onNavigateChapter={(chapterId, reviewId) => {
            if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "item-cards") return;
            const href = `?${new URLSearchParams({ workspace: "chapter-editor", chapter_id: chapterId, chapter_review_id: reviewId })}`;
            setNavigationError("");
            if (bodyDirty) { setPendingAssistantHref(href); return; }
            navigateTo(href);
          }}
          initialFilters={requestedItemFilters}
          onItemChange={selectItemWorkspaceLocation}
          onDirtyChange={hierarchyDirtyChanged}
          onBusyChange={workspaceBusyChanged}
          beforeLeaveRef={workspaceBeforeLeave}
          onFormalFactsChanged={() => void loadReadiness()}
        />
      );
    }
    if (activeItem === "entity-graph") {
      return <EntityGraphWorkspace mode={mode} novelId={novelId} />;
    }
    if (activeItem === "foreshadowings" && mode === "edit" && novelId) {
      return <ForeshadowingsWorkspace key={novelId} novelId={novelId} initialView={(activeView ?? "active") as "active" | "trash"} requestedId={requestedForeshadowingId} onLocationChange={(view, identity) => { if (!activeWorkspace.current.pageActive || activeWorkspace.current.activeItem !== "foreshadowings") return; const params = new URLSearchParams({ workspace: "foreshadowings", view }); if (identity) params.set("foreshadowing_id", identity); window.history.pushState({}, "", `?${params}`); }} onDirtyChange={hierarchyDirtyChanged} onBusyChange={workspaceBusyChanged} beforeLeaveRef={workspaceBeforeLeave} />;
    }
    return (
      <WritingPlaceholder
        moduleKey={activeItem}
        phaseGate={
          activeItem === "rule-cards" || activeItem === "volume-planning" || activeItem === "location-cards" || activeItem === "item-cards"
            ? nextPhaseReady
            : undefined
        }
      />
    );
  };

  return (
    // 顶栏的下边框占据 1px，工作区同步扣除，避免页面产生无意义的整页滚动条。
    <AssistantProvider key={novelId ?? "new"} novelId={mode === "edit" ? novelId : undefined} active={pageActive} onNavigate={navigateAssistant}
      initialFocus={searchParams.get("assistant_kind") && searchParams.get("assistant_id") ? { resource_type: searchParams.get("assistant_kind") as NavigationTarget["resource_type"], id: searchParams.get("assistant_id")!, deleted: searchParams.get("assistant_deleted") === "true" } : undefined}>
    <div className="flex h-[calc(100dvh-3.5rem-1px)] w-full min-w-0 max-w-full flex-col overflow-x-clip [contain:inline-size] md:flex-row">
      <WritingSidebar
        readiness={readiness?.novel_id === novelId && !readinessError ? readiness : null}
        progress={flowProgress?.novelId === novelId && !readinessError ? flowProgress : null}
        flow={mode === "edit" && novelId ? <WritingFlowProgress novelId={novelId} readiness={readiness} activeHref={searchParams.toString()} disabled={workspaceBusy || Boolean(readinessError)} onProgressChange={setFlowProgress} onNavigate={(href) => {
          if (bodyDirty) { setPendingAssistantHref(href); return; }
          void keepActiveFacts().then(() => navigateTo(href)).catch((failure) => setNavigationError(failure.message));
        }} /> : undefined}
        activeItem={activeItem}
        onSelect={(item) => workspaceBusy ? undefined : bodyDirty ? setPendingItem(item) : activeItem === "character-cards" || activeItem === "volume-planning" ? void keepActiveFacts().then(() => selectItem(item)).catch((error) => setNavigationError(error.message)) : selectItem(item)}
        nextPhaseReady={nextPhaseReady}
        nextPhaseBlockedReason={readinessUnknown ? readinessError ?? initializationT("loading") : undefined}
      />
      <div className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden">
      <div data-assistant-workspaces className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {navigationError && <p role="alert" className="px-4 py-2 text-sm text-danger">{navigationError}</p>}
        {readinessError && <div role="alert" className="flex shrink-0 flex-wrap items-center gap-3 border-y border-red-500/40 px-4 py-3 text-sm text-red-700 dark:text-red-300 sm:px-6">
          <p className="min-w-0 flex-1 break-words">{readinessError}</p>
          <Button size="sm" variant="outline" isDisabled={readinessLoading} onPress={() => void loadReadiness()}>{initializationT(readinessLoading ? "refreshing" : "retry")}</Button>
        </div>}
        {/* 读取失败只隐藏已经打开的工作台，重试恢复时继续使用原候选和草稿。 */}
        <RetainedViews key={novelId ?? "new"} activeKey={requiresNextPhase && readinessError ? null : activeItem}>
          {renderMainArea()}
        </RetainedViews>
      </div>
      <AssistantSidebar />
      </div>
      {pendingAssistantHref && <ConfirmActionModal error={navigationError} title={activeItem === "item-cards" ? recordsT("review.leaveTitle") : activeItem === "foreshadowings" ? foreshadowingT("leaveTitle") : hierarchyT("leaveTitle")} message={activeItem === "item-cards" ? recordsT("review.leaveMessage") : activeItem === "foreshadowings" ? foreshadowingT("leaveMessage") : hierarchyT("leaveMessage")} confirmText={hierarchyT("leaveKeepDraft")} cancelText={hierarchyT("stay")} onCancel={() => { setPendingAssistantHref(null); pendingAssistantDecision.current?.(false); }} isConfirmDisabled={workspaceBusy} onConfirm={async () => { try { await workspaceBeforeLeave.current?.(); } catch (failure) { setNavigationError((failure as Error).message); return; } window.history.pushState({}, "", pendingAssistantHref); setPendingAssistantHref(null); setBodyDirty(false); pendingAssistantDecision.current?.(true); }} />}
      {pendingItem && <ConfirmActionModal error={navigationError} title={activeItem === "item-cards" ? recordsT("review.leaveTitle") : activeItem === "foreshadowings" ? foreshadowingT("leaveTitle") : hierarchyT("leaveTitle")} message={activeItem === "item-cards" ? recordsT("review.leaveMessage") : activeItem === "foreshadowings" ? foreshadowingT("leaveMessage") : hierarchyT("leaveMessage")} confirmText={hierarchyT("leaveKeepDraft")} cancelText={hierarchyT("stay")} onCancel={() => setPendingItem(null)} isConfirmDisabled={workspaceBusy} onConfirm={async () => { try { await workspaceBeforeLeave.current?.(); } catch (failure) { setNavigationError((failure as Error).message); return; } selectItem(pendingItem); setPendingItem(null); setBodyDirty(false); }} />}
      {pendingTraversal !== null && <ConfirmActionModal error={navigationError} title={activeItem === "item-cards" ? recordsT("review.leaveTitle") : activeItem === "foreshadowings" ? foreshadowingT("leaveTitle") : hierarchyT("leaveTitle")} message={activeItem === "item-cards" ? recordsT("review.leaveMessage") : activeItem === "foreshadowings" ? foreshadowingT("leaveMessage") : hierarchyT("leaveMessage")} confirmText={hierarchyT("leaveKeepDraft")} cancelText={hierarchyT("stay")} onCancel={() => { traversalRequest.current = null; setPendingTraversal(null); }} isConfirmDisabled={workspaceBusy} onConfirm={async () => {
        const atSource = () => traversalRequest.current === pendingTraversal && !restoringHistory.current && window.history.state?.workspaceHistorySession === pendingTraversal.session && window.history.state?.writingHierarchyIndex === pendingTraversal.from;
        if (!atSource()) return;
        try { await workspaceBeforeLeave.current?.(); } catch (failure) { setNavigationError((failure as Error).message); return; }
        if (!atSource()) return;
        approvedHistory.current = pendingTraversal; window.history.go(pendingTraversal.to - pendingTraversal.from); setPendingTraversal(null);
      }} />}
    </div>
    </AssistantProvider>
  );
}
