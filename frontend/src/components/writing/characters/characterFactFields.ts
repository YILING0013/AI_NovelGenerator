import type { CharacterFactField } from "@/types/characterFacts";

/** 资料业务节与接管字段使用同一份明确名单，不混入设计或计划。 */
export const CHARACTER_FACT_SECTIONS = {
  identity: ["gender", "age_group", "race", "identity"],
  profile: ["appearance", "personality", "strengths", "weaknesses", "abilities"],
  motivation: ["core_desire", "core_fear"],
  situation: ["psychological_state", "public_state", "hidden_state", "actual_goal"],
} as const satisfies Record<string, readonly CharacterFactField[]>;

export const CHARACTER_PROFILE_FACT_FIELDS: CharacterFactField[] = [...CHARACTER_FACT_SECTIONS.identity, ...CHARACTER_FACT_SECTIONS.profile, ...CHARACTER_FACT_SECTIONS.motivation];
export const CHARACTER_FACT_FIELDS: CharacterFactField[] = [...CHARACTER_PROFILE_FACT_FIELDS, ...CHARACTER_FACT_SECTIONS.situation];
