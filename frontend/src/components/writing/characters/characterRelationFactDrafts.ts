import type { WritingDraft } from "@/lib/writingDrafts";
import type { CharacterRelationFactConfirmV1, CharacterRelationFactPreviewV1, CharacterRelationFactResultV1, CharacterRelationFactValuesV1 } from "@/types/characterRelationFacts";

/** 原确认命令独立登记；后来的编辑权变化不影响成功回执。 */
export interface CharacterRelationFactCommandV1 {
  schema_id: "character_relation.fact.command";
  schema_version: 1;
  key: string;
  positionLabel: string;
  body: CharacterRelationFactConfirmV1;
  unknown: boolean;
  saved?: CharacterRelationFactResultV1;
  readbackDone?: boolean;
}

/** 每份人工预览有独立稿 ID 与版本，不能继承旧 D 确认键。 */
export interface CharacterRelationFactDraftV1 {
  schema_id: "character_relation.fact.draft";
  schema_version: 1;
  key: string;
  revision: number;
  positionLabel: string;
  preview: CharacterRelationFactPreviewV1;
  after: CharacterRelationFactValuesV1;
  reason: string;
  authorConfirmed: boolean;
  /** 原建议只作来源，人工依据和确认请求仍保存在本稿。 */
  origin?: { scope: string; draftKey: string; candidateRef?: string };
  command?: CharacterRelationFactCommandV1;
}
export type CharacterRelationFactDraftEntryV1 = WritingDraft<CharacterRelationFactDraftV1>;
export type CharacterRelationFactCommandEntryV1 = WritingDraft<CharacterRelationFactCommandV1> & { draft_key: string };

/** 功能：固定关系事实范围，与人物草稿隔离。Args: 小说 ID。Returns: 原书范围键。 */
export function characterRelationFactDraftScope(novelId: string): string {
  return `${novelId}:character-relation-facts`;
}

/** 功能：冻结作者确认的原请求和原键。Args: 已预览且已勾选的稿、新命令键。Returns: 须先落盘再发送的冻结稿。 */
export function freezeCharacterRelationFactDraft(draft: CharacterRelationFactDraftV1, key: string): CharacterRelationFactDraftV1 {
  if (draft.command) return draft;
  if (!draft.authorConfirmed) throw new Error("CHARACTER_RELATION_FACT_CONFIRMATION_REQUIRED");
  const basis = draft.preview.basis;
  let body: CharacterRelationFactConfirmV1;
  if (basis.operation === "void") {
    if (!draft.reason.trim() || Array.from(draft.reason.trim()).length > 2000) throw new Error("CHARACTER_RELATION_FACT_REASON_REQUIRED");
    const historyId = basis.void_targets.current_state;
    if (!historyId) throw new Error("CHARACTER_RELATION_FACT_TARGET_REQUIRED");
    body = { operation: "void", basis, expected_version: basis.target.version, targets: { current_state: historyId }, reason: draft.reason, confirmed: true };
  } else {
    const value = draft.after.current_state;
    if (basis.fields.length !== 1 || basis.fields[0] !== "current_state" || Object.keys(draft.after).length !== 1
      || typeof value !== "string" || !value.trim() || Array.from(value.trim()).length > 2000) {
      throw new Error("CHARACTER_RELATION_FACT_VALUES_REQUIRED");
    }
    const after = { current_state: value };
    switch (basis.operation) {
      case "create": body = { operation: "create", basis, after, confirmed: true }; break;
      case "establish": body = { operation: "establish", basis, expected_version: basis.target.version, after, confirmed: true }; break;
      case "correct_initial": body = { operation: "correct_initial", basis, expected_version: basis.target.version, after, confirmed: true }; break;
      case "change": body = { operation: "change", basis, expected_version: basis.target.version, after, confirmed: true }; break;
      case "replace": body = { operation: "replace", basis, expected_version: basis.target.version, after, confirmed: true }; break;
    }
  }
  // 请求与可编辑对象分离；作者再改原稿不能改变已登记的请求。
  return { ...draft, revision: draft.revision + 1, command: { schema_id: "character_relation.fact.command", schema_version: 1, key, positionLabel: draft.positionLabel, body: structuredClone(body), unknown: true } };
}
