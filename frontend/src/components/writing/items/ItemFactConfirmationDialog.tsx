"use client";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost } from "@/lib/api";
import { parseItemReadV1, type ItemReadV1 } from "@/types/item";
import type { ItemFactResultV1, ItemFactBatchResultV1, ItemFactReadResultV1, ItemFactValuesV1 } from "@/types/itemFacts";
import { useFactPersistence, confirmFact } from "../characters/factConfirmation";
import type { ItemFactDraftV1, ItemFactBatchDraftV1 } from "./itemFactDrafts";
import ItemFactValues, { validItemFactValues, type ItemFactChoices } from "./ItemFactValues";
import { reprepareItemFact, returnItemFactToCheck, type ItemFactPreparationV1 } from "./itemFactPreparation";
import type { ChapterRecordDraft } from "../chapter-records/chapterRecordDrafts";

type Draft = ItemFactDraftV1 | ItemFactBatchDraftV1;

/** 功能：沿现有确认队列保存单件或整批物品，未知请求只重发原键原内容。Args: 已落盘原稿、选项和当前读取回调。Returns: 原工作台的确认弹窗。 */
export default function ItemFactConfirmationDialog({ novelId, initialDraft, choices, onClose, onReadback, onReprepared, onReturnedToCheck, onBusy, beforeLeaveRef }: {
  novelId: string; initialDraft: Draft; choices: ItemFactChoices; onClose: () => void;
  onReadback: (receipt: ItemFactResultV1 | ItemFactBatchResultV1) => Promise<void>;
  onReprepared: (preparation: ItemFactPreparationV1) => void;
  onReturnedToCheck: (draft: ChapterRecordDraft) => void;
  onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characterFacts");
  const f = useTranslations("writing.itemFacts");
  const active = useContext(RetainedViewActive);
  const [draft, setDraft] = useState(initialDraft);
  const current = useRef(initialDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [exported, setExported] = useState(false);
  const [recovery, setRecovery] = useState<{ preparation: ItemFactPreparationV1; values: ItemFactValuesV1 | null; names?: string[] } | null>(null);
  const pending = useRef(false);
  const alive = useRef(true);
  const errorRef = useRef<HTMLDivElement>(null);
  const batch = draft.schema_id === "item.fact.batch.draft";
  const { persist, remove, queue, persisted, localError } = useFactPersistence<Draft>(batch ? "item_batch" : "item", `${novelId}:${batch ? "item-fact-batches" : "item-facts"}`, t("localFailed"));
  useEffect(() => { persisted.current.set(initialDraft.key, initialDraft.revision); }, [initialDraft, persisted]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, []);
  const keep = async () => { if (pending.current) throw new Error(t("saving")); await persist(current.current); await queue.current; };
  useEffect(() => { if (!beforeLeaveRef) return; beforeLeaveRef.current = keep; return () => { beforeLeaveRef.current = null; }; });
  const update = (next: Draft) => { current.current = next; if (alive.current) setDraft(next); };
  const close = async () => { try { await keep(); onClose(); } catch (failure) { setError((failure as Error).message); } };
  const confirm = async () => {
    if (pending.current || current.current.reprepared || current.current.returnedToCheck) return;
    pending.current = true; setBusy(true); setError(""); setRecovery(null);
    const outcome = await confirmFact<Draft>({ draft: current.current, key: () => crypto.randomUUID(), persist, remove, update,
      send: (command) => apiPost<ItemFactResultV1 | ItemFactBatchResultV1>(`/api/item-facts/novel/${novelId}/${command.schema_id === "item.fact.batch.command" ? "batch/confirm" : "confirm"}`, command.body, { headers: { "Idempotency-Key": command.key } }), readback: onReadback });
    pending.current = false;
    if (!alive.current) return;
    setBusy(false);
    if (outcome.ok) onClose();
    else setError(outcome.stage === "readback" ? t("savedReadFailed") : outcome.stage === "cleanup" ? t("savedCleanupFailed") : outcome.error instanceof Error ? outcome.error.message : t("saveFailed"));
  };
  const prepareAgain = async (accept: boolean) => {
    const previous = current.current;
    if (pending.current || previous.command && (previous.command.unknown !== false || previous.command.saved) || previous.reprepared || previous.returnedToCheck) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const saved = await persist(previous);
      if (saved) { update({ ...previous, revision: previous.revision + 1, command: { ...previous.command, saved, unknown: false, readbackDone: false } } as Draft); setRecovery(null); return; }
      if (accept && recovery) {
        await reprepareItemFact(previous, recovery.preparation);
        onClose(); onReprepared(recovery.preparation); return;
      }
      let preparation: ItemFactPreparationV1;
      let values: ItemFactValuesV1 | null = null;
      let names: string[] | undefined;
      if (previous.schema_id === "item.fact.batch.draft") {
        const rows = await apiGet<ItemReadV1[]>(`/api/items/novel/${novelId}`);
        names = rows.map((row) => parseItemReadV1(row, novelId).name);
        const first = previous.preview.entries[0];
        preparation = { key: crypto.randomUUID(), revision: 1, novelId, operation: "create", kind: "start", generation: structuredClone(previous.command?.body.generation ?? previous.preview.generation),
          position: first.preview.basis.position, note: first.preview.basis.source.kind === "author" ? first.preview.basis.source.note : "", evidence: null, after: first.after, reason: "", resolves: [] };
      } else {
        const body = previous.command?.body, basis = body?.basis ?? previous.preview.basis, target = basis.target;
        const original = previous.preparation;
        preparation = { key: crypto.randomUUID(), revision: 1, novelId, operation: basis.operation, kind: basis.kind,
          position: basis.position, note: basis.source.kind === "author" ? basis.source.note : "", evidence: basis.source.kind === "chapter" ? basis.source.evidence : null,
          after: structuredClone(body?.after ?? previous.after), reason: body?.reason ?? previous.reason, resolves: [...basis.resolves], origin: previous.origin,
          record: original?.record ?? basis.read.records.find((row) => row.history_id === (basis.void_target ?? basis.replaces)), ownerOnly: Boolean(previous.origin) };
        if (target.kind === "new") {
          const rows = await apiGet<ItemReadV1[]>(`/api/items/novel/${novelId}`);
          names = rows.map((row) => parseItemReadV1(row, novelId).name);
          preparation.candidate = { ...target.candidate, ...preparation.after };
        } else {
          const item = parseItemReadV1(await apiGet<unknown>(`/api/items/novel/${novelId}/${target.item_id}`), novelId);
          const read = await apiPost<ItemFactReadResultV1>(`/api/item-facts/novel/${novelId}/read`, { item_ids: [target.item_id], position: basis.kind === "change" ? { ...basis.position, intent: "chapter_before" } : basis.position });
          const currentItem = read.items.find((row) => row.entity_id === target.entity_id && row.item_id === target.item_id);
          if (read.novel_id !== novelId || !currentItem || item.item_id !== target.item_id || currentItem.version !== item.version || item.is_deleted) throw new Error(f("wrongScope"));
          values = currentItem.values;
          preparation.target = { entity_id: target.entity_id, item_id: target.item_id, expected_version: item.version, name: item.name };
          if (preparation.ownerOnly) {
            if (!values || values.lifecycle_status !== "held" || !values.owner_character_id || values.owner_character_id !== basis.before.values?.owner_character_id) throw new Error(f("ownerRecoveryUnavailable"));
            // B/F 只改持有人，另外三项固定为本次源章之前读取的完整状态。
            preparation.after = { ...values, owner_character_id: preparation.after.owner_character_id };
            preparation.ownerBefore = { ...values };
          }
        }
      }
      if (alive.current) setRecovery({ preparation, values, names });
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : t("saveFailed")); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const returnToCheck = async () => {
    if (pending.current || current.current.schema_id !== "item.fact.draft") return;
    pending.current = true; setBusy(true); setError("");
    try {
      await queue.current;
      const returned = await returnItemFactToCheck(novelId, current.current);
      onClose(); onReturnedToCheck(returned);
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  useEffect(() => {
    if (!active || !(error || localError)) return;
    const frame = requestAnimationFrame(() => errorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]")?.focus());
    return () => cancelAnimationFrame(frame);
  }, [active, error, localError]);
  const entries = draft.schema_id === "item.fact.batch.draft" ? draft.preview.entries : [{ candidate_ref: draft.key, preview: draft.preview, after: draft.after }];
  const valuesValid = entries.every((entry) => entry.preview.basis.operation === "void" || validItemFactValues(entry.after, choices));
  const recoverable = !draft.reprepared && !draft.returnedToCheck && (!draft.command || draft.command.unknown === false && !draft.command.saved);
  return <RetainedModalBackdrop isOpen isDismissable={!busy} onOpenChange={(open) => { if (!open) void close(); }}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
    <Modal.Header className="border-b border-border px-5 py-4 sm:px-6"><Modal.Heading>{f(batch ? "confirmBatch" : "confirm")}</Modal.Heading><Modal.CloseTrigger aria-label={t("closeKeep")} isDisabled={busy} /></Modal.Header>
    <Modal.Body className="space-y-5 px-5 py-5 sm:px-6">
      <div ref={errorRef}>{(error || localError) && <RelationEditorErrorSummary message={error === "ITEM_FACT_LOCAL_CONFLICT" || error === "ITEM_FACT_BATCH_LOCAL_CONFLICT" ? f("localConflict") : error || localError} />}</div>
      {draft.command && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{t(draft.command.saved ? draft.command.readbackDone ? "savedCleanup" : "savedReadback" : draft.command.unknown ? "unknownResult" : "frozenRequest")}</p>}
      {draft.reprepared && <p role="status" className="text-sm">{f("reprepared")}</p>}
      {draft.returnedToCheck && <p role="status" className="text-sm">{f("returnedToCheck")}</p>}
      {!draft.command && !valuesValid && <p role="alert" className="text-sm text-danger">{f("invalidValues")}</p>}
      {recovery && <section className="space-y-3 border-y border-border py-3"><h3 className="text-sm font-semibold">{f("currentForRecovery")}</h3>
        {recovery.names ? <p className="reading-copy">{recovery.names.join("、") || f("none")}</p> : <><p className="text-sm">{recovery.preparation.target?.name} · v{recovery.preparation.target?.expected_version}</p><ItemFactValues value={recovery.values} choices={choices} /></>}
        <p className="text-sm text-muted">{f("recoveryConfirm")}</p>
        <Button variant="outline" isDisabled={busy} onPress={() => void prepareAgain(true)}>{draft.command ? t("repreviewExplicit") : f("reprepareDraft")}</Button>
      </section>}
      <dl className="min-w-0 border-y border-border py-3"><dt className="text-xs font-medium text-muted">{t("position")}</dt><dd className="mt-2 reading-copy whitespace-pre-wrap">{draft.command?.positionLabel ?? draft.positionLabel}</dd></dl>
      {entries.map((entry) => { const basis = entry.preview.basis; return <section key={entry.candidate_ref} className="min-w-0 space-y-4 border-t border-border pt-4">
        <h3 className="text-base font-semibold [overflow-wrap:anywhere]">{basis.target.kind === "new" ? basis.target.candidate.name : basis.target.name} · {f(`operations.${basis.operation}`)}</h3>
        <div className="space-y-2"><h4 className="text-xs font-medium text-muted">{t(basis.source.kind === "author" ? "authorNote" : "source")}</h4><div className="reading-copy whitespace-pre-wrap">{basis.source.kind === "author" ? basis.source.note : <blockquote className="border-l-2 border-accent/40 pl-3">{basis.source.evidence.quote}</blockquote>}</div></div>
        <div className="space-y-3"><h4 className="text-sm font-medium">{t("before")}</h4><ItemFactValues value={basis.before.values} choices={choices} /></div>
        {basis.operation !== "void" && <div className="space-y-3"><h4 className="text-sm font-medium">{f("after")}</h4><ItemFactValues value={entry.after} choices={choices} /></div>}
        {basis.operation === "void" && draft.schema_id === "item.fact.draft" && <p className="reading-copy whitespace-pre-wrap">{draft.reason}</p>}
      </section>; })}
      <label className="flex min-h-11 items-start gap-3 text-sm leading-6"><input type="checkbox" className="mt-1 h-4 w-4 accent-accent" checked={Boolean(draft.command) || draft.authorConfirmed} disabled={busy || Boolean(draft.command || draft.reprepared || draft.returnedToCheck)} onChange={(event) => { const next = { ...draft, revision: draft.revision + 1, authorConfirmed: event.target.checked }; update(next); void persist(next).catch(() => {}); }} /><span>{f(batch ? "authorConfirmedBatch" : "authorConfirmed")}</span></label>
    </Modal.Body>
    <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-6">
      {recoverable && <Button variant="outline" isDisabled={busy} onPress={() => void prepareAgain(false)}>{f("readForRecovery")}</Button>}
      {recoverable && draft.schema_id === "item.fact.draft" && draft.origin && <Button variant="outline" isDisabled={busy} onPress={() => void returnToCheck()}>{f("returnToCheck")}</Button>}
      <Button variant="ghost" isDisabled={busy} onPress={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(current.current, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = `item-fact-${current.current.key}.json`; link.click(); URL.revokeObjectURL(url); setExported(true); }}>{t("exportDraft")}</Button>
      {exported && <Button variant="outline" isDisabled={busy} onPress={onClose}>{f("closeAfterCopy")}</Button>}
      <Button variant="ghost" isDisabled={busy} onPress={() => void close()}>{t("closeKeep")}</Button>
      <Button variant="primary" isDisabled={busy || Boolean(draft.reprepared || draft.returnedToCheck) || (!draft.command && (!draft.authorConfirmed || Boolean(localError) || !valuesValid))} onPress={() => void confirm()}>{t(busy ? "saving" : draft.command?.saved ? "retryRead" : draft.command ? "retryOriginal" : "confirm")}</Button>
    </Modal.Footer>
  </Modal.Dialog></Modal.Container></RetainedModalBackdrop>;
}
