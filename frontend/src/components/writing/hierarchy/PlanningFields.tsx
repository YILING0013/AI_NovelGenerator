"use client";

import { useId } from "react";
import { useTranslations } from "next-intl";
import { RelationFieldShell } from "@/components/shared/RelationEditorPrimitives";
import TagList from "@/components/shared/TagList";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import type { ApiFieldErrors } from "@/lib/api";
import type { ChapterPlanning, EntityChoices, HierarchyRecord, PartPlanning, PlanningDraft, PlanningKind } from "@/types/hierarchy";

export const PLANNING_INPUT = "min-h-11 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30";
export const PLANNING_SECTIONS = ["identity", "planning", "references"] as const;
export type PlanningSection = typeof PLANNING_SECTIONS[number];
export const REFERENCE_FIELDS = ["character_ids", "faction_ids", "location_ids", "item_ids", "rule_ids", "pov_character_id"];

/** 功能：编辑篇章、场景或章计划，共用于人工编辑和候选审核。Args: props 当前草稿、实体选项、错误和修改回调。Returns: 稳定字段控件。 */
export default function PlanningFields({ kind, value, onChange, choices, disabled = false, errors = {}, section, readOnlyFields = [] }: {
  kind: PlanningKind; value: PlanningDraft; onChange: (value: PlanningDraft) => void;
  choices: EntityChoices; disabled?: boolean; errors?: ApiFieldErrors; section?: PlanningSection; readOnlyFields?: readonly string[];
}) {
  const t = useTranslations("writing.hierarchy");
  const id = useId();
  const plan = value.planning;
  const update = (field: string, next: unknown) => onChange({ ...value, planning: { ...plan, [field]: next } });
  const textFields = ["goal", "start_state", "end_state", ...(kind === "chapter" ? [] : ["continuity_notes"])];
  const listFields = kind === "chapter" ? ["beats", "must_include", "must_avoid"] : ["key_beats"];
  return <div className="space-y-4">
    {(!section || section === "identity") && <div className="grid gap-4">
      {(["title", "summary"] as const).map((field) => {
        const error = errors[field]?.join(" ");
        return <RelationFieldShell key={field} label={t(`fields.${field}`)} error={error} errorId={`${id}-${field}-error`}>
          {field === "title" ? <input name={field} value={value[field]} maxLength={120} disabled={disabled} onChange={(e) => onChange({ ...value, [field]: e.target.value })} className={PLANNING_INPUT} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined} />
            : <textarea name={field} value={value[field]} maxLength={2000} disabled={disabled} onChange={(e) => onChange({ ...value, [field]: e.target.value })} className={`${PLANNING_INPUT} min-h-24 resize-y leading-6`} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined} />}
        </RelationFieldShell>;
      })}
    </div>}
    {(!section || section === "planning") && <div className="grid gap-4">
      {textFields.map((field) => {
        const error = (errors[`planning.${field}`] ?? errors[field])?.join(" ");
        return <RelationFieldShell key={field} label={t(`fields.${field}`)} error={error} errorId={`${id}-${field}-error`}>
          <textarea name={field} value={String(plan[field as keyof typeof plan] ?? "")} maxLength={2000} disabled={disabled} readOnly={readOnlyFields.includes(field)} onChange={(e) => update(field, e.target.value)} className={`${PLANNING_INPUT} min-h-24 resize-y leading-6`} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined} />
        </RelationFieldShell>;
      })}
      {listFields.map((field) => {
        const values = (plan as unknown as Record<string, string[]>)[field];
        const error = (errors[`planning.${field}`] ?? errors[field])?.join(" ");
        return <RelationFieldShell key={field} label={t(`fields.${field}`)} error={error} errorId={`${id}-${field}-error`}>
          <textarea name={field} value={values.join("\n")} disabled={disabled} onChange={(e) => update(field, e.target.value.split("\n"))} className={`${PLANNING_INPUT} min-h-28 resize-y leading-6`} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined} />
        </RelationFieldShell>;
      })}
      <div className="grid gap-5 sm:grid-cols-2">
        {(kind === "chapter" ? ["target_word_count"] : ["target_chapter_count", "target_word_count"]).map((field) => {
          const error = (errors[`planning.${field}`] ?? errors[field])?.join(" ");
          return <RelationFieldShell key={field} label={t(`fields.${field}`)} error={error} errorId={`${id}-${field}-error`}>
            <input name={field} type="number" min={1} step={1} disabled={disabled} readOnly={readOnlyFields.includes(field)} value={(plan as PartPlanning)[field as "target_word_count" | "target_chapter_count"] ?? ""} onChange={(e) => update(field, e.target.value === "" ? null : Number(e.target.value))} className={PLANNING_INPUT} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined} />
          </RelationFieldShell>;
        })}
      </div>
    </div>}
    {(!section || section === "references") && <div className="grid gap-4">
      {kind === "chapter" ? <RelationFieldShell label={t("fields.pov_character_id")}>
        <select name="pov_character_id" value={(plan as ChapterPlanning).pov_character_id ?? ""} onChange={(e) => update("pov_character_id", e.target.value || null)} disabled={disabled} className={PLANNING_INPUT}>
          <option value="">{t("none")}</option>
          {choices.character_ids.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          {(plan as ChapterPlanning).pov_character_id && !choices.character_ids.some((item) => item.id === (plan as ChapterPlanning).pov_character_id) && <option value={(plan as ChapterPlanning).pov_character_id!}>{t("unavailableReference", { id: (plan as ChapterPlanning).pov_character_id! })}</option>}
        </select>
      </RelationFieldShell> : <EntityReferenceFields choices={choices} selected={plan as PartPlanning} onChange={update} disabled={disabled} errors={errors} />}
    </div>}
  </div>;
}

/** 功能：按业务名称选择五类引用，共用于计划与生成范围。Args: props 选项、已选ID、字段更新及错误。Returns: 可键盘操作的选择清单。 */
export function EntityReferenceFields({ choices, selected, onChange, disabled, errors = {} }: {
  choices: EntityChoices; selected: Record<keyof EntityChoices, string[]>;
  onChange: (field: keyof EntityChoices, ids: string[]) => void; disabled?: boolean; errors?: ApiFieldErrors;
}) {
  const t = useTranslations("writing.hierarchy");
  const id = useId();
  return <>{(Object.keys(choices) as (keyof EntityChoices)[]).map((field) => {
    const error = (errors[`planning.${field}`] ?? errors[field])?.join(" ");
    const options = [...choices[field], ...selected[field].filter((value) => !choices[field].some((item) => item.id === value)).map((value) => ({ id: value, name: t("unavailableReference", { id: value }) }))];
    return <fieldset key={field} className="min-w-0" aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-${field}-error` : undefined}>
        <legend className="mb-2 text-xs font-medium text-muted">{t(`fields.${field}`)}</legend>
        <div className="workspace-scrollbar flex max-h-52 min-w-0 flex-wrap gap-2 overflow-y-auto">
          {options.length ? options.map((item) => <label key={item.id} className={`flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-xl border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-accent/30 ${selected[field].includes(item.id) ? "border-accent/40 bg-selected text-accent" : "border-border bg-surface"}`}>
            <input type="checkbox" name={field} disabled={disabled} checked={selected[field].includes(item.id)} onChange={(e) => onChange(field, e.target.checked ? [...selected[field], item.id] : selected[field].filter((v) => v !== item.id))} className="size-4 shrink-0 accent-accent" /><span className="min-w-0 [overflow-wrap:anywhere]">{item.name}</span>
          </label>) : <span className="text-sm text-muted">{t("none")}</span>}
        </div>
        {error && <span id={`${id}-${field}-error`} className="text-xs text-danger">{error}</span>}
      </fieldset>;
  })}</>;
}

/** 功能：展示完整计划，共用于工作台与冲突对照。Args: props 已保存记录和实体名称。Returns: 按字段排列的只读计划。 */
export function PlanningReadout({ record, choices, section }: { record: HierarchyRecord; choices: EntityChoices; section?: PlanningSection }) {
  const t = useTranslations("writing.hierarchy");
  const fields: [string, unknown][] = [
    ...(!section || section === "identity" ? [["title", record.title], ["summary", record.summary]] as [string, unknown][] : []),
    ...Object.entries(record.planning ?? {}).filter(([field]) => !section || (section === "references" ? REFERENCE_FIELDS.includes(field) : section === "planning" && !REFERENCE_FIELDS.includes(field))),
  ];
  return <dl className="detail-fields grid min-w-0 gap-4">
    {fields.length ? fields.map(([field, value]) => <ReadOnlyField key={field}
      label={t.has(`fields.${field}`) ? t(`fields.${field}`) : field}
      wide={!["title", "target_chapter_count", "target_word_count", ...REFERENCE_FIELDS].includes(field)}
      value={Array.isArray(value) ? value.length ? <TagList values={value.map((item) => choices[field as keyof EntityChoices]?.find((entry) => entry.id === item)?.name ?? item)} label={t(`fields.${field}`)} /> : t("none") : field === "pov_character_id" && value ? choices.character_ids.find((entry) => entry.id === value)?.name ?? t("unavailableReference", { id: String(value) }) : value === null || value === "" ? t("none") : String(value)}
    />) : <ReadOnlyField label={t("none")} value="—" wide />}
  </dl>;
}
