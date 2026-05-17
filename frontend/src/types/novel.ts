import type { NovelRewriteFieldKey } from "@/lib/novelFields";

export type { NovelRewriteFieldKey } from "@/lib/novelFields";

export interface NovelSummary {
  _id: string;
  title: string;
  subtitle?: string;
  genre: string;
  tags: string[];
  cover_image?: string;
  status: string;
  stats: {
    chapter_count: number;
    total_word_count: number;
  };
  created_at: string;
  updated_at: string;
}

export interface NovelDetail extends NovelSummary {
  introduction?: string;
  summary?: string;
  core_seed?: string;
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
  plot?: string;
  tone?: string;
  target_audience?: string;
  core_idea?: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
}

export interface CreateNovelRequest {
  title: string;
  subtitle?: string;
  genre?: string;
  tags?: string[];
  introduction?: string;
  summary?: string;
  core_seed?: string;
  worldview?: string;
  writing_style?: string;
  narrative_pov?: string;
  era_background?: string;
  cover_image?: string;
  plot?: string;
  tone?: string;
  target_audience?: string;
  core_idea?: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
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

export interface RewriteNovelFieldRequest {
  provider: string;
  target_field: NovelRewriteFieldKey;
  instruction: string;
  current_value: string | string[];
  context: Record<string, unknown>;
  chat_history: Pick<RewriteChatMessage, "role" | "content">[];
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
  _id?: string;
  novel_id?: string;
  faction_id?: string;
  is_deleted?: boolean;
  deleted_at?: string | null;
  name: string;
  alias?: string[];
  faction_type: string;
  level_type?: string;
  parent_faction_id?: string | null;
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
  active_status?: string;
  expandability: string;
  tags: string[];
  sort_order?: number;
}

export interface FactionRelation {
  _id?: string;
  novel_id?: string;
  relation_id?: string;
  source_faction_id?: string;
  target_faction_id?: string;
  source_faction_name?: string;
  target_faction_name?: string;
  relation_type: FactionRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension?: string;
  possible_change: string;
  intensity: number;
  is_active: boolean;
}

export interface GeneratedFactionRelation extends FactionRelation {
  source_faction_name: string;
  target_faction_name: string;
}

export interface CoreFactionsPayload {
  core_factions: CoreFaction[];
  faction_relations: GeneratedFactionRelation[];
}

export interface GenerateCoreFactionsRequest {
  novel_id: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface BulkCreateCoreFactionsResponse {
  factions: CoreFaction[];
  faction_relations: FactionRelation[];
}

export interface AICreateRequest {
  user_idea: string;
  number_of_chapters?: number;
  words_per_chapter?: number;
  cached_steps?: AICreateCachedSteps;
  // 可选生成参数
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

export interface AICreateStepResult {
  step: string;
  data: Record<string, unknown>;
}

export interface AICreateResponse {
  expand_idea?: {
    plot: string;
  };
  extract_idea: {
    plot?: string;
    genre: string;
    tone: string;
    target_audience: string;
    core_idea: string;
  };
  core_seed: {
    core_seed: string;
  };
  novel_meta: {
    title: string;
    subtitle: string;
    introduction: string;
    summary: string;
    worldview: string;
    writing_style: string;
    narrative_pov: string;
    era_background: string;
    tags: string[];
  };
}

export type AICreateStepKey = "expand_idea" | "extract_idea" | "core_seed" | "novel_meta";

export type AICreateCachedSteps = Partial<{
  expand_idea: NonNullable<AICreateResponse["expand_idea"]>;
  extract_idea: AICreateResponse["extract_idea"];
  core_seed: AICreateResponse["core_seed"];
  novel_meta: AICreateResponse["novel_meta"];
}>;

/** AI 创建草稿，用于本地存储传递到 Writing 创建态 */
export interface WritingDraft extends CreateNovelRequest {
  _fromAI?: boolean;
  _rewriteState?: WritingDraftRewriteState;
}

/** Writing 侧栏导航项 */
export type WritingSidebarItem =
  | "novel-info"
  | "chapter-editor"
  | "character-cards"
  | "location-cards"
  | "faction-cards"
  | "item-cards"
  | "rule-cards"
  | "relationship-map";
