"use client";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useContext, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { TaskFlowForm, TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow, type TaskFlowSetup } from "@/hooks/useTaskFlow";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import type { FlowRef } from "@/types/taskFlow";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import { CHILD_KIND, hierarchyChildrenUrl, type EntityChoices, type HierarchyNode, type HierarchyPreview, type HierarchyRecord, type PartPlanning } from "@/types/hierarchy";
import PlanningFields, { PlanningReadout, PLANNING_INPUT } from "./PlanningFields";
import { readChapterPlanConfirmations, writeChapterPlanConfirmation } from "./chapterPlanConfirmations";

const TASKS = { volume: "plan_arcs_by_ai", arc: "plan_scenes_by_ai", scene: "plan_chapters_by_ai", chapter: "write_chapter_by_ai" };
interface ReviewState { candidate_snapshot: string; needs_recheck: boolean; targets_aligned: boolean }
export type GenerationSetup = TaskFlowSetup;
export interface PlanGenerationOrigin { scene: HierarchyNode; arc: HierarchyNode; volume: HierarchyNode }
interface SavedGeneration { records: HierarchyRecord[]; kind: HierarchyNode["kind"]; ids?: string[]; planOrigin?: PlanGenerationOrigin; notified?: boolean }
export interface GenerationDraft { preview: HierarchyPreview | null; flow_ref: FlowRef | null; inputs: Record<string, unknown>; params: GenerationParamsValue; selected_entities: Record<keyof EntityChoices, string[]>; command: { payload: string; key: string } | null; error?: string; field_errors?: ApiFieldErrors; selected?: number; review_state?: ReviewState | null; target_version?: number; stale?: boolean; saved?: SavedGeneration; planOrigin?: PlanGenerationOrigin }
interface GenerationProps {
  node: HierarchyNode; choices: EntityChoices; choicesError?: string; fixedSetup?: GenerationSetup; planOrigin?: PlanGenerationOrigin;
  onSetup?: (setup: GenerationSetup) => Promise<void>;
  onPageChange?: (visible: boolean) => void;
  onSaved: (records: HierarchyRecord[], kind: HierarchyNode["kind"], confirmationKey: string, confirmedIds?: string[], planOrigin?: PlanGenerationOrigin) => void | Promise<void>; onClose: () => void;
}
// 本机存储失败时，重开同一章仍保留已收到的正式响应。
const confirmedCommands = new Map<string, SavedGeneration>();

/** 功能：从当前部分生成候选，审核后交原业务接口保存。Args: props 当前节点、子级及实体选项、完成和关闭回调。Returns: 可取消的生成与审核弹窗。 */
export default function HierarchyGeneration(props: GenerationProps) {
  // 节点身份变更后隔开草稿、缓存和迟到响应。
  return <GenerationEditor key={`${props.node.record.novel_id}:${props.node.kind}:${props.node.id}`} {...props} />;
}

function GenerationEditor({ node, choices, choicesError, fixedSetup, planOrigin, onSetup, onSaved, onClose, onPageChange }: GenerationProps) {
  const t = useTranslations("writing.hierarchy");
  const active = useContext(RetainedViewActive);
  const flow = useTaskFlow(TASKS[node.kind]);
  const { loading: flowLoading, select: selectFlow, setInputs, setParams } = flow;
  const [preview, setPreview] = useState<HierarchyPreview | null>(null);
  const [reviewState, setReviewState] = useState<ReviewState | null>(null);
  const [selected, setSelected] = useState(0);
  const [running, setRunning] = useState(false);
  const [inPage, setInPage] = useState(false);
  const generationRegion = useRef<HTMLElement>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [restored, setRestored] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<ApiFieldErrors>({});
  const [stale, setStale] = useState(false);
  const [latest, setLatest] = useState<HierarchyRecord | null>(null);
  const [savedResult, setSavedResult] = useState<SavedGeneration | null>(null);
  const [draftReadAttempt, setDraftReadAttempt] = useState(0);
  const [draftReadFailed, setDraftReadFailed] = useState(false);
  const [selectedEntities, setSelectedEntities] = useState(() => Object.fromEntries(Object.keys(choices).map((field) => [field, (node.record.planning as PartPlanning)?.[field as keyof EntityChoices] ?? []])) as Record<keyof EntityChoices, string[]>);
  const controller = useRef<AbortController | null>(null);
  const writes = useRef(Promise.resolve());
  const command = useRef<{ payload: string; key: string } | null>(null);
  const planConfirmationKey = useRef<string | null>(null);
  const discardedPlan = useRef(false);
  const version = useRef(node.record.version);
  const draftVersion = useRef(node.record.version);
  const initialVersion = useRef(node.record.version);
  const setup = useRef<GenerationDraft | null>(null);
  const pinnedSetup = useRef(fixedSetup);
  const origin = useRef(planOrigin);
  const appliedSetup = useRef<string | null>(null);
  const mounted = useRef(false);
  const visible = useRef(active);
  visible.current = active;
  const savingRef = useRef(false);
  const completed = useRef<SavedGeneration | null>(null);
  const callbacks = useRef({ onSaved, onClose, onSetup });
  callbacks.current = { onSaved, onClose, onSetup };
  const generationVersion = useRef<number | null>(null);
  const candidateSelect = useRef<HTMLSelectElement | null>(null);
  const key = `${node.record.novel_id}:${node.kind}:${node.id}:generation`;
  const childKind = node.kind === "chapter" ? "chapter" : CHILD_KIND[node.kind];
  const candidateKey = `${childKind}s` as "arcs" | "scenes" | "chapters";
  const candidates = preview?.candidate[candidateKey] ?? [];
  const requiredSetup = fixedSetup ?? pinnedSetup.current;
  const setupMatches = !requiredSetup || (flow.definition?.id === requiredSetup.flow_ref.id && flow.definition?.revision === requiredSetup.flow_ref.revision && JSON.stringify(flow.inputs) === JSON.stringify(requiredSetup.inputs) && JSON.stringify(flow.params) === JSON.stringify(requiredSetup.params));
  const uncertain = Boolean(command.current) && !stale && !savedResult;
  const candidateLocked = saving || uncertain || Boolean(savedResult);
  // 旧信封缺少生成依据时仍保留稿件，但不能反复提交已被明确拒绝的新确认。
  const legacyBasisMissing = Boolean(preview && (
    (errors["basis.flow_ref"] && !preview.basis.flow_ref)
    || (errors["basis.flow_snapshot"] && !preview.basis.flow_snapshot)
  ));

  useEffect(() => {
    let active = true;
    mounted.current = true;
    setLoading(true); setDraftReadFailed(false);
    Promise.all([
      readWritingDraft<GenerationDraft>(key, draftVersion.current),
      node.kind === "scene" ? readChapterPlanConfirmations(key) : Promise.resolve([]),
    ]).then(([shared, confirmations]) => {
      if (!active) return;
      const confirmation = confirmations.find((item) => item.value.preview || item.value.command || item.value.saved)
        ?? (shared?.value.preview || shared?.value.command || shared?.value.saved ? undefined : confirmations[0]);
      const draft = confirmation ?? shared;
      planConfirmationKey.current = confirmation?.key.slice(`${key}:confirmations:`.length) ?? null;
      if (draft) {
        // 旧稿没有原父链时不拿当前父链冒充，也不从标题或目录猜本批章节。
        origin.current = draft.value.planOrigin;
        if (draft.value.preview || draft.value.command || draft.value.saved) setInPage(true);
        setPreview(draft.value.preview); setup.current = draft.value; command.current = draft.value.command; setSelectedEntities(draft.value.selected_entities); draftVersion.current = draft.base_version; version.current = draft.value.target_version ?? draft.base_version;
        const saved = draft.value.saved ?? (draft.value.command ? confirmedCommands.get(draft.value.command.key) : undefined);
        if (saved) { completed.current = saved; setSavedResult(saved); }
        const snapshot = JSON.stringify(draft.value.preview?.candidate);
        const storedReview = draft.value.review_state;
        // 快照只用于防止草稿错连候选，不证明意见或引文正确。
        const aligned = Boolean(storedReview?.targets_aligned && storedReview.candidate_snapshot === snapshot);
        setReviewState(draft.value.preview?.coverage_review ? { candidate_snapshot: snapshot, needs_recheck: !aligned || Boolean(storedReview?.needs_recheck), targets_aligned: aligned } : null);
        setSelected(draft.value.selected ?? 0); setError(draft.value.error ?? ""); setErrors(draft.value.field_errors ?? {});
        setStale(Boolean(draft.value.stale) || (node.kind === "chapter" && version.current !== initialVersion.current && Boolean(draft.value.preview) && !draft.value.command && !saved));
      }
      else if (!pinnedSetup.current) setRestored(true);
    }).catch(() => { if (active) { setError(t("draftFailed")); setDraftReadFailed(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; mounted.current = false; controller.current?.abort(); };
  }, [key, node.kind, t, draftReadAttempt]);

  useEffect(() => {
    if (loading || flowLoading || draftReadFailed) return;
    const stored = setup.current;
    const requested = fixedSetup ?? stored;
    if (!requested || (!stored && appliedSetup.current === JSON.stringify(fixedSetup))) return;
    setup.current = null;
    appliedSetup.current = JSON.stringify(fixedSetup);
    void (async () => {
      if (requested.flow_ref) await selectFlow(requested.flow_ref);
      if (!mounted.current) return;
      setInputs(requested.inputs); setParams(requested.params); setRestored(true);
    })();
  }, [loading, flowLoading, selectFlow, setInputs, setParams, fixedSetup, draftReadFailed]);

  useEffect(() => {
    if (loading || saving || !restored || draftReadFailed || completed.current || (node.kind === "scene" && command.current)) return;
    if (planConfirmationKey.current && discardedPlan.current && !preview) return;
    const localVersion = draftVersion.current;
    const localConfirmationKey = planConfirmationKey.current;
    const draft: GenerationDraft = { preview, review_state: reviewState, flow_ref: requiredSetup?.flow_ref ?? (flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null), inputs: requiredSetup?.inputs ?? flow.inputs, params: requiredSetup?.params ?? flow.params, selected_entities: selectedEntities, command: command.current, target_version: version.current, stale, planOrigin: origin.current, ...(preview ? { error, field_errors: errors, selected } : {}) };
    writes.current = writes.current.then(() => localConfirmationKey
      ? writeChapterPlanConfirmation(key, localVersion, localConfirmationKey, draft)
      : writeWritingDraft(key, localVersion, draft))
      .catch(() => { if (mounted.current) setError(t("draftFailed")); });
  }, [key, node.kind, loading, preview, reviewState, saving, t, restored, flow.definition, flow.inputs, flow.params, selectedEntities, error, errors, selected, requiredSetup, stale, draftReadFailed]);

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (!visible.current || controller.current || savingRef.current || command.current || completed.current || !restored || flowLoading || !flow.definition || !setupMatches) return;
    const abort = new AbortController(); controller.current = abort;
    setRunning(true); setInPage(true); setError(""); setErrors({}); setStale(false);
    const suffix = node.kind === "chapter" ? `chapters/${node.id}/writing` : `${node.kind}s/${node.id}/planning/${childKind}s`;
    try {
      const selectedSetup = requiredSetup ?? flow.resolveSetup();
      // 显式重试和追加整理同样要检查作者新改的正文及列表。
      await callbacks.current.onSetup?.(selectedSetup);
      if (abort.signal.aborted || !visible.current) return;
      if (!retry || generationVersion.current === null) {
        // 作者明确开始新规划时才换父链；重试、旧确认和成功回执继续使用原快照。
        if (!retry && node.kind === "scene") origin.current = planOrigin;
        if (callbacks.current.onSetup) { pinnedSetup.current = selectedSetup; appliedSetup.current = JSON.stringify(selectedSetup); setInputs(selectedSetup.inputs); setParams(selectedSetup.params); }
        generationVersion.current = null; await flow.discard();
      }
      // 新生成使用当前正式版本；旧候选的版本和原请求键只用于重试确认。
      if (generationVersion.current === null) {
        const current = await apiGet<HierarchyRecord>(`/api/${node.kind}s/${node.id}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        if (callbacks.current.onSetup && node.kind === "chapter" && (current.content || current.is_deleted || current.version !== node.record.version || current.chapter_id !== node.id || current.scene_id !== node.record.scene_id || current.arc_id !== node.record.arc_id || current.volume_id !== node.record.volume_id || current.novel_id !== node.record.novel_id || current.order_index !== node.record.order_index)) throw new Error(t("continuation.changed"));
        generationVersion.current = current.version; setLatest(current);
      }
      version.current = generationVersion.current;
      if (node.kind === "scene" && planConfirmationKey.current && discardedPlan.current) {
        // 放弃独立候选后，明确新生成才重新保留这份设置，不回写其他标签页的共享稿。
        await writes.current;
        await writeChapterPlanConfirmation(key, draftVersion.current, planConfirmationKey.current, {
          preview: null, review_state: null, flow_ref: selectedSetup.flow_ref, inputs: selectedSetup.inputs, params: selectedSetup.params,
          selected_entities: selectedEntities, command: null, target_version: version.current, planOrigin: origin.current,
        });
        discardedPlan.current = false;
        if (abort.signal.aborted) return;
      }
      const generated = await flow.run(`/api/llm/novels/${node.record.novel_id}/${suffix}/stream`, {
        novel_id: node.record.novel_id, target_type: node.kind, target_id: node.id,
        ...(node.kind === "chapter" ? { expected_version: version.current } : { mode: "append" }),
      }, abort.signal, retry, fixedSetup ?? pinnedSetup.current);
      if (abort.signal.aborted) return;
      const result = generated.result as HierarchyPreview;
      if (!result?.basis || !result.candidate || (node.kind === "chapter" ? typeof result.candidate.content !== "string" : !Array.isArray(result.candidate[candidateKey]))) throw new Error(t("invalidResult"));
      setPreview(result); setSelected(0); command.current = null;
      setReviewState(result.coverage_review ? { candidate_snapshot: JSON.stringify(result.candidate), needs_recheck: false, targets_aligned: true } : null);
    } catch (failure) {
      if (!abort.signal.aborted) {
        setError(failure instanceof Error ? failure.message : t("generateFailed"));
        if (failure instanceof ApiRequestError) {
          // 缺项随生成错误返回，必须放进当前弹窗，作者才能知道要补什么。
          const missing = failure.code === "WRITING_MATERIAL_MISSING"
            ? failure.details.missing as { field: string; message: string }[] | undefined
            : undefined;
          setErrors({ ...failure.fieldErrors, ...Object.fromEntries(
            (missing ?? []).map((item, index) => [`missing.${index}`, [`${item.field}：${item.message}`]]),
          ) });
          // 只接收后端已核对来源、明确允许人工修改的候选，不从步骤输出拼接依据。
          const editable = failure.details.editable_candidate as HierarchyPreview | undefined;
          if (editable?.basis && editable.candidate && (node.kind === "chapter" ? typeof editable.candidate.content === "string" : Array.isArray(editable.candidate[candidateKey]))) {
            setPreview(editable); command.current = null;
            setReviewState(editable.coverage_review ? { candidate_snapshot: JSON.stringify(editable.candidate), needs_recheck: false, targets_aligned: true } : null);
            const invalidIndex = Object.keys(failure.fieldErrors)[0]?.match(/^candidate\.(?:arcs|scenes|chapters)\.(\d+)\./)?.[1];
            setSelected(invalidIndex === undefined ? 0 : Number(invalidIndex));
            if (visible.current) focusRelationEditorError(failure.fieldErrors, generationRegion.current);
          }
        }
      }
    } finally { if (controller.current === abort) { controller.current = null; setRunning(false); } }
  };

  /** 功能：保留保存成功的回执，再交给原工作台更新进度。Args: draft 原章草稿；saved 正式保存结果。Returns: 通知及该版本清稿完成。 */
  const deliverSaved = async (draft: GenerationDraft, saved: SavedGeneration) => {
    completed.current = saved;
    confirmedCommands.set(draft.command!.key, saved);
    if (mounted.current) setSavedResult(saved);
    await writes.current;
    if (node.kind === "scene") {
      await writeChapterPlanConfirmation(key, draftVersion.current, draft.command!.key, { ...draft, saved });
      planConfirmationKey.current = draft.command!.key;
    }
    else await writeWritingDraft(key, draftVersion.current, { ...draft, saved });
    // 隐藏或已离开的工作台只保留回执，不触发父级跳转或下一章。
    if (!mounted.current || !visible.current) return;
    if (!saved.notified) {
      if (node.kind === "scene" && saved.ids) await callbacks.current.onSaved(saved.records, saved.kind, draft.command!.key, saved.ids, saved.planOrigin);
      else await callbacks.current.onSaved(saved.records, saved.kind, draft.command!.key);
      saved.notified = true;
      if (node.kind === "scene") await writeChapterPlanConfirmation(key, draftVersion.current, draft.command!.key, { ...draft, saved });
      else await writeWritingDraft(key, draftVersion.current, { ...draft, saved });
    }
    if (node.kind === "scene") await writeChapterPlanConfirmation(key, draftVersion.current, draft.command!.key, null);
    else await writeWritingDraft(key, draftVersion.current, null);
    confirmedCommands.delete(draft.command!.key);
    if (mounted.current && visible.current) callbacks.current.onClose();
  };

  const confirm = async () => {
    if (!visible.current || !preview || savingRef.current || stale || !restored || (legacyBasisMissing && !command.current && !savedResult)) return;
    savingRef.current = true;
    setSaving(true); setError(""); setErrors({});
    const previous = command.current;
    // 结果未知时只重放冻结请求；当前候选或正式版本不能改写原载荷。
    const current = previous ?? { payload: JSON.stringify({ candidate: preview.candidate, basis: preview.basis, ...(node.kind === "chapter" ? { expected_version: version.current } : {}) }), key: crypto.randomUUID() };
    command.current = current;
    const request = JSON.parse(current.payload);
    const draft: GenerationDraft = { preview, review_state: reviewState, flow_ref: requiredSetup?.flow_ref ?? (flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null), inputs: requiredSetup?.inputs ?? flow.inputs, params: requiredSetup?.params ?? flow.params, selected_entities: selectedEntities, command: current, selected, target_version: version.current, planOrigin: origin.current };
    try {
      if (completed.current) {
        await deliverSaved(draft, completed.current);
        return;
      }
      try {
        await writes.current;
        // 独立确认恢复不能覆盖另一标签页的新候选；首次提交仍给原稿标明自己的确认键。
        if (node.kind !== "scene" || (!previous && !planConfirmationKey.current)) await writeWritingDraft(key, draftVersion.current, draft);
        if (node.kind === "scene") {
          await writeChapterPlanConfirmation(key, draftVersion.current, current.key, draft, planConfirmationKey.current ?? undefined);
          planConfirmationKey.current = current.key;
        }
      } catch {
        command.current = previous;
        if (mounted.current) setError(t("draftFailed"));
        return;
      }
      if (!mounted.current || !visible.current) { command.current = previous; return; }
      let response: { operation?: string; ids?: string[]; data: HierarchyRecord[] };
      try {
        response = await apiPost<typeof response>(node.kind === "chapter" ? `/api/chapters/${node.id}/content/confirm` : `${hierarchyChildrenUrl(node)}/confirm`, request, { headers: { "Idempotency-Key": current.key } });
        const saved = response.data?.[0];
        if (!Array.isArray(response.data) || (node.kind === "chapter" && (response.data.length !== 1 || saved?.chapter_id !== node.id || saved.novel_id !== node.record.novel_id))) throw new Error(t("invalidResult"));
        // 回执对应原规划父链；旧稿未记录父链时只核对已固定的小说和场景，不建立写作批次。
        const originalScene = origin.current?.scene.record;
        if (node.kind === "scene" && (response.operation !== TASKS.scene || !Array.isArray(response.ids) || response.ids.length !== response.data.length || new Set(response.ids).size !== response.ids.length || response.ids.some((id, index) => {
          const record = response.data[index];
          return typeof id !== "string" || !id || record?.chapter_id !== id || record.scene_id !== node.id || record.novel_id !== node.record.novel_id || (originalScene && (record.arc_id !== originalScene.arc_id || record.volume_id !== originalScene.volume_id));
        }))) throw new Error(t("invalidResult"));
      } catch (failure) {
        if (!mounted.current) return;
        setError(failure instanceof Error ? failure.message : t("saveFailed"));
        if (failure instanceof ApiRequestError) {
          setErrors(failure.fieldErrors);
          const staleFailure = ["WRITING_SOURCE_CHANGED", "WRITING_VERSION_CONFLICT", "WRITING_CANDIDATE_MISMATCH", "WRITING_REFERENCE_UNAVAILABLE", "WRITING_IDEMPOTENCY_CONFLICT", "AGENT_SCOPE_CHANGED", "AGENT_READS_CHANGED"].includes(failure.code ?? "") || failure.status === 403 || failure.status === 404;
          const invalidIndex = Object.keys(failure.fieldErrors)[0]?.match(/^candidate\.(?:arcs|scenes|chapters)\.(\d+)\./)?.[1];
          if (node.kind === "scene" && (failure.status === 400 || failure.status === 422 || staleFailure)) {
            // 先保留可修改的拒绝稿，再解除冻结；本地失败时原请求仍能核对。
            await writeChapterPlanConfirmation(key, draftVersion.current, current.key, {
              ...draft, command: null, error: failure.message, field_errors: failure.fieldErrors, stale: staleFailure,
              selected: invalidIndex === undefined ? selected : Number(invalidIndex),
            });
          }
          if (failure.status === 400 || failure.status === 422) {
            command.current = null;
          }
          else if (staleFailure) {
            command.current = null; setStale(true);
            try { const latest = await apiGet<HierarchyRecord>(`/api/${node.kind}s/${node.id}`); if (mounted.current) setLatest(latest); }
            catch (readFailure) { if (mounted.current) setError(`${failure.message} ${readFailure instanceof Error ? readFailure.message : t("loadFailed")}`); }
          }
          if (invalidIndex !== undefined) setSelected(Number(invalidIndex));
          if (visible.current) focusRelationEditorError(failure.fieldErrors, generationRegion.current);
        }
        return;
      }
      await deliverSaved(draft, { records: response.data, kind: childKind, ...(node.kind === "scene" ? { ids: response.ids, planOrigin: origin.current } : {}) });
    } catch (failure) {
      // 本地失败保留原请求或成功回执，不能另建确认键。
      if (mounted.current) setError(failure instanceof Error ? failure.message : t("draftFailed"));
    } finally { savingRef.current = false; if (mounted.current) setSaving(false); }
  };

  const discardCandidate = async () => {
    if (candidateLocked || savingRef.current) return;
    savingRef.current = true; setSaving(true);
    try {
      await writes.current;
      if (planConfirmationKey.current) {
        await writeChapterPlanConfirmation(key, draftVersion.current, planConfirmationKey.current, null);
        discardedPlan.current = true;
      }
      void flow.discard(); command.current = null; setPreview(null); setReviewState(null); setStale(false); setError(""); setErrors({}); setInPage(false);
    } catch (failure) { setError(failure instanceof Error ? failure.message : t("draftFailed")); }
    finally { savingRef.current = false; if (mounted.current) setSaving(false); }
  };

  useEffect(() => {
    onPageChange?.(inPage && active);
    return () => onPageChange?.(false);
  }, [inPage, active, onPageChange]);
  useEffect(() => {
    if (!inPage || !active) return;
    const frame = requestAnimationFrame(() => generationRegion.current?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [inPage, active]);
  const close = async () => {
    if (savingRef.current || controller.current) return;
    try { await writes.current; callbacks.current.onClose(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : t("draftFailed")); }
  };
  const generationBody = active ? <>
          {inPage && flow.error && flow.error !== error && <RelationEditorErrorSummary message={flow.error} />}
          {error && <RelationEditorErrorSummary message={error} fieldErrors={errors} className="mb-4" />}
          {legacyBasisMissing && <p role="alert" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("legacyCandidateBasisMissing")}</p>}
          {draftReadFailed && <Button size="sm" variant="outline" onPress={() => setDraftReadAttempt((value) => value + 1)}>{t("retryRead")}</Button>}
          {uncertain && <p role="status" className="mb-4 border-l-2 border-amber-500 pl-3 text-sm">{t("confirmUncertain")}</p>}
          {savedResult && <p role="status" className="mb-4 border-l-2 border-amber-500 pl-3 text-sm">{t("savedAwaitingRefresh")}</p>}
          {!preview && restored && !flowLoading && !setupMatches && <p role="alert" className="mb-4 text-sm">{t("fixedSetupUnavailable")}</p>}
          {choicesError && <RelationEditorErrorSummary message={choicesError} className="mb-4" />}
          {stale && <p role="alert" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("candidateStale")}</p>}
          {stale && <details className="mb-5 border-b border-border pb-4"><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t(node.kind === "chapter" ? "latestBody" : "latestPlan")}</summary><h3 className="font-semibold">{(latest ?? node.record).title}</h3>{node.kind === "chapter" ? <pre className="reading-copy whitespace-pre-wrap font-sans">{(latest ?? node.record).content}</pre> : <PlanningReadout record={latest ?? node.record} choices={choices} />}</details>}
          {preview?.coverage_review && <details className="mb-5 min-w-0 border-b border-border pb-4">
            <summary className="min-h-11 cursor-pointer py-2 text-sm text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"><span>{t("coverageReview", { count: preview.coverage_review.issues.length })}</span>{reviewState?.needs_recheck && <span className="ml-2 text-foreground">{t("coverageRecheckStatus")}</span>}</summary>
            {reviewState?.needs_recheck && <p role="status" className="mb-3 border-y border-amber-500/50 py-3 text-sm">{t(reviewState.targets_aligned ? "coverageNeedsRecheck" : "coverageUnlinked")}</p>}
            <p className="reading-copy whitespace-pre-wrap">{preview.coverage_review.summary}</p>
            <p className="mt-2 text-sm text-muted">{t("coverageQuoteLimit")}</p>
            {preview.coverage_review.issues.length > 0 && <ul className="mt-4 divide-y divide-border">
              {preview.coverage_review.issues.map((issue, index) => <li key={index} className="min-w-0 space-y-2 py-3 first:pt-0 last:pb-0">
                <p className="text-xs font-medium text-muted">{t(reviewState?.needs_recheck ? "coverageRecheckStatus" : preview.coverage_review?.schema_version === 1 && issue.verification?.status === "matched" ? "coverageMatched" : "coverageUnverified")}</p>
                <p className="reading-copy whitespace-pre-wrap">{issue.message}</p>
                {(issue.candidate_field !== undefined || issue.candidate_quote !== undefined) && <dl className="grid min-w-0 gap-2">
                  <div className="min-w-0"><dt className="text-xs font-medium text-muted">{t("coverageCandidateField")}</dt><dd className="reading-copy whitespace-pre-wrap">{issue.candidate_field || t("coverageMissing")}</dd></div>
                  <div className="min-w-0"><dt className="text-xs font-medium text-muted">{t("coverageCandidateQuote")} · {t(reviewState?.needs_recheck ? "coverageRecheckStatus" : preview.coverage_review?.schema_version === 1 && issue.verification?.candidate === "matched" ? "coverageMatched" : "coverageUnverified")}</dt><dd className="reading-copy whitespace-pre-wrap">{issue.candidate_quote || t("coverageMissing")}</dd></div>
                </dl>}
                {issue.source && <dl className="grid min-w-0 gap-2">
                  <div className="min-w-0"><dt className="text-xs font-medium text-muted">{t("coverageSource")}</dt><dd className="reading-copy whitespace-pre-wrap">{issue.source.resource_type} / {issue.source.id} / {issue.source.field}</dd></div>
                  <div className="min-w-0"><dt className="text-xs font-medium text-muted">{t("coverageSourceQuote")} · {t(reviewState?.needs_recheck ? "coverageRecheckStatus" : preview.coverage_review?.schema_version === 1 && issue.verification?.source === "matched" ? "coverageMatched" : "coverageUnverified")}</dt><dd className="reading-copy whitespace-pre-wrap">{issue.source.quote || t("coverageMissing")}</dd>{issue.verification?.source_truncated && <dd className="text-sm text-muted">{t("coverageSourceTruncated")}</dd>}</div>
                </dl>}
                {reviewState?.targets_aligned && candidates[issue.candidate_index - 1] ? <Button size="sm" variant="ghost" className="h-auto max-w-full whitespace-normal py-2 text-left text-accent" isDisabled={saving} onPress={() => {
                  setSelected(issue.candidate_index - 1); candidateSelect.current?.focus();
                }}>{t("coverageCandidate", { index: issue.candidate_index, title: candidates[issue.candidate_index - 1].title })}</Button> : <p className="text-xs text-muted">{t("coverageOriginalCandidate", { index: issue.candidate_index })}</p>}
              </li>)}
            </ul>}
          </details>}
          {loading ? <p role="status">{t("loading")}</p> : !preview ? <>
            {!inPage && <TaskFlowForm flow={flow} disabled={Boolean(requiredSetup) || !restored} showError={error !== flow.error} />}
          </> : node.kind === "chapter" ? <label className="grid gap-3 text-sm">{t("bodyCandidate")}<textarea value={preview.candidate.content} disabled={candidateLocked} onChange={(e) => { if (!candidateLocked) setPreview({ ...preview, candidate: { content: e.target.value } }); }} className={`${PLANNING_INPUT} min-h-[50vh] resize-y text-[15px] leading-[1.85]`} /></label> : <>
            <div className="mb-5 flex flex-wrap items-end gap-3 border-b border-border pb-4">
              <label className="grid min-w-0 flex-1 gap-2 text-xs font-medium text-muted">{t("candidates", { count: candidates.length })}<select ref={candidateSelect} className={PLANNING_INPUT} value={selected} disabled={saving} onChange={(e) => setSelected(Number(e.target.value))}>{candidates.map((item, index) => <option key={index} value={index}>{index + 1}. {item.title}</option>)}</select></label>
              <Button size="sm" variant="ghost" isDisabled={candidateLocked || candidates.length < 2} onPress={() => {
                // 检查使用从1开始的候选编号，删除后同步移动，不能指向别的候选。
                const review = preview.coverage_review;
                const candidate = { [candidateKey]: candidates.filter((_, i) => i !== selected) };
                setPreview({ ...preview, candidate, ...(review && reviewState?.targets_aligned ? { coverage_review: {
                  ...review, issues: review.issues.filter((issue) => issue.candidate_index !== selected + 1).map((issue) => ({ ...issue, candidate_index: issue.candidate_index > selected + 1 ? issue.candidate_index - 1 : issue.candidate_index })),
                } } : {}) });
                if (reviewState) setReviewState({ ...reviewState, candidate_snapshot: JSON.stringify(candidate), needs_recheck: true });
                setSelected(Math.max(0, selected - 1));
              }}>{t("removeCandidate")}</Button>
            </div>
            {candidates[selected] && <PlanningFields kind={childKind} value={candidates[selected]} onChange={(value) => {
              const candidate = { [candidateKey]: candidates.map((item, i) => i === selected ? value : item) };
              setPreview({ ...preview, candidate });
              if (reviewState) setReviewState({ ...reviewState, candidate_snapshot: JSON.stringify(candidate), needs_recheck: true });
            }} choices={choices} disabled={candidateLocked} errors={Object.fromEntries(Object.entries(errors).map(([field, messages]) => [field.replace(`candidate.${candidateKey}.${selected}.`, ""), messages]))} />}
          </>}
          {!preview && <TaskFlowProgress flow={flow} running={running} failed={Boolean(error)} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={() => { void flow.discard(); setError(""); setErrors({}); setInPage(false); }} />}
  </> : null;
  const generationActions = <>
          {running ? <Button size="sm" variant="outline" onPress={() => { controller.current?.abort(); void flow.discard(); setInPage(false); }}>{t("cancelGeneration")}</Button> : <Button size="sm" variant="ghost" isDisabled={saving} onPress={() => void close()}>{t("closeKeepDraft")}</Button>}
          {preview && <Button size="sm" variant="ghost" onPress={() => {
            const blob = new Blob([JSON.stringify({ ...preview, ...(reviewState ? { review_state: reviewState } : {}) }, null, 2)], { type: "application/json;charset=utf-8" });
            const url = URL.createObjectURL(blob); const link = document.createElement("a");
            link.href = url; link.download = `${node.record.title}-candidate.json`; link.click(); URL.revokeObjectURL(url);
          }}>{t("exportDraft")}</Button>}
          {preview && <Button size="sm" variant="outline" isDisabled={candidateLocked} onPress={() => void discardCandidate()}>{t("discardCandidate")}</Button>}
          {(!inPage || preview) && <Button size="sm" variant="primary" isDisabled={loading || !restored || running || saving || (preview ? stale || (legacyBasisMissing && !command.current && !savedResult) : flow.loading || !flow.definition || !setupMatches)} onPress={() => void (preview ? confirm() : generate())}>{saving ? t("saving") : savedResult ? t("retrySavedRefresh") : preview ? t("confirmCandidate") : t("generateNow")}</Button>}
  </>;
  if (inPage) return active ? <section ref={generationRegion} tabIndex={-1} aria-label={t("generationWorkspace")} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden outline-none">
    <header className="shrink-0 border-b border-border px-5 py-4 sm:px-7"><h2 className="text-lg font-semibold [overflow-wrap:anywhere]">{t(`generate.${node.kind}`)} · {node.record.title}</h2></header>
    <div className="workspace-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">{generationBody}</div>
    <footer className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-7">{generationActions}</footer>
  </section> : null;
  return <RetainedModalBackdrop isOpen onOpenChange={(open) => !open && void close()}>
    <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-4xl">
      <Modal.Header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-7"><Modal.Heading className="text-lg font-semibold [overflow-wrap:anywhere]">{t(`generate.${node.kind}`)} · {node.record.title}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} /></Modal.Header>
      <Modal.Body className="workspace-scrollbar min-h-0 px-5 py-5 sm:px-7">{generationBody}</Modal.Body>
      <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-7">{generationActions}</Modal.Footer>
    </Modal.Dialog></Modal.Container>
  </RetainedModalBackdrop>;
}
