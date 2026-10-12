"use client";

import { useTranslations } from "next-intl";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import TagList from "@/components/shared/TagList";
import type { CharacterFactBasisV1, CharacterFactField } from "@/types/characterFacts";
import { CHARACTER_PROFILE_FACT_FIELDS } from "./characterFactFields";

/** 功能：展示作者预览冻结的旧保存文字，不补未知事实，也不替作者采用旧值。Args: 原 basis。Returns: 原来源及缺口的只读参考。 */
export default function CharacterFactLegacySources({ basis }: { basis: CharacterFactBasisV1 }) {
  const t = useTranslations("writing.characterFacts");
  if (!Array.isArray(basis.legacy_sources)) return <p role="alert" className="text-sm text-amber-700 dark:text-amber-300">{t("previewContractChanged")}</p>;
  if (!basis.legacy_sources.length) return null;
  const situation = basis.fields.some((field) => ["psychological_state", "public_state", "hidden_state", "actual_goal"].includes(field));
  const display = (raw: object, field: string) => {
    if (!Object.hasOwn(raw, field)) return t("legacyMissing");
    const value = (raw as Record<string, string | string[] | null>)[field];
    if (value === null) return t("legacyNull");
    if (!value.length) return t("cleared");
    return Array.isArray(value) ? <TagList values={value} /> : value;
  };
  return <section className="space-y-4" aria-label={t("legacyTitle")}>
    <h4 className="text-sm font-semibold">{t("legacyTitle")}</h4>
    <p className="reading-copy text-sm text-muted">{t("legacyExplanation")}</p>
    {basis.legacy_sources.map((source) => {
      const fields = source.kind === "profile"
        ? basis.fields.filter((field) => CHARACTER_PROFILE_FACT_FIELDS.includes(field))
        : basis.fields.filter((field) => ["psychological_state", "public_state", "hidden_state", "actual_goal"].includes(field));
      return <section key={source.kind === "profile" ? source.entity_id : source.state_id} className="space-y-3 border-l-2 border-border pl-4">
        <h5 className="text-sm font-medium">{source.kind === "profile" ? t("legacyProfile") : t("legacyVolume", { volume: source.volume?.title ?? source.volume_id })}</h5>
        <p className="text-xs text-muted">{t("referenceVersion", { version: source.version })}{source.kind === "volume_state" && (source.is_deleted || source.volume?.is_deleted) ? ` · ${t("legacyDeleted")}` : ""}</p>
        {source.kind === "volume_state" && !source.volume && <p className="text-xs text-amber-700 dark:text-amber-300">{t("legacyVolumeMissing")}</p>}
        <dl className="detail-fields grid gap-3">{fields.map((field: CharacterFactField) => <ReadOnlyField key={field} label={field === "actual_goal" ? t("legacyGoalPlan") : t(`fields.${field}`)} value={display(source.raw, field === "actual_goal" ? "current_goal" : field)} wide />)}</dl>
        {situation && <ReadOnlyField label={t(source.kind === "profile" ? "legacyInitialPlan" : "legacyOpeningPlan")} value={display(source.notes, source.kind === "profile" ? "initial_state" : "start_state")} wide />}
      </section>;
    })}
    {situation && !basis.legacy_sources.some((source) => source.kind === "volume_state") && <p className="text-sm text-muted">{t("legacyNoVolumeStates")}</p>}
  </section>;
}
