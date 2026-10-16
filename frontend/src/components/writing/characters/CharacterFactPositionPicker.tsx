"use client";

import { useEffect, useId } from "react";
import { TooltipHint } from "@/components/shared/TooltipHint";
import { useTranslations } from "next-intl";
import type { CharacterFactPositionV1 } from "@/types/characterFacts";
import type { HierarchyRecord } from "@/types/hierarchy";
import { FORESHADOWING_INPUT as INPUT } from "../foreshadowings/EvidencePicker";
import { characterFactPositionFromKey, characterFactPositionKey } from "./characterFactPositions";

/** 功能：以书初或明确章前后选择同一套剧情位置。Args: 原目录和位置；latest 只用于读取。Returns: 语义位置选择器。 */
export default function CharacterFactPositionPicker({ novelId, chapters: directory, volumes = [], value, onChange, disabled = false, latest = false, afterOnly = false, required = false, error }: {
  novelId: string; chapters: HierarchyRecord[] | null; volumes?: { volume_id?: string; title: string }[]; value: CharacterFactPositionV1 | null; onChange: (value: CharacterFactPositionV1 | null) => void; disabled?: boolean; latest?: boolean; afterOnly?: boolean; required?: boolean; error?: string;
}) {
  const chapters = directory ?? [];
  const t = useTranslations("writing.characterFacts");
  const key = characterFactPositionKey(value);
  const errorId = useId();
  const onlyChapterAfter = directory !== null && !latest && afterOnly && chapters.length === 1 && (!value || value.intent === "chapter_after" && value.target_id === chapters[0].chapter_id);
  const onlyBookStart = directory !== null && !latest && !afterOnly && !chapters.length && !volumes.some((volume) => volume.volume_id) && (!value || value.intent === "book_start");
  const singleKey = onlyBookStart ? "book_start" : onlyChapterAfter ? `chapter_after:${chapters[0].chapter_id}` : null;
  useEffect(() => {
    if (singleKey && !value && !disabled) onChange(characterFactPositionFromKey(novelId, singleKey));
  }, [singleKey, value, disabled, novelId, onChange]);
  return <div className="grid min-w-0 gap-2 text-xs font-medium text-muted"><span><TooltipHint label={t("position")} text={t("positionHelp")} />{required && <span aria-hidden="true" className="ml-1 text-danger">*</span>}</span>
    {singleKey ? <output aria-label={t("position")} className="py-2 text-sm text-foreground">{onlyBookStart ? t("positions.book_start") : `${chapters[0].title} · ${t("positions.chapter_after")}`}</output> : <select name="position" aria-label={t("position")} required={required} aria-required={required || undefined} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined} className={INPUT} value={key} disabled={disabled} onChange={(event) => onChange(characterFactPositionFromKey(novelId, event.target.value))}>
      <option value="">{t(latest ? "latest" : "choosePosition")}</option>
      {!afterOnly && <option value="book_start">{t("positions.book_start")}</option>}
      {!afterOnly && volumes.filter((volume) => volume.volume_id).map((volume) => <option key={volume.volume_id} value={`volume_start:${volume.volume_id}`}>{volume.title} · {t("positions.volume_start")}</option>)}
      {value?.intent === "volume_start" && !volumes.some((volume) => volume.volume_id === value.target_id) && <option value={key}>{t("positions.volume_start")}</option>}
      {chapters.flatMap((chapter) => (afterOnly ? ["chapter_after"] : ["chapter_before", "chapter_after"]).map((intent) => <option key={`${intent}:${chapter.chapter_id}`} value={`${intent}:${chapter.chapter_id}`}>{chapter.title} · {t(`positions.${intent}`)}</option>))}
      {value?.target_type === "chapter" && !chapters.some((chapter) => chapter.chapter_id === value.target_id) && <option value={key}>{value.target_id} · {t(`positions.${value.intent}`)}</option>}
    </select>}
    {error && <span id={errorId} className="text-danger">{error}</span>}
  </div>;
}
