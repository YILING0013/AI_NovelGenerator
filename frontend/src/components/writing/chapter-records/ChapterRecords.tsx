"use client";

import { Button, Modal } from "@heroui/react";
import { useCallback, useContext, useEffect, useId, useRef, useState, type RefObject } from "react";
import { useLocale, useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import DocumentSection from "@/components/shared/DocumentSection";
import TagInput from "@/components/shared/TagInput";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { EntityChoices, HierarchyRecord } from "@/types/hierarchy";
import type { CharacterVolumeStateReadV1, CharacterVolumeStateListV1 } from "@/types/characterVolumeState";
import type { CharacterRelationResponseV1 } from "@/types/character";
import type { CharacterRelationFactReadResultV1 } from "@/types/characterRelationFacts";
import type { ItemFactRecordV1 } from "@/types/itemFacts";
import type { ChapterCharacterRelationConfirmV1, ChapterEventReadV1, ChapterReportReadV1, ChapterReportHeadReadV1, EntityStateHistoryReadV1, ChapterRecordEntityRefV1, ChapterPsychologicalCheckSourceV1 } from "@/types/chapterRecords";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import { readChapterRecordDrafts, writeChapterRecordDraft, claimChapterCheckReviewDraft, reviseChapterCheckReviewDraft, handoffChapterRelationFact, readChapterRelationFactHandoff, type ChapterCharacterRelationTarget, type ChapterRecordDraft } from "./chapterRecordDrafts";
import PsychologicalStateCheck from "./PsychologicalStateCheck";
import { WorldRuleSelection } from "./WorldRuleCheckReview";
import ChapterCheckReview from "./ChapterCheckReview";
import { confirmChapterRecord, useChapterRecordPersistence, type ChapterRecordReceipt } from "./chapterRecordConfirmation";
import { ChapterRecordAuthorConfirmation, ChapterRecordCommandStatus, ChapterRecordExport } from "./ChapterRecordConfirmationParts";
import CharacterFactsPanel from "../characters/CharacterFactsPanel";
import CharacterRelationFactPreparationDialog from "../characters/CharacterRelationFactPreparationDialog";
import CharacterRelationFactConfirmationDialog from "../characters/CharacterRelationFactConfirmationDialog";
import { reprepareChapterRelationFact, type CharacterRelationFactPreparationV1 } from "../characters/characterRelationFactPreparation";
import type { CharacterRelationFactDraftV1 } from "../characters/characterRelationFactDrafts";

const EMPTY_CHOICES: EntityChoices = { character_ids: [], faction_ids: [], location_ids: [], item_ids: [], rule_ids: [] };
const ENTITY_FIELDS = { character: "character_ids", faction: "faction_ids", location: "location_ids", item: "item_ids", world_rule: "rule_ids" } as const;
type RecordRow = ChapterEventReadV1 | ChapterReportReadV1 | EntityStateHistoryReadV1;

/** 功能：只保留关系检查所需的开始值。Args: row 当前关系。Returns: 固定端点、版本及原值。 */
function relationCheckTarget(row: CharacterRelationResponseV1): ChapterCharacterRelationTarget {
  const { relation_id, version, source_character_id, target_character_id, source_character_name, target_character_name, relation_type, current_state } = row;
  return { relation_id, version, source_character_id, target_character_id, source_character_name, target_character_name, relation_type, current_state };
}

/** 功能：查看原记录、真实状态变化与不可变修订证据。Args: props 记录及名称。Returns: 连续正文详情。 */
function RecordDetail({ row, novelId, choices }: { row: RecordRow; novelId: string; choices: EntityChoices }) {
  const t = useTranslations("writing.chapterRecords");
  const locale = useLocale();
  const [sourceOpen, setSourceOpen] = useState(false);
  const isHistory = "history_id" in row;
  return <div className="grid min-w-0 gap-3">
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
      <span>{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(row.confirmed_at))}</span>
      {!isHistory && <span>{t(row.voided_at ? "voided" : "confirmed")}</span>}
      {isHistory && <span>{t("versions", { before: row.before_version, after: row.after_version })}</span>}
      {isHistory && row.entity_type === "character_relation" && <span className="font-mono">{row.relation_id}</span>}
    </div>
    {row.needs_review && <p role="status" className="border-l-2 border-amber-500 px-3 text-sm">{t("needsReview")}</p>}
    {"content" in row && <p className="reading-copy whitespace-pre-wrap">{row.content}</p>}
    {"summary" in row && <><p className="reading-copy whitespace-pre-wrap">{row.summary}</p>{row.issues.length > 0 && <div><h5 className="mb-2 text-xs font-medium text-muted">{t("issues")}</h5><ul className="list-inside list-disc space-y-2">{row.issues.map((issue, index) => <li key={index} className="reading-copy whitespace-pre-wrap">{issue}</li>)}</ul></div>}</>}
    {isHistory && <div className="detail-fields">
      <div><h5 className="mb-1 text-xs font-medium text-muted">{t("before")}</h5><p className="reading-copy whitespace-pre-wrap">{row.entity_type === "item" ? choices.character_ids.find((choice) => choice.id === row.before.owner_character_id)?.name ?? row.before.owner_character_id : row.entity_type === "character_relation" ? row.before.current_state || t("emptyValue") : row.before.psychological_state || t("emptyValue")}</p></div>
      <div><h5 className="mb-1 text-xs font-medium text-muted">{t("after")}</h5><p className="reading-copy whitespace-pre-wrap">{row.entity_type === "item" ? choices.character_ids.find((choice) => choice.id === row.after.owner_character_id)?.name ?? row.after.owner_character_id : row.entity_type === "character_relation" ? row.after.current_state || t("emptyValue") : row.after.psychological_state || t("emptyValue")}</p></div>
    </div>}
    {!isHistory && row.related_entities.length > 0 && <div><h5 className="mb-1 text-xs font-medium text-muted">{t("relatedEntities")}</h5><ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm">{row.related_entities.map((ref) => <li key={`${ref.entity_type}:${ref.entity_id}`}>{Object.entries(ENTITY_FIELDS).find(([kind]) => kind === ref.entity_type)?.[1] ? choices[ENTITY_FIELDS[ref.entity_type as keyof typeof ENTITY_FIELDS]].find((choice) => choice.id === ref.entity_id)?.name ?? ref.entity_id : ref.entity_id}</li>)}</ul></div>}
    {!isHistory && row.voided_at && <p className="reading-copy whitespace-pre-wrap">{t("voidReason")}: {row.void_reason}</p>}
    <details open={sourceOpen} onToggle={(event) => setSourceOpen(event.currentTarget.open)}>
      <summary className="min-h-11 cursor-pointer py-2 text-sm text-accent focus-visible:outline-2 focus-visible:outline-accent">{t("source")}</summary>
      {sourceOpen && <EvidencePicker key={JSON.stringify(row.evidence)} novelId={novelId} chapters={[]} value={row.evidence} readOnly chapterRecordSource label={t("source")} />}
    </details>
  </div>;
}

/** 功能：在来源章查看记录并单独确认心理或人物关系现状。Args: props 本书和来源章；只读入口无需提供可编辑章。Returns: 章后记录与独立作者确认稿。 */
export default function ChapterRecords({ novelId, chapterId, chapter, choices = EMPTY_CHOICES, readOnly = false, refreshToken = 0, chapterReviewId, onNavigateItem, onBusy, onDirty, beforeLeaveRef, relationCheckVersion = 1 }: {
  novelId: string; chapterId: string; chapter?: HierarchyRecord; choices?: EntityChoices; readOnly?: boolean; refreshToken?: number;
  chapterReviewId?: string | null; onNavigateItem?: (itemId: string, chapterId: string, reviewId: string) => void;
  onBusy?: (busy: boolean) => void; onDirty?: (dirty: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  relationCheckVersion?: 1 | 2;
}) {
  const t = useTranslations("writing.chapterRecords");
  const characterT = useTranslations("writing.characters");
  const itemT = useTranslations("writing.items");
  const itemFactT = useTranslations("writing.itemFacts");
  const factT = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const id = useId();
  const base = `/api/chapter-records/novel/${novelId}`;
  const scope = `${novelId}:chapter:${chapterId}:chapter-records`;
  const [events, setEvents] = useState<ChapterEventReadV1[]>([]);
  const [reports, setReports] = useState<ChapterReportReadV1[]>([]);
  const [history, setHistory] = useState<EntityStateHistoryReadV1[]>([]);
  const [itemHistory, setItemHistory] = useState<ItemFactRecordV1[]>([]);
  const [itemSourceIds, setItemSourceIds] = useState<string[]>([]);
  const [head, setHead] = useState<ChapterReportHeadReadV1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [drafts, setDrafts] = useState<ChapterRecordDraft[]>([]);
  const [draft, setDraft] = useState<ChapterRecordDraft | null>(null);
  const [states, setStates] = useState<CharacterVolumeStateReadV1[]>([]);
  const [statesLoading, setStatesLoading] = useState(false);
  const [statesError, setStatesError] = useState("");
  const [factSession, setFactSession] = useState<{ novelId: string; chapterId: string } | null>(null);
  const [factCharacterId, setFactCharacterId] = useState("");
  const [factsBusy, setFactsBusy] = useState(false);
  const [factsClosing, setFactsClosing] = useState(false);
  const [factsError, setFactsError] = useState("");
  const factBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const [relationSession, setRelationSession] = useState<({ preparation: CharacterRelationFactPreparationV1 } | { draft: CharacterRelationFactDraftV1 }) & { epoch: number } | null>(null);
  const [relationBusy, setRelationBusy] = useState(false);
  const relationBeforeLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const [relations, setRelations] = useState<CharacterRelationResponseV1[]>([]);
  const [relationsLoading, setRelationsLoading] = useState(false);
  const [relationsError, setRelationsError] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { queue, persisted, persist, remove, localError, setLocalError } = useChapterRecordPersistence(scope, t("localFailed"));
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [checked, setChecked] = useState(false);
  const [message, setMessage] = useState("");
  const [currentRead, setCurrentRead] = useState<ChapterReportHeadReadV1 | CharacterVolumeStateReadV1 | CharacterRelationResponseV1 | null>(null);
  const [reviewChecked, setReviewChecked] = useState(false);
  const [readingCurrent, setReadingCurrent] = useState(false);
  const [checkSource, setCheckSource] = useState<ChapterPsychologicalCheckSourceV1 | null>(null);
  const cancelCheck = useRef<(() => void) | null>(null);
  const draftRef = useRef(draft);
  const pending = useRef(false);
  const openingRef = useRef(false);
  const [opening, setOpening] = useState(false);
  const alive = useRef(true);
  const epoch = useRef(0);
  const loadEpoch = useRef(0);
  const context = useRef({ active, chapterId }); context.current = { active, chapterId };
  const writable = !readOnly && Boolean(chapter && !chapter.is_deleted);
  const factsOpen = factSession?.novelId === novelId && factSession.chapterId === chapterId;
  const blocked = saving || Boolean(draft?.command);
  const voiding = draft?.mode === "void-event" || draft?.mode === "void-report";
  const fixedSource = draft?.review?.source;
  const relationTarget = draft?.relationTarget;
  const relationFactsMode = draft?.mode === "character-relation-state" && draft.relationCheckVersion === 2;
  const relationInput = draft?.relationCheck?.result?.basis.flow_snapshot.business_input;
  const relationSourceReady = Boolean(checkSource && relationInput && relationInput.source.chapter_id === checkSource.chapter_id
    && relationInput.source.revision_id === checkSource.revision_id && relationInput.source.version === checkSource.version
    && relationInput.source.content_hash === checkSource.content_hash && draft?.evidence
    && draft.evidence.chapter_id === checkSource.chapter_id && draft.evidence.revision_id === checkSource.revision_id
    && draft.evidence.version === checkSource.version && draft.evidence.content_hash === checkSource.content_hash);
  const relationCheckReady = Boolean(relationTarget && relationInput && draft?.relationCheck?.status === "adopted" && relationSourceReady
    && relationInput.novel_id === novelId && relationInput.relation_id === relationTarget.relation_id && relationInput.expected_version === relationTarget.version);
  const relationStateLength = Array.from(draft?.relationState?.trim() ?? "").length;
  const relationValueValid = relationStateLength >= 1 && relationStateLength <= 2000;
  const relationValid = relationCheckReady && relationValueValid;
  const relationStateErrors = !draft?.command && relationTarget && !relationValueValid ? [t("relationState.lengthError")] : fieldErrors.current_state;
  // 恢复稿里的引文不代表本次已核验原文；首次确认须等固定修订加载并核验完成。
  const reviewSourceReady = !fixedSource || Boolean(checkSource && checkSource.chapter_id === fixedSource.chapter_id
    && checkSource.revision_id === fixedSource.revision_id && checkSource.version === fixedSource.version
    && checkSource.content_hash === fixedSource.content_hash);

  useEffect(() => { alive.current = true; return () => { alive.current = false; epoch.current += 1; loadEpoch.current += 1; }; }, []);
  useEffect(() => { onBusy?.(saving || opening || factsBusy || factsClosing || relationBusy); return () => onBusy?.(false); }, [saving, opening, factsBusy, factsClosing, relationBusy, onBusy]);
  useEffect(() => { onDirty?.(Boolean(draft) || factsOpen || Boolean(relationSession)); return () => onDirty?.(false); }, [draft, factsOpen, relationSession, onDirty]);
  useEffect(() => {
    if (!active || !beforeLeaveRef) return;
    beforeLeaveRef.current = async () => {
      if (pending.current || openingRef.current || factsBusy || factsClosing || relationBusy) throw new Error(t("saving"));
      cancelCheck.current?.();
      try {
        if (factsOpen) await factBeforeLeaveRef.current?.();
        if (relationSession) await relationBeforeLeaveRef.current?.();
        if (draftRef.current) await persist(draftRef.current);
        await queue.current;
        epoch.current += 1; draftRef.current = null; setDraft(null); setFactSession(null); setRelationSession(null);
      } catch (failure) { if (factsOpen) setFactsError(t("localFailed")); else setError(t("localFailed")); throw new Error(t("localFailed"), { cause: failure }); }
    };
    return () => { beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef, t, queue, persist, factsBusy, factsClosing, factsOpen, relationBusy, relationSession]);
  useEffect(() => {
    if (!active || !draft) return;
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [active, draft]);

  const readLists = useCallback(async (signal?: AbortSignal) => {
    const request = ++loadEpoch.current;
    const result = await Promise.all([
      apiGet<ChapterEventReadV1[]>(`${base}/events?chapter_id=${chapterId}`, { signal }),
      apiGet<ChapterReportReadV1[]>(`${base}/reports?chapter_id=${chapterId}`, { signal }),
      apiGet<EntityStateHistoryReadV1[]>(`${base}/state-history?chapter_id=${chapterId}`, { signal }),
      apiGet<ChapterReportHeadReadV1>(`${base}/chapters/${chapterId}/report`, { signal }),
    ]);
    // 新物品记录保留完整四项状态，不改旧 state-history 的响应形状。
    const itemRows: ItemFactRecordV1[] = [];
    let page: ItemFactRecordV1[];
    do {
      page = await apiGet<ItemFactRecordV1[]>(`${base}/item-facts/history?chapter_id=${chapterId}&limit=100${itemRows.length ? `&before_id=${itemRows.at(-1)!.history_id}` : ""}`, { signal });
      itemRows.push(...page);
    } while (page.length === 100);
    if (signal?.aborted || !alive.current || request !== loadEpoch.current || !context.current.active) return;
    setEvents(result[0]); setReports(result[1]); setHistory(result[2]); setItemHistory(itemRows); setHead(result[3]); setLoadError("");
  }, [base, chapterId]);

  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    setLoading(true);
    void readLists(abort.signal).catch((failure) => { if (!abort.signal.aborted) setLoadError(failure.message); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    if (!readOnly) void readChapterRecordDrafts(scope).then((rows) => { if (!abort.signal.aborted) { setDrafts(rows); setLocalError(""); } }).catch(() => { if (!abort.signal.aborted) setLocalError(t("localFailed")); });
    return () => { abort.abort(); loadEpoch.current += 1; };
  }, [active, readLists, scope, refresh, refreshToken, t, readOnly, setLocalError]);

  useEffect(() => {
    if (!active || !factsOpen || !chapter) return;
    const abort = new AbortController();
    setStatesLoading(true); setStates([]); setStatesError("");
    void apiGet<CharacterVolumeStateListV1>(`/api/character-volume-states/novel/${novelId}/volume/${chapter.volume_id}?status=active`, { signal: abort.signal }).then((page) => {
      if (!abort.signal.aborted) setStates(page.data.filter((row) => row.novel_id === novelId && row.volume_id === chapter.volume_id && !row.is_deleted));
    }).catch((failure) => { if (!abort.signal.aborted) setStatesError(failure.message); }).finally(() => { if (!abort.signal.aborted) setStatesLoading(false); });
    return () => abort.abort();
  }, [active, factsOpen, chapter, novelId, refresh]);

  const closeFacts = async () => {
    if (factsBusy || factsClosing) return;
    setFactsClosing(true); setFactsError("");
    try { await factBeforeLeaveRef.current?.(); setFactSession(null); }
    catch (failure) { setFactsError(failure instanceof Error ? failure.message : t("localFailed")); }
    finally { setFactsClosing(false); }
  };

  const changeDraft = (next: ChapterRecordDraft) => {
    const updated = { ...next, revision: (draftRef.current?.revision ?? 0) + 1 };
    draftRef.current = updated; setDraft(updated); setChecked(false); void persist(updated);
  };
  const openDraft = async (mode: ChapterRecordDraft["mode"], restored?: ChapterRecordDraft, row?: ChapterEventReadV1 | ChapterReportReadV1, preparedDraft = false) => {
    if (openingRef.current || pending.current) return;
    openingRef.current = true; setOpening(true);
    const request = epoch.current;
    const sourceChapter = context.current.chapterId;
    try {
      // 作者明确换稿时使用刚准备的内容；清单恢复才重新核对本机原稿。
      if (restored?.review && !preparedDraft) {
        restored = await claimChapterCheckReviewDraft(scope, restored);
      } else if (restored?.mode === "character-relation-state" && !preparedDraft) {
        // 清单可能来自另一标签交接之前；只重读本机稿，不更换检查时的正式版本。
        const current = (await readChapterRecordDrafts(scope)).find((item) => item.key === restored!.key);
        if (!current) throw new Error(t("localFailed"));
        restored = current;
      }
      if (!alive.current || !context.current.active || epoch.current !== request || context.current.chapterId !== sourceChapter) return;
      if (restored?.relationFact && (!restored.command || restored.command.unknown === false && !restored.command.saved)) {
        const linked = await readChapterRelationFactHandoff(novelId, restored.relationFact);
        if (!alive.current || !context.current.active || epoch.current !== request || context.current.chapterId !== sourceChapter) return;
        epoch.current += 1;
        if (linked.draft) setRelationSession({ draft: linked.draft, epoch: epoch.current });
        else if (linked.preparation) setRelationSession({ preparation: linked.preparation, epoch: epoch.current });
        else if (linked.operation?.saved) setMessage(t("saved"));
        else setLocalError(t("relationCheck.handoffMissing"));
        return;
      }
      cancelCheck.current?.(); setCheckSource(null);
      epoch.current += 1; setError(""); setFieldErrors({}); setChecked(false); setCurrentRead(null); setReviewChecked(false); setStatesError(""); setRelationsError(""); setReadingCurrent(false); setStatesLoading(false); setRelationsLoading(false);
      let next: ChapterRecordDraft = restored?.review || restored?.relationCheckVersion === 2 ? restored : restored ? { ...restored, key: crypto.randomUUID(), revision: 1, ...(restored.command ? { command: { ...restored.command, readbackDone: false } } : {}), ...(restored.check ? { check: { ...restored.check, status: restored.check.status === "running" ? "interrupted" : restored.check.status } } : {}), ...(restored.worldRuleCheck ? { worldRuleCheck: { ...restored.worldRuleCheck, status: restored.worldRuleCheck.status === "running" ? "interrupted" : restored.worldRuleCheck.status } } : {}), ...(restored.relationCheck ? { relationCheck: { ...restored.relationCheck, status: restored.relationCheck.status === "running" ? "interrupted" : restored.relationCheck.status } } : {}) } : {
        key: crypto.randomUUID(), revision: 1, mode, chapterId, title: row && "title" in row ? row.title : "", content: "", summary: "", issues: [], psychologicalState: "", reason: "", evidence: row?.evidence ?? null, relatedEntities: [], targetState: null, expectedReportVersion: head?.report_version ?? 0, recordId: row ? "event_id" in row ? row.event_id : row.report_id : null, ...(mode === "character-relation-state" ? { relationCheckVersion } : {}),
      };
      draftRef.current = next; setDraft(next);
      if (next.review || restored?.relationCheckVersion === 2) {
        persisted.current.set(next.key, next.revision);
        if (next.relationCheckVersion === 2 && next.relationCheck?.status === "running") {
          next = { ...next, revision: next.revision + 1, relationCheck: { ...next.relationCheck, status: "interrupted" } };
          draftRef.current = next; setDraft(next); await persist(next);
        }
      } else void persist(next);
      if (mode === "psychological-state" && !next.command && chapter) {
        const request = epoch.current;
        setStatesLoading(true); setStates([]);
        void apiGet<CharacterVolumeStateListV1>(`/api/character-volume-states/novel/${novelId}/volume/${chapter.volume_id}?status=active`).then((page) => {
          if (alive.current && epoch.current === request) setStates(page.data);
        }).catch((failure) => { if (alive.current && epoch.current === request) setStatesError(failure.message); }).finally(() => { if (alive.current && epoch.current === request) setStatesLoading(false); });
      }
      if (mode === "character-relation-state" && !next.command) {
        const request = epoch.current;
        setRelationsLoading(true); setRelations([]);
        void apiGet<{ data: CharacterRelationResponseV1[] }>(`/api/character-relations/novel/${novelId}?is_active=true`).then((page) => {
          if (alive.current && epoch.current === request) setRelations(page.data.filter((row) => row.novel_id === novelId && row.is_active && !row.is_deleted));
        }).catch((failure) => { if (alive.current && epoch.current === request) setRelationsError(failure.message); }).finally(() => { if (alive.current && epoch.current === request) setRelationsLoading(false); });
      }
    } catch { setLocalError(t("localFailed")); }
    finally { openingRef.current = false; if (alive.current) setOpening(false); }
  };
  const closeEditor = async () => {
    if (pending.current) return;
    cancelCheck.current?.();
    try {
      if (draftRef.current) await persist(draftRef.current);
      epoch.current += 1; draftRef.current = null; setDraft(null); setError("");
      setDrafts(await readChapterRecordDrafts(scope));
    } catch { setError(t("localFailed")); }
  };

  /** 功能：采用原建议后交给已有人工准备流程，原检查稿和旧请求始终保留。Args: 无。Returns: 本地事务完成后切换确认层。 */
  const prepareRelationFact = async () => {
    const original = draftRef.current;
    if (!original || pending.current || original.relationFact || original.command && (original.command.saved || original.command.unknown !== false)) return;
    pending.current = true; setSaving(true); setError("");
    const request = epoch.current;
    try {
      await queue.current;
      if (draftRef.current?.key !== original.key || epoch.current !== request) return;
      const handed = await handoffChapterRelationFact(novelId, scope, draftRef.current);
      persisted.current.set(handed.draft.key, handed.draft.revision);
      if (!alive.current || epoch.current !== request) return;
      epoch.current += 1; draftRef.current = null; setDraft(null);
      if (context.current.active) setRelationSession({ preparation: handed.preparation, epoch: epoch.current });
      setDrafts(await readChapterRecordDrafts(scope));
    } catch (failure) { if (alive.current && epoch.current === request) setError(failure instanceof Error ? failure.message : t("localFailed")); }
    finally { pending.current = false; if (alive.current) setSaving(false); }
  };

  const readCurrent = async () => {
    const session = draftRef.current;
    if (!session || pending.current) return;
    const request = epoch.current;
    setReadingCurrent(true); setError(""); setCurrentRead(null); setReviewChecked(false);
    try {
      const value = session.mode === "report" ? await apiGet<ChapterReportHeadReadV1>(`${base}/chapters/${chapterId}/report`)
        : session.mode === "character-relation-state" && session.relationTarget ? await apiGet<CharacterRelationResponseV1>(`/api/character-relations/novel/${novelId}/${session.relationTarget.relation_id}`)
        : session.targetState ? await apiGet<CharacterVolumeStateReadV1>(`/api/character-volume-states/novel/${novelId}/${session.targetState.state_id}`) : null;
      if (alive.current && request === epoch.current && context.current.active) setCurrentRead(value);
    } catch (failure) { if (alive.current && request === epoch.current) setError((failure as Error).message); }
    finally { if (alive.current && request === epoch.current) setReadingCurrent(false); }
  };

  /** 功能：作者核对当前资料后换稿，关联稿只替换自己的成员。Args: 无。Returns: 保留原来源和作者输入的新稿。 */
  const reviseDraft = async () => {
    const session = draftRef.current;
    if (!session || pending.current || !readyToRevise || !writable) return;
    if (session.review) {
      if (session.command && (session.command.unknown !== false || session.command.saved)) return;
      pending.current = true; setSaving(true);
      const request = epoch.current;
      const queuedBeforeCancel = queue.current;
      // 取消会先把检查中断写回原稿；等它落盘后再取最新 revision 和作者输入。
      cancelCheck.current?.();
      try {
        await queuedBeforeCancel;
        await queue.current;
        const current = draftRef.current;
        if (!current || current.key !== session.key || epoch.current !== request) return;
        // 换目标版本不能修复已过期的章正文，保留原稿及原检查错误。
        const source = current.review!.source;
        const chapterNow = await apiGet<HierarchyRecord>(`/api/chapters/${source.chapter_id}`);
        const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(chapterNow.content ?? ""));
        if (!alive.current || !context.current.active || epoch.current !== request) return;
        if (chapterNow.chapter_id !== source.chapter_id || chapterNow.novel_id !== novelId || chapterNow.is_deleted || Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("") !== source.content_hash) {
          setError(t("review.sourceOutdated")); return;
        }
        const next: ChapterRecordDraft = {
          ...current, key: crypto.randomUUID(), revision: 1, command: undefined, evidence: null, check: undefined, relationCheck: undefined,
          targetState: currentRead && "state_id" in currentRead ? { ...current.targetState!, version: currentRead.version, psychological_state: currentRead.psychological_state } : current.targetState,
          relationTarget: currentRead && "relation_id" in currentRead ? relationCheckTarget(currentRead) : current.relationTarget,
        };
        const revised = await reviseChapterCheckReviewDraft(scope, current, next);
        pending.current = false;
        if (alive.current && context.current.active && epoch.current === request) await openDraft(revised.mode, revised, undefined, true);
      } catch { if (alive.current && epoch.current === request) setError(t("localFailed")); }
      finally { pending.current = false; if (alive.current) setSaving(false); }
      return;
    }
    const next = { ...session, command: undefined,
      expectedReportVersion: currentRead && "report_version" in currentRead ? currentRead.report_version : session.expectedReportVersion,
      targetState: currentRead && "state_id" in currentRead ? { ...session.targetState!, version: currentRead.version, psychological_state: currentRead.psychological_state } : session.targetState,
    };
    if (session.mode === "character-relation-state" && currentRead && "relation_id" in currentRead) {
      await openDraft(session.mode, { ...next, relationTarget: relationCheckTarget(currentRead), relationCheck: undefined, evidence: null }, undefined, true);
    } else await openDraft(next.mode, next, undefined, true);
  };

  const submit = async () => {
    if (pending.current || !draftRef.current || draftRef.current.check?.status === "running" || draftRef.current.relationCheck?.status === "running" || draftRef.current.worldRuleCheck?.status === "running") return;
    const session = draftRef.current;
    if (!session.command && (session.relationCheckVersion === 2 || session.relationFact)) return;
    if (!session.command && (!checked || !writable || !reviewSourceReady || session.mode === "character-relation-state" && !relationValid)) return;
    pending.current = true; setSaving(true); setError(""); setFieldErrors({});
    const request = epoch.current;
    const outcome = await confirmChapterRecord({
      draft: session, persist, remove,
      command: () => {
        if (session.mode === "character-relation-state") {
          const body: ChapterCharacterRelationConfirmV1 = { relation_id: session.relationTarget!.relation_id, expected_version: session.relationTarget!.version, current_state: session.relationState!, evidence: session.evidence!, basis: session.relationCheck!.result!.basis };
          return { action: "confirm-character-relation-state", target: session.relationTarget!.relation_id, body, key: crypto.randomUUID(), unknown: true };
        }
        const action = session.mode === "event" ? "create-event" : session.mode === "report" ? "create-report" : session.mode === "psychological-state" ? "patch-psychological-state" : session.mode === "void-event" ? "void-event" : "void-report";
        const body = session.mode === "event" ? { title: session.title, content: session.content, evidence: session.evidence, related_entities: session.relatedEntities }
          : session.mode === "report" ? { expected_report_version: session.expectedReportVersion, summary: session.summary, issues: session.issues, evidence: session.evidence, related_entities: session.relatedEntities }
          : session.mode === "psychological-state" ? { state_id: session.targetState!.state_id, expected_version: session.targetState!.version, psychological_state: session.psychologicalState, evidence: session.evidence }
          : { reason: session.reason };
        return { action, target: session.recordId ?? session.targetState?.state_id ?? chapterId, body, key: crypto.randomUUID(), unknown: true };
      },
      update: (next) => { if (alive.current && epoch.current === request) { draftRef.current = next; setDraft(next); } },
      send: (command) => {
        const path = command.action === "create-event" ? "/events" : command.action === "create-report" ? "/reports" : command.action === "patch-psychological-state" ? "/psychological-state" : command.action === "confirm-character-relation-state" ? "/character-relation-state/confirm" : `/${command.action === "void-event" ? "events" : "reports"}/${command.target}/void`;
        return apiPost<ChapterRecordReceipt>(`${base}${path}`, command.body, { headers: { "Idempotency-Key": command.key } });
      },
      readback: async (result) => {
        if ("event_id" in result) await apiGet<ChapterEventReadV1>(`${base}/events/${result.event_id}`);
        else if ("report_id" in result) await apiGet<ChapterReportReadV1>(`${base}/reports/${result.report_id}`);
        else if ("state_id" in result) await apiGet<CharacterVolumeStateReadV1>(`/api/character-volume-states/novel/${novelId}/${result.state_id}`);
        else if ("relation_id" in result) await apiGet<CharacterRelationResponseV1>(`/api/character-relations/novel/${novelId}/${result.relation_id}`);
        await readLists();
      },
    });
    if (alive.current && epoch.current === request) {
      if (outcome.ok) {
        draftRef.current = null; setDraft(null);
        try { setDrafts(await readChapterRecordDrafts(scope)); } catch { setLocalError(t("localFailed")); }
        if (context.current.active) setMessage("history" in outcome.receipt && outcome.receipt.history === null ? t("noChangeSaved") : t("saved"));
      } else {
        const failure = outcome.error;
        if (outcome.rolledBack) setChecked(false);
        setFieldErrors(failure instanceof ApiRequestError ? failure.fieldErrors : {});
        setError(`${outcome.draft.command?.saved ? t("savedPending") : outcome.stage === "register" ? t("localFailed") : outcome.draft.command?.unknown ? t("unknown") : ""} ${failure instanceof Error ? failure.message : t("saveFailed")}`.trim());
        requestAnimationFrame(() => { if (context.current.active && epoch.current === request) focusRelationEditorError(outcome.draft.command ? {} : failure instanceof ApiRequestError ? failure.fieldErrors : {}); });
      }
    }
    pending.current = false; if (alive.current) setSaving(false);
  };

  const valid = draft && (voiding ? Boolean(draft.reason.trim()) : Boolean(draft.evidence) && (draft.mode === "event" ? Boolean(draft.title.trim() && draft.content.trim()) : draft.mode === "report" ? Boolean(draft.summary.trim()) : draft.mode === "character-relation-state" ? relationValid : Boolean(draft.targetState) && reviewSourceReady));
  const rejected = Boolean(draft?.command && !draft.command.saved && draft.command.unknown === false);
  const currentTargetMatches = !draft?.review || Boolean(currentRead && (
    draft.mode === "psychological-state" && "state_id" in currentRead && currentRead.novel_id === novelId && !currentRead.is_deleted
      && currentRead.state_id === draft.targetState?.state_id && currentRead.character_id === draft.targetState.character_id && currentRead.volume_id === draft.targetState.volume_id
    || draft.mode === "character-relation-state" && "relation_id" in currentRead && currentRead.novel_id === novelId && currentRead.is_active && !currentRead.is_deleted
      && currentRead.relation_id === draft.relationTarget?.relation_id && currentRead.source_character_id === draft.relationTarget.source_character_id && currentRead.target_character_id === draft.relationTarget.target_character_id
  ));
  const readyToRevise = currentTargetMatches && (draft?.mode === "character-relation-state" ? Boolean(currentRead && "relation_id" in currentRead && currentRead.novel_id === novelId && currentRead.is_active && !currentRead.is_deleted) && reviewChecked : draft?.mode === "report" || draft?.mode === "psychological-state" ? Boolean(currentRead) && reviewChecked : reviewChecked);
  const relationName = (value: ChapterCharacterRelationTarget) => `${value.source_character_name ?? value.source_character_id} / ${value.target_character_name ?? value.target_character_id} · ${characterT(`options.relationType.${value.relation_type}`)}`;
  const draftTitle = (value: ChapterRecordDraft) => value.title || (value.mode === "report" ? t("reportVersion", { version: value.expectedReportVersion + 1 }) : value.relationTarget ? relationName(value.relationTarget) : value.targetState?.name || t(`modes.${value.mode}`));

  // 弹窗已隔离背景交互；入口保持可聚焦，交给 HeroUI 在关闭后恢复焦点。
  return <section data-testid="chapter-records" aria-label={t("title")} className="grid min-w-0 gap-4">
    <header className="flex flex-wrap items-center justify-between gap-2"><h2 className="sr-only">{t("title")}</h2><Button size="sm" variant="ghost" isDisabled={loading || saving} onPress={() => setRefresh((value) => value + 1)}>{t("refresh")}</Button></header>
    {(readOnly || chapter?.is_deleted) && <p role="status" className="border-l-2 border-amber-500 px-3 text-sm">{t("readOnly")}</p>}
    {loadError && <RelationEditorErrorSummary message={loadError} />}
    {localError && !draft && !readOnly && <RelationEditorErrorSummary message={localError} />}
    {loading && <p role="status">{t("loading")}</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    {writable && chapter && <ChapterCheckReview novelId={novelId} chapter={chapter} choices={choices} relationCheckVersion={relationCheckVersion} itemCheckVersion={2} selectedReviewId={chapterReviewId} disabled={saving || loading || Boolean(loadError)} opening={opening} refreshToken={`${refresh}:${refreshToken}:${draft?.key ?? ""}`} onResumeDraft={(stored) => { void openDraft(stored.mode, stored); }} onNavigateItem={onNavigateItem} />}
    {!readOnly && drafts.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("localDrafts", { count: drafts.length })}</summary><ul className="divide-y divide-border">{drafts.map((stored) => <li key={stored.key} className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2"><span className="min-w-0 break-words text-sm">{draftTitle(stored)} · {t(stored.command?.saved ? "savedPending" : stored.command && stored.command.unknown !== false ? "unknown" : stored.command ? "rejected" : "draft")}</span><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" isDisabled={saving} aria-disabled={opening || undefined} onPress={() => { if (!openingRef.current) void openDraft(stored.mode, stored); }}>{t("resume")}</Button>{!stored.relationFact && (!stored.review || stored.command?.saved) && (!stored.command || stored.command.unknown === false || stored.command.saved) && <Button size="sm" variant="ghost" isDisabled={Boolean(draft) || saving} onPress={async () => {
      try { await writeChapterRecordDraft(scope, stored, stored.revision, true); setDrafts(await readChapterRecordDrafts(scope)); setLocalError(""); }
      catch { setLocalError(t("localFailed")); }
    }}>{t("discard")}</Button>}</div></li>)}</ul></details>}
    <DocumentSection number="01" title={t("events")}>
      {writable && <Button size="sm" variant="outline" isDisabled={loading || Boolean(loadError)} onPress={() => openDraft("event")}>{t("confirmEvent")}</Button>}
      {!loading && events.length === 0 && <p className="py-3 text-sm text-muted">{t("noEvents")}</p>}
      <ul className="divide-y divide-border">{events.map((row) => <li key={row.event_id} data-record-id={row.event_id} className="grid min-w-0 gap-3 py-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="min-w-0 break-words text-base font-semibold">{row.title}</h4>{writable && !row.voided_at && <Button size="sm" variant="ghost" className="text-danger" onPress={() => openDraft("void-event", undefined, row)}>{t("voidEvent")}</Button>}</div><RecordDetail row={row} novelId={novelId} choices={choices} /></li>)}</ul>
    </DocumentSection>
    <DocumentSection number="02" title={t("reports")}>
      <div className="flex flex-wrap items-center gap-3">{writable && <Button size="sm" variant="outline" isDisabled={loading || Boolean(loadError) || !head} onPress={() => openDraft("report")}>{t("addReport")}</Button>}{head && <span className="text-xs text-muted">{head.report_version === 0 ? t("noReport") : head.report ? t("currentReport", { version: head.report_version }) : t("voidHead", { version: head.report_version })}</span>}</div>
      <ul className="divide-y divide-border">{reports.map((row) => <li key={row.report_id} data-record-id={row.report_id} className="grid min-w-0 gap-3 py-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-base font-semibold">{t("reportVersion", { version: row.report_version })}</h4>{writable && !row.voided_at && <Button size="sm" variant="ghost" className="text-danger" onPress={() => openDraft("void-report", undefined, row)}>{t("voidReport")}</Button>}</div><RecordDetail row={row} novelId={novelId} choices={choices} /></li>)}</ul>
    </DocumentSection>
    <DocumentSection number="03" title={t("history")}>
      {writable && <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" isDisabled={loading || Boolean(loadError)} onPress={() => { setFactCharacterId(""); setFactsError(""); setFactSession({ novelId, chapterId }); }}>{t("confirmState")}</Button><Button size="sm" variant="outline" isDisabled={loading || Boolean(loadError)} onPress={() => openDraft("character-relation-state")}>{t("relationState.confirmState")}</Button></div>}
      {!loading && history.length === 0 && itemHistory.length === 0 && <p className="py-3 text-sm text-muted">{t("noHistory")}</p>}
      <ul className="divide-y divide-border">{itemHistory.map((row) => <li key={row.history_id} data-record-id={row.history_id} className="grid min-w-0 gap-3 py-4">
        <h4 className="break-words text-base font-semibold">{choices.item_ids.find((choice) => choice.id === row.item_id)?.name ?? row.item_name} · {itemFactT(`operations.${row.operation}`)}</h4>
        <p className="text-xs text-muted">{factT(`validityStates.${row.validity.state}`)} · {t("versions", { before: row.before_version ?? 0, after: row.after_version })}</p>
        <div className="detail-fields">{(["before", "after"] as const).map((side) => {
          const values = side === "before" ? row.before.values : row.after;
          return <section key={side} className="min-w-0 space-y-2"><h5 className="text-xs font-medium text-muted">{t(side)}</h5>{values ? <dl className="grid gap-2 text-sm">
            <div><dt className="text-muted">{itemT("fields.status")}</dt><dd>{itemT(`status.${values.lifecycle_status}`)}</dd></div>
            {([{ field: "owner_character_id", label: "owner", choices: choices.character_ids }, { field: "controlling_faction_id", label: "faction", choices: choices.faction_ids }, { field: "current_location_id", label: "location", choices: choices.location_ids }] as const).map((ref) => <div key={ref.field}><dt className="text-muted">{itemT(`fields.${ref.label}`)}</dt><dd className="break-words">{ref.choices.find((choice) => choice.id === values[ref.field])?.name ?? values[ref.field] ?? itemFactT("none")}</dd></div>)}
          </dl> : <p>{itemFactT("unknown")}</p>}</section>;
        })}</div>
        {row.source.kind === "author" ? <p className="reading-copy whitespace-pre-wrap">{row.source.note}</p> : <details onToggle={(event) => { const open = event.currentTarget.open; setItemSourceIds((current) => open ? [...current.filter((id) => id !== row.history_id), row.history_id] : current.filter((id) => id !== row.history_id)); }}><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("source")}</summary>{itemSourceIds.includes(row.history_id) && <EvidencePicker novelId={novelId} chapters={[]} value={row.source.evidence} readOnly chapterRecordSource label={t("source")} />}</details>}
      </li>)}</ul>
      <ul className="divide-y divide-border">{history.map((row) => <li key={row.history_id} data-record-id={row.history_id} className="grid min-w-0 gap-3 py-4"><h4 className="min-w-0 break-words text-base font-semibold">{row.entity_type === "item" ? `${choices.item_ids.find((choice) => choice.id === row.item_id)?.name ?? row.item_id} · ${t("itemOwner.holder")}` : row.entity_type === "character_relation" ? `${choices.character_ids.find((choice) => choice.id === row.source_character_id)?.name ?? row.source_character_id} / ${choices.character_ids.find((choice) => choice.id === row.target_character_id)?.name ?? row.target_character_id} · ${t("relationState.currentState")}` : choices.character_ids.find((choice) => choice.id === row.character_id)?.name ?? row.character_id}</h4><RecordDetail row={row} novelId={novelId} choices={choices} /></li>)}</ul>
    </DocumentSection>

    <RetainedModalBackdrop isOpen={factsOpen} isDismissable={!factsBusy && !factsClosing} isKeyboardDismissDisabled={factsBusy || factsClosing} onOpenChange={(open) => { if (!open) void closeFacts(); }}>
      <Modal.Container scroll="inside">{factsOpen && <Modal.Dialog className="h-[100dvh] w-full max-w-none p-0 sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
        <Modal.Header className="flex shrink-0 items-center justify-between gap-3 px-5 py-4 sm:px-7"><Modal.Heading>{t("factConfirmation")}</Modal.Heading><Modal.CloseTrigger isDisabled={factsBusy || factsClosing} /></Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 overflow-y-auto px-5 py-5 sm:px-7">
          <div className="grid min-w-0 gap-4">
            {factsError && <RelationEditorErrorSummary message={factsError} />}
            {statesLoading && <p role="status">{t("loading")}</p>}{statesError && <><RelationEditorErrorSummary message={statesError} /><Button variant="outline" onPress={() => setRefresh((value) => value + 1)}>{t("refresh")}</Button></>}
            {!statesLoading && !statesError && states.length === 0 && <p role="status" className="text-sm">{t("noStates")}</p>}
            <label className="grid gap-1 text-xs text-muted">{t("character")}<select className={INPUT} disabled={statesLoading || Boolean(statesError) || factsBusy || factsClosing} value={factCharacterId} onChange={async (event) => {
              const nextCharacterId = event.target.value;
              setFactsClosing(true); setFactsError("");
              try { await factBeforeLeaveRef.current?.(); setFactCharacterId(nextCharacterId); }
              catch (failure) { setFactsError(failure instanceof Error ? failure.message : t("localFailed")); }
              finally { setFactsClosing(false); }
            }}>
              <option value="">{t("chooseCharacter")}</option>{states.map((state) => <option key={state.state_id} value={state.character_id}>{choices.character_ids.find((choice) => choice.id === state.character_id)?.name ?? state.character_id}</option>)}
            </select></label>
            {factCharacterId && <CharacterFactsPanel key={factCharacterId} novelId={novelId} characterId={factCharacterId} initialPosition={{ version: 1, intent: "chapter_after", target_type: "chapter", target_id: chapterId }} initialFields={["psychological_state"]} onChanged={readLists} readOnly={!writable} onBusy={setFactsBusy} beforeLeaveRef={factBeforeLeaveRef} />}
          </div>
        </Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex shrink-0 flex-wrap gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7"><Button variant="ghost" isDisabled={factsBusy || factsClosing} onPress={() => void closeFacts()}>{t("closeKeepDraft")}</Button></Modal.Footer>
      </Modal.Dialog>}</Modal.Container>
    </RetainedModalBackdrop>

    {relationSession && "preparation" in relationSession && <CharacterRelationFactPreparationDialog key={relationSession.preparation.key} initialPreparation={relationSession.preparation} chapters={chapter ? [chapter] : []} onBusy={setRelationBusy} beforeLeaveRef={relationBeforeLeaveRef} onPrepared={(prepared) => {
      if (!alive.current || epoch.current !== relationSession.epoch || context.current.chapterId !== chapterId) return;
      if (!context.current.active) { setRelationSession(null); return; }
      setRelationSession({ draft: prepared, epoch: relationSession.epoch });
    }} onClose={() => {
      if (epoch.current !== relationSession.epoch || context.current.chapterId !== chapterId) return;
      epoch.current += 1; setRelationSession(null); setRefresh((value) => value + 1);
    }} />}
    {relationSession && "draft" in relationSession && <CharacterRelationFactConfirmationDialog key={relationSession.draft.key} novelId={novelId} initialDraft={relationSession.draft} onBusy={setRelationBusy} beforeLeaveRef={relationBeforeLeaveRef} onReadback={async (receipt) => {
      const position = relationSession.draft.preview.basis.position;
      const current = await apiPost<CharacterRelationFactReadResultV1>(`/api/character-relation-facts/novel/${novelId}/read`, { relation_ids: [receipt.relation_id], position });
      if (current.novel_id !== novelId || !current.relations.some((row) => row.relation_id === receipt.relation_id && row.entity_id === receipt.entity_id)) throw new Error(t("relationCheck.handoffMissing"));
      if (alive.current && context.current.active && epoch.current === relationSession.epoch && context.current.chapterId === chapterId) await readLists();
    }} onRepreview={async (previous) => {
      const preparation = await reprepareChapterRelationFact(novelId, previous);
      if (!alive.current || epoch.current !== relationSession.epoch || context.current.chapterId !== chapterId) return;
      // 旧确认层随后会回调关闭；换代后它不能关闭这份新准备。
      epoch.current += 1;
      setRelationSession(context.current.active ? { preparation, epoch: epoch.current } : null);
      setRefresh((value) => value + 1);
    }} onClose={() => {
      if (epoch.current !== relationSession.epoch || context.current.chapterId !== chapterId) return;
      epoch.current += 1; setRelationSession(null); setRefresh((value) => value + 1);
    }} />}

    {/* 保留弹窗外壳，让组件先解除背景锁定并完成退出，再恢复入口焦点。 */}
    <RetainedModalBackdrop isOpen={Boolean(draft)} isDismissable={!saving} isKeyboardDismissDisabled={saving} onOpenChange={(open) => { if (!open) void closeEditor(); }}>
      <Modal.Container scroll="inside">{draft && <Modal.Dialog className="h-[100dvh] w-full max-w-none p-0 sm:h-auto sm:max-h-[90vh] sm:max-w-3xl"><Modal.Header className="flex shrink-0 items-center justify-between gap-3 px-5 py-4 sm:px-7"><Modal.Heading>{t(`modes.${draft.mode}`)}</Modal.Heading><Modal.CloseTrigger isDisabled={saving} /></Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 overflow-y-auto px-5 py-5 sm:px-7">
          <div data-testid="chapter-record-editor" className="grid min-w-0 gap-4">
            {(error || localError) && <div id={`${id}-errors`}><RelationEditorErrorSummary message={error || localError} fieldErrors={fieldErrors} /></div>}
            <ChapterRecordCommandStatus draft={draft} />
            {draft.mode === "psychological-state" && !draft.command?.saved && <p role="status" className="border-l-2 border-amber-500 px-3 text-sm">{t("legacyPsychologicalDraft")}</p>}
            {voiding ? <><p className="text-sm">{t("voidWarning")}</p><label className="grid gap-1 text-xs text-muted">{t("voidReason")}<textarea name="reason" aria-invalid={Boolean(fieldErrors.reason)} aria-describedby={fieldErrors.reason ? `${id}-errors` : undefined} className={`${INPUT} min-h-28`} maxLength={1000} value={draft.reason} disabled={blocked} onChange={(event) => changeDraft({ ...draft, reason: event.target.value })} /></label></> : <>
              {draft.mode === "event" && <><label className="grid gap-1 text-xs text-muted">{t("eventTitle")}<input name="title" aria-invalid={Boolean(fieldErrors.title)} aria-describedby={fieldErrors.title ? `${id}-errors` : undefined} className={INPUT} maxLength={120} value={draft.title} disabled={blocked} onChange={(event) => changeDraft({ ...draft, title: event.target.value })} /></label><label className="grid gap-1 text-xs text-muted">{t("eventContent")}<textarea name="content" aria-invalid={Boolean(fieldErrors.content)} aria-describedby={fieldErrors.content ? `${id}-errors` : undefined} className={`${INPUT} min-h-32`} maxLength={12000} value={draft.content} disabled={blocked} onChange={(event) => changeDraft({ ...draft, content: event.target.value })} /></label></>}
              {draft.mode === "report" && <><p className="text-xs text-muted">{t("appendAfter", { version: draft.expectedReportVersion })}</p><label className="grid gap-1 text-xs text-muted">{t("summary")}<textarea name="summary" aria-invalid={Boolean(fieldErrors.summary)} aria-describedby={fieldErrors.summary ? `${id}-errors` : undefined} className={`${INPUT} min-h-32`} maxLength={12000} value={draft.summary} disabled={blocked} onChange={(event) => changeDraft({ ...draft, summary: event.target.value })} /></label><TagInput label={t("issues")} name="issues" values={draft.issues} onChange={(issues) => changeDraft({ ...draft, issues })} getRemoveAriaLabel={(value) => t("removeIssue", { value })} disabled={blocked} maxItems={50} splitOnPunctuation={false} wrapTags /></>}
              {draft.mode === "psychological-state" && <>
                {statesLoading && <p role="status">{t("loading")}</p>}{statesError && <RelationEditorErrorSummary message={statesError} />}
                {!statesLoading && !statesError && !draft.targetState && states.length === 0 && <p role="status" className="text-sm">{t("noStates")}</p>}
                <label className="grid gap-1 text-xs text-muted">{t("character")}<select className={INPUT} disabled={blocked || statesLoading || Boolean(draft.review)} value={draft.targetState?.state_id ?? ""} onChange={(event) => { cancelCheck.current?.(); const state = states.find((value) => value.state_id === event.target.value); changeDraft({ ...draftRef.current!, targetState: state ? { state_id: state.state_id, version: state.version, character_id: state.character_id, psychological_state: state.psychological_state, volume_id: state.volume_id, name: choices.character_ids.find((choice) => choice.id === state.character_id)?.name ?? state.character_id } : null, psychologicalState: state?.psychological_state ?? "" }); }}><option value="">{t("chooseCharacter")}</option>{draft.targetState && !states.some((value) => value.state_id === draft.targetState!.state_id) && <option value={draft.targetState.state_id}>{draft.targetState.name}</option>}{states.map((state) => <option key={state.state_id} value={state.state_id}>{choices.character_ids.find((choice) => choice.id === state.character_id)?.name ?? state.character_id}</option>)}</select></label>
                {draft.targetState && <div><h4 className="mb-1 text-xs font-medium text-muted">{t("originalState", { version: draft.targetState.version })}</h4><p className="reading-copy whitespace-pre-wrap">{draft.targetState.psychological_state || t("emptyValue")}</p></div>}
                <label className="grid gap-1 text-xs text-muted">{t("psychologicalState")}<textarea name="psychological_state" aria-invalid={Boolean(fieldErrors.psychological_state)} aria-describedby={fieldErrors.psychological_state ? `${id}-errors` : undefined} className={`${INPUT} min-h-28`} maxLength={1000} value={draft.psychologicalState} disabled={blocked} onChange={(event) => changeDraft({ ...draft, psychologicalState: event.target.value })} /></label>
              </>}
              {draft.mode === "character-relation-state" && <>
                {relationsLoading && <p role="status">{t("loading")}</p>}{relationsError && <RelationEditorErrorSummary message={relationsError} />}
                {!relationsLoading && !relationsError && !relationTarget && relations.length === 0 && <p role="status" className="text-sm">{t("relationState.noRelations")}</p>}
                <label className="grid gap-1 text-xs text-muted">{t("relationState.relation")}<select className={INPUT} disabled={blocked || relationsLoading || Boolean(relationsError) || Boolean(draft.review)} value={relationTarget?.relation_id ?? ""} onChange={(event) => {
                  cancelCheck.current?.();
                  const selected = relations.find((row) => row.relation_id === event.target.value);
                  changeDraft({ ...draftRef.current!, relationTarget: selected ? relationCheckTarget(selected) : undefined, relationState: relationFactsMode ? "" : selected?.current_state ?? "", evidence: null });
                }}><option value="">{t("relationState.chooseRelation")}</option>{relationTarget && !relations.some((row) => row.relation_id === relationTarget.relation_id) && <option value={relationTarget.relation_id}>{relationName(relationTarget)}</option>}{relations.map((row) => <option key={row.relation_id} value={row.relation_id}>{relationName(row)}</option>)}</select></label>
                {relationTarget && !relationFactsMode && <div><h4 className="mb-1 text-xs font-medium text-muted">{t("originalState", { version: relationTarget.version })}</h4><p className="reading-copy whitespace-pre-wrap">{relationTarget.current_state}</p></div>}
                {!relationFactsMode && <label className="grid gap-1 text-xs text-muted">{t("relationState.currentState")}<textarea name="current_state" aria-invalid={!relationFactsMode && Boolean(relationStateErrors?.length)} aria-describedby={relationStateErrors?.length ? `${id}-relation-state-errors` : undefined} className={`${INPUT} min-h-28`} value={draft.relationState ?? ""} disabled={blocked} onChange={(event) => changeDraft({ ...draft, relationState: event.target.value })} /></label>}
                {!relationFactsMode && Boolean(relationStateErrors?.length) && <div id={`${id}-relation-state-errors`} role="alert" className="text-sm text-danger">{relationStateErrors!.map((message, index) => <p key={index}>{message}</p>)}</div>}
              </>}
              {(draft.mode === "event" || draft.mode === "report") && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("relatedEntities")}</summary><div className="detail-fields">{Object.entries(ENTITY_FIELDS).map(([kind, field]) => <fieldset key={kind} className="grid gap-1"><legend className="mb-1 text-xs font-medium text-muted">{t(`entityKinds.${kind}`)}</legend>{choices[field].map((choice) => { const selected = draft.relatedEntities.some((value) => value.entity_type === kind && value.entity_id === choice.id); return <label key={choice.id} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" disabled={blocked || !selected && draft.relatedEntities.length >= 50} checked={selected} onChange={() => changeDraft({ ...draft, relatedEntities: selected ? draft.relatedEntities.filter((value) => value.entity_type !== kind || value.entity_id !== choice.id) : [...draft.relatedEntities, { entity_type: kind as ChapterRecordEntityRefV1["entity_type"], entity_id: choice.id }] })} />{choice.name}</label>; })}</fieldset>)}</div></details>}
              <EvidencePicker key={draft.key} novelId={novelId} chapters={chapter ? [chapter] : []} value={draft.evidence} fixedSource={draft.review?.source} initialSource={draft.worldRuleCheck?.source ?? draft.relationCheck?.source} disabled={blocked} onSelectRevision={draft.mode === "report" || draft.mode === "psychological-state" || draft.mode === "character-relation-state" ? (source) => { cancelCheck.current?.(); setCheckSource(source); if (draft.review || draft.mode === "character-relation-state" || draft.mode === "report") setChecked(false); } : undefined} onChange={(value) => { if (value === null) changeDraft({ ...draftRef.current!, evidence: null }); }} onSelectEvidence={(evidence) => changeDraft({ ...draftRef.current!, evidence })} label={t("source")} />
              {draft.mode === "report" && <>
                <WorldRuleSelection novelId={novelId} rules={draft.worldRuleTarget?.rules ?? []} disabled={blocked} onChange={(rules) => {
                  cancelCheck.current?.(); changeDraft({ ...draftRef.current!, worldRuleTarget: { rules } });
                }} />
                <PsychologicalStateCheck key={`check:${draft.key}`} mode="world-rules" novelId={novelId} draft={draft} source={checkSource} blocked={blocked} cancelRef={cancelCheck} onCheck={async (check) => {
                  const current = draftRef.current;
                  if (!current || current.key !== draft.key || current.command) return;
                  const updated = { ...current, worldRuleCheck: check, revision: current.revision + 1 };
                  draftRef.current = updated; setDraft(updated); setChecked(false);
                  await persist(updated);
                }} onAdopt={(check) => {
                  const current = draftRef.current;
                  if (!current || current.key !== draft.key || current.command || current.worldRuleCheck !== check || !check.result || !check.issueEdits) return;
                  const selected = check.issueEdits.filter((issue) => issue.selected && !issue.rejected && !issue.appended);
                  if (!selected.length || selected.some((issue) => { const size = Array.from(issue.text.trim()).length; return size < 1 || size > 2000; })) return;
                  const known = new Set(current.issues.map((issue) => issue.trim()));
                  const texts: string[] = [];
                  const issueEdits = check.issueEdits.map((issue) => {
                    if (!issue.selected || issue.rejected || issue.appended) return issue;
                    const text = issue.text.trim(); const duplicate = known.has(text);
                    if (!duplicate) { texts.push(text); known.add(text); }
                    return { ...issue, selected: false, appended: true, duplicate };
                  });
                  if (current.issues.length + texts.length > 50) { setError(t("worldRuleCheck.reportIssueLimit")); return; }
                  setError("");
                  changeDraft({ ...current, issues: [...current.issues, ...texts], worldRuleCheck: { ...check, issueEdits } });
                }} />
              </>}
              {draft.mode === "psychological-state" && <PsychologicalStateCheck key={`check:${draft.key}`} novelId={novelId} draft={draft} source={checkSource} blocked={blocked} cancelRef={cancelCheck} onCheck={async (check) => {
                const current = draftRef.current;
                if (!current || current.key !== draft.key || current.command) return;
                const updated = { ...current, check, revision: current.revision + 1 };
                draftRef.current = updated; setDraft(updated);
                await persist(updated);
              }} onAdopt={(check) => {
                const current = draftRef.current;
                const suggestion = check.result?.candidate.suggestion;
                if (!current || current.key !== draft.key || current.command || !suggestion || current.check !== check) return;
                changeDraft({ ...current, psychologicalState: suggestion.psychological_state, evidence: { ...check.result!.basis.flow_snapshot.business_input.source, start: suggestion.start, quote: suggestion.quote }, check: { ...check, status: "adopted" } });
              }} />}
              {draft.mode === "character-relation-state" && <PsychologicalStateCheck key={`check:${draft.key}`} mode="character-relation-state" novelId={novelId} draft={draft} source={checkSource} blocked={blocked} cancelRef={cancelCheck} onCheck={async (check) => {
                const current = draftRef.current;
                if (!current || current.key !== draft.key || current.command) return;
                const entityId = check.result?.check_target.entity_id;
                const target = current.relationCheckVersion === 2 && entityId ? { ...check.target, entity_id: entityId } : check.target;
                const updated = { ...current, relationTarget: target, relationCheck: { ...check, target }, revision: current.revision + 1 };
                draftRef.current = updated; setDraft(updated); setChecked(false);
                await persist(updated);
              }} onAdopt={(check) => {
                const current = draftRef.current;
                const suggestion = check.result?.candidate.suggestion;
                if (!current || current.key !== draft.key || current.command || !suggestion || current.relationCheck !== check) return;
                if (current.relationCheckVersion === 2) { void prepareRelationFact(); return; }
                changeDraft({ ...current, relationState: suggestion.current_state, evidence: { ...check.source, start: suggestion.start, quote: suggestion.quote }, relationCheck: { ...check, status: "adopted" } });
              }} />}
              {!relationFactsMode && !draft.evidence && <p role="status" className="text-sm text-muted">{t("evidenceRequired")}</p>}
            </>}
            {!draft.command && !relationFactsMode && <ChapterRecordAuthorConfirmation checked={checked} disabled={saving || !reviewSourceReady || draft.mode === "character-relation-state" && !relationValid} onChange={setChecked} />}
            {!draft.command && !relationFactsMode && draft.mode === "character-relation-state" && !relationCheckReady && <p role="status" className="text-sm text-muted">{t("relationState.checkRequired")}</p>}
            {!relationFactsMode && (rejected || draft.review && !draft.command) && <div className="grid gap-3 border-t border-border pt-3">
              {(draft.mode === "report" || draft.mode === "psychological-state" || draft.mode === "character-relation-state") && <Button variant="outline" isDisabled={readingCurrent || saving || opening} onPress={() => void readCurrent()}>{t("readCurrent")}</Button>}
              {currentRead && ("report_version" in currentRead ? <div><p className="mb-2 text-sm">{t("readHead", { version: currentRead.report_version })}</p>{currentRead.report ? <RecordDetail row={currentRead.report} novelId={novelId} choices={choices} /> : <p className="text-sm">{t(currentRead.report_version ? "noActiveReport" : "noReport")}</p>}</div> : <div><p className="mb-2 text-sm">{t("currentState", { version: currentRead.version })}</p><p className="reading-copy whitespace-pre-wrap">{"relation_id" in currentRead ? currentRead.current_state : currentRead.psychological_state || t("emptyValue")}</p></div>)}
              {currentRead && !currentTargetMatches && <p role="alert" className="text-sm text-danger">{t("review.targetChanged")}</p>}
              <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={reviewChecked} onChange={(event) => setReviewChecked(event.target.checked)} />{t("reviewConfirmed")}</label>
              <Button variant="outline" isDisabled={saving || readingCurrent || !readyToRevise || !writable || Boolean(draft.review && draft.command && draft.command.unknown !== false)} onPress={() => void reviseDraft()}>{t("revise")}</Button>
            </div>}
          </div>
        </Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex shrink-0 flex-wrap gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
          {(!relationFactsMode || draft.command) && <Button variant="primary" isDisabled={saving || draft.check?.status === "running" || draft.relationCheck?.status === "running" || draft.worldRuleCheck?.status === "running" || rejected || !draft.command && (!valid || !checked || !writable)} onPress={() => void submit()}>{t(saving ? "saving" : draft.command?.readbackDone ? "retryCleanup" : draft.command?.saved ? "retryRead" : draft.command ? "retryOriginal" : "confirm")}</Button>}
          {relationCheckVersion === 2 && !relationFactsMode && draft.mode === "character-relation-state" && draft.relationCheck?.result?.candidate.suggestion && (!draft.command || rejected) && <Button variant="outline" isDisabled={saving || !checkSource || checkSource.chapter_id !== draft.relationCheck.source.chapter_id || checkSource.revision_id !== draft.relationCheck.source.revision_id || checkSource.version !== draft.relationCheck.source.version || checkSource.content_hash !== draft.relationCheck.source.content_hash} onPress={() => void prepareRelationFact()}>{t("relationCheck.prepareLegacy")}</Button>}
          <Button variant="ghost" isDisabled={saving} onPress={() => void closeEditor()}>{t("closeKeepDraft")}</Button>
          <ChapterRecordExport draft={draft} />
          {!draft.relationFact && (!draft.review || draft.command?.saved) && (!draft.command || rejected || draft.command.saved) && <Button variant="ghost" isDisabled={saving} onPress={async () => {
            try { cancelCheck.current?.(); await queue.current; await writeChapterRecordDraft(scope, draftRef.current!, persisted.current.get(draft.key)!, true); persisted.current.delete(draft.key); epoch.current += 1; draftRef.current = null; setDraft(null); setDrafts(await readChapterRecordDrafts(scope)); }
            catch { setError(t("localFailed")); }
          }}>{t("discard")}</Button>}
        </Modal.Footer>
      </Modal.Dialog>}</Modal.Container>
    </RetainedModalBackdrop>
  </section>;
}
