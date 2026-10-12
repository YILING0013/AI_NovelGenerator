import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type { CharacterFactCommandV1, CharacterFactDraftV1 } from "./characterFactDrafts";
import type { CharacterRelationFactCommandV1, CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import type { ItemFactCommandV1, ItemFactDraftV1, ItemFactBatchCommandV1, ItemFactBatchDraftV1 } from "../items/itemFactDrafts";

/** 人物、关系和物品共用原本地事务；域只决定标记和范围，不能互换原稿。 */
export type FactDomain = "character" | "character_relation" | "item" | "item_batch";
export type FactDraft = CharacterFactDraftV1 | CharacterRelationFactDraftV1 | ItemFactDraftV1 | ItemFactBatchDraftV1;
export type FactCommand = CharacterFactCommandV1 | CharacterRelationFactCommandV1 | ItemFactCommandV1 | ItemFactBatchCommandV1;
export type FactResult<D extends FactDraft> = NonNullable<NonNullable<D["command"]>["saved"]>;
type CommandEntry = WritingDraft<FactCommand> & { draft_key: string };

const domains = {
  character: { scope: "character-facts", error: "CHARACTER_FACT", draft: "character.fact.draft", command: "character.fact.command" },
  character_relation: { scope: "character-relation-facts", error: "CHARACTER_RELATION_FACT", draft: "character_relation.fact.draft", command: "character_relation.fact.command" },
  item: { scope: "item-facts", error: "ITEM_FACT", draft: "item.fact.draft", command: "item.fact.command" },
  item_batch: { scope: "item-fact-batches", error: "ITEM_FACT_BATCH", draft: "item.fact.batch.draft", command: "item.fact.batch.command" },
} as const;

export interface FactDraftWriteResult<D extends FactDraft> {
  saved?: FactResult<D>;
  /** 成功回执优先返回时不改稿，也不能提升调用方持有的稿版本。 */
  written: boolean;
}

/** 功能：比较原请求及展示快照，成功状态不改变请求身份。Args: 固定域、两份命令。Returns: 冻结内容是否一致。 */
function sameCommand(domain: FactDomain, left: FactCommand, right: FactCommand): boolean {
  return left.schema_id === domains[domain].command && left.schema_version === 1
    && right.schema_id === domains[domain].command && right.schema_version === 1
    && left.key === right.key && left.positionLabel === right.positionLabel && JSON.stringify(left.body) === JSON.stringify(right.body);
}

/** 功能：拒绝其他书、其他域或非法本地版本，不升级旧结构。Args: 固定域、范围和原稿。Returns: 无。 */
function checkDraft(domain: FactDomain, scope: string, draft: FactDraft): void {
  const config = domains[domain];
  if (draft.schema_id !== config.draft || draft.schema_version !== 1 || !draft.key || !Number.isSafeInteger(draft.revision) || draft.revision < 1
    || scope !== `${draft.schema_id === "item.fact.batch.draft" ? draft.preview.generation.basis.novel_id : draft.preview.basis.target.novel_id}:${config.scope}`
    || (draft.command && (draft.command.schema_id !== config.command || draft.command.schema_version !== 1
      || scope !== `${draft.command.schema_id === "item.fact.batch.command" ? draft.command.body.generation.basis.novel_id : draft.command.body.basis.target.novel_id}:${config.scope}` || !draft.command.key))) {
    throw new Error(`${config.error}_LOCAL_CONFLICT`);
  }
}

/** 功能：核对成功结果属于原目标、原动作和原版本。Args: 原命令及返回结果。Returns: 是否可保存为原请求回执。 */
function matchesReceipt(command: FactCommand, receipt: FactResult<FactDraft>): boolean {
  if (command.schema_id === "item.fact.batch.command") {
    if (!("candidate_ref_map" in receipt) || receipt.items.length !== command.body.entries.length
      || Object.keys(receipt.candidate_ref_map).length !== command.body.entries.length) return false;
    const ids = new Set<string>();
    return command.body.entries.every((entry) => {
      const itemId = receipt.candidate_ref_map[entry.candidate_ref];
      const item = receipt.items.find((row) => row.item_id === itemId);
      if (!item || ids.has(itemId) || item.version !== 1 || item.novel_id !== command.body.generation.basis.novel_id) return false;
      ids.add(itemId);
      const target = entry.command.basis.target;
      return target.kind === "new" && Object.entries({ ...target.candidate, ...entry.command.after }).every(([key, value]) => JSON.stringify(item[key as keyof typeof item]) === JSON.stringify(value));
    });
  }
  const target = command.body.basis.target;
  if (command.schema_id === "item.fact.command") {
    if (!("item_id" in receipt) || receipt.schema_version !== 1 || receipt.novel_id !== target.novel_id
      || receipt.entity_id !== target.entity_id || receipt.operation !== command.body.operation) return false;
    const item = command.body.basis.target;
    if (item.kind === "new" ? receipt.before_version !== null || receipt.after_version !== 1
      : receipt.item_id !== item.item_id || receipt.before_version !== item.version || receipt.after_version !== item.version + 1) return false;
    return command.body.operation === "void" ? receipt.record === null : receipt.record?.schema_id === "item.fact"
      && receipt.record.entity_id === receipt.entity_id && receipt.record.item_id === receipt.item_id
      && (["lifecycle_status", "owner_character_id", "controlling_faction_id", "current_location_id"] as const).every((field) => receipt.record!.after[field] === command.body.after?.[field]);
  }
  if (command.schema_id === "character.fact.command") {
    const character = command.body.basis.target;
    return "character_id" in receipt && receipt.schema_version === 1 && receipt.operation === command.body.operation
      && receipt.novel_id === target.novel_id && receipt.entity_id === target.entity_id
      && (character.kind === "new" ? receipt.before_version === null : receipt.character_id === character.character_id && receipt.before_version === character.version);
  }
  const relation = command.body.basis.target;
  if (!("relation_id" in receipt) || receipt.schema_version !== 1 || receipt.operation !== command.body.operation
    || receipt.novel_id.toLowerCase() !== relation.novel_id.toLowerCase() || receipt.entity_id.toLowerCase() !== relation.entity_id.toLowerCase()
    || !/^cr_[0-9]{6,19}$/.test(receipt.relation_id)
    || (relation.kind === "new" ? receipt.before_version !== null || receipt.after_version !== 1
      : receipt.relation_id !== relation.relation_id || receipt.before_version !== relation.version || receipt.after_version !== relation.version + 1)) return false;
  for (const side of ["source", "target"] as const) {
    const endpoint = relation[`${side}_character`];
    if (receipt[`${side}_character_id`] !== endpoint.character_id || receipt[`${side}_character_entity_id`].toLowerCase() !== endpoint.entity_id.toLowerCase()
      || receipt[`${side}_character_name`] !== endpoint.name) return false;
  }
  const record = receipt.record;
  return command.body.operation === "void" ? record === null
    : record !== null && record.schema_id === "character_relation.fact" && record.schema_version === 1 && record.entity_type === "character_relation"
      && record.entity_id.toLowerCase() === receipt.entity_id.toLowerCase() && record.novel_id.toLowerCase() === receipt.novel_id.toLowerCase()
      && record.relation_id === receipt.relation_id && record.operation === receipt.operation
      && record.before_version === receipt.before_version && record.after_version === receipt.after_version;
}

/** 功能：在一个读取事务恢复原稿及独立成功回执。Args: 固定域和小说范围。Returns: 仍须读取当前资料的原稿列表。 */
export async function readFactDrafts<D extends FactDraft>(domain: FactDomain, scope: string): Promise<D[]> {
  const config = domains[domain];
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const store = transaction.objectStore("business_drafts");
      const drafts = store.index("scope").getAll(scope);
      const operations = store.index("scope").getAll(`${scope}:operations`);
      transaction.oncomplete = () => {
        try {
          const commands = new Map((operations.result as CommandEntry[]).map((row) => [row.value.key, row]));
          resolve((drafts.result as WritingDraft<D>[]).sort((a, b) => a.updated_at - b.updated_at).map((row) => {
            const draft = row.value;
            checkDraft(domain, scope, draft);
            if (row.key !== `${scope}:${draft.key}` || row.scope !== scope) throw new Error(`${config.error}_LOCAL_CONFLICT`);
            if (!draft.command) return draft;
            const operation = commands.get(draft.command.key);
            if (!operation || operation.draft_key !== draft.key || !sameCommand(domain, operation.value, draft.command) || (draft.command.saved && !operation.value.saved)) throw new Error(`${config.error}_LOCAL_CONFLICT`);
            const saved = operation.value.saved;
            // 别页读回不能证明当前页面已读；未成功命令保持原形状，避免同版本恢复被误判改稿。
            return saved ? { ...draft, command: { ...draft.command, saved, unknown: false, readbackDone: false } } : draft;
          }));
        } catch (error) { reject(error); }
      };
      transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error(`${config.error}_LOCAL_FAILED`));
    });
  } finally { db.close(); }
}

/** 功能：同事务比较稿版本并登记原请求，事务完成后才可发送。Args: 固定域、范围、原稿、已持有版本；remove 只清已读回成功稿或未冻结稿。Returns: 是否写稿及首次成功。 */
export async function writeFactDraft<D extends FactDraft>(domain: FactDomain, scope: string, draft: D, expectedRevision: number | null, remove = false): Promise<FactDraftWriteResult<D>> {
  checkDraft(domain, scope, draft);
  const config = domains[domain];
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const key = `${scope}:${draft.key}`;
      let conflict = false;
      let result: FactDraftWriteResult<D> = { written: false };
      const abort = () => { conflict = true; transaction.abort(); };
      const save = (operation?: CommandEntry) => {
        const command = draft.command;
        if (operation && (operation.scope !== `${scope}:operations` || operation.draft_key !== draft.key || !command || !sameCommand(domain, operation.value, command))) { abort(); return; }
        // 原成功先于普通稿 CAS；旧页面不重发，也不覆盖新页面的稿。
        if (!remove && operation?.value.saved) { result = { saved: operation.value.saved as FactResult<D>, written: false }; return; }
        if (command && (command.saved || command.readbackDone) && !operation?.value.saved) { abort(); return; }
        const current = store.get(key);
        current.onsuccess = () => {
          const previous = current.result as WritingDraft<D> | undefined;
          if (remove && !previous && operation?.value.saved && command?.readbackDone) { result = { saved: operation.value.saved as FactResult<D>, written: false }; return; }
          if (previous && (previous.scope !== scope || previous.value.schema_id !== config.draft || previous.value.schema_version !== 1)) { abort(); return; }
          if ((previous?.value.revision ?? null) !== expectedRevision) { abort(); return; }
          if (previous && (previous.value.schema_id === "item.fact.draft" || previous.value.schema_id === "item.fact.batch.draft")
            && (previous.value.reprepared || previous.value.returnedToCheck) && JSON.stringify(draft) !== JSON.stringify(previous.value)) { abort(); return; }
          if (previous?.value.command && (!command || !sameCommand(domain, previous.value.command, command) || !operation)) { abort(); return; }
          if (!remove && previous && draft.revision <= previous.value.revision && JSON.stringify(draft) !== JSON.stringify(previous.value)) { abort(); return; }
          if (remove) {
            if (command && (!operation?.value.saved || !command.readbackDone)) { abort(); return; }
            store.delete(key);
            result = { saved: operation?.value.saved as FactResult<D> | undefined, written: true };
            return;
          }
          if (command && !operation) {
            store.add({ key: `${scope}:operation:${command.key}`, scope: `${scope}:operations`, draft_key: draft.key, base_version: 0,
              value: { schema_id: config.command, schema_version: 1, key: command.key, positionLabel: command.positionLabel, body: command.body, unknown: true }, updated_at: Date.now() });
          }
          store.put({ key, scope, base_version: draft.schema_id !== "item.fact.batch.draft" && draft.preview.basis.target.kind === "existing" ? draft.preview.basis.target.version : 0, value: draft, updated_at: Date.now() } satisfies WritingDraft<D>);
          result = { written: true };
        };
      };
      if (draft.command) {
        const operation = store.get(`${scope}:operation:${draft.command.key}`);
        operation.onsuccess = () => save(operation.result as CommandEntry | undefined);
      } else save();
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = transaction.onabort = () => reject(conflict ? new Error(`${config.error}_LOCAL_CONFLICT`) : transaction.error ?? new Error(`${config.error}_LOCAL_FAILED`));
    });
  } finally { db.close(); }
}

/** 功能：保存原命令的首次成功，迟到响应不依赖当前稿编辑权。Args: 固定域、范围、带成功结果的原命令。Returns: 首次完整回执。 */
export async function writeFactReceipt<C extends FactCommand>(domain: FactDomain, scope: string, command: C): Promise<NonNullable<C["saved"]>> {
  const config = domains[domain];
  if (scope !== `${command.schema_id === "item.fact.batch.command" ? command.body.generation.basis.novel_id : command.body.basis.target.novel_id}:${config.scope}`) throw new Error(`${config.error}_LOCAL_CONFLICT`);
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const request = store.get(`${scope}:operation:${command.key}`);
      let conflict = false;
      let saved: NonNullable<C["saved"]>;
      request.onsuccess = () => {
        const row = request.result as CommandEntry | undefined;
        if (!row || row.scope !== `${scope}:operations` || !sameCommand(domain, row.value, command) || (!row.value.saved && (!command.saved || !matchesReceipt(command, command.saved)))) { conflict = true; transaction.abort(); return; }
        saved = (row.value.saved ?? command.saved!) as NonNullable<C["saved"]>;
        if (!row.value.saved) store.put({ ...row, value: { ...row.value, saved, unknown: false }, updated_at: Date.now() });
      };
      transaction.oncomplete = () => resolve(saved);
      transaction.onerror = transaction.onabort = () => reject(conflict ? new Error(`${config.error}_LOCAL_CONFLICT`) : transaction.error ?? new Error(`${config.error}_LOCAL_FAILED`));
    });
  } finally { db.close(); }
}
