"use client";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import { formatStableReferenceLabel } from "@/types/contracts";
import type { CharacterResponseV1 } from "@/types/character";
import type { LocationReadV1 } from "@/types/location";
import type { CoreFaction } from "@/types/novel";
import type {
  WorldRuleContentFieldsV1,
  WorldRuleScopeType,
} from "@/types/worldRule";

type WorldRuleContentForScope<TScope extends WorldRuleScopeType> = Omit<
  WorldRuleContentFieldsV1,
  "scope_type"
> & { scope_type: TScope };

export type WorldRuleEditorSection = "identity" | "scope" | "exceptions" | "consequences";

interface WorldRuleFieldsFormProps<TScope extends WorldRuleScopeType> {
  value: WorldRuleContentForScope<TScope>;
  allowedScopes: readonly TScope[];
  factions: CoreFaction[];
  characters: CharacterResponseV1[];
  locations?: LocationReadV1[];
  disabled: boolean;
  fieldErrors?: ApiFieldErrors;
  errorIdPrefix: string;
  onChange: (value: WorldRuleContentForScope<TScope>) => void;
  section?: WorldRuleEditorSection;
}

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;

/**
 * 渲染正式规则编辑与 AI 候选复核共同使用的业务字段。
 *
 * Args:
 *   value: 当前规则内容字段。
 *   allowedScopes: 当前调用方允许选择的规则范围；核心规则候选不包含地点。
 *   factions: 可绑定的同书势力。
 *   characters: 可绑定的同书角色。
 *   locations: 可绑定的同书地点，仅正式规则编辑传入。
 *   disabled: 是否锁定全部可编辑控件。
 *   fieldErrors: 顶层字段对应的错误信息。
 *   errorIdPrefix: 当前编辑器稳定的错误元素前缀。
 *   onChange: 任一业务字段变化后的完整值回调。
 *   section: 原位编辑时只显示当前节；创建和候选省略后显示全部字段。
 *
 * Returns:
 *   连续章节式的规则字段编辑节点；不包含正式状态、版本或 ID。
 */
export default function WorldRuleFieldsForm<TScope extends WorldRuleScopeType>({
  value,
  allowedScopes,
  factions,
  characters,
  locations = [],
  disabled,
  fieldErrors = {},
  errorIdPrefix,
  onChange,
  section,
}: WorldRuleFieldsFormProps<TScope>) {
  const t = useTranslations("writing.worldRules");
  const activeFactions = factions.filter(
    (faction) => !faction.is_deleted && faction.active_status === "active",
  );
  const activeCharacters = characters.filter(
    (character) => !character.is_deleted && character.status === "active",
  );
  const visibleLocations = locations.filter(
    (location) => (!location.is_deleted && location.status === "active")
      || (value.scope_type === "location" && value.scope_entity_ids.includes(location.location_id)),
  );
  const missingLocationIds = value.scope_type === "location"
    ? value.scope_entity_ids.filter((id) => !locations.some((location) => location.location_id === id))
    : [];

  const update = <K extends keyof WorldRuleContentForScope<TScope>>(
    field: K,
    nextValue: WorldRuleContentForScope<TScope>[K],
  ) => onChange({ ...value, [field]: nextValue });

  return (
    <div className={section ? "min-w-0" : "space-y-8"}>
      {(!section || section === "identity") && (
      <section>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.identity")}</h3>}
        <div className={`${section ? "" : "mt-5"} grid gap-5 detail-fields`}>
          <RuleField
            label={t("fields.name")}
            error={fieldErrors.name?.[0]}
            errorId={`${errorIdPrefix}-name-error`}
          >
            <input
              name="name"
              value={value.name}
              onChange={(event) => update("name", event.target.value)}
              maxLength={80}
              className={INPUT_CLASS}
              aria-invalid={Boolean(fieldErrors.name) || undefined}
              aria-describedby={fieldErrors.name ? `${errorIdPrefix}-name-error` : undefined}
              disabled={disabled}
            />
          </RuleField>
          <RuleField
            label={t("fields.category")}
            error={fieldErrors.category?.[0]}
            errorId={`${errorIdPrefix}-category-error`}
          >
            <input
              name="category"
              value={value.category}
              onChange={(event) => update("category", event.target.value)}
              maxLength={40}
              className={INPUT_CLASS}
              aria-invalid={Boolean(fieldErrors.category) || undefined}
              aria-describedby={fieldErrors.category ? `${errorIdPrefix}-category-error` : undefined}
              disabled={disabled}
            />
          </RuleField>
          <RuleField
            label={t("fields.priority")}
            error={fieldErrors.priority?.[0]}
            errorId={`${errorIdPrefix}-priority-error`}
          >
            <input
              name="priority"
              type="number"
              min={0}
              max={100}
              step={1}
              value={value.priority}
              onChange={(event) => update("priority", Number(event.target.value))}
              className={INPUT_CLASS}
              aria-invalid={Boolean(fieldErrors.priority) || undefined}
              aria-describedby={fieldErrors.priority ? `${errorIdPrefix}-priority-error` : undefined}
              disabled={disabled}
            />
          </RuleField>
          <RuleField
            label={t("fields.statement")}
            className="col-span-full"
            error={fieldErrors.statement?.[0]}
            errorId={`${errorIdPrefix}-statement-error`}
          >
            <textarea
              name="statement"
              value={value.statement}
              onChange={(event) => update("statement", event.target.value)}
              maxLength={2000}
              className={TEXTAREA_CLASS}
              aria-invalid={Boolean(fieldErrors.statement) || undefined}
              aria-describedby={fieldErrors.statement ? `${errorIdPrefix}-statement-error` : undefined}
              disabled={disabled}
            />
          </RuleField>
          <RuleField label={t("fields.enforcement")} className="col-span-full">
            <textarea
              name="enforcement"
              value={value.enforcement}
              onChange={(event) => update("enforcement", event.target.value)}
              maxLength={1000}
              className={TEXTAREA_CLASS}
              disabled={disabled}
            />
          </RuleField>
          <TagInput
            name="tags"
            label={t("fields.tags")}
            values={value.tags}
            onChange={(tags) => update("tags", tags)}
            getRemoveAriaLabel={(tag) => t("tag.remove", { value: tag })}
            placeholder={t("placeholders.tags")}
            limitReachedText={t("tag.limit", { count: 20 })}
            maxItems={20}
            disabled={disabled}
            className="col-span-full"
          />
        </div>
      </section>
      )}

      {(!section || section === "scope") && (
      <section className={section ? "" : "border-t border-border pt-8"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.scope")}</h3>}
        <div className={`${section ? "" : "mt-5"} grid gap-5`}>
          <RuleField label={t("fields.scopeType")}>
            <select
              name="scope_type"
              value={value.scope_type}
              onChange={(event) => onChange({
                ...value,
                scope_type: event.target.value as TScope,
                scope_entity_ids: [],
              })}
              className={INPUT_CLASS}
              disabled={disabled}
            >
              {allowedScopes.map((scope) => (
                <option key={scope} value={scope}>{{
                  global: t("scope.global"),
                  faction: t("scope.faction"),
                  character: t("scope.character"),
                  location: t("scope.location"),
                }[scope]}</option>
              ))}
            </select>
          </RuleField>
          {value.scope_type !== "global" && (
            <fieldset
              className="rounded-xl border border-border px-4 py-3"
              aria-describedby={fieldErrors.scope_entity_ids ? `${errorIdPrefix}-scope-entities-error` : undefined}
            >
              <legend className="px-1 text-xs font-medium text-muted">{t("fields.scopeEntities")}</legend>
              <div
                className="workspace-scrollbar mt-2 flex max-h-52 min-w-0 flex-wrap gap-2 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-accent/20"
                tabIndex={0}
                aria-label={t("fields.scopeEntities")}
              >
                {(value.scope_type === "faction"
                  ? activeFactions
                  : value.scope_type === "character"
                    ? activeCharacters
                    : visibleLocations).map((entity) => {
                  const id = value.scope_type === "faction"
                    ? (entity as CoreFaction).faction_id
                    : value.scope_type === "character"
                      ? (entity as CharacterResponseV1).character_id
                      : (entity as LocationReadV1).location_id;
                  const selected = value.scope_entity_ids.includes(id);
                  const unavailable = value.scope_type === "location"
                    && ((entity as LocationReadV1).is_deleted || (entity as LocationReadV1).status !== "active");
                  return (
                    <label key={id} className="flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm has-checked:border-accent/40 has-checked:bg-selected has-checked:text-accent focus-within:ring-2 focus-within:ring-accent/30">
                      <input
                        name="scope_entity_ids"
                        type="checkbox"
                        checked={selected}
                        onChange={(event) => update(
                          "scope_entity_ids",
                          event.target.checked
                            ? [...value.scope_entity_ids, id]
                            : value.scope_entity_ids.filter((item) => item !== id),
                        )}
                        className="size-4 shrink-0 accent-accent"
                        disabled={disabled || (!selected && value.scope_entity_ids.length >= 100)}
                      />
                      <span className="min-w-0 [overflow-wrap:anywhere]">
                        {formatStableReferenceLabel(entity.name, id)}
                        {unavailable ? ` · ${t("scope.unavailable")}` : ""}
                      </span>
                    </label>
                  );
                })}
                {missingLocationIds.map((id) => (
                  <label key={id} className="flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2 text-sm has-checked:border-accent/40 has-checked:bg-selected has-checked:text-accent focus-within:ring-2 focus-within:ring-accent/30">
                    <input
                      name="scope_entity_ids"
                      type="checkbox"
                      checked
                      onChange={() => update("scope_entity_ids", value.scope_entity_ids.filter((item) => item !== id))}
                      className="size-4 shrink-0 accent-accent"
                      disabled={disabled}
                    />
                    <span className="min-w-0 [overflow-wrap:anywhere]">{id} · {t("scope.unavailable")}</span>
                  </label>
                ))}
                {(value.scope_type === "faction"
                  ? activeFactions
                  : value.scope_type === "character"
                    ? activeCharacters
                    : visibleLocations).length === 0 && missingLocationIds.length === 0 && (
                  <p className="py-4 text-sm text-muted">
                    {value.scope_type === "faction"
                      ? t("scope.empty.faction")
                      : value.scope_type === "character"
                        ? t("scope.empty.character")
                        : t("scope.empty.location")}
                  </p>
                )}
              </div>
              {fieldErrors.scope_entity_ids?.[0] && (
                <p id={`${errorIdPrefix}-scope-entities-error`} className="mt-2 text-xs text-red-600 dark:text-red-300">
                  {fieldErrors.scope_entity_ids[0]}
                </p>
              )}
            </fieldset>
          )}
        </div>
      </section>
      )}

      {(!section || section === "exceptions") && (
      <section className={section ? "" : "border-t border-border pt-8"}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          {!section && <div>
            <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.exceptions")}</h3>
          </div>}
          <Button
            variant="outline"
            size="sm"
            onPress={() => update("exceptions", [...value.exceptions, { condition: "", effect: "" }])}
            isDisabled={disabled || value.exceptions.length >= 20}
          >
            {t("actions.addException")}
          </Button>
        </div>
        {fieldErrors.exceptions?.[0] && (
          <p id={`${errorIdPrefix}-exceptions-error`} className="mt-3 text-xs text-red-600 dark:text-red-300">
            {fieldErrors.exceptions[0]}
          </p>
        )}
        <div className="mt-5 space-y-6">
          {value.exceptions.map((item, index) => (
            <div key={`exception-${index}`} className="grid gap-4 border-b border-border pb-6 last:border-b-0">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-xs font-medium text-muted">{t("editor.exceptionIndex", { index: index + 1 })}</h4>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-danger"
                  onPress={() => update("exceptions", value.exceptions.filter((_, itemIndex) => itemIndex !== index))}
                  isDisabled={disabled}
                >
                  {t("actions.remove")}
                </Button>
              </div>
              <RuleField label={t("fields.exceptionCondition")}>
                <textarea
                  name={index === 0 ? "exceptions" : `exception_condition_${index}`}
                  value={item.condition}
                  onChange={(event) => update(
                    "exceptions",
                    value.exceptions.map((current, itemIndex) => itemIndex === index
                      ? { ...current, condition: event.target.value }
                      : current),
                  )}
                  maxLength={500}
                  className={TEXTAREA_CLASS}
                  aria-invalid={Boolean(fieldErrors.exceptions) || undefined}
                  aria-describedby={fieldErrors.exceptions ? `${errorIdPrefix}-exceptions-error` : undefined}
                  disabled={disabled}
                />
              </RuleField>
              <RuleField label={t("fields.exceptionEffect")}>
                <textarea
                  name={`exception_effect_${index}`}
                  value={item.effect}
                  onChange={(event) => update(
                    "exceptions",
                    value.exceptions.map((current, itemIndex) => itemIndex === index
                      ? { ...current, effect: event.target.value }
                      : current),
                  )}
                  maxLength={500}
                  className={TEXTAREA_CLASS}
                  disabled={disabled}
                />
              </RuleField>
            </div>
          ))}
        </div>
      </section>
      )}

      {(!section || section === "consequences") && (
        <section className={section ? "" : "border-t border-border pt-8"}>
          <TagInput
            name="costs_and_consequences"
            label={t("sections.consequences")}
            values={value.costs_and_consequences}
            onChange={(items) => update("costs_and_consequences", items)}
            getRemoveAriaLabel={(item) => t("tag.remove", { value: item })}
            maxItems={20}
            limitReachedText={t("tag.limit", { count: 20 })}
            splitOnPunctuation={false}
            wrapTags
            disabled={disabled}
            error={fieldErrors.costs_and_consequences?.[0]}
          />
        </section>
      )}
    </div>
  );
}

function RuleField({
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
    <label className={`grid gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {error && <span id={errorId} className="text-xs text-red-600 dark:text-red-300">{error}</span>}
    </label>
  );
}
