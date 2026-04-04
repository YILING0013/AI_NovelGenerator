"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslations } from "next-intl";
import { Card, Button, Chip } from "@heroui/react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import type { NovelSummary } from "@/types/novel";

interface DeletedNovel extends NovelSummary {
  deleted_at?: string;
}

interface TrashBinProps {
  open: boolean;
  onClose: () => void;
  onRestored: () => void;
}

export default function TrashBin({ open, onClose, onRestored }: TrashBinProps) {
  const t = useTranslations("bookshelf");
  const tn = useTranslations("novel");
  const [novels, setNovels] = useState<DeletedNovel[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchDeleted = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiGet<{ data: DeletedNovel[] }>("/api/novels/deleted/list");
      setNovels(res.data);
    } catch {
      // handle error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchDeleted();
  }, [open, fetchDeleted]);

  const handleRestore = async (id: string) => {
    try {
      setActionLoading(id);
      await apiPost(`/api/novels/${id}/restore`, {});
      setNovels((prev) => prev.filter((n) => n._id !== id));
      onRestored();
    } catch {
      // handle error
    } finally {
      setActionLoading(null);
    }
  };

  const handleHardDelete = async (id: string, title: string) => {
    if (!confirm(t("hardDeleteConfirm", { title }))) return;
    try {
      setActionLoading(id);
      await apiDelete(`/api/novels/${id}/hard`);
      setNovels((prev) => prev.filter((n) => n._id !== id));
    } catch {
      // handle error
    } finally {
      setActionLoading(null);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-background rounded-xl shadow-xl w-full max-w-2xl mx-4 border border-border flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted">
              <path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
            </svg>
            <h2 className="text-lg font-semibold text-foreground">{t("trashBin")}</h2>
            <span className="text-xs text-muted">({novels.length})</span>
          </div>
          <button
            className="text-muted hover:text-foreground transition-colors"
            onClick={onClose}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18" /><path d="m6 6 12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent" />
            </div>
          ) : novels.length === 0 ? (
            <div className="text-center text-muted py-12">
              <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="mx-auto mb-3 opacity-30">
                <path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
                <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
              </svg>
              <p className="text-sm">{t("trashEmpty")}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {novels.map((novel) => (
                <Card key={novel._id} className="transition-all">
                  <Card.Header>
                    <div className="flex items-center justify-between w-full">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground truncate">
                            {novel.title}
                          </span>
                          {novel.genre !== "unclassified" && (
                            <Chip variant="soft" size="sm">{novel.genre}</Chip>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-muted">
                          <span>{tn("chapterCount")}: {novel.stats?.chapter_count ?? 0}</span>
                          <span>{tn("totalWords")}: {(novel.stats?.total_word_count ?? 0).toLocaleString()}</span>
                          {novel.deleted_at && (
                            <span>{t("deletedAt")}: {new Date(novel.deleted_at).toLocaleDateString()}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-2 shrink-0 ml-4">
                        <Button
                          variant="outline"
                          size="sm"
                          isDisabled={actionLoading === novel._id}
                          onPress={() => handleRestore(novel._id)}
                        >
                          {t("restore")}
                        </Button>
                        <Button
                          variant="danger-soft"
                          size="sm"
                          isDisabled={actionLoading === novel._id}
                          onPress={() => handleHardDelete(novel._id, novel.title)}
                        >
                          {t("hardDelete")}
                        </Button>
                      </div>
                    </div>
                  </Card.Header>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
