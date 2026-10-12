"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import TagInput from "@/components/shared/TagInput";
import TagList from "@/components/shared/TagList";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { ApiFieldErrors } from "@/lib/api";
import type { CharacterFactField, CharacterFactSourceV1, CharacterFactValuesV1 } from "@/types/characterFacts";
import CharacterFactLegacySources from "./CharacterFactLegacySources";
import type { CharacterFactDraftV1 } from "./characterFactDrafts";

const INPUT_CLASS_NAME = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const ARRAY_FIELDS = new Set<CharacterFactField>(["strengths", "weaknesses", "abilities"]);
const SHORT_FIELDS = new Set<CharacterFactField>(["gender", "age_group", "race"]);
const CLEARABLE_FIELDS = new Set<CharacterFactField>(["strengths", "weaknesses", "abilities", "psychological_state", "public_state", "hidden_state", "actual_goal"]);

interface CharacterFactEditorProps {
  draft: CharacterFactDraftV1;
  disabled?: boolean;
  error?: string;
  fieldErrors?: ApiFieldErrors;
  onChange: (draft: CharacterFactDraftV1) => void;
}

/**
 * 功能：共用人物事实的人工预览及编辑，逐字段区分前值、未知和处置对象。
 * Args: draft 独立事实稿及原预览位置标题；onChange 只更新本地稿。
 * Returns: 无网络请求和保存入口的编辑内容，供人物详情与卷工作台共用。
 */
export default function CharacterFactEditor({ draft, disabled = false, error, fieldErrors = {}, onChange }: CharacterFactEditorProps) {
  const t = useTranslations("writing.characterFacts");
  const id = useId();
  // 一旦登记请求，显示也以冻结原件为准，不受外层仍可导出的稿对象变更影响。
  const command = draft.command;
  const positionLabel = command?.positionLabel ?? draft.positionLabel;
  const basis = command?.body.basis ?? draft.preview.basis;
  const after = command && command.body.operation !== "void" ? command.body.after : draft.after;
  const reason = command?.body.operation === "void" ? command.body.reason : draft.reason;
  const locked = disabled || Boolean(command);
  const targetName = basis.target.kind === "existing" ? basis.target.name : basis.target.candidate.name;
  const ready = basis.operation === "void"
    ? Boolean(reason.trim())
    : basis.fields.every((field) => after[field] !== undefined) && Object.keys(after).length === basis.fields.length;

  const updateValue = (field: CharacterFactField, value: string | string[]) => {
    if (locked) return;
    onChange({ ...draft, revision: draft.revision + 1, after: { ...draft.after, [field]: value }, authorConfirmed: false });
  };
  const displayValue = (value: CharacterFactValuesV1[CharacterFactField]) => {
    if (value === undefined) return t("notEntered");
    if (value.length === 0) return t("cleared");
    return Array.isArray(value) ? <TagList values={value} /> : value;
  };
  const sourceValue = (source: CharacterFactSourceV1) => source.kind === "author"
    ? source.note
    : <div className="space-y-2"><p className="text-xs text-muted">{t("chapterRevision", { chapter: source.evidence.chapter_id, version: source.evidence.version })}</p><blockquote className="whitespace-pre-wrap border-l-2 border-accent/40 pl-3">{source.evidence.quote}</blockquote></div>;

  return <div className="space-y-8">
    {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} />}
    {command && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{t(command.saved ? (command.readbackDone ? "savedCleanup" : "savedReadback") : command.unknown ? "unknownResult" : "frozenRequest")}</p>}
    <DocumentSection number="01" title={t("basisTitle")}>
      <dl className="detail-fields grid gap-5">
        <ReadOnlyField label={t("character")} value={targetName} />
        <ReadOnlyField label={t("operation")} value={t(`operations.${basis.operation}`)} />
        <ReadOnlyField label={t("position")} value={positionLabel} />
        <ReadOnlyField label={t("source")} value={sourceValue(basis.source)} wide />
      </dl>
    </DocumentSection>
    <CharacterFactLegacySources basis={basis} />
    <DocumentSection number="02" title={t(basis.operation === "void" ? "voidTitle" : "valuesTitle")}>
      <div className="space-y-6">
        {basis.fields.map((field) => {
          const fieldLabel = t(`fields.${field}`);
          const fieldId = `${id}-${field}`;
          const fieldError = fieldErrors[`after.${field}`]?.[0] ?? fieldErrors[field]?.[0];
          const unknown = basis.before.unknown[field];
          const selectedIds = [...new Set([basis.previous[field], ...(basis.blockers[field] ?? []), basis.replaces[field], ...(basis.resolves[field] ?? []), basis.void_targets[field]].filter((value): value is string => Boolean(value)))];
          return <section key={field} aria-labelledby={`${fieldId}-title`} className="space-y-3 border-b border-border pb-6 last:border-b-0 last:pb-0">
            <h4 id={`${fieldId}-title`} className="text-sm font-semibold text-foreground">{fieldLabel}</h4>
            <dl className="detail-fields grid gap-3">
              <ReadOnlyField label={t("before")} value={unknown ? <span className="text-amber-700 dark:text-amber-300">{t(`unknown.${unknown}`)}</span> : displayValue(basis.before.values[field])} wide />
              {basis.previous[field] && <ReadOnlyField label={t("previous")} value={basis.previous[field]} />}
              {!!basis.blockers[field]?.length && <ReadOnlyField label={t("blockers")} value={<TagList values={basis.blockers[field]!} />} wide />}
              {basis.replaces[field] && <ReadOnlyField label={t("replaces")} value={basis.replaces[field]} />}
              {!!basis.resolves[field]?.length && <ReadOnlyField label={t("resolves")} value={<TagList values={basis.resolves[field]!} />} wide />}
              {basis.void_targets[field] && <ReadOnlyField label={t("voidTarget")} value={basis.void_targets[field]} />}
            </dl>
            {selectedIds.map((historyId) => {
              const record = [...basis.field_sources, ...basis.targets].find((item) => item.history_id === historyId);
              return record && <details key={historyId} className="text-sm">
                <summary className="cursor-pointer text-muted">{t("recordDetails", { id: historyId })}</summary>
                <dl className="mt-3 grid gap-3">
                  <ReadOnlyField label={t("recordValue")} value={displayValue(record.after[field])} wide />
                  <ReadOnlyField label={t("position")} value={`${t(`positions.${record.position.intent}`)} · ${record.position.target_id}`} />
                  <ReadOnlyField label={t("source")} value={sourceValue(record.source)} wide />
                  {record.validity[field] && <ReadOnlyField label={t("validity")} value={t(`validityStates.${record.validity[field]!.state}`)} />}
                </dl>
              </details>;
            })}
            {basis.operation !== "void" && <div className="space-y-2">
              {ARRAY_FIELDS.has(field) ? <TagInput
                name={field}
                label={t("afterField", { field: fieldLabel })}
                values={Array.isArray(after[field]) ? after[field] as string[] : []}
                onChange={(value) => updateValue(field, value)}
                getRemoveAriaLabel={(value) => t("removeTag", { value })}
                maxItems={12}
                preserveItems
                limitReachedText={t("tagLimit")}
                disabled={locked}
                error={fieldError}
              /> : <div className="grid gap-2">
                <label htmlFor={fieldId} className="text-xs font-medium text-muted">{t("afterField", { field: fieldLabel })}</label>
                {SHORT_FIELDS.has(field) ? <input id={fieldId} name={field} value={typeof after[field] === "string" ? after[field] : ""} onChange={(event) => updateValue(field, event.target.value)} disabled={locked} maxLength={80} required aria-invalid={Boolean(fieldError) || undefined} aria-describedby={fieldError ? `${fieldId}-error` : undefined} className={INPUT_CLASS_NAME} />
                  : <textarea id={fieldId} name={field} value={typeof after[field] === "string" ? after[field] : ""} onChange={(event) => updateValue(field, event.target.value)} disabled={locked} maxLength={field === "identity" ? 500 : 1000} required={!CLEARABLE_FIELDS.has(field)} rows={4} aria-invalid={Boolean(fieldError) || undefined} aria-describedby={fieldError ? `${fieldId}-error` : undefined} className={`${INPUT_CLASS_NAME} resize-y leading-6`} />}
                {fieldError && <p id={`${fieldId}-error`} className="text-xs text-red-600 dark:text-red-300">{fieldError}</p>}
              </div>}
              {after[field] === undefined && <p className="text-xs text-muted">{t("notEntered")}</p>}
              {CLEARABLE_FIELDS.has(field) && after[field] === undefined && <button type="button" disabled={locked} className="text-sm text-accent disabled:opacity-60" onClick={() => updateValue(field, ARRAY_FIELDS.has(field) ? [] : "")}>{t("setEmpty")}</button>}
            </div>}
          </section>;
        })}
        {basis.operation === "void" && <div className="grid gap-2">
          <label htmlFor={`${id}-reason`} className="text-xs font-medium text-muted">{t("reason")}</label>
          <textarea id={`${id}-reason`} value={reason} onChange={(event) => { if (!locked) onChange({ ...draft, revision: draft.revision + 1, reason: event.target.value, authorConfirmed: false }); }} disabled={locked} maxLength={2000} required rows={4} aria-invalid={Boolean(fieldErrors.reason) || undefined} aria-describedby={fieldErrors.reason ? `${id}-reason-error` : undefined} className={`${INPUT_CLASS_NAME} resize-y leading-6`} />
          {fieldErrors.reason && <p id={`${id}-reason-error`} className="text-xs text-red-600 dark:text-red-300">{fieldErrors.reason[0]}</p>}
        </div>}
      </div>
    </DocumentSection>
    <details className="text-sm">
      <summary className="cursor-pointer text-muted">{t("referencesTitle")}</summary>
      <div className="mt-3 space-y-3">
        <p className="break-all">{t("characterIdentity")} · {basis.target.kind === "existing" ? basis.target.character_id : basis.target.entity_id}</p>
        <p className="break-all">{t(`positions.${basis.position.intent}`)} · {basis.position.target_id}</p>
        <p>{basis.references.length ? t("referencesCount", { count: basis.references.length }) : t("noReferences")}</p>
        {!!basis.reference_reads.length && <ul className="space-y-1">{basis.reference_reads.map((read) => <li key={`${read.reference.entity_type}:${read.reference.entity_id}`} className="break-all">{t(`referenceKinds.${read.reference.entity_type}`)} · {read.reference.entity_id} · {t("referenceVersion", { version: read.version })}</li>)}</ul>}
        {basis.reads.map((read, index) => <p key={`${read.fingerprint}:${index}`}>{read.identities.length ? t("readCharacters", { count: read.identities.length }) : t("emptyRead")}</p>)}
      </div>
    </details>
    <label className="flex items-start gap-3 text-sm leading-6 text-foreground">
      <input type="checkbox" checked={Boolean(command) || draft.authorConfirmed} disabled={locked || !ready} onChange={(event) => { if (!locked) onChange({ ...draft, revision: draft.revision + 1, authorConfirmed: event.target.checked }); }} className="mt-1 h-4 w-4 accent-accent" />
      <span>{t("authorConfirmed")}</span>
    </label>
  </div>;
}
