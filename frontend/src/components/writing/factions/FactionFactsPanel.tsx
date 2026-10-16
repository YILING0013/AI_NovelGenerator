"use client";

import { useCallback, useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import DraftChip from "@/components/shared/DraftChip";
import { SectionActionButton } from "@/components/shared/SectionEditButton";
import { apiGet, apiPost } from "@/lib/api";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { FactionFactPositionV1, FactionFactReadResultV1, FactionFactRecordV1, FactionFactResultV1, FactionFactsAtPositionV1 } from "@/types/factionFacts";
import CharacterFactPositionPicker from "../characters/CharacterFactPositionPicker";
import { loadCharacterFactChapters } from "../characters/characterFactPositions";
import { readFactDrafts, writeFactDraft } from "../characters/factDraftStorage";
import { factionFactDraftScope, type FactionFactDraftV1 } from "./factionFactDrafts";
import { readFactionFactPreparations, removeFactionFactPreparation, writeFactionFactPreparation, type FactionFactPreparationV1 } from "./factionFactPreparation";
import { FACTION_FACT_SECTIONS } from "./factionFactFields";
import FactionFactDialog from "./FactionFactDialog";
import FactionFactValue from "./FactionFactValue";
import EvidencePicker from "../foreshadowings/EvidencePicker";

interface Props {
  novelId: string; factionId: string; initialPosition?: FactionFactPositionV1;
  readOnly?: boolean; onChanged?: () => Promise<void> | void;
  volumeStartPreview?: boolean;
  onRead?: (value: FactionFactsAtPositionV1 | null) => void;
  onBusy?: (value: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}

/** 详情与卷工作台共用原位置读取；切换身份时隔离请求和草稿生命周期。 */
export default function FactionFactsPanel(props: Props) {
  return <FactionFactsContent key={`${props.novelId}:${props.factionId}:${props.initialPosition?.intent ?? "latest"}:${props.initialPosition?.target_id ?? ""}`} {...props} />;
}

function FactionFactsContent({ novelId, factionId, initialPosition, readOnly = false, volumeStartPreview = false, onChanged, onRead, onBusy, beforeLeaveRef }: Props) {
  const t = useTranslations("writing.factionFacts"), common = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const [position, setPosition] = useState<FactionFactPositionV1 | null>(initialPosition ?? null);
  const [result, setResult] = useState<FactionFactReadResultV1 | null>(null);
  const [history, setHistory] = useState<FactionFactRecordV1[]>([]), [historyMore, setHistoryMore] = useState(false);
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]), [volumes, setVolumes] = useState<HierarchyRecord[]>([]);
  const [error, setError] = useState(""), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const [preparations, setPreparations] = useState<FactionFactPreparationV1[]>([]), [drafts, setDrafts] = useState<FactionFactDraftV1[]>([]);
  const [preparation, setPreparation] = useState<FactionFactPreparationV1 | null>(null), [draft, setDraft] = useState<FactionFactDraftV1 | null>(null);
  const [source, setSource] = useState<FactionFactRecordV1 | null>(null);
  const sourceRequest = useRef(0);
  const alive = useRef(true), request = useRef(0), dialogLeave = useRef<(() => Promise<void>) | null>(null);
  const readCallback = useRef(onRead); readCallback.current = onRead;
  const fact = result?.factions.find((row) => row.faction_id === factionId) ?? null;
  const base = `/api/faction-facts/novel/${novelId}`;
  const label = (value: FactionFactPositionV1) => value.intent === "book_start" ? common("positions.book_start")
    : value.intent === "volume_start" ? `${volumes.find((row) => row.volume_id === value.target_id)?.title ?? ""} · ${common("positions.volume_start")}`
      : `${chapters.find((row) => row.chapter_id === value.target_id)?.title ?? common("source")} · ${common(`positions.${value.intent}`)}`;
  const readDrafts = useCallback(async () => {
    const [pending, saved] = await Promise.all([readFactionFactPreparations(novelId), readFactDrafts<FactionFactDraftV1>("faction", factionFactDraftScope(novelId))]);
    if (!alive.current) return;
    setPreparations(pending.filter((row) => row.target?.faction_id === factionId));
    setDrafts(saved.filter((row) => !row.reprepared && row.preview.basis.target.kind === "existing" && row.preview.basis.target.faction_id === factionId));
  }, [novelId, factionId]);
  const readFacts = useCallback(async (at: FactionFactPositionV1 | null, signal?: AbortSignal) => {
    const current = ++request.current;
    const response = await apiPost<FactionFactReadResultV1>(`${base}/read`, { faction_ids: [factionId], position: at }, { signal });
    if (response.novel_id !== novelId || response.factions.some((row) => row.faction_id !== factionId)) throw new Error(common("wrongScope"));
    const row = response.factions.find((item) => item.faction_id === factionId);
    const records = row ? await apiGet<FactionFactRecordV1[]>(`${base}/history?${new URLSearchParams({ entity_id: row.entity_id, limit: "100" })}`, { signal }) : [];
    if (signal?.aborted || !alive.current || current !== request.current) { if (!signal) throw new Error(common("readInterrupted")); return; }
    setResult(response); setHistory(records); setHistoryMore(records.length === 100); setError(""); readCallback.current?.(row ?? null);
  }, [base, factionId, novelId, common]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current += 1; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (busy) throw new Error(common("saving")); await dialogLeave.current?.(); };
    return () => { beforeLeaveRef.current = null; };
  });
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); setLoading(true);
    void readFacts(position, abort.signal).catch((failure) => { if (!abort.signal.aborted) { setError(failure.message); setResult(null); readCallback.current?.(null); } }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    if (!volumeStartPreview) void readDrafts().catch(() => { if (!abort.signal.aborted) setError(common("localFailed")); });
    return () => { abort.abort(); request.current += 1; sourceRequest.current += 1; };
  }, [active, readFacts, readDrafts, position, refresh, common, volumeStartPreview]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    void Promise.all([loadCharacterFactChapters(novelId, abort.signal), apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal: abort.signal })])
      .then(([rows, page]) => { if (!abort.signal.aborted) { setChapters(rows); setVolumes(page.data); } })
      .catch((failure) => { if (!abort.signal.aborted) setError(failure.message); });
    return () => abort.abort();
  }, [active, novelId, refresh]);
  const open = async (record?: FactionFactRecordV1, voidRecord = false, change = false) => {
    if (!fact || !result || busy) return;
    setBusy(true); setError("");
    try {
      const ids = [...new Set([...Object.values(fact.origins), ...Object.values(fact.blockers).flat()].filter((id): id is string => Boolean(id)))];
      const originals = await Promise.all(ids.map((id) => history.find((item) => item.history_id === id) ?? apiGet<FactionFactRecordV1>(`${base}/history/${id}`)));
      const next: FactionFactPreparationV1 = { schema_id: "faction.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1,
        novel_id: novelId, position: record?.position ?? { version: 1, intent: result.position.intent, target_type: result.position.target_type, target_id: result.position.target_id } as FactionFactPositionV1,
        target: { entity_id: fact.entity_id, faction_id: fact.faction_id, expected_version: fact.version }, candidate: null,
        initial: structuredClone(record?.after ?? fact.values), after: {}, records: record ? [record] : originals,
        ...(record ? { fields: Object.entries(record.validity).filter(([, state]) => state?.state === "active").map(([field]) => field as keyof typeof record.after) } : {}),
        blockers: structuredClone(fact.blockers), void_record: voidRecord ? record! : null, reason: "", change: change || record?.kind === "change", evidence: record?.source.kind === "chapter" ? record.source.evidence : null };
      await writeFactionFactPreparation(next, null);
      if (alive.current) { setPreparation(next); setDraft(null); }
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { if (alive.current) setBusy(false); }
  };
  const readback = async (receipt: FactionFactResultV1) => {
    const at = receipt.record?.position ?? draft?.preview.basis.position ?? preparation?.position ?? position;
    await readFacts(at); setPosition(at); await onChanged?.();
  };
  const close = () => { setPreparation(null); setDraft(null); void readDrafts().catch(() => setError(common("localFailed"))); };
  const openSource = async (historyId: string) => {
    const current = ++sourceRequest.current;
    try {
      const record = history.find((row) => row.history_id === historyId) ?? await apiGet<FactionFactRecordV1>(`${base}/history/${historyId}`);
      if (alive.current && current === sourceRequest.current) setSource(record);
    } catch (failure) { if (alive.current && current === sourceRequest.current) setError((failure as Error).message); }
  };
  return <section className={volumeStartPreview ? "space-y-4" : "mt-8 space-y-6"} aria-label={volumeStartPreview ? common("volumeStartTitle") : t("title")}>
    <div className={`workspace-toolbar flex flex-wrap gap-3 ${volumeStartPreview ? "items-center" : "items-end"}`}><div className="min-w-0 flex-1">{volumeStartPreview ? <h3 className="text-sm font-semibold">{common("volumeStartTitle")}</h3> : <CharacterFactPositionPicker novelId={novelId} chapters={chapters} volumes={volumes} value={position} latest disabled={busy || Boolean(preparation || draft)} onChange={(at) => { sourceRequest.current += 1; setSource(null); setPosition(at); setResult(null); setHistory([]); }} />}</div>
      <SectionActionButton action="refresh" label={common("refresh")} variant="ghost" isDisabled={busy || loading || Boolean(preparation || draft)} onPress={() => setRefresh((value) => value + 1)} /></div>
    {result && !volumeStartPreview && <p className="text-xs text-muted">{common("resolvedPosition", { position: label(result.position as FactionFactPositionV1) })}</p>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {loading && <p role="status">{common("loading")}</p>}
    {fact && Object.entries(FACTION_FACT_SECTIONS).map(([section, fields], index) => <DocumentSection key={section} number={String(index + 1).padStart(2, "0")} title={t(`sections.${section}`)}
      actions={!readOnly && <SectionActionButton action="edit" label={t("editTitle")} variant="ghost" isDisabled={busy || loading || Boolean(error || preparation || draft)} onPress={() => void open()} />}>
      <dl className="detail-fields grid gap-4">{fields.map((field) => {
        const value = fact.values[field], text = !fact.unknown[field] && typeof value === "string" && value !== "" && field !== "story_status";
        return <div key={field} className={`min-w-0 ${text && (value.length > 120 || value.includes("\n")) ? "col-span-full" : ""}`}><ReadOnlyField label={t(`fields.${field}`)} wide={text} value={fact.unknown[field]
          ? <span className="text-amber-700 dark:text-amber-300">{common(`unknown.${fact.unknown[field]}`)}</span>
          : text ? value : <FactionFactValue value={value} field={field} />} />
          <div className="flex flex-wrap gap-1">
            {fact.origins[field] && <Button size="sm" variant="ghost" onPress={() => void openSource(fact.origins[field]!)}>{common("source")}</Button>}
            {fact.blockers[field]?.map((historyId) => <Button key={historyId} size="sm" variant="ghost" onPress={() => void openSource(historyId)}>{common("blockingSource")}</Button>)}
          </div>
        </div>;
      })}</dl>
    </DocumentSection>)}
    {!readOnly && result?.position.intent === "chapter_after" && <Button size="sm" variant="outline" isDisabled={busy || loading || Boolean(error || preparation || draft)} onPress={() => void open(undefined, false, true)}>{t("recordChange")}</Button>}
    {!readOnly && (preparations.length > 0 || drafts.length > 0) && <div className="flex flex-wrap gap-2" aria-label={common("retainedDrafts")}>
      {preparations.map((row) => <DraftChip key={row.key} label={label(row.position)} isDisabled={busy || Boolean(preparation || draft)} onResume={() => { setPreparation(row); setDraft(null); }}
        onDiscard={async () => { await removeFactionFactPreparation(row); await readDrafts(); }} />)}
      {drafts.map((row) => <DraftChip key={row.key} label={row.positionLabel} status={row.command?.saved ? "saved" : row.command ? row.command.unknown ? "pending" : "rejected" : "draft"} isDisabled={busy || Boolean(preparation || draft)} onResume={() => { setDraft(row); setPreparation(null); }}
        onDiscard={!row.command || row.command.saved && row.command.readbackDone ? async () => { await writeFactDraft("faction", factionFactDraftScope(novelId), row, row.revision, true); await readDrafts(); } : undefined} />)}
    </div>}
    {!!history.length && <details><summary className="cursor-pointer py-2 text-sm text-accent">{common("history")}</summary><ol className="space-y-3">{history.map((record) => <li key={record.history_id} className="space-y-3 border-b border-border py-4">
      <p className="text-sm font-medium">{label(record.position)}</p><dl className="grid gap-3">{Object.entries(record.after).map(([field, value]) => <ReadOnlyField key={field} label={t(`fields.${field}`)} value={<><FactionFactValue value={value} field={field} /><span className="mt-1 block text-xs text-muted">{t(`validity.${record.validity[field as keyof typeof record.validity]?.state ?? "active"}`)}</span></>} wide />)}</dl>
      <Button size="sm" variant="ghost" onPress={() => void openSource(record.history_id)}>{common("source")}</Button>
      {!readOnly && Object.values(record.validity).some((value) => value.state === "active") && <div className="flex flex-wrap gap-2"><Button size="sm" variant="ghost" isDisabled={busy || Boolean(preparation || draft)} onPress={() => void open(record)}>{t("correctRecord")}</Button><Button size="sm" variant="ghost" isDisabled={busy || Boolean(preparation || draft)} onPress={() => void open(record, true)}>{t("voidTitle")}</Button></div>}
    </li>)}</ol>{historyMore && <Button variant="ghost" isDisabled={busy} onPress={async () => { try { const next = await apiGet<FactionFactRecordV1[]>(`${base}/history?${new URLSearchParams({ entity_id: fact!.entity_id, limit: "100", before_version: String(history.at(-1)!.after_version) })}`); setHistory((rows) => [...rows, ...next]); setHistoryMore(next.length === 100); } catch (failure) { setError((failure as Error).message); } }}>{common("moreHistory")}</Button>}</details>}
    {(preparation || draft) && <FactionFactDialog key={preparation?.key ?? draft!.key} novelId={novelId} initialPreparation={preparation ?? undefined} initialDraft={draft ?? undefined}
      positionLabel={draft?.positionLabel ?? label(preparation!.position)} onClose={close} onReadback={readback} onBusy={setBusy} beforeLeaveRef={dialogLeave} />}
    {source && <RetainedModalBackdrop isOpen onOpenChange={(openModal) => { if (!openModal) setSource(null); }}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full max-w-3xl"><Modal.Header className="px-5 py-4"><Modal.Heading>{common("source")}</Modal.Heading><Modal.CloseTrigger aria-label={common("close")} /></Modal.Header><Modal.Body className="space-y-4 px-5 py-5">
      <p className="text-sm">{source.faction_name} · {label(source.position)}</p>
      <dl className="detail-fields grid gap-3">{Object.entries(source.after).map(([field, value]) => <ReadOnlyField key={field} label={t(`fields.${field}`)} value={typeof value === "string" && field !== "story_status" ? value : <FactionFactValue field={field} value={value} />} wide />)}</dl>
      {source.source.kind === "author" ? <p className="reading-copy whitespace-pre-wrap">{source.source.note}</p> : <EvidencePicker novelId={novelId} chapters={[]} value={source.source.evidence} readOnly chapterRecordSource label={common("source")} />}
    </Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
  </section>;
}
