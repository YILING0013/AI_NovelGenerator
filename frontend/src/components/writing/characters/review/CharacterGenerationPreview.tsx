"use client";


import { Button } from "@heroui/react";
import { useRef } from "react";
import SectionEditButton from "@/components/shared/SectionEditButton";
import { useTranslations } from "next-intl";
import type { CandidateStateName } from "@/lib/aiCandidate";
import type { CoreFaction } from "@/types/novel";
import type {
  CharacterFactionBindingCandidateV1,
  CharacterFactionBindingResponseV1,
  CharacterFactionMembershipType,
  CharacterRelationCandidateV1,
  CharacterRelationsResultV1,
  CharacterResponseV1,
  CoreCharacterCandidateV1,
  CoreCharactersResultV1,
} from "@/types/character";
import CharacterProfileForm from "../forms/CharacterProfileForm";
import CharacterRelationEditor from "../forms/CharacterRelationEditor";

const INPUT_CLASS_NAME =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";

const TEXTAREA_CLASS_NAME = `${INPUT_CLASS_NAME} min-h-24 resize-y leading-6`;

const MEMBERSHIP_TYPES: readonly CharacterFactionMembershipType[] = [
  "primary",
  "secondary",
  "covert",
];

/** 本地角色生成预览公开属性。 */
export interface CharacterGenerationPreviewProps {
  corePreview: CoreCharactersResultV1 | null;
  relationPreview: CharacterRelationsResultV1 | null;
  selectedCoreCharacterRefs: string[];
  selectedRelationRefs: string[];
  relationCharacterIds: string[];
  selectedCoreIndex: number;
  selectedRelationIndex: number;
  characters: CharacterResponseV1[];
  factions: CoreFaction[];
  bindings: CharacterFactionBindingResponseV1[];
  status: CandidateStateName;
  error: string;
  hasRequiredProtagonist: boolean;
  onSelectCore: (index: number) => void;
  onSelectRelation: (index: number) => void;
  onToggleCore: (characterRef: string) => void;
  onCoreChange: (index: number, value: CoreCharacterCandidateV1) => void;
  onBindingChange: (
    characterRef: string,
    value: CharacterFactionBindingCandidateV1
  ) => void;
  onRelationChange: (index: number, value: CharacterRelationCandidateV1) => void;
  onToggleRelation: (relationRef: string) => void;
  onConfirm: () => void;
  onRevise?: () => void;
  onAdoptCore?: () => void;
  onAdoptRelation?: () => void;
  onExportRelation?: () => void;
  relationAdoptionBlocked?: boolean;
  relationRequestBusy?: boolean;
  relationEditingBlocked?: boolean;
  preparedRelationRefs?: string[];
  hasLegacyRelationCommand?: boolean;
  onExportCore?: () => void;
  coreAdoptionBlocked?: boolean;
  hasLegacyCoreCommand?: boolean;
  discardBlocked?: boolean;
  onDiscard: () => void;
  t: ReturnType<typeof useTranslations>;
}

/**
 * 功能：限制候选索引处于当前候选数组范围内。
 * Args:
 *   index: 外部保存的当前候选索引。
 *   length: 当前候选数量。
 * Returns:
 *   可安全读取数组的索引；空数组返回 -1。
 */
function clampCandidateIndex(index: number, length: number): number {
  if (length === 0) return -1;
  return Math.min(Math.max(index, 0), length - 1);
}

/**
 * 功能：为缺失的角色势力绑定构造符合“未绑定”约束的本地候选。
 * Args:
 *   characterRef: 核心角色候选的稳定局部引用。
 * Returns:
 *   除 character_ref 外全部为 null 的绑定候选。
 */
function createUnboundCandidate(
  characterRef: string
): CharacterFactionBindingCandidateV1 {
  return {
    character_ref: characterRef,
    faction_id: null,
    membership_type: null,
    role_title: null,
    public_status: null,
    loyalty_level: null,
    reason: null,
  };
}

/**
 * 功能：筛出拥有正式 faction_id、可供角色候选绑定的核心势力。
 * Args:
 *   factions: 当前小说的核心势力列表。
 * Returns:
 *   faction_id 已收窄为非空字符串的势力列表。
 */
function getBindableFactions(
  factions: CoreFaction[]
): Array<CoreFaction & { faction_id: string }> {
  return factions.filter(
    (faction): faction is CoreFaction & { faction_id: string } =>
      typeof faction.faction_id === "string" &&
      faction.faction_id.length > 0 &&
      faction.is_deleted !== true &&
      (faction.level_type ?? "core") === "core" &&
      (faction.active_status ?? "active") === "active"
  );
}

/**
 * 功能：渲染核心角色或人物关系的一次性本地生成预览。
 * Args:
 *   props: 候选预览、正式引用数据、交互状态和确认或放弃回调。
 * Returns:
 *   支持候选切换、白名单编辑、关系勾选与一次确认写入的预览界面。
 */
export default function CharacterGenerationPreview({
  corePreview,
  relationPreview,
  selectedCoreCharacterRefs,
  selectedRelationRefs,
  relationCharacterIds,
  selectedCoreIndex,
  selectedRelationIndex,
  characters,
  factions,
  bindings,
  status,
  error,
  hasRequiredProtagonist,
  onSelectCore,
  onSelectRelation,
  onToggleCore,
  onCoreChange,
  onBindingChange,
  onRelationChange,
  onToggleRelation,
  onConfirm,
  onRevise,
  onAdoptCore,
  onAdoptRelation,
  onExportRelation,
  relationAdoptionBlocked = false,
  relationRequestBusy = false,
  relationEditingBlocked = false,
  preparedRelationRefs = [],
  hasLegacyRelationCommand = false,
  onExportCore,
  coreAdoptionBlocked = false,
  hasLegacyCoreCommand = false,
  onDiscard,
  discardBlocked = false,
  t,
}: CharacterGenerationPreviewProps) {
  const factT = useTranslations("writing.characterFacts");
  const isCorePreview = corePreview !== null;
  const saving = status === "confirming" || (!isCorePreview && relationRequestBusy);
  const stale = status === "stale";
  const selectedCoreSet = new Set(selectedCoreCharacterRefs);
  const relationCharacterSet = new Set(relationCharacterIds);
  const selectedCoreCharacters = corePreview?.core_characters.filter((character) => selectedCoreSet.has(character.character_ref)) ?? [];
  const selectedRelationCharacters = characters.filter((character) => relationCharacterSet.has(character.character_id));
  const selectedCharacters = corePreview ? selectedCoreCharacters : selectedRelationCharacters;
  const protagonistCount = selectedCharacters.filter((character) => character.role_type === "protagonist").length;
  const unboundCount = corePreview
    ? corePreview.binding_candidates.filter((binding) => selectedCoreSet.has(binding.character_ref) && binding.faction_id === null).length
    : selectedRelationCharacters.filter((character) => !bindings.some((binding) =>
        binding.character_id === character.character_id && binding.is_active && !binding.is_deleted,
      )).length;
  const selectedRelationCount = relationPreview ? selectedRelationRefs.length : 0;
  const title = isCorePreview
    ? t("candidate.characterTitle")
    : t("candidate.relationTitle");

  return (
    <div className="@container/candidates flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden bg-surface">
      <div className="@container workspace-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto @min-[800px]/candidates:overflow-hidden px-4 py-5 sm:px-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={title}>
        <header className="shrink-0 border-b border-border pb-4">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
          <h2 className="text-lg font-semibold text-foreground">{title}</h2>
          <dl className="flex flex-wrap gap-x-4 gap-y-2 text-xs">
            {[
              [t("candidate.counts.characters"), selectedCharacters.length],
              [t("candidate.counts.protagonists"), protagonistCount],
              [t("candidate.counts.unbound"), unboundCount],
              ...(relationPreview ? [[t("candidate.counts.relations"), selectedRelationCount]] : []),
            ].map(([label, count]) => (
              <div key={String(label)} className="flex items-baseline gap-1.5">
                <dt className="text-muted">{label}</dt>
                <dd className="font-semibold tabular-nums text-foreground">{count}</dd>
              </div>
            ))}
          </dl>
          </div>
          {stale && <p className="mt-4 border-y border-amber-300 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/25 dark:text-amber-200" role="alert">{t(!isCorePreview && onAdoptRelation ? "candidate.relationStale" : "candidate.stale")}</p>}
          {error && <p className="mt-4 border-y border-red-200 bg-red-50/70 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">{error}</p>}
          <p className="mt-3 text-sm text-muted">{t("candidate.bookStart")}</p>
          {corePreview && !hasRequiredProtagonist && <p className="mt-3 text-sm text-amber-700 dark:text-amber-300" role="status">{t("errors.protagonistRequired")}</p>}
        </header>

        {corePreview ? (
          <CoreCandidateReview
            preview={corePreview}
            selectedIndex={selectedCoreIndex}
            factions={factions}
            disabled={saving || (hasLegacyCoreCommand && coreAdoptionBlocked)}
            selectedCharacterRefs={selectedCoreCharacterRefs}
            onSelect={onSelectCore}
            onToggle={onToggleCore}
            onCoreChange={onCoreChange}
            onBindingChange={onBindingChange}
            t={t}
          />
        ) : relationPreview ? (
          <RelationCandidateReview
            preview={relationPreview}
            selectedRelationRefs={selectedRelationRefs}
            selectedIndex={selectedRelationIndex}
            characters={characters}
            disabled={saving}
            onSelect={onSelectRelation}
            onRelationChange={onRelationChange}
            onToggleRelation={onToggleRelation}
            manualPreparation={Boolean(onAdoptRelation)}
            editBlocked={relationEditingBlocked}
            preparedRefs={preparedRelationRefs}
            t={t}
          />
        ) : null}

      </div>
      <footer className="flex shrink-0 flex-col-reverse flex-wrap gap-2 border-t border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-end sm:px-6">
        <Button variant="ghost" size="sm" onPress={onDiscard} isDisabled={saving || discardBlocked || (isCorePreview && coreAdoptionBlocked)}>
          {!isCorePreview && onAdoptRelation ? factT("closeKeep") : t("candidate.discard")}
        </Button>
        {onRevise && <Button variant="outline" size="sm" onPress={onRevise} isDisabled={saving}>{t("candidate.reviseBatch")}</Button>}
        {isCorePreview && onExportCore && <Button variant="ghost" size="sm" onPress={onExportCore}>{t("candidate.exportOriginal")}</Button>}
        {isCorePreview && onAdoptCore && <Button variant="primary" size="sm" onPress={onAdoptCore} isDisabled={saving || coreAdoptionBlocked || !corePreview?.core_characters.length}>{t("candidate.adoptFactStart")}</Button>}
        {!isCorePreview && onExportRelation && <Button variant="ghost" size="sm" onPress={onExportRelation}>{t("candidate.exportOriginal")}</Button>}
        {!isCorePreview && onAdoptRelation && <Button variant="primary" size="sm" onPress={onAdoptRelation} isDisabled={saving || relationAdoptionBlocked || !relationPreview?.relations.length}>{t(preparedRelationRefs.includes(relationPreview?.relations[selectedRelationIndex]?.relation_ref ?? "") ? "candidate.continueRelationFact" : "candidate.adoptRelationFactStart")}</Button>}
        {(isCorePreview ? hasLegacyCoreCommand || !onAdoptCore : hasLegacyRelationCommand || !onAdoptRelation) && <Button
          variant={isCorePreview && onAdoptCore ? "ghost" : "primary"}
          size="sm"
          onPress={onConfirm}
          isDisabled={saving || (isCorePreview && hasLegacyCoreCommand || !isCorePreview && hasLegacyRelationCommand ? false : stale || (isCorePreview ? selectedCoreCharacterRefs.length === 0 || !hasRequiredProtagonist : selectedRelationRefs.length === 0))}
        >
          {saving
            ? t("candidate.confirming")
            : isCorePreview
              ? t(hasLegacyCoreCommand ? "candidate.retryLegacy" : "candidate.reviewCharacters")
              : t(hasLegacyRelationCommand ? "candidate.retryRelationOriginal" : "candidate.reviewRelations")}
        </Button>}
      </footer>
    </div>
  );
}

interface CoreCandidateReviewProps {
  preview: CoreCharactersResultV1;
  selectedIndex: number;
  factions: CoreFaction[];
  disabled: boolean;
  selectedCharacterRefs: string[];
  onSelect: (index: number) => void;
  onToggle: (characterRef: string) => void;
  onCoreChange: (index: number, value: CoreCharacterCandidateV1) => void;
  onBindingChange: (
    characterRef: string,
    value: CharacterFactionBindingCandidateV1
  ) => void;
  t: ReturnType<typeof useTranslations>;
}

/**
 * 功能：渲染核心角色候选列表、角色档案表单和同角色势力绑定编辑器。
 * Args:
 *   props: 核心候选预览、势力数据、选择状态和编辑回调。
 * Returns:
 *   左侧候选导航与右侧角色详情编辑布局。
 */
function CoreCandidateReview({ preview, selectedIndex, factions, disabled, selectedCharacterRefs,
  onSelect, onToggle, onCoreChange, onBindingChange, t }: CoreCandidateReviewProps) {
  const detailRef = useRef<HTMLDivElement>(null);
  const activeIndex = clampCandidateIndex(selectedIndex, preview.core_characters.length);
  const activeCandidate = preview.core_characters[activeIndex];
  if (!activeCandidate) return <p className="py-8 text-muted">{t("emptyCharacters")}</p>;
  const activeBinding = preview.binding_candidates.find((row) => row.character_ref === activeCandidate.character_ref)
    ?? createUnboundCandidate(activeCandidate.character_ref);
  return <section className="grid shrink-0 min-h-0 min-w-0 gap-5 py-5 @min-[800px]/candidates:flex-1 @min-[800px]/candidates:shrink @min-[800px]/candidates:overflow-hidden @min-[800px]/candidates:grid-cols-[260px_minmax(0,1fr)]" aria-label={t("candidate.chooseCharacter")}>
    <ul className="workspace-scrollbar max-h-64 divide-y divide-border border border-border bg-surface-secondary/45 overflow-y-auto @min-[800px]/candidates:min-h-0 @min-[800px]/candidates:max-h-none">
      {preview.core_characters.map((candidate, index) => <li key={candidate.character_ref}
        className={`flex min-w-0 items-center gap-3 border-l-2 px-3 ${index === activeIndex ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
        <input type="checkbox" checked={selectedCharacterRefs.includes(candidate.character_ref)}
          aria-label={t("candidate.toggleCharacter", { name: candidate.name })} disabled={disabled}
          onChange={() => onToggle(candidate.character_ref)} className="size-4 shrink-0 accent-[var(--color-accent)]" />
        <button type="button" className="min-h-11 min-w-0 flex-1 py-3 text-left" disabled={disabled}
          aria-label={candidate.name || t("card.untitled")} aria-current={index === activeIndex ? "true" : undefined} onClick={() => onSelect(index)}>
          <span className="block text-sm font-medium [overflow-wrap:anywhere]">{candidate.name || t("card.untitled")}</span>
          <span className="block text-xs text-muted">{t(`options.roleType.${candidate.role_type}`)}</span>
        </button>
        <SectionEditButton label={t("actions.edit")} isDisabled={disabled} onPress={() => { onSelect(index); requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus()); }} />
      </li>)}
    </ul>
    <div ref={detailRef} className="workspace-scrollbar min-w-0 bg-surface pb-4 @min-[800px]/candidates:min-h-0 @min-[800px]/candidates:max-h-none @min-[800px]/candidates:overflow-y-auto @min-[800px]/candidates:px-3">
      <h3 className="mb-4 text-[22px] font-semibold leading-7 [overflow-wrap:anywhere]">{activeCandidate.name}</h3>
      <CharacterProfileForm value={activeCandidate} disabled={disabled}
        onChange={(value) => onCoreChange(activeIndex, { ...value, character_ref: activeCandidate.character_ref })} t={t} />
      <FactionBindingCandidateEditor value={activeBinding} factions={factions} disabled={disabled}
        onChange={(value) => onBindingChange(activeCandidate.character_ref, value)} t={t} />
    </div>
  </section>;
}

interface FactionBindingCandidateEditorProps {
  value: CharacterFactionBindingCandidateV1;
  factions: CoreFaction[];
  disabled: boolean;
  onChange: (value: CharacterFactionBindingCandidateV1) => void;
  t: ReturnType<typeof useTranslations>;
}

/**
 * 功能：编辑核心角色候选对应的可空势力绑定。
 * Args:
 *   props: 当前绑定、可选势力、禁用状态、更新回调和国际化函数。
 * Returns:
 *   遵守后端“无势力时其余字段全部为 null”规则的绑定表单。
 */
function FactionBindingCandidateEditor({
  value,
  factions,
  disabled,
  onChange,
  t,
}: FactionBindingCandidateEditorProps) {
  const bindableFactions = getBindableFactions(factions);

  /**
   * 功能：切换绑定势力并同步建立或清空整组可空业务字段。
   * Args:
   *   factionId: 新选择的正式势力 ID；空字符串表示不绑定。
   * Returns:
   *   无；通过 onChange 提交新的完整绑定候选。
   */
  const changeFaction = (factionId: string): void => {
    if (!factionId) {
      // 后端要求无势力候选不能残留任何半条绑定信息。
      onChange(createUnboundCandidate(value.character_ref));
      return;
    }
    onChange({
      ...value,
      faction_id: factionId,
      membership_type: value.membership_type ?? "primary",
      role_title: value.role_title,
      public_status: value.public_status ?? "",
      loyalty_level: value.loyalty_level ?? 3,
      reason: value.reason ?? "",
    });
  };

  /**
   * 功能：更新绑定候选的单个白名单字段。
   * Args:
   *   field: 待更新的绑定字段名。
   *   nextValue: 与字段类型匹配的新值。
   * Returns:
   *   无；通过 onChange 提交派生后的完整候选。
   */
  const updateField = <K extends keyof CharacterFactionBindingCandidateV1>(
    field: K,
    nextValue: CharacterFactionBindingCandidateV1[K]
  ): void => {
    onChange({ ...value, [field]: nextValue });
  };

  return (
    <section className="mt-8 border-t border-border pt-6">
      <div className="mb-5 border-b border-border pb-4">
        <h3 className="text-base font-semibold text-foreground">{t("binding.title")}</h3>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <FieldShell label={t("binding.faction")} className="md:col-span-2">
          <select
            value={value.faction_id ?? ""}
            onChange={(event) => changeFaction(event.target.value)}
            disabled={disabled}
            className={INPUT_CLASS_NAME}
          >
            <option value="">{t("binding.unbound")}</option>
            {bindableFactions.map((faction) => (
              <option key={faction.faction_id} value={faction.faction_id}>
                {faction.name} · {faction.faction_id}
              </option>
            ))}
          </select>
        </FieldShell>

        {value.faction_id !== null && (
          <>
            <FieldShell label={t("binding.membershipType")}>
              <select
                value={value.membership_type ?? "primary"}
                onChange={(event) =>
                  updateField(
                    "membership_type",
                    event.target.value as CharacterFactionMembershipType
                  )
                }
                disabled={disabled}
                className={INPUT_CLASS_NAME}
                required
              >
                {MEMBERSHIP_TYPES.map((membershipType) => (
                  <option key={membershipType} value={membershipType}>
                    {t(`options.membershipType.${membershipType}`)}
                  </option>
                ))}
              </select>
            </FieldShell>

            <FieldShell label={t("binding.roleTitle")}>
              <input
                type="text"
                value={value.role_title ?? ""}
                onChange={(event) =>
                  updateField("role_title", event.target.value || null)
                }
                placeholder={t("placeholders.roleTitle")}
                maxLength={100}
                disabled={disabled}
                className={INPUT_CLASS_NAME}
              />
            </FieldShell>

            <FieldShell label={t("binding.publicStatus")}>
              <input
                type="text"
                value={value.public_status ?? ""}
                onChange={(event) =>
                  updateField("public_status", event.target.value || null)
                }
                placeholder={t("placeholders.publicStatus")}
                maxLength={200}
                disabled={disabled}
                className={INPUT_CLASS_NAME}
                required
              />
            </FieldShell>

            <FieldShell label={t("binding.loyaltyLevel")}>
              <input
                type="number"
                min={1}
                max={5}
                step={1}
                value={value.loyalty_level ?? ""}
                onChange={(event) =>
                  updateField(
                    "loyalty_level",
                    event.target.value ? Number(event.target.value) : null
                  )
                }
                disabled={disabled}
                className={INPUT_CLASS_NAME}
                required
              />
            </FieldShell>

            <FieldShell label={t("binding.notes")} className="md:col-span-2">
              <textarea
                value={value.reason ?? ""}
                onChange={(event) => updateField("reason", event.target.value || null)}
                placeholder={t("placeholders.notes")}
                maxLength={1000}
                disabled={disabled}
                rows={3}
                className={TEXTAREA_CLASS_NAME}
                required
              />
            </FieldShell>
          </>
        )}
      </div>
    </section>
  );
}

interface RelationCandidateReviewProps {
  manualPreparation?: boolean;
  editBlocked?: boolean;
  preparedRefs?: string[];
  preview: CharacterRelationsResultV1;
  selectedRelationRefs: string[];
  selectedIndex: number;
  characters: CharacterResponseV1[];
  disabled: boolean;
  onSelect: (index: number) => void;
  onRelationChange: (index: number, value: CharacterRelationCandidateV1) => void;
  onToggleRelation: (relationRef: string) => void;
  t: ReturnType<typeof useTranslations>;
}

/**
 * 功能：渲染关系候选选择列表及当前关系编辑器。
 * Args:
 *   props: 关系审核数据、已保存角色、选择状态和编辑回调。
 * Returns:
 *   支持切换候选、勾选提交范围和编辑关系白名单字段的布局。
 */
function RelationCandidateReview({
  manualPreparation = false,
  editBlocked = false,
  preparedRefs = [],
  preview,
  selectedRelationRefs,
  selectedIndex,
  characters,
  disabled,
  onSelect,
  onRelationChange,
  onToggleRelation,
  t,
}: RelationCandidateReviewProps) {
  const detailRef = useRef<HTMLDivElement>(null);
  const activeIndex = clampCandidateIndex(selectedIndex, preview.relations.length);
  const activeRelation = preview.relations[activeIndex];
  const characterNames = new Map(
    characters.map((character) => [character.character_id, character.name])
  );

  if (!activeRelation) {
    return (
      <p className="border-y border-dashed border-border p-8 text-center text-sm text-muted">
        {t("emptyRelations")}
      </p>
    );
  }

  return (
    <section className="flex shrink-0 min-h-0 flex-col py-5 @min-[800px]/candidates:flex-1 @min-[800px]/candidates:shrink @min-[800px]/candidates:overflow-hidden" aria-labelledby="character-relation-candidate-heading">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 id="character-relation-candidate-heading" className="text-sm font-semibold text-foreground">
          {t("candidate.chooseRelation")}
        </h3>
        {!manualPreparation && <span className="text-xs text-muted">{t("candidate.selectedCount", { count: selectedRelationRefs.length })}</span>}
      </div>
      <div className="grid min-h-0 min-w-0 gap-5 @min-[800px]/candidates:flex-1 @min-[800px]/candidates:shrink @min-[800px]/candidates:overflow-hidden @min-[800px]/candidates:grid-cols-[260px_minmax(0,1fr)]">
      <ul className="workspace-scrollbar max-h-64 divide-y divide-border border border-border bg-surface-secondary/45 overflow-y-auto @min-[800px]/candidates:min-h-0 @min-[800px]/candidates:max-h-none">
          {preview.relations.map((relation, index) => {
            const selectedForCommit = selectedRelationRefs.includes(relation.relation_ref);
            const sourceName =
              characterNames.get(relation.source_character_id) ??
              relation.source_character_id;
            const targetName =
              characterNames.get(relation.target_character_id) ??
              relation.target_character_id;

            return (
              <li
                key={relation.relation_ref}
                className={`flex min-w-0 items-center gap-3 border-l-2 px-3 py-3 ${index === activeIndex ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}
              >
                {!manualPreparation && <input
                  type="checkbox"
                  aria-label={t("candidate.toggleRelation", { ref: relation.relation_ref })}
                  checked={selectedForCommit}
                  onChange={() => onToggleRelation(relation.relation_ref)}
                  disabled={disabled}
                  className="size-4 shrink-0 accent-[var(--color-accent)]"
                />}
                <div className="min-w-0 flex-1">
                  <button type="button" className="min-h-11 w-full min-w-0 text-left text-sm font-medium text-foreground [overflow-wrap:anywhere] focus-visible:outline-2 focus-visible:outline-accent" disabled={disabled} aria-current={index === activeIndex ? "true" : undefined} onClick={() => onSelect(index)}>{sourceName} → {targetName}</button>
                  <p className="mt-1 text-xs text-muted">{t(`options.relationType.${relation.relation_type}`)} · {t("fields.intensity")}: {relation.intensity}/5</p>
                </div>
                <SectionEditButton label={t("actions.edit")} isDisabled={disabled || editBlocked || preparedRefs.includes(relation.relation_ref)} onPress={() => { onSelect(index); requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input:not([readonly]), select, textarea")?.focus()); }} />
              </li>
            );
          })}
      </ul>

      <div ref={detailRef} className="workspace-scrollbar min-w-0 bg-surface pb-4 @min-[800px]/candidates:min-h-0 @min-[800px]/candidates:max-h-none @min-[800px]/candidates:overflow-y-auto @min-[800px]/candidates:px-3">
        <h3 className="mb-4 text-[22px] font-semibold leading-7 [overflow-wrap:anywhere]">{characterNames.get(activeRelation.source_character_id) ?? activeRelation.source_character_id} → {characterNames.get(activeRelation.target_character_id) ?? activeRelation.target_character_id}</h3>
        <CharacterRelationEditor
          value={activeRelation}
          characters={characters}
          relationRef={activeRelation.relation_ref}
          disabled={disabled || editBlocked || preparedRefs.includes(activeRelation.relation_ref)}
          onChange={(value) => onRelationChange(activeIndex, { ...value, relation_ref: activeRelation.relation_ref, is_active: true })}
          t={t}
        />
      </div></div>
    </section>
  );
}

interface FieldShellProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * 功能：为势力绑定控件提供统一标签、间距和可点击区域。
 * Args:
 *   props: 字段标签、控件节点和可选布局类名。
 * Returns:
 *   可直接包裹原生表单控件的标签节点。
 */
function FieldShell({ label, children, className = "" }: FieldShellProps) {
  return (
    <label className={`grid gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}
