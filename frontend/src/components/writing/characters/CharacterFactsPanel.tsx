"use client";

import { useCallback, useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import TagList from "@/components/shared/TagList";
import { apiGet, apiPost, ApiRequestError } from "@/lib/api";
import type { CharacterFactField, CharacterFactPositionV1, CharacterFactPreviewInputV1, CharacterFactPreviewV1, CharacterFactReadResultV1, CharacterFactRecordV1, CharacterFactsAtPositionV1 } from "@/types/characterFacts";
import type { HierarchyRecord } from "@/types/hierarchy";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import CharacterFactConfirmationDialog from "./CharacterFactConfirmationDialog";
import CharacterFactPositionPicker from "./CharacterFactPositionPicker";
import { characterFactPositionKey, loadCharacterFactChapters } from "./characterFactPositions";
import { CHARACTER_FACT_FIELDS, CHARACTER_FACT_SECTIONS } from "./characterFactFields";
import { characterFactDraftScope, type CharacterFactDraftV1 } from "./characterFactDrafts";
import { readCharacterFactDrafts } from "./characterFactStorage";
import { readCharacterFactPreparations, useCharacterFactPreparationPersistence, type CharacterFactPreparationV1, type CharacterFactPreparationSetupV1 } from "./characterFactPreparation";

interface CharacterFactsPanelProps {
  novelId: string; characterId: string; onChanged?: () => Promise<void> | void; readOnly?: boolean;
  initialPosition?: CharacterFactPositionV1; initialFields?: CharacterFactField[]; numberOffset?: number;
  onRead?: (facts: CharacterFactsAtPositionV1 | null) => void;
  onBusy?: (value: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}

type FactSetup = CharacterFactPreparationSetupV1;
type ExistingPreparation = Extract<CharacterFactPreparationV1, { kind: "existing" }>;

/** 功能：隔离不同人物的读取和本地编辑生命周期。Args: 当前小说与稳定人物。Returns: 原详情中的人物事实区。 */
export default function CharacterFactsPanel(props: CharacterFactsPanelProps) {
  return <CharacterFactsContent key={`${props.novelId}:${props.characterId}`} {...props} />;
}

/** 功能：在人物详情和卷工作台共用事实读取、历史与人工确认。Args: 原宿主范围及离开保护。Returns: 连续资料区，不建立新中心。 */
function CharacterFactsContent({ novelId, characterId, onChanged, readOnly = false, initialPosition, initialFields, numberOffset = 0, onRead, onBusy, beforeLeaveRef }: CharacterFactsPanelProps) {
  const t = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const base = `/api/character-facts/novel/${novelId}`;
  const scope = characterFactDraftScope(novelId);
  const [position, setPosition] = useState<CharacterFactPositionV1 | null>(initialPosition ?? null);
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]);
  const [directoryError, setDirectoryError] = useState("");
  const [result, setResult] = useState<CharacterFactReadResultV1 | null>(null);
  const [history, setHistory] = useState<CharacterFactRecordV1[]>([]);
  const [historyMore, setHistoryMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [preparation, setPreparation] = useState<ExistingPreparation | null>(null);
  const [preparations, setPreparations] = useState<ExistingPreparation[]>([]);
  const preparationRef = useRef<ExistingPreparation | null>(null);
  const preparationStore = useCharacterFactPreparationPersistence(novelId);
  const setup = preparation?.setup ?? null;
  const keepPreparation = async () => {
    if (preparationRef.current) await preparationStore.persist(preparationRef.current);
    await preparationStore.queue.current;
  };
  const setSetup = (value: FactSetup) => {
    const current = preparationRef.current;
    const next: ExistingPreparation = { schema_id: "character.fact.preparation", schema_version: 1, kind: "existing", key: current?.key ?? crypto.randomUUID(), revision: (current?.revision ?? 0) + 1, novel_id: novelId, character_id: characterId, setup: value };
    preparationRef.current = next; setPreparation(next);
    void preparationStore.persist(next).catch((failure) => setSetupError(failure.message));
  };
  const [setupFacts, setSetupFacts] = useState<CharacterFactsAtPositionV1 | null>(null);
  const setupErrorRef = useRef<HTMLDivElement>(null);
  const [setupError, setSetupError] = useState("");
  const [preparing, setPreparing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [drafts, setDrafts] = useState<CharacterFactDraftV1[]>([]);
  const [draft, setDraft] = useState<CharacterFactDraftV1 | null>(null);
  const [source, setSource] = useState<CharacterFactRecordV1 | null>(null);
  const readCallback = useRef(onRead);
  readCallback.current = onRead;
  const request = useRef(0);
  const alive = useRef(true);
  const preparePending = useRef(false);
  const dialogLeave = useRef<(() => Promise<void>) | null>(null);
  const fact = result?.characters.find((row) => row.character_id === characterId) ?? null;
  const busy = preparing || confirming;
  const positionLabel = (anchor: CharacterFactPositionV1) => anchor.intent === "book_start" ? t("positions.book_start") : anchor.intent === "volume_start" ? t("positions.volume_start") : `${chapters.find((row) => row.chapter_id === anchor.target_id)?.title ?? anchor.target_id} · ${t(`positions.${anchor.intent}`)}`;
  const readDrafts = useCallback(async () => {
    const [rows, pending] = await Promise.allSettled([readCharacterFactDrafts(scope), readCharacterFactPreparations(novelId)]);
    if (!alive.current) return;
    if (rows.status === "fulfilled") setDrafts(rows.value.filter((row) => row.preview.basis.target.kind === "existing" && row.preview.basis.target.character_id === characterId));
    if (pending.status === "fulfilled") setPreparations(pending.value.filter((row): row is ExistingPreparation => row.kind === "existing" && row.character_id === characterId));
    if (rows.status === "rejected") throw rows.reason;
    if (pending.status === "rejected") throw pending.reason;
  }, [scope, characterId, novelId]);
  const closeSetup = async () => {
    try { await keepPreparation(); preparationRef.current = null; setPreparation(null); await readDrafts(); }
    catch (failure) { setSetupError((failure as Error).message); }
  };
  const readFacts = useCallback(async (signal?: AbortSignal) => {
    const current = ++request.current;
    const response = await apiPost<CharacterFactReadResultV1>(`${base}/read`, { character_ids: [characterId], position }, { signal });
    if (response.novel_id !== novelId || response.characters.some((row) => row.character_id !== characterId)) throw new Error(t("wrongScope"));
    const target = response.characters.find((row) => row.character_id === characterId);
    const records = target ? await apiGet<CharacterFactRecordV1[]>(`${base}/history?${new URLSearchParams({ entity_id: target.entity_id, limit: "100" })}`, { signal }) : [];
    if (signal?.aborted || !alive.current || current !== request.current) { if (!signal) throw new Error(t("readInterrupted")); return; }
    readCallback.current?.(target ?? null);
    setResult(response); setHistory(records); setHistoryMore(records.length === 100); setError("");
  }, [base, characterId, novelId, position, t]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current += 1; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (preparePending.current || confirming) throw new Error(t("saving")); await keepPreparation(); await dialogLeave.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  });
  useEffect(() => {
    if (!setup) return;
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [setup]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); setLoading(true);
    void readFacts(abort.signal).catch((failure) => {
      if (!abort.signal.aborted) { setError(failure.message); if (failure instanceof ApiRequestError && [403, 404].includes(failure.status)) { setResult(null); setHistory([]); readCallback.current?.(null); } }
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    void readDrafts().catch((failure) => { if (!abort.signal.aborted) setError(failure.message); });
    return () => { abort.abort(); request.current += 1; };
  }, [active, readFacts, readDrafts, refresh]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    void loadCharacterFactChapters(novelId, abort.signal).then((rows) => { if (!abort.signal.aborted) { setChapters(rows); setDirectoryError(""); } }).catch((failure) => { if (!abort.signal.aborted) setDirectoryError(failure.message); });
    return () => abort.abort();
  }, [novelId, active, refresh]);
  useEffect(() => {
    if (!active || !setupError) return;
    const frame = requestAnimationFrame(() => {
      const summary = setupErrorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      if (!summary || summary.closest("[inert]")) return;
      summary.focus({ preventScroll: true }); summary.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, setupError]);
  const setupPosition = setup?.position;
  const setupOperation = setup?.operation;
  const setupKind = setup?.record?.kind ?? (setupOperation === "change" ? "change" : "start");
  useEffect(() => {
    setSetupFacts(null);
    if (!setupPosition || setupOperation === "void") return;
    const abort = new AbortController();
    const before = setupKind === "change" && setupPosition.target_type === "chapter" ? { ...setupPosition, intent: "chapter_before" as const } : setupPosition;
    void apiPost<CharacterFactReadResultV1>(`${base}/read`, { character_ids: [characterId], position: before }, { signal: abort.signal }).then((response) => { if (!abort.signal.aborted) setSetupFacts(response.characters.find((row) => row.character_id === characterId) ?? null); }).catch((failure) => { if (!abort.signal.aborted) setSetupError(failure.message); });
    return () => abort.abort();
  }, [base, characterId, setupPosition, setupOperation, setupKind]);

  const open = (operation: FactSetup["operation"], fields: CharacterFactField[], record: CharacterFactRecordV1 | null = null) => {
    preparationRef.current = null;
    setSetupError("");
    setSetup({ operation, fields, record, position: record?.position ?? (operation === "correct_initial" ? { version: 1, intent: "book_start", target_type: "novel", target_id: novelId } : initialPosition ?? position), note: record?.source.kind === "author" ? record.source.note : "", evidence: null, resolves: {} });
  };
  const preview = async () => {
    if (!setup || !fact || preparePending.current) return;
    if (!setup.fields.length || (setup.operation !== "void" && (!setup.position || (setupKind === "start" ? !setup.note.trim() : !setup.evidence)))) { setSetupError(t("previewRequired")); return; }
    preparePending.current = true; setPreparing(true); setSetupError("");
    try {
      await keepPreparation();
      const target = { entity_id: fact.entity_id, character_id: fact.character_id, expected_version: fact.version };
      const chosen = setup.record ? Object.fromEntries(setup.fields.map((field) => [field, setup.record!.history_id])) : {};
      const input: CharacterFactPreviewInputV1 = setup.operation === "void"
        ? { operation: "void", target, targets: chosen }
        : { operation: setup.operation, target, kind: setupKind, position: setup.position!, source: setupKind === "start" ? { kind: "author", note: setup.note } : { kind: "chapter", evidence: setup.evidence! }, fields: setup.fields, replaces: setup.record ? chosen : {}, resolves: setup.resolves };
      const response = await apiPost<CharacterFactPreviewV1>(`${base}/preview`, input);
      const next: CharacterFactDraftV1 = { schema_id: "character.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel: positionLabel(response.basis.position), preview: response, after: setup.operation === "void" ? {} : { ...structuredClone(response.values.values), ...Object.fromEntries(response.basis.fields.filter((field) => setup.after?.[field] !== undefined).map((field) => [field, structuredClone(setup.after![field])])) }, reason: setup.reason ?? "", authorConfirmed: false };
      await preparationStore.promote(preparationRef.current!, next);
      if (!alive.current) return;
      setDraft(next); preparationRef.current = null; setPreparation(null); await readDrafts();
    } catch (failure) { if (alive.current) setSetupError((failure as Error).message); }
    finally { preparePending.current = false; if (alive.current) setPreparing(false); }
  };
  const openSource = async (historyId: string) => {
    try { const row = history.find((record) => record.history_id === historyId) ?? await apiGet<CharacterFactRecordV1>(`${base}/history/${historyId}`); if (alive.current) setSource(row); }
    catch (failure) { if (alive.current) setError((failure as Error).message); }
  };
  const readback = async () => { await readFacts(); await onChanged?.(); };
  const displayValue = (field: CharacterFactField) => {
    const unknown = fact?.unknown[field];
    if (unknown) return <span className="text-amber-700 dark:text-amber-300">{t(`unknown.${unknown}`)}</span>;
    const value = fact?.values[field];
    if (value === undefined) return t("unknown.nonexistent");
    if (!value.length) return t("cleared");
    return Array.isArray(value) ? <TagList values={value} /> : value;
  };
  return <section className="mt-8 space-y-6" aria-label={t("panelTitle")}>
    <div className="flex flex-wrap items-end gap-3"><div className="min-w-0 flex-1"><CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={position} onChange={(next) => { setResult(null); setHistory([]); readCallback.current?.(null); setPosition(next); }} latest disabled={busy} /></div><Button variant="ghost" isDisabled={busy || loading} onPress={() => setRefresh((value) => value + 1)}>{t("refresh")}</Button></div>
    {result && <p className="text-xs text-muted">{t("resolvedPosition", { position: positionLabel(result.position as CharacterFactPositionV1) })}</p>}
    {loading && <p role="status">{t("loading")}</p>}
    {(error || directoryError) && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{error || directoryError}</p>}
    {!loading && !fact && !error && <p>{t("missingCharacter")}</p>}
    {fact && Object.entries(CHARACTER_FACT_SECTIONS).map(([section, fields], index) => <DocumentSection key={section} number={String(numberOffset + index + 1).padStart(2, "0")} title={t(`sections.${section}`)} actions={!readOnly && <Button variant="ghost" size="sm" isDisabled={busy || loading || Boolean(error)} onPress={() => open("establish", initialFields?.length ? initialFields : [...fields])}>{t("editFacts")}</Button>}>
      <dl className="detail-fields grid gap-5">{fields.map((field) => <div key={field} className="min-w-0">
        <ReadOnlyField label={t(`fields.${field}`)} value={displayValue(field)} wide />
        {fact.origins[field] && <Button size="sm" variant="ghost" onPress={() => void openSource(fact.origins[field]!)}>{t("source")}</Button>}
        {fact.blockers[field]?.map((historyId) => <Button key={historyId} size="sm" variant="ghost" onPress={() => void openSource(historyId)}>{t("blockingSource")}</Button>)}
      </div>)}</dl>
    </DocumentSection>)}
    {!readOnly && preparations.length > 0 && <div className="space-y-2"><h4 className="text-sm font-semibold">{t("preparationDrafts")}</h4>{preparations.map((row) => <Button key={row.key} variant="outline" size="sm" isDisabled={busy} onPress={() => { preparationStore.persisted.current.set(row.key, row.revision); preparationRef.current = row; setPreparation(row); setSetupError(""); }}>{row.setup.position ? positionLabel(row.setup.position) : t("choosePosition")}</Button>)}</div>}
    {!readOnly && drafts.length > 0 && <div className="space-y-2"><h4 className="text-sm font-semibold">{t("retainedDrafts")}</h4>{drafts.map((row) => <Button key={row.key} variant="outline" size="sm" isDisabled={busy} onPress={() => { setDraft(row); preparationRef.current = null; setPreparation(null); }}>{t("resumeDraft", { position: row.positionLabel })}</Button>)}</div>}
    {history.length > 0 && <details><summary className="cursor-pointer py-2 text-sm text-accent">{t("history")}</summary><ol className="space-y-3">{history.map((record) => <li key={record.history_id} className="border-b border-border py-3"><div className="flex flex-wrap items-center gap-2"><span className="text-sm">{positionLabel(record.position)} · {t(`operations.${record.operation}`)}</span><Button size="sm" variant="ghost" onPress={() => setSource(record)}>{t("source")}</Button>{!readOnly && Object.values(record.validity).some((value) => value.state === "active") && <>
      <Button size="sm" variant="ghost" isDisabled={busy} onPress={() => open(record.position.intent === "book_start" ? "correct_initial" : "replace", CHARACTER_FACT_FIELDS.filter((field) => record.validity[field]?.state === "active"), record)}>{t(record.position.intent === "book_start" ? "operations.correct_initial" : "operations.replace")}</Button>
      <Button size="sm" variant="ghost" isDisabled={busy} onPress={() => open("void", CHARACTER_FACT_FIELDS.filter((field) => record.validity[field]?.state === "active"), record)}>{t("operations.void")}</Button>
    </>}</div></li>)}</ol>{historyMore && <Button variant="ghost" isDisabled={busy} onPress={async () => { try { const next = await apiGet<CharacterFactRecordV1[]>(`${base}/history?${new URLSearchParams({ entity_id: fact!.entity_id, limit: "100", before_version: String(history.at(-1)!.after_version) })}`); setHistory((rows) => [...rows, ...next]); setHistoryMore(next.length === 100); } catch (failure) { setError((failure as Error).message); } }}>{t("moreHistory")}</Button>}</details>}

    {setup && <RetainedModalBackdrop isOpen isDismissable={!preparing} onOpenChange={(openModal) => { if (!openModal && !preparing) void closeSetup(); }}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl"><Modal.Header className="border-b border-border px-5 py-4"><Modal.Heading>{t("previewTitle")}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} isDisabled={preparing} /></Modal.Header><Modal.Body className="space-y-5 px-5 py-5">
      {setupError && <div ref={setupErrorRef}><RelationEditorErrorSummary message={setupError} /></div>}
      {!setup.record && <label className="grid gap-2 text-xs text-muted">{t("operation")}<select className={INPUT} value={setup.operation} disabled={preparing} onChange={(event) => setSetup({ ...setup, operation: event.target.value as "establish" | "change", position: null, evidence: null, resolves: {} })}><option value="establish">{t("operations.establish")}</option><option value="change">{t("operations.change")}</option></select></label>}
      <fieldset disabled={preparing}><legend className="mb-2 text-xs font-medium text-muted">{t("selectedFields")}</legend><div className="grid gap-2 sm:grid-cols-2">{(setup.record ? CHARACTER_FACT_FIELDS.filter((field) => setup.record!.validity[field]?.state === "active") : CHARACTER_FACT_FIELDS).map((field) => <label key={field} className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={setup.fields.includes(field)} onChange={(event) => setSetup({ ...setup, fields: event.target.checked ? [...setup.fields, field] : setup.fields.filter((item) => item !== field), resolves: {} })} />{t(`fields.${field}`)}</label>)}</div></fieldset>
      <CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={setup.position} onChange={(next) => setSetup({ ...setup, position: next, evidence: null, resolves: {} })} disabled={preparing || Boolean(setup.record)} afterOnly={setupKind === "change"} />
      {setup.operation !== "void" && (setupKind === "start" ? <label className="grid gap-2 text-xs text-muted">{t("authorNote")}<textarea className={INPUT} value={setup.note} onChange={(event) => setSetup({ ...setup, note: event.target.value })} disabled={preparing} maxLength={2000} rows={3} /></label> : <EvidencePicker key={characterFactPositionKey(setup.position)} novelId={novelId} chapters={chapters.filter((chapter) => chapter.chapter_id === setup.position?.target_id)} value={setup.evidence} label={t("source")} disabled={preparing || !setup.position} onChange={(value) => { if (value === null) setSetup({ ...setup, evidence: null }); }} onSelectEvidence={(evidence) => setSetup({ ...setup, evidence })} />)}
      {setup.operation !== "void" && setupFacts && setup.fields.flatMap((field) => (setupFacts.blockers[field] ?? []).map((historyId) => <label key={`${field}:${historyId}`} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={setup.resolves[field]?.includes(historyId) ?? false} onChange={(event) => { const ids = event.target.checked ? [...(setup.resolves[field] ?? []), historyId] : (setup.resolves[field] ?? []).filter((value) => value !== historyId); const resolves = { ...setup.resolves }; if (ids.length) resolves[field] = ids; else delete resolves[field]; setSetup({ ...setup, resolves }); }} />{t("resolveBlocking", { field: t(`fields.${field}`), id: historyId })}</label>))}
    </Modal.Body><Modal.Footer className="border-t border-border px-5 py-4"><Button variant="ghost" isDisabled={preparing} onPress={() => void closeSetup()}>{t("close")}</Button><Button variant="primary" isDisabled={preparing || !setup.fields.length} onPress={() => void preview()}>{t(preparing ? "loading" : "preview")}</Button></Modal.Footer></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
    {draft && <CharacterFactConfirmationDialog key={draft.key} novelId={novelId} initialDraft={draft} onReadback={readback} onBusy={setConfirming} beforeLeaveRef={dialogLeave} onRepreview={async (previous) => {
      const basis = previous.command?.body.basis ?? previous.preview.basis;
      if (basis.target.kind !== "existing" || basis.operation === "create") throw new Error(t("wrongScope"));
      await readFacts();
      const record = basis.operation === "void" || basis.operation === "replace" || basis.operation === "correct_initial" ? basis.targets[0] ?? null : null;
      const setup: FactSetup = { operation: basis.operation, fields: [...basis.fields], position: basis.position, note: basis.source.kind === "author" ? basis.source.note : "", evidence: basis.source.kind === "chapter" ? basis.source.evidence : null, record, resolves: structuredClone(basis.resolves), after: previous.command ? previous.command.body.operation === "void" ? {} : structuredClone(previous.command.body.after) : structuredClone(previous.after), reason: previous.command?.body.operation === "void" ? previous.command.body.reason : previous.reason };
      const next: ExistingPreparation = { schema_id: "character.fact.preparation", schema_version: 1, kind: "existing", key: crypto.randomUUID(), revision: 1, novel_id: novelId, character_id: characterId, setup };
      await preparationStore.persist(next); preparationRef.current = next; setPreparation(next); setSetupError("");
    }} onClose={() => { setDraft(null); void readDrafts().catch((failure) => setError(failure.message)); }} />}
    {source && <RetainedModalBackdrop isOpen onOpenChange={(openModal) => { if (!openModal) setSource(null); }}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full max-w-3xl"><Modal.Header className="px-5 py-4"><Modal.Heading>{t("source")}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} /></Modal.Header><Modal.Body className="space-y-4 px-5 py-5"><p className="text-sm">{source.character_name} · {positionLabel(source.position)}</p><dl className="grid gap-3">{CHARACTER_FACT_FIELDS.filter((field) => field in source.after).map((field) => <ReadOnlyField key={field} label={t(`fields.${field}`)} value={Array.isArray(source.after[field]) ? source.after[field]!.length ? <TagList values={source.after[field] as string[]} /> : t("cleared") : source.after[field] || t("cleared")} wide />)}</dl>{source.source.kind === "author" ? <p className="reading-copy whitespace-pre-wrap">{source.source.note}</p> : <EvidencePicker novelId={novelId} chapters={[]} value={source.source.evidence} readOnly chapterRecordSource label={t("source")} />}</Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
  </section>;
}
