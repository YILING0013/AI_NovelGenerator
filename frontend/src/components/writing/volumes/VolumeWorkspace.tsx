"use client";
import { useAssistantResource } from "@/components/writing/assistant/AssistantContext";
import { useResourceRefresh } from "@/hooks/useResourceRefresh";
import { RetainedModalBackdrop, RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";

import {
  ConfirmActionModal,
  focusRelationEditorError,
  RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import DocumentSection from "@/components/shared/DocumentSection";
import TagList from "@/components/shared/TagList";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import VolumeFieldsForm from "@/components/writing/volumes/VolumeFieldsForm";
import PlotSection from "@/components/writing/hierarchy/PlotSection";
import VolumePreparation from "./VolumePreparation";
import VolumePlanningCandidateWorkspace from "@/components/writing/volumes/VolumePlanningCandidateWorkspace";
import CharacterVolumeStateWorkspace from "@/components/writing/characters/CharacterVolumeStateWorkspace";
import FactionVolumeStateWorkspace from "@/components/writing/factions/FactionVolumeStateWorkspace";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  ApiRequestError,
  type ApiFieldErrors,
} from "@/lib/api";
import {
  parseVolumeDeleteImpactV2,
  type VolumeCreateV2,
  type VolumeBulkPlanResponseV1,
  type VolumeDeleteImpactV2,
  type VolumePlanningV1,
  type VolumeReadV2,
  type VolumeStatus,
} from "@/types/volume";

export type VolumeWorkspaceView = "overview" | "characters" | "factions" | "locations" | "trash";

interface VolumeWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: VolumeWorkspaceView;
  requestedVolumeId?: string | null;
  focusPlot?: boolean;
  requestedEntityId?: string | null;
  onProcessLaunchContext?: (kind: "character" | "faction", id: string, volumeId: string) => void;
  onViewChange?: (view: VolumeWorkspaceView) => void;
  onVolumeIdChange?: (volumeId: string | null, replace?: boolean) => void;
  onLocationChange?: (view: VolumeWorkspaceView, volumeId: string | null, replace?: boolean) => void;
  onFormalFactsChanged?: () => void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}

interface VolumeListEnvelope {
  data: VolumeReadV2[];
}

interface VolumeCreateEnvelope {
  id: string;
  message: string;
  data: VolumeReadV2;
}

interface VolumeMutationEnvelope {
  success: true;
  data: VolumeReadV2;
}

interface VolumeDraft {
  title: string;
  subtitle: string;
  summary: string;
  goal: string;
  theme: string;
  status: VolumeStatus;
  planning: VolumePlanningV1 | null;
}

type EditorState =
  | { mode: "create"; source: null }
  | { mode: "edit"; source: VolumeReadV2; section: "identity" | "planning" };

type ConfirmIntent =
  | { kind: "soft-delete"; volume: VolumeReadV2; impact: VolumeDeleteImpactV2 }
  | { kind: "restore"; volume: VolumeReadV2; impact: null }
  | { kind: "hard-delete"; volume: VolumeReadV2; impact: VolumeDeleteImpactV2 };

const VOLUME_STATUSES: VolumeStatus[] = ["draft", "planned", "active", "completed", "archived"];
const VOLUME_VIEWS: VolumeWorkspaceView[] = ["overview", "characters", "factions", "locations", "trash"];
const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const FILTER_CLASS =
  "min-h-10 min-w-0 w-full rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";

const EMPTY_DRAFT: VolumeDraft = {
  title: "",
  subtitle: "",
  summary: "",
  goal: "",
  theme: "",
  status: "draft",
  planning: null,
};

/**
 * 渲染卷列表、卷详情和五个子页面。
 *
 * @param props 小说模式、小说 ID、当前子页面与卷选择同步回调。
 * @returns 支持卷列表、连续详情、编辑、回收站和移动端切换的工作区。
 */
export default function VolumeWorkspace({
  mode,
  novelId,
  initialView = "overview",
  requestedVolumeId = null,
  requestedEntityId = null,
  onProcessLaunchContext,
  focusPlot = false,
  onViewChange,
  onVolumeIdChange,
  onLocationChange,
  onFormalFactsChanged,
  onBusyChange,
  beforeLeaveRef,
}: VolumeWorkspaceProps) {
  const t = useTranslations("writing.volumes");
  const plotT = useTranslations("writing.plot");
  const locale = useLocale();
  const active = useContext(RetainedViewActive);
  const tabPrefix = `volume-workspace-${useId()}`;
  const [storedVolumes, setVolumes] = useState<VolumeReadV2[]>([]);
  const [storedTrashVolumes, setTrashVolumes] = useState<VolumeReadV2[]>([]);
  const [loadedNovelId, setLoadedNovelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(mode === "edit" && Boolean(novelId));
  const [dataError, setDataError] = useState("");
  const [pageActionError, setPageActionError] = useState("");
  const [selectedVolumeId, setSelectedVolumeId] = useState("");
  const [invalidVolumeId, setInvalidVolumeId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(focusPlot);
  useEffect(() => { if (active && focusPlot && initialView === "overview") setMobileDetailOpen(true); }, [active, focusPlot, initialView, requestedVolumeId]);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | VolumeStatus>("all");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [draft, setDraft] = useState<VolumeDraft>(EMPTY_DRAFT);
  const [editorError, setEditorError] = useState("");
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [plotBusy, setPlotBusy] = useState(false);
  const [plotRunning, setPlotRunning] = useState(false);
  const [stateBusy, setStateBusy] = useState(false);
  const [preparationBusy, setPreparationBusy] = useState(false);
  const [leavingCharacters, setLeavingCharacters] = useState(false);
  const [confirmIntent, setConfirmIntent] = useState<ConfirmIntent | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const [actionVolumeId, setActionVolumeId] = useState("");
  const [candidateStates, setCandidateStates] = useState<Record<string, { reviewing?: boolean; busy?: boolean }>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const createCommandRef = useRef<{ fingerprint: string; key: string } | null>(null);
  const editorReturnFocusRef = useRef<HTMLElement | null>(null);
  const inlineEditorRef = useRef<HTMLDivElement | null>(null);
  const confirmReturnFocusRef = useRef<HTMLElement | null>(null);
  const pendingLocationRef = useRef<{ view: VolumeWorkspaceView; volumeId: string | null } | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadRequestIdRef = useRef(0);
  const volumeReadAbortRef = useRef<AbortController | null>(null);
  const volumeReadRequestIdRef = useRef(0);
  const currentNovelIdRef = useRef(novelId);
  const currentVolumeIdRef = useRef(selectedVolumeId);
  const previousNovelIdRef = useRef(novelId);
  // 隐藏的卷继续保留组件；每卷单独登记，回到旧卷时不能调用另一卷的保稿函数。
  const characterLeaveRefs = useRef(new Map<string, RefObject<(() => Promise<void>) | null>>());
  const leavingCharactersRef = useRef(false);
  const currentContextRef = useRef({ active, novelId, view: initialView, volumeId: selectedVolumeId });
  currentContextRef.current = { active, novelId, view: initialView, volumeId: selectedVolumeId };
  currentNovelIdRef.current = novelId;
  currentVolumeIdRef.current = selectedVolumeId;

  const workspaceReady = loadedNovelId === novelId;
  const volumes = workspaceReady ? storedVolumes : [];
  const trashVolumes = workspaceReady ? storedTrashVolumes : [];
  const stateView = initialView === "characters" || initialView === "factions";
  const sourceVolumes = useMemo(() => {
    if (!workspaceReady) return [];
    return initialView === "trash" ? storedTrashVolumes : stateView ? [...storedVolumes, ...storedTrashVolumes] : storedVolumes;
  }, [initialView, stateView, workspaceReady, storedTrashVolumes, storedVolumes]);
  const canUseSavedNovel = mode === "edit" && Boolean(novelId);

  const loadWorkspace = useCallback(async () => {
    if (!novelId || mode !== "edit") return;
    // 刷新只重读资料；已打开的候选、运行和各卷草稿继续保留。
    setRefreshKey((current) => current + 1);
    loadAbortRef.current?.abort();
    volumeReadAbortRef.current?.abort();
    volumeReadRequestIdRef.current += 1;
    const controller = new AbortController();
    const requestId = loadRequestIdRef.current + 1;
    const requestNovelId = novelId;
    loadAbortRef.current = controller;
    loadRequestIdRef.current = requestId;
    setLoading(true);
    setDataError("");
    try {
      const [activeResponse, trashResponse] = await Promise.all([
        apiGet<VolumeListEnvelope>(`/api/volumes/novel/${novelId}`, { signal: controller.signal }),
        apiGet<VolumeListEnvelope>(`/api/volumes/novel/${novelId}/trash`, { signal: controller.signal }),
      ]);
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      setVolumes(activeResponse.data);
      setTrashVolumes(trashResponse.data);
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
        loadAbortRef.current === controller
        && loadRequestIdRef.current === requestId
        && currentNovelIdRef.current === requestNovelId
      ) {
        loadAbortRef.current = null;
        setLoading(false);
      }
    }
  }, [mode, novelId, t]);

  useResourceRefresh(novelId, loadWorkspace, active);

  useEffect(() => {
    if (previousNovelIdRef.current === novelId) return;
    previousNovelIdRef.current = novelId;
    setVolumes([]);
    setTrashVolumes([]);
    setLoadedNovelId(null);
    setSelectedVolumeId("");
    setInvalidVolumeId("");
    setMobileDetailOpen(false);
    setListCollapsed(false);
    setSearch("");
    setStatusFilter("all");
    setEditor(null);
    setConfirmIntent(null);
    setPageActionError("");
    setConfirmError("");
    setActionVolumeId("");
    setSaving(false);
    setCandidateStates({});
    setRefreshKey((current) => current + 1);
    createCommandRef.current = null;
    pendingLocationRef.current = null;
  }, [novelId]);

  useEffect(() => {
    return () => {
      loadAbortRef.current?.abort();
      volumeReadAbortRef.current?.abort();
      volumeReadRequestIdRef.current += 1;
    };
  }, [loadWorkspace]);

  useEffect(() => {
    if (!workspaceReady) return;
    const pendingLocation = pendingLocationRef.current;
    if (pendingLocation) {
      if (initialView !== pendingLocation.view || requestedVolumeId !== pendingLocation.volumeId) return;
      pendingLocationRef.current = null;
    }
    if (requestedVolumeId) {
      if (sourceVolumes.some((volume) => volume.volume_id === requestedVolumeId)) {
        setSelectedVolumeId(requestedVolumeId);
        setInvalidVolumeId("");
      } else if (invalidVolumeId !== requestedVolumeId) {
        setSelectedVolumeId("");
        setInvalidVolumeId(requestedVolumeId);
        setMobileDetailOpen(false);
        // 页面保留找不到卷的提示，只从地址中移除已确认无效的卷 ID。
        if (onLocationChange) pendingLocationRef.current = { view: initialView, volumeId: null };
        onVolumeIdChange?.(null, true);
      }
      return;
    }
    if (invalidVolumeId) return;
    if (sourceVolumes.some((volume) => volume.volume_id === selectedVolumeId)) return;
    const firstVolume = sourceVolumes[0];
    if (firstVolume) {
      setSelectedVolumeId(firstVolume.volume_id);
      if (onLocationChange) pendingLocationRef.current = { view: initialView, volumeId: firstVolume.volume_id };
      onVolumeIdChange?.(firstVolume.volume_id, true);
    }
  }, [initialView, invalidVolumeId, onLocationChange, onVolumeIdChange, requestedVolumeId, selectedVolumeId, sourceVolumes, workspaceReady]);
  const filteredVolumes = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return sourceVolumes.filter((volume) => {
      if (statusFilter !== "all" && volume.status !== statusFilter) return false;
      if (!query) return true;
      return [volume.title, volume.subtitle, volume.summary, volume.goal, volume.theme]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query);
    });
  }, [search, sourceVolumes, statusFilter]);
  const entityView = initialView === "characters" || initialView === "factions" || initialView === "locations";
  const selectedVolume = (entityView ? sourceVolumes : filteredVolumes).find((volume) => volume.volume_id === selectedVolumeId) ?? null;
  const characterScope = `${novelId}:${selectedVolumeId}`;
  if (!characterLeaveRefs.current.has(characterScope)) characterLeaveRefs.current.set(characterScope, { current: null });
  const characterBeforeLeaveRef = characterLeaveRefs.current.get(characterScope)!;
  useAssistantResource(!entityView && selectedVolume ? { resource_type: "volume", id: selectedVolume.volume_id, name: selectedVolume.title, version: selectedVolume.version, draft: editor?.mode === "edit" && editor.source.volume_id === selectedVolume.volume_id ? { text: JSON.stringify(draft), fields: Object.keys(draft), version: editor.source.version } : undefined } : null);

  /** 接收已保存或完整读到的卷，保留当前选择，并阻止此前的读取覆盖新版本。
   * Args: record 正式接口返回的完整卷。
   * Returns: 通知父级资料变化；通知失败只显示读取错误。
   */
  const acceptSavedVolume = useCallback(async (record: VolumeReadV2) => {
    if (record.novel_id !== currentNovelIdRef.current) return;
    loadAbortRef.current?.abort();
    loadAbortRef.current = null;
    loadRequestIdRef.current += 1;
    volumeReadAbortRef.current?.abort();
    const notificationRequestId = ++volumeReadRequestIdRef.current;
    setLoading(false);
    setVolumes((records) => records.map((current) => current.volume_id === record.volume_id && current.version <= record.version ? record : current));
    try {
      await onFormalFactsChanged?.();
    } catch (failure) {
      // 卷已经保存，后续通知失败不能让子组件重新提交。
      if (notificationRequestId === volumeReadRequestIdRef.current && record.novel_id === currentNovelIdRef.current && record.volume_id === currentVolumeIdRef.current) {
        setPageActionError(failure instanceof Error ? failure.message : t("errors.load"));
      }
    }
  }, [onFormalFactsChanged, t]);

  const refreshVolume = useCallback(async (readVolume?: VolumeReadV2) => {
    // 卷内候选确认后，使用工作台已完整读到的卷，不再另发一轮读取。
    if (readVolume) {
      await acceptSavedVolume(readVolume);
      return;
    }
    if (!selectedVolumeId || novelId !== currentNovelIdRef.current) return;
    volumeReadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = ++volumeReadRequestIdRef.current;
    volumeReadAbortRef.current = controller;
    try {
      if (selectedVolume?.is_deleted) {
        const response = await apiGet<VolumeListEnvelope>(`/api/volumes/novel/${novelId}/trash`, { signal: controller.signal });
        if (controller.signal.aborted || requestId !== volumeReadRequestIdRef.current || novelId !== currentNovelIdRef.current) return;
        setTrashVolumes(response.data);
        await onFormalFactsChanged?.();
      } else {
        const current = await apiGet<VolumeReadV2>(`/api/volumes/${selectedVolumeId}`, { signal: controller.signal });
        if (controller.signal.aborted || requestId !== volumeReadRequestIdRef.current || novelId !== currentNovelIdRef.current) return;
        await acceptSavedVolume(current);
      }
    } catch (failure) {
      if (controller.signal.aborted || requestId !== volumeReadRequestIdRef.current || novelId !== currentNovelIdRef.current || selectedVolumeId !== currentVolumeIdRef.current) return;
      setPageActionError(failure instanceof Error ? failure.message : t("errors.load"));
    } finally {
      if (volumeReadAbortRef.current === controller) volumeReadAbortRef.current = null;
    }
  }, [novelId, selectedVolumeId, selectedVolume?.is_deleted, acceptSavedVolume, onFormalFactsChanged, t]);
  const candidateScope = `${initialView}:${selectedVolumeId || "none"}`;
  const candidateReviewing = candidateStates[candidateScope]?.reviewing ?? false;
  const candidateBusy = candidateStates[candidateScope]?.busy ?? false;
  // 后台候选只更新自己的卷和栏目，不能盖住当前页面或锁住另一卷的操作。
  const setCandidateReviewing = useCallback((reviewing: boolean) => {
    setCandidateStates((current) => current[candidateScope]?.reviewing === reviewing ? current : {
      ...current, [candidateScope]: { ...current[candidateScope], reviewing },
    });
  }, [candidateScope]);
  const setCandidateBusy = useCallback((busy: boolean) => {
    setCandidateStates((current) => current[candidateScope]?.busy === busy ? current : {
      ...current, [candidateScope]: { ...current[candidateScope], busy },
    });
  }, [candidateScope]);
  const filtersActive = Boolean(search) || statusFilter !== "all";
  const mutationBlocked = loading || Boolean(actionVolumeId) || candidateBusy || plotBusy;

  const waitForCharacterDraft = useCallback(async () => {
    if (initialView !== "characters") return;
    if (saving || stateBusy || preparationBusy || leavingCharactersRef.current) throw new Error(t("actions.saving"));
    leavingCharactersRef.current = true; setLeavingCharacters(true);
    try { await characterBeforeLeaveRef.current?.(); }
    finally { leavingCharactersRef.current = false; setLeavingCharacters(false); }
  }, [initialView, saving, stateBusy, preparationBusy, characterBeforeLeaveRef, t]);
  useEffect(() => {
    if (!active || !beforeLeaveRef) return;
    beforeLeaveRef.current = waitForCharacterDraft;
    return () => { beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef, waitForCharacterDraft]);
  useEffect(() => {
    if (!active) return;
    onBusyChange?.(saving || stateBusy || preparationBusy || leavingCharacters || plotBusy && !plotRunning || candidateBusy || Boolean(actionVolumeId));
    return () => onBusyChange?.(false);
  }, [active, saving, stateBusy, preparationBusy, leavingCharacters, plotBusy, plotRunning, candidateBusy, actionVolumeId, onBusyChange]);

  useEffect(() => {
    if (editor?.mode !== "edit" || (editor.source.volume_id === selectedVolumeId && initialView === "overview")) return;
    setEditor(null);
    setEditorError("");
    setEditorFieldErrors({});
  }, [editor, initialView, selectedVolumeId]);

  const selectVolume = async (volumeId: string) => {
    if (plotBusy || saving || stateBusy || preparationBusy || leavingCharactersRef.current || (editor && (editor.mode !== "edit" || editor.source.volume_id !== volumeId))) return false;
    const source = currentContextRef.current;
    try { await waitForCharacterDraft(); }
    catch (failure) { setPageActionError(failure instanceof Error ? failure.message : t("errors.load")); return false; }
    if (!currentContextRef.current.active || source.novelId !== currentContextRef.current.novelId || source.view !== currentContextRef.current.view || source.volumeId !== currentContextRef.current.volumeId) return false;
    setPageActionError("");
    setSelectedVolumeId(volumeId);
    setInvalidVolumeId("");
    setMobileDetailOpen(true);
    if (onLocationChange) pendingLocationRef.current = { view: initialView, volumeId };
    onVolumeIdChange?.(volumeId);
    requestAnimationFrame(() => {
      const detail = document.getElementById(`volume-detail-${novelId}-${initialView}-${volumeId}`);
      if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
        detail.focus();
      }
    });
    return true;
  };

  const changeView = async (nextView: VolumeWorkspaceView, preferredVolumeId?: string | null, replace = false) => {
    if (plotBusy || editor || saving || stateBusy || preparationBusy || leavingCharactersRef.current) return false;
    const source = currentContextRef.current;
    try { await waitForCharacterDraft(); }
    catch (failure) { setPageActionError(failure instanceof Error ? failure.message : t("errors.load")); return false; }
    if (!currentContextRef.current.active || source.novelId !== currentContextRef.current.novelId || source.view !== currentContextRef.current.view || source.volumeId !== currentContextRef.current.volumeId) return false;
    setPageActionError("");
    const targetVolumes = nextView === "trash" ? trashVolumes : nextView === "characters" || nextView === "factions" ? [...volumes, ...trashVolumes] : volumes;
    const currentId = preferredVolumeId === undefined ? selectedVolumeId : preferredVolumeId;
    const nextVolumeId = targetVolumes.some((volume) => volume.volume_id === currentId)
      ? currentId || null
      : targetVolumes[0]?.volume_id ?? null;
    setSelectedVolumeId(nextVolumeId ?? "");
    setInvalidVolumeId("");
    setMobileDetailOpen(false);
    if (onLocationChange) {
      pendingLocationRef.current = { view: nextView, volumeId: nextVolumeId };
      onLocationChange(nextView, nextVolumeId, replace);
    } else {
      onViewChange?.(nextView);
    }
    return true;
  };

  const openCreate = () => {
    if (mutationBlocked || candidateReviewing || editor) return;
    editorReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setDraft({ ...EMPTY_DRAFT });
    setEditor({ mode: "create", source: null });
    setEditorError("");
    setEditorFieldErrors({});
    createCommandRef.current = null;
  };

  const openEdit = (volume: VolumeReadV2, section: "identity" | "planning") => {
    if (mutationBlocked || candidateReviewing || editor) return;
    editorReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setDraft({
      title: volume.title,
      subtitle: volume.subtitle,
      summary: volume.summary,
      goal: volume.goal,
      theme: volume.theme,
      status: volume.status,
      planning: volume.planning
        ? { ...volume.planning, key_turning_points: [...volume.planning.key_turning_points] }
        : null,
    });
    // 本节始终使用开始编辑时的版本，后台刷新不能把旧草稿改成覆盖新版本。
    setEditor({ mode: "edit", source: volume, section });
    setEditorError("");
    setEditorFieldErrors({});
    requestAnimationFrame(() => inlineEditorRef.current?.querySelector<HTMLElement>("input, textarea")?.focus());
  };

  const closeEditor = () => {
    if (saving) return;
    const returnFocus = editorReturnFocusRef.current;
    setEditor(null);
    setEditorError("");
    setEditorFieldErrors({});
    requestAnimationFrame(() => {
      if (editor?.mode === "edit") document.getElementById(`volume-edit-${editor.source.volume_id}-${editor.section}`)?.focus();
      else returnFocus?.focus();
    });
  };

  const focusEditorError = (fieldErrors: ApiFieldErrors) => {
    if (editor?.mode === "create") {
      focusRelationEditorError(fieldErrors);
      return;
    }
    requestAnimationFrame(() => {
      const firstField = Object.keys(fieldErrors)[0];
      const target = (firstField ? inlineEditorRef.current?.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`) : null)
        ?? inlineEditorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest" });
    });
  };

  const saveEditor = async () => {
    if (!editor || !novelId || mutationBlocked || saving) return;
    const commandNovelId = novelId;
    const fieldErrors: ApiFieldErrors = {};
    if ((editor.mode === "create" || editor.section === "identity") && !draft.title.trim()) fieldErrors.title = [t("validation.titleRequired")];
    if ((editor.mode === "create" || editor.section === "planning") && draft.planning) {
      if (!Number.isInteger(draft.planning.target_chapter_count) || draft.planning.target_chapter_count < 1 || draft.planning.target_chapter_count > 1000) {
        fieldErrors.target_chapter_count = [t("validation.targetChapterCount")];
      }
      if (!Number.isInteger(draft.planning.target_word_count) || draft.planning.target_word_count < 1 || draft.planning.target_word_count > 10_000_000) {
        fieldErrors.target_word_count = [t("validation.targetWordCount")];
      }
    }
    if (Object.keys(fieldErrors).length > 0) {
      setEditorError(t("errors.validation"));
      setEditorFieldErrors(fieldErrors);
      focusEditorError(fieldErrors);
      return;
    }

    const fields = {
      title: draft.title.trim(),
      subtitle: draft.subtitle.trim(),
      summary: draft.summary.trim(),
      goal: draft.goal.trim(),
      theme: draft.theme.trim(),
      status: draft.status,
      planning: draft.planning
        ? {
            premise: draft.planning.premise.trim(),
            major_conflict: draft.planning.major_conflict.trim(),
            key_turning_points: draft.planning.key_turning_points
              .map((item) => item.trim())
              .filter(Boolean),
            start_state: draft.planning.start_state.trim(),
            end_state: draft.planning.end_state.trim(),
            target_chapter_count: draft.planning.target_chapter_count,
            target_word_count: draft.planning.target_word_count,
          }
        : null,
    };

    setSaving(true);
    setEditorError("");
    setEditorFieldErrors({});
    try {
      let saved: VolumeReadV2;
      if (editor.mode === "create") {
        const payload: VolumeCreateV2 = { novel_id: novelId, ...fields };
        const fingerprint = JSON.stringify(payload);
        if (createCommandRef.current?.fingerprint !== fingerprint) {
          createCommandRef.current = {
            fingerprint,
            key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
          };
        }
        const response = await apiPost<VolumeCreateEnvelope>(
          "/api/volumes/create",
          payload,
          { headers: { "Idempotency-Key": createCommandRef.current.key } },
        );
        saved = response.data;
      } else {
        const { planning, ...identity } = fields;
        const response = await apiPut<VolumeMutationEnvelope>(
          `/api/volumes/${editor.source.volume_id}`,
          { ...(editor.section === "identity" ? identity : { planning }), expected_version: editor.source.version },
        );
        saved = response.data;
      }
      if (currentNovelIdRef.current !== commandNovelId) return;
      if (editor.mode === "create") {
        setVolumes((current) => [...current, saved].sort((left, right) => left.order_index - right.order_index));
      } else {
        setVolumes((current) => current.map((volume) => volume.volume_id === saved.volume_id ? saved : volume));
      }
      setSelectedVolumeId(saved.volume_id);
      setInvalidVolumeId("");
      setEditor(null);
      if (editor.mode === "edit") requestAnimationFrame(() => document.getElementById(`volume-edit-${saved.volume_id}-${editor.section}`)?.focus());
      createCommandRef.current = null;
      onVolumeIdChange?.(saved.volume_id, true);
      onFormalFactsChanged?.();
    } catch (error) {
      if (currentNovelIdRef.current !== commandNovelId) return;
      if (error instanceof ApiRequestError) {
        setEditorError(error.status === 409 ? t("errors.conflict") : t("errors.save"));
        const normalizedFieldErrors: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          const focusField = field.split(".").at(-1) ?? field;
          normalizedFieldErrors[focusField] = [...(normalizedFieldErrors[focusField] ?? []), ...messages];
        }
        setEditorFieldErrors(normalizedFieldErrors);
        focusEditorError(normalizedFieldErrors);
      } else {
        setEditorError(error instanceof Error ? error.message : t("errors.save"));
        focusEditorError({});
      }
    } finally {
      if (currentNovelIdRef.current === commandNovelId) setSaving(false);
    }
  };

  const openDeleteConfirm = async (volume: VolumeReadV2, kind: "soft-delete" | "hard-delete") => {
    if (mutationBlocked || candidateReviewing || editor || !novelId) return;
    confirmReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const commandNovelId = novelId;
    setActionVolumeId(volume.volume_id);
    setPageActionError("");
    try {
      const response = await apiGet<unknown>(`/api/volumes/${volume.volume_id}/delete-impact`);
      if (currentNovelIdRef.current !== commandNovelId) return;
      setConfirmIntent({ kind, volume, impact: parseVolumeDeleteImpactV2(response) });
      setConfirmError("");
    } catch (error) {
      if (currentNovelIdRef.current !== commandNovelId) return;
      setPageActionError(error instanceof Error ? error.message : t("errors.impact"));
    } finally {
      if (currentNovelIdRef.current === commandNovelId) setActionVolumeId("");
    }
  };

  const runConfirmAction = async () => {
    if (!confirmIntent || mutationBlocked || !novelId) return;
    if (
      confirmIntent.impact
      && hasBlockingVolumeImpact(confirmIntent.impact, confirmIntent.kind)
    ) return;
    const commandNovelId = novelId;
    const { volume } = confirmIntent;
    setActionVolumeId(volume.volume_id);
    setConfirmError("");
    try {
      if (confirmIntent.kind === "soft-delete") {
        const response = await apiDelete<VolumeMutationEnvelope>(
          `/api/volumes/${volume.volume_id}?expected_version=${volume.version}`,
        );
        if (currentNovelIdRef.current !== commandNovelId) return;
        setVolumes((current) => current.filter((item) => item.volume_id !== volume.volume_id));
        setTrashVolumes((current) => [response.data, ...current]);
        setSelectedVolumeId(response.data.volume_id);
        if (onLocationChange) {
          pendingLocationRef.current = { view: "trash", volumeId: response.data.volume_id };
          onLocationChange("trash", response.data.volume_id, true);
        } else {
          onViewChange?.("trash");
        }
      } else if (confirmIntent.kind === "restore") {
        const response = await apiPost<VolumeMutationEnvelope>(
          `/api/volumes/${volume.volume_id}/restore`,
          { expected_version: volume.version },
        );
        if (currentNovelIdRef.current !== commandNovelId) return;
        setTrashVolumes((current) => current.filter((item) => item.volume_id !== volume.volume_id));
        setVolumes((current) => [...current, response.data].sort((left, right) => left.order_index - right.order_index));
        setSelectedVolumeId(response.data.volume_id);
        if (onLocationChange) {
          pendingLocationRef.current = { view: "overview", volumeId: response.data.volume_id };
          onLocationChange("overview", response.data.volume_id, true);
        } else {
          onViewChange?.("overview");
        }
      } else {
        await apiDelete(
          `/api/volumes/${volume.volume_id}/hard?expected_version=${volume.version}`,
        );
        if (currentNovelIdRef.current !== commandNovelId) return;
        const remaining = trashVolumes.filter((item) => item.volume_id !== volume.volume_id);
        setTrashVolumes(remaining);
        setSelectedVolumeId(remaining[0]?.volume_id ?? "");
        if (onLocationChange) {
          pendingLocationRef.current = { view: "trash", volumeId: remaining[0]?.volume_id ?? null };
          onLocationChange("trash", remaining[0]?.volume_id ?? null, true);
        } else {
          onVolumeIdChange?.(remaining[0]?.volume_id ?? null, true);
        }
      }
      setConfirmIntent(null);
      setMobileDetailOpen(false);
      // 删除或恢复会同时改变其他卷的顺序和版本，所以这里马上重新读取。
      await loadWorkspace();
      if (currentNovelIdRef.current !== commandNovelId) return;
      onFormalFactsChanged?.();
    } catch (error) {
      if (currentNovelIdRef.current !== commandNovelId) return;
      setConfirmError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.conflict")
        : error instanceof Error ? error.message : t("errors.action"));
    } finally {
      if (currentNovelIdRef.current === commandNovelId) setActionVolumeId("");
    }
  };

  if (!canUseSavedNovel) {
    return (
      <section className="grid h-full min-h-72 place-items-center bg-background px-5 py-10">
        <div className="w-full max-w-xl border-y border-border py-10 text-center">
          <span className="text-2xl text-accent" aria-hidden="true">◇</span>
          <h1 className="mt-3 text-xl font-semibold text-foreground">{t("disabled.title")}</h1>
        </div>
      </section>
    );
  }

  const statusField = (
    <label className="grid gap-2 text-sm">
      <span className="text-xs font-medium text-muted">{t("fields.status")}</span>
      <select name="status" value={draft.status} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as VolumeStatus }))} disabled={saving} className={INPUT_CLASS}>
        {VOLUME_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
      </select>
    </label>
  );

  const volumeSelector = (
            <label className="grid min-w-0 flex-[0_1_180px] gap-1.5 text-xs font-medium text-muted">
              <span>{t("fields.volume")}</span>
              <select className={FILTER_CLASS} value={selectedVolume?.volume_id ?? ""} disabled={loading || stateBusy || preparationBusy || leavingCharacters} onChange={(event) => void selectVolume(event.target.value)}>
                {!selectedVolume && <option value="">{t("empty.volumesTitle")}</option>}
                {volumes.map((volume) => <option key={volume.volume_id} value={volume.volume_id}>{t("order", { order: volume.order_index })} · {volume.title}</option>)}
                {stateView && trashVolumes.length > 0 && <optgroup label={t("tabs.trash")}>
                  {trashVolumes.map((volume) => <option key={volume.volume_id} value={volume.volume_id}>{t("order", { order: volume.order_index })} · {volume.title} · {t("tabs.trash")}</option>)}
                </optgroup>}
              </select>
            </label>
  );

  const toolbar = (
    <section className={`workspace-toolbar min-w-0 flex-[1_1_440px] ${mobileDetailOpen && !listCollapsed ? "hidden @min-[800px]/master:block" : ""}`}>
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid min-w-0 flex-[1_1_180px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.search")}</span>
          <span className="relative block">
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("filters.searchPlaceholder")} disabled={Boolean(editor)} className={`${FILTER_CLASS} pr-10 [&::-webkit-search-cancel-button]:hidden`} />
            {filtersActive && <button type="button" title={t("actions.clearFilters")} aria-label={t("actions.clearFilters")} disabled={Boolean(editor)} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-lg text-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-accent" onClick={() => { setSearch(""); setStatusFilter("all"); }}>
              <svg aria-hidden="true" className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>}
          </span>
        </label>
        <label className="grid flex-[0_1_160px] gap-1.5 text-xs font-medium text-muted">
          <span>{t("filters.status")}</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "all" | VolumeStatus)} disabled={Boolean(editor)} className={FILTER_CLASS}>
            <option value="all">{t("filters.allStatuses")}</option>
            {VOLUME_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          {initialView === "overview" && <Button variant="primary" size="sm" onPress={openCreate} isDisabled={mutationBlocked || Boolean(editor)}>{t("actions.create")}</Button>}
        </div>
      </div>
    </section>
  );

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b border-border bg-surface">
        <h1 className="sr-only">{t("title")}</h1>
        <div className="flex min-w-0 items-end justify-between gap-2 px-4 sm:px-6">
          <div className="flex min-w-0 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
            {VOLUME_VIEWS.map((view, index) => (
              <button
                key={view}
                id={`${tabPrefix}-${view}-tab`}
                type="button"
                role="tab"
                aria-selected={initialView === view}
                aria-controls={`${tabPrefix}-${view}-panel`}
                tabIndex={initialView === view ? 0 : -1}
                disabled={Boolean(editor) || stateBusy || preparationBusy || leavingCharacters}
                onClick={() => void changeView(view)}
                onKeyDown={(event) => {
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? VOLUME_VIEWS.length - 1
                      : (index + (event.key === "ArrowRight" ? 1 : -1) + VOLUME_VIEWS.length) % VOLUME_VIEWS.length;
                  const nextView = VOLUME_VIEWS[nextIndex];
                  void changeView(nextView).then((changed) => { if (changed) document.getElementById(`${tabPrefix}-${nextView}-tab`)?.focus(); });
                }}
                className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors ${initialView === view ? "border-accent text-accent" : "border-transparent text-muted hover:border-border hover:text-foreground"}`}
              >
                {t(`tabs.${view}`)}
                {(view === "overview" || view === "trash") && (
                  <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs tabular-nums text-muted">
                    {view === "trash" ? trashVolumes.length : volumes.length}
                  </span>
                )}
              </button>
            ))}
          </div>
          <SectionActionButton action="refresh" label={loading ? t("actions.refreshing") : t("actions.refresh")} className="mb-1 shrink-0" variant="ghost" size="sm" onPress={() => void loadWorkspace()} isDisabled={loading || saving || Boolean(actionVolumeId) || candidateBusy || stateBusy || preparationBusy || leavingCharacters} />
        </div>
      </header>

      <RetainedViews key={novelId} activeKey={initialView}>
      <div
        id={`${tabPrefix}-${initialView}-panel`}
        role="tabpanel"
        aria-labelledby={`${tabPrefix}-${initialView}-tab`}
        className="@container/master flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 sm:px-6"
      >
        {entityView ? <>

          {(dataError || pageActionError) && <RelationEditorErrorSummary message={dataError || pageActionError} />}
          {invalidVolumeId && <RelationEditorErrorSummary message={t("notFound.title")} />}
          {selectedVolume && novelId ? <RetainedViews activeKey={selectedVolume.volume_id}>
            <div className="flex min-h-0 flex-1 flex-col gap-3" key={selectedVolume.volume_id}>
              <VolumePreparation volume={selectedVolume} stage={initialView} refreshKey={refreshKey} disabled={stateBusy || leavingCharacters} toolbarBefore={volumeSelector} onBusyChange={setPreparationBusy} onSaved={acceptSavedVolume} onGoToStage={(stage) => void changeView(stage)} beforeConfirm={initialView === "characters" ? async () => { await characterBeforeLeaveRef.current?.(); } : undefined}>
                {initialView !== "locations" ? ({ confirmAction, canGenerate, error }) => <div className="flex min-h-0 flex-1 flex-col" inert={preparationBusy}>
                  {initialView === "characters" ? <CharacterVolumeStateWorkspace
                    requestedEntityId={requestedEntityId}
                    novelId={novelId} fixedVolumeId={selectedVolume.volume_id} fixedVolumeTitle={selectedVolume.title} fixedVolumeOrderIndex={selectedVolume.order_index}
                    fixedVolumeDeleted={selectedVolume.is_deleted} volumeVersion={selectedVolume.version} refreshKey={refreshKey} onBusyChange={setStateBusy} onFormalFactsChanged={refreshVolume} beforeLeaveRef={characterBeforeLeaveRef}
                    toolbarBefore={volumeSelector} toolbarAfter={confirmAction} beforeContent={error} generationDisabled={!canGenerate}
                  /> : <FactionVolumeStateWorkspace
                    requestedEntityId={requestedEntityId}
                    novelId={novelId} fixedVolumeId={selectedVolume.volume_id} fixedVolumeTitle={selectedVolume.title} fixedVolumeOrderIndex={selectedVolume.order_index}
                    fixedVolumeDeleted={selectedVolume.is_deleted} volumeVersion={selectedVolume.version} refreshKey={refreshKey} onBusyChange={setStateBusy} onFormalFactsChanged={refreshVolume}
                    toolbarBefore={volumeSelector} toolbarAfter={confirmAction} beforeContent={error} generationDisabled={!canGenerate}
                  />}
                </div> : undefined}
              </VolumePreparation>
            </div>
          </RetainedViews> : <><div className="workspace-toolbar flex shrink-0 flex-wrap items-end gap-2">{volumeSelector}</div>{!loading && <p className="py-6 text-sm text-muted">{t("empty.volumesTitle")}</p>}</>}
        </> : <>
        {/* 保留卷会话的容器不参与工具栏排版，让生成进度在按钮下方占满一行。 */}
        <div className={candidateReviewing
          ? "flex min-h-0 flex-1 flex-col"
          : `flex shrink-0 flex-wrap items-end gap-3 border-b border-border pb-3 [&>div:not([hidden])]:contents ${mobileDetailOpen && !listCollapsed && initialView !== "overview" ? "hidden @min-[800px]/master:flex" : ""}`}>
          {!candidateReviewing && toolbar}
          {initialView === "overview" && novelId && (
            <RetainedViews activeKey={selectedVolumeId || "none"}>
            <VolumePlanningCandidateWorkspace
              task="all"
              key={`${novelId}:${selectedVolume?.volume_id ?? "none"}`}
              novelId={novelId}
              volumes={volumes}
              selectedVolume={selectedVolume}
              disabled={loading || saving || Boolean(actionVolumeId) || Boolean(editor) || Boolean(confirmIntent)}
              onReviewingChange={setCandidateReviewing}
              onBusyChange={setCandidateBusy}
              onProcessLaunchContext={onProcessLaunchContext && selectedVolume ? (kind, id) => onProcessLaunchContext(kind, id, selectedVolume.volume_id) : undefined}
              onLaunchConfirmed={() => {
                onFormalFactsChanged?.();
                void loadWorkspace();
              }}
              onSkeletonConfirmed={(response: VolumeBulkPlanResponseV1) => {
                // 先接入已保存的卷，避免地址更新后被旧列表误判为无效卷。
                setVolumes((current) => {
                  const confirmed = new Map(response.volumes.map((volume) => [volume.volume_id, volume]));
                  return current.filter((volume) => !confirmed.has(volume.volume_id))
                    .concat(response.volumes).sort((left, right) => left.order_index - right.order_index);
                });
                const firstVolume = response.volumes[0] ?? null;
                if (firstVolume) {
                  setSelectedVolumeId(firstVolume.volume_id);
                  setInvalidVolumeId("");
                  if (onLocationChange) {
                    pendingLocationRef.current = { view: "overview", volumeId: firstVolume.volume_id };
                    onLocationChange("overview", firstVolume.volume_id, true);
                  } else {
                    onVolumeIdChange?.(firstVolume.volume_id, true);
                  }
                }
                onFormalFactsChanged?.();
                void loadWorkspace();
              }}
            />
            </RetainedViews>
          )}
        </div>

        {!candidateReviewing && (
          <>
            {dataError && (
              <div className="shrink-0 border-y border-red-500/40 bg-red-50 px-5 py-4 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
                <p className="font-semibold">{t("errors.load")}</p>
                <p className="mt-1">{dataError}</p>
                <Button className="mt-3" variant="outline" size="sm" onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
              </div>
            )}
            {pageActionError && !dataError && (
              <div className="shrink-0 border-y border-red-500/40 bg-red-50 px-5 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{pageActionError}</div>
            )}
            {invalidVolumeId && !dataError && (
              <div className="shrink-0 border-y border-amber-500/45 bg-amber-50 px-5 py-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" role="alert">
                <p className="font-semibold">{t("notFound.title")}</p>
                <p className="mt-1 text-sm leading-6">{t("notFound.description")}</p>
                <p className="mt-2 font-mono text-xs">{invalidVolumeId}</p>
              </div>
            )}

        {loading && sourceVolumes.length === 0 ? (
          <div className="border-y border-border px-5 py-14 text-center" role="status">
            <span className="mx-auto block size-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted">{t("loading")}</p>
          </div>
        ) : filteredVolumes.length === 0 ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center">
            <p className="text-sm font-medium text-foreground">{filtersActive ? t("empty.filteredTitle") : initialView === "trash" ? t("empty.trashTitle") : t("empty.volumesTitle")}</p>
          </div>
        ) : (
          <div className={`grid min-h-[520px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
            {/* 手柄在清单滚动区外，收起后保留零宽边界和原来的滚动位置。 */}
            <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
              <aside
                id={`volume-list-${novelId}-${initialView}`}
                className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
                aria-label={t("title")}
                aria-hidden={listCollapsed || undefined}
                inert={listCollapsed}
                tabIndex={0}
              >
                <ul className="divide-y divide-border" role="tree" aria-label={t("title")}>
                  {filteredVolumes.map((volume, index) => (
                    <li key={volume.volume_id} role="none">
                      <button
                        id={`volume-tree-${novelId}-${initialView}-${volume.volume_id}`}
                        type="button"
                        role="treeitem"
                        aria-level={1}
                        aria-selected={selectedVolume?.volume_id === volume.volume_id}
                        tabIndex={selectedVolume?.volume_id === volume.volume_id || (!selectedVolume && index === 0) ? 0 : -1}
                        disabled={plotBusy || saving || Boolean(editor && (editor.mode !== "edit" || editor.source.volume_id !== volume.volume_id))}
                        onClick={() => selectVolume(volume.volume_id)}
                        onKeyDown={(event) => {
                          if (event.altKey || event.ctrlKey || event.metaKey) return;
                          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                          event.preventDefault();
                          const nextIndex = index + (event.key === "ArrowDown" ? 1 : -1);
                          const next = filteredVolumes[nextIndex];
                          if (next) {
                            selectVolume(next.volume_id);
                            document.getElementById(`volume-tree-${novelId}-${initialView}-${next.volume_id}`)?.focus();
                          }
                        }}
                        className={`w-full px-4 py-3 text-left transition-colors ${selectedVolume?.volume_id === volume.volume_id ? "bg-accent/10" : "hover:bg-surface-secondary/55"}`}
                      >
                        <span className="flex items-center justify-between gap-3">
                          <span className="truncate text-sm font-semibold text-foreground">{volume.title}</span>
                          <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${volume.status === "active" ? "bg-emerald-500" : "bg-muted/45"}`} />
                        </span>
                        <span className="mt-1 block truncate text-xs text-muted">{t("order", { order: volume.order_index })} · {t(`status.${volume.status}`)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </aside>
              <SidebarEdgeHandle
                controls={`volume-list-${novelId}-${initialView}`}
                className="hidden @min-[800px]/master:flex"
                leftAction={listCollapsed ? undefined : {
                  label: t("actions.collapseList"), expanded: true,
                  onPress: () => { setListCollapsed(true); setMobileDetailOpen(true); },
                }}
                rightAction={listCollapsed ? {
                  label: t("actions.expandList"), expanded: false,
                  onPress: () => { setListCollapsed(false); setMobileDetailOpen(false); },
                } : undefined}
              />
            </div>

            <article
              id={selectedVolume ? `volume-detail-${novelId}-${initialView}-${selectedVolume.volume_id}` : undefined}
              className={`@container/detail ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0`}
              aria-label={selectedVolume ? `${t("title")} · ${selectedVolume.title}` : t("title")}
              tabIndex={0}
            >
              {selectedVolume ? (
                <>
                  <button
                    type="button"
                    className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden"
                    onClick={() => {
                      const volumeId = selectedVolume.volume_id;
                      setListCollapsed(false);
                      setMobileDetailOpen(false);
                      requestAnimationFrame(() => document.getElementById(`volume-tree-${novelId}-${initialView}-${volumeId}`)?.focus());
                    }}
                  >
                    ← {t("actions.backToTree")}
                  </button>
                  <div className="min-w-0 px-5 py-4 sm:px-7">
                    <h2 className="sr-only">{selectedVolume.title}</h2>
                    <header className="flex flex-wrap items-center justify-between gap-2">
                      {initialView === "overview" && <Button size="sm" variant="ghost" className="text-accent" onPress={() => { const target = document.getElementById(`plot-section-volume-${selectedVolume.volume_id}`); target?.focus({ preventScroll: true }); target?.scrollIntoView({ block: "start" }); }}><span aria-hidden="true">↓</span>{plotT("jumpToPlot")}</Button>}
                      <div className="flex flex-wrap gap-2">
                        {initialView === "trash" ? (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onPress={() => {
                                confirmReturnFocusRef.current = document.activeElement instanceof HTMLElement
                                  ? document.activeElement
                                  : null;
                                setConfirmIntent({ kind: "restore", volume: selectedVolume, impact: null });
                                setConfirmError("");
                              }}
                              isDisabled={mutationBlocked}
                            >
                              {t("actions.restore")}
                            </Button>
                            <Button size="sm" variant="ghost" className="text-danger" onPress={() => void openDeleteConfirm(selectedVolume, "hard-delete")} isDisabled={mutationBlocked}>{t("actions.hardDelete")}</Button>
                          </>
                        ) : (
                          <>
                            <SectionActionButton action="trash" label={t("actions.delete")} size="sm" variant="ghost" className="text-danger" onPress={() => void openDeleteConfirm(selectedVolume, "soft-delete")} isDisabled={mutationBlocked || Boolean(editor)} />
                          </>
                        )}
                      </div>
                    </header>

                    {initialView === "overview" || initialView === "trash" ? (
                      <>
                        <div className="mt-4 space-y-4">
                          {(["identity", "planning"] as const).map((section, index) => {
                            const editing = editor?.mode === "edit" && editor.section === section && editor.source.volume_id === selectedVolume.volume_id;
                            return (
                              <DocumentSection
                                key={section}
                                number={String(index + 1).padStart(2, "0")}
                                title={t(`sections.${section}`)}
                                actions={initialView === "trash" ? undefined : editing ? <>
                                  <SectionActionButton action="cancel" label={t("actions.cancel")} variant="ghost" size="sm" onPress={closeEditor} isDisabled={saving} />
                                  <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} variant="primary" size="sm" onPress={() => void saveEditor()} isDisabled={saving || mutationBlocked} />
                                </> : <SectionEditButton id={`volume-edit-${selectedVolume.volume_id}-${section}`} label={t("actions.edit")} onPress={() => openEdit(selectedVolume, section)} isDisabled={mutationBlocked || Boolean(editor)} />}
                              >
                                {editing ? <div ref={inlineEditorRef}>
                                  {editorError && <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} className="mb-4" />}
                                  <VolumeFieldsForm
                                    value={draft} onChange={setDraft} disabled={saving}
                                    fieldErrors={editorFieldErrors} errorIdPrefix={`volume-${section}`}
                                    section={section} allowPlanningToggle identityExtra={statusField}
                                  />
                                </div> : <VolumeOverview volume={selectedVolume} section={section} t={t} locale={locale} />}
                              </DocumentSection>
                            );
                          })}
                        {initialView !== "trash" && <PlotSection focusPlot={focusPlot} key={`plot-${selectedVolume.volume_id}`} kind="volume" record={selectedVolume} disabled={loading || saving || Boolean(editor) || candidateBusy} onBusyChange={setPlotBusy} onRunningChange={setPlotRunning} onSaved={(record) => acceptSavedVolume(record as VolumeReadV2)} />}
                        </div>
                      </>
                    ) : null}
                  </div>
                </>
              ) : (
                <div className="grid min-h-72 place-items-center px-5 py-10 text-center text-sm text-muted">{t("actions.backToTree")}</div>
              )}
            </article>
          </div>
        )}
          </>
        )}
        </>}
      </div>
      </RetainedViews>

      {editor?.mode === "create" && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !saving && closeEditor()} variant="blur" isDismissable={!saving} isKeyboardDismissDisabled={saving}>
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <Modal.Heading className="text-lg font-semibold text-foreground">{t("editor.createTitle")}</Modal.Heading>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
                {editorError && <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} className="mb-6" />}
                <VolumeFieldsForm
                  value={draft}
                  onChange={setDraft}
                  disabled={saving}
                  fieldErrors={editorFieldErrors}
                  errorIdPrefix="volume"
                  autoFocusTitle
                  allowPlanningToggle
                  identityExtra={statusField}
                />
              </Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeEditor} isDisabled={saving}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void saveEditor()} isDisabled={saving || mutationBlocked}>{saving ? t("actions.saving") : t("actions.save")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}

      {confirmIntent && (
        <ConfirmActionModal
          title={confirmIntent.kind === "soft-delete" ? t("confirm.softDelete.title") : confirmIntent.kind === "restore" ? t("confirm.restore.title") : t("confirm.hardDelete.title")}
          message={confirmIntent.kind === "soft-delete"
            ? <VolumeImpactDetails volume={confirmIntent.volume} impact={confirmIntent.impact} kind="softDelete" t={t} />
            : confirmIntent.kind === "restore"
              ? t("confirm.restore.message", { name: confirmIntent.volume.title })
              : <VolumeImpactDetails volume={confirmIntent.volume} impact={confirmIntent.impact} kind="hardDelete" t={t} />}
          confirmText={confirmIntent.kind === "soft-delete" ? t("confirm.softDelete.action") : confirmIntent.kind === "restore" ? t("confirm.restore.action") : t("confirm.hardDelete.action")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          danger={confirmIntent.kind !== "restore"}
          error={confirmError}
          isLoading={actionVolumeId === confirmIntent.volume.volume_id}
          isConfirmDisabled={loading || Boolean(
            confirmIntent.impact
            && hasBlockingVolumeImpact(confirmIntent.impact, confirmIntent.kind),
          )}
          onCancel={() => {
            const returnFocus = confirmReturnFocusRef.current;
            setConfirmIntent(null);
            setConfirmError("");
            requestAnimationFrame(() => returnFocus?.focus());
          }}
          onConfirm={() => void runConfirmAction()}
        />
      )}
    </section>
  );
}

function VolumeImpactDetails({
  volume,
  impact,
  kind,
  t,
}: {
  volume: VolumeReadV2;
  impact: VolumeDeleteImpactV2;
  kind: "softDelete" | "hardDelete";
  t: ReturnType<typeof useTranslations>;
}) {
  const hasBlockers = hasBlockingVolumeImpact(
    impact,
    kind === "softDelete" ? "soft-delete" : "hard-delete",
  );
  const items = [
    ["arcs", impact.arcs],
    ["scenes", impact.scenes],
    ["chapters", impact.chapters],
    ["factions", impact.factions],
    ["characterVolumeStates", impact.character_volume_states],
    ["factionVolumeStates", impact.faction_volume_states],
    ["characterFirstAppearances", impact.character_first_appearances],
    ["factionFirstAppearances", impact.faction_first_appearances],
    ["bindingBoundaries", impact.character_faction_binding_boundaries],
    ["foreshadowings", impact.foreshadowings],
    ["chapterRecords", impact.chapter_records],
  ] as const;
  return (
    <div>
      <p>{t(`confirm.${kind}.message`, {
        name: volume.title,
        total: impact.total,
        blockers: hasBlockers ? t("confirm.blocked") : t("confirm.clear"),
      })}</p>
      <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-2 border-y border-border py-3 text-xs">
        {items.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-3">
            <dt>{t(`impact.${key}`)}</dt>
            <dd className="tabular-nums text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {kind === "softDelete" && impact.character_volume_states > 0 && (
        <p className="mt-3 text-amber-800 dark:text-amber-200">
          {t("impact.characterStatesPropagated", { count: impact.character_volume_states })}
        </p>
      )}
      {kind === "softDelete" && impact.faction_volume_states > 0 && (
        <p className="mt-3 text-amber-800 dark:text-amber-200">
          {t("impact.factionStatesPropagated", { count: impact.faction_volume_states })}
        </p>
      )}
      {kind === "softDelete" && impact.chapter_records > 0 && (
        <p className="mt-3 text-amber-800 dark:text-amber-200">
          {t("impact.chapterRecordsPreserved", { count: impact.chapter_records })}
        </p>
      )}
      {hasBlockers && (
        <p className="mt-3 font-medium text-red-700 dark:text-red-300" role="alert">
          {kind === "hardDelete" && impact.chapter_records > 0
            ? t("impact.chapterRecordsDeleteBlocked", { count: impact.chapter_records })
            : t("impact.blockedDescription")}
        </p>
      )}
    </div>
  );
}

/** 软删除会标记卷内状态并保留章后记录；永久删除仍会被所有引用阻止。 */
function hasBlockingVolumeImpact(
  impact: VolumeDeleteImpactV2,
  kind: "soft-delete" | "restore" | "hard-delete",
): boolean {
  if (kind === "restore") return false;
  return kind === "soft-delete"
    ? impact.total - impact.character_volume_states - impact.faction_volume_states - impact.chapter_records > 0
    : impact.has_blockers;
}

/** 功能：按章节显示卷的基本资料或规划字段。Args: volume 当前卷；section 当前章节；t 文案；locale 数字格式。Returns: 可展开长文的字段列表。 */
function VolumeOverview({ volume, section, t, locale }: { volume: VolumeReadV2; section: "identity" | "planning"; t: ReturnType<typeof useTranslations>; locale: string }) {
  if (section === "identity") return (
    <dl className="detail-fields grid gap-4">
      <ReadOnlyField label={t("fields.title")} value={volume.title} />
      <ReadOnlyField label={t("fields.subtitle")} value={volume.subtitle} />
      <ReadOnlyField label={t("fields.status")} value={t(`status.${volume.status}`)} />
      <ReadOnlyField label={t("fields.summary")} value={volume.summary} wide />
      <ReadOnlyField label={t("fields.goal")} value={volume.goal} wide />
      <ReadOnlyField label={t("fields.theme")} value={volume.theme} wide />
      <ReadOnlyField label={t("stats.arcs")} value={String(volume.arcs_count)} />
      <ReadOnlyField label={t("stats.words")} value={String(volume.word_count)} />
    </dl>
  );
  if (!volume.planning) return <p className="text-sm text-muted">—</p>;
  return (
    <dl className="detail-fields grid gap-4">
      <ReadOnlyField label={t("fields.premise")} value={volume.planning.premise} wide />
      <ReadOnlyField label={t("fields.majorConflict")} value={volume.planning.major_conflict} wide />
      <ReadOnlyField label={t("fields.turningPoints")} wide value={volume.planning.key_turning_points.length
        ? <TagList values={volume.planning.key_turning_points} label={t("fields.turningPoints")} /> : "—"} />
      <ReadOnlyField label={t("fields.startState")} value={volume.planning.start_state} wide />
      <ReadOnlyField label={t("fields.endState")} value={volume.planning.end_state} wide />
      <ReadOnlyField label={t("fields.targetChapterCount")} value={volume.planning.target_chapter_count.toLocaleString(locale)} />
      <ReadOnlyField label={t("fields.targetWordCount")} value={volume.planning.target_word_count.toLocaleString(locale)} />
    </dl>
  );
}
