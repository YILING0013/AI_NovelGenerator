import { hasCandidateFlow } from "@/lib/aiCandidate";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";
import type { CharacterFactCreateDataV1, CharacterFactValuesV1 } from "./characterFacts";
import { CHARACTER_FACT_FIELDS } from "@/components/writing/characters/characterFactFields";
import type { CharacterProfileFields, JsonValue } from "./character";
import type { CharacterVolumePlanFieldsV1, CharacterVolumeStateReadV1 } from "./characterVolumeState";
import type { FactionVolumeStateFields, FactionVolumeStateReadV1, FactionVolumePlanFieldsV1 } from "./factionVolumeState";
import type { FactionFactField, FactionFactValuesV1 } from "./factionFacts";
import type { FactionCreateRequestV1 } from "./novel";

export type VolumeEntityKind = "characters" | "factions";
export const CHARACTER_PLAN_CONTRACT = "character_plan_initial_facts_v1" as const;
export type VolumeCharacterProfile = CharacterFactCreateDataV1 & { is_core_character: false; sort_order?: number; extra?: Record<string, JsonValue> };
export type VolumeFactionProfile = Omit<FactionCreateRequestV1, "level_type" | "sort_order" | FactionFactField> & Partial<Pick<FactionCreateRequestV1, Extract<keyof FactionCreateRequestV1, FactionFactField>>> & {
  level_type: "volume" | "local";
  sort_order?: number | null;
  first_appearance_volume_id?: null;
  first_appearance_chapter_id?: null;
};

/** 本卷新角色或已有角色的参与状态候选。 */
export interface VolumeCharacterCandidate {
  candidate_ref: string;
  character_id: string | null;
  profile: VolumeCharacterProfile | null;
  state: CharacterVolumePlanFieldsV1;
  initial_facts: CharacterFactValuesV1 | null;
  state_expected_version: number | null;
}

/** 本卷新势力或已有势力的参与状态候选。 */
export interface VolumeFactionCandidate {
  candidate_ref: string;
  faction_id: string | null;
  profile: VolumeFactionProfile | null;
  state: FactionVolumePlanFieldsV1 & Partial<FactionVolumeStateFields>;
  initial_facts?: FactionFactValuesV1;
  state_expected_version: number | null;
}

export type VolumeEntityCandidate = VolumeCharacterCandidate | VolumeFactionCandidate;
export interface VolumeEntityGenerationInput {
  selection_mode?: "auto" | "manual";
  novel_id: string;
  volume_id: string;
  volume_expected_version: number;
  new_count: number;
  selected_existing_ids: string[];
  user_guidance: string;
}
export interface VolumeEntityBasis extends CandidateBasisV1 { generation_input: VolumeEntityGenerationInput }
export type VolumeEntityPreview = CandidateGenerationEnvelopeV1<{
  characters?: VolumeCharacterCandidate[];
  factions?: VolumeFactionCandidate[];
}> & { basis: VolumeEntityBasis; contract?: typeof CHARACTER_PLAN_CONTRACT };
export interface VolumeEntityConfirmResult {
  novel_id: string;
  volume_id: string;
  data: (CharacterVolumeStateReadV1 | FactionVolumeStateReadV1)[];
  mapping: Record<string, string>;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const stringArray = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");

/** 功能：核对卷实体候选属于本轮小说、卷和任务，并保留服务端原始依据。Args: value 原响应；kind 实体种类；novelId 小说；volumeId 当前卷。Returns: 有效候选，或 null。 */
export function parseVolumeEntityPreview(value: unknown, kind: VolumeEntityKind, novelId: string, volumeId: string): VolumeEntityPreview | null {
  if (!isRecord(value) || !hasCandidateFlow(value.basis) || !isRecord(value.candidate)) return null;
  const workflow = `create_${kind}_for_volume_by_ai`;
  const basis = value.basis;
  const execution = basis.flow_snapshot?.execution;
  if (kind === "characters" && (value.contract !== CHARACTER_PLAN_CONTRACT
    || !isRecord(execution) || execution.character_candidate_contract !== CHARACTER_PLAN_CONTRACT)) return null;
  const input = basis.generation_input;
  if (value.workflow !== workflow || basis.workflow !== workflow || value.schema_version !== 1 || basis.schema_version !== 1
    || value.step !== `create_${kind}_for_volume` || value.schema_id !== `volume_${kind}_result`
    || value.step !== basis.step || value.schema_id !== basis.schema_id || basis.novel_id !== novelId
    || !isRecord(input) || input.novel_id !== novelId || input.volume_id !== volumeId
    || !isRecord(basis.flow_snapshot) || !isRecord(basis.flow_snapshot.scope)
    || basis.flow_snapshot.scope.novel_id !== novelId || basis.flow_snapshot.scope.volume_id !== volumeId
    || !Number.isInteger(input.volume_expected_version) || Number(input.volume_expected_version) < 1
    || typeof basis.input_fingerprint !== "string" || !/^[a-f0-9]{64}$/.test(basis.input_fingerprint)
    || !Array.isArray(basis.source_refs) || !basis.source_refs.every((source) => isRecord(source)
      && typeof source.resource_type === "string" && typeof source.id === "string" && Number.isInteger(source.version) && Number(source.version) > 0)
    || !basis.source_refs.some((source) => source.resource_type === "volume" && source.id === volumeId && (input.selection_mode === "auto" || source.version === input.volume_expected_version))
    || !basis.source_refs.some((source) => source.resource_type === "novel" && source.id === novelId)
    || Object.keys(value.candidate).length !== 1) return null;
  const candidates = value.candidate[kind];
  if (!Array.isArray(candidates) || candidates.length > 20) return null;
  const refs = new Set<string>();
  for (const item of candidates) {
    if (!isRecord(item) || typeof item.candidate_ref !== "string" || refs.has(item.candidate_ref)
      || !isRecord(item.state) || !(item.state_expected_version === null || Number.isInteger(item.state_expected_version) && Number(item.state_expected_version) > 0)) return null;
    refs.add(item.candidate_ref);
    const id = item[kind === "characters" ? "character_id" : "faction_id"];
    if (id === null ? !isRecord(item.profile) || item.state_expected_version !== null : typeof id !== "string" || item.profile !== null) return null;
    const state = item.state;
    if (!["primary", "secondary", "background"].includes(String(state.participation_scope))
      || !["current_goal", "start_state", "planned_end_state"].every((key) => typeof state[key] === "string")) return null;
    if (kind === "characters") {
      if (!stringArray(state.relationship_focus_ids) || typeof state.arc_progress !== "number"
        || Object.keys(state).some((key) => !["participation_scope", "current_goal", "start_state", "planned_end_state", "relationship_focus_ids", "arc_progress"].includes(key))) return null;
      if (id !== null ? item.initial_facts !== null : !isRecord(item.initial_facts) || !Object.keys(item.initial_facts).length) return null;
      if (isRecord(item.initial_facts) && Object.entries(item.initial_facts).some(([field, value]) =>
        !CHARACTER_FACT_FIELDS.includes(field as typeof CHARACTER_FACT_FIELDS[number])
        || (["strengths", "weaknesses", "abilities"].includes(field) ? !stringArray(value) : typeof value !== "string"))) return null;
      if (isRecord(item.profile) && (item.profile.is_core_character !== false
        || CHARACTER_FACT_FIELDS.some((field) => field in (item.profile as Record<string, unknown>))
        || !["name", "role_type", "importance_level"].every((key) => typeof (item.profile as Record<string, unknown>)[key] === "string")
        || !["conflict_with_mainline", "relationship_with_protagonist", "initial_state", "growth_direction", "story_function", "arc_seed"].every((key) => !(key in (item.profile as Record<string, unknown>)) || typeof (item.profile as Record<string, unknown>)[key] === "string")
        || !["aliases", "tags"].every((key) => !(key in (item.profile as Record<string, unknown>)) || stringArray((item.profile as Record<string, unknown>)[key])))) return null;
    } else {
      if (typeof state.hidden_agenda !== "string" || ("resources" in state && !stringArray(state.resources))
        || ("power_level" in state && typeof state.power_level !== "number")
        || !["public_stance", "influence_scope", "active_status"].every((key) => !(key in state) || typeof state[key] === "string")) return null;
      if (isRecord(item.profile) && (item.profile.volume_id !== null && item.profile.volume_id !== volumeId || !["volume", "local"].includes(String(item.profile.level_type))
        || !["name", "core_goal", "hidden_goal", "conflict_with_mainline", "expandability"].every((key) => typeof (item.profile as Record<string, unknown>)[key] === "string")
        || !["alias", "resources_and_advantages", "tags"].every((key) => stringArray((item.profile as Record<string, unknown>)[key]))
        || !["faction_type", "positioning", "public_stance", "organization_style", "influence_scope"].every((key) => !(key in (item.profile as Record<string, unknown>)) || typeof (item.profile as Record<string, unknown>)[key] === "string")
        || ("core_values" in item.profile && !stringArray(item.profile.core_values))
        || ("is_public" in item.profile && typeof item.profile.is_public !== "boolean"))) return null;
    }
  }
  return value as unknown as VolumeEntityPreview;
}

/** 只收集生成或作者明确输入的初始事实，保留空值与未提供的区别。 */
export function volumeFactionFacts(row: VolumeFactionCandidate): FactionFactValuesV1 {
  const profile = row.profile ?? {};
  const profileFields: FactionFactField[] = ["faction_type", "positioning", "organization_style", "core_values", "is_public", "public_stance", "influence_scope"];
  return { ...Object.fromEntries(profileFields.filter((field) => field in profile).map((field) => [field, profile[field as keyof typeof profile]])),
    ...Object.fromEntries(["power_level", "resources", "public_stance", "influence_scope", "active_status"].filter((field) => field in row.state)
      .map((field) => [field === "active_status" ? "story_status" : field, row.state[field as keyof typeof row.state]])), ...row.initial_facts };
}

/** 编辑值覆盖原明确输入；选择未填写时同步移除原候选中的对应事实。 */
export function editVolumeFactionFact(row: VolumeFactionCandidate, field: FactionFactField, value: FactionFactValuesV1[FactionFactField]): VolumeFactionCandidate {
  const profile = row.profile ? { ...row.profile } : null;
  const state = { ...row.state }, initial_facts = { ...row.initial_facts };
  if (profile) delete (profile as Record<string, unknown>)[field];
  delete (state as Record<string, unknown>)[field === "story_status" ? "active_status" : field];
  if (value === undefined) delete initial_facts[field]; else Object.assign(initial_facts, { [field]: value });
  return { ...row, profile, state, initial_facts };
}

/** 原生成依据决定能否区分明确事实；旧冻结命令另走原请求回放。 */
export function hasExplicitFactionValues(preview: VolumeEntityPreview | null): boolean {
  const execution = preview?.basis.flow_snapshot?.execution;
  return isRecord(execution) && execution.faction_candidate_contract === "explicit_faction_values_v1";
}

/** 为既有设计表单提供展示值，隐藏的事实占位不进入候选。
 * Args: profile 新合同中的设计资料。
 * Returns: 供 designOnly 表单使用的完整显示字段。
 */
export function volumeCharacterDesignForm(profile: VolumeCharacterProfile): CharacterProfileFields {
  return { name: profile.name, role_type: profile.role_type, importance_level: profile.importance_level,
    aliases: profile.aliases ?? [], tags: profile.tags ?? [], conflict_with_mainline: profile.conflict_with_mainline ?? "",
    relationship_with_protagonist: profile.relationship_with_protagonist ?? "", initial_state: profile.initial_state ?? "",
    growth_direction: profile.growth_direction ?? "", story_function: profile.story_function ?? "", arc_seed: profile.arc_seed ?? "",
    gender: "", age_group: "", race: "", identity: "", appearance: "", personality: "", core_desire: "", core_fear: "",
    strengths: [], weaknesses: [], abilities: [] };
}

/** 只采用设计表单的可见字段，事实继续独立保留。
 * Args: profile 原设计资料；value 表单当前值。
 * Returns: 只合入设计字段的新候选资料。
 */
export function editVolumeCharacterDesign(profile: VolumeCharacterProfile, value: CharacterProfileFields): VolumeCharacterProfile {
  const { name, aliases, role_type, importance_level, conflict_with_mainline, relationship_with_protagonist,
    initial_state, growth_direction, story_function, arc_seed, tags } = value;
  return { ...profile, name, aliases, role_type, importance_level, conflict_with_mainline, relationship_with_protagonist,
    initial_state, growth_direction, story_function, arc_seed, tags };
}
