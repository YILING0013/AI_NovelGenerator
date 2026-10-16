import type { ReasoningOptions } from "@/types/generation";
import type { NovelRewriteFieldKey } from "@/lib/novelFields";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";

export type { NovelRewriteFieldKey } from "@/lib/novelFields";

export type NovelStatus = "draft" | "ongoing" | "completed" | "archived";

export interface NovelSummary {
  id: string;
  version: number;
  title: string;
  subtitle: string | null;
  genre: string;
  tags: string[];
  cover_image: string | null;
  status: NovelStatus;
  stats: {
    chapter_count: number;
    total_word_count: number;
  };
  current_volume_count: number;
  current_chapter_count: number;
  current_word_count: number;
  is_deleted: boolean;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface NovelDetail extends NovelSummary {
  introduction: string | null;
  summary: string | null;
  core_seed: string | null;
  worldview: string | null;
  writing_style: string | null;
  narrative_pov: string | null;
  era_background: string | null;
  plot: string | null;
  tone: string | null;
  target_audience: string | null;
  core_idea: string | null;
  number_of_chapters: number | null;
  words_per_chapter: number | null;
}

export interface CreateNovelRequest {
  title: string;
  subtitle?: string | null;
  genre?: string;
  tags?: string[];
  introduction?: string | null;
  summary?: string | null;
  core_seed?: string | null;
  worldview?: string | null;
  writing_style?: string | null;
  narrative_pov?: string | null;
  era_background?: string | null;
  plot?: string | null;
  tone?: string | null;
  target_audience?: string | null;
  core_idea?: string | null;
  number_of_chapters?: number | null;
  words_per_chapter?: number | null;
}

/** 整书永久删除前必须由作者确认的章后记录数量。 */
export interface ChapterRecordDeleteCounts {
  events: number;
  chapter_reports: number;
  entity_state_history: number;
  chapter_record_confirmation_receipts: number;
  report_heads: number;
}

export interface NovelHistoryDeleteImpact {
  novel_id: string;
  version: number;
  revision_count: number;
  foreshadowings: number;
  chapter_records: ChapterRecordDeleteCounts;
}

/**
 * 校验整书删除影响，缺少任何确认数量时不能放行。
 *
 * @param value 后端返回的 JSON。
 * @param novelId 当前待删除的小说 ID。
 * @returns 完整删除影响；响应不符合契约时返回 null，由界面显示本地化错误。
 */
export function parseNovelHistoryDeleteImpact(value: unknown, novelId: string): NovelHistoryDeleteImpact | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const impact = value as Record<string, unknown>;
  const keys = ["novel_id", "version", "revision_count", "foreshadowings", "chapter_records"];
  if (Object.keys(impact).length !== keys.length || keys.some((key) => !(key in impact))
    || impact.novel_id !== novelId
    || typeof impact.version !== "number" || !Number.isSafeInteger(impact.version) || impact.version < 1
    || ![impact.revision_count, impact.foreshadowings].every((count) => typeof count === "number" && Number.isSafeInteger(count) && count >= 0)
    || typeof impact.chapter_records !== "object" || impact.chapter_records === null || Array.isArray(impact.chapter_records)) return null;
  const records = impact.chapter_records as Record<string, unknown>;
  const recordKeys = ["events", "chapter_reports", "entity_state_history", "chapter_record_confirmation_receipts", "report_heads"];
  if (Object.keys(records).length !== recordKeys.length
    || !recordKeys.every((key) => typeof records[key] === "number" && Number.isSafeInteger(records[key]) && records[key] >= 0)) return null;
  return impact as unknown as NovelHistoryDeleteImpact;
}

export interface NovelCreateResponse {
  id: string;
  version: number;
}

export interface NovelManualCreateRequest extends CreateNovelRequest {
  request_type: "manual";
}

export interface NovelVersionRequest {
  expected_version: number;
}

export interface NovelUpdateRequest extends Partial<CreateNovelRequest>, NovelVersionRequest {
  request_type: "manual";
}

export interface RewriteChatMessage {
  id: string;
  role: "user" | "assistant";
  target_field: NovelRewriteFieldKey;
  content: string;
  provider?: string;
  status?: "failed";
  error_message?: string;
  created_at: string;
}

export interface RewriteFieldRevision {
  id: string;
  value: string | string[];
  source: "initial" | "manual" | "ai";
  instruction?: string;
  created_at: string;
}

export interface WritingDraftRewriteState {
  messagesByField: Partial<Record<NovelRewriteFieldKey, RewriteChatMessage[]>>;
  revisionsByField: Partial<Record<NovelRewriteFieldKey, RewriteFieldRevision[]>>;
  activeRevisionIdByField: Partial<Record<NovelRewriteFieldKey, string>>;
}

export interface RewriteNovelFieldRequest extends ReasoningOptions {
  provider: string;
  novel_id?: string;
  use_stream?: boolean;
  target_field: NovelRewriteFieldKey;
  instruction: string;
  current_value: string | string[];
  context: Record<string, unknown>;
  chat_history: Pick<RewriteChatMessage, "role" | "content">[];
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface RewriteNovelFieldResponse {
  target_field: NovelRewriteFieldKey;
  value: string | string[];
}

export type FactionRelationType =
  | "hostile"
  | "allied"
  | "cold_war"
  | "dependent"
  | "subordinate"
  | "trade_partner"
  | "secret_cooperation"
  | "historical_enemy";

export interface CoreFaction {
  novel_id: string;
  faction_id: string;
  is_deleted: boolean;
  deleted_at: string | null;
  deletion_sources: Array<"user">;
  created_at: string;
  updated_at: string;
  name: string;
  alias?: string[];
  faction_type: string;
  level_type: "core" | "volume" | "local";
  parent_faction_id?: string | null;
  volume_id?: string | null;
  positioning: string;
  public_stance: string;
  core_goal: string;
  hidden_goal?: string;
  resources_and_advantages: string[];
  organization_style: string;
  core_values: string[];
  conflict_with_mainline: string;
  is_public: boolean;
  influence_scope: string;
  active_status: "active" | "inactive";
  expandability: string;
  tags: string[];
  sort_order?: number;
  version: number;
}

export interface FactionCreateRequestV1 {
  level_type: "core" | "volume" | "local";
  parent_faction_id: string | null;
  volume_id: string | null;
  name: string;
  alias: string[];
  faction_type: string;
  positioning: string;
  public_stance: string;
  core_goal: string;
  hidden_goal: string;
  resources_and_advantages: string[];
  organization_style: string;
  core_values: string[];
  conflict_with_mainline: string;
  is_public: boolean;
  influence_scope: string;
  expandability: string;
  tags: string[];
  sort_order: number;
}

export interface FactionUpdateRequestV1 extends Omit<
  FactionCreateRequestV1,
  "level_type" | "volume_id"
> {
  expected_version: number;
  active_status: "active" | "inactive";
}

export interface FactionSortItemV1 {
  faction_id: string;
  expected_version: number;
  sort_order: number;
}

export interface FactionBatchSortRequestV1 {
  items: FactionSortItemV1[];
}

export type RewriteNovelFieldGenerationInput = Omit<RewriteNovelFieldRequest, "use_stream">;

export interface RewriteNovelFieldAIConfirmRequest {
  request_type: "ai_field_confirmation";
  candidate: RewriteNovelFieldResponse;
  basis: CandidateBasisV1;
  generation_input: RewriteNovelFieldGenerationInput;
  expected_versions: Record<string, number>;
}

export interface GeneratedCoreFaction {
  faction_ref: string;
  name: string;
  faction_type: string;
  positioning: string;
  public_stance: string;
  core_goal: string;
  hidden_goal: string;
  resources_and_advantages: string[];
  organization_style: string;
  core_values: string[];
  conflict_with_mainline: string;
  is_public: boolean;
  influence_scope: string;
  expandability: string;
  tags: string[];
}

export interface FactionRelationResponseV1 {
  novel_id: string;
  relation_id: string;
  source_faction_id: string;
  target_faction_id: string;
  source_faction_name: string | null;
  target_faction_name: string | null;
  relation_type: FactionRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  intensity: number;
  is_active: boolean;
  user_is_active: boolean;
  sort_order: number;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  deletion_sources: string[];
  disabled_by_faction_ids: string[];
  created_at: string;
  updated_at: string;
}

export type CoreFactionRelationEndpointV2 =
  | { kind: "candidate"; faction_ref: string }
  | { kind: "existing"; faction_id: string };

export interface CoreFactionRelationCandidateV2 {
  relation_ref: string;
  source: CoreFactionRelationEndpointV2;
  target: CoreFactionRelationEndpointV2;
  relation_type: FactionRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  intensity: number;
  is_active: boolean;
}

export interface CoreFactionsResultV2 {
  core_factions: GeneratedCoreFaction[];
  faction_relations: CoreFactionRelationCandidateV2[];
}

export interface CoreFactionsGenerationInputV2 {
  novel_id: string;
  faction_count: number | null;
  independent_faction_count: number;
  user_guidance: string;
  single_faction_integrity_score: number | null;
  connect_to_existing: boolean;
  existing_relation_targets: Array<{
    faction_id: string;
    relation_score: number;
  }>;
  existing_relation_score: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface GenerateCoreFactionsRequestV2 extends CoreFactionsGenerationInputV2 {
  use_stream?: boolean;
}

export type CoreFactionsCandidateEnvelopeV2 = CandidateGenerationEnvelopeV1<CoreFactionsResultV2>;

export interface CoreFactionsAIConfirmationRequestV2 {
  request_type: "ai_confirmation";
  candidate: CoreFactionsResultV2;
  selected_faction_refs: string[];
  selected_relation_refs: string[];
  basis: CandidateBasisV1;
  generation_input: CoreFactionsGenerationInputV2;
  expected_versions: Record<string, number>;
}

/** 势力工作台使用的关系响应类型。 */
export type FactionRelation = FactionRelationResponseV1;

/** 人工创建正式阵营关系时只提交稳定的 faction_id 端点。 */
export interface FactionRelationCreateRequestV1 {
  source_faction_id: string;
  target_faction_id: string;
  relation_type: FactionRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  intensity: number;
  is_active?: boolean;
}

/** AI 生成或浏览器本地编辑后的单条阵营关系候选。 */
export interface FactionRelationCandidateV1 extends FactionRelationCreateRequestV1 {
  relation_ref: string;
  is_active: true;
}

/** 直接生成阵营关系候选时提交的完整扁平请求。 */
export interface FactionRelationsGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  faction_ids: string[];
  allow_isolated_factions: boolean;
  relation_count_limit: number | null;
  user_guidance: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface FactionRelationsGenerateRequestV1 extends FactionRelationsGenerationInputV1 {
  use_stream?: boolean;
}

/** 阵营关系 AI 生成接口返回的浏览器本地候选集合。 */
export interface FactionRelationsResultV1 {
  relations: FactionRelationCandidateV1[];
}

export type FactionRelationsCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<FactionRelationsResultV1>;

export interface FactionRelationsAIConfirmationRequestV1 {
  request_type: "ai_confirmation";
  candidate: FactionRelationsResultV1;
  selected_faction_refs: string[];
  selected_relation_refs: string[];
  basis: CandidateBasisV1;
  generation_input: FactionRelationsGenerationInputV1;
  expected_versions: Record<string, number>;
}

/** 用户确认后批量追加正式阵营关系的请求。 */
export interface BulkAppendFactionRelationsRequestV1 {
  request_type: "manual";
  relations: FactionRelationCreateRequestV1[];
}

/** 正式阵营关系允许更新的内容字段；端点不可通过更新接口改写。 */
export interface FactionRelationUpdateRequestV1 {
  expected_version: number;
  relation_type: FactionRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  intensity: number;
}

/** 正式阵营关系的用户启停请求。 */
export interface FactionRelationActiveUpdateRequestV1 {
  expected_version: number;
  is_active: boolean;
}

export interface BulkCreateCoreFactionsResponse {
  factions: CoreFaction[];
  faction_relations: FactionRelation[];
  faction_ref_map: Record<string, string>;
  relation_ref_map: Record<string, string>;
}

export type AICreateGenerationInput = import("@/types/taskFlow").TaskFlowRequest;

export interface AICreateCandidateV1 extends CreateNovelRequest {
  title: string;
  genre: string;
  tags: string[];
  subtitle: string | null;
  introduction: string | null;
  summary: string | null;
  core_seed: string | null;
  worldview: string | null;
  writing_style: string | null;
  narrative_pov: string | null;
  era_background: string | null;
  plot: string | null;
  tone: string | null;
  target_audience: string | null;
  core_idea: string | null;
  number_of_chapters: number | null;
  words_per_chapter: number | null;
}

export type AICreateCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<AICreateCandidateV1>;

export interface NovelAIConfirmationRequest {
  request_type: "ai_confirmation";
  candidate: AICreateCandidateV1;
  basis: CandidateBasisV1;
  generation_input: AICreateGenerationInput;
  expected_versions: Record<string, never>;
}

/** AI 创建草稿，用于本地存储传递到 Writing 创建态 */
export interface WritingDraft extends CreateNovelRequest {
  _fromAI?: boolean;
  _aiCreate?: {
    basis: CandidateBasisV1;
    generation_input: AICreateGenerationInput;
  };
  _rewriteState?: WritingDraftRewriteState;
}

/** Writing 侧栏导航项 */
export type WritingSidebarItem =
  | "novel-info"
  | "chapter-editor"
  | "arc-planning"
  | "volume-planning"
  | "character-cards"
  | "location-cards"
  | "faction-cards"
  | "item-cards"
  | "rule-cards"
  | "foreshadowings"
  | "entity-graph";
