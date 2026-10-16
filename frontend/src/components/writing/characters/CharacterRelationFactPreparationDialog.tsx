"use client";
import { TooltipHint } from "@/components/shared/TooltipHint";

import { downloadExport } from "@/lib/userExport";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterResponseV1 } from "@/types/character";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { CharacterRelationFactPreviewInputV1, CharacterRelationFactPreviewV1, CharacterRelationFactReadResultV1, CharacterRelationFactRecordV1 } from "@/types/characterRelationFacts";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import CharacterFactPositionPicker from "./CharacterFactPositionPicker";
import { characterFactPositionKey } from "./characterFactPositions";
import { CharacterRelationDesignFields } from "./CharacterRelationDesignSection";
import type { CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import { useCharacterRelationFactPreparationPersistence, type CharacterRelationFactPreparationV1 } from "./characterRelationFactPreparation";

/** 功能：保留原目标版本和作者选择，再申请零写入预览。Args: 已保存的准备稿、真实目录及人物名称。Returns: 新建和既有关系共用的准备弹窗，不注册生产入口。 */
export default function CharacterRelationFactPreparationDialog({ initialPreparation, chapters, characters = [], onPrepared, onClose, onBusy, beforeLeaveRef }: {
  initialPreparation: CharacterRelationFactPreparationV1; chapters: HierarchyRecord[]; characters?: CharacterResponseV1[];
  onPrepared: (draft: CharacterRelationFactDraftV1) => void; onClose: () => void; onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characterFacts");
  const relationT = useTranslations("writing.characterRelationFacts");
  const active = useContext(RetainedViewActive);
  const [preparation, setPreparation] = useState(initialPreparation);
  const current = useRef(initialPreparation);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const alive = useRef(true);
  const errorRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [storageConflict, setStorageConflict] = useState(false);
  const [exportRequested, setExportRequested] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [blockers, setBlockers] = useState<string[]>([]);
  const [samePosition, setSamePosition] = useState<CharacterRelationFactRecordV1[]>([]);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState("");
  const store = useCharacterRelationFactPreparationPersistence(initialPreparation.novel_id);
  const novelId = preparation.novel_id;
  const operation = preparation.kind === "create" ? "create" : preparation.setup.operation;
  const setup = preparation.kind === "existing" ? preparation.setup : null;
  const position = preparation.kind === "create" ? preparation.position : preparation.setup.position;
  const kind = setup?.record?.kind ?? (operation === "change" ? "change" : "start");
  const note = preparation.kind === "create" ? preparation.note : preparation.setup.note;
  const blocked = busy || storageConflict;
  const discard = async () => {
    if (pending.current || storageConflict || current.current.origin) return;
    pending.current = true; setBusy(true);
    try { await store.remove(current.current); onClose(); }
    catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  useEffect(() => { store.persisted.current.set(initialPreparation.key, initialPreparation.revision); }, [initialPreparation, store]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, []);
  const keep = async () => { if (pending.current) throw new Error(t("saving")); await store.persist(current.current); await store.queue.current; };
  useEffect(() => { if (!beforeLeaveRef) return; beforeLeaveRef.current = keep; return () => { beforeLeaveRef.current = null; }; });
  const update = (next: CharacterRelationFactPreparationV1) => {
    const changed = { ...next, revision: current.current.revision + 1 };
    current.current = changed; setPreparation(changed); setFieldErrors({});
    void store.persist(changed).catch((failure) => { if (alive.current) {
      setError(failure.message);
      if (failure.message === "CHARACTER_RELATION_FACT_PREPARATION_CONFLICT") setStorageConflict(true);
    } });
  };
  const target = preparation.kind === "existing" ? preparation.target : null;
  useEffect(() => {
    setBlockers([]); setSamePosition([]); setReadError(""); setReading(false);
    if (!active || !position || !target || operation === "void") return;
    const abort = new AbortController(); setReading(true);
    const before = kind === "change" && position.target_type === "chapter" ? { ...position, intent: "chapter_before" as const } : position;
    void apiPost<CharacterRelationFactReadResultV1>(`/api/character-relation-facts/novel/${novelId}/read`, { relation_ids: [target.relation_id], position: before }, { signal: abort.signal }).then(async (result) => {
      if (abort.signal.aborted) return;
      const row = result.relations.find((item) => item.entity_id === target.entity_id && item.relation_id === target.relation_id);
      if (result.novel_id !== novelId || !row) throw new Error(relationT("missingRelation"));
      setBlockers(row.blockers.current_state ?? []);
      if (preparation.origin) {
        // 只提供同位置的原记录供作者选择，不从读取结果更新检查时的目标版本。
        const matches: CharacterRelationFactRecordV1[] = [];
        let beforeVersion: number | undefined;
        for (;;) {
          const query = new URLSearchParams({ entity_id: target.entity_id, limit: "100" });
          if (beforeVersion !== undefined) query.set("before_version", String(beforeVersion));
          const rows = await apiGet<CharacterRelationFactRecordV1[]>(`/api/character-relation-facts/novel/${novelId}/history?${query}`, { signal: abort.signal });
          if (abort.signal.aborted) return;
          if (rows.some((record) => record.novel_id !== novelId || record.entity_id !== target.entity_id || record.relation_id !== target.relation_id)) throw new Error(relationT("wrongHistory"));
          matches.push(...rows.filter((record) => record.position.intent === position.intent && record.position.target_id === position.target_id && record.validity.current_state.state === "active"));
          if (rows.length < 100) break;
          beforeVersion = rows.at(-1)!.after_version;
        }
        setSamePosition(matches);
      }
    }).catch((failure) => { if (!abort.signal.aborted) setReadError(failure.message); }).finally(() => { if (!abort.signal.aborted) setReading(false); });
    return () => abort.abort();
  }, [active, kind, novelId, operation, position, preparation.origin, relationT, target]);
  useEffect(() => {
    if (!active || !error) return;
    const frame = requestAnimationFrame(() => { const summary = errorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]"); const target = summary?.closest('[role="dialog"]')?.querySelector<HTMLElement>("[aria-invalid=true]") ?? summary; if (target && !target.closest("[inert]")) target.focus(); });
    return () => cancelAnimationFrame(frame);
  }, [active, error]);
  const close = async () => { try { await keep(); onClose(); } catch (failure) { if (alive.current) {
    setError((failure as Error).message);
    if ((failure as Error).message === "CHARACTER_RELATION_FACT_PREPARATION_CONFLICT") setStorageConflict(true);
  } } };
  const exportCopy = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true);
    try {
      // 只等本页已排队的保稿结束，不再碰另一页持有的稿。
      await store.queue.current.catch(() => {});
      if (!alive.current) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(current.current, null, 2)], { type: "application/json;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `character-relation-preparation-${current.current.key}.json`;
      void downloadExport(link); URL.revokeObjectURL(url); setExportRequested(true);
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const preview = async () => {
    if (pending.current) return;
    if (operation !== "void" && (!position || (kind === "start" ? !note.trim() : !setup?.evidence))) { setError(relationT("previewRequired")); return; }
    if (kind === "start" && Array.from(note).length > 2000) { setError(relationT("tooLong")); return; }
    pending.current = true; setBusy(true); setError("");
    try {
      await store.persist(current.current); await store.queue.current;
      const original = structuredClone(current.current);
      let input: CharacterRelationFactPreviewInputV1;
      if (original.kind === "create") input = { operation: "create", target: { candidate: original.candidate }, position: original.position!, source: { kind: "author", note: original.note }, fields: ["current_state"] };
      else if (original.setup.operation === "void") input = { operation: "void", target: original.target, targets: { current_state: original.setup.record!.history_id } };
      else input = { operation: original.setup.operation, target: original.target, kind, position: original.setup.position!, source: kind === "start" ? { kind: "author", note: original.setup.note } : { kind: "chapter", evidence: original.setup.evidence! }, fields: ["current_state"], replaces: original.setup.record ? { current_state: original.setup.record.history_id } : {}, resolves: original.setup.resolves };
      const response = await apiPost<CharacterRelationFactPreviewV1>(`/api/character-relation-facts/novel/${novelId}/preview`, input);
      const anchor = response.basis.position;
      const positionLabel = anchor.intent === "book_start" ? t("positions.book_start") : anchor.intent === "volume_start" ? t("positions.volume_start") : `${chapters.find((chapter) => chapter.chapter_id === anchor.target_id)?.title ?? anchor.target_id} · ${t(`positions.${anchor.intent}`)}`;
      // 未认领的裸值不填入 after；只保留已知前值或作者明确带来的改稿。
      const authored = original.kind === "create" ? original.after : original.setup.after;
      const draft: CharacterRelationFactDraftV1 = { schema_id: "character_relation.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel, preview: response, after: operation === "void" ? {} : { ...response.values.values, ...authored }, reason: original.kind === "existing" ? original.setup.reason ?? "" : "", authorConfirmed: false, ...(original.origin ? { origin: original.origin } : {}) };
      await store.promote(original, draft);
      if (alive.current) onPrepared(draft);
    } catch (failure) { if (alive.current) {
      setError(preparation.origin && failure instanceof ApiRequestError && failure.code === "CHARACTER_RELATION_FACT_VERSION_CONFLICT" ? relationT("recheckRequired") : (failure as Error).message);
      if ((failure as Error).message === "CHARACTER_RELATION_FACT_PREPARATION_CONFLICT") setStorageConflict(true);
      const fields: ApiFieldErrors = {};
      if (failure instanceof ApiRequestError) for (const [path, messages] of Object.entries(failure.fieldErrors)) fields[path.replace(/^(?:create\.)?target\.candidate\./, "")] = messages;
      setFieldErrors(fields);
    } }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  return <RetainedModalBackdrop isOpen isDismissable={!blocked} onOpenChange={(open) => { if (!open) void close(); }}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
    <Modal.Header className="border-b border-border px-5 py-4 sm:px-6"><Modal.Heading>{relationT("prepareTitle")}</Modal.Heading><Modal.CloseTrigger aria-label={t("closeKeep")} isDisabled={blocked} /></Modal.Header>
    <Modal.Body className="space-y-5 px-5 py-5 sm:px-6">
      {error && <div ref={errorRef}><RelationEditorErrorSummary message={error === "CHARACTER_RELATION_FACT_PREPARATION_CONFLICT" ? relationT("preparationConflict") : error} fieldErrors={fieldErrors} /></div>}
      <p className="text-sm font-medium">{relationT(`operations.${operation}`)}</p>
      {preparation.kind === "create" && <div className="space-y-5">
        <div className="detail-fields grid gap-4">{(["source_character_id", "target_character_id"] as const).map((field) => {
          const errorId = `${preparation.key}-${field}-error`;
          return <div key={field} className="grid gap-2"><label className="grid gap-2 text-xs font-medium text-muted">
            {relationT(field === "source_character_id" ? "sourceCharacter" : "targetCharacter")}
            <select className={INPUT} value={preparation.candidate[field]} disabled={blocked} required aria-invalid={Boolean(fieldErrors[field]) || undefined} aria-describedby={fieldErrors[field] ? errorId : undefined} onChange={(event) => update({ ...preparation, candidate: { ...preparation.candidate, [field]: event.target.value } })}>
              <option value="">{relationT("chooseCharacter")}</option>
              {characters.filter((row) => !row.is_deleted && row.status === "active").map((row) => <option key={row.character_id} value={row.character_id} disabled={row.character_id === preparation.candidate[field === "source_character_id" ? "target_character_id" : "source_character_id"]}>{row.name}</option>)}
            </select>
          </label>{fieldErrors[field] && <p id={errorId} className="text-xs text-red-600 dark:text-red-300">{fieldErrors[field][0]}</p>}</div>;
        })}</div>
        <CharacterRelationDesignFields value={preparation.candidate} onChange={(value) => update({ ...preparation, candidate: { ...preparation.candidate, ...value } })} disabled={blocked} fieldErrors={fieldErrors} />
      </div>}
      <CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={position} disabled={blocked || Boolean(setup?.record) || preparation.kind === "existing" && Boolean(preparation.origin)} afterOnly={kind === "change"} onChange={(value) => update(preparation.kind === "create" ? { ...preparation, position: value } : { ...preparation, setup: { ...preparation.setup, position: value, evidence: null, resolves: {} } })} />
      {preparation.kind === "existing" && preparation.origin && <label className="grid gap-2 text-xs font-medium text-muted">{relationT("suppliedValue")}<textarea className={`${INPUT} min-h-28 resize-y leading-6`} rows={4} disabled={blocked} value={preparation.setup.after?.current_state ?? ""} onChange={(event) => update({ ...preparation, setup: { ...preparation.setup, after: { current_state: event.target.value } } })} /></label>}
      {preparation.kind === "existing" && samePosition.length > 0 && <section className="space-y-3 border-y border-border py-3">
        <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{relationT("samePosition")}</p>
        {samePosition.map((record) => <div key={record.history_id} className="grid min-w-0 gap-2"><p className="reading-copy whitespace-pre-wrap">{record.after.current_state}</p><div><Button variant="outline" isDisabled={blocked || preparation.setup.record?.history_id === record.history_id} onPress={() => update({ ...preparation, setup: { ...preparation.setup, operation: "replace", record } })}>{relationT("replaceRecord")}</Button></div></div>)}
      </section>}
      {operation !== "void" && (kind === "start" ? <label className="grid gap-2 text-xs font-medium text-muted"><TooltipHint label={t("authorNote")} text={t("authorNoteHelp")} /><textarea aria-label={t("authorNote")} className={`${INPUT} resize-y leading-6`} rows={3} disabled={blocked} value={note} onChange={(event) => update(preparation.kind === "create" ? { ...preparation, note: event.target.value } : { ...preparation, setup: { ...preparation.setup, note: event.target.value } })} /></label> : preparation.kind === "existing" && <EvidencePicker key={characterFactPositionKey(position)} novelId={novelId} chapters={chapters.filter((chapter) => chapter.chapter_id === position?.target_id)} value={preparation.setup.evidence} label={t("source")} disabled={blocked || !position} onChange={(value) => { if (value === null) update({ ...preparation, setup: { ...preparation.setup, evidence: null } }); }} onSelectEvidence={(evidence) => update({ ...preparation, setup: { ...preparation.setup, evidence } })} />)}
      {reading && <p role="status">{t("loading")}</p>}
      {readError && <p role="alert" className="text-sm text-red-600 dark:text-red-300">{readError}</p>}
      {preparation.kind === "existing" && blockers.map((historyId) => <label key={historyId} className="flex min-h-11 items-start gap-2 text-sm"><input type="checkbox" disabled={blocked} checked={preparation.setup.resolves.current_state?.includes(historyId) ?? false} onChange={(event) => { const ids = event.target.checked ? [...(preparation.setup.resolves.current_state ?? []), historyId] : (preparation.setup.resolves.current_state ?? []).filter((id) => id !== historyId); update({ ...preparation, setup: { ...preparation.setup, resolves: ids.length ? { current_state: ids } : {} } }); }} /><span>{t("resolveBlocking", { field: relationT("currentState"), id: historyId })}</span></label>)}
    </Modal.Body><Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-6">{storageConflict && <Button variant="outline" isDisabled={busy} onPress={() => void exportCopy()}>{relationT("exportPreparation")}</Button>}{exportRequested && <Button variant="outline" isDisabled={busy} onPress={onClose}>{relationT("closeAfterSavingCopy")}</Button>}{!preparation.origin && <Button variant="ghost" isDisabled={blocked} onPress={() => void discard()}>{t("discardClose")}</Button>}<Button variant="ghost" isDisabled={blocked} onPress={() => void close()}>{t("closeKeep")}</Button><Button variant="primary" isDisabled={blocked || reading || Boolean(readError)} onPress={() => void preview()}>{t(busy ? "loading" : "preview")}</Button></Modal.Footer>
  </Modal.Dialog></Modal.Container></RetainedModalBackdrop>;
}
