import { openTaskFlowDatabase } from "@/lib/taskFlowCache";
import type { WritingDraft } from "@/lib/writingDrafts";
import type {
  ChapterEventReadV1,
  ChapterPsychologicalStateResultV1,
  ChapterRecordEntityRefV1,
  ChapterRecordEvidenceV1,
  ChapterReportReadV1,
  ChapterPsychologicalCheckSourceV1,
  ChapterPsychologicalCheckResultV1,
  ChapterItemOwnerCheckResult,
  ChapterItemOwnerResultV1,
  ChapterCharacterRelationCheckResult,
  ChapterCharacterRelationResultV1,
  ChapterWorldRulesCheckResultV1,
} from "@/types/chapterRecords";
import type { WorldRuleReadV1 } from "@/types/worldRule";
import type { CharacterRelationResponseV1 } from "@/types/character";
import type { CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";
import type { TaskFlowSetup } from "@/hooks/useTaskFlow";
import type { CharacterRelationFactCommandEntryV1, CharacterRelationFactCommandV1, CharacterRelationFactDraftV1 } from "../characters/characterRelationFactDrafts";
import type { CharacterRelationFactPreparationV1 } from "../characters/characterRelationFactPreparation";
import type { ItemFactCommandV1, ItemFactDraftV1 } from "../items/itemFactDrafts";
import type { ItemFactPreparationV1 } from "../items/itemFactPreparation";

/** 同一心理确认稿中的检查输入与结果；恢复不自动运行。 */
export interface ChapterPsychologicalCheck {
  source: ChapterPsychologicalCheckSourceV1;
  target: NonNullable<ChapterRecordDraft["targetState"]>;
  setup: TaskFlowSetup;
  status: "running" | "interrupted" | "done" | "failed" | "adopted" | "rejected";
  result: ChapterPsychologicalCheckResultV1 | null;
  error: string;
}

/** 物品确认稿的固定持有人变更，不随来源章节选择迁移草稿。 */
export interface ChapterItemOwnerTarget {
  item_id: string;
  name: string;
  version: number;
  from_character_id: string;
  from_name: string;
  to_character_id: string;
  to_name: string;
}

/** 与心理检查共用执行流程，恢复时只恢复原检查输入和结果。 */
export interface ChapterItemOwnerCheck {
  source: ChapterPsychologicalCheckSourceV1;
  target: ChapterItemOwnerTarget;
  setup: TaskFlowSetup;
  status: ChapterPsychologicalCheck["status"];
  result: ChapterItemOwnerCheckResult | null;
  error: string;
}

/** 原稿保留关系开始版本及固定端点，不复制完整关系编辑器。 */
export type ChapterCharacterRelationTarget = Pick<CharacterRelationResponseV1,
  "relation_id" | "version" | "source_character_id" | "target_character_id" | "source_character_name" | "target_character_name" | "relation_type" | "current_state"
> & { entity_id?: string };

/** 关系检查沿用原稿的本地保存和中断恢复，不自动修改关系。 */
export interface ChapterCharacterRelationCheck {
  source: ChapterPsychologicalCheckSourceV1;
  target: ChapterCharacterRelationTarget;
  setup: TaskFlowSetup;
  status: ChapterPsychologicalCheck["status"];
  result: ChapterCharacterRelationCheckResult | null;
  error: string;
}

/** 报告稿保留实际检查范围和作者逐条审阅，不把这些字段提交普通报告。 */
export interface ChapterWorldRulesCheck {
  source: ChapterPsychologicalCheckSourceV1;
  target: { rules: WorldRuleReadV1[] };
  setup: TaskFlowSetup;
  status: ChapterPsychologicalCheck["status"];
  result: ChapterWorldRulesCheckResultV1 | null;
  error: string;
  issueEdits?: Array<{ text: string; selected: boolean; rejected: boolean; appended: boolean; duplicate?: boolean }>;
}

/** 章后记录的独立本地稿；冻结请求保留原键、目标和内容。 */
export interface ChapterRecordDraft {
  key: string;
  revision: number;
  mode: "event" | "report" | "psychological-state" | "void-event" | "void-report" | "item-owner" | "character-relation-state";
  chapterId: string;
  title: string;
  content: string;
  summary: string;
  issues: string[];
  psychologicalState: string;
  reason: string;
  evidence: ChapterRecordEvidenceV1 | null;
  relatedEntities: ChapterRecordEntityRefV1[];
  targetState: (Pick<CharacterVolumeStateReadV1, "state_id" | "version" | "character_id" | "psychological_state" | "volume_id"> & { name: string }) | null;
  expectedReportVersion: number;
  recordId: string | null;
  check?: ChapterPsychologicalCheck;
  itemOwner?: ChapterItemOwnerTarget;
  itemOwnerCheck?: ChapterItemOwnerCheck;
  itemCheckVersion?: 1 | 2;
  itemFact?: { preparationKey?: string; draftKey?: string };
  relationTarget?: ChapterCharacterRelationTarget;
  relationCheck?: ChapterCharacterRelationCheck;
  relationState?: string;
  relationCheckVersion?: 1 | 2;
  /** 交接后原建议保留，只从这里继续已有的人工事实准备或确认。 */
  relationFact?: { preparationKey: string; draftKey?: string };
  worldRuleTarget?: ChapterWorldRulesCheck["target"];
  worldRuleCheck?: ChapterWorldRulesCheck;
  review?: { scope: string; reviewId: string; memberId?: string; kind: ChapterCheckReviewMember["kind"]; source: ChapterPsychologicalCheckSourceV1 };
  command?: {
    action: "create-event" | "create-report" | "patch-psychological-state" | "void-event" | "void-report" | "confirm-item-owner" | "confirm-character-relation-state";
    target: string | null;
    body: object;
    key: string;
    saved?: ChapterEventReadV1 | ChapterReportReadV1 | ChapterPsychologicalStateResultV1 | ChapterItemOwnerResultV1 | ChapterCharacterRelationResultV1;
    unknown?: boolean;
    readbackDone?: boolean;
  };
}

export type ChapterRecordOperation = NonNullable<ChapterRecordDraft["command"]>;

/** 关联检查的成员；目标身份沿用对应确认稿，版本保留在独立稿中。 */
export type ChapterCheckReviewMember = {
  draftScope: string;
  draftKey: string;
  operationKey: string | null;
} & (
  | { kind: "psychological"; target: Pick<NonNullable<ChapterRecordDraft["targetState"]>, "state_id" | "character_id" | "volume_id" | "name"> }
  | { kind: "itemOwner"; target: Omit<ChapterItemOwnerTarget, "version"> }
  | { kind: "characterRelation"; target: Omit<ChapterCharacterRelationTarget, "version" | "current_state"> }
);

/** 同一章修订的有限目标检查；成员键固定，不随改稿或确认键变化。 */
export interface ChapterCheckReview {
  reviewId: string;
  source: ChapterPsychologicalCheckSourceV1;
  members: Record<string, ChapterCheckReviewMember>;
}

/** 列表使用同一次读取的原稿与请求回执，成功清稿后仍保留回执。 */
export interface ChapterCheckReviewRead {
  review: ChapterCheckReview;
  members: Record<string, { draft: ChapterRecordDraft | null; operation: ChapterRecordOperation | null; relationFact?: ChapterRelationFactHandoffRead; itemFact?: ChapterItemFactHandoffRead }>;
}

export interface ChapterItemFactHandoffRead {
  preparation: ItemFactPreparationV1 | null;
  draft: ItemFactDraftV1 | null;
  operation: ItemFactCommandV1 | null;
}

/** 功能：在原事务读取物品确认稿与独立回执。Args: 当前表、小说及关联键。Returns: 事务完成后可用的原数据。 */
function readItemFactEntries(store: IDBObjectStore, novelId: string, link: NonNullable<ChapterRecordDraft["itemFact"]>): ChapterItemFactHandoffRead {
  const result: ChapterItemFactHandoffRead = { preparation: null, draft: null, operation: null };
  if (link.preparationKey) {
    const preparation = store.get(`${novelId}:item-fact-preparations:${link.preparationKey}`);
    preparation.onsuccess = () => { result.preparation = (preparation.result as WritingDraft<ItemFactPreparationV1> | undefined)?.value ?? null; };
  }
  if (!link.draftKey) return result;
  const draft = store.get(`${novelId}:item-facts:${link.draftKey}`);
  draft.onsuccess = () => { result.draft = (draft.result as WritingDraft<ItemFactDraftV1> | undefined)?.value ?? null; };
  const commands = store.index("scope").getAll(`${novelId}:item-facts:operations`);
  commands.onsuccess = () => { result.operation = (commands.result as Array<WritingDraft<ItemFactCommandV1> & { draft_key: string }>).find((row) => row.draft_key === link.draftKey)?.value ?? null; };
  return result;
}

/** 功能：恢复 B/F 已交接的物品确认，不给旧请求换键。Args: 小说及原关联键。Returns: 同次读取的原稿和独立回执。 */
export async function readChapterItemFactHandoff(novelId: string, link: NonNullable<ChapterRecordDraft["itemFact"]>): Promise<ChapterItemFactHandoffRead> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly");
    const result = readItemFactEntries(tx.objectStore("business_drafts"), novelId, link);
    tx.oncomplete = () => resolve(result);
    tx.onerror = tx.onabort = () => reject(tx.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：同事务锁住原 B/F 稿并登记其完整物品确认。Args: 原章后稿、持有版本及服务端预览形成的确认稿。Returns: 已关联的原稿。 */
export async function handoffChapterItemFact(scope: string, original: ChapterRecordDraft, confirmation: ItemFactDraftV1): Promise<ChapterRecordDraft> {
  const target = confirmation.preview.basis.target;
  const source = confirmation.preview.basis.source;
  if (original.itemCheckVersion !== 2 || original.command || original.itemFact || original.itemOwnerCheck?.status !== "adopted"
    || target.kind !== "existing" || original.itemOwner?.item_id !== target.item_id || original.itemOwner.version !== target.version
    || source.kind !== "chapter" || (!original.evidence || !sameSource(source.evidence, original.evidence) || source.evidence.start !== original.evidence.start || source.evidence.quote !== original.evidence.quote)) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
  const linked = { ...original, revision: original.revision + 1, itemFact: { draftKey: confirmation.key } };
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    const request = store.get(`${scope}:${original.key}`);
    let conflict = false;
    const abort = () => { conflict = true; tx.abort(); };
    request.onsuccess = () => {
      const row = request.result as WritingDraft<ChapterRecordDraft> | undefined;
      if (!row || JSON.stringify(row.value) !== JSON.stringify(original)) { abort(); return; }
      const save = () => {
        const destination = `${target.novel_id}:item-facts`;
        store.add({ key: `${destination}:${confirmation.key}`, scope: destination, base_version: target.version, value: confirmation, updated_at: Date.now() });
        store.put({ ...row, value: linked, updated_at: Date.now() });
      };
      if (original.review) {
        const review = store.get(`${original.review.scope}:${original.review.reviewId}`);
        review.onsuccess = () => {
          const stored = review.result as WritingDraft<ChapterCheckReview> | undefined;
          if (!stored || !matchesReview(scope, original, stored.value) || stored.value.members[reviewMemberId(original.review!)!].operationKey !== null) { abort(); return; }
          save();
        };
      } else save();
    };
    tx.oncomplete = () => resolve(linked);
    tx.onerror = tx.onabort = () => reject(new Error(conflict ? "CHAPTER_RECORD_LOCAL_CONFLICT" : "CHAPTER_RECORD_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 新事实回执与旧章后 D 回执分开读取，确认稿清理后仍保留成功。 */
export interface ChapterRelationFactHandoffRead {
  preparation: CharacterRelationFactPreparationV1 | null;
  draft: CharacterRelationFactDraftV1 | null;
  operation: CharacterRelationFactCommandV1 | null;
}

/** 功能：在现有读取事务内取关联的人工准备、确认和独立回执。Args: store 原事务、小说及关联键。Returns: 事务完成后可用的结果。 */
function readRelationFactEntries(store: IDBObjectStore, novelId: string, link: NonNullable<ChapterRecordDraft["relationFact"]>): ChapterRelationFactHandoffRead {
  const result: ChapterRelationFactHandoffRead = { preparation: null, draft: null, operation: null };
  const preparation = store.get(`${novelId}:character-relation-fact-preparations:${link.preparationKey}`);
  preparation.onsuccess = () => { result.preparation = (preparation.result as WritingDraft<CharacterRelationFactPreparationV1> | undefined)?.value ?? null; };
  if (link.draftKey) {
    const draft = store.get(`${novelId}:character-relation-facts:${link.draftKey}`);
    draft.onsuccess = () => { result.draft = (draft.result as WritingDraft<CharacterRelationFactDraftV1> | undefined)?.value ?? null; };
    const commands = store.index("scope").getAll(`${novelId}:character-relation-facts:operations`);
    commands.onsuccess = () => {
      result.operation = (commands.result as CharacterRelationFactCommandEntryV1[]).find((row) => row.draft_key === link.draftKey)?.value ?? null;
    };
  }
  return result;
}

/** 功能：恢复 D 原稿关联的人工准备或确认，不转换新旧回执。Args: 小说和原稿关联。Returns: 同次读取中的三类原数据。 */
export async function readChapterRelationFactHandoff(novelId: string, link: NonNullable<ChapterRecordDraft["relationFact"]>): Promise<ChapterRelationFactHandoffRead> {
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readonly");
    const result = readRelationFactEntries(tx.objectStore("business_drafts"), novelId, link);
    tx.oncomplete = () => resolve(result);
    tx.onerror = tx.onabort = () => reject(tx.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：作者明确采用后，同事务保留原建议并建立人工事实准备。Args: 小说、原稿范围和已读原稿。Returns: 已持久关联及准备稿；失败不改两边。 */
export async function handoffChapterRelationFact(novelId: string, scope: string, originalDraft: ChapterRecordDraft): Promise<{ draft: ChapterRecordDraft; preparation: CharacterRelationFactPreparationV1 }> {
  const original = structuredClone(originalDraft), check = original.relationCheck, result = check?.result, target = original.relationTarget;
  const checked = result?.check_target, suggestion = result?.candidate.suggestion, source = check?.source;
  if (scope !== `${novelId}:chapter:${original.chapterId}:chapter-records` || original.mode !== "character-relation-state" || original.relationFact
    || !target || !source || !checked || !suggestion || !["done", "adopted", "rejected"].includes(check!.status)
    || original.chapterId !== source.chapter_id || result!.basis.flow_snapshot.business_input.novel_id !== novelId
    || !sameSource(result!.basis.flow_snapshot.business_input.source, source) || result!.basis.flow_snapshot.business_input.relation_id !== target.relation_id
    || result!.basis.flow_snapshot.business_input.expected_version !== target.version || checked.relation_id !== target.relation_id
    || checked.expected_version !== target.version || checked.source_character_id !== target.source_character_id || checked.target_character_id !== target.target_character_id
    || !checked.entity_id || (target.entity_id && target.entity_id !== checked.entity_id)
    || !matchesCheckedFacts(result!, source) || result!.schema_version === 2 && original.relationCheckVersion !== 2
    || check!.target.entity_id && check!.target.entity_id !== checked.entity_id
    || check!.target.relation_id !== target.relation_id || check!.target.version !== target.version
    || check!.target.source_character_id !== target.source_character_id || check!.target.target_character_id !== target.target_character_id) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
  if (original.command && (original.command.saved || original.command.unknown !== false)) throw new Error("CHAPTER_RECORD_ORIGINAL_CONFIRMATION_REQUIRED");
  const preparation: CharacterRelationFactPreparationV1 = {
    schema_id: "character_relation.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1, novel_id: novelId,
    kind: "existing", relation_id: target.relation_id, target: { entity_id: checked.entity_id, relation_id: target.relation_id, expected_version: target.version },
    origin: { scope, draftKey: original.key },
    setup: { operation: "change", position: { version: 1, intent: "chapter_after", target_type: "chapter", target_id: source.chapter_id }, note: "",
      evidence: { ...source, start: suggestion.start, quote: suggestion.quote }, record: null, resolves: {}, after: { current_state: suggestion.current_state } },
  };
  const linked: ChapterRecordDraft = { ...original, revision: original.revision + 1, relationFact: { preparationKey: preparation.key } };
  const db = await openTaskFlowDatabase();
  try { return await new Promise((resolve, reject) => {
    const tx = db.transaction("business_drafts", "readwrite"), store = tx.objectStore("business_drafts");
    let conflict = false;
    const abort = () => { conflict = true; tx.abort(); };
    const request = store.get(`${scope}:${original.key}`);
    request.onsuccess = () => {
      const row = request.result as WritingDraft<ChapterRecordDraft> | undefined, current = row?.value;
      if (!current || current.revision !== original.revision || JSON.stringify(current) !== JSON.stringify(original) || current.relationFact) { abort(); return; }
      const save = () => {
        const preparationScope = `${novelId}:character-relation-fact-preparations`;
        store.add({ key: `${preparationScope}:${preparation.key}`, scope: preparationScope, base_version: 0, value: preparation, updated_at: Date.now() } satisfies WritingDraft<CharacterRelationFactPreparationV1>);
        store.put({ ...row!, value: linked, updated_at: Date.now() });
      };
      const checkCommand = () => {
        if (!current.command) { save(); return; }
        const operation = store.get(`${scope}:operation:${current.command.key}`);
        operation.onsuccess = () => {
          const stored = operation.result as WritingDraft<ChapterRecordOperation> | undefined;
          if (current.command!.unknown !== false || current.command!.saved || !stored || stored.scope !== `${scope}:operations` || stored.value.saved || !sameOperation(stored.value, current.command!)) { abort(); return; }
          // 旧 D 恢复可能复制稿 ID；另一份同请求仍未知时，不能只凭本稿的迟到拒绝升级。
          const copies = store.index("scope").getAll(scope);
          copies.onsuccess = () => {
            if ((copies.result as WritingDraft<ChapterRecordDraft>[]).some(({ value }) => value.command && sameOperation(value.command, current.command!) && (value.command.unknown !== false || value.command.saved))) { abort(); return; }
            save();
          };
        };
      };
      if (current.review) {
        const review = store.get(`${current.review.scope}:${current.review.reviewId}`);
        review.onsuccess = () => {
          const stored = review.result as WritingDraft<ChapterCheckReview> | undefined;
          if (!stored || stored.scope !== current.review!.scope || !matchesReview(scope, current, stored.value)
            || stored.value.members[reviewMemberId(current.review!)!].operationKey !== (current.command?.key ?? null)) { abort(); return; }
          checkCommand();
        };
      } else checkCommand();
    };
    tx.oncomplete = () => resolve({ draft: linked, preparation });
    tx.onerror = tx.onabort = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : tx.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
  }); } finally { db.close(); }
}

/** 功能：定位新成员或旧两成员稿。Args: link 原关联字段。Returns: 固定成员键；旧关联保持原样，不在读取时补字段。 */
function reviewMemberId(link: NonNullable<ChapterRecordDraft["review"]>): string | null {
  return link.memberId ?? (link.kind === "psychological" || link.kind === "itemOwner" ? link.kind : null);
}

/** 功能：比较不可变章修订。Args: left、right 两份来源。Returns: 四个字段是否相同。 */
function sameSource(left: ChapterPsychologicalCheckSourceV1, right: ChapterPsychologicalCheckSourceV1): boolean {
  return left.chapter_id === right.chapter_id && left.revision_id === right.revision_id && left.version === right.version && left.content_hash === right.content_hash;
}

/** 功能：比较同一个冻结请求。Args: left、right 两份请求。Returns: 动作、目标、键和完整载荷是否相同。 */
function sameOperation(left: ChapterRecordOperation, right: ChapterRecordOperation): boolean {
  return left.key === right.key && left.action === right.action && left.target === right.target && JSON.stringify(left.body) === JSON.stringify(right.body);
}

/** 功能：新版建议只接受原章章前的已知值或明确未知，旧稿继续用旧合同。Args: result 原检查结果；source 原章修订。Returns: 事实位置和值语义是否一致。 */
function matchesCheckedFacts(result: ChapterCharacterRelationCheckResult, source: ChapterPsychologicalCheckSourceV1): boolean {
  if (result.schema_version !== 2) return result.schema_version === 1;
  if (!("checked_facts" in result)) return false;
  const facts = result.checked_facts;
  return facts.position.version === 1 && facts.position.intent === "chapter_before" && facts.position.target_type === "chapter" && facts.position.target_id === source.chapter_id
    && (Object.hasOwn(facts.values, "current_state") !== Object.hasOwn(facts.unknown, "current_state"));
}

/** 功能：核对关联稿的固定来源、目标和当前位置。Args: scope 稿件范围；draft 待写稿；review 已存关联。Returns: 是否仍属于原成员。 */
function matchesReview(scope: string, draft: ChapterRecordDraft, review: ChapterCheckReview): boolean {
  const link = draft.review;
  if (!link || link.reviewId !== review.reviewId || !sameSource(link.source, review.source) || draft.chapterId !== review.source.chapter_id) return false;
  const memberId = reviewMemberId(link);
  const member = memberId ? review.members[memberId] : undefined;
  if (!member || member.kind !== link.kind || member.draftScope !== scope || member.draftKey !== draft.key) return false;
  if (draft.evidence && !sameSource(draft.evidence, review.source)) return false;
  const body = draft.command?.body as Record<string, unknown> | undefined;
  if (body && (!body.evidence || !sameSource(body.evidence as ChapterRecordEvidenceV1, review.source))) return false;
  if (member.kind === "psychological") {
    const target = draft.targetState;
    if (draft.mode !== "psychological-state" || !target || target.state_id !== member.target.state_id || target.character_id !== member.target.character_id || target.volume_id !== member.target.volume_id) return false;
    if (draft.command && (draft.command.action !== "patch-psychological-state" || draft.command.target !== target.state_id || body!.state_id !== target.state_id || body!.expected_version !== target.version)) return false;
    if (draft.check) {
      const check = draft.check;
      if (!sameSource(check.source, review.source) || check.target.state_id !== target.state_id || check.target.character_id !== target.character_id || check.target.volume_id !== target.volume_id || check.target.version !== target.version) return false;
      if (check.result) {
        const input = check.result.basis.flow_snapshot.business_input;
        const checked = check.result.check_target;
        if (!sameSource(input.source, review.source) || input.state_id !== target.state_id || input.expected_version !== target.version || checked.state_id !== target.state_id || checked.character_id !== target.character_id || checked.volume_id !== target.volume_id || checked.expected_version !== target.version) return false;
      }
    }
  } else if (member.kind === "itemOwner") {
    const target = draft.itemOwner;
    if (draft.mode !== "item-owner" || !target || target.item_id !== member.target.item_id || target.from_character_id !== member.target.from_character_id || target.to_character_id !== member.target.to_character_id) return false;
    if (draft.command && (draft.command.action !== "confirm-item-owner" || draft.command.target !== target.item_id || body!.item_id !== target.item_id || body!.expected_version !== target.version || body!.from_character_id !== target.from_character_id || body!.to_character_id !== target.to_character_id)) return false;
    if (draft.itemOwnerCheck) {
      const check = draft.itemOwnerCheck;
      if (!sameSource(check.source, review.source) || check.target.item_id !== target.item_id || check.target.from_character_id !== target.from_character_id || check.target.to_character_id !== target.to_character_id || check.target.version !== target.version) return false;
      if (check.result) {
        const input = check.result.basis.flow_snapshot.business_input;
        if (!sameSource(input.source, review.source) || input.item_id !== target.item_id || input.expected_version !== target.version || input.from_character_id !== target.from_character_id || input.to_character_id !== target.to_character_id) return false;
      }
    }
  } else {
    const target = draft.relationTarget;
    if (draft.mode !== "character-relation-state" || !target || target.relation_id !== member.target.relation_id || target.source_character_id !== member.target.source_character_id || target.target_character_id !== member.target.target_character_id || member.target.entity_id && member.target.entity_id !== target.entity_id) return false;
    if (draft.command && (draft.command.action !== "confirm-character-relation-state" || draft.command.target !== target.relation_id || body!.relation_id !== target.relation_id || body!.expected_version !== target.version)) return false;
    if (draft.relationCheck) {
      const check = draft.relationCheck;
      if (!sameSource(check.source, review.source) || check.target.relation_id !== target.relation_id || check.target.source_character_id !== target.source_character_id || check.target.target_character_id !== target.target_character_id || check.target.version !== target.version || (draft.relationCheckVersion !== 2 && check.target.current_state !== target.current_state) || check.target.entity_id !== target.entity_id) return false;
      if (check.result) {
        const input = check.result.basis.flow_snapshot.business_input;
        const checked = check.result.check_target;
        if (!sameSource(input.source, review.source) || input.relation_id !== target.relation_id || input.expected_version !== target.version || !checked.entity_id || checked.relation_id !== target.relation_id || checked.source_character_id !== target.source_character_id || checked.target_character_id !== target.target_character_id || checked.expected_version !== target.version) return false;
        if (!matchesCheckedFacts(check.result, review.source) || check.target.entity_id && check.target.entity_id !== checked.entity_id || member.target.entity_id && member.target.entity_id !== checked.entity_id) return false;
        if (check.result.schema_version === 2 ? draft.relationCheckVersion !== 2 || Boolean(target.entity_id && checked.entity_id !== target.entity_id) : !("current_state" in checked) || checked.current_state !== target.current_state) return false;
      }
    }
  }
  return true;
}

/** 功能：读取本书章后记录的独立草稿，优先使用已确认的请求回执。Args: scope 本书范围。Returns: 按时间排列的草稿。 */
export async function readChapterRecordDrafts(scope: string): Promise<ChapterRecordDraft[]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const store = transaction.objectStore("business_drafts");
      const drafts = store.index("scope").getAll(scope);
      const operations = store.index("scope").getAll(`${scope}:operations`);
      transaction.oncomplete = () => {
        const rows = drafts.result as WritingDraft<ChapterRecordDraft>[];
        const receipts = new Map((operations.result as WritingDraft<ChapterRecordOperation>[]).map((row) => [row.value.key, row.value.saved]));
        resolve(rows.sort((a, b) => a.updated_at - b.updated_at).map(({ value: draft }) => {
          const saved = draft.command && receipts.get(draft.command.key);
          return saved ? { ...draft, command: { ...draft.command!, saved, unknown: false } } : draft;
        }));
      };
      transaction.onerror = () => reject(transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
      transaction.onabort = () => reject(transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：按本地版本保存或清理自己的稿件，提交事务后才允许发送网络请求。Args: scope 本书范围；draft 独立稿件；expectedRevision 已读版本，新稿为 null；remove 是否清理。Returns: 已确认的请求回执，未确认时为空。 */
export async function writeChapterRecordDraft(scope: string, draft: ChapterRecordDraft, expectedRevision: number | null, remove = false): Promise<ChapterRecordOperation["saved"]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const key = `${scope}:${draft.key}`;
      let conflict = false;
      let savedReceipt: ChapterRecordOperation["saved"];
      const current = store.get(key);
      current.onsuccess = () => {
        const previous = current.result as WritingDraft<ChapterRecordDraft> | undefined;
        // 已交给人工事实表单的原稿只供查看；旧标签页不能覆盖或删掉关联。
        if (previous?.value.relationFact || draft.relationFact || previous?.value.itemFact || draft.itemFact) { conflict = true; transaction.abort(); return; }
        if ((previous?.value.revision ?? null) !== expectedRevision) { conflict = true; transaction.abort(); return; }
        if (!remove && previous && draft.revision <= previous.value.revision && JSON.stringify(draft) !== JSON.stringify(previous.value)) { conflict = true; transaction.abort(); return; }
        // 以已存稿为准，调用方删掉关联字段也不能绕过成员核对。
        if (JSON.stringify(previous?.value.review) !== JSON.stringify(draft.review)) { conflict = true; transaction.abort(); return; }
        const save = (reviewRow?: WritingDraft<ChapterCheckReview>) => {
          const memberId = draft.review && reviewMemberId(draft.review);
          const member = reviewRow && memberId ? reviewRow.value.members[memberId] : undefined;
          if (reviewRow && (!matchesReview(scope, draft, reviewRow.value) || member!.operationKey !== (previous!.value.command?.key ?? null) || (previous!.value.targetState?.version !== draft.targetState?.version) || (previous!.value.itemOwner?.version !== draft.itemOwner?.version) || (previous!.value.relationTarget?.version !== draft.relationTarget?.version))) { conflict = true; transaction.abort(); return; }
          if (member?.operationKey && member.operationKey !== draft.command?.key) { conflict = true; transaction.abort(); return; }
          if (remove && !reviewRow) { store.delete(key); return; }
          if (draft.command) {
            const operationKey = `${scope}:operation:${draft.command.key}`;
            const operation = store.get(operationKey);
            operation.onsuccess = () => {
              const command = draft.command!;
              const frozen = { action: command.action, target: command.target, body: command.body, key: command.key };
              const stored = operation.result as WritingDraft<ChapterRecordOperation> | undefined;
              if (stored && (stored.scope !== `${scope}:operations` || !sameOperation(stored.value, command))) { conflict = true; transaction.abort(); return; }
              if (member?.operationKey && !stored) { conflict = true; transaction.abort(); return; }
              if (remove) {
                if (!stored?.value.saved) { conflict = true; transaction.abort(); return; }
                store.delete(key); return;
              }
              if (!stored) store.add({ key: operationKey, scope: `${scope}:operations`, base_version: 0, value: { ...frozen, ...(command.saved ? { saved: command.saved } : {}) }, updated_at: Date.now() } satisfies WritingDraft<ChapterRecordOperation>);
              else if (command.saved && !stored.value.saved) store.put({ ...stored, value: { ...stored.value, saved: command.saved } });
              savedReceipt = stored?.value.saved ?? command.saved;
              if (reviewRow && member!.operationKey === null) {
                store.put({ ...reviewRow, value: { ...reviewRow.value, members: { ...reviewRow.value.members, [memberId!]: { ...member, operationKey: command.key } } }, updated_at: Date.now() });
              }
            };
          } else if (remove) { conflict = true; transaction.abort(); return; }
          if (!remove) store.put({ key, scope, base_version: draft.relationTarget?.version ?? draft.itemOwner?.version ?? draft.targetState?.version ?? draft.expectedReportVersion, value: draft, updated_at: Date.now() } satisfies WritingDraft<ChapterRecordDraft>);
        };
        if (previous?.value.review) {
          const link = previous.value.review;
          const review = store.get(`${link.scope}:${link.reviewId}`);
          review.onsuccess = () => {
            const row = review.result as WritingDraft<ChapterCheckReview> | undefined;
            if (!row || row.scope !== link.scope) { conflict = true; transaction.abort(); return; }
            save(row);
          };
        } else save();
      };
      transaction.oncomplete = () => resolve(savedReceipt);
      transaction.onerror = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
      transaction.onabort = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：独立补存已登记请求的成功回执，旧标签页失去稿件后仍可完成。Args: scope 原范围；command 原冻结请求及成功结果。Returns: 首次成功回执。 */
export async function writeChapterRecordReceipt(scope: string, command: ChapterRecordOperation): Promise<ChapterRecordOperation["saved"]> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      const request = store.get(`${scope}:operation:${command.key}`);
      let conflict = false;
      let saved: ChapterRecordOperation["saved"];
      request.onsuccess = () => {
        const row = request.result as WritingDraft<ChapterRecordOperation> | undefined;
        if (!row || row.scope !== `${scope}:operations` || !sameOperation(row.value, command) || !command.saved) { conflict = true; transaction.abort(); return; }
        saved = row.value.saved ?? command.saved;
        if (!row.value.saved) store.put({ ...row, value: { ...row.value, saved }, updated_at: Date.now() });
      };
      transaction.oncomplete = () => resolve(saved);
      transaction.onerror = transaction.onabort = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：原子建立同章修订的两至五个不同目标及初始稿。Args: novelId 小说；source 固定章修订；drafts 作者选定的各项稿。Returns: 已持久的关联和各稿，展示前须用其 revision 初始化保存记录。 */
export async function createChapterCheckReview(novelId: string, source: ChapterPsychologicalCheckSourceV1, drafts: ChapterRecordDraft[]): Promise<ChapterCheckReviewRead> {
  if (drafts.length < 2 || drafts.length > 5) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
  const reviewId = crypto.randomUUID();
  const scope = `${novelId}:chapter:${source.chapter_id}:chapter-check-reviews`;
  const chapterScope = `${novelId}:chapter:${source.chapter_id}:chapter-records`;
  const review: ChapterCheckReview = { reviewId, source, members: {} };
  const result: ChapterCheckReviewRead = { review, members: {} };
  const targets = new Set<string>();
  for (const draft of drafts) {
    if (draft.command || draft.review) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
    const memberId = crypto.randomUUID();
    const position = { draftScope: chapterScope, draftKey: draft.key, operationKey: null };
    let member: ChapterCheckReviewMember;
    let targetId: string;
    if (draft.mode === "psychological-state" && draft.targetState) {
      const target = draft.targetState;
      targetId = target.state_id;
      member = { ...position, kind: "psychological", target: { state_id: target.state_id, character_id: target.character_id, volume_id: target.volume_id, name: target.name } };
    } else if (draft.mode === "item-owner" && draft.itemOwner) {
      const target = draft.itemOwner;
      if (!target.from_character_id || !target.to_character_id || target.from_character_id === target.to_character_id) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
      targetId = target.item_id;
      member = { ...position, draftScope: `${novelId}:item:${target.item_id}:chapter-records`, kind: "itemOwner", target: { item_id: target.item_id, name: target.name, from_character_id: target.from_character_id, from_name: target.from_name, to_character_id: target.to_character_id, to_name: target.to_name } };
    } else if (draft.mode === "character-relation-state" && draft.relationTarget) {
      const target = draft.relationTarget;
      targetId = target.relation_id;
      member = { ...position, kind: "characterRelation", target: { relation_id: target.relation_id, source_character_id: target.source_character_id, target_character_id: target.target_character_id, source_character_name: target.source_character_name, target_character_name: target.target_character_name, relation_type: target.relation_type, ...(target.entity_id ? { entity_id: target.entity_id } : {}) } };
    } else throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
    const identity = `${member.kind}:${targetId}`;
    if (targets.has(identity)) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
    targets.add(identity);
    const linked = { ...draft, revision: 1, review: { scope, reviewId, memberId, kind: member.kind, source } };
    review.members[memberId] = member;
    if (!matchesReview(member.draftScope, linked, review)) throw new Error("CHAPTER_RECORD_LOCAL_CONFLICT");
    result.members[memberId] = { draft: linked, operation: null };
  }
  const db = await openTaskFlowDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      store.add({ key: `${scope}:${reviewId}`, scope, base_version: 0, value: review, updated_at: Date.now() } satisfies WritingDraft<ChapterCheckReview>);
      for (const [memberId, member] of Object.entries(review.members)) {
        const draft = result.members[memberId].draft!;
        store.add({ key: `${member.draftScope}:${draft.key}`, scope: member.draftScope, base_version: draft.relationTarget?.version ?? draft.itemOwner?.version ?? draft.targetState!.version, value: draft, updated_at: Date.now() } satisfies WritingDraft<ChapterRecordDraft>);
      }
      transaction.oncomplete = () => resolve();
      transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
    return result;
  } finally { db.close(); }
}

/** 功能：在一个读取事务中取得关联及各成员当前稿和回执。Args: novelId 小说；chapterId 章节。Returns: 按更新时间排列的关联，不复制确认状态。 */
export async function readChapterCheckReviews(novelId: string, chapterId: string): Promise<ChapterCheckReviewRead[]> {
  const scope = `${novelId}:chapter:${chapterId}:chapter-check-reviews`;
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readonly");
      const store = transaction.objectStore("business_drafts");
      const request = store.index("scope").getAll(scope);
      let rows: ChapterCheckReviewRead[] = [];
      request.onsuccess = () => {
        rows = (request.result as WritingDraft<ChapterCheckReview>[]).sort((a, b) => a.updated_at - b.updated_at).map(({ value: review }) => {
          const row: ChapterCheckReviewRead = { review, members: {} };
          for (const [memberId, member] of Object.entries(review.members)) {
            const entry: ChapterCheckReviewRead["members"][string] = { draft: null, operation: null };
            row.members[memberId] = entry;
            const draft = store.get(`${member.draftScope}:${member.draftKey}`);
            draft.onsuccess = () => {
              entry.draft = (draft.result as WritingDraft<ChapterRecordDraft> | undefined)?.value ?? null;
              if (entry.draft?.relationFact) entry.relationFact = readRelationFactEntries(store, novelId, entry.draft.relationFact);
              if (entry.draft?.itemFact) entry.itemFact = readItemFactEntries(store, novelId, entry.draft.itemFact);
            };
            if (member.operationKey) {
              const operation = store.get(`${member.draftScope}:operation:${member.operationKey}`);
              operation.onsuccess = () => { entry.operation = (operation.result as WritingDraft<ChapterRecordOperation> | undefined)?.value ?? null; };
            }
          }
          return row;
        });
      };
      transaction.oncomplete = () => {
        for (const row of rows) for (const entry of Object.values(row.members)) {
          if (entry.draft?.command && entry.operation?.saved) entry.draft = { ...entry.draft, command: { ...entry.draft.command, saved: entry.operation.saved, unknown: false } };
        }
        resolve(rows);
      };
      transaction.onerror = transaction.onabort = () => reject(transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：显式继续原关联稿，以最新稿 revision 加一取得编辑权。Args: scope 原范围；draft 用于定位的稿件。Returns: 已持久的同键最新稿，须用其 revision 初始化保存记录。 */
export async function claimChapterCheckReviewDraft(scope: string, draft: ChapterRecordDraft): Promise<ChapterRecordDraft> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      let conflict = false;
      let claimed: ChapterRecordDraft;
      const request = store.get(`${scope}:${draft.key}`);
      request.onsuccess = () => {
        const row = request.result as WritingDraft<ChapterRecordDraft> | undefined;
        const current = row?.value;
        if (!current?.review || JSON.stringify(current.review) !== JSON.stringify(draft.review)) { conflict = true; transaction.abort(); return; }
        if (current.relationFact || current.itemFact) { claimed = current; return; }
        const reviewRequest = store.get(`${current.review.scope}:${current.review.reviewId}`);
        reviewRequest.onsuccess = () => {
          const reviewRow = reviewRequest.result as WritingDraft<ChapterCheckReview> | undefined;
          if (!reviewRow || reviewRow.scope !== current.review!.scope || !matchesReview(scope, current, reviewRow.value) || !matchesReview(scope, draft, reviewRow.value)) { conflict = true; transaction.abort(); return; }
          const member = reviewRow.value.members[reviewMemberId(current.review!)!];
          if (member.operationKey !== (current.command?.key ?? null)) { conflict = true; transaction.abort(); return; }
          claimed = { ...current, revision: current.revision + 1,
            ...(current.command ? { command: { ...current.command, readbackDone: false } } : {}),
            ...(current.check?.status === "running" ? { check: { ...current.check, status: "interrupted" } } : {}),
            ...(current.itemOwnerCheck?.status === "running" ? { itemOwnerCheck: { ...current.itemOwnerCheck, status: "interrupted" } } : {}),
            ...(current.relationCheck?.status === "running" ? { relationCheck: { ...current.relationCheck, status: "interrupted" } } : {}),
          };
          if (current.command) {
            const operation = store.get(`${scope}:operation:${current.command.key}`);
            operation.onsuccess = () => {
              const stored = operation.result as WritingDraft<ChapterRecordOperation> | undefined;
              if (!stored || stored.scope !== `${scope}:operations` || !sameOperation(stored.value, current.command!)) { conflict = true; transaction.abort(); return; }
              if (stored.value.saved) claimed.command = { ...claimed.command!, saved: stored.value.saved, unknown: false };
              store.put({ ...row!, value: claimed, updated_at: Date.now() });
            };
          } else store.put({ ...row!, value: claimed, updated_at: Date.now() });
        };
      };
      transaction.oncomplete = () => resolve(claimed);
      transaction.onerror = transaction.onabort = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}

/** 功能：作者复核未提交或明确拒绝的稿后，原子替换该成员。Args: scope 原范围；oldDraft 已读原稿；newDraft 复核后的新稿。Returns: 已持久新稿，其他成员保留事务内最新值。 */
export async function reviseChapterCheckReviewDraft(scope: string, oldDraft: ChapterRecordDraft, newDraft: ChapterRecordDraft): Promise<ChapterRecordDraft> {
  const db = await openTaskFlowDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction("business_drafts", "readwrite");
      const store = transaction.objectStore("business_drafts");
      let conflict = false;
      let replacement: ChapterRecordDraft;
      const request = store.get(`${scope}:${oldDraft.key}`);
      request.onsuccess = () => {
        const row = request.result as WritingDraft<ChapterRecordDraft> | undefined;
        const current = row?.value;
        if (!current?.review || current.relationFact || newDraft.relationFact || current.itemFact || newDraft.itemFact || current.revision !== oldDraft.revision || JSON.stringify(current.review) !== JSON.stringify(oldDraft.review) || (newDraft.review && JSON.stringify(newDraft.review) !== JSON.stringify(current.review)) || newDraft.command || newDraft.key === oldDraft.key) { conflict = true; transaction.abort(); return; }
        // 没有提交过的稿可以复核新版本；已冻结的稿必须双方都明确拒绝，不能借换稿丢掉未知或成功。
        if (current.command
          ? !oldDraft.command || current.command.unknown !== false || oldDraft.command.unknown !== false || current.command.saved || oldDraft.command.saved || JSON.stringify(current.command) !== JSON.stringify(oldDraft.command)
          : oldDraft.command) { conflict = true; transaction.abort(); return; }
        const reviewRequest = store.get(`${current.review.scope}:${current.review.reviewId}`);
        reviewRequest.onsuccess = () => {
          const reviewRow = reviewRequest.result as WritingDraft<ChapterCheckReview> | undefined;
          if (!reviewRow || reviewRow.scope !== current.review!.scope || !matchesReview(scope, current, reviewRow.value) || !matchesReview(scope, oldDraft, reviewRow.value)) { conflict = true; transaction.abort(); return; }
          const memberId = reviewMemberId(current.review!)!;
          const member = reviewRow.value.members[memberId];
          if (member.operationKey !== (current.command?.key ?? null)) { conflict = true; transaction.abort(); return; }
          const replace = () => {
            replacement = { ...newDraft, revision: 1, review: current.review };
            const review: ChapterCheckReview = { ...reviewRow.value, members: { ...reviewRow.value.members, [memberId]: { ...member, draftKey: replacement.key, operationKey: null } } };
            if (!matchesReview(scope, replacement, review)) { conflict = true; transaction.abort(); return; }
            store.add({ key: `${scope}:${replacement.key}`, scope, base_version: replacement.relationTarget?.version ?? replacement.itemOwner?.version ?? replacement.targetState!.version, value: replacement, updated_at: Date.now() } satisfies WritingDraft<ChapterRecordDraft>);
            store.put({ ...reviewRow, value: review, updated_at: Date.now() });
            store.delete(`${scope}:${current.key}`);
          };
          if (!current.command) { replace(); return; }
          const operation = store.get(`${scope}:operation:${current.command.key}`);
          operation.onsuccess = () => {
            const stored = operation.result as WritingDraft<ChapterRecordOperation> | undefined;
            if (!stored || stored.scope !== `${scope}:operations` || stored.value.saved || !sameOperation(stored.value, current.command!)) { conflict = true; transaction.abort(); return; }
            replace();
          };
        };
      };
      transaction.oncomplete = () => resolve(replacement);
      transaction.onerror = transaction.onabort = () => reject(conflict ? new Error("CHAPTER_RECORD_LOCAL_CONFLICT") : transaction.error ?? new Error("CHAPTER_RECORD_LOCAL_FAILED"));
    });
  } finally { db.close(); }
}
