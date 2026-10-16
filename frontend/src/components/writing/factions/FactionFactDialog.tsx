"use client";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import { apiPost, ApiRequestError } from "@/lib/api";
import { apiGet } from "@/lib/api";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { CoreFaction } from "@/types/novel";
import type { FactionFactField, FactionFactPreviewV1, FactionFactReadResultV1, FactionFactRecordV1, FactionFactResultV1 } from "@/types/factionFacts";
import { confirmFact, useFactPersistence } from "../characters/factConfirmation";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import { factionFactDraftScope, type FactionFactDraftV1 } from "./factionFactDrafts";
import { factionFactPreviewInput, reprepareFactionFact, removeFactionFactPreparation, writeFactionFactPreparation, type FactionFactPreparationV1 } from "./factionFactPreparation";
import FactionFactFieldsEditor from "./FactionFactFieldsEditor";
import FactionFactValue from "./FactionFactValue";
import CharacterFactPositionPicker from "../characters/CharacterFactPositionPicker";
import { loadCharacterFactChapters } from "../characters/characterFactPositions";

/** 一次确认位置与实际内容；原命令登记后仅原样重试，离开和跨标签均保稿。 */
export default function FactionFactDialog({ novelId, initialPreparation, initialDraft, positionLabel, onClose, onReadback, onBusy, beforeLeaveRef, factions = [], preferredVolumeId }: {
  novelId: string; initialPreparation?: FactionFactPreparationV1; initialDraft?: FactionFactDraftV1;
  positionLabel: string; onClose: () => void; onReadback: (receipt: FactionFactResultV1) => Promise<void>;
  onBusy?: (value: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  factions?: CoreFaction[]; preferredVolumeId?: string;
}) {
  const t = useTranslations("writing.factionFacts"), common = useTranslations("writing.characterFacts");
  const profileT = useTranslations("writing.factions");
  const active = useContext(RetainedViewActive);
  const [preparation, setPreparation] = useState(initialPreparation ?? null), preparationRef = useRef(initialPreparation ?? null);
  const [draft, setDraft] = useState(initialDraft ?? null), draftRef = useRef(initialDraft ?? null);
  const [busy, setBusy] = useState(false), pending = useRef(false), alive = useRef(true);
  const [error, setError] = useState("");
  const editorRef = useRef<HTMLDivElement>(null);
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]), [volumes, setVolumes] = useState<HierarchyRecord[]>([]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    void Promise.all([loadCharacterFactChapters(novelId, abort.signal), apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal: abort.signal })])
      .then(([rows, page]) => { if (!abort.signal.aborted) { setChapters(rows); setVolumes(page.data); } })
      .catch((failure) => { if (!abort.signal.aborted) setError(failure.message); });
    return () => abort.abort();
  }, [novelId, active]);
  const preparationQueue = useRef<Promise<void>>(Promise.resolve());
  const preparationRevision = useRef(initialPreparation?.revision ?? null);
  const persistence = useFactPersistence<FactionFactDraftV1>("faction", factionFactDraftScope(novelId), common("localFailed"));
  useEffect(() => { if (initialDraft) persistence.persisted.current.set(initialDraft.key, initialDraft.revision); }, [initialDraft, persistence.persisted]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  const storePreparation = (next: FactionFactPreparationV1) => {
    const queued = preparationQueue.current.catch(() => {}).then(async () => {
      await writeFactionFactPreparation(next, preparationRevision.current);
      preparationRevision.current = next.revision;
    });
    preparationQueue.current = queued;
    void queued.catch(() => { if (alive.current) setError(common("localFailed")); });
    return queued;
  };
  const keep = async () => {
    if (pending.current) throw new Error(common("saving"));
    // 标签框先提交尚未回车的输入，再保存父级草稿；Escape 与切换页面共用。
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && editorRef.current?.contains(focused)) focused.blur();
    if (preparationRef.current) await storePreparation(preparationRef.current);
    if (draftRef.current) await persistence.persist(draftRef.current);
    await preparationQueue.current; await persistence.queue.current;
  };
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = keep;
    return () => { beforeLeaveRef.current = null; };
  });
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  const updateDraft = (next: FactionFactDraftV1) => { draftRef.current = next; if (alive.current) setDraft(next); };
  const updatePreparation = (next: FactionFactPreparationV1) => {
    preparationRef.current = next; setPreparation(next); void storePreparation(next);
  };
  const close = async () => { try { await keep(); onClose(); } catch (failure) { setError((failure as Error).message); } };
  const discard = async () => {
    if (pending.current || !preparationRef.current || draftRef.current) return;
    pending.current = true; setBusy(true);
    try {
      await preparationQueue.current;
      await removeFactionFactPreparation(preparationRef.current);
      preparationRef.current = null; onClose();
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const save = async () => {
    if (pending.current || draftRef.current?.reprepared) return;
    pending.current = true; setBusy(true); setError("");
    try {
      let next = draftRef.current;
      if (!next) {
        const prepared = preparationRef.current!;
        await storePreparation(prepared);
        const preview = await apiPost<FactionFactPreviewV1>(`/api/faction-facts/novel/${novelId}/preview`, factionFactPreviewInput(prepared));
        next = { schema_id: "faction.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1,
          positionLabel: prepared.position.intent === "book_start" ? common("positions.book_start")
            : prepared.position.intent === "volume_start" ? `${volumes.find((row) => row.volume_id === prepared.position.target_id)?.title ?? ""} · ${common("positions.volume_start")}`
              : chapters.length ? `${chapters.find((row) => row.chapter_id === prepared.position.target_id)?.title ?? ""} · ${common(`positions.${prepared.position.intent}`)}` : positionLabel,
          preview, after: structuredClone(prepared.after), reason: prepared.reason, authorConfirmed: true };
        await writeFactionFactPreparation(prepared, preparationRevision.current, next);
        persistence.persisted.current.set(next.key, next.revision);
        preparationRef.current = null; if (alive.current) setPreparation(null);
        updateDraft(next);
      }
      const confirmed = next.command ? next : { ...next, revision: next.revision + 1, authorConfirmed: true };
      const result = await confirmFact<FactionFactDraftV1>({ draft: confirmed, key: () => crypto.randomUUID(),
        persist: persistence.persist, remove: persistence.remove, update: updateDraft,
        send: (command) => apiPost<FactionFactResultV1>(`/api/faction-facts/novel/${novelId}/confirm`, command.body, { headers: { "Idempotency-Key": command.key } }),
        readback: onReadback });
      if (!alive.current) return;
      if (result.ok) onClose();
      else setError(result.stage === "readback" ? common("savedReadFailed") : result.stage === "cleanup" ? common("savedCleanupFailed")
        : result.error instanceof ApiRequestError ? result.error.message : common("saveFailed"));
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const recheck = async () => {
    const old = draftRef.current, prepared = preparationRef.current;
    if (pending.current || old?.reprepared || old?.command && (old.command.unknown !== false || old.command.saved)) return;
    setBusy(true); pending.current = true;
    try {
      await preparationQueue.current; await persistence.queue.current;
      const basis = old?.command?.body.basis ?? old?.preview.basis;
      const position = basis?.position ?? prepared!.position;
      const target = basis?.target;
      const factionId = target?.kind === "existing" ? target.faction_id : prepared?.target?.faction_id;
      const current = factionId ? (await apiPost<FactionFactReadResultV1>(`/api/faction-facts/novel/${novelId}/read`, { faction_ids: [factionId], position })).factions[0] : null;
      if (factionId && !current) throw new Error(common("wrongScope"));
      const ids = current ? [...new Set([...Object.values(current.origins), ...Object.values(current.blockers).flat()].filter((id): id is string => Boolean(id)))] : [];
      const records = await Promise.all(ids.map((id) => apiGet<FactionFactRecordV1>(`/api/faction-facts/novel/${novelId}/history/${id}`)));
      const voidId = basis?.operation === "void" ? Object.values(basis.void_targets)[0] : prepared?.void_record?.history_id;
      const voidRecord = voidId ? await apiGet<FactionFactRecordV1>(`/api/faction-facts/novel/${novelId}/history/${voidId}`) : null;
      const source = basis?.source;
      const next: FactionFactPreparationV1 = { schema_id: "faction.fact.preparation", schema_version: 1,
        key: old ? crypto.randomUUID() : prepared!.key, revision: old ? 1 : prepared!.revision + 1, novel_id: novelId, position,
        target: current ? { entity_id: current.entity_id, faction_id: current.faction_id, expected_version: current.version } : null,
        candidate: target?.kind === "new" ? target.candidate : prepared?.candidate ?? null,
        initial: current?.values ?? {}, after: structuredClone(old?.after ?? prepared!.after), records,
        blockers: current?.blockers ?? {}, void_record: voidRecord, reason: old?.reason ?? prepared!.reason,
        change: basis && "kind" in basis ? basis.kind === "change" : prepared?.change,
        evidence: source?.kind === "chapter" ? source.evidence : prepared?.evidence,
        comparison: { before: basis?.before.values ?? prepared?.initial ?? {}, current: current?.values ?? {} },
      };
      if (old) await reprepareFactionFact(old, next); else await writeFactionFactPreparation(next, preparationRevision.current);
      preparationRevision.current = next.revision; preparationRef.current = next; setPreparation(next);
      draftRef.current = null; setDraft(null); setError("");
    } catch (failure) { setError((failure as Error).message); }
    finally { pending.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (!active || !(error || persistence.localError)) return;
    const frame = requestAnimationFrame(() => editorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]")?.focus({ preventScroll: true }));
    return () => cancelAnimationFrame(frame);
  }, [active, error, persistence.localError]);
  const command = draft?.command;
  const basis = command?.body.basis ?? draft?.preview.basis;
  const isVoid = basis?.operation === "void" || Boolean(preparation?.void_record);
  const values = command && command.body.operation !== "void" ? command.body.after : draft?.after ?? { ...preparation?.initial, ...preparation?.after };
  const fields = basis?.fields ?? preparation?.fields;
  const reason = command?.body.operation === "void" ? command.body.reason : draft?.reason ?? preparation?.reason ?? "";
  return <RetainedModalBackdrop isOpen isDismissable={!busy} onOpenChange={(open) => { if (!open) void close(); }}>
    <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-4xl">
      <Modal.Header className="border-b border-border px-5 py-4"><Modal.Heading>{t(isVoid ? "voidTitle" : "editTitle")}</Modal.Heading><Modal.CloseTrigger isDisabled={busy} aria-label={common("closeKeep")} /></Modal.Header>
      <Modal.Body className="space-y-5 px-5 py-5"><div ref={editorRef} className="space-y-5">
        {preparation?.candidate ? <><label className="grid gap-2 text-sm"><span>{t("factionName")}</span><input name="name" className={INPUT} maxLength={80} required value={preparation.candidate.name} disabled={busy}
          onChange={(event) => updatePreparation({ ...preparation, revision: preparation.revision + 1, candidate: { ...preparation.candidate!, name: event.target.value } })} /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-2 text-sm"><span>{profileT("fields.levelType")}</span><select className={INPUT} value={preparation.candidate.level_type ?? "core"} disabled={busy} onChange={(event) => {
              const level = event.target.value as "core" | "volume" | "local", volumeId = level === "core" ? null : preparation.candidate!.volume_id ?? preferredVolumeId ?? volumes[0]?.volume_id ?? null;
              updatePreparation({ ...preparation, revision: preparation.revision + 1, candidate: { ...preparation.candidate!, level_type: level, volume_id: volumeId, parent_faction_id: null },
                ...(volumeId ? { position: { version: 1, intent: "volume_start", target_type: "volume", target_id: volumeId } as const } : {}) });
            }}>{["core", "volume", "local"].map((level) => <option key={level} value={level} disabled={level !== "core" && !volumes.length}>{profileT(`categories.${level}`)}</option>)}</select></label>
            {preparation.candidate.level_type !== "core" && <label className="grid gap-2 text-sm"><span>{profileT("fields.volumeId")}</span><select className={INPUT} value={preparation.candidate.volume_id ?? ""} disabled={busy} onChange={(event) => updatePreparation({ ...preparation, revision: preparation.revision + 1,
              candidate: { ...preparation.candidate!, volume_id: event.target.value, parent_faction_id: null }, position: { version: 1, intent: "volume_start", target_type: "volume", target_id: event.target.value } })}>
              <option value="" disabled>{profileT("fields.volumeId")}</option>{volumes.map((volume) => <option key={volume.volume_id} value={volume.volume_id}>{volume.title}</option>)}</select></label>}
            {preparation.candidate.level_type !== "core" && <label className="grid gap-2 text-sm"><span>{profileT("fields.parentFaction")}</span><select className={INPUT} value={preparation.candidate.parent_faction_id ?? ""} disabled={busy} onChange={(event) => updatePreparation({ ...preparation, revision: preparation.revision + 1, candidate: { ...preparation.candidate!, parent_faction_id: event.target.value || null } })}>
              <option value="">{profileT("editor.noParent")}</option>{factions.filter((row) => !row.is_deleted && (row.level_type === "core" || preparation.candidate!.level_type === "local" && row.level_type === "volume" && row.volume_id === preparation.candidate!.volume_id))
                .map((row) => <option key={row.faction_id} value={row.faction_id}>{row.name}</option>)}</select></label>}
          </div>
          <CharacterFactPositionPicker novelId={novelId} chapters={chapters} volumes={volumes} value={preparation.position} required disabled={busy} onChange={(at) => { if (at) updatePreparation({ ...preparation, revision: preparation.revision + 1, position: at }); }} /></>
          : <p className="text-sm font-medium">{command?.positionLabel ?? draft?.positionLabel ?? positionLabel}</p>}
        {(error || persistence.localError) && <RelationEditorErrorSummary message={error || persistence.localError} fieldErrors={{}} />}
        {basis?.target.kind === "new" && <ReadOnlyField label={t("factionName")} value={basis.target.candidate.name} wide />}
        {command && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{common(command.saved ? "savedReadback" : command.unknown ? "unknownResult" : "frozenRequest")}</p>}
        {Object.keys(preparation?.blockers ?? basis?.blockers ?? {}).length > 0 && <p className="text-sm text-amber-700 dark:text-amber-300">{t("reviewSources")}</p>}
        {preparation?.comparison && <details open><summary className="cursor-pointer text-sm text-accent">{t("compareChanges")}</summary><dl className="mt-3 grid gap-3">{Object.keys(preparation.after).map((field) => <ReadOnlyField key={field} label={t(`fields.${field}`)} value={<FactionFactValue field={field} value={preparation.initial[field as FactionFactField]} />} wide />)}</dl></details>}
        {preparation?.change && !isVoid && <EvidencePicker novelId={novelId} chapters={chapters.filter((row) => row.chapter_id === preparation.position.target_id)} value={preparation.evidence ?? null}
          disabled={busy} label={common("source")} onChange={() => updatePreparation({ ...preparation, revision: preparation.revision + 1, evidence: null })}
          onSelectEvidence={(evidence) => updatePreparation({ ...preparation, revision: preparation.revision + 1, evidence })} />}
        {isVoid ? <><dl className="grid gap-4">{Object.entries(preparation?.void_record?.after ?? basis?.targets[0]?.after ?? {}).filter(([field]) => fields?.includes(field as FactionFactField)).map(([field, value]) => <ReadOnlyField key={field} label={t(`fields.${field}`)} value={<FactionFactValue value={value} field={field} />} wide />)}</dl>
          <label className="grid gap-2 text-sm"><span>{common("reason")}</span><textarea className={INPUT} rows={3} value={reason} disabled={busy || Boolean(command)} onChange={(event) => {
            if (draft) { const next = { ...draft, revision: draft.revision + 1, reason: event.target.value }; updateDraft(next); void persistence.persist(next).catch(() => {}); }
            else if (preparation) updatePreparation({ ...preparation, revision: preparation.revision + 1, reason: event.target.value });
          }} /></label></> : <FactionFactFieldsEditor values={values} fields={fields} disabled={busy || Boolean(command)} onChange={(field, value) => {
          if (draft) { const after = { ...draft.after }; if (value === undefined) delete after[field]; else Object.assign(after, { [field]: value }); const next = { ...draft, revision: draft.revision + 1, after, authorConfirmed: false }; updateDraft(next); void persistence.persist(next).catch(() => {}); }
          else if (preparation) { const after = { ...preparation.after }; if (value === undefined || JSON.stringify(value) === JSON.stringify(preparation.initial[field])) delete after[field]; else Object.assign(after, { [field]: value }); updatePreparation({ ...preparation, revision: preparation.revision + 1, after }); }
        }} />}
        {!!basis?.legacy_sources.length && <details><summary className="cursor-pointer text-sm text-accent">{t("legacyTitle")}</summary><p className="my-3 text-sm text-muted">{t("legacyExplanation")}</p>{basis.legacy_sources.map((source) => <dl key={source.kind === "profile" ? source.entity_id : source.state_id} className="grid gap-3 border-t border-border py-3">{Object.entries(source.raw).map(([field, value]) => <ReadOnlyField key={field} label={t(`legacyFields.${field}`)} value={<FactionFactValue value={value} field={field} />} wide />)}</dl>)}</details>}
      </div></Modal.Body>
      <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4">
        {preparation && !draft && <Button variant="ghost" isDisabled={busy} onPress={() => void discard()}>{common("discardClose")}</Button>}
        <Button variant="ghost" isDisabled={busy} onPress={() => void close()}>{common("closeKeep")}</Button>
        {(preparation || command?.unknown === false && !command.saved && !draft?.reprepared) && error && <Button variant="outline" isDisabled={busy} onPress={() => void recheck()}>{t("recheck")}</Button>}
        <Button variant="primary" isDisabled={busy || Boolean(draft?.reprepared) || Boolean(preparation?.change && !preparation.evidence) || Boolean(preparation?.candidate && !preparation.candidate.name.trim()) || (isVoid ? !reason.trim() : !command && !Object.keys(draft?.after ?? preparation?.after ?? {}).length)} onPress={() => void save()}>{common(busy ? "saving" : command?.saved ? "retryRead" : command ? "retryOriginal" : "confirm")}</Button>
      </Modal.Footer>
    </Modal.Dialog></Modal.Container>
  </RetainedModalBackdrop>;
}
