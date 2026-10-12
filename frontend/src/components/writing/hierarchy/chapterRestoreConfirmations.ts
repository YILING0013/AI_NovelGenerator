import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { HierarchyRecord } from "@/types/hierarchy";

export type ChapterRestoreCommand = { chapter_id: string; revision: number; key: string; expected_version: number; saved?: HierarchyRecord };

/** 功能：按时间读取本章各自独立的恢复请求，不提交网络。Args: scope 本章恢复范围。Returns: 原确认键及成功快照。 */
export async function readChapterRestoreConfirmations(scope: string): Promise<WritingDraft<ChapterRestoreCommand>[]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const request = transaction.objectStore("business_drafts").index("scope").getAll(scope);
      let drafts: WritingDraft<ChapterRestoreCommand>[] = [];
      request.onsuccess = () => { drafts = request.result; };
      transaction.oncomplete = () => resolve(drafts.sort((a, b) => a.updated_at - b.updated_at || a.key.localeCompare(b.key)));
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

/** 功能：在本地事务内只登记或清理自己的恢复请求，别的标签页原键不受影响。Args: scope 章节范围；command 冻结三元组及键；remove 是否只清此键。Returns: 本地事务提交完成。 */
export async function writeChapterRestoreConfirmation(scope: string, command: ChapterRestoreCommand, remove = false): Promise<void> {
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const key = `${scope}:${command.key}`;
      if (remove) store.delete(key);
      else store.put({ key, scope, base_version: command.expected_version, value: command, updated_at: Date.now() } satisfies WritingDraft<ChapterRestoreCommand>);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}
