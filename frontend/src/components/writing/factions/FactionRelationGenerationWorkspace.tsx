"use client";


import { useRef } from "react";
import SectionEditButton from "@/components/shared/SectionEditButton";
import { Button } from "@heroui/react";
import type { useTranslations } from "next-intl";
import {
  RelationFieldShell,
  RelationIntensityField,
} from "@/components/shared/RelationEditorPrimitives";
import type {
  CoreFaction,
  FactionRelationCandidateV1,
  FactionRelationCreateRequestV1,
  FactionRelationType,
} from "@/types/novel";

/** 页面中尚未保存的阵营关系审核数据。 */
export interface FactionRelationReviewState {
  relations: FactionRelationCandidateV1[];
  selectedRelationRefs: string[];
  selectedIndex: number;
}

interface FactionRelationGenerationPreviewProps {
  value: FactionRelationReviewState;
  factions: Array<CoreFaction & { faction_id: string }>;
  relationTypeLabels: Record<FactionRelationType, string>;
  saving: boolean;
  stale: boolean;
  error: string;
  onSelect: (index: number) => void;
  onToggle: (relationRef: string) => void;
  onChange: (index: number, value: FactionRelationCandidateV1) => void;
  onConfirm: () => void;
  onDiscard: () => void;
  t: ReturnType<typeof useTranslations>;
}

const RELATION_TYPES: readonly FactionRelationType[] = [
  "hostile",
  "allied",
  "cold_war",
  "dependent",
  "subordinate",
  "trade_partner",
  "secret_cooperation",
  "historical_enemy",
];

const INPUT_CLASS_NAME =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const TEXTAREA_CLASS_NAME = `${INPUT_CLASS_NAME} min-h-28 resize-y leading-6`;

/**
 * 功能：渲染阵营关系生成后的浏览器本地候选审核区。
 * Args:
 *   props: 候选、勾选范围、活动阵营、编辑回调及确认或放弃动作。
 * Returns:
 *   支持逐条编辑、选择提交范围和一次性确认的关系审核节点。
 */
export function FactionRelationGenerationPreview({
  value,
  factions,
  relationTypeLabels,
  saving,
  stale,
  error,
  onSelect,
  onToggle,
  onChange,
  onConfirm,
  onDiscard,
  t,
}: FactionRelationGenerationPreviewProps) {
  const detailRef = useRef<HTMLDivElement>(null);
  const activeIndex = Math.min(
    Math.max(value.selectedIndex, 0),
    Math.max(value.relations.length - 1, 0),
  );
  const activeRelation = value.relations[activeIndex];
  const factionNames = new Map(factions.map((faction) => [faction.faction_id, faction.name]));

  return (
    <div className="@container/candidates flex h-full min-h-0 flex-col overflow-hidden bg-surface">
      <div className="@container workspace-scrollbar flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-y-auto @min-[800px]/candidates:overflow-hidden px-4 py-5 sm:px-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={t("relationCandidate.title")}>
        <header className="shrink-0 border-b border-border pb-4">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t("relationCandidate.title")}
            </h2>
            <p className="text-xs text-muted">
              {t("relationCandidate.meta", {
                relations: value.relations.length,
                selected: value.selectedRelationRefs.length,
              })}
            </p>
          </div>
          {stale && (
            <p className="mt-4 border-y border-amber-300 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/25 dark:text-amber-200" role="alert">
              {t("candidate.stale")}
            </p>
          )}
          {!stale && error && (
            <p className="mt-4 border-y border-red-200 bg-red-50/70 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">
              {error}
            </p>
          )}
        </header>

        {activeRelation && (
          <section className="flex min-h-0 shrink-0 flex-col py-5 @min-[800px]/candidates:flex-1 @min-[800px]/candidates:shrink @min-[800px]/candidates:overflow-hidden" aria-labelledby="relation-candidate-list-heading">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 id="relation-candidate-list-heading" className="text-sm font-semibold text-foreground">
                {t("relationCandidate.chooseRelation")}
              </h3>
              <span className="text-xs text-muted">{t("candidate.selectedCount", { count: value.selectedRelationRefs.length })}</span>
            </div>
            <div className="grid min-h-0 min-w-0 gap-5 @min-[800px]/candidates:flex-1 @min-[800px]/candidates:overflow-hidden @min-[800px]/candidates:grid-cols-[260px_minmax(0,1fr)]">
              <ul className="workspace-scrollbar min-h-0 max-h-64 divide-y divide-border overflow-y-auto border border-border bg-surface-secondary/45 @min-[800px]/candidates:max-h-none">
                {value.relations.map((relation, index) => {
                  const selectedForCommit = value.selectedRelationRefs.includes(relation.relation_ref);
                  return (
                    <li
                      key={relation.relation_ref}
                      className={`flex min-w-0 items-center gap-3 border-l-2 px-3 py-3 ${index === activeIndex ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}
                    >
                      <input
                        type="checkbox"
                        aria-label={t("candidate.toggleRelation", { ref: relation.relation_ref })}
                        checked={selectedForCommit}
                        onChange={() => onToggle(relation.relation_ref)}
                        disabled={saving}
                        className="size-4 shrink-0 accent-[var(--color-accent)]"
                      />
                      <div className="min-w-0 flex-1">
                        <button type="button" disabled={saving} aria-current={index === activeIndex ? "true" : undefined} onClick={() => onSelect(index)} className="min-h-11 w-full min-w-0 text-left text-sm font-medium text-foreground [overflow-wrap:anywhere] focus-visible:outline-2 focus-visible:outline-accent">
                          {factionNames.get(relation.source_faction_id) ?? relation.source_faction_id}
                          {" → "}
                          {factionNames.get(relation.target_faction_id) ?? relation.target_faction_id}
                        </button>
                        <p className="mt-1 text-xs text-muted">
                          {relationTypeLabels[relation.relation_type]} · {relation.intensity}/5
                        </p>

                      </div>
                      <SectionEditButton label={t("edit")} isDisabled={saving} onPress={() => {
                        onSelect(index);
                        requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input:not([readonly]), select, textarea")?.focus());
                      }} />
                    </li>
                  );
                })}
              </ul>
              <div ref={detailRef} className="workspace-scrollbar min-h-0 min-w-0 bg-surface pb-4 @min-[800px]/candidates:max-h-none @min-[800px]/candidates:overflow-y-auto @min-[800px]/candidates:px-3">
                <h3 className="mb-4 text-[22px] font-semibold leading-7 [overflow-wrap:anywhere]">{factionNames.get(activeRelation.source_faction_id) ?? activeRelation.source_faction_id} → {factionNames.get(activeRelation.target_faction_id) ?? activeRelation.target_faction_id}</h3>
                <FactionRelationCandidateEditor value={activeRelation} factions={factions} relationTypeLabels={relationTypeLabels} disabled={saving} onChange={(relation) => onChange(activeIndex, relation)} t={t} />
              </div>
            </div>
          </section>
        )}

      </div>
      <footer className="flex shrink-0 flex-col-reverse flex-wrap gap-2 border-t border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-end sm:px-6">
        <Button variant="ghost" size="sm" onPress={onDiscard} isDisabled={saving}>
          {t("relationCandidate.discard")}
        </Button>
        <Button variant="primary" size="sm" onPress={onConfirm} isDisabled={saving || stale || value.selectedRelationRefs.length === 0}>
          {saving ? t("relationCandidate.confirming") : t("relationCandidate.review")}
        </Button>
      </footer>


    </div>
  );
}

interface FactionRelationCandidateEditorProps {
  value: FactionRelationCandidateV1;
  factions: Array<CoreFaction & { faction_id: string }>;
  relationTypeLabels: Record<FactionRelationType, string>;
  disabled: boolean;
  onChange: (value: FactionRelationCandidateV1) => void;
  t: ReturnType<typeof useTranslations>;
}

/**
 * 功能：编辑单条阵营关系候选的白名单业务字段。
 * Args:
 *   props: 当前候选、正式阵营候选项、关系类型文案、禁用状态与更新回调。
 * Returns:
 *   保持 relation_ref 和 is_active 不变的受控关系表单。
 */
function FactionRelationCandidateEditor({
  value,
  factions,
  relationTypeLabels,
  disabled,
  onChange,
  t,
}: FactionRelationCandidateEditorProps) {
  /**
   * 功能：更新候选的单个可编辑字段。
   * Args:
   *   name: 待更新的关系业务字段名。
   *   nextValue: 与字段类型一致的新值。
   * Returns:
   *   无；通过 onChange 提交完整候选对象。
   */
  const update = <K extends keyof FactionRelationCreateRequestV1>(
    name: K,
    nextValue: FactionRelationCreateRequestV1[K],
  ): void => {
    onChange({ ...value, [name]: nextValue, is_active: true });
  };

  return (
    <div className="space-y-8">
      <section className="border-b border-border pb-7">
        <h4 className="text-sm font-semibold text-foreground">{t("relationEditor.endpoints")}</h4>
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <RelationFieldShell label={t("relationCandidate.relationRef")} className="md:col-span-2">
            <input readOnly value={value.relation_ref} className={`${INPUT_CLASS_NAME} bg-surface-secondary/55`} />
          </RelationFieldShell>
          <RelationFieldShell label={t("fields.sourceFaction")}>
            <select
              value={value.source_faction_id}
              onChange={(event) => update("source_faction_id", event.target.value)}
              disabled={disabled}
              className={INPUT_CLASS_NAME}
            >
              {factions
                .filter((faction) => faction.faction_id !== value.target_faction_id)
                .map((faction) => (
                  <option key={faction.faction_id} value={faction.faction_id}>
                    {faction.name} · {faction.faction_id}
                  </option>
                ))}
            </select>
          </RelationFieldShell>
          <RelationFieldShell label={t("fields.targetFaction")}>
            <select
              value={value.target_faction_id}
              onChange={(event) => update("target_faction_id", event.target.value)}
              disabled={disabled}
              className={INPUT_CLASS_NAME}
            >
              {factions
                .filter((faction) => faction.faction_id !== value.source_faction_id)
                .map((faction) => (
                  <option key={faction.faction_id} value={faction.faction_id}>
                    {faction.name} · {faction.faction_id}
                  </option>
                ))}
            </select>
          </RelationFieldShell>
          <RelationFieldShell label={t("fields.relationType")}>
            <select
              value={value.relation_type}
              onChange={(event) => update("relation_type", event.target.value as FactionRelationType)}
              disabled={disabled}
              className={INPUT_CLASS_NAME}
            >
              {RELATION_TYPES.map((relationType) => (
                <option key={relationType} value={relationType}>
                  {relationTypeLabels[relationType]}
                </option>
              ))}
            </select>
          </RelationFieldShell>
          <RelationIntensityField
            label={t("fields.intensity")}
            value={value.intensity}
            onChange={(intensity) => update("intensity", intensity)}
            disabled={disabled}
            inputClassName={INPUT_CLASS_NAME}
          />
        </div>
      </section>

      <section>
        <h4 className="text-sm font-semibold text-foreground">{t("relationEditor.narrative")}</h4>
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          {([
            ["current_state", "currentState"],
            ["core_conflict", "coreConflict"],
            ["hidden_tension", "hiddenTension"],
            ["possible_change", "possibleChange"],
          ] as const).map(([name, labelKey]) => (
            <RelationFieldShell
              key={name}
              label={t(`fields.${labelKey}`)}
              className={name === "current_state" ? "md:col-span-2" : ""}
            >
              <textarea
                value={value[name]}
                onChange={(event) => update(name, event.target.value)}
                maxLength={2000}
                rows={name === "current_state" ? 3 : 5}
                disabled={disabled}
                className={TEXTAREA_CLASS_NAME}
              />
            </RelationFieldShell>
          ))}
        </div>
      </section>
    </div>
  );
}
