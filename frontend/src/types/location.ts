import type { ReasoningOptions } from "@/types/generation";
import { REASONING_FIELDS, hasValidReasoningOptions } from "@/types/generation";
import { hasCandidateFlow } from "@/lib/aiCandidate";
import { isBusinessId, isObjectIdString } from "@/types/contracts";
import type { CandidateBasisV1 } from "@/lib/aiCandidate";

/** 正式地点的用户可见状态。 */
export type LocationStatus = "active" | "inactive";

/** 人工编辑与后续 AI 候选共同使用的地点内容字段。 */
export interface LocationContentFieldsV1 {
  name: string;
  aliases: string[];
  location_type: string;
  parent_location_id: string | null;
  description: string;
  environment: string;
  atmosphere: string;
  geography: string;
  rules_and_constraints: string[];
  applicable_rule_ids: string[];
  associated_faction_ids: string[];
  story_function: string;
  tags: string[];
}

/** 正式地点创建和编辑共用的业务字段。 */
export interface LocationFieldsV1 extends LocationContentFieldsV1 {
  status: LocationStatus;
}

/** 人工创建正式地点的严格请求。 */
export type LocationCreateV1 = Pick<
  LocationFieldsV1,
  "name" | "location_type" | "description"
> & Partial<Omit<LocationFieldsV1, "name" | "location_type" | "description">>;

/** 正式地点更新请求；公开版本只通过 expected_version 提交。 */
export type LocationUpdateV1 = Partial<LocationFieldsV1> & {
  expected_version: number;
};

/** 正式地点公开响应。 */
export interface LocationReadV1 extends LocationFieldsV1 {
  location_id: string;
  novel_id: string;
  order_index: number;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 单卷地点 AI 返回的一条可编辑候选。 */
export interface VolumeLocationCandidateV1 extends Omit<LocationContentFieldsV1, "parent_location_id"> {
  candidate_ref: string;
  parent_location_ref: string | null;
  parent_location_id: string | null;
}

/** 单卷地点 AI 的严格候选结果。 */
export interface VolumeLocationsResultV1 {
  locations: VolumeLocationCandidateV1[];
}

/** 服务端写入 basis 的确定性生成输入；前端只校验并原样回传。 */
export interface VolumeLocationsGenerationInputV1 extends ReasoningOptions {
  selection_mode?: "auto" | "manual";
  novel_id: string;
  volume_id: string;
  location_count: number;
  volume_expected_version: number;
  allow_incremental: boolean;
  selected_existing_location_ids: string[];
  user_guidance: string;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
}

/** 单卷地点候选依据；generation_input 也由后端签发。 */
export interface VolumeLocationsBasisV1 extends CandidateBasisV1 {
  generation_input: VolumeLocationsGenerationInputV1;
}

/** 普通响应与 SSE done.result 共用的单卷地点候选信封。 */
export interface VolumeLocationsPreviewV1 {
  workflow: "create_locations_for_volume_by_ai";
  step: "create_locations_for_volume";
  schema_id: "volume_locations_result";
  schema_version: 1;
  candidate: VolumeLocationsResultV1;
  basis: VolumeLocationsBasisV1;
}

/** 单卷地点生成请求。 */
export interface VolumeLocationsGenerateRequestV1 extends ReasoningOptions {
  location_count: number;
  volume_expected_version: number;
  allow_incremental: boolean;
  selected_existing_location_ids: string[];
  user_guidance: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
  use_stream: boolean;
}

/** 单卷地点候选整批确认请求。 */
export interface VolumeLocationsConfirmV1 {
  candidates: VolumeLocationCandidateV1[];
  basis: VolumeLocationsBasisV1;
  expected_versions: Record<string, number>;
}

/** 单卷地点候选整批确认后的正式映射。 */
export interface VolumeLocationsConfirmResponseV1 {
  candidate_ref_map: Record<string, string>;
  locations: LocationReadV1[];
}

/** 同父级完整重排中的单条 CAS 命令。 */
export interface LocationReorderItemV1 {
  location_id: string;
  order_index: number;
  expected_version: number;
}

/** 同父级完整重排请求。 */
export interface LocationReorderRequestV1 {
  parent_location_id: string | null;
  items: LocationReorderItemV1[];
}

/** 地点恢复请求。 */
export interface LocationRestoreRequestV1 {
  expected_version: number;
}

/** 删除父地点前展示的子级与受保护引用影响。 */
export interface LocationDeleteImpactV1 {
  location_id: string;
  direct_child_location_ids: string[];
  active_direct_children: number;
  deleted_direct_children: number;
  world_rules: number;
  arcs: number;
  chapters: number;
  scenes: number;
  items: number;
  foreshadowings: number;
  total_protected_references: number;
  has_children: boolean;
  has_protected_references: boolean;
}

/** 地点永久删除成功响应。 */
export interface LocationHardDeleteResponseV1 {
  message: string;
  location_id: string;
  impact: LocationDeleteImpactV1;
}

const LOCATION_KEYS = [
  "location_id",
  "novel_id",
  "name",
  "aliases",
  "location_type",
  "parent_location_id",
  "description",
  "environment",
  "atmosphere",
  "geography",
  "rules_and_constraints",
  "applicable_rule_ids",
  "associated_faction_ids",
  "story_function",
  "status",
  "tags",
  "order_index",
  "version",
  "is_deleted",
  "deleted_at",
  "created_at",
  "updated_at",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown, maximum: number): value is string[] {
  return Array.isArray(value)
    && value.length <= maximum
    && value.every((item) => typeof item === "string" && item.trim().length > 0);
}

/**
 * 严格解析单条正式地点响应。
 *
 * Args:
 *   value: API 返回的未知 JSON 值。
 *   novelId: 可选的当前小说 ObjectId；传入后同时校验父级隔离。
 *
 * Returns:
 *   字段、类型、稳定引用和删除审计均符合 V1 契约时返回地点，否则抛出错误。
 */
export function parseLocationReadV1(value: unknown, novelId?: string): LocationReadV1 {
  if (!isRecord(value)) throw new Error("Invalid location response");
  if (
    Object.keys(value).length !== LOCATION_KEYS.length
    || LOCATION_KEYS.some((key) => !(key in value))
    || !isBusinessId("location", value.location_id)
    || !isObjectIdString(value.novel_id)
    || (novelId !== undefined && value.novel_id !== novelId)
    || typeof value.name !== "string"
    || value.name.trim().length < 1
    || value.name.length > 80
    || !isStringArray(value.aliases, 10)
    || typeof value.location_type !== "string"
    || value.location_type.trim().length < 1
    || value.location_type.length > 40
    || !(value.parent_location_id === null || isBusinessId("location", value.parent_location_id))
    || typeof value.description !== "string"
    || value.description.trim().length < 1
    || value.description.length > 2000
    || typeof value.environment !== "string"
    || value.environment.length > 1000
    || typeof value.atmosphere !== "string"
    || value.atmosphere.length > 1000
    || typeof value.geography !== "string"
    || value.geography.length > 1000
    || !isStringArray(value.rules_and_constraints, 20)
    || !Array.isArray(value.applicable_rule_ids)
    || value.applicable_rule_ids.length > 50
    || !value.applicable_rule_ids.every((id) => isBusinessId("world_rule", id))
    || !Array.isArray(value.associated_faction_ids)
    || value.associated_faction_ids.length > 50
    || !value.associated_faction_ids.every((id) => isBusinessId("faction", id))
    || typeof value.story_function !== "string"
    || value.story_function.length > 1000
    || !["active", "inactive"].includes(String(value.status))
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
  ) throw new Error("Invalid location response");

  return value as unknown as LocationReadV1;
}

/**
 * 严格解析正式地点列表响应。
 *
 * Args:
 *   value: API 返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   保持服务端顺序的正式地点数组；任一条非法时整体抛错。
 */
export function parseLocationListV1(value: unknown, novelId: string): LocationReadV1[] {
  if (!Array.isArray(value)) throw new Error("Invalid location list response");
  const locations = value.map((location) => parseLocationReadV1(location, novelId));
  const ids = locations.map((location) => location.location_id);
  if (new Set(ids).size !== ids.length) throw new Error("Invalid location list response");
  return locations;
}

/**
 * 严格解析未筛选的活动地点全量列表及其层级不变量。
 *
 * Args:
 *   value: 活动地点列表接口返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   ID、父链、同父规范名称和 1-based 连续顺序均合法的地点数组。
 */
export function parseActiveLocationListV1(value: unknown, novelId: string): LocationReadV1[] {
  const locations = parseLocationListV1(value, novelId);
  if (locations.some((location) => location.is_deleted)) {
    throw new Error("Invalid active location list response");
  }
  const byId = new Map(locations.map((location) => [location.location_id, location]));
  for (const location of locations) {
    if (location.parent_location_id && !byId.has(location.parent_location_id)) {
      throw new Error("Invalid active location list response");
    }
    if (location.parent_location_id && byId.get(location.parent_location_id)?.status !== "active") {
      throw new Error("Invalid active location list response");
    }
    const visited = new Set([location.location_id]);
    let parentId = location.parent_location_id;
    while (parentId) {
      if (visited.has(parentId)) throw new Error("Invalid active location list response");
      visited.add(parentId);
      parentId = byId.get(parentId)?.parent_location_id ?? null;
    }
  }

  const siblings = new Map<string, LocationReadV1[]>();
  for (const location of locations) {
    const parentKey = location.parent_location_id ?? "__root__";
    siblings.set(parentKey, [...(siblings.get(parentKey) ?? []), location]);
  }
  for (const group of siblings.values()) {
    const orders = group.map((location) => location.order_index).sort((left, right) => left - right);
    if (orders.some((order, index) => order !== index + 1)) {
      throw new Error("Invalid active location list response");
    }
    const normalizedNames = group.map((location) => location.name
      .normalize("NFKC")
      .trim()
      .replace(/\s+/g, " ")
      .toLowerCase());
    if (new Set(normalizedNames).size !== normalizedNames.length) {
      throw new Error("Invalid active location list response");
    }
  }
  return locations;
}

/**
 * 严格解析地点回收站列表，不把活动层级连续性错误套用到已删除记录。
 *
 * Args:
 *   value: 回收站列表接口返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *
 * Returns:
 *   ID 唯一且全部带删除审计的地点数组。
 */
export function parseTrashLocationListV1(value: unknown, novelId: string): LocationReadV1[] {
  const locations = parseLocationListV1(value, novelId);
  if (locations.some((location) => !location.is_deleted)) {
    throw new Error("Invalid trash location list response");
  }
  return locations;
}

/**
 * 严格解析地点删除影响响应。
 *
 * Args:
 *   value: 删除影响接口返回的未知 JSON 值。
 *   locationId: 当前操作目标地点 ID。
 *
 * Returns:
 *   子级与保护引用计数完全符合公开契约时返回影响对象，否则抛出错误。
 */
export function parseLocationDeleteImpactV1(
  value: unknown,
  locationId: string,
): LocationDeleteImpactV1 {
  if (!isRecord(value)) throw new Error("Invalid location delete impact response");
  const keys = [
    "location_id",
    "direct_child_location_ids",
    "active_direct_children",
    "deleted_direct_children",
    "world_rules",
    "arcs",
    "chapters",
    "scenes",
    "items",
    "foreshadowings",
    "total_protected_references",
    "has_children",
    "has_protected_references",
  ];
  const counts = [
    value.active_direct_children,
    value.deleted_direct_children,
    value.world_rules,
    value.arcs,
    value.chapters,
    value.scenes,
    value.items,
    value.foreshadowings,
    value.total_protected_references,
  ];
  if (
    Object.keys(value).length !== keys.length
    || keys.some((key) => !(key in value))
    || value.location_id !== locationId
    || !Array.isArray(value.direct_child_location_ids)
    || !value.direct_child_location_ids.every((id) => isBusinessId("location", id))
    || new Set(value.direct_child_location_ids).size !== value.direct_child_location_ids.length
    || value.direct_child_location_ids.length !== Number(value.active_direct_children)
    || !counts.every((count) => Number.isInteger(count) && Number(count) >= 0)
    || typeof value.has_children !== "boolean"
    || typeof value.has_protected_references !== "boolean"
    || value.has_children !== (Number(value.active_direct_children) + Number(value.deleted_direct_children) > 0)
    || Number(value.total_protected_references) !== [
      value.world_rules,
      value.arcs,
      value.chapters,
      value.scenes,
      value.items,
      value.foreshadowings,
    ].reduce<number>((total, count) => total + Number(count), 0)
    || value.has_protected_references !== (Number(value.total_protected_references) > 0)
  ) throw new Error("Invalid location delete impact response");
  return value as unknown as LocationDeleteImpactV1;
}

/**
 * 严格解析地点永久删除响应。
 *
 * Args:
 *   value: 永久删除接口返回的未知 JSON 值。
 *   locationId: 当前操作目标地点 ID。
 *
 * Returns:
 *   固定消息、目标 ID 与影响清单均合法时返回响应，否则抛出错误。
 */
export function parseLocationHardDeleteResponseV1(
  value: unknown,
  locationId: string,
): LocationHardDeleteResponseV1 {
  if (
    !isRecord(value)
    || Object.keys(value).length !== 3
    || !("message" in value && "location_id" in value && "impact" in value)
    || value.message !== "Hard deleted successfully"
    || value.location_id !== locationId
  ) throw new Error("Invalid location hard delete response");
  const impact = parseLocationDeleteImpactV1(value.impact, locationId);
  if (
    impact.has_children
    || impact.has_protected_references
    || impact.direct_child_location_ids.length > 0
    || [
      impact.active_direct_children,
      impact.deleted_direct_children,
      impact.world_rules,
      impact.arcs,
      impact.chapters,
      impact.scenes,
      impact.items,
      impact.foreshadowings,
      impact.total_protected_references,
    ].some((count) => count !== 0)
  ) throw new Error("Invalid location hard delete response");
  return {
    message: value.message,
    location_id: locationId,
    impact,
  };
}

const VOLUME_LOCATION_CANDIDATE_KEYS = [
  "candidate_ref",
  "name",
  "aliases",
  "location_type",
  "parent_location_ref",
  "parent_location_id",
  "description",
  "environment",
  "atmosphere",
  "geography",
  "rules_and_constraints",
  "applicable_rule_ids",
  "associated_faction_ids",
  "story_function",
  "tags",
] as const;

const VOLUME_LOCATION_INPUT_KEYS = [
  "novel_id",
  "volume_id",
  "location_count",
  "volume_expected_version",
  "allow_incremental",
  "selected_existing_location_ids",
  "user_guidance",
  "temperature",
  "top_p",
  "max_tokens",
  "presence_penalty",
  "frequency_penalty",
  "system_prompt",
] as const;

function hasOnlyKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  optionalKeys: readonly string[] = [],
): boolean {
  const expected = new Set(keys);
  const actual = Object.keys(value).filter((key) => !optionalKeys.includes(key));
  return actual.length === expected.size && actual.every((key) => expected.has(key));
}

function isNullableNumberInRange(value: unknown, minimum: number, maximum: number): boolean {
  return value === null
    || (typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum);
}

function normalizeLocationName(value: string): string {
  return value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function isVolumeLocationGenerationInput(
  value: unknown,
  expected: VolumeLocationsGenerationInputV1,
): value is VolumeLocationsGenerationInputV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, VOLUME_LOCATION_INPUT_KEYS, [...REASONING_FIELDS, "selection_mode", "prepared_context"])) return false;
  if (
    !hasValidReasoningOptions(value)
    || REASONING_FIELDS.some((key) => (value[key] ?? null) !== (expected[key] ?? null))
    || value.novel_id !== expected.novel_id
    || value.volume_id !== expected.volume_id
    || value.location_count !== expected.location_count
    || value.volume_expected_version !== expected.volume_expected_version
    || value.allow_incremental !== expected.allow_incremental
    || value.user_guidance !== expected.user_guidance
    || value.temperature !== expected.temperature
    || value.top_p !== expected.top_p
    || value.max_tokens !== expected.max_tokens
    || value.presence_penalty !== expected.presence_penalty
    || value.frequency_penalty !== expected.frequency_penalty
    || value.system_prompt !== expected.system_prompt
    || !isObjectIdString(value.novel_id)
    || !isObjectIdString(value.volume_id)
    || !Number.isInteger(value.location_count)
    || Number(value.location_count) < 0
    || Number(value.location_count) > 20
    || !Number.isInteger(value.volume_expected_version)
    || Number(value.volume_expected_version) < 1
    || typeof value.allow_incremental !== "boolean"
    || !Array.isArray(value.selected_existing_location_ids)
    || value.selected_existing_location_ids.length > 50
    || !value.selected_existing_location_ids.every((id) => isBusinessId("location", id))
    || new Set(value.selected_existing_location_ids).size !== value.selected_existing_location_ids.length
    || JSON.stringify(value.selected_existing_location_ids) !== JSON.stringify(expected.selected_existing_location_ids)
    || typeof value.user_guidance !== "string"
    || value.user_guidance.length > 2000
    || !isNullableNumberInRange(value.temperature, 0, 2)
    || !isNullableNumberInRange(value.top_p, 0, 1)
    || !(value.max_tokens === null || (Number.isInteger(value.max_tokens) && Number(value.max_tokens) > 0))
    || !isNullableNumberInRange(value.presence_penalty, -2, 2)
    || !isNullableNumberInRange(value.frequency_penalty, -2, 2)
    || !(value.system_prompt === null || (typeof value.system_prompt === "string" && value.system_prompt.length <= 40000))
  ) return false;
  return true;
}

function isCandidateSourceRef(value: unknown): value is VolumeLocationsBasisV1["source_refs"][number] {
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

function isVolumeLocationCandidate(value: unknown, editable = false): value is VolumeLocationCandidateV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, VOLUME_LOCATION_CANDIDATE_KEYS)) return false;
  if (editable) {
    // 人工稿可能尚未填完；只保证表单能安全展示，不把它当成已通过保存校验。
    return typeof value.candidate_ref === "string"
      && value.candidate_ref.trim().length > 0
      && value.candidate_ref.length <= 64
      && ["name", "location_type", "description", "environment", "atmosphere", "geography", "story_function"]
        .every((field) => typeof value[field] === "string")
      && ["aliases", "rules_and_constraints", "applicable_rule_ids", "associated_faction_ids", "tags"]
        .every((field) => Array.isArray(value[field]) && value[field].every((item) => typeof item === "string"))
      && (value.parent_location_ref === null || typeof value.parent_location_ref === "string")
      && (value.parent_location_id === null || typeof value.parent_location_id === "string");
  }
  if (
    typeof value.candidate_ref !== "string"
    || value.candidate_ref.trim().length < 1
    || value.candidate_ref.length > 64
    || typeof value.name !== "string"
    || value.name.trim().length < 1
    || value.name.length > 80
    || !isStringArray(value.aliases, 10)
    || typeof value.location_type !== "string"
    || value.location_type.trim().length < 1
    || value.location_type.length > 40
    || !(value.parent_location_ref === null || (
      typeof value.parent_location_ref === "string"
      && value.parent_location_ref.trim().length >= 1
      && value.parent_location_ref.length <= 64
    ))
    || !(value.parent_location_id === null || isBusinessId("location", value.parent_location_id))
    || (value.parent_location_ref !== null && value.parent_location_id !== null)
    || typeof value.description !== "string"
    || value.description.trim().length < 1
    || value.description.length > 2000
    || typeof value.environment !== "string"
    || value.environment.length > 1000
    || typeof value.atmosphere !== "string"
    || value.atmosphere.length > 1000
    || typeof value.geography !== "string"
    || value.geography.length > 1000
    || !isStringArray(value.rules_and_constraints, 20)
    || !Array.isArray(value.applicable_rule_ids)
    || value.applicable_rule_ids.length > 50
    || !value.applicable_rule_ids.every((id) => isBusinessId("world_rule", id))
    || new Set(value.applicable_rule_ids).size !== value.applicable_rule_ids.length
    || !Array.isArray(value.associated_faction_ids)
    || value.associated_faction_ids.length > 50
    || !value.associated_faction_ids.every((id) => isBusinessId("faction", id))
    || new Set(value.associated_faction_ids).size !== value.associated_faction_ids.length
    || typeof value.story_function !== "string"
    || value.story_function.trim().length < 1
    || value.story_function.length > 1000
    || !isStringArray(value.tags, 20)
  ) return false;
  const normalizedTexts = [value.name, ...value.aliases].map(normalizeLocationName);
  const normalizedConstraints = value.rules_and_constraints.map(normalizeLocationName);
  const normalizedTags = value.tags.map(normalizeLocationName);
  return new Set(normalizedTexts).size === normalizedTexts.length
    && new Set(normalizedConstraints).size === normalizedConstraints.length
    && new Set(normalizedTags).size === normalizedTags.length;
}

/**
 * 解析单卷地点生成结果，或恢复带原依据的本地人工稿。
 *
 * Args:
 *   value: 待解析的未知响应值。
 *   expectedInput: 当前请求对应的确定性生成输入。
 *   existingLocations: 请求发出时的活动正式地点快照。
 *   options: editable 仅用于恢复本地人工稿，允许未填完或待修正的内容。
 *
 * Returns:
 *   依据和字段结构完整时返回候选信封，否则返回 null；生成结果还须通过内容校验。
 */
export function parseVolumeLocationsPreviewV1(
  value: unknown,
  expectedInput: VolumeLocationsGenerationInputV1,
  existingLocations: readonly LocationReadV1[],
  options: { editable?: boolean } = {},
): VolumeLocationsPreviewV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "workflow",
    "step",
    "schema_id",
    "schema_version",
    "candidate",
    "basis",
  ])) return null;
  if (
    value.workflow !== "create_locations_for_volume_by_ai"
    || value.step !== "create_locations_for_volume"
    || value.schema_id !== "volume_locations_result"
    || value.schema_version !== 1
    || !isRecord(value.candidate)
    || !hasOnlyKeys(value.candidate, ["locations"])
    || !Array.isArray(value.candidate.locations)
    || (!options.editable && value.candidate.locations.length !== expectedInput.location_count)
    || !value.candidate.locations.every((candidate) => isVolumeLocationCandidate(candidate, options.editable))
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
    ], ["prepared_context", "context_basis", "content_fingerprint"])
    || value.basis.novel_id !== expectedInput.novel_id
    || value.basis.workflow !== value.workflow
    || value.basis.step !== value.step
    || value.basis.schema_id !== value.schema_id
    || value.basis.schema_version !== value.schema_version
    || typeof value.basis.input_fingerprint !== "string"
    || !/^[0-9a-f]{64}$/.test(value.basis.input_fingerprint)
    || !Array.isArray(value.basis.source_refs)
    || value.basis.source_refs.length < 1
    || value.basis.source_refs.length > 2000
    || !value.basis.source_refs.every(isCandidateSourceRef)
    || !isVolumeLocationGenerationInput(value.basis.generation_input, expectedInput)
  ) return null;

  const sourceKeys = value.basis.source_refs.map((source) => `${source.resource_type}:${source.id}`);
  if (new Set(sourceKeys).size !== sourceKeys.length) return null;
  const sourceRefs = value.basis.source_refs as VolumeLocationsBasisV1["source_refs"];
  const sourceIds = (resourceType: string) => new Set(
    sourceRefs
      .filter((source) => source.resource_type === resourceType)
      .map((source) => source.id),
  );
  const novelSources = sourceRefs.filter((source) => source.resource_type === "novel");
  const volumeSources = sourceRefs.filter((source) => source.resource_type === "volume");
  if (
    novelSources.length !== 1
    || novelSources[0].id !== expectedInput.novel_id
    || volumeSources.length !== 1
    || volumeSources[0].id !== expectedInput.volume_id
    || (expectedInput.selection_mode !== "auto" && volumeSources[0].version !== expectedInput.volume_expected_version)
  ) return null;

  const candidates = value.candidate.locations as VolumeLocationCandidateV1[];
  const refs = candidates.map((candidate) => candidate.candidate_ref);
  if (new Set(refs).size !== refs.length) return null;
  const allowedLocationIds = sourceIds("location");
  if (expectedInput.selected_existing_location_ids.some((id) => !allowedLocationIds.has(id))) return null;
  // 当前列表可能已变化，原稿仍要保留；失效判断和确认继续使用原 basis。
  if (options.editable) return value as unknown as VolumeLocationsPreviewV1;
  const formalIds = new Set(
    existingLocations
      .filter((location) => !location.is_deleted && location.status === "active")
      .map((location) => location.location_id),
  );
  const allowedRuleIds = sourceIds("world_rule");
  const allowedFactionIds = sourceIds("faction");
  if (
    allowedLocationIds.size !== formalIds.size
    || [...allowedLocationIds].some((id) => !formalIds.has(id))
  ) return null;
  const usedNames = new Set(
    existingLocations
      .filter((location) => !location.is_deleted && location.status === "active")
      .flatMap((location) => [location.name, ...location.aliases])
      .map(normalizeLocationName),
  );
  const seenRefs = new Set<string>();
  for (const candidate of candidates) {
    if (candidate.parent_location_ref && !seenRefs.has(candidate.parent_location_ref)) return null;
    if (candidate.parent_location_id && !allowedLocationIds.has(candidate.parent_location_id)) return null;
    if (candidate.applicable_rule_ids.some((id) => !allowedRuleIds.has(id))) return null;
    if (candidate.associated_faction_ids.some((id) => !allowedFactionIds.has(id))) return null;
    for (const text of [candidate.name, ...candidate.aliases]) {
      const normalized = normalizeLocationName(text);
      if (usedNames.has(normalized)) return null;
      usedNames.add(normalized);
    }
    seenRefs.add(candidate.candidate_ref);
  }
  return value as unknown as VolumeLocationsPreviewV1;
}

/**
 * 严格解析单卷地点整批确认响应。
 *
 * Args:
 *   value: 确认接口返回的未知 JSON 值。
 *   novelId: 当前小说 ObjectId。
 *   candidateRefs: 本批提交的稳定候选引用。
 *
 * Returns:
 *   映射完整且正式地点与映射一致时返回响应，否则返回 null。
 */
export function parseVolumeLocationsConfirmResponseV1(
  value: unknown,
  novelId: string,
  candidateRefs: readonly string[],
): VolumeLocationsConfirmResponseV1 | null {
  if (
    !isRecord(value)
    || !hasOnlyKeys(value, ["candidate_ref_map", "locations"])
    || !isRecord(value.candidate_ref_map)
    || !Array.isArray(value.locations)
    || value.locations.length !== candidateRefs.length
  ) return null;
  const expectedRefs = new Set(candidateRefs);
  const responseRefs = Object.keys(value.candidate_ref_map);
  const locationIds = Object.values(value.candidate_ref_map);
  if (
    responseRefs.length !== expectedRefs.size
    || !responseRefs.every((reference) => expectedRefs.has(reference))
    || !locationIds.every((id) => isBusinessId("location", id))
    || new Set(locationIds).size !== locationIds.length
  ) return null;
  let locations: LocationReadV1[];
  try {
    locations = value.locations.map((location) => parseLocationReadV1(location, novelId));
  } catch {
    return null;
  }
  const returnedIds = new Set(locations.map((location) => location.location_id));
  if (!locationIds.every((id) => returnedIds.has(id as string))) return null;
  return {
    candidate_ref_map: value.candidate_ref_map as Record<string, string>,
    locations,
  };
}
