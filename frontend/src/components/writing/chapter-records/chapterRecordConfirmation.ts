"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api";
import { writeChapterRecordDraft, writeChapterRecordReceipt, type ChapterRecordDraft } from "./chapterRecordDrafts";

export type ChapterRecordCommand = NonNullable<ChapterRecordDraft["command"]>;
export type ChapterRecordReceipt = NonNullable<ChapterRecordCommand["saved"]>;
export type ConfirmationStage = "register" | "write" | "receipt" | "readback" | "cleanup";

/** 功能：两个确认表单共用本地写入队列和版本核对。Args: scope 固定稿件范围；failureMessage 本地错误。Returns: 保存、清理及原事务队列。 */
export function useChapterRecordPersistence(scope: string, failureMessage: string) {
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const persisted = useRef(new Map<string, number>());
  const alive = useRef(true);
  const [localError, setLocalError] = useState("");
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const persist = (draft: ChapterRecordDraft, expectedRevision?: number) => {
    const write = queue.current.catch(() => {}).then(async () => {
      // 回执先独立提交，随后草稿失去编辑权也不能回滚已知成功。
      const saved = draft.command?.saved ? await writeChapterRecordReceipt(scope, draft.command) : undefined;
      const stored = saved ? { ...draft, command: { ...draft.command!, saved, unknown: false } } : draft;
      const receipt = await writeChapterRecordDraft(scope, stored, expectedRevision ?? persisted.current.get(draft.key) ?? null);
      persisted.current.set(draft.key, draft.revision);
      return saved ?? receipt;
    });
    queue.current = write;
    void write.then(() => { if (alive.current) setLocalError(""); }, () => { if (alive.current) setLocalError(failureMessage); });
    return write;
  };
  const remove = async (draft: ChapterRecordDraft) => {
    await queue.current;
    await writeChapterRecordDraft(scope, draft, persisted.current.get(draft.key) ?? draft.revision, true);
    persisted.current.delete(draft.key);
  };
  return { queue, persisted, persist, remove, localError, setLocalError };
}

/** 功能：先冻结本地请求，再核对回执、提交、读回与清稿。Args: options 两个固定表单的请求及当前读取。Returns: 成功或保留原稿的明确失败阶段。 */
export async function confirmChapterRecord(options: {
  draft: ChapterRecordDraft;
  command: () => ChapterRecordCommand;
  persist: (draft: ChapterRecordDraft, expectedRevision?: number) => Promise<ChapterRecordCommand["saved"]>;
  remove: (draft: ChapterRecordDraft) => Promise<void>;
  send: (command: ChapterRecordCommand) => Promise<ChapterRecordReceipt>;
  readback: (receipt: ChapterRecordReceipt) => Promise<void>;
  update: (draft: ChapterRecordDraft) => void;
}): Promise<
  | { ok: true; draft: ChapterRecordDraft; receipt: ChapterRecordReceipt }
  | { ok: false; draft: ChapterRecordDraft; stage: ConfirmationStage; error: unknown; rolledBack: boolean }
> {
  let session = options.draft;
  const authorDraft = session.command ? null : session;
  const wasUnknown = Boolean(session.command && session.command.unknown !== false);
  let stage: ConfirmationStage = session.command?.saved ? "receipt" : "register";
  try {
    if (!session.command) session = { ...session, command: options.command(), revision: session.revision + 1 };
    else if (!session.command.saved) session = { ...session, revision: session.revision + 1, command: { ...session.command, unknown: true } };
    options.update(session);
    let command = session.command!;
    // 其他标签页已有确定回执时，先沿用它，不能被现在的版本变化挡住。
    const receipt = await options.persist(session);
    if (receipt && JSON.stringify(command.saved) !== JSON.stringify(receipt)) {
      command = { ...command, saved: receipt, unknown: false };
      session = { ...session, command, revision: session.revision + 1 };
      options.update(session);
      stage = "receipt";
      await options.persist(session);
    }
    if (!command.saved) {
      stage = "write";
      const saved = await options.send(command);
      command = { ...command, saved, unknown: false };
      session = { ...session, command, revision: session.revision + 1 };
      options.update(session);
      stage = "receipt";
      await options.persist(session);
    }
    if (!command.readbackDone) {
      stage = "readback";
      await options.readback(command.saved!);
      command = { ...command, readbackDone: true };
      session = { ...session, command, revision: session.revision + 1 };
      options.update(session);
      stage = "receipt";
      await options.persist(session);
    }
    stage = "cleanup";
    await options.remove(session);
    return { ok: true, draft: session, receipt: command.saved! };
  } catch (error) {
    const rolledBack = stage === "register" && Boolean(authorDraft);
    if (rolledBack) { session = authorDraft!; options.update(session); }
    // 断响应之后的 409 仍不能证明原请求失败，继续保留原键核对。
    if (stage === "write" && !wasUnknown && error instanceof ApiRequestError && error.status >= 400 && error.status < 500
      && !(session.command?.action === "confirm-character-relation-state" && error.status === 409)) {
      const rejected = { ...session, command: { ...session.command!, unknown: false }, revision: session.revision + 1 };
      try {
        // 只确认本次发出请求的版本；迟到拒绝不能解锁另一页已接手的稿。
        const saved = await options.persist(rejected, session.revision);
        session = saved ? { ...rejected, command: { ...rejected.command, saved, unknown: false } } : rejected;
        options.update(session);
      } catch { /* 拒绝未落盘时保留原请求的未知状态。 */ }
    }
    return { ok: false, draft: session, stage, error, rolledBack };
  }
}
