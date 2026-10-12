"use client";

import type { useTranslations } from "next-intl";
import type { ApiFieldErrors } from "@/lib/api";
import {
  RelationFieldShell,
  RelationIntensityField,
} from "@/components/shared/RelationEditorPrimitives";
import type {
  CharacterRelationCandidateV1,
  CharacterRelationFields,
  CharacterResponseV1,
} from "@/types/character";

/** 全书级角色关系编辑器支持的稳定关系类型。 */
export const CHARACTER_RELATION_TYPES: readonly CharacterRelationFields["relation_type"][] = [
  "friend",
  "romantic",
  "ally",
  "rival",
  "enemy",
  "parent_of",
  "mentor_of",
  "superior_of",
  "protector_of",
  "debtor_to",
];

/** 全书级角色关系编辑器的公开属性。 */
export interface CharacterRelationEditorProps {
  inline?: boolean;
  value: CharacterRelationFields;
  characters: CharacterResponseV1[];
  relationRef?: CharacterRelationCandidateV1["relation_ref"];
  disabled?: boolean;
  endpointsReadOnly?: boolean;
  fieldErrors?: ApiFieldErrors;
  onChange: (value: CharacterRelationFields) => void;
  t: ReturnType<typeof useTranslations>;
}

const INPUT_CLASS_NAME =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";

const TEXTAREA_CLASS_NAME = `${INPUT_CLASS_NAME} min-h-28 resize-y leading-6`;

/**
 * 渲染可复用的全书级角色关系表单。
 *
 * Args:
 *   props: 关系字段、可选候选引用、可选角色端点、禁用状态、更新回调与翻译函数。
 *
 * Returns:
 *   覆盖人工创建和 AI 关系候选白名单字段的响应式表单节点。
 */
export default function CharacterRelationEditor({
  value,
  inline = false,
  characters,
  relationRef,
  disabled = false,
  endpointsReadOnly = false,
  fieldErrors = {},
  onChange,
  t,
}: CharacterRelationEditorProps) {
  const errorFor = (field: keyof CharacterRelationFields) => fieldErrors[field]?.[0];
  /**
   * 更新一个关系业务字段并保留其余白名单字段。
   *
   * Args:
   *   field: 待更新的关系字段名。
   *   nextValue: 与字段类型一致的新值。
   *
   * Returns:
   *   无；通过 onChange 向父组件提交新关系对象。
   */
  const updateField = <K extends keyof CharacterRelationFields>(
    field: K,
    nextValue: CharacterRelationFields[K],
  ) => {
    // 编辑器只派生关系白名单字段，不注入正式 ID 或版本字段。
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <div className="space-y-6" aria-disabled={disabled || undefined}>
      <RelationSection title={inline ? undefined : t("sections.relationCore")}>
        <div className={inline ? "grid gap-5 detail-fields" : "grid gap-5 md:grid-cols-2"}>
          {relationRef && (
            <ReadOnlyField
              label={t("fields.relationRef")}
              value={relationRef}
              className="col-span-full"
            />
          )}

          <CharacterSelectField
            field="source_character_id"
            label={t("fields.sourceCharacter")}
            value={value.source_character_id}
            characters={characters}
            forbiddenCharacterId={value.target_character_id}
            onChange={(nextValue) => updateField("source_character_id", nextValue)}
            disabled={disabled}
            readOnly={endpointsReadOnly}
            error={errorFor("source_character_id")}
            required
          />

          <CharacterSelectField
            field="target_character_id"
            label={t("fields.targetCharacter")}
            value={value.target_character_id}
            characters={characters}
            forbiddenCharacterId={value.source_character_id}
            onChange={(nextValue) => updateField("target_character_id", nextValue)}
            disabled={disabled}
            readOnly={endpointsReadOnly}
            error={errorFor("target_character_id")}
            required
          />

          <SelectField
            field="relation_type"
            label={t("fields.relationType")}
            value={value.relation_type}
            onChange={(nextValue) => updateField("relation_type", nextValue)}
            disabled={disabled}
            error={errorFor("relation_type")}
          >
            {CHARACTER_RELATION_TYPES.map((relationType) => (
              <option key={relationType} value={relationType}>
                {t(`options.relationType.${relationType}`)}
              </option>
            ))}
          </SelectField>

          <RelationIntensityField
            label={t("fields.intensity")}
            value={value.intensity}
            onChange={(nextValue) => updateField("intensity", nextValue)}
            disabled={disabled}
            error={errorFor("intensity")}
            inputClassName={INPUT_CLASS_NAME}
          />

          <TextAreaField
            field="current_state"
            label={t("fields.currentState")}
            value={value.current_state}
            onChange={(nextValue) => updateField("current_state", nextValue)}
            maxLength={2000}
            disabled={disabled}
            required
            error={errorFor("current_state")}
            className="col-span-full"
          />
        </div>
      </RelationSection>

      <RelationSection title={inline ? undefined : t("sections.relationStory")}>
        <div className={inline ? "grid gap-5 detail-fields" : "grid gap-5 md:grid-cols-2"}>
          <TextAreaField
            field="core_conflict"
            label={t("fields.coreConflict")}
            value={value.core_conflict}
            onChange={(nextValue) => updateField("core_conflict", nextValue)}
            maxLength={2000}
            disabled={disabled}
            required
            error={errorFor("core_conflict")}
          />

          <TextAreaField
            field="hidden_tension"
            label={t("fields.hiddenTension")}
            value={value.hidden_tension}
            onChange={(nextValue) => updateField("hidden_tension", nextValue)}
            maxLength={2000}
            disabled={disabled}
            required
            error={errorFor("hidden_tension")}
          />

          <TextAreaField
            field="possible_change"
            label={t("fields.possibleChange")}
            value={value.possible_change}
            onChange={(nextValue) => updateField("possible_change", nextValue)}
            maxLength={2000}
            disabled={disabled}
            required
            error={errorFor("possible_change")}
          />

          <TextAreaField
            field="story_value"
            label={t("fields.storyValue")}
            value={value.story_value}
            onChange={(nextValue) => updateField("story_value", nextValue)}
            maxLength={2000}
            disabled={disabled}
            required
            error={errorFor("story_value")}
          />
        </div>
      </RelationSection>
    </div>
  );
}

interface RelationSectionProps {
  title?: string;
  children: React.ReactNode;
}

/**
 * 渲染关系表单的语义分组。
 *
 * Args:
 *   props: 分组标题与字段节点。
 *
 * Returns:
 *   带标题和统一边框的章节节点。
 */
function RelationSection({ title, children }: RelationSectionProps) {
  return (
    <section className={title ? "border-b border-border pb-7 last:border-b-0 last:pb-0" : undefined}>
      {title && <h3 className="mb-5 text-base font-semibold text-foreground">{title}</h3>}
      {children}
    </section>
  );
}

interface CharacterSelectFieldProps {
  field: "source_character_id" | "target_character_id";
  label: string;
  value: string;
  characters: CharacterResponseV1[];
  forbiddenCharacterId?: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  required?: boolean;
  readOnly?: boolean;
  error?: string;
}

/**
 * 渲染可搜索角色端点选择器并排除另一端已选角色。
 *
 * Args:
 *   props: 字段标题、当前角色 ID、候选角色、禁止选择的另一端 ID 与交互属性。
 *
 * Returns:
 *   始终展示“名称 · ID”并以稳定 character_id 作为表单值的原生选择器。
 */
function CharacterSelectField({
  field,
  label,
  value,
  characters,
  forbiddenCharacterId,
  onChange,
  disabled,
  required,
  readOnly,
  error,
}: CharacterSelectFieldProps) {
  const errorId = `relation-${field}-error`;
  if (readOnly) {
    const selected = characters.find((character) => character.character_id === value);
    return (
      <RelationFieldShell label={label} error={error} errorId={errorId}>
        <input name={field} value={selected ? `${selected.name} · ${selected.character_id}` : value} readOnly aria-readonly="true" aria-invalid={Boolean(error) || undefined} aria-describedby={error ? errorId : undefined} className={`${INPUT_CLASS_NAME} bg-surface-secondary/55`} />
      </RelationFieldShell>
    );
  }
  return (
    <RelationFieldShell label={label} error={error} errorId={errorId}>
      <select
        name={field}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        required={required}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? errorId : undefined}
        className={INPUT_CLASS_NAME}
      >
        <option value="" disabled>{label}</option>
        {characters.map((character) => (
          <option
            key={character.character_id}
            value={character.character_id}
            disabled={character.character_id === forbiddenCharacterId}
          >
            {character.name} · {character.character_id}
          </option>
        ))}
      </select>
    </RelationFieldShell>
  );
}

interface SelectFieldProps<TValue extends string> {
  field: keyof CharacterRelationFields;
  label: string;
  value: TValue;
  onChange: (value: TValue) => void;
  disabled?: boolean;
  children: React.ReactNode;
  error?: string;
}

/**
 * 渲染保留字符串枚举类型的关系选择器。
 *
 * Args:
 *   props: 字段标题、枚举值、更新回调、禁用状态与选项节点。
 *
 * Returns:
 *   统一视觉样式的原生选择器。
 */
function SelectField<TValue extends string>({
  field,
  label,
  value,
  onChange,
  disabled,
  children,
  error,
}: SelectFieldProps<TValue>) {
  const errorId = `relation-${String(field)}-error`;
  return (
    <RelationFieldShell label={label} error={error} errorId={errorId}>
      <select
        name={field}
        value={value}
        onChange={(event) => onChange(event.target.value as TValue)}
        disabled={disabled}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? errorId : undefined}
        className={INPUT_CLASS_NAME}
      >
        {children}
      </select>
    </RelationFieldShell>
  );
}

interface TextAreaFieldProps {
  field: keyof CharacterRelationFields;
  label: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  error?: string;
}

/**
 * 渲染角色关系的多行叙述字段。
 *
 * Args:
 *   props: 字段标题、当前值、更新回调、长度限制、禁用状态与布局类名。
 *
 * Returns:
 *   可纵向调整高度的文本区节点。
 */
function TextAreaField({
  field,
  label,
  value,
  onChange,
  maxLength,
  disabled,
  required,
  className,
  error,
}: TextAreaFieldProps) {
  const errorId = `relation-${field}-error`;
  return (
    <RelationFieldShell label={label} className={`col-span-full ${className ?? ""}`} error={error} errorId={errorId}>
      <textarea
        name={field}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={maxLength}
        disabled={disabled}
        required={required}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? errorId : undefined}
        rows={4}
        className={TEXTAREA_CLASS_NAME}
      />
    </RelationFieldShell>
  );
}

interface ReadOnlyFieldProps {
  label: string;
  value: string;
  className?: string;
}

/**
 * 渲染 AI 关系候选的只读局部引用。
 *
 * Args:
 *   props: 字段标题、局部引用值与可选布局类名。
 *
 * Returns:
 *   不允许改写但可复制的候选引用字段。
 */
function ReadOnlyField({ label, value, className }: ReadOnlyFieldProps) {
  return (
    <RelationFieldShell label={label} className={className}>
      <input
        type="text"
        value={value}
        readOnly
        aria-readonly="true"
        className={`${INPUT_CLASS_NAME} cursor-default bg-surface-secondary/65 font-mono text-xs`}
      />
    </RelationFieldShell>
  );
}
