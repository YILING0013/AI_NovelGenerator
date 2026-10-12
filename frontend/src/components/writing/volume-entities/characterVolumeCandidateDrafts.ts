"use client";

import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import type { FlowRef } from "@/types/taskFlow";
import type { VolumeEntityPreview } from "@/types/volumeEntity";

/** 卷人物和势力批次稿沿用现有结构；缺 unknown 的旧命令仍按未知处理。 */
export interface CharacterVolumeCandidateDraft {
  preview: VolumeEntityPreview | null;
  flow_ref: FlowRef | null;
  inputs: Record<string, unknown>;
  params: GenerationParamsValue;
  command: { payload: string; key: string; unknown?: boolean } | null;
  stale: boolean;
  completed?: true;
}
export type CharacterVolumeCandidateEntry = WritingDraft<CharacterVolumeCandidateDraft>;
export type CharacterVolumeCandidateResolution =
  | { kind: "rejected"; previous: CharacterVolumeCandidateEntry | null; registered: CharacterVolumeCandidateEntry }
  | { kind: "revise" }
  | { kind: "saved"; command: { key: string; payload: string } };
export interface CharacterVolumeCandidateWriteResult { written: boolean; current: CharacterVolumeCandidateEntry | null }

function sameCommand(left: CharacterVolumeCandidateDraft["command"], right: CharacterVolumeCandidateDraft["command"]): boolean {
  return Boolean(left && right && left.key === right.key && left.payload === right.payload);
}
function sameEntry(left: CharacterVolumeCandidateEntry | null, right: CharacterVolumeCandidateEntry | null): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}
function currentEntry(rows: CharacterVolumeCandidateEntry[], baseVersion: number): CharacterVolumeCandidateEntry | null {
  const latest = [...rows].sort((left, right) => right.updated_at - left.updated_at);
  return latest.find((row) => row.value.completed)
    ?? latest.find((row) => row.value.command && row.value.command.unknown !== false)
    ?? latest.find((row) => row.value.command)
    ?? latest.find((row) => row.base_version === baseVersion)
    ?? latest[0] ?? null;
}

/** 功能：同卷所有版本中先恢复成功或未知原命令，不能用新版本鲜稿遮住它。Args: 原人物或势力候选 scope 与卷版本。Returns: 必须先处理的原行。 */
export async function readCharacterVolumeCandidateDraft(scope: string, baseVersion: number): Promise<CharacterVolumeCandidateEntry | null> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const request = transaction.objectStore("business_drafts").index("scope").getAll(scope);
      transaction.oncomplete = () => resolve(currentEntry(request.result as CharacterVolumeCandidateEntry[], baseVersion));
      transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error("CHARACTER_VOLUME_CANDIDATE_STORAGE_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：卷人物和势力候选在一笔事务中核对原行后保存或清理，原命令和成功优先。Args: 原 scope、版本、稿或删除、最近成功读取/写入的原行；仅确认阶段传明确结果依据。Returns: 写入后的原行；冲突只返回当前行，不覆盖或删除。 */
export async function writeCharacterVolumeCandidateDraft(
  scope: string,
  baseVersion: number,
  value: CharacterVolumeCandidateDraft | null,
  expected: CharacterVolumeCandidateEntry | null,
  resolution?: CharacterVolumeCandidateResolution,
): Promise<CharacterVolumeCandidateWriteResult> {
  const next = value === null ? null : structuredClone(value);
  const original = expected === null ? null : structuredClone(expected);
  const proof = resolution === undefined ? undefined : structuredClone(resolution);
  const key = `${scope}:${baseVersion}`;
  if (!scope.endsWith(":characters:generation") && !scope.endsWith(":factions:generation")) throw new Error("CHARACTER_VOLUME_CANDIDATE_SCOPE_INVALID");
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const request = store.index("scope").getAll(scope);
      let result!: CharacterVolumeCandidateWriteResult;
      request.onsuccess = () => {
        const current = currentEntry(request.result as CharacterVolumeCandidateEntry[], baseVersion);
        result = { written: false, current };
        const command = current?.value.command ?? null;
        const nextCommand = next?.command ?? null;
        const saved = proof?.kind === "saved" && next?.completed === true && sameCommand(nextCommand, proof.command);
        // 晚成功可越过同原命令的普通稿修改，但不能覆盖另一个请求。
        const sameSavedCommand = saved && sameCommand(command, nextCommand) && current?.key === key;
        if (!sameEntry(current, original) && !sameSavedCommand) return;
        if (current?.value.completed && next && (!next.completed || !sameCommand(command, nextCommand))) return;
        const revising = proof?.kind === "revise" && command?.unknown === false && !current?.value.completed && !nextCommand;
        if (command && !revising && (next === null ? !current?.value.completed : !sameCommand(command, nextCommand))) return;
        if (next?.completed && !current?.value.completed && !saved) return;
        if (nextCommand?.unknown === false && command?.unknown !== false && command) {
          const permittedRejection = proof?.kind === "rejected" && sameEntry(current, proof.registered)
            && sameCommand(proof.registered.value.command, nextCommand)
            && (!proof.previous?.value.command || sameCommand(proof.previous.value.command, nextCommand) && proof.previous.value.command.unknown === false);
          if (!saved && !permittedRejection) return;
        }
        if (next === null) {
          if (current && current.key !== key) return;
          store.delete(key); result = { written: true, current: null };
        } else {
          const row: CharacterVolumeCandidateEntry = { key, scope, base_version: baseVersion, value: sameSavedCommand ? { ...current!.value, completed: true } : next, updated_at: Math.max(Date.now(), (current?.updated_at ?? 0) + 1) };
          store.put(row); result = { written: true, current: row };
        }
      };
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error("CHARACTER_VOLUME_CANDIDATE_STORAGE_FAILED"));
    });
  } finally { db.close(); }
}
