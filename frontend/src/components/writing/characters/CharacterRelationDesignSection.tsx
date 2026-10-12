"use client";

import { useContext, useEffect, useId, useRef, useState } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import { RelationEditorErrorSummary, RelationFieldShell, RelationIntensityField } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPut, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterRelationFields, CharacterRelationResponseV1 } from "@/types/character";
import { CHARACTER_RELATION_TYPES } from "./forms/CharacterRelationEditor";

export type CharacterRelationDesignValues = Pick<CharacterRelationFields,
  "relation_type" | "core_conflict" | "hidden_tension" | "possible_change" | "story_value" | "intensity"
>;

const TEXT_FIELDS = [
  ["core_conflict", "coreConflict"], ["hidden_tension", "hiddenTension"],
  ["possible_change", "possibleChange"], ["story_value", "storyValue"],
] as const;
const INPUT = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";

/**
 * 显示新建关系和已有关系共用的六个设计字段。
 * Args: value 当前设计；onChange 更新设计；disabled 禁用输入；fieldErrors 字段错误。
 * Returns: 不含端点和事实值的设计表单。
 */
export function CharacterRelationDesignFields({ value, onChange, disabled = false, fieldErrors = {} }: {
  value: CharacterRelationDesignValues;
  onChange: (value: CharacterRelationDesignValues) => void;
  disabled?: boolean;
  fieldErrors?: ApiFieldErrors;
}) {
  const t = useTranslations("writing.characters");
  const id = useId();
  return <div className="detail-fields grid min-w-0 gap-5">
    <RelationFieldShell label={t("fields.relationType")} error={fieldErrors.relation_type?.[0]} errorId={`${id}-relation_type`}>
      <select name="relation_type" value={value.relation_type} disabled={disabled} className={INPUT}
        aria-invalid={Boolean(fieldErrors.relation_type) || undefined} aria-describedby={fieldErrors.relation_type ? `${id}-relation_type` : undefined}
        onChange={(event) => onChange({ ...value, relation_type: event.target.value as CharacterRelationFields["relation_type"] })}>
        {CHARACTER_RELATION_TYPES.map((type) => <option key={type} value={type}>{t(`options.relationType.${type}`)}</option>)}
      </select>
    </RelationFieldShell>
    <RelationIntensityField label={t("fields.intensity")} value={value.intensity} onChange={(intensity) => onChange({ ...value, intensity })}
      disabled={disabled} error={fieldErrors.intensity?.[0]} errorId={`${id}-intensity`} inputClassName={INPUT} />
    {TEXT_FIELDS.map(([field, label]) => <RelationFieldShell key={field} label={t(`fields.${label}`)} className="col-span-full"
      error={fieldErrors[field]?.[0]} errorId={`${id}-${field}`}>
      <textarea name={field} value={value[field]} required maxLength={2000} rows={4} disabled={disabled}
        className={`${INPUT} min-h-28 resize-y leading-6`} aria-invalid={Boolean(fieldErrors[field]) || undefined}
        aria-describedby={fieldErrors[field] ? `${id}-${field}` : undefined} onChange={(event) => onChange({ ...value, [field]: event.target.value })} />
    </RelationFieldShell>)}
  </div>;
}

interface DesignSession {
  draft?: { value: CharacterRelationDesignValues; version: number };
  saved?: CharacterRelationResponseV1;
  needsReadback?: boolean;
  busy?: boolean;
  error?: Error;
}

/**
 * 在关系详情中独立阅读和保存设计字段。
 * Args: relation 正式关系；number 章节编号；readOnly 只读状态；onChanged 保存或读回通知；onBusy 当前目标忙碌通知。
 * Returns: 保留开始版本和失败草稿、端点只读的资料节。
 */
export default function CharacterRelationDesignSection({ relation, number = "01", readOnly = false, onChanged, onBusy }: {
  relation: CharacterRelationResponseV1;
  number?: string;
  readOnly?: boolean;
  onChanged?: (relation: CharacterRelationResponseV1) => void;
  onBusy?: (busy: boolean) => void;
}) {
  const t = useTranslations("writing.characters");
  const active = useContext(RetainedViewActive);
  const targetKey = `${relation.novel_id}:${relation.relation_id}`;
  const [sessions, setSessions] = useState<Record<string, DesignSession>>({});
  const session = sessions[targetKey];
  const draft = session?.draft;
  const editBlocked = readOnly || relation.is_deleted;
  const current = session?.saved && session.saved.version >= relation.version ? session.saved : relation;
  const fieldErrors = session?.error instanceof ApiRequestError ? session.error.fieldErrors : {};
  const areaRef = useRef<HTMLDivElement>(null);
  const pending = useRef(new Set<string>());
  const alive = useRef(true);
  const visibleTarget = useRef(active ? targetKey : null);
  const visibleVersion = useRef(current.version);
  useEffect(() => { visibleTarget.current = active ? targetKey : null; }, [active, targetKey]);
  useEffect(() => { visibleVersion.current = current.version; }, [current.version]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { onBusy?.(Boolean(session?.busy)); return () => onBusy?.(false); }, [onBusy, session?.busy]);
  useEffect(() => {
    if (!active || !session?.error) return;
    const errors = session.error instanceof ApiRequestError ? session.error.fieldErrors : {};
    const field = Object.keys(errors)[0]?.split(".").at(-1);
    const target = (field ? areaRef.current?.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`) : null)
      ?? areaRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]");
    target?.focus({ preventScroll: true });
    target?.scrollIntoView?.({ block: "nearest" });
  }, [active, session?.error]);

  const save = async () => {
    if (pending.current.has(targetKey) || (!draft && !session?.needsReadback)) return;
    if (draft && editBlocked) return;
    pending.current.add(targetKey);
    setSessions((previous) => ({ ...previous, [targetKey]: { ...previous[targetKey], busy: true, error: undefined } }));
    const path = `/api/character-relations/novel/${relation.novel_id}/${relation.relation_id}`;
    try {
      if (!session?.needsReadback && draft) {
        const saved = await apiPut<CharacterRelationResponseV1>(`${path}/design`, { ...draft.value, expected_version: draft.version });
        if (!alive.current) return;
        // 成功响应先留下；此后的失败只允许重读，不再提交设计修改。
        setSessions((previous) => ({ ...previous, [targetKey]: { saved, needsReadback: true, busy: true } }));
        if (visibleTarget.current === targetKey && saved.version >= visibleVersion.current) onChanged?.(saved);
      }
      const latest = await apiGet<CharacterRelationResponseV1>(path);
      if (!alive.current) return;
      setSessions((previous) => ({ ...previous, [targetKey]: { saved: latest } }));
      if (visibleTarget.current === targetKey) {
        if (latest.version >= visibleVersion.current) onChanged?.(latest);
        requestAnimationFrame(() => { if (visibleTarget.current === targetKey) document.getElementById(`relation-design-edit-${targetKey}`)?.focus(); });
      }
    } catch (error) {
      if (alive.current) setSessions((previous) => ({ ...previous, [targetKey]: {
        ...previous[targetKey], error: error instanceof Error ? error : new Error(t("relationDesign.saveFailed")),
      } }));
    } finally {
      pending.current.delete(targetKey);
      if (alive.current) setSessions((previous) => ({ ...previous, [targetKey]: { ...previous[targetKey], busy: false } }));
    }
  };

  return <DocumentSection number={number} title={t("relationDesign.title")} actions={draft ? <>
    <SectionActionButton action="save" label={session?.busy ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" type="submit" form={`relation-design-${targetKey}`} isDisabled={session?.busy || editBlocked} />
    <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" isDisabled={session?.busy} onPress={() => {
      setSessions((previous) => ({ ...previous, [targetKey]: { saved: previous[targetKey]?.saved } }));
      requestAnimationFrame(() => { if (visibleTarget.current === targetKey) document.getElementById(`relation-design-edit-${targetKey}`)?.focus(); });
    }} />
  </> : !readOnly && !relation.is_deleted && !session?.needsReadback ? <SectionEditButton
    id={`relation-design-edit-${targetKey}`} label={t("relationDesign.edit")} isDisabled={session?.busy} onPress={() => {
      const { relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity } = current;
      // 后台刷新只更新阅读内容，草稿版本在开始编辑时固定。
      setSessions((previous) => ({ ...previous, [targetKey]: { ...previous[targetKey], error: undefined,
        draft: { value: { relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity }, version: current.version },
      } }));
      requestAnimationFrame(() => { if (visibleTarget.current === targetKey) areaRef.current?.querySelector<HTMLElement>("select")?.focus(); });
    }} /> : undefined}>
    <div ref={areaRef} className="min-w-0 space-y-4" aria-busy={session?.busy || undefined}>
      <dl className="detail-fields grid min-w-0 gap-4">
        <ReadOnlyField label={t("fields.sourceCharacter")} value={relation.source_character_name ?? relation.source_character_id} />
        <ReadOnlyField label={t("fields.targetCharacter")} value={relation.target_character_name ?? relation.target_character_id} />
      </dl>
      {draft && relation.is_deleted && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">{t("relationDesign.recycled")}</p>}
      {session?.error && <RelationEditorErrorSummary message={session.needsReadback ? t("relationDesign.savedReadbackFailed") : session.error.message}
        fieldErrors={session.needsReadback ? {} : fieldErrors} />}
      {session?.needsReadback && <Button size="sm" variant="outline" isDisabled={session.busy} onPress={() => void save()}>
        {t("relationDesign.retryRead")}
      </Button>}
      {draft ? <form id={`relation-design-${targetKey}`} onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <CharacterRelationDesignFields value={draft.value} disabled={session?.busy || editBlocked} fieldErrors={fieldErrors}
          onChange={(value) => setSessions((previous) => ({ ...previous, [targetKey]: { ...previous[targetKey], draft: { ...draft, value } } }))} />
      </form> : <dl className="detail-fields grid min-w-0 gap-4">
        <ReadOnlyField label={t("fields.relationType")} value={t(`options.relationType.${current.relation_type}`)} />
        <ReadOnlyField label={t("fields.intensity")} value={`${current.intensity}/5`} />
        {TEXT_FIELDS.map(([field, label]) => <ReadOnlyField key={field} wide label={t(`fields.${label}`)} value={current[field]} />)}
      </dl>}
    </div>
  </DocumentSection>;
}
