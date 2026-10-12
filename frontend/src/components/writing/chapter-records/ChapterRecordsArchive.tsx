"use client";

import { useContext, useEffect, useState } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiGet } from "@/lib/api";
import type { ChapterEventReadV1, ChapterReportReadV1, EntityStateHistoryReadV1 } from "@/types/chapterRecords";
import type { ItemFactRecordV1 } from "@/types/itemFacts";
import ChapterRecords from "./ChapterRecords";

/**
 * 功能：从书架只读查看章后记录，来源书或上级已回收时仍可进入。
 * Args: novelId 小说 ID；novelTitle 书名；open 打开状态；onClose 关闭回调。
 * Returns: 已有记录的来源章节选择器及只读记录弹层。
 */
export default function ChapterRecordsArchive({ novelId, novelTitle, open, onClose }: {
  novelId: string;
  novelTitle: string;
  open: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("writing.chapterRecords");
  const active = useContext(RetainedViewActive);
  const [chapters, setChapters] = useState<{ id: string; excerpt: string }[]>([]);
  const [chapterId, setChapterId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!open || !active) return;
    const abort = new AbortController();
    const base = `/api/chapter-records/novel/${novelId}`;
    // 层级目录不读取已回收的上级，直接从保存的记录取得真实来源章。
    Promise.all([
      apiGet<ChapterEventReadV1[]>(`${base}/events`, { signal: abort.signal }),
      apiGet<ChapterReportReadV1[]>(`${base}/reports`, { signal: abort.signal }),
      apiGet<EntityStateHistoryReadV1[]>(`${base}/state-history`, { signal: abort.signal }),
      (async () => {
        const records: ItemFactRecordV1[] = [];
        let page: ItemFactRecordV1[];
        do {
          page = await apiGet<ItemFactRecordV1[]>(`${base}/item-facts/history?limit=100${records.length ? `&before_id=${records.at(-1)!.history_id}` : ""}`, { signal: abort.signal });
          records.push(...page);
        } while (page.length === 100);
        return records;
      })(),
    ]).then(([events, reports, history, itemHistory]) => {
      if (abort.signal.aborted) return;
      const sources = new Map<string, string>();
      for (const record of [...events, ...reports, ...history]) {
        if (sources.has(record.evidence.chapter_id)) continue;
        // 摘录仅用于辨认记录，不当作当前章节名称。
        const excerpt = "title" in record ? record.title : "summary" in record ? record.summary : record.entity_type === "item" ? record.evidence.quote : record.entity_type === "character_relation" ? record.after.current_state : record.after.psychological_state;
        sources.set(record.evidence.chapter_id, Array.from(excerpt.replace(/\s+/g, " ")).slice(0, 60).join(""));
      }
      for (const record of itemHistory) {
        if (sources.has(record.position.target_id)) continue;
        const excerpt = `${record.item_name} · ${record.source.kind === "chapter" ? record.source.evidence.quote : record.source.note}`;
        sources.set(record.position.target_id, Array.from(excerpt.replace(/\s+/g, " ")).slice(0, 60).join(""));
      }
      const next = Array.from(sources, ([id, excerpt]) => ({ id, excerpt }));
      setChapters(next);
      setError("");
      setChapterId((current) => next.some((chapter) => chapter.id === current) ? current : next[0]?.id ?? "");
    }).catch((failure) => {
      if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : t("archiveLoadFailed"));
    }).finally(() => {
      if (!abort.signal.aborted) setLoading(false);
    });
    return () => abort.abort();
  }, [novelId, open, active, reload, t]);

  return <RetainedModalBackdrop isOpen={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
    <Modal.Container scroll="inside" size="cover" className="p-0 sm:px-6">
      <Modal.Dialog data-testid="chapter-records-archive" className="flex h-[100dvh] max-h-none w-full min-w-0 max-w-6xl flex-col sm:h-[90dvh]">
        <Modal.Header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
          <Modal.Heading className="min-w-0 break-words text-base font-semibold">{t("archiveTitle")} · {novelTitle}</Modal.Heading>
          <Modal.CloseTrigger aria-label={t("archiveClose")} />
        </Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 sm:px-6" tabIndex={0} aria-label={t("archiveTitle")}>
          {loading && <p role="status" className="py-4 text-sm text-muted">{t("loading")}</p>}
          {error && <div className="flex flex-wrap items-center gap-3 border-y border-red-300 py-3 text-sm text-red-700 dark:border-red-800 dark:text-red-300" role="alert">
            <p className="min-w-0 break-words">{error}</p>
            <Button variant="outline" size="sm" onPress={() => { setLoading(true); setError(""); setReload((value) => value + 1); }}>{t("archiveRetry")}</Button>
          </div>}
          {!loading && !error && chapters.length === 0 && <p className="border border-dashed border-border px-4 py-8 text-center text-sm text-muted">{t("archiveEmpty")}</p>}
          {chapters.length > 0 && <div className="workspace-toolbar mb-3">
            <label className="grid min-w-0 flex-1 gap-1 text-xs text-muted">{t("archiveChapter")}
              <select className="min-h-11 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3 py-2 text-sm text-foreground focus:border-accent focus:ring-2 focus:ring-accent/15" value={chapterId} onChange={(event) => setChapterId(event.target.value)}>
                {chapters.map((chapter) => <option key={chapter.id} value={chapter.id}>{t("archiveChapterOption", { id: chapter.id.slice(-8) })}{chapter.excerpt ? ` · ${chapter.excerpt}` : ""}</option>)}
              </select>
            </label>
          </div>}
          {chapterId && <ChapterRecords key={`${novelId}:${chapterId}`} novelId={novelId} chapterId={chapterId} readOnly />}
        </Modal.Body>
      </Modal.Dialog>
    </Modal.Container>
  </RetainedModalBackdrop>;
}
