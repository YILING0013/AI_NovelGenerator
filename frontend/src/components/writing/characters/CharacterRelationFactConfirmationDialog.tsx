"use client";

import { downloadExport } from "@/lib/userExport";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterRelationFactResultV1 } from "@/types/characterRelationFacts";
import CharacterRelationFactEditor from "./CharacterRelationFactEditor";
import { characterFactFieldErrors } from "./CharacterFactConfirmationDialog";
import { characterRelationFactDraftScope, type CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import { confirmCharacterRelationFact, useCharacterRelationFactPersistence } from "./characterRelationFactConfirmation";

/** 功能：按原请求保存关系事实并分别恢复读回和清稿。Args: 已持久化的确认稿、当前读取回调及离开保护。Returns: 不随后台结果导航的确认弹窗。 */
export default function CharacterRelationFactConfirmationDialog({ novelId, initialDraft, onClose, onReadback, onRepreview, onBusy, beforeLeaveRef }: {
  novelId: string; initialDraft: CharacterRelationFactDraftV1; onClose: () => void; onReadback: (receipt: CharacterRelationFactResultV1) => Promise<void>;
  onRepreview?: (draft: CharacterRelationFactDraftV1) => Promise<void>; onBusy?: (value: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characterFacts");
  const relationT = useTranslations("writing.characterRelationFacts");
  const active = useContext(RetainedViewActive);
  const [draft, setDraft] = useState(initialDraft);
  const current = useRef(initialDraft);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const alive = useRef(true);
  const editor = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const [exportRequested, setExportRequested] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const { queue, persisted, persist, remove, localError } = useCharacterRelationFactPersistence(characterRelationFactDraftScope(novelId), t("localFailed"));
  useEffect(() => { persisted.current.set(initialDraft.key, initialDraft.revision); }, [initialDraft, persisted]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => { const guard = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener("beforeunload", guard); return () => window.removeEventListener("beforeunload", guard); }, []);
  const keep = async () => { if (pending.current) throw new Error(t("saving")); await persist(current.current); await queue.current; };
  useEffect(() => { if (!beforeLeaveRef) return; beforeLeaveRef.current = keep; return () => { beforeLeaveRef.current = null; }; });
  const update = (next: CharacterRelationFactDraftV1) => { current.current = next; if (alive.current) setDraft(next); };
  const close = async () => { try { await keep(); onClose(); } catch (failure) { if (alive.current) setError((failure as Error).message); } };
  const confirm = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setFieldErrors({});
    const result = await confirmCharacterRelationFact({ draft: current.current, key: () => crypto.randomUUID(), persist, remove,
      send: (command) => apiPost<CharacterRelationFactResultV1>(`/api/character-relation-facts/novel/${novelId}/confirm`, command.body, { headers: { "Idempotency-Key": command.key } }), readback: onReadback, update });
    pending.current = false;
    if (!alive.current) return;
    setBusy(false);
    if (result.ok) { onClose(); return; }
    setError(result.stage === "readback" ? t("savedReadFailed") : result.stage === "cleanup" ? t("savedCleanupFailed") : result.error instanceof Error ? result.error.message : t("saveFailed"));
    setFieldErrors(result.error instanceof ApiRequestError ? characterFactFieldErrors(result.error.fieldErrors) : {});
  };
  const repreview = async () => {
    if (pending.current || !onRepreview || current.current.command?.unknown || current.current.command?.saved) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const saved = await persist(current.current);
      if (saved) { update({ ...current.current, revision: current.current.revision + 1, command: { ...current.current.command!, saved, unknown: false, readbackDone: false } }); return; }
      await onRepreview(structuredClone(current.current)); onClose();
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  useEffect(() => {
    if (!active || !(error || localError)) return;
    const frame = requestAnimationFrame(() => { const target = editor.current?.querySelector<HTMLElement>("[aria-invalid=true]") ?? editor.current?.querySelector<HTMLElement>("[data-editor-error-summary]"); if (target && !target.closest("[inert]")) { target.focus({ preventScroll: true }); target.scrollIntoView?.({ block: "nearest" }); } });
    return () => cancelAnimationFrame(frame);
  }, [active, error, localError]);
  return <RetainedModalBackdrop isOpen isDismissable={!busy} onOpenChange={(open) => { if (!open) void close(); }}><Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-4xl">
    <Modal.Header className="border-b border-border px-5 py-4 sm:px-6"><Modal.Heading>{relationT("confirmTitle")}</Modal.Heading><Modal.CloseTrigger aria-label={t("closeKeep")} isDisabled={busy} /></Modal.Header>
    <Modal.Body className="px-5 py-5 sm:px-6"><div ref={editor}><CharacterRelationFactEditor draft={draft} disabled={busy} error={error === "CHARACTER_RELATION_FACT_LOCAL_CONFLICT" ? relationT("preparationConflict") : error || localError} fieldErrors={fieldErrors} onChange={(next) => { update(next); setFieldErrors({}); void persist(next).catch(() => {}); }} /></div></Modal.Body>
    <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-6">
      {onRepreview && draft.command && !draft.command.unknown && !draft.command.saved && <Button variant="outline" isDisabled={busy} onPress={() => void repreview()}>{t("repreviewExplicit")}</Button>}
      <Button variant="ghost" isDisabled={busy} onPress={() => { const url = URL.createObjectURL(new Blob([JSON.stringify(current.current, null, 2)], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = `character-relation-fact-${current.current.key}.json`; void downloadExport(link); URL.revokeObjectURL(url); setExportRequested(true); }}>{t("exportDraft")}</Button>
      {exportRequested && <Button variant="outline" isDisabled={busy} onPress={onClose}>{relationT("closeAfterSavingCopy")}</Button>}
      <Button variant="ghost" isDisabled={busy} onPress={() => void close()}>{t("closeKeep")}</Button>
      <Button variant="primary" isDisabled={busy || (!draft.command && (!draft.authorConfirmed || Boolean(localError)))} onPress={() => void confirm()}>{t(busy ? "saving" : draft.command?.saved ? "retryRead" : draft.command ? "retryOriginal" : "confirm")}</Button>
    </Modal.Footer>
  </Modal.Dialog></Modal.Container></RetainedModalBackdrop>;
}
