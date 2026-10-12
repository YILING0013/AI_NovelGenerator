"use client";

import { useMemo } from "react";
import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { CharacterProfileFields } from "@/types/character";
import type { ChapterRecordEvidenceV1 } from "@/types/chapterRecords";
import type { CharacterFactField, CharacterFactOperation, CharacterFactPositionV1, CharacterFactRecordV1, CharacterFactValuesV1 } from "@/types/characterFacts";
import { CHARACTER_FACT_FIELDS, CHARACTER_PROFILE_FACT_FIELDS } from "./characterFactFields";
import { characterFactDraftScope, type CharacterFactDraftEntryV1, type CharacterFactDraftV1 } from "./characterFactDrafts";

/** 作者尚未取得预览时的选择；after 仅用于明确另建预览，不能改写旧命令。 */
export interface CharacterFactPreparationSetupV1 {
  operation: Exclude<CharacterFactOperation, "create">;
  fields: CharacterFactField[];
  position: CharacterFactPositionV1 | null;
  note: string;
  evidence: ChapterRecordEvidenceV1 | null;
  record: CharacterFactRecordV1 | null;
  resolves: Partial<Record<CharacterFactField, string[]>>;
  after?: CharacterFactValuesV1;
  reason?: string;
}

/** 预览前只存作者输入，没有 basis、命令或成功回执。 */
export type CharacterFactPreparationV1 = {
  schema_id: "character.fact.preparation";
  schema_version: 1;
  key: string;
  revision: number;
  novel_id: string;
} & (
  | { kind: "existing"; character_id: string; setup: CharacterFactPreparationSetupV1 }
  | { kind: "create"; profile: CharacterProfileFields; fields: CharacterFactField[]; is_core_character: boolean; position: CharacterFactPositionV1 | null; note: string; candidate_ref?: string }
);
export type CharacterFactPreparationEntryV1 = WritingDraft<CharacterFactPreparationV1>;

const INVALID = "CHARACTER_FACT_PREPARATION_INVALID";
const CONFLICT = "CHARACTER_FACT_PREPARATION_CONFLICT";
const FAILED = "CHARACTER_FACT_PREPARATION_FAILED";
const textFields = ["name", "gender", "age_group", "race", "identity", "appearance", "personality", "core_desire", "core_fear", "conflict_with_mainline", "relationship_with_protagonist", "initial_state", "growth_direction", "story_function", "arc_seed"];
const listFields = ["aliases", "strengths", "weaknesses", "abilities", "tags"];
const arrayFacts = ["strengths", "weaknesses", "abilities"];
const operations = ["establish", "correct_initial", "change", "replace", "void"];

function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function keys(value: unknown, required: string[], optional: string[] = []): value is Record<string, unknown> {
  return object(value) && required.every((key) => Object.hasOwn(value, key)) && Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
}
function id(value: unknown): value is string { return typeof value === "string" && value.length > 0; }
function oneOf(value: unknown, choices: string[]): boolean { return typeof value === "string" && choices.includes(value); }
function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every((item) => typeof item === "string"); }
function revision(value: unknown): value is number { return Number.isSafeInteger(value) && Number(value) >= 1; }
function fieldMap(value: unknown, valid: (item: unknown, field: string) => boolean): boolean {
  return object(value) && Object.entries(value).every(([field, item]) => CHARACTER_FACT_FIELDS.includes(field as CharacterFactField) && valid(item, field));
}
function values(value: unknown): boolean { return fieldMap(value, (item, field) => arrayFacts.includes(field) ? strings(item) : typeof item === "string"); }
function position(value: unknown, novelId: string): boolean {
  return keys(value, ["version", "intent", "target_type", "target_id"]) && value.version === 1 && id(value.target_id)
    && (value.intent === "book_start" ? value.target_type === "novel" && value.target_id === novelId : value.intent === "volume_start" ? value.target_type === "volume" : oneOf(value.intent, ["chapter_before", "chapter_after"]) && value.target_type === "chapter");
}
function evidence(value: unknown): boolean {
  return keys(value, ["chapter_id", "version", "revision_id", "content_hash", "start", "quote"])
    && id(value.chapter_id) && revision(value.version) && id(value.revision_id) && typeof value.content_hash === "string" && /^[a-f0-9]{64}$/.test(value.content_hash)
    && Number.isSafeInteger(value.start) && Number(value.start) >= 0 && id(value.quote);
}
function record(value: unknown, novelId: string, characterId: string): boolean {
  if (!keys(value, ["schema_id", "schema_version", "history_id", "novel_id", "entity_type", "entity_id", "character_id", "character_name", "operation", "kind", "position", "source", "before_version", "after_version", "before", "after", "previous", "replaces", "resolves", "validity", "protected_sources", "confirmed_at"])) return false;
  const source = value.source;
  const validSource = keys(source, ["kind", "note"]) && source.kind === "author" && id(source.note)
    || keys(source, ["kind", "evidence"]) && source.kind === "chapter" && evidence(source.evidence);
  const validBefore = keys(value.before, ["values", "unknown"]) && values(value.before.values)
    && fieldMap(value.before.unknown, (reason) => oneOf(reason, ["nonexistent", "unclaimed", "before_start", "voided", "needs_review", "unresolved_reference"]));
  const validValidity = fieldMap(value.validity, (state) => keys(state, ["state"]) && state.state === "active"
    || keys(state, ["state", "by_history_id"]) && state.state === "replaced" && id(state.by_history_id)
    || keys(state, ["state", "by_receipt_key_hash"]) && state.state === "voided" && typeof state.by_receipt_key_hash === "string" && /^[a-f0-9]{64}$/.test(state.by_receipt_key_hash));
  return value.schema_id === "character.fact" && value.schema_version === 1 && id(value.history_id) && value.novel_id === novelId
    && value.entity_type === "character" && id(value.entity_id) && value.character_id === characterId && id(value.character_name)
    && oneOf(value.operation, ["create", ...operations.filter((item) => item !== "void")]) && oneOf(value.kind, ["start", "change"])
    && position(value.position, novelId) && validSource && (value.before_version === null || revision(value.before_version)) && revision(value.after_version)
    && validBefore && values(value.after) && fieldMap(value.previous, (item) => item === null || id(item)) && fieldMap(value.replaces, id)
    && fieldMap(value.resolves, (item) => strings(item) && item.every(id)) && validValidity && id(value.confirmed_at)
    && Array.isArray(value.protected_sources) && value.protected_sources.every((item) => keys(item, ["resource_type", "id", "parent_id"]) && id(item.id)
      && (item.resource_type === "novel" ? item.id === novelId && item.parent_id === null : oneOf(item.resource_type, ["volume", "arc", "scene", "chapter"]) && id(item.parent_id)));
}

/** 只接受本业务保存的完整形状；不把旧稿或损坏记录补成新稿。 */
function checkPreparation(value: unknown): asserts value is CharacterFactPreparationV1 {
  const common = ["schema_id", "schema_version", "key", "revision", "novel_id", "kind"];
  if (!object(value) || value.schema_id !== "character.fact.preparation" || value.schema_version !== 1 || !id(value.key) || !revision(value.revision) || !id(value.novel_id)) throw new Error(INVALID);
  if (value.kind === "create") {
    const profile = value.profile;
    if (!keys(value, [...common, "profile", "fields", "is_core_character", "position", "note"], ["candidate_ref"])
      || !Array.isArray(value.fields) || value.fields.some((field) => !CHARACTER_PROFILE_FACT_FIELDS.includes(field)) || new Set(value.fields).size !== value.fields.length
      || !keys(profile, [...textFields, ...listFields, "role_type", "importance_level"])
      || !textFields.every((field) => typeof profile[field] === "string") || !listFields.every((field) => strings(profile[field]))
      || !oneOf(profile.role_type, ["protagonist", "deuteragonist", "antagonist", "supporting", "minor"])
      || !oneOf(profile.importance_level, ["core", "major", "supporting", "background"])
      || typeof value.is_core_character !== "boolean" || typeof value.note !== "string" || (value.position !== null && !position(value.position, value.novel_id))
      || (Object.hasOwn(value, "candidate_ref") && !id(value.candidate_ref))) throw new Error(INVALID);
    return;
  }
  if (value.kind !== "existing" || !keys(value, [...common, "character_id", "setup"]) || !id(value.character_id)
    || !keys(value.setup, ["operation", "fields", "position", "note", "evidence", "record", "resolves"], ["after", "reason"])) throw new Error(INVALID);
  const setup = value.setup;
  if (!oneOf(setup.operation, operations) || !Array.isArray(setup.fields) || setup.fields.some((field) => !CHARACTER_FACT_FIELDS.includes(field)) || new Set(setup.fields).size !== setup.fields.length
    || (setup.position !== null && !position(setup.position, value.novel_id)) || typeof setup.note !== "string"
    || (setup.evidence !== null && !evidence(setup.evidence)) || (setup.record !== null && !record(setup.record, value.novel_id, value.character_id))
    || !fieldMap(setup.resolves, (item) => strings(item) && item.every(id)) || (Object.hasOwn(setup, "after") && !values(setup.after))
    || (Object.hasOwn(setup, "reason") && typeof setup.reason !== "string")) throw new Error(INVALID);
}

function checkEntry(value: unknown, novelId: string): asserts value is CharacterFactPreparationEntryV1 {
  if (!keys(value, ["key", "scope", "base_version", "value", "updated_at"])) throw new Error(INVALID);
  checkPreparation(value.value);
  if (value.scope !== `${novelId}:character-fact-preparations` || value.value.novel_id !== novelId || value.key !== `${value.scope}:${value.value.key}`
    || value.base_version !== 0 || typeof value.updated_at !== "number" || !Number.isFinite(value.updated_at)) throw new Error(INVALID);
}

/** 功能：恢复本书准备稿；旧新建稿补空选择并同事务提升版本，不猜作者已确认哪些字段。Args: novelId 小说身份。Returns: 事务完成后按保存时间排列的原稿。 */
export async function readCharacterFactPreparations(novelId: string): Promise<CharacterFactPreparationV1[]> {
  if (!id(novelId)) throw new Error(INVALID);
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const request = store.index("scope").getAll(`${novelId}:character-fact-preparations`);
      let rows: CharacterFactPreparationEntryV1[] = [];
      let failure: unknown;
      request.onsuccess = () => {
        try {
          const found: unknown = request.result;
          if (!Array.isArray(found)) throw new Error(INVALID);
          for (const row of found) {
            const value = object(row) ? row.value : undefined;
            // 仅兼容没有字段选择的旧准备稿；严格检查仍拒绝 basis、command 或其他多余键。
            const legacy = object(value) && value.kind === "create" && !Object.hasOwn(value, "fields");
            if (legacy) {
              if (!revision(value.revision)) throw new Error(INVALID);
              row.value = { ...value, fields: [], revision: value.revision + 1 };
            }
            checkEntry(row, novelId);
            if (legacy) store.put(row);
          }
          rows = found as CharacterFactPreparationEntryV1[];
        } catch (error) { failure = error; transaction.abort(); }
      };
      transaction.oncomplete = () => resolve(rows.sort((a, b) => a.updated_at - b.updated_at).map((row) => row.value));
      transaction.onerror = transaction.onabort = () => reject(failure ?? transaction.error ?? new Error(FAILED));
    });
  } finally { db.close(); }
}

/** 功能：同一事务比较本地原版本后保存作者输入，不产生服务端依据。Args: 原稿和持有版本，新稿版本为 null。Returns: 提交成功标记。 */
export async function writeCharacterFactPreparation(preparation: CharacterFactPreparationV1, expectedRevision: number | null): Promise<{ written: true }> {
  checkPreparation(preparation);
  if (expectedRevision !== null && !revision(expectedRevision)) throw new Error(INVALID);
  const snapshot = structuredClone(preparation);
  const scope = `${snapshot.novel_id}:character-fact-preparations`;
  const key = `${scope}:${snapshot.key}`;
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const request = store.get(key);
      let failure: unknown;
      request.onsuccess = () => {
        try {
          const previous: unknown = request.result;
          if (previous !== undefined) checkEntry(previous, snapshot.novel_id);
          const current = previous as CharacterFactPreparationEntryV1 | undefined;
          if ((current?.value.revision ?? null) !== expectedRevision || current && (current.value.kind !== snapshot.kind
            || current.value.kind === "existing" && snapshot.kind === "existing" && current.value.character_id !== snapshot.character_id
            || snapshot.revision <= current.value.revision && JSON.stringify(snapshot) !== JSON.stringify(current.value))) throw new Error(CONFLICT);
          store.put({ key, scope, base_version: 0, value: snapshot, updated_at: Date.now() } satisfies CharacterFactPreparationEntryV1);
        } catch (error) { failure = error; transaction.abort(); }
      };
      transaction.oncomplete = () => resolve({ written: true });
      transaction.onerror = transaction.onabort = () => reject(failure ?? transaction.error ?? new Error(FAILED));
    });
  } finally { db.close(); }
}

/** 功能：仅删除作者仍持有的准备稿版本，其他标签页改过则保留。Args: 小说、原稿键和持有版本。Returns: 删除事务完成。 */
export async function removeCharacterFactPreparation(novelId: string, key: string, expectedRevision: number): Promise<void> {
  if (!id(novelId) || !id(key) || !revision(expectedRevision)) throw new Error(INVALID);
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const storageKey = `${novelId}:character-fact-preparations:${key}`;
      const request = store.get(storageKey);
      let failure: unknown;
      request.onsuccess = () => {
        try {
          if (request.result === undefined) throw new Error(CONFLICT);
          checkEntry(request.result, novelId);
          if (request.result.value.revision !== expectedRevision) throw new Error(CONFLICT);
          store.delete(storageKey);
        } catch (error) { failure = error; transaction.abort(); }
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = transaction.onabort = () => reject(failure ?? transaction.error ?? new Error(FAILED));
    });
  } finally { db.close(); }
}

/** 功能：预览成功后用一笔本地事务保存确认稿并移除准备稿，失败时两边都不改变。Args: 原准备稿、新预览稿和持有版本。Returns: 提交成功标记。 */
export async function promoteCharacterFactPreparation(preparation: CharacterFactPreparationV1, draft: CharacterFactDraftV1, expectedRevision: number): Promise<{ written: true }> {
  checkPreparation(preparation);
  const target = draft.preview?.basis?.target;
  if (!revision(expectedRevision) || preparation.revision !== expectedRevision || draft.schema_id !== "character.fact.draft" || draft.schema_version !== 1
    || !id(draft.key) || !revision(draft.revision) || draft.command !== undefined || draft.authorConfirmed !== false || target?.novel_id !== preparation.novel_id
    || (preparation.kind === "create" ? target.kind !== "new" || draft.preview.basis.operation !== "create" : target.kind !== "existing" || target.character_id !== preparation.character_id || draft.preview.basis.operation !== preparation.setup.operation)) throw new Error(INVALID);
  const snapshot = structuredClone(draft);
  const frozenTarget = snapshot.preview.basis.target;
  const original = structuredClone(preparation);
  const scope = characterFactDraftScope(original.novel_id);
  const draftKey = `${scope}:${snapshot.key}`;
  const preparationKey = `${original.novel_id}:character-fact-preparations:${original.key}`;
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const current = store.get(preparationKey);
      let failure: unknown;
      current.onsuccess = () => {
        try {
          if (current.result === undefined) throw new Error(CONFLICT);
          checkEntry(current.result, original.novel_id);
          if (current.result.value.revision !== expectedRevision || JSON.stringify(current.result.value) !== JSON.stringify(original)) throw new Error(CONFLICT);
          const destination = store.get(draftKey);
          destination.onsuccess = () => {
            try {
              if (destination.result !== undefined) throw new Error(CONFLICT);
              store.add({ key: draftKey, scope, base_version: frozenTarget.kind === "existing" ? frozenTarget.version : 0, value: snapshot, updated_at: Date.now() } satisfies CharacterFactDraftEntryV1);
              store.delete(preparationKey);
            } catch (error) { failure = error; transaction.abort(); }
          };
        } catch (error) { failure = error; transaction.abort(); }
      };
      transaction.oncomplete = () => resolve({ written: true });
      transaction.onerror = transaction.onabort = () => reject(failure ?? transaction.error ?? new Error(FAILED));
    });
  } finally { db.close(); }
}

/** 功能：串行保存每次输入，只有事务完成才更新持有版本，已清理的原键不复建。Args: 当前小说。Returns: 队列、持有版本和保存、清理、转换接口；恢复稿后由宿主登记持有版本。 */
export function useCharacterFactPreparationPersistence(novelId: string) {
  return useMemo(() => {
    const state = { queue: { current: Promise.resolve() as Promise<unknown> }, persisted: { current: new Map<string, number>() }, removed: new Set<string>() };
    const persist = (preparation: CharacterFactPreparationV1) => {
      const snapshot = structuredClone(preparation);
      const pending = state.queue.current.catch(() => {}).then(async () => {
        if (snapshot.novel_id !== novelId || state.removed.has(snapshot.key)) throw new Error(CONFLICT);
        const result = await writeCharacterFactPreparation(snapshot, state.persisted.current.get(snapshot.key) ?? null);
        state.persisted.current.set(snapshot.key, snapshot.revision);
        return result;
      });
      state.queue.current = pending;
      return pending;
    };
    const remove = (preparation: CharacterFactPreparationV1) => {
      const snapshot = structuredClone(preparation);
      const pending = state.queue.current.then(async () => {
        if (snapshot.novel_id !== novelId) throw new Error(CONFLICT);
        await removeCharacterFactPreparation(novelId, snapshot.key, state.persisted.current.get(snapshot.key) ?? snapshot.revision);
        state.persisted.current.delete(snapshot.key); state.removed.add(snapshot.key);
      });
      state.queue.current = pending;
      return pending;
    };
    const promote = (preparation: CharacterFactPreparationV1, draft: CharacterFactDraftV1) => {
      const original = structuredClone(preparation), snapshot = structuredClone(draft);
      const pending = state.queue.current.then(async () => {
        if (original.novel_id !== novelId || state.removed.has(original.key)) throw new Error(CONFLICT);
        const result = await promoteCharacterFactPreparation(original, snapshot, state.persisted.current.get(original.key) ?? original.revision);
        state.persisted.current.delete(original.key); state.removed.add(original.key);
        return result;
      });
      state.queue.current = pending;
      return pending;
    };
    return { queue: state.queue, persisted: state.persisted, persist, remove, promote };
  }, [novelId]);
}
