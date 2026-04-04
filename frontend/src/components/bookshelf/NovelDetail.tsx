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

/** Fields that may cause irreversible impact when volumes/chapters exist */
const DANGEROUS_FIELDS: (keyof NovelDetail)[] = [
  "summary",
  "core_seed",
  "worldview",
  "writing_style",
  "narrative_pov",
  "era_background",
];

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
  const [showDangerConfirm, setShowDangerConfirm] = useState(false);

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

  const hasChaptersOrVolumes = (novel.stats?.chapter_count ?? 0) > 0;

  const statusKey = `status${novel.status.charAt(0).toUpperCase()}${novel.status.slice(1)}` as
    | "statusDraft"
    | "statusOngoing"
    | "statusCompleted"
    | "statusPaused";

  const startEdit = () => {
    setEditData({
      title: novel.title,
      subtitle: novel.subtitle ?? "",
      genre: novel.genre ?? "unclassified",
      tags: novel.tags ?? [],
      introduction: novel.introduction ?? "",
      summary: novel.summary ?? "",
      core_seed: novel.core_seed ?? "",
      worldview: novel.worldview ?? "",
      writing_style: novel.writing_style ?? "",
      narrative_pov: novel.narrative_pov ?? "",
      era_background: novel.era_background ?? "",
    });
    setEditing(true);
  };

  const hasDangerousChanges = (): boolean => {
    if (!hasChaptersOrVolumes) return false;
    return DANGEROUS_FIELDS.some((field) => {
      const original = novel[field] ?? "";
      const edited = editData[field] ?? "";
      return original !== edited;
    });
  };

  const doSave = async () => {
    try {
      setSaving(true);
      await apiPut(`/api/novels/${novel._id}`, editData);
      setEditing(false);
      setShowDangerConfirm(false);
      onUpdated();
    } catch {
      // handle error
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (hasDangerousChanges()) {
      setShowDangerConfirm(true);
      return;
    }
    await doSave();
  };

  const handleDeleteClick = () => {
    if (confirm(tb("deleteConfirm", { title: novel.title }))) {
      onDelete(novel._id);
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      {/* Danger Confirm Modal */}
      {showDangerConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-background rounded-xl shadow-xl p-6 max-w-md mx-4 border border-border">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-warning">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                  <path d="M12 9v4" /><path d="M12 17h.01" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-foreground">{t("dangerEditTitle")}</h3>
            </div>
            <p className="text-sm text-muted mb-5">{t("dangerEditMessage")}</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onPress={() => setShowDangerConfirm(false)}>
                {t("cancel")}
              </Button>
              <Button variant="primary" size="sm" isDisabled={saving} onPress={doSave}>
                {t("confirmContinue")}
              </Button>
            </div>
          </div>
        </div>
      )}

      <Card className="min-h-full">
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
                {editing ? (
                  <div className="space-y-2">
                    <input
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xl font-bold text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      value={editData.title ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, title: e.target.value }))
                      }
                      placeholder={t("title")}
                    />
                    <input
                      className="w-full rounded-lg border border-border bg-background px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      value={editData.subtitle ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, subtitle: e.target.value }))
                      }
                      placeholder={t("subtitle")}
                    />
                  </div>
                ) : (
                  <>
                    <h2 className="text-xl font-bold text-foreground truncate">
                      {novel.title}
                    </h2>
                    {novel.subtitle && (
                      <p className="text-sm text-muted mt-0.5">{novel.subtitle}</p>
                    )}
                  </>
                )}
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <Chip variant={STATUS_COLOR_MAP[novel.status] || "secondary"} size="sm">
                    {t(statusKey)}
                  </Chip>
                  {editing ? (
                    <input
                      className="rounded-lg border border-border bg-background px-2 py-0.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary w-32"
                      value={editData.genre ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, genre: e.target.value }))
                      }
                      placeholder={t("genre")}
                    />
                  ) : (
                    novel.genre !== "unclassified" && (
                      <Chip variant="soft" size="sm">
                        {novel.genre}
                      </Chip>
                    )
                  )}
                </div>
                {editing ? (
                  <div className="mt-2">
                    <TagEditor
                      tags={editData.tags ?? []}
                      onChange={(tags) => setEditData((prev) => ({ ...prev, tags }))}
                      placeholder={t("tags")}
                    />
                  </div>
                ) : (
                  novel.tags && novel.tags.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {novel.tags.map((tag) => (
                        <Chip key={tag} variant="tertiary" size="sm">
                          {tag}
                        </Chip>
                      ))}
                    </div>
                  )
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
                    onPress={() => { setEditing(false); setShowDangerConfirm(false); }}
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

            {/* Summary */}
            {(novel.summary || editing) && (
              <DetailSection label={t("summary")} danger={editing && hasChaptersOrVolumes}>
                {editing ? (
                  <textarea
                    className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
                    value={editData.summary ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({ ...prev, summary: e.target.value }))
                    }
                  />
                ) : (
                  <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                    {novel.summary}
                  </p>
                )}
              </DetailSection>
            )}

            {/* Core Seed */}
            {(novel.core_seed || editing) && (
              <DetailSection label={t("coreSeed")} danger={editing && hasChaptersOrVolumes}>
                {editing ? (
                  <textarea
                    className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[60px] focus:outline-none focus:ring-2 focus:ring-primary"
                    value={editData.core_seed ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({ ...prev, core_seed: e.target.value }))
                    }
                  />
                ) : (
                  <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                    {novel.core_seed}
                  </p>
                )}
              </DetailSection>
            )}

            {/* Worldview */}
            {(novel.worldview || editing) && (
              <DetailSection label={t("worldview")} danger={editing && hasChaptersOrVolumes}>
                {editing ? (
                  <textarea
                    className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[80px] focus:outline-none focus:ring-2 focus:ring-primary"
                    value={editData.worldview ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({ ...prev, worldview: e.target.value }))
                    }
                  />
                ) : (
                  <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                    {novel.worldview}
                  </p>
                )}
              </DetailSection>
            )}

            {/* Writing Style / POV / Era */}
            <div className="grid grid-cols-3 gap-4">
              {(novel.writing_style || editing) && (
                <DetailSection label={t("writingStyle")} danger={editing && hasChaptersOrVolumes}>
                  {editing ? (
                    <input
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      value={editData.writing_style ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, writing_style: e.target.value }))
                      }
                    />
                  ) : (
                    <p className="text-sm text-foreground/80">{novel.writing_style}</p>
                  )}
                </DetailSection>
              )}
              {(novel.narrative_pov || editing) && (
                <DetailSection label={t("narrativePov")} danger={editing && hasChaptersOrVolumes}>
                  {editing ? (
                    <select
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      value={editData.narrative_pov ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, narrative_pov: e.target.value }))
                      }
                    >
                      <option value="">{t("narrativePov")}</option>
                      <option value="first_person">{t("povFirst")}</option>
                      <option value="third_person_limited">{t("povThirdLimited")}</option>
                      <option value="omniscient">{t("povOmniscient")}</option>
                    </select>
                  ) : (
                    <p className="text-sm text-foreground/80">{novel.narrative_pov}</p>
                  )}
                </DetailSection>
              )}
              {(novel.era_background || editing) && (
                <DetailSection label={t("eraBackground")} danger={editing && hasChaptersOrVolumes}>
                  {editing ? (
                    <input
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      value={editData.era_background ?? ""}
                      onChange={(e) =>
                        setEditData((prev) => ({ ...prev, era_background: e.target.value }))
                      }
                    />
                  ) : (
                    <p className="text-sm text-foreground/80">{novel.era_background}</p>
                  )}
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
  danger,
}: {
  label: string;
  children: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 flex items-center gap-1">
        {label}
        {danger && (
          <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-warning">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <path d="M12 9v4" /><path d="M12 17h.01" />
          </svg>
        )}
      </h3>
      {children}
    </div>
  );
}

function TagEditor({
  tags,
  onChange,
  placeholder,
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  const addTag = () => {
    const tag = input.trim();
    if (tag && !tags.includes(tag)) {
      onChange([...tags, tag]);
    }
    setInput("");
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag));
  };

  return (
    <div>
      <div className="flex gap-1 flex-wrap mb-1">
        {tags.map((tag) => (
          <Chip key={tag} variant="tertiary" size="sm">
            {tag}
            <button
              className="ml-1 text-muted hover:text-foreground"
              onClick={() => removeTag(tag)}
            >
              ×
            </button>
          </Chip>
        ))}
      </div>
      <input
        className="w-full rounded-lg border border-border bg-background px-3 py-1 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); addTag(); }
        }}
        placeholder={placeholder}
      />
    </div>
  );
}
