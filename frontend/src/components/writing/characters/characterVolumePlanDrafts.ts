import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { CharacterVolumePlanFieldsV1, CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";

export interface CharacterVolumePlanDraft {
  key: string;
  revision: number;
  editor: { characterId: string; volumeId: string; source: CharacterVolumeStateReadV1 | null;
    section?: "participation" | "relationships"; adopted?: boolean };
  fields: CharacterVolumePlanFieldsV1;
  previousPlanUse: "pristine" | "edited" | "used";
  command?: { key: string; path: string; method: "POST" | "PUT"; body: Record<string, unknown>;
    unknown: boolean; saved?: CharacterVolumeStateReadV1 };
}
type Command = NonNullable<CharacterVolumePlanDraft["command"]>;
const failure = () => new Error("CHARACTER_PLAN_LOCAL_CONFLICT");
const sameCommand = (left: Command, right: Command) => left.key === right.key && left.path === right.path
  && left.method === right.method && JSON.stringify(left.body) === JSON.stringify(right.body);

/** 功能：读取同卷独立计划稿及原成功回执。Args: 小说和卷组成的范围。Returns: 待作者明确恢复的原稿。 */
export async function readCharacterVolumePlanDrafts(scope: string): Promise<CharacterVolumePlanDraft[]> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly"), store = tx.objectStore("business_drafts");
    const drafts = store.index("scope").getAll(scope), operations = store.index("scope").getAll(`${scope}:operations`);
    tx.oncomplete = () => {
      const commands = new Map((operations.result as WritingDraft<Command>[]).map((row) => [row.value.key, row.value]));
      resolve((drafts.result as WritingDraft<CharacterVolumePlanDraft>[]).map(({ value }) => {
        const saved = value.command && commands.get(value.command.key)?.saved;
        return saved ? { ...value, command: { ...value.command!, saved, unknown: false } } : value;
      }));
    };
    tx.onerror = tx.onabort = () => reject(tx.error ?? failure());
  }); } finally { db.close(); }
}

/** 功能：同事务比较原稿、冻结请求或精确清稿。Args: 范围、新稿、持有版本、清理及明确拒绝标记。Returns: 原成功优先，否则本次保存的稿。 */
export async function writeCharacterVolumePlanDraft(scope: string, value: CharacterVolumePlanDraft,
  expected: CharacterVolumePlanDraft | null, remove = false, rejected = false): Promise<CharacterVolumePlanDraft> {
  const next = structuredClone(value), original = structuredClone(expected), db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    const key = `${scope}:${next.key}`, request = store.get(key);
    let conflict = false, result = next;
    const abort = () => { conflict = true; tx.abort(); };
    request.onsuccess = () => {
      const current = (request.result?.value ?? null) as CharacterVolumePlanDraft | null;
      const commit = (operation?: Command) => {
        if (operation && (!next.command || !sameCommand(operation, next.command))) { abort(); return; }
        // 另一页已经清稿时仍保留成功标记，旧页只做读回／清理。
        if (operation?.saved) result = { ...(current ?? next), command: { ...(current?.command ?? next.command!), saved: operation.saved, unknown: false } };
        if (!remove && operation?.saved) return;
        const comparable = current?.command && operation?.saved
          ? { ...current, command: { ...current.command, saved: operation.saved, unknown: false } } : current;
        if (JSON.stringify(comparable) !== JSON.stringify(original) && !(remove && !current && operation?.saved)) { abort(); return; }
        if (current?.command && (!next.command || !sameCommand(current.command, next.command))
          && (current.command.unknown || current.command.saved)) { abort(); return; }
        if (current?.command?.unknown && next.command?.unknown === false && !rejected && !operation?.saved) { abort(); return; }
        if (remove) {
          if (next.command?.unknown && !operation?.saved) { abort(); return; }
          store.delete(key);
        } else {
          if (next.command && !operation) store.add({ key: `${scope}:operation:${next.command.key}`, scope: `${scope}:operations`,
            base_version: next.editor.source?.version ?? 0, value: next.command, updated_at: Date.now() });
          store.put({ key, scope, base_version: next.editor.source?.version ?? 0, value: next, updated_at: Date.now() });
        }
      };
      if (next.command) {
        const command = store.get(`${scope}:operation:${next.command.key}`);
        command.onsuccess = () => commit(command.result?.value);
      } else commit();
    };
    tx.oncomplete = () => resolve(result);
    tx.onerror = tx.onabort = () => reject(conflict ? failure() : tx.error ?? failure());
  }); } finally { db.close(); }
}

/** 功能：持久保存原请求成功，迟到响应只更新原回执。Args: 范围、冻结请求及完整响应。Returns: 回执写入完成。 */
export async function writeCharacterVolumePlanReceipt(scope: string, command: Command, saved: CharacterVolumeStateReadV1): Promise<void> {
  const db = await openTaskFlowDatabase();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    const request = store.get(`${scope}:operation:${command.key}`);
    request.onsuccess = () => {
      const row = request.result as WritingDraft<Command> | undefined;
      if (!row || !sameCommand(row.value, command)) { tx.abort(); return; }
      if (!row.value.saved) store.put({ ...row, value: { ...row.value, saved, unknown: false }, updated_at: Date.now() });
    };
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(tx.error ?? failure());
  }); } finally { db.close(); }
}
