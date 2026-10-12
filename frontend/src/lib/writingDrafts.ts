import { openTaskFlowDatabase } from "./taskFlowCache";

export interface WritingDraft<T> {
  key: string;
  scope: string;
  base_version: number;
  value: T;
  updated_at: number;
}

/** 功能：读取当前小说节点的本地稿。Args: key 小说、节点及稿件种类组成的键。Returns: 原稿及其基准版本。 */
export async function readWritingDraft<T>(key: string, version?: number): Promise<WritingDraft<T> | null> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction("business_drafts", "readonly").objectStore("business_drafts").index("scope").getAll(key);
      request.onsuccess = () => {
        const drafts = request.result as WritingDraft<T>[];
        resolve(drafts.find((draft) => draft.base_version === version) ?? drafts.sort((a, b) => b.updated_at - a.updated_at)[0] ?? null);
      };
      request.onerror = () => reject(request.error);
    });
  } finally { db.close(); }
}

/** 功能：保存或清除本地稿，不写入作品。Args: key 稿件键；version 基准版本；value 原稿，null表示清除。Returns: 存储完成。 */
export async function writeWritingDraft<T>(key: string, version: number, value: T | null): Promise<void> {
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      if (value === null) store.delete(`${key}:${version}`);
      else store.put({ key: `${key}:${version}`, scope: key, base_version: version, value, updated_at: Date.now() });
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } finally { db.close(); }
}
