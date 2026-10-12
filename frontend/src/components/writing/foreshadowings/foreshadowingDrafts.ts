import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { Foreshadowing, ForeshadowingPlan, ForeshadowingEvidenceInput, ForeshadowingStatus } from "@/types/foreshadowing";

export interface ForeshadowingDraft {
  key: string;
  revision: number;
  source: Foreshadowing | null;
  mode: "plan" | "records" | "delete" | "restore" | "hard-delete";
  plan: ForeshadowingPlan;
  status: ForeshadowingStatus;
  planted_evidence: ForeshadowingEvidenceInput | null;
  resolved_evidence: ForeshadowingEvidenceInput | null;
  command?: { action: "create" | "patch" | "records" | "delete" | "restore" | "hard-delete"; body: object; key: string; saved?: Foreshadowing | { deleted: true }; unknown?: boolean };
}

/** 功能：读取本书各自独立的伏笔草稿和原请求。Args: scope 本书范围。Returns: 按时间排列的稿件。 */
export async function readForeshadowingDrafts(scope: string): Promise<ForeshadowingDraft[]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const request = transaction.objectStore("business_drafts").index("scope").getAll(scope);
      const operations = transaction.objectStore("business_drafts").index("scope").getAll(`${scope}:operations`);
      let rows: WritingDraft<ForeshadowingDraft>[] = [];
      request.onsuccess = () => { rows = request.result; };
      transaction.oncomplete = () => resolve(rows.sort((a, b) => a.updated_at - b.updated_at).map((row) => {
        const draft = row.value;
        const saved = draft.command && operations.result.find((operation: WritingDraft<{ key: string }>) => operation.value.key === draft.command!.key)?.value.saved;
        return saved ? { ...draft, command: { ...draft.command!, saved, unknown: false } } : draft;
      }));
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
    });
  } finally { db.close(); }
}

/** 功能：只写或清理自己的稿件，事务结束后才允许网络提交。Args: scope 本书范围；draft 独立稿件；expectedRevision 已读本机版本，新稿为 null；remove 是否清理。Returns: 本地事务读到的成功回执；未确认时为 undefined。 */
export async function writeForeshadowingDraft(scope: string, draft: ForeshadowingDraft, expectedRevision: number | null, remove = false): Promise<NonNullable<ForeshadowingDraft["command"]>["saved"]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise<NonNullable<ForeshadowingDraft["command"]>["saved"]>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const key = `${scope}:${draft.key}`;
      let conflict = false;
      let savedReceipt: NonNullable<ForeshadowingDraft["command"]>["saved"];
      const current = store.get(key);
      current.onsuccess = () => {
        const previous = current.result as WritingDraft<ForeshadowingDraft> | undefined;
        if ((previous?.value.revision ?? null) !== expectedRevision) { conflict = true; transaction.abort(); return; }
        if (remove) { store.delete(key); return; }
        if (previous && draft.revision <= previous.value.revision && JSON.stringify(draft) !== JSON.stringify(previous.value)) { conflict = true; transaction.abort(); return; }
        if (draft.command) {
          // 冻结命令单独登记；同一原键只能对应同一目标和载荷，不能被另一个编辑器覆盖。
          const operationKey = `${scope}:operation:${draft.command.key}`;
          const operation = store.get(operationKey);
          operation.onsuccess = () => {
            const frozen = { action: draft.command!.action, body: draft.command!.body, key: draft.command!.key, target: draft.source?.foreshadowing_id ?? null };
            const previous = operation.result?.value;
            if (previous && JSON.stringify({ action: previous.action, body: previous.body, key: previous.key, target: previous.target }) !== JSON.stringify(frozen)) { conflict = true; transaction.abort(); return; }
            if (!operation.result) store.add({ key: operationKey, scope: `${scope}:operations`, base_version: draft.source?.version ?? 0, value: { ...frozen, ...(draft.command!.saved ? { saved: draft.command!.saved } : {}) }, updated_at: Date.now() });
            else if (draft.command!.saved && !previous.saved) store.put({ ...operation.result, value: { ...previous, saved: draft.command!.saved } });
            savedReceipt = previous?.saved ?? draft.command!.saved;
          };
        }
        store.put({ key, scope, base_version: draft.source?.version ?? 0, value: draft, updated_at: Date.now() } satisfies WritingDraft<ForeshadowingDraft>);
      };
      transaction.oncomplete = () => resolve(savedReceipt);
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(conflict ? new Error("FORESHADOWING_LOCAL_CONFLICT") : transaction.error);
    });
  } finally { db.close(); }
}
