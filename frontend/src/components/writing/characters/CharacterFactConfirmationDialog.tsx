"use client";

import { downloadExport } from "@/lib/userExport";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterFactResultV1 } from "@/types/characterFacts";
import CharacterFactEditor from "./CharacterFactEditor";
import { characterFactDraftScope, type CharacterFactDraftV1 } from "./characterFactDrafts";
/** 功能：严格联合模型的 operation 前缀和数组项错误归到实际 after 控件。Args: 服务端原错误。Returns: 合并后的字段消息。 */
export function characterFactFieldErrors(errors: ApiFieldErrors): ApiFieldErrors {
  const normalized: ApiFieldErrors = {};
  for (const [path, messages] of Object.entries(errors)) {
    const match = path.match(/^(?:(?:create|establish|correct_initial|change|replace|void)\.)?after\.([a-z_]+)(?:\.\d+)?$/);
    const key = match ? `after.${match[1]}` : path;
    normalized[key] = [...(normalized[key] ?? []), ...messages];
  }
  return normalized;
}

import { confirmCharacterFact, useCharacterFactPersistence } from "./characterFactConfirmation";

/** 功能：共用原稿登记、冻结确认、成功读回和安全清稿。Args: 已落本地的原稿及宿主当前读取。Returns: 保留失败稿的原位确认 Modal。 */
export default function CharacterFactConfirmationDialog({ novelId, initialDraft, onClose, onReadback, onBusy, beforeLeaveRef, onRepreview }: {
  novelId: string; initialDraft: CharacterFactDraftV1; onClose: () => void; onReadback: (receipt: CharacterFactResultV1) => Promise<void>;
  onRepreview?: (draft: CharacterFactDraftV1) => Promise<void>;
  onBusy?: (value: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const editorRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState(initialDraft);
  const draftRef = useRef(initialDraft);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const alive = useRef(true);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const { queue, persisted, persist, remove, localError } = useCharacterFactPersistence(characterFactDraftScope(novelId), t("localFailed"));
  useEffect(() => { persisted.current.set(initialDraft.key, initialDraft.revision); }, [initialDraft, persisted]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  const keep = async () => {
    if (pending.current) throw new Error(t("saving"));
    await persist(draftRef.current);
    await queue.current;
  };
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = keep;
    return () => { beforeLeaveRef.current = null; };
  });
  const update = (next: CharacterFactDraftV1) => { draftRef.current = next; if (alive.current) setDraft(next); };
  const close = async () => {
    try { await keep(); onClose(); }
    catch (failure) { if (alive.current) setError((failure as Error).message); }
  };
  const confirm = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setFieldErrors({});
    const result = await confirmCharacterFact({
      draft: draftRef.current, key: () => crypto.randomUUID(), persist, remove,
      send: (command) => apiPost<CharacterFactResultV1>(`/api/character-facts/novel/${novelId}/confirm`, command.body, { headers: { "Idempotency-Key": command.key } }),
      readback: onReadback, update,
    });
    pending.current = false;
    if (!alive.current) return;
    setBusy(false);
    if (result.ok) { onClose(); return; }
    setError(result.stage === "readback" ? t("savedReadFailed") : result.stage === "cleanup" ? t("savedCleanupFailed") : result.error instanceof Error ? result.error.message : t("saveFailed"));
    setFieldErrors(result.error instanceof ApiRequestError ? characterFactFieldErrors(result.error.fieldErrors) : {});
  };
  useEffect(() => {
    if (!active || !(error || localError)) return;
    const frame = requestAnimationFrame(() => {
      const summary = editorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      if (!summary || summary.closest("[inert]")) return;
      summary.focus({ preventScroll: true }); summary.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, error, localError]);
  const repreview = async () => {
    if (pending.current || !onRepreview || draftRef.current.command?.unknown || draftRef.current.command?.saved || (!draftRef.current.command && Array.isArray(draftRef.current.preview.basis.legacy_sources))) return;
    pending.current = true; setBusy(true); setError("");
    try {
      // 跨标签页首次成功先于另建意图；保留原请求并让作者读回当前值。
      const saved = await persist(draftRef.current);
      if (saved) { update({ ...draftRef.current, revision: draftRef.current.revision + 1, command: { ...draftRef.current.command!, saved, unknown: false, readbackDone: false } }); return; }
      await onRepreview(structuredClone(draftRef.current));
      onClose();
    } catch (failure) { if (alive.current) setError((failure as Error).message); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const exportDraft = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(draftRef.current, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `character-fact-${draftRef.current.key}.json`; void downloadExport(link); URL.revokeObjectURL(url);
  };
  return <RetainedModalBackdrop isOpen isDismissable={!busy} onOpenChange={(open) => { if (!open) void close(); }}>
    <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-5xl">
      <Modal.Header className="border-b border-border px-5 py-4 sm:px-6"><Modal.Heading>{t("confirmTitle")}</Modal.Heading><Modal.CloseTrigger aria-label={t("closeKeep")} isDisabled={busy} /></Modal.Header>
      <Modal.Body className="px-5 py-5 sm:px-6"><div ref={editorRef}><CharacterFactEditor draft={draft} disabled={busy} error={error || localError} fieldErrors={fieldErrors} onChange={(next) => { update(next); setFieldErrors({}); void persist(next).catch(() => {}); }} /></div></Modal.Body>
      <Modal.Footer className="flex flex-wrap justify-end gap-2 border-t border-border px-5 py-4 sm:px-6">
        {onRepreview && (draft.command ? !draft.command.unknown && !draft.command.saved : !Array.isArray(draft.preview.basis.legacy_sources)) && <Button variant="outline" isDisabled={busy} onPress={() => void repreview()}>{t("repreviewExplicit")}</Button>}
        <Button variant="ghost" onPress={exportDraft}>{t("exportDraft")}</Button>
        <Button variant="ghost" isDisabled={busy} onPress={() => void close()}>{t("closeKeep")}</Button>
        <Button variant="primary" isDisabled={busy || (!draft.command && (!draft.authorConfirmed || Boolean(localError) || !Array.isArray(draft.preview.basis.legacy_sources)))} onPress={() => void confirm()}>{t(busy ? "saving" : draft.command?.saved ? "retryRead" : draft.command ? "retryOriginal" : "confirm")}</Button>
      </Modal.Footer>
    </Modal.Dialog></Modal.Container>
  </RetainedModalBackdrop>;
}
