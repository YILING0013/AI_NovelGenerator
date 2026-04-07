/* eslint-disable @next/next/no-img-element */
"use client";

import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import { Card, Button, Chip } from "@heroui/react";
import { getImageUrl } from "@/lib/api";
import type { NovelDetail } from "@/types/novel";

interface NovelDetailPanelProps {
  novel: NovelDetail | null;
  onDelete: (id: string) => void;
}

const STATUS_COLOR_MAP: Record<string, "primary" | "secondary" | "tertiary" | "soft"> = {
  draft: "secondary",
  ongoing: "primary",
  completed: "tertiary",
  paused: "soft",
};

const PREVIEW_LONG_FIELDS: { key: keyof NovelDetail; labelKey: string }[] = [
  { key: "introduction", labelKey: "introduction" },
  { key: "summary", labelKey: "summary" },
  { key: "tone", labelKey: "tone" },
  { key: "target_audience", labelKey: "targetAudience" },
];

const STYLE_THREE_COLS: { key: keyof NovelDetail; labelKey: string }[] = [
  { key: "writing_style", labelKey: "writingStyle" },
  { key: "narrative_pov", labelKey: "narrativePov" },
  { key: "era_background", labelKey: "eraBackground" },
];

export default function NovelDetailPanel({
  novel,
  onDelete,
}: NovelDetailPanelProps) {
  const t = useTranslations("novel");
  const tb = useTranslations("bookshelf");
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";

  if (!novel) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center text-muted">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="48"
            height="48"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="mx-auto mb-4 opacity-30"
          >
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
          </svg>
          <p className="text-sm">{tb("noSelection")}</p>
        </div>
      </div>
    );
  }

  const statusKey = `status${novel.status.charAt(0).toUpperCase()}${novel.status.slice(1)}` as
    | "statusDraft"
    | "statusOngoing"
    | "statusCompleted"
    | "statusPaused";

  const handleDeleteClick = () => {
    if (confirm(tb("deleteConfirm", { title: novel.title }))) {
      onDelete(novel._id);
    }
  };

  const goWriting = () => {
    router.push(`/${locale}/writing/${novel._id}`);
  };

  return (
    <div className="h-full overflow-y-auto">
      <Card className="min-h-full">
        <Card.Header>
          <div className="flex items-start justify-between w-full">
            <div className="flex items-start gap-4 flex-1 min-w-0">
              {novel.cover_image ? (
                <img
                  src={getImageUrl(novel.cover_image)}
                  alt={novel.title}
                  className="w-24 h-32 rounded-lg object-cover shrink-0 shadow-sm"
                />
              ) : (
                <div className="w-24 h-32 rounded-lg bg-muted/30 shrink-0 flex items-center justify-center">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="32"
                    height="32"
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

              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-bold text-foreground truncate">
                  {novel.title}
                </h2>
                {novel.subtitle && (
                  <p className="text-sm text-muted mt-0.5">{novel.subtitle}</p>
                )}
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <Chip variant={STATUS_COLOR_MAP[novel.status] || "secondary"} size="sm">
                    {t(statusKey)}
                  </Chip>
                  {novel.genre !== "unclassified" && (
                    <Chip variant="soft" size="sm">
                      {novel.genre}
                    </Chip>
                  )}
                </div>
                {novel.tags && novel.tags.length > 0 && (
                  <div className="flex gap-1 mt-2 flex-wrap">
                    {novel.tags.map((tag) => (
                      <Chip key={tag} variant="tertiary" size="sm">
                        {tag}
                      </Chip>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex gap-2 shrink-0 ml-4">
              <Button
                variant="primary"
                size="sm"
                onPress={goWriting}
                className="bg-accent text-white hover:bg-accent-hover"
              >
                {tb("goWriting")}
              </Button>
              <Button variant="danger-soft" size="sm" onPress={handleDeleteClick}>
                {t("delete")}
              </Button>
            </div>
          </div>
        </Card.Header>

        <Card.Content>
          <div className="space-y-4">
            <div className="flex gap-6 text-sm text-muted">
              <span>
                {t("chapterCount")}: {novel.stats?.chapter_count ?? 0}
              </span>
              <span>
                {t("totalWords")}: {(novel.stats?.total_word_count ?? 0).toLocaleString()}
              </span>
              <span>
                {t("createdAt")}: {new Date(novel.created_at).toLocaleDateString()}
              </span>
            </div>

            {PREVIEW_LONG_FIELDS.map(({ key, labelKey }) => {
              const value = novel[key];
              if (!value) return null;
              return (
                <PreviewField
                  key={key}
                  label={t(labelKey)}
                  value={String(value)}
                />
              );
            })}

            {/* writing_style / narrative_pov / era_background — blockquote 3-col */}
            {STYLE_THREE_COLS.some(({ key }) => novel[key]) && (
              <div className="grid grid-cols-3 gap-3">
                {STYLE_THREE_COLS.map(({ key, labelKey }) => (
                  <div key={key} className="border-l-3 border-accent/40 pl-3 py-1">
                    <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">
                      {t(labelKey)}
                    </h3>
                    <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
                      {novel[key] ? String(novel[key]) : "-"}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card.Content>
      </Card>
    </div>
  );
}

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-muted uppercase tracking-wide">
        {label}
      </h3>
      <div className="pt-1 pb-1">
        <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
          {value}
        </p>
      </div>
    </div>
  );
}
