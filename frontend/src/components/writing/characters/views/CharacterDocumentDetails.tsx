"use client";
import { useAssistantResource } from "@/components/writing/assistant/AssistantContext";

import { useEffect, useRef, useState } from "react";
import type { useTranslations } from "next-intl";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import TagList from "@/components/shared/TagList";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterFactField } from "@/types/characterFacts";
import type { CharacterProfileFields, CharacterResponseV1 } from "@/types/character";
import CharacterProfileForm, { CHARACTER_PROFILE_SECTIONS, type CharacterProfileSection } from "../forms/CharacterProfileForm";
import { CHARACTER_PROFILE_FACT_FIELDS } from "../characterFactFields";

type Translator = ReturnType<typeof useTranslations>;
export type ProfileSectionUpdate = Partial<CharacterProfileFields> & { expected_version: number };

interface ProfileDraft {
  section: CharacterProfileSection;
  fields: (keyof CharacterProfileFields)[];
  value: CharacterProfileFields;
  original: CharacterProfileFields;
  version: number;
  error: string;
  fieldErrors: ApiFieldErrors;
}

const PROFILE_LABELS: Record<keyof CharacterProfileFields, string> = {
  name: "name", aliases: "aliases", role_type: "roleType", importance_level: "importanceLevel",
  gender: "gender", age_group: "ageGroup", race: "race", identity: "identity",
  appearance: "appearance", personality: "personality", strengths: "strengths", weaknesses: "weaknesses", abilities: "abilities",
  core_desire: "coreDesire", core_fear: "coreFear", conflict_with_mainline: "conflictWithMainline", relationship_with_protagonist: "relationshipWithProtagonist",
  initial_state: "initialState", growth_direction: "growthDirection", story_function: "storyFunction", arc_seed: "arcSeed", tags: "tags",
};
const SHORT_PROFILE_FIELDS = new Set(["name", "role_type", "importance_level", "gender", "age_group", "race"]);
const DESIGN_FIELDS = Object.fromEntries(Object.entries(CHARACTER_PROFILE_SECTIONS).map(([section, fields]) => [section, fields.filter((field) => !CHARACTER_PROFILE_FACT_FIELDS.some((fact) => fact === field))])) as Record<CharacterProfileSection, (keyof CharacterProfileFields)[]>;

/**
 * 展示角色编号章节，并在当前节编辑、保存或取消。
 * Args: 角色、保存状态、只提交当前节的回调和翻译。
 * Returns: 保留各角色草稿与编辑开始版本的资料章节。
 */
export function CharacterProfileSections({ character, busy, onSave, t, claimedFactFields }: {
  character: CharacterResponseV1;
  claimedFactFields?: CharacterFactField[];
  busy: boolean;
  onSave: (character: CharacterResponseV1, payload: ProfileSectionUpdate) => Promise<void>;
  t: Translator;
}) {
  const [drafts, setDrafts] = useState<Record<string, ProfileDraft | undefined>>({});
  const draft = drafts[character.character_id];
  const legacyFields = claimedFactFields === undefined ? [] : CHARACTER_PROFILE_FACT_FIELDS.filter((field) => !claimedFactFields.includes(field));
  const sectionFields = (section: CharacterProfileSection) => CHARACTER_PROFILE_SECTIONS[section].filter((field) => DESIGN_FIELDS[section].includes(field) || legacyFields.some((fact) => fact === field));
  useAssistantResource({ resource_type: "character", id: character.character_id, name: character.name, version: character.version, draft: draft ? { text: JSON.stringify(Object.fromEntries(draft.fields.map((field) => [field, draft.value[field]]))), fields: draft.fields, version: draft.version } : undefined });
  const editorRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (!draft?.error) return;
    const field = Object.keys(draft.fieldErrors)[0]?.split(".").at(-1);
    const target = (field ? editorRef.current?.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`) : null)
      ?? editorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
    target?.focus({ preventScroll: true });
    target?.scrollIntoView?.({ block: "nearest" });
  }, [draft?.error, draft?.fieldErrors]);

  const finish = (id: string) => {
    setDrafts((current) => ({ ...current, [id]: undefined }));
    requestAnimationFrame(() => document.getElementById(`character-edit-${id}-${draft?.section}`)?.focus({ preventScroll: true }));
  };
  const save = async () => {
    if (!draft || busy) return;
    const id = character.character_id;
    const payload: ProfileSectionUpdate = { expected_version: draft.version };
    for (const field of draft.fields) if (JSON.stringify(draft.value[field]) !== JSON.stringify(draft.original[field])) Object.assign(payload, { [field]: draft.value[field] });
    const newlyManaged = Object.keys(payload).filter((field) => CHARACTER_PROFILE_FACT_FIELDS.includes(field as CharacterFactField) && !legacyFields.includes(field as CharacterFactField));
    if (newlyManaged.length) { setDrafts((current) => ({ ...current, [id]: { ...draft, error: t("editor.factManaged"), fieldErrors: Object.fromEntries(newlyManaged.map((field) => [field, [t("editor.factManaged")]])) } })); return; }
    if (Object.keys(payload).length === 1) { finish(id); return; }
    setDrafts((current) => ({ ...current, [id]: { ...draft, error: "", fieldErrors: {} } }));
    try {
      await onSave(character, payload);
      finish(id);
    } catch (error) {
      setDrafts((current) => ({ ...current, [id]: { ...draft,
        error: error instanceof Error ? error.message : String(error),
        fieldErrors: error instanceof ApiRequestError ? error.fieldErrors : {},
      } }));
    }
  };

  return <div className="mt-4 space-y-4">
    {(Object.keys(CHARACTER_PROFILE_SECTIONS) as CharacterProfileSection[]).filter((section) => sectionFields(section).length > 0 || draft?.section === section).map((section, index) => (
      <DocumentSection key={section} number={String(index + 1).padStart(2, "0")} title={t(`sections.${section}`)} actions={draft?.section === section ? <>
        <SectionActionButton action="save" label={busy ? t("actions.saving") : t("actions.save")} key="save" size="sm" variant="primary" type="button" onPress={() => void save()} isDisabled={busy} />
        <SectionActionButton action="cancel" label={t("actions.cancel")} key="cancel" type="button" size="sm" variant="ghost" isDisabled={busy} onPress={() => finish(character.character_id)} />
      </> : <SectionEditButton key="edit" type="button" id={`character-edit-${character.character_id}-${section}`} label={t("actions.edit")} isDisabled={busy || Boolean(draft)} onPress={() => {
        // 基准版本只在开始编辑时捕获，后台刷新不会覆盖旧草稿或提升其版本。
        setDrafts((current) => ({ ...current, [character.character_id]: { section, fields: [...sectionFields(section)], value: structuredClone(character), original: structuredClone(character), version: character.version, error: "", fieldErrors: {} } }));
        requestAnimationFrame(() => editorRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus());
      }} />}>
        {sectionFields(section).some((field) => legacyFields.includes(field as CharacterFactField)) && <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">{t("editor.unclaimedText")}</p>}
        {draft?.section === section ? <form id={`character-section-${character.character_id}-${section}`} ref={editorRef} onSubmit={(event) => { event.preventDefault(); void save(); }} className="space-y-4">
          {draft.error && <RelationEditorErrorSummary message={draft.error} fieldErrors={draft.fieldErrors} />}
          <CharacterProfileForm section={section} visibleFactFields={draft.fields.filter((field): field is CharacterFactField & keyof CharacterProfileFields => CHARACTER_PROFILE_FACT_FIELDS.includes(field as CharacterFactField))} value={draft.value} onChange={(value) => setDrafts((current) => ({ ...current, [character.character_id]: { ...draft, value } }))} disabled={busy} fieldErrors={draft.fieldErrors} t={t} />
        </form> : <dl className="detail-fields grid min-w-0 gap-4">
          {sectionFields(section).map((field) => {
            const value = character[field];
            const label = t(`fields.${PROFILE_LABELS[field]}`);
            return <ReadOnlyField key={field} label={label} wide={!Array.isArray(value) && !SHORT_PROFILE_FIELDS.has(field)} value={
              Array.isArray(value) ? value.length > 0 ? <TagList values={value} label={label} /> : "—"
                : field === "role_type" ? <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${value === "protagonist" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-surface-secondary text-muted"}`}>{t(`options.roleType.${value}`)}</span> : field === "importance_level" ? t(`options.importanceLevel.${value}`) : value || "—"
            } />;
          })}
        </dl>}
      </DocumentSection>
    ))}
  </div>;
}
