"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import type { VolumePlanningV1 } from "@/types/volume";

export interface VolumeFieldsValue {
  title: string;
  subtitle: string;
  summary: string;
  goal: string;
  theme: string;
  planning: VolumePlanningV1 | null;
}

interface VolumeFieldsFormProps<TValue extends VolumeFieldsValue> {
  value: TValue;
  onChange: (value: TValue) => void;
  disabled: boolean;
  fieldErrors: ApiFieldErrors;
  errorIdPrefix: string;
  autoFocusTitle?: boolean;
  identityExtra?: ReactNode;
  allowPlanningToggle?: boolean;
  section?: "identity" | "planning";
  readOnlyFields?: readonly string[];
}

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;

function Field({
  label,
  children,
  className = "",
  error,
  errorId,
}: {
  label: string;
  children: ReactNode;
  className?: string;
  error?: string;
  errorId?: string;
}) {
  return (
    <div className={`grid gap-2 text-sm ${className}`}>
      <label className="contents">
        <span className="text-xs font-medium text-muted">{label}</span>
        {children}
      </label>
      {error && <span id={errorId} className="text-xs text-red-600 dark:text-red-300">{error}</span>}
    </div>
  );
}

/**
 * 渲染卷编辑和两种 AI 结果共同使用的卷字段表单。
 *
 * Args:
 *   props: 当前卷字段、更新回调、错误和普通编辑使用的额外字段。
 *
 * Returns:
 *   卷信息和本卷规划表单。
 */
export default function VolumeFieldsForm<TValue extends VolumeFieldsValue>({
  value,
  onChange,
  disabled,
  fieldErrors,
  errorIdPrefix,
  autoFocusTitle = false,
  identityExtra,
  allowPlanningToggle = false,
  section,
  readOnlyFields = [],
}: VolumeFieldsFormProps<TValue>) {
  const t = useTranslations("writing.volumes");

  return (
    <div className="grid gap-6">
      {section !== "planning" && <section className={section ? undefined : "border-b border-border pb-5"}>
        {!section && <h3 className="text-sm font-semibold tracking-normal text-foreground">{t("sections.identity")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-4 md:grid-cols-2`}>
          <Field label={t("fields.title")} error={fieldErrors.title?.[0]} errorId={`${errorIdPrefix}-title-error`}>
            <input
              name="title"
              autoFocus={autoFocusTitle}
              value={value.title}
              onChange={(event) => onChange({ ...value, title: event.target.value })}
              maxLength={120}
              placeholder={t("placeholders.title")}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.title) || undefined}
              aria-describedby={fieldErrors.title ? `${errorIdPrefix}-title-error` : undefined}
              className={INPUT_CLASS}
            />
          </Field>
          <Field label={t("fields.subtitle")}>
            <input name="subtitle" value={value.subtitle} onChange={(event) => onChange({ ...value, subtitle: event.target.value })} maxLength={120} placeholder={t("placeholders.subtitle")} disabled={disabled} className={INPUT_CLASS} />
          </Field>
          {identityExtra}
          <Field label={t("fields.theme")} className="md:col-span-2">
            <textarea name="theme" value={value.theme} onChange={(event) => onChange({ ...value, theme: event.target.value })} maxLength={500} placeholder={t("placeholders.theme")} disabled={disabled} className={TEXTAREA_CLASS} />
          </Field>
          <Field label={t("fields.summary")} className="md:col-span-2">
            <textarea name="summary" value={value.summary} onChange={(event) => onChange({ ...value, summary: event.target.value })} maxLength={2000} placeholder={t("placeholders.summary")} disabled={disabled} className={TEXTAREA_CLASS} />
          </Field>
          <Field label={t("fields.goal")} className="md:col-span-2">
            <textarea name="goal" value={value.goal} onChange={(event) => onChange({ ...value, goal: event.target.value })} maxLength={1000} placeholder={t("placeholders.goal")} disabled={disabled} className={TEXTAREA_CLASS} />
          </Field>
        </div>
      </section>}

      {section !== "identity" && <section>
        <div className="flex flex-wrap items-start justify-between gap-4">
          {!section && <h3 className="text-sm font-semibold tracking-normal text-foreground">{t("sections.planning")}</h3>}
          {allowPlanningToggle && (
            <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-medium text-foreground">
              <input
                name="planning_enabled"
                type="checkbox"
                checked={value.planning !== null}
                onChange={(event) => onChange({
                  ...value,
                  planning: event.target.checked
                    ? {
                        premise: "",
                        major_conflict: "",
                        key_turning_points: [],
                        start_state: "",
                        end_state: "",
                        target_chapter_count: 1,
                        target_word_count: 1,
                      }
                    : null,
                })}
                disabled={disabled}
                className="size-4 accent-accent"
              />
              {t("planning.enable")}
            </label>
          )}
        </div>
        {value.planning && (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label={t("fields.premise")} className="md:col-span-2">
              <textarea name="premise" value={value.planning.premise} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, premise: event.target.value } })} maxLength={1000} placeholder={t("placeholders.premise")} disabled={disabled} className={TEXTAREA_CLASS} />
            </Field>
            <Field label={t("fields.majorConflict")} className="md:col-span-2">
              <textarea name="major_conflict" value={value.planning.major_conflict} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, major_conflict: event.target.value } })} maxLength={2000} placeholder={t("placeholders.majorConflict")} disabled={disabled} className={TEXTAREA_CLASS} />
            </Field>
              <TagInput
                name="key_turning_points"
                label={t("fields.turningPoints")}
                values={value.planning.key_turning_points}
                onChange={(points) => onChange({ ...value, planning: { ...value.planning!, key_turning_points: points } })}
                getRemoveAriaLabel={(point) => t("ai.actions.removeTurningPoint", { point })}
                placeholder={t("placeholders.turningPoint")}
                limitReachedText={t("ai.validation.turningPointLimit")}
                disabled={disabled}
                maxItems={20}
                splitOnPunctuation={false}
                wrapTags
                error={fieldErrors.key_turning_points?.[0]}
                className="md:col-span-2"
              />
            <Field label={t("fields.startState")} error={fieldErrors.start_state?.[0]} errorId={`${errorIdPrefix}-start-state-error`}>
              <textarea name="start_state" value={value.planning.start_state} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, start_state: event.target.value } })} maxLength={2000} placeholder={t("placeholders.startState")} disabled={disabled} readOnly={readOnlyFields.includes("start_state")} aria-invalid={Boolean(fieldErrors.start_state) || undefined} aria-describedby={fieldErrors.start_state ? `${errorIdPrefix}-start-state-error` : undefined} className={TEXTAREA_CLASS} />
            </Field>
            <Field label={t("fields.endState")} error={fieldErrors.end_state?.[0]} errorId={`${errorIdPrefix}-end-state-error`}>
              <textarea name="end_state" value={value.planning.end_state} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, end_state: event.target.value } })} maxLength={2000} placeholder={t("placeholders.endState")} disabled={disabled} readOnly={readOnlyFields.includes("end_state")} aria-invalid={Boolean(fieldErrors.end_state) || undefined} aria-describedby={fieldErrors.end_state ? `${errorIdPrefix}-end-state-error` : undefined} className={TEXTAREA_CLASS} />
            </Field>
            <Field label={t("fields.targetChapterCount")} error={fieldErrors.target_chapter_count?.[0]} errorId={`${errorIdPrefix}-chapters-error`}>
              <input name="target_chapter_count" type="number" min={1} max={1000} step={1} value={value.planning.target_chapter_count} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, target_chapter_count: Number(event.target.value) } })} disabled={disabled} readOnly={readOnlyFields.includes("target_chapter_count")} aria-invalid={Boolean(fieldErrors.target_chapter_count) || undefined} aria-describedby={fieldErrors.target_chapter_count ? `${errorIdPrefix}-chapters-error` : undefined} className={INPUT_CLASS} />
            </Field>
            <Field label={t("fields.targetWordCount")} error={fieldErrors.target_word_count?.[0]} errorId={`${errorIdPrefix}-words-error`}>
              <input name="target_word_count" type="number" min={1} max={10_000_000} step={1} value={value.planning.target_word_count} onChange={(event) => onChange({ ...value, planning: { ...value.planning!, target_word_count: Number(event.target.value) } })} disabled={disabled} readOnly={readOnlyFields.includes("target_word_count")} aria-invalid={Boolean(fieldErrors.target_word_count) || undefined} aria-describedby={fieldErrors.target_word_count ? `${errorIdPrefix}-words-error` : undefined} className={INPUT_CLASS} />
            </Field>
          </div>
        )}
      </section>}
    </div>
  );
}
