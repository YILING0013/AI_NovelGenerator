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
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

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
  const t = useTranslations("writing.characterVolumeStates");
  const listT = useTranslations("writing.listLayout");
  const aiT = useTranslations("writing.volumeEntitiesAi");
  const factT = useTranslations("writing.characterFacts");
  const [aiOpen, setAiOpen] = useState(false);
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
  const [previousStateCharacterIds, setPreviousStateCharacterIds] = useState<string[]>([]);
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
  const loadAbortRef = useRef<AbortController | null>(null);
  const mutationAbortRef = useRef<AbortController | null>(null);
  const contextKeyRef = useRef(contextKey);
  const createCommandRef = useRef<{ fingerprint: string; key: string } | null>(null);
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
  const previousStateCharacterIdSet = useMemo(
    () => new Set(previousStateCharacterIds),
    [previousStateCharacterIds],
  );
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
      let previousIds: string[] = [];
      let previousError = "";
      if (fixedVolumeId && !fixedVolumeDeleted && fixedVolumeOrderIndex !== null) {
        const previousVolume = volumeResponse.data
          .filter((volume) => volume.order_index < fixedVolumeOrderIndex)
          .sort((left, right) => right.order_index - left.order_index)[0];
        if (previousVolume) {
          try {
            const previousStates = await apiGet<CharacterVolumeStateListV1>(
              `/api/character-volume-states/novel/${props.novelId}/volume/${previousVolume.volume_id}?status=active`,
              { signal: controller.signal },
            );
            if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
            previousIds = previousStates.data.map((state) => state.character_id);
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
      setPreviousStateCharacterIds(previousIds);
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
    setPreviousStateCharacterIds([]);
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

  const busy = Boolean(editor || lifecycleIntent || initializeOpen || saving || conflictRefreshing || actionStateId || initializing || factsBusy || legacyBusy || adoptBusy || leavingFacts);
  const beforeLeaveRef = props.beforeLeaveRef;
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { await legacyBeforeLeaveRef.current?.(); await adoptBeforeLeaveRef.current?.(); await factsBeforeLeaveRef.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  }, [beforeLeaveRef]);

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
  useAssistantRefresh(props.novelId, async () => { await loadWorkspace(); });
  useAssistantFocus("character_volume_state", (target) => { if (busy || !visibleStates.some((state) => state.state_id === target.id)) return false; void leaveFacts(() => { setSelectedStateId(target.id); setShowTrash(Boolean(visibleStates.find((state) => state.state_id === target.id)?.is_deleted)); setSearch(""); setScopeFilter("all"); setDetailOpen(true); }); });
  useAssistantResource(selectedState ? { resource_type: "character_volume_state", id: selectedState.state_id, name: selectedState.state_id, version: selectedState.version, draft: editor?.source?.state_id === selectedState.state_id ? { text: JSON.stringify(draft), fields: Object.keys(draft), version: editor.source.version } : undefined } : null);

  const openCreate = (characterId: string, volumeId: string) => {
    editTriggerRef.current = null;
    setDraft({ ...EMPTY_FIELDS });
    setEditor({ characterId, volumeId, source: null });
    setEditorError("");
    setEditorFieldErrors({});
    setEditorConflict(false);
    setEditorConflictLatest(null);
    createCommandRef.current = null;
  };

  const openEdit = (state: CharacterVolumeStateReadV1, section: StateSection) => {
    editTriggerRef.current = document.activeElement as HTMLElement;
    setDraft(draftFromState(state));
    setEditor({ characterId: state.character_id, volumeId: state.volume_id, source: state, section });
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
      if (Object.keys(payload).length === 1) { closeEditor(); return; }
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
    if (Object.keys(fieldErrors).length > 0) {
      setEditorError(t("errors.validation"));
      setEditorFieldErrors(fieldErrors);
      focusRelationEditorError(fieldErrors);
      return;
    }
    if (!editor.source) {
      const fingerprint = JSON.stringify({
        novel_id: props.novelId,
        volume_id: editor.volumeId,
        character_id: editor.characterId,
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
      const saved = editor.source
        ? await apiPut<CharacterVolumeStateReadV1>(
            `/api/character-volume-states/novel/${props.novelId}/${editor.source.state_id}/plan`,
            payload,
            { signal: controller.signal },
          )
        : await apiPost<CharacterVolumeStateReadV1>(
            `/api/character-volume-states/novel/${props.novelId}/plans`,
            payload,
            { headers: { "Idempotency-Key": createCommandRef.current!.key }, signal: controller.signal },
          );
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      // 保存前发出的读取已过期，不能盖回刚保存的新版本。
      loadAbortRef.current?.abort();
      loadAbortRef.current = null;
      setLoading(false);
      if (editor.source) {
        setStates((current) => [saved, ...current.filter((state) => state.state_id !== saved.state_id)]);
        setSelectedStateId(saved.state_id);
        props.onFormalFactsChanged?.();
      } else {
        // 新建可能返回旧成功回执，只用后续读取的当前资料。
        confirmedContextRef.current = { scope: contextKey, stateId: selectedStateIdRef.current };
        setSelectedStateId(selectedStateIdRef.current);
        pendingVolumeRefreshRef.current = true;
        setDetailOpen(true);
        void loadWorkspace();
      }
      setEditor(null);
      requestAnimationFrame(() => { if (editTriggerRef.current?.id) document.getElementById(editTriggerRef.current.id)?.focus(); });
      createCommandRef.current = null;
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
      if (error instanceof ApiRequestError) {
        const factBlocked = error.code === "CHARACTER_FACT_MANAGED_FIELDS" || error.code === "CHARACTER_FACT_CONTRACT_REQUIRED";
        setEditorError(factBlocked || !editor.source ? error.message : error.status === 409 ? t("errors.conflict") : t("errors.save"));
        // 新建失败仍是原新建请求，不能凭后来读到一条记录改成更新。
        setEditorConflict(Boolean(editor.source) && error.status === 409 && !factBlocked);
        setEditorConflictLatest(null);
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

  const runInitialize = async () => {
    if (!fixedVolumeId || initializing || initializeCharacterIds.length === 0) return;
    const requestContextKey = contextKey;
    const fingerprint = JSON.stringify({
      volume_id: fixedVolumeId,
      character_ids: [...initializeCharacterIds].sort(),
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
      await apiPost<CharacterVolumeStateInitializeResultV1>(
        `/api/character-volume-states/novel/${props.novelId}/volume/${fixedVolumeId}/initialize-from-previous`,
        { character_ids: initializeCharacterIds, skip_existing: false },
        {
          headers: { "Idempotency-Key": createCommandRef.current.key },
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
      createCommandRef.current = null;
      void loadWorkspace();
    } catch (error) {
      if (controller.signal.aborted || contextKeyRef.current !== requestContextKey) return;
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

  const selectedEditorCharacter = editor
    ? characters.find((character) => character.character_id === editor.characterId) ?? null
    : null;
  const selectedEditorVolume = editor
    ? volumes.find((volume) => volume.volume_id === editor.volumeId) ?? null
    : null;

  const renderEditorFields = editor && (
    <>
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
              onChange={setDraft}
              characterId={editor.characterId}
              relations={relations}
              characterNames={characterNames}
              disabled={saving || conflictRefreshing}
              fieldErrors={editorFieldErrors}
              errorIdPrefix={`character-volume-state-${editor.source?.state_id ?? "new"}`}
              autoFocusCurrentGoal={Boolean(editor.source)}
            />
    </>
  );

  const renderEditor = editor && (!editor.source || !editor.section) && (
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
              <p className="mt-1 break-words text-sm leading-6 text-muted">
                {selectedEditorCharacter?.name ?? editor.characterId} · {editor.characterId}
                <br />
                {selectedEditorVolume?.title ?? fixedVolumeTitle ?? editor.volumeId} · {editor.volumeId}
              </p>
            </div>
            <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving || conflictRefreshing} />
          </Modal.Header>
          <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
            {!editor.source && !editor.adopted && fixedVolumeId && (
              <label className="mb-6 grid gap-1.5 text-xs font-medium text-muted">
                <span>{t("fields.character")}</span>
                <select
                  value={editor.characterId}
                  onChange={(event) => {
                    setEditor({ ...editor, characterId: event.target.value });
                    setDraft({ ...EMPTY_FIELDS });
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
                  {availableCreateCharacters.map((character) => (
                    <option key={character.character_id} value={character.character_id}>{character.name} · {character.character_id}</option>
                  ))}
                </select>
              </label>
            )}
            {editor.adopted && <section className="mb-6 border-b border-border pb-5" aria-label={editor.source ? t("version", { version: editor.source.version }) : t("editor.noCurrentPlan")}>
              <h3 className="mb-3 text-sm font-semibold">{editor.source ? t("version", { version: editor.source.version }) : t("editor.noCurrentPlan")}</h3>
              {editor.source && <dl className="detail-fields grid gap-4">{PLAN_FIELDS.map((field) => <ReadOnlyField key={field} label={t(`fields.${FIELD_LABELS[field]}`)} wide value={field === "participation_scope" ? t(`scope.${editor.source!.participation_scope}`) : field === "relationship_focus_ids" ? relationNames(editor.source!, relations, characterNames).join(t("listSeparator")) || "—" : field === "arc_progress" ? `${editor.source!.arc_progress}%` : editor.source![field] || "—"} />)}</dl>}
            </section>}
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
      <h3 id={`volume-character-states-${fixedVolumeId}`} className={fixedVolumeDeleted ? "mb-4 text-sm font-semibold tracking-normal text-foreground" : "sr-only"}>
        {fixedVolumeDeleted ? t("trashSection.title") : t("volumeSection.title")}
      </h3>
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
        {fixedVolumeDeleted ? <p className="flex min-h-10 items-center text-sm text-muted">{t("filters.trash")}</p> : <label className="flex min-h-10 shrink-0 items-center gap-2 whitespace-nowrap text-sm text-foreground">
          <input type="checkbox" disabled={busy} checked={showTrash} onChange={(event) => { const value = event.target.checked; void leaveFacts(() => setShowTrash(value)); }} className="size-4 accent-accent" />{t("filters.trash")}
        </label>}
        {!fixedVolumeDeleted && <>
          <Button variant="outline" size="sm" isDisabled={busy || loading || Boolean(loadError) || !fixedVolume || props.generationDisabled} onPress={() => setAiOpen(true)}>{aiT("characters.open")}</Button>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" onPress={() => { setInitializeCharacterIds([]); setInitializeError(""); setInitializeOpen(true); createCommandRef.current = null; }} isDisabled={busy || loading || fixedVolumeOrderIndex === 1 || previousStateCharacterIds.length === 0}>{t("actions.initialize")}</Button>
            {(fixedVolumeOrderIndex === 1 || previousStateCharacterIds.length === 0) && <TooltipHint text={fixedVolumeOrderIndex === 1 ? t("initialize.firstVolume") : t("initialize.noSourceStates")} />}
          </div>
          {availableCreateCharacters.length > 0 && <Button variant="primary" size="sm" onPress={() => availableCreateCharacters[0] && fixedVolumeId && openCreate(availableCreateCharacters[0].character_id, fixedVolumeId)} isDisabled={busy || loading || !fixedVolume}>{t("actions.create")}</Button>}
        </>}
        <fieldset disabled={loading || Boolean(loadError)} className="contents">{props.toolbarAfter}</fieldset>
      </div>
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
      ) : loadError && !savedReadFailed ? null : filteredStates.length === 0 ? (
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
                </> : <Button size="sm" variant="ghost" className="text-danger" isDisabled={busy} onPress={() => void leaveFacts(() => { setLifecycleIntent({ action: "soft-delete", state: selectedState }); setLifecycleError(""); })}>{t("actions.delete")}</Button>}
              </div>
            </header>
            <div className="space-y-4">
              {STATE_SECTIONS.map((section) => <Fragment key={section}><DocumentSection number={section === "participation" ? "01" : "06"} title={t(SECTION_TITLES[section])}
                actions={!selectedState.is_deleted && (editor?.source?.state_id === selectedState.state_id && editor.section === section ? <>
                  <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" onPress={closeEditor} isDisabled={saving || conflictRefreshing} />
                  <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" onPress={() => void saveEditor()} isDisabled={saving || conflictRefreshing || editorConflict} />
                </> : <SectionEditButton id={`character-state-edit-${selectedState.state_id}-${section}`} label={t("actions.edit")} isDisabled={busy} onPress={() => openEdit(selectedState, section)} />)}>
                {editor?.source?.state_id === selectedState.state_id && editor.section === section ? renderEditorFields : <dl className="detail-fields grid min-w-0 gap-4">
                  {section === "participation" && <ReadOnlyField label={t("fields.character")} value={characterNames.get(selectedState.character_id) ?? selectedState.character_id} />}
                  {SECTION_FIELDS[section].map((field) => <ReadOnlyField key={field} label={t(`fields.${FIELD_LABELS[field]}`)} wide={!["participation_scope", "arc_progress"].includes(field)} value={field === "participation_scope" ? t(`scope.${selectedState.participation_scope}`) : field === "relationship_focus_ids" ? relationNames(selectedState, relations, characterNames).join(t("listSeparator")) || "—" : field === "arc_progress" ? `${selectedState.arc_progress}%` : selectedState[field] || "—"} />)}
                </dl>}
              </DocumentSection>
              {section === "participation" && <>
                <CharacterFactsPanel novelId={props.novelId} characterId={selectedState.character_id} numberOffset={1}
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

      {aiOpen && fixedVolume && <VolumeEntityCandidateWorkspace
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
            createCommandRef.current = null;
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
        onClose={() => { setAiOpen(false); void loadWorkspace(); }}
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
                <fieldset disabled={initializing}>
                  <legend className="text-sm font-semibold text-foreground">{t("initialize.characters")}</legend>
                  <div className="mt-3 divide-y divide-border border-y border-border">
                    {characters.filter((character) => (
                      character.status === "active"
                      && !character.is_deleted
                      && previousStateCharacterIdSet.has(character.character_id)
                    )).map((character) => {
                      const checked = initializeCharacterIds.includes(character.character_id);
                      const exists = anyStateCharacterIds.has(character.character_id);
                      return (
                        <label key={character.character_id} className="flex min-h-11 items-start gap-3 px-1 py-3 text-sm text-foreground">
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={exists}
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
                    {previousStateCharacterIds.length === 0 && (
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
                <Button variant="primary" onPress={() => void runInitialize()} isDisabled={initializing || initializeCharacterIds.length === 0}>{initializing ? t("actions.initializing") : t("actions.initialize")}</Button>
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
