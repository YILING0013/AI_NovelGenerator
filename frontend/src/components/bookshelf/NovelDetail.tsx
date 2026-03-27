/* eslint-disable @next/next/no-img-element */
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Card, Button, Chip } from "@heroui/react";
import { apiPut, getImageUrl } from "@/lib/api";
import type { NovelDetail } from "@/types/novel";

interface NovelDetailPanelProps {
  novel: NovelDetail | null;
  onDelete: (id: string) => void;
  onUpdated: () => void;
}

const STATUS_COLOR_MAP: Record<string, "primary" | "secondary" | "tertiary" | "soft"> = {
  draft: "secondary",
  ongoing: "primary",
  completed: "tertiary",
  paused: "soft",
};

export default function NovelDetailPanel({
  novel,
  onDelete,
  onUpdated,
}: NovelDetailPanelProps) {
  const t = useTranslations("novel");
  const tb = useTranslations("bookshelf");
  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState<Partial<NovelDetail>>({});
  const [saving, setSaving] = useState(false);

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

  const startEdit = () => {
    setEditData({
      introduction: novel.introduction,
      tags: novel.tags,
    });
    setEditing(true);
  };

  const saveEdit = async () => {
    try {
      setSaving(true);
      await apiPut(`/api/novels/${novel._id}`, editData);
      setEditing(false);
      onUpdated();
    } catch {
      // handle error
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteClick = () => {
    if (confirm(tb("deleteConfirm", { title: novel.title }))) {
      onDelete(novel._id);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <Card className="h-full">
        <Card.Header>
          <div className="flex items-start justify-between w-full">
            <div className="flex items-start gap-4 flex-1 min-w-0">
              {/* Cover */}
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

              {/* Title & Meta */}
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

            {/* Action Buttons */}
            <div className="flex gap-2 shrink-0 ml-4">
              {editing ? (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    isDisabled={saving}
                    onPress={saveEdit}
                  >
                    {t("save")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onPress={() => setEditing(false)}
                  >
                    {t("cancel")}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" size="sm" onPress={startEdit}>
                    {t("edit")}
                  </Button>
                  <Button variant="danger-soft" size="sm" onPress={handleDeleteClick}>
                    {t("delete")}
                  </Button>
                </>
              )}
            </div>
          </div>
        </Card.Header>

        <Card.Content>
          <div className="space-y-4">
            {/* Stats Row */}
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

            {/* Introduction */}
            {(novel.introduction || editing) && (
              <DetailSection label={t("introduction")}>
                {editing ? (
                  <textarea
                    className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
                    value={editData.introduction ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({ ...prev, introduction: e.target.value }))
                    }
                  />
                ) : (
                  <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                    {novel.introduction}
                  </p>
                )}
              </DetailSection>
            )}

            {/* Worldview */}
            {novel.worldview && (
              <DetailSection label={t("worldview")}>
                <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                  {novel.worldview}
                </p>
              </DetailSection>
            )}

            {/* Writing Style / POV / Era */}
            <div className="grid grid-cols-3 gap-4">
              {novel.writing_style && (
                <DetailSection label={t("writingStyle")}>
                  <p className="text-sm text-foreground/80">{novel.writing_style}</p>
                </DetailSection>
              )}
              {novel.narrative_pov && (
                <DetailSection label={t("narrativePov")}>
                  <p className="text-sm text-foreground/80">{novel.narrative_pov}</p>
                </DetailSection>
              )}
              {novel.era_background && (
                <DetailSection label={t("eraBackground")}>
                  <p className="text-sm text-foreground/80">{novel.era_background}</p>
                </DetailSection>
              )}
            </div>
          </div>
        </Card.Content>
      </Card>
    </div>
  );
}

function DetailSection({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1">
        {label}
      </h3>
      {children}
    </div>
  );
}
