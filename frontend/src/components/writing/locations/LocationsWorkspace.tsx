"use client";
import { useAssistantRefresh, useAssistantResource } from "@/components/writing/assistant/AssistantContext";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import {
  ConfirmActionModal,
  focusRelationEditorError,
  RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  ApiRequestError,
  type ApiFieldErrors,
} from "@/lib/api";
import { formatStableReferenceLabel } from "@/types/contracts";
import {
  parseActiveLocationListV1,
  parseLocationDeleteImpactV1,
  parseLocationHardDeleteResponseV1,
  parseLocationReadV1,
  parseTrashLocationListV1,
  type LocationCreateV1,
  type LocationDeleteImpactV1,
  type LocationFieldsV1,
  type LocationReadV1,
  type LocationStatus,
} from "@/types/location";
import type { CoreFaction } from "@/types/novel";
import type { WorldRuleReadV1 } from "@/types/worldRule";
import LocationFieldsForm, { type LocationEditorSection } from "./LocationFieldsForm";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import TagList from "@/components/shared/TagList";

export type LocationsWorkspaceView = "locations" | "trash";

export interface LocationWorkspaceFilters {
  q: string;
  locationType: string;
  status: "all" | LocationStatus;
  parentId: string;
  factionId: string;
}

interface LocationsWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: LocationsWorkspaceView;
  requestedLocationId?: string | null;
  initialFilters?: Partial<LocationWorkspaceFilters>;
  onLocationChange?: (
    view: LocationsWorkspaceView,
    locationId: string | null,
    filters: LocationWorkspaceFilters,
    replace?: boolean,
  ) => void;
  onFormalFactsChanged?: () => void;
}

type LocationEditorState = { mode: "create"; source: null };

interface LocationInlineSession {
  section: LocationEditorSection;
  source: LocationReadV1;
  draft: LocationFieldsV1;
  error: string;
  fieldErrors: ApiFieldErrors;
}

const SECTION_FIELDS: Record<LocationEditorSection, (keyof LocationFieldsV1)[]> = {
  identity: ["name", "aliases", "location_type", "parent_location_id", "description", "tags", "status"],
  setting: ["environment", "atmosphere", "geography"],
  references: ["rules_and_constraints", "applicable_rule_ids", "associated_faction_ids"],
  story: ["story_function"],
};

type ConfirmIntent =
  | { kind: "soft-delete"; location: LocationReadV1 }
  | { kind: "restore"; location: LocationReadV1 }
  | { kind: "hard-delete"; location: LocationReadV1 };

interface LocationTreeRow {
  location: LocationReadV1;
  depth: number;
}

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const FILTER_CLASS =
  "min-h-10 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";
const TAB_PREFIX = "locations-workspace";
const LOCATION_STATUSES: LocationStatus[] = ["active", "inactive"];
const EMPTY_LOCATIONS: LocationReadV1[] = [];
const EMPTY_RULES: WorldRuleReadV1[] = [];
const EMPTY_FACTIONS: CoreFaction[] = [];
const DEFAULT_FILTERS: LocationWorkspaceFilters = {
  q: "",
  locationType: "all",
  status: "all",
  parentId: "all",
  factionId: "all",
};
const EMPTY_LOCATION: LocationFieldsV1 = {
  name: "",
  aliases: [],
  location_type: "",
  parent_location_id: null,
  description: "",
  environment: "",
  atmosphere: "",
  geography: "",
  rules_and_constraints: [],
  applicable_rule_ids: [],
  associated_faction_ids: [],
  story_function: "",
  status: "active",
  tags: [],
};

/**
 * 渲染正式地点的层级名册、连续详情和生命周期操作。
 *
 * Args:
 *   mode: 当前小说处于创建态或正式编辑态。
 *   novelId: 已保存小说的 ObjectId。
 *   initialView: 初始展示正式地点或回收站。
 *   requestedLocationId: URL 中请求的稳定地点 ID。
 *   initialFilters: URL 中恢复的地点筛选条件。
 *   onLocationChange: 选择、筛选或切换视图后原子同步 URL。
 *   onFormalFactsChanged: 正式地点写入成功后通知上层刷新事实状态。
 *
 * Returns:
 *   支持父子层级、完整同父重排、回收站和危险影响确认的地点工作台。
 */
export default function LocationsWorkspace({
  mode,
  novelId,
  initialView = "locations",
  requestedLocationId = null,
  initialFilters,
  onLocationChange,
  onFormalFactsChanged,
}: LocationsWorkspaceProps) {
  const t = useTranslations("writing.locations");
  const tLayout = useTranslations("writing.listLayout");
  const [inlineSessions, setInlineSessions] = useState<Record<string, LocationInlineSession | undefined>>({});
  const [listCollapsed, setListCollapsed] = useState(false);
  const [wideLayout, setWideLayout] = useState(false);
  const workspaceRef = useRef<HTMLElement>(null);
  const [view, setView] = useState<LocationsWorkspaceView>(initialView);
  const [filters, setFilters] = useState<LocationWorkspaceFilters>({
    ...DEFAULT_FILTERS,
    ...initialFilters,
  });
  const [storedLocations, setLocations] = useState<LocationReadV1[]>([]);
  const [storedTrash, setTrash] = useState<LocationReadV1[]>([]);
  const [storedRules, setRules] = useState<WorldRuleReadV1[]>([]);
  const [storedFactions, setFactions] = useState<CoreFaction[]>([]);
  const [loadedNovelId, setLoadedNovelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [pageActionError, setPageActionError] = useState("");
  const [selectedLocationId, setSelectedLocationId] = useState("");
  const [invalidRequestedId, setInvalidRequestedId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [editor, setEditor] = useState<LocationEditorState | null>(null);
  const [draft, setDraft] = useState<LocationFieldsV1>(EMPTY_LOCATION);
  const [editorError, setEditorError] = useState("");
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [confirmIntent, setConfirmIntent] = useState<ConfirmIntent | null>(null);
  const [impact, setImpact] = useState<LocationDeleteImpactV1 | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [detachChildren, setDetachChildren] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [actionLocationId, setActionLocationId] = useState("");
  const createCommandRef = useRef<{ fingerprint: string; key: string } | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadRequestIdRef = useRef(0);
  const commandAbortRef = useRef<AbortController | null>(null);
  const commandRequestIdRef = useRef(0);
  const currentNovelIdRef = useRef(novelId);
  const previousNovelIdRef = useRef(novelId);
  const previousRequestedIdRef = useRef(requestedLocationId);
  // 消费键包含视图与筛选；本地选择不能改写它，否则父级回放新 URL 前，旧深链会覆盖用户刚选中的地点。
  const appliedRequestedKeyRef = useRef<string | null>(null);
  currentNovelIdRef.current = novelId;
  const initialQ = initialFilters?.q ?? DEFAULT_FILTERS.q;
  const initialLocationType = initialFilters?.locationType ?? DEFAULT_FILTERS.locationType;
  const initialStatus = initialFilters?.status ?? DEFAULT_FILTERS.status;
  const initialParentId = initialFilters?.parentId ?? DEFAULT_FILTERS.parentId;
  const initialFactionId = initialFilters?.factionId ?? DEFAULT_FILTERS.factionId;

  const workspaceReady = loadedNovelId === novelId;
  const locations = workspaceReady ? storedLocations : EMPTY_LOCATIONS;
  const trash = workspaceReady ? storedTrash : EMPTY_LOCATIONS;
  const rules = workspaceReady ? storedRules : EMPTY_RULES;
  const factions = workspaceReady ? storedFactions : EMPTY_FACTIONS;
  const sourceLocations = view === "locations" ? locations : trash;
  const canUseSavedNovel = mode === "edit" && Boolean(novelId);
  const busy = loading || saving || impactLoading || Boolean(actionLocationId);
  useEffect(() => {
    const element = workspaceRef.current?.querySelector<HTMLElement>(`#${TAB_PREFIX}-${view}-panel`);
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWideLayout(entry.contentRect.width >= 800);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [view, canUseSavedNovel, novelId]);
  const hideList = listCollapsed && wideLayout;

  const loadWorkspace = useCallback(async () => {
    if (!novelId || mode !== "edit") return;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = loadRequestIdRef.current + 1;
    const requestNovelId = novelId;
    loadAbortRef.current = controller;
    loadRequestIdRef.current = requestId;
    setLoading(true);
    setDataError("");
    try {
      const [activeResult, trashResult, rulesResult, factionsResult] = await Promise.all([
        apiGet<unknown>(`/api/locations/novel/${novelId}`, { signal: controller.signal }),
        apiGet<unknown>(`/api/locations/novel/${novelId}/trash`, { signal: controller.signal }),
        apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}`, { signal: controller.signal }),
      ]);
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      const nextLocations = parseActiveLocationListV1(activeResult, requestNovelId);
      const nextTrash = parseTrashLocationListV1(trashResult, requestNovelId);
      setLocations(nextLocations);
      setTrash(nextTrash);
      setRules(rulesResult);
      setFactions(factionsResult.data);
      setLoadedNovelId(requestNovelId);
    } catch (error) {
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      setDataError(error instanceof Error ? error.message : t("errors.load"));
    } finally {
      if (
        !controller.signal.aborted
        && loadAbortRef.current === controller
        && loadRequestIdRef.current === requestId
        && currentNovelIdRef.current === requestNovelId
      ) setLoading(false);
    }
  }, [mode, novelId, t]);

  useAssistantRefresh(novelId, loadWorkspace);

  useEffect(() => {
    const novelChanged = previousNovelIdRef.current !== novelId;
    previousNovelIdRef.current = novelId;
    if (novelChanged) {
      loadAbortRef.current?.abort();
      loadRequestIdRef.current += 1;
      commandAbortRef.current?.abort();
      commandRequestIdRef.current += 1;
      setLoadedNovelId(null);
      setLocations([]);
      setTrash([]);
      setRules([]);
      setFactions([]);
      setSelectedLocationId("");
      appliedRequestedKeyRef.current = null;
      setInvalidRequestedId("");
      setMobileDetailOpen(false);
      setEditor(null);
      setInlineSessions({});
      setConfirmIntent(null);
      setSaving(false);
      setImpactLoading(false);
      setActionLocationId("");
      createCommandRef.current = null;
      setPageActionError("");
    }
    void loadWorkspace();
    return () => loadAbortRef.current?.abort();
  }, [loadWorkspace, novelId]);

  useEffect(() => () => {
    commandAbortRef.current?.abort();
    commandRequestIdRef.current += 1;
  }, []);

  useEffect(() => {
    setView(initialView);
    setMobileDetailOpen(false);
    setConfirmIntent(null);
  }, [initialView]);


  useEffect(() => {
    const next: LocationWorkspaceFilters = {
      q: initialQ,
      locationType: initialLocationType,
      status: initialStatus,
      parentId: initialParentId,
      factionId: initialFactionId,
    };
    setFilters((current) => (
      current.q === next.q
      && current.locationType === next.locationType
      && current.status === next.status
      && current.parentId === next.parentId
      && current.factionId === next.factionId
        ? current
        : next
    ));
  }, [initialFactionId, initialLocationType, initialParentId, initialQ, initialStatus]);

  useEffect(() => {
    if (previousRequestedIdRef.current !== requestedLocationId) {
      previousRequestedIdRef.current = requestedLocationId;
      appliedRequestedKeyRef.current = null;
      // replaceState 清理非法 ID 后仍保留 404，直到用户明确返回名册。
      if (requestedLocationId) setInvalidRequestedId("");
    }
  }, [requestedLocationId]);

  const rows = useMemo(() => {
    const normalizedSearch = filters.q.trim().toLowerCase();
    const matches = (location: LocationReadV1) => (
      (!normalizedSearch || [location.name, location.description, location.location_type, ...location.aliases, ...location.tags]
        .some((value) => value.toLowerCase().includes(normalizedSearch)))
      && (filters.locationType === "all" || location.location_type === filters.locationType)
      && (filters.status === "all" || location.status === filters.status)
      && (filters.parentId === "all"
        || (filters.parentId === "root" ? location.parent_location_id === null : location.parent_location_id === filters.parentId))
      && (filters.factionId === "all" || location.associated_faction_ids.includes(filters.factionId))
    );
    if (view === "trash") {
      return sourceLocations
        .filter(matches)
        .sort((left, right) => left.name.localeCompare(right.name))
        .map((location) => ({ location, depth: 0 }));
    }

    const byParent = new Map<string, LocationReadV1[]>();
    const byId = new Map(sourceLocations.map((location) => [location.location_id, location]));
    for (const location of sourceLocations) {
      const parentKey = location.parent_location_id ?? "__root__";
      byParent.set(parentKey, [...(byParent.get(parentKey) ?? []), location]);
    }
    for (const siblings of byParent.values()) {
      siblings.sort((left, right) => left.order_index - right.order_index);
    }
    const included = new Set<string>();
    for (const location of sourceLocations.filter(matches)) {
      included.add(location.location_id);
      let parentId = location.parent_location_id;
      while (parentId) {
        included.add(parentId);
        parentId = byId.get(parentId)?.parent_location_id ?? null;
      }
    }
    const flattened: LocationTreeRow[] = [];
    const appendChildren = (parentId: string | null, depth: number) => {
      for (const location of byParent.get(parentId ?? "__root__") ?? []) {
        if (!included.has(location.location_id)) continue;
        flattened.push({ location, depth });
        appendChildren(location.location_id, depth + 1);
      }
    };
    appendChildren(null, 0);
    return flattened;
  }, [filters, sourceLocations, view]);

  const filtersActive = filters.q.trim() !== ""
    || filters.locationType !== "all"
    || filters.status !== "all"
    || filters.parentId !== "all"
    || filters.factionId !== "all";
  const rowIds = useMemo(() => new Set(rows.map((row) => row.location.location_id)), [rows]);
  const selectedLocation = rows.find((row) => row.location.location_id === selectedLocationId)?.location ?? null;
  const inlineSession = selectedLocation ? inlineSessions[selectedLocation.location_id] : undefined;
  useAssistantResource(selectedLocation ? { resource_type: "location", id: selectedLocation.location_id, name: selectedLocation.name, version: selectedLocation.version, draft: inlineSession ? { text: JSON.stringify(inlineSession.draft), fields: Object.keys(inlineSession.draft), version: inlineSession.source.version } : undefined } : null);
  const requestedSelectionKey = requestedLocationId
    ? JSON.stringify([
      view,
      requestedLocationId,
      filters.q,
      filters.locationType,
      filters.status,
      filters.parentId,
      filters.factionId,
    ])
    : null;

  useEffect(() => {
    if (
      !workspaceReady
      || loading
      || view !== initialView
      || filters.q !== initialQ
      || filters.locationType !== initialLocationType
      || filters.status !== initialStatus
      || filters.parentId !== initialParentId
      || filters.factionId !== initialFactionId
    ) return;
    if (requestedLocationId) {
      if (appliedRequestedKeyRef.current === requestedSelectionKey) {
        if (!rowIds.has(selectedLocationId)) {
          setSelectedLocationId(rows[0]?.location.location_id ?? "");
        }
        return;
      }
      if (rowIds.has(requestedLocationId)) {
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedLocationId(requestedLocationId);
        setInvalidRequestedId("");
      } else if (sourceLocations.some((location) => location.location_id === requestedLocationId)) {
        // 地点仍存在但被当前筛选排除时清理 URL 选中项，避免名册与详情指向不同地点。
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedLocationId(rows[0]?.location.location_id ?? "");
        setInvalidRequestedId("");
        onLocationChange?.(view, null, filters, true);
      } else if (invalidRequestedId !== requestedLocationId) {
        appliedRequestedKeyRef.current = requestedSelectionKey;
        setSelectedLocationId("");
        setInvalidRequestedId(requestedLocationId);
        onLocationChange?.(view, null, filters, true);
      }
      return;
    }
    if (!rowIds.has(selectedLocationId)) {
      setSelectedLocationId(rows[0]?.location.location_id ?? "");
    }
  }, [filters, initialFactionId, initialLocationType, initialParentId, initialQ, initialStatus, initialView, invalidRequestedId, loading, onLocationChange, requestedLocationId, requestedSelectionKey, rowIds, rows, selectedLocationId, sourceLocations, view, workspaceReady]);

  const locationTypes = useMemo(
    () => Array.from(new Set([...locations, ...trash].map((location) => location.location_type))).sort(),
    [locations, trash],
  );
  const locationNames = useMemo(
    () => new Map([...locations, ...trash].map((location) => [location.location_id, location.name])),
    [locations, trash],
  );
  const ruleNames = useMemo(() => new Map(rules.map((rule) => [rule.rule_id, rule.name])), [rules]);
  const factionNames = useMemo(() => new Map(factions.map((faction) => [faction.faction_id, faction.name])), [factions]);

  const updateFilters = (next: LocationWorkspaceFilters) => {
    if (saving) return;
    if (requestedLocationId) {
      appliedRequestedKeyRef.current = JSON.stringify([
        view,
        requestedLocationId,
        next.q,
        next.locationType,
        next.status,
        next.parentId,
        next.factionId,
      ]);
    }
    setFilters(next);
    // 筛选与 location_id 必须在同一次 History 写入中保持一致；新结果首项只作为本地默认，不写入旧 ID。
    setSelectedLocationId("");
    setInvalidRequestedId("");
    setMobileDetailOpen(false);
    onLocationChange?.(view, null, next, false);
  };

  const changeView = (nextView: LocationsWorkspaceView) => {
    if (saving) return;
    if (nextView === view) return;
    if (requestedLocationId) {
      appliedRequestedKeyRef.current = JSON.stringify([
        nextView,
        requestedLocationId,
        filters.q,
        filters.locationType,
        filters.status,
        filters.parentId,
        filters.factionId,
      ]);
    }
    setView(nextView);
    setSelectedLocationId("");
    setInvalidRequestedId("");
    setMobileDetailOpen(false);
    setPageActionError("");
    onLocationChange?.(nextView, null, filters, false);
  };

  const selectLocation = (locationId: string) => {
    if (saving) return;
    setSelectedLocationId(locationId);
    setInvalidRequestedId("");
    setMobileDetailOpen(true);
    onLocationChange?.(view, locationId, filters, false);
    requestAnimationFrame(() => {
      const detail = document.getElementById(`location-detail-${locationId}`);
      if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
        detail.focus();
      }
    });
  };

  const openCreate = () => {
    setDraft({ ...EMPTY_LOCATION, aliases: [], rules_and_constraints: [], applicable_rule_ids: [], associated_faction_ids: [], tags: [] });
    setEditor({ mode: "create", source: null });
    setEditorError("");
    setEditorFieldErrors({});
    createCommandRef.current = null;
  };

  const openEdit = (location: LocationReadV1, section: LocationEditorSection) => {
    if (busy || inlineSessions[location.location_id]) return;
    const nextDraft = {
      name: location.name,
      aliases: [...location.aliases],
      location_type: location.location_type,
      parent_location_id: location.parent_location_id,
      description: location.description,
      environment: location.environment,
      atmosphere: location.atmosphere,
      geography: location.geography,
      rules_and_constraints: [...location.rules_and_constraints],
      applicable_rule_ids: [...location.applicable_rule_ids],
      associated_faction_ids: [...location.associated_faction_ids],
      story_function: location.story_function,
      status: location.status,
      tags: [...location.tags],
    };
    // 草稿保留开始编辑时的版本；刷新资料不能悄悄改变保存基准。
    setInlineSessions((current) => ({ ...current, [location.location_id]: { section, source: location, draft: nextDraft, error: "", fieldErrors: {} } }));
    requestAnimationFrame(() => document.getElementById(`location-editor-${location.location_id}`)?.querySelector<HTMLElement>("input, select, textarea")?.focus());
  };

  const descendantIds = useMemo(() => {
    if (!inlineSession) return new Set<string>();
    const excluded = new Set([inlineSession.source.location_id]);
    let changed = true;
    while (changed) {
      changed = false;
      for (const location of locations) {
        if (location.parent_location_id && excluded.has(location.parent_location_id) && !excluded.has(location.location_id)) {
          excluded.add(location.location_id);
          changed = true;
        }
      }
    }
    return excluded;
  }, [inlineSession, locations]);

  const closeEditor = () => {
    if (saving) return;
    setEditor(null);
    setEditorError("");
    setEditorFieldErrors({});
  };

  const saveEditor = async (session?: LocationInlineSession) => {
    const targetEditor = session ? { mode: "edit" as const, source: session.source } : editor;
    const targetDraft = session?.draft ?? draft;
    const reportError = (message: string, errors: ApiFieldErrors = {}) => {
      if (!session) {
        setEditorError(message);
        setEditorFieldErrors(errors);
        if (message) focusRelationEditorError(errors);
        return;
      }
      setInlineSessions((current) => ({ ...current, [session.source.location_id]: { ...session, error: message, fieldErrors: errors } }));
      if (message) requestAnimationFrame(() => {
        const root = document.getElementById(`location-editor-${session.source.location_id}`);
        const field = Object.keys(errors)[0];
        const target = (field ? root?.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`) : null) ?? root?.querySelector<HTMLElement>("[data-editor-error-summary]");
        target?.focus();
      });
    };
    if (!targetEditor || !novelId) return;
    const fieldErrors: ApiFieldErrors = {};
    if (!targetDraft.name.trim()) fieldErrors.name = [t("validation.nameRequired")];
    if (!targetDraft.location_type.trim()) fieldErrors.location_type = [t("validation.typeRequired")];
    if (!targetDraft.description.trim()) fieldErrors.description = [t("validation.descriptionRequired")];
    if (session) {
      for (const field of Object.keys(fieldErrors)) if (!SECTION_FIELDS[session.section].includes(field as keyof LocationFieldsV1)) delete fieldErrors[field];
    }
    if (Object.keys(fieldErrors).length > 0) {
      reportError(t("errors.validation"), fieldErrors);
      return;
    }
    const payload: LocationCreateV1 = {
      name: targetDraft.name.normalize("NFKC").trim(),
      aliases: targetDraft.aliases.map((item) => item.normalize("NFKC").trim()),
      location_type: targetDraft.location_type.normalize("NFKC").trim(),
      parent_location_id: targetDraft.parent_location_id,
      description: targetDraft.description.normalize("NFKC").trim(),
      environment: targetDraft.environment.normalize("NFKC").trim(),
      atmosphere: targetDraft.atmosphere.normalize("NFKC").trim(),
      geography: targetDraft.geography.normalize("NFKC").trim(),
      rules_and_constraints: targetDraft.rules_and_constraints.map((item) => item.normalize("NFKC").trim()),
      applicable_rule_ids: [...targetDraft.applicable_rule_ids],
      associated_faction_ids: [...targetDraft.associated_faction_ids],
      story_function: targetDraft.story_function.normalize("NFKC").trim(),
      status: targetDraft.status,
      tags: targetDraft.tags.map((item) => item.normalize("NFKC").trim()),
    };

    setSaving(true);
    reportError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    let saveCompleted = false;
    try {
      let saved: LocationReadV1;
      if (targetEditor.mode === "create") {
        const fingerprint = JSON.stringify(payload);
        if (createCommandRef.current?.fingerprint !== fingerprint) {
          createCommandRef.current = {
            fingerprint,
            key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
          };
        }
        const result = await apiPost<unknown>(
          `/api/locations/novel/${novelId}`,
          payload,
          { headers: { "Idempotency-Key": createCommandRef.current.key }, signal: controller.signal },
        );
        saved = parseLocationReadV1(result, novelId);
        if (
          saved.version !== 1
          || saved.is_deleted
          || saved.deleted_at !== null
          || !matchesLocationFields(saved, payload)
        ) throw new Error("Invalid location create response");
      } else {
        const result = await apiPut<unknown>(
          `/api/locations/novel/${novelId}/${targetEditor.source.location_id}`,
          { ...Object.fromEntries(SECTION_FIELDS[session!.section].map((field) => [field, payload[field]])), expected_version: targetEditor.source.version },
          { signal: controller.signal },
        );
        saved = parseLocationReadV1(result, novelId);
        if (
          saved.location_id !== targetEditor.source.location_id
          || saved.version !== targetEditor.source.version + 1
          || saved.is_deleted
          || SECTION_FIELDS[session!.section].some((field) => JSON.stringify(saved[field]) !== JSON.stringify(payload[field]))
        ) throw new Error("Invalid location update response");
      }
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setLocations((current) => [...current.filter((location) => location.location_id !== saved.location_id), saved]);
      setSelectedLocationId(saved.location_id);
      if (session) {
        setInlineSessions((current) => ({ ...current, [saved.location_id]: undefined }));
      } else setEditor(null);
      saveCompleted = true;
      createCommandRef.current = null;
      onFormalFactsChanged?.();
      await loadWorkspace();
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      onLocationChange?.("locations", saved.location_id, filters, false);
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      if (error instanceof ApiRequestError) {
        const normalized: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          const formField = field.split(".").find((part) => (
            Object.prototype.hasOwnProperty.call(EMPTY_LOCATION, part)
          )) ?? field;
          normalized[formField] = [...(normalized[formField] ?? []), ...messages];
        }
        reportError(error.status === 409 ? t("errors.conflict") : error.message, normalized);
      } else {
        reportError(error instanceof Error ? error.message : t("errors.save"));
      }
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) {
        setSaving(false);
        if (saveCompleted && session) requestAnimationFrame(() => document.getElementById(`location-edit-${session.source.location_id}-${session.section}`)?.focus({ preventScroll: true }));
      }
    }
  };

  const openConfirm = async (intent: ConfirmIntent) => {
    setConfirmIntent(intent);
    setImpact(null);
    setDetachChildren(false);
    setConfirmError("");
    if (intent.kind === "restore") return;
    setImpactLoading(true);
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      const result = await apiGet<unknown>(
        `/api/locations/novel/${novelId}/${intent.location.location_id}/delete-impact`,
        { signal: controller.signal },
      );
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setImpact(parseLocationDeleteImpactV1(result, intent.location.location_id));
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof Error ? error.message : t("errors.impact"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setImpactLoading(false);
    }
  };

  const runConfirmAction = async () => {
    if (!confirmIntent || !novelId) return;
    const { location } = confirmIntent;
    setActionLocationId(location.location_id);
    setConfirmError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      if (confirmIntent.kind === "soft-delete") {
        const result = await apiDelete<unknown>(
          `/api/locations/novel/${novelId}/${location.location_id}?expected_version=${location.version}&detach_children=${detachChildren ? "true" : "false"}`,
          { signal: controller.signal },
        );
        const deleted = parseLocationReadV1(result, novelId);
        if (
          deleted.location_id !== location.location_id
          || deleted.version !== location.version + 1
          || !deleted.is_deleted
          || deleted.deleted_at === null
        ) throw new Error("Invalid location delete response");
      } else if (confirmIntent.kind === "restore") {
        const result = await apiPost<unknown>(
          `/api/locations/novel/${novelId}/${location.location_id}/restore`,
          { expected_version: location.version },
          { signal: controller.signal },
        );
        const restored = parseLocationReadV1(result, novelId);
        if (
          restored.location_id !== location.location_id
          || restored.version !== location.version + 1
          || restored.is_deleted
          || restored.deleted_at !== null
        ) throw new Error("Invalid location restore response");
      } else {
        const result = await apiDelete<unknown>(
          `/api/locations/novel/${novelId}/${location.location_id}/hard?expected_version=${location.version}`,
          { signal: controller.signal },
        );
        parseLocationHardDeleteResponseV1(result, location.location_id);
      }
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setSelectedLocationId("");
      setMobileDetailOpen(false);
      setConfirmIntent(null);
      onFormalFactsChanged?.();
      await loadWorkspace();
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      onLocationChange?.(view, null, filters, true);
      requestAnimationFrame(() => document.getElementById(`${TAB_PREFIX}-${view}-tab`)?.focus());
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.conflict")
        : error instanceof Error ? error.message : t("errors.action"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setActionLocationId("");
    }
  };

  const handleTreeKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number, row: LocationTreeRow) => {
    let nextId = "";
    if (event.key === "ArrowUp") nextId = rows[Math.max(0, index - 1)]?.location.location_id ?? "";
    if (event.key === "ArrowDown") nextId = rows[Math.min(rows.length - 1, index + 1)]?.location.location_id ?? "";
    if (event.key === "Home") nextId = rows[0]?.location.location_id ?? "";
    if (event.key === "End") nextId = rows.at(-1)?.location.location_id ?? "";
    if (event.key === "ArrowLeft") nextId = row.location.parent_location_id ?? "";
    if (event.key === "ArrowRight") {
      nextId = rows.find((candidate) => candidate.location.parent_location_id === row.location.location_id)?.location.location_id ?? "";
    }
    if (!nextId) return;
    event.preventDefault();
    selectLocation(nextId);
    requestAnimationFrame(() => document.getElementById(`location-tree-${nextId}`)?.focus());
  };

  if (!canUseSavedNovel) {
    return (
      <section className="grid h-full min-h-72 place-items-center bg-background px-5 py-10">
        <div className="w-full max-w-xl border-y border-border py-10 text-center">
          <span className="text-2xl text-accent" aria-hidden="true">⌖</span>
          <h1 className="mt-3 text-xl font-semibold text-foreground">{t("disabled.title")}</h1>
        </div>
      </section>
    );
  }

  return (
    <section ref={workspaceRef} className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b border-border bg-surface">
        <h1 className="sr-only">{t("title")}</h1>
        {dataError && workspaceReady && (
          <div className="flex flex-col gap-3 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200 sm:flex-row sm:items-center sm:justify-between sm:px-6" role="alert">
            <span>{dataError}</span>
            <Button size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
          </div>
        )}
        <div className="flex min-w-0 items-center gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 flex-1 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
            {(["locations", "trash"] as const).map((tab, index, tabs) => (
              <button
                key={tab}
                id={`${TAB_PREFIX}-${tab}-tab`}
                type="button"
                role="tab"
                aria-selected={view === tab}
                aria-controls={`${TAB_PREFIX}-${tab}-panel`}
                tabIndex={view === tab ? 0 : -1}
                disabled={busy}
                onClick={() => changeView(tab)}
                onKeyDown={(event) => {
                  if (busy) return;
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                  const nextTab = tabs[nextIndex];
                  changeView(nextTab);
                  document.getElementById(`${TAB_PREFIX}-${nextTab}-tab`)?.focus();
                }}
                className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${view === tab ? "border-accent text-accent" : "border-transparent text-muted hover:border-border hover:text-foreground"}`}
              >
                {t(`tabs.${tab}`)}
                <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs tabular-nums text-muted">{tab === "locations" ? locations.length : trash.length}</span>
              </button>
            ))}
          </div>
          <SectionActionButton action="refresh" label={loading ? t("actions.refreshing") : t("actions.refresh")} className="shrink-0" variant="ghost" size="sm" onPress={() => void loadWorkspace()} isDisabled={busy} />
        </div>
      </header>

      <div id={`${TAB_PREFIX}-${view}-panel`} data-entity-body role="tabpanel" aria-labelledby={`${TAB_PREFIX}-${view}-tab`} className="@container/master flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 sm:px-6">
        <section className={`shrink-0 border-b border-border pb-3 ${mobileDetailOpen ? "hidden @min-[800px]/master:block" : ""}`}>
          <div data-entity-toolbar className="workspace-toolbar grid min-w-0 items-end gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[minmax(220px,1fr)_repeat(4,minmax(0,160px))_auto]">
            <Field label={t("filters.search")}>
              <span className="relative block min-w-0">
          <input aria-label={t("filters.search")} disabled={saving} value={filters.q} onChange={(event) => updateFilters({ ...filters, q: event.target.value })} placeholder={t("filters.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-11`} />
          {filtersActive && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("actions.clearFilters")} title={t("actions.clearFilters")} disabled={saving} onClick={() => updateFilters(DEFAULT_FILTERS)}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}
        </span>
            </Field>
            <Field label={t("filters.type")}>
              <select disabled={saving} value={filters.locationType} onChange={(event) => updateFilters({ ...filters, locationType: event.target.value })} className={FILTER_CLASS}>
                <option value="all">{t("filters.allTypes")}</option>
                {locationTypes.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </Field>
            <Field label={t("filters.status")}>
              <select disabled={saving} value={filters.status} onChange={(event) => updateFilters({ ...filters, status: event.target.value as LocationWorkspaceFilters["status"] })} className={FILTER_CLASS}>
                <option value="all">{t("filters.allStatuses")}</option>
                {LOCATION_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
              </select>
            </Field>
            <Field label={t("filters.parent")}>
              <select disabled={saving} value={filters.parentId} onChange={(event) => updateFilters({ ...filters, parentId: event.target.value })} className={FILTER_CLASS}>
                <option value="all">{t("filters.allParents")}</option>
                <option value="root">{t("parent.root")}</option>
                {(view === "trash" ? [...locations, ...trash] : locations.filter((location) => location.status === "active")).map((location) => (
                  <option key={location.location_id} value={location.location_id}>
                    {formatStableReferenceLabel(location.name, location.location_id)}
                    {(location.is_deleted || location.status !== "active") ? ` · ${t("references.unavailable")}` : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("filters.faction")}>
              <select disabled={saving} value={filters.factionId} onChange={(event) => updateFilters({ ...filters, factionId: event.target.value })} className={FILTER_CLASS}>
                <option value="all">{t("filters.allFactions")}</option>
                {factions.filter((faction) => !faction.is_deleted && faction.active_status === "active").map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{formatStableReferenceLabel(faction.name, faction.faction_id)}</option>)}
              </select>
            </Field>
            <div className="flex flex-wrap gap-2">
              {view === "locations" && (
                <>
                  <Button variant="outline" size="sm" onPress={openCreate} isDisabled={busy || !workspaceReady}>{t("actions.create")}</Button>
                </>
              )}
            </div>
          </div>
        </section>

        {pageActionError && <div className="shrink-0 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{pageActionError}</div>}

        {dataError && !workspaceReady ? (
          <div className="border-y border-red-500/40 bg-red-50 px-5 py-14 text-center text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
            <p className="text-sm font-medium">{dataError}</p>
            <Button className="mt-5" size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
          </div>
        ) : loading && sourceLocations.length === 0 ? (
          <div className="border-y border-border px-5 py-14 text-center" role="status">
            <span className="mx-auto block size-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted">{t("loading")}</p>
          </div>
        ) : invalidRequestedId ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center" role="alert">
            <p className="text-sm font-medium text-foreground">{t("invalid.title")}</p>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted">{t("invalid.description", { id: invalidRequestedId })}</p>
            <Button
              className="mt-5"
              size="sm"
              variant="outline"
              onPress={() => {
                const firstId = rows[0]?.location.location_id ?? "";
                setInvalidRequestedId("");
                setSelectedLocationId(firstId);
                onLocationChange?.(view, firstId || null, filters, true);
              }}
            >
              {t("actions.backToRoster")}
            </Button>
          </div>
        ) : rows.length === 0 ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center">
            <p className="text-sm font-medium text-foreground">{filtersActive ? t("empty.filteredTitle") : view === "trash" ? t("empty.trashTitle") : t("empty.locationsTitle")}</p>
            {!filtersActive && view === "locations" && (
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <Button variant="outline" size="sm" onPress={openCreate}>{t("actions.createFirst")}</Button>
              </div>
            )}
          </div>
        ) : selectedLocation && (
          <div className={`grid min-h-[520px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${hideList ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
            <div className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
            <aside data-entity-roster id={`location-list-${novelId}-${view}`} className={`${hideList ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`} aria-label={t(`tabs.${view}`)} aria-hidden={hideList || undefined} inert={hideList} tabIndex={0} role="tree">
              {rows.map((row, index) => (
                <button
                  key={row.location.location_id}
                  disabled={saving} id={`location-tree-${row.location.location_id}`}
                  type="button"
                  role="treeitem"
                  aria-level={row.depth + 1}
                  aria-selected={selectedLocation.location_id === row.location.location_id}
                  tabIndex={selectedLocation.location_id === row.location.location_id ? 0 : -1}
                  onClick={() => selectLocation(row.location.location_id)}
                  onKeyDown={(event) => handleTreeKeyDown(event, index, row)}
                  className={`block min-h-16 w-full border-b border-border px-4 py-3 text-left transition-colors ${selectedLocation.location_id === row.location.location_id ? "bg-selected" : "hover:bg-surface-secondary/55"}`}
                  style={{ paddingInlineStart: `${1 + Math.min(row.depth, 8) * 1.15}rem` }}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="truncate text-sm font-semibold text-foreground">{row.location.name}</span>
                    <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${row.location.status === "active" ? "bg-emerald-500" : "bg-muted/45"}`} />
                  </span>
                  <span className="mt-1 block truncate text-xs text-muted">{row.location.location_type} · {t(`status.${row.location.status}`)}</span>
                </button>
              ))}
            </aside>
            <SidebarEdgeHandle controls={`location-list-${novelId}-${view}`} className="hidden @min-[800px]/master:flex"
              leftAction={hideList ? undefined : { label: tLayout("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }}
              rightAction={hideList ? { label: tLayout("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined}
            />
            </div>

            <article id={`location-detail-${selectedLocation.location_id}`} className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0`} aria-label={`${t(`tabs.${view}`)} · ${selectedLocation.name}`} tabIndex={0}>
              <button type="button" disabled={saving} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                setMobileDetailOpen(false);
                requestAnimationFrame(() => document.getElementById(`location-tree-${selectedLocation.location_id}`)?.focus());
              }}>← {t("actions.backToRoster")}</button>
              <div data-entity-detail className="min-w-0 px-5 py-4 sm:px-7">
                <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <Pill active={selectedLocation.status === "active"}>{t(`status.${selectedLocation.status}`)}</Pill>
                    </div>
                    <h2 className="sr-only">{selectedLocation.name}</h2>
                    <p className="mt-1 font-mono text-xs text-muted">{selectedLocation.location_id} · v{selectedLocation.version}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {view === "locations" ? (
                      <>
                        <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={() => void openConfirm({ kind: "soft-delete", location: selectedLocation })} isDisabled={busy || Boolean(inlineSession)} />
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onPress={() => void openConfirm({ kind: "restore", location: selectedLocation })} isDisabled={busy}>{t("actions.restore")}</Button>
                        <Button size="sm" variant="ghost" className="text-danger" onPress={() => void openConfirm({ kind: "hard-delete", location: selectedLocation })} isDisabled={busy}>{t("actions.hardDelete")}</Button>
                      </>
                    )}
                  </div>
                </header>

                <div className="mt-4 space-y-4">
                  {(["identity", "setting", "references", "story"] as const).map((section, index) => {
                    const editing = view === "locations" && inlineSession?.section === section;
                    return <DocumentSection key={section} number={String(index + 1).padStart(2, "0")} title={t(`editor.sections.${section === "references" ? "constraints" : section}`)} actions={view === "locations" && (editing ? <>
                      <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" isDisabled={saving} onPress={() => {
                        setInlineSessions((current) => ({ ...current, [selectedLocation.location_id]: undefined }));
                        requestAnimationFrame(() => document.getElementById(`location-edit-${selectedLocation.location_id}-${section}`)?.focus({ preventScroll: true }));
                      }} />
                      <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" isDisabled={busy} onPress={() => void saveEditor(inlineSession)} />
                    </> : <SectionEditButton id={`location-edit-${selectedLocation.location_id}-${section}`} isDisabled={busy || Boolean(inlineSession)} onPress={() => openEdit(selectedLocation, section)} label={t("actions.edit")} />)}>
                      {editing ? <div id={`location-editor-${selectedLocation.location_id}`} className="space-y-4">
                        {inlineSession.error && <RelationEditorErrorSummary message={inlineSession.error} fieldErrors={inlineSession.fieldErrors} />}
                        {inlineSession.error === t("errors.conflict") && selectedLocation.version !== inlineSession.source.version && <Button size="sm" variant="outline" isDisabled={saving} onPress={() => {
                          // 只有作者明确采用时才更新版本，并保留当前节的修改。
                          setInlineSessions((current) => ({ ...current, [selectedLocation.location_id]: { ...inlineSession,
                            source: selectedLocation, draft: { ...selectedLocation, ...Object.fromEntries(SECTION_FIELDS[section].map((field) => [field, inlineSession.draft[field]])) }, error: "", fieldErrors: {},
                          } }));
                        }}>{t("actions.useLatest")}</Button>}
                        {section === "identity" && <Field label={t("fields.status")} error={inlineSession.fieldErrors.status?.[0]} errorId={`location-${selectedLocation.location_id}-status-error`}><select name="status" value={inlineSession.draft.status} aria-invalid={Boolean(inlineSession.fieldErrors.status?.length)} aria-describedby={inlineSession.fieldErrors.status?.length ? `location-${selectedLocation.location_id}-status-error` : undefined} disabled={saving} className={INPUT_CLASS} onChange={(event) => setInlineSessions((current) => ({ ...current, [selectedLocation.location_id]: { ...inlineSession, draft: { ...inlineSession.draft, status: event.target.value as LocationStatus } } }))}>{LOCATION_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}</select></Field>}
                        <LocationFieldsForm section={section} value={inlineSession.draft} locations={locations} excludedParentIds={descendantIds} rules={rules} factions={factions} disabled={saving} fieldErrors={inlineSession.fieldErrors} errorIdPrefix={`location-${selectedLocation.location_id}`} onChange={(value) => setInlineSessions((current) => ({ ...current, [selectedLocation.location_id]: { ...inlineSession, draft: { ...inlineSession.draft, ...value } } }))} />
                      </div> : <dl className="detail-fields grid min-w-0 gap-4">
                        {section === "identity" && <>
                          <ReadOnlyField label={t("fields.name")} value={selectedLocation.name} />
                          <ReadOnlyField label={t("fields.locationType")} value={selectedLocation.location_type} />
                          <ReadOnlyField label={t("fields.parent")} value={selectedLocation.parent_location_id ? formatStableReferenceLabel(locationNames.get(selectedLocation.parent_location_id) ?? t("references.unknown"), selectedLocation.parent_location_id) : t("parent.root")} />
                          <ReadOnlyField label={t("fields.aliases")} value={selectedLocation.aliases.length ? <TagList values={selectedLocation.aliases} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReadOnlyField label={t("fields.tags")} value={selectedLocation.tags.length ? <TagList values={selectedLocation.tags} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReadOnlyField wide label={t("fields.description")} value={selectedLocation.description || t("empty.none")} />
                        </>}
                        {section === "setting" && <>
                          <ReadOnlyField wide label={t("fields.environment")} value={selectedLocation.environment || t("empty.none")} />
                          <ReadOnlyField wide label={t("fields.atmosphere")} value={selectedLocation.atmosphere || t("empty.none")} />
                          <ReadOnlyField wide label={t("fields.geography")} value={selectedLocation.geography || t("empty.none")} />
                        </>}
                        {section === "references" && <>
                          <ReadOnlyField label={t("fields.rulesAndConstraints")} value={selectedLocation.rules_and_constraints.length ? <TagList values={selectedLocation.rules_and_constraints} /> : <span className="text-sm text-muted">{t("empty.none")}</span>} />
                          <ReferenceList title={t("fields.applicableRules")} ids={selectedLocation.applicable_rule_ids} names={ruleNames} empty={t("references.emptyRules")} unavailable={t("references.unavailable")} />
                          <ReferenceList title={t("fields.associatedFactions")} ids={selectedLocation.associated_faction_ids} names={factionNames} empty={t("references.emptyFactions")} unavailable={t("references.unavailable")} />
                        </>}
                        {section === "story" && <>
                          <ReadOnlyField wide label={t("fields.storyFunction")} value={selectedLocation.story_function || t("empty.none")} />
                        </>}
                      </dl>}
                    </DocumentSection>;
                  })}
                </div>
              </div>
            </article>
          </div>
        )}
      </div>

      {editor && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !saving && closeEditor()} variant="blur" isDismissable={!saving} isKeyboardDismissDisabled={saving}>
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-5xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">{editor.mode === "create" ? t("editor.createTitle") : t("editor.editTitle")}</Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
                {editorError && <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} className="mb-6" />}
                <Field label={t("fields.status")} className="mb-8" error={editorFieldErrors.status?.[0]} errorId="location-editor-status-error">
                  <select name="status" value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as LocationStatus }))} className={INPUT_CLASS} disabled={saving} aria-invalid={Boolean(editorFieldErrors.status?.length)} aria-describedby={editorFieldErrors.status?.length ? "location-editor-status-error" : undefined}>
                    {LOCATION_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
                  </select>
                </Field>
                <LocationFieldsForm
                  value={draft}
                  locations={locations}
                  excludedParentIds={descendantIds}
                  rules={rules}
                  factions={factions}
                  disabled={saving}
                  fieldErrors={editorFieldErrors}
                  errorIdPrefix="location-editor"
                  onChange={(fields) => setDraft((current) => ({ ...current, ...fields }))}
                />
              </Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeEditor} isDisabled={saving}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void saveEditor()} isDisabled={saving}>{saving ? t("actions.saving") : t("actions.save")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}

      {confirmIntent && confirmIntent.kind === "restore" && (
        <ConfirmActionModal
          title={t("confirm.restore.title")}
          message={t("confirm.restore.message", { name: confirmIntent.location.name })}
          confirmText={t("confirm.restore.confirm")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          error={confirmError}
          isLoading={actionLocationId === confirmIntent.location.location_id}
          onCancel={() => { setConfirmIntent(null); setConfirmError(""); }}
          onConfirm={() => void runConfirmAction()}
        />
      )}

      {confirmIntent && confirmIntent.kind !== "restore" && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !actionLocationId && setConfirmIntent(null)} variant="blur" isDismissable={!actionLocationId}>
          <Modal.Container size="sm" scroll="inside">
            <Modal.Dialog className="w-full max-w-lg">
              <Modal.Header className="flex items-center justify-between gap-3 px-5 pb-0 pt-5">
                <Modal.Heading className="text-base font-semibold text-foreground">{t(`confirm.${confirmIntent.kind}.title`)}</Modal.Heading>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={Boolean(actionLocationId)} />
              </Modal.Header>
              <Modal.Body className="px-5 py-4">
                <p className="text-sm leading-6 text-muted">{t(`confirm.${confirmIntent.kind}.message`, { name: confirmIntent.location.name })}</p>
                {impactLoading && <p className="mt-4 text-sm text-muted" role="status">{t("impact.loading")}</p>}
                {confirmError && <RelationEditorErrorSummary message={confirmError} className="mt-4" />}
                {impact && (
                  <div className="mt-4 border-y border-border py-4">
                    <h3 className="text-xs font-semibold tracking-normal text-accent">{t("impact.title")}</h3>
                    <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                      <ImpactCount label={t("impact.activeChildren")} value={impact.active_direct_children} />
                      <ImpactCount label={t("impact.deletedChildren")} value={impact.deleted_direct_children} />
                      <ImpactCount label={t("impact.worldRules")} value={impact.world_rules} />
                      <ImpactCount label={t("impact.arcs")} value={impact.arcs} />
                      <ImpactCount label={t("impact.chapters")} value={impact.chapters} />
                      <ImpactCount label={t("impact.scenes")} value={impact.scenes} />
                      <ImpactCount label={t("impact.items")} value={impact.items} />
                      <ImpactCount label={t("impact.foreshadowings")} value={impact.foreshadowings} />
                    </dl>
                    {impact.direct_child_location_ids.length > 0 && (
                      <div className="mt-4 border-t border-border pt-4">
                        <h4 className="text-xs font-medium text-muted">{t("impact.directChildList")}</h4>
                        <ul className="mt-2 divide-y divide-border">
                          {impact.direct_child_location_ids.map((id) => (
                            <li key={id} className="py-2 text-sm text-foreground/85">
                              {formatStableReferenceLabel(locationNames.get(id) ?? t("references.unknown"), id)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {confirmIntent.kind === "soft-delete" && impact.active_direct_children > 0 && (
                      <label className="mt-4 flex min-h-11 items-start gap-3 border-t border-border pt-4 text-sm leading-6 text-foreground">
                        <input type="checkbox" checked={detachChildren} onChange={(event) => setDetachChildren(event.target.checked)} className="mt-1 size-4 accent-accent" disabled={Boolean(actionLocationId)} />
                        <span>{t("impact.detachAcknowledge", { count: impact.active_direct_children })}</span>
                      </label>
                    )}
                    {confirmIntent.kind === "hard-delete" && (impact.has_children || impact.has_protected_references) && <p className="mt-4 text-sm font-medium text-danger">{t("impact.hardBlocked")}</p>}
                  </div>
                )}
              </Modal.Body>
              <Modal.Footer className="flex justify-end gap-2 px-5 pb-5 pt-0">
                <Button variant="ghost" size="sm" onPress={() => { setConfirmIntent(null); setConfirmError(""); }} isDisabled={Boolean(actionLocationId)}>{t("actions.cancel")}</Button>
                <Button
                  variant="primary"
                  size="sm"
                  className="bg-red-600 text-white hover:bg-red-700"
                  onPress={() => void runConfirmAction()}
                  isDisabled={impactLoading || !impact || Boolean(actionLocationId) || (confirmIntent.kind === "soft-delete" && impact.active_direct_children > 0 && !detachChildren) || (confirmIntent.kind === "hard-delete" && (impact.has_children || impact.has_protected_references))}
                >
                  {actionLocationId ? t("actions.processing") : t(`confirm.${confirmIntent.kind}.confirm`)}
                </Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </section>
  );
}

function Field({ label, children, className = "", error, errorId }: { label: string; children: ReactNode; className?: string; error?: string; errorId?: string }) {
  return <label className={`grid min-w-0 gap-1.5 text-xs font-medium text-muted ${className}`}><span>{label}</span>{children}{error && <span id={errorId} className="text-xs font-medium text-danger">{error}</span>}</label>;
}

function Pill({ children, active = false }: { children: ReactNode; active?: boolean }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-surface-secondary text-muted"}`}>{children}</span>;
}



function ReferenceList({ title, ids, names, empty, unavailable }: { title: string; ids: string[]; names: ReadonlyMap<string, string>; empty: string; unavailable: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted">{title}</dt>
      <dd className="mt-2">{ids.length === 0 ? <p className="text-sm text-muted">{empty}</p> : <ul className="divide-y divide-border">{ids.map((id) => <li key={id} className="py-2 text-sm text-foreground/85">{names.has(id) ? formatStableReferenceLabel(names.get(id) as string, id) : `${id} · ${unavailable}`}</li>)}</ul>}</dd>
    </div>
  );
}

function ImpactCount({ label, value }: { label: string; value: number }) {
  return <div><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 font-semibold tabular-nums text-foreground">{value}</dd></div>;
}

function matchesLocationFields(
  location: LocationReadV1,
  fields: LocationCreateV1,
): boolean {
  return location.name === fields.name
    && location.location_type === fields.location_type
    && location.description === fields.description
    && location.parent_location_id === (fields.parent_location_id ?? null)
    && location.environment === (fields.environment ?? "")
    && location.atmosphere === (fields.atmosphere ?? "")
    && location.geography === (fields.geography ?? "")
    && location.story_function === (fields.story_function ?? "")
    && location.status === (fields.status ?? "active")
    && JSON.stringify(location.aliases) === JSON.stringify(fields.aliases ?? [])
    && JSON.stringify(location.rules_and_constraints) === JSON.stringify(fields.rules_and_constraints ?? [])
    && JSON.stringify(location.applicable_rule_ids) === JSON.stringify(fields.applicable_rule_ids ?? [])
    && JSON.stringify(location.associated_faction_ids) === JSON.stringify(fields.associated_faction_ids ?? [])
    && JSON.stringify(location.tags) === JSON.stringify(fields.tags ?? []);
}
