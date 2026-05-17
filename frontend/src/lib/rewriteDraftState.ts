import type {
  NovelRewriteFieldKey,
  RewriteChatMessage,
  RewriteFieldRevision,
  WritingDraftRewriteState,
} from "@/types/novel";

function createClientId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}_${crypto.randomUUID()}`;
  }

  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function normalizeRewriteValue(value: unknown): string | string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }

  return String(value ?? "").trim();
}

function cloneRewriteState(state?: WritingDraftRewriteState): WritingDraftRewriteState {
  const normalized = normalizeRewriteState(state);

  return {
    messagesByField: Object.fromEntries(
      Object.entries(normalized.messagesByField).map(([field, messages]) => [
        field,
        (messages || []).map((message) => ({ ...message })),
      ]),
    ),
    revisionsByField: Object.fromEntries(
      Object.entries(normalized.revisionsByField).map(([field, revisions]) => [
        field,
        [...(revisions || [])],
      ]),
    ),
    activeRevisionIdByField: { ...normalized.activeRevisionIdByField },
  };
}

function rewriteValuesEqual(left: unknown, right: unknown): boolean {
  return JSON.stringify(normalizeRewriteValue(left)) === JSON.stringify(normalizeRewriteValue(right));
}

/**
 * 规范化草稿里的 AI 改写状态。
 *
 * Args:
 *   state: localStorage 中读取到的原始改写状态。
 *
 * Returns:
 *   带有完整容器字段的改写状态。
 */
export function normalizeRewriteState(state?: WritingDraftRewriteState): WritingDraftRewriteState {
  return {
    messagesByField: state?.messagesByField || {},
    revisionsByField: state?.revisionsByField || {},
    activeRevisionIdByField: state?.activeRevisionIdByField || {},
  };
}

/**
 * 创建一条可持久化的字段改写聊天消息。
 *
 * Args:
 *   role: 消息角色，user 表示用户，assistant 表示 AI。
 *   targetField: 消息所属的改写字段。
 *   content: 消息正文。
 *   options: 可选消息元数据，例如本次请求使用的 Provider。
 *
 * Returns:
 *   带本地唯一 ID 与时间戳的聊天消息。
 */
export function createRewriteMessage(
  role: RewriteChatMessage["role"],
  targetField: NovelRewriteFieldKey,
  content: string,
  options: {
    provider?: string;
    status?: RewriteChatMessage["status"];
    errorMessage?: string;
  } = {},
): RewriteChatMessage {
  const message: RewriteChatMessage = {
    id: createClientId("msg"),
    role,
    target_field: targetField,
    content,
    created_at: new Date().toISOString(),
  };

  if (options.provider) {
    message.provider = options.provider;
  }
  if (options.status) {
    message.status = options.status;
  }
  if (options.errorMessage) {
    message.error_message = options.errorMessage;
  }

  return message;
}

/**
 * 向指定字段追加一条聊天消息。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 消息所属字段。
 *   message: 需要追加的消息。
 *
 * Returns:
 *   追加消息后的新改写状态。
 */
export function appendRewriteMessage(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  message: RewriteChatMessage,
): WritingDraftRewriteState {
  const nextState = cloneRewriteState(state);
  const currentMessages = nextState.messagesByField[targetField] || [];
  nextState.messagesByField[targetField] = [...currentMessages, message];
  return nextState;
}

/**
 * 将指定聊天消息标记为失败。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 失败消息所属字段。
 *   messageId: 失败消息 ID。
 *   errorMessage: 请求返回的错误说明。
 *
 * Returns:
 *   已写入失败状态的新改写状态。
 */
export function markRewriteMessageFailed(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  messageId: string,
  errorMessage: string,
): WritingDraftRewriteState {
  const nextState = cloneRewriteState(state);
  const currentMessages = nextState.messagesByField[targetField] || [];

  nextState.messagesByField[targetField] = currentMessages.map((message) => {
    if (message.id !== messageId) {
      return message;
    }

    // 失败状态持久化到草稿中，刷新后仍能看到该请求没有成功。
    return {
      ...message,
      status: "failed",
      error_message: errorMessage,
    };
  });

  return nextState;
}

/**
 * 清除指定聊天消息上的失败标记。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 消息所属字段。
 *   messageId: 需要清除失败标记的消息 ID。
 *
 * Returns:
 *   清理失败标记后的新改写状态。
 */
export function clearRewriteMessageFailure(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  messageId: string,
): WritingDraftRewriteState {
  const nextState = cloneRewriteState(state);
  const currentMessages = nextState.messagesByField[targetField] || [];

  nextState.messagesByField[targetField] = currentMessages.map((message) => {
    if (message.id !== messageId) {
      return message;
    }

    const nextMessage = { ...message };
    delete nextMessage.status;
    delete nextMessage.error_message;
    return nextMessage;
  });

  return nextState;
}

/**
 * 确保字段当前表单值已进入版本栈。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 需要维护版本的字段。
 *   value: 字段当前表单值。
 *
 * Returns:
 *   包含当前值版本的新改写状态。
 */
export function ensureFieldCurrentRevision(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  value: unknown,
): WritingDraftRewriteState {
  const nextState = cloneRewriteState(state);
  const revisions = nextState.revisionsByField[targetField] || [];
  const existing = revisions.find((revision) => rewriteValuesEqual(revision.value, value));

  if (existing) {
    nextState.activeRevisionIdByField[targetField] = existing.id;
    return nextState;
  }

  const revision: RewriteFieldRevision = {
    id: createClientId("rev"),
    value: normalizeRewriteValue(value),
    source: revisions.length > 0 ? "manual" : "initial",
    created_at: new Date().toISOString(),
  };

  nextState.revisionsByField[targetField] = [...revisions, revision];
  nextState.activeRevisionIdByField[targetField] = revision.id;
  return nextState;
}

/**
 * 追加一条 AI 改写版本并设为当前版本。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 被改写字段。
 *   value: AI 返回的新字段值。
 *   instruction: 触发该版本的用户需求。
 *
 * Returns:
 *   已追加 AI 版本的新改写状态。
 */
export function appendAiRewriteRevision(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  value: unknown,
  instruction: string,
): WritingDraftRewriteState {
  const nextState = cloneRewriteState(state);
  const revisions = nextState.revisionsByField[targetField] || [];
  const revision: RewriteFieldRevision = {
    id: createClientId("rev"),
    value: normalizeRewriteValue(value),
    source: "ai",
    instruction,
    created_at: new Date().toISOString(),
  };

  nextState.revisionsByField[targetField] = [...revisions, revision];
  nextState.activeRevisionIdByField[targetField] = revision.id;
  return nextState;
}

/**
 * 选择指定字段的历史版本。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 需要切换版本的字段。
 *   revisionId: 目标版本 ID。
 *
 * Returns:
 *   命中的版本与切换后的改写状态。
 */
export function selectRewriteRevision(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
  revisionId: string,
): { revision: RewriteFieldRevision | null; state: WritingDraftRewriteState } {
  const nextState = cloneRewriteState(state);
  const revision = (nextState.revisionsByField[targetField] || []).find((item) => item.id === revisionId) || null;

  if (revision) {
    nextState.activeRevisionIdByField[targetField] = revision.id;
  }

  return { revision, state: nextState };
}

/**
 * 读取指定字段的版本列表。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 目标字段。
 *
 * Returns:
 *   该字段的版本数组。
 */
export function getFieldRevisions(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
): RewriteFieldRevision[] {
  return normalizeRewriteState(state).revisionsByField[targetField] || [];
}

/**
 * 获取指定字段当前激活的版本 ID。
 *
 * Args:
 *   state: 当前改写状态。
 *   targetField: 目标字段。
 *
 * Returns:
 *   激活版本 ID；没有版本时返回空字符串。
 */
export function getActiveRevisionId(
  state: WritingDraftRewriteState | undefined,
  targetField: NovelRewriteFieldKey,
): string {
  return normalizeRewriteState(state).activeRevisionIdByField[targetField] || "";
}

/**
 * 将改写字段值转为对话中展示的文本。
 *
 * Args:
 *   value: 字段值，标签字段可能是字符串数组。
 *
 * Returns:
 *   可读的字段内容。
 */
export function formatRewriteValueForDisplay(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean).join("、");
  }

  return String(value ?? "").trim();
}
