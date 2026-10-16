import type { CandidateBasisV1 } from "@/lib/aiCandidate";
import type { CoreFactionRelationCandidateV2, CoreFactionsGenerationInputV2, FactionRelation } from "./novel";
import type { FactionFactCreateDataV1, FactionFactPositionV1, FactionFactResultV1, FactionFactValuesV1 } from "./factionFacts";

/** 一次采用的原内容；设计和事实不互相填充。 */
export interface FactionFactBatchCreateV1 {
  position: FactionFactPositionV1;
  candidates: { candidate_ref: string; profile: FactionFactCreateDataV1; facts: FactionFactValuesV1 }[];
  relations: CoreFactionRelationCandidateV2[];
  generation?: { basis: CandidateBasisV1; generation_input: CoreFactionsGenerationInputV2 } | null;
  confirmed: true;
}

/** 每一成员和关系均为第一次保存的完整结果。 */
export interface FactionFactBatchResultV1 {
  novel_id: string;
  factions: { candidate_ref: string; result: FactionFactResultV1 }[];
  relations: { relation_ref: string; result: FactionRelation }[];
  faction_ref_map: Record<string, string>;
  relation_ref_map: Record<string, string>;
}
