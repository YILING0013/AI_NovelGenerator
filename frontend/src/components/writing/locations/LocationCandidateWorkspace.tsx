"use client";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { TaskFlowForm,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import type { FlowRef } from "@/types/taskFlow";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";

import { Button,Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
useCallback,
useEffect,
useMemo,
useReducer,
useRef,
useState,
type ReactNode,
} from "react";

import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import {
buildCandidateExpectedVersions,
createLocalCandidateState,
localCandidateReducer,
type LocalCandidateAction,
type LocalCandidateState,
} from "@/lib/aiCandidate";
import {
apiGet,
apiPost,
ApiRequestError,
type ApiFieldErrors
} from "@/lib/api";
import {
parseActiveLocationListV1,
parseVolumeLocationsConfirmResponseV1,
parseVolumeLocationsPreviewV1,
type LocationContentFieldsV1,
type LocationReadV1,
type VolumeLocationCandidateV1,
type VolumeLocationsBasisV1,
type VolumeLocationsConfirmResponseV1,
type VolumeLocationsGenerationInputV1,
type VolumeLocationsResultV1
} from "@/types/location";
import type { CoreFaction } from "@/types/novel";
import type { VolumeReadV2 } from "@/types/volume";
import type { WorldRuleReadV1 } from "@/types/worldRule";
import LocationFieldsForm from "./LocationFieldsForm";

interface LocationCandidateWorkspaceProps {
  novelId: string;
  volume: VolumeReadV2;
  disabled?: boolean;
  refreshKey?: number;
  toolbarBefore?: ReactNode;
  toolbarAfter?: ReactNode;
  beforeContent?: ReactNode;
  onBusyChange?: (busy: boolean) => void;
  onConfirmed?: (response: VolumeLocationsConfirmResponseV1) => void;
  onFormalFactsChanged?: () => void;
}

interface StableConfirmCommand {
  payload: string;
  key: string;
}

interface LocationDraft {
  state: LocalCandidateState<VolumeLocationsResultV1>;
  flow_ref: FlowRef | null;
  inputs: Record<string, unknown>;
  params: GenerationParamsValue;
  command: StableConfirmCommand | null;
  fieldErrors: Record<string, ApiFieldErrors>;
  pageVersions: Record<string, number>;
  generationVersion: number | null;
  generationFieldErrors?: ApiFieldErrors;
  completed?: VolumeLocationsConfirmResponseV1;
}

// 本地清稿失败时，关闭重开仍记住已经收到的成功响应。
const confirmedCommands = new Map<string, VolumeLocationsConfirmResponseV1>();

function normalizeLocationName(value: string): string {
  return value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function validateEditableCandidates(
  candidates: readonly VolumeLocationCandidateV1[],
  formalLocations: readonly LocationReadV1[],
  messages: {
    nameRequired: string;
    typeRequired: string;
    descriptionRequired: string;
    storyFunctionRequired: string;
    duplicateName: string;
    parentInvalid: string;
  },
): Record<string, ApiFieldErrors> {
  const result: Record<string, ApiFieldErrors> = {};
  const usedNames = new Set(
    formalLocations
      .filter((location) => !location.is_deleted && location.status === "active")
      .flatMap((location) => [location.name, ...location.aliases])
      .map(normalizeLocationName),
  );
  const formalIds = new Set(
    formalLocations
      .filter((location) => !location.is_deleted && location.status === "active")
      .map((location) => location.location_id),
  );
  const seenCandidateRefs = new Set<string>();

  for (const candidate of candidates) {
    const errors: ApiFieldErrors = {};
    if (!candidate.name.trim()) errors.name = [messages.nameRequired];
    if (!candidate.location_type.trim()) errors.location_type = [messages.typeRequired];
    if (!candidate.description.trim()) errors.description = [messages.descriptionRequired];
    if (!candidate.story_function.trim()) errors.story_function = [messages.storyFunctionRequired];
    if (
      (candidate.parent_location_ref && !seenCandidateRefs.has(candidate.parent_location_ref))
      || (candidate.parent_location_id && !formalIds.has(candidate.parent_location_id))
      || (candidate.parent_location_ref !== null && candidate.parent_location_id !== null)
    ) errors.parent_location_id = [messages.parentInvalid];

    for (const text of [candidate.name, ...candidate.aliases]) {
      const normalized = normalizeLocationName(text);
      if (normalized && usedNames.has(normalized)) errors.name = [messages.duplicateName];
      if (normalized) usedNames.add(normalized);
    }
    if (Object.keys(errors).length > 0) result[candidate.candidate_ref] = errors;
    seenCandidateRefs.add(candidate.candidate_ref);
  }
  return result;
}

function normalizeConfirmFieldErrors(
  fieldErrors: ApiFieldErrors,
  candidates: readonly VolumeLocationCandidateV1[],
  localizedMessage: string,
): Record<string, ApiFieldErrors> {
  const result: Record<string, ApiFieldErrors> = {};
  for (const path of Object.keys(fieldErrors)) {
    const parts = path.split(".");
    const candidateIndex = parts[0] === "candidates" ? Number(parts[1]) : Number.NaN;
    const candidate = Number.isInteger(candidateIndex) ? candidates[candidateIndex] : candidates[0];
    if (!candidate) continue;
    const rawField = parts[0] === "candidates" && parts.length >= 3 ? parts[2] : parts[0];
    const field = rawField === "parent_location_ref" ? "parent_location_id" : rawField;
    result[candidate.candidate_ref] = {
      ...(result[candidate.candidate_ref] ?? {}),
      [field]: fieldErrors[path].length ? fieldErrors[path] : [localizedMessage],
    };
  }
  return result;
}

function focusCandidateError(fieldErrors: ApiFieldErrors): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const workspace = document.querySelector<HTMLElement>(
        '[aria-labelledby="volume-locations-candidate-heading"]',
      );
      if (!workspace) return;
      const firstField = Object.keys(fieldErrors)[0];
      const target = firstField
        ? workspace.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`)
        : workspace.querySelector<HTMLElement>("[data-editor-error-summary]");
      (target ?? workspace.querySelector<HTMLElement>("[data-editor-error-summary]"))?.focus({
        preventScroll: true,
      });
    });
  });
}

/**
 * 渲染当前卷的新地点生成与候选复核；手选参考地点放在生成表单内。
 *
 * Args:
 *   novelId: 当前小说 ObjectId。
 *   volume: 当前卷及其版本。
 *   disabled: 当前卷还没填写规划，或页面正在执行其他操作时禁用生成。
 *   onBusyChange: 生成或保存期间通知卷工作台锁定卷操作。
 *   onConfirmed: 新地点整批确认成功后的完整响应回调。
 *   onFormalFactsChanged: 正式地点写入成功后通知上层刷新事实状态。
 *
 * Returns:
 *   支持本地草稿恢复和原请求重试的卷内地点工作区。
 */
export default function LocationCandidateWorkspace({
  novelId,
  volume,
  disabled = false,
  refreshKey,
  toolbarBefore,
  toolbarAfter,
  beforeContent,
  onBusyChange,
  onConfirmed,
  onFormalFactsChanged,
}: LocationCandidateWorkspaceProps) {
  const t = useTranslations("writing.locations.ai");
  const locationT = useTranslations("writing.locations");
  const [formalLocations, setFormalLocations] = useState<LocationReadV1[]>([]);
  const [rules, setRules] = useState<WorldRuleReadV1[]>([]);
  const [factions, setFactions] = useState<CoreFaction[]>([]);
  const [factsLoading, setFactsLoading] = useState(true);
  const [factsError, setFactsError] = useState("");
  const taskFlow = useTaskFlow("create_locations_for_volume_by_ai");
  const { loading: flowLoading, select: selectFlow, setInputs, setParams, discard: discardFlow } = taskFlow;
  const [dialogOpen, setDialogOpen] = useState(false);
  const [candidateState, dispatchCandidate] = useReducer(
    (state: LocalCandidateState<VolumeLocationsResultV1>, action: LocalCandidateAction<VolumeLocationsResultV1> | { type: "restore"; state: LocalCandidateState<VolumeLocationsResultV1> }) =>
      action.type === "restore" ? action.state : localCandidateReducer(state, action),
    createLocalCandidateState<VolumeLocationsResultV1>(),
  );
  const [selectedCandidateRef, setSelectedCandidateRef] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [candidateFieldErrors, setCandidateFieldErrors] = useState<Record<string, ApiFieldErrors>>({});
  const draftKey = `${novelId}:volume:${volume.volume_id}:locations:generation`;
  const [restoredScope, setRestoredScope] = useState("");
  const [draftReadError, setDraftReadError] = useState(false);
  const [draftReadAttempt, setDraftReadAttempt] = useState(0);
  const [storageError, setStorageError] = useState("");
  const [completed, setCompleted] = useState<VolumeLocationsConfirmResponseV1 | null>(null);
  const [savedFacts, setSavedFacts] = useState(false);
  const sessionRef = useRef<object | null>(null);
  const writes = useRef(Promise.resolve());
  const setup = useRef<LocationDraft | null>(null);
  const draftVersion = useRef(volume.version);
  const generationVersion = useRef<number | null>(null);
  const [completionDraft, setCompletionDraft] = useState<LocationDraft | null>(null);
  const [generationFieldErrors, setGenerationFieldErrors] = useState<ApiFieldErrors>({});
  const lastDraftScope = useRef("");
  const selectedStoredFlow = useRef(false);
  const [clearing, setClearing] = useState(false);
  const callbacks = useRef({ onConfirmed, onFormalFactsChanged });
  callbacks.current = { onConfirmed, onFormalFactsChanged };
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadRequestIdRef = useRef(0);
  const generationAbortRef = useRef<AbortController | null>(null);
  const confirmationAbortRef = useRef<AbortController | null>(null);
  const confirmCommandRef = useRef<StableConfirmCommand | null>(null);
  const dialogReturnFocusRef = useRef<HTMLElement | null>(null);
  const previewPageVersionsRef = useRef<Record<string, number>>({});
  const currentNovelIdRef = useRef(novelId);
  const currentVolumeIdRef = useRef(volume.volume_id);
  const currentVolumeVersionRef = useRef(volume.version);
  currentNovelIdRef.current = novelId;
  currentVolumeIdRef.current = volume.volume_id;
  currentVolumeVersionRef.current = volume.version;

  const candidates = candidateState.candidate?.locations ?? [];
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_ref === selectedCandidateRef)
    ?? candidates[0]
    ?? null;
  const reviewing = Boolean(candidateState.candidate);
  const restoring = restoredScope !== draftKey;
  const retryOnly = Boolean(confirmCommandRef.current) && candidateState.status !== "stale";
  const busy = clearing || candidateState.status === "generating" || candidateState.status === "confirming";
  const readOnly = disabled || restoring || factsLoading || Boolean(factsError) || retryOnly || candidateState.status === "stale" || candidateState.status === "confirming";

  const activeFormalLocations = useMemo(
    () => formalLocations.filter((location) => !location.is_deleted && location.status === "active"),
    [formalLocations],
  );
  const currentKnownVersions = useMemo(() => {
    const versions: Record<string, number> = {
      [`volume:${volume.volume_id}`]: volume.version,
    };
    for (const location of formalLocations) {
      if (!location.is_deleted && location.status === "active") {
        versions[`location:${location.location_id}`] = location.version;
      }
    }
    for (const rule of rules) {
      if (!rule.is_deleted && rule.status === "active") {
        versions[`world_rule:${rule.rule_id}`] = rule.version;
      }
    }
    for (const faction of factions) versions[`faction:${faction.faction_id}`] = faction.version;
    return versions;
  }, [factions, formalLocations, rules, volume.version, volume.volume_id]);
  const currentKnownVersionsRef = useRef(currentKnownVersions);
  currentKnownVersionsRef.current = currentKnownVersions;

  const loadFormalFacts = useCallback(async () => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = loadRequestIdRef.current + 1;
    const requestNovelId = novelId;
    const requestVolumeId = volume.volume_id;
    loadAbortRef.current = controller;
    loadRequestIdRef.current = requestId;
    setFactsLoading(true);
    setFactsError("");
    try {
      const results = await Promise.allSettled([
        apiGet<unknown>(`/api/locations/novel/${novelId}`, { signal: controller.signal }),
        apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}`, { signal: controller.signal }),
      ]);
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
        || currentVolumeIdRef.current !== requestVolumeId
      ) return;
      const failures = results.filter((result) => result.status === "rejected");
      const denied = failures.find((result) => result.reason instanceof ApiRequestError && [403, 404].includes(result.reason.status));
      if (denied) throw denied.reason;
      if (failures.length) throw failures[0].reason;
      const locationsResult = (results[0] as PromiseFulfilledResult<unknown>).value;
      const rulesResult = (results[1] as PromiseFulfilledResult<WorldRuleReadV1[]>).value;
      const factionsResult = (results[2] as PromiseFulfilledResult<{ data: CoreFaction[] }>).value;
      const locations = parseActiveLocationListV1(locationsResult, requestNovelId);
      setFormalLocations(locations);
      setRules(rulesResult);
      setFactions(factionsResult.data);
      setSavedFacts(false);
    } catch (error) {
      if (
        controller.signal.aborted
        || loadAbortRef.current !== controller
        || loadRequestIdRef.current !== requestId
        || currentNovelIdRef.current !== requestNovelId
        || currentVolumeIdRef.current !== requestVolumeId
      ) return;
      if (error instanceof ApiRequestError && [403, 404].includes(error.status)) {
        setFormalLocations([]); setRules([]); setFactions([]); setSavedFacts(false);
      }
      setFactsError(error instanceof Error ? error.message : t("errors.loadFacts"));
    } finally {
      if (loadAbortRef.current === controller) {
        loadAbortRef.current = null;
        setFactsLoading(false);
      }
    }
  }, [novelId, volume.volume_id, t]);

  useEffect(() => {
    void loadFormalFacts();
    return () => loadAbortRef.current?.abort();
  }, [loadFormalFacts, volume.volume_id, refreshKey]);

  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  useEffect(() => () => onBusyChange?.(false), [onBusyChange]);

  /** 功能：清理已成功请求的本地稿。Args: draft 成功回执；version 原版本；session 原页面会话。Returns: 清理结束，失败时保留成功回执。 */
  const cleanupCompleted = useCallback(async (draft: LocationDraft, version: number, session: object) => {
    try {
      await writes.current;
      await writeWritingDraft(draftKey, version, draft);
      await writeWritingDraft(draftKey, version, null);
      if (draft.command) confirmedCommands.delete(draft.command.key);
      if (sessionRef.current === session) { setStorageError(""); setCompletionDraft(null); }
    } catch {
      if (sessionRef.current === session) setStorageError(t("errors.savedDraftCleanupFailed"));
    }
  }, [draftKey, t]);

  useEffect(() => {
    const session = {};
    sessionRef.current = session;
    generationAbortRef.current?.abort(); generationAbortRef.current = null;
    confirmationAbortRef.current?.abort(); confirmationAbortRef.current = null;
    void discardFlow();
    setGenerationFieldErrors({});
    if (lastDraftScope.current !== draftKey) {
      setFormalLocations([]); setRules([]); setFactions([]);
      lastDraftScope.current = draftKey;
    }
    dispatchCandidate({ type: "discard" });
    setRestoredScope(""); setDraftReadError(false); setStorageError("");
    setDialogOpen(false); setSelectedCandidateRef(""); setMobileDetailOpen(false);
    setCandidateFieldErrors({}); setCompleted(null); setSavedFacts(false);
    confirmCommandRef.current = null; previewPageVersionsRef.current = {};
    generationVersion.current = null; draftVersion.current = currentVolumeVersionRef.current;
    setup.current = null; setCompletionDraft(null); selectedStoredFlow.current = false; setClearing(false);
    void (async () => {
      try {
        await writes.current;
        const stored = await readWritingDraft<LocationDraft>(draftKey);
        if (sessionRef.current !== session) return;
        if (!stored) { setRestoredScope(draftKey); return; }
        const draft = stored.value;
        const saved = draft.completed ?? (draft.command ? confirmedCommands.get(draft.command.key) : undefined);
        draftVersion.current = stored.base_version;
        if (saved) {
          const receipt = parseVolumeLocationsConfirmResponseV1(saved, novelId, draft.state.candidate?.locations.map((item) => item.candidate_ref) ?? []);
          if (!receipt) throw new Error(t("errors.invalidConfirmation"));
          const completedDraft = { ...draft, completed: receipt };
          setCompletionDraft(completedDraft);
          setCompleted(receipt); setSavedFacts(true); setRestoredScope(draftKey);
          loadAbortRef.current?.abort(); loadAbortRef.current = null; setFactsLoading(false);
          setFormalLocations((current) => [...current.filter((item) => !receipt.locations.some((savedItem) => savedItem.location_id === item.location_id)), ...receipt.locations]);
          callbacks.current.onConfirmed?.(receipt);
          callbacks.current.onFormalFactsChanged?.();
          void loadFormalFacts();
          void cleanupCompleted(completedDraft, stored.base_version, session);
          return;
        }
        if (draft.state.candidate) {
          const basis = draft.state.basis as VolumeLocationsBasisV1 | null;
          if (!basis || basis.generation_input.novel_id !== novelId || basis.generation_input.volume_id !== volume.volume_id
            || !parseVolumeLocationsPreviewV1({ workflow: basis.workflow, step: basis.step, schema_id: basis.schema_id, schema_version: basis.schema_version, candidate: draft.state.candidate, basis }, basis.generation_input, [], { editable: true })) {
            throw new Error(t("errors.invalidPreview"));
          }
        }
        setup.current = draft;
        // 原候选已有完整依据；图暂不可读也能继续审核或核对保存结果。
        if (draft.state.candidate) setRestoredScope(draftKey);
        confirmCommandRef.current = draft.command;
        previewPageVersionsRef.current = draft.pageVersions;
        generationVersion.current = draft.generationVersion;
        setCandidateFieldErrors(draft.fieldErrors);
        setGenerationFieldErrors(draft.generationFieldErrors ?? {});
        setSelectedCandidateRef(draft.state.candidate?.locations[0]?.candidate_ref ?? "");
        dispatchCandidate({ type: "restore", state: {
          ...draft.state,
          status: ["generating", "confirming"].includes(draft.state.status) ? "error" : draft.state.status,
          error: draft.state.error ?? (draft.state.status === "generating" ? t("errors.interrupted") : draft.command ? t("errors.retryConfirmation") : null),
        } });
      } catch (failure) {
        if (sessionRef.current === session) {
          setDraftReadError(true);
          setStorageError(`${t("errors.draftLoadFailed")} ${failure instanceof Error ? failure.message : ""}`);
        }
      }
    })();
    return () => {
      sessionRef.current = null;
      generationAbortRef.current?.abort(); confirmationAbortRef.current?.abort();
    };
  }, [draftKey, draftReadAttempt, novelId, volume.volume_id, cleanupCompleted, discardFlow, loadFormalFacts, t]);

  useEffect(() => {
    if (flowLoading || !setup.current) return;
    const draft = setup.current;
    const session = sessionRef.current;
    if (draft.flow_ref && (taskFlow.definition?.id !== draft.flow_ref.id || taskFlow.definition?.revision !== draft.flow_ref.revision)) {
      if (selectedStoredFlow.current) return;
      selectedStoredFlow.current = true;
      // 不把旧稿套在默认新修订上；选回原修订后再恢复作者输入。
      void selectFlow(draft.flow_ref).then(() => {
        if (sessionRef.current === session) setStorageError(t("errors.restoreFlowFailed"));
      });
      return;
    }
    setup.current = null;
    setInputs(draft.inputs); setParams(draft.params);
    setStorageError(""); setRestoredScope(draftKey);
  }, [flowLoading, taskFlow.definition, selectFlow, setInputs, setParams, draftKey, candidateState, t]);

  useEffect(() => {
    if (restoring || busy || completed) return;
    const session = sessionRef.current;
    const draft: LocationDraft = {
      state: candidateState, generationFieldErrors, flow_ref: setup.current?.flow_ref ?? (taskFlow.definition ? { id: taskFlow.definition.id, revision: taskFlow.definition.revision } : null),
      inputs: setup.current?.inputs ?? taskFlow.inputs, params: setup.current?.params ?? taskFlow.params, command: confirmCommandRef.current,
      fieldErrors: candidateFieldErrors, pageVersions: previewPageVersionsRef.current, generationVersion: generationVersion.current,
    };
    const version = draftVersion.current;
    writes.current = writes.current.then(() => writeWritingDraft(draftKey, version, draft)).catch(() => {
      if (sessionRef.current === session) setStorageError(t("errors.draftFailed"));
    });
  }, [draftKey, restoring, busy, completed, candidateState, candidateFieldErrors, generationFieldErrors, taskFlow.definition, taskFlow.inputs, taskFlow.params, t]);

  useEffect(() => {
    if (!generationAbortRef.current) return;
    generationAbortRef.current.abort();
    generationAbortRef.current = null;
    dispatchCandidate({ type: "discard" });
  }, [volume.version]);

  useEffect(() => {
    const basis = candidateState.basis;
    if (!basis || candidateState.status === "stale" || restoring || factsLoading || factsError || confirmCommandRef.current) return;
    const changedSource = basis.source_refs.some((source) => {
      // 自动资料准备由后端比较内容，卷和小说的统计版本变化不应使候选失效。
      if (basis.content_fingerprint && ["volume", "novel"].includes(source.resource_type)) return false;
      const key = `${source.resource_type}:${source.id}`;
      const previewVersion = previewPageVersionsRef.current[key];
      const currentVersion = currentKnownVersions[key];
      if (previewVersion === undefined || currentVersion === previewVersion) return false;
      return currentVersion === undefined || currentVersion !== source.version;
    });
    const inputSetChanged = ["location", "world_rule"].some((resourceType) => {
      const prefix = `${resourceType}:`;
      const previewKeys = Object.keys(previewPageVersionsRef.current)
        .filter((key) => key.startsWith(prefix))
        .sort();
      const currentKeys = Object.keys(currentKnownVersions)
        .filter((key) => key.startsWith(prefix))
        .sort();
      return JSON.stringify(previewKeys) !== JSON.stringify(currentKeys);
    });
    if (changedSource || inputSetChanged) dispatchCandidate({ type: "mark_stale" });
  }, [candidateState.basis, candidateState.status, currentKnownVersions, restoring, factsLoading, factsError]);

  const discardCandidate = async () => {
    if (retryOnly || confirmationAbortRef.current || restoring || clearing) return;
    const session = sessionRef.current;
    const version = draftVersion.current;
    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    setClearing(true);
    try {
      await taskFlow.discard();
      await writes.current;
      await writeWritingDraft(draftKey, version, null);
    } catch {
      if (sessionRef.current === session) {
        setStorageError(t("errors.draftFailed")); setClearing(false);
        if (candidateState.status === "generating") dispatchCandidate({ type: "generation_failed", requestId: candidateState.requestId, message: t("errors.interrupted") });
      }
      return;
    }
    if (sessionRef.current !== session) return;
    dispatchCandidate({ type: "discard" });
    setSelectedCandidateRef("");
    setMobileDetailOpen(false);
    setCandidateFieldErrors({});
    confirmCommandRef.current = null;
    previewPageVersionsRef.current = {};
    setup.current = null;
    setGenerationFieldErrors({});
    generationVersion.current = null;
    setStorageError(""); setClearing(false);
  };

  const closeGenerationDialog = () => {
    const returnFocus = dialogReturnFocusRef.current;
    setDialogOpen(false);
    requestAnimationFrame(() => returnFocus?.focus());
  };

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (
      disabled
      || restoring
      || clearing
      || confirmCommandRef.current
      || completionDraft
      || factsLoading
      || Boolean(factsError)
      || generationAbortRef.current
      || candidateState.candidate
    ) return;
    const requestId = candidateState.requestId + 1;
    const requestNovelId = novelId;
    const requestVolumeId = volume.volume_id;
    const requestVolumeVersion = retry && generationVersion.current !== null ? generationVersion.current : volume.version;
    generationVersion.current = requestVolumeVersion;
    draftVersion.current = requestVolumeVersion;
    setCompleted(null);
    const formalSnapshot = formalLocations;
    const controller = new AbortController();
    generationAbortRef.current = controller;
    setGenerationFieldErrors({});
    dispatchCandidate({ type: "generate", requestId });
    setDialogOpen(false);

    try {
      const draft: LocationDraft = {
        state: { ...createLocalCandidateState<VolumeLocationsResultV1>(requestId), status: "generating" },
        flow_ref: taskFlow.definition ? { id: taskFlow.definition.id, revision: taskFlow.definition.revision } : null,
        inputs: taskFlow.inputs, params: taskFlow.params, command: null, fieldErrors: {}, pageVersions: {}, generationVersion: requestVolumeVersion,
      };
      await writes.current;
      if (controller.signal.aborted) return;
      await writeWritingDraft(draftKey, requestVolumeVersion, draft);
      if (controller.signal.aborted) return;
      const generated = await taskFlow.run(
        `/api/llm/novels/${novelId}/volumes/${requestVolumeId}/locations/stream`,
        { novel_id: requestNovelId, volume_id: requestVolumeId, volume_expected_version: requestVolumeVersion },
        controller.signal,
        retry,
      );
      if (controller.signal.aborted || generationAbortRef.current !== controller || currentNovelIdRef.current !== requestNovelId || currentVolumeIdRef.current !== requestVolumeId) return;
      const expectedInput = generated.generationInput as VolumeLocationsGenerationInputV1;
      const envelope = parseVolumeLocationsPreviewV1(generated.result, expectedInput, formalSnapshot);
      if (!envelope) throw new Error(t("errors.invalidPreview"));
      dispatchCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      const basisPageVersions = Object.fromEntries(
        envelope.basis.source_refs.flatMap((source) => {
          const key = `${source.resource_type}:${source.id}`;
          const pageVersion = currentKnownVersionsRef.current[key];
          return pageVersion === undefined ? [] : [[key, pageVersion]];
        }),
      );
      previewPageVersionsRef.current = {
        ...Object.fromEntries(
          Object.entries(currentKnownVersionsRef.current).filter(([key]) =>
            key.startsWith("location:") || key.startsWith("world_rule:"),
          ),
        ),
        ...basisPageVersions,
      };
      setSelectedCandidateRef(envelope.candidate.locations[0]?.candidate_ref ?? "");
      setCandidateFieldErrors({});
    } catch (error) {
      if (!controller.signal.aborted && generationAbortRef.current === controller && currentNovelIdRef.current === requestNovelId && currentVolumeIdRef.current === requestVolumeId) {
        if (error instanceof ApiRequestError) setGenerationFieldErrors(Object.fromEntries(
          Object.entries(error.fieldErrors).map(([field, messages]) => [field.replace(/^body\./, "").replace(/^flow_inputs\./, ""), messages]),
        ));
        const message = error instanceof Error ? error.message : t("errors.generate");
        dispatchCandidate({ type: "generation_failed", requestId, message });
      }
    } finally {
      if (generationAbortRef.current === controller) generationAbortRef.current = null;
    }
  };

  const updateCandidate = (nextCandidate: VolumeLocationCandidateV1) => {
    if (!candidateState.candidate || readOnly) return;
    dispatchCandidate({
      type: "edit",
      candidate: {
        locations: candidates.map((candidate) =>
          candidate.candidate_ref === nextCandidate.candidate_ref ? nextCandidate : candidate,
        ),
      },
    });
    setCandidateFieldErrors((current) => ({ ...current, [nextCandidate.candidate_ref]: {} }));
    confirmCommandRef.current = null;
  };

  const removeCandidate = (candidateRef: string) => {
    if (!candidateState.candidate || readOnly) return;
    const currentIndex = candidates.findIndex((candidate) => candidate.candidate_ref === candidateRef);
    const remaining = candidates
      .filter((candidate) => candidate.candidate_ref !== candidateRef)
      .map((candidate) => candidate.parent_location_ref === candidateRef
        ? { ...candidate, parent_location_ref: null }
        : candidate);
    dispatchCandidate({ type: "edit", candidate: { locations: remaining } });
    setCandidateFieldErrors((current) => {
      const next = { ...current };
      delete next[candidateRef];
      return next;
    });
    setSelectedCandidateRef(remaining[Math.min(currentIndex, remaining.length - 1)]?.candidate_ref ?? "");
    if (remaining.length === 0) setMobileDetailOpen(false);
    confirmCommandRef.current = null;
  };

  const confirmCandidates = async () => {
    if (
      !candidateState.candidate
      || !candidateState.basis
      || candidateState.status === "stale"
      || candidateState.status === "confirming"
      || confirmationAbortRef.current
      || restoring || clearing || completed
      || (!retryOnly && (disabled || factsLoading || Boolean(factsError)))
    ) return;
    const errorsByRef = retryOnly ? {} : validateEditableCandidates(candidates, formalLocations, {
      nameRequired: locationT("validation.nameRequired"),
      typeRequired: locationT("validation.typeRequired"),
      descriptionRequired: locationT("validation.descriptionRequired"),
      storyFunctionRequired: t("validation.storyFunctionRequired"),
      duplicateName: t("validation.duplicateName"),
      parentInvalid: t("validation.parentInvalid"),
    });
    const firstInvalid = candidates.find((candidate) => errorsByRef[candidate.candidate_ref]);
    if (firstInvalid) {
      setCandidateFieldErrors(errorsByRef);
      setSelectedCandidateRef(firstInvalid.candidate_ref);
      setMobileDetailOpen(true);
      dispatchCandidate({ type: "confirm_failed", message: t("errors.validation") });
      focusCandidateError(errorsByRef[firstInvalid.candidate_ref]);
      return;
    }

    const request = confirmCommandRef.current ? JSON.parse(confirmCommandRef.current.payload) : {
      candidates,
      basis: candidateState.basis,
      expected_versions: buildCandidateExpectedVersions(
        candidateState.basis as VolumeLocationsBasisV1,
      ),
    };
    if (!confirmCommandRef.current) {
      confirmCommandRef.current = {
        payload: JSON.stringify(request),
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    const command = confirmCommandRef.current;
    const session = sessionRef.current!;
    const version = draftVersion.current;
    const draft: LocationDraft = {
      state: { ...candidateState, status: "confirming" },
      flow_ref: setup.current?.flow_ref ?? (taskFlow.definition ? { id: taskFlow.definition.id, revision: taskFlow.definition.revision } : null),
      inputs: setup.current?.inputs ?? taskFlow.inputs, params: setup.current?.params ?? taskFlow.params, command,
      fieldErrors: candidateFieldErrors, pageVersions: previewPageVersionsRef.current, generationVersion: generationVersion.current,
    };
    dispatchCandidate({ type: "confirm" });
    const controller = new AbortController();
    confirmationAbortRef.current = controller;
    let submitted = false;
    let response: VolumeLocationsConfirmResponseV1;
    try {
      // 先确认原载荷和键已经落盘；丢响应后只重放这一条请求。
      await writes.current;
      await writeWritingDraft(draftKey, version, draft);
      if (sessionRef.current !== session || controller.signal.aborted) return;
      setStorageError("");
      submitted = true;
      const rawResponse = await apiPost<unknown>(
        `/api/locations/novel/${novelId}/bulk-generated`,
        request,
        {
          headers: { "Idempotency-Key": command.key },
          signal: controller.signal,
        },
      );
      const parsed = parseVolumeLocationsConfirmResponseV1(
        rawResponse,
        novelId,
        candidates.map((candidate) => candidate.candidate_ref),
      );
      if (!parsed) throw new Error(t("errors.invalidConfirmation"));
      response = parsed;
    } catch (error) {
      if (sessionRef.current !== session || controller.signal.aborted) return;
      if (!submitted) {
        if (!retryOnly) confirmCommandRef.current = null;
        setStorageError(t("errors.draftFailed"));
      }
      if (error instanceof ApiRequestError && (error.status === 422 || error.code === "LOCATION_NAME_CONFLICT")) {
        confirmCommandRef.current = null;
        const normalized = normalizeConfirmFieldErrors(
          error.fieldErrors,
          candidates,
          t("errors.fieldInvalid"),
        );
        setCandidateFieldErrors(normalized);
        const firstRef = candidates.find((candidate) => normalized[candidate.candidate_ref])?.candidate_ref;
        if (firstRef) {
          setSelectedCandidateRef(firstRef);
          setMobileDetailOpen(true);
          focusCandidateError(normalized[firstRef]);
        } else {
          focusCandidateError({});
        }
      }
      const basisInvalid = error instanceof ApiRequestError && ([403, 404].includes(error.status)
        || ["LOCATION_BASIS_CONFLICT", "LOCATION_BASIS_SOURCE_NOT_FOUND", "LOCATION_REFERENCE_NOT_FOUND", "LOCATION_REFERENCE_CONFLICT", "CANDIDATE_SOURCE_CHANGED", "IDEMPOTENCY_KEY_REUSED"].includes(error.code ?? ""));
      const message = error instanceof Error ? error.message : t("errors.confirm");
      dispatchCandidate({ type: "confirm_failed", message, stale: basisInvalid });
      return;
    } finally {
      if (confirmationAbortRef.current === controller) confirmationAbortRef.current = null;
    }
    // 已收到正式结果，先保留并通知父级；清稿和读取不再进入保存失败分支。
    confirmedCommands.set(command.key, response);
    const savedDraft = { ...draft, completed: response };
    if (sessionRef.current === session) {
      loadAbortRef.current?.abort(); loadAbortRef.current = null;
      setFactsLoading(false);
      setCompletionDraft(savedDraft);
      setCompleted(response); setSavedFacts(true);
      setFormalLocations((current) => [...current.filter((item) => !response.locations.some((saved) => saved.location_id === item.location_id)), ...response.locations]);
      dispatchCandidate({ type: "discard" }); setSelectedCandidateRef(""); setMobileDetailOpen(false); setCandidateFieldErrors({});
      confirmCommandRef.current = null; previewPageVersionsRef.current = {};
      setup.current = null;
      callbacks.current.onConfirmed?.(response);
      callbacks.current.onFormalFactsChanged?.();
      void loadFormalFacts();
    }
    await cleanupCompleted(savedDraft, version, session);
  };

  if (restoring) return <div className="space-y-3" role={draftReadError || storageError ? "alert" : "status"}>
    <p>{storageError || t("draftLoading")}</p>
    {(draftReadError || storageError) && <Button size="sm" variant="outline" onPress={() => setDraftReadAttempt((attempt) => attempt + 1)}>{t("actions.retryDraft")}</Button>}
  </div>;

  if (reviewing) {
    const selectedIndex = selectedCandidate
      ? candidates.findIndex((candidate) => candidate.candidate_ref === selectedCandidate.candidate_ref)
      : -1;
    const contentValue: LocationContentFieldsV1 | null = selectedCandidate ? {
      name: selectedCandidate.name,
      aliases: selectedCandidate.aliases,
      location_type: selectedCandidate.location_type,
      parent_location_id: selectedCandidate.parent_location_id,
      description: selectedCandidate.description,
      environment: selectedCandidate.environment,
      atmosphere: selectedCandidate.atmosphere,
      geography: selectedCandidate.geography,
      rules_and_constraints: selectedCandidate.rules_and_constraints,
      applicable_rule_ids: selectedCandidate.applicable_rule_ids,
      associated_faction_ids: selectedCandidate.associated_faction_ids,
      story_function: selectedCandidate.story_function,
      tags: selectedCandidate.tags,
    } : null;
    const basisSources = candidateState.basis?.source_refs ?? [];
    const basisLocationIds = new Set(basisSources.filter((source) => source.resource_type === "location").map((source) => source.id));
    const basisRuleIds = new Set(basisSources.filter((source) => source.resource_type === "world_rule").map((source) => source.id));
    const basisFactionIds = new Set(basisSources.filter((source) => source.resource_type === "faction").map((source) => source.id));
    const candidateLocations = formalLocations.filter((location) =>
      basisLocationIds.has(location.location_id),
    );
    const candidateRules = rules.filter((rule) => basisRuleIds.has(rule.rule_id));
    const candidateFactions = factions.filter((faction) => basisFactionIds.has(faction.faction_id));

    return (
      <section className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden border-y border-border bg-surface" aria-labelledby="volume-locations-candidate-heading">
        {(toolbarBefore || toolbarAfter) && <div className="workspace-toolbar flex shrink-0 flex-wrap items-end gap-2 border-b border-border pb-3">{toolbarBefore}{toolbarAfter}</div>}
        <header className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 id="volume-locations-candidate-heading" className="text-lg font-semibold text-foreground">{t("preview.title")}</h3>
              <p className="text-xs tabular-nums text-muted">{t("preview.count", { count: candidates.length })}</p>
            </div>
            <span className="self-start rounded-full bg-surface-secondary px-2.5 py-1 text-xs tabular-nums text-muted">
              {t(`status.${candidateState.status}`)}
            </span>
          </div>
          {candidateState.status === "stale" && (
            <div className="mt-4 border-y border-amber-400/60 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="alert">
              {t("errors.conflict")}
            </div>
          )}
          {candidateState.error && (
            <RelationEditorErrorSummary message={candidateState.error} className="mt-4" />
          )}
          {retryOnly && candidateState.status !== "confirming" && <p role="status" className="mt-3 text-sm text-muted">{t("errors.retryConfirmation")}</p>}
          {storageError && <RelationEditorErrorSummary message={storageError} className="mt-3" />}
          {factsError && <div role="alert" className="mt-3 text-sm text-danger"><p>{factsError}</p><Button size="sm" variant="outline" onPress={() => void loadFormalFacts()}>{t("actions.retry")}</Button></div>}
        </header>

        {selectedCandidate && contentValue ? (
          <div className="grid min-h-0 flex-1 overflow-hidden @min-[800px]/master:grid-cols-[minmax(240px,280px)_minmax(480px,1fr)]">
            <aside
              className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} workspace-scrollbar min-h-0 overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:border-b-0 @min-[800px]/master:border-r`}
              tabIndex={0}
              aria-label={t("preview.rosterLabel")}
            >
              <ul className="divide-y divide-border">
                {candidates.map((candidate) => (
                  <li key={candidate.candidate_ref}>
                    <button
                      id={`location-candidate-${candidate.candidate_ref}`}
                      type="button"
                      onClick={() => {
                        setSelectedCandidateRef(candidate.candidate_ref);
                        setMobileDetailOpen(true);
                        requestAnimationFrame(() => {
                          const detail = document.getElementById(`location-candidate-detail-${candidate.candidate_ref}`);
                          if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                            detail.focus();
                          }
                        });
                      }}
                      className={`w-full px-4 py-3 text-left transition-colors ${selectedCandidate.candidate_ref === candidate.candidate_ref ? "bg-accent/10" : "hover:bg-surface-secondary/55"}`}
                    >
                      <span className="block truncate text-sm font-semibold text-foreground">{candidate.name || t("preview.untitled")}</span>
                      <span className="mt-1 block truncate text-xs text-muted">{candidate.location_type || t("preview.uncategorized")}</span>
                      {candidateFieldErrors[candidate.candidate_ref] && Object.keys(candidateFieldErrors[candidate.candidate_ref]).length > 0 && (
                        <span className="mt-2 block text-xs font-medium text-red-600 dark:text-red-300">{t("preview.hasErrors")}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </aside>

            <article
              id={`location-candidate-detail-${selectedCandidate.candidate_ref}`}
              className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30`}
              tabIndex={0}
              aria-label={`${t("preview.detailLabel")} · ${selectedCandidate.name}`}
            >
              <div className="px-5 py-6 sm:px-7">
                <button type="button" className="mb-5 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                  const candidateRef = selectedCandidate.candidate_ref;
                  setMobileDetailOpen(false);
                  requestAnimationFrame(() => document.getElementById(`location-candidate-${candidateRef}`)?.focus());
                }}>
                  ← {t("actions.backToCandidates")}
                </button>
                <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h4 className="text-xl font-semibold text-foreground">{selectedCandidate.name || t("preview.untitled")}</h4>
                  </div>
                  <Button variant="ghost" size="sm" className="text-danger" onPress={() => removeCandidate(selectedCandidate.candidate_ref)} isDisabled={readOnly}>
                    {t("actions.removeCandidate")}
                  </Button>
                </div>
                {candidateFieldErrors[selectedCandidate.candidate_ref] && Object.keys(candidateFieldErrors[selectedCandidate.candidate_ref]).length > 0 && (
                  <RelationEditorErrorSummary
                    message={t("errors.validation")}
                    fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]}
                    className="mt-6"
                  />
                )}
                <div className="pt-7">
                  <LocationFieldsForm
                    value={contentValue}
                    locations={candidateLocations}
                    excludedParentIds={new Set<string>()}
                    rules={candidateRules}
                    factions={candidateFactions}
                    disabled={readOnly}
                    fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]}
                    errorIdPrefix={`volume-location-candidate-${selectedCandidate.candidate_ref}`}
                    candidateParentOptions={candidates.slice(0, selectedIndex).map((candidate) => ({
                      candidate_ref: candidate.candidate_ref,
                      name: candidate.name,
                    }))}
                    parentCandidateRef={selectedCandidate.parent_location_ref}
                    onParentSelectionChange={({ parentLocationId, parentCandidateRef }) => updateCandidate({
                      ...selectedCandidate,
                      parent_location_id: parentLocationId,
                      parent_location_ref: parentCandidateRef,
                    })}
                    onChange={(fields) => updateCandidate({
                      ...selectedCandidate,
                      ...fields,
                      parent_location_ref: selectedCandidate.parent_location_ref,
                    })}
                  />
                </div>
              </div>
            </article>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 place-items-center px-5 py-12 text-center">
            <p className="text-sm font-medium text-foreground">{t("preview.emptyTitle")}</p>
          </div>
        )}

        <footer className="shrink-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
            <Button variant="ghost" size="sm" onPress={() => void discardCandidate()} isDisabled={busy || retryOnly}>
              {t("actions.discard")}
            </Button>
            <Button variant="primary" size="sm" onPress={() => void confirmCandidates()} isDisabled={busy || candidateState.status === "stale" || (!retryOnly && readOnly)}>
              {candidateState.status === "confirming" ? t("actions.confirming") : retryOnly ? t("actions.retrySave") : t("actions.confirm")}
            </Button>
          </div>
        </footer>
      </section>
    );
  }

  return (
    <div className="workspace-scrollbar min-h-0 flex-1 space-y-3 overflow-y-auto">
      <section aria-labelledby="volume-location-ai-heading">
        <h3 id="volume-location-ai-heading" className="sr-only">{t("generate.title")}</h3>
        <div className="workspace-toolbar flex min-w-0 flex-wrap items-end gap-2 border-b border-border pb-3">
          {toolbarBefore}
          {candidateState.status === "generating" ? (
            <Button variant="outline" size="sm" onPress={() => void discardCandidate()} isDisabled={clearing}>{t("actions.cancelGeneration")}</Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onPress={() => {
                dialogReturnFocusRef.current = document.activeElement instanceof HTMLElement
                  ? document.activeElement
                  : null;
                if (completed) { setCompleted(null); generationVersion.current = null; draftVersion.current = volume.version; }
                setDialogOpen(true);
              }}
              isDisabled={disabled || busy || candidateState.status === "error" || factsLoading || Boolean(factsError) || Boolean(completionDraft)}
            >
              {t("actions.open")}
            </Button>
          )}
          {toolbarAfter}
        </div>
        {factsLoading && <div className="mt-3 text-sm text-muted" role="status">{t("existing.loading")}</div>}
        {factsError && <div className="mt-3 border-y border-red-500/40 px-4 py-3 text-sm text-red-800 dark:text-red-200" role="alert">
          {savedFacts && <p>{t("errors.savedReadFailed")}</p>}
          <p>{factsError}</p>
          <Button className="mt-3" variant="outline" size="sm" onPress={() => void loadFormalFacts()}>{t("actions.retry")}</Button>
        </div>}
        {storageError && <div role="alert" className="mt-3 text-sm text-danger"><p>{storageError}</p>
          {completionDraft && <Button size="sm" variant="outline" onPress={() => void cleanupCompleted(completionDraft!, draftVersion.current, sessionRef.current!)}>{t("actions.retryCleanup")}</Button>}
        </div>}
        {candidateState.status === "error" && candidateState.error && (
          <RelationEditorErrorSummary message={candidateState.error} fieldErrors={generationFieldErrors} className="mt-4" />
        )}
      </section>

      {beforeContent}
      {(candidateState.status === "generating" || candidateState.status === "error") && <TaskFlowProgress flow={taskFlow} running={candidateState.status === "generating"} failed={candidateState.status === "error" && candidateState.candidate === null} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={() => void discardCandidate()} label={t("progress.starting")} />}
      {dialogOpen && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && closeGenerationDialog()} variant="blur" isDismissable>
          <Modal.Container size="lg" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">{t("dialog.title")}</Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} />
              </Modal.Header>
              <Modal.Body className="px-5 py-6 sm:px-7"><TaskFlowForm flow={{ ...taskFlow, fieldErrors: { ...taskFlow.fieldErrors, ...generationFieldErrors }, error: candidateState.error ?? taskFlow.error }} fieldChoices={{ selected_existing_location_ids: activeFormalLocations.map((location) => ({ value: location.location_id, label: location.name })) }} /></Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeGenerationDialog}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void generate()} isDisabled={taskFlow.loading || !taskFlow.definition}>{t("actions.generate")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </div>
  );
}
