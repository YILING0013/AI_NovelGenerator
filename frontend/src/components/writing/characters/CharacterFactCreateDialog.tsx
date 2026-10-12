"use client";

import { useContext, useEffect, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterFactCreatePreviewInputV1, CharacterFactPreviewV1 } from "@/types/characterFacts";
import type { HierarchyRecord } from "@/types/hierarchy";
import { ModalLayer } from "./views/CharacterWorkspaceViews";
import CharacterProfileForm from "./forms/CharacterProfileForm";
import CharacterFactPositionPicker from "./CharacterFactPositionPicker";
import { loadCharacterFactChapters } from "./characterFactPositions";
import { CHARACTER_PROFILE_FACT_FIELDS } from "./characterFactFields";
import { splitCharacterFactCreate } from "./characterFactCreate";
import { useCharacterFactPreparationPersistence, type CharacterFactPreparationV1 } from "./characterFactPreparation";
import type { CharacterFactDraftV1 } from "./characterFactDrafts";

type CreatePreparation = Extract<CharacterFactPreparationV1, { kind: "create" }>;
const INPUT = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:opacity-60";

/** 功能：人物手工、核心候选和卷候选共用明确起点的创建预览。Args: 已保留的独立准备稿及宿主回调。Returns: 原人物新建 Modal，不确认旧批量命令。 */
export default function CharacterFactCreateDialog({ novelId, initialPreparation, onClose, onPreviewed, onBusy, beforeLeaveRef }: {
  novelId: string; initialPreparation: CreatePreparation; onClose: () => void; onPreviewed: (draft: CharacterFactDraftV1) => void;
  onBusy?: (busy: boolean) => void; beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}) {
  const t = useTranslations("writing.characters"), ft = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const errorRef = useRef<HTMLDivElement>(null);
  const [preparation, setPreparation] = useState(initialPreparation);
  const current = useRef(initialPreparation), alive = useRef(true), pending = useRef(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]), [directoryError, setDirectoryError] = useState("");
  const store = useCharacterFactPreparationPersistence(novelId);
  useEffect(() => { store.persisted.current.set(initialPreparation.key, initialPreparation.revision); }, [initialPreparation, store]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(busy); return () => onBusy?.(false); }, [busy, onBusy]);
  useEffect(() => {
    const abort = new AbortController();
    void loadCharacterFactChapters(novelId, abort.signal).then((rows) => { if (!abort.signal.aborted) setChapters(rows); }).catch((failure) => { if (!abort.signal.aborted) setDirectoryError(failure.message); });
    return () => abort.abort();
  }, [novelId]);
  const keep = async () => { await store.persist(current.current); await store.queue.current; };
  useEffect(() => {
    if (!beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { if (pending.current) throw new Error(ft("saving")); await keep(); };
    return () => { beforeLeaveRef.current = null; };
  });
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  useEffect(() => {
    if (!active || !error) return;
    const frame = requestAnimationFrame(() => {
      const summary = errorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
      if (!summary || summary.closest("[inert]")) return;
      const target = summary.closest('[role="dialog"]')?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? summary;
      if (target.closest("[inert]")) return;
      target.focus({ preventScroll: true }); target.scrollIntoView?.({ block: "nearest" });
    });
    return () => cancelAnimationFrame(frame);
  }, [active, error, fieldErrors]);
  const update = (patch: Partial<Pick<CreatePreparation, "profile" | "fields" | "is_core_character" | "position" | "note">>) => {
    const next = { ...current.current, ...patch, revision: current.current.revision + 1 };
    current.current = next; setPreparation(next);
    void store.persist(next).catch((failure) => { if (alive.current) setError(failure.message); });
  };
  const close = async () => { try { await keep(); onClose(); } catch (failure) { if (alive.current) setError((failure as Error).message); } };
  const preview = async () => {
    if (pending.current) return;
    const original = current.current;
    const missing = ["name", ...original.fields].filter((field) => {
      const value = original.profile[field as keyof CreatePreparation["profile"]];
      return typeof value === "string" && !value.trim();
    });
    if (missing.length) { setFieldErrors(Object.fromEntries(missing.map((field) => [field, [t("errors.requiredField")]]))); setError(t("errors.profileRequired")); return; }
    if (!original.fields.length || !original.position || !original.note.trim()) { setFieldErrors({}); setError(ft("previewRequired")); return; }
    pending.current = true; setBusy(true); setError(""); setFieldErrors({});
    try {
      await keep();
      const { candidate, after } = splitCharacterFactCreate(original.profile, original.is_core_character, original.fields);
      const input: CharacterFactCreatePreviewInputV1 = { operation: "create", target: { candidate }, position: original.position, source: { kind: "author", note: original.note }, fields: [...original.fields], references: [] };
      const response = await apiPost<CharacterFactPreviewV1>(`/api/character-facts/novel/${novelId}/preview`, input);
      const positionLabel = original.position.intent === "book_start" ? ft("positions.book_start") : original.position.intent === "volume_start" ? ft("positions.volume_start") : `${chapters.find((row) => row.chapter_id === original.position!.target_id)?.title ?? original.position.target_id} · ${ft(`positions.${original.position.intent}`)}`;
      const draft: CharacterFactDraftV1 = { schema_id: "character.fact.draft", schema_version: 1, key: crypto.randomUUID(), revision: 1, positionLabel, preview: response, after, reason: "", authorConfirmed: false };
      await store.promote(original, draft);
      if (alive.current) onPreviewed(draft);
    } catch (failure) { if (alive.current) { setError((failure as Error).message); setFieldErrors(failure instanceof ApiRequestError ? failure.fieldErrors : {}); } }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  return <ModalLayer title={t("manualCharacter.title")} busy={busy} onClose={() => void close()} footer={<><Button variant="ghost" size="sm" isDisabled={busy} onPress={() => void close()}>{ft("closeKeep")}</Button><Button variant="primary" size="sm" isDisabled={busy} onPress={() => void preview()}>{busy ? ft("saving") : ft("preview")}</Button></>}>
    {error && <div ref={errorRef}><RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} className="mb-5" /></div>}
    <fieldset className="mb-6 border-b border-border pb-5" disabled={busy}><legend className="text-sm font-semibold">{t("manualCharacter.coreIdentity")}</legend><div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-surface-secondary/55 p-1" aria-label={t("manualCharacter.coreIdentity")}>{[false, true].map((isCore) => <button key={String(isCore)} type="button" aria-pressed={preparation.is_core_character === isCore} onClick={() => update({ is_core_character: isCore })} className={`min-h-10 rounded-lg px-3 text-sm font-medium ${preparation.is_core_character === isCore ? "bg-background text-foreground shadow-sm" : "text-muted"}`}>{t(isCore ? "status.core" : "status.nonCore")}</button>)}</div></fieldset>
    <div className="mb-6 grid gap-4 border-b border-border pb-5"><CharacterFactPositionPicker novelId={novelId} chapters={chapters} value={preparation.position} onChange={(position) => update({ position })} disabled={busy} /><label className="grid gap-2 text-xs font-medium text-muted">{ft("authorNote")}<textarea className={INPUT} value={preparation.note} onChange={(event) => update({ note: event.target.value })} disabled={busy} maxLength={2000} /></label>{directoryError && <p role="alert" className="text-sm text-danger">{directoryError}</p>}</div>
    <fieldset className="mb-6 border-b border-border pb-5" disabled={busy}><legend className="text-sm font-semibold">{ft("selectedFields")}</legend><div className="mt-3 grid gap-2 sm:grid-cols-2">{CHARACTER_PROFILE_FACT_FIELDS.map((field) => <label key={field} className="flex min-h-10 items-center gap-2 text-sm"><input type="checkbox" checked={preparation.fields.includes(field)} onChange={(event) => update({ fields: event.target.checked ? [...preparation.fields, field] : preparation.fields.filter((selected) => selected !== field) })} />{ft(`fields.${field}`)}</label>)}</div></fieldset>
    <CharacterProfileForm value={preparation.profile} visibleFactFields={preparation.fields} onChange={(profile) => update({ profile })} disabled={busy} t={t} fieldErrors={fieldErrors} />
  </ModalLayer>;
}
