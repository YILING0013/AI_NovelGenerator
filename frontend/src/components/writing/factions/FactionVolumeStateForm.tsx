"use client";

import { useTranslations } from "next-intl";

import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import type {
  FactionVolumeActiveStatus,
  FactionVolumeParticipationScope,
  FactionVolumeStateFields,
  FactionVolumePlanFieldsV1,
} from "@/types/factionVolumeState";

type EditableFields = FactionVolumePlanFieldsV1 & Partial<FactionVolumeStateFields>;
interface FactionVolumeStateFormProps<T extends EditableFields> {
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  fieldErrors?: ApiFieldErrors;
  errorIdPrefix: string;
  autoFocusCurrentGoal?: boolean;
  planOnly?: boolean;
  section?: "participation" | "agenda";
}

const PARTICIPATION_SCOPES: FactionVolumeParticipationScope[] = [
  "primary",
  "secondary",
  "background",
];
const ACTIVE_STATUSES: FactionVolumeActiveStatus[] = ["active", "dormant", "dissolved"];
const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;

/**
 * 渲染卷内势力的创建表单或当前编辑章节。
 *
 * @param props 正式字段草稿、错误与禁用状态。
 * @returns 只包含业务字段、不持有主档版本或提交状态的表单节点。
 */
export default function FactionVolumeStateForm<T extends EditableFields>({
  value,
  onChange,
  disabled = false,
  fieldErrors = {},
  errorIdPrefix,
  autoFocusCurrentGoal = true,
  section,
  planOnly = false,
}: FactionVolumeStateFormProps<T>) {
  const t = useTranslations("writing.factionVolumeStates");

  const updateText = (field: keyof FactionVolumeStateFields, nextValue: string) => {
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
                participation_scope: event.target.value as FactionVolumeParticipationScope,
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
          {!planOnly && <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.activeStatus")}</span>
            <select
              name="active_status"
              value={value.active_status}
              onChange={(event) => onChange({
                ...value,
                active_status: event.target.value as FactionVolumeActiveStatus,
              })}
              className={INPUT_CLASS}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.active_status)}
              aria-describedby={fieldErrors.active_status ? `${errorIdPrefix}-active_status-error` : undefined}
            >
              {ACTIVE_STATUSES.map((status) => (
                <option key={status} value={status}>{t(`activeStatus.${status}`)}</option>
              ))}
            </select>
            <FieldError id={`${errorIdPrefix}-active_status-error`} messages={fieldErrors.active_status} />
          </label>}
          {!planOnly && <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.powerLevel")}</span>
            <input
              name="power_level"
              type="number"
              min={1}
              max={5}
              step={1}
              value={value.power_level}
              onChange={(event) => onChange({ ...value, power_level: Number(event.target.value) })}
              className={INPUT_CLASS}
              disabled={disabled}
              aria-invalid={Boolean(fieldErrors.power_level)}
              aria-describedby={fieldErrors.power_level ? `${errorIdPrefix}-power_level-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-power_level-error`} messages={fieldErrors.power_level} />
          </label>}
          {!planOnly && <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.influenceScope")}</span>
            <textarea
              name="influence_scope"
              value={value.influence_scope}
              onChange={(event) => updateText("influence_scope", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={1000}
              aria-invalid={Boolean(fieldErrors.influence_scope)}
              aria-describedby={fieldErrors.influence_scope ? `${errorIdPrefix}-influence_scope-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-influence_scope-error`} messages={fieldErrors.influence_scope} />
          </label>}
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

      {(!section || section === "agenda") && <section className={section ? "" : "border-t border-border pt-7"} aria-labelledby={section ? undefined : `${errorIdPrefix}-agenda-heading`}>
        {!section && <h3 id={`${errorIdPrefix}-agenda-heading`} className={section ? "sr-only" : "text-sm font-semibold text-foreground"}>
          {t("form.agendaTitle")}
        </h3>}
        <div className={`${section ? "" : "mt-5"} grid gap-5 detail-fields`}>
          {!planOnly && <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.publicStance")}</span>
            <textarea
              name="public_stance"
              value={value.public_stance}
              onChange={(event) => updateText("public_stance", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={1000}
              aria-invalid={Boolean(fieldErrors.public_stance)}
              aria-describedby={fieldErrors.public_stance ? `${errorIdPrefix}-public_stance-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-public_stance-error`} messages={fieldErrors.public_stance} />
          </label>}
          <label className="grid gap-1.5 text-xs font-medium text-muted">
            <span>{t("fields.hiddenAgenda")}</span>
            <textarea
              name="hidden_agenda"
              value={value.hidden_agenda}
              onChange={(event) => updateText("hidden_agenda", event.target.value)}
              className={TEXTAREA_CLASS}
              disabled={disabled}
              maxLength={1000}
              aria-invalid={Boolean(fieldErrors.hidden_agenda)}
              aria-describedby={fieldErrors.hidden_agenda ? `${errorIdPrefix}-hidden_agenda-error` : undefined}
            />
            <FieldError id={`${errorIdPrefix}-hidden_agenda-error`} messages={fieldErrors.hidden_agenda} />
          </label>
        </div>
        {!planOnly && <TagInput
          className="mt-5"
          name="resources"
          label={t("fields.resources")}
          values={value.resources ?? []}
          onChange={(resources) => onChange({ ...value, resources })}
          getRemoveAriaLabel={(tag) => t("removeResource", { tag })}
          placeholder={t("resourcePlaceholder")}
          limitReachedText={t("resourceLimit")}
          maxItems={20}
          disabled={disabled}
          error={fieldErrors.resources?.join(" ")}
        />}
      </section>}
    </div>
  );
}

function FieldError({ id, messages }: { id: string; messages?: string[] }) {
  if (!messages?.length) return null;
  return <p id={id} className="text-xs font-medium text-red-700 dark:text-red-300">{messages.join(" ")}</p>;
}
