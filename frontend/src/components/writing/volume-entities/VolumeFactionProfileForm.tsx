"use client";

import { useTranslations } from "next-intl";
import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import type { CoreFaction } from "@/types/novel";
import type { VolumeFactionProfile } from "@/types/volumeEntity";

const INPUT = "min-h-11 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:opacity-60";

/** 功能：编辑本卷新势力的档案，父势力从同书可用资料中选择。Args: props 新档案、可用父势力、字段错误及更新方法。Returns: 不含内部 ID 输入的档案表单。 */
export default function VolumeFactionProfileForm({ value, factions, disabled, errors, onChange }: {
  value: VolumeFactionProfile; factions: CoreFaction[]; disabled: boolean; errors: ApiFieldErrors; onChange: (value: VolumeFactionProfile) => void;
}) {
  const t = useTranslations("writing.factions");
  const aiT = useTranslations("writing.volumeEntitiesAi");
  const textFields = [
    ["name", "name", 80], ["core_goal", "coreGoal", 500],
    ["hidden_goal", "hiddenGoal", 500],
    ["conflict_with_mainline", "conflict", 600], ["expandability", "expandability", 500],
  ] as const;
  return <div className="space-y-6">
    <div className="grid gap-5 sm:grid-cols-2">
      <label className="grid gap-2 text-xs font-medium text-muted">{aiT("factions.level")}
        <select className={INPUT} value={value.level_type} disabled={disabled} onChange={(event) => onChange({ ...value, level_type: event.target.value as "volume" | "local" })}>
          <option value="volume">{aiT("factions.volume")}</option><option value="local">{aiT("factions.local")}</option>
        </select>
      </label>
      <label className="grid gap-2 text-xs font-medium text-muted">{aiT("factions.parent")}
        <select className={INPUT} value={value.parent_faction_id ?? ""} disabled={disabled} onChange={(event) => onChange({ ...value, parent_faction_id: event.target.value || null })}>
          <option value="">{aiT("factions.noParent")}</option>
          {factions.map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{faction.name}</option>)}
        </select>
      </label>
    </div>
    {textFields.map(([field, label, maxLength]) => <label key={field} className="grid gap-2 text-xs font-medium text-muted">
      {t(`fields.${label}`)}
      {maxLength <= 80 ? <input className={INPUT} name={field} value={value[field]} disabled={disabled} maxLength={maxLength} aria-invalid={Boolean(errors[field])} onChange={(event) => onChange({ ...value, [field]: event.target.value })} />
        : <textarea className={`${INPUT} min-h-28 resize-y leading-6`} name={field} value={value[field]} disabled={disabled} maxLength={maxLength} aria-invalid={Boolean(errors[field])} onChange={(event) => onChange({ ...value, [field]: event.target.value })} />}
      {errors[field] && <span role="alert" className="text-danger">{errors[field].join(" · ")}</span>}
    </label>)}
    <div className="grid gap-5 sm:grid-cols-2">
      {([ ["alias", "aliases", 10], ["resources_and_advantages", "resources", 6], ["tags", "tags", 8] ] as const).map(([field, label, limit]) => <TagInput key={field} name={field} label={t(`fields.${label}`)} values={value[field]} disabled={disabled} error={errors[field]?.[0]} maxItems={limit} onChange={(items) => onChange({ ...value, [field]: items })} getRemoveAriaLabel={(tag) => t("removeTag", { tag })} />)}
    </div>
  </div>;
}
