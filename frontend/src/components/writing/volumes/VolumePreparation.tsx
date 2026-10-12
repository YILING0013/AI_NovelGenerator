"use client";
import { Button } from "@heroui/react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { TooltipHint } from "@/components/shared/TooltipHint";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import type { PlanningReadiness } from "@/types/hierarchy";
import type { VolumeReadV2 } from "@/types/volume";
import type { LocationReadV1 } from "@/types/location";
import LocationCandidateWorkspace from "../locations/LocationCandidateWorkspace";
import { useAssistantResource } from "../assistant/AssistantContext";

const STAGES = ["factions", "characters", "locations"] as const;
type Stage = typeof STAGES[number];
type ConfirmCommand = { expected_version: number; location_ids?: string[]; key: string };
type PreparationDraft = {
  expected_version: number;
  location_ids?: string[];
  command: ConfirmCommand | null;
  error: { message: string; status?: number; code?: string | null; fieldErrors?: ApiFieldErrors } | null;
  stale?: boolean;
  completed?: VolumeReadV2;
};

// 成功标记也写不进本机时，同一会话重开仍先认已经收到的正式响应。
const confirmedCommands = new Map<string, VolumeReadV2>();

interface PreparationTools {
  confirmAction: ReactNode;
  canGenerate: boolean;
  error: ReactNode;
  missingStage: "overview" | Stage | null;
  blockedReason: string | null;
}

/**
 * 读取当前卷的准备结果，把确认操作放进对应页工具栏。
 * Args: props 当前卷、资料类别、工具栏内容和保存回调。
 * Returns: 卷内状态工作台，或地点选择与生成区域。
 */
export default function VolumePreparation({ volume, stage, refreshKey = 0, disabled, toolbarBefore, children, onBusyChange, beforeConfirm, onSaved, onGoToStage }: {
  volume: VolumeReadV2;
  stage: Stage;
  refreshKey?: number;
  disabled?: boolean;
  toolbarBefore?: ReactNode;
  children?: (tools: PreparationTools) => ReactNode;
  onBusyChange?: (busy: boolean) => void;
  beforeConfirm?: () => Promise<void>;
  onSaved: (volume: VolumeReadV2) => void;
  onGoToStage?: (stage: "overview" | Stage) => void;
}) {
  const t = useTranslations("writing.preparation");
  const tCandidates = useTranslations("writing.volumeEntitiesAi");
  const [readiness, setReadiness] = useState<PlanningReadiness | null>(null);
  const [error, setError] = useState("");
  const [readStatus, setReadStatus] = useState<"loading" | "ready" | "error">("loading");
  const [retryRead, setRetryRead] = useState(0);
  const [busy, setBusy] = useState<Stage | null>(null);
  const [candidateBusy, setCandidateBusy] = useState(false);
  const [locations, setLocations] = useState<LocationReadV1[]>([]);
  const draftKey = `${volume.novel_id}:volume:${volume.volume_id}:preparation:${stage}`;
  const [draft, setDraft] = useState<PreparationDraft | null>(null);
  const [restoredScope, setRestoredScope] = useState("");
  const [draftReadError, setDraftReadError] = useState(false);
  const [retryDraftRead, setRetryDraftRead] = useState(0);
  const [storageError, setStorageError] = useState("");
  const [cleaning, setCleaning] = useState(false);
  const writes = useRef<Promise<void>>(Promise.resolve());
  const sessionRef = useRef<object>({});
  const confirmationRequest = useRef<AbortController | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const currentVolume = useRef(volume);
  useEffect(() => { currentVolume.current = volume; }, [volume]);
  const locationDraft = stage === "locations" && draft && !draft.completed ? draft : null;
  const restoring = restoredScope !== draftKey;
  const uncertain = Boolean(draft?.command && !draft.completed);
  const [savedReadError, setSavedReadError] = useState(false);
  const [readError, setReadError] = useState<PreparationDraft["error"]>(null);
  const [readUnavailable, setReadUnavailable] = useState(false);
  const savedVersion = useRef(0);
  const pendingSavedRead = useRef<"saved" | "unavailable" | null>(null);
  const readRequest = useRef<AbortController | null>(null);
  const locationRequest = useRef<AbortController | null>(null);
  const syncedRead = useRef<{ version: number; refreshKey: number; retryRead: number } | null>(null);
  const onSavedRef = useRef(onSaved);
  useEffect(() => { onSavedRef.current = onSaved; }, [onSaved]);
  useAssistantResource(stage === "locations" && locationDraft ? { resource_type: "volume", id: volume.volume_id, name: volume.title, version: locationDraft.expected_version, draft: { text: JSON.stringify({ location_ids: locationDraft.location_ids }), fields: ["location_ids"], version: locationDraft.expected_version } } : null);
  // 没有手动修改时直接跟随正式列表；首次勾选后保留当时版本，刷新不能替换保存基准。
  const locationIds = locationDraft?.location_ids ?? volume.location_ids ?? [];
  /** 功能：按原版本排队存稿。Args: value 当前原稿或清除；version 原版本。Returns: 本次存储完成，失败交给当前操作显示。 */
  const persistDraft = useCallback((value: PreparationDraft | null, version: number) => {
    const write = writes.current.then(() => writeWritingDraft(draftKey, version, value));
    writes.current = write.catch(() => undefined);
    return write;
  }, [draftKey]);

  /** 功能：保存成功标记后清理同一版本的稿件。Args: saved 已成功原稿；session 当前页面会话。Returns: 清理结束，不改变业务成功状态。 */
  const cleanupCompleted = useCallback(async (saved: PreparationDraft, session: object) => {
    if (sessionRef.current === session) setCleaning(true);
    try {
      await persistDraft(saved, saved.expected_version);
      await persistDraft(null, saved.expected_version);
      if (saved.command) confirmedCommands.delete(saved.command.key);
      if (sessionRef.current === session) { setDraft(null); setStorageError(""); }
    } catch {
      if (sessionRef.current === session) setStorageError(t("savedDraftCleanupFailed"));
    } finally {
      if (sessionRef.current === session) setCleaning(false);
    }
  }, [persistDraft, t]);

  useEffect(() => {
    const session = {};
    sessionRef.current = session;
    pendingSavedRead.current = null;
    syncedRead.current = null;
    savedVersion.current = 0;
    setReadUnavailable(false);
    confirmationRequest.current?.abort();
    confirmationRequest.current = null;
    setSavedReadError(false);
    setReadError(null);
    setDraft(null);
    setRestoredScope(""); setDraftReadError(false); setStorageError(""); setCleaning(false); setBusy(null);
    setLocations([]);
    setError("");
    void (async () => {
      try {
        await writes.current;
        const stored = await readWritingDraft<PreparationDraft | ConfirmCommand>(draftKey);
        if (sessionRef.current !== session) return;
        if (stored) {
          const value = stored.value;
          // 旧版已经发出的确认命令也只能用原请求核对。
          const restored: PreparationDraft = "key" in value ? { ...value, command: value, error: null } : value;
          const completed = restored.completed ?? (restored.command ? confirmedCommands.get(restored.command.key) : undefined);
          if (completed) {
            savedVersion.current = completed.version;
            const saved = { ...restored, completed };
            setDraft(saved);
            readRequest.current?.abort();
            pendingSavedRead.current = "saved";
            setReadiness(null); setReadStatus("loading"); setRetryRead((value) => value + 1);
            if (completed.version >= currentVolume.current.version) onSavedRef.current(completed);
            void cleanupCompleted(saved, session);
          } else setDraft(restored);
        }
        setRestoredScope(draftKey);
      } catch {
        if (sessionRef.current === session) { setDraftReadError(true); setStorageError(t("draftReadFailed")); }
      }
    })();
    return () => { sessionRef.current = {}; confirmationRequest.current?.abort(); locationRequest.current?.abort(); };
  }, [draftKey, retryDraftRead, cleanupCompleted, t]);
  useEffect(() => {
    if (volume.is_deleted) return;
    // 刚读回的卷同步给父组件时，不再发一轮相同读取。
    const synced = syncedRead.current;
    syncedRead.current = null;
    if (synced?.version === volume.version && synced.refreshKey === refreshKey && synced.retryRead === retryRead) return;
    const abort = new AbortController();
    readRequest.current = abort;
    setReadStatus("loading");
    const read = async () => {
      try {
        const readinessPath = `/api/novels/${volume.novel_id}/planning-readiness?target_type=volume&target_id=${volume.volume_id}`;
        let current: VolumeReadV2 | undefined;
        let value: PlanningReadiness;
        if (pendingSavedRead.current) {
          const results = await Promise.allSettled([
            apiGet<VolumeReadV2>(`/api/volumes/${volume.volume_id}`, { signal: abort.signal }),
            apiGet<PlanningReadiness>(readinessPath, { signal: abort.signal }),
          ]);
          if (abort.signal.aborted) return;
          // 权限或对象失效优先，不能被同批的网络故障掩盖。
          const unavailable = results.find((result) => result.status === "rejected" && result.reason instanceof ApiRequestError && [403, 404].includes(result.reason.status));
          if (unavailable?.status === "rejected") throw unavailable.reason;
          if (results[0].status === "rejected") throw results[0].reason;
          if (results[1].status === "rejected") throw results[1].reason;
          current = results[0].value;
          value = results[1].value;
          if (current.novel_id !== volume.novel_id || current.volume_id !== volume.volume_id || current.is_deleted) {
            throw new ApiRequestError({ status: 404, message: t("loadFailed") });
          }
          if (current.version < Math.max(currentVolume.current.version, savedVersion.current)) throw new Error(t("loadFailed"));
        } else {
          value = await apiGet<PlanningReadiness>(readinessPath, { signal: abort.signal });
        }
        if (abort.signal.aborted) return;
        setReadiness(value);
        setReadStatus("ready");
        setSavedReadError(false);
        setReadError(null);
        setReadUnavailable(false);
        pendingSavedRead.current = null;
        if (current) {
          if (current.version !== volume.version) syncedRead.current = { version: current.version, refreshKey, retryRead };
          onSavedRef.current(current);
        }
      } catch (failure) {
        if (abort.signal.aborted) return;
        const unavailable = failure instanceof ApiRequestError && [403, 404].includes(failure.status);
        if (unavailable) {
          if (pendingSavedRead.current) pendingSavedRead.current = "unavailable";
          locationRequest.current?.abort();
          setLocations([]);
        }
        if (unavailable) setReadUnavailable(true);
        setReadError({ message: failure instanceof Error ? failure.message : t("loadFailed"), ...(failure instanceof ApiRequestError ? { status: failure.status, code: failure.code, fieldErrors: failure.fieldErrors } : {}) });
        setSavedReadError(pendingSavedRead.current === "saved");
        setReadiness(null);
        setReadStatus("error");
      }
    };
    void read();
    return () => abort.abort();
  }, [volume.novel_id, volume.volume_id, volume.version, volume.is_deleted, stage, refreshKey, retryRead, t]);
  const confirmCurrent = async () => {
    if (busy || cleaning || confirmationRequest.current || restoring || draft?.completed || draft?.stale || readUnavailable) return;
    const session = sessionRef.current;
    const abort = new AbortController();
    confirmationRequest.current = abort;
    setBusy(stage); setError("");
    if (beforeConfirm) {
      // 先保留当前人物稿，失败时不登记或更换准备确认请求。
      try { await beforeConfirm(); }
      catch (failure) {
        if (sessionRef.current === session) {
          setError(failure instanceof Error ? failure.message : String(failure));
          confirmationRequest.current = null; setBusy(null);
        }
        return;
      }
      if (sessionRef.current !== session) return;
    }
    const expectedVersion = draft?.expected_version ?? volume.version;
    const command = draft?.command ?? { expected_version: expectedVersion, ...(stage === "locations" ? { location_ids: locationIds } : {}), key: crypto.randomUUID() };
    const original: PreparationDraft = { expected_version: command.expected_version, ...(stage === "locations" ? { location_ids: command.location_ids } : {}), command, error: draft?.error ?? null };
    let submitted = false;
    let current: VolumeReadV2;
    try {
      await persistDraft(original, command.expected_version);
      if (sessionRef.current !== session) return;
      setDraft(original); setStorageError("");
      // 确认开始就取消旧读取，避免旧准备状态在提交之后重新放行。
      readRequest.current?.abort();
      const { key, ...payload } = command;
      submitted = true;
      current = await apiPost<VolumeReadV2>(`/api/novels/${volume.novel_id}/volumes/${volume.volume_id}/preparation/${stage}/confirm`, payload, { headers: { "Idempotency-Key": key }, signal: abort.signal });
      if (sessionRef.current !== session) return;
      if (!current || current.novel_id !== volume.novel_id || current.volume_id !== volume.volume_id
        || current._id !== current.volume_id
        || !Number.isInteger(current.version) || current.version <= command.expected_version || current.is_deleted !== false
        || (["title", "subtitle", "summary", "goal", "theme", "status", "created_at", "updated_at"] as const).some((field) => typeof current[field] !== "string")
        || !Number.isInteger(current.order_index) || !Number.isInteger(current.arcs_count) || !Number.isInteger(current.word_count)
        || !(current.planning === null || (typeof current.planning === "object" && current.planning !== null)) || current.deleted_at !== null
        || typeof current.preparation?.[stage] !== "string" || !current.preparation[stage]?.trim()
        || (stage === "locations" && (!Array.isArray(current.location_ids) || current.location_ids.some((id) => typeof id !== "string")))) {
        throw new Error(t("invalidConfirmation"));
      }
    } catch (failure) {
      if (sessionRef.current !== session) return;
      if (!submitted) {
        setStorageError(t("draftFailed"));
      } else {
        const apiError = failure instanceof ApiRequestError ? failure : null;
        const stale = apiError?.status === 409 && ["VOLUME_VERSION_CONFLICT", "VOLUME_PREPARATION_CHANGED", "VOLUME_PREPARATION_REQUIRED", "VOLUME_PLOT_REQUIRED"].includes(apiError.code ?? "");
        const editable = apiError?.status === 422 || apiError?.code === "VOLUME_LOCATION_UNAVAILABLE";
        const failed: PreparationDraft = {
          ...original, command: stale || editable ? null : command, stale,
          error: { message: failure instanceof Error ? failure.message : t("saveFailed"), ...(apiError ? { status: apiError.status, code: apiError.code, fieldErrors: apiError.fieldErrors } : {}) },
        };
        setDraft(failed);
        try { await persistDraft(failed, command.expected_version); }
        catch { if (sessionRef.current === session) setStorageError(t("draftFailed")); }
        if (sessionRef.current !== session) return;
        if (apiError && [403, 404].includes(apiError.status)) {
          readRequest.current?.abort();
          pendingSavedRead.current = "unavailable";
          setReadUnavailable(true); setReadiness(null); setReadStatus("error");
          locationRequest.current?.abort(); setLocations([]);
        } else if (stale) {
          pendingSavedRead.current = "unavailable";
          setReadiness(null); setReadStatus("loading"); setRetryRead((value) => value + 1);
        } else if (editable) {
          // 原请求核对可能取消了正在进行的读取；确定拒绝后要恢复读取，才能继续改选。
          setReadStatus("loading"); setRetryRead((value) => value + 1);
        }
        requestAnimationFrame(() => {
          if (sessionRef.current === session) sectionRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]")?.focus();
        });
      }
      return;
    } finally {
      if (sessionRef.current === session) { confirmationRequest.current = null; setBusy(null); }
    }
    // 收到完整正式响应即保存成功，后续本地清稿和 GET 各自报告失败。
    readRequest.current?.abort();
    confirmedCommands.set(command.key, current);
    savedVersion.current = current.version;
    const saved = { ...original, error: null, completed: current };
    setDraft(saved);
    pendingSavedRead.current = "saved";
    setReadiness(null); setReadStatus("loading"); setSavedReadError(false);
    setRetryRead((value) => value + 1);
    try { if (current.version >= currentVolume.current.version) onSavedRef.current(current); }
    finally { void cleanupCompleted(saved, session); }
  };
  useEffect(() => {
    onBusyChange?.(Boolean(busy));
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  const index = STAGES.indexOf(stage);
  const missing = readStatus === "ready" && readiness ? [
    ...(readiness.plot_status === "ready" ? [] : [t("plot")]),
    ...STAGES.slice(0, index).filter((prior) => !readiness.preparation?.[prior]).map((prior) => t(prior)),
  ] : [];
  const missingStage = readStatus === "ready" && readiness
    ? readiness.plot_status !== "ready" ? "overview" : STAGES.slice(0, index).find((prior) => !readiness.preparation?.[prior]) ?? null
    : null;
  const blockedReason = missing.length ? t("missingRequirements", { requirements: missing.join(t("separator")) }) : null;
  const available = !volume.is_deleted && !restoring && !cleaning && !uncertain && !draft?.completed && !draft?.stale && readStatus === "ready" && missing.length === 0;
  const changedLocations = stage === "locations" && JSON.stringify([...locationIds].sort()) !== JSON.stringify([...(volume.location_ids ?? [])].sort());
  const ready = readStatus === "ready" && Boolean(readiness?.preparation?.[stage]) && !changedLocations;
  const confirmAction = volume.is_deleted ? null : draftReadError ? (
    <Button size="sm" variant="outline" onPress={() => setRetryDraftRead((value) => value + 1)}>{t("retryDraft")}</Button>
  ) : uncertain && !readUnavailable ? (
    <Button size="sm" variant="outline" isDisabled={Boolean(busy) || candidateBusy || disabled || restoring} onPress={() => void confirmCurrent()}>{t(busy ? "saving" : "retrySave")}</Button>
  ) : readStatus === "error" ? (
    <Button size="sm" variant="outline" onPress={() => setRetryRead((value) => value + 1)}>{t("loadFailedRetry")}</Button>
  ) : (
    <div className="flex items-center gap-1">
      <Button size="sm" variant="outline" isDisabled={restoring || readStatus === "loading" || ready || Boolean(busy) || candidateBusy || disabled || !available} onPress={() => void confirmCurrent()}>
        {t(restoring || readStatus === "loading" ? "loading" : busy === stage ? "saving" : ready ? "ready" : "confirmCurrent")}
      </Button>
      {missing.length > 0 && <TooltipHint text={t("missingRequirements", { requirements: missing.join(t("separator")) })} />}
    </div>
  );
  const errorSummary = <>
    {readError && <RelationEditorErrorSummary message={savedReadError ? tCandidates("savedReadFailed") : readError.message} fieldErrors={{ ...readError.fieldErrors, ...(savedReadError ? { read: [readError.message] } : {}) }} />}
    {draft?.error && <RelationEditorErrorSummary message={draft.error.message} fieldErrors={draft.error.fieldErrors} />}
    {error && <RelationEditorErrorSummary message={error} />}
    {uncertain && <p className="py-2 text-sm text-muted">{t("retryConfirmation")}</p>}
    {draft?.stale && <div className="flex flex-wrap items-center gap-2 py-2">
      <p className="text-sm text-muted">{t("selectionConflict")}</p>
      <Button size="sm" variant="outline" isDisabled={readStatus !== "ready" || Boolean(busy) || cleaning} onPress={async () => {
        const session = sessionRef.current;
        setCleaning(true);
        try {
          await persistDraft(null, draft.expected_version);
          if (sessionRef.current === session) { setDraft(null); setStorageError(""); }
        } catch { if (sessionRef.current === session) setStorageError(t("draftFailed")); }
        finally { if (sessionRef.current === session) setCleaning(false); }
      }}>{t("reviewLatest")}</Button>
    </div>}
    {storageError && <>
      <RelationEditorErrorSummary message={storageError} />
      {!draftReadError && <Button size="sm" variant="outline" isDisabled={Boolean(busy) || cleaning} onPress={async () => {
        const session = sessionRef.current;
        if (draft?.completed) { await cleanupCompleted(draft, session); return; }
        try { await persistDraft(draft, draft?.expected_version ?? volume.version); if (sessionRef.current === session) setStorageError(""); }
        catch { if (sessionRef.current === session) setStorageError(t("draftFailed")); }
      }}>{t(draft?.completed ? "retryCleanup" : "retryDraft")}</Button>}
    </>}
  </>;
  return <section ref={sectionRef} aria-label={t(stage)} className="flex min-h-0 min-w-0 flex-1 flex-col">
    {blockedReason && <div role="status" className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border py-3 text-sm"><p>{blockedReason}</p>{missingStage && onGoToStage && <Button size="sm" variant="primary" onPress={() => onGoToStage(missingStage)}>{t("returnToCurrent")}</Button>}</div>}
    {children ? children({ confirmAction, canGenerate: available, error: errorSummary, missingStage, blockedReason }) : stage === "locations" ? (
      <LocationCandidateWorkspace key={`${volume.novel_id}:${volume.volume_id}`} refreshKey={refreshKey} novelId={volume.novel_id} volume={volume}
        toolbarBefore={toolbarBefore} toolbarAfter={confirmAction}
        disabled={disabled || !available || Boolean(busy)} onBusyChange={setCandidateBusy} onConfirmed={() => {
          readRequest.current?.abort();
          pendingSavedRead.current = "saved";
          setError("");
          setSavedReadError(false);
          setReadStatus("loading");
          setRetryRead((value) => value + 1);
        }}
        beforeContent={<>
          {errorSummary}
          <details onToggle={(event) => {
            if (!event.currentTarget.open) return;
            locationRequest.current?.abort();
            const abort = new AbortController();
            locationRequest.current = abort;
            void apiGet<LocationReadV1[]>(`/api/locations/novel/${volume.novel_id}`, { signal: abort.signal })
              .then((response) => {
                if (!abort.signal.aborted) setLocations(response.filter((location) => !location.is_deleted && location.status === "active"));
              })
              .catch((failure) => {
                if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : t("loadFailed"));
              });
          }}>
            <summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("currentLocations")}</summary>
            <div className="flex flex-wrap gap-x-5">{locations.map((location) => <label key={location.location_id} className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" disabled={!available || Boolean(busy) || candidateBusy || disabled || cleaning} checked={locationIds.includes(location.location_id)} onChange={(event) => {
                const session = sessionRef.current;
                const ids = event.target.checked ? [...locationIds, location.location_id] : locationIds.filter((id) => id !== location.location_id);
                const next: PreparationDraft = { expected_version: draft?.expected_version ?? volume.version, location_ids: ids, command: null, error: draft?.error ?? null };
                setDraft(next);
                void persistDraft(next, next.expected_version).then(() => {
                  if (sessionRef.current === session) setStorageError("");
                }).catch(() => { if (sessionRef.current === session) setStorageError(t("draftFailed")); });
              }} />{location.name}
            </label>)}</div>
            {locationDraft && !draft?.stale && <Button size="sm" variant="ghost" isDisabled={uncertain || Boolean(busy) || candidateBusy || disabled || cleaning} onPress={async () => {
              const session = sessionRef.current;
              setCleaning(true);
              try {
                await persistDraft(null, locationDraft.expected_version);
                if (sessionRef.current === session) { setDraft(null); setError(""); setStorageError(""); }
              } catch { if (sessionRef.current === session) setStorageError(t("draftFailed")); }
              finally { if (sessionRef.current === session) setCleaning(false); }
            }}>{t("cancelSelection")}</Button>}
          </details>
        </>} />
    ) : <><div className="workspace-toolbar flex flex-wrap items-end gap-2 border-b border-border pb-3">{toolbarBefore}{confirmAction}</div>{errorSummary}</>}
  </section>;
}
