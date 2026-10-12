import type { WritingDraft } from "@/lib/writingDrafts";
import type { CharacterFactConfirmV1, CharacterFactPreviewV1, CharacterFactResultV1, CharacterFactValuesV1 } from "@/types/characterFacts";

/** 人物事实的独立冻结请求；成功回执另存，不能受草稿编辑权变化影响。 */
export interface CharacterFactCommandV1 {
  schema_id: "character.fact.command";
  schema_version: 1;
  key: string;
  positionLabel: string;
  body: CharacterFactConfirmV1;
  unknown: boolean;
  saved?: CharacterFactResultV1;
  readbackDone?: boolean;
}

/** 已取得人工预览的独立稿；不复用旧章后稿或卷状态身份。 */
export interface CharacterFactDraftV1 {
  schema_id: "character.fact.draft";
  schema_version: 1;
  key: string;
  revision: number;
  /** 预览时的目录标题，仅用于展示；服务端依据仍为 preview.basis.position。 */
  positionLabel: string;
  preview: CharacterFactPreviewV1;
  after: CharacterFactValuesV1;
  reason: string;
  authorConfirmed: boolean;
  command?: CharacterFactCommandV1;
}

/** 沿用 IDB v3 的 business_drafts；物理键分别以稿 ID 和原请求键结尾。 */
export type CharacterFactDraftEntryV1 = WritingDraft<CharacterFactDraftV1>;
export type CharacterFactCommandEntryV1 = WritingDraft<CharacterFactCommandV1> & { draft_key: string };

/** 功能：固定本书事实稿范围，切人物或来源章不移动原稿。Args: novelId 小说身份。Returns: 与章后旧稿隔离的范围。 */
export function characterFactDraftScope(novelId: string): string {
  return `${novelId}:character-facts`;
}

/**
 * 功能：固定作者当前确认的完整请求；已有请求始终原样返回。
 * Args: draft 已预览且经作者勾选的稿；key 新操作的幂等键。
 * Returns: 含冻结请求的新稿。调用方仍须完成本地登记事务后才能发送。
 */
export function freezeCharacterFactDraft(draft: CharacterFactDraftV1, key: string): CharacterFactDraftV1 {
  if (draft.command) return draft;
  if (!draft.authorConfirmed) throw new Error("CHARACTER_FACT_CONFIRMATION_REQUIRED");
  const basis = draft.preview.basis;
  if (!Array.isArray(basis.legacy_sources)) throw new Error("CHARACTER_FACT_CONTRACT_REQUIRED");
  let body: CharacterFactConfirmV1;
  if (basis.operation === "void") {
    if (!draft.reason.trim()) throw new Error("CHARACTER_FACT_REASON_REQUIRED");
    body = { operation: "void", basis, expected_version: basis.target.version, targets: basis.void_targets, reason: draft.reason, confirmed: true };
  } else {
    const fields = Object.keys(draft.after);
    if (fields.length !== basis.fields.length || fields.some((field) => !basis.fields.includes(field as keyof CharacterFactValuesV1) || draft.after[field as keyof CharacterFactValuesV1] === undefined)) {
      throw new Error("CHARACTER_FACT_VALUES_REQUIRED");
    }
    switch (basis.operation) {
      case "create":
        body = { operation: "create", basis, after: draft.after, confirmed: true };
        break;
      case "establish":
        body = { operation: "establish", basis, expected_version: basis.target.version, after: draft.after, confirmed: true };
        break;
      case "correct_initial":
        body = { operation: "correct_initial", basis, expected_version: basis.target.version, after: draft.after, confirmed: true };
        break;
      case "change":
        body = { operation: "change", basis, expected_version: basis.target.version, after: draft.after, confirmed: true };
        break;
      case "replace":
        body = { operation: "replace", basis, expected_version: basis.target.version, after: draft.after, confirmed: true };
        break;
    }
  }
  // body 与仍可导出的作者稿分开，后续对象改动不能改变原请求或原依据。
  return { ...draft, revision: draft.revision + 1, command: { schema_id: "character.fact.command", schema_version: 1, key, positionLabel: draft.positionLabel, body: structuredClone(body), unknown: true } };
}
