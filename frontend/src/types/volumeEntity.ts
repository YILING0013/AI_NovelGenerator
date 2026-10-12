import { hasCandidateFlow } from "@/lib/aiCandidate";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";
import type { CharacterProfileFields, JsonValue } from "./character";
import type { CharacterVolumeStateFields, CharacterVolumeStateReadV1 } from "./characterVolumeState";
import type { FactionVolumeStateFields, FactionVolumeStateReadV1 } from "./factionVolumeState";
import type { FactionCreateRequestV1 } from "./novel";

export type VolumeEntityKind = "characters" | "factions";
export type VolumeCharacterProfile = CharacterProfileFields & { is_core_character: false; sort_order?: number; extra?: Record<string, JsonValue> };
export type VolumeFactionProfile = Omit<FactionCreateRequestV1, "level_type" | "sort_order"> & {
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
  state: CharacterVolumeStateFields;
  state_expected_version: number | null;
}

/** 本卷新势力或已有势力的参与状态候选。 */
export interface VolumeFactionCandidate {
  candidate_ref: string;
  faction_id: string | null;
  profile: VolumeFactionProfile | null;
  state: FactionVolumeStateFields;
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
}> & { basis: VolumeEntityBasis };
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
        || !["psychological_state", "public_state", "hidden_state"].every((key) => typeof state[key] === "string")) return null;
      if (isRecord(item.profile) && (item.profile.is_core_character !== false
        || !["name", "role_type", "importance_level", "gender", "age_group", "race", "identity", "appearance", "personality", "core_desire", "core_fear", "conflict_with_mainline", "relationship_with_protagonist", "initial_state", "growth_direction", "story_function", "arc_seed"].every((key) => typeof item.profile === "object" && item.profile !== null && typeof (item.profile as Record<string, unknown>)[key] === "string")
        || !["aliases", "strengths", "weaknesses", "abilities", "tags"].every((key) => stringArray((item.profile as Record<string, unknown>)[key])))) return null;
    } else {
      if (!stringArray(state.resources) || typeof state.power_level !== "number"
        || !["public_stance", "hidden_agenda", "influence_scope", "active_status"].every((key) => typeof state[key] === "string")) return null;
      if (isRecord(item.profile) && (item.profile.volume_id !== null && item.profile.volume_id !== volumeId || !["volume", "local"].includes(String(item.profile.level_type))
        || !["name", "faction_type", "positioning", "public_stance", "core_goal", "hidden_goal", "organization_style", "conflict_with_mainline", "influence_scope", "expandability"].every((key) => typeof (item.profile as Record<string, unknown>)[key] === "string")
        || !["alias", "resources_and_advantages", "core_values", "tags"].every((key) => stringArray((item.profile as Record<string, unknown>)[key])))) return null;
    }
  }
  return value as unknown as VolumeEntityPreview;
}
