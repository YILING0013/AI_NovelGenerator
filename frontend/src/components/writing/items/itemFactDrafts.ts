import type { ItemFactPreviewV1, ItemFactValuesV1, ItemFactConfirmV1, ItemFactResultV1, ItemFactBatchPreviewV1, ItemFactBatchConfirmV1, ItemFactBatchResultV1 } from "@/types/itemFacts";
import type { ItemFactPreparationV1 } from "./itemFactPreparation";

export interface ItemFactCommandV1 {
  schema_id: "item.fact.command"; schema_version: 1; key: string; positionLabel: string;
  body: ItemFactConfirmV1; unknown: boolean; saved?: ItemFactResultV1; readbackDone?: boolean;
}
export interface ItemFactDraftV1 {
  schema_id: "item.fact.draft"; schema_version: 1; key: string; revision: number; positionLabel: string;
  preview: ItemFactPreviewV1; after: ItemFactValuesV1; reason: string; authorConfirmed: boolean;
  origin?: { scope: string; draftKey: string; reviewId?: string };
  preparation?: ItemFactPreparationV1;
  reprepared?: string;
  returnedToCheck?: boolean;
  command?: ItemFactCommandV1;
}
export interface ItemFactBatchCommandV1 {
  schema_id: "item.fact.batch.command"; schema_version: 1; key: string; positionLabel: string;
  body: ItemFactBatchConfirmV1; unknown: boolean; saved?: ItemFactBatchResultV1; readbackDone?: boolean;
}
export interface ItemFactBatchDraftV1 {
  schema_id: "item.fact.batch.draft"; schema_version: 1; key: string; revision: number; positionLabel: string;
  preview: ItemFactBatchPreviewV1; authorConfirmed: boolean; command?: ItemFactBatchCommandV1;
  preparation?: ItemFactPreparationV1;
  reprepared?: string;
  returnedToCheck?: boolean;
}

/** 功能：冻结单件或整批作者确认，状态、位置、原键随后不可替换。Args: 原预览稿和首次确认键。Returns: 须先本地登记的原请求。 */
export function freezeItemFactDraft<D extends ItemFactDraftV1 | ItemFactBatchDraftV1>(draft: D, key: string): D {
  if (draft.command) return draft;
  if (!draft.authorConfirmed) throw new Error("ITEM_FACT_CONFIRMATION_REQUIRED");
  if (draft.schema_id === "item.fact.batch.draft") {
    const body: ItemFactBatchConfirmV1 = { generation: structuredClone(draft.preview.generation), confirmed: true,
      entries: draft.preview.entries.map((entry) => ({ candidate_ref: entry.candidate_ref, command: { operation: "create", basis: structuredClone(entry.preview.basis), after: structuredClone(entry.after), confirmed: true } })) };
    return { ...draft, revision: draft.revision + 1, command: { schema_id: "item.fact.batch.command", schema_version: 1, key, positionLabel: draft.positionLabel, body, unknown: true } } as D;
  }
  const basis = draft.preview.basis;
  const body: ItemFactConfirmV1 = { operation: basis.operation, basis: structuredClone(basis), confirmed: true };
  if (basis.target.kind === "existing") body.expected_version = basis.target.version;
  if (basis.operation === "void") {
    if (!draft.reason.trim() || !basis.void_target) throw new Error("ITEM_FACT_REASON_REQUIRED");
    body.history_id = basis.void_target; body.reason = draft.reason;
  } else body.after = structuredClone(draft.after);
  return { ...draft, revision: draft.revision + 1, command: { schema_id: "item.fact.command", schema_version: 1, key, positionLabel: draft.positionLabel, body, unknown: true } } as D;
}
