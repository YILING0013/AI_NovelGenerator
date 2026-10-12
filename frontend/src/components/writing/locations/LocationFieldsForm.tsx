"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import { formatStableReferenceLabel } from "@/types/contracts";
import type { LocationContentFieldsV1, LocationReadV1 } from "@/types/location";
import type { CoreFaction } from "@/types/novel";
import type { WorldRuleReadV1 } from "@/types/worldRule";

export type LocationEditorSection = "identity" | "setting" | "references" | "story";

interface LocationFieldsFormProps {
  section?: LocationEditorSection;
  value: LocationContentFieldsV1;
  locations: LocationReadV1[];
  excludedParentIds: ReadonlySet<string>;
  rules: WorldRuleReadV1[];
  factions: CoreFaction[];
  disabled: boolean;
  fieldErrors?: ApiFieldErrors;
  errorIdPrefix: string;
  onChange: (value: LocationContentFieldsV1) => void;
  candidateParentOptions?: ReadonlyArray<{ candidate_ref: string; name: string }>;
  parentCandidateRef?: string | null;
  onParentSelectionChange?: (selection: {
    parentLocationId: string | null;
    parentCandidateRef: string | null;
  }) => void;
}

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;

/**
 * 渲染人工维护与后续地点候选共同使用的业务字段。
 *
 * Args:
 *   section: 只显示当前编辑章节；省略时显示完整创建表单。
 *   value: 当前地点内容字段。
 *   locations: 当前小说的活动地点，用于选择父级。
 *   excludedParentIds: 编辑目标自身及全部后代 ID，不能成为新父级。
 *   rules: 当前小说的正式世界规则。
 *   factions: 当前小说的正式势力。
 *   disabled: 是否锁定全部编辑控件。
 *   fieldErrors: 顶层字段对应的服务端或客户端错误。
 *   errorIdPrefix: 当前表单稳定的错误元素前缀。
 *   onChange: 任一内容字段变化后的完整值回调。
 *   candidateParentOptions: 当前候选之前、可作为临时父级的地点候选。
 *   parentCandidateRef: 当前选中的临时父级引用。
 *   onParentSelectionChange: 候选父级变化后的互斥选择回调；提供时启用正式/候选双来源父级选择。
 *
 * Returns:
 *   不包含正式状态、版本、顺序和审计字段的连续地点编辑章节。
 */
export default function LocationFieldsForm({
  section,
  value,
  locations,
  excludedParentIds,
  rules,
  factions,
  disabled,
  fieldErrors = {},
  errorIdPrefix,
  onChange,
  candidateParentOptions = [],
  parentCandidateRef = null,
  onParentSelectionChange,
}: LocationFieldsFormProps) {
  const t = useTranslations("writing.locations");
  const parentOptions = locations.filter(
    (location) => !location.is_deleted
      && location.status === "active"
      && !excludedParentIds.has(location.location_id),
  );
  const visibleRules = rules.filter(
    (rule) => (!rule.is_deleted && rule.status === "active")
      || value.applicable_rule_ids.includes(rule.rule_id),
  );
  const missingRuleIds = value.applicable_rule_ids.filter(
    (id) => !rules.some((rule) => rule.rule_id === id),
  );
  const visibleFactions = factions.filter(
    (faction) => (!faction.is_deleted && faction.active_status === "active")
      || value.associated_faction_ids.includes(faction.faction_id),
  );
  const missingFactionIds = value.associated_faction_ids.filter(
    (id) => !factions.some((faction) => faction.faction_id === id),
  );

  const update = <K extends keyof LocationContentFieldsV1>(
    field: K,
    nextValue: LocationContentFieldsV1[K],
  ) => onChange({ ...value, [field]: nextValue });
  const parentError = fieldErrors.parent_location_ref?.[0] ?? fieldErrors.parent_location_id?.[0];
  const candidateParentMode = onParentSelectionChange !== undefined;
  const parentSelectValue = candidateParentMode
    ? parentCandidateRef
      ? `candidate:${parentCandidateRef}`
      : value.parent_location_id
        ? `location:${value.parent_location_id}`
        : ""
    : value.parent_location_id ?? "";

  return (
    <div className="space-y-4">
      {(!section || section === "identity") && <section>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.identity")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <LocationField label={t("fields.name")} error={fieldErrors.name?.[0]} errorId={`${errorIdPrefix}-name-error`}>
            <input
              name="name"
              autoFocus
              value={value.name}
              onChange={(event) => update("name", event.target.value)}
              maxLength={80}
              className={INPUT_CLASS}
              aria-invalid={Boolean(fieldErrors.name) || undefined}
              aria-describedby={fieldErrors.name ? `${errorIdPrefix}-name-error` : undefined}
              disabled={disabled}
            />
          </LocationField>
          <LocationField label={t("fields.locationType")} error={fieldErrors.location_type?.[0]} errorId={`${errorIdPrefix}-type-error`}>
            <input
              name="location_type"
              value={value.location_type}
              onChange={(event) => update("location_type", event.target.value)}
              maxLength={40}
              className={INPUT_CLASS}
              aria-invalid={Boolean(fieldErrors.location_type) || undefined}
              aria-describedby={fieldErrors.location_type ? `${errorIdPrefix}-type-error` : undefined}
              disabled={disabled}
            />
          </LocationField>
          <TagInput
            name="aliases"
            label={t("fields.aliases")}
            values={value.aliases}
            onChange={(aliases) => update("aliases", aliases)}
            getRemoveAriaLabel={(alias) => t("tag.removeAlias", { value: alias })}
            placeholder={t("placeholders.aliases")}
            limitReachedText={t("tag.aliasLimit", { count: 10 })}
            maxItems={10}
            disabled={disabled}
            error={fieldErrors.aliases?.[0]}
          />
          <LocationField label={t("fields.parent")} error={parentError} errorId={`${errorIdPrefix}-parent-error`}>
            <select
              name="parent_location_id"
              value={parentSelectValue}
              onChange={(event) => {
                if (!candidateParentMode) {
                  update("parent_location_id", event.target.value || null);
                  return;
                }
                if (event.target.value.startsWith("candidate:")) {
                  onParentSelectionChange?.({
                    parentLocationId: null,
                    parentCandidateRef: event.target.value.slice("candidate:".length),
                  });
                } else if (event.target.value.startsWith("location:")) {
                  onParentSelectionChange?.({
                    parentLocationId: event.target.value.slice("location:".length),
                    parentCandidateRef: null,
                  });
                } else {
                  onParentSelectionChange?.({ parentLocationId: null, parentCandidateRef: null });
                }
              }}
              className={INPUT_CLASS}
              aria-invalid={Boolean(parentError) || undefined}
              aria-describedby={parentError ? `${errorIdPrefix}-parent-error` : undefined}
              disabled={disabled}
            >
              <option value="">{t("parent.root")}</option>
              {candidateParentMode ? (
                <>
                  {parentOptions.length > 0 && (
                    <optgroup label={t("parent.formalGroup")}>
                      {parentOptions.map((location) => (
                        <option key={location.location_id} value={`location:${location.location_id}`}>
                          {formatStableReferenceLabel(location.name, location.location_id)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {candidateParentOptions.length > 0 && (
                    <optgroup label={t("parent.candidateGroup")}>
                      {candidateParentOptions.map((candidate) => (
                        <option key={candidate.candidate_ref} value={`candidate:${candidate.candidate_ref}`}>
                          {formatStableReferenceLabel(candidate.name, candidate.candidate_ref)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </>
              ) : parentOptions.map((location) => (
                <option key={location.location_id} value={location.location_id}>
                  {formatStableReferenceLabel(location.name, location.location_id)}
                </option>
              ))}
            </select>
          </LocationField>
          <LocationField className="col-span-full" label={t("fields.description")} error={fieldErrors.description?.[0]} errorId={`${errorIdPrefix}-description-error`}>
            <textarea
              name="description"
              value={value.description}
              onChange={(event) => update("description", event.target.value)}
              maxLength={2000}
              className={TEXTAREA_CLASS}
              aria-invalid={Boolean(fieldErrors.description) || undefined}
              aria-describedby={fieldErrors.description ? `${errorIdPrefix}-description-error` : undefined}
              disabled={disabled}
            />
          </LocationField>
          <TagInput
            name="tags"
            label={t("fields.tags")}
            values={value.tags}
            onChange={(tags) => update("tags", tags)}
            getRemoveAriaLabel={(tag) => t("tag.removeTag", { value: tag })}
            placeholder={t("placeholders.tags")}
            limitReachedText={t("tag.tagLimit", { count: 20 })}
            maxItems={20}
            disabled={disabled}
            error={fieldErrors.tags?.[0]}
            className="col-span-full"
          />
        </div>
      </section>}

      {(!section || section === "setting") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.setting")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <LocationField className="col-span-full" label={t("fields.environment")} error={fieldErrors.environment?.[0]} errorId={`${errorIdPrefix}-environment-error`}>
            <textarea name="environment" value={value.environment} onChange={(event) => update("environment", event.target.value)} maxLength={1000} className={TEXTAREA_CLASS} aria-invalid={Boolean(fieldErrors.environment) || undefined} aria-describedby={fieldErrors.environment ? `${errorIdPrefix}-environment-error` : undefined} disabled={disabled} />
          </LocationField>
          <LocationField label={t("fields.atmosphere")} error={fieldErrors.atmosphere?.[0]} errorId={`${errorIdPrefix}-atmosphere-error`}>
            <textarea name="atmosphere" value={value.atmosphere} onChange={(event) => update("atmosphere", event.target.value)} maxLength={1000} className={TEXTAREA_CLASS} aria-invalid={Boolean(fieldErrors.atmosphere) || undefined} aria-describedby={fieldErrors.atmosphere ? `${errorIdPrefix}-atmosphere-error` : undefined} disabled={disabled} />
          </LocationField>
          <LocationField label={t("fields.geography")} error={fieldErrors.geography?.[0]} errorId={`${errorIdPrefix}-geography-error`}>
            <textarea name="geography" value={value.geography} onChange={(event) => update("geography", event.target.value)} maxLength={1000} className={TEXTAREA_CLASS} aria-invalid={Boolean(fieldErrors.geography) || undefined} aria-describedby={fieldErrors.geography ? `${errorIdPrefix}-geography-error` : undefined} disabled={disabled} />
          </LocationField>
        </div>
      </section>}

      {(!section || section === "references") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.constraints")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5`}>
          <TagInput
            name="rules_and_constraints"
            className="grid-cols-1"
            splitOnPunctuation={false}
            wrapTags
            label={t("fields.rulesAndConstraints")}
            values={value.rules_and_constraints}
            onChange={(items) => update("rules_and_constraints", items)}
            getRemoveAriaLabel={(item) => t("tag.removeConstraint", { value: item })}
            placeholder={t("placeholders.constraints")}
            limitReachedText={t("tag.constraintLimit", { count: 20 })}
            maxItems={20}
            disabled={disabled}
            error={fieldErrors.rules_and_constraints?.[0]}
          />

          <fieldset className="min-w-0 rounded-xl border border-border px-4 py-3" aria-describedby={fieldErrors.applicable_rule_ids ? `${errorIdPrefix}-rules-error` : undefined}>
            <legend className="px-1 text-xs font-medium text-muted">{t("fields.applicableRules")}</legend>
            <div className="workspace-scrollbar mt-2 max-h-52 space-y-1 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-accent/20" tabIndex={0} aria-label={t("fields.applicableRules")}>
              {visibleRules.map((rule) => {
                const selected = value.applicable_rule_ids.includes(rule.rule_id);
                const unavailable = rule.is_deleted || rule.status !== "active";
                return (
                  <label key={rule.rule_id} className="flex min-h-11 items-center gap-3 border-b border-border/70 py-2 text-sm last:border-b-0">
                    <input
                      name="applicable_rule_ids"
                      type="checkbox"
                      checked={selected}
                      onChange={(event) => update(
                        "applicable_rule_ids",
                        event.target.checked
                          ? [...value.applicable_rule_ids, rule.rule_id]
                          : value.applicable_rule_ids.filter((id) => id !== rule.rule_id),
                      )}
                      className="size-4 shrink-0 accent-accent"
                      disabled={disabled || (!selected && value.applicable_rule_ids.length >= 50)}
                    />
                    <span className="min-w-0 truncate">
                      {formatStableReferenceLabel(rule.name, rule.rule_id)}
                      {unavailable ? ` · ${t("references.unavailable")}` : ""}
                    </span>
                  </label>
                );
              })}
              {missingRuleIds.map((id) => (
                <label key={id} className="flex min-h-11 items-center gap-3 border-b border-border/70 py-2 text-sm last:border-b-0">
                  <input name="applicable_rule_ids" type="checkbox" checked onChange={() => update("applicable_rule_ids", value.applicable_rule_ids.filter((item) => item !== id))} className="size-4 shrink-0 accent-accent" disabled={disabled} />
                  <span className="min-w-0 truncate">{id} · {t("references.unavailable")}</span>
                </label>
              ))}
              {visibleRules.length === 0 && missingRuleIds.length === 0 && <p className="py-4 text-sm text-muted">{t("references.emptyRules")}</p>}
            </div>
            {fieldErrors.applicable_rule_ids?.[0] && <p id={`${errorIdPrefix}-rules-error`} className="mt-2 text-xs text-red-600 dark:text-red-300">{fieldErrors.applicable_rule_ids[0]}</p>}
          </fieldset>

          <fieldset className="min-w-0 rounded-xl border border-border px-4 py-3" aria-describedby={fieldErrors.associated_faction_ids ? `${errorIdPrefix}-factions-error` : undefined}>
            <legend className="px-1 text-xs font-medium text-muted">{t("fields.associatedFactions")}</legend>
            <div className="workspace-scrollbar mt-2 max-h-52 space-y-1 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-accent/20" tabIndex={0} aria-label={t("fields.associatedFactions")}>
              {visibleFactions.map((faction) => {
                const selected = value.associated_faction_ids.includes(faction.faction_id);
                const unavailable = Boolean(faction.is_deleted) || faction.active_status !== "active";
                return (
                  <label key={faction.faction_id} className="flex min-h-11 items-center gap-3 border-b border-border/70 py-2 text-sm last:border-b-0">
                    <input
                      name="associated_faction_ids"
                      type="checkbox"
                      checked={selected}
                      onChange={(event) => update(
                        "associated_faction_ids",
                        event.target.checked
                          ? [...value.associated_faction_ids, faction.faction_id]
                          : value.associated_faction_ids.filter((id) => id !== faction.faction_id),
                      )}
                      className="size-4 shrink-0 accent-accent"
                      disabled={disabled || (!selected && value.associated_faction_ids.length >= 50)}
                    />
                    <span className="min-w-0 truncate">
                      {formatStableReferenceLabel(faction.name, faction.faction_id)}
                      {unavailable ? ` · ${t("references.unavailable")}` : ""}
                    </span>
                  </label>
                );
              })}
              {missingFactionIds.map((id) => (
                <label key={id} className="flex min-h-11 items-center gap-3 border-b border-border/70 py-2 text-sm last:border-b-0">
                  <input name="associated_faction_ids" type="checkbox" checked onChange={() => update("associated_faction_ids", value.associated_faction_ids.filter((item) => item !== id))} className="size-4 shrink-0 accent-accent" disabled={disabled} />
                  <span className="min-w-0 truncate">{id} · {t("references.unavailable")}</span>
                </label>
              ))}
              {visibleFactions.length === 0 && missingFactionIds.length === 0 && <p className="py-4 text-sm text-muted">{t("references.emptyFactions")}</p>}
            </div>
            {fieldErrors.associated_faction_ids?.[0] && <p id={`${errorIdPrefix}-factions-error`} className="mt-2 text-xs text-red-600 dark:text-red-300">{fieldErrors.associated_faction_ids[0]}</p>}
          </fieldset>
        </div>
      </section>}

      {(!section || section === "story") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.story")}</h3>}
        <LocationField className={section ? undefined : "mt-4"} label={t("fields.storyFunction")} error={fieldErrors.story_function?.[0]} errorId={`${errorIdPrefix}-story-error`}>
          <textarea name="story_function" value={value.story_function} onChange={(event) => update("story_function", event.target.value)} maxLength={1000} className={TEXTAREA_CLASS} aria-invalid={Boolean(fieldErrors.story_function) || undefined} aria-describedby={fieldErrors.story_function ? `${errorIdPrefix}-story-error` : undefined} disabled={disabled} />
        </LocationField>
      </section>}
    </div>
  );
}

function LocationField({
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
