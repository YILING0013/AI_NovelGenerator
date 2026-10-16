import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { FactionFactCreateDataV1, FactionFactField, FactionFactPositionV1, FactionFactPreviewExistingTargetV1, FactionFactPreviewInputV1, FactionFactRecordV1, FactionFactValuesV1 } from "@/types/factionFacts";
import type { ChapterRecordEvidenceV1 } from "@/types/chapterRecords";
import type { FactionFactDraftV1 } from "./factionFactDrafts";

/** 只有作者输入；预览后固定映射到独立事实稿，旧标签不能再次派发。 */
export interface FactionFactPreparationV1 {
  schema_id: "faction.fact.preparation";
  schema_version: 1;
  key: string;
  revision: number;
  novel_id: string;
  position: FactionFactPositionV1;
  target: FactionFactPreviewExistingTargetV1 | null;
  candidate: FactionFactCreateDataV1 | null;
  initial: FactionFactValuesV1;
  after: FactionFactValuesV1;
  records: FactionFactRecordV1[];
  fields?: FactionFactField[];
  blockers: Partial<Record<FactionFactField, string[]>>;
  void_record: FactionFactRecordV1 | null;
  reason: string;
  change?: boolean;
  evidence?: ChapterRecordEvidenceV1 | null;
  comparison?: { before: FactionFactValuesV1; current: FactionFactValuesV1 };
  promoted_to?: string;
}

/** 明确拒绝后才能另建核对稿；同一事务保留并封存原请求，未知或成功绝不换键。 */
export async function reprepareFactionFact(previous: FactionFactDraftV1, next: FactionFactPreparationV1): Promise<void> {
  const scope = `${next.novel_id}:faction-facts`, command = previous.command;
  if (!command || command.unknown !== false || command.saved || previous.reprepared
    || command.body.basis.target.novel_id !== next.novel_id) throw failure();
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
      let error: unknown;
      const fail = () => { error = failure(); tx.abort(); };
      const draftRequest = store.get(`${scope}:${previous.key}`), operationRequest = store.get(`${scope}:operation:${command.key}`);
      operationRequest.onsuccess = () => {
        const row = draftRequest.result as WritingDraft<FactionFactDraftV1> | undefined, operation = operationRequest.result;
        if (!row || JSON.stringify(row.value) !== JSON.stringify(previous) || !operation || operation.draft_key !== previous.key
          || operation.value.saved || JSON.stringify(operation.value.body) !== JSON.stringify(command.body)) { fail(); return; }
        const nextScope = scopeFor(next.novel_id);
        const entry = { key: `${nextScope}:${next.key}`, scope: nextScope, base_version: 0, value: structuredClone(next), updated_at: Date.now() };
        try { checkEntry(entry, next.novel_id); } catch { fail(); return; }
        store.add(entry);
        store.put({ ...row, value: { ...row.value, revision: row.value.revision + 1, reprepared: next.key }, updated_at: Date.now() });
      };
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () => reject(error ?? tx.error ?? failure());
    });
  } finally { db.close(); }
}

type Entry = WritingDraft<FactionFactPreparationV1>;
const scopeFor = (novelId: string) => `${novelId}:faction-fact-preparations`;
const failure = () => new Error("另一页已保存或更新这份草稿，请重新打开查看；本页文字仍会保留");

/** 位置和内容决定原操作；同位置更正明确关联原记录，旧设计不会变成事实。 */
export function factionFactPreviewInput(value: FactionFactPreparationV1): FactionFactPreviewInputV1 {
  if (value.void_record && value.target) return { operation: "void", target: value.target,
    targets: Object.fromEntries(Object.entries(value.void_record.validity).filter(([, state]) => state?.state === "active").map(([field]) => [field, value.void_record!.history_id])) };
  const fields = Object.keys(value.after) as FactionFactField[];
  if (!fields.length) throw new Error("请先填写或修改要保存的资料");
  const source = { kind: "author" as const, note: "作者确认这处剧情位置的势力资料" };
  if (value.candidate) return { operation: "create", target: { candidate: value.candidate }, position: value.position, source, fields };
  if (!value.target) throw failure();
  const selected = value.records.filter((record) => record.position.intent === value.position.intent
    && record.position.target_id === value.position.target_id && fields.some((field) => record.validity[field]?.state === "active"));
  const kinds = new Set(selected.map((record) => record.kind));
  const sources = new Set(selected.filter((record) => record.kind === "change").map((record) => JSON.stringify(record.source)));
  if (kinds.size > 1 || sources.size > 1) throw new Error("这些资料来自不同的剧情记录，请从对应历史记录更正；编辑内容已保留");
  const replaces = Object.fromEntries(fields.flatMap((field) => {
    const record = selected.find((row) => row.validity[field]?.state === "active");
    return record ? [[field, record.history_id]] : [];
  }));
  const kind = selected[0]?.kind ?? (value.change ? "change" : "start");
  if (kind === "change" && !value.evidence && !selected.length) throw new Error("FACTION_FACT_EVIDENCE_REQUIRED");
  return { operation: selected.length ? value.position.intent === "book_start" ? "correct_initial" : "replace" : kind === "change" ? "change" : "establish",
    target: value.target, position: value.position, kind, source: kind === "change" ? value.evidence ? { kind: "chapter", evidence: value.evidence } : selected[0].source : source,
    fields, replaces, resolves: Object.fromEntries(fields.filter((field) => value.blockers[field]?.length).map((field) => [field, value.blockers[field]])) };
}

function checkEntry(row: Entry, novelId: string) {
  const value = row?.value;
  if (!value || value.schema_id !== "faction.fact.preparation" || value.schema_version !== 1
    || value.novel_id !== novelId || !value.key || !Number.isSafeInteger(value.revision) || value.revision < 1
    || row.scope !== scopeFor(novelId) || row.key !== `${row.scope}:${value.key}`
    || Boolean(value.target) === Boolean(value.candidate) || !value.position || !value.after || !value.initial
    || !Array.isArray(value.records) || "command" in value || "basis" in value) throw failure();
}

/** 读取原准备稿；已转为确认稿的原文仍保留，但不能作为新的保存操作。 */
export async function readFactionFactPreparations(novelId: string): Promise<FactionFactPreparationV1[]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("business_drafts", "readonly");
      const request = tx.objectStore("business_drafts").index("scope").getAll(scopeFor(novelId));
      tx.oncomplete = () => {
        try {
          const rows = request.result as Entry[];
          rows.forEach((row) => checkEntry(row, novelId));
          resolve(rows.filter((row) => !row.value.promoted_to).sort((a, b) => a.updated_at - b.updated_at).map((row) => row.value));
        } catch (error) { reject(error); }
      };
      tx.onerror = tx.onabort = () => reject(tx.error ?? failure());
    });
  } finally { db.close(); }
}

/** 比较原版本后保存；转入确认稿时在同一事务封住准备稿，避免跨标签重复保存。 */
export async function writeFactionFactPreparation(value: FactionFactPreparationV1, expected: number | null, promote?: FactionFactDraftV1): Promise<void> {
  const scope = scopeFor(value.novel_id);
  const row: Entry = { key: `${scope}:${value.key}`, scope, base_version: 0, value: structuredClone(value), updated_at: Date.now() };
  checkEntry(row, value.novel_id);
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("business_drafts", "readwrite");
      const store = tx.objectStore("business_drafts"), request = store.get(row.key);
      let error: unknown;
      request.onsuccess = () => {
        try {
          const previous = request.result as Entry | undefined;
          if (previous) checkEntry(previous, value.novel_id);
          if ((previous?.value.revision ?? null) !== expected || previous?.value.promoted_to
            || previous && (value.revision < previous.value.revision || value.revision === previous.value.revision && JSON.stringify(previous.value) !== JSON.stringify(value))) throw failure();
          if (promote) {
            if (promote.command || promote.preview.basis.target.novel_id !== value.novel_id) throw failure();
            const targetScope = `${value.novel_id}:faction-facts`;
            store.add({ key: `${targetScope}:${promote.key}`, scope: targetScope,
              base_version: promote.preview.basis.target.kind === "existing" ? promote.preview.basis.target.version : 0,
              value: structuredClone(promote), updated_at: Date.now() });
            row.value.promoted_to = promote.key;
            row.value.revision += 1;
          }
          store.put(row);
        } catch (caught) { error = caught; tx.abort(); }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () => reject(error ?? tx.error ?? failure());
    });
  } finally { db.close(); }
}

/**
 * 放弃尚未发送的势力准备稿，另一页改过或已开始确认时保留原稿。
 * Args: value 当前持有的完整准备稿。
 * Returns: 删除本稿的事务完成。
 */
export async function removeFactionFactPreparation(value: FactionFactPreparationV1): Promise<void> {
  const scope = scopeFor(value.novel_id);
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("business_drafts", "readwrite");
      const store = tx.objectStore("business_drafts"), request = store.get(`${scope}:${value.key}`);
      let error: unknown;
      request.onsuccess = () => {
        try {
          const row = request.result as Entry;
          checkEntry(row, value.novel_id);
          if (row.value.promoted_to || JSON.stringify(row.value) !== JSON.stringify(value)) throw failure();
          store.delete(row.key);
        } catch (caught) { error = caught; tx.abort(); }
      };
      tx.oncomplete = () => resolve();
      tx.onerror = tx.onabort = () => reject(error ?? tx.error ?? failure());
    });
  } finally { db.close(); }
}
