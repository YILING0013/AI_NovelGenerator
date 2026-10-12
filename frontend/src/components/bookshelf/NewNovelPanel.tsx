"use client";

import { useContext, useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import { Button } from "@heroui/react";
import AICreateStepper from "./AICreateStepper";
import { RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";
import NovelForm from "./NovelForm";
import type { AICreateCandidateEnvelopeV1, AICreateGenerationInput, WritingDraft } from "@/types/novel";
import { saveWritingDraft } from "@/lib/writingDraft";

interface NewNovelPanelProps {
  onCreated: (novelId: string) => void;
  onCancel: () => void;
}

type CreateMode = "manual" | "ai";

export default function NewNovelPanel({ onCreated, onCancel }: NewNovelPanelProps) {
  const t = useTranslations("create");
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const [createMode, setCreateMode] = useState<CreateMode>("manual");
  const active = useContext(RetainedViewActive);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [unsavedDraft, setUnsavedDraft] = useState<WritingDraft | null>(null);
  const openedDraft = useRef<string | null>(null);
  const [cancelController] = useState(() => new AbortController());
  const tabId = useId();
  const manualTabRef = useRef<HTMLButtonElement>(null);
  const aiTabRef = useRef<HTMLButtonElement>(null);

  const handleCancel = () => {
    // 返回动作先取消当前 AI 流，再由父级卸载面板，避免同一事件循环内收到迟到终态。
    cancelController.abort();
    onCancel();
  };

  /** 保存候选后才进入审核；失败时保留原稿。Args: draft 待保存的候选。Returns: 无。 */
  const saveCandidate = (draft: WritingDraft) => {
    try {
      const savedDraftId = saveWritingDraft(draft);
      setUnsavedDraft(null);
      setDraftId(savedDraftId);
    } catch {
      setUnsavedDraft(draft);
    }
  };

  const handleAIComplete = (
    result: AICreateCandidateEnvelopeV1,
    generationInput: AICreateGenerationInput,
  ) => {
    const draft: WritingDraft = {
      ...result.candidate,
      _fromAI: true,
      _aiCreate: {
        basis: result.basis,
        generation_input: generationInput,
      },
    };
    saveCandidate(draft);
  };

  useEffect(() => {
    // 后台完成只保存候选；回到 AI 栏目后再进入审核页，避免打断当前页面。
    if (draftId && active && createMode === "ai" && openedDraft.current !== draftId) {
      openedDraft.current = draftId;
      router.push(`/${locale}/writing/new?draft=${encodeURIComponent(draftId)}`);
    }
  }, [active, createMode, draftId, locale, router]);

  const selectMode = (mode: CreateMode) => {
    setCreateMode(mode);
    (mode === "manual" ? manualTabRef : aiTabRef).current?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    selectMode(createMode === "manual" ? "ai" : "manual");
  };

  const handleManualCreated = (novelId: string, coverUploadFailed: boolean) => {
    onCreated(novelId);
    const suffix = coverUploadFailed ? "?coverUpload=failed" : "";
    router.push(`/${locale}/writing/${novelId}${suffix}`);
  };

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden bg-surface">
      <header className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <Button variant="ghost" size="sm" onPress={handleCancel}>
            {t("back")}
          </Button>
        </div>
        <div
          className="mt-3 inline-flex rounded-lg border border-border bg-background p-1"
          role="tablist"
          aria-label={t("modeLabel")}
        >
          <button
            ref={manualTabRef}
            id={`${tabId}-manual-tab`}
            type="button"
            role="tab"
            aria-selected={createMode === "manual"}
            aria-controls={`${tabId}-manual-panel`}
            tabIndex={createMode === "manual" ? 0 : -1}
            className={`min-h-11 rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 ${
              createMode === "manual" ? "bg-accent text-accent-foreground" : "text-muted hover:text-foreground"
            }`}
            onClick={() => selectMode("manual")}
            onKeyDown={handleTabKeyDown}
          >
            {t("tabManual")}
          </button>
          <button
            ref={aiTabRef}
            id={`${tabId}-ai-tab`}
            type="button"
            role="tab"
            aria-selected={createMode === "ai"}
            aria-controls={`${tabId}-ai-panel`}
            tabIndex={createMode === "ai" ? 0 : -1}
            className={`min-h-11 rounded-md px-4 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 ${
              createMode === "ai" ? "bg-accent text-accent-foreground" : "text-muted hover:text-foreground"
            }`}
            onClick={() => selectMode("ai")}
            onKeyDown={handleTabKeyDown}
          >
            {t("tabAI")}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <RetainedViews activeKey={createMode}>
        {createMode === "manual" ? (
          <div
            id={`${tabId}-manual-panel`}
            role="tabpanel"
            aria-labelledby={`${tabId}-manual-tab`}
            className="h-full min-h-0"
          >
            <NovelForm defaults={{}} onCreated={handleManualCreated} />
          </div>
        ) : (
          <div
            id={`${tabId}-ai-panel`}
            role="tabpanel"
            aria-labelledby={`${tabId}-ai-tab`}
            className="h-full min-h-0"
          >
            {unsavedDraft ? (
              <div className="space-y-3 px-4 py-5 sm:px-6">
                <p className="break-words text-sm font-medium text-foreground">{unsavedDraft.title}</p>
                <p role="alert" className="text-sm text-danger">{t("draftSaveFailed")}</p>
                <Button variant="primary" onPress={() => saveCandidate(unsavedDraft)}>{t("retryDraftSave")}</Button>
              </div>
            ) : draftId ? (
              <div className="flex flex-wrap items-center gap-3 px-4 py-5 sm:px-6">
                <p role="status" className="text-sm text-foreground">{t("stepComplete")}</p>
                <Button variant="primary" onPress={() => router.push(`/${locale}/writing/new?draft=${encodeURIComponent(draftId)}`)}>{t("viewCandidate")}</Button>
                <Button variant="outline" onPress={() => setDraftId(null)}>{t("startAI")}</Button>
              </div>
            ) : (
              <AICreateStepper
                onComplete={handleAIComplete}
                cancelSignal={cancelController.signal}
              />
            )}
          </div>
        )}
        </RetainedViews>
      </div>
    </section>
  );
}
