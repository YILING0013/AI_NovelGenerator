"use client";

import { useState, useEffect, useCallback, useContext, useRef } from "react";
import { useTranslations } from "next-intl";
import { apiGet, apiDelete } from "@/lib/api";
import type { NovelSummary, NovelDetail } from "@/types/novel";
import NovelList from "./NovelList";
import NovelDetailPanel from "./NovelDetail";
import NewNovelPanel from "./NewNovelPanel";
import TrashBin from "./TrashBin";
import { RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";
import { subscribeResourceChanges } from "@/lib/resourceChanges";

type RightPanel = "detail" | "new";

export default function BookshelfContent() {
  const t = useTranslations("bookshelf");
  const active = useContext(RetainedViewActive);
  const [novels, setNovels] = useState<NovelSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNovel, setSelectedNovel] = useState<NovelDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [rightPanel, setRightPanel] = useState<RightPanel>("detail");
  const [newSession, setNewSession] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [trashOpen, setTrashOpen] = useState(false);
  const detailPanelRef = useRef<HTMLDivElement>(null);
  const focusDetailPending = useRef(false);
  const returnToNovelId = useRef<string | null>(null);
  const listRequest = useRef(0);

  const fetchNovels = useCallback(async () => {
    // 以最近一次读取为准，避免创建前的慢请求覆盖返回后的列表。
    const request = ++listRequest.current;
    try {
      setLoading(true);
      setLoadError("");
      const res = await apiGet<{ data: NovelSummary[] }>("/api/novels/list");
      if (request === listRequest.current) setNovels(res.data);
    } catch (error) {
      if (request === listRequest.current) setLoadError(error instanceof Error ? error.message : t("loadFailed"));
    } finally {
      if (request === listRequest.current) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (!active) return;
    // 书架常驻：返回时读当前列表，保存通知只刷新列表，不重建创建稿。
    void fetchNovels();
    const unsubscribe = subscribeResourceChanges(() => { void fetchNovels(); });
    return () => { unsubscribe(); listRequest.current += 1; };
  }, [active, fetchNovels]);

  useEffect(() => {
    if (rightPanel !== "detail") return;
    // 窄屏清单会隐藏，等正文挂载后再交接焦点；宽屏继续留在书行。
    if (focusDetailPending.current && selectedId && selectedNovel && !detailLoading) {
      if (!window.matchMedia("(min-width: 768px)").matches) {
        detailPanelRef.current?.querySelector<HTMLElement>("article")?.focus();
      }
      focusDetailPending.current = false;
    }
    if (!selectedId && returnToNovelId.current) {
      document.getElementById(`bookshelf-novel-${returnToNovelId.current}`)?.focus();
      returnToNovelId.current = null;
    }
  }, [selectedId, selectedNovel, detailLoading, rightPanel]);

  const handleSelect = async (id: string) => {
    focusDetailPending.current = !window.matchMedia("(min-width: 768px)").matches;
    setSelectedId(id);
    setRightPanel("detail");
    try {
      setDetailLoading(true);
      const novel = await apiGet<NovelDetail>(`/api/novels/${id}`);
      setSelectedNovel(novel);
    } catch {
      setSelectedNovel(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleNewNovel = () => {
    setSelectedId(null);
    setSelectedNovel(null);
    setRightPanel("new");
  };

  const handleDelete = async (id: string, expectedVersion: number) => {
    await apiDelete(`/api/novels/${id}?expected_version=${expectedVersion}`);
    await fetchNovels();
    if (selectedId === id) {
      setSelectedId(null);
      setSelectedNovel(null);
    }
  };

  const handleNovelCreated = async (novelId: string) => {
    await fetchNovels();
    await handleSelect(novelId);
  };

  return (
    <div className="grid h-[calc(100dvh-3.5rem)] min-h-0 min-w-0 gap-4 overflow-hidden bg-background p-4 md:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[296px_minmax(0,1fr)] sm:gap-5 sm:p-6">
      <h1 className="sr-only">{t("title")}</h1>
      <div className={`${rightPanel === "new" || selectedId ? "hidden md:flex" : "flex"} min-h-0 min-w-0 flex-col`}>
        <NovelList
          novels={novels}
          selectedId={selectedId}
          loading={loading}
          error={loadError}
          onSelect={handleSelect}
          onNewNovel={handleNewNovel}
          onOpenTrash={() => setTrashOpen(true)}
          onRetry={fetchNovels}
        />
      </div>

      <div ref={detailPanelRef} className={`${rightPanel === "new" || selectedId ? "block" : "hidden md:block"} min-h-0 min-w-0 overflow-hidden rounded-xl border border-border bg-surface`}>
        <RetainedViews activeKey={rightPanel}>
        {rightPanel === "new" ? (
          <NewNovelPanel
            key={newSession}
            onCreated={handleNovelCreated}
            onCancel={() => {
              setNewSession((current) => current + 1);
              setRightPanel("detail");
              setSelectedId(null);
            }}
          />
        ) : (
          <NovelDetailPanel
            novel={selectedNovel}
            loading={detailLoading}
            onDelete={handleDelete}
            onBack={() => {
              returnToNovelId.current = selectedId;
              focusDetailPending.current = false;
              setSelectedId(null);
            }}
          />
        )}
        </RetainedViews>
      </div>

      <TrashBin
        open={trashOpen}
        onClose={() => setTrashOpen(false)}
        onRestored={fetchNovels}
      />
    </div>
  );
}
