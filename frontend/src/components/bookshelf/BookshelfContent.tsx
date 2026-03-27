"use client";

import { useState, useEffect, useCallback } from "react";
import { apiGet, apiDelete } from "@/lib/api";
import type { NovelSummary, NovelDetail } from "@/types/novel";
import NovelList from "./NovelList";
import NovelDetailPanel from "./NovelDetail";
import NewNovelPanel from "./NewNovelPanel";

type RightPanel = "detail" | "new";

export default function BookshelfContent() {
  const [novels, setNovels] = useState<NovelSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNovel, setSelectedNovel] = useState<NovelDetail | null>(null);
  const [rightPanel, setRightPanel] = useState<RightPanel>("detail");
  const [loading, setLoading] = useState(true);

  const fetchNovels = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiGet<{ data: NovelSummary[] }>("/api/novels/list");
      setNovels(res.data);
    } catch {
      // silently handle
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNovels();
  }, [fetchNovels]);

  const handleSelect = async (id: string) => {
    setSelectedId(id);
    setRightPanel("detail");
    try {
      const novel = await apiGet<NovelDetail>(`/api/novels/${id}`);
      setSelectedNovel(novel);
    } catch {
      setSelectedNovel(null);
    }
  };

  const handleNewNovel = () => {
    setSelectedId(null);
    setSelectedNovel(null);
    setRightPanel("new");
  };

  const handleDelete = async (id: string) => {
    try {
      await apiDelete(`/api/novels/${id}`);
      await fetchNovels();
      if (selectedId === id) {
        setSelectedId(null);
        setSelectedNovel(null);
      }
    } catch {
      // handle error
    }
  };

  const handleNovelCreated = async (novelId: string) => {
    await fetchNovels();
    await handleSelect(novelId);
  };

  return (
    <div className="mx-auto max-w-7xl h-[calc(100vh-3.5rem)] flex gap-4 p-4">
      {/* Left: Novel List (3/10) */}
      <div className="w-[30%] min-w-[280px] flex flex-col">
        <NovelList
          novels={novels}
          selectedId={selectedId}
          loading={loading}
          onSelect={handleSelect}
          onNewNovel={handleNewNovel}
        />
      </div>

      {/* Right: Detail / New Panel (7/10) */}
      <div className="flex-1 min-w-0">
        {rightPanel === "new" ? (
          <NewNovelPanel
            onCreated={handleNovelCreated}
            onCancel={() => setRightPanel("detail")}
          />
        ) : (
          <NovelDetailPanel
            novel={selectedNovel}
            onDelete={handleDelete}
            onUpdated={() => {
              if (selectedId) handleSelect(selectedId);
              fetchNovels();
            }}
          />
        )}
      </div>
    </div>
  );
}
