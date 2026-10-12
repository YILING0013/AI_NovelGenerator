import type { ItemFieldsV1, ItemBulkGeneratedRequestV1, ItemBulkGeneratedResponseV1 } from "./item";
import type { CharacterFactPositionV1, CharacterFactReadPositionV1, CharacterFactSourceV1, CharacterFactUnknownReason, CharacterFactValidityV1, CharacterFactProtectedSourceV1, CharacterFactDirectoryEntryV1, CharacterFactSourceObservationV1 } from "./characterFacts";

export type ItemFactValuesV1 = Pick<ItemFieldsV1, "lifecycle_status" | "owner_character_id" | "controlling_faction_id" | "current_location_id">;
export type ItemFactDesignV1 = Omit<ItemFieldsV1, keyof ItemFactValuesV1>;
export type ItemFactOperation = "create" | "establish" | "correct_initial" | "change" | "replace" | "void";
export interface ItemFactBeforeV1 { values: ItemFactValuesV1 | null; unknown: CharacterFactUnknownReason | null }
export interface ItemFactRecordV1 {
  schema_id: "item.fact"; schema_version: 1; history_id: string; novel_id: string; entity_type: "item";
  entity_id: string; item_id: string; item_name: string; operation: Exclude<ItemFactOperation, "void">;
  kind: "start" | "change"; position: CharacterFactPositionV1; source: CharacterFactSourceV1;
  before_version: number | null; after_version: number; before: ItemFactBeforeV1; after: ItemFactValuesV1;
  previous: string | null; replaces: string | null; resolves: string[]; validity: CharacterFactValidityV1;
  protected_sources: CharacterFactProtectedSourceV1[]; confirmed_at: string;
}
export interface ItemFactsAtPositionV1 extends ItemFactBeforeV1 {
  entity_id: string; item_id: string; name: string; version: number; origin: string | null; blockers: string[]; claimed: boolean;
}
export interface ItemFactReferenceV1 {
  resource_type: "character" | "faction" | "location"; business_id: string; entity_id: string | null;
  version: number | null; is_deleted: boolean | null; status: string | null; available: boolean;
}
export interface ItemFactReadV1 {
  kind: "item_facts"; novel_id: string; item_ids: string[]; position: CharacterFactReadPositionV1;
  directory: CharacterFactDirectoryEntryV1[];
  identities: { entity_id: string; item_id: string; name: string; version: number; is_deleted: boolean }[];
  records: ItemFactRecordV1[]; sources: CharacterFactSourceObservationV1[]; references: ItemFactReferenceV1[]; fingerprint: string;
}
export interface ItemFactReadResultV1 {
  novel_id: string; position: CharacterFactReadPositionV1; items: ItemFactsAtPositionV1[]; missing_item_ids: string[]; read: ItemFactReadV1;
}
export type ItemFactTargetV1 = { kind: "new"; novel_id: string; entity_id: string; candidate: ItemFactDesignV1 }
  | { kind: "existing"; novel_id: string; entity_id: string; item_id: string; name: string; version: number; is_deleted: boolean };
export interface ItemFactBasisV1 {
  schema_version: 1; operation: ItemFactOperation; kind: "start" | "change"; target: ItemFactTargetV1;
  position: CharacterFactPositionV1; source: CharacterFactSourceV1; before: ItemFactBeforeV1;
  previous: string | null; blockers: string[]; replaces: string | null; resolves: string[]; void_target: string | null;
  legacy_values: ItemFactValuesV1 | null;
  reference_selection: Omit<ItemFactValuesV1, "lifecycle_status"> | null;
  preview_references: ItemFactReferenceV1[]; read: ItemFactReadV1; protected_sources: CharacterFactProtectedSourceV1[]; fingerprint: string;
}
export interface ItemFactPreviewV1 { basis: ItemFactBasisV1; values: ItemFactBeforeV1 }
export type ItemFactConfirmV1 = { operation: ItemFactOperation; basis: ItemFactBasisV1; confirmed: true; expected_version?: number; after?: ItemFactValuesV1; history_id?: string; reason?: string };
export interface ItemFactResultV1 {
  schema_version: 1; operation: ItemFactOperation; novel_id: string; entity_id: string; item_id: string; item_name: string;
  before_version: number | null; after_version: number; record: ItemFactRecordV1 | null;
  validity_changes: { history_id: string; before: { state: "active" }; after: CharacterFactValidityV1 }[]; confirmed_at: string;
}
export interface ItemFactBatchPreviewV1 {
  generation: ItemBulkGeneratedRequestV1;
  entries: { candidate_ref: string; preview: ItemFactPreviewV1; after: ItemFactValuesV1 }[];
}
export interface ItemFactBatchConfirmV1 {
  generation: ItemBulkGeneratedRequestV1;
  entries: { candidate_ref: string; command: ItemFactConfirmV1 }[];
  confirmed: true;
}
export type ItemFactBatchResultV1 = ItemBulkGeneratedResponseV1;
