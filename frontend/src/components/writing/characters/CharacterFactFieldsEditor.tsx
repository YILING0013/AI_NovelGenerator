"use client";

import { useId } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import type { CharacterFactField, CharacterFactValuesV1 } from "@/types/characterFacts";
import { CHARACTER_FACT_FIELDS } from "./characterFactFields";

const INPUT = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-60";
const ARRAY_FIELDS = new Set<CharacterFactField>(["strengths", "weaknesses", "abilities"]);
const SHORT_FIELDS = new Set<CharacterFactField>(["gender", "age_group", "race"]);
const CLEARABLE_FIELDS = new Set<CharacterFactField>([...ARRAY_FIELDS, "psychological_state", "public_state", "hidden_state", "actual_goal"]);

/** 编辑明确的初始事实，未编辑字段保持未知。
 * Args: values 稀疏事实；onChange 修改回调；disabled 锁定状态；fieldErrors 字段错误。
 * Returns: 区分未知、明确空值与撤回认领的字段表单。
 */
export default function CharacterFactFieldsEditor({ values, onChange, disabled = false, fieldErrors = {} }: {
  values: CharacterFactValuesV1;
  onChange: (values: CharacterFactValuesV1) => void;
  disabled?: boolean;
  fieldErrors?: ApiFieldErrors;
}) {
  const t = useTranslations("writing.characterFacts");
  const id = useId();
  const update = (field: CharacterFactField, value: string | string[] | undefined) => {
    const next = { ...values };
    if (value === undefined) delete next[field];
    else Object.assign(next, { [field]: value });
    onChange(next);
  };
  return <div className="detail-fields grid gap-5">{CHARACTER_FACT_FIELDS.map((field) => {
    const value = values[field], fieldId = `${id}-${field}`, error = fieldErrors[field]?.join(" ");
    return <div key={field} className="min-w-0 space-y-2">
      {ARRAY_FIELDS.has(field) ? <TagInput name={field} label={t(`fields.${field}`)} values={Array.isArray(value) ? value : []}
        preserveItems disabled={disabled} maxItems={12} getRemoveAriaLabel={(tag) => t("removeTag", { value: tag })}
        error={error} onChange={(next) => update(field, next)} />
        : <label htmlFor={fieldId} className="grid gap-2 text-xs font-medium text-muted"><span>{t(`fields.${field}`)}</span>
          {SHORT_FIELDS.has(field) ? <input id={fieldId} name={field} type="text" className={INPUT} maxLength={80}
            value={typeof value === "string" ? value : ""} placeholder={t("notEntered")} disabled={disabled}
            aria-invalid={Boolean(error)} aria-describedby={error ? `${fieldId}-error` : `${fieldId}-status`}
            onChange={(event) => update(field, event.target.value)} />
          : <textarea id={fieldId} name={field} rows={4} className={`${INPUT} resize-y leading-6`}
            maxLength={field === "identity" ? 500 : 1000}
            value={typeof value === "string" ? value : ""} placeholder={t("notEntered")} disabled={disabled}
            aria-invalid={Boolean(error)} aria-describedby={error ? `${fieldId}-error` : `${fieldId}-status`}
            onChange={(event) => update(field, event.target.value)} />}
        </label>}
      <p id={`${fieldId}-status`} className="text-xs text-muted">{value === undefined ? t("notEntered") : value.length === 0 ? t("cleared") : null}</p>
      <div className="flex flex-wrap gap-3 text-xs text-accent">
        {value !== undefined && <Button type="button" size="sm" variant="ghost" isDisabled={disabled} className="min-h-11" onPress={() => update(field, undefined)}>{t("leaveUnknown")}</Button>}
        {value === undefined && CLEARABLE_FIELDS.has(field) && <Button type="button" size="sm" variant="ghost" isDisabled={disabled} className="min-h-11" onPress={() => update(field, ARRAY_FIELDS.has(field) ? [] : "")}>{t("recordEmpty")}</Button>}
      </div>
      {error && <p id={`${fieldId}-error`} role="alert" className="text-xs text-danger">{error}</p>}
    </div>;
  })}</div>;
}
