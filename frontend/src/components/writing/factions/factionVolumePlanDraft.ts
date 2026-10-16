import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { FactionVolumeStateFields, FactionVolumeStateReadV1 } from "@/types/factionVolumeState";

/** 本卷人工参与计划的输入和已派发原请求；与 AI 候选、实际事实稿隔离。 */
export interface FactionVolumeRequestDraft<T> {
  key: string;
  revision: number;
  command?: { key: string; path: string; method: "POST" | "PUT"; body: Record<string, unknown>; unknown: boolean; saved?: T };
}

export interface FactionVolumePlanDraft extends FactionVolumeRequestDraft<FactionVolumeStateReadV1> {
  editor: { factionId: string; volumeId: string; source: FactionVolumeStateReadV1 | null; section?: "participation" | "agenda" };
  fields: FactionVolumeStateFields;
}

export const factionVolumePlanScope = (novelId: string, volumeId: string) => `${novelId}:faction-volume-plans:${volumeId}`;
const failure = () => new Error("FACTION_PLAN_LOCAL_CONFLICT");

/** 只读同卷原稿；未知请求不会因卷或势力版本变化被覆盖。 */
export async function readFactionVolumePlanDraft<T extends FactionVolumeRequestDraft<unknown> = FactionVolumePlanDraft>(scope: string): Promise<T | null> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly"), request = tx.objectStore("business_drafts").get(scope);
    tx.oncomplete = () => resolve(request.result?.value ?? null);
    tx.onerror = tx.onabort = () => reject(failure());
  }); } finally { db.close(); }
}

/** CAS 保稿；请求登记后禁止改键改内容，成功先保留再由当前页清理。 */
export async function writeFactionVolumePlanDraft<T extends FactionVolumeRequestDraft<unknown> = FactionVolumePlanDraft>(scope: string, value: T | null,
  expected: T | null, resolution?: "rejected" | "revised" | "saved"): Promise<void> {
  const next = structuredClone(value), original = structuredClone(expected), db = await openTaskFlowDatabase();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), request = store.get(scope);
    let failed = false;
    request.onsuccess = () => {
      const current = (request.result?.value ?? null) as T | null;
      const command = current?.command;
      const same = command && next?.command && command.key === next.command.key && command.path === next.command.path
        && command.method === next.command.method && JSON.stringify(command.body) === JSON.stringify(next.command.body);
      const success = resolution === "saved" && same && next?.command?.saved;
      const revise = resolution === "revised" && command?.unknown === false && !command.saved && !next?.command;
      const bad = JSON.stringify(current) !== JSON.stringify(original) && !success
        || command && !same && !revise && !(next === null && command.saved)
        || command?.saved && next && !next.command?.saved
        || command?.unknown && next?.command?.unknown === false && !success && resolution !== "rejected";
      if (bad) { failed = true; tx.abort(); return; }
      if (revise && current) store.put({ key: `${scope}:rejected:${current.command!.key}`, scope: `${scope}:rejected`, base_version: 0, value: current, updated_at: Date.now() });
      if (next === null) store.delete(scope);
      else store.put({ key: scope, scope, base_version: 0, value: next, updated_at: Date.now() });
    };
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(failed ? failure() : tx.error ?? failure());
  }); } finally { db.close(); }
}
