"use client";

import { useCallback, useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import { apiGet, apiPost, apiPut, ApiRequestError } from "@/lib/api";
import type { CharacterRelationResponseV1, CharacterRelationUpdateRequestV1 } from "@/types/character";
import type { CharacterFactPositionV1 } from "@/types/characterFacts";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { CharacterRelationFactOperation, CharacterRelationFactReadResultV1, CharacterRelationFactRecordV1 } from "@/types/characterRelationFacts";
import EvidencePicker from "../foreshadowings/EvidencePicker";
import CharacterFactPositionPicker from "./CharacterFactPositionPicker";
import { loadCharacterFactChapters } from "./characterFactPositions";
import CharacterRelationFactPreparationDialog from "./CharacterRelationFactPreparationDialog";
import CharacterRelationFactConfirmationDialog from "./CharacterRelationFactConfirmationDialog";
import { characterRelationFactDraftScope, type CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import { readCharacterRelationFactDrafts } from "./characterRelationFactStorage";
import { readCharacterRelationFactPreparations, reprepareChapterRelationFact, useCharacterRelationFactPreparationPersistence, type CharacterRelationFactPreparationV1 } from "./characterRelationFactPreparation";

import { reprepareCharacterRelationCandidate } from "./characterRelationCandidateDrafts";

type ExistingPreparation = Extract<CharacterRelationFactPreparationV1, { kind: "existing" }>;
interface Props {
  novelId: string;
  entityId?: string;
  relation: CharacterRelationResponseV1;
  onChanged?: () => Promise<void>; readOnly?: boolean; numberOffset?: number; onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}

/** 功能：把每个关系的读取和本地草稿分开，切目标不复用旧请求状态。Args: 原关系与宿主回调。Returns: 关系事实与尚未认领的旧文字。 */
export default function CharacterRelationFactsPanel(props: Props) {
  return <RelationFacts key={`${props.novelId}:${props.relation.relation_id}:${props.entityId ?? ""}`} {...props} />;
}

function RelationFacts({ novelId, entityId, relation, onChanged, readOnly = false, numberOffset = 0, onBusy, beforeLeaveRef }: Props) {
  const t = useTranslations("writing.characterFacts");
  const relationT = useTranslations("writing.characterRelationFacts");
  const characterT = useTranslations("writing.characters");
  const active = useContext(RetainedViewActive);
  const base = `/api/character-relation-facts/novel/${novelId}`;
  const [position, setPosition] = useState<CharacterFactPositionV1 | null>(null);
  const [result, setResult] = useState<CharacterRelationFactReadResultV1 | null>(null);
  const [history, setHistory] = useState<CharacterRelationFactRecordV1[]>([]);
  const [more, setMore] = useState(false);
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [directoryError, setDirectoryError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [drafts, setDrafts] = useState<CharacterRelationFactDraftV1[]>([]);
  const [preparations, setPreparations] = useState<ExistingPreparation[]>([]);
  const [draft, setDraft] = useState<CharacterRelationFactDraftV1 | null>(null);
  const [preparation, setPreparation] = useState<CharacterRelationFactPreparationV1 | null>(null);
  const [legacy, setLegacy] = useState<{ body: CharacterRelationUpdateRequestV1; saved: boolean } | null>(null);
  const [legacyError, setLegacyError] = useState("");
  const [legacyBusy, setLegacyBusy] = useState(false);
  const legacyInput = useRef<HTMLTextAreaElement>(null);
  const visible = useRef(active);
  const [source, setSource] = useState<CharacterRelationFactRecordV1 | null>(null);
  const alive = useRef(true);
  const request = useRef(0);
  const pending = useRef(false);
  const historyEntity = useRef<string | null>(entityId ?? null);
  const historyRequest = useRef(0);
  const sourceRequest = useRef(0);
  const dialogKeys = useRef({ preparation: preparation?.key, draft: draft?.key });
  dialogKeys.current = { preparation: preparation?.key, draft: draft?.key };
  const dialogLeave = useRef<(() => Promise<void>) | null>(null);
  const store = useCharacterRelationFactPreparationPersistence(novelId);
  const fact = result?.relations.find((row) => row.relation_id === relation.relation_id);
  const blocked = busy || starting || legacyBusy || Boolean(legacy) || loading || Boolean(error || directoryError) || relation.is_deleted || !relation.is_active;
  const label = (anchor: CharacterFactPositionV1) => anchor.intent === "book_start" ? t("positions.book_start") : anchor.intent === "volume_start" ? t("positions.volume_start") : `${chapters.find((row) => row.chapter_id === anchor.target_id)?.title ?? anchor.target_id} · ${t(`positions.${anchor.intent}`)}`;
  const readDrafts = useCallback(async () => {
    const [saved, preparing] = await Promise.all([readCharacterRelationFactDrafts(characterRelationFactDraftScope(novelId)), readCharacterRelationFactPreparations(novelId)]);
    if (!alive.current) return;
    setDrafts(saved.filter((row) => row.preview.basis.target.kind === "existing" && row.preview.basis.target.relation_id === relation.relation_id));
    setPreparations(preparing.filter((row): row is ExistingPreparation => row.kind === "existing" && row.relation_id === relation.relation_id));
  }, [novelId, relation.relation_id]);
  const readHistory = useCallback(async (physicalId: string, signal?: AbortSignal, beforeVersion?: number) => {
    const id = ++historyRequest.current; setHistoryLoading(true);
    try {
      const query = new URLSearchParams({ entity_id: physicalId, limit: "100" });
      if (beforeVersion !== undefined) query.set("before_version", String(beforeVersion));
      const rows = await apiGet<CharacterRelationFactRecordV1[]>(`${base}/history?${query}`, { signal });
      if (signal?.aborted || !alive.current || id !== historyRequest.current) return;
      if (rows.some((row) => row.novel_id !== novelId || row.entity_id !== physicalId || row.relation_id !== relation.relation_id)) throw new Error(relationT("wrongScope"));
      setHistory((old) => beforeVersion === undefined ? rows : [...old, ...rows]); setMore(rows.length === 100); setHistoryError("");
    } catch (failure) { if (!signal?.aborted && alive.current && id === historyRequest.current) setHistoryError((failure as Error).message); }
    finally { if (!signal?.aborted && alive.current && id === historyRequest.current) setHistoryLoading(false); }
  }, [base, novelId, relation.relation_id, relationT]);
  const readFacts = useCallback(async (signal?: AbortSignal) => {
    const id = ++request.current;
    let response: CharacterRelationFactReadResultV1;
    try { response = await apiPost<CharacterRelationFactReadResultV1>(`${base}/read`, { relation_ids: [relation.relation_id], position }, { signal }); }
    catch (failure) { if (historyEntity.current && !signal?.aborted) await readHistory(historyEntity.current, signal); throw failure; }
    if (response.novel_id !== novelId || response.relations.some((row) => row.relation_id !== relation.relation_id)) throw new Error(relationT("wrongScope"));
    const row = response.relations[0];
    const physicalId = row?.entity_id ?? response.reads[0].identities.find((item) => item.relation_id === relation.relation_id)?.entity_id ?? historyEntity.current;
    if (historyEntity.current && physicalId !== historyEntity.current) { await readHistory(historyEntity.current, signal); throw new Error(relationT("wrongScope")); }
    if (signal?.aborted || !alive.current || id !== request.current) { if (!signal) throw new Error(relationT("readInterrupted")); return; }
    historyEntity.current = physicalId;
    setResult(response); setError("");
    if (physicalId) await readHistory(physicalId, signal);
    return row;
  }, [base, novelId, position, relation.relation_id, relationT, readHistory]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current += 1; }; }, []);
  useEffect(() => { visible.current = active; }, [active]);
  useEffect(() => { if (!active) sourceRequest.current += 1; return () => { sourceRequest.current += 1; }; }, [active]);
  useEffect(() => { onBusy?.(busy || starting || legacyBusy); return () => onBusy?.(false); }, [busy, starting, legacyBusy, onBusy]);
  useEffect(() => { if (!beforeLeaveRef) return; beforeLeaveRef.current = async () => { if (legacy) throw new Error(t("finishLegacyEditing")); if (pending.current || busy || legacyBusy) throw new Error(t("saving")); await store.queue.current; await dialogLeave.current?.(); }; return () => { beforeLeaveRef.current = null; }; });
  useEffect(() => {
    if (!legacy) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [legacy]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); setLoading(true);
    void readFacts(abort.signal).catch((failure) => { if (!abort.signal.aborted) { setError(failure.message); if (failure instanceof ApiRequestError && [403, 404].includes(failure.status)) setResult(null); } }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    void readDrafts().catch((failure) => { if (!abort.signal.aborted) setError(failure.message); });
    void loadCharacterFactChapters(novelId, abort.signal).then((rows) => { if (!abort.signal.aborted) { setChapters(rows); setDirectoryError(""); } }).catch((failure) => { if (!abort.signal.aborted) setDirectoryError(failure.message); });
    return () => abort.abort();
  }, [active, novelId, readDrafts, readFacts, refresh, relation.version]);
  const open = async (operation: Exclude<CharacterRelationFactOperation, "create">, record: CharacterRelationFactRecordV1 | null = null) => {
    if (!fact || pending.current) return;
    pending.current = true; setStarting(true);
    const next: ExistingPreparation = { schema_id: "character_relation.fact.preparation", schema_version: 1, kind: "existing", key: crypto.randomUUID(), revision: 1, novel_id: novelId, relation_id: relation.relation_id, target: { entity_id: fact.entity_id, relation_id: relation.relation_id, expected_version: fact.version }, setup: { operation, position: record?.position ?? position, note: record?.source.kind === "author" ? record.source.note : "", evidence: null, record, resolves: {} } };
    try { await store.persist(next); if (alive.current && visible.current) setPreparation(next); } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setStarting(false); }
  };
  const openSource = async (historyId: string) => {
    const id = ++sourceRequest.current;
    try { const row = await apiGet<CharacterRelationFactRecordV1>(`${base}/history/${historyId}`); if (alive.current && id === sourceRequest.current) setSource(row); }
    catch (failure) { if (alive.current && id === sourceRequest.current) setError((failure as Error).message); }
  };
  const saveLegacy = async () => {
    if (!legacy || pending.current || legacyBusy) return;
    if (!legacy.saved && (readOnly || !fact || fact.claimed_fields.length || relation.is_deleted)) { setLegacyError(t("managedLegacyField")); return; }
    pending.current = true; setLegacyBusy(true); setLegacyError("");
    try {
      if (!legacy.saved) {
        await apiPut(`/api/character-relations/novel/${novelId}/${relation.relation_id}`, legacy.body);
        // 成功先记住，后续重读失败不能再提交旧文字。
        if (!alive.current) return;
        setLegacy({ ...legacy, saved: true });
      }
      await onChanged?.(); await readFacts();
      if (alive.current) {
        setLegacy(null);
        requestAnimationFrame(() => { if (visible.current) document.getElementById(`relation-legacy-${relation.relation_id}`)?.focus(); });
      }
    } catch (failure) { if (alive.current) setLegacyError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setLegacyBusy(false); }
  };
  return <section className="space-y-6" aria-label={relationT("panelTitle")}>
    <div className="workspace-toolbar flex flex-wrap items-end gap-3"><div className="min-w-0 flex-1"><CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={position} latest disabled={busy || starting} onChange={(next) => { setResult(null); setPosition(next); }} /></div><Button variant="ghost" isDisabled={busy || starting || loading} onPress={() => setRefresh((value) => value + 1)}>{t("refresh")}</Button></div>
    {loading && <p role="status">{t("loading")}</p>}
    {(error || directoryError) && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{error || directoryError}</p>}
    {!relation.is_active && !relation.is_deleted && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{relationT("inactive")}</p>}
    {(!fact && result || relation.is_deleted) && <p role="status">{relationT("missingRelation")}</p>}
    {fact && <DocumentSection number={String(numberOffset + 1).padStart(2, "0")} title={relationT("currentState")}><div className="space-y-4">
      <dl className="grid gap-4"><ReadOnlyField label={t("position")} value={label(result!.position as CharacterFactPositionV1)} /><ReadOnlyField label={relationT("currentState")} value={fact.unknown.current_state ? <span className="text-amber-700 dark:text-amber-300">{relationT(`unknown.${fact.unknown.current_state}`)}</span> : fact.values.current_state} wide /></dl>
      <div className="flex flex-wrap gap-2">{fact.origins.current_state && <Button variant="ghost" size="sm" onPress={() => void openSource(fact.origins.current_state!)}>{t("source")}</Button>}{fact.blockers.current_state?.map((id) => <Button key={id} variant="ghost" size="sm" onPress={() => void openSource(id)}>{t("blockingSource")}</Button>)}{!readOnly && <><Button variant="outline" isDisabled={blocked} onPress={() => void open("establish")}>{relationT("operations.establish")}</Button><Button variant="outline" isDisabled={blocked} onPress={() => void open("change")}>{relationT("operations.change")}</Button></>}</div>
    </div></DocumentSection>}
    {(fact && !fact.claimed_fields.length || legacy) && <DocumentSection number={String(numberOffset + 2).padStart(2, "0")} title={relationT("legacyValue")} actions={legacy ? <>
      <Button size="sm" variant="primary" type="submit" form={`relation-legacy-form-${relation.relation_id}`} isDisabled={legacyBusy || !legacy.saved && (readOnly || loading || !fact || Boolean(fact.claimed_fields.length) || relation.is_deleted)}>{legacy.saved ? characterT("relationDesign.retryRead") : t("saveLegacyText")}</Button>
      <SectionActionButton action="cancel" label={characterT("actions.cancel")} size="sm" variant="ghost" isDisabled={legacyBusy} onPress={() => { setLegacy(null); setLegacyError(""); requestAnimationFrame(() => document.getElementById(`relation-legacy-${relation.relation_id}`)?.focus()); }} />
    </> : !readOnly && !relation.is_deleted ? <SectionEditButton id={`relation-legacy-${relation.relation_id}`} label={t("editLegacyText")} isDisabled={busy || starting || loading || Boolean(error)} onPress={() => {
      const { relation_type, current_state, core_conflict, hidden_tension, possible_change, story_value, intensity, version } = relation;
      // 旧接口要求整组字段，保留开始时的设计和版本，只让作者改旧文字。
      setLegacy({ body: { relation_type, current_state, core_conflict, hidden_tension, possible_change, story_value, intensity, expected_version: version }, saved: false }); setLegacyError("");
      requestAnimationFrame(() => { if (visible.current) legacyInput.current?.focus(); });
    }} /> : undefined}>
      <div className="min-w-0 space-y-4">
        {legacyError && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{legacy?.saved ? characterT("relationDesign.savedReadbackFailed") : legacyError}</p>}
        {legacy && Boolean(fact?.claimed_fields.length) && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{t("managedLegacyField")}</p>}
        {legacy ? <form id={`relation-legacy-form-${relation.relation_id}`} onSubmit={(event) => { event.preventDefault(); void saveLegacy(); }}><label className="grid min-w-0 gap-2 text-xs font-medium text-muted">{relationT("legacyValue")}<textarea ref={legacyInput} name="current_state" value={legacy.body.current_state} required maxLength={2000} rows={4} disabled={legacyBusy || legacy.saved || readOnly} className="min-h-28 w-full resize-y rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm leading-6 text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15" onChange={(event) => setLegacy({ ...legacy, body: { ...legacy.body, current_state: event.target.value } })} /></label></form>
          : <p className="reading-copy whitespace-pre-wrap">{relation.current_state}</p>}
      </div>
    </DocumentSection>}
    {!readOnly && preparations.length > 0 && <div className="space-y-2"><h4 className="text-sm font-semibold">{relationT("preparationDrafts")}</h4><div className="flex flex-wrap gap-2">{preparations.map((row) => <Button key={row.key} variant="outline" isDisabled={busy || starting} onPress={() => setPreparation(row)}>{relationT(`operations.${row.setup.operation}`)} · {row.setup.position ? label(row.setup.position) : t("choosePosition")}</Button>)}</div></div>}
    {!readOnly && drafts.length > 0 && <div className="space-y-2"><h4 className="text-sm font-semibold">{t("retainedDrafts")}</h4><div className="flex flex-wrap gap-2">{drafts.map((row) => <Button key={row.key} variant="outline" isDisabled={busy || starting} onPress={() => setDraft(row)}>{t("resumeDraft", { position: row.positionLabel })}</Button>)}</div></div>}
    {historyError && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{relationT("historyFailed", { error: historyError })}</p>}
    {history.length > 0 && <details><summary className="cursor-pointer py-2 text-sm text-accent">{t("history")}</summary><ol className="divide-y divide-border">{history.map((row) => <li key={row.history_id} className="space-y-2 py-3"><div className="flex flex-wrap items-center gap-2"><span className="text-sm">{label(row.position)} · {relationT(`operations.${row.operation}`)} · {t(`validityStates.${row.validity.current_state!.state}`)}</span><Button size="sm" variant="ghost" onPress={() => void openSource(row.history_id)}>{t("source")}</Button>{!readOnly && row.validity.current_state?.state === "active" && <><Button size="sm" variant="ghost" isDisabled={blocked || !fact} onPress={() => void open(row.position.intent === "book_start" ? "correct_initial" : "replace", row)}>{relationT(`operations.${row.position.intent === "book_start" ? "correct_initial" : "replace"}`)}</Button><Button size="sm" variant="ghost" isDisabled={blocked || !fact} onPress={() => void open("void", row)}>{relationT("operations.void")}</Button></>}</div><p className="reading-copy whitespace-pre-wrap">{row.after.current_state}</p></li>)}</ol>{more && <Button variant="ghost" isDisabled={busy || historyLoading} onPress={() => { if (historyEntity.current) void readHistory(historyEntity.current, undefined, history.at(-1)!.after_version); }}>{t("moreHistory")}</Button>}</details>}
    {preparation && <CharacterRelationFactPreparationDialog key={preparation.key} initialPreparation={preparation} chapters={chapters} onBusy={setBusy} beforeLeaveRef={dialogLeave} onClose={() => { setPreparation((current) => current?.key === preparation.key ? null : current); void readDrafts().catch((failure) => setError(failure.message)); }} onPrepared={(next) => { if (alive.current && visible.current && dialogKeys.current.preparation === preparation.key) { setPreparation(null); setDraft(next); } }} />}
    {draft && <CharacterRelationFactConfirmationDialog key={draft.key} novelId={novelId} initialDraft={draft} onBusy={setBusy} beforeLeaveRef={dialogLeave} onReadback={async (receipt) => {
      const current = await readFacts();
      if (!current || current.entity_id !== receipt.entity_id) throw new Error(relationT("missingRelation"));
      await onChanged?.();
    }} onClose={() => { setDraft((current) => current?.key === draft.key ? null : current); void readDrafts().catch((failure) => setError(failure.message)); }} onRepreview={async (previous) => {
      if (previous.origin) {
        const next = previous.origin.candidateRef
          ? await reprepareCharacterRelationCandidate(novelId, previous)
          : await reprepareChapterRelationFact(novelId, previous);
        if (alive.current && visible.current && dialogKeys.current.draft === previous.key) setPreparation(next);
        return;
      }
      const basis = previous.command?.body.basis ?? previous.preview.basis;
      if (basis.target.kind !== "existing" || basis.operation === "create") throw new Error(relationT("wrongScope"));
      const latest = await readFacts();
      if (!latest || latest.entity_id !== basis.target.entity_id) throw new Error(relationT("missingRelation"));
      const authored = previous.command?.body.operation === "void" ? undefined : (previous.command?.body.after ?? previous.after).current_state;
      const next: ExistingPreparation = { schema_id: "character_relation.fact.preparation", schema_version: 1, kind: "existing", key: crypto.randomUUID(), revision: 1, novel_id: novelId, relation_id: latest.relation_id, target: { entity_id: latest.entity_id, relation_id: latest.relation_id, expected_version: latest.version }, setup: { operation: basis.operation, position: basis.position, note: basis.source.kind === "author" ? basis.source.note : "", evidence: basis.source.kind === "chapter" ? basis.source.evidence : null, record: basis.targets[0] ?? null, resolves: structuredClone(basis.resolves), ...(authored === undefined ? {} : { after: { current_state: authored } }), reason: previous.command?.body.operation === "void" ? previous.command.body.reason : previous.reason } };
      await store.persist(next); if (alive.current && visible.current && dialogKeys.current.draft === previous.key) setPreparation(next);
    }} />}
    {source && <RetainedModalBackdrop isOpen onOpenChange={(openModal) => { if (!openModal) { sourceRequest.current += 1; setSource(null); } }}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full sm:max-w-3xl"><Modal.Header className="border-b border-border px-5 py-4"><Modal.Heading>{t("source")}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} /></Modal.Header><Modal.Body className="space-y-4 px-5 py-5"><dl className="grid gap-4"><ReadOnlyField label={relationT("sourceCharacter")} value={source.source_character_name} /><ReadOnlyField label={relationT("targetCharacter")} value={source.target_character_name} /><ReadOnlyField label={t("position")} value={label(source.position)} /><ReadOnlyField label={relationT("currentState")} value={source.after.current_state} wide /><ReadOnlyField label={t("validity")} value={t(`validityStates.${source.validity.current_state!.state}`)} /></dl>{source.source.kind === "author" ? <p className="reading-copy whitespace-pre-wrap">{source.source.note}</p> : <EvidencePicker novelId={novelId} chapters={[]} value={source.source.evidence} readOnly chapterRecordSource label={t("source")} />}</Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
  </section>;
}
