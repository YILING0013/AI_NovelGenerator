"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import TagInput from "@/components/shared/TagInput";
import type { FactionFactField, FactionFactValuesV1 } from "@/types/factionFacts";
import { FACTION_FACT_FIELDS } from "./factionFactFields";
import { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";

/** 作者只编辑实际内容；未触及的空控件不生成空事实或默认状态。 */
export default function FactionFactFieldsEditor({ values, onChange, disabled = false, fields = FACTION_FACT_FIELDS }: {
  values: FactionFactValuesV1;
  onChange: (field: FactionFactField, value: FactionFactValuesV1[FactionFactField]) => void;
  disabled?: boolean;
  fields?: readonly FactionFactField[];
}) {
  const t = useTranslations("writing.factionFacts");
  const id = useId();
  return <div className="detail-fields grid gap-5">{fields.map((field) => {
    const value = values[field], fieldId = `${id}-${field}`;
    if (field === "core_values" || field === "resources") return <div key={field} className="min-w-0 space-y-2">
      <TagInput label={t(`fields.${field}`)} name={field} values={Array.isArray(value) ? value : []}
        onChange={(next) => onChange(field, next)} preserveItems disabled={disabled}
        maxItems={field === "core_values" ? 6 : 20} getRemoveAriaLabel={(tag) => t("removeTag", { value: tag })} />
      {value === undefined && <button type="button" disabled={disabled} className="text-xs text-accent disabled:opacity-60" onClick={() => onChange(field, [])}>{t("setEmpty")}</button>}
    </div>;
    return <label key={field} htmlFor={fieldId} className="grid min-w-0 gap-2 text-xs font-medium text-muted">
      <span>{t(`fields.${field}`)}</span>
      {field === "is_public" || field === "power_level" || field === "story_status" ? <select id={fieldId} name={field} className={INPUT} disabled={disabled}
        value={value === undefined ? "" : String(value)} onChange={(event) => onChange(field, event.target.value === "" ? undefined
          : field === "is_public" ? event.target.value === "true" : field === "power_level" ? Number(event.target.value) : event.target.value as "active" | "dormant" | "dissolved")}>
        <option value="">{t("notEntered")}</option>
        {field === "is_public" ? <><option value="true">{t("public")}</option><option value="false">{t("hidden")}</option></>
          : field === "power_level" ? [1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{t("power", { level })}</option>)
          : ["active", "dormant", "dissolved"].map((state) => <option key={state} value={state}>{t(`status.${state}`)}</option>)}
      </select> : <textarea id={fieldId} name={field} className={`${INPUT} resize-y leading-6`} rows={field === "faction_type" ? 2 : 4}
        value={typeof value === "string" ? value : ""} placeholder={t("notEntered")} disabled={disabled}
        maxLength={field === "faction_type" ? 80 : field === "positioning" ? 500 : field === "organization_style" ? 300 : 1000}
        onChange={(event) => onChange(field, event.target.value)} />}
    </label>;
  })}</div>;
}
