export type InitializationStepKey =
  | "novel_profile"
  | "core_factions"
  | "faction_relations"
  | "protagonist"
  | "core_characters"
  | "character_bindings"
  | "character_relations";

export type InitializationStepState =
  | "not_started"
  | "in_progress"
  | "ready"
  | "blocked";

export interface InitializationStepV1 {
  key: InitializationStepKey;
  state: InitializationStepState;
  count: number;
  blockers: string[];
  href: string;
}

export interface InitializationReadinessResponseV1 {
  novel_id: string;
  steps: InitializationStepV1[];
  ready_for_world_and_volume: boolean;
}

