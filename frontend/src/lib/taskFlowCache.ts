import type { TaskFlow } from "@/types/taskFlow";

export interface TaskFlowEditDraft {
  flow_id: string;
  base_revision: number;
  definition: TaskFlow;
  updated_at: number;
}

/** 功能：打开任务缓存与业务草稿共用数据库。Args: 无。Returns: 本次使用后需关闭的连接。 */
export function openTaskFlowDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("novel-task-flow", 3);
    request.onupgradeneeded = () => {
      request.result.createObjectStore("completed_nodes", { keyPath: "key" });
      request.result.createObjectStore("editor_drafts", { keyPath: "flow_id" });
      const drafts = request.result.createObjectStore("business_drafts", { keyPath: "key" });
      drafts.createIndex("scope", "scope");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** 功能：读取方案尚未保存的编辑内容。Args: flowId 方案 ID。Returns: 草稿及编辑时的修订号，未编辑时为空。 */
export async function readTaskFlowEditDraft(
  flowId: string,
): Promise<TaskFlowEditDraft | null> {
  if (typeof indexedDB === "undefined") return null;
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const read = db
        .transaction("editor_drafts", "readonly")
        .objectStore("editor_drafts")
        .get(flowId);
      read.onsuccess = () => resolve(read.result ?? null);
      read.onerror = () => reject(read.error);
    });
  } finally {
    db.close();
  }
}

/** 功能：保存编辑草稿，或在保存完成后清除它。Args: flowId 方案 ID；definition 当前草稿，空值表示清除。Returns: 写入完成。 */
export async function writeTaskFlowEditDraft(
  flowId: string,
  definition: TaskFlow | null,
): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("editor_drafts", "readwrite");
      const store = transaction.objectStore("editor_drafts");
      if (definition)
        store.put({
          flow_id: flowId,
          base_revision: definition.revision,
          definition,
          updated_at: Date.now(),
        } satisfies TaskFlowEditDraft);
      else store.delete(flowId);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    db.close();
  }
}
