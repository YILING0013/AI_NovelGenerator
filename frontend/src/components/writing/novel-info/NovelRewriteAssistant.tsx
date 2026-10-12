"use client";
import ReplacementCharacterNotice from "@/components/shared/ReplacementCharacterNotice";

import { TaskFlowForm,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import type { TaskFlowRunMode } from "@/types/taskFlow";

import {
createLocalCandidateState,
hasCandidateFlow,
localCandidateReducer,
type CandidateGenerationEnvelopeV1,
} from "@/lib/aiCandidate";
import { apiPut,ApiRequestError } from "@/lib/api";
import {
FIELD_LABEL_MAP,
REWRITABLE_NOVEL_FIELDS,
type NovelRewriteFieldKey,
} from "@/lib/novelFields";
import {
appendAiRewriteRevision,
appendRewriteMessage,
clearRewriteMessageFailure,
createRewriteMessage,
ensureFieldCurrentRevision,
formatRewriteValueForDisplay,
getActiveRevisionId,
getFieldRevisions,
markRewriteMessageFailed,
normalizeRewriteState,
selectRewriteRevision,
} from "@/lib/rewriteDraftState";
import type {
NovelDetail,
RewriteChatMessage,
RewriteNovelFieldAIConfirmRequest,
RewriteNovelFieldGenerationInput,
RewriteNovelFieldRequest,
RewriteNovelFieldResponse,
WritingDraftRewriteState,
} from "@/types/novel";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useEffect,useMemo,useReducer,useRef,useState } from "react";

interface NovelRewriteAssistantProps {
  data: Record<string, unknown>;
  rewriteState?: WritingDraftRewriteState;
  onApplyRewrite: (
    field: NovelRewriteFieldKey,
    value: string | string[],
    rewriteState: WritingDraftRewriteState,
  ) => void;
  onRewriteStateChange: (rewriteState: WritingDraftRewriteState) => void;
  mode: "create" | "edit";
  novelId?: string;
  novelVersion?: number;
  isOpen: boolean;
  onClose: () => void;
  onNovelConfirmed?: (novel: NovelDetail) => void;
}

interface PendingRewriteRequest {
  targetField: NovelRewriteFieldKey;
  messageId: string;
}

const REWRITE_CONTEXT_FIELDS = [
  "title",
  "subtitle",
  "genre",
  "tags",
  "tone",
  "target_audience",
  "core_idea",
  "core_seed",
  "writing_style",
  "narrative_pov",
  "era_background",
  "number_of_chapters",
  "words_per_chapter",
] as const;

function getFieldValue(data: Record<string, unknown>, field: NovelRewriteFieldKey): string | string[] {
  if (field === "tags") {
    const tags = data.tags;
    return Array.isArray(tags) ? tags.map(String) : [];
  }

  return String(data[field] ?? "");
}

function buildRewriteContext(
  data: Record<string, unknown>,
  targetField: NovelRewriteFieldKey,
): Record<string, unknown> {
  const context: Record<string, unknown> = {};

  for (const field of REWRITE_CONTEXT_FIELDS) {
    // 目标字段已通过 current_value 单独发送，避免同一字段重复消耗 token。
    if (field === targetField) {
      continue;
    }

    if (field in data) {
      context[field] = data[field];
    }
  }

  return context;
}

/**
 * 构造发送给后端的改写历史。
 *
 * Args:
 *   messages: 当前字段的本地聊天记录。
 *   excludeMessageId: 当前正在发送或重试的消息 ID。
 *
 * Returns:
 *   不包含失败消息和当前消息的聊天记录。
 */
function buildRewriteHistory(
  messages: RewriteChatMessage[],
  excludeMessageId?: string,
): RewriteNovelFieldRequest["chat_history"] {
  return messages
    .filter((message) => {
      // 失败请求只供用户查看，不再发给 AI。
      return message.status !== "failed" && message.id !== excludeMessageId;
    })
    .map(({ role, content }) => ({ role, content }));
}

/**
 * 校验后端返回的 AI 改写结果。
 *
 * Args:
 *   value: 后端返回的未知数据。
 *   targetField: 当前请求目标字段。
 *   novelId: 保存态小说 ID；创建态为空。
 *
 * Returns:
 *   接口版本、小说和字段都匹配时返回改写结果，否则返回 null。
 */
const REWRITE_ENVELOPE = {
  workflow: "rewrite_novel_field_by_ai",
  step: "novel_field",
  schema_id: "novel.field_rewrite_candidate",
  schema_version: 1,
} as const;

function parseRewriteEnvelope(
  value: unknown,
  targetField: NovelRewriteFieldKey,
  novelId?: string,
): CandidateGenerationEnvelopeV1<RewriteNovelFieldResponse> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const envelope = value as Partial<CandidateGenerationEnvelopeV1<RewriteNovelFieldResponse>>;
  const basis = envelope.basis;
  const candidate = envelope.candidate;
  if (envelope.workflow !== REWRITE_ENVELOPE.workflow
    || envelope.step !== REWRITE_ENVELOPE.step
    || envelope.schema_id !== REWRITE_ENVELOPE.schema_id
    || envelope.schema_version !== REWRITE_ENVELOPE.schema_version
    || !hasCandidateFlow(basis) || basis.workflow !== envelope.workflow || basis.step !== envelope.step
    || basis.schema_id !== envelope.schema_id || basis.schema_version !== envelope.schema_version
    || basis.novel_id !== (novelId ?? null) || !Array.isArray(basis.source_refs)
    || (novelId
      ? !basis.source_refs.some((source) => source.resource_type === "novel" && source.id === novelId)
      : basis.source_refs.length !== 0)
    || !/^[0-9a-f]{64}$/.test(basis.input_fingerprint)
    || !candidate || candidate.target_field !== targetField
    || (targetField === "tags"
      ? !Array.isArray(candidate.value)
        || candidate.value.length === 0
        || !candidate.value.every((item) => typeof item === "string" && item.trim())
      : typeof candidate.value !== "string" || !candidate.value.trim())) {
    return null;
  }
  return envelope as CandidateGenerationEnvelopeV1<RewriteNovelFieldResponse>;
}

export default function NovelRewriteAssistant({
  data,
  rewriteState,
  onApplyRewrite,
  onRewriteStateChange,
  mode,
  novelId,
  novelVersion,
  isOpen,
  onClose,
  onNovelConfirmed,
}: NovelRewriteAssistantProps) {
  const t = useTranslations("writing.rewriteAssistant");
  const tn = useTranslations("novel");
  const taskFlow = useTaskFlow("rewrite_novel_field_by_ai");
  const [selectedField, setSelectedField] = useState<NovelRewriteFieldKey>("plot");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [retryRequest, setRetryRequest] = useState<PendingRewriteRequest | null>(null);
  const [candidateState, dispatchCandidate] = useReducer(
    localCandidateReducer<RewriteNovelFieldResponse>,
    createLocalCandidateState<RewriteNovelFieldResponse>(),
  );
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isOpen) closeButtonRef.current?.focus();
  }, [isOpen]);
  const [candidateGenerationInput, setCandidateGenerationInput] = useState<RewriteNovelFieldGenerationInput | null>(null);
  const requestAbortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const confirmIdempotencyRef = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => () => { requestIdRef.current += 1; requestAbortRef.current?.abort(); }, []);

  const normalizedState = useMemo(
    () => normalizeRewriteState(rewriteState),
    [rewriteState],
  );

  useEffect(() => {
    if (mode !== "edit" || !novelId || !novelVersion || !candidateState.basis || candidateState.status === "stale") {
      return;
    }
    const source = candidateState.basis.source_refs.find(
      (item) => item.resource_type === "novel" && item.id === novelId,
    );
    if (!source || source.version !== novelVersion) {
      dispatchCandidate({ type: "mark_stale" });
    }
  }, [candidateState.basis, candidateState.status, mode, novelId, novelVersion]);
  const messages = normalizedState.messagesByField[selectedField] || [];
  const revisions = getFieldRevisions(normalizedState, selectedField);
  const activeRevisionId = getActiveRevisionId(normalizedState, selectedField);
  const selectedFieldLabel = tn(FIELD_LABEL_MAP[selectedField]);
  const activeRevisionIndex = revisions.findIndex((revision) => revision.id === activeRevisionId);
  const versionPosition = revisions.length > 0 && activeRevisionIndex >= 0
    ? `${activeRevisionIndex + 1}/${revisions.length}`
    : t("currentVersion");
  const canUndoRevision = activeRevisionIndex > 0;
  const canRedoRevision = activeRevisionIndex >= 0 && activeRevisionIndex < revisions.length - 1;
  const inlineSelectClassName =
    "h-8 w-auto min-w-0 rounded-md border border-transparent bg-transparent px-2 pr-7 text-left text-xs text-foreground outline-none hover:border-border/60 hover:text-accent focus:border-border focus:text-accent disabled:opacity-50";

  const applyStateOnly = (nextState: WritingDraftRewriteState) => {
    onRewriteStateChange(nextState);
  };

  const handleRevisionChange = (revisionId: string) => {
    const { revision, state: nextState } = selectRewriteRevision(
      normalizedState,
      selectedField,
      revisionId,
    );

    if (!revision) {
      return;
    }

    onApplyRewrite(selectedField, revision.value, nextState);
  };

  const handleStepRevision = (direction: -1 | 1) => {
    if (activeRevisionIndex < 0) {
      return;
    }

    const nextRevision = revisions[activeRevisionIndex + direction];
    if (!nextRevision) {
      return;
    }

    // 标题栏的撤回/恢复只切换当前字段版本，不影响其他创建信息。
    handleRevisionChange(nextRevision.id);
  };

  /**
   * 执行新增发送或失败重试的改写请求。
   *
   * Args:
   *   request: 本次改写的 Provider、目标字段与用户需求。
   *   retryMessageId: 需要重试的失败消息 ID；为空时会新增一条用户消息。
   *
   * Returns:
   *   请求完成后的 Promise。
   */
  const executeRewriteRequest = async (
    request: Omit<PendingRewriteRequest, "messageId">,
    retryMessageId?: string,
    runMode: TaskFlowRunMode = Boolean(retryMessageId),
  ) => {
    const instruction = Object.values(taskFlow.inputs).filter((value) => value !== null && value !== "").map((value) => typeof value === "string" ? value : JSON.stringify(value)).join("\n") || taskFlow.definition?.name || "";
    const provider = String(taskFlow.inputs.provider ?? "");
    const targetField = request.targetField;
    const currentValue = getFieldValue(data, targetField);

    if (!taskFlow.definition || sending) {
      return;
    }

    setSending(true);
    // 发送按钮随后会被替换，先把焦点留在侧栏内，让 Escape 仍能关闭并取消。
    closeButtonRef.current?.focus();
    setError("");
    setRetryRequest(null);
    const controller = new AbortController();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    requestAbortRef.current?.abort();
    requestAbortRef.current = controller;
    dispatchCandidate({ type: "generate", requestId });
    setCandidateGenerationInput(null);

    let requestMessageId = retryMessageId;
    let stateForRequest = normalizedState;

    if (requestMessageId) {
      // 重试同一条失败消息时先移除失败态，但构造模型历史时仍会排除这条消息。
      stateForRequest = clearRewriteMessageFailure(
        normalizedState,
        targetField,
        requestMessageId,
      );
    } else {
      const userMessage = createRewriteMessage("user", targetField, instruction, { provider });
      requestMessageId = userMessage.id;
      stateForRequest = appendRewriteMessage(normalizedState, targetField, userMessage);
    }

    applyStateOnly(stateForRequest);

    try {
      const generated = await taskFlow.run("/api/llm/rewrite-novel-field/stream", {
        ...(mode === "edit" && novelId ? { novel_id: novelId } : {}),
        target_field: targetField,
        current_value: currentValue,
        context: buildRewriteContext(data, targetField),
        chat_history: buildRewriteHistory(stateForRequest.messagesByField[targetField] || [], requestMessageId),
      }, controller.signal, runMode);
      if (controller.signal.aborted || requestIdRef.current !== requestId) return;
      const generationInput = generated.generationInput as RewriteNovelFieldGenerationInput;
      const response = parseRewriteEnvelope(generated.result, targetField, mode === "edit" ? novelId : undefined);

      if (!response) {
        throw new Error(t("invalidCandidate"));
      }
      dispatchCandidate({
        type: "preview",
        requestId,
        candidate: response.candidate,
        basis: response.basis,
      });
      setCandidateGenerationInput(generationInput);
    } catch (err) {
      if (controller.signal.aborted || (err instanceof Error && err.name === "AbortError")) return;
      const errorMessage = err instanceof Error ? err.message : t("rewriteFailed");
      const failedState = markRewriteMessageFailed(
        stateForRequest,
        targetField,
        requestMessageId,
        errorMessage,
      );

      applyStateOnly(failedState);
      setError(errorMessage);
      dispatchCandidate({ type: "generation_failed", requestId, message: errorMessage });
      setRetryRequest({
        targetField,
        messageId: requestMessageId,
      });
    } finally {
      if (requestAbortRef.current === controller) requestAbortRef.current = null;
      if (requestIdRef.current === requestId) setSending(false);
    }
  };

  const handleSend = async () => {
    await executeRewriteRequest({
      targetField: selectedField,
    });
  };

  const handleRetry = async (runMode: TaskFlowRunMode = true) => {
    if (!retryRequest || sending) {
      return;
    }

    setSelectedField(retryRequest.targetField);
    await executeRewriteRequest(
      {
        targetField: retryRequest.targetField,
        },
      retryRequest.messageId,
      runMode,
    );
  };

  const cancelRewrite = () => {
    setError("");
    setRetryRequest(null);
    void taskFlow.discard();

    requestIdRef.current += 1;
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
    setSending(false);
    dispatchCandidate({ type: "discard" });
    setCandidateGenerationInput(null);
  };

  const closePanel = () => {
    // 收起侧栏只取消正在生成的请求，已经生成的候选继续保留。
    if (requestAbortRef.current) cancelRewrite();
    onClose();
  };

  const applyConfirmedCandidate = (candidate: RewriteNovelFieldResponse) => {
    const currentValue = getFieldValue(data, candidate.target_field);
    let nextState = ensureFieldCurrentRevision(normalizedState, candidate.target_field, currentValue);
    nextState = appendAiRewriteRevision(
      nextState,
      candidate.target_field,
      candidate.value,
      candidateGenerationInput?.instruction ?? "",
    );
    nextState = appendRewriteMessage(
      nextState,
      candidate.target_field,
      createRewriteMessage(
        "assistant",
        candidate.target_field,
        formatRewriteValueForDisplay(candidate.value),
      ),
    );
    onApplyRewrite(candidate.target_field, candidate.value, nextState);
  };

  const confirmCandidate = async () => {
    const candidate = candidateState.candidate;
    const basis = candidateState.basis;
    if (!candidate || !basis || !candidateGenerationInput || candidateState.status === "stale") return;
    dispatchCandidate({ type: "confirm" });

    if (mode === "create") {
      applyConfirmedCandidate(candidate);
      dispatchCandidate({ type: "discard" });
      setCandidateGenerationInput(null);
      return;
    }
    if (!novelId || !novelVersion) return;

    const payload: RewriteNovelFieldAIConfirmRequest = {
      request_type: "ai_field_confirmation",
      candidate,
      basis,
      generation_input: candidateGenerationInput,
      expected_versions: { [`novel:${novelId}`]: novelVersion },
    };
    const signature = JSON.stringify(payload);
    if (confirmIdempotencyRef.current?.signature !== signature) {
      confirmIdempotencyRef.current = {
        signature,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }

    try {
      const updated = await apiPut<NovelDetail>(`/api/novels/${novelId}`, payload, {
        headers: { "Idempotency-Key": confirmIdempotencyRef.current.key },
      });
      onNovelConfirmed?.(updated);
      applyConfirmedCandidate(candidate);
      dispatchCandidate({ type: "discard" });
      setCandidateGenerationInput(null);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : t("confirmFailed");
      dispatchCandidate({
        type: "confirm_failed",
        message,
        stale: caught instanceof ApiRequestError && caught.status === 409,
      });
    }
  };

  return (
    <aside
      id="novel-rewrite-sidebar"
      aria-label={t("title")}
      aria-hidden={!isOpen}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          closePanel();
        }
      }}
      className={`${isOpen ? "flex" : "hidden"} absolute inset-y-0 right-0 z-40 h-full w-full min-w-0 flex-col overflow-hidden border-l border-border bg-surface shadow-xl sm:w-[390px] xl:relative xl:inset-auto xl:shrink-0 xl:shadow-none`}
    >
      <div className="flex shrink-0 items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">{t("title")}</h3>
          <p className="truncate text-xs text-muted">{selectedFieldLabel}</p>
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1.5">
          <div className="flex items-center gap-1 rounded-full border border-border/70 px-1.5 py-0.5">
            <button
              type="button"
              className="flex h-6 w-6 items-center justify-center rounded-full text-muted hover:bg-background hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
              onClick={() => handleStepRevision(-1)}
              disabled={!canUndoRevision || sending}
              title={t("undoVersion")}
              aria-label={t("undoVersion")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 14 4 9l5-5" />
                <path d="M4 9h10a6 6 0 0 1 0 12h-1" />
              </svg>
            </button>
            <span className="min-w-8 text-center text-xs text-muted">{versionPosition}</span>
            <button
              type="button"
              className="flex h-6 w-6 items-center justify-center rounded-full text-muted hover:bg-background hover:text-foreground disabled:cursor-not-allowed disabled:opacity-35"
              onClick={() => handleStepRevision(1)}
              disabled={!canRedoRevision || sending}
              title={t("redoVersion")}
              aria-label={t("redoVersion")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m15 14 5-5-5-5" />
                <path d="M20 9H10a6 6 0 0 0 0 12h1" />
              </svg>
            </button>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="flex h-7 w-7 items-center justify-center rounded-full text-muted hover:bg-background hover:text-foreground"
            onClick={closePanel}
            title={t("closePanel")}
            aria-label={t("closePanel")}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
          </button>
        </div>
      </div>

      {messages.length > 0 && (
        <div
          className="workspace-scrollbar max-h-[40%] min-h-0 shrink-0 space-y-3 overflow-y-auto px-4 py-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/20"
          tabIndex={0}
          aria-label={t("historyLabel")}
        >
          {messages.map((message) => {
            const isUserMessage = message.role === "user";
            const isFailedMessage = message.status === "failed";

            return (
              <div
                key={message.id}
                className={`flex items-start gap-1.5 ${
                  isUserMessage ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[82%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed ${
                    isUserMessage
                      ? "bg-accent text-accent-foreground"
                      : "border border-border bg-background text-foreground"
                  }`}
                >
                  {message.content}
                </div>
                {isFailedMessage && (
                  <span
                    className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-red-300 bg-red-50 text-xs font-semibold text-red-600 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
                    title={message.error_message || t("requestFailed")}
                    aria-label={t("requestFailed")}
                  >
                    !
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col border-t border-border/60">
        <div
          className="workspace-scrollbar min-h-0 flex-1 overflow-y-auto p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/20"
          role="region"
          aria-label={t("instructionLabel")}
          tabIndex={0}
        >
        {candidateState.candidate && (
          <section className="mb-3 border-y border-border py-3" aria-labelledby="rewrite-candidate-title">
            <div className="flex items-center justify-between gap-3">
              <h4 id="rewrite-candidate-title" className="text-xs font-semibold text-foreground">
                {t("candidateTitle")}
              </h4>
              <span className="text-xs text-muted">{tn(FIELD_LABEL_MAP[candidateState.candidate.target_field])}</span>
            </div>
            <ReplacementCharacterNotice value={{ [candidateState.candidate.target_field]: candidateState.candidate.value }} />
            <p className="mt-2 max-h-32 overflow-y-auto whitespace-pre-wrap text-xs leading-5 text-foreground">
              {formatRewriteValueForDisplay(candidateState.candidate.value)}
            </p>
            {candidateState.error && (
              <p className="mt-2 text-xs text-red-700 dark:text-red-300" role="alert">
                {candidateState.status === "stale" ? t("candidateStale") : candidateState.error}
              </p>
            )}
            <div className="mt-3 flex flex-wrap justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                isDisabled={candidateState.status === "confirming"}
                onPress={() => {
                  dispatchCandidate({ type: "discard" });
                  setCandidateGenerationInput(null);
                }}
              >
                {t("discardCandidate")}
              </Button>
              <Button
                variant="primary"
                size="sm"
                className="bg-accent text-accent-foreground hover:bg-accent-hover"
                isDisabled={candidateState.status === "confirming" || candidateState.status === "stale"}
                onPress={confirmCandidate}
              >
                {candidateState.status === "confirming"
                  ? t("confirmingCandidate")
                  : mode === "create"
                    ? t("applyCandidate")
                    : t("confirmCandidate")}
              </Button>
            </div>
          </section>
        )}

        {error && (
          <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            <div>{error}</div>
          </div>
        )}

        <TaskFlowForm flow={taskFlow} disabled={sending} />
        <TaskFlowProgress flow={taskFlow} running={sending} failed={candidateState.status === "error" && candidateState.candidate === null} onRetry={() => void handleRetry()} onContinue={(additionalRounds) => void handleRetry({ continuation: true, additionalRounds })} onDiscard={cancelRewrite} label={t("sending")} />
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border/60 bg-surface p-3">
          <select
            className={`${inlineSelectClassName} max-w-[10rem]`}
            value={selectedField}
            onChange={(event) => setSelectedField(event.target.value as NovelRewriteFieldKey)}
            disabled={sending}
            title={t("field")}
            aria-label={t("field")}
          >
            {REWRITABLE_NOVEL_FIELDS.map((field) => (
              <option key={field} value={field}>
                {tn(FIELD_LABEL_MAP[field])}
              </option>
            ))}
          </select>

          <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2">
            <Button
              variant="primary"
              size="sm"
              className="h-8 shrink-0 bg-accent px-3 text-accent-foreground hover:bg-accent-hover"
              onPress={handleSend}
              isDisabled={sending || taskFlow.loading || !taskFlow.definition || Boolean(candidateState.candidate)}
            >
              {sending ? t("sending") : t("send")}
            </Button>
            {sending && (
              <Button variant="outline" size="sm" className="h-8 shrink-0" onPress={cancelRewrite}>
                {t("cancelGeneration")}
              </Button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
