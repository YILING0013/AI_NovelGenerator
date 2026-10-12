"use client";

import { useMemo } from "react";
import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { ChapterRecordEvidenceV1 } from "@/types/chapterRecords";
import type { CharacterRelationFactCreateDataV1, CharacterRelationFactOperation, CharacterRelationFactPositionV1, CharacterRelationFactPreviewExistingTargetV1, CharacterRelationFactRecordV1 } from "@/types/characterRelationFacts";
import { characterRelationFactDraftScope, type CharacterRelationFactCommandEntryV1, type CharacterRelationFactDraftEntryV1, type CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import type { ChapterRecordDraft } from "../chapter-records/chapterRecordDrafts";
import type { CharacterRelationCandidateDraftEntry } from "./characterRelationCandidateDrafts";

/** 作者在预览前的输入；空文字可以保稿，提交是否合法仍由预览检查。 */
export interface CharacterRelationFactPreparationSetupV1 {
  operation: Exclude<CharacterRelationFactOperation, "create">;
  position: CharacterRelationFactPositionV1 | null;
  note: string;
  evidence: ChapterRecordEvidenceV1 | null;
  record: CharacterRelationFactRecordV1 | null;
  resolves: { current_state?: string[] };
  after?: { current_state: string };
  reason?: string;
}
/** 准备稿只保存作者输入和选择的历史，不接受依据、冻结请求或回执。 */
export type CharacterRelationFactPreparationV1 = {
  schema_id: "character_relation.fact.preparation"; schema_version: 1; key: string; revision: number; novel_id: string;
  origin?: CharacterRelationFactDraftV1["origin"];
} & (
  | { kind: "create"; candidate: CharacterRelationFactCreateDataV1; position: CharacterRelationFactPositionV1 | null; note: string; after?: { current_state: string } }
  | { kind: "existing"; relation_id: string; target: CharacterRelationFactPreviewExistingTargetV1; setup: CharacterRelationFactPreparationSetupV1 }
);
export type CharacterRelationFactPreparationEntryV1 = WritingDraft<CharacterRelationFactPreparationV1>;

const INVALID = "CHARACTER_RELATION_FACT_PREPARATION_INVALID", CONFLICT = "CHARACTER_RELATION_FACT_PREPARATION_CONFLICT", FAILED = "CHARACTER_RELATION_FACT_PREPARATION_FAILED";
const operations = ["establish", "correct_initial", "change", "replace", "void"];
const symmetric = ["friend", "romantic", "ally", "rival", "enemy"];
function keys(value: unknown, required: string[], optional: string[] = []): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) && required.every((key) => Object.hasOwn(value, key))
    && Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
}
function text(value: unknown): value is string { return typeof value === "string"; }
function id(value: unknown): value is string { return text(value) && value.length > 0; }
function revision(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 1; }
function values(value: unknown): boolean { return keys(value, ["current_state"]) && text(value.current_state); }
function references(value: unknown): boolean { return keys(value, [], ["current_state"]) && (!Object.hasOwn(value, "current_state") || Array.isArray(value.current_state) && value.current_state.every(id)); }
function position(value: unknown, novelId: string): boolean {
  return keys(value, ["version", "intent", "target_type", "target_id"]) && value.version === 1 && id(value.target_id)
    && (value.intent === "book_start" ? value.target_type === "novel" && value.target_id === novelId : value.intent === "volume_start" ? value.target_type === "volume" : ["chapter_before", "chapter_after"].includes(String(value.intent)) && value.target_type === "chapter");
}
function evidence(value: unknown): boolean {
  return keys(value, ["chapter_id", "version", "revision_id", "content_hash", "start", "quote"]) && id(value.chapter_id) && revision(value.version)
    && id(value.revision_id) && text(value.content_hash) && /^[a-f0-9]{64}$/.test(value.content_hash) && Number.isSafeInteger(value.start) && Number(value.start) >= 0 && id(value.quote);
}
function record(value: unknown, novelId: string, target: CharacterRelationFactPreviewExistingTargetV1): boolean {
  if (!keys(value, ["schema_id", "schema_version", "history_id", "novel_id", "entity_type", "entity_id", "relation_id", "source_character_id", "source_character_entity_id", "source_character_name", "target_character_id", "target_character_entity_id", "target_character_name", "operation", "kind", "position", "source", "before_version", "after_version", "before", "after", "previous", "replaces", "resolves", "validity", "protected_sources", "confirmed_at"])) return false;
  const source = value.source, before = value.before, validity = keys(value.validity, ["current_state"]) ? value.validity.current_state : null;
  return value.schema_id === "character_relation.fact" && value.schema_version === 1 && value.entity_type === "character_relation" && value.novel_id === novelId
    && value.entity_id === target.entity_id && value.relation_id === target.relation_id && ["history_id", "source_character_id", "source_character_entity_id", "source_character_name", "target_character_id", "target_character_entity_id", "target_character_name", "confirmed_at"].every((field) => id(value[field]))
    && ["create", ...operations.slice(0, -1)].includes(String(value.operation)) && ["start", "change"].includes(String(value.kind)) && position(value.position, novelId)
    && (keys(source, ["kind", "note"]) && source.kind === "author" && id(source.note) || keys(source, ["kind", "evidence"]) && source.kind === "chapter" && evidence(source.evidence))
    && (value.before_version === null || revision(value.before_version)) && revision(value.after_version) && values(value.after)
    && keys(before, ["values", "unknown"]) && keys(before.values, [], ["current_state"]) && (!Object.hasOwn(before.values, "current_state") || text(before.values.current_state))
    && keys(before.unknown, [], ["current_state"]) && (!Object.hasOwn(before.unknown, "current_state") || ["nonexistent", "unclaimed", "before_start", "voided", "needs_review", "unresolved_reference"].includes(String(before.unknown.current_state)))
    && keys(value.previous, ["current_state"]) && (value.previous.current_state === null || id(value.previous.current_state))
    && keys(value.replaces, [], ["current_state"]) && (!Object.hasOwn(value.replaces, "current_state") || id(value.replaces.current_state)) && references(value.resolves)
    && (keys(validity, ["state"]) && validity.state === "active" || keys(validity, ["state", "by_history_id"]) && validity.state === "replaced" && id(validity.by_history_id)
      || keys(validity, ["state", "by_receipt_key_hash"]) && validity.state === "voided" && text(validity.by_receipt_key_hash) && /^[a-f0-9]{64}$/.test(validity.by_receipt_key_hash))
    && Array.isArray(value.protected_sources) && value.protected_sources.every((row) => keys(row, ["resource_type", "id", "parent_id"]) && id(row.id)
      && (row.resource_type === "novel" ? row.id === novelId && row.parent_id === null : ["volume", "arc", "scene", "chapter"].includes(String(row.resource_type)) && id(row.parent_id)));
}
function checkPreparation(value: unknown): asserts value is CharacterRelationFactPreparationV1 {
  const common = ["schema_id", "schema_version", "key", "revision", "novel_id", "kind"];
  if (!keys(value, common, ["candidate", "position", "note", "after", "relation_id", "target", "setup", "origin"]) || value.schema_id !== "character_relation.fact.preparation" || value.schema_version !== 1 || !id(value.key) || !revision(value.revision) || !id(value.novel_id)) throw new Error(INVALID);
  if (value.origin !== undefined && (!keys(value.origin, ["scope", "draftKey"], ["candidateRef"]) || !id(value.origin.scope) || !id(value.origin.draftKey)
    || (value.kind === "create" ? !id(value.origin.candidateRef) || value.origin.scope !== `${value.novel_id}:character-relation-candidates`
      : Object.hasOwn(value.origin, "candidateRef") || !value.origin.scope.startsWith(`${value.novel_id}:chapter:`) || !value.origin.scope.endsWith(":chapter-records")))) throw new Error(INVALID);
  if (value.kind === "create") {
    const candidate = value.candidate;
    if (!keys(value, [...common, "candidate", "position", "note"], ["after", "origin"]) || !keys(candidate, ["source_character_id", "target_character_id", "relation_type", "core_conflict", "hidden_tension", "possible_change", "story_value", "intensity"], ["sort_order"])
      || !["source_character_id", "target_character_id", "core_conflict", "hidden_tension", "possible_change", "story_value"].every((field) => text(candidate[field]))
      || ![...symmetric, "parent_of", "mentor_of", "superior_of", "protector_of", "debtor_to"].includes(String(candidate.relation_type)) || !Number.isInteger(candidate.intensity) || Number(candidate.intensity) < 1 || Number(candidate.intensity) > 5
      || (Object.hasOwn(candidate, "sort_order") && (!Number.isSafeInteger(candidate.sort_order) || Number(candidate.sort_order) < 0))
      || !text(value.note) || (value.position !== null && !position(value.position, value.novel_id)) || (Object.hasOwn(value, "after") && !values(value.after))) throw new Error(INVALID);
    return;
  }
  if (value.kind !== "existing" || !keys(value, [...common, "relation_id", "target", "setup"], ["origin"]) || !id(value.relation_id)
    || !keys(value.target, ["entity_id", "relation_id", "expected_version"]) || !id(value.target.entity_id) || value.target.relation_id !== value.relation_id || !revision(value.target.expected_version)
    || !keys(value.setup, ["operation", "position", "note", "evidence", "record", "resolves"], ["after", "reason"])) throw new Error(INVALID);
  const setup = value.setup;
  if (!operations.includes(String(setup.operation)) || !text(setup.note) || (setup.position !== null && !position(setup.position, value.novel_id)) || (setup.evidence !== null && !evidence(setup.evidence))
    || (setup.record !== null && !record(setup.record, value.novel_id, value.target as unknown as CharacterRelationFactPreviewExistingTargetV1)) || !references(setup.resolves)
    || (Object.hasOwn(setup, "after") && !values(setup.after)) || (Object.hasOwn(setup, "reason") && !text(setup.reason))) throw new Error(INVALID);
}

/** 功能：在同一事务核对交接原稿，阻止旧页重建已转为确认的准备稿。Args: store 原事务、准备稿、核对后回调及失败回调。Returns: 无。 */
function readPreparationOrigin(store: IDBObjectStore, preparation: CharacterRelationFactPreparationV1, done: (row?: WritingDraft<ChapterRecordDraft> | CharacterRelationCandidateDraftEntry) => void, failed: () => void): void {
  if (!preparation.origin) { done(); return; }
  const origin = preparation.origin, request = store.get(`${origin.scope}:${origin.draftKey}`);
  request.onsuccess = () => {
    if (origin.candidateRef) {
      const row = request.result as CharacterRelationCandidateDraftEntry | undefined, source = row?.value, link = source?.members[origin.candidateRef];
      if (!source || row!.scope !== origin.scope || source.key !== origin.draftKey || preparation.kind !== "create"
        || link?.preparationKey !== preparation.key || link.draftKey) { failed(); return; }
      done(row); return;
    }
    const row = request.result as WritingDraft<ChapterRecordDraft> | undefined, source = row?.value;
    if (!source || row!.scope !== origin.scope || source.key !== origin.draftKey || source.relationFact?.preparationKey !== preparation.key || source.relationFact.draftKey
      || preparation.kind !== "existing" || source.relationTarget?.relation_id !== preparation.relation_id || source.relationTarget.version !== preparation.target.expected_version
      || source.relationCheck?.result?.check_target.entity_id !== preparation.target.entity_id) { failed(); return; }
    done(row);
  };
}
function checkEntry(value: unknown, novelId: string): asserts value is CharacterRelationFactPreparationEntryV1 {
  if (!keys(value, ["key", "scope", "base_version", "value", "updated_at"])) throw new Error(INVALID);
  checkPreparation(value.value);
  if (value.scope !== `${novelId}:character-relation-fact-preparations` || value.value.novel_id !== novelId || value.key !== `${value.scope}:${value.value.key}` || value.base_version !== 0 || !Number.isFinite(value.updated_at)) throw new Error(INVALID);
}

/** 功能：读取本书作者准备稿，不补造旧稿。Args: 小说 ID。Returns: 按保存时间排列的原稿。 */
export async function readCharacterRelationFactPreparations(novelId: string): Promise<CharacterRelationFactPreparationV1[]> {
  if (!id(novelId)) throw new Error(INVALID);
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly"), request = tx.objectStore("business_drafts").index("scope").getAll(`${novelId}:character-relation-fact-preparations`);
    let rows: CharacterRelationFactPreparationEntryV1[] = [], failure: unknown;
    request.onsuccess = () => { try { rows = request.result; for (const row of rows) checkEntry(row, novelId); } catch (error) { failure = error; tx.abort(); } };
    tx.oncomplete = () => resolve(rows.sort((a, b) => a.updated_at - b.updated_at).map((row) => row.value));
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：同事务比较持有版本后保稿；同键不换原目标或动作。Args: 准备稿与原版本，新稿为 null。Returns: 事务完成标记。 */
export async function writeCharacterRelationFactPreparation(preparation: CharacterRelationFactPreparationV1, expectedRevision: number | null): Promise<{ written: true }> {
  checkPreparation(preparation);
  if (expectedRevision !== null && !revision(expectedRevision)) throw new Error(INVALID);
  const snapshot = structuredClone(preparation), scope = `${preparation.novel_id}:character-relation-fact-preparations`, key = `${scope}:${preparation.key}`;
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), request = store.get(key);
    let failure: unknown;
    request.onsuccess = () => { try {
      const previous: unknown = request.result;
      if (previous !== undefined) checkEntry(previous, snapshot.novel_id);
      const current = previous as CharacterRelationFactPreparationEntryV1 | undefined;
      const selectedReplacement = current?.value.kind === "existing" && snapshot.kind === "existing" && Boolean(snapshot.origin)
        && current.value.setup.operation === "change" && snapshot.setup.operation === "replace" && snapshot.setup.record?.validity.current_state.state === "active" && JSON.stringify(current.value.setup.position) === JSON.stringify(snapshot.setup.position)
        && JSON.stringify(snapshot.setup.position) === JSON.stringify(snapshot.setup.record.position);
      if ((current?.value.revision ?? null) !== expectedRevision || current && (current.value.kind !== snapshot.kind || JSON.stringify(current.value.origin) !== JSON.stringify(snapshot.origin)
        || current.value.kind === "existing" && snapshot.kind === "existing" && (JSON.stringify(current.value.target) !== JSON.stringify(snapshot.target) || current.value.setup.operation !== snapshot.setup.operation && !selectedReplacement)
        || snapshot.revision <= current.value.revision && JSON.stringify(snapshot) !== JSON.stringify(current.value))) throw new Error(CONFLICT);
      readPreparationOrigin(store, snapshot, () => store.put({ key, scope, base_version: 0, value: snapshot, updated_at: Date.now() } satisfies CharacterRelationFactPreparationEntryV1), () => { failure = new Error(CONFLICT); tx.abort(); });
    } catch (error) { failure = error; tx.abort(); } };
    tx.oncomplete = () => resolve({ written: true }); tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：只删除作者仍持有的版本。Args: 小说、原稿键和原版本。Returns: 删除事务完成。 */
export async function removeCharacterRelationFactPreparation(novelId: string, key: string, expectedRevision: number): Promise<void> {
  if (!id(novelId) || !id(key) || !revision(expectedRevision)) throw new Error(INVALID);
  const db = await openTaskFlowDatabase();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), storageKey = `${novelId}:character-relation-fact-preparations:${key}`, request = store.get(storageKey);
    let failure: unknown;
    request.onsuccess = () => { try {
      if (request.result === undefined) throw new Error(CONFLICT);
      checkEntry(request.result, novelId);
      if (request.result.value.revision !== expectedRevision || request.result.value.origin) throw new Error(CONFLICT);
      store.delete(storageKey);
    } catch (error) { failure = error; tx.abort(); } };
    tx.oncomplete = () => resolve(); tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：一笔事务保存新预览稿并移除原准备稿，任一步失败都不改变两边。Args: 原准备稿、新预览稿和原版本。Returns: 事务完成标记。 */
export async function promoteCharacterRelationFactPreparation(preparation: CharacterRelationFactPreparationV1, draft: CharacterRelationFactDraftV1, expectedRevision: number): Promise<{ written: true }> {
  checkPreparation(preparation);
  const basis = draft.preview?.basis, target = basis?.target;
  if (!revision(expectedRevision) || preparation.revision !== expectedRevision || draft.schema_id !== "character_relation.fact.draft" || draft.schema_version !== 1 || !id(draft.key) || !revision(draft.revision)
    || draft.command !== undefined || draft.authorConfirmed !== false || target?.novel_id !== preparation.novel_id || JSON.stringify(draft.origin) !== JSON.stringify(preparation.origin)) throw new Error(INVALID);
  if (preparation.kind === "create") {
    const candidate = { ...preparation.candidate };
    if (symmetric.includes(candidate.relation_type)) [candidate.source_character_id, candidate.target_character_id] = [candidate.source_character_id, candidate.target_character_id].sort();
    if (target.kind !== "new" || basis.operation !== "create" || Object.keys(candidate).length !== Object.keys(target.candidate).length
      || Object.entries(candidate).some(([key, value]) => target.candidate[key as keyof CharacterRelationFactCreateDataV1] !== value)) throw new Error(INVALID);
  } else if (target.kind !== "existing" || target.entity_id !== preparation.target.entity_id || target.relation_id !== preparation.relation_id
    || target.version !== preparation.target.expected_version || basis.operation !== preparation.setup.operation) throw new Error(INVALID);
  const snapshot = structuredClone(draft), original = structuredClone(preparation), scope = characterRelationFactDraftScope(original.novel_id);
  const draftKey = `${scope}:${snapshot.key}`, preparationKey = `${original.novel_id}:character-relation-fact-preparations:${original.key}`;
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts"), current = store.get(preparationKey);
    let failure: unknown;
    current.onsuccess = () => { try {
      if (current.result === undefined) throw new Error(CONFLICT);
      checkEntry(current.result, original.novel_id);
      if (current.result.value.revision !== expectedRevision || JSON.stringify(current.result.value) !== JSON.stringify(original)) throw new Error(CONFLICT);
      const destination = store.get(draftKey);
      destination.onsuccess = () => { try {
        if (destination.result !== undefined) throw new Error(CONFLICT);
        const frozenTarget = snapshot.preview.basis.target;
        readPreparationOrigin(store, original, (source) => {
          store.add({ key: draftKey, scope, base_version: frozenTarget.kind === "existing" ? frozenTarget.version : 0, value: snapshot, updated_at: Date.now() } satisfies CharacterRelationFactDraftEntryV1);
          if (source) {
            const link = { preparationKey: original.key, draftKey: snapshot.key };
            store.put({ ...source, value: { ...source.value, revision: source.value.revision + 1,
              ...("members" in source.value ? { members: { ...source.value.members, [original.origin!.candidateRef!]: link } } : { relationFact: link }) }, updated_at: Date.now() });
          }
          store.delete(preparationKey);
        }, () => { failure = new Error(CONFLICT); tx.abort(); });
      } catch (error) { failure = error; tx.abort(); } };
    } catch (error) { failure = error; tx.abort(); } };
    tx.oncomplete = () => resolve({ written: true }); tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：作者明确选择后，把已可靠拒绝的关联确认另建为准备稿，保留原请求。Args: 小说及已读失败确认稿。Returns: 同事务建立的新准备；原实体版本和来源章不刷新。 */
export async function reprepareChapterRelationFact(novelId: string, previous: CharacterRelationFactDraftV1): Promise<CharacterRelationFactPreparationV1> {
  const original = structuredClone(previous), command = original.command, origin = original.origin;
  if (!origin || origin.candidateRef || !command || command.unknown !== false || command.saved || command.body.operation === "create" || command.body.operation === "void"
    || command.body.basis.target.kind !== "existing" || command.body.basis.target.novel_id !== novelId) throw new Error(CONFLICT);
  const body = command.body, target = body.basis.target;
  const scope = characterRelationFactDraftScope(novelId), db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let failure: unknown, preparation: CharacterRelationFactPreparationV1;
    const abort = () => { failure = new Error(CONFLICT); tx.abort(); };
    const draftRequest = store.get(`${scope}:${original.key}`);
    draftRequest.onsuccess = () => {
      const row = draftRequest.result as CharacterRelationFactDraftEntryV1 | undefined, current = row?.value;
      if (!current || row!.scope !== scope || current.revision !== original.revision || JSON.stringify(current) !== JSON.stringify(original)
        || current.command?.unknown !== false || current.command.saved) { abort(); return; }
      const operationRequest = store.get(`${scope}:operation:${command.key}`);
      operationRequest.onsuccess = () => {
        const operation = operationRequest.result as CharacterRelationFactCommandEntryV1 | undefined;
        if (!operation || operation.scope !== `${scope}:operations` || operation.draft_key !== original.key || operation.value.saved
          || operation.value.schema_id !== command.schema_id || operation.value.schema_version !== command.schema_version || operation.value.positionLabel !== command.positionLabel
          || operation.value.key !== command.key || JSON.stringify(operation.value.body) !== JSON.stringify(command.body)) { abort(); return; }
        const sourceRequest = store.get(`${origin.scope}:${origin.draftKey}`);
        sourceRequest.onsuccess = () => {
          const sourceRow = sourceRequest.result as WritingDraft<ChapterRecordDraft> | undefined, source = sourceRow?.value;
          const checked = source?.relationCheck?.result?.check_target, chapterSource = source?.relationCheck?.source;
          if (!source || sourceRow!.scope !== origin.scope || source.key !== origin.draftKey || source.mode !== "character-relation-state" || source.relationFact?.draftKey !== original.key
            || origin.scope !== `${novelId}:chapter:${source.chapterId}:chapter-records` || !checked || !chapterSource || chapterSource.chapter_id !== source.chapterId
            || checked.entity_id !== target.entity_id || checked.relation_id !== target.relation_id || checked.expected_version !== target.version
            || checked.source_character_id !== target.source_character.character_id || checked.target_character_id !== target.target_character.character_id
            || source.relationTarget?.relation_id !== checked.relation_id || source.relationTarget.version !== checked.expected_version
            || body.basis.position.intent !== "chapter_after" || body.basis.position.target_id !== chapterSource.chapter_id) { abort(); return; }
          // 失败请求里的作者值和原文继续保留，人工依据须重新预览取得。
          preparation = { schema_id: "character_relation.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1, novel_id: novelId,
            kind: "existing", relation_id: checked.relation_id, target: { entity_id: checked.entity_id, relation_id: checked.relation_id, expected_version: checked.expected_version }, origin,
            setup: { operation: "change", position: { version: 1, intent: "chapter_after", target_type: "chapter", target_id: chapterSource.chapter_id }, note: "",
              evidence: body.basis.source.kind === "chapter" ? body.basis.source.evidence : source.relationCheck!.result!.candidate.suggestion ? { ...chapterSource, start: source.relationCheck!.result!.candidate.suggestion.start, quote: source.relationCheck!.result!.candidate.suggestion.quote } : null,
              record: null, resolves: {}, after: { current_state: body.after.current_state } } };
          try { checkPreparation(preparation); } catch (error) { failure = error; tx.abort(); return; }
          const preparationScope = `${novelId}:character-relation-fact-preparations`;
          store.add({ key: `${preparationScope}:${preparation.key}`, scope: preparationScope, base_version: 0, value: preparation, updated_at: Date.now() } satisfies CharacterRelationFactPreparationEntryV1);
          // 旧页失去编辑权，但完整失败命令仍可查看和导出。
          store.put({ ...row!, value: { ...current, revision: current.revision + 1 }, updated_at: Date.now() });
          store.put({ ...sourceRow!, value: { ...source, revision: source.revision + 1, relationFact: { preparationKey: preparation.key } }, updated_at: Date.now() });
        };
      };
    };
    tx.oncomplete = () => resolve(preparation);
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error(FAILED));
  }); } finally { db.close(); }
}

/** 功能：串行保稿，提交后才更新持有版本；清理后拒绝迟到保稿。Args: 小说 ID。Returns: 队列、持有版本及保稿、删除、转换接口。 */
export function useCharacterRelationFactPreparationPersistence(novelId: string) {
  return useMemo(() => {
    const queue = { current: Promise.resolve() as Promise<unknown> }, persisted = { current: new Map<string, number>() }, removed = new Set<string>();
    const persist = (preparation: CharacterRelationFactPreparationV1) => {
      const snapshot = structuredClone(preparation);
      const pending = queue.current.catch(() => {}).then(async () => {
        if (snapshot.novel_id !== novelId || removed.has(snapshot.key)) throw new Error(CONFLICT);
        const result = await writeCharacterRelationFactPreparation(snapshot, persisted.current.get(snapshot.key) ?? null);
        persisted.current.set(snapshot.key, snapshot.revision); return result;
      });
      queue.current = pending; return pending;
    };
    const remove = (preparation: CharacterRelationFactPreparationV1) => {
      const snapshot = structuredClone(preparation);
      const pending = queue.current.then(async () => {
        if (snapshot.novel_id !== novelId) throw new Error(CONFLICT);
        await removeCharacterRelationFactPreparation(novelId, snapshot.key, persisted.current.get(snapshot.key) ?? snapshot.revision);
        persisted.current.delete(snapshot.key); removed.add(snapshot.key);
      });
      queue.current = pending; return pending;
    };
    const promote = (preparation: CharacterRelationFactPreparationV1, draft: CharacterRelationFactDraftV1) => {
      const original = structuredClone(preparation), snapshot = structuredClone(draft);
      const pending = queue.current.then(async () => {
        if (original.novel_id !== novelId || removed.has(original.key)) throw new Error(CONFLICT);
        const result = await promoteCharacterRelationFactPreparation(original, snapshot, persisted.current.get(original.key) ?? original.revision);
        persisted.current.delete(original.key); removed.add(original.key); return result;
      });
      queue.current = pending; return pending;
    };
    return { queue, persisted, persist, remove, promote };
  }, [novelId]);
}
