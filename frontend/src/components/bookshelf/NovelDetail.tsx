/* eslint-disable @next/next/no-img-element */
"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import { Button, Chip } from "@heroui/react";
import { ConfirmActionModal } from "@/components/shared/RelationEditorPrimitives";
import { getImageUrl } from "@/lib/api";
import type { NovelDetail } from "@/types/novel";
import ChapterRecordsArchive from "@/components/writing/chapter-records/ChapterRecordsArchive";

interface NovelDetailPanelProps {
  novel: NovelDetail | null;
  loading?: boolean;
  onDelete: (id: string, expectedVersion: number) => Promise<void>;
  onBack: () => void;
}

const STATUS_COLOR_MAP: Record<string, "primary" | "secondary" | "tertiary" | "soft"> = {
  draft: "secondary",
  ongoing: "primary",
  completed: "tertiary",
  archived: "soft",
};

const PREVIEW_LONG_FIELDS: { key: keyof NovelDetail; labelKey: string }[] = [
  { key: "introduction", labelKey: "introduction" },
  { key: "summary", labelKey: "summary" },
];

const SETTING_FIELDS: { key: keyof NovelDetail; labelKey: string }[] = [
  { key: "tone", labelKey: "tone" },
  { key: "target_audience", labelKey: "targetAudience" },
  { key: "writing_style", labelKey: "writingStyle" },
  { key: "narrative_pov", labelKey: "narrativePov" },
  { key: "era_background", labelKey: "eraBackground" },
];

export default function NovelDetailPanel({
  novel,
  loading = false,
  onDelete,
  onBack,
}: NovelDetailPanelProps) {
  const t = useTranslations("novel");
  const tb = useTranslations("bookshelf");
  const router = useRouter();
  const pathname = usePathname();
  const intlLocale = useLocale();
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [recordsOpen, setRecordsOpen] = useState(false);

  if (loading || !novel) {
    return (
      <div className="relative flex h-full items-center justify-center px-4">
        <Button variant="ghost" size="sm" className="absolute left-4 top-4 md:hidden" onPress={onBack}>
          {tb("backToList")}
        </Button>
        <div className="text-center text-muted">
          {loading ? (
            <div className="flex items-center gap-3" role="status">
              <span className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              <span className="text-sm">{tb("loading")}</span>
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      </div>
    );
  }

  const statusKey = `status${novel.status.charAt(0).toUpperCase()}${novel.status.slice(1)}` as
    | "statusDraft"
    | "statusOngoing"
    | "statusCompleted"
    | "statusArchived";

  const handleDeleteConfirm = async () => {
    try {
      setDeleting(true);
      setDeleteError("");
      await onDelete(novel.id, novel.version);
      setConfirmingDelete(false);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : tb("deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  const goWriting = () => {
    router.push(`/${locale}/writing/${novel.id}`);
  };
  const hasNarrative = PREVIEW_LONG_FIELDS.some(({ key }) => novel[key]);

  return (
    <article
      className="@container/book workspace-scrollbar h-full min-h-0 overflow-y-auto px-4 py-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:px-6"
      tabIndex={0}
      aria-labelledby="bookshelf-novel-title"
    >
      <Button variant="ghost" size="sm" className="mb-4 md:hidden" onPress={onBack}>
        {tb("backToList")}
      </Button>

      <header className="flex flex-col gap-4 @[720px]/book:flex-row @[720px]/book:items-start @[720px]/book:justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          {novel.cover_image ? (
            <img
              src={getImageUrl(novel.cover_image)}
              alt={novel.title}
              className="h-28 w-20 shrink-0 rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-28 w-20 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-secondary">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted" aria-hidden="true">
                <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
              </svg>
            </div>
          )}

          <div className="min-w-0 flex-1">
            <h2 id="bookshelf-novel-title" className="break-words text-[22px] font-semibold leading-7 text-foreground">
              {novel.title}
            </h2>
            {novel.subtitle && <p className="mt-1 text-sm leading-6 text-muted">{novel.subtitle}</p>}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Chip variant={STATUS_COLOR_MAP[novel.status] || "secondary"} size="sm">
                {t(statusKey)}
              </Chip>
              {novel.genre !== "unclassified" && <Chip variant="soft" size="sm">{novel.genre}</Chip>}
            </div>
            {novel.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {novel.tags.map((tag) => <Chip key={tag} variant="tertiary" size="sm">{tag}</Chip>)}
              </div>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button variant="primary" size="sm" onPress={goWriting} className="bg-accent text-accent-foreground hover:bg-accent-hover">
            {tb("goWriting")}
          </Button>
          <Button variant="outline" size="sm" onPress={() => setRecordsOpen(true)}>
            {tb("viewChapterRecords")}
          </Button>
          <Button variant="ghost" size="sm" className="text-red-700 hover:bg-red-500/10 dark:text-red-300" onPress={() => setConfirmingDelete(true)}>
            {t("delete")}
          </Button>
        </div>
      </header>

      {/* 宽屏用右侧展示已有设定，正文占满剩余栏宽；窄屏按阅读顺序回到单列。 */}
      <div className={`mt-4 grid min-w-0 gap-y-4 ${hasNarrative ? "@[960px]/book:grid-cols-[minmax(0,1fr)_15rem] @[960px]/book:gap-8" : ""}`}>
        {hasNarrative && (
          <div className="min-w-0 space-y-4">
            {PREVIEW_LONG_FIELDS.map(({ key, labelKey }) => {
              const value = novel[key];
              return value ? <PreviewField key={key} label={t(labelKey)} value={String(value)} /> : null;
            })}
          </div>
        )}

        <div className={`min-w-0 ${hasNarrative ? "@[960px]/book:border-l @[960px]/book:border-border @[960px]/book:pl-6" : ""}`}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-4">
            <div><dt className="text-xs text-muted">{t("chapterCount")}</dt><dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">{new Intl.NumberFormat(intlLocale).format(novel.stats.chapter_count)}</dd></div>
            <div><dt className="text-xs text-muted">{t("totalWords")}</dt><dd className="mt-1 text-xl font-semibold tabular-nums text-foreground">{new Intl.NumberFormat(intlLocale).format(novel.stats.total_word_count)}</dd></div>
            {novel.created_at && (
              <div className="col-span-full flex flex-wrap items-baseline justify-between gap-2 text-xs"><dt className="text-muted">{t("createdAt")}</dt><dd className="tabular-nums text-foreground">{new Intl.DateTimeFormat(intlLocale).format(new Date(novel.created_at))}</dd></div>
            )}
          </dl>
          {SETTING_FIELDS.some(({ key }) => novel[key]) && (
            <dl className="mt-4 grid gap-4 @min-[560px]/book:grid-cols-2 @[960px]/book:grid-cols-1">
              {SETTING_FIELDS.map(({ key, labelKey }) => novel[key] ? (
                <div key={key} className="min-w-0">
                  <dt className="text-xs font-medium text-muted">{t(labelKey)}</dt>
                  <dd className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-foreground">{String(novel[key])}</dd>
                </div>
              ) : null)}
            </dl>
          )}
        </div>
      </div>

      {recordsOpen && <ChapterRecordsArchive key={novel.id} novelId={novel.id} novelTitle={novel.title} open onClose={() => setRecordsOpen(false)} />}

      {confirmingDelete && (
        <ConfirmActionModal
          title={tb("deleteTitle")}
          message={tb("deleteConfirm", { title: novel.title })}
          confirmText={t("delete")}
          cancelText={t("cancel")}
          loadingText={tb("deleting")}
          danger
          error={deleteError}
          isLoading={deleting}
          onCancel={() => {
            setConfirmingDelete(false);
            setDeleteError("");
          }}
          onConfirm={handleDeleteConfirm}
        />
      )}
    </article>
  );
}

function PreviewField({ label, value }: { label: string; value: string }) {
  return (
    <section>
      <h3 className="text-sm font-semibold text-foreground">
        {label}
      </h3>
      <div className="pt-2">
        <p className="reading-copy whitespace-pre-wrap text-foreground">
          {value}
        </p>
      </div>
    </section>
  );
}
