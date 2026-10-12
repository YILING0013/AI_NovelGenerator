"use client";

import { useTranslations } from "next-intl";

import type { ApiFieldErrors } from "@/lib/api";
import type { CharacterRelationResponseV1 } from "@/types/character";
import type {
  CharacterVolumeParticipationScope,
  CharacterVolumePlanFieldsV1,
} from "@/types/characterVolumeState";

interface CharacterVolumeStateFormProps<T extends CharacterVolumePlanFieldsV1> {
  value: T;
  onChange: (value: T) => void;
  characterId: string;
  relations: CharacterRelationResponseV1[];
  characterNames: ReadonlyMap<string, string>;
  disabled?: boolean;
  fieldErrors?: ApiFieldErrors;
  errorIdPrefix: string;
  autoFocusCurrentGoal?: boolean;
  section?: "participation" | "relationships";
}

const PARTICIPATION_SCOPES: CharacterVolumeParticipationScope[] = [
  "primary",
  "secondary",
  "background",
];

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;

/**
 * 渲染卷内角色的参与计划表单；旧候选附带的处境字段保留原值，不在此编辑。
 *
 * @param props 正式字段草稿、当前角色、可选关系、错误与禁用状态。
 * @returns 只包含业务字段、不持有版本和提交状态的表单节点。
 */
export default function CharacterVolumeStateForm<T extends CharacterVolumePlanFieldsV1>({
  value,
  onChange,
  characterId,
  relations,
  characterNames,
  disabled = false,
  fieldErrors = {},
  errorIdPrefix,
  autoFocusCurrentGoal = true,
  section,
}: CharacterVolumeStateFormProps<T>) {
  const t = useTranslations("writing.characterVolumeStates");
  const availableRelations = relations.filter((relation) => (
    relation.is_active
    && !relation.is_deleted
    && (relation.source_character_id === characterId || relation.target_character_id === characterId)
  ));
  const availableRelationIds = new Set(availableRelations.map((relation) => relation.relation_id));
  const unavailableSelectedRelationIds = value.relationship_focus_ids.filter((relationId) => !availableRelationIds.has(relationId));

  const updateText = (field: "current_goal" | "start_state" | "planned_end_state", nextValue: string) => {
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <div className="space-y-8">
      {(!section || section === "participation") && <section aria-labelledby={section ? undefined : `${errorIdPrefix}-participation-heading`}>
        {!section && <h3 id={`${errorIdPrefix}-participation-heading`} className={section ? "sr-only" : "text-sm font-semibold text-foreground"}>
          {t("form.participationTitle")}
        </h3>}
        <div className={`${section ? "" : "mt-5"} grid gap-5 detail-fields`}>
          <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.participationScope")}</span>
            <select
              name="participation_scope"
              value={value.participation_scope}
              onChange={(event) => onChange({
                ...value,
                participation_scope: event.target.value as CharacterVolumeParticipationScope,
              })}
              className={INPUT_CLASS}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.participation_scope)}
              aria-describedby={fieldErrors.participation_scope ? `${errorIdPrefix}-participation_scope-error` : undefined}
            >
              {PARTICIPATION_SCOPES.map((scope) => (
                <option key={scope} value={scope}>{t(`scope.${scope}`)}</option>
              ))}
            </select>
            <FieldError id={`${errorIdPrefix}-participation_scope-error`} messages={fieldErrors.participation_scope} />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.arcProgress")}</span>
            <input
              name="arc_progress"
              type="number"
              min={0}
              max={100}
              step={1}
              value={value.arc_progress}
              onChange={(event) => onChange({ ...value, arc_progress: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.arc_progress)}
              aria-describedby={fieldErrors.arc_progress ? `${errorIdPrefix}-arc_progress-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-arc_progress-error`} messages={fieldErrors.arc_progress} />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-muted col-span-full">
            <span>{t("fields.currentGoal")}</span>
            <textarea
              name="current_goal"
              value={value.current_goal}
              onChange={(event) => updateText("current_goal", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={1000}
              autoFocus={autoFocusCurrentGoal}
              aria-invalid={Boolean(fieldErrors.current_goal)}
              aria-describedby={fieldErrors.current_goal ? `${errorIdPrefix}-current_goal-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-current_goal-error`} messages={fieldErrors.current_goal} />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-muted col-span-full">
            <span>{t("fields.startState")}</span>
            <textarea
              name="start_state"
              value={value.start_state}
              onChange={(event) => updateText("start_state", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={2000}
              aria-invalid={Boolean(fieldErrors.start_state)}
              aria-describedby={fieldErrors.start_state ? `${errorIdPrefix}-start_state-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-start_state-error`} messages={fieldErrors.start_state} />
          </label>
          <label className="grid gap-1.5 text-xs font-medium text-muted col-span-full">
            <span>{t("fields.plannedEndState")}</span>
            <textarea
              name="planned_end_state"
              value={value.planned_end_state}
              onChange={(event) => updateText("planned_end_state", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={2000}
              aria-invalid={Boolean(fieldErrors.planned_end_state)}
              aria-describedby={fieldErrors.planned_end_state ? `${errorIdPrefix}-planned_end_state-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-planned_end_state-error`} messages={fieldErrors.planned_end_state} />
          </label>
        </div>
      </section>}

      {(!section || section === "relationships") && <fieldset
        className={section ? "" : "border-t border-border pt-7"}
        disabled={disabled}
        aria-invalid={Boolean(fieldErrors.relationship_focus_ids)}
        aria-describedby={fieldErrors.relationship_focus_ids
          ? `${errorIdPrefix}-relationship_focus_ids-error`
          : undefined}
      >
        <legend className={section ? "sr-only" : "text-sm font-semibold text-foreground"}>{t("fields.relationshipFocus")}</legend>
        {unavailableSelectedRelationIds.length > 0 && (
          <div className="mt-4 divide-y divide-amber-500/30 border-y border-amber-500/40 bg-amber-50 px-3 dark:bg-amber-950/30">
            {unavailableSelectedRelationIds.map((relationId) => {
              const relation = relations.find((item) => item.relation_id === relationId);
              const sourceName = relation ? characterNames.get(relation.source_character_id) ?? relation.source_character_id : "";
              const targetName = relation ? characterNames.get(relation.target_character_id) ?? relation.target_character_id : "";
              return (
                <label key={relationId} className="flex min-h-11 cursor-pointer items-start gap-3 py-3 text-sm text-amber-950 dark:text-amber-100">
                  <input
                    type="checkbox"
                    checked
                    onChange={() => onChange({
                      ...value,
                      relationship_focus_ids: value.relationship_focus_ids.filter((id) => id !== relationId),
                    })}
                    className="mt-0.5 size-4 accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="block font-medium">{t("form.unavailableRelationship")}</span>
                    <span className="mt-1 block break-words text-xs">
                      {relation ? `${sourceName} ↔ ${targetName} · ${relationId}` : relationId}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
        {availableRelations.length === 0 ? (
          <p className="mt-4 border-y border-dashed border-border py-5 text-sm text-muted">
            {t("form.noRelationships")}
          </p>
        ) : (
          <div className="mt-4 divide-y divide-border border-y border-border">
            {availableRelations.map((relation) => {
              const checked = value.relationship_focus_ids.includes(relation.relation_id);
              const sourceName = characterNames.get(relation.source_character_id) ?? relation.source_character_id;
              const targetName = characterNames.get(relation.target_character_id) ?? relation.target_character_id;
              return (
                <label key={relation.relation_id} className="flex min-h-11 cursor-pointer items-start gap-3 px-1 py-3 text-sm text-foreground">
                  <input
                    type="checkbox"
                    name="relationship_focus_ids"
                    value={relation.relation_id}
                    checked={checked}
                    onChange={(event) => onChange({
                      ...value,
                      relationship_focus_ids: event.target.checked
                        ? [...value.relationship_focus_ids, relation.relation_id]
                        : value.relationship_focus_ids.filter((id) => id !== relation.relation_id),
                    })}
                    className="mt-0.5 size-4 accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="block leading-5">{sourceName} ↔ {targetName}</span>
                    <span className="mt-1 block font-mono text-xs text-muted">{relation.relation_id}</span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
        <FieldError id={`${errorIdPrefix}-relationship_focus_ids-error`} messages={fieldErrors.relationship_focus_ids} />
      </fieldset>}
    </div>
  );
}

function FieldError({ id, messages }: { id: string; messages?: string[] }) {
  if (!messages?.length) return null;
  return <p id={id} className="text-xs font-medium text-red-700 dark:text-red-300">{messages.join(" ")}</p>;
}
