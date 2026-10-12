"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api";
import { freezeCharacterFactDraft } from "./characterFactDrafts";
import { freezeCharacterRelationFactDraft } from "./characterRelationFactDrafts";
import { freezeItemFactDraft } from "../items/itemFactDrafts";
import { writeFactDraft, writeFactReceipt } from "./factDraftStorage";
import type { FactDomain, FactDraft, FactResult, FactDraftWriteResult } from "./factDraftStorage";
import { writeCharacterFactDraft, writeCharacterFactReceipt } from "./characterFactStorage";
import { writeCharacterRelationFactDraft, writeCharacterRelationFactReceipt } from "./characterRelationFactStorage";

export type FactConfirmationStage = "register" | "write" | "receipt" | "readback" | "cleanup";

/** 功能：沿原确认队列保存事实稿，独立成功先于普通稿写入。Args: 固定域、范围和本地失败提示。Returns: 原事务队列、持有版本及保存清理接口。 */
export function useFactPersistence<D extends FactDraft>(domain: FactDomain, scope: string, failureMessage: string) {
  // 原公开入口保留各域存储函数的签名；物品使用同一个登记流程。
  const writeDraft = (domain === "character" ? writeCharacterFactDraft : domain === "character_relation" ? writeCharacterRelationFactDraft
    : (scope: string, draft: D, expected: number | null, remove = false) => writeFactDraft(domain, scope, draft, expected, remove)) as unknown as (scope: string, draft: D, expectedRevision: number | null, remove?: boolean) => Promise<FactDraftWriteResult<D>>;
  const writeReceipt = (domain === "character" ? writeCharacterFactReceipt : domain === "character_relation" ? writeCharacterRelationFactReceipt
    : (scope: string, command: NonNullable<D["command"]>) => writeFactReceipt(domain, scope, command)) as (scope: string, command: NonNullable<D["command"]>) => Promise<FactResult<D>>;
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const persisted = useRef(new Map<string, number>());
  const alive = useRef(true);
  const [localError, setLocalError] = useState("");
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const persist = (draft: D, expectedRevision?: number) => {
    const write = queue.current.catch(() => {}).then(async () => {
      const saved = draft.command?.saved ? await writeReceipt(scope, draft.command) : undefined;
      const stored = saved ? { ...draft, command: { ...draft.command!, saved, unknown: false } } : draft;
      const result = await writeDraft(scope, stored, expectedRevision ?? persisted.current.get(draft.key) ?? null);
      if (result.written) persisted.current.set(draft.key, draft.revision);
      return result.saved ?? saved;
    });
    queue.current = write;
    void write.then(() => { if (alive.current) setLocalError(""); }, () => { if (alive.current) setLocalError(failureMessage); });
    return write;
  };
  const remove = (draft: D) => {
    const cleanup = queue.current.then(async () => {
      await writeDraft(scope, draft, persisted.current.get(draft.key) ?? draft.revision, true);
      persisted.current.delete(draft.key);
    });
    queue.current = cleanup;
    return cleanup;
  };
  return { queue, persisted, persist, remove, localError, setLocalError };
}

/** 功能：完成本地登记、原请求发送、独立回执、当前资料重读与安全清稿。Args: 宿主提供实际路由及当前读取回调。Returns: 首次成功或保留原稿的明确失败阶段。 */
export async function confirmFact<D extends FactDraft>(options: {
  draft: D;
  key: () => string;
  persist: (draft: D, expectedRevision?: number) => Promise<FactResult<D> | undefined>;
  remove: (draft: D) => Promise<void>;
  send: (command: NonNullable<D["command"]>) => Promise<FactResult<D>>;
  readback: (receipt: FactResult<D>) => Promise<void>;
  update: (draft: D) => void;
}): Promise<
  | { ok: true; draft: D; receipt: FactResult<D> }
  | { ok: false; draft: D; stage: FactConfirmationStage; error: unknown; rolledBack: boolean }
> {
  let session = options.draft;
  const authorDraft = session.command ? null : session;
  const wasUnknown = Boolean(session.command?.unknown);
  let stage: FactConfirmationStage = session.command?.saved ? "receipt" : "register";
  try {
    if (!session.command) session = (session.schema_id === "character.fact.draft" ? freezeCharacterFactDraft(session, options.key())
      : session.schema_id === "character_relation.fact.draft" ? freezeCharacterRelationFactDraft(session, options.key()) : freezeItemFactDraft(session, options.key())) as D;
    // 每次重发前都先登记本次未知结果；加版本让两个页面不能沿同一稿版本同时取得发送权。
    else if (!session.command.saved) session = { ...session, revision: session.revision + 1, command: { ...session.command, unknown: true } };
    options.update(session);
    let command = session.command!;
    const receipt = await options.persist(session);
    if (receipt && JSON.stringify(command.saved) !== JSON.stringify(receipt)) {
      command = { ...command, saved: receipt, unknown: false, readbackDone: false } as NonNullable<D["command"]>;
      session = { ...session, command, revision: session.revision + 1 };
      options.update(session);
      stage = "receipt";
      await options.persist(session);
    }
    if (!command.saved) {
      stage = "write";
      const saved = await options.send(command);
      command = { ...command, saved, unknown: false } as NonNullable<D["command"]>;
      session = { ...session, command, revision: session.revision + 1 };
      options.update(session);
      stage = "receipt";
      const original = await options.persist(session);
      if (original && JSON.stringify(original) !== JSON.stringify(saved)) {
        command = { ...command, saved: original, readbackDone: false } as NonNullable<D["command"]>;
        session = { ...session, command, revision: session.revision + 1 };
        options.update(session);
      }
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
    // 首次明确拒绝也保留原命令；断响应后再遇 409 仍按未知处理，不能换键升级。
    if (stage === "write") {
      let saved: FactResult<D> | undefined;
      if (!wasUnknown && error instanceof ApiRequestError && error.status >= 400 && error.status < 500) {
        const rejected = { ...session, command: { ...session.command!, unknown: false }, revision: session.revision + 1 };
        try {
          // 迟到的拒绝只能修改本次登记的版本；另一页已重试或收到成功时，不能解锁旧稿。
          saved = await options.persist(rejected, session.revision);
          if (!saved) { session = rejected; options.update(session); }
        } catch { /* 未落盘的拒绝不解锁；仍保留原请求的未知状态。 */ }
      } else {
        // 报错期间另一页可能已收到原成功；原回执始终先于普通草稿 CAS。
        saved = await options.persist(session).catch(() => undefined);
      }
      if (saved) {
        session = { ...session, command: { ...session.command!, saved, unknown: false, readbackDone: false }, revision: session.revision + 1 };
        options.update(session);
        return confirmFact({ ...options, draft: session });
      }
    }
    return { ok: false, draft: session, stage, error, rolledBack };
  }
}
