"use client";

import { useState, useRef } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { apiPostSSE } from "@/lib/api";
import { OptionalSliderParam, OptionalNumberParam, OptionalTextParam } from "@/components/shared/OptionalParamControls";
import type { AICreateResponse, AICreateRequest } from "@/types/novel";

interface AICreateStepperProps {
  onComplete: (result: AICreateResponse, chapters: number, wordsPerChapter: number) => void;
}

type StepStatus = "pending" | "running" | "done" | "error";

interface StepState {
  key: string;
  status: StepStatus;
  error?: string;
}

const STEPS = ["expand_idea", "extract_idea", "core_seed", "novel_meta"] as const;

export default function AICreateStepper({ onComplete }: AICreateStepperProps) {
  const t = useTranslations("create");
  const [idea, setIdea] = useState("");
  const [chapters, setChapters] = useState(600);
  const [wordsPerChapter, setWordsPerChapter] = useState(3000);
  const [showGenParams, setShowGenParams] = useState(false);
  const [temperature, setTemperature] = useState<number | null>(null);
  const [topP, setTopP] = useState<number | null>(null);
  const [maxTokens, setMaxTokens] = useState<number | null>(null);
  const [presencePenalty, setPresencePenalty] = useState<number | null>(null);
  const [frequencyPenalty, setFrequencyPenalty] = useState<number | null>(null);
  const [systemPrompt, setSystemPrompt] = useState<string | null>(null);
  const [steps, setSteps] = useState<StepState[]>(
    STEPS.map((key) => ({ key, status: "pending" }))
  );
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AICreateResponse | null>(null);
  const stepsRef = useRef(steps);
  stepsRef.current = steps;

  const stepLabelMap: Record<string, string> = {
    expand_idea: t("stepExpandIdea"),
    extract_idea: t("stepExtractIdea"),
    core_seed: t("stepCoreSeed"),
    novel_meta: t("stepNovelMeta"),
  };

  const startGeneration = async () => {
    if (!idea.trim()) return;

    setIsRunning(true);
    setResult(null);
    setSteps(STEPS.map((key) => ({ key, status: "pending" })));

    const payload: AICreateRequest = {
      user_idea: idea.trim(),
      number_of_chapters: chapters,
      words_per_chapter: wordsPerChapter,
      ...(temperature != null && { temperature }),
      ...(topP != null && { top_p: topP }),
      ...(maxTokens != null && { max_tokens: maxTokens }),
      ...(presencePenalty != null && { presence_penalty: presencePenalty }),
      ...(frequencyPenalty != null && { frequency_penalty: frequencyPenalty }),
      ...(systemPrompt != null && { system_prompt: systemPrompt }),
    };

    try {
      await apiPostSSE(
        "/api/llm/create-novel-by-ai",
        payload,
        (event, data) => {
          if (event === "step") {
            const stepName = data.step as string;
            const status = data.status as StepStatus;
            const error = data.error as string | undefined;

            setSteps((prev) =>
              prev.map((s) =>
                s.key === stepName ? { ...s, status, error } : s
              )
            );
          } else if (event === "done") {
            if (data.success && data.result) {
              const res = data.result as AICreateResponse;
              setResult(res);
              onComplete(res, chapters, wordsPerChapter);
            }
          }
        }
      );
    } catch (err) {
      // 如果发生错误，标记当前正在运行的步骤为 error
      setSteps((prev) => {
        const firstPending = prev.findIndex(
          (s) => s.status === "pending" || s.status === "running"
        );
        if (firstPending < 0) return prev;
        return prev.map((s, i) =>
          i === firstPending
            ? { ...s, status: "error" as StepStatus, error: err instanceof Error ? err.message : String(err) }
            : s
        );
      });
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6 p-1">
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

      {/* Generation Parameters (collapsible) */}
      <div>
        <button
          type="button"
          className="flex items-center gap-2 text-sm font-medium text-muted hover:text-foreground transition-colors py-1"
          onClick={() => setShowGenParams(!showGenParams)}
          disabled={isRunning}
        >
          <svg
            className={`w-4 h-4 transition-transform ${showGenParams ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          {t("genParams.title")}
        </button>
        {showGenParams && (
          <div className="border border-border rounded-lg p-4 mt-1 space-y-3 bg-surface-secondary/30">
            <p className="text-xs text-muted">{t("genParams.hint")}</p>

            <OptionalSliderParam
              label={t("genParams.temperature")}
              value={temperature}
              onToggle={(on) => setTemperature(on ? 0.7 : null)}
              onValueChange={setTemperature}
              min={0} max={2} step={0.05}
            />
            <OptionalSliderParam
              label={t("genParams.topP")}
              value={topP}
              onToggle={(on) => setTopP(on ? 0.9 : null)}
              onValueChange={setTopP}
              min={0} max={1} step={0.05}
            />
            <OptionalNumberParam
              label={t("genParams.maxTokens")}
              value={maxTokens}
              onToggle={(on) => setMaxTokens(on ? 4096 : null)}
              onValueChange={setMaxTokens}
              min={256} max={1000000} step={256}
            />
            <OptionalSliderParam
              label={t("genParams.presencePenalty")}
              value={presencePenalty}
              onToggle={(on) => setPresencePenalty(on ? 0 : null)}
              onValueChange={setPresencePenalty}
              min={-2} max={2} step={0.1}
            />
            <OptionalSliderParam
              label={t("genParams.frequencyPenalty")}
              value={frequencyPenalty}
              onToggle={(on) => setFrequencyPenalty(on ? 0 : null)}
              onValueChange={setFrequencyPenalty}
              min={-2} max={2} step={0.1}
            />
            <OptionalTextParam
              label={t("genParams.systemPrompt")}
              value={systemPrompt}
              onToggle={(on) => setSystemPrompt(on ? "" : null)}
              onValueChange={setSystemPrompt}
              placeholder={t("genParams.systemPromptPlaceholder")}
            />
          </div>
        )}
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
