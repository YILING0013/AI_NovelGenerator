"use client";

import { Button, Modal } from "@heroui/react";
import { useContext, useEffect, useId, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import { parseItemReadV1, type ItemReadV1 } from "@/types/item";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { ChapterItemOwnerConfirmV1, ChapterItemOwnerResultV1, ChapterPsychologicalCheckSourceV1 } from "@/types/chapterRecords";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import PsychologicalStateCheck from "../chapter-records/PsychologicalStateCheck";
import { readChapterRecordDrafts, writeChapterRecordDraft, claimChapterCheckReviewDraft, reviseChapterCheckReviewDraft, handoffChapterItemFact, readChapterItemFactHandoff, type ChapterRecordDraft } from "../chapter-records/chapterRecordDrafts";
import { readFactDrafts } from "../characters/factDraftStorage";
import type { ItemFactDraftV1 } from "./itemFactDrafts";
import type { ItemFactPreparationV1 } from "./itemFactPreparation";
import type { ItemFactPreviewV1, ItemFactValuesV1, ItemFactReadResultV1 } from "@/types/itemFacts";
import ItemFactValues, { type ItemFactChoices } from "./ItemFactValues";
import { confirmChapterRecord, useChapterRecordPersistence } from "../chapter-records/chapterRecordConfirmation";
import { ChapterRecordAuthorConfirmation, ChapterRecordCommandStatus, ChapterRecordExport } from "../chapter-records/ChapterRecordConfirmationParts";

type CharacterChoice = { character_id: string; name: string; status: "active" | "inactive"; is_deleted: boolean };

/** 功能：在关联资料中显示固定物品的入口及本机草稿。Args: props 当前物品和启动回调。Returns: 不承载运行中稿件的入口。 */
export function ItemOwnerConfirmationEntry({ novelId, item, disabled, refresh = 0, onStart }: {
  novelId: string;
  item: ItemReadV1;
  disabled: boolean;
  refresh?: number;
  onStart: (draft?: ChapterRecordDraft) => void;
}) {
  const t = useTranslations("writing.chapterRecords");
  const active = useContext(RetainedViewActive);
  const scope = `${novelId}:item:${item.item_id}:chapter-records`;
  const [drafts, setDrafts] = useState<ChapterRecordDraft[]>([]);
  const [error, setError] = useState("");
  const eligible = !item.is_deleted;
  useEffect(() => {
    if (!active) return;
    let disposed = false;
    void readChapterRecordDrafts(scope).then((rows) => { if (!disposed) { setDrafts(rows); setError(""); } }).catch(() => { if (!disposed) setError(t("localFailed")); });
    return () => { disposed = true; };
  }, [active, scope, refresh, t]);
  return <section data-testid="item-owner-confirmation" className={`${eligible || drafts.length > 0 || error ? "mt-4 " : ""}grid min-w-0 gap-3`}>
    {eligible && <div><Button size="sm" variant="outline" isDisabled={disabled} onPress={() => onStart()}>{t("itemOwner.open")}</Button></div>}
    {error && <RelationEditorErrorSummary message={error} />}
    {drafts.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("localDrafts", { count: drafts.length })}</summary><ul className="divide-y divide-border">{drafts.map((stored) => <li key={stored.key} className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2"><span className="break-words text-sm">{stored.itemOwner?.from_name} → {stored.itemOwner?.to_name || t("itemOwner.newHolder")} · {t(stored.command?.saved ? "savedPending" : stored.command?.unknown ? "unknown" : stored.command ? "rejected" : "draft")}</span><Button size="sm" variant="outline" isDisabled={disabled} onPress={() => onStart(stored)}>{t("resume")}</Button>{!stored.itemFact && (!stored.review || stored.command?.saved) && (!stored.command?.unknown || stored.command.saved) && <Button size="sm" variant="ghost" isDisabled={disabled} onPress={async () => {
      try { await writeChapterRecordDraft(scope, stored, stored.revision, true); setDrafts(await readChapterRecordDrafts(scope)); setError(""); } catch { setError(t("localFailed")); }
    }}>{t("discard")}</Button>}</li>)}</ul></details>}
  </section>;
}

/** 功能：为一次明确启动的物品确认创建独立稿件。Args: 正式物品、持有人名称及待恢复原稿。Returns: 新稿件身份，保留原不可变命令。 */
function createDraft(item: ItemReadV1 | null, fromName: string, restored?: ChapterRecordDraft): ChapterRecordDraft {
  return restored?.review || restored?.itemFact ? restored : restored ? { ...restored, key: crypto.randomUUID(), revision: 1, ...(restored.command ? { command: { ...restored.command, readbackDone: false } } : {}), ...(restored.itemOwnerCheck ? { itemOwnerCheck: { ...restored.itemOwnerCheck, status: restored.itemOwnerCheck.status === "running" ? "interrupted" : restored.itemOwnerCheck.status } } : {}) } : {
    key: crypto.randomUUID(), revision: 1, mode: "item-owner", chapterId: "", title: item!.name, content: "", summary: "", issues: [], psychologicalState: "", reason: "", evidence: null, relatedEntities: [], targetState: null, expectedReportVersion: 0, recordId: null,
    itemCheckVersion: 2,
    itemOwner: { item_id: item!.item_id, name: item!.name, version: item!.version, from_character_id: "", from_name: "", to_character_id: "", to_name: "" },
  };
}

/** 功能：在工作台固定宿主核对一次持有人变更。Args: props 启动物品快照、恢复稿及安全关闭回调。Returns: 独立于列表选择和筛选的确认层。 */
export default function ItemOwnerConfirmation({ novelId, item, characters, choices, initialDraft, onBusy, onDirty, beforeLeaveRef, onReadback, onClose, onPrepareFact, onResumePreparation }: {
  novelId: string;
  item: ItemReadV1 | null;
  characters: CharacterChoice[];
  choices: ItemFactChoices;
  initialDraft?: ChapterRecordDraft;
  onBusy: (busy: boolean) => void;
  onDirty?: (dirty: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  onReadback: (item: ItemReadV1) => void;
  onClose: (saved: boolean) => void;
  onPrepareFact: (draft: ItemFactDraftV1) => void;
  onResumePreparation?: (preparation: ItemFactPreparationV1) => void;
}) {
  const t = useTranslations("writing.chapterRecords");
  const f = useTranslations("writing.itemFacts");
  const active = useContext(RetainedViewActive);
  const id = useId();
  const scope = `${novelId}:item:${initialDraft?.itemOwner?.item_id ?? item!.item_id}:chapter-records`;
  const { persist, remove, queue, persisted, localError } = useChapterRecordPersistence(scope, t("localFailed"));
  const holderName = (owner: string | null) => characters.find((character) => character.character_id === owner)?.name ?? owner ?? t("emptyValue");
  const [draft, setDraft] = useState<ChapterRecordDraft | null>(() => createDraft(item, holderName(item?.owner_character_id ?? null), initialDraft));
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]);
  const [source, setSource] = useState<ChapterPsychologicalCheckSourceV1 | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [structureRetry, setStructureRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const [checked, setChecked] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [current, setCurrent] = useState<ItemReadV1 | null>(null);
  const [reading, setReading] = useState(false);
  const [reviewChecked, setReviewChecked] = useState(false);
  const [beforeState, setBeforeState] = useState<ItemFactValuesV1 | null>(null);
  const [readingBefore, setReadingBefore] = useState(false);
  const [beforeError, setBeforeError] = useState("");
  const draftRef = useRef(draft);
  const pending = useRef(false);
  const alive = useRef(true);
  const epoch = useRef(0);
  const activeRef = useRef(active); activeRef.current = active;
  const cancelCheck = useRef<(() => void) | null>(null);
  const readbackRef = useRef(onReadback); readbackRef.current = onReadback;
  const [claiming, setClaiming] = useState(Boolean(initialDraft?.review));
  const claimed = useRef(!initialDraft?.review);
  const blocked = saving || claiming || !claimed.current || Boolean(draft?.command || draft?.itemFact);
  const rejected = Boolean(draft?.command && !draft.command.saved && !draft.command.unknown);
  const open = Boolean(draft);
  const currentCharacters = characters.filter((character) => !character.is_deleted && character.status === "active");
  const started = useRef(false);

  useEffect(() => { alive.current = true; return () => { alive.current = false; epoch.current += 1; }; }, []);
  useEffect(() => { onBusy(saving || claiming); return () => onBusy(false); }, [saving, claiming, onBusy]);
  useEffect(() => { onDirty?.(Boolean(draft)); return () => onDirty?.(false); }, [draft, onDirty]);
  useEffect(() => {
    if (started.current || !draftRef.current) return;
    started.current = true;
    if (draftRef.current.itemFact) { claimed.current = true; setClaiming(false); return; }
    if (!draftRef.current.review) { void persist(draftRef.current); return; }
    void claimChapterCheckReviewDraft(scope, draftRef.current).then((next) => {
      persisted.current.set(next.key, next.revision);
      if (alive.current) { claimed.current = true; draftRef.current = next; setDraft(next); }
    }).catch(() => { if (alive.current) setError(t("localFailed")); })
      .finally(() => { if (alive.current) setClaiming(false); });
  }, [persist, persisted, scope, t]);
  useEffect(() => {
    if (!beforeLeaveRef || !active) return;
    beforeLeaveRef.current = async () => {
      if (pending.current || claiming) throw new Error(t("saving"));
      cancelCheck.current?.();
      try {
        if (claimed.current && draftRef.current && !draftRef.current.itemFact) await persist(draftRef.current);
        await queue.current;
        epoch.current += 1; draftRef.current = null; setDraft(null); setSource(null); onClose(false);
      } catch { setError(t("localFailed")); throw new Error(t("localFailed")); }
    };
    return () => { beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef, claiming, onClose, persist, queue, t]);
  useEffect(() => {
    if (!open || !active) return;
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [open, active]);
  useEffect(() => {
    if (!open || !active || initialDraft?.review) return;
    const abort = new AbortController();
    setLoading(true); setLoadError("");
    const load = async () => {
      const volumes = (await apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal: abort.signal })).data;
      const arcs = (await Promise.all(volumes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/arcs/volume/${row.volume_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
      const scenes = (await Promise.all(arcs.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/scenes/arc/${row.arc_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
      const rows = (await Promise.all(scenes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/chapters/scene/${row.scene_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
      if (abort.signal.aborted) return;
      if ([...volumes, ...arcs, ...scenes, ...rows].some((row) => row.novel_id !== novelId || row.is_deleted)) throw new Error(t("itemOwner.wrongScope"));
      setChapters(rows);
    };
    void load().catch((failure) => { if (!abort.signal.aborted) setLoadError((failure as Error).message); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [open, active, novelId, t, structureRetry, initialDraft?.review]);

  const update = (next: ChapterRecordDraft) => {
    const changed = { ...next, revision: (draftRef.current?.revision ?? 0) + 1 };
    draftRef.current = changed; setDraft(changed); setChecked(false); void persist(changed);
  };
  useEffect(() => {
    if (!active || draft?.itemCheckVersion !== 2 || !source || draft.command || draft.itemFact) return;
    const abort = new AbortController(); setReadingBefore(true); setBeforeError(""); setBeforeState(null);
    void apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${novelId}/read`, { item_ids: [draft.itemOwner!.item_id], position: { version: 1, intent: "chapter_before", target_type: "chapter", target_id: source.chapter_id } }, { signal: abort.signal }).then((result) => {
      if (abort.signal.aborted) return;
      const row = result.items.find((entry) => entry.item_id === draft.itemOwner!.item_id);
      if (!row || result.novel_id !== novelId) throw new Error(f("wrongScope"));
      setBeforeState(row.values);
      const original = draftRef.current;
      if (original && !original.review && !original.itemOwnerCheck && !original.command && !original.itemFact) {
        const owner = row.values?.lifecycle_status === "held" ? row.values.owner_character_id : null;
        update({ ...original, itemOwner: { ...original.itemOwner!, from_character_id: owner ?? "", from_name: holderName(owner) } });
      }
    }).catch((failure) => { if (!abort.signal.aborted) setBeforeError(failure.message); }).finally(() => { if (!abort.signal.aborted) setReadingBefore(false); });
    return () => abort.abort();
  // 保留启动时的版本和已有检查；读取章前值不能悄悄换版本。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, novelId, draft?.key, draft?.itemCheckVersion, source]);
  const openDraft = (restored?: ChapterRecordDraft, start = item, alreadyPersisted = false) => {
    cancelCheck.current?.(); epoch.current += 1;
    setSource(null); setChecked(false); setError(""); setFieldErrors({}); setCurrent(null); setReviewChecked(false);
    const next = createDraft(start, holderName(start?.owner_character_id ?? null), restored);
    draftRef.current = next; setDraft(next);
    if (alreadyPersisted) persisted.current.set(next.key, next.revision);
    else void persist(next);
  };
  const close = async () => {
    if (pending.current || claiming) return;
    cancelCheck.current?.();
    try {
      if (claimed.current && draftRef.current && !draftRef.current.itemFact) await persist(draftRef.current);
      epoch.current += 1; draftRef.current = null; setDraft(null); setSource(null); setError("");
      onClose(false);
    } catch { setError(t("localFailed")); }
  };
  const submit = async () => {
    const session = draftRef.current;
    if (session?.itemFact && !pending.current) {
      pending.current = true; setSaving(true); setError("");
      try {
        // 另一页可能已把明确失败的请求交回准备，先读取当前关联。
        const original = (await readChapterRecordDrafts(scope)).find((row) => row.key === session.key);
        const currentLink = original?.itemFact;
        if (!currentLink) throw new Error(t("localFailed"));
        const link = await readChapterItemFactHandoff(novelId, currentLink);
        const restored = currentLink.draftKey ? (await readFactDrafts<ItemFactDraftV1>("item", `${novelId}:item-facts`)).find((row) => row.key === currentLink.draftKey) : null;
        if (link.preparation && onResumePreparation) onResumePreparation(link.preparation);
        else if (restored) onPrepareFact(restored);
        else {
          if (!link.operation?.saved) throw new Error(t("localFailed"));
          onReadback(parseItemReadV1(await apiGet<unknown>(`/api/items/novel/${novelId}/${session.itemOwner!.item_id}`), novelId));
        }
        draftRef.current = null; setDraft(null); onClose(false);
      } catch (failure) { setError((failure as Error).message); }
      finally { pending.current = false; setSaving(false); }
      return;
    }
    if (!session || pending.current || claiming || !claimed.current || session.itemOwnerCheck?.status === "running" || !session.command && (!checked || !valid)) return;
    pending.current = true; setSaving(true); setError(""); setFieldErrors({});
    const request = epoch.current;
    if (session.itemCheckVersion === 2 && !session.command) {
      try {
        await persist(session); await queue.current;
        const target = session.itemOwner!;
        const prepared = await apiPost<{ preview: ItemFactPreviewV1; after: ItemFactValuesV1 }>(`/api/chapter-records/novel/${novelId}/item-facts/prepare`, {
          item_id: target.item_id, expected_version: target.version, from_character_id: target.from_character_id, to_character_id: target.to_character_id, evidence: session.evidence, basis: session.itemOwnerCheck!.result!.basis,
        });
        const confirmation: ItemFactDraftV1 = { schema_id: "item.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel: `${chapters.find((row) => row.chapter_id === session.evidence!.chapter_id)?.title ?? session.evidence!.chapter_id} · ${f("operations.change")}`, ...prepared, reason: "", authorConfirmed: false, origin: { scope, draftKey: session.key, reviewId: session.review?.reviewId } };
        await handoffChapterItemFact(scope, session, confirmation);
        if (alive.current && epoch.current === request) { draftRef.current = null; setDraft(null); onPrepareFact(confirmation); onClose(false); }
      } catch (failure) { if (alive.current) setError((failure as Error).message); }
      finally { pending.current = false; if (alive.current) setSaving(false); }
      return;
    }
    const outcome = await confirmChapterRecord({
      draft: session, persist, remove,
      command: () => {
        const target = session.itemOwner!;
        const body: ChapterItemOwnerConfirmV1 = { item_id: target.item_id, expected_version: target.version, from_character_id: target.from_character_id, to_character_id: target.to_character_id, evidence: session.evidence!, basis: session.itemOwnerCheck!.result!.basis };
        return { action: "confirm-item-owner", target: target.item_id, body, key: crypto.randomUUID(), unknown: true };
      },
      update: (next) => { if (alive.current && epoch.current === request) { draftRef.current = next; setDraft(next); } },
      send: (command) => apiPost<ChapterItemOwnerResultV1>(`/api/chapter-records/novel/${novelId}/item-owner/confirm`, command.body, { headers: { "Idempotency-Key": command.key } }),
      readback: async () => {
        const latest = parseItemReadV1(await apiGet<unknown>(`/api/items/novel/${novelId}/${session.itemOwner!.item_id}`), novelId);
        if (alive.current) readbackRef.current(latest);
      },
    });
    if (alive.current && epoch.current === request) {
      if (outcome.ok) {
        draftRef.current = null; setDraft(null); setSource(null);
        onClose(true);
      } else {
        if (outcome.rolledBack) setChecked(false);
        const failure = outcome.error;
        setFieldErrors(failure instanceof ApiRequestError ? failure.fieldErrors : {});
        setError(`${outcome.draft.command?.saved ? t("savedPending") : outcome.stage === "register" ? t("localFailed") : outcome.draft.command?.unknown ? t("unknown") : ""} ${failure instanceof Error ? failure.message : t("saveFailed")}`.trim());
        requestAnimationFrame(() => { if (activeRef.current && epoch.current === request) focusRelationEditorError({}); });
      }
    }
    pending.current = false; if (alive.current) setSaving(false);
  };
  const target = draft?.itemOwner;
  const check = draft?.itemOwnerCheck;
  // 新版独立 B 退回后没有旧确认命令；仍须允许作者读取当前版本，再明确另建检查稿。
  const canReadCurrent = !draft?.itemFact && (rejected || !draft?.command && Boolean(draft?.review || draft?.itemCheckVersion === 2));
  const input = check?.result?.basis.flow_snapshot.business_input;
  const valid = Boolean(target && target.from_character_id && target.to_character_id && target.from_character_id !== target.to_character_id && draft?.evidence && check?.status === "adopted" && input && input.item_id === target.item_id && input.expected_version === target.version && input.from_character_id === target.from_character_id && input.to_character_id === target.to_character_id && source && input.source.chapter_id === source.chapter_id && input.source.revision_id === source.revision_id && input.source.version === source.version && input.source.content_hash === source.content_hash && draft.evidence.revision_id === source.revision_id);
  const currentTargetMatches = !draft?.review || Boolean(current && target && current.novel_id === novelId && current.item_id === target.item_id
    && !current.is_deleted && (draft.itemCheckVersion === 2 ? beforeState?.lifecycle_status === "held" && beforeState.owner_character_id === target.from_character_id : current.lifecycle_status === "held" && current.owner_character_id === target.from_character_id)
    && target.from_character_id !== target.to_character_id && currentCharacters.some((row) => row.character_id === target.to_character_id));

  /** 功能：作者核对当前物品后另建检查稿，关联审核保留原转交方向。Args: 无。Returns: 等待重新检查的新稿。 */
  const reviseDraft = async () => {
    const session = draftRef.current;
    if (!session || !current || pending.current || claiming || !claimed.current || !reviewChecked || !currentTargetMatches) return;
    if (!session.review) { openDraft(undefined, current); return; }
    if (session.command && (session.command.unknown !== false || session.command.saved)) return;
    pending.current = true; setSaving(true);
    const request = epoch.current;
    const queuedBeforeCancel = queue.current;
    // 中断回写可能增加 revision，不能拿点击前的草稿去替换成员。
    cancelCheck.current?.();
    try {
      await queuedBeforeCancel;
      await queue.current;
      const latestDraft = draftRef.current;
      if (!latestDraft || latestDraft.key !== session.key || epoch.current !== request) return;
      // 换物品版本不能修复已过期的章正文，保留原稿及原检查错误。
      const source = latestDraft.review!.source;
      const chapterNow = await apiGet<HierarchyRecord>(`/api/chapters/${source.chapter_id}`);
      const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(chapterNow.content ?? ""));
      if (!alive.current || !activeRef.current || epoch.current !== request) return;
      if (chapterNow.chapter_id !== source.chapter_id || chapterNow.novel_id !== novelId || chapterNow.is_deleted || Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("") !== source.content_hash) {
        setError(t("review.sourceOutdated")); return;
      }
      const revised = await reviseChapterCheckReviewDraft(scope, latestDraft, {
        ...latestDraft, key: crypto.randomUUID(), revision: 1, command: undefined, evidence: null, itemOwnerCheck: undefined,
        itemOwner: { ...latestDraft.itemOwner!, version: current.version },
      });
      if (alive.current && activeRef.current && epoch.current === request) openDraft(revised, null, true);
    } catch { if (alive.current && epoch.current === request) setError(t("localFailed")); }
    finally { pending.current = false; if (alive.current) setSaving(false); }
  };

  return <RetainedModalBackdrop isOpen={open} isDismissable={!saving && !claiming} isKeyboardDismissDisabled={saving || claiming} onOpenChange={(next) => { if (!next) void close(); }}>
      <Modal.Container scroll="inside">{draft && target && <Modal.Dialog className="h-[100dvh] w-full max-w-none p-0 sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
        <Modal.Header className="flex shrink-0 items-center justify-between gap-3 px-5 py-4 sm:px-7"><Modal.Heading>{t("itemOwner.title")}</Modal.Heading><Modal.CloseTrigger isDisabled={saving || claiming} /></Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 overflow-y-auto px-5 py-5 sm:px-7"><div data-testid="item-owner-editor" className="grid min-w-0 gap-4">
          {(error || localError) && <div id={`${id}-errors`}><RelationEditorErrorSummary message={error || localError} fieldErrors={fieldErrors} /></div>}
          {claiming && <p role="status">{t("loading")}</p>}
          {claimed.current && <><ChapterRecordCommandStatus draft={draft} />
          {draft.itemCheckVersion === 2 ? <><ItemFactValues value={draft.itemOwnerCheck?.result && "checked_facts" in draft.itemOwnerCheck.result ? draft.itemOwnerCheck.result.checked_facts.values : beforeState} choices={choices} />{(readingBefore || beforeError || !beforeState) && <p role={beforeError ? "alert" : "status"} className="text-sm text-muted">{beforeError || (readingBefore ? t("loading") : f("sourceRequired"))}</p>}</> : null}
          <dl className="detail-fields"><div><dt className="text-xs text-muted">{t("itemOwner.item")}</dt><dd className="reading-copy">{target.name}</dd></div><div><dt className="text-xs text-muted">{t("itemOwner.originalHolder", { version: target.version })}</dt><dd className="reading-copy">{target.from_name}</dd></div></dl>
          <label className="grid gap-1 text-xs text-muted">{t("itemOwner.newHolder")}<select name="to_character_id" className={INPUT} value={target.to_character_id} disabled={blocked || Boolean(draft.review)} onChange={(event) => {
            cancelCheck.current?.(); const selected = currentCharacters.find((row) => row.character_id === event.target.value);
            update({ ...draftRef.current!, evidence: null, itemOwner: { ...target, to_character_id: selected?.character_id ?? "", to_name: selected?.name ?? "" } });
          }}><option value="">{t("chooseCharacter")}</option>{target.to_character_id && !currentCharacters.some((row) => row.character_id === target.to_character_id) && <option value={target.to_character_id}>{target.to_name}</option>}{currentCharacters.filter((row) => row.character_id !== target.from_character_id).map((row) => <option key={row.character_id} value={row.character_id}>{row.name}</option>)}</select></label>
          {loading && <p role="status">{t("loading")}</p>}{loadError && <><RelationEditorErrorSummary message={loadError} /><Button variant="outline" onPress={() => setStructureRetry((value) => value + 1)}>{t("archiveRetry")}</Button></>}
          <EvidencePicker key={draft.key} novelId={novelId} chapters={chapters} value={draft.evidence} fixedSource={draft.review?.source} initialSource={draft.itemOwnerCheck?.source} disabled={blocked || loading || Boolean(loadError)} onSelectRevision={(next) => {
            cancelCheck.current?.();
            const current = draftRef.current;
            // Picker 在挂载、重验证和卸载时都会暂报 null；只有核验过的不同来源才作废原检查。
            if (next && current?.itemCheckVersion === 2 && !current.review && !current.command && !current.itemFact && current.itemOwnerCheck
              && (current.itemOwnerCheck.source.chapter_id !== next.chapter_id || current.itemOwnerCheck.source.revision_id !== next.revision_id
                || current.itemOwnerCheck.source.version !== next.version || current.itemOwnerCheck.source.content_hash !== next.content_hash)) update({ ...current, itemOwnerCheck: undefined, evidence: null });
            setSource(next); setChecked(false);
          }} onChange={(value) => { if (value === null && draftRef.current?.evidence) update({ ...draftRef.current, evidence: null }); }} onSelectEvidence={(evidence) => update({ ...draftRef.current!, evidence })} label={t("source")} />
          <PsychologicalStateCheck key={`check:${draft.key}`} mode="item-owner" novelId={novelId} draft={draft} source={source} blocked={blocked || readingBefore || Boolean(beforeError)} cancelRef={cancelCheck} onCheck={async (next) => {
            const currentDraft = draftRef.current;
            if (!currentDraft || currentDraft.key !== draft.key || currentDraft.command || currentDraft.itemFact) return;
            const updated = { ...currentDraft, itemOwnerCheck: next, revision: currentDraft.revision + 1 };
            draftRef.current = updated; setDraft(updated); setChecked(false); await persist(updated);
          }} onAdopt={(next) => {
            const currentDraft = draftRef.current;
            const suggestion = next.result?.candidate.suggestion;
            if (!currentDraft || currentDraft.key !== draft.key || currentDraft.command || !suggestion || currentDraft.itemOwnerCheck !== next) return;
            update({ ...currentDraft, chapterId: next.source.chapter_id, evidence: { ...next.source, start: suggestion.start, quote: suggestion.quote }, itemOwnerCheck: { ...next, status: "adopted" } });
          }} />
          {!draft.command && !draft.itemFact && <ChapterRecordAuthorConfirmation checked={checked} disabled={saving || !valid} onChange={setChecked} />}
          {!draft.command && !draft.itemFact && !valid && <p role="status" className="text-sm text-muted">{t("itemOwner.checkRequired")}</p>}
          {canReadCurrent && <div className="grid gap-3 border-t border-border pt-3"><Button variant="outline" isDisabled={reading || saving || claiming} onPress={async () => {
            const request = epoch.current; setReading(true); setCurrent(null); setReviewChecked(false); setError("");
            try { const latest = parseItemReadV1(await apiGet<unknown>(`/api/items/novel/${novelId}/${target.item_id}`), novelId); if (alive.current && epoch.current === request && activeRef.current) setCurrent(latest); }
            catch (failure) { if (alive.current && epoch.current === request) setError((failure as Error).message); }
            finally { if (alive.current && epoch.current === request) setReading(false); }
          }}>{t("readCurrent")}</Button>{current && <p className="reading-copy">{t("itemOwner.currentHolder", { version: current.version, name: holderName(current.owner_character_id) })}</p>}
            {current && !currentTargetMatches && <p role="alert" className="text-sm text-danger">{t(current.owner_character_id !== target.from_character_id ? "review.originalHolderChanged" : "review.targetChanged")}</p>}
            <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={reviewChecked} onChange={(event) => setReviewChecked(event.target.checked)} />{t("reviewConfirmed")}</label>
            <Button variant="outline" isDisabled={saving || claiming || reading || !reviewChecked || !current || current.is_deleted || (draft.itemCheckVersion !== 2 && (current.lifecycle_status !== "held" || !current.owner_character_id)) || !currentTargetMatches || Boolean(draft.review && draft.command && draft.command.unknown !== false)} onPress={() => void reviseDraft()}>{t("revise")}</Button></div>}
          </>}
        </div></Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex shrink-0 flex-wrap gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
          <Button variant="primary" isDisabled={saving || claiming || !claimed.current || check?.status === "running" || !draft.itemFact && (rejected || !draft.command && (!valid || !checked))} onPress={() => void submit()}>{draft.itemFact ? t("resume") : draft.itemCheckVersion === 2 && !draft.command ? f("prepareCheck") : t(saving ? "saving" : draft.command?.readbackDone ? "retryCleanup" : draft.command?.saved ? "retryRead" : draft.command ? "retryOriginal" : "confirm")}</Button>
          <Button variant="ghost" isDisabled={saving || claiming} onPress={() => void close()}>{t("closeKeepDraft")}</Button><ChapterRecordExport draft={draft} />
          {!draft.itemFact && (!draft.review || draft.command?.saved) && (!draft.command || rejected || draft.command.saved) && <Button variant="ghost" isDisabled={saving || claiming || !claimed.current} onPress={async () => {
            try { cancelCheck.current?.(); await queue.current; await remove(draftRef.current!); epoch.current += 1; draftRef.current = null; setDraft(null); onClose(false); }
            catch { setError(t("localFailed")); }
          }}>{t("discard")}</Button>}
        </Modal.Footer>
      </Modal.Dialog>}</Modal.Container>
    </RetainedModalBackdrop>;
}
