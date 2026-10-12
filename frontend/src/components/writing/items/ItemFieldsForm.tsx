"use client";

import { useTranslations } from "next-intl";
import { type ReactNode } from "react";

import TagInput from "@/components/shared/TagInput";
import type { ApiFieldErrors } from "@/lib/api";
import { formatStableReferenceLabel } from "@/types/contracts";
import type {
  ItemFieldsV1,
  ItemLifecycleStatus,
} from "@/types/item";

const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS = `${INPUT_CLASS} min-h-28 resize-y leading-6`;
const ITEM_STATUSES: readonly ItemLifecycleStatus[] = ["available", "held", "lost", "destroyed", "consumed"];
const TERMINAL_ITEM_STATUSES = new Set<ItemLifecycleStatus>(["destroyed", "consumed"]);

interface CharacterOption {
  character_id: string;
  name: string;
  status: "active" | "inactive";
  is_deleted: boolean;
}

interface FactionOption {
  faction_id: string;
  name: string;
  active_status: "active" | "inactive";
  is_deleted: boolean;
}

interface LocationOption {
  location_id: string;
  name: string;
  status: "active" | "inactive";
  is_deleted: boolean;
}

export type ItemEditorSection = "identity" | "profile" | "capabilities" | "references" | "story";

interface ItemFieldsFormProps {
  section?: ItemEditorSection;
  value: ItemFieldsV1;
  characters: readonly CharacterOption[];
  factions: readonly FactionOption[];
  locations: readonly LocationOption[];
  disabled?: boolean;
  statusEditable?: boolean;
  allowedStatuses?: readonly ItemLifecycleStatus[];
  referenceErrors?: {
    character?: string;
    faction?: string;
    location?: string;
  };
  fieldErrors?: ApiFieldErrors;
  errorIdPrefix: string;
  onChange: (value: ItemFieldsV1) => void;
}

/**
 * 显示正式物品与 AI 候选共用的字段。
 *
 * Args:
 *   section: 只显示当前编辑章节；省略时显示完整创建表单。
 *   value: 当前物品字段。
 *   characters: 可以作为持有人的角色。
 *   factions: 可以控制物品的势力。
 *   locations: 可以放置物品的地点。
 *   disabled: 是否禁用编辑。
 *   statusEditable: 是否允许直接选择状态。
 *   allowedStatuses: 当前流程允许选择的状态。
 *   referenceErrors: 角色、势力和地点列表的加载错误。
 *   fieldErrors: 按字段返回的保存错误。
 *   errorIdPrefix: 当前表单错误元素的唯一前缀。
 *   onChange: 字段变化回调。
 *
 * Returns:
 *   物品字段表单。
 */
export default function ItemFieldsForm({
  section,
  value,
  characters,
  factions,
  locations,
  disabled = false,
  statusEditable = true,
  allowedStatuses = ITEM_STATUSES,
  referenceErrors = {},
  fieldErrors = {},
  errorIdPrefix,
  onChange,
}: ItemFieldsFormProps) {
  const t = useTranslations("writing.items");
  const characterNames = new Map(characters.map((item) => [item.character_id, item.name]));
  const factionNames = new Map(factions.map((item) => [item.faction_id, item.name]));
  const locationNames = new Map(locations.map((item) => [item.location_id, item.name]));
  const activeCharacters = characters.filter((item) => !item.is_deleted && item.status === "active");
  const activeFactions = factions.filter((item) => !item.is_deleted && item.active_status === "active");
  const activeLocations = locations.filter((item) => !item.is_deleted && item.status === "active");
  const referencesLocked = TERMINAL_ITEM_STATUSES.has(value.lifecycle_status);

  const update = (fields: Partial<ItemFieldsV1>) => onChange({ ...value, ...fields });

  return (
    <div className="space-y-4">
      {(!section || section === "identity") && <section>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.identity")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <Field label={t("fields.name")} required error={fieldErrors.name?.[0]} errorId={`${errorIdPrefix}-name-error`}>
            <input name="name" required aria-required="true" aria-label={t("fields.name")} value={value.name} onChange={(event) => update({ name: event.target.value })} maxLength={80} className={INPUT_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? `${errorIdPrefix}-name-error` : undefined} />
          </Field>
          <Field label={t("fields.type")} required error={fieldErrors.item_type?.[0]} errorId={`${errorIdPrefix}-type-error`}>
            <input name="item_type" required aria-required="true" aria-label={t("fields.type")} value={value.item_type} onChange={(event) => update({ item_type: event.target.value })} maxLength={40} className={INPUT_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.item_type)} aria-describedby={fieldErrors.item_type ? `${errorIdPrefix}-type-error` : undefined} />
          </Field>
          <TagInput name="aliases" label={t("fields.aliases")} values={value.aliases} onChange={(aliases) => update({ aliases })} getRemoveAriaLabel={(entry) => t("tag.removeAlias", { value: entry })} placeholder={t("placeholders.aliases")} limitReachedText={t("tag.aliasLimit", { count: 10 })} maxItems={10} disabled={disabled} error={fieldErrors.aliases?.[0]} className="col-span-full" />
          <Field className="col-span-full" label={t("fields.description")} required error={fieldErrors.description?.[0]} errorId={`${errorIdPrefix}-description-error`}>
            <textarea name="description" required aria-required="true" aria-label={t("fields.description")} value={value.description} onChange={(event) => update({ description: event.target.value })} maxLength={2000} className={TEXTAREA_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.description)} aria-describedby={fieldErrors.description ? `${errorIdPrefix}-description-error` : undefined} />
          </Field>
          {statusEditable ? (
            <Field label={t("fields.status")} error={fieldErrors.lifecycle_status?.[0]} errorId={`${errorIdPrefix}-status-error`}>
              <select
                name="lifecycle_status"
                aria-label={t("fields.status")}
                value={value.lifecycle_status}
                onChange={(event) => {
                  const lifecycleStatus = event.target.value as ItemLifecycleStatus;
                  update({
                    lifecycle_status: lifecycleStatus,
                    ...(TERMINAL_ITEM_STATUSES.has(lifecycleStatus) ? {
                      owner_character_id: null,
                      controlling_faction_id: null,
                      current_location_id: null,
                    } : {}),
                  });
                }}
                className={INPUT_CLASS}
                disabled={disabled}
                aria-invalid={Boolean(fieldErrors.lifecycle_status)}
                aria-describedby={fieldErrors.lifecycle_status ? `${errorIdPrefix}-status-error` : undefined}
              >
                {allowedStatuses.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
              </select>
            </Field>
          ) : !section && (
            <div className="border-y border-border py-3 text-sm leading-6 text-muted col-span-full">
              {t("editor.statusManaged", { status: t(`status.${value.lifecycle_status}`) })}
            </div>
          )}
        </div>
      </section>}

      {(!section || section === "profile") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.profile")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <Field label={t("fields.appearance")} error={fieldErrors.appearance?.[0]} errorId={`${errorIdPrefix}-appearance-error`}>
            <textarea name="appearance" aria-label={t("fields.appearance")} value={value.appearance} onChange={(event) => update({ appearance: event.target.value })} maxLength={1000} className={TEXTAREA_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.appearance)} aria-describedby={fieldErrors.appearance ? `${errorIdPrefix}-appearance-error` : undefined} />
          </Field>
          <Field label={t("fields.origin")} error={fieldErrors.origin?.[0]} errorId={`${errorIdPrefix}-origin-error`}>
            <textarea name="origin" aria-label={t("fields.origin")} value={value.origin} onChange={(event) => update({ origin: event.target.value })} maxLength={1000} className={TEXTAREA_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.origin)} aria-describedby={fieldErrors.origin ? `${errorIdPrefix}-origin-error` : undefined} />
          </Field>
        </div>
      </section>}

      {(!section || section === "capabilities") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.capabilities")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <TagInput name="abilities" className="grid-cols-1" label={t("fields.abilities")} values={value.abilities} onChange={(abilities) => update({ abilities })} getRemoveAriaLabel={(entry) => t("tag.removeAbility", { value: entry })} placeholder={t("placeholders.abilities")} limitReachedText={t("tag.entryLimit", { count: 20 })} maxItems={20} splitOnPunctuation={false} wrapTags disabled={disabled} error={fieldErrors.abilities?.[0]} />
          <TagInput name="limitations" className="grid-cols-1" label={t("fields.limitations")} values={value.limitations} onChange={(limitations) => update({ limitations })} getRemoveAriaLabel={(entry) => t("tag.removeLimitation", { value: entry })} placeholder={t("placeholders.limitations")} limitReachedText={t("tag.entryLimit", { count: 20 })} maxItems={20} splitOnPunctuation={false} wrapTags disabled={disabled} error={fieldErrors.limitations?.[0]} />
          <TagInput name="costs" className="grid-cols-1" label={t("fields.costs")} values={value.costs} onChange={(costs) => update({ costs })} getRemoveAriaLabel={(entry) => t("tag.removeCost", { value: entry })} placeholder={t("placeholders.costs")} limitReachedText={t("tag.entryLimit", { count: 20 })} maxItems={20} splitOnPunctuation={false} wrapTags disabled={disabled} error={fieldErrors.costs?.[0]} />
        </div>
      </section>}

      {(!section || section === "references") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.references")}</h3>}
        {referencesLocked && (
          <div className="mt-4 border-y border-border bg-surface-secondary/45 px-4 py-3 text-sm leading-6 text-muted">
            {t("editor.terminalReferencesLocked")}
          </div>
        )}
        <div className={`${section ? "" : "mt-4 "}grid gap-5 detail-fields`}>
          <ReferenceSelectField label={t("fields.owner")} error={referenceErrors.character || fieldErrors.owner_character_id?.[0]} errorId={`${errorIdPrefix}-owner-error`}>
            <select name="owner_character_id" aria-label={t("fields.owner")} value={value.owner_character_id ?? ""} onChange={(event) => update({ owner_character_id: event.target.value || null })} className={INPUT_CLASS} disabled={disabled || Boolean(referenceErrors.character) || referencesLocked} aria-invalid={Boolean(fieldErrors.owner_character_id)} aria-describedby={(referenceErrors.character || fieldErrors.owner_character_id) ? `${errorIdPrefix}-owner-error` : undefined}>
              <option value="">{t("references.none")}</option>
              {value.owner_character_id && !characterNames.has(value.owner_character_id) && <option value={value.owner_character_id}>{value.owner_character_id} · {t("references.unavailable")}</option>}
              {activeCharacters.map((character) => <option key={character.character_id} value={character.character_id}>{formatStableReferenceLabel(character.name, character.character_id)}</option>)}
            </select>
          </ReferenceSelectField>
          <ReferenceSelectField label={t("fields.faction")} error={referenceErrors.faction || fieldErrors.controlling_faction_id?.[0]} errorId={`${errorIdPrefix}-faction-error`}>
            <select name="controlling_faction_id" aria-label={t("fields.faction")} value={value.controlling_faction_id ?? ""} onChange={(event) => update({ controlling_faction_id: event.target.value || null })} className={INPUT_CLASS} disabled={disabled || Boolean(referenceErrors.faction) || referencesLocked} aria-invalid={Boolean(fieldErrors.controlling_faction_id)} aria-describedby={(referenceErrors.faction || fieldErrors.controlling_faction_id) ? `${errorIdPrefix}-faction-error` : undefined}>
              <option value="">{t("references.none")}</option>
              {value.controlling_faction_id && !factionNames.has(value.controlling_faction_id) && <option value={value.controlling_faction_id}>{value.controlling_faction_id} · {t("references.unavailable")}</option>}
              {activeFactions.map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{formatStableReferenceLabel(faction.name, faction.faction_id)}</option>)}
            </select>
          </ReferenceSelectField>
          <ReferenceSelectField label={t("fields.location")} error={referenceErrors.location || fieldErrors.current_location_id?.[0]} errorId={`${errorIdPrefix}-location-error`}>
            <select name="current_location_id" aria-label={t("fields.location")} value={value.current_location_id ?? ""} onChange={(event) => update({ current_location_id: event.target.value || null })} className={INPUT_CLASS} disabled={disabled || Boolean(referenceErrors.location) || referencesLocked} aria-invalid={Boolean(fieldErrors.current_location_id)} aria-describedby={(referenceErrors.location || fieldErrors.current_location_id) ? `${errorIdPrefix}-location-error` : undefined}>
              <option value="">{t("references.none")}</option>
              {value.current_location_id && !locationNames.has(value.current_location_id) && <option value={value.current_location_id}>{value.current_location_id} · {t("references.unavailable")}</option>}
              {activeLocations.map((location) => <option key={location.location_id} value={location.location_id}>{formatStableReferenceLabel(location.name, location.location_id)}</option>)}
            </select>
          </ReferenceSelectField>
        </div>
      </section>}

      {(!section || section === "story") && <section className={section ? undefined : "border-t border-border pt-4"}>
        {!section && <h3 className="text-sm font-semibold text-foreground">{t("editor.sections.story")}</h3>}
        <div className={`${section ? "" : "mt-4 "}grid gap-5`}>
          <Field label={t("fields.storyFunction")} error={fieldErrors.story_function?.[0]} errorId={`${errorIdPrefix}-story-error`}>
            <textarea name="story_function" aria-label={t("fields.storyFunction")} value={value.story_function} onChange={(event) => update({ story_function: event.target.value })} maxLength={1000} className={TEXTAREA_CLASS} disabled={disabled} aria-invalid={Boolean(fieldErrors.story_function)} aria-describedby={fieldErrors.story_function ? `${errorIdPrefix}-story-error` : undefined} />
          </Field>
          <TagInput name="tags" label={t("fields.tags")} values={value.tags} onChange={(tags) => update({ tags })} getRemoveAriaLabel={(entry) => t("tag.removeTag", { value: entry })} placeholder={t("placeholders.tags")} limitReachedText={t("tag.tagLimit", { count: 20 })} maxItems={20} disabled={disabled} error={fieldErrors.tags?.[0]} />
        </div>
      </section>}
    </div>
  );
}

function Field({ label, children, className = "", error, errorId, required = false }: { label: string; children: ReactNode; className?: string; error?: string; errorId?: string; required?: boolean }) {
  return <label className={`grid min-w-0 gap-1.5 text-xs font-medium text-muted ${className}`}><span>{label}{required && <span aria-hidden="true" className="ml-1 text-danger">*</span>}</span>{children}{error && <span id={errorId} className="text-xs font-medium text-danger">{error}</span>}</label>;
}

function ReferenceSelectField({ label, children, error, errorId }: { label: string; children: ReactNode; error?: string; errorId: string }) {
  return <label className="grid min-w-0 content-start gap-1.5 text-xs font-medium text-muted"><span>{label}</span>{children}{error && <span id={errorId} className="text-xs font-normal leading-5 text-red-600 dark:text-red-300" role="alert">{error}</span>}</label>;
}
