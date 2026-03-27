"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { apiPost } from "@/lib/api";
import type { AICreateResponse, AICreateRequest } from "@/types/novel";

interface AICreateStepperProps {
  onComplete: (result: AICreateResponse) => void;
}

type StepStatus = "pending" | "running" | "done" | "error";

interface StepState {
  key: string;
  status: StepStatus;
  error?: string;
}

const STEPS = ["extract_idea", "core_seed", "novel_meta"] as const;

export default function AICreateStepper({ onComplete }: AICreateStepperProps) {
  const t = useTranslations("create");
  const [idea, setIdea] = useState("");
  const [chapters, setChapters] = useState(100);
  const [wordsPerChapter, setWordsPerChapter] = useState(3000);
  const [steps, setSteps] = useState<StepState[]>(
    STEPS.map((key) => ({ key, status: "pending" }))
  );
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AICreateResponse | null>(null);

  const stepLabelMap: Record<string, string> = {
    extract_idea: t("stepExtractIdea"),
    core_seed: t("stepCoreSeed"),
    novel_meta: t("stepNovelMeta"),
  };

  const updateStep = (idx: number, patch: Partial<StepState>) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const startGeneration = async () => {
    if (!idea.trim()) return;

    setIsRunning(true);
    setSteps(STEPS.map((key) => ({ key, status: "pending" })));

    // Mark all as pending, then run sequentially via single API call
    setSteps((prev) => prev.map((s, i) => (i === 0 ? { ...s, status: "running" } : s)));

    try {
      const payload: AICreateRequest = {
        user_idea: idea.trim(),
        number_of_chapters: chapters,
        words_per_chapter: wordsPerChapter,
      };

      // Use SSE-like polling: single API call that runs all 3 steps
      const res = await apiPost<AICreateResponse & { _step_progress?: string }>(
        "/api/llm/create-novel-by-ai",
        payload
      );

      // Mark all steps as done since the API runs them all
      setSteps(STEPS.map((key) => ({ key, status: "done" })));
      setResult(res);
      onComplete(res);
    } catch (err) {
      const currentRunning = steps.findIndex((s) => s.status === "running");
      const failIdx = currentRunning >= 0 ? currentRunning : 0;
      updateStep(failIdx, {
        status: "error",
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Idea Input */}
      <div>
        <label className="block text-sm font-medium text-foreground mb-2">
          {t("ideaLabel")}
        </label>
        <textarea
          className="w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground resize-y min-h-[120px] focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder={t("ideaPlaceholder")}
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          disabled={isRunning}
        />
      </div>

      {/* Chapter / Words Config */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            {t("chaptersLabel")}
          </label>
          <input
            type="number"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={chapters}
            onChange={(e) => setChapters(Number(e.target.value) || 1)}
            min={1}
            max={1000}
            disabled={isRunning}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-foreground mb-1">
            {t("wordsPerChapterLabel")}
          </label>
          <input
            type="number"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            value={wordsPerChapter}
            onChange={(e) => setWordsPerChapter(Number(e.target.value) || 1000)}
            min={500}
            max={10000}
            disabled={isRunning}
          />
        </div>
      </div>

      {/* Step Progress */}
      {(isRunning || result || steps.some((s) => s.status === "error")) && (
        <div className="space-y-3">
          {steps.map((step, idx) => (
            <div key={step.key} className="flex items-center gap-3">
              {/* Step Indicator */}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm font-semibold ${
                  step.status === "done"
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : step.status === "running"
                    ? "bg-primary/10 text-primary"
                    : step.status === "error"
                    ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                    : "bg-muted/30 text-muted"
                }`}
              >
                {step.status === "done" ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : step.status === "running" ? (
                  <div className="animate-spin w-4 h-4 border-2 border-current border-t-transparent rounded-full" />
                ) : step.status === "error" ? (
                  "✕"
                ) : (
                  idx + 1
                )}
              </div>

              {/* Step Label */}
              <div className="flex-1">
                <p
                  className={`text-sm font-medium ${
                    step.status === "done"
                      ? "text-green-700 dark:text-green-400"
                      : step.status === "running"
                      ? "text-primary"
                      : step.status === "error"
                      ? "text-red-600 dark:text-red-400"
                      : "text-muted"
                  }`}
                >
                  {stepLabelMap[step.key]}
                </p>
                {step.error && (
                  <p className="text-xs text-red-500 mt-0.5">{step.error}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Start Button */}
      <Button
        variant="primary"
        className="w-full"
        isDisabled={isRunning || !idea.trim()}
        onPress={startGeneration}
      >
        {isRunning ? t("generating") : t("startAI")}
      </Button>
    </div>
  );
}
