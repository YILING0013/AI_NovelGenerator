import type { CandidateBasisV1 } from "@/lib/aiCandidate";
import type { CoreFactionsGenerationInputV2, CoreFactionsResultV2 } from "@/types/novel";
import type { FactionFactPositionV1 } from "@/types/factionFacts";
import type { FactionFactBatchCreateV1 } from "@/types/factionFactBatch";

/** 候选实际字段与设计原文分别采用；不把目标或资源优势重新命名成事实。 */
export function buildCoreFactionFactBatch(candidate: CoreFactionsResultV2, selected: string[], selectedRelations: string[],
  position: FactionFactPositionV1, basis: CandidateBasisV1, generationInput: CoreFactionsGenerationInputV2): FactionFactBatchCreateV1 {
  return { position, confirmed: true, generation: { basis, generation_input: generationInput },
    candidates: selected.map((ref) => {
      const row = candidate.core_factions.find((item) => item.faction_ref === ref);
      if (!row) throw new Error("所选势力候选已变化，请保留原稿");
      return { candidate_ref: ref, profile: { name: row.name, level_type: "core", core_goal: row.core_goal, hidden_goal: row.hidden_goal,
        resources_and_advantages: row.resources_and_advantages, conflict_with_mainline: row.conflict_with_mainline, expandability: row.expandability, tags: row.tags },
        facts: { faction_type: row.faction_type, positioning: row.positioning, organization_style: row.organization_style,
          core_values: row.core_values, is_public: row.is_public, public_stance: row.public_stance, influence_scope: row.influence_scope } };
    }), relations: selectedRelations.map((ref) => {
      const row = candidate.faction_relations.find((item) => item.relation_ref === ref);
      if (!row) throw new Error("所选关系候选已变化，请保留原稿");
      return row;
    }) };
}
