"use client";

import { useTranslations } from "next-intl";
import TagList from "@/components/shared/TagList";

/** 原文直接展示，明确空值、布尔和状态使用作者可读文字。 */
export default function FactionFactValue({ value, field }: { value: unknown; field?: string }) {
  const t = useTranslations("writing.factionFacts");
  if (value === undefined || value === null) return <span className="text-muted">{t("notEntered")}</span>;
  if (Array.isArray(value)) return value.length ? <TagList values={value} /> : <span>{t("cleared")}</span>;
  if (typeof value === "boolean") return <span>{t(value ? "public" : "hidden")}</span>;
  if (field === "story_status" && ["active", "dormant", "dissolved"].includes(String(value))) return <span>{t(`status.${value}`)}</span>;
  return <span className="reading-copy whitespace-pre-wrap">{String(value) || t("cleared")}</span>;
}
