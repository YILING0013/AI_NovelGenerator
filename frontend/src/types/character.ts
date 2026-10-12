import type { ReasoningOptions } from "@/types/generation";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";

/** 后端 JsonValue 在前端的递归 JSON 表示。 */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

/** ISO 8601 日期时间字符串。 */
export type IsoDateTime = string;

/** 全书级角色定位。 */
export type CharacterRoleType =
  | "protagonist"
  | "deuteragonist"
  | "antagonist"
  | "supporting"
  | "minor";

/** 全书级角色重要程度。 */
export type CharacterImportanceLevel =
  | "core"
  | "major"
  | "supporting"
  | "background";

/** 角色业务状态。 */
export type CharacterStatus = "active" | "inactive";

/** 角色与势力的成员关系类型。 */
export type CharacterFactionMembershipType = "primary" | "secondary" | "covert";

/** 人工创建与普通编辑允许直接选择的非主归属类型。 */
export type CharacterFactionBindingEditableMembershipType = "secondary" | "covert";

/** 角色档案中由创建请求、候选和公开响应共用的叙述字段。 */
export interface CharacterProfileFields {
  name: string;
  aliases: string[];
  role_type: CharacterRoleType;
  importance_level: CharacterImportanceLevel;
  gender: string;
  age_group: string;
  race: string;
  identity: string;
  appearance: string;
  personality: string;
  core_desire: string;
  core_fear: string;
  strengths: string[];
  weaknesses: string[];
  abilities: string[];
  conflict_with_mainline: string;
  relationship_with_protagonist: string;
  initial_state: string;
  growth_direction: string;
  story_function: string;
  arc_seed: string;
  tags: string[];
}

/** 人工创建全书级角色的 V1 请求。 */
export type CharacterCreateRequestV1 = Omit<
  CharacterProfileFields,
  "aliases" | "strengths" | "weaknesses" | "abilities" | "tags"
> & {
  aliases?: string[];
  strengths?: string[];
  weaknesses?: string[];
  abilities?: string[];
  tags?: string[];
  is_core_character?: boolean;
  sort_order?: number;
  extra?: Record<string, JsonValue>;
};

/** 正式角色档案允许更新的业务字段与并发版本。 */
export interface CharacterUpdateRequestV1 extends CharacterProfileFields {
  expected_version: number;
}

/** 正式角色启停请求；核心身份在创建后不可由该接口修改。 */
export interface CharacterStatusUpdateRequestV1 {
  expected_version: number;
  status: CharacterStatus;
}

/** 正式实体恢复请求。 */
export interface VersionedRestoreRequestV1 {
  expected_version: number;
}

/** 正式实体硬删除响应。 */
export interface HardDeleteResponseV1 {
  deleted: true;
  character_id?: string;
  relation_id?: string;
}

/** 全书级角色公开响应。 */
export interface CharacterResponseV1 extends CharacterProfileFields {
  novel_id: string;
  character_id: string;
  status: CharacterStatus;
  is_core_character: boolean;
  first_appearance_volume_id: string | null;
  first_appearance_chapter_id: string | null;
  sort_order: number;
  extra: Record<string, JsonValue>;
  version: number;
  is_deleted: boolean;
  deleted_at: IsoDateTime | null;
  deletion_sources: string[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** 模型生成的单个核心角色候选。 */
export interface CoreCharacterCandidateV1 extends CharacterProfileFields {
  character_ref: string;
}

/** 核心角色候选对应的势力绑定决策。 */
export interface CharacterFactionBindingCandidateV1 {
  character_ref: string;
  faction_id: string | null;
  membership_type: CharacterFactionMembershipType | null;
  role_title: string | null;
  public_status: string | null;
  loyalty_level: number | null;
  reason: string | null;
}

/** 全书级核心角色生成结果。 */
export interface CoreCharactersResultV1 {
  core_characters: CoreCharacterCandidateV1[];
  binding_candidates: CharacterFactionBindingCandidateV1[];
}

/** 核心角色生成确认时可重算指纹的严格业务输入。 */
export interface CoreCharactersGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  character_count: number;
  user_guidance: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

/** 核心角色生成 HTTP 请求，在业务输入外增加传输模式。 */
export interface CoreCharactersGenerateRequestV1 extends CoreCharactersGenerationInputV1 {
  use_stream?: boolean;
}

export type CoreCharactersCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<CoreCharactersResultV1>;

/** 核心角色候选的严格显式确认请求。 */
export interface CoreCharactersAIConfirmationRequestV1 {
  request_type: "ai_confirmation";
  candidate: CoreCharactersResultV1;
  selected_character_refs: string[];
  basis: CandidateBasisV1;
  generation_input: CoreCharactersGenerationInputV1;
  expected_versions: Record<string, number>;
}

/** 核心角色确认后的严格公开响应。 */
export interface CoreCharactersConfirmationResponseV1 {
  character_ref_map: Record<string, string>;
  characters: CharacterResponseV1[];
  character_faction_bindings: CharacterFactionBindingResponseV1[];
}

/** 人工创建角色势力绑定的 V1 请求。 */
export interface CharacterFactionBindingCreateRequestV1 {
  character_id: string;
  faction_id: string;
  membership_type: CharacterFactionBindingEditableMembershipType;
  role_title?: string | null;
  public_status?: string | null;
  loyalty_level?: number | null;
  notes?: string | null;
}

/** 普通绑定更新请求；主归属的进入和离开必须使用专用接口。 */
export interface CharacterFactionBindingUpdateRequestV1 {
  expected_version: number;
  membership_type?: CharacterFactionBindingEditableMembershipType;
  role_title?: string | null;
  public_status?: string | null;
  loyalty_level?: number | null;
  notes?: string | null;
}

/** 修改绑定用户启停意图的请求。 */
export interface CharacterFactionBindingActiveRequestV1 {
  expected_version: number;
  is_active: boolean;
}

/** 把既有绑定切换为主归属的严格请求。 */
export interface CharacterFactionBindingPrimaryRequestV1 {
  expected_version: number;
  replaced_expected_versions: Record<string, number>;
}

/** 角色势力绑定公开响应。 */
export interface CharacterFactionBindingResponseV1 {
  novel_id: string;
  binding_id: string;
  character_id: string;
  faction_id: string;
  membership_type: CharacterFactionMembershipType;
  role_title: string | null;
  public_status: string | null;
  loyalty_level: number | null;
  joined_volume_id: null;
  left_volume_id: null;
  user_is_active: boolean;
  is_active: boolean;
  notes: string | null;
  sort_order: number;
  version: number;
  is_deleted: boolean;
  deleted_at: IsoDateTime | null;
  deletion_sources: string[];
  disabled_by_character_ids: string[];
  disabled_by_faction_ids: string[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** 主归属切换返回的新主归属与被停用旧主归属。 */
export interface CharacterFactionBindingPrimaryResponseV1 {
  primary_binding: CharacterFactionBindingResponseV1;
  affected_bindings: CharacterFactionBindingResponseV1[];
}

/** 绑定硬删除响应。 */
export interface CharacterFactionBindingHardDeleteResponseV1 {
  deleted: boolean;
  binding_id: string;
}

/** 角色关系类型；前五项为对称关系，其余为有向关系。 */
export type CharacterRelationType =
  | "friend"
  | "romantic"
  | "ally"
  | "rival"
  | "enemy"
  | "parent_of"
  | "mentor_of"
  | "superior_of"
  | "protector_of"
  | "debtor_to";

/** 关系编辑器、创建请求、候选和公开响应共用的业务字段。 */
export interface CharacterRelationFields {
  source_character_id: string;
  target_character_id: string;
  relation_type: CharacterRelationType;
  current_state: string;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  story_value: string;
  intensity: number;
  is_active: boolean;
}

/** 人工创建角色关系的 V1 请求。 */
export type CharacterRelationCreateRequestV1 = Omit<CharacterRelationFields, "is_active"> & {
  is_active?: boolean;
  sort_order?: number;
};

/** 角色关系公开响应。 */
export interface CharacterRelationResponseV1 extends CharacterRelationFields {
  novel_id: string;
  relation_id: string;
  source_character_name: string | null;
  target_character_name: string | null;
  sort_order: number;
  version: number;
  user_is_active: boolean;
  disabled_by_character_ids: string[];
  is_deleted: boolean;
  deleted_at: IsoDateTime | null;
  deletion_sources: string[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/** 正式人物关系允许更新的内容字段；关系端点保持只读。 */
export type CharacterRelationUpdateRequestV1 = Pick<
  CharacterRelationFields,
  | "relation_type"
  | "current_state"
  | "core_conflict"
  | "hidden_tension"
  | "possible_change"
  | "story_value"
  | "intensity"
> & {
  expected_version: number;
};

/** 正式人物关系的用户启停请求。 */
export interface CharacterRelationActiveUpdateRequestV1 {
  expected_version: number;
  is_active: boolean;
}

/** 模型生成或用户编辑后的单条角色关系候选。 */
export interface CharacterRelationCandidateV1 extends CharacterRelationFields {
  relation_ref: string;
  is_active: true;
}

/** Provider 返回的角色关系候选集合。 */
export interface CharacterRelationsResultV1 {
  relations: CharacterRelationCandidateV1[];
}

/** 角色关系确认时可重算指纹的严格业务输入。 */
export interface CharacterRelationsGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  character_ids: string[];
  allow_isolated_characters: boolean;
  relation_count_limit: number | null;
  user_guidance: string | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
}

/** 角色关系生成 HTTP 请求，在业务输入外增加传输模式。 */
export interface CharacterRelationsGenerateRequestV1 extends CharacterRelationsGenerationInputV1 {
  use_stream?: boolean;
}

export type CharacterRelationsCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<CharacterRelationsResultV1>;

/** 角色关系候选的严格显式确认请求。 */
export interface CharacterRelationsAIConfirmationRequestV1 {
  request_type: "ai_confirmation";
  candidate: CharacterRelationsResultV1;
  selected_character_refs: string[];
  selected_relation_refs: string[];
  basis: CandidateBasisV1;
  generation_input: CharacterRelationsGenerationInputV1;
  expected_versions: Record<string, number>;
}

/** 人工批量追加关系的可判别严格请求。 */
export interface BulkAppendCharacterRelationsRequestV1 {
  request_type: "manual";
  relations: CharacterRelationCreateRequestV1[];
}
