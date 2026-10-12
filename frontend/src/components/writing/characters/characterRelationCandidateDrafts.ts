"use client";

import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { CandidateBasisV1 } from "@/lib/aiCandidate";
import type { BulkAppendCharacterRelationsRequestV1, CharacterRelationCreateRequestV1, CharacterRelationsAIConfirmationRequestV1, CharacterRelationsGenerationInputV1, CharacterRelationsResultV1 } from "@/types/character";
import type { CharacterRelationFactPreparationEntryV1, CharacterRelationFactPreparationV1 } from "./characterRelationFactPreparation";
import { characterRelationFactDraftScope, type CharacterRelationFactCommandEntryV1, type CharacterRelationFactDraftEntryV1, type CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";

/** 只保留已经存在的旧请求；没有 unknown 标记也须按未知原请求恢复。 */
export type CharacterRelationCandidateCommand = {
  key: string; unknown?: boolean; saved?: unknown;
} & (
  | { kind: "create"; body: CharacterRelationCreateRequestV1 }
  | { kind: "bulk"; body: CharacterRelationsAIConfirmationRequestV1 | BulkAppendCharacterRelationsRequestV1 }
);
export interface CharacterRelationCandidateLink { preparationKey: string; draftKey?: string }
/** 模型原文、作者编辑和每个成员的人工准备共用现有本地草稿表。 */
export interface CharacterRelationCandidateDraft {
  /** 新生成结果使用整批创建；旧稿保留原恢复入口。 */
  batch_creation?: true;
  key: string;
  revision: number;
  original_candidate: CharacterRelationsResultV1 | null;
  candidate: CharacterRelationsResultV1 | null;
  basis: CandidateBasisV1 | null;
  generation_input: CharacterRelationsGenerationInputV1 | null;
  members: Record<string, CharacterRelationCandidateLink>;
  command: CharacterRelationCandidateCommand | null;
}
export type CharacterRelationCandidateDraftEntry = WritingDraft<CharacterRelationCandidateDraft>;
export type CharacterRelationCandidateResolution =
  | { kind: "rejected"; previous: CharacterRelationCandidateDraftEntry | null; registered: CharacterRelationCandidateDraftEntry }
  | { kind: "saved"; command: Pick<CharacterRelationCandidateCommand, "kind" | "key" | "body"> };
export interface CharacterRelationCandidateWriteResult { written: boolean; current: CharacterRelationCandidateDraftEntry | null }

const CONFLICT = "CHARACTER_RELATION_CANDIDATE_CONFLICT", FAILED = "CHARACTER_RELATION_CANDIDATE_STORAGE_FAILED";
function sameCommand(left: CharacterRelationCandidateCommand | null | undefined, right: Pick<CharacterRelationCandidateCommand, "kind" | "key" | "body"> | null | undefined): boolean {
  return Boolean(left && right && left.kind === right.kind && left.key === right.key && JSON.stringify(left.body) === JSON.stringify(right.body));
}
function same(left: unknown, right: unknown): boolean { return JSON.stringify(left) === JSON.stringify(right); }

/** 功能：恢复本书所有原组，成功与未知旧请求排在前面。Args: 小说 ID。Returns: 完整候选和原命令。 */
export async function readCharacterRelationCandidateDrafts(novelId: string): Promise<CharacterRelationCandidateDraftEntry[]> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly"), request = tx.objectStore("business_drafts").index("scope").getAll(`${novelId}:character-relation-candidates`);
    tx.oncomplete = () => {
      const priority = (row: CharacterRelationCandidateDraftEntry) => row.value.command?.saved !== undefined ? 2 : row.value.command && row.value.command.unknown !== false ? 1 : 0;
      resolve((request.result as CharacterRelationCandidateDraftEntry[]).sort((a, b) => priority(b) - priority(a) || b.updated_at - a.updated_at));
    };
    tx.onerror = tx.onabort = () => reject(tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：同事务核对完整原行再保稿；旧命令、模型原文和已交接成员不能被陈旧页面覆盖。Args: 本书、新稿或明确删除、持有原行及原请求结果。Returns: 当前行与是否写入。 */
export async function writeCharacterRelationCandidateDraft(novelId: string, value: CharacterRelationCandidateDraft | null, expected: CharacterRelationCandidateDraftEntry | null, resolution?: CharacterRelationCandidateResolution): Promise<CharacterRelationCandidateWriteResult> {
  const next = value === null ? null : structuredClone(value), original = expected === null ? null : structuredClone(expected), proof = resolution && structuredClone(resolution);
  const scope = `${novelId}:character-relation-candidates`, key = `${scope}:${next?.key ?? original?.value.key}`;
  if ((!next && !original) || original && (original.scope !== scope || original.key !== key) || next && (!next.key || !Number.isSafeInteger(next.revision) || next.revision < 1 || next.generation_input && next.generation_input.novel_id !== novelId)) throw new Error(CONFLICT);
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), request = store.get(key);
    let result: CharacterRelationCandidateWriteResult;
    request.onsuccess = () => {
      const current = (request.result as CharacterRelationCandidateDraftEntry | undefined) ?? null, command = current?.value.command;
      result = { written: false, current };
      const saved = proof?.kind === "saved" && next?.command?.saved !== undefined && sameCommand(next.command, proof.command);
      const lateSaved = saved && sameCommand(command, next?.command);
      if (!same(current, original) && !lateSaved) return;
      if (current?.value.command?.saved !== undefined && (!next || !same(current.value.command, next.command))) return;
      if (command && (!next || !sameCommand(command, next.command))) return;
      if (next?.command?.saved !== undefined && command?.saved === undefined && !saved) return;
      if (next?.command?.unknown === false && command && command.unknown !== false && !saved) {
        const rejected = proof?.kind === "rejected" && same(current, proof.registered) && sameCommand(proof.registered.value.command, next.command)
          && proof.previous?.value.command?.unknown === false && sameCommand(proof.previous.value.command, next.command);
        if (!rejected) return;
      }
      if (lateSaved && current) {
        const row = { ...current, value: { ...current.value, revision: current.value.revision + 1, command: next!.command }, updated_at: Math.max(Date.now(), current.updated_at + 1) };
        store.put(row); result = { written: true, current: row }; return;
      }
      if (current && (!next ? Object.keys(current.value.members).length > 0 : next.revision <= current.value.revision
        || !same(current.value.original_candidate, next.original_candidate) || !same(current.value.basis, next.basis) || !same(current.value.generation_input, next.generation_input)
        || !same(current.value.members, next.members) || command && !same(current.value.candidate, next.candidate)
        || Object.keys(current.value.members).some((ref) => !same(current.value.candidate?.relations.find((row) => row.relation_ref === ref), next.candidate?.relations.find((row) => row.relation_ref === ref))))) return;
      if (!current && next && Object.keys(next.members).length) return;
      if (!next) { store.delete(key); result = { written: true, current: null }; return; }
      const row: CharacterRelationCandidateDraftEntry = { key, scope, base_version: 0, value: next, updated_at: Math.max(Date.now(), (current?.updated_at ?? 0) + 1) };
      if (next.command && next.command.unknown !== false) {
        const recovered = store.index("scope").getAll(scope);
        recovered.onsuccess = () => {
          // 同请求的任何恢复稿已交接后，都不能重新取得旧命令的发送权。
          if (Object.keys(current?.value.members ?? {}).length || (recovered.result as CharacterRelationCandidateDraftEntry[]).some((item) => sameCommand(item.value.command, next.command) && Object.keys(item.value.members).length)) return;
          store.put(row); result = { written: true, current: row };
        };
        return;
      }
      store.put(row); result = { written: true, current: row };
    };
    tx.oncomplete = () => resolve(result); tx.onerror = tx.onabort = () => reject(tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：作者逐条选择后，一笔事务保留候选并关联新人工创建准备。Args: 本书、持有完整候选行、原成员 ref。Returns: 更新后的原组与准备稿；历史 basis 不会成为人工依据。 */
export async function handoffCharacterRelationCandidate(novelId: string, expected: CharacterRelationCandidateDraftEntry, candidateRef: string): Promise<{ entry: CharacterRelationCandidateDraftEntry; preparation: CharacterRelationFactPreparationV1 }> {
  const original = structuredClone(expected), scope = `${novelId}:character-relation-candidates`, command = original.value.command;
  const candidate = original.value.candidate?.relations.find((row) => row.relation_ref === candidateRef)
    ?? (candidateRef === "manual-create" && command?.kind === "create" ? command.body : undefined);
  if (original.scope !== scope || original.key !== `${scope}:${original.value.key}` || !candidate || original.value.members[candidateRef]
    || command && (command.unknown !== false || command.saved !== undefined)) throw new Error(CONFLICT);
  const { source_character_id, target_character_id, relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity, current_state } = candidate;
  const preparation: CharacterRelationFactPreparationV1 = {
    schema_id: "character_relation.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1, novel_id: novelId,
    origin: { scope, draftKey: original.value.key, candidateRef }, kind: "create", position: null, note: "",
    candidate: { source_character_id, target_character_id, relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity, ...("sort_order" in candidate ? { sort_order: candidate.sort_order } : {}) }, after: { current_state },
  };
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), request = store.index("scope").getAll(scope);
    let entry: CharacterRelationCandidateDraftEntry, failure: unknown;
    request.onsuccess = () => {
      const rows = request.result as CharacterRelationCandidateDraftEntry[], current = rows.find((row) => row.key === original.key);
      // 同一旧请求可能来自恢复后的另一个组；任何未知或成功副本都阻止换键采用。
      if (!same(current, original) || command && rows.some((row) => sameCommand(row.value.command, command) && (row.value.command!.unknown !== false || row.value.command!.saved !== undefined))) { failure = new Error(CONFLICT); tx.abort(); return; }
      entry = { ...original, value: { ...original.value, revision: original.value.revision + 1, members: { ...original.value.members, [candidateRef]: { preparationKey: preparation.key } } }, updated_at: Math.max(Date.now(), original.updated_at + 1) };
      const preparationScope = `${novelId}:character-relation-fact-preparations`;
      store.add({ key: `${preparationScope}:${preparation.key}`, scope: preparationScope, base_version: 0, value: preparation, updated_at: Date.now() } satisfies CharacterRelationFactPreparationEntryV1);
      store.put(entry);
    };
    tx.oncomplete = () => resolve({ entry, preparation }); tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：人工创建或候选明确另建准备时，保留失败请求并撤销旧稿发送权。Args: 小说 ID、已读的可靠失败稿。Returns: 同事务新建的准备稿。 */
export async function reprepareCharacterRelationCandidate(novelId: string, previous: CharacterRelationFactDraftV1): Promise<CharacterRelationFactPreparationV1> {
  const original = structuredClone(previous), origin = original.origin, command = original.command;
  if (origin && (!origin.candidateRef || origin.scope !== `${novelId}:character-relation-candidates`) || !command || command.unknown !== false || command.saved
    || command.body.operation !== "create" || command.body.basis.target.novel_id !== novelId) throw new Error(CONFLICT);
  const body = command.body, scope = characterRelationFactDraftScope(novelId);
  if (body.basis.source.kind !== "author") throw new Error(CONFLICT);
  const preparation: CharacterRelationFactPreparationV1 = {
    schema_id: "character_relation.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1, novel_id: novelId, kind: "create", ...(origin ? { origin } : {}),
    candidate: structuredClone(body.basis.target.candidate), position: structuredClone(body.basis.position), note: body.basis.source.note, after: structuredClone(body.after),
  };
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let failure: unknown;
    const abort = () => { failure = new Error(CONFLICT); tx.abort(); };
    const draftRequest = store.get(`${scope}:${original.key}`);
    draftRequest.onsuccess = () => {
      const row = draftRequest.result as CharacterRelationFactDraftEntryV1 | undefined;
      if (!row || row.scope !== scope || !same(row.value, original)) { abort(); return; }
      const operationRequest = store.get(`${scope}:operation:${command.key}`);
      operationRequest.onsuccess = () => {
        const operation = operationRequest.result as CharacterRelationFactCommandEntryV1 | undefined;
        if (!operation || operation.scope !== `${scope}:operations` || operation.draft_key !== original.key || operation.value.saved
          || operation.value.schema_id !== command.schema_id || operation.value.schema_version !== command.schema_version || operation.value.positionLabel !== command.positionLabel
          || operation.value.key !== command.key || !same(operation.value.body, body)) { abort(); return; }
        const savePreparation = () => {
          const preparationScope = `${novelId}:character-relation-fact-preparations`;
          store.add({ key: `${preparationScope}:${preparation.key}`, scope: preparationScope, base_version: 0, value: preparation, updated_at: Date.now() } satisfies CharacterRelationFactPreparationEntryV1);
          // 旧页失去发送权，但原键、请求和独立成功回执仍可恢复。
          store.put({ ...row, value: { ...row.value, revision: row.value.revision + 1 }, updated_at: Date.now() });
        };
        if (!origin) { savePreparation(); return; }
        const candidateRef = origin.candidateRef!;
        const sourceRequest = store.index("scope").getAll(origin.scope);
        sourceRequest.onsuccess = () => {
          const rows = sourceRequest.result as CharacterRelationCandidateDraftEntry[], sourceRow = rows.find((item) => item.key === `${origin.scope}:${origin.draftKey}`), source = sourceRow?.value;
          if (!source || sourceRow!.scope !== origin.scope || source.key !== origin.draftKey || source.members[candidateRef]?.draftKey !== original.key
            || source.command && rows.some((item) => sameCommand(item.value.command, source.command) && (item.value.command!.unknown !== false || item.value.command!.saved !== undefined))) { abort(); return; }
          savePreparation();
          store.put({ ...sourceRow!, value: { ...source, revision: source.revision + 1, members: { ...source.members, [candidateRef]: { preparationKey: preparation.key } } }, updated_at: Date.now() });
        };
      };
    };
    tx.oncomplete = () => resolve(preparation); tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}
