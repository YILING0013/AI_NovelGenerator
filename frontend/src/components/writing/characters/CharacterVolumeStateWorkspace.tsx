"use client";
import { useAssistantFocus, useAssistantRefresh, useAssistantResource } from "../assistant/AssistantContext";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";


import { TooltipHint } from "@/components/shared/TooltipHint";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import DraftChip from "@/components/shared/DraftChip";
import { readCharacterVolumePlanDrafts, writeCharacterVolumePlanDraft, writeCharacterVolumePlanReceipt, type CharacterVolumePlanDraft } from "./characterVolumePlanDrafts";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import DocumentSection from "@/components/shared/DocumentSection";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

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
  CharacterRelationResponseV1,
  CharacterResponseV1,
} from "@/types/character";
import type {
  CharacterVolumeParticipationScope,
  CharacterVolumePlanFieldsV1,
  CharacterVolumePlanCreateV1,
  CharacterVolumePlanUpdateV1,
  CharacterVolumeStateHardDeleteV1,
  CharacterVolumeStateInitializeResultV1,
  CharacterVolumeStateListV1,
  CharacterVolumeStateReadV1,
} from "@/types/characterVolumeState";
import type { VolumeReadV2 } from "@/types/volume";
import CharacterVolumeStateForm from "./CharacterVolumeStateForm";
import CharacterFactsPanel from "./CharacterFactsPanel";
import CharacterLegacyVolumeFields from "./CharacterLegacyVolumeFields";
import CharacterFactCreateDialog from "./CharacterFactCreateDialog";
import CharacterFactConfirmationDialog from "./CharacterFactConfirmationDialog";
import { createEmptyCharacterProfile, profileForCharacterFactDraft } from "./characterFactCreate";
import { writeCharacterFactPreparation, type CharacterFactPreparationV1 } from "./characterFactPreparation";
import type { CharacterFactDraftV1 } from "./characterFactDrafts";
import type { CharacterFactReadResultV1, CharacterFactsAtPositionV1 } from "@/types/characterFacts";
import VolumeEntityCandidateWorkspace from "../volume-entities/VolumeEntityCandidateWorkspace";

export interface CharacterVolumeStateWorkspaceProps {
  novelId: string;
  fixedVolumeId: string;
  requestedEntityId?: string | null;
  fixedVolumeTitle: string;
  fixedVolumeOrderIndex: number;
  fixedVolumeDeleted?: boolean;
  volumeVersion?: number;
  onFormalFactsChanged?: (volume?: VolumeReadV2) => void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  refreshKey?: number;
  toolbarBefore?: ReactNode;
  toolbarAfter?: ReactNode;
  beforeContent?: ReactNode;
  generationDisabled?: boolean;
}

interface ListEnvelope<T> {
  data: T[];
}

type StateSection = "participation" | "relationships";

type EditorState = {
  characterId: string;
  volumeId: string;
  source: CharacterVolumeStateReadV1 | null;
  section?: StateSection;
  adopted?: boolean;
} | null;

type LifecycleIntent = {
  action: "soft-delete" | "restore" | "hard-delete";
  state: CharacterVolumeStateReadV1;
} | null;

const STATE_SECTIONS: StateSection[] = ["participation", "relationships"];
const SECTION_FIELDS: Record<StateSection, (keyof CharacterVolumePlanFieldsV1)[]> = {
  "participation": [
    "participation_scope",
    "current_goal",
    "start_state",
    "planned_end_state",
    "arc_progress"
  ],
  "relationships": [
    "relationship_focus_ids"
  ]
};
const SECTION_TITLES: Record<StateSection, string> = {
  "participation": "form.participationTitle",
  "relationships": "fields.relationshipFocus"
};
const PLAN_FIELDS: (keyof CharacterVolumePlanFieldsV1)[] = [...SECTION_FIELDS.participation, ...SECTION_FIELDS.relationships];
const FIELD_LABELS: Record<keyof CharacterVolumePlanFieldsV1, string> = {
  "participation_scope": "participationScope",
  "current_goal": "currentGoal",
  "start_state": "startState",
  "planned_end_state": "plannedEndState",
  "arc_progress": "arcProgress",
  "relationship_focus_ids": "relationshipFocus"
};

const EMPTY_FIELDS: CharacterVolumePlanFieldsV1 = {
  participation_scope: "secondary",
  current_goal: "",
  start_state: "",
  planned_end_state: "",
  relationship_focus_ids: [],
  arc_progress: 0,
};

const FILTER_CLASS =
  "min-h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const PARTICIPATION_SCOPES: CharacterVolumeParticipationScope[] = [
  "primary",
  "secondary",
  "background",
];
const NO_STATES: CharacterVolumeStateReadV1[] = [];

/**
 * 在卷内角色页用名册和连续详情管理本卷状态。
 *
 * @param props 当前卷、小说 ID、变更和编辑锁定回调。
 * @returns 可独立滚动的名册与原位分节编辑详情。
 */
export default function CharacterVolumeStateWorkspace(props: CharacterVolumeStateWorkspaceProps) {
  const active = useContext(RetainedViewActive);
  const activeRef = useRef(active); activeRef.current = active;
  const t = useTranslations("writing.characterVolumeStates");
  const listT = useTranslations("writing.listLayout");
  const aiT = useTranslations("writing.volumeEntitiesAi");
  const factT = useTranslations("writing.characterFacts");
  const [aiOpen, setAiOpen] = useState(false);
  const [aiMinimized, setAiMinimized] = useState(false);
  const aiTriggerRef = useRef<HTMLButtonElement>(null);
  const [adoptPreparation, setAdoptPreparation] = useState<Extract<CharacterFactPreparationV1, { kind: "create" }> | null>(null);
  const [adoptDraft, setAdoptDraft] = useState<CharacterFactDraftV1 | null>(null);
  const [adoptBusy, setAdoptBusy] = useState(false);
  const adoptBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const [factsBusy, setFactsBusy] = useState(false);
  const [legacyBusy, setLegacyBusy] = useState(false);
  const [selectedFacts, setSelectedFacts] = useState<CharacterFactsAtPositionV1 | null>(null);
  const [leaveError, setLeaveError] = useState("");
  const [leavingFacts, setLeavingFacts] = useState(false);
  const factsBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const legacyBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
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
  const [states, setStates] = useState<CharacterVolumeStateReadV1[]>([]);
  const [characters, setCharacters] = useState<CharacterResponseV1[]>([]);
  const [relations, setRelations] = useState<CharacterRelationResponseV1[]>([]);
  const [volumes, setVolumes] = useState<VolumeReadV2[]>([]);
  const [previousPlans, setPreviousPlans] = useState<{ volumeTitle: string; fields: Record<string, CharacterVolumePlanFieldsV1> } | null>(null);
  const previousStateCharacterIds = Object.keys(previousPlans?.fields ?? {});
  const [previousStatesError, setPreviousStatesError] = useState("");
  const [loadedContextKey, setLoadedContextKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [savedReadFailed, setSavedReadFailed] = useState(false);
  const confirmedContextRef = useRef<{ scope: string; stateId: string } | null>(null);
  const selectedStateIdRef = useRef("");
  const [search, setSearch] = useState("");
  const [scopeFilter, setScopeFilter] = useState<"all" | CharacterVolumeParticipationScope>("all");
  const [showTrash, setShowTrash] = useState(false);
  const [selectedStateId, setSelectedStateId] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [listCollapsed, setListCollapsed] = useState(false);
  const rosterRef = useRef<HTMLDivElement | null>(null);
  const detailRef = useRef<HTMLElement | null>(null);
  const rowRefs = useRef(new Map<string, HTMLButtonElement>());
  const editTriggerRef = useRef<HTMLElement | null>(null);
  const [editor, setEditor] = useState<EditorState>(null);
  const [draft, setDraft] = useState<CharacterVolumePlanFieldsV1>(EMPTY_FIELDS);
  const [previousPlanUse, setPreviousPlanUse] = useState<"pristine" | "edited" | "used">("pristine");
  const [editorError, setEditorError] = useState("");
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [editorConflict, setEditorConflict] = useState(false);
  const [editorConflictLatest, setEditorConflictLatest] = useState<CharacterVolumeStateReadV1 | null>(null);
  const [conflictRefreshing, setConflictRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [lifecycleIntent, setLifecycleIntent] = useState<LifecycleIntent>(null);
  const [lifecycleError, setLifecycleError] = useState("");
  const [actionStateId, setActionStateId] = useState("");
  const [initializeOpen, setInitializeOpen] = useState(false);
  const [initializeCharacterIds, setInitializeCharacterIds] = useState<string[]>([]);
  const [initializeError, setInitializeError] = useState("");
  const [initializing, setInitializing] = useState(false);
  const initializeCommandRef = useRef<{ key: string; characterIds: string[] } | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRef = useRef<AbortController | null>(null);
  const contextKeyRef = useRef(contextKey);
  const planRef = useRef<CharacterVolumePlanDraft | null>(null);
  const persistedPlans = useRef(new Map<string, CharacterVolumePlanDraft>());
  const planQueue = useRef<Promise<unknown>>(Promise.resolve());
  const [planDrafts, setPlanDrafts] = useState<CharacterVolumePlanDraft[]>([]);
  const [planLocalError, setPlanLocalError] = useState("");
  const [planLoading, setPlanLoading] = useState(true);
  const planScope = `${props.novelId}:character-volume-plans:${fixedVolumeId}`;
  const planCommand = planRef.current?.command;
  const planLocked = Boolean(planCommand?.unknown || planCommand?.saved);

  const refreshPlanDrafts = useCallback(async () => {
    const rows = await readCharacterVolumePlanDrafts(planScope);
    if (contextKeyRef.current === contextKey) setPlanDrafts(rows);
  }, [contextKey, planScope]);

  useEffect(() => {
    let live = true;
    setPlanLoading(true); setPlanLocalError(""); setPlanDrafts([]);
    void refreshPlanDrafts().catch(() => { if (live) setPlanLocalError(t("recovery.localFailed")); })
      .finally(() => { if (live) setPlanLoading(false); });
    const refresh = () => { void refreshPlanDrafts().catch(() => { if (live) setPlanLocalError(t("recovery.localFailed")); }); };
    window.addEventListener("focus", refresh);
    return () => { live = false; window.removeEventListener("focus", refresh); };
  }, [refreshPlanDrafts, t]);

  // 每份稿独立排队，完成事务后才推进持有版本；失败时保留输入。
  const persistPlan = useCallback((value: CharacterVolumePlanDraft, remove = false, rejected = false) => {
    const scope = `${props.novelId}:character-volume-plans:${value.editor.volumeId}`;
    const snapshot = structuredClone(value);
    const task = planQueue.current.then(async () => {
      const result = await writeCharacterVolumePlanDraft(scope, snapshot, persistedPlans.current.get(snapshot.key) ?? null, remove, rejected);
      if (remove) persistedPlans.current.delete(snapshot.key);
      else persistedPlans.current.set(snapshot.key, result);
      return result;
    });
    planQueue.current = task.catch(() => {});
    return task;
  }, [props.novelId]);
  const beginPlan = (nextEditor: NonNullable<EditorState>, fields: CharacterVolumePlanFieldsV1, use: CharacterVolumePlanDraft["previousPlanUse"] = "pristine") => {
    planRef.current = { key: crypto.randomUUID(), revision: 0, editor: nextEditor, fields, previousPlanUse: use };
    setPlanLocalError("");
  };
  useEffect(() => {
    const current = planRef.current;
    if (!editor || !current || current.command?.unknown || current.command?.saved) return;
    if (JSON.stringify([current.editor, current.fields, current.previousPlanUse]) === JSON.stringify([editor, draft, previousPlanUse])) return;
    const next = { ...current, revision: current.revision + 1, editor, fields: draft, previousPlanUse };
    planRef.current = next;
    void persistPlan(next).catch(() => { if (planRef.current?.key === next.key) setPlanLocalError(t("recovery.localFailed")); });
  }, [editor, draft, previousPlanUse, persistPlan, t]);

  contextKeyRef.current = contextKey;

  const workspaceReady = loadedContextKey === contextKey;
  const visibleStates = workspaceReady ? states : NO_STATES;
  const characterNames = useMemo(
    () => new Map(characters.map((character) => [character.character_id, character.name] as const)),
    [characters],
  );
  const activeStateCharacterIds = useMemo(
    () => new Set(visibleStates.filter((state) => !state.is_deleted).map((state) => state.character_id)),
    [visibleStates],
  );
  const anyStateCharacterIds = useMemo(
    () => new Set(visibleStates.map((state) => state.character_id)),
    [visibleStates],
  );
  const previousStateCharacterIdSet = new Set(previousStateCharacterIds);
  const availableCreateCharacters = characters.filter((character) => (
    character.status === "active"
    && !character.is_deleted
    && !activeStateCharacterIds.has(character.character_id)
  ));
  const fixedVolume = fixedVolumeId
    ? volumes.find((volume) => volume.volume_id === fixedVolumeId) ?? null
    : null;
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
        characterNames.get(state.character_id) ?? state.character_id,
        state.character_id,
        state.current_goal,
        state.start_state,
      ].join(" ").toLocaleLowerCase().includes(query);
    });
  }, [characterNames, scopeFilter, search, showTrash, visibleStates]);

  const loadWorkspace = useCallback(async () => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestContextKey = contextKey;
    loadAbortRef.current = controller;
    setLoading(true);
    setPreviousStatesError("");
    try {
      const statePath = `/api/character-volume-states/novel/${props.novelId}/volume/${fixedVolumeId}?status=all`;
      const sources = await Promise.allSettled([
        apiGet<CharacterVolumeStateListV1>(statePath, { signal: controller.signal }),
        apiGet<ListEnvelope<CharacterResponseV1>>(`/api/characters/novel/${props.novelId}`, { signal: controller.signal }),
        apiGet<ListEnvelope<CharacterRelationResponseV1>>(`/api/character-relations/novel/${props.novelId}`, { signal: controller.signal }),
        apiGet<ListEnvelope<VolumeReadV2>>(`/api/volumes/novel/${props.novelId}`, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 等这批读取结束再判断；不能让较快的 503 掩盖另一个接口的 403／404。
      const refused = sources.find((source) => source.status === "rejected" && source.reason instanceof ApiRequestError && source.reason.status < 500);
      if (refused?.status === "rejected") throw refused.reason;
      const [stateSource, characterSource, relationSource, volumeSource] = sources;
      if (!fixedVolumeDeleted && volumeSource.status === "fulfilled" && !volumeSource.value.data.some((volume) => volume.volume_id === fixedVolumeId)) throw new ApiRequestError({ status: 404, message: t("errors.load") });
      if (stateSource.status === "rejected") throw stateSource.reason;
      if (characterSource.status === "rejected") throw characterSource.reason;
      if (relationSource.status === "rejected") throw relationSource.reason;
      if (volumeSource.status === "rejected") throw volumeSource.reason;
      const [stateResponse, characterResponse, relationResponse, volumeResponse] = [stateSource.value, characterSource.value, relationSource.value, volumeSource.value] as const;
      let previousPlanSource: typeof previousPlans = null;
      let previousError = "";
      if (fixedVolumeId && !fixedVolumeDeleted && fixedVolumeOrderIndex !== null) {
        const previousVolume = volumeResponse.data
          .filter((volume) => !volume.is_deleted && volume.order_index < fixedVolumeOrderIndex)
          .sort((left, right) => right.order_index - left.order_index)[0];
        if (previousVolume) {
          try {
            const previousStates = await apiGet<CharacterVolumeStateListV1>(
              `/api/character-volume-states/novel/${props.novelId}/volume/${previousVolume.volume_id}?status=active`,
              { signal: controller.signal },
            );
            if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
            previousPlanSource = { volumeTitle: previousVolume.title, fields: Object.fromEntries(previousStates.data
              .filter((state) => !state.is_deleted && state.volume_id === previousVolume.volume_id)
              .map((state) => [state.character_id, draftFromState(state)])) };
          } catch {
            if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
            previousError = t("errors.previousStatesLoad");
          }
        }
      }
      setStates(stateResponse.data);
      setCharacters(characterResponse.data);
      setRelations(relationResponse.data);
      setVolumes(volumeResponse.data);
      setPreviousPlans(previousPlanSource);
      setPreviousStatesError(previousError);
      setLoadedContextKey(requestContextKey);
      setLoadError("");
      readVolumeVersionRef.current = volumeResponse.data.find((volume) => volume.volume_id === fixedVolumeId)?.version;
      const notifyVolume = pendingVolumeRefreshRef.current;
      pendingVolumeRefreshRef.current = false;
      confirmedContextRef.current = null;
      setSavedReadFailed(false);
      if (notifyVolume) onFormalFactsChangedRef.current?.(volumeResponse.data.find((volume) => volume.volume_id === fixedVolumeId));
      return true;
    } catch (failure) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      const temporary = failure instanceof TypeError || failure instanceof ApiRequestError && failure.status >= 500;
      if (!temporary) pendingVolumeRefreshRef.current = false;
      const keepSaved = temporary && confirmedContextRef.current?.scope === requestContextKey
        && confirmedContextRef.current.stateId === selectedStateIdRef.current;
      setSavedReadFailed(keepSaved);
      if (!keepSaved) {
        confirmedContextRef.current = null;
        setStates([]);
        setCharacters([]);
        setRelations([]);
        setVolumes([]);
        setLoadedContextKey("");
      }
      setLoadError(failure instanceof Error ? failure.message : t("errors.load"));
      return false;
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
    setAdoptPreparation(null);
    setAdoptDraft(null);
    setAdoptBusy(false);
    setSelectedFacts(null);
    setLegacyBusy(false);
    setLeaveError("");
    readVolumeVersionRef.current = undefined;
    pendingVolumeRefreshRef.current = false;
    confirmedContextRef.current = null;
    setSavedReadFailed(false);
    setLoadError("");
    setStates([]);
    setCharacters([]);
    setRelations([]);
    setVolumes([]);
    setPreviousPlans(null);
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
    initializeCommandRef.current = null;
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
    planRef.current = null;
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

  const busy = Boolean(editor || lifecycleIntent || initializeOpen || saving || conflictRefreshing || actionStateId || initializing || factsBusy || legacyBusy || adoptBusy || leavingFacts);
  const beforeLeaveRef = props.beforeLeaveRef;
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (planRef.current) await persistPlan(planRef.current); await legacyBeforeLeaveRef.current?.(); await adoptBeforeLeaveRef.current?.(); await factsBeforeLeaveRef.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  }, [beforeLeaveRef, persistPlan]);

  const leaveFacts = async (change: () => void) => {
    if (busy) return;
    setLeavingFacts(true);
    setLeaveError("");
    try {
      await legacyBeforeLeaveRef.current?.();
      await factsBeforeLeaveRef.current?.();
      if (contextKeyRef.current === contextKey) change();
    } catch (failure) {
      setLeaveError(failure instanceof Error ? failure.message : factT("localFailed"));
    } finally {
      setLeavingFacts(false);
    }
  };
  const onBusyChange = props.onBusyChange;
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);

  useEffect(() => {
    if (!active || !editor?.source || !editorError) return;
    const frame = requestAnimationFrame(() => {
      const target = detailRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")
        ?? detailRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, editor, editorError, editorFieldErrors]);

  const requestedEntity = characters.find((row) => row.character_id === props.requestedEntityId);
  const requestedState = states.find((row) => row.character_id === props.requestedEntityId);
  const requestedEntityKey = `${contextKey}:${props.requestedEntityId ?? ""}`;
  const [dismissedEntity, setDismissedEntity] = useState("");
  const unplannedEntity = workspaceReady && requestedEntity && !requestedState && !fixedVolumeDeleted && dismissedEntity !== requestedEntityKey ? requestedEntity : null;
  const consumedEntity = useRef("");
  useEffect(() => {
    if (!active) { consumedEntity.current = ""; setDismissedEntity(""); return; }
    if (!active || !workspaceReady || loading || busy || !props.requestedEntityId) return;
    const key = `${contextKey}:${props.requestedEntityId}`;
    if (consumedEntity.current === key) return;
    if (requestedState) {
      setSelectedStateId(requestedState.state_id); setSearch(""); setScopeFilter("all");
      setShowTrash(Boolean(requestedState.is_deleted)); setDetailOpen(true);
    }
    consumedEntity.current = key;
  }, [active, workspaceReady, loading, busy, contextKey, props.requestedEntityId, requestedState]);

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
  useAssistantRefresh(props.novelId, async () => { await loadWorkspace(); });
  useAssistantFocus("character_volume_state", (target) => { if (busy || !visibleStates.some((state) => state.state_id === target.id)) return false; void leaveFacts(() => { setSelectedStateId(target.id); setShowTrash(Boolean(visibleStates.find((state) => state.state_id === target.id)?.is_deleted)); setSearch(""); setScopeFilter("all"); setDetailOpen(true); }); });
  useAssistantResource(unplannedEntity
    ? { resource_type: "character", id: unplannedEntity.character_id, name: unplannedEntity.name, version: unplannedEntity.version }
    : selectedState ? { resource_type: "character_volume_state", id: selectedState.state_id, name: selectedState.state_id, version: selectedState.version, draft: editor?.source?.state_id === selectedState.state_id ? { text: JSON.stringify(draft), fields: Object.keys(draft), version: editor.source.version } : undefined } : null);

  const openCreate = (characterId: string, volumeId: string) => {
    editTriggerRef.current = document.activeElement as HTMLElement;
    setDraft({ ...EMPTY_FIELDS });
    setPreviousPlanUse("pristine");
    setEditor({ characterId, volumeId, source: null });
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    beginPlan({ characterId, volumeId, source: null }, { ...EMPTY_FIELDS });
  };

  const openEdit = (state: CharacterVolumeStateReadV1, section: StateSection) => {
    editTriggerRef.current = document.activeElement as HTMLElement;
    beginPlan({ characterId: state.character_id, volumeId: state.volume_id, source: state, section }, draftFromState(state));
    setDraft(draftFromState(state));
    setEditor({ characterId: state.character_id, volumeId: state.volume_id, source: state, section });
    requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus());
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
  };

  const closeEditor = async () => {
    if (saving || conflictRefreshing) return;
    const current = planRef.current;
    try {
      if (current) {
        const unchanged = !current.command && JSON.stringify(current.fields) === JSON.stringify(current.editor.source ? draftFromState(current.editor.source) : EMPTY_FIELDS);
        await persistPlan(current, unchanged);
      }
      if (planRef.current?.key !== current?.key) return;
      planRef.current = null;
      setEditor(null);
      await refreshPlanDrafts();
      if (planRef.current || contextKeyRef.current !== contextKey || !activeRef.current) return;
      requestAnimationFrame(() => { if (editTriggerRef.current?.id) document.getElementById(editTriggerRef.current.id)?.focus(); });
      setEditorError(""); setEditorFieldErrors({}); setEditorConflict(false); setEditorConflictLatest(null);
    } catch { setPlanLocalError(t("recovery.localFailed")); }
  };

  const saveEditor = async () => {
    if (!editor || saving || !planRef.current) return;
    const original = planRef.current;
    const recovering = Boolean(original.command?.unknown || original.command?.saved);
    const fields: CharacterVolumePlanFieldsV1 = {
      ...draft,
      current_goal: draft.current_goal.trim(),
      start_state: draft.start_state.trim(),
      planned_end_state: draft.planned_end_state.trim(),
    };
    const payload: CharacterVolumePlanUpdateV1 | CharacterVolumePlanCreateV1 = editor.source
      ? { expected_version: editor.source.version }
      : { ...fields, volume_id: editor.volumeId, character_id: editor.characterId };
    if (editor.source) {
      // 普通编辑只提交本节真正改过的字段，不能夹带其他节或已认领的旧状态。
      for (const field of editor.section ? SECTION_FIELDS[editor.section] : PLAN_FIELDS) {
        if (JSON.stringify(fields[field]) !== JSON.stringify(editor.source[field])) {
          Object.assign(payload, { [field]: fields[field] });
        }
      }
      if (!recovering && Object.keys(payload).length === 1) { void closeEditor(); return; }
    }
    const fieldErrors: ApiFieldErrors = {};
    if (payload.current_goal !== undefined && !payload.current_goal) fieldErrors.current_goal = [t("validation.currentGoalRequired")];
    if (payload.start_state !== undefined && !payload.start_state) fieldErrors.start_state = [t("validation.startStateRequired")];
    if (payload.arc_progress !== undefined && (!Number.isInteger(payload.arc_progress) || payload.arc_progress < 0 || payload.arc_progress > 100)) {
      fieldErrors.arc_progress = [t("validation.arcProgress")];
    }
    if (payload.relationship_focus_ids && payload.relationship_focus_ids.length > 30) {
      fieldErrors.relationship_focus_ids = [t("validation.relationshipLimit")];
    }
    if (!recovering && Object.keys(fieldErrors).length > 0) {
      setEditorError(t("errors.validation"));
      setEditorFieldErrors(fieldErrors);
      focusRelationEditorError(fieldErrors);
      return;
    }
    const command = recovering ? original.command! : {
      key: original.command && JSON.stringify(original.command.body) === JSON.stringify(payload) ? original.command.key : crypto.randomUUID(), method: editor.source ? "PUT" as const : "POST" as const,
      path: editor.source ? `/api/character-volume-states/novel/${props.novelId}/${editor.source.state_id}/plan`
        : `/api/character-volume-states/novel/${props.novelId}/plans`,
      body: { ...payload }, unknown: true,
    };
    let frozen: CharacterVolumePlanDraft = { ...original, revision: original.revision + 1, editor, fields: draft, previousPlanUse, command };
    const requestContextKey = contextKey, scope = planScope;
    const stillHere = () => contextKeyRef.current === requestContextKey && planRef.current?.key === original.key;
    planRef.current = frozen;
    setSaving(true); setEditorError(""); setEditorFieldErrors({}); setPlanLocalError("");
    let dispatched = false, receiptStored = false;
    try {
      // 已收到成功时先补写回执，不能让磁盘上的未知稿阻止同页恢复。
      if (frozen.command!.saved) {
        await writeCharacterVolumePlanReceipt(scope, frozen.command!, frozen.command!.saved!);
        receiptStored = true;
      }
      // 未知请求仍先核对最新稿；成功回执落盘后再核对并清理原稿。
      frozen = await persistPlan(frozen);
      if (stillHere()) planRef.current = frozen;
      if (!frozen.command!.saved) {
        dispatched = true;
        const saved = await (command.method === "PUT" ? apiPut : apiPost)<CharacterVolumeStateReadV1>(command.path, command.body,
          { headers: { "Idempotency-Key": command.key } });
        if (!saved.state_id || !Number.isSafeInteger(saved.version) || saved.version < 1 || saved.novel_id !== props.novelId || saved.volume_id !== editor.volumeId || saved.character_id !== editor.characterId
          || (editor.source && saved.state_id !== editor.source.state_id)) throw new Error("Invalid plan response");
        frozen = { ...frozen, command: { ...command, saved, unknown: false } };
        // 先记住已成功，再落回执；清稿或读取失败不能重新创建。
        if (stillHere()) planRef.current = frozen;
      }
      if (!receiptStored) await writeCharacterVolumePlanReceipt(scope, frozen.command!, frozen.command!.saved!);
      receiptStored = true;
      persistedPlans.current.set(frozen.key, frozen);
      if (!stillHere()) return;
      loadAbortRef.current?.abort(); loadAbortRef.current = null; setLoading(false);
      if (!recovering && editor.source) {
        const saved = frozen.command!.saved!;
        setStates((current) => [saved, ...current.filter((row) => row.state_id !== saved.state_id)]);
        setSelectedStateId(saved.state_id);
        props.onFormalFactsChanged?.();
      } else {
        // 创建回执和恢复回执可能很旧，只展示随后读取的当前资料。
        if (!editor.source) setEditor(null);
        pendingVolumeRefreshRef.current = true;
        if (!await loadWorkspace()) throw new Error("Plan readback failed");
      }
      if (!stillHere()) return;
      await persistPlan(frozen, true);
      if (!stillHere()) return;
      planRef.current = null; setEditor(null); setEditorConflict(false); setEditorConflictLatest(null);
      await refreshPlanDrafts();
      if (contextKeyRef.current === requestContextKey) requestAnimationFrame(() => {
        if (activeRef.current && !planRef.current && editTriggerRef.current?.id) document.getElementById(editTriggerRef.current.id)?.focus();
      });
    } catch (error) {
      // 首发的明确拒绝才解锁；未知写后来的 409 不能证明首次未保存。
      const rejected = dispatched && !recovering && !frozen.command?.saved && error instanceof ApiRequestError && error.status < 500;
      if (rejected) {
        frozen = { ...frozen, revision: frozen.revision + 1, command: { ...command, unknown: false } };
        try { await persistPlan(frozen, false, true); }
        catch { if (stillHere()) setPlanLocalError(t("recovery.localFailed")); return; }
      }
      if (!stillHere()) return;
      planRef.current = frozen;
      const localOnly = !dispatched && !recovering;
      if (localOnly) {
        // 登记失败没有发送，仍保留这次原稿供重试落盘。
        setPlanLocalError(t("recovery.localFailed"));
      }
      const factBlocked = error instanceof ApiRequestError && (error.code === "CHARACTER_FACT_MANAGED_FIELDS" || error.code === "CHARACTER_FACT_CONTRACT_REQUIRED");
      setEditorError(frozen.command?.saved ? t("recovery.saved") : rejected && error instanceof ApiRequestError
        ? !editor.source || factBlocked ? error.message : error.status === 409 ? t("errors.conflict") : t("errors.save") : t("recovery.unknown"));
      // 回执还没落盘时保留表单和内存成功，按钮继续重试回执；落盘后才交给草稿入口。
      if (frozen.command?.saved && !editor.source && receiptStored) {
        planRef.current = null; setEditor(null); setSaving(false);
        try { await refreshPlanDrafts(); }
        catch { if (contextKeyRef.current === requestContextKey) setPlanLocalError(t("recovery.localFailed")); }
        if (contextKeyRef.current !== requestContextKey || planRef.current) return;
      }
      setEditorConflict(Boolean(rejected && editor.source && error instanceof ApiRequestError && error.status === 409));
      setEditorConflictLatest(null);
      if (rejected && error instanceof ApiRequestError) {
        const normalized: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) normalized[field.split(".").at(-1) ?? field] = messages;
        setEditorFieldErrors(normalized); if (activeRef.current) focusRelationEditorError(normalized);
      }
    } finally { if (stillHere()) setSaving(false); else if (contextKeyRef.current === requestContextKey && !planRef.current) setSaving(false); }
  };

  const refreshEditorConflict = async () => {
    if (!editor || conflictRefreshing) return;
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    const requestContextKey = contextKey;
    mutationAbortRef.current = controller;
    setConflictRefreshing(true);
    try {
      let refreshed: CharacterVolumeStateReadV1 | undefined;
      if (editor.source) {
        refreshed = await apiGet<CharacterVolumeStateReadV1>(
          `/api/character-volume-states/novel/${props.novelId}/${editor.source.state_id}`,
          { signal: controller.signal },
        );
      } else {
        const response = await apiGet<CharacterVolumeStateListV1>(
          `/api/character-volume-states/novel/${props.novelId}/volume/${editor.volumeId}?status=all`,
          { signal: controller.signal },
        );
        refreshed = response.data.find((state) => state.character_id === editor.characterId);
      }
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      if (!refreshed || refreshed.is_deleted) {
        setEditorError(t(refreshed ? "errors.deletedConflict" : "errors.conflictMissing"));
        setEditorFieldErrors({});
        setEditorConflictLatest(null);
        return;
      }
      setStates((current) => [refreshed, ...current.filter((state) => state.state_id !== refreshed.state_id)]);
      // 只展示最新正式值，不静默替换 CAS 版本；必须由用户明确选择保留草稿或采用正式值。
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
        await apiDelete<CharacterVolumeStateHardDeleteV1>(
          `/api/character-volume-states/novel/${props.novelId}/${state.state_id}/hard?expected_version=${state.version}`,
          { signal: controller.signal },
        );
        if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
        setStates((current) => current.filter((item) => item.state_id !== state.state_id));
      } else {
        const saved = action === "restore"
          ? await apiPost<CharacterVolumeStateReadV1>(
              `/api/character-volume-states/novel/${props.novelId}/${state.state_id}/restore`,
              { expected_version: state.version },
              { signal: controller.signal },
            )
          : await apiDelete<CharacterVolumeStateReadV1>(
              `/api/character-volume-states/novel/${props.novelId}/${state.state_id}?expected_version=${state.version}`,
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
      if (error instanceof ApiRequestError && error.status === 409) {
        // 生命周期动作没有草稿可合并；刷新名册并要求用户关闭后从最新版本重新确认。
        void loadWorkspace();
      }
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setActionStateId("");
      }
    }
  };

  // 兼容旧资料的完整状态复制；普通本卷计划使用上面的六字段填稿和 /plans。
  const runInitialize = async () => {
    if (!fixedVolumeId || initializing || initializeCharacterIds.length === 0) return;
    const requestContextKey = contextKey;
    const wasPending = Boolean(initializeCommandRef.current);
    const command = initializeCommandRef.current ?? {
      key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      characterIds: [...initializeCharacterIds],
    };
    initializeCommandRef.current = command;
    mutationAbortRef.current?.abort();
    const controller = new AbortController();
    mutationAbortRef.current = controller;
    setInitializing(true);
    setInitializeError("");
    try {
      await apiPost<CharacterVolumeStateInitializeResultV1>(
        `/api/character-volume-states/novel/${props.novelId}/volume/${fixedVolumeId}/initialize-from-previous`,
        { character_ids: command.characterIds, skip_existing: false },
        {
          headers: { "Idempotency-Key": command.key },
          signal: controller.signal,
        },
      );
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 原请求可能回放很早的成功结果；当前资料只采纳随后重新读取的值。
      confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
      setSelectedStateId(selectedStateIdRef.current);
      pendingVolumeRefreshRef.current = true;
      setInitializeOpen(false);
      setInitializeCharacterIds([]);
      initializeCommandRef.current = null;
      void loadWorkspace();
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 原请求结果不明时，后来目标不可用等拒绝不能证明首次没有成功。
      if (!wasPending && error instanceof ApiRequestError && error.status < 500) initializeCommandRef.current = null;
      setInitializeError(error instanceof ApiRequestError
        ? error.code === "CHARACTER_VOLUME_STATE_INITIALIZATION_CONFLICT" ? t("errors.initializeConflict") : error.message
        : t("errors.initialize"));
    } finally {
      if (mutationAbortRef.current === controller && contextKeyRef.current === requestContextKey) {
        mutationAbortRef.current = null;
        setInitializing(false);
      }
    }
  };

  const initializeCharacters = initializeCommandRef.current
    ? initializeCommandRef.current.characterIds.map((characterId) => ({ character_id: characterId, name: characterNames.get(characterId) ?? characterId }))
    : characters.filter((character) => character.status === "active" && !character.is_deleted && previousStateCharacterIdSet.has(character.character_id));
  const selectedEditorCharacter = editor
    ? characters.find((character) => character.character_id === editor.characterId) ?? null
    : null;
  const selectedEditorVolume = editor
    ? volumes.find((volume) => volume.volume_id === editor.volumeId) ?? null
    : null;

  const renderEditorFields = editor && (
    <>
      {planLocalError && <p role="alert" className="text-sm text-danger">{planLocalError}</p>}
      {planLocked && !saving && !editorError && <p role="status" className="text-sm text-muted">{t(planCommand?.saved ? "recovery.saved" : "recovery.unknown")}</p>}
            {editorError && (
              <div className="mb-6">
                <RelationEditorErrorSummary
                  message={editorError}
                  fieldErrors={editorFieldErrors}
                />
                {editorConflict && (
                  <>
                    {!editorConflictLatest && (
                      <Button className="mt-3" size="sm" variant="outline" onPress={() => void refreshEditorConflict()} isDisabled={conflictRefreshing}>
                        {conflictRefreshing ? t("actions.refreshingConflict") : t("actions.refreshConflict")}
                      </Button>
                    )}
                    {editorConflictLatest && (
                      <section className="mt-4 border-y border-amber-500/40 bg-amber-50 px-4 py-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" aria-labelledby="character-volume-state-conflict-latest">
                        <h3 id="character-volume-state-conflict-latest" className="text-sm font-semibold">
                          {t("conflictReview.title", { version: editorConflictLatest.version })}
                        </h3>
                        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                          <div>
                            <dt className="text-xs font-medium opacity-75">{t("fields.participationScope")}</dt>
                            <dd className="mt-1">{t(`scope.${editorConflictLatest.participation_scope}`)}</dd>
                          </div>
                          <div>
                            <dt className="text-xs font-medium opacity-75">{t("fields.currentGoal")}</dt>
                            <dd className="mt-1 whitespace-pre-wrap break-words">{editorConflictLatest.current_goal}</dd>
                          </div>
                          <div>
                            <dt className="text-xs font-medium opacity-75">{t("fields.startState")}</dt>
                            <dd className="mt-1 whitespace-pre-wrap break-words">{editorConflictLatest.start_state}</dd>
                          </div>
                          <div>
                            <dt className="text-xs font-medium opacity-75">{t("fields.plannedEndState")}</dt>
                            <dd className="mt-1 whitespace-pre-wrap break-words">{editorConflictLatest.planned_end_state || "—"}</dd>
                          </div>
                          <div>
                            <dt className="text-xs font-medium opacity-75">{t("fields.arcProgress")}</dt>
                            <dd className="mt-1">{editorConflictLatest.arc_progress}%</dd>
                          </div>
                          <div className="sm:col-span-2">
                            <dt className="text-xs font-medium opacity-75">{t("fields.relationshipFocus")}</dt>
                            <dd className="mt-1 whitespace-pre-wrap break-words">
                              {relationNames(editorConflictLatest, relations, characterNames).join(t("listSeparator")) || "—"}
                            </dd>
                          </div>
                        </dl>
                        <div className="mt-4 flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onPress={() => {
                              setDraft(draftFromState(editorConflictLatest));
                              setEditor({
                                characterId: editorConflictLatest.character_id,
                                volumeId: editorConflictLatest.volume_id,
                                source: editorConflictLatest,
                                section: editor.section,
                                adopted: editor.adopted,
                              });
                              setEditorError("");
                              setEditorConflict(false);
                              setEditorConflictLatest(null);
                            }}
                          >
                            {t("actions.useLatest")}
                          </Button>
                          <Button
                            size="sm"
                            variant="primary"
                            onPress={() => {
                              const revised = draftFromState(editorConflictLatest);
                              // 作者只保留自己改过的字段，同节未改内容使用刚展示的最新值。
                              for (const field of editor.section ? SECTION_FIELDS[editor.section] : PLAN_FIELDS) {
                                if (JSON.stringify(draft[field]) !== JSON.stringify(editor.source![field])) {
                                  Object.assign(revised, { [field]: draft[field] });
                                }
                              }
                              setDraft(revised);
                              setEditor({
                                characterId: editorConflictLatest.character_id,
                                volumeId: editorConflictLatest.volume_id,
                                source: editorConflictLatest,
                                section: editor.section,
                                adopted: editor.adopted,
                              });
                              setEditorError("");
                              setEditorConflict(false);
                              setEditorConflictLatest(null);
                            }}
                          >
                            {t("actions.keepDraftAgainstLatest")}
                          </Button>
                        </div>
                      </section>
                    )}
                  </>
                )}
              </div>
            )}
            <CharacterVolumeStateForm
              section={editor.section}
              value={draft}
              onChange={(fields) => { setDraft(fields); setPreviousPlanUse((current) => current === "used" ? current : "edited"); }}
              characterId={editor.characterId}
              relations={relations}
              characterNames={characterNames}
              disabled={saving || conflictRefreshing || planLocked}
              fieldErrors={editorFieldErrors}
              errorIdPrefix={`character-volume-state-${editor.source?.state_id ?? "new"}`}
              autoFocusCurrentGoal={Boolean(editor.source)}
            />
    </>
  );

  const renderEditor = editor && (!editor.source || !editor.section || !visibleStates.some((row) => row.state_id === editor.source?.state_id)) && (
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
                  : fixedVolumeId ? t("editor.selectCharacterTitle") : t("editor.createTitle")}
              </Modal.Heading>
              <p className="mt-1 break-words text-sm leading-6 text-muted">{selectedEditorVolume?.title ?? fixedVolumeTitle}</p>
            </div>
            <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving || conflictRefreshing} />
          </Modal.Header>
          <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
            {!editor.source && !editor.adopted && fixedVolumeId && (
              <label className="mb-4 grid gap-1.5 text-xs font-medium text-muted">
                <span>{t("fields.character")}</span>
                <select
                  value={editor.characterId}
                  onChange={(event) => {
                    setEditor({ ...editor, characterId: event.target.value });
                    setDraft({ ...EMPTY_FIELDS });
                    setPreviousPlanUse("pristine");
                    setEditorError("");
                    setEditorFieldErrors({});
                    setEditorConflict(false);
                    setEditorConflictLatest(null);
                    beginPlan({ ...editor, characterId: event.target.value }, { ...EMPTY_FIELDS });
                  }}
                  className={`${FILTER_CLASS} min-w-0 w-full`}
                  disabled={saving || conflictRefreshing || planLocked}
                  autoFocus
                >
                  {availableCreateCharacters.map((character) => (
                    <option key={character.character_id} value={character.character_id}>{character.name}</option>
                  ))}
                </select>
              </label>
            )}
            {(editor.source || editor.adopted || !fixedVolumeId) && <p className="mb-4 text-sm font-medium">{selectedEditorCharacter?.name ?? editor.characterId}</p>}
            <CharacterFactsPanel novelId={props.novelId} characterId={editor.characterId}
              initialPosition={{ version: 1, intent: "volume_start", target_type: "volume", target_id: editor.volumeId }} readOnly volumeStartPreview />
            {editor.adopted && <section className="mb-6 border-b border-border pb-5" aria-label={editor.source ? t("version", { version: editor.source.version }) : t("editor.noCurrentPlan")}>
              <h3 className="mb-3 text-sm font-semibold">{editor.source ? t("version", { version: editor.source.version }) : t("editor.noCurrentPlan")}</h3>
              {editor.source && <dl className="detail-fields grid gap-4">{PLAN_FIELDS.map((field) => <ReadOnlyField key={field} label={t(`fields.${FIELD_LABELS[field]}`)} wide value={field === "participation_scope" ? t(`scope.${editor.source!.participation_scope}`) : field === "relationship_focus_ids" ? relationNames(editor.source!, relations, characterNames).join(t("listSeparator")) || "—" : field === "arc_progress" ? `${editor.source!.arc_progress}%` : editor.source![field] || "—"} />)}</dl>}
            </section>}
            <section className="mt-4 space-y-4 border-t border-border pt-4" aria-label={t("planTitle")}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">{t("planTitle")}</h3>
                {!editor.source && !editor.adopted && !anyStateCharacterIds.has(editor.characterId) && previousPlans?.fields[editor.characterId] && <Button size="sm" variant="outline"
                  isDisabled={saving || conflictRefreshing || planLocked || previousPlanUse !== "pristine" || Boolean(planRef.current?.command)}
                  onPress={() => {
                    if (saving || conflictRefreshing || planLocked || previousPlanUse !== "pristine" || planRef.current?.command || anyStateCharacterIds.has(editor.characterId)) return;
                    const fields = previousPlans?.fields[editor.characterId];
                    if (!fields) return;
                    setDraft(structuredClone(fields));
                    setPreviousPlanUse("used");
                  }}>{t("reusePrevious.action")}</Button>}
              </div>
              {!editor.source && !editor.adopted && previousPlans?.fields[editor.characterId] && !anyStateCharacterIds.has(editor.characterId) && <p className="text-xs leading-6 text-muted" role={previousPlanUse === "used" ? "status" : undefined}>
                {t(previousPlanUse === "used" ? "reusePrevious.used" : previousPlanUse === "edited" ? "reusePrevious.edited" : "reusePrevious.hint", { volume: previousPlans.volumeTitle })}
              </p>}
              {renderEditorFields}
            </section>
          </Modal.Body>
          <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
            <Button variant="ghost" onPress={closeEditor} isDisabled={saving || conflictRefreshing}>{t("actions.cancel")}</Button>
            <Button variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing}>
              {saving ? t("actions.saving") : t(planCommand?.saved ? "recovery.finish" : planCommand?.unknown ? "recovery.retry" : "actions.save")}
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
            character: characterNames.get(lifecycleIntent.state.character_id) ?? lifecycleIntent.state.character_id,
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
    <section className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden" aria-labelledby={`volume-character-states-${fixedVolumeId}`}>
      <div className={aiOpen && !aiMinimized ? "hidden" : "flex min-h-0 flex-1 flex-col"}>
      <h3 id={`volume-character-states-${fixedVolumeId}`} className={fixedVolumeDeleted ? "mb-4 text-sm font-semibold tracking-normal text-foreground" : "sr-only"}>
        {fixedVolumeDeleted ? t("trashSection.title") : t("volumeSection.title")}
      </h3>
      {!editor && <div className="flex shrink-0 flex-wrap gap-2">
        {planLocalError && <p role="alert" className="text-sm text-danger">{planLocalError}</p>}
        {planDrafts.map((row) => <DraftChip key={row.key} label={characterNames.get(row.editor.characterId) ?? row.editor.characterId}
          status={row.command?.saved ? "saved" : row.command?.unknown ? "pending" : "draft"} isDisabled={busy || planLoading}
          onResume={() => { void (async () => {
            try {
              const fresh = (await readCharacterVolumePlanDrafts(planScope)).find((item) => item.key === row.key);
              if (!fresh || planRef.current || contextKeyRef.current !== contextKey) return;
              persistedPlans.current.set(fresh.key, fresh); planRef.current = fresh;
              setDraft(fresh.fields); setPreviousPlanUse(fresh.previousPlanUse); setEditor(fresh.editor);
              if (fresh.editor.source) { setSelectedStateId(fresh.editor.source.state_id); setDetailOpen(true); setSearch(""); setScopeFilter("all"); }
              setEditorError(""); setEditorFieldErrors({}); setEditorConflict(false); setEditorConflictLatest(null); setPlanLocalError("");
            } catch { setPlanLocalError(t("recovery.localFailed")); }
          })(); }} onDiscard={row.command?.unknown ? undefined : async () => {
            await writeCharacterVolumePlanDraft(planScope, row, row, true); await refreshPlanDrafts();
          }} />)}
      </div>}
      <div className={`workspace-toolbar ${detailOpen && selectedState ? "hidden @min-[800px]/master:flex" : "flex"} shrink-0 flex-wrap items-end gap-2 border-b border-border pb-3`}>
        {props.toolbarBefore}
        <label className="grid min-w-[140px] flex-[1_1_160px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.search")}</span>
          <span className="relative block">
            <input type="search" value={search} disabled={busy} onChange={(event) => { const value = event.target.value; void leaveFacts(() => setSearch(value)); }} placeholder={t("filters.searchPlaceholder")} className={`${FILTER_CLASS} w-full pr-10 [&::-webkit-search-cancel-button]:hidden`} />
            {filtersActive && <button type="button" title={t("actions.clearFilters")} aria-label={t("actions.clearFilters")} disabled={busy} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-lg text-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50" onClick={() => void leaveFacts(() => { setSearch(""); setScopeFilter("all"); setShowTrash(fixedVolumeDeleted); })}>
              <svg aria-hidden="true" className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>}
          </span>
        </label>
        <label className="grid flex-[0_0_110px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.scope")}</span>
          <select value={scopeFilter} disabled={busy} onChange={(event) => { const value = event.target.value as "all" | CharacterVolumeParticipationScope; void leaveFacts(() => setScopeFilter(value)); }} className={FILTER_CLASS}>
            <option value="all">{t("filters.allScopes")}</option>
            {PARTICIPATION_SCOPES.map((scope) => <option key={scope} value={scope}>{t(`scope.${scope}`)}</option>)}
          </select>
        </label>
        {fixedVolumeDeleted ? <p className="flex min-h-10 items-center text-sm text-muted">{t("filters.trash")}</p> : <TooltipHint text={t("filters.trash")}>
          <Button isIconOnly size="sm" variant="ghost" aria-label={t("filters.trash")} aria-pressed={showTrash} isDisabled={busy} className={`size-11 shrink-0 sm:size-10 ${showTrash ? "border border-accent bg-selected text-accent" : "text-muted"}`} onPress={() => { const value = !showTrash; void leaveFacts(() => setShowTrash(value)); }}>
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4"><path d="M3 6h18M9 6V4h6v2M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg>
          </Button>
        </TooltipHint>}
        {!fixedVolumeDeleted && <>
          <Button ref={aiTriggerRef} variant="outline" size="sm" isDisabled={busy || loading || Boolean(loadError) || !fixedVolume || props.generationDisabled} onPress={() => { setAiMinimized(false); setAiOpen(true); }}>{aiT("characters.open")}</Button>
          {availableCreateCharacters.length > 0 && <Button variant="primary" size="sm" onPress={() => availableCreateCharacters[0] && fixedVolumeId && openCreate(availableCreateCharacters[0].character_id, fixedVolumeId)} isDisabled={busy || loading || !fixedVolume}>{t("actions.create")}</Button>}
        </>}
        <fieldset disabled={loading || Boolean(loadError)} className="contents">{props.toolbarAfter}</fieldset>
      </div>
      {!fixedVolumeDeleted && (previousStateCharacterIds.length > 0 || initializeCommandRef.current) && <details className="shrink-0 border-b border-border py-2">
        <summary className="cursor-pointer text-xs text-muted">{t("initialize.legacyTitle")}</summary>
        <p className="mt-2 text-xs leading-6 text-muted">{t("initialize.legacyHint")}</p>
        <Button variant="ghost" size="sm" isDisabled={busy || loading} onPress={() => {
          setInitializeCharacterIds(initializeCommandRef.current?.characterIds ?? []);
          setInitializeError(""); setInitializeOpen(true);
        }}>{t(initializeCommandRef.current ? "initialize.resume" : "initialize.legacyAction")}</Button>
      </details>}
      {props.beforeContent}

      {loadError && (
        <div className="border-y border-red-500/40 bg-red-50 px-4 py-4 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
          <p className="font-semibold">{savedReadFailed && workspaceReady ? aiT("savedReadFailed") : t("errors.load")}</p>
          <p className="mt-1">{loadError}</p>
          <Button className="mt-3" variant="outline" size="sm" isDisabled={loading} onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
        </div>
      )}
      {loading && !workspaceReady ? (
        <div className="border-b border-border py-10 text-center text-sm text-muted" role="status">{t("loading")}</div>
      ) : loadError && !savedReadFailed ? null : unplannedEntity ? (
        <article aria-label={t("detail")} tabIndex={0} className="workspace-scrollbar min-h-0 flex-1 overflow-y-auto bg-surface px-5 py-4 sm:px-7">
          <div className="mb-3 flex flex-wrap items-center gap-3"><h3 className="min-w-0 break-words text-sm font-semibold">{unplannedEntity.name}</h3><Button size="sm" variant="ghost" isDisabled={busy} onPress={() => void leaveFacts(() => setDismissedEntity(requestedEntityKey))}>{t("actions.backToList")}</Button></div>
          <CharacterFactsPanel novelId={props.novelId} characterId={unplannedEntity.character_id}
            initialPosition={{ version: 1, intent: "volume_start", target_type: "volume", target_id: fixedVolumeId! }}
            readOnly={Boolean(editor || saving)} onBusy={setFactsBusy}
            beforeLeaveRef={factsBeforeLeaveRef} onChanged={async () => { await loadWorkspace(); }} />
        </article>
      ) : filteredStates.length === 0 ? (
        <div className="border-b border-dashed border-border py-10 text-center">
          <p className="text-sm font-medium text-foreground">
            {filtersActive ? t("empty.filteredTitle") : fixedVolumeDeleted ? t("empty.trashVolumeTitle") : t("empty.volumeTitle")}
          </p>
        </div>
      ) : (
        <div className={`grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] overflow-visible ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
          <div ref={rosterRef} className={`${detailOpen ? "hidden" : "block"} relative min-h-0 min-w-0 border-border bg-surface @min-[800px]/master:block @min-[800px]/master:border-r`}>
          <aside id={`character-volume-roster-${fixedVolumeId}`} aria-label={t("roster")} tabIndex={0} className={`${listCollapsed ? "@min-[800px]/master:hidden" : ""} workspace-scrollbar h-full min-h-0 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent`}>
            <ul className="divide-y divide-border">
              {filteredStates.map((state) => (
                <li key={state.state_id}>
                  <button type="button" ref={(node) => { if (node) rowRefs.current.set(state.state_id, node); else rowRefs.current.delete(state.state_id); }}
                    disabled={busy} aria-current={selectedState?.state_id === state.state_id ? "true" : undefined}
                    onClick={() => void leaveFacts(() => {
                      setSelectedStateId(state.state_id);
                      setDetailOpen(true);
                      requestAnimationFrame(() => {
                        // 仅窄屏名册隐藏时把焦点交给详情，宽屏继续在名册导航。
                        if (rosterRef.current && getComputedStyle(rosterRef.current).display === "none") detailRef.current?.focus();
                      });
                    })}
                    className={`w-full border-l-2 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent disabled:cursor-not-allowed ${selectedState?.state_id === state.state_id ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
                    <span className="block truncate text-sm font-semibold text-foreground">{characterNames.get(state.character_id) ?? state.character_id}</span>
                    <span className="mt-1 block text-xs text-muted">{t(`scope.${state.participation_scope}`)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <SidebarEdgeHandle controls={`character-volume-roster-${fixedVolumeId}`} className="hidden @min-[800px]/master:flex"
            leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }}
            rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined} />
          </div>
          {selectedState && <article ref={detailRef} aria-label={t("detail")} tabIndex={0} className={`${detailOpen ? "block" : "hidden"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto bg-surface px-5 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent sm:px-7 @min-[800px]/master:block`}>
            <Button size="sm" variant="ghost" className="mb-3 @min-[800px]/master:hidden" isDisabled={busy} onPress={() => void leaveFacts(() => {
              setDetailOpen(false);
              requestAnimationFrame(() => rowRefs.current.get(selectedState.state_id)?.focus());
            })}>{t("actions.backToList")}</Button>
            <h4 className="sr-only">{characterNames.get(selectedState.character_id) ?? selectedState.character_id}</h4>
            {leaveError && <p role="alert" className="mb-3 text-sm text-danger">{leaveError}</p>}
            <header className="mb-4 flex flex-wrap items-center justify-end gap-3">
              {selectedState.is_deleted && <p className="mr-auto text-xs text-muted">{t("status.deleted")}</p>}
              <div className="flex flex-wrap gap-2">
                {selectedState.is_deleted ? <>
                  {selectedState.deletion_sources.includes("user") && <Button size="sm" variant="outline" isDisabled={busy} onPress={() => void leaveFacts(() => { setLifecycleIntent({ action: "restore", state: selectedState }); setLifecycleError(""); })}>{t("actions.restore")}</Button>}
                  <Button size="sm" variant="ghost" className="text-danger" isDisabled={busy} onPress={() => void leaveFacts(() => { setLifecycleIntent({ action: "hard-delete", state: selectedState }); setLifecycleError(""); })}>{t("actions.hardDelete")}</Button>
                </> : <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" isDisabled={busy} onPress={() => void leaveFacts(() => { setLifecycleIntent({ action: "soft-delete", state: selectedState }); setLifecycleError(""); })} />}
              </div>
            </header>
            <div className="space-y-4">
              {STATE_SECTIONS.map((section) => <Fragment key={section}><DocumentSection number={section === "participation" ? "01" : "06"} title={t(SECTION_TITLES[section])}
                actions={!selectedState.is_deleted && (editor?.source?.state_id === selectedState.state_id && editor.section === section ? <>
                  <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" onPress={closeEditor} isDisabled={saving || conflictRefreshing} />
                  {planLocked ? <Button size="sm" variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing}>{t(planCommand?.saved ? "recovery.finish" : "recovery.retry")}</Button> : <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing || editorConflict} />}
                </> : <SectionEditButton id={`character-state-edit-${selectedState.state_id}-${section}`} label={t("actions.edit")} isDisabled={busy} onPress={() => openEdit(selectedState, section)} />)}>
                {editor?.source?.state_id === selectedState.state_id && editor.section === section ? renderEditorFields : <dl className="detail-fields grid min-w-0 gap-4">
                  {section === "participation" && <ReadOnlyField label={t("fields.character")} value={characterNames.get(selectedState.character_id) ?? selectedState.character_id} />}
                  {SECTION_FIELDS[section].map((field) => <ReadOnlyField key={field} label={t(`fields.${FIELD_LABELS[field]}`)} wide={!["participation_scope", "arc_progress"].includes(field)} value={field === "participation_scope" ? t(`scope.${selectedState.participation_scope}`) : field === "relationship_focus_ids" ? relationNames(selectedState, relations, characterNames).join(t("listSeparator")) || "—" : field === "arc_progress" ? `${selectedState.arc_progress}%` : selectedState[field] || "—"} />)}
                </dl>}
              </DocumentSection>
              {section === "participation" && <>
                <CharacterFactsPanel novelId={props.novelId} characterId={selectedState.character_id} numberOffset={1}
                  initialPosition={{ version: 1, intent: "volume_start", target_type: "volume", target_id: selectedState.volume_id }}
                  readOnly={fixedVolumeDeleted || selectedState.is_deleted || Boolean(editor) || legacyBusy}
                  onRead={setSelectedFacts}
                  onChanged={async () => {
                    if (contextKeyRef.current !== contextKey) return;
                    confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
                    setSelectedStateId(selectedStateIdRef.current);
                    pendingVolumeRefreshRef.current = true;
                    await loadWorkspace();
                  }} onBusy={setFactsBusy} beforeLeaveRef={factsBeforeLeaveRef} />
                <details className="border-y border-border py-3">
                  <summary className="cursor-pointer text-sm text-muted">{t("legacyStatesTitle")}</summary>
                  <div className="mt-3"><CharacterLegacyVolumeFields key={selectedState.state_id} state={selectedState}
                    claimedFields={selectedFacts?.character_id === selectedState.character_id ? selectedFacts.claimed_fields : undefined}
                    disabled={fixedVolumeDeleted || selectedState.is_deleted || Boolean(editor) || factsBusy}
                    onBusy={setLegacyBusy} beforeLeaveRef={legacyBeforeLeaveRef}
                    onSave={async (patch) => {
                      await apiPut<CharacterVolumeStateReadV1>(`/api/character-volume-states/novel/${props.novelId}/${selectedState.state_id}`, patch);
                      confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
                      setSelectedStateId(selectedStateIdRef.current);
                      pendingVolumeRefreshRef.current = true;
                    }}
                    onReadback={async () => { if (!await loadWorkspace()) throw new Error(factT("savedReadFailed")); }}
                  /></div>
                </details>
              </>}
              </Fragment>)}
            </div>
          </article>}
        </div>
      )}
      {!fixedVolumeDeleted && fixedVolumeOrderIndex !== null && fixedVolumeOrderIndex > 1 && workspaceReady && previousStatesError && (
        <div className="mt-3 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
          <p>{t("errors.previousStatesLoad")}</p>
          <p className="mt-1">{previousStatesError}</p>
          <Button className="mt-2" size="sm" variant="outline" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
        </div>
      )}


      {renderEditor}
      {renderLifecycle}

      </div>
      {aiOpen && fixedVolume && <VolumeEntityCandidateWorkspace
        minimized={aiMinimized} onMinimizedChange={setAiMinimized}
        key={`${props.novelId}:${fixedVolume.volume_id}:characters`}
        kind="characters" novelId={props.novelId} volume={fixedVolume}
        characters={characters} factions={[]} relations={relations}
        adoptionOpen={Boolean(adoptPreparation || adoptDraft || editor)}
        onAdoptPlan={async (characterId, fields) => {
          if (editor || adoptPreparation || adoptDraft || contextKeyRef.current !== contextKey) return;
          editTriggerRef.current = document.activeElement as HTMLElement;
          setAdoptBusy(true);
          try {
            await legacyBeforeLeaveRef.current?.();
            await factsBeforeLeaveRef.current?.();
            const [latest, people] = await Promise.all([
              apiGet<CharacterVolumeStateListV1>(`/api/character-volume-states/novel/${props.novelId}/volume/${fixedVolume.volume_id}?status=all`),
              apiGet<ListEnvelope<CharacterResponseV1>>(`/api/characters/novel/${props.novelId}`),
            ]);
            if (contextKeyRef.current !== contextKey) return;
            const character = people.data.find((item) => item.character_id === characterId);
            if (!character || character.is_deleted || character.status !== "active") throw new Error(t("disabled.characterUnavailable"));
            const source = latest.data.find((item) => item.character_id === characterId) ?? null;
            if (source?.is_deleted) throw new Error(t("errors.deletedConflict"));
            setStates(latest.data); setCharacters(people.data);
            setSearch(""); setScopeFilter("all"); setShowTrash(false);
            if (source) setSelectedStateId(source.state_id);
            setDraft(structuredClone(fields));
            setEditor({ characterId, volumeId: fixedVolume.volume_id, source, adopted: true });
            setEditorError(""); setEditorFieldErrors({}); setEditorConflict(false); setEditorConflictLatest(null);
            beginPlan({ characterId, volumeId: fixedVolume.volume_id, source, adopted: true }, structuredClone(fields), "edited");
          } finally { if (contextKeyRef.current === contextKey) setAdoptBusy(false); }
        }}
        onAdoptCharacter={async (profile, candidateRef) => {
          if (adoptPreparation || adoptDraft || contextKeyRef.current !== contextKey) return;
          const preparation: Extract<CharacterFactPreparationV1, { kind: "create" }> = {
            schema_id: "character.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1,
            novel_id: props.novelId, kind: "create", profile: profileForCharacterFactDraft(profile), fields: [],
            is_core_character: false, position: null, note: "", candidate_ref: candidateRef,
          };
          setAdoptBusy(true);
          try {
            await writeCharacterFactPreparation(preparation, null);
            if (contextKeyRef.current === contextKey) setAdoptPreparation(preparation);
          } finally { if (contextKeyRef.current === contextKey) setAdoptBusy(false); }
        }}
        onClose={() => { setAiOpen(false); requestAnimationFrame(() => { if (aiTriggerRef.current?.getClientRects().length && !aiTriggerRef.current.closest("[inert]")) aiTriggerRef.current.focus({ preventScroll: true }); }); }}
        onSaved={(result) => {
          if (contextKeyRef.current !== contextKey) return;
          loadAbortRef.current?.abort();
          // 成功回执不能覆盖之后的修改；保留原选择和草稿，重读当前资料。
          confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
          setSelectedStateId(selectedStateIdRef.current);
          pendingVolumeRefreshRef.current = true;
          setSearch(""); setScopeFilter("all"); setShowTrash(false);
          setDetailOpen(result.data.length > 0);
          setAiOpen(false);
          void loadWorkspace();
          requestAnimationFrame(() => {
            if (rosterRef.current && getComputedStyle(rosterRef.current).display === "none") detailRef.current?.focus();
          });
        }}
      />}

      {adoptPreparation && <CharacterFactCreateDialog key={adoptPreparation.key} novelId={props.novelId}
        initialPreparation={adoptPreparation} onBusy={setAdoptBusy} beforeLeaveRef={adoptBeforeLeaveRef}
        onClose={() => setAdoptPreparation(null)}
        onPreviewed={(draft) => { setAdoptPreparation(null); setAdoptDraft(draft); }} />}
      {adoptDraft && <CharacterFactConfirmationDialog key={adoptDraft.key} novelId={props.novelId}
        initialDraft={adoptDraft} onBusy={setAdoptBusy} beforeLeaveRef={adoptBeforeLeaveRef}
        onClose={() => setAdoptDraft(null)}
        onRepreview={async (previous) => {
          const command = previous.command!;
          if (command.body.operation !== "create") throw new Error(factT("wrongScope"));
          const basis = command.body.basis;
          const preparation: Extract<CharacterFactPreparationV1, { kind: "create" }> = {
            schema_id: "character.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1,
            novel_id: props.novelId, kind: "create", fields: [...basis.fields],
            profile: profileForCharacterFactDraft({ ...createEmptyCharacterProfile(), ...basis.target.candidate, ...structuredClone(command.body.after) }),
            is_core_character: Boolean(basis.target.candidate.is_core_character), position: basis.position,
            note: basis.source.kind === "author" ? basis.source.note : "",
          };
          await writeCharacterFactPreparation(preparation, null);
          if (contextKeyRef.current === contextKey) setAdoptPreparation(preparation);
        }}
        onReadback={async (receipt) => {
          await apiPost<CharacterFactReadResultV1>(`/api/character-facts/novel/${props.novelId}/read`, { character_ids: [receipt.character_id], position: null });
          if (contextKeyRef.current !== contextKey) throw new Error(factT("wrongScope"));
          confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
          setSelectedStateId(selectedStateIdRef.current);
          pendingVolumeRefreshRef.current = true;
          if (!await loadWorkspace()) throw new Error(factT("savedReadFailed"));
        }} />}

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
                {initializeCommandRef.current && <p role="status" className="mb-4 text-sm text-muted">{t("initialize.pending")}</p>}
                <fieldset disabled={initializing || Boolean(initializeCommandRef.current)}>
                  <legend className="text-sm font-semibold text-foreground">{t("initialize.characters")}</legend>
                  <div className="mt-3 divide-y divide-border border-y border-border">
                    {initializeCharacters.map((character) => {
                      const checked = initializeCharacterIds.includes(character.character_id);
                      const exists = anyStateCharacterIds.has(character.character_id);
                      return (
                        <label key={character.character_id} className="flex min-h-11 items-start gap-3 px-1 py-3 text-sm text-foreground">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!checked && exists}
                            onChange={(event) => setInitializeCharacterIds((current) => event.target.checked
                              ? [...current, character.character_id]
                              : current.filter((id) => id !== character.character_id))}
                            className="mt-0.5 size-4 accent-accent"
                          />
                          <span className="min-w-0">
                            <span className="block">{character.name} · <span className="font-mono text-xs">{character.character_id}</span></span>
                            {exists && <span className="mt-1 block text-xs text-muted">{t("initialize.targetExists")}</span>}
                          </span>
                        </label>
                      );
                    })}
                    {initializeCharacters.length === 0 && (
                      <p className="py-5 text-sm text-muted">{t("initialize.noSourceStates")}</p>
                    )}
                  </div>
                </fieldset>
                <p className="mt-5 border-y border-amber-500/40 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100">
                  {t("initialize.conflictPolicy")}
                </p>
              </Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" onPress={() => setInitializeOpen(false)} isDisabled={initializing}>{t("actions.cancel")}</Button>
                <Button variant="primary" onPress={() => void runInitialize()} isDisabled={initializing || initializeCharacterIds.length === 0}>{initializing ? t("actions.initializing") : t(initializeCommandRef.current ? "initialize.resume" : "initialize.legacyAction")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </section>
  );
}

function relationNames(
  state: CharacterVolumeStateReadV1,
  relations: CharacterRelationResponseV1[],
  characterNames: ReadonlyMap<string, string>,
): string[] {
  return state.relationship_focus_ids.map((relationId) => {
    const relation = relations.find((item) => item.relation_id === relationId);
    if (!relation) return relationId;
    const source = characterNames.get(relation.source_character_id) ?? relation.source_character_id;
    const target = characterNames.get(relation.target_character_id) ?? relation.target_character_id;
    return `${source} ↔ ${target} · ${relation.relation_id}`;
  });
}

function draftFromState(state: CharacterVolumeStateReadV1): CharacterVolumePlanFieldsV1 {
  return {
    participation_scope: state.participation_scope,
    current_goal: state.current_goal,
    start_state: state.start_state,
    planned_end_state: state.planned_end_state,
    relationship_focus_ids: [...state.relationship_focus_ids],
    arc_progress: state.arc_progress,
  };
}
