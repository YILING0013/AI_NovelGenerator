"use client";

import { Button, Modal } from "@heroui/react";
import { useContext, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import { hierarchyNode, type EntityChoices, type HierarchyNode, type HierarchyRecord, type PlanningReadiness, type PlanningDraft } from "@/types/hierarchy";
import HierarchyGeneration, { type GenerationSetup } from "./HierarchyGeneration";
import { readChapterPlanConfirmations } from "./chapterPlanConfirmations";
import { PLANNING_SECTIONS } from "./PlanningFields";

interface ChapterSelection { id: string; title: string; order_index: number; scene_id?: string; scene_order_index?: number; scene_title?: string }
/** 场景章计划正式确认后保留的目标，以及当时核对的父级计划。 */
export interface SavedChapterBatch {
  confirmationKey: string;
  ids: string[];
  scene: HierarchyNode;
  arc: HierarchyNode;
  volume: HierarchyNode;
  records: HierarchyRecord[];
}
interface ContinuationDraft {
  volume_id?: string;
  arc_id?: string;
  selected: ChapterSelection[];
  completed: { id: string; key: string; record: HierarchyRecord; acceptedContent?: string }[];
  setup: GenerationSetup | null;
  started: boolean;
  currentId: string | null;
  currentRecord?: HierarchyRecord;
  needsRead: boolean;
}

/** 功能：按作者选定的场景或篇章内章节逐章审核，保存后等待手动继续。Args: props 固定范围、显示状态、未保存修改与保存回调。Returns: 本地列表和原单章生成弹窗。 */
export default function ChapterContinuation({ scene: selectedScene, arc, scope: selectedScope = "scene", batch, open, dirty, readBlocked = false, readError = "", onRetryRead, choices, choicesError, onClose, onSaved, onGenerationPageChange }: {
  scene: HierarchyNode; open: boolean; dirty: boolean; choices: EntityChoices; choicesError?: string;
  scope?: "scene" | "arc"; arc?: HierarchyNode;
  batch?: SavedChapterBatch;
  readBlocked?: boolean; readError?: string; onRetryRead?: () => void;
  onClose: () => void; onSaved: (record: HierarchyRecord) => void; onGenerationPageChange?: (visible: boolean) => void;
}) {
  const t = useTranslations("writing.hierarchy");
  const active = useContext(RetainedViewActive);
  const scene = batch?.scene ?? selectedScene;
  const scope = batch ? "scene" : selectedScope;
  const parent = scope === "arc" ? arc! : scene;
  const key = `${parent.record.novel_id}:${scope}:${parent.id}:chapter-continuation${batch ? `:batch:${batch.confirmationKey}` : ""}`;
  const [draft, setDraft] = useState<ContinuationDraft>({ volume_id: parent.record.volume_id, arc_id: scope === "arc" ? parent.id : scene.record.arc_id, selected: [], completed: [], setup: null, started: false, currentId: null, needsRead: false });
  const [rows, setRows] = useState<HierarchyRecord[]>([]);
  const [scenes, setScenes] = useState<HierarchyRecord[]>([scene.record]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [error, setError] = useState("");
  const [needsReview, setNeedsReview] = useState(false);
  const [batchChanged, setBatchChanged] = useState(false);
  const [changedBodies, setChangedBodies] = useState<HierarchyRecord[]>([]);
  const [target, setTarget] = useState<HierarchyNode | null>(null);
  const draftRef = useRef(draft);
  const stateRef = useRef({ active, open, dirty, readBlocked }); stateRef.current = { active, open, dirty, readBlocked };
  const operation = useRef<AbortController | null>(null);
  const writes = useRef(Promise.resolve());
  const writeRevision = useRef(0);
  const mounted = useRef(true);
  const completion = useRef<Promise<void> | null>(null);
  const stoppingRef = useRef(false);

  /** 功能：读取当前范围的场景与章节目录。Args: signal 本次操作的取消信号。Returns: 原场景身份和各场景已有章节。 */
  const readCatalog = async (signal: AbortSignal) => {
    const sceneRows = scope === "arc"
      ? (await apiGet<{ data: HierarchyRecord[] }>(`/api/scenes/arc/${parent.id}`, { signal })).data
      : [scene.record];
    const chapters = await Promise.all(sceneRows.map(async (item) =>
      (await apiGet<{ data: HierarchyRecord[] }>(`/api/chapters/scene/${item.scene_id}`, { signal })).data));
    return { scenes: sceneRows, chapters: chapters.flat().filter((item) => !batch || batch.ids.includes(item.chapter_id!)) };
  };

  /** 功能：核对已审核计划，忽略正文保存带来的父级统计变化。Args: record 当前详情；saved 本批保存时的计划。Returns: 内容和位置是否相同。 */
  const sameBatchPlan = (record: HierarchyRecord, saved: HierarchyRecord) =>
    record.novel_id === saved.novel_id && record.volume_id === saved.volume_id && record.arc_id === saved.arc_id && record.scene_id === saved.scene_id && record.chapter_id === saved.chapter_id &&
    record.order_index === saved.order_index && record.title === saved.title && record.summary === saved.summary &&
    record.subtitle === saved.subtitle && record.goal === saved.goal && record.theme === saved.theme && JSON.stringify(record.location_ids) === JSON.stringify(saved.location_ids) &&
    JSON.stringify(record.planning) === JSON.stringify(saved.planning) && record.plot === saved.plot && record.plot_source_fingerprint === saved.plot_source_fingerprint;

  /** 功能：恢复时仍只允许本批正式目标，不把异常清单改成另一批。Args: value 待恢复的列表。Returns: 检查通过；否则保留原稿并暂停。 */
  const checkBatchSelection = (value: ContinuationDraft) => {
    if (batch && (value.selected.some((item) => !batch.ids.includes(item.id)) || value.currentId && !value.selected.some((item) => item.id === value.currentId) || value.completed.some((item) => !value.selected.some((selected) => selected.id === item.id)))) {
      setNeedsReview(true); setBatchChanged(true); throw new Error(t("continuation.batchChanged"));
    }
  };

  /** 功能：固定章与场景的身份和顺序。Args: record 章节；parents 当前场景目录。Returns: 不依赖全书展示章号的目标。 */
  const selectionFor = (record: HierarchyRecord, parents = scenes): ChapterSelection => {
    const owner = parents.find((item) => item.scene_id === record.scene_id)!;
    return { id: record.chapter_id!, title: record.title, order_index: record.order_index, scene_id: record.scene_id, scene_order_index: owner.order_index, scene_title: owner.title };
  };

  /** 功能：按场景、章的实际顺序排列清单。Args: a、b 已固定的目标。Returns: 顺序差。 */
  const compareSelection = (a: ChapterSelection, b: ChapterSelection) =>
    (a.scene_order_index ?? scene.record.order_index) - (b.scene_order_index ?? scene.record.order_index) || a.order_index - b.order_index;

  // 列表没有业务版本；固定本地版本槽，章节本身仍保留各自的原版本草稿。
  const persist = async (next: ContinuationDraft) => {
    const revision = ++writeRevision.current;
    const write = writes.current.then(() => writeWritingDraft(key, 0, next));
    writes.current = write.catch(() => {});
    await write;
    if (revision === writeRevision.current) {
      draftRef.current = next;
      if (mounted.current) setDraft(next);
    }
  };

  useEffect(() => {
    mounted.current = true;
    let current = true;
    readWritingDraft<ContinuationDraft>(key, 0).then((stored) => {
      if (!current) return;
      if (stored) { draftRef.current = stored.value; setDraft(stored.value); }
      setLoaded(true);
    }).catch(() => { if (current) setError(t("draftFailed")); });
    return () => { current = false; mounted.current = false; operation.current?.abort(); };
  }, [key, t]);

  useEffect(() => {
    if (!open || !active) { if (!stoppingRef.current) { operation.current?.abort(); operation.current = null; setBusy(false); } return; }
    const abort = new AbortController();
    readCatalog(abort.signal)
      .then((catalog) => { if (!abort.signal.aborted) { setRows(catalog.chapters); setScenes(catalog.scenes); } })
      .catch((failure) => { if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : t("loadFailed")); });
    return () => abort.abort();
  // 范围和启动记录由外层稳定 key 固定；打开时才读取目录。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, active, key, t]);

  // 开始、恢复和继续都重读整个选定范围；不能把失效章节换成另一个目标。
  const inspect = async (value: ContinuationDraft, signal: AbortSignal) => {
    checkBatchSelection(value);
    if (stateRef.current.dirty) throw new Error(t("continuation.dirty"));
    const catalog = await readCatalog(signal);
    if (signal.aborted) return null;
    setRows(catalog.chapters); setScenes(catalog.scenes);
    const arcId = scope === "arc" ? parent.id : scene.record.arc_id;
    if (value.volume_id && value.volume_id !== parent.record.volume_id || value.arc_id && value.arc_id !== arcId) {
      setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : "continuation.restartList"));
    }
    const [volume, currentArc] = await Promise.all([
      apiGet<HierarchyRecord>(`/api/volumes/${parent.record.volume_id}`, { signal }),
      apiGet<HierarchyRecord>(`/api/arcs/${arcId}`, { signal }),
    ]);
    if (volume.is_deleted || volume.volume_id !== parent.record.volume_id || volume.novel_id !== parent.record.novel_id || currentArc.is_deleted || currentArc.arc_id !== arcId || currentArc.volume_id !== volume.volume_id || currentArc.novel_id !== parent.record.novel_id) {
      setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : value.currentId ? "continuation.restartList" : "continuation.changed"));
    }
    if (batch && (!sameBatchPlan(volume, batch.volume.record) || !sameBatchPlan(currentArc, batch.arc.record))) {
      setNeedsReview(true); setBatchChanged(true); throw new Error(t("continuation.batchChanged"));
    }
    if (batch) {
      for (const record of [volume, currentArc]) {
        const kind = record.arc_id ? "arc" : "volume";
        const id = record.arc_id ?? record.volume_id;
        const [plot, planning] = await Promise.all([
          readWritingDraft<{ text: string; editing: boolean; preview?: unknown; command?: unknown; saved?: unknown }>(`${record.novel_id}:${kind}:${id}:plot`, record.version),
          readWritingDraft<{ preview?: unknown; command?: unknown; saved?: unknown }>(`${record.novel_id}:${kind}:${id}:generation`, record.version),
        ]);
        // 父页尚在编辑或核对剧情保存时，先由作者回原处完成；写作不接管这些回执。
        if (plot && (plot.value.editing || plot.value.text !== (record.plot ?? "") || plot.value.preview || plot.value.command || plot.value.saved)) {
          setNeedsReview(true); throw new Error(t("continuation.dirty"));
        }
        if (planning && (planning.value.preview || planning.value.command || planning.value.saved)) {
          setNeedsReview(true); throw new Error(t("continuation.hasDraft", { title: record.title }));
        }
      }
    }
    const participatingScenes = await Promise.all([...new Set(value.selected.map((item) => item.scene_id ?? scene.id))].map(async (id) => {
      const summary = catalog.scenes.find((item) => item.scene_id === id);
      if (!summary || summary.is_deleted) { setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : value.currentId ? "continuation.restartList" : "continuation.changed")); }
      const record = await apiGet<HierarchyRecord>(`/api/scenes/${id}`, { signal });
      if (record.is_deleted || record.scene_id !== id || record.arc_id !== arcId || record.volume_id !== volume.volume_id || record.novel_id !== parent.record.novel_id || scope === "arc" && record.order_index !== summary.order_index) {
        setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : value.currentId ? "continuation.restartList" : "continuation.changed"));
      }
      if (batch && !sameBatchPlan(record, batch.scene.record)) {
        setNeedsReview(true); setBatchChanged(true); throw new Error(t("continuation.batchChanged"));
      }
      if (batch) {
        const generationScope = `${record.novel_id}:scene:${id}:generation`;
        const [planning, confirmations] = await Promise.all([
          readWritingDraft<{ preview?: unknown; command?: { key: string }; saved?: unknown }>(generationScope, record.version),
          readChapterPlanConfirmations(generationScope),
        ]);
        const ownSaved = confirmations.some((confirmation) => confirmation.value.command?.key === batch.confirmationKey && confirmation.value.saved);
        // 原批保存后的清稿失败不阻断写作；新的未确认计划必须先处理。
        if (confirmations.some((confirmation) => (confirmation.value.preview || confirmation.value.command || confirmation.value.saved) && (confirmation.value.command?.key !== batch.confirmationKey || !confirmation.value.saved)) ||
          planning && (planning.value.preview || planning.value.command || planning.value.saved) && !(planning.value.command?.key === batch.confirmationKey && (planning.value.saved || ownSaved))) {
          setNeedsReview(true); throw new Error(t("continuation.hasDraft", { title: record.title }));
        }
      }
      return record;
    }));
    if (scope === "scene") setScenes(participatingScenes);
    const records = await Promise.all(value.selected.map(async (item) => {
      const owner = participatingScenes.find((record) => record.scene_id === (item.scene_id ?? scene.id))!;
      const summary = catalog.chapters.find((record) => record.chapter_id === item.id);
      if (owner.order_index !== (item.scene_order_index ?? scene.record.order_index) || !summary || summary.is_deleted || summary.scene_id !== owner.scene_id || summary.arc_id !== arcId || summary.volume_id !== volume.volume_id || summary.novel_id !== parent.record.novel_id || summary.order_index !== item.order_index) {
        setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : value.currentId ? "continuation.restartList" : "continuation.changed"));
      }
      const record = await apiGet<HierarchyRecord>(`/api/chapters/${item.id}`, { signal });
      if (record.is_deleted || record.chapter_id !== item.id || record.scene_id !== owner.scene_id || record.arc_id !== arcId || record.volume_id !== volume.volume_id || record.novel_id !== parent.record.novel_id || record.order_index !== summary.order_index) {
        setNeedsReview(true); setBatchChanged(Boolean(batch)); throw new Error(t(batch ? "continuation.batchChanged" : value.currentId ? "continuation.restartList" : "continuation.changed"));
      }
      const completed = value.completed.find((entry) => entry.id === item.id);
      if (batch) {
        const saved = batch.records.find((entry) => entry.chapter_id === item.id);
        if (!saved || !sameBatchPlan(record, saved) || !completed && record.version !== saved.version) {
          setNeedsReview(true); setBatchChanged(true); throw new Error(t("continuation.batchChanged"));
        }
      }
      if (completed && record.content !== (completed.acceptedContent ?? completed.record.content)) {
        if (!signal.aborted && stateRef.current.active && stateRef.current.open) {
          setChangedBodies((current) => [...current.filter((entry) => entry.chapter_id !== record.chapter_id), record]);
          setNeedsReview(true);
        }
        throw new Error(t("continuation.bodyChanged", { title: record.title }));
      }
      const generation = await readWritingDraft<{ preview?: unknown; command?: { key: string }; saved?: unknown }>(`${record.novel_id}:chapter:${item.id}:generation`, record.version);
      const ownCurrent = value.currentId === item.id;
      // 回应丢失时正文可能已落库，必须允许原键核对；新生成仍不能覆盖正文。
      const verifyingSave = ownCurrent && Boolean(generation?.value.command || generation?.value.saved);
      if (record.content && !completed && !verifyingSave) { setNeedsReview(true); throw new Error(t("continuation.hasBody", { title: record.title })); }
      const pendingGeneration = generation && (generation.value.preview || generation.value.command || generation.value.saved);
      if (pendingGeneration && !ownCurrent && (!completed || generation.value.command?.key !== completed.key)) { setNeedsReview(true); throw new Error(t("continuation.hasDraft", { title: record.title })); }
      const body = await readWritingDraft<string>(`${record.novel_id}:chapter:${item.id}:body`, record.version);
      if (body && (body.value !== record.content || body.base_version !== record.version)) { setNeedsReview(true); throw new Error(t("continuation.dirty")); }
      return record;
    }));
    for (const record of [...(batch ? [currentArc] : []), ...participatingScenes, ...records]) {
      const kind = record.chapter_id ? "chapter" : record.scene_id ? "scene" : "arc";
      const id = record.chapter_id ?? record.scene_id ?? record.arc_id;
      const plans = await Promise.all(["", ...PLANNING_SECTIONS.map((section) => `:${section}`)].map((suffix) => readWritingDraft<{ draft: PlanningDraft; command?: unknown }>(`${record.novel_id}:${kind}:${id}:plan${suffix}`, record.version)));
      if (plans.some((plan) => plan && (batch && plan.value.command || plan.base_version !== record.version || plan.value.draft.title !== record.title || plan.value.draft.summary !== record.summary || JSON.stringify(plan.value.draft.planning) !== JSON.stringify(record.planning)))) {
        setNeedsReview(true); throw new Error(t("continuation.dirty"));
      }
    }
    if (signal.aborted || !stateRef.current.active || !stateRef.current.open) return null;
    if (stateRef.current.dirty) throw new Error(t("continuation.dirty"));
    let inspectedDraft = value;
    if (value.volume_id === undefined || value.arc_id === undefined || value.selected.some((item) => item.scene_id === undefined || item.scene_order_index === undefined)) {
      // 旧清单从本次完整核对起固定父链和场景顺序，不补猜旧清单创建时的结构。
      inspectedDraft = {
        ...value, volume_id: value.volume_id ?? volume.volume_id, arc_id: value.arc_id ?? currentArc.arc_id,
        selected: value.selected.map((item) => {
          const record = records.find((entry) => entry.chapter_id === item.id)!;
          const owner = participatingScenes.find((entry) => entry.scene_id === record.scene_id)!;
          return { ...item, scene_id: item.scene_id ?? record.scene_id, scene_order_index: item.scene_order_index ?? owner.order_index, scene_title: item.scene_title ?? owner.title };
        }),
      };
      await persist(inspectedDraft);
      if (signal.aborted || !stateRef.current.active || !stateRef.current.open) return null;
    }
    return { records: records.sort((a, b) => compareSelection(selectionFor(a, participatingScenes), selectionFor(b, participatingScenes))), draft: inspectedDraft };
  };

  const startOrContinue = async () => {
    if (operation.current || stoppingRef.current || !loaded || !active || !open) return;
    const abort = new AbortController(); operation.current = abort; setBusy(true); setError("");
    try {
      const current = draftRef.current;
      checkBatchSelection(current);
      if (current.currentId) {
        const pending = await readWritingDraft<{ command?: unknown; saved?: unknown }>(`${scene.record.novel_id}:chapter:${current.currentId}:generation`, current.currentRecord?.version);
        if (pending?.value.command || pending?.value.saved) {
          // 核对原请求不重新生成，也不受后文或新就绪状态阻断。
          const original = current.currentRecord ?? await apiGet<HierarchyRecord>(`/api/chapters/${current.currentId}`, { signal: abort.signal });
          if (!abort.signal.aborted && stateRef.current.active && stateRef.current.open) setTarget(hierarchyNode("chapter", original));
          return;
        }
      }
      if (stateRef.current.readBlocked) throw new Error(t("continuation.readBlocked"));
      if (!current.selected.length || current.selected.length > 20) throw new Error(t(scope === "arc" ? "continuation.limitArc" : "continuation.limit"));
      const inspected = await inspect(current, abort.signal);
      if (!inspected || abort.signal.aborted) return;
      const records = inspected.records;
      const next = current.currentId ? records.find((record) => record.chapter_id === current.currentId) : records.find((record) => !current.completed.some((entry) => entry.id === record.chapter_id));
      if (!next) return;
      const readiness = await apiGet<PlanningReadiness>(`/api/novels/${scene.record.novel_id}/planning-readiness?target_type=chapter&target_id=${next.chapter_id}`, { signal: abort.signal });
      if (abort.signal.aborted || !stateRef.current.active || !stateRef.current.open) return;
      if (!readiness.can_write) throw new Error([t("generationBlocked"), ...readiness.missing_fields.map((item) => item.message), ...readiness.blockers.map((item) => item.message)].join(" "));
      await persist({ ...inspected.draft, selected: [...inspected.draft.selected].sort(compareSelection), started: true, currentId: next.chapter_id!, currentRecord: next, needsRead: false });
      if (!abort.signal.aborted && stateRef.current.active && stateRef.current.open) { setNeedsReview(false); setTarget(hierarchyNode("chapter", next)); }
    } catch (failure) { if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : t("loadFailed")); }
    finally { if (operation.current === abort) { operation.current = null; setBusy(false); } }
  };

  const rereadSaved = async (value = draftRef.current) => {
    if (operation.current || stoppingRef.current) return;
    const abort = new AbortController(); operation.current = abort; setBusy(true); setError("");
    try {
      checkBatchSelection(value);
      const saved = value.completed.at(-1)!;
      const record = await apiGet<HierarchyRecord>(`/api/chapters/${saved.id}`, { signal: abort.signal });
      if (record.novel_id !== parent.record.novel_id || record.volume_id !== parent.record.volume_id || record.arc_id !== (scope === "arc" ? parent.id : scene.record.arc_id) || record.scene_id !== saved.record.scene_id || record.chapter_id !== saved.id || record.order_index !== saved.record.order_index || record.is_deleted || record.version < saved.record.version) throw new Error(t("continuation.changed"));
      if (record.content !== (saved.acceptedContent ?? saved.record.content)) {
        if (!abort.signal.aborted && stateRef.current.active && stateRef.current.open) {
          setChangedBodies((current) => [...current.filter((entry) => entry.chapter_id !== record.chapter_id), record]);
          setNeedsReview(true);
        }
        throw new Error(t("continuation.bodyChanged", { title: record.title }));
      }
      // 保存成功已先记入列表；读回整个固定范围通过后，才恢复继续入口。
      const inspected = await inspect(value, abort.signal);
      if (!inspected || abort.signal.aborted) return;
      await apiGet<PlanningReadiness>(`/api/novels/${scene.record.novel_id}/planning-readiness?target_type=chapter&target_id=${saved.id}`, { signal: abort.signal });
      if (abort.signal.aborted || !stateRef.current.active || !stateRef.current.open) return;
      await persist({ ...inspected.draft, needsRead: false });
      if (!abort.signal.aborted && stateRef.current.active && stateRef.current.open && stateRef.current.readBlocked) onRetryRead?.();
    } catch (failure) { if (!abort.signal.aborted) setError(`${t("savedReadFailed")} ${failure instanceof Error ? failure.message : t("loadFailed")}`); }
    finally { if (operation.current === abort) { operation.current = null; setBusy(false); } }
  };

  const close = () => { if (stoppingRef.current) return; operation.current?.abort(); operation.current = null; setTarget(null); onClose(); };
  const completedCount = draft.selected.filter((item) => draft.completed.some((entry) => entry.id === item.id)).length;
  const finished = draft.selected.length > 0 && completedCount === draft.selected.length;
  const displayed = batch ? batch.records.filter((record) => batch.ids.includes(record.chapter_id!)).map((record) => selectionFor(record, [batch.scene.record])).sort(compareSelection)
    : [...rows.map((record) => selectionFor(record)), ...draft.selected.filter((item) => !rows.some((record) => record.chapter_id === item.id))].sort(compareSelection);

  return <>
    <RetainedModalBackdrop isOpen={open && !target} onOpenChange={(value) => !value && close()} isDismissable={!stopping} isKeyboardDismissDisabled={stopping}>
      <Modal.Container size="lg" scroll="inside" className="p-0 sm:p-4">
        <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-2xl">
          <Modal.Header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-7">
            <Modal.Heading className="text-lg font-semibold">{t("continuation.title")}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} isDisabled={stopping} />
          </Modal.Header>
          <Modal.Body className="workspace-scrollbar min-h-0 px-5 py-5 sm:px-7">
            {(error || readError) && <RelationEditorErrorSummary message={error || readError} className="mb-4" />}
            {dirty && <p role="alert" className="mb-4 text-sm">{t("continuation.dirty")}</p>}
            {readBlocked && !error && !readError && <p role="status" className="mb-4 text-sm">{t("continuation.readBlocked")}</p>}
            {!loaded ? <p role="status">{t("loading")}</p> : <>
              <p role="status" className="text-sm tabular-nums">{draft.started ? t("continuation.progress", { completed: completedCount, total: draft.selected.length }) : t("continuation.selectCount", { count: draft.selected.length, max: 20 })}</p>
              <ul className="mt-3 divide-y divide-border">
                {displayed.map((item) => {
                  const selected = draft.selected.some((entry) => entry.id === item.id);
                  const done = draft.completed.some((entry) => entry.id === item.id);
                  return <li key={item.id} className={`flex min-h-11 min-w-0 items-center gap-3 border-l-2 px-3 py-2 ${selected ? "border-accent bg-selected" : "border-transparent"}`}>
                    <label className="flex min-h-11 min-w-0 flex-1 items-center gap-3 text-sm">
                      <input type="checkbox" className="size-4 shrink-0 accent-accent" checked={selected} disabled={busy || draft.started || done || draft.currentId === item.id || (!selected && draft.selected.length >= 20)} onChange={(event) => {
                        if (operation.current || stoppingRef.current) return;
                        const next = { ...draftRef.current, selected: event.target.checked ? [...draftRef.current.selected, item].sort(compareSelection) : draftRef.current.selected.filter((entry) => entry.id !== item.id) };
                        draftRef.current = next; setDraft(next);
                        void persist(next).catch(() => setError(t("draftFailed")));
                      }} /><span className="min-w-0 break-words">{scope === "arc" && <span className="block text-xs text-muted">{item.scene_title}</span>}{item.title}</span>
                    </label>
                    {selected && <span className="shrink-0 text-xs text-muted">{t(done ? "continuation.saved" : "continuation.pending")}</span>}
                  </li>;
                })}
              </ul>
              {changedBodies.map((record) => <details key={record.chapter_id} open className="mt-4 border-t border-border pt-4">
                <summary className="cursor-pointer text-sm font-medium">{t("latestBody")} · {record.title}</summary>
                <pre className="reading-copy mt-3 whitespace-pre-wrap break-words font-sans">{record.content || t("continuation.emptyBody")}</pre>
              </details>)}
              {finished && <p role="status" className="mt-4 text-sm">{t("continuation.finished")}</p>}
            </>}
          </Modal.Body>
          <Modal.Footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
            <Button size="sm" variant="ghost" isDisabled={stopping} onPress={close}>{t("closeKeepDraft")}</Button>
            <Button size="sm" variant="ghost" isDisabled={busy || !loaded} onPress={() => {
              if (operation.current || stoppingRef.current) return;
              const abort = new AbortController(); operation.current = abort;
              stoppingRef.current = true; setStopping(true); setBusy(true);
              void (async () => {
                try {
                  const removal = writes.current.then(() => writeWritingDraft(key, 0, null)); writes.current = removal.catch(() => {}); await removal;
                  draftRef.current = { volume_id: parent.record.volume_id, arc_id: scope === "arc" ? parent.id : scene.record.arc_id, selected: [], completed: [], setup: null, started: false, currentId: null, needsRead: false };
                  if (mounted.current) { setDraft(draftRef.current); setNeedsReview(false); setBatchChanged(false); setChangedBodies([]); setError(""); }
                  stoppingRef.current = false;
                  if (mounted.current && stateRef.current.active && stateRef.current.open) close();
                } catch { if (mounted.current) setError(t("draftFailed")); }
                finally { stoppingRef.current = false; if (operation.current === abort) operation.current = null; if (mounted.current) { setStopping(false); setBusy(false); } }
              })();
            }}>{t("continuation.stop")}</Button>
            {needsReview && (!batchChanged || changedBodies.length > 0) && <Button size="sm" variant="outline" isDisabled={busy || dirty} onPress={() => {
              if (operation.current || stoppingRef.current) return;
              const abort = new AbortController(); operation.current = abort; setBusy(true);
              const selected = draftRef.current.selected.map((item) => {
                // 已打开章节的原稿仍绑定原顺序；结构变化须放弃列表后重新选择。
                if (batch || draftRef.current.currentId) return item;
                const current = rows.find((row) => row.chapter_id === item.id && row.scene_id === (item.scene_id ?? scene.id));
                return current ? selectionFor(current) : item;
              }).sort(compareSelection);
              // 只认可已经展示的正文，原保存结果和确认键保留不变。
              const completed = draftRef.current.completed.map((entry) => { const shown = changedBodies.find((record) => record.chapter_id === entry.id); return shown ? { ...entry, acceptedContent: shown.content } : entry; });
              void persist({ ...draftRef.current, selected, completed, started: Boolean(draftRef.current.currentId) }).then(() => { setNeedsReview(false); setChangedBodies([]); setError(""); }).catch(() => setError(t("draftFailed"))).finally(() => { if (operation.current === abort) { operation.current = null; setBusy(false); } });
            }}>{t(changedBodies.length ? "continuation.acceptBodyChanges" : "continuation.reviewList")}</Button>}
            {draft.needsRead || readBlocked && !draft.currentId ? <Button size="sm" variant="primary" isDisabled={busy || dirty} onPress={() => { if (draft.needsRead) void rereadSaved(); else onRetryRead?.(); }}>{t("retryRead")}</Button>
              : !finished && <Button size="sm" variant="primary" isDisabled={!loaded || busy || (dirty || needsReview) && !draft.currentId || !draft.selected.length} onPress={() => void startOrContinue()}>{t(!draft.started ? "continuation.start" : draft.currentId ? "continuation.resume" : "continuation.next")}</Button>}
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </RetainedModalBackdrop>
    {target && <RetainedViewActive.Provider value={active && open}><HierarchyGeneration onPageChange={onGenerationPageChange} key={target.id} node={target} choices={choices} choicesError={choicesError} fixedSetup={draft.setup ?? undefined}
      onSetup={async (setup) => {
        const abort = new AbortController();
        if (!stateRef.current.active || !stateRef.current.open) throw new Error(t("continuation.paused"));
        operation.current = abort;
        try {
          const inspected = await inspect(draftRef.current, abort.signal);
          if (!inspected || abort.signal.aborted) throw new Error(t("continuation.paused"));
          if (!inspected.draft.setup) await persist({ ...inspected.draft, setup });
        } finally { if (operation.current === abort) operation.current = null; }
      }}
      onClose={() => setTarget(null)} onSaved={async (records, _kind, confirmationKey) => {
        // 拒绝交付会让原生成弹窗保留成功回执，不把停止当成已经接收。
        if (stoppingRef.current) throw new Error(t("continuation.paused"));
        if (completion.current) return completion.current;
        const record = records[0]; const current = draftRef.current;
        if (!record || !confirmationKey || record.chapter_id !== target.id) return;
        if (current.completed.some((entry) => entry.id === target.id)) { await writes.current; return; }
        if (current.currentId !== target.id) throw new Error(t("continuation.paused"));
        const finish = async () => {
        const next = { ...current, completed: current.completed.some((entry) => entry.id === target.id) ? current.completed : [...current.completed, { id: target.id, key: confirmationKey, record }], currentId: null, needsRead: true };
        try { await persist(next); }
        catch (failure) { draftRef.current = current; if (mounted.current) setDraft(current); throw failure; }
        if (stoppingRef.current) throw new Error(t("continuation.paused"));
        if (mounted.current) setTarget(null);
        if (!mounted.current || !stateRef.current.active || !stateRef.current.open) return;
        onSaved(record); await rereadSaved(next);
        };
        completion.current = finish();
        try { await completion.current; } finally { completion.current = null; }
      }} /></RetainedViewActive.Provider>}
  </>;
}
