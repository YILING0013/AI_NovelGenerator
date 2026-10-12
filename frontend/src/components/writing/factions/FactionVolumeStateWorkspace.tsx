"use client";
import { useAssistantFocus, useAssistantRefresh, useAssistantResource } from "../assistant/AssistantContext";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { TooltipHint } from "@/components/shared/TooltipHint";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import DocumentSection from "@/components/shared/DocumentSection";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

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
import type {
  FactionVolumeParticipationScope,
  FactionVolumeStateFields,
  FactionVolumeStateHardDeleteV1,
  FactionVolumeStateInitializeResultV1,
  FactionVolumeStateListV1,
  FactionVolumeStateReadV1,
  FactionVolumeStateUpsertV1,
} from "@/types/factionVolumeState";
import type { CoreFaction } from "@/types/novel";
import type { VolumeReadV2 } from "@/types/volume";
import FactionVolumeStateForm from "./FactionVolumeStateForm";
import VolumeEntityCandidateWorkspace from "../volume-entities/VolumeEntityCandidateWorkspace";

export interface FactionVolumeStateWorkspaceProps {
  novelId: string;
  fixedVolumeId: string;
  fixedVolumeTitle: string;
  fixedVolumeOrderIndex: number;
  fixedVolumeDeleted?: boolean;
  volumeVersion?: number;
  onFormalFactsChanged?: (volume?: VolumeReadV2) => void;
  onBusyChange?: (busy: boolean) => void;
  refreshKey?: number;
  toolbarBefore?: ReactNode;
  toolbarAfter?: ReactNode;
  beforeContent?: ReactNode;
  generationDisabled?: boolean;
}

interface ListEnvelope<T> {
  data: T[];
}

type StateSection = "participation" | "agenda";

type EditorState = {
  factionId: string;
  volumeId: string;
  source: FactionVolumeStateReadV1 | null;
  section?: StateSection;
} | null;

type LifecycleIntent = {
  action: "soft-delete" | "restore" | "hard-delete";
  state: FactionVolumeStateReadV1;
} | null;

const STATE_SECTIONS: StateSection[] = ["participation", "agenda"];
const SECTION_FIELDS: Record<StateSection, (keyof FactionVolumeStateFields)[]> = {
  "participation": [
    "participation_scope",
    "active_status",
    "power_level",
    "influence_scope",
    "current_goal",
    "start_state",
    "planned_end_state"
  ],
  "agenda": [
    "public_stance",
    "hidden_agenda",
    "resources"
  ]
};
const SECTION_TITLES: Record<StateSection, string> = {
  "participation": "form.participationTitle",
  "agenda": "form.agendaTitle"
};
const FIELD_LABELS: Record<keyof FactionVolumeStateFields, string> = {
  "participation_scope": "participationScope",
  "active_status": "activeStatus",
  "power_level": "powerLevel",
  "influence_scope": "influenceScope",
  "current_goal": "currentGoal",
  "start_state": "startState",
  "planned_end_state": "plannedEndState",
  "public_stance": "publicStance",
  "hidden_agenda": "hiddenAgenda",
  "resources": "resources"
};

const EMPTY_FIELDS: FactionVolumeStateFields = {
  participation_scope: "secondary",
  current_goal: "",
  start_state: "",
  planned_end_state: "",
  power_level: 3,
  resources: [],
  public_stance: "",
  hidden_agenda: "",
  influence_scope: "",
  active_status: "active",
};
const FILTER_CLASS =
  "min-h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const PARTICIPATION_SCOPES: FactionVolumeParticipationScope[] = [
  "primary",
  "secondary",
  "background",
];
const NO_STATES: FactionVolumeStateReadV1[] = [];

/**
 * 在卷内势力页用名册和连续详情管理本卷状态。
 *
 * @param props 当前卷、小说 ID、变更和编辑锁定回调。
 * @returns 可独立滚动的名册与原位分节编辑详情。
 */
export default function FactionVolumeStateWorkspace(props: FactionVolumeStateWorkspaceProps) {
  const t = useTranslations("writing.factionVolumeStates");
  const listT = useTranslations("writing.listLayout");
  const aiT = useTranslations("writing.volumeEntitiesAi");
  const [aiOpen, setAiOpen] = useState(false);
  const fixedVolumeId = props.fixedVolumeId ?? null;
  const fixedVolumeTitle = props.fixedVolumeTitle ?? "";
  const fixedVolumeOrderIndex = props.fixedVolumeOrderIndex ?? null;
  const fixedVolumeDeleted = props.fixedVolumeDeleted ?? false;
  const volumeVersion = props.volumeVersion;
  const onFormalFactsChangedRef = useRef(props.onFormalFactsChanged);
  const readVolumeVersionRef = useRef<number | undefined>(undefined);
  const pendingVolumeRefreshRef = useRef(false);
  const previousVolumeVersionRef = useRef(volumeVersion);
  useEffect(() => { onFormalFactsChangedRef.current = props.onFormalFactsChanged; }, [props.onFormalFactsChanged]);
  const contextKey = `${props.novelId}:${fixedVolumeId}`;
  const [states, setStates] = useState<FactionVolumeStateReadV1[]>([]);
  const [factions, setFactions] = useState<CoreFaction[]>([]);
  const [volumes, setVolumes] = useState<VolumeReadV2[]>([]);
  const [previousStateFactionIds, setPreviousStateFactionIds] = useState<string[]>([]);
  const [previousStatesError, setPreviousStatesError] = useState("");
  const [loadedContextKey, setLoadedContextKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [savedReadFailed, setSavedReadFailed] = useState(false);
  const [savedNames, setSavedNames] = useState<Record<string, string>>({});
  const confirmedContextRef = useRef<{ scope: string; stateId: string } | null>(null);
  const selectedStateIdRef = useRef("");
  const [search, setSearch] = useState("");
  const [scopeFilter, setScopeFilter] = useState<"all" | FactionVolumeParticipationScope>("all");
  const [showTrash, setShowTrash] = useState(false);
  const [selectedStateId, setSelectedStateId] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [listCollapsed, setListCollapsed] = useState(false);
  const rosterRef = useRef<HTMLDivElement | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());
  const editTriggerRef = useRef<HTMLElement | null>(null);
  const [editor, setEditor] = useState<EditorState>(null);
  const [draft, setDraft] = useState<FactionVolumeStateFields>(EMPTY_FIELDS);
  const [editorError, setEditorError] = useState("");
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [editorConflict, setEditorConflict] = useState(false);
  const [editorConflictLatest, setEditorConflictLatest] = useState<FactionVolumeStateReadV1 | null>(null);
  const [conflictRefreshing, setConflictRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lifecycleIntent, setLifecycleIntent] = useState<LifecycleIntent>(null);
  const [lifecycleError, setLifecycleError] = useState("");
  const [actionStateId, setActionStateId] = useState("");
  const [initializeOpen, setInitializeOpen] = useState(false);
  const [initializeFactionIds, setInitializeFactionIds] = useState<string[]>([]);
  const [initializeError, setInitializeError] = useState("");
  const [initializing, setInitializing] = useState(false);
  const loadAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRef = useRef<AbortController | null>(null);
  const contextKeyRef = useRef(contextKey);
  const createCommandRef = useRef<{ fingerprint: string; key: string } | null>(null);
  contextKeyRef.current = contextKey;

  const workspaceReady = loadedContextKey === contextKey;
  const visibleStates = workspaceReady ? states : NO_STATES;
  const factionNames = useMemo(
    () => new Map([...Object.entries(savedNames), ...factions.map((faction) => [faction.faction_id, faction.name] as const)]),
    [factions, savedNames],
  );
  const anyStateFactionIds = useMemo(
    () => new Set(visibleStates.map((state) => state.faction_id)),
    [visibleStates],
  );
  const previousStateFactionIdSet = useMemo(
    () => new Set(previousStateFactionIds),
    [previousStateFactionIds],
  );
  const fixedVolume = fixedVolumeId
    ? volumes.find((volume) => volume.volume_id === fixedVolumeId) ?? null
    : null;
  const factionCanJoinVolume = (faction: CoreFaction, volumeId: string) => (
    (faction.level_type ?? "core") === "core" || faction.volume_id === volumeId
  );
  const availableCreateFactions = factions.filter((faction) => (
    !faction.is_deleted
    && (faction.active_status ?? "active") === "active"
    && Boolean(fixedVolumeId && factionCanJoinVolume(faction, fixedVolumeId))
    && !anyStateFactionIds.has(faction.faction_id)
  ));
  const eligiblePreviousFactions = factions.filter((faction) => (
    !faction.is_deleted
    && (faction.active_status ?? "active") === "active"
    && Boolean(fixedVolumeId && factionCanJoinVolume(faction, fixedVolumeId))
    && previousStateFactionIdSet.has(faction.faction_id)
  ));
  const filtersActive = Boolean(search.trim())
    || scopeFilter !== "all"
    || showTrash !== fixedVolumeDeleted;
  const filteredStates = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return visibleStates.filter((state) => {
      if (state.is_deleted !== showTrash) return false;
      if (scopeFilter !== "all" && state.participation_scope !== scopeFilter) return false;
      if (!query) return true;
      return [
        factionNames.get(state.faction_id) ?? state.faction_id,
        state.faction_id,
        state.current_goal,
        state.start_state,
      ].join(" ").toLocaleLowerCase().includes(query);
    });
  }, [factionNames, scopeFilter, search, showTrash, visibleStates]);

  const loadWorkspace = useCallback(async () => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestContextKey = contextKey;
    loadAbortRef.current = controller;
    setLoading(true);
    setPreviousStatesError("");
    try {
      const statePath = `/api/faction-volume-states/novel/${props.novelId}/volume/${fixedVolumeId}?status=all`;
      const sources = await Promise.allSettled([
        apiGet<FactionVolumeStateListV1>(statePath, { signal: controller.signal }),
        apiGet<ListEnvelope<CoreFaction>>(`/api/factions/novel/${props.novelId}/level/core`, { signal: controller.signal }),
        apiGet<ListEnvelope<CoreFaction>>(`/api/factions/novel/${props.novelId}/level/volume`, { signal: controller.signal }),
        apiGet<ListEnvelope<CoreFaction>>(`/api/factions/novel/${props.novelId}/level/local`, { signal: controller.signal }),
        apiGet<ListEnvelope<VolumeReadV2>>(`/api/volumes/novel/${props.novelId}`, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 等这批读取结束再判断；不能让较快的 503 掩盖另一个接口的 403／404。
      const refused = sources.find((source) => source.status === "rejected" && source.reason instanceof ApiRequestError && source.reason.status < 500);
      if (refused?.status === "rejected") throw refused.reason;
      const [stateSource, coreSource, volumeFactionSource, localFactionSource, volumeSource] = sources;
      if (!fixedVolumeDeleted && volumeSource.status === "fulfilled" && !volumeSource.value.data.some((volume) => volume.volume_id === fixedVolumeId)) throw new ApiRequestError({ status: 404, message: t("errors.load") });
      if (stateSource.status === "rejected") throw stateSource.reason;
      if (coreSource.status === "rejected") throw coreSource.reason;
      if (volumeFactionSource.status === "rejected") throw volumeFactionSource.reason;
      if (localFactionSource.status === "rejected") throw localFactionSource.reason;
      if (volumeSource.status === "rejected") throw volumeSource.reason;
      const [stateResponse, coreResponse, volumeFactionResponse, localFactionResponse, volumeResponse] = [stateSource.value, coreSource.value, volumeFactionSource.value, localFactionSource.value, volumeSource.value] as const;
      let previousIds: string[] = [];
      let previousError = "";
      if (fixedVolumeId && !fixedVolumeDeleted && fixedVolumeOrderIndex !== null) {
        const previousVolume = volumeResponse.data
          .filter((volume) => volume.order_index < fixedVolumeOrderIndex)
          .sort((left, right) => right.order_index - left.order_index)[0];
        if (previousVolume) {
          try {
            const previousStates = await apiGet<FactionVolumeStateListV1>(
              `/api/faction-volume-states/novel/${props.novelId}/volume/${previousVolume.volume_id}?status=active`,
              { signal: controller.signal },
            );
            if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
            previousIds = previousStates.data.map((state) => state.faction_id);
          } catch {
            if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
            previousError = t("errors.previousStatesLoad");
          }
        }
      }
      setStates(stateResponse.data);
      setFactions([
        ...coreResponse.data,
        ...volumeFactionResponse.data,
        ...localFactionResponse.data,
      ]);
      setVolumes(volumeResponse.data);
      setPreviousStateFactionIds(previousIds);
      setPreviousStatesError(previousError);
      setLoadedContextKey(requestContextKey);
      setLoadError("");
      readVolumeVersionRef.current = volumeResponse.data.find((volume) => volume.volume_id === fixedVolumeId)?.version;
      const notifyVolume = pendingVolumeRefreshRef.current;
      pendingVolumeRefreshRef.current = false;
      confirmedContextRef.current = null;
      setSavedReadFailed(false);
      setSavedNames({});
      if (notifyVolume) onFormalFactsChangedRef.current?.(volumeResponse.data.find((volume) => volume.volume_id === fixedVolumeId));
    } catch (failure) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      const temporary = failure instanceof TypeError || failure instanceof ApiRequestError && failure.status >= 500;
      if (!temporary) pendingVolumeRefreshRef.current = false;
      const keepSaved = temporary && confirmedContextRef.current?.scope === requestContextKey
        && confirmedContextRef.current.stateId === selectedStateIdRef.current;
      setSavedReadFailed(keepSaved);
      if (!keepSaved) {
        confirmedContextRef.current = null;
        setSavedNames({});
        setStates([]);
        setFactions([]);
        setVolumes([]);
        setLoadedContextKey("");
      }
      setLoadError(failure instanceof Error ? failure.message : t("errors.load"));
    } finally {
      if (loadAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        loadAbortRef.current = null;
        setLoading(false);
      }
    }
  }, [contextKey, fixedVolumeDeleted, fixedVolumeId, fixedVolumeOrderIndex, props.novelId, t]);

  useEffect(() => {
    mutationAbortRef.current?.abort();
    setAiOpen(false);
    readVolumeVersionRef.current = undefined;
    pendingVolumeRefreshRef.current = false;
    confirmedContextRef.current = null;
    setSavedReadFailed(false);
    setSavedNames({});
    setLoadError("");
    setStates([]);
    setFactions([]);
    setVolumes([]);
    setPreviousStateFactionIds([]);
    setPreviousStatesError("");
    setLoadedContextKey("");
    setSelectedStateId("");
    setDetailOpen(false);
    setSearch("");
    setScopeFilter("all");
    setShowTrash(fixedVolumeDeleted);
    setEditor(null);
    setLifecycleIntent(null);
    setInitializeOpen(false);
    setSaving(false);
    setActionStateId("");
    setInitializing(false);
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    setConflictRefreshing(false);
    setLifecycleError("");
    setInitializeError("");
    createCommandRef.current = null;
    return () => {
      loadAbortRef.current?.abort();
      mutationAbortRef.current?.abort();
    };
  }, [contextKey, fixedVolumeDeleted]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace, props.refreshKey]);

  useEffect(() => {
    const previous = previousVolumeVersionRef.current;
    previousVolumeVersionRef.current = volumeVersion;
    // 刚读到的卷传回父组件时，不再为相同版本重复读取。
    if (volumeVersion !== previous && volumeVersion !== readVolumeVersionRef.current) void loadWorkspace();
  }, [loadWorkspace, volumeVersion]);

  const busy = Boolean(editor || lifecycleIntent || initializeOpen || saving || conflictRefreshing || actionStateId || initializing);
  const onBusyChange = props.onBusyChange;
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);

  useEffect(() => {
    if (!editor?.source || !editorError) return;
    const frame = requestAnimationFrame(() => {
      const target = detailRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")
        ?? detailRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [editor, editorError, editorFieldErrors]);

  const selectedState = filteredStates.find((state) => state.state_id === selectedStateId)
    ?? filteredStates[0] ?? null;
  selectedStateIdRef.current = selectedState?.state_id ?? "";
  useEffect(() => {
    // 搜索、筛选和助手定位也可能换目标，不能只处理名册点击。
    if (confirmedContextRef.current && (confirmedContextRef.current.scope !== contextKey
      || confirmedContextRef.current.stateId !== (selectedState?.state_id ?? ""))) {
      confirmedContextRef.current = null;
      setSavedReadFailed(false);
    }
  }, [contextKey, selectedState?.state_id]);
  useAssistantRefresh(props.novelId, loadWorkspace);
  useAssistantFocus("faction_volume_state", (target) => { if (!visibleStates.some((state) => state.state_id === target.id)) return false; setSelectedStateId(target.id); setShowTrash(Boolean(visibleStates.find((state) => state.state_id === target.id)?.is_deleted)); setSearch(""); setScopeFilter("all"); setDetailOpen(true); });
  useAssistantResource(selectedState ? { resource_type: "faction_volume_state", id: selectedState.state_id, name: selectedState.state_id, version: selectedState.version, draft: editor?.source?.state_id === selectedState.state_id ? { text: JSON.stringify(draft), fields: Object.keys(draft), version: editor.source.version } : undefined } : null);

  const openCreate = (factionId: string, volumeId: string) => {
    editTriggerRef.current = null;
    setDraft({ ...EMPTY_FIELDS, resources: [] });
    setEditor({ factionId, volumeId, source: null });
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    createCommandRef.current = null;
  };

  const openEdit = (state: FactionVolumeStateReadV1, section: StateSection) => {
    editTriggerRef.current = document.activeElement as HTMLElement;
    setDraft(draftFromState(state));
    setEditor({ factionId: state.faction_id, volumeId: state.volume_id, source: state, section });
    requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus());
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
  };

  const closeEditor = () => {
    if (saving || conflictRefreshing) return;
    setEditor(null);
    requestAnimationFrame(() => { if (editTriggerRef.current?.id) document.getElementById(editTriggerRef.current.id)?.focus(); });
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    createCommandRef.current = null;
  };

  const saveEditor = async () => {
    if (!editor || saving) return;
    const fieldErrors: ApiFieldErrors = {};
    if (!draft.current_goal.trim()) fieldErrors.current_goal = [t("validation.currentGoalRequired")];
    if (!draft.start_state.trim()) fieldErrors.start_state = [t("validation.startStateRequired")];
    if (!Number.isInteger(draft.power_level) || draft.power_level < 1 || draft.power_level > 5) {
      fieldErrors.power_level = [t("validation.powerLevel")];
    }
    if (draft.resources.length > 20) fieldErrors.resources = [t("validation.resourceLimit")];
    if (Object.keys(fieldErrors).length > 0) {
      setEditorError(t("errors.validation"));
      setEditorFieldErrors(fieldErrors);
      focusRelationEditorError(fieldErrors);
      return;
    }

    // 接口仍要求完整记录；只覆盖当前节，其他字段沿用开始编辑时的数据和版本。
    const fields = editor.source ? draftFromState(editor.source) : draft;
    if (editor.source && editor.section) {
      for (const field of SECTION_FIELDS[editor.section]) Object.assign(fields, { [field]: draft[field] });
    }
    const payload: FactionVolumeStateUpsertV1 = {
      participation_scope: fields.participation_scope,
      current_goal: fields.current_goal.trim(),
      start_state: fields.start_state.trim(),
      planned_end_state: fields.planned_end_state.trim(),
      power_level: fields.power_level,
      resources: fields.resources,
      public_stance: fields.public_stance.trim(),
      hidden_agenda: fields.hidden_agenda.trim(),
      influence_scope: fields.influence_scope.trim(),
      active_status: fields.active_status,
      ...(editor.source ? { expected_version: editor.source.version } : {}),
    };
    if (!editor.source) {
      const fingerprint = JSON.stringify({
        novel_id: props.novelId,
        volume_id: editor.volumeId,
        faction_id: editor.factionId,
        payload,
      });
      if (createCommandRef.current?.fingerprint !== fingerprint) {
        createCommandRef.current = {
          fingerprint,
          key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
        };
      }
    }
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    const requestContextKey = contextKey;
    mutationAbortRef.current = controller;
    setSaving(true);
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    try {
      const saved = await apiPut<FactionVolumeStateReadV1>(
        `/api/faction-volume-states/novel/${props.novelId}/volume/${editor.volumeId}/faction/${editor.factionId}`,
        payload,
        editor.source
          ? { signal: controller.signal }
          : {
              headers: { "Idempotency-Key": createCommandRef.current!.key },
              signal: controller.signal,
            },
      );
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 保存前发出的读取已过期，不能盖回刚保存的新版本。
      loadAbortRef.current?.abort();
      loadAbortRef.current = null;
      setLoading(false);
      setStates((current) => [saved, ...current.filter((state) => state.state_id !== saved.state_id)]);
      setEditor(null);
      setSelectedStateId(saved.state_id);
      requestAnimationFrame(() => { if (editTriggerRef.current?.id) document.getElementById(editTriggerRef.current.id)?.focus(); });
      createCommandRef.current = null;
      props.onFormalFactsChanged?.();
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      if (error instanceof ApiRequestError) {
        setEditorError(error.status === 409 ? t("errors.conflict") : t("errors.save"));
        setEditorConflict(error.status === 409);
        const normalized: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          const key = field.split(".").at(-1) ?? field;
          normalized[key] = [...(normalized[key] ?? []), ...messages];
        }
        setEditorFieldErrors(normalized);
        focusRelationEditorError(normalized);
      } else {
        setEditorError(t("errors.save"));
        focusRelationEditorError({});
      }
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setSaving(false);
      }
    }
  };

  const refreshEditorConflict = async () => {
    if (!editor || conflictRefreshing) return;
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    const requestContextKey = contextKey;
    mutationAbortRef.current = controller;
    setConflictRefreshing(true);
    try {
      let refreshed: FactionVolumeStateReadV1 | undefined;
      if (editor.source) {
        refreshed = await apiGet<FactionVolumeStateReadV1>(
          `/api/faction-volume-states/novel/${props.novelId}/${editor.source.state_id}`,
          { signal: controller.signal },
        );
      } else {
        const response = await apiGet<FactionVolumeStateListV1>(
          `/api/faction-volume-states/novel/${props.novelId}/volume/${editor.volumeId}?status=all`,
          { signal: controller.signal },
        );
        refreshed = response.data.find((state) => state.faction_id === editor.factionId);
      }
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      if (!refreshed || refreshed.is_deleted) {
        setEditorError(t(refreshed ? "errors.deletedConflict" : "errors.conflictMissing"));
        setEditorFieldErrors({});
        setEditorConflictLatest(null);
        return;
      }
      setStates((current) => [refreshed, ...current.filter((state) => state.state_id !== refreshed.state_id)]);
      // CAS 冲突后必须让用户明确选择，不能静默覆盖当前草稿或版本。
      setEditorConflictLatest(refreshed);
      setEditorError(t("errors.conflictReview", { version: refreshed.version }));
      setEditorFieldErrors({});
    } catch {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      setEditorError(t("errors.conflictRefresh"));
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setConflictRefreshing(false);
      }
    }
  };

  const runLifecycle = async () => {
    if (!lifecycleIntent || actionStateId) return;
    const requestContextKey = contextKey;
    const { action, state } = lifecycleIntent;
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    mutationAbortRef.current = controller;
    setActionStateId(state.state_id);
    setLifecycleError("");
    try {
      if (action === "hard-delete") {
        await apiDelete<FactionVolumeStateHardDeleteV1>(
          `/api/faction-volume-states/novel/${props.novelId}/${state.state_id}/hard?expected_version=${state.version}`,
          { signal: controller.signal },
        );
        if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
        setStates((current) => current.filter((item) => item.state_id !== state.state_id));
      } else {
        const saved = action === "restore"
          ? await apiPost<FactionVolumeStateReadV1>(
              `/api/faction-volume-states/novel/${props.novelId}/${state.state_id}/restore`,
              { expected_version: state.version },
              { signal: controller.signal },
            )
          : await apiDelete<FactionVolumeStateReadV1>(
              `/api/faction-volume-states/novel/${props.novelId}/${state.state_id}?expected_version=${state.version}`,
              { signal: controller.signal },
            );
        if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
        setStates((current) => current.map((item) => item.state_id === saved.state_id ? saved : item));
      }
      setLifecycleIntent(null);
      props.onFormalFactsChanged?.();
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      setLifecycleError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.conflict")
        : t("errors.action"));
      if (error instanceof ApiRequestError && error.status === 409) void loadWorkspace();
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setActionStateId("");
      }
    }
  };

  const runInitialize = async () => {
    if (!fixedVolumeId || initializing || initializeFactionIds.length === 0) return;
    const requestContextKey = contextKey;
    const factionIds = [...initializeFactionIds].sort();
    const fingerprint = JSON.stringify({
      volume_id: fixedVolumeId,
      faction_ids: factionIds,
      skip_existing: false,
    });
    if (createCommandRef.current?.fingerprint !== fingerprint) {
      createCommandRef.current = {
        fingerprint,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    mutationAbortRef.current = controller;
    setInitializing(true);
    setInitializeError("");
    try {
      const response = await apiPost<FactionVolumeStateInitializeResultV1>(
        `/api/faction-volume-states/novel/${props.novelId}/volume/${fixedVolumeId}/initialize-from-previous`,
        { faction_ids: factionIds, skip_existing: false },
        {
          headers: { "Idempotency-Key": createCommandRef.current.key },
          signal: controller.signal,
        },
      );
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      setStates((current) => [
        ...response.states,
        ...current.filter((state) => !response.states.some((saved) => saved.state_id === state.state_id)),
      ]);
      setInitializeOpen(false);
      setInitializeFactionIds([]);
      createCommandRef.current = null;
      props.onFormalFactsChanged?.();
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      setInitializeError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.initializeConflict")
        : t("errors.initialize"));
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setInitializing(false);
      }
    }
  };

  const selectedEditorFaction = editor
    ? factions.find((faction) => faction.faction_id === editor.factionId) ?? null
    : null;
  const selectedEditorVolume = editor
    ? volumes.find((volume) => volume.volume_id === editor.volumeId) ?? null
    : null;

  const renderEditorFields = editor && (
    <>
            {editorError && (
              <div className="mb-6">
                <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} />
                {editorConflict && (
                  <>
                    {!editorConflictLatest && (
                      <Button className="mt-3" size="sm" variant="outline" onPress={() => void refreshEditorConflict()} isDisabled={conflictRefreshing}>
                        {conflictRefreshing ? t("actions.refreshingConflict") : t("actions.refreshConflict")}
                      </Button>
                    )}
                    {editorConflictLatest && (
                      <ConflictReview
                        state={editorConflictLatest}
                        t={t}
                        onUseLatest={() => {
                          setDraft(draftFromState(editorConflictLatest));
                          setEditor({
                            factionId: editorConflictLatest.faction_id,
                            volumeId: editorConflictLatest.volume_id,
                            source: editorConflictLatest,
                                section: editor.section,
                          });
                          setEditorError("");
                          setEditorConflict(false);
                          setEditorConflictLatest(null);
                        }}
                        onKeepDraft={() => {
                          setEditor({
                            factionId: editorConflictLatest.faction_id,
                            volumeId: editorConflictLatest.volume_id,
                            source: editorConflictLatest,
                                section: editor.section,
                          });
                          setEditorError("");
                          setEditorConflict(false);
                          setEditorConflictLatest(null);
                        }}
                      />
                    )}
                  </>
                )}
              </div>
            )}
            <FactionVolumeStateForm
              section={editor.section}
              value={draft}
              onChange={setDraft}
              disabled={saving || conflictRefreshing}
              fieldErrors={editorFieldErrors}
              errorIdPrefix={`faction-volume-state-${editor.source?.state_id ?? "new"}`}
              autoFocusCurrentGoal={Boolean(editor.source)}
            />
    </>
  );

  const renderEditor = editor && !editor.source && (
    <RetainedModalBackdrop
      isOpen
      onOpenChange={(isOpen) => !isOpen && !saving && !conflictRefreshing && closeEditor()}
      variant="blur"
      isDismissable={!saving && !conflictRefreshing}
      isKeyboardDismissDisabled={saving || conflictRefreshing}
    >
      <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
        <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
          <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
            <div className="min-w-0">
              <Modal.Heading className="text-lg font-semibold text-foreground">
                {editor.source
                  ? t("editor.editTitle")
                  : fixedVolumeId ? t("editor.selectFactionTitle") : t("editor.createTitle")}
              </Modal.Heading>
              <p className="mt-1 break-words text-sm leading-6 text-muted">
                {selectedEditorFaction?.name ?? editor.factionId} · {editor.factionId}
                <br />
                {selectedEditorVolume?.title ?? fixedVolumeTitle ?? editor.volumeId} · {editor.volumeId}
              </p>
            </div>
            <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving || conflictRefreshing} />
          </Modal.Header>
          <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
            {!editor.source && fixedVolumeId && (
              <label className="mb-6 grid gap-1.5 text-xs font-medium text-muted">
                <span>{t("fields.faction")}</span>
                <select
                  value={editor.factionId}
                  onChange={(event) => {
                    setEditor({ ...editor, factionId: event.target.value });
                    setDraft({ ...EMPTY_FIELDS, resources: [] });
                    setEditorError("");
                    setEditorFieldErrors({});
                    setEditorConflict(false);
                    setEditorConflictLatest(null);
                    createCommandRef.current = null;
                  }}
                  className={FILTER_CLASS}
                  disabled={saving || conflictRefreshing}
                  autoFocus
                >
                  {availableCreateFactions.map((faction) => (
                    <option key={faction.faction_id} value={faction.faction_id}>{faction.name} · {faction.faction_id}</option>
                  ))}
                </select>
              </label>
            )}
            {renderEditorFields}
          </Modal.Body>
          <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
            <Button variant="ghost" onPress={closeEditor} isDisabled={saving || conflictRefreshing}>{t("actions.cancel")}</Button>
            <Button variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing}>
              {saving ? t("actions.saving") : t("actions.save")}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </RetainedModalBackdrop>
  );

  const renderLifecycle = lifecycleIntent && (
    <ConfirmActionModal
      title={t(`confirm.${lifecycleIntent.action}.title`)}
      message={(
        <>
          <p>{t(`confirm.${lifecycleIntent.action}.description`, {
            faction: factionNames.get(lifecycleIntent.state.faction_id) ?? lifecycleIntent.state.faction_id,
          })}</p>
          {lifecycleIntent.action === "hard-delete" && (
            <p className="mt-2">
              {t("confirm.deletionSources", {
                sources: lifecycleIntent.state.deletion_sources
                  .map((source) => t(`deletionSource.${source}`))
                  .join(t("listSeparator")),
              })}
            </p>
          )}
        </>
      )}
      confirmText={t(`confirm.${lifecycleIntent.action}.confirm`)}
      cancelText={t("actions.cancel")}
      loadingText={t("actions.processing")}
      danger={lifecycleIntent.action !== "restore"}
      error={lifecycleError}
      isLoading={actionStateId === lifecycleIntent.state.state_id}
      isConfirmDisabled={Boolean(lifecycleError)}
      onCancel={() => {
        if (actionStateId) return;
        setLifecycleIntent(null);
        setLifecycleError("");
      }}
      onConfirm={() => void runLifecycle()}
    />
  );


  return (
    <section className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden" aria-labelledby={`volume-faction-states-${fixedVolumeId}`}>
      <h3 id={`volume-faction-states-${fixedVolumeId}`} className={fixedVolumeDeleted ? "mb-4 text-sm font-semibold tracking-normal text-foreground" : "sr-only"}>
        {fixedVolumeDeleted ? t("trashSection.title") : t("volumeSection.title")}
      </h3>
      <div className={`workspace-toolbar ${detailOpen && selectedState ? "hidden @min-[800px]/master:flex" : "flex"} shrink-0 flex-wrap items-end gap-2 border-b border-border pb-3`}>
        {props.toolbarBefore}
        <label className="grid min-w-[140px] flex-[1_1_160px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.search")}</span>
          <span className="relative block">
            <input type="search" value={search} disabled={busy} onChange={(event) => setSearch(event.target.value)} placeholder={t("filters.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-10 [&::-webkit-search-cancel-button]:hidden`} />
            {filtersActive && <button type="button" title={t("actions.clearFilters")} aria-label={t("actions.clearFilters")} disabled={busy} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-lg text-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50" onClick={() => { setSearch(""); setScopeFilter("all"); setShowTrash(fixedVolumeDeleted); }}>
              <svg aria-hidden="true" className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>}
          </span>
        </label>
        <label className="grid flex-[0_0_110px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.scope")}</span>
          <select value={scopeFilter} disabled={busy} onChange={(event) => setScopeFilter(event.target.value as "all" | FactionVolumeParticipationScope)} className={FILTER_CLASS}>
            <option value="all">{t("filters.allScopes")}</option>
            {PARTICIPATION_SCOPES.map((scope) => <option key={scope} value={scope}>{t(`scope.${scope}`)}</option>)}
          </select>
        </label>
        {fixedVolumeDeleted ? <p className="flex min-h-10 items-center text-sm text-muted">{t("filters.trash")}</p> : <label className="flex min-h-10 shrink-0 items-center gap-2 whitespace-nowrap text-sm text-foreground">
          <input type="checkbox" disabled={busy} checked={showTrash} onChange={(event) => setShowTrash(event.target.checked)} className="size-4 accent-accent" />{t("filters.trash")}
        </label>}
        {!fixedVolumeDeleted && <>
          <Button variant="outline" size="sm" isDisabled={busy || loading || Boolean(loadError) || !fixedVolume || props.generationDisabled} onPress={() => setAiOpen(true)}>{aiT("factions.open")}</Button>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onPress={() => { setInitializeFactionIds([]); setInitializeError(""); setInitializeOpen(true); createCommandRef.current = null; }} isDisabled={busy || loading || fixedVolumeOrderIndex === 1 || eligiblePreviousFactions.length === 0}>{t("actions.initialize")}</Button>
            {(fixedVolumeOrderIndex === 1 || eligiblePreviousFactions.length === 0) && <TooltipHint text={fixedVolumeOrderIndex === 1 ? t("initialize.firstVolume") : t("initialize.noSourceStates")} />}
          </div>
          {availableCreateFactions.length > 0 && <Button variant="primary" size="sm" onPress={() => availableCreateFactions[0] && fixedVolumeId && openCreate(availableCreateFactions[0].faction_id, fixedVolumeId)} isDisabled={busy || loading || !fixedVolume}>{t("actions.create")}</Button>}
        </>}
        <fieldset disabled={loading || Boolean(loadError)} className="contents">{props.toolbarAfter}</fieldset>
      </div>
      {props.beforeContent}

      {loadError && <LoadError message={loadError} title={savedReadFailed && workspaceReady ? aiT("savedReadFailed") : t("errors.load")} loading={loading} onRetry={() => void loadWorkspace()} t={t} />}
      {loading && !workspaceReady ? (
        <div className="border-b border-border py-10 text-center text-sm text-muted" role="status">{t("loading")}</div>
      ) : loadError && !savedReadFailed ? null : filteredStates.length === 0 ? (
        <div className="border-b border-dashed border-border py-10 text-center">
          <p className="text-sm font-medium text-foreground">{filtersActive ? t("empty.filteredTitle") : fixedVolumeDeleted ? t("empty.trashVolumeTitle") : t("empty.volumeTitle")}</p>
        </div>
      ) : (
        <div className={`grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] overflow-visible ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
          <div ref={rosterRef} className={`${detailOpen ? "hidden" : "block"} relative min-h-0 min-w-0 border-border bg-surface @min-[800px]/master:block @min-[800px]/master:border-r`}>
          <aside id={`faction-volume-roster-${fixedVolumeId}`} aria-label={t("roster")} tabIndex={0} className={`${listCollapsed ? "@min-[800px]/master:hidden" : ""} workspace-scrollbar h-full min-h-0 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent`}>
            <ul className="divide-y divide-border">
              {filteredStates.map((state) => (
                <li key={state.state_id}>
                  <button type="button" ref={(node) => { if (node) rowRefs.current.set(state.state_id, node); else rowRefs.current.delete(state.state_id); }}
                    disabled={busy} aria-current={selectedState?.state_id === state.state_id ? "true" : undefined}
                    onClick={() => {
                      setSelectedStateId(state.state_id);
                      setDetailOpen(true);
                      requestAnimationFrame(() => {
                        // 仅窄屏名册隐藏时把焦点交给详情，宽屏继续在名册导航。
                        if (rosterRef.current && getComputedStyle(rosterRef.current).display === "none") detailRef.current?.focus();
                      });
                    }}
                    className={`w-full border-l-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent disabled:cursor-not-allowed ${selectedState?.state_id === state.state_id ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
                    <span className="block truncate text-sm font-semibold text-foreground">{factionNames.get(state.faction_id) ?? state.faction_id}</span>
                    <span className="mt-1 block text-xs text-muted">{t(`scope.${state.participation_scope}`)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <SidebarEdgeHandle controls={`faction-volume-roster-${fixedVolumeId}`} className="hidden @min-[800px]/master:flex"
            leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }}
            rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined} />
          </div>
          {selectedState && <article ref={detailRef} aria-label={t("detail")} tabIndex={0} className={`${detailOpen ? "block" : "hidden"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto bg-surface px-5 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:px-7 @min-[800px]/master:block`}>
            <Button size="sm" variant="ghost" className="mb-3 @min-[800px]/master:hidden" isDisabled={busy} onPress={() => {
              setDetailOpen(false);
              requestAnimationFrame(() => rowRefs.current.get(selectedState.state_id)?.focus());
            }}>{t("actions.backToList")}</Button>
            <h4 className="sr-only">{factionNames.get(selectedState.faction_id) ?? selectedState.faction_id}</h4>
            <header className="mb-4 flex flex-wrap items-center justify-end gap-3">
              {selectedState.is_deleted && <p className="mr-auto text-xs text-muted">{t("status.deleted")}</p>}
              <div className="flex flex-wrap gap-2">
                {selectedState.is_deleted ? <>
                  {selectedState.deletion_sources.includes("user") && <Button size="sm" variant="outline" isDisabled={busy} onPress={() => { setLifecycleIntent({ action: "restore", state: selectedState }); setLifecycleError(""); }}>{t("actions.restore")}</Button>}
                  <Button size="sm" variant="ghost" className="text-danger" isDisabled={busy} onPress={() => { setLifecycleIntent({ action: "hard-delete", state: selectedState }); setLifecycleError(""); }}>{t("actions.hardDelete")}</Button>
                </> : <Button size="sm" variant="ghost" className="text-danger" isDisabled={busy} onPress={() => { setLifecycleIntent({ action: "soft-delete", state: selectedState }); setLifecycleError(""); }}>{t("actions.delete")}</Button>}
              </div>
            </header>
            <div className="space-y-4">
              {STATE_SECTIONS.map((section, index) => <DocumentSection key={section} number={String(index + 1).padStart(2, "0")} title={t(SECTION_TITLES[section])}
                actions={!selectedState.is_deleted && (editor?.source?.state_id === selectedState.state_id && editor.section === section ? <>
                  <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" onPress={closeEditor} isDisabled={saving || conflictRefreshing} />
                  <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing || editorConflict} />
                </> : <SectionEditButton id={`faction-state-edit-${selectedState.state_id}-${section}`} label={t("actions.edit")} isDisabled={busy} onPress={() => openEdit(selectedState, section)} />)}>
                {editor?.source?.state_id === selectedState.state_id && editor.section === section ? renderEditorFields : <dl className="detail-fields grid min-w-0 gap-4">
                  {section === "participation" && <ReadOnlyField label={t("fields.faction")} value={factionNames.get(selectedState.faction_id) ?? selectedState.faction_id} />}
                  {SECTION_FIELDS[section].map((field) => <ReadOnlyField key={field} label={t(`fields.${FIELD_LABELS[field]}`)} wide={!["participation_scope", "active_status", "power_level"].includes(field)} value={field === "participation_scope" ? t(`scope.${selectedState.participation_scope}`) : field === "active_status" ? t(`activeStatus.${selectedState.active_status}`) : field === "resources" ? selectedState.resources.join(t("listSeparator")) || "—" : field === "power_level" ? `${selectedState.power_level}/5` : selectedState[field] || "—"} />)}
                </dl>}
              </DocumentSection>)}
            </div>
          </article>}
        </div>
      )}
      {!fixedVolumeDeleted && fixedVolumeOrderIndex !== null && fixedVolumeOrderIndex > 1 && workspaceReady && previousStatesError && (
        <div className="mt-3 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
          <p>{t("errors.previousStatesLoad")}</p>
          <Button className="mt-2" size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
        </div>
      )}


      {renderEditor}
      {renderLifecycle}

      {aiOpen && fixedVolume && <VolumeEntityCandidateWorkspace
        key={`${props.novelId}:${fixedVolume.volume_id}:factions`}
        kind="factions" novelId={props.novelId} volume={fixedVolume}
        characters={[]} factions={factions} relations={[]}
        onClose={() => setAiOpen(false)}
        onSaved={(result, names) => {
          if (contextKeyRef.current !== contextKey) return;
          loadAbortRef.current?.abort();
          // 正式状态按 ID 合并；候选名称仅用于辨认，不补造完整档案。
          const saved = result.data as FactionVolumeStateReadV1[];
          const targetId = saved[0]?.state_id ?? selectedState?.state_id ?? "";
          confirmedContextRef.current = { scope: contextKey, stateId: targetId };
          pendingVolumeRefreshRef.current = true;
          selectedStateIdRef.current = targetId;
          setStates((current) => [...new Map([...current, ...saved].map((state) => [state.state_id, state])).values()]);
          setSavedNames(names);
          setLoadedContextKey(contextKey);
          setSelectedStateId(targetId);
          setSearch(""); setScopeFilter("all"); setShowTrash(false);
          setDetailOpen(saved.length > 0);
          setAiOpen(false);
          void loadWorkspace();
          requestAnimationFrame(() => {
            if (rosterRef.current && getComputedStyle(rosterRef.current).display === "none") detailRef.current?.focus();
          });
        }}
      />}

      {initializeOpen && fixedVolumeId && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !initializing && setInitializeOpen(false)} variant="blur" isDismissable={!initializing} isKeyboardDismissDisabled={initializing}>
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,760px)] sm:max-w-2xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">{t("initialize.title")}</Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={initializing} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
                {initializeError && <RelationEditorErrorSummary message={initializeError} fieldErrors={{}} className="mb-5" />}
                <fieldset disabled={initializing}>
                  <legend className="text-sm font-semibold text-foreground">{t("initialize.factions")}</legend>
                  <div className="mt-3 divide-y divide-border border-y border-border">
                    {eligiblePreviousFactions.map((faction) => {
                      const checked = initializeFactionIds.includes(faction.faction_id);
                      const exists = anyStateFactionIds.has(faction.faction_id);
                      return (
                        <label key={faction.faction_id} className="flex min-h-11 items-start gap-3 px-1 py-3 text-sm text-foreground">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={exists}
                            onChange={(event) => setInitializeFactionIds((current) => event.target.checked
                              ? [...current, faction.faction_id]
                              : current.filter((id) => id !== faction.faction_id))}
                            className="mt-0.5 size-4 accent-accent"
                          />
                          <span className="min-w-0">
                            <span className="block">{faction.name} · <span className="font-mono text-xs">{faction.faction_id}</span></span>
                            {exists && <span className="mt-1 block text-xs text-muted">{t("initialize.targetExists")}</span>}
                          </span>
                        </label>
                      );
                    })}
                    {eligiblePreviousFactions.length === 0 && <p className="py-5 text-sm text-muted">{t("initialize.noSourceStates")}</p>}
                  </div>
                </fieldset>
                <p className="mt-5 border-y border-amber-500/40 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">{t("initialize.conflictPolicy")}</p>
              </Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" onPress={() => setInitializeOpen(false)} isDisabled={initializing}>{t("actions.cancel")}</Button>
                <Button variant="primary" onPress={() => void runInitialize()} isDisabled={initializing || initializeFactionIds.length === 0}>{initializing ? t("actions.initializing") : t("actions.initialize")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </section>
  );
}

function ConflictReview({ state, onUseLatest, onKeepDraft, t }: {
  state: FactionVolumeStateReadV1;
  onUseLatest: () => void;
  onKeepDraft: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const values = [
    [t("fields.participationScope"), t(`scope.${state.participation_scope}`)],
    [t("fields.activeStatus"), t(`activeStatus.${state.active_status}`)],
    [t("fields.currentGoal"), state.current_goal],
    [t("fields.startState"), state.start_state],
    [t("fields.plannedEndState"), state.planned_end_state || "—"],
    [t("fields.powerLevel"), `${state.power_level}/5`],
    [t("fields.resources"), state.resources.join(t("listSeparator")) || "—"],
    [t("fields.publicStance"), state.public_stance || "—"],
    [t("fields.hiddenAgenda"), state.hidden_agenda || "—"],
    [t("fields.influenceScope"), state.influence_scope || "—"],
  ];
  return (
    <section className="mt-4 border-y border-amber-500/40 bg-amber-50 px-4 py-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" aria-labelledby="faction-volume-state-conflict-latest">
      <h3 id="faction-volume-state-conflict-latest" className="text-sm font-semibold">{t("conflictReview.title", { version: state.version })}</h3>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        {values.map(([label, value]) => <div key={label}><dt className="text-xs font-medium opacity-75">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words">{value}</dd></div>)}
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onPress={onUseLatest}>{t("actions.useLatest")}</Button>
        <Button size="sm" variant="primary" onPress={onKeepDraft}>{t("actions.keepDraftAgainstLatest")}</Button>
      </div>
    </section>
  );
}

function LoadError({ message, title, loading, onRetry, t }: {
  message: string;
  title: string;
  loading: boolean;
  onRetry: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="mt-5 border-y border-red-500/40 bg-red-50 px-4 py-4 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
      <p className="font-semibold">{title}</p>
      <p className="mt-1">{message}</p>
      <Button className="mt-3" variant="outline" size="sm" isDisabled={loading} onPress={onRetry}>{t("actions.retry")}</Button>
    </div>
  );
}

function draftFromState(state: FactionVolumeStateReadV1): FactionVolumeStateFields {
  return {
    participation_scope: state.participation_scope,
    current_goal: state.current_goal,
    start_state: state.start_state,
    planned_end_state: state.planned_end_state,
    power_level: state.power_level,
    resources: [...state.resources],
    public_stance: state.public_stance,
    hidden_agenda: state.hidden_agenda,
    influence_scope: state.influence_scope,
    active_status: state.active_status,
  };
}
