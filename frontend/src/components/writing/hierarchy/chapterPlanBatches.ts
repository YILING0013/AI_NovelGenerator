import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { SavedChapterBatch } from "./ChapterContinuation";

/**
 * 在同一个本地事务中登记章计划批次，避免不同工作台或标签页互相覆盖。
 *
 * Args:
 *   batch: 正式确认返回的章节、确认键和原父链。
 *   messages: 确认身份冲突和本地保存失败的界面提示。
 * Returns:
 *   事务提交后，该场景已经登记的全部批次。
 */
export async function registerSavedChapterBatch(
  batch: SavedChapterBatch,
  messages: { conflict: string; failed: string },
): Promise<SavedChapterBatch[]> {
  const scope = `${batch.scene.record.novel_id}:scene:${batch.scene.id}:chapter-plan-batches`;
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise<SavedChapterBatch[]>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      let items: SavedChapterBatch[] = [];
      let failure: unknown;
      transaction.oncomplete = () => resolve(items);
      transaction.onerror = () => reject(failure ?? transaction.error ?? new Error(messages.failed));
      transaction.onabort = () => reject(failure ?? transaction.error ?? new Error(messages.failed));
      const request = store.get(`${scope}:0`);
      request.onsuccess = () => {
        try {
          const stored = request.result as WritingDraft<SavedChapterBatch[]> | undefined;
          items = stored?.value ?? [];
          const existing = items.find((item) => item.confirmationKey === batch.confirmationKey);
          if (existing && JSON.stringify(existing.ids) !== JSON.stringify(batch.ids)) {
            failure = new Error(messages.conflict);
            transaction.abort();
            return;
          }
          if (!existing) {
            items = [...items, batch];
            store.put({ key: `${scope}:0`, scope, base_version: 0, value: items, updated_at: Date.now() } satisfies WritingDraft<SavedChapterBatch[]>);
          }
        } catch (error) {
          failure = error;
          transaction.abort();
        }
      };
    });
  } finally { db.close(); }
}
