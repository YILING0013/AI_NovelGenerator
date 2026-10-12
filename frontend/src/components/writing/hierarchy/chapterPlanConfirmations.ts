import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { GenerationDraft } from "./HierarchyGeneration";

/**
 * 读取当前场景尚未交付完成的章计划确认，按保存时间逐个恢复。
 *
 * Args:
 *   generationScope: 当前场景原有的生成草稿范围。
 * Returns:
 *   各确认键独立保存的冻结请求、被拒绝的候选和成功回执；读取不提交确认。
 */
export async function readChapterPlanConfirmations(generationScope: string): Promise<WritingDraft<GenerationDraft>[]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const request = transaction.objectStore("business_drafts").index("scope").getAll(`${generationScope}:confirmations`);
      let drafts: WritingDraft<GenerationDraft>[] = [];
      request.onsuccess = () => { drafts = request.result as WritingDraft<GenerationDraft>[]; };
      transaction.oncomplete = () => resolve(drafts.sort((a, b) => a.updated_at - b.updated_at || a.key.localeCompare(b.key)));
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

/**
 * 按确认键保存章计划请求和回执，避免另一标签页的新候选覆盖恢复依据。
 *
 * Args:
 *   generationScope: 当前场景原有的生成草稿范围。
 *   baseVersion: 候选开始时的版本。
 *   confirmationKey: 本次确认的固定身份。
 *   value: 完整请求、被拒绝的候选或成功回执；null 只清理本次确认。
 *   previousKey: 修改被拒绝的候选后，新确认需要替换的旧条目。
 * Returns:
 *   本地事务提交完成；失败时由原生成弹窗保留恢复入口。
 */
export async function writeChapterPlanConfirmation(
  generationScope: string,
  baseVersion: number,
  confirmationKey: string,
  value: GenerationDraft | null,
  previousKey?: string,
): Promise<void> {
  const scope = `${generationScope}:confirmations`;
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      let failure: unknown;
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(failure ?? transaction.error);
      transaction.onabort = () => reject(failure ?? transaction.error);
      try {
        if (value !== null) store.put({ key: `${scope}:${confirmationKey}`, scope, base_version: baseVersion, value, updated_at: Date.now() } satisfies WritingDraft<GenerationDraft>);
        const removedKey = value === null ? confirmationKey : previousKey !== confirmationKey ? previousKey : undefined;
        if (removedKey) {
          store.delete(`${scope}:${removedKey}`);
          // 新请求与旧稿的清理一起提交，且不能清掉另一标签页的候选。
          const shared = store.get(`${generationScope}:${baseVersion}`);
          shared.onsuccess = () => {
            try {
              const draft = shared.result as WritingDraft<GenerationDraft> | undefined;
              if (draft?.value.command?.key === removedKey) store.delete(`${generationScope}:${baseVersion}`);
            } catch (error) { failure = error; transaction.abort(); }
          };
        }
      } catch (error) {
        failure = error;
        transaction.abort();
      }
    });
  } finally { db.close(); }
}
