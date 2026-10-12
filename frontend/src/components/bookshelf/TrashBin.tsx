"use client";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { useState, useEffect, useCallback } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Button, Chip, Modal } from "@heroui/react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { ConfirmActionModal } from "@/components/shared/RelationEditorPrimitives";
import { parseNovelHistoryDeleteImpact, type NovelHistoryDeleteImpact, type NovelSummary } from "@/types/novel";
import ForeshadowingsWorkspace from "@/components/writing/foreshadowings/ForeshadowingsWorkspace";
import ChapterRecordsArchive from "@/components/writing/chapter-records/ChapterRecordsArchive";

type DeletedNovel = NovelSummary;

interface TrashBinProps {
  open: boolean;
  onClose: () => void;
  onRestored: () => void;
}

export default function TrashBin({ open, onClose, onRestored }: TrashBinProps) {
  const t = useTranslations("bookshelf");
  const tn = useTranslations("novel");
  const locale = useLocale();
  const [novels, setNovels] = useState<DeletedNovel[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [hardDeleteTarget, setHardDeleteTarget] = useState<DeletedNovel | null>(null);
  const [historyImpact, setHistoryImpact] = useState<NovelHistoryDeleteImpact | null>(null);
  const [cleanupNovel, setCleanupNovel] = useState<DeletedNovel | null>(null);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [recordsNovel, setRecordsNovel] = useState<DeletedNovel | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);

  useEffect(() => {
    if (!hardDeleteTarget) return;
    let current = true;
    setHistoryImpact(null); setImpactLoading(true); setError("");
    apiGet<unknown>(`/api/novels/${hardDeleteTarget.id}/delete-impact`).then((result) => {
      if (!current) return;
      const impact = parseNovelHistoryDeleteImpact(result, hardDeleteTarget.id);
      if (!impact) throw new Error(t("deleteImpactInvalid"));
      if (impact.version !== hardDeleteTarget.version) throw new Error(t("historyChanged"));
      setHistoryImpact(impact);
    }).catch((failure) => { if (current) setError(failure instanceof Error ? failure.message : t("trashLoadFailed")); })
      .finally(() => { if (current) setImpactLoading(false); });
    return () => { current = false; };
  }, [hardDeleteTarget, t]);

  const fetchDeleted = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const res = await apiGet<{ data: DeletedNovel[] }>("/api/novels/deleted/list");
      setNovels(res.data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("trashLoadFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (open) fetchDeleted();
  }, [open, fetchDeleted]);

  const handleRestore = async (novel: DeletedNovel) => {
    try {
      setActionLoading(novel.id);
      setError("");
      await apiPost(`/api/novels/${novel.id}/restore`, { expected_version: novel.version });
      setNovels((prev) => prev.filter((item) => item.id !== novel.id));
      onRestored();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("restoreFailed"));
    } finally {
      setActionLoading(null);
    }
  };

  const handleHardDelete = async () => {
    if (!hardDeleteTarget || !historyImpact || historyImpact.foreshadowings > 0) return;
    try {
      setActionLoading(hardDeleteTarget.id);
      setError("");
      await apiDelete(`/api/novels/${hardDeleteTarget.id}/hard?expected_version=${historyImpact.version}&expected_revision_count=${historyImpact.revision_count}`, {
        data: historyImpact.chapter_records,
      });
      setNovels((prev) => prev.filter((item) => item.id !== hardDeleteTarget.id));
      setHardDeleteTarget(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("hardDeleteFailed"));
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <>
      <RetainedModalBackdrop
        isOpen={open && !cleanupNovel}
        onOpenChange={(isOpen) => !isOpen && actionLoading === null && onClose()}
        variant="blur"
        isDismissable={actionLoading === null}
      >
        <Modal.Container size="lg" scroll="inside" className="px-3 sm:px-6">
          <Modal.Dialog className="w-full max-w-2xl">
            <Modal.Header className="flex items-center justify-between border-b border-border px-5 py-4 sm:px-6">
          <div className="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted">
              <path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
            </svg>
                <Modal.Heading className="text-lg font-semibold text-foreground">{t("trashBin")}</Modal.Heading>
                <span className="text-xs tabular-nums text-muted">({novels.length})</span>
          </div>
              <Modal.CloseTrigger aria-label={t("closeTrash")} isDisabled={actionLoading !== null} />
            </Modal.Header>

            <Modal.Body className="min-h-0 px-5 py-5 sm:px-6">
          {error && (
            <div className="mb-4 border-y border-red-300 py-3 text-sm text-red-700 dark:border-red-800 dark:text-red-300" role="alert">
              {error}
            </div>
          )}
          {loading ? (
            <div className="flex items-center justify-center gap-3 py-12" role="status">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              <span className="text-sm text-muted">{t("loading")}</span>
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
            <ul className="divide-y divide-border">
              {novels.map((novel) => (
                <li key={novel.id} className="flex min-w-0 flex-col gap-3 py-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground truncate">
                            {novel.title}
                          </span>
                          {novel.genre !== "unclassified" && (
                            <Chip variant="soft" size="sm">{novel.genre}</Chip>
                          )}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                          <span>{tn("chapterCount")}: {new Intl.NumberFormat(locale).format(novel.stats.chapter_count)}</span>
                          <span>{tn("totalWords")}: {new Intl.NumberFormat(locale).format(novel.stats.total_word_count)}</span>
                          {novel.deleted_at && (
                            <span>{t("deletedAt")}: {new Intl.DateTimeFormat(locale).format(new Date(novel.deleted_at))}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex min-w-0 flex-wrap gap-2">
                        <Button variant="outline" size="sm" isDisabled={actionLoading !== null} onPress={() => setRecordsNovel(novel)}>{t("viewChapterRecords")}</Button>
                        <Button variant="outline" size="sm" isDisabled={actionLoading !== null} onPress={() => setCleanupNovel(novel)}>{t("cleanupForeshadowings")}</Button>
                        <Button
                          variant="outline"
                          size="sm"
                          isDisabled={actionLoading === novel.id}
                          onPress={() => handleRestore(novel)}
                        >
                          {t("restore")}
                        </Button>
                        <Button
                          variant="danger-soft"
                          size="sm"
                          isDisabled={actionLoading === novel.id}
                          onPress={() => {
                            setError("");
                            setHardDeleteTarget(novel);
                          }}
                        >
                          {t("hardDelete")}
                        </Button>
                      </div>
                </li>
              ))}
            </ul>
          )}
            </Modal.Body>
          </Modal.Dialog>
        </Modal.Container>
      </RetainedModalBackdrop>

      {recordsNovel && <ChapterRecordsArchive key={recordsNovel.id} novelId={recordsNovel.id} novelTitle={recordsNovel.title} open={open} onClose={() => setRecordsNovel(null)} />}

      {hardDeleteTarget && (
        <ConfirmActionModal
          title={t("hardDeleteTitle")}
          message={<>
            <p>{t("hardDeleteConfirm", { title: hardDeleteTarget.title })}</p>
            {historyImpact ? <>
              <p className="mt-2">{t("historyDeleteImpact", { count: historyImpact.revision_count })}</p>
              <p className="mt-2">{t("chapterRecordsDeleteImpact", { ...historyImpact.chapter_records })}</p>
              <p className="mt-2">{t("exportedBackupsRemain")}</p>
              {historyImpact.foreshadowings > 0 && <div className="mt-2"><p>{t("foreshadowingDeleteBlocked", { count: historyImpact.foreshadowings })}</p><Button variant="outline" onPress={() => { setCleanupNovel(hardDeleteTarget); setHardDeleteTarget(null); }}>{t("cleanupForeshadowings")}</Button></div>}
            </> : impactLoading && <p className="mt-2">{t("loading")}</p>}
          </>}
          confirmText={t("hardDelete")}
          cancelText={tn("cancel")}
          loadingText={t("deleting")}
          danger
          error={error}
          isLoading={actionLoading === hardDeleteTarget.id}
          isConfirmDisabled={impactLoading || !historyImpact || historyImpact.foreshadowings > 0}
          onCancel={() => {
            setHardDeleteTarget(null);
            setError("");
          }}
          onConfirm={handleHardDelete}
        />
      )}
      {cleanupNovel && <RetainedModalBackdrop isOpen={open} onOpenChange={(isOpen) => !isOpen && !cleanupBusy && setCleanupNovel(null)} isDismissable={!cleanupBusy}><Modal.Container scroll="inside" size="cover"><Modal.Dialog className="flex h-[90dvh] w-full max-w-6xl flex-col"><Modal.Header className="px-5 py-4"><Modal.Heading>{cleanupNovel.title}</Modal.Heading><Modal.CloseTrigger aria-label={t("closeTrash")} isDisabled={cleanupBusy} /></Modal.Header><Modal.Body className="flex min-h-0 flex-1 flex-col p-0"><ForeshadowingsWorkspace key={cleanupNovel.id} novelId={cleanupNovel.id} cleanupOnly onBusyChange={setCleanupBusy} /></Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
    </>
  );
}
