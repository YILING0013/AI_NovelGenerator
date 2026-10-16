import type { ReasoningOptions } from "@/types/generation";
import { REASONING_FIELDS, hasValidReasoningOptions } from "@/types/generation";
import { hasCandidateFlow } from "@/lib/aiCandidate";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1, CandidateSourceRefV1 } from "@/lib/aiCandidate";
import { isBusinessId, isObjectIdString } from "@/types/contracts";

/** 正式物品的生命周期状态。 */
export type ItemLifecycleStatus = "available" | "held" | "lost" | "destroyed" | "consumed";

/** 人工创建和编辑共用的物品业务字段。 */
export interface ItemFieldsV1 {
  name: string;
  aliases: string[];
  item_type: string;
  description: string;
  appearance: string;
  origin: string;
  abilities: string[];
  limitations: string[];
  costs: string[];
  owner_character_id: string | null;
  controlling_faction_id: string | null;
  current_location_id: string | null;
  lifecycle_status: ItemLifecycleStatus;
  story_function: string;
  tags: string[];
}

/** 人工创建正式物品的严格请求。 */
export type ItemCreateV1 = ItemFieldsV1;

/** 正式物品普通编辑请求；生命周期变化只走专用转换接口。 */
export type ItemUpdateV1 = Partial<Omit<ItemFieldsV1, "lifecycle_status">> & {
  expected_version: number;
};

/** 正式物品公开响应。 */
export interface ItemReadV1 extends ItemFieldsV1 {
  item_id: string;
  novel_id: string;
  order_index: number;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 完整活动集合重排中的单条 CAS 命令。 */
export interface ItemReorderItemV1 {
  item_id: string;
  order_index: number;
  expected_version: number;
}

/** 物品完整重排请求。 */
export interface ItemReorderRequestV1 {
  items: ItemReorderItemV1[];
}

/** 物品恢复和状态转换共用的 CAS 请求。 */
export interface ItemVersionCommandV1 {
  expected_version: number;
}

/** 永久删除前展示的受保护引用影响。 */
export interface ItemDeleteImpactV1 {
  item_id: string;
  arcs: number;
  chapters: number;
  scenes: number;
  foreshadowings: number;
  total_protected_references: number;
  has_protected_references: boolean;
}

/** 物品永久删除成功响应。 */
export interface ItemHardDeleteResponseV1 {
  message: string;
  item_id: string;
  impact: ItemDeleteImpactV1;
}

/** 物品 AI 生成请求中会写入 basis 的业务输入。 */
export interface ItemsGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  item_count: number | null;
  allow_incremental: boolean;
  user_guidance: string;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
}

/** 物品 AI 普通与流式入口共用的请求。 */
export interface ItemsGenerateRequestV1 extends ReasoningOptions {
  item_count: number | null;
  allow_incremental: boolean;
  user_guidance: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
  use_stream: boolean;
}

/** AI 返回、页面可编辑但还没有正式 ID 的物品。 */
export interface ItemCandidateV1 extends ItemFieldsV1 {
  candidate_ref: string;
}

/** Provider 必须返回的物品候选根对象。 */
export interface ItemsResultV1 {
  items: ItemCandidateV1[];
}

/** 服务端锁定的物品候选生成依据。 */
export interface ItemsBasisV1 extends CandidateBasisV1 {
  novel_id: string;
  generation_input: ItemsGenerationInputV1;
}

/** 普通响应与 SSE done.result 共用的候选信封。 */
export type ItemsCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<ItemsResultV1> & {
  basis: ItemsBasisV1;
};

/** 把当前候选整批保存为正式物品的请求。 */
export interface ItemBulkGeneratedRequestV1 {
  candidates: ItemCandidateV1[];
  basis: ItemsBasisV1;
  expected_versions: Record<string, number>;
}

/** 物品候选整批保存成功响应。 */
export interface ItemBulkGeneratedResponseV1 {
  candidate_ref_map: Record<string, string>;
  items: ItemReadV1[];
}

const ITEM_KEYS = [
  "item_id",
  "novel_id",
  "name",
  "aliases",
  "item_type",
  "description",
  "appearance",
  "origin",
  "abilities",
  "limitations",
  "costs",
  "owner_character_id",
  "controlling_faction_id",
  "current_location_id",
  "lifecycle_status",
  "story_function",
  "tags",
  "order_index",
  "version",
  "is_deleted",
  "deleted_at",
  "created_at",
  "updated_at",
] as const;

const ITEM_STATUSES: readonly ItemLifecycleStatus[] = [
  "available",
  "held",
  "lost",
  "destroyed",
  "consumed",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOnlyKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  optionalKeys: readonly string[] = [],
): boolean {
  const expected = new Set(keys);
  const actual = Object.keys(value).filter((key) => !optionalKeys.includes(key));
  return actual.length === expected.size && actual.every((key) => expected.has(key));
}

function isStringArray(value: unknown, maximum: number, itemMaximum?: number): value is string[] {
  return Array.isArray(value)
    && value.length <= maximum
    && value.every((item) => (
      typeof item === "string"
      && item.trim().length > 0
      && (itemMaximum === undefined || item.length <= itemMaximum)
    ));
}

function isNullableNumberInRange(value: unknown, minimum: number, maximum: number): boolean {
  return value === null
    || (typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum);
}

function isItemsGenerationInput(value: unknown, novelId: string): value is ItemsGenerationInputV1 {
  return isRecord(value)
    && hasOnlyKeys(value, [
      "novel_id",
      "item_count",
      "allow_incremental",
      "user_guidance",
      ...REASONING_FIELDS.filter((key) => key in value),
      "temperature",
      "top_p",
      "max_tokens",
      "presence_penalty",
      "frequency_penalty",
      "system_prompt",
    ])
    && value.novel_id === novelId
    && (value.item_count === null || (Number.isInteger(value.item_count)
    && Number(value.item_count) >= 1
    && Number(value.item_count) <= 20))
    && typeof value.allow_incremental === "boolean"
    && typeof value.user_guidance === "string"
    && value.user_guidance.length <= 2000
    && hasValidReasoningOptions(value)
    && isNullableNumberInRange(value.temperature, 0, 2)
    && isNullableNumberInRange(value.top_p, 0, 1)
    && (value.max_tokens === null || (Number.isInteger(value.max_tokens) && Number(value.max_tokens) > 0))
    && isNullableNumberInRange(value.presence_penalty, -2, 2)
    && isNullableNumberInRange(value.frequency_penalty, -2, 2)
    && (value.system_prompt === null || (typeof value.system_prompt === "string" && value.system_prompt.length <= 40_000));
}

function isCandidateSourceRef(value: unknown): value is CandidateSourceRefV1 {
  return isRecord(value)
    && hasOnlyKeys(value, ["resource_type", "id", "version"])
    && typeof value.resource_type === "string"
    && /^[a-z][a-z0-9_]{1,63}$/.test(value.resource_type)
    && typeof value.id === "string"
    && value.id.length >= 1
    && value.id.length <= 100
    && Number.isInteger(value.version)
    && Number(value.version) >= 1;
}

function isItemCandidate(value: unknown): value is ItemCandidateV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "candidate_ref",
    "name",
    "aliases",
    "item_type",
    "description",
    "appearance",
    "origin",
    "abilities",
    "limitations",
    "costs",
    "owner_character_id",
    "controlling_faction_id",
    "current_location_id",
    "lifecycle_status",
    "story_function",
    "tags",
  ])) return false;
  const status = value.lifecycle_status;
  return typeof value.candidate_ref === "string"
    && /^item_candidate_[0-9]+$/.test(value.candidate_ref)
    && typeof value.name === "string"
    && value.name.trim().length >= 1
    && value.name.length <= 80
    && isStringArray(value.aliases, 10)
    && typeof value.item_type === "string"
    && value.item_type.trim().length >= 1
    && value.item_type.length <= 40
    && typeof value.description === "string"
    && value.description.trim().length >= 1
    && value.description.length <= 2000
    && typeof value.appearance === "string"
    && value.appearance.length <= 1000
    && typeof value.origin === "string"
    && value.origin.length <= 1000
    && isStringArray(value.abilities, 20, 500)
    && isStringArray(value.limitations, 20, 500)
    && isStringArray(value.costs, 20, 500)
    && (value.owner_character_id === null || isBusinessId("character", value.owner_character_id))
    && (value.controlling_faction_id === null || isBusinessId("faction", value.controlling_faction_id))
    && (value.current_location_id === null || isBusinessId("location", value.current_location_id))
    && typeof status === "string"
    && ITEM_STATUSES.includes(status as ItemLifecycleStatus)
    && !(status === "held" && value.owner_character_id === null && value.controlling_faction_id === null)
    && !((status === "destroyed" || status === "consumed") && (
      value.owner_character_id !== null
      || value.controlling_faction_id !== null
      || value.current_location_id !== null
    ))
    && typeof value.story_function === "string"
    && value.story_function.trim().length >= 1
    && value.story_function.length <= 1000
    && isStringArray(value.tags, 20);
}

/**
 * 严格解析物品 AI 的普通响应或 SSE 完成结果。
 *
 * Args:
 *   value: 待解析的未知 JSON。
 *   novelId: 当前小说 ID。
 *
 * Returns:
 *   完整匹配物品生成契约时返回候选信封，否则返回 null。
 */
export function parseItemsCandidateEnvelopeV1(
  value: unknown,
  novelId: string,
): ItemsCandidateEnvelopeV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "workflow",
    "step",
    "schema_id",
    "schema_version",
    "candidate",
    "basis",
  ])) return null;
  if (
    value.workflow !== "create_items_by_ai"
    || value.step !== "create_items"
    || value.schema_id !== "item.generation.result"
    || value.schema_version !== 1
    || !isRecord(value.candidate)
    || !hasOnlyKeys(value.candidate, ["items"])
    || !Array.isArray(value.candidate.items)
    || value.candidate.items.length < 1
    || value.candidate.items.length > 20
    || !value.candidate.items.every(isItemCandidate)
    || !hasCandidateFlow(value.basis)
    || !hasOnlyKeys(value.basis, [
      "novel_id",
      "workflow",
      "step",
      "schema_id",
      "schema_version",
      "input_fingerprint",
      "source_refs",
      "generation_input",
      "flow_ref",
      "flow_snapshot",
    ])
    || value.basis.novel_id !== novelId
    || value.basis.workflow !== "create_items_by_ai"
    || value.basis.step !== "create_items"
    || value.basis.schema_id !== "item.generation.result"
    || value.basis.schema_version !== 1
    || typeof value.basis.input_fingerprint !== "string"
    || !/^[0-9a-f]{64}$/.test(value.basis.input_fingerprint)
    || !Array.isArray(value.basis.source_refs)
    || value.basis.source_refs.length < 1
    || value.basis.source_refs.length > 2000
    || !value.basis.source_refs.every(isCandidateSourceRef)
    || !isItemsGenerationInput(value.basis.generation_input, novelId)
  ) return null;
  const candidates = value.candidate.items as ItemCandidateV1[];
  const refs = candidates.map((candidate) => candidate.candidate_ref);
  const names = candidates.map((candidate) => candidate.name.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase());
  const sourceKeys = (value.basis.source_refs as CandidateSourceRefV1[])
    .map((source) => `${source.resource_type}:${source.id}`);
  if (
    new Set(refs).size !== refs.length
    || new Set(names).size !== names.length
    || new Set(sourceKeys).size !== sourceKeys.length
    || !(value.basis.source_refs as CandidateSourceRefV1[]).some((source) => source.resource_type === "novel" && source.id === novelId)
  ) return null;
  return value as unknown as ItemsCandidateEnvelopeV1;
}

/**
 * 严格解析物品候选整批保存响应。
 *
 * Args:
 *   value: 批量确认接口返回的未知 JSON。
 *   novelId: 当前小说 ID。
 *   candidateRefs: 本次提交的候选引用。
 *
 * Returns:
 *   每个候选都映射到一条正式物品时返回响应，否则返回 null。
 */
export function parseItemBulkGeneratedResponseV1(
  value: unknown,
  novelId: string,
  candidateRefs: readonly string[],
): ItemBulkGeneratedResponseV1 | null {
  if (
    !isRecord(value)
    || !hasOnlyKeys(value, ["candidate_ref_map", "items"])
    || !isRecord(value.candidate_ref_map)
    || !Array.isArray(value.items)
    || value.items.length !== candidateRefs.length
  ) return null;
  const expectedRefs = new Set(candidateRefs);
  const responseRefs = Object.keys(value.candidate_ref_map);
  const mappedIds = Object.values(value.candidate_ref_map);
  let items: ItemReadV1[];
  try {
    items = value.items.map((item) => parseItemReadV1(item, novelId));
  } catch {
    return null;
  }
  const responseIds = new Set(items.map((item) => item.item_id));
  if (
    expectedRefs.size !== candidateRefs.length
    || responseIds.size !== items.length
    || responseRefs.length !== expectedRefs.size
    || !responseRefs.every((candidateRef) => expectedRefs.has(candidateRef))
    || !mappedIds.every((itemId) => typeof itemId === "string" && isBusinessId("item", itemId) && responseIds.has(itemId))
    || new Set(mappedIds).size !== mappedIds.length
  ) return null;
  return {
    candidate_ref_map: value.candidate_ref_map as Record<string, string>,
    items,
  };
}

/**
 * 严格解析单条正式物品响应。
 *
 * Args:
 *   value: API 返回的未知 JSON 值。
 *   novelId: 可选的当前小说 ObjectId；传入后同时校验小说隔离。
 *
 * Returns:
 *   字段、类型、状态组合、稳定引用和删除审计均符合 V1 契约时返回物品，否则抛出错误。
 */
export function parseItemReadV1(value: unknown, novelId?: string): ItemReadV1 {
  if (!isRecord(value)) throw new Error("Invalid item response");
  const status = value.lifecycle_status;
  if (
    Object.keys(value).length !== ITEM_KEYS.length
    || ITEM_KEYS.some((key) => !(key in value))
    || !isBusinessId("item", value.item_id)
    || !isObjectIdString(value.novel_id)
    || (novelId !== undefined && value.novel_id !== novelId)
    || typeof value.name !== "string"
    || value.name.trim().length < 1
    || value.name.length > 80
    || !isStringArray(value.aliases, 10)
    || typeof value.item_type !== "string"
    || value.item_type.trim().length < 1
    || value.item_type.length > 40
    || typeof value.description !== "string"
    || value.description.trim().length < 1
    || value.description.length > 2000
    || typeof value.appearance !== "string"
    || value.appearance.length > 1000
    || typeof value.origin !== "string"
    || value.origin.length > 1000
    || !isStringArray(value.abilities, 20, 500)
    || !isStringArray(value.limitations, 20, 500)
    || !isStringArray(value.costs, 20, 500)
    || !(value.owner_character_id === null || isBusinessId("character", value.owner_character_id))
    || !(value.controlling_faction_id === null || isBusinessId("faction", value.controlling_faction_id))
    || !(value.current_location_id === null || isBusinessId("location", value.current_location_id))
    || typeof status !== "string"
    || !ITEM_STATUSES.includes(status as ItemLifecycleStatus)
    || (status === "held" && value.owner_character_id === null && value.controlling_faction_id === null)
    || ((status === "destroyed" || status === "consumed") && (
      value.owner_character_id !== null
      || value.controlling_faction_id !== null
      || value.current_location_id !== null
    ))
    || typeof value.story_function !== "string"
    || value.story_function.length > 1000
    || !isStringArray(value.tags, 20)
    || !Number.isInteger(value.order_index)
    || Number(value.order_index) < 1
    || !Number.isInteger(value.version)
    || Number(value.version) < 1
    || typeof value.is_deleted !== "boolean"
    || !(value.deleted_at === null || (typeof value.deleted_at === "string" && value.deleted_at.length > 0))
    || value.is_deleted !== (value.deleted_at !== null)
    || typeof value.created_at !== "string"
    || value.created_at.length < 1
    || typeof value.updated_at !== "string"
    || value.updated_at.length < 1
  ) throw new Error("Invalid item response");
  return value as unknown as ItemReadV1;
}

/**
 * 严格解析正式物品列表响应。
 *
 * Args:
 *   value: API 返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   保持服务端顺序且业务 ID 唯一的物品数组；任一条非法时整体抛错。
 */
export function parseItemListV1(value: unknown, novelId: string): ItemReadV1[] {
  if (!Array.isArray(value)) throw new Error("Invalid item list response");
  const items = value.map((item) => parseItemReadV1(item, novelId));
  if (new Set(items.map((item) => item.item_id)).size !== items.length) {
    throw new Error("Invalid item list response");
  }
  return items;
}

/**
 * 严格解析未筛选的活动物品全量列表及连续顺序。
 *
 * Args:
 *   value: 活动物品列表接口返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   全部未删除、规范名称唯一且 1-based 连续排序的物品数组。
 */
export function parseActiveItemListV1(value: unknown, novelId: string): ItemReadV1[] {
  const items = parseItemListV1(value, novelId);
  const orders = items.map((item) => item.order_index).sort((left, right) => left - right);
  const names = items.map((item) => item.name.normalize("NFKC").trim().replace(/\s+/g, " ").toLowerCase());
  if (
    items.some((item) => item.is_deleted)
    || orders.some((order, index) => order !== index + 1)
    || new Set(names).size !== names.length
  ) throw new Error("Invalid active item list response");
  return items;
}

/**
 * 严格解析物品回收站列表，不把活动集合的顺序连续性套用到已删除记录。
 *
 * Args:
 *   value: 回收站列表接口返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   ID 唯一且全部带删除审计的物品数组。
 */
export function parseTrashItemListV1(value: unknown, novelId: string): ItemReadV1[] {
  const items = parseItemListV1(value, novelId);
  if (items.some((item) => !item.is_deleted)) throw new Error("Invalid trash item list response");
  return items;
}

/**
 * 严格解析物品永久删除影响响应。
 *
 * Args:
 *   value: 删除影响接口返回的未知 JSON 值。
 *   itemId: 当前操作目标物品 ID。
 *
 * Returns:
 *   各正式引用计数及合计完全一致时返回影响对象，否则抛出错误。
 */
export function parseItemDeleteImpactV1(value: unknown, itemId: string): ItemDeleteImpactV1 {
  if (!isRecord(value)) throw new Error("Invalid item delete impact response");
  const keys = [
    "item_id",
    "arcs",
    "chapters",
    "scenes",
    "foreshadowings",
    "total_protected_references",
    "has_protected_references",
  ];
  const counts = [value.arcs, value.chapters, value.scenes, value.foreshadowings];
  if (
    Object.keys(value).length !== keys.length
    || keys.some((key) => !(key in value))
    || value.item_id !== itemId
    || !counts.every((count) => Number.isInteger(count) && Number(count) >= 0)
    || !Number.isInteger(value.total_protected_references)
    || Number(value.total_protected_references) < 0
    || Number(value.total_protected_references) !== counts.reduce<number>((sum, count) => sum + Number(count), 0)
    || typeof value.has_protected_references !== "boolean"
    || value.has_protected_references !== (Number(value.total_protected_references) > 0)
  ) throw new Error("Invalid item delete impact response");
  return value as unknown as ItemDeleteImpactV1;
}

/**
 * 严格解析物品永久删除成功响应。
 *
 * Args:
 *   value: 永久删除接口返回的未知 JSON 值。
 *   itemId: 当前操作目标物品 ID。
 *
 * Returns:
 *   固定消息、目标 ID 与零引用影响均合法时返回响应，否则抛出错误。
 */
export function parseItemHardDeleteResponseV1(value: unknown, itemId: string): ItemHardDeleteResponseV1 {
  if (
    !isRecord(value)
    || Object.keys(value).length !== 3
    || value.message !== "Hard deleted successfully"
    || value.item_id !== itemId
    || !("impact" in value)
  ) throw new Error("Invalid item hard delete response");
  const impact = parseItemDeleteImpactV1(value.impact, itemId);
  if (impact.has_protected_references || impact.total_protected_references !== 0) {
    throw new Error("Invalid item hard delete response");
  }
  return { message: value.message, item_id: itemId, impact };
}
