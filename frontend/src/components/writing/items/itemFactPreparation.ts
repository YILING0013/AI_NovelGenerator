import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { ItemFieldsV1, ItemBulkGeneratedRequestV1 } from "@/types/item";
import type { CharacterFactPositionV1 } from "@/types/characterFacts";
import type { ChapterRecordEvidenceV1 } from "@/types/chapterRecords";
import type { ItemFactOperation, ItemFactRecordV1, ItemFactValuesV1 } from "@/types/itemFacts";
import type { ItemFactDraftV1, ItemFactBatchDraftV1 } from "./itemFactDrafts";
import type { ChapterRecordDraft } from "../chapter-records/chapterRecordDrafts";

/** 预览前只存作者正在填写的内容，不在恢复时重读或改写原请求。 */
export interface ItemFactPreparationV1 {
  key: string; revision: number; novelId: string;
  operation: ItemFactOperation; kind: "start" | "change";
  target?: { entity_id: string; item_id: string; expected_version: number; name: string };
  candidate?: ItemFieldsV1; generation?: ItemBulkGeneratedRequestV1;
  position: CharacterFactPositionV1 | null; note: string; evidence: ChapterRecordEvidenceV1 | null;
  after: ItemFactValuesV1; reason: string; record?: ItemFactRecordV1; resolves: string[];
  origin?: ItemFactDraftV1["origin"];
  ownerOnly?: boolean;
  ownerBefore?: ItemFactValuesV1;
  returnedToCheck?: boolean;
}

/** 功能：读取本书预览前的物品稿。Args: 小说。Returns: 原稿列表。 */
export async function readItemFactPreparations(novelId: string): Promise<ItemFactPreparationV1[]> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly");
    const request = tx.objectStore("business_drafts").index("scope").getAll(`${novelId}:item-fact-preparations`);
    tx.oncomplete = () => resolve((request.result as WritingDraft<ItemFactPreparationV1>[]).map((row) => row.value));
    tx.onerror = tx.onabort = () => reject(tx.error ?? new Error("ITEM_FACT_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：只识别尚未填写的独立新建物品稿。Args: 当前准备稿。Returns: 是否没有作者内容、来源或已有资料。 */
export function isEmptyItemFactPreparation(draft: ItemFactPreparationV1): boolean {
  if (draft.operation !== "create" || draft.kind !== "start" || !draft.candidate || draft.target || draft.generation || draft.record || draft.origin || draft.ownerOnly || draft.returnedToCheck
    || draft.position || draft.evidence || draft.note.trim() || draft.reason.trim() || draft.resolves.length) return false;
  return Object.entries(draft.candidate).every(([field, value]) => field === "lifecycle_status" ? value === "available"
    : value === null || (Array.isArray(value) ? value.length === 0 : typeof value === "string" && !value.trim()))
    && draft.after.lifecycle_status === "available" && !draft.after.owner_character_id && !draft.after.controlling_faction_id && !draft.after.current_location_id;
}

/** 功能：只丢弃作者持有的同版本准备稿，不处理已预览原请求或检查关联。Args: 完整原稿。Returns: 精确单稿清理完成；跨标签变化时拒绝。 */
export async function discardItemFactPreparation(original: ItemFactPreparationV1): Promise<void> {
  if (original.origin || original.returnedToCheck) throw new Error("ITEM_FACT_LOCAL_CONFLICT");
  const db = await openTaskFlowDatabase();
  const scope = `${original.novelId}:item-fact-preparations`;
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let failure: Error | undefined;
    const key = `${scope}:${original.key}`;
    const request = store.get(key);
    request.onsuccess = () => {
      const row = request.result as WritingDraft<ItemFactPreparationV1> | undefined;
      if (!row || row.scope !== scope || JSON.stringify(row.value) !== JSON.stringify(original)) {
        failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); return;
      }
      store.delete(key);
    };
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error("ITEM_FACT_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：比较本地稿版本后保存，预览成功时同事务换成确认稿。Args: 原稿、持有版本和可选确认稿。Returns: 落盘完成。 */
export async function writeItemFactPreparation(draft: ItemFactPreparationV1, expected: number | null, confirmation?: ItemFactDraftV1 | ItemFactBatchDraftV1): Promise<void> {
  const db = await openTaskFlowDatabase();
  const scope = `${draft.novelId}:item-fact-preparations`;
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite");
    const store = tx.objectStore("business_drafts");
    const key = `${scope}:${draft.key}`;
    const request = store.get(key);
    let failure: Error | undefined;
    request.onsuccess = () => {
      const current = (request.result as WritingDraft<ItemFactPreparationV1> | undefined)?.value;
      if ((current?.revision ?? null) !== expected || current && (current.novelId !== draft.novelId || draft.revision < current.revision || draft.revision === current.revision && JSON.stringify(current) !== JSON.stringify(draft))) {
        failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); return;
      }
      if (current?.returnedToCheck) {
        if (confirmation || JSON.stringify(current) !== JSON.stringify(draft)) { failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); }
        return;
      }
      const save = (source?: WritingDraft<ChapterRecordDraft>) => {
      if (confirmation) {
        const destination = `${draft.novelId}:${confirmation.schema_id === "item.fact.batch.draft" ? "item-fact-batches" : "item-facts"}`;
        store.add({ key: `${destination}:${confirmation.key}`, scope: destination, base_version: draft.target?.expected_version ?? 0, value: confirmation, updated_at: Date.now() });
        if (source) store.put({ ...source, value: { ...source.value, revision: source.value.revision + 1, itemFact: { preparationKey: draft.key, draftKey: confirmation.key } }, updated_at: Date.now() });
        store.delete(key);
      } else store.put({ key, scope, base_version: draft.target?.expected_version ?? 0, value: draft, updated_at: Date.now() });
      };
      if (draft.origin) {
        const source = store.get(`${draft.origin.scope}:${draft.origin.draftKey}`);
        source.onsuccess = () => {
          const row = source.result as WritingDraft<ChapterRecordDraft> | undefined;
          if (!row || row.scope !== draft.origin!.scope || row.value.itemFact?.preparationKey !== draft.key || row.value.itemFact.draftKey
            || row.value.itemOwner?.from_character_id !== draft.ownerBefore?.owner_character_id || row.value.itemOwner?.to_character_id !== draft.after.owner_character_id) {
            failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); return;
          }
          save(row);
        };
      } else save();
    };
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error("ITEM_FACT_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：安全取消物品事实关联并退回原检查，保留原稿和审核方向。Args: 小说及未派发或明确拒绝的确认稿／准备稿。Returns: 已取消采用的原 B/F 检查稿。 */
export async function returnItemFactToCheck(novelId: string, original: ItemFactDraftV1 | ItemFactPreparationV1): Promise<ChapterRecordDraft> {
  const confirmation = "schema_id" in original;
  const command = confirmation ? original.command : undefined;
  const origin = original.origin;
  if (!origin || original.returnedToCheck || confirmation && original.reprepared
    || command && (command.unknown !== false || command.saved)) throw new Error("ITEM_FACT_LOCAL_CONFLICT");
  const scope = `${novelId}:${confirmation ? "item-facts" : "item-fact-preparations"}`;
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let returned: ChapterRecordDraft;
    let failure: Error | undefined;
    const abort = () => { failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); };
    const request = store.get(`${scope}:${original.key}`);
    request.onsuccess = () => {
      const row = request.result as WritingDraft<typeof original> | undefined;
      if (!row || row.scope !== scope || JSON.stringify(row.value) !== JSON.stringify(original)) { abort(); return; }
      const operations = store.index("scope").getAll(`${novelId}:item-facts:operations`);
      operations.onsuccess = () => {
        const entries = (operations.result as (WritingDraft<NonNullable<ItemFactDraftV1["command"]>> & { draft_key: string })[]).filter((entry) => entry.draft_key === original.key);
        if (command ? entries.length !== 1 || entries[0].value.saved || entries[0].value.key !== command.key || JSON.stringify(entries[0].value.body) !== JSON.stringify(command.body) : entries.length > 0) { abort(); return; }
        const source = store.get(`${origin.scope}:${origin.draftKey}`);
        source.onsuccess = () => {
          const sourceRow = source.result as WritingDraft<ChapterRecordDraft> | undefined;
          const link = sourceRow?.value.itemFact;
          if (!sourceRow || sourceRow.scope !== origin.scope || !sourceRow.value.itemOwner || sourceRow.value.command
            || (confirmation ? link?.draftKey !== original.key : link?.preparationKey !== original.key || link.draftKey)) { abort(); return; }
          returned = { ...sourceRow.value, revision: sourceRow.value.revision + 1, itemFact: undefined,
            itemOwnerCheck: sourceRow.value.itemOwnerCheck ? { ...sourceRow.value.itemOwnerCheck, status: "rejected" } : undefined };
          store.put({ ...row, value: { ...original, revision: original.revision + 1, returnedToCheck: true }, updated_at: Date.now() });
          store.put({ ...sourceRow, value: returned, updated_at: Date.now() });
        };
      };
    };
    tx.oncomplete = () => resolve(returned);
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error("ITEM_FACT_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：未派发或明确拒绝后另存准备，原稿、发送记录和 B/F 关联在同一事务核对。Args: 原确认稿和作者核对后的新准备。Returns: 原稿失去发送权，新准备可继续编辑。 */
export async function reprepareItemFact(previous: ItemFactDraftV1 | ItemFactBatchDraftV1, preparation: ItemFactPreparationV1): Promise<void> {
  const command = previous.command;
  const novelId = preparation.novelId;
  if (command && (command.unknown !== false || command.saved) || previous.reprepared || previous.returnedToCheck
    || (previous.schema_id === "item.fact.draft" ? previous.preview.basis.target.novel_id : previous.preview.generation.basis.novel_id) !== novelId) throw new Error("ITEM_FACT_LOCAL_CONFLICT");
  const scope = `${novelId}:${previous.schema_id === "item.fact.draft" ? "item-facts" : "item-fact-batches"}`;
  const db = await openTaskFlowDatabase();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let failure: Error | undefined;
    const abort = () => { failure = new Error("ITEM_FACT_LOCAL_CONFLICT"); tx.abort(); };
    const original = store.get(`${scope}:${previous.key}`);
    original.onsuccess = () => {
      const row = original.result as WritingDraft<typeof previous> | undefined;
      if (!row || row.scope !== scope || JSON.stringify(row.value) !== JSON.stringify(previous)) { abort(); return; }
      const operation = command ? store.get(`${scope}:operation:${command.key}`) : store.index("scope").getAll(`${scope}:operations`);
      operation.onsuccess = () => {
        if (command) {
          const entry = operation.result as (WritingDraft<typeof command> & { draft_key: string }) | undefined;
          if (!entry || entry.scope !== `${scope}:operations` || entry.draft_key !== previous.key || entry.value.saved
            || entry.value.key !== command.key || entry.value.schema_id !== command.schema_id || JSON.stringify(entry.value.body) !== JSON.stringify(command.body)) { abort(); return; }
        } else if ((operation.result as { draft_key: string }[]).some((entry) => entry.draft_key === previous.key)) { abort(); return; }
        const save = (source?: WritingDraft<ChapterRecordDraft>) => {
          const destination = `${novelId}:item-fact-preparations`;
          store.add({ key: `${destination}:${preparation.key}`, scope: destination, base_version: preparation.target?.expected_version ?? 0, value: preparation, updated_at: Date.now() });
          store.put({ ...row, value: { ...previous, revision: previous.revision + 1, reprepared: preparation.key }, updated_at: Date.now() });
          if (source) store.put({ ...source, value: { ...source.value, revision: source.value.revision + 1, itemFact: { preparationKey: preparation.key } }, updated_at: Date.now() });
        };
        const origin = previous.schema_id === "item.fact.draft" ? previous.origin : undefined;
        if (!origin) { save(); return; }
        const source = store.get(`${origin.scope}:${origin.draftKey}`);
        source.onsuccess = () => {
          const sourceRow = source.result as WritingDraft<ChapterRecordDraft> | undefined;
          if (!sourceRow || sourceRow.scope !== origin.scope || sourceRow.value.itemFact?.draftKey !== previous.key
            || JSON.stringify(preparation.origin) !== JSON.stringify(origin) || !preparation.ownerOnly
            || sourceRow.value.itemOwner?.item_id !== preparation.target?.item_id
            || sourceRow.value.itemOwner?.from_character_id !== preparation.ownerBefore?.owner_character_id
            || sourceRow.value.itemOwner?.to_character_id !== preparation.after.owner_character_id) { abort(); return; }
          save(sourceRow);
        };
      };
    };
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(failure ?? tx.error ?? new Error("ITEM_FACT_LOCAL_FAILED"));
  }); } finally { db.close(); }
}
