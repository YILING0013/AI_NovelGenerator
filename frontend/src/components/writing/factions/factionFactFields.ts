import type { FactionFactField } from "@/types/factionFacts";

/** 面向作者的资料分组；设计目标、优势与卷计划保持原义。 */
export const FACTION_FACT_SECTIONS = {
  identity: ["faction_type", "positioning", "organization_style", "core_values", "is_public"],
  situation: ["actual_goal", "public_stance", "power_level", "resources", "influence_scope", "story_status"],
} as const satisfies Record<string, readonly FactionFactField[]>;
export const FACTION_FACT_FIELDS: FactionFactField[] = [...FACTION_FACT_SECTIONS.identity, ...FACTION_FACT_SECTIONS.situation];
