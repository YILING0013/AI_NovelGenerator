import type { WritingDraft } from "@/lib/writingDrafts";
import type { FactionFactConfirmV1, FactionFactPreviewV1, FactionFactResultV1, FactionFactValuesV1 } from "@/types/factionFacts";

/** 势力事实的独立冻结请求；成功回执另存，不能受草稿编辑权变化影响。 */
export interface FactionFactCommandV1 {
  schema_id: "faction.fact.command";
  schema_version: 1;
  key: string;
  positionLabel: string;
  body: FactionFactConfirmV1;
  unknown: boolean;
  saved?: FactionFactResultV1;
  readbackDone?: boolean;
}

/** 已取得人工预览的独立稿；不复用旧章后稿或卷状态身份。 */
export interface FactionFactDraftV1 {
  schema_id: "faction.fact.draft";
  schema_version: 1;
  key: string;
  revision: number;
  /** 预览时的目录标题，仅用于展示；服务端依据仍为 preview.basis.position。 */
  positionLabel: string;
  preview: FactionFactPreviewV1;
  after: FactionFactValuesV1;
  reason: string;
  authorConfirmed: boolean;
  command?: FactionFactCommandV1;
  reprepared?: string;
}

/** 沿用 IDB v3 的 business_drafts；物理键分别以稿 ID 和原请求键结尾。 */
export type FactionFactDraftEntryV1 = WritingDraft<FactionFactDraftV1>;
export type FactionFactCommandEntryV1 = WritingDraft<FactionFactCommandV1> & { draft_key: string };

/** 功能：固定本书事实稿范围，切势力或来源章不移动原稿。Args: novelId 小说身份。Returns: 与章后旧稿隔离的范围。 */
export function factionFactDraftScope(novelId: string): string {
  return `${novelId}:faction-facts`;
}

/**
 * 功能：固定作者当前确认的完整请求；已有请求始终原样返回。
 * Args: draft 已预览且经作者勾选的稿；key 新操作的幂等键。
 * Returns: 含冻结请求的新稿。调用方仍须完成本地登记事务后才能发送。
 */
export function freezeFactionFactDraft(draft: FactionFactDraftV1, key: string): FactionFactDraftV1 {
  if (draft.reprepared) throw new Error("FACTION_FACT_REPREPARED");
  if (draft.command) return draft;
  if (!draft.authorConfirmed) throw new Error("FACTION_FACT_CONFIRMATION_REQUIRED");
  const basis = draft.preview.basis;
  if (!Array.isArray(basis.legacy_sources)) throw new Error("FACTION_FACT_CONTRACT_REQUIRED");
  let body: FactionFactConfirmV1;
  if (basis.operation === "void") {
    if (!draft.reason.trim()) throw new Error("FACTION_FACT_REASON_REQUIRED");
    body = { operation: "void", basis, expected_version: basis.target.version, targets: basis.void_targets, reason: draft.reason, confirmed: true };
  } else {
    const fields = Object.keys(draft.after);
    if (fields.length !== basis.fields.length || fields.some((field) => !basis.fields.includes(field as keyof FactionFactValuesV1) || draft.after[field as keyof FactionFactValuesV1] === undefined)) {
      throw new Error("FACTION_FACT_VALUES_REQUIRED");
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
  return { ...draft, revision: draft.revision + 1, command: { schema_id: "faction.fact.command", schema_version: 1, key, positionLabel: draft.positionLabel, body: structuredClone(body), unknown: true } };
}
