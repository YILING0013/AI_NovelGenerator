"use client";

import {
  TaskFlowForm,
  TaskFlowProgress,
} from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { hasCandidateFlow } from "@/lib/aiCandidate";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import type {
  AICreateCandidateEnvelopeV1,
  AICreateGenerationInput,
} from "@/types/novel";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

interface AICreateStepperProps {
  onComplete: (
    result: AICreateCandidateEnvelopeV1,
    generationInput: AICreateGenerationInput,
  ) => void;
  cancelSignal?: AbortSignal;
}

const AI_CREATE_ENVELOPE = {
  workflow: "create_novel_by_ai",
  step: "novel_meta",
  schema_id: "novel.create_candidate",
  schema_version: 1,
} as const;

function parseAICreateEnvelope(
  value: unknown,
): AICreateCandidateEnvelopeV1 | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const envelope = value as Partial<AICreateCandidateEnvelopeV1>;
  const basis = envelope.basis;
  const candidate = envelope.candidate;
  const nullableTextFields = [
    "subtitle",
    "introduction",
    "summary",
    "core_seed",
    "worldview",
    "writing_style",
    "narrative_pov",
    "era_background",
    "plot",
    "tone",
    "target_audience",
    "core_idea",
  ] as const;
  if (
    envelope.workflow !== AI_CREATE_ENVELOPE.workflow ||
    envelope.step !== AI_CREATE_ENVELOPE.step ||
    envelope.schema_id !== AI_CREATE_ENVELOPE.schema_id ||
    envelope.schema_version !== AI_CREATE_ENVELOPE.schema_version ||
    !hasCandidateFlow(basis) ||
    basis.novel_id !== null ||
    !Array.isArray(basis.source_refs) ||
    basis.source_refs.length !== 0 ||
    basis.workflow !== envelope.workflow ||
    basis.step !== envelope.step ||
    basis.schema_id !== envelope.schema_id ||
    basis.schema_version !== envelope.schema_version ||
    !/^[0-9a-f]{64}$/.test(basis.input_fingerprint) ||
    !candidate ||
    typeof candidate.title !== "string" ||
    !candidate.title.trim() ||
    typeof candidate.genre !== "string" ||
    !candidate.genre.trim() ||
    !Array.isArray(candidate.tags) ||
    !candidate.tags.every((item) => typeof item === "string") ||
    !nullableTextFields.every(
      (field) =>
        candidate[field] === null || typeof candidate[field] === "string",
    ) ||
    (candidate.number_of_chapters !== null &&
      (typeof candidate.number_of_chapters !== "number" ||
        !Number.isInteger(candidate.number_of_chapters) ||
        candidate.number_of_chapters < 1)) ||
    (candidate.words_per_chapter !== null &&
      (typeof candidate.words_per_chapter !== "number" ||
        !Number.isInteger(candidate.words_per_chapter) ||
        candidate.words_per_chapter < 1))
  ) {
    return null;
  }
  return envelope as AICreateCandidateEnvelopeV1;
}

export default function AICreateStepper({
  onComplete,
  cancelSignal,
}: AICreateStepperProps) {
  const t = useTranslations("create");
  const tf = useTranslations("taskFlows");
  const flow = useTaskFlow("create_novel_by_ai");
  const discard = flow.discard;
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setRunning(false);
    setError("");
    void discard();
  }, [discard]);
  useEffect(() => {
    cancelSignal?.addEventListener("abort", cancel);
    return () => {
      cancelSignal?.removeEventListener("abort", cancel);
      cancel();
    };
  }, [cancel, cancelSignal]);

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    setError("");
    try {
      const { result, generationInput } = await flow.run(
        "/api/llm/create-novel-by-ai",
        {},
        controller.signal,
        retry,
      );
      if (controller.signal.aborted || abortRef.current !== controller) return;
      const envelope = parseAICreateEnvelope(result);
      if (!envelope) throw new Error(t("invalidCandidate"));
      onComplete(envelope, generationInput as AICreateGenerationInput);
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setRunning(false);
      }
    }
  };

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      <div className="workspace-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-5 sm:px-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={t("tabAI")}>
        <TaskFlowForm flow={flow} disabled={running || Boolean(error)} />
        {error && error !== flow.error && (
          <p
            role="alert"
            className="border-y border-red-500/30 py-3 text-sm text-red-600 dark:text-red-300"
          >
            {error}
          </p>
        )}
        <TaskFlowProgress flow={flow} running={running} failed={Boolean(error)} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={cancel} />
      </div>
      <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-border bg-surface px-4 py-3 sm:px-6">
        {running && (
          <Button variant="outline" onPress={cancel}>
            {tf("close")}
          </Button>
        )}
        <Button
          variant="primary"
          isDisabled={running || Boolean(error) || flow.loading || !flow.definition}
          onPress={() => void generate()}
        >
          {running
            ? tf("states.running")
            : tf("generate")}
        </Button>
      </div>
    </div>
  );
}
