"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { apiGet, apiPost } from "@/lib/api";
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
import { normalizeAppConfig, type AppConfig } from "@/types/config";
import type {
  RewriteChatMessage,
  RewriteNovelFieldRequest,
  RewriteNovelFieldResponse,
  WritingDraftRewriteState,
} from "@/types/novel";

interface NovelRewriteAssistantProps {
  data: Record<string, unknown>;
  rewriteState?: WritingDraftRewriteState;
  onApplyRewrite: (
    field: NovelRewriteFieldKey,
    value: string | string[],
    rewriteState: WritingDraftRewriteState,
  ) => void;
  onRewriteStateChange: (rewriteState: WritingDraftRewriteState) => void;
}

interface PendingRewriteRequest {
  provider: string;
  targetField: NovelRewriteFieldKey;
  instruction: string;
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
 *   已过滤失败消息和当前消息的模型上下文历史。
 */
function buildRewriteHistory(
  messages: RewriteChatMessage[],
  excludeMessageId?: string,
): RewriteNovelFieldRequest["chat_history"] {
  return messages
    .filter((message) => {
      // 失败请求只作为本地记录展示，不能继续带入下一次模型上下文。
      return message.status !== "failed" && message.id !== excludeMessageId;
    })
    .map(({ role, content }) => ({ role, content }));
}

export default function NovelRewriteAssistant({
  data,
  rewriteState,
  onApplyRewrite,
  onRewriteStateChange,
}: NovelRewriteAssistantProps) {
  const t = useTranslations("writing.rewriteAssistant");
  const tn = useTranslations("novel");
  const [input, setInput] = useState("");
  const [selectedField, setSelectedField] = useState<NovelRewriteFieldKey>("plot");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [providers, setProviders] = useState<string[]>([]);
  const [providerLoading, setProviderLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [retryRequest, setRetryRequest] = useState<PendingRewriteRequest | null>(null);
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function loadProviders() {
      try {
        setProviderLoading(true);
        const res = await apiGet<{ data: AppConfig }>("/api/config");
        if (!mounted) return;

        const config = normalizeAppConfig(res.data);
        const enabledProviders = Object.entries(config.llm.providers)
          .filter(([, provider]) => provider.enabled)
          .map(([alias]) => alias);
        const defaultProvider = config.llm.default_provider;
        const initialProvider = enabledProviders.includes(defaultProvider)
          ? defaultProvider
          : enabledProviders[0] || "";

        setProviders(enabledProviders);
        setSelectedProvider((current) => current || initialProvider);
        setError("");
      } catch (err) {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : t("loadProvidersFailed"));
      } finally {
        if (mounted) {
          setProviderLoading(false);
        }
      }
    }

    loadProviders();

    return () => {
      mounted = false;
    };
  }, [t]);

  const normalizedState = useMemo(
    () => normalizeRewriteState(rewriteState),
    [rewriteState],
  );
  const messages = normalizedState.messagesByField[selectedField] || [];
  const revisions = getFieldRevisions(normalizedState, selectedField);
  const activeRevisionId = getActiveRevisionId(normalizedState, selectedField);
  const selectedFieldLabel = tn(FIELD_LABEL_MAP[selectedField]);
  const canSend = Boolean(selectedProvider) && Boolean(input.trim()) && !sending;
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
  ) => {
    const instruction = request.instruction.trim();
    const provider = request.provider;
    const targetField = request.targetField;
    const currentValue = getFieldValue(data, targetField);

    if (!instruction || !provider || sending) {
      return;
    }

    setSending(true);
    setError("");
    setRetryRequest(null);

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

    const payload: RewriteNovelFieldRequest = {
      provider,
      target_field: targetField,
      instruction,
      current_value: currentValue,
      context: buildRewriteContext(data, targetField),
      chat_history: buildRewriteHistory(
        stateForRequest.messagesByField[targetField] || [],
        requestMessageId,
      ),
    };

    try {
      const response = await apiPost<RewriteNovelFieldResponse>(
        "/api/llm/rewrite-novel-field",
        payload,
      );
      // AI 改写前先把当前表单值压入版本栈，保证自动覆盖后仍可返回旧版本。
      let nextState = ensureFieldCurrentRevision(stateForRequest, targetField, currentValue);
      nextState = appendAiRewriteRevision(
        nextState,
        response.target_field,
        response.value,
        instruction,
      );
      nextState = appendRewriteMessage(
        nextState,
        response.target_field,
        createRewriteMessage(
          "assistant",
          response.target_field,
          formatRewriteValueForDisplay(response.value),
        ),
      );

      onApplyRewrite(response.target_field, response.value, nextState);
      setInput((current) => (current.trim() === instruction ? "" : current));
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : t("rewriteFailed");
      const failedState = markRewriteMessageFailed(
        stateForRequest,
        targetField,
        requestMessageId,
        errorMessage,
      );

      applyStateOnly(failedState);
      setError(errorMessage);
      setRetryRequest({
        provider,
        targetField,
        instruction,
        messageId: requestMessageId,
      });
    } finally {
      setSending(false);
    }
  };

  const handleSend = async () => {
    await executeRewriteRequest({
      provider: selectedProvider,
      targetField: selectedField,
      instruction: input,
    });
  };

  const handleRetry = async () => {
    if (!retryRequest || sending) {
      return;
    }

    setSelectedField(retryRequest.targetField);
    setSelectedProvider(retryRequest.provider);
    await executeRewriteRequest(
      {
        provider: retryRequest.provider,
        targetField: retryRequest.targetField,
        instruction: retryRequest.instruction,
      },
      retryRequest.messageId,
    );
  };

  return (
    <aside
      className={`fixed bottom-24 right-6 z-40 max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-surface shadow-2xl transition-all max-sm:inset-x-3 max-sm:bottom-20 max-sm:w-auto ${
        isCollapsed ? "w-[260px]" : "w-[390px]"
      }`}
    >
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">{t("title")}</h3>
          {!isCollapsed && <p className="truncate text-xs text-muted">{selectedFieldLabel}</p>}
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1.5">
          {!isCollapsed && (
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
              <span className="min-w-8 text-center text-[11px] text-muted">{versionPosition}</span>
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
          )}
          <button
            type="button"
            className="flex h-7 w-7 items-center justify-center rounded-full text-muted hover:bg-background hover:text-foreground"
            onClick={() => setIsCollapsed((current) => !current)}
            title={isCollapsed ? t("expandPanel") : t("collapsePanel")}
            aria-label={isCollapsed ? t("expandPanel") : t("collapsePanel")}
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
              className={`transition-transform ${isCollapsed ? "rotate-180" : ""}`}
            >
              <path d="m18 15-6-6-6 6" />
            </svg>
          </button>
        </div>
      </div>

      {!isCollapsed && (
        <>
      <div className="max-h-64 min-h-40 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 ? (
          <div className="flex h-28 items-center justify-center rounded-lg border border-dashed border-border/70 text-xs text-muted">
            {t("emptyMessages")}
          </div>
        ) : (
          messages.map((message) => {
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
                      ? "bg-accent text-white"
                      : "border border-border bg-background text-foreground"
                  }`}
                >
                  {message.content}
                </div>
                {isFailedMessage && (
                  <span
                    className="mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-red-300 bg-red-50 text-[11px] font-semibold text-red-600 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
                    title={message.error_message || t("requestFailed")}
                    aria-label={t("requestFailed")}
                  >
                    !
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="border-t border-border/60 p-3">
        {error && (
          <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            <div>{error}</div>
            {retryRequest && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2 h-7 border-red-300 px-2 text-xs text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/60"
                onPress={handleRetry}
                isDisabled={sending}
              >
                {sending ? t("sending") : t("retry")}
              </Button>
            )}
          </div>
        )}

        <textarea
          className="min-h-20 w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:outline-none focus:ring-2 focus:ring-primary"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("placeholder")}
          disabled={sending || providerLoading || providers.length === 0}
        />

        <div className="mt-2 flex items-center gap-2">
          <select
            className={`${inlineSelectClassName} max-w-[10rem]`}
            value={selectedField}
            onChange={(event) => setSelectedField(event.target.value as NovelRewriteFieldKey)}
            disabled={sending}
            title={t("field")}
          >
            {REWRITABLE_NOVEL_FIELDS.map((field) => (
              <option key={field} value={field}>
                {tn(FIELD_LABEL_MAP[field])}
              </option>
            ))}
          </select>

          <div className="ml-auto flex min-w-0 items-center gap-2">
            <select
              className={`${inlineSelectClassName} max-w-[12rem]`}
              value={selectedProvider}
              onChange={(event) => setSelectedProvider(event.target.value)}
              disabled={sending || providerLoading || providers.length === 0}
              title={t("provider")}
            >
              {providers.length === 0 ? (
                <option value="">{providerLoading ? t("loadingProviders") : t("noProvider")}</option>
              ) : (
                providers.map((provider) => (
                  <option key={provider} value={provider}>
                    {provider}
                  </option>
                ))
              )}
            </select>

            <Button
              variant="primary"
              size="sm"
              className="h-8 shrink-0 bg-accent px-3 text-white hover:bg-accent-hover"
              onPress={handleSend}
              isDisabled={!canSend}
            >
              {sending ? t("sending") : t("send")}
            </Button>
          </div>
        </div>
      </div>
        </>
      )}
    </aside>
  );
}
