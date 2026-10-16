"use client";

import { downloadExport } from "@/lib/userExport";

import { Button, Modal } from "@heroui/react";
import { useContext, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import DocumentSection from "@/components/shared/DocumentSection";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { focusRelationEditorError, RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { TaskFlowForm, TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import { apiGet, apiPost, apiPut, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import type { CandidateBasisV1 } from "@/lib/aiCandidate";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import type { FlowRef } from "@/types/taskFlow";
import type { EntityChoices, HierarchyRecord, PartPlanning, PlanningReadiness } from "@/types/hierarchy";
import type { VolumePlanningV1, VolumeReadV2 } from "@/types/volume";
import VolumeFieldsForm from "../volumes/VolumeFieldsForm";
import PlanningFields, { PLANNING_INPUT } from "./PlanningFields";
import { useAssistantResource } from "../assistant/AssistantContext";

type PlotRecord = HierarchyRecord | VolumeReadV2;
interface PlotSource { resource_type: string; id: string; field: string; quote: string; verification: { status: "matched" | "unverified"; source_truncated: boolean | null } }
interface PlotSourceReport { reported: boolean; items: { id: string; message: string; saved_text: PlotSource; old_plan: PlotSource; semantic_check: "not_performed" }[] }
interface PlotSourceDecision { conflict_id: string; confirmed: boolean; note?: string }
interface ConfirmedPlotContent { plot: string; planning?: PartPlanning | VolumePlanningV1 }
interface PlotPreview { candidate: { plot: string; planning: PartPlanning | VolumePlanningV1; coverage_notes: string }; basis: CandidateBasisV1; context?: { planning_editable?: boolean; has_children?: boolean } }
interface PlotDraft {
  text: string; editing: boolean; preview: PlotPreview | null; command: { payload: string; key: string } | null;
  flow_ref: FlowRef | null; inputs: Record<string, unknown>; params: GenerationParamsValue; error?: string;
  error_context?: { status: number; code: string | null; fieldErrors: ApiFieldErrors };
  stale?: boolean; latest?: PlotRecord | null; generation_started?: boolean; target_version?: number; saved?: PlotRecord;
  source_conflict_decisions?: PlotSourceDecision[]; source_conflict_confirmed_content?: ConfirmedPlotContent;
}
const EMPTY_CHOICES: EntityChoices = { character_ids: [], faction_ids: [], location_ids: [], item_ids: [], rule_ids: [] };
const PROTECTED_PLANNING_FIELDS = ["start_state", "end_state", "target_chapter_count", "target_word_count"];
// 本机清稿失败时，同一会话重开仍记住正式响应。
const confirmedCommands = new Map<string, PlotRecord>();
interface PlotSectionProps {
  kind: "volume" | "arc"; record: PlotRecord; focusPlot?: boolean; choices?: EntityChoices; disabled?: boolean;
  onSaved: (record: PlotRecord) => void; onBusyChange?: (busy: boolean) => void; onRunningChange?: (running: boolean) => void;
}

/** 功能：在卷和篇章原位置编辑详细剧情，并审核 AI 剧情与配套规划。Args: props 当前部分、引用选项、锁定与保存回调。Returns: 保留本地草稿和确认请求键的剧情章节。 */
export default function PlotSection(props: PlotSectionProps) {
  // 换小说或节点时隔开整个编辑会话，迟到结果不能改到新节点。
  const id = props.kind === "volume" ? props.record.volume_id : (props.record as HierarchyRecord).arc_id;
  return <PlotEditor key={`${props.record.novel_id}:${props.kind}:${id}`} {...props} />;
}

function PlotEditor({ kind, record, focusPlot = false, choices = EMPTY_CHOICES, disabled = false, onSaved, onBusyChange, onRunningChange }: PlotSectionProps) {
  const active = useContext(RetainedViewActive);
  const t = useTranslations("writing.plot");
  const detailText = useTranslations("writing.novelInfo");
  const flow = useTaskFlow(`generate_${kind}_plot_by_ai`);
  const { loading: flowLoading, select, setInputs, setParams } = flow;
  const id = kind === "volume" ? record.volume_id : (record as HierarchyRecord).arc_id!;
  const key = `${record.novel_id}:${kind}:${id}:plot`;
  const [text, setText] = useState(record.plot ?? "");
  const [editing, setEditing] = useState(false);
  const [plotExpanded, setPlotExpanded] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(true);
  const generationRegion = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<PlotPreview | null>(null);
  const [sourceDecisions, setSourceDecisions] = useState<PlotSourceDecision[]>([]);
  const [confirmedContent, setConfirmedContent] = useState<ConfirmedPlotContent>();
  const candidateInput = useRef<HTMLTextAreaElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [errorContext, setErrorContext] = useState<PlotDraft["error_context"]>();
  const [storageError, setStorageError] = useState("");
  const [draftReadAttempt, setDraftReadAttempt] = useState(0);
  const [draftActive, setDraftActive] = useState(false);
  const [generationStarted, setGenerationStarted] = useState(false);
  const [restoringFlow, setRestoringFlow] = useState(false);
  const [cleanupDraft, setCleanupDraft] = useState<{ value: PlotDraft; version: number } | null>(null);
  const [savedRecord, setSavedRecord] = useState<PlotRecord | null>(null);
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [stale, setStale] = useState(false);
  const [latest, setLatest] = useState<PlotRecord | null>(null);
  const [readinessError, setReadinessError] = useState("");
  const [readinessFieldErrors, setReadinessFieldErrors] = useState<ApiFieldErrors>({});
  const [savedReadFailure, setSavedReadFailure] = useState(false);
  const [readiness, setReadiness] = useState<PlanningReadiness | null>(null);
  const plotGenerationBlocked = readiness?.can_generate_plot === false;
  const planningEditable = preview?.context?.planning_editable !== false && preview?.context?.has_children !== true;
  const sourceReport = (preview?.basis.flow_snapshot?.execution as { plot_source_conflicts_v1?: PlotSourceReport } | undefined)?.plot_source_conflicts_v1;
  const sourcesConfirmed = !sourceReport?.items.length || (Boolean(confirmedContent) && sourceReport.items.every((item) => sourceDecisions.some((decision) => decision.conflict_id === item.id && decision.confirmed)));
  const baseVersion = useRef(record.version);
  const draftVersion = useRef(record.version);
  const command = useRef<PlotDraft["command"]>(null);
  const controller = useRef<AbortController | null>(null);
  const writes = useRef(Promise.resolve());
  const restored = useRef<PlotDraft | null>(null);
  const completed = useRef(false);
  const mounted = useRef(false);
  const pinnedFlow = useRef<FlowRef | null>(null);
  const readinessAbort = useRef<AbortController | null>(null);
  const callbacks = useRef({ onSaved });
  callbacks.current = { onSaved };
  const recordVersion = useRef(record.version);
  recordVersion.current = record.version;
  const hasSaved = useRef(false);
  const uncertain = Boolean(command.current) && !stale;
  const fieldErrors = Object.fromEntries(Object.entries(errorContext?.fieldErrors ?? {}).map(([name, value]) => [name.replace(/^body\./, "").replace(/^candidate\./, ""), value]));
  const plotError = fieldErrors.plot?.join(" ");
  const displayedRecord = savedRecord && savedRecord.version > record.version ? savedRecord : record;
  useAssistantResource(editing ? { resource_type: kind, id, name: record.title, version: baseVersion.current, draft: { text, fields: ["plot"], version: baseVersion.current } } : null);

  useEffect(() => {
    let active = true;
    mounted.current = true;
    setLoaded(false); setStorageError("");
    readWritingDraft<PlotDraft>(key, baseVersion.current).then((draft) => {
      if (!active || !draft) return;
      const saved = draft.value.saved ?? (draft.value.command ? confirmedCommands.get(draft.value.command.key) : undefined);
      if (saved) {
        completed.current = true; hasSaved.current = true; baseVersion.current = saved.version; draftVersion.current = saved.version; setSavedRecord(saved);
        setCleanupDraft({ value: { ...draft.value, saved }, version: draft.base_version });
        setStorageError(t("savedCleanupFailed"));
        if (saved.version > recordVersion.current) callbacks.current.onSaved(saved);
        return;
      }
      setText(draft.value.text); setEditing(draft.value.editing); setPreview(draft.value.preview);
      const restoredPreview = draft.value.preview;
      const reviewedContent = draft.value.source_conflict_confirmed_content;
      const savedContent = restoredPreview ? { plot: restoredPreview.candidate.plot, ...(restoredPreview.context?.planning_editable !== false && restoredPreview.context?.has_children !== true ? { planning: restoredPreview.candidate.planning } : {}) } : undefined;
      const contentMatches = reviewedContent?.plot === savedContent?.plot && JSON.stringify(Object.entries(reviewedContent?.planning ?? {}).sort(([a], [b]) => a.localeCompare(b))) === JSON.stringify(Object.entries(savedContent?.planning ?? {}).sort(([a], [b]) => a.localeCompare(b)));
      // 原勾选只对核对过的内容有效；清除勾选不改已冻结的确认请求。
      setSourceDecisions((draft.value.source_conflict_decisions ?? []).map((decision) => contentMatches ? decision : { ...decision, confirmed: false }));
      setConfirmedContent(contentMatches ? reviewedContent : undefined);
      setError(draft.value.error || (draft.value.generation_started && !draft.value.preview ? t("generateInterrupted") : ""));
      setErrorContext(draft.value.error_context); setStale(draft.value.stale ?? false); setLatest(draft.value.latest ?? null);
      setDraftActive(true); setGenerationStarted(draft.value.generation_started ?? false);
      pinnedFlow.current = draft.value.flow_ref;
      command.current = draft.value.command; baseVersion.current = draft.value.target_version ?? draft.base_version; draftVersion.current = draft.base_version; restored.current = draft.value;
      if (draft.value.flow_ref && !draft.value.preview) setRestoringFlow(true);
    }).then(() => { if (active) setLoaded(true); }).catch(() => { if (active) setStorageError(t("draftLoadFailed")); });
    return () => { active = false; mounted.current = false; controller.current?.abort(); };
  }, [key, t, draftReadAttempt]);
  useEffect(() => {
    if (!loaded || flowLoading || !restored.current) return;
    const draft = restored.current; restored.current = null;
    void (async () => {
      if (draft.flow_ref && !draft.preview) await select(draft.flow_ref);
      if (!mounted.current) return;
      setInputs(draft.inputs); setParams(draft.params); setRestoringFlow(false);
    })();
  }, [loaded, flowLoading, select, setInputs, setParams]);
  useEffect(() => {
    // 未开始生成的参数恢复完成后，作者仍可主动选择其他方案。
    if (!generationStarted && !preview && !restoringFlow && pinnedFlow.current?.id === flow.definition?.id && pinnedFlow.current?.revision === flow.definition?.revision) pinnedFlow.current = null;
  }, [generationStarted, preview, restoringFlow, flow.definition]);
  useEffect(() => {
    if (!loaded || completed.current || !draftActive || restored.current || restoringFlow || saving) return;
    const version = draftVersion.current;
    const draft: PlotDraft = { text, editing, preview, source_conflict_decisions: sourceDecisions, source_conflict_confirmed_content: confirmedContent, command: command.current, flow_ref: pinnedFlow.current ?? (flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null), inputs: flow.inputs, params: flow.params, error, error_context: errorContext, stale, latest, generation_started: generationStarted, target_version: baseVersion.current };
    writes.current = writes.current.then(() => writeWritingDraft(key, version, draft)).catch(() => { if (mounted.current) setStorageError(t("draftFailed")); });
  }, [key, loaded, draftActive, restoringFlow, saving, editing, text, preview, sourceDecisions, confirmedContent, flow.definition, flow.inputs, flow.params, error, errorContext, stale, latest, generationStarted, t]);
  useEffect(() => {
    const abort = new AbortController();
    readinessAbort.current = abort; setReadiness(null);
    apiGet<PlanningReadiness>(`/api/novels/${record.novel_id}/planning-readiness?target_type=${kind}&target_id=${id}`, { signal: abort.signal }).then((value) => {
      if (!abort.signal.aborted) { setReadiness(value); setReadinessError(""); setReadinessFieldErrors({}); setSavedReadFailure(false); }
    }).catch((failure) => {
      if (abort.signal.aborted) return;
      const temporary = !(failure instanceof ApiRequestError) || failure.status >= 500;
      setSavedReadFailure(hasSaved.current && temporary);
      setReadinessError(failure instanceof Error ? failure.message : t("saveFailed"));
      setReadinessFieldErrors(failure instanceof ApiRequestError ? failure.fieldErrors : {});
      if (failure instanceof ApiRequestError && (failure.status === 403 || failure.status === 404)) { hasSaved.current = false; setSavedRecord(null); }
    });
    return () => abort.abort();
  }, [record.novel_id, record.version, kind, id, readinessAttempt, t]);
  useEffect(() => { onRunningChange?.(running); return () => onRunningChange?.(false); }, [running, onRunningChange]);
  useEffect(() => { onBusyChange?.(saving || running || editing); return () => onBusyChange?.(false); }, [saving, running, editing, onBusyChange]);

  /** 功能：只清理已确认的原版本草稿。Args: draft 正式回执与原稿；version 原本地版本。Returns: 清理结束，失败保留回执和重试入口。 */
  const cleanupSaved = async (draft: PlotDraft, version: number) => {
    const cleanup = writes.current.then(async () => {
      await writeWritingDraft(key, version, draft);
      await writeWritingDraft(key, version, null);
      if (draft.command) confirmedCommands.delete(draft.command.key);
    });
    writes.current = cleanup.catch(() => undefined);
    try {
      await cleanup;
      if (mounted.current) { setCleanupDraft(null); setStorageError(""); }
    } catch {
      if (mounted.current) { setCleanupDraft({ value: draft, version }); setStorageError(t("savedCleanupFailed")); }
    }
  };
  /** 功能：先交付正式剧情，再独立清理本地稿。Args: saved 有效正式响应；draft 原草稿；version 原版本。Returns: 无。 */
  const finish = (saved: PlotRecord, draft: PlotDraft, version: number) => {
    const savedDraft = { ...draft, saved };
    if (draft.command) confirmedCommands.set(draft.command.key, saved);
    if (mounted.current) {
      completed.current = true; hasSaved.current = true;
      readinessAbort.current?.abort(); setReadiness(null); setReadinessAttempt((value) => value + 1);
      setSavedRecord(saved); setText(saved.plot ?? ""); setEditing(false); setPreview(null); setDialog(false); setStale(false); command.current = null;
      setSourceDecisions([]); setConfirmedContent(undefined);
      setError(""); setErrorContext(undefined); setGenerationStarted(false); setDraftActive(false); setSaving(false);
      pinnedFlow.current = null; void flow.discard();
      setCleanupDraft({ value: savedDraft, version });
      baseVersion.current = saved.version; draftVersion.current = saved.version;
      try { if (saved.version >= recordVersion.current) callbacks.current.onSaved(saved); } finally { void cleanupSaved(savedDraft, version); }
    } else void cleanupSaved(savedDraft, version);
  };
  const save = async () => {
    if (saving || stale || !loaded) return;
    setSaving(true); setError(""); setErrorContext(undefined);
    const version = baseVersion.current;
    const localVersion = draftVersion.current;
    const draft: PlotDraft = { text, editing, preview, command: null, flow_ref: pinnedFlow.current, inputs: flow.inputs, params: flow.params, target_version: version };
    let saved: PlotRecord;
    try {
      const response = await apiPut<PlotRecord | { data: PlotRecord }>(`/api/${kind}s/${id}`, { plot: text, expected_version: version });
      saved = "data" in response ? response.data : response;
      if (!saved || saved.novel_id !== record.novel_id || saved.volume_id !== record.volume_id || (kind === "arc" && (saved as HierarchyRecord).arc_id !== id) || !Number.isInteger(saved.version) || saved.version <= version || typeof saved.plot !== "string" || typeof saved.title !== "string" || typeof saved.summary !== "string" || !Number.isInteger(saved.order_index) || !Number.isInteger(saved.word_count) || !Object.hasOwn(saved, "planning") || saved.is_deleted !== false) throw new Error(t("invalidResult"));
    } catch (failure) {
      if (!mounted.current) return;
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      setErrorContext(failure instanceof ApiRequestError ? { status: failure.status, code: failure.code, fieldErrors: failure.fieldErrors } : undefined);
      if (failure instanceof ApiRequestError && failure.status === 409) {
        setStale(true); try { const current = await apiGet<PlotRecord>(`/api/${kind}s/${id}`); if (mounted.current) setLatest(current); } catch { /* 原保存错误继续留在当前编辑区。 */ }
      }
      setSaving(false); return;
    }
    finish(saved, draft, localVersion);
  };
  const generate = async (retry: TaskFlowRunMode = false) => {
    if (controller.current || command.current || saving || restoringFlow || flow.loading || !flow.definition || !loaded || !readiness || plotGenerationBlocked || readinessError || (pinnedFlow.current && (pinnedFlow.current.id !== flow.definition.id || pinnedFlow.current.revision !== flow.definition.revision))) return;
    const abort = new AbortController(); controller.current = abort; setRunning(true); setError(""); setErrorContext(undefined); setStale(false); completed.current = false;
    setDraftActive(true); setGenerationStarted(true); setDialog(false); setReviewOpen(true);
    try {
      if (!retry) { await flow.discard(); const current = await apiGet<PlotRecord>(`/api/${kind}s/${id}`, { signal: abort.signal }); baseVersion.current = current.version; }
      if (abort.signal.aborted) return;
      pinnedFlow.current = flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null;
      await writes.current;
      await writeWritingDraft<PlotDraft>(key, draftVersion.current, { text, editing, preview: null, command: null, flow_ref: pinnedFlow.current, inputs: flow.inputs, params: flow.params, generation_started: true, target_version: baseVersion.current });
      if (abort.signal.aborted) return;
      const generated = await flow.run(`/api/llm/novels/${record.novel_id}/${kind}s/${id}/plot/stream`, { expected_version: baseVersion.current }, abort.signal, retry);
      if (abort.signal.aborted) return;
      const result = generated.result as PlotPreview;
      if (!result?.basis || typeof result.candidate?.plot !== "string" || !result.candidate.planning) throw new Error(t("invalidResult"));
      setPreview(result); setSourceDecisions([]); setConfirmedContent(undefined); command.current = null;
    } catch (failure) {
      if (!abort.signal.aborted) {
        setError(failure instanceof Error ? failure.message : t("generateFailed"));
        setErrorContext(failure instanceof ApiRequestError ? { status: failure.status, code: failure.code, fieldErrors: failure.fieldErrors } : undefined);
        if (failure instanceof ApiRequestError && failure.code === "PLOT_PLANNING_INVALID") {
          // 后端已核对剧情与来源，并保留原规划；不从失败步骤自行拼接候选。
          const editable = failure.details.editable_candidate as PlotPreview | undefined;
          if (editable?.basis && typeof editable.candidate?.plot === "string" && editable.candidate.planning) {
            setPreview(editable); setSourceDecisions([]); setConfirmedContent(undefined); command.current = null;
            focusRelationEditorError({}, generationRegion.current);
          }
        }
      }
    }
    finally { if (controller.current === abort) { controller.current = null; setRunning(false); } }
  };
  /** 功能：修改真正会保存的候选后，要求重新核对来源。Args: candidate 当前候选。Returns: 无。 */
  const updateCandidate = (candidate: PlotPreview["candidate"]) => {
    if (!preview || JSON.stringify(candidate) === JSON.stringify(preview.candidate)) return;
    setPreview({ ...preview, candidate });
    setSourceDecisions((decisions) => decisions.map((decision) => ({ ...decision, confirmed: false })));
    setConfirmedContent(undefined);
  };
  const confirm = async () => {
    if (!preview || saving || stale || !loaded || (!command.current && !sourcesConfirmed)) return;
    const previous = command.current;
    const current = previous ?? { payload: JSON.stringify({ candidate: preview.candidate, basis: preview.basis, expected_version: baseVersion.current, ...(sourceReport?.items.length ? { source_conflict_review: { report: sourceReport, decisions: sourceDecisions.filter((decision) => decision.confirmed), confirmed_content: confirmedContent } } : {}) }), key: crypto.randomUUID() };
    const request = JSON.parse(current.payload) as { candidate: PlotPreview["candidate"]; basis: CandidateBasisV1; expected_version: number };
    command.current = current;
    setSaving(true); setError(""); setErrorContext(undefined);
    const version = draftVersion.current;
    const draft: PlotDraft = { text, editing, preview, source_conflict_decisions: sourceDecisions, source_conflict_confirmed_content: confirmedContent, command: current, flow_ref: pinnedFlow.current ?? (flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null), inputs: flow.inputs, params: flow.params, error, error_context: errorContext, generation_started: generationStarted, target_version: baseVersion.current };
    try {
      await writes.current;
      await writeWritingDraft<PlotDraft>(key, version, draft);
      if (!mounted.current) return;
    } catch {
      command.current = previous;
      if (mounted.current) { setError(error); setErrorContext(errorContext); setStorageError(t("draftFailed")); setSaving(false); }
      return;
    }
    let saved: PlotRecord;
    try {
      const response = await apiPost<{ operation: string; ids: string[]; data: PlotRecord[] }>(`/api/${kind}s/${id}/plot/confirm`, request, { headers: { "Idempotency-Key": current.key } });
      saved = response?.data?.[0];
      if (response?.operation !== `generate_${kind}_plot_by_ai` || response.ids?.length !== 1 || response.ids[0] !== id || response.data?.length !== 1 || !saved || saved.novel_id !== record.novel_id || saved.volume_id !== record.volume_id || (kind === "arc" && (saved as HierarchyRecord).arc_id !== id) || !Number.isInteger(saved.version) || saved.version <= request.expected_version || typeof saved.plot !== "string" || typeof saved.title !== "string" || typeof saved.summary !== "string" || !Number.isInteger(saved.order_index) || !Number.isInteger(saved.word_count) || !Object.hasOwn(saved, "planning") || saved.is_deleted !== false) throw new Error(t("invalidResult"));
    } catch (failure) {
      if (!mounted.current) return;
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      setErrorContext(failure instanceof ApiRequestError ? { status: failure.status, code: failure.code, fieldErrors: failure.fieldErrors } : undefined);
      if (failure instanceof ApiRequestError) {
        if (failure.status === 422 || failure.status === 400) command.current = null;
        else if (["PLOT_CANDIDATE_MISMATCH", "PLOT_VERSION_CONFLICT", "PLOT_SOURCE_CHANGED", "PLOT_SOURCE_CONFLICT_REPORT_CHANGED", "PLOT_PARENT_NOT_READY", "AGENT_SCOPE_CHANGED", "AGENT_READS_CHANGED", "WRITING_REFERENCE_UNAVAILABLE"].includes(failure.code ?? "") || failure.status === 403 || failure.status === 404) {
          command.current = null; setStale(true);
          if (failure.status === 403 || failure.status === 404) { readinessAbort.current?.abort(); setReadiness(null); setReadinessError(failure.message); }
        }
      }
      focusRelationEditorError(failure instanceof ApiRequestError ? failure.fieldErrors : {}, generationRegion.current);
      setSaving(false); return;
    }
    finish(saved, draft, version);
  };
  useEffect(() => {
    if (!focusPlot || !active || !loaded) return;
    const frame = requestAnimationFrame(() => {
      const section = document.getElementById(`plot-section-${kind}-${id}`);
      section?.focus({ preventScroll: true }); section?.scrollIntoView?.({ block: "start" });
    });
    return () => cancelAnimationFrame(frame);
  }, [focusPlot, active, loaded, kind, id]);
  const inPage = generationStarted || Boolean(preview);
  const close = () => { setDialog(false); if (inPage) { setReviewOpen(false); requestAnimationFrame(() => document.getElementById(`plot-review-${id}`)?.focus()); } };
  useEffect(() => {
    if (!inPage || !reviewOpen || !active) return;
    const frame = requestAnimationFrame(() => { generationRegion.current?.focus({ preventScroll: true }); generationRegion.current?.scrollIntoView?.({ block: "start" }); });
    return () => cancelAnimationFrame(frame);
  }, [inPage, reviewOpen, active]);
  const generationBody = (dialog || inPage && reviewOpen) ? <>
      {inPage && flow.error && flow.error !== error && <RelationEditorErrorSummary message={flow.error} />}
      {storageError && <RelationEditorErrorSummary message={storageError} />}
      {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} />}{stale && <p role="alert" className="text-amber-700 dark:text-amber-300">{t("stale")}</p>}
      {uncertain && <p role="status" className="border-l-2 border-amber-500 pl-3 text-sm">{t("confirmUncertain")}</p>}
      {!preview && plotGenerationBlocked && <div role="status" className="space-y-1 border-l-2 border-amber-500 pl-3 text-sm">
        {readiness.blockers.map((item) => <p key={item.code}>{item.message}</p>)}
        {kind === "arc" && readiness.missing_fields.filter((item) => item.field.startsWith("volume.")).map((item) => <p key={item.field}>{item.message}</p>)}
      </div>}
      {!preview ? !inPage && <TaskFlowForm flow={flow} disabled={restoringFlow} showError={error !== flow.error} /> : <>
        <label className="grid gap-2 text-sm">{t("title")}<textarea ref={candidateInput} name="plot" aria-label={t("title")} aria-invalid={Boolean(plotError)} aria-describedby={plotError ? `plot-${id}-error` : undefined} value={preview.candidate.plot} disabled={saving || stale || uncertain} maxLength={40000} onChange={(event) => updateCandidate({ ...preview.candidate, plot: event.target.value })} className={`${PLANNING_INPUT} min-h-[45vh] resize-y leading-7`} />{plotError && <span id={`plot-${id}-error`}>{plotError}</span>}</label>
        {Boolean(sourceReport?.items.length) && <section aria-labelledby={`plot-sources-${id}`} className="min-w-0 space-y-3 border-b border-border pb-4">
          <div className="flex flex-wrap items-center gap-2"><h3 id={`plot-sources-${id}`} className="text-sm font-semibold">{t("needsAttention")}</h3>{Boolean(sourceReport?.items.length) && <SectionEditButton id={`plot-candidate-edit-${id}`} label={t("editCandidate")} isDisabled={saving || stale || uncertain} onPress={() => candidateInput.current?.focus()} />}</div>
          {!sourceReport?.reported ? <p className="text-sm text-muted">{t("sourceUnreported")}</p> : !sourceReport.items.length ? <p className="text-sm text-muted">{t("sourceNoneReported")}</p> : <>
            <p className="reading-copy border-l-2 border-amber-500 pl-3">{t(planningEditable ? "sourceReviewRisk" : "sourceReviewRiskPlotOnly")}</p>
            <div className="divide-y divide-border">{sourceReport.items.map((item, index) => {
              const decision = sourceDecisions.find((entry) => entry.conflict_id === item.id);
              return <fieldset key={item.id} className="min-w-0 space-y-3 py-4">
                <legend className="text-sm font-semibold">{t("sourceConflictNumber", { number: index + 1 })}</legend>
                <p className="reading-copy whitespace-pre-wrap">{item.message}</p>
                <dl className="grid min-w-0 gap-4 sm:grid-cols-2">{(["saved_text", "old_plan"] as const).map((side) => {
                  const source = item[side];
                  return <div key={side} className="min-w-0 space-y-2">
                    <dt className="text-xs font-medium text-muted">{t(side === "saved_text" ? "sourceSavedText" : "sourceOldPlan")}</dt>
                    <dd className="min-w-0 space-y-2">
                      <blockquote className="reading-copy whitespace-pre-wrap border-l-2 border-border pl-3">{source.quote || t("sourceMissingQuote")}</blockquote>
                      <details><summary className="min-h-11 cursor-pointer py-2 text-xs text-accent">{t("sourceDetails")}</summary>
                      <p className="break-words text-xs text-muted">{t.has(`sourceTypes.${source.resource_type}`) ? t(`sourceTypes.${source.resource_type}`) : source.resource_type} · {source.id || t("sourceMissingLocation")} · {source.field || t("sourceMissingLocation")}</p>
                      <p className="text-xs font-medium">{t(source.verification.status === "matched" ? "sourceMatched" : "sourceUnverified")}</p>
                      <p className="text-xs text-muted">{t(source.verification.source_truncated === true ? "sourceTruncated" : source.verification.source_truncated === false ? "sourceNotTruncated" : "sourceTruncationUnknown")}</p>
                      </details>
                    </dd>
                  </div>;
                })}</dl>
                <label className="flex min-h-11 items-start gap-3 py-2 text-sm leading-6">
                  <input type="checkbox" name={`source_conflict_review.decisions.${index}.confirmed`} checked={decision?.confirmed ?? false} disabled={saving || stale || uncertain} onChange={(event) => {
                    setSourceDecisions([...sourceDecisions.filter((entry) => entry.conflict_id !== item.id), { conflict_id: item.id, confirmed: event.target.checked, note: decision?.note ?? "" }]);
                    setConfirmedContent(structuredClone({ plot: preview.candidate.plot, ...(planningEditable ? { planning: preview.candidate.planning } : {}) }));
                  }} className="mt-1 size-4 shrink-0 accent-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent" />
                  <span>{t("sourceConfirm")}</span>
                </label>
                <label className="grid gap-2 text-sm">{t("sourceNote")}<textarea name={`source_conflict_review.decisions.${index}.note`} maxLength={500} value={decision?.note ?? ""} disabled={saving || stale || uncertain} onChange={(event) => setSourceDecisions([...sourceDecisions.filter((entry) => entry.conflict_id !== item.id), { conflict_id: item.id, confirmed: decision?.confirmed ?? false, note: event.target.value }])} className={`${PLANNING_INPUT} min-h-24 resize-y leading-6`} /></label>
              </fieldset>;
            })}</div>
            {!sourcesConfirmed && !uncertain && <p role="status" className="text-sm">{t("sourceConfirmationRequired")}</p>}
          </>}
        </section>}
        {!sourceReport?.items.length && <details><summary className="min-h-11 cursor-pointer py-2 text-accent">{t("sourceConflicts")}</summary><p className="text-sm text-muted">{t(sourceReport?.reported ? "sourceNoneReported" : "sourceUnreported")}</p></details>}
        {preview.candidate.coverage_notes && <details><summary className="min-h-11 cursor-pointer py-2 text-accent">{t("analysisDetails")}</summary><p className="reading-copy whitespace-pre-wrap">{preview.candidate.coverage_notes}</p></details>}
        <details><summary className="min-h-11 cursor-pointer py-2 text-accent">{t("planning")}</summary><div className="mb-3 space-y-2"><p role="status" className="text-sm">{t(planningEditable ? "planningProtected" : "planningReadOnly")}</p><Button size="sm" variant="outline" isDisabled={saving || uncertain} onPress={() => { close(); requestAnimationFrame(() => document.getElementById(kind === "volume" ? `volume-edit-${id}-planning` : `planning-${id}-planning-edit`)?.click()); }}>{t("editOriginalPlanning")}</Button></div>{kind === "volume" ? <VolumeFieldsForm value={{ ...(record as VolumeReadV2), planning: preview.candidate.planning as VolumePlanningV1 }} section="planning" fieldErrors={fieldErrors} errorIdPrefix={`plot-${id}`} disabled={saving || stale || uncertain || !planningEditable} readOnlyFields={PROTECTED_PLANNING_FIELDS} onChange={(value) => updateCandidate({ ...preview.candidate, planning: value.planning! })} /> : <PlanningFields kind="arc" value={{ title: record.title, summary: record.summary, planning: preview.candidate.planning as PartPlanning }} choices={choices} section="planning" errors={fieldErrors} disabled={saving || stale || uncertain || !planningEditable} readOnlyFields={PROTECTED_PLANNING_FIELDS} onChange={(value) => updateCandidate({ ...preview.candidate, planning: value.planning as PartPlanning })} />}</details>
      </>}
      {!preview && pinnedFlow.current && !flow.loading && (pinnedFlow.current.id !== flow.definition?.id || pinnedFlow.current.revision !== flow.definition?.revision) && <Button size="sm" variant="outline" onPress={() => void select(pinnedFlow.current!, true)}>{t("readinessRetry")}</Button>}
      <TaskFlowProgress flow={flow} running={running} failed={Boolean(error) && !preview} onRetry={plotGenerationBlocked ? undefined : () => void generate(true)} onContinue={plotGenerationBlocked ? undefined : (additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={() => { void flow.discard(); setGenerationStarted(false); pinnedFlow.current = null; setError(""); setErrorContext(undefined); }} />
  </> : null;
  const generationActions = <>{running && <Button size="sm" variant="outline" onPress={() => { controller.current?.abort(); setGenerationStarted(false); setRunning(false); }}>{t("stopGeneration")}</Button>}{!running && <Button size="sm" variant="ghost" isDisabled={saving} onPress={close}>{t("closeKeep")}</Button>}{preview && <Button size="sm" variant="ghost" isDisabled={saving} onPress={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(preview, null, 2)], { type: "application/json;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `${record.title}-plot.json`; void downloadExport(link); URL.revokeObjectURL(url); }}>{t("export")}</Button>}{preview && <Button size="sm" variant="outline" isDisabled={saving || uncertain} onPress={() => { void flow.discard(); setPreview(null); setSourceDecisions([]); setConfirmedContent(undefined); command.current = null; pinnedFlow.current = null; setGenerationStarted(false); setDialog(true); setStale(false); setError(""); setErrorContext(undefined); }}>{t("regenerate")}</Button>}{(!inPage || preview) && <Button size="sm" variant="primary" isDisabled={running || saving || (preview ? stale || (!uncertain && !sourcesConfirmed) : generationStarted || restoringFlow || flow.loading || !flow.definition || !readiness || plotGenerationBlocked || Boolean(readinessError) || Boolean(pinnedFlow.current && (pinnedFlow.current.id !== flow.definition.id || pinnedFlow.current.revision !== flow.definition.revision)))} onPress={() => void (preview ? confirm() : generate())}>{t(saving ? "saving" : preview ? uncertain ? "retryConfirm" : planningEditable ? "confirm" : "confirmPlotOnly" : "generate")}</Button>}</>;
  return <DocumentSection id={`plot-section-${kind}-${id}`} number={kind === "volume" ? "03" : "04"} title={t("title")} actions={!record.is_deleted && <>
    {editing ? <><SectionActionButton action="cancel" label={t("cancel")} size="sm" variant="ghost" isDisabled={saving} onPress={async () => {
      setSaving(true);
      try { await writes.current; await writeWritingDraft(key, draftVersion.current, null); setEditing(false); setDraftActive(false); setError(""); setErrorContext(undefined); setStale(false); setLatest(null); }
      catch { setStorageError(t("draftFailed")); } finally { setSaving(false); }
    }} /><SectionActionButton action="save" label={t(saving ? "saving" : "save")} size="sm" variant="primary" isDisabled={saving || stale} onPress={() => void save()} /></> : <>
      <SectionEditButton id={`plot-edit-${id}`} isDisabled={disabled || !loaded || inPage || Boolean(cleanupDraft)} onPress={() => { completed.current = false; baseVersion.current = displayedRecord.version; if (!draftActive) draftVersion.current = displayedRecord.version; setText(displayedRecord.plot ?? ""); setEditing(true); setDraftActive(true); setGenerationStarted(false); void flow.discard(); setError(""); setErrorContext(undefined); setStale(false); }} label={t("edit")} />
    </>}
  </>} secondaryActions={!record.is_deleted && !editing && <Button id={`plot-review-${id}`} size="sm" variant="primary" className="w-full" isDisabled={!loaded || Boolean(cleanupDraft) || (!inPage && (disabled || !readiness || plotGenerationBlocked || Boolean(readinessError)))} onPress={() => { completed.current = false; if (!draftActive) { baseVersion.current = displayedRecord.version; draftVersion.current = displayedRecord.version; } setDraftActive(true); if (inPage) { setReviewOpen(true); requestAnimationFrame(() => { generationRegion.current?.focus(); generationRegion.current?.scrollIntoView?.({ block: "start" }); }); } else setDialog(true); }}>{t(preview ? "review" : inPage ? "viewGeneration" : "generate")}</Button>}>
    {readiness?.plot_status === "stale" && <p role="status" className="border-l-2 border-amber-500 pl-3 text-sm">{t("needsReview")}</p>}
    {readinessError && <>{savedReadFailure && <p role="status" className="border-l-2 border-amber-500 pl-3 text-sm">{t("savedReadFailed")}</p>}<RelationEditorErrorSummary message={readinessError} fieldErrors={readinessFieldErrors} /><Button size="sm" variant="outline" onPress={() => setReadinessAttempt((value) => value + 1)}>{t("readinessRetry")}</Button></>}
    {!dialog && !(inPage && reviewOpen) && storageError && <><RelationEditorErrorSummary message={storageError} />{!loaded && <Button size="sm" variant="outline" onPress={() => setDraftReadAttempt((value) => value + 1)}>{t("readinessRetry")}</Button>}{cleanupDraft && <Button size="sm" variant="outline" onPress={() => void cleanupSaved(cleanupDraft.value, cleanupDraft.version)}>{t("retryCleanup")}</Button>}</>}
    {!dialog && !(inPage && reviewOpen) && error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} />}
    {editing ? <label className="grid gap-2 text-sm">{t("title")}<textarea autoFocus name="plot" aria-label={t("title")} aria-invalid={Boolean(plotError)} aria-describedby={plotError ? `plot-${id}-error` : undefined} value={text} maxLength={40000} disabled={saving} onChange={(event) => setText(event.target.value)} className={`${PLANNING_INPUT} min-h-72 resize-y leading-7`} />{plotError && <span id={`plot-${id}-error`}>{plotError}</span>}</label> : <div className="min-w-0">
      <p id={`plot-${kind}-${id}-readout`} className={`reading-copy whitespace-pre-wrap ${!plotExpanded && (displayedRecord.plot?.length ?? 0) > 200 ? "line-clamp-3" : ""}`}>{displayedRecord.plot || t("empty")}</p>
      {(displayedRecord.plot?.length ?? 0) > 200 && <Button size="sm" variant="ghost" aria-expanded={plotExpanded} aria-controls={`plot-${kind}-${id}-readout`} onPress={() => setPlotExpanded((value) => !value)}>{detailText(plotExpanded ? "collapse" : "expand")}</Button>}
    </div>}
    {editing && stale && latest && <div className="space-y-3"><details><summary className="min-h-11 cursor-pointer py-2 text-accent">{t("latest")}</summary><p className="reading-copy whitespace-pre-wrap">{latest.plot}</p></details><Button size="sm" variant="outline" onPress={async () => {
      setSaving(true);
      try { await writes.current; baseVersion.current = latest.version; setStale(false); }
      catch { setStorageError(t("draftFailed")); } finally { setSaving(false); }
    }}>{t("useLatest")}</Button></div>}
    {inPage && reviewOpen && <section ref={generationRegion} tabIndex={-1} aria-label={t("generationWorkspace")} className="min-w-0 space-y-4 border-t border-border pt-4 outline-none">
      <h4 className="text-base font-semibold [overflow-wrap:anywhere]">{t("generate")} · {record.title}</h4>
      {generationBody}
      <footer className="flex flex-wrap justify-end gap-2 border-t border-border py-4">{generationActions}</footer>
    </section>}
    {dialog && !inPage && <RetainedModalBackdrop isOpen onOpenChange={(open) => !open && close()}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-5xl"><Modal.Header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-7"><Modal.Heading>{t("generate")} · {record.title}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} /></Modal.Header><Modal.Body className="workspace-scrollbar min-h-0 space-y-4 px-5 py-5 sm:px-7">{generationBody}</Modal.Body><Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">{generationActions}</Modal.Footer></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
  </DocumentSection>;
}
