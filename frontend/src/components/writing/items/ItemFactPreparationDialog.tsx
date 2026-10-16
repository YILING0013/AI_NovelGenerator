"use client";

import { TooltipHint } from "@/components/shared/TooltipHint";
import { downloadExport } from "@/lib/userExport";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { ConfirmActionModal, RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiPost, type ApiFieldErrors } from "@/lib/api";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { ItemFactPreviewV1, ItemFactBatchPreviewV1, ItemFactReadResultV1 } from "@/types/itemFacts";
import CharacterFactPositionPicker from "../characters/CharacterFactPositionPicker";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import ItemFieldsForm from "./ItemFieldsForm";
import ItemFactValues, { validItemFactValues, type ItemFactChoices } from "./ItemFactValues";
import type { ItemFactDraftV1, ItemFactBatchDraftV1 } from "./itemFactDrafts";
import { discardItemFactPreparation, isEmptyItemFactPreparation, returnItemFactToCheck, writeItemFactPreparation, type ItemFactPreparationV1 } from "./itemFactPreparation";
import type { ChapterRecordDraft } from "../chapter-records/chapterRecordDrafts";

/** 功能：在原工作台填写物品起点或变化，先保留本地稿再进入确认。Args: 已落盘原稿、目录及引用选项。Returns: 可关闭恢复的准备弹窗。 */
export default function ItemFactPreparationDialog({ initialPreparation, chapters, choices, referenceErrors, isOpen = true, onPrepared, onReturnedToCheck, onClose, onDiscarded, onBusy, beforeLeaveRef }: {
  isOpen?: boolean; referenceErrors?: { character?: string; faction?: string; location?: string };
  initialPreparation: ItemFactPreparationV1; chapters: HierarchyRecord[] | null; choices: ItemFactChoices;
  onPrepared: (draft: ItemFactDraftV1 | ItemFactBatchDraftV1) => void; onClose: () => void;
  onDiscarded: () => void;
  onReturnedToCheck: (draft: ChapterRecordDraft) => void;
  onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characterFacts");
  const f = useTranslations("writing.itemFacts");
  const itemT = useTranslations("writing.items");
  const active = useContext(RetainedViewActive);
  const [draft, setDraft] = useState(initialPreparation);
  const current = useRef(initialPreparation);
  const stored = useRef(initialPreparation.revision);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const alive = useRef(true);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [conflict, setConflict] = useState(false);
  const [exported, setExported] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [blockers, setBlockers] = useState<string[]>([]);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  const persist = (value: ItemFactPreparationV1) => {
    const write = queue.current.catch(() => {}).then(async () => { await writeItemFactPreparation(value, stored.current); stored.current = value.revision; });
    queue.current = write;
    return write;
  };
  const fail = (failure: unknown) => { if (alive.current) { setError((failure as Error).message); if ((failure as Error).message === "ITEM_FACT_LOCAL_CONFLICT") setConflict(true); } };
  const update = (value: ItemFactPreparationV1) => { const next = { ...value, revision: current.current.revision + 1 }; current.current = next; setDraft(next); void persist(next).catch(fail); };
  const keep = async () => { if (pending.current) throw new Error(t("saving")); await persist(current.current); await queue.current; };
  useEffect(() => { if (!beforeLeaveRef || !isOpen) return; beforeLeaveRef.current = keep; return () => { beforeLeaveRef.current = null; }; });
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => { if (!isOpen) return; const guard = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, [isOpen]);
  useEffect(() => {
    setBlockers([]); setReadError(""); setReading(false);
    if (!active || !isOpen || !draft.target || !draft.position || draft.operation === "void") return;
    const abort = new AbortController(); setReading(true);
    const position = draft.kind === "change" ? { ...draft.position, intent: "chapter_before" } : draft.position;
    void apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${draft.novelId}/read`, { item_ids: [draft.target.item_id], position }, { signal: abort.signal }).then((result) => {
      if (abort.signal.aborted) return;
      const item = result.items.find((row) => row.entity_id === draft.target!.entity_id && row.item_id === draft.target!.item_id);
      if (!item || result.novel_id !== draft.novelId) throw new Error(f("wrongScope"));
      setBlockers(item.blockers);
    }).catch((failure) => { if (!abort.signal.aborted) setReadError(failure.message); }).finally(() => { if (!abort.signal.aborted) setReading(false); });
    return () => abort.abort();
  }, [active, isOpen, draft.target, draft.position, draft.operation, draft.kind, draft.novelId, f]);
  useEffect(() => {
    if (!active || !isOpen || !error) return;
    const frame = requestAnimationFrame(() => {
      const root = errorRef.current?.closest<HTMLElement>("[role=dialog]");
      const target = root?.querySelector<HTMLElement>('[aria-invalid="true"]:not(:disabled)') ?? errorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true }); target?.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, isOpen, error, fieldErrors]);
  const discard = async () => {
    if (pending.current || conflict) return;
    pending.current = true; setBusy(true);
    try { await queue.current; await discardItemFactPreparation(current.current); onDiscarded(); }
    catch (failure) { setConfirmDiscard(false); fail(failure); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const close = async () => {
    // Escape 不一定先触发失焦；先提交 TagInput 的当前文字，再判断是否真的空白。
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && errorRef.current?.closest("[role=dialog]")?.contains(focused)) focused.blur();
    if (isEmptyItemFactPreparation(current.current)) { await discard(); return; }
    try { await keep(); onClose(); } catch (failure) { fail(failure); }
  };
  const valuesValid = (draft.operation === "void" || (draft.generation ? draft.generation.candidates.every((row) => validItemFactValues(row, choices)) : validItemFactValues(draft.after, choices)))
    && (!draft.ownerOnly || Boolean(draft.after.owner_character_id && draft.after.owner_character_id !== draft.ownerBefore?.owner_character_id));
  const preview = async () => {
    if (pending.current || conflict || current.current.returnedToCheck || !valuesValid) return;
    const original = structuredClone(current.current);
    const invalid: ApiFieldErrors = {};
    if (original.operation !== "void") {
      if (!original.position) invalid.position = [f("positionRequired")];
      if (original.kind !== "start" && !original.evidence) invalid.evidence = [f("evidenceRequired")];
    } else if (!original.reason.trim()) invalid.reason = [f("reasonRequired")];
    for (const [index, candidate] of (original.candidate ? [original.candidate] : original.generation?.candidates ?? []).entries()) {
      for (const [field, message] of [["name", "nameRequired"], ["item_type", "typeRequired"], ["description", "descriptionRequired"]] as const) {
        if (!candidate[field].trim()) invalid[original.candidate ? field : `candidates.${index}.${field}`] = [itemT(`validation.${message}`)];
      }
    }
    setFieldErrors(invalid);
    if (Object.keys(invalid).length) { setError(itemT("errors.validation")); return; }
    pending.current = true; setBusy(true); setError("");
    try {
      await persist(original);
      const label = original.position?.intent === "book_start" ? t("positions.book_start") : `${chapters?.find((row) => row.chapter_id === original.position?.target_id)?.title ?? original.position?.target_id} · ${t(`positions.${original.position?.intent ?? original.record!.position.intent}`)}`;
      let confirmation: ItemFactDraftV1 | ItemFactBatchDraftV1;
      if (original.generation) {
        const response = await apiPost<ItemFactBatchPreviewV1>(`/api/item-facts/novel/${original.novelId}/batch/preview`, { generation: original.generation, position: original.position, note: original.note });
        confirmation = { schema_id: "item.fact.batch.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel: label, preview: response, preparation: original, authorConfirmed: false };
      } else {
        const { lifecycle_status, ...reference_selection } = original.after;
        void lifecycle_status;
        const { name, ...target } = original.target ?? {};
        void name;
        let input: object;
        if (original.candidate) {
          const { lifecycle_status: status, owner_character_id, controlling_faction_id, current_location_id, ...candidate } = original.candidate;
          void status; void owner_character_id; void controlling_faction_id; void current_location_id;
          input = { operation: "create", candidate, position: original.position, source: { kind: "author", note: original.note }, reference_selection };
        } else if (original.operation === "void") input = { operation: "void", target, history_id: original.record!.history_id };
        else input = { operation: original.operation, target, kind: original.kind, position: original.position, source: original.kind === "start" ? { kind: "author", note: original.note } : { kind: "chapter", evidence: original.evidence }, reference_selection, replaces: original.operation === "replace" || original.operation === "correct_initial" ? original.record?.history_id ?? null : null, resolves: original.resolves };
        const response = await apiPost<ItemFactPreviewV1>(`/api/item-facts/novel/${original.novelId}/preview`, input);
        if (original.ownerOnly && (!original.ownerBefore || (Object.keys(original.ownerBefore) as (keyof typeof original.ownerBefore)[]).some((field) => original.ownerBefore![field] !== response.basis.before.values?.[field]))) throw new Error(f("ownerRecoveryUnavailable"));
        confirmation = { schema_id: "item.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel: label, preview: response, after: original.after, reason: original.reason, preparation: original, origin: original.origin, authorConfirmed: false };
      }
      await writeItemFactPreparation(original, stored.current, confirmation);
      if (alive.current) onPrepared(confirmation);
    } catch (failure) { fail(failure); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const returnToCheck = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      await persist(current.current);
      const returned = await returnItemFactToCheck(draft.novelId, current.current);
      onClose(); onReturnedToCheck(returned);
    } catch (failure) { fail(failure); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const blocked = busy || conflict || Boolean(draft.returnedToCheck);
  const empty = isEmptyItemFactPreparation(draft);
  return <><RetainedModalBackdrop isOpen={isOpen} isDismissable={!blocked && !confirmDiscard} onOpenChange={(open) => { if (!open) void close(); }}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
    <Modal.Header className="border-b border-border px-5 py-4 sm:px-6"><Modal.Heading>{f(draft.generation ? "prepareBatch" : `operations.${draft.operation}`)}</Modal.Heading><Modal.CloseTrigger aria-label={empty ? f("closeEmpty") : t("closeKeep")} isDisabled={blocked} /></Modal.Header>
    <Modal.Body className="space-y-5 px-5 py-5 sm:px-6">
      <div ref={errorRef}>{error && <RelationEditorErrorSummary message={conflict ? f("localConflict") : error} fieldErrors={fieldErrors} />}</div>
      {draft.operation !== "void" && <CharacterFactPositionPicker required error={fieldErrors.position?.[0]} novelId={draft.novelId} chapters={chapters} value={draft.position} disabled={blocked || Boolean(draft.ownerOnly) || Boolean(draft.record) || draft.operation === "correct_initial"} afterOnly={draft.kind === "change"} onChange={(position) => update({ ...draft, position, evidence: null, resolves: [] })} />}
      {draft.operation === "void" ? <label className="grid min-w-0 gap-2 text-xs font-medium text-muted"><span>{t("reason")}<span aria-hidden="true" className="ml-1 text-danger">*</span></span><textarea name="reason" required aria-required="true" aria-label={t("reason")} aria-invalid={Boolean(fieldErrors.reason)} aria-describedby={fieldErrors.reason ? `${draft.key}-reason-error` : undefined} className={INPUT} rows={3} maxLength={2000} value={draft.reason} disabled={blocked} onChange={(event) => update({ ...draft, reason: event.target.value })} />{fieldErrors.reason && <span id={`${draft.key}-reason-error`} className="text-danger">{fieldErrors.reason[0]}</span>}</label>
        : draft.kind === "start" ? <div className="grid min-w-0 gap-2 text-xs font-medium text-muted"><span><TooltipHint label={t("authorNote")} text={f("noteHelp")} /></span><textarea name="note" aria-label={t("authorNote")} aria-invalid={Boolean(fieldErrors.note)} aria-describedby={fieldErrors.note ? `${draft.key}-note-error` : undefined} className={INPUT} rows={3} maxLength={2000} value={draft.note} disabled={blocked} onChange={(event) => update({ ...draft, note: event.target.value })} />{fieldErrors.note && <span id={`${draft.key}-note-error`} className="text-danger">{fieldErrors.note[0]}</span>}</div>
        : <div tabIndex={-1} aria-label={t("source")} aria-invalid={Boolean(fieldErrors.evidence)} aria-describedby={fieldErrors.evidence ? `${draft.key}-evidence-error` : undefined}><EvidencePicker key={draft.position?.target_id ?? "none"} novelId={draft.novelId} chapters={chapters?.filter((row) => row.chapter_id === draft.position?.target_id) ?? []} value={draft.evidence} disabled={blocked || !draft.position} label={t("source")} onChange={(value) => { if (!value) update({ ...draft, evidence: null }); }} onSelectEvidence={(evidence) => update({ ...draft, evidence })} />{fieldErrors.evidence && <p id={`${draft.key}-evidence-error`} className="mt-2 text-xs text-danger">{fieldErrors.evidence[0]}</p>}</div>}
      {draft.candidate ? <ItemFieldsForm value={draft.candidate} referenceErrors={referenceErrors} fieldErrors={fieldErrors} characters={choices.characters as Parameters<typeof ItemFieldsForm>[0]["characters"]} factions={choices.factions as Parameters<typeof ItemFieldsForm>[0]["factions"]} locations={choices.locations as Parameters<typeof ItemFieldsForm>[0]["locations"]} disabled={blocked} errorIdPrefix={draft.key} onChange={(candidate) => update({ ...draft, candidate, after: { lifecycle_status: candidate.lifecycle_status, owner_character_id: candidate.owner_character_id, controlling_faction_id: candidate.controlling_faction_id, current_location_id: candidate.current_location_id } })} />
        : draft.generation ? <ul className="divide-y divide-border">{draft.generation.candidates.map((row, index) => <li key={row.candidate_ref} className="min-w-0 py-3"><details open={index === 0 || Object.keys(fieldErrors).some((field) => field.startsWith(`candidates.${index}.`))}><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold [overflow-wrap:anywhere]">{row.name || f("untitledDraft")}</summary><ItemFieldsForm value={row} fieldErrors={Object.fromEntries(Object.entries(fieldErrors).filter(([field]) => field.startsWith(`candidates.${index}.`)).map(([field, messages]) => [field.replace(`candidates.${index}.`, ""), messages]))} characters={choices.characters as Parameters<typeof ItemFieldsForm>[0]["characters"]} factions={choices.factions as Parameters<typeof ItemFieldsForm>[0]["factions"]} locations={choices.locations as Parameters<typeof ItemFieldsForm>[0]["locations"]} referenceErrors={referenceErrors} disabled={blocked} errorIdPrefix={`${draft.key}-${row.candidate_ref}`} onChange={(fields) => update({ ...draft, generation: { ...draft.generation!, candidates: draft.generation!.candidates.map((candidate) => candidate.candidate_ref === row.candidate_ref ? { ...candidate, ...fields } : candidate) } })} /></details></li>)}</ul>
        : draft.operation !== "void" && <ItemFactValues value={draft.after} choices={choices} disabled={blocked} ownerOnly={draft.ownerOnly} onChange={(after) => update({ ...draft, after })} />}
      {draft.ownerOnly && <p className="text-sm text-muted">{f("ownerRecoveryDirection")}</p>}
      {draft.returnedToCheck && <p role="status" className="text-sm">{f("returnedToCheck")}</p>}
      {!valuesValid && <p role="alert" className="text-sm text-danger">{f("invalidValues")}</p>}
      {reading && <p role="status">{t("loading")}</p>}{readError && <p role="alert">{readError}</p>}
      {blockers.map((id) => <label key={id} className="flex min-h-11 items-start gap-2 text-sm"><input type="checkbox" disabled={blocked} checked={draft.resolves.includes(id)} onChange={(event) => update({ ...draft, resolves: event.target.checked ? [...draft.resolves, id] : draft.resolves.filter((entry) => entry !== id) })} /><span>{f("resolve", { id })}</span></label>)}
    </Modal.Body>
    <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-6">
      {draft.origin && !draft.returnedToCheck && <Button variant="outline" isDisabled={blocked} onPress={() => void returnToCheck()}>{f("returnToCheck")}</Button>}
      {(conflict || draft.returnedToCheck) && <Button variant="outline" isDisabled={busy} onPress={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(current.current, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = `item-preparation-${current.current.key}.json`; void downloadExport(link); URL.revokeObjectURL(url); setExported(true); }}>{t("exportDraft")}</Button>}
      {exported && <Button variant="outline" isDisabled={busy} onPress={onClose}>{f("closeAfterCopy")}</Button>}
      {!empty && !draft.origin && !draft.returnedToCheck && <Button variant="ghost" className="text-danger" isDisabled={blocked} onPress={() => setConfirmDiscard(true)}>{f("discardPreparation")}</Button>}
      <Button variant="ghost" isDisabled={busy || conflict} onPress={() => void close()}>{empty ? f("closeEmpty") : t("closeKeep")}</Button><Button variant="primary" isDisabled={blocked || reading || Boolean(readError) || !valuesValid} onPress={() => void preview()}>{t(busy ? "loading" : "preview")}</Button>
    </Modal.Footer>
  </Modal.Dialog></Modal.Container></RetainedModalBackdrop>
    {isOpen && confirmDiscard && <ConfirmActionModal title={f("discardPreparation")} message={f("discardPreparationMessage")} confirmText={f("discardPreparation")} cancelText={itemT("actions.cancel")} danger isLoading={busy} onCancel={() => setConfirmDiscard(false)} onConfirm={() => void discard()} />}
  </>;
}
