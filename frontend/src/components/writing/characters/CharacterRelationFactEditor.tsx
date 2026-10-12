"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { ApiFieldErrors } from "@/lib/api";
import type { CharacterFactSourceV1 } from "@/types/characterFacts";
import { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import type { CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";

/** 功能：展示关系原依据并让作者填写唯一事实字段。Args: 原预览稿、错误与更新回调。Returns: 不请求网络、不保存设计字段的确认内容。 */
export default function CharacterRelationFactEditor({ draft, disabled = false, error, fieldErrors = {}, onChange }: {
  draft: CharacterRelationFactDraftV1; disabled?: boolean; error?: string; fieldErrors?: ApiFieldErrors; onChange: (draft: CharacterRelationFactDraftV1) => void;
}) {
  const t = useTranslations("writing.characterFacts");
  const relationT = useTranslations("writing.characterRelationFacts");
  const id = useId();
  const command = draft.command;
  const basis = command?.body.basis ?? draft.preview.basis;
  const after = command && command.body.operation !== "void" ? command.body.after : draft.after;
  const reason = command?.body.operation === "void" ? command.body.reason : draft.reason;
  const locked = disabled || Boolean(command);
  const isVoid = basis.operation === "void";
  const entered = isVoid ? reason : after.current_state ?? "";
  const tooLong = Array.from(entered).length > 2000;
  const ready = Boolean(entered.trim()) && !tooLong;
  const unknown = basis.before.unknown.current_state;
  const selected = [...new Set([basis.previous.current_state, ...(basis.blockers.current_state ?? []), basis.replaces.current_state, ...(basis.resolves.current_state ?? []), basis.void_targets.current_state].filter((value): value is string => Boolean(value)))];
  const sourceValue = (source: CharacterFactSourceV1) => source.kind === "author" ? source.note : <div className="space-y-2"><p className="text-xs text-muted">{t("chapterRevision", { chapter: source.evidence.chapter_id, version: source.evidence.version })}</p><blockquote className="whitespace-pre-wrap border-l-2 border-accent/40 pl-3">{source.evidence.quote}</blockquote></div>;
  const valueError = fieldErrors["after.current_state"]?.[0] ?? fieldErrors.current_state?.[0];
  return <div className="space-y-6">
    {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} />}
    {command && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{t(command.saved ? command.readbackDone ? "savedCleanup" : "savedReadback" : command.unknown ? "unknownResult" : "frozenRequest")}</p>}
    <DocumentSection number="01" title={t("basisTitle")}><dl className="detail-fields grid gap-4">
      <ReadOnlyField label={relationT("sourceCharacter")} value={basis.target.source_character.name} />
      <ReadOnlyField label={relationT("targetCharacter")} value={basis.target.target_character.name} />
      <ReadOnlyField label={t("operation")} value={relationT(`operations.${basis.operation}`)} />
      <ReadOnlyField label={t("position")} value={command?.positionLabel ?? draft.positionLabel} />
      <ReadOnlyField label={t("source")} value={sourceValue(basis.source)} wide />
    </dl></DocumentSection>
    <DocumentSection number="02" title={relationT("currentState")}><div className="space-y-4">
      <dl className="grid gap-4">
        <ReadOnlyField label={t("before")} value={unknown ? <span className="text-amber-700 dark:text-amber-300">{relationT(`unknown.${unknown}`)}</span> : basis.before.values.current_state} wide />
        {basis.legacy_values.current_state !== undefined && <ReadOnlyField label={relationT("legacyValue")} value={basis.legacy_values.current_state} wide />}
      </dl>
      {selected.map((historyId) => {
        const record = [...basis.field_sources, ...basis.targets].find((row) => row.history_id === historyId);
        return record && <details key={historyId} className="text-sm"><summary className="cursor-pointer py-2 text-muted">{t("recordDetails", { id: historyId })}</summary><dl className="grid gap-3">
          <ReadOnlyField label={t("recordValue")} value={record.after.current_state} wide />
          <ReadOnlyField label={t("position")} value={`${t(`positions.${record.position.intent}`)} · ${record.position.target_id}`} />
          <ReadOnlyField label={t("source")} value={sourceValue(record.source)} wide />
          <ReadOnlyField label={t("validity")} value={t(`validityStates.${record.validity.current_state!.state}`)} />
          {basis.replaces.current_state === historyId && <ReadOnlyField label={t("replaces")} value={historyId} />}
          {basis.void_targets.current_state === historyId && <ReadOnlyField label={t("voidTarget")} value={historyId} />}
          {basis.resolves.current_state?.includes(historyId) && <ReadOnlyField label={t("resolves")} value={historyId} />}
        </dl></details>;
      })}
      <div className="grid gap-2">
        <label htmlFor={`${id}-value`} className="text-xs font-medium text-muted">{isVoid ? t("reason") : relationT("after")}</label>
        <textarea id={`${id}-value`} name={isVoid ? "reason" : "current_state"} className={`${INPUT} min-h-28 resize-y leading-6`} rows={4} required disabled={locked} value={entered} aria-invalid={tooLong || Boolean(isVoid ? fieldErrors.reason : valueError) || undefined} aria-describedby={tooLong || (isVoid ? fieldErrors.reason : valueError) ? `${id}-error` : undefined} onChange={(event) => {
          if (locked) return;
          onChange({ ...draft, revision: draft.revision + 1, ...(isVoid ? { reason: event.target.value } : { after: { current_state: event.target.value } }), authorConfirmed: false });
        }} />
        {(tooLong || (isVoid ? fieldErrors.reason : valueError)) && <p id={`${id}-error`} className="text-xs text-red-600 dark:text-red-300">{tooLong ? relationT("tooLong") : isVoid ? fieldErrors.reason?.[0] : valueError}</p>}
      </div>
    </div></DocumentSection>
    <label className="flex min-h-11 items-start gap-3 text-sm leading-6"><input className="mt-1 h-4 w-4 accent-accent" type="checkbox" checked={Boolean(command) || draft.authorConfirmed} disabled={locked || !ready} onChange={(event) => { if (!locked) onChange({ ...draft, revision: draft.revision + 1, authorConfirmed: event.target.checked }); }} /><span>{relationT("authorConfirmed")}</span></label>
  </div>;
}
