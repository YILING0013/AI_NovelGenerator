import type { CharacterProfileFields } from "@/types/character";
import type { CharacterFactCreateDataV1, CharacterFactField, CharacterFactValuesV1 } from "@/types/characterFacts";
import { CHARACTER_PROFILE_FACT_FIELDS } from "./characterFactFields";

export const REQUIRED_PROFILE_TEXT_FIELDS: Array<
  keyof Pick<
    CharacterProfileFields,
    | "name"
    | "gender"
    | "age_group"
    | "race"
    | "identity"
    | "appearance"
    | "personality"
    | "core_desire"
    | "core_fear"
    | "conflict_with_mainline"
    | "relationship_with_protagonist"
    | "initial_state"
    | "growth_direction"
    | "story_function"
    | "arc_seed"
  >
> = [
  "name",
  "gender",
  "age_group",
  "race",
  "identity",
  "appearance",
  "personality",
  "core_desire",
  "core_fear",
  "conflict_with_mainline",
  "relationship_with_protagonist",
  "initial_state",
  "growth_direction",
  "story_function",
  "arc_seed",
];


export function createEmptyCharacterProfile(): CharacterProfileFields {
  return {
    name: "",
    aliases: [],
    role_type: "supporting",
    importance_level: "supporting",
    gender: "",
    age_group: "",
    race: "",
    identity: "",
    appearance: "",
    personality: "",
    core_desire: "",
    core_fear: "",
    strengths: [],
    weaknesses: [],
    abilities: [],
    conflict_with_mainline: "",
    relationship_with_protagonist: "",
    initial_state: "",
    growth_direction: "",
    story_function: "",
    arc_seed: "",
    tags: [],
  };
}

/** 功能：只认领作者明确选中的事实，未选字段不补空值。Args: 作者档案、核心标记与已选字段。Returns: 设计候选和对应 after。 */
export function splitCharacterFactCreate(profile: CharacterProfileFields, isCoreCharacter: boolean, fields: readonly CharacterFactField[]): { candidate: CharacterFactCreateDataV1; after: CharacterFactValuesV1 } {
  if (fields.some((field) => !CHARACTER_PROFILE_FACT_FIELDS.includes(field)) || new Set(fields).size !== fields.length) throw new Error("CHARACTER_FACT_PREPARATION_INVALID");
  const candidate: CharacterFactCreateDataV1 = {
    name: profile.name, aliases: [...profile.aliases], role_type: profile.role_type,
    importance_level: profile.importance_level, is_core_character: isCoreCharacter,
    conflict_with_mainline: profile.conflict_with_mainline, relationship_with_protagonist: profile.relationship_with_protagonist,
    initial_state: profile.initial_state, growth_direction: profile.growth_direction,
    story_function: profile.story_function, arc_seed: profile.arc_seed, tags: [...profile.tags], sort_order: 0,
  };
  const after = Object.fromEntries(fields.map((field) => [field, structuredClone(profile[field as keyof CharacterProfileFields])])) as CharacterFactValuesV1;
  return { candidate, after };
}

/** 功能：逐人另建稿只复制档案白名单，原候选与绑定继续保留。Args: 当前候选。Returns: 独立作者档案。 */
export function profileForCharacterFactDraft(candidate: CharacterProfileFields): CharacterProfileFields {
  return Object.fromEntries(Object.keys(createEmptyCharacterProfile()).map((field) => [field, structuredClone(candidate[field as keyof CharacterProfileFields])])) as unknown as CharacterProfileFields;
}
