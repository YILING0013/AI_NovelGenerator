"use client";
import { useAssistantRefresh, useAssistantResource, useNovelAssistant } from "@/components/writing/assistant/AssistantContext";

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { Button } from "@heroui/react";
import { ConfirmActionModal } from "@/components/shared/RelationEditorPrimitives";
import ReplacementCharacterNotice from "@/components/shared/ReplacementCharacterNotice";
import { apiGet, apiPost, apiPutForm } from "@/lib/api";
import type {
  AICreateCandidateV1,
  CreateNovelRequest,
  NovelCreateResponse,
  NovelDetail,
  NovelAIConfirmationRequest,
  NovelManualCreateRequest,
  NovelRewriteFieldKey,
  WritingDraft,
  WritingDraftRewriteState,
} from "@/types/novel";
import { clearWritingDraft, loadWritingDraft, updateWritingDraft } from "@/lib/writingDraft";
import { normalizeRewriteState } from "@/lib/rewriteDraftState";
import { CREATE_NOVEL_CONTEXT_FIELDS } from "@/lib/novelFields";
import NovelInfoSection, { type SectionKey } from "./NovelInfoSection";
import NovelRewriteAssistant from "./NovelRewriteAssistant";
import StickyActionBar from "./StickyActionBar";

const SECTIONS: SectionKey[] = ["basic", "creative", "content", "style"];

/**
 * 判断创建态复核字段是否已经有可用内容。
 *
 * Args:
 *   value: 草稿中的字段值。
 *
 * Returns:
 *   字符串、数组或数字已填写时返回 true，否则返回 false。
 */
function hasReviewValue(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "number") return Number.isFinite(value) && value > 0;
  if (typeof value === "string") return value.trim().length > 0;
  return value !== null && value !== undefined;
}

/**
 * 校验可选规模字段；空值允许保存，填写后必须为正整数。
 *
 * Args:
 *   value: 章节数或单章字数。
 *
 * Returns:
 *   空值或正整数返回 true，其他值返回 false。
 */
function isValidOptionalPositiveInteger(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

interface NovelInfoWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  query?: string;
  onFormalFactsChanged?: () => void;
}

/**
 * 渲染小说资料章节式编辑器与字段改写助手。
 *
 * Args:
 *   mode: 创建态或已保存小说编辑态。
 *   novelId: 已保存小说 ObjectId。
 *   onFormalFactsChanged: 小说保存后重新读取哪些功能可用。
 *
 * Returns:
 *   小说资料工作台 React 节点。
 */
export default function NovelInfoWorkspace({
  mode,
  novelId,
  query,
  onFormalFactsChanged,
}: NovelInfoWorkspaceProps) {
  const tw = useTranslations("writing.novelInfo");
  const twd = useTranslations("writing");
  const rewriteT = useTranslations("writing.rewriteAssistant");
  const router = useRouter();
  const pathname = usePathname();
  const routeSearchParams = useSearchParams();
  const searchParams = query === undefined ? routeSearchParams : new URLSearchParams(query);
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const draftId = searchParams.get("draft") || undefined;
  const didLoadDraftRef = useRef(false);
  const createIdempotencyRef = useRef<{ signature: string; key: string } | null>(null);

  const [data, setData] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(mode === "edit");
  const [loadError, setLoadError] = useState(false);
  const [noDraft, setNoDraft] = useState(false);
  const [editingSection, setEditingSection] = useState<SectionKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [hasChapters, setHasChapters] = useState(false);
  const [coverUploading, setCoverUploading] = useState(false);
  const [pendingCover, setPendingCover] = useState<File | null>(null);
  const [createError, setCreateError] = useState("");
  const [rewriteOpen, setRewriteOpen] = useState(false);
  const rewriteButtonRef = useRef<HTMLButtonElement>(null);

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

  const assistant = useNovelAssistant();
  useAssistantResource(mode === "edit" && novelId ? { resource_type: "novel", id: novelId, name: String(data.title ?? ""), version: Number(data.version) } : null);
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

  useAssistantRefresh(novelId, loadNovel);

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

  const handleCreate = async () => {
    if (!canCreate || coverUploading) return;
    try {
      setCreating(true);
      const candidate: AICreateCandidateV1 = {
        title: String(data.title || "").trim(),
        subtitle: data.subtitle ? String(data.subtitle) : null,
        genre: data.genre ? String(data.genre) : "unclassified",
        tags: Array.isArray(data.tags) ? data.tags.map(String) : [],
        introduction: data.introduction ? String(data.introduction) : null,
        summary: data.summary ? String(data.summary) : null,
        core_seed: data.core_seed ? String(data.core_seed) : null,
        worldview: data.worldview ? String(data.worldview) : null,
        writing_style: data.writing_style ? String(data.writing_style) : null,
        narrative_pov: data.narrative_pov ? String(data.narrative_pov) : null,
        era_background: data.era_background ? String(data.era_background) : null,
        plot: data.plot ? String(data.plot) : null,
        tone: data.tone ? String(data.tone) : null,
        target_audience: data.target_audience ? String(data.target_audience) : null,
        core_idea: data.core_idea ? String(data.core_idea) : null,
        number_of_chapters: data.number_of_chapters ? Number(data.number_of_chapters) : null,
        words_per_chapter: data.words_per_chapter ? Number(data.words_per_chapter) : null,
      };
      const aiCreate = data._aiCreate as WritingDraft["_aiCreate"] | undefined;
      const payload: NovelManualCreateRequest | NovelAIConfirmationRequest = aiCreate
        ? {
            request_type: "ai_confirmation",
            candidate,
            basis: aiCreate.basis,
            generation_input: aiCreate.generation_input,
            expected_versions: {},
          }
        : {
            ...(candidate as CreateNovelRequest),
            request_type: "manual",
          };
      const signature = JSON.stringify(payload);
      if (createIdempotencyRef.current?.signature !== signature) {
        createIdempotencyRef.current = {
          signature,
          key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
        };
      }
      setCreateError("");
      const res = await apiPost<NovelCreateResponse>("/api/novels/create", payload, {
        headers: { "Idempotency-Key": createIdempotencyRef.current.key },
      });
      clearWritingDraft(draftId);
      let coverUploadFailed = false;
      if (pendingCover) {
        const coverData = new FormData();
        coverData.append("file", pendingCover);
        coverData.append("expected_version", String(res.version));
        setCoverUploading(true);
        try {
          await apiPutForm<NovelDetail>(`/api/novels/${res.id}/cover`, coverData);
        } catch {
          coverUploadFailed = true;
        } finally {
          setCoverUploading(false);
        }
      }
      router.push(`/${locale}/writing/${res.id}${coverUploadFailed ? "?coverUpload=failed" : ""}`);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : tw("createFailed"));
    } finally {
      setCreating(false);
    }
  };

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

  const requestDangerConfirm = (): Promise<boolean> => {
    return new Promise((resolve) => {
      setDangerResolve(() => resolve);
      setShowDangerModal(true);
    });
  };

  const handleDangerResponse = useCallback((confirmed: boolean) => {
    setShowDangerModal(false);
    dangerResolve?.(confirmed);
    setDangerResolve(null);
  }, [dangerResolve]);

  const closeRewrite = useCallback(() => {
    setRewriteOpen(false);
    rewriteButtonRef.current?.focus();
  }, []);

  const reviewTotal = CREATE_NOVEL_CONTEXT_FIELDS.length;
  const reviewCompleted = CREATE_NOVEL_CONTEXT_FIELDS.reduce(
    (count, field) => count + (hasReviewValue(data[field]) ? 1 : 0),
    0,
  );
  const reviewPercent = Math.round((reviewCompleted / reviewTotal) * 100);
  const remainingReviewFields = reviewTotal - reviewCompleted;
  const canCreate =
    String(data.title ?? "").trim().length > 0 &&
    isValidOptionalPositiveInteger(data.number_of_chapters) &&
    isValidOptionalPositiveInteger(data.words_per_chapter);

  if (loading && !data.id) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted">{twd("loading")}</p>
      </div>
    );
  }

  if (loadError && !data.id) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-muted">{twd("loadFailed")}</p>
        <Button variant="outline" onPress={loadNovel}>{tw("retryLoad")}</Button>
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
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden">
      {showDangerModal && (
        <ConfirmActionModal
          title={twd("dangerEditTitle")}
          message={twd("dangerEditMessage")}
          confirmText={twd("confirmContinue")}
          cancelText={twd("cancel")}
          danger
          onCancel={() => handleDangerResponse(false)}
          onConfirm={() => handleDangerResponse(true)}
        />
      )}

      <div className="shrink-0 border-b border-border bg-surface/45 px-4 py-3 sm:px-6">
        <div className={mode === "create"
          ? "flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
          : "flex items-center justify-between gap-3"}>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-foreground">
              {mode === "create" ? tw("createTitle") : tw("editTitle")}
            </h2>
          </div>

          <div className={mode === "create"
            ? "flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-end"
            : "shrink-0"}>
            {mode === "create" && (
              <div className="w-full max-w-sm sm:w-72">
                <div className="mb-2 flex items-center justify-between gap-4 text-xs">
                  <span className="font-medium text-foreground">
                    {remainingReviewFields === 0
                      ? tw("reviewReady")
                      : tw("reviewPending", { count: remainingReviewFields })}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">
                    {tw("reviewProgress", { completed: reviewCompleted, total: reviewTotal })}
                  </span>
                </div>
                <div
                  className="h-1.5 overflow-hidden rounded-full bg-border/60"
                  role="progressbar"
                  aria-label={tw("reviewProgressLabel")}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={reviewPercent}
                >
                  <div
                    className="h-full rounded-full bg-accent transition-[width] duration-300"
                    style={{ width: `${reviewPercent}%` }}
                  />
                </div>
              </div>
            )}
            <Button
              ref={rewriteButtonRef}
              variant={rewriteOpen ? "primary" : "outline"}
              size="sm"
              aria-expanded={assistant.enabled ? assistant.open : rewriteOpen}
              aria-controls={assistant.enabled ? "novel-assistant-panel" : "novel-rewrite-sidebar"}
              onPress={() => assistant.enabled && novelId ? assistant.openFor({ resource_type: "novel", id: novelId, fields: ["summary"], usage: "target", origin: "saved", version: Number(data.version) }) : setRewriteOpen(true)}
              className={rewriteOpen ? "bg-accent text-accent-foreground hover:bg-accent-hover" : undefined}
            >
              {rewriteT("title")}
            </Button>
          </div>
        </div>
        {(createError || (mode === "edit" && searchParams.get("coverUpload") === "failed")) && (
          <div className="mt-4 border-y border-red-300 py-3 text-sm text-red-700 dark:border-red-800 dark:text-red-300" role="alert">
            {createError || tw("coverUploadAfterCreateFailed")}
          </div>
        )}
      </div>

      {loading && <p role="status" className="shrink-0 px-4 py-2 text-sm text-muted sm:px-6">{twd("loading")}</p>}
      {loadError && <div role="alert" className="flex shrink-0 flex-wrap items-center gap-3 border-y border-border px-4 py-2 text-sm text-danger sm:px-6">
        <p>{twd("loadFailed")}</p>
        <Button variant="outline" size="sm" isDisabled={loading} onPress={() => void loadNovel()}>{tw("retryLoad")}</Button>
      </div>}
      <div className="relative flex min-h-0 flex-1">
        <div className="@container/novel-info workspace-scrollbar min-w-0 flex-1 overflow-x-hidden overflow-y-auto bg-surface px-4 sm:px-6">
          {mode === "create" && data._fromAI === true && <ReplacementCharacterNotice value={Object.fromEntries(CREATE_NOVEL_CONTEXT_FIELDS.map((field) => [field, data[field]]))} />}
          <div>
            {SECTIONS.map((sectionKey) => (
              <NovelInfoSection
                key={sectionKey}
                sectionKey={sectionKey}
                data={data}
                novelId={novelId}
                isCreateMode={mode === "create"}
                isEditing={mode === "create" || editingSection === sectionKey}
                onStartEdit={() => setEditingSection(sectionKey)}
                onCancelEdit={() => setEditingSection(null)}
                onSaved={(novel) => {
                  setData(novel as unknown as Record<string, unknown>);
                  setHasChapters(novel.stats.chapter_count > 0);
                  setEditingSection(null);
                  onFormalFactsChanged?.();
                }}
                onNovelChanged={(novel) => {
                  setData(novel as unknown as Record<string, unknown>);
                  setHasChapters(novel.stats.chapter_count > 0);
                  onFormalFactsChanged?.();
                }}
                onChange={mode === "create" ? handleFieldChange : undefined}
                hasChapters={hasChapters}
                onDangerConfirm={requestDangerConfirm}
                editLocked={editingSection !== null && editingSection !== sectionKey}
                onCoverUploadStateChange={setCoverUploading}
                createCoverFile={pendingCover}
                onCreateCoverChange={setPendingCover}
              />
            ))}
          </div>
        </div>

        <NovelRewriteAssistant
          data={data}
          rewriteState={normalizeRewriteState(data._rewriteState as WritingDraftRewriteState | undefined)}
          onApplyRewrite={handleApplyRewrite}
          onRewriteStateChange={handleRewriteStateChange}
          mode={mode}
          novelId={novelId}
          novelVersion={typeof data.version === "number" ? data.version : undefined}
          isOpen={rewriteOpen}
          onClose={closeRewrite}
          onNovelConfirmed={(novel) => {
            setData((current) => ({
              ...(novel as unknown as Record<string, unknown>),
              _rewriteState: current._rewriteState,
            }));
            setHasChapters(novel.stats.chapter_count > 0);
            onFormalFactsChanged?.();
          }}
        />
      </div>

      {mode === "create" && (
        <StickyActionBar>
          <Button
            variant="ghost"
            isDisabled={coverUploading || creating}
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
            isDisabled={creating || coverUploading || !canCreate}
            className="bg-accent text-accent-foreground hover:bg-accent-hover"
          >
            {creating ? tw("creating") : tw("saveCreate")}
          </Button>
        </StickyActionBar>
      )}

    </div>
  );
}
