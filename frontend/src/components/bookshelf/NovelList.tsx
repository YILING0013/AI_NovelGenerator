/* eslint-disable @next/next/no-img-element */
"use client";

import { useTranslations } from "next-intl";
import { Card, Button } from "@heroui/react";
import { getImageUrl } from "@/lib/api";
import type { NovelSummary } from "@/types/novel";

interface NovelListProps {
  novels: NovelSummary[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onNewNovel: () => void;
}

export default function NovelList({
  novels,
  selectedId,
  loading,
  onSelect,
  onNewNovel,
}: NovelListProps) {
  const t = useTranslations("bookshelf");

  return (
    <div className="flex flex-col h-full gap-3">
      {/* New Novel Button */}
      <Button
        variant="primary"
        className="w-full shrink-0"
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

      {/* Novel Count */}
      {!loading && novels.length > 0 && (
        <p className="text-xs text-muted px-1">
          {t("novelCount", { count: novels.length })}
        </p>
      )}

      {/* Novel List */}
      <div className="flex-1 overflow-y-auto space-y-2 px-1">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
          </div>
        ) : novels.length === 0 ? (
          <div className="text-center text-muted text-sm py-8 px-2">
            {t("emptyGuide")}
          </div>
        ) : (
          novels.map((novel) => (
            <NovelCard
              key={novel._id}
              novel={novel}
              isSelected={selectedId === novel._id}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  );
}

function NovelCard({
  novel,
  isSelected,
  onSelect,
}: {
  novel: NovelSummary;
  isSelected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <Card
      className={`cursor-pointer transition-all hover:shadow-md ${
        isSelected
          ? "border-l-3 border-l-primary bg-primary/5 shadow-sm"
          : "hover:bg-muted/30"
      }`}
    >
      <button
        className="w-full text-left"
        onClick={() => onSelect(novel._id)}
      >
        <Card.Header>
          <div className="flex items-start gap-3 w-full">
            {/* Cover Thumbnail */}
            {novel.cover_image ? (
              <img
                src={getImageUrl(novel.cover_image)}
                alt={novel.title}
                className="w-12 h-16 rounded object-cover shrink-0"
              />
            ) : (
              <div className="w-12 h-16 rounded bg-muted/50 shrink-0 flex items-center justify-center">
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
                >
                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
                </svg>
              </div>
            )}

            {/* Info */}
            <div className="flex-1 min-w-0">
              <Card.Title className="text-sm font-semibold truncate">
                {novel.title}
              </Card.Title>
              <p className="text-xs text-muted mt-0.5 truncate">
                {novel.genre !== "unclassified" ? novel.genre : ""}
                {novel.subtitle && ` · ${novel.subtitle}`}
              </p>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-muted">
                  {novel.stats?.chapter_count ?? 0}章
                </span>
                <span className="text-xs text-muted">
                  {(novel.stats?.total_word_count ?? 0).toLocaleString()}字
                </span>
              </div>
            </div>
          </div>
        </Card.Header>
      </button>
    </Card>
  );
}
