/* eslint-disable @next/next/no-img-element */
"use client";

import { useLocale, useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { TooltipHint } from "@/components/shared/TooltipHint";
import { getImageUrl } from "@/lib/api";
import type { NovelSummary } from "@/types/novel";

interface NovelListProps {
  novels: NovelSummary[];
  selectedId: string | null;
  loading: boolean;
  error: string;
  onSelect: (id: string) => void;
  onNewNovel: () => void;
  onOpenTrash: () => void;
  onRetry: () => void;
}

export default function NovelList({
  novels,
  selectedId,
  loading,
  error,
  onSelect,
  onNewNovel,
  onOpenTrash,
  onRetry,
}: NovelListProps) {
  const t = useTranslations("bookshelf");
  const locale = useLocale();
  const numberFormatter = new Intl.NumberFormat(locale);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3">
      <div className="flex gap-2 shrink-0">
        <Button
          variant="outline"
          className="flex-1 border-border bg-surface text-foreground hover:bg-surface-secondary"
          onPress={onNewNovel}
        >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        {t("newNovel")}
      </Button>
        <TooltipHint text={t("trashBin")}><Button
          isIconOnly
          variant="ghost"
          className="size-11 shrink-0 text-muted sm:size-9"
          onPress={onOpenTrash}
          aria-label={t("trashBin")}
        >
          <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
            <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
          </svg>
        </Button></TooltipHint>
      </div>

      {!loading && !error && novels.length > 0 && (
        <p className="text-xs text-muted px-1">
          {t("novelCount", { count: novels.length })}
        </p>
      )}

      <div
        className="workspace-scrollbar min-h-0 flex-1 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        tabIndex={0}
        aria-label={t("listLabel")}
      >
        {loading ? (
          <div className="flex items-center justify-center gap-3 py-8" role="status">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-sm text-muted">{t("loading")}</span>
          </div>
        ) : error ? (
          <div className="border-y border-red-300 py-6 text-center dark:border-red-800" role="alert">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
            <Button variant="outline" size="sm" className="mt-3" onPress={onRetry}>
              {t("retry")}
            </Button>
          </div>
        ) : novels.length === 0 ? (
          <div className="border border-dashed border-border px-4 py-10 text-center">
            <p className="text-sm font-medium text-foreground">{t("emptyTitle")}</p>
            <p className="mt-1 text-sm text-muted">{t("emptyGuide")}</p>
          </div>
        ) : (
          <ul className="space-y-1">
            {novels.map((novel) => (
              <li key={novel.id}>
                <NovelRow
                  novel={novel}
                  isSelected={selectedId === novel.id}
                  onSelect={onSelect}
                  formatNumber={(value) => numberFormatter.format(value)}
                  chapterLabel={t("chapterStat")}
                  wordLabel={t("wordStat")}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function NovelRow({
  novel,
  isSelected,
  onSelect,
  formatNumber,
  chapterLabel,
  wordLabel,
}: {
  novel: NovelSummary;
  isSelected: boolean;
  onSelect: (id: string) => void;
  formatNumber: (value: number) => string;
  chapterLabel: string;
  wordLabel: string;
}) {
  return (
    <button
      id={`bookshelf-novel-${novel.id}`}
      className={`flex w-full min-w-0 items-center gap-3 rounded-lg border-l-2 px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent ${
        isSelected
          ? "border-accent bg-selected"
          : "border-transparent bg-transparent hover:bg-surface-secondary"
      }`}
      onClick={() => onSelect(novel.id)}
      aria-current={isSelected ? "true" : undefined}
    >
      {novel.cover_image ? (
        <img
          src={getImageUrl(novel.cover_image)}
          alt=""
          className="h-14 w-10 shrink-0 rounded-md object-cover"
        />
      ) : (
        <div className="flex h-14 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-surface">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-muted"
            aria-hidden="true"
          >
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
          </svg>
        </div>
      )}

      <div className="flex-1 min-w-0">
        <h3 className="truncate text-sm font-semibold leading-5 text-foreground">
          {novel.title}
        </h3>
        <p className="text-xs text-muted mt-0.5 truncate">
          {novel.genre !== "unclassified" ? novel.genre : ""}
          {novel.subtitle && ` · ${novel.subtitle}`}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 tabular-nums">
          <span className="text-xs text-muted">
            {chapterLabel} {formatNumber(novel.stats?.chapter_count ?? 0)}
          </span>
          <span className="text-xs text-muted">
            {wordLabel} {formatNumber(novel.stats?.total_word_count ?? 0)}
          </span>
        </div>
      </div>
    </button>
  );
}
