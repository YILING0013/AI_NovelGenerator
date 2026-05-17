"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Button } from "@heroui/react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  CreateNovelRequest,
  NovelDetail,
  NovelRewriteFieldKey,
  WritingDraft,
  WritingDraftRewriteState,
} from "@/types/novel";
import { clearWritingDraft, loadWritingDraft, updateWritingDraft } from "@/lib/writingDraft";
import { normalizeRewriteState } from "@/lib/rewriteDraftState";
import NovelInfoSection, { type SectionKey } from "./NovelInfoSection";
import NovelRewriteAssistant from "./NovelRewriteAssistant";
import StickyActionBar from "./StickyActionBar";

const SECTIONS: SectionKey[] = ["basic", "creative", "scale", "content", "style"];

interface NovelInfoWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
}

export default function NovelInfoWorkspace({ mode, novelId }: NovelInfoWorkspaceProps) {
  const tw = useTranslations("writing.novelInfo");
  const twd = useTranslations("writing");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const draftId = searchParams.get("draft") || undefined;
  const didLoadDraftRef = useRef(false);

  /* state */
  const [data, setData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(mode === "edit");
  const [loadError, setLoadError] = useState(false);
  const [noDraft, setNoDraft] = useState(false);
  const [editingSection, setEditingSection] = useState<SectionKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [hasChapters, setHasChapters] = useState(false);

  /* danger confirm */
  const [showDangerModal, setShowDangerModal] = useState(false);
  const [dangerResolve, setDangerResolve] = useState<((v: boolean) => void) | null>(null);

  const persistCreateDraft = useCallback(
    (nextData: Record<string, unknown>) => {
      if (mode !== "create") {
        return;
      }

      updateWritingDraft(draftId, (draft) => ({
        ...draft,
        ...(nextData as Partial<WritingDraft>),
      }));
    },
    [draftId, mode],
  );

  const updateCreateData = useCallback(
    (updater: (prev: Record<string, unknown>) => Record<string, unknown>) => {
      setData((prev) => {
        const nextData = updater(prev);
        // 创建态表单是本地草稿驱动，任何字段和改写状态变化都立即写回草稿。
        persistCreateDraft(nextData);
        return nextData;
      });
    },
    [persistCreateDraft],
  );

  /* load data */
  const loadNovel = useCallback(async () => {
    if (!novelId) return;
    try {
      setLoading(true);
      setLoadError(false);
      const novel = await apiGet<NovelDetail>(`/api/novels/${novelId}`);
      setData(novel as unknown as Record<string, unknown>);
      setHasChapters((novel.stats?.chapter_count ?? 0) > 0);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [novelId]);

  useEffect(() => {
    if (mode === "edit") {
      loadNovel();
      return;
    }

    if (didLoadDraftRef.current) {
      return;
    }
    didLoadDraftRef.current = true;

    const draft: WritingDraft | null = loadWritingDraft(draftId);
    if (draft) {
      setData(draft as unknown as Record<string, unknown>);
      setNoDraft(false);
    } else {
      setNoDraft(true);
    }
  }, [mode, loadNovel, draftId]);

  /* create novel */
  const handleCreate = async () => {
    try {
      setCreating(true);
      const payload: CreateNovelRequest = {
        title: String(data.title || ""),
        subtitle: data.subtitle ? String(data.subtitle) : undefined,
        genre: data.genre ? String(data.genre) : undefined,
        tags: Array.isArray(data.tags) ? data.tags : undefined,
        introduction: data.introduction ? String(data.introduction) : undefined,
        summary: data.summary ? String(data.summary) : undefined,
        core_seed: data.core_seed ? String(data.core_seed) : undefined,
        worldview: data.worldview ? String(data.worldview) : undefined,
        writing_style: data.writing_style ? String(data.writing_style) : undefined,
        narrative_pov: data.narrative_pov ? String(data.narrative_pov) : undefined,
        era_background: data.era_background ? String(data.era_background) : undefined,
        cover_image: data.cover_image ? String(data.cover_image) : undefined,
        plot: data.plot ? String(data.plot) : undefined,
        tone: data.tone ? String(data.tone) : undefined,
        target_audience: data.target_audience ? String(data.target_audience) : undefined,
        core_idea: data.core_idea ? String(data.core_idea) : undefined,
        number_of_chapters: data.number_of_chapters ? Number(data.number_of_chapters) : undefined,
        words_per_chapter: data.words_per_chapter ? Number(data.words_per_chapter) : undefined,
      };
      const res = await apiPost<{ id: string }>("/api/novels/create", payload);
      clearWritingDraft(draftId);
      router.push(`/${locale}/writing/${res.id}`);
    } catch {
      alert(tw("createFailed"));
    } finally {
      setCreating(false);
    }
  };

  /* field change (create mode) */
  const handleFieldChange = (field: string, value: unknown) => {
    updateCreateData((prev) => ({ ...prev, [field]: value }));
  };

  const handleRewriteStateChange = (rewriteState: WritingDraftRewriteState) => {
    updateCreateData((prev) => ({
      ...prev,
      _rewriteState: normalizeRewriteState(rewriteState),
    }));
  };

  const handleApplyRewrite = (
    field: NovelRewriteFieldKey,
    value: string | string[],
    rewriteState: WritingDraftRewriteState,
  ) => {
    updateCreateData((prev) => ({
      ...prev,
      [field]: value,
      _rewriteState: normalizeRewriteState(rewriteState),
    }));
  };

  /* danger confirm promise */
  const requestDangerConfirm = (): Promise<boolean> => {
    return new Promise((resolve) => {
      setDangerResolve(() => resolve);
      setShowDangerModal(true);
    });
  };

  const handleDangerResponse = (confirmed: boolean) => {
    setShowDangerModal(false);
    dangerResolve?.(confirmed);
    setDangerResolve(null);
  };

  /* render */

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted">{twd("loading")}</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-muted">{twd("loadFailed")}</p>
        <Button variant="outline" onPress={loadNovel}>{tw("saveSection")}</Button>
      </div>
    );
  }

  if (mode === "create" && noDraft) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-muted">{tw("noDraft")}</p>
        <Button
          variant="outline"
          onPress={() => {
            clearWritingDraft(draftId);
            router.push(`/${locale}`);
          }}
        >
          {twd("backToCreate")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Danger Confirm Modal */}
      {showDangerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-background rounded-xl shadow-xl p-6 max-w-md mx-4 border border-border">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-warning/10 flex items-center justify-center shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-warning">
                  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
                  <path d="M12 9v4" /><path d="M12 17h.01" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-foreground">{twd("dangerEditTitle")}</h3>
            </div>
            <p className="text-sm text-muted mb-5">{twd("dangerEditMessage")}</p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onPress={() => handleDangerResponse(false)}>
                {twd("cancel")}
              </Button>
              <Button variant="primary" size="sm" className="bg-accent text-white hover:bg-accent-hover" onPress={() => handleDangerResponse(true)}>
                {twd("confirmContinue")}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="px-6 py-4 border-b border-border">
        <h2 className="text-lg font-bold text-foreground">
          {mode === "create" ? tw("createTitle") : tw("editTitle")}
        </h2>
        {mode === "create" && (
          <p className="text-sm text-muted mt-1">{tw("createDescription")}</p>
        )}
      </div>

      {/* Sections */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {SECTIONS.map((sk) => (
          <NovelInfoSection
            key={sk}
            sectionKey={sk}
            data={data}
            novelId={novelId}
            isCreateMode={mode === "create"}
            isEditing={mode === "create" || editingSection === sk}
            onStartEdit={() => setEditingSection(sk)}
            onCancelEdit={() => setEditingSection(null)}
            onSaved={() => {
              setEditingSection(null);
              loadNovel();
            }}
            onChange={mode === "create" ? handleFieldChange : undefined}
            hasChapters={hasChapters}
            onDangerConfirm={requestDangerConfirm}
          />
        ))}
      </div>

      {/* Sticky action bar - create mode */}
      {mode === "create" && (
        <StickyActionBar>
          <Button
            variant="ghost"
            onPress={() => {
              clearWritingDraft(draftId);
              router.push(`/${locale}`);
            }}
          >
            {twd("backToCreate")}
          </Button>
          <Button
            variant="primary"
            onPress={handleCreate}
            isDisabled={creating || !data.title}
            className="bg-accent text-white hover:bg-accent-hover"
          >
            {creating ? tw("creating") : tw("saveCreate")}
          </Button>
        </StickyActionBar>
      )}

      {mode === "create" && (
        <NovelRewriteAssistant
          data={data}
          rewriteState={normalizeRewriteState(data._rewriteState as WritingDraftRewriteState | undefined)}
          onApplyRewrite={handleApplyRewrite}
          onRewriteStateChange={handleRewriteStateChange}
        />
      )}
    </div>
  );
}
