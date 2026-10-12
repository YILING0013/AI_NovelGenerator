import type { CandidateBasisV1 } from "@/lib/aiCandidate";
import type { CharacterFactCreateDataV1, CharacterFactPositionV1, CharacterFactValuesV1 } from "./characterFacts";
import type { CharacterRelationFactCreateDataV1 } from "./characterRelationFacts";
import type { CoreCharactersGenerationInputV1, CharacterRelationsGenerationInputV1 } from "./character";

export interface CharacterBatchBindingV1 {
  faction_id: string; faction_version: number; membership_type: "primary" | "secondary" | "covert";
  role_title?: string | null; public_status?: string | null; loyalty_level?: number | null; notes?: string | null;
}
export interface CharacterFactBatchCreateV1 {
  position: CharacterFactPositionV1;
  candidates: { candidate_ref: string; profile: CharacterFactCreateDataV1; facts: CharacterFactValuesV1; bindings?: CharacterBatchBindingV1[] }[];
  generation?: { basis: CandidateBasisV1; generation_input: CoreCharactersGenerationInputV1 } | null;
  confirmed: true;
}
export interface CharacterRelationFactBatchCreateV1 {
  position: CharacterFactPositionV1;
  candidates: { candidate_ref: string; profile: CharacterRelationFactCreateDataV1; facts: { current_state: string } }[];
  generation?: { basis: CandidateBasisV1; generation_input: CharacterRelationsGenerationInputV1 } | null;
  confirmed: true;
}
export interface CharacterFactBatchResultV1 {
  novel_id: string;
  characters: { candidate_ref: string; entity_id: string; character_id: string; version: number; history_id: string }[];
  bindings: { candidate_ref: string; binding_id: string; version: number }[];
}
export interface CharacterRelationFactBatchResultV1 {
  novel_id: string;
  relations: { candidate_ref: string; entity_id: string; relation_id: string; version: number; history_id: string }[];
}
