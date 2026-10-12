import type { CharacterFactCommandV1, CharacterFactDraftV1 } from "./characterFactDrafts";
import { readFactDrafts, writeFactDraft, writeFactReceipt, type FactDraftWriteResult } from "./factDraftStorage";

export type CharacterFactDraftWriteResult = FactDraftWriteResult<CharacterFactDraftV1>;

/** 功能：恢复本域原稿和独立成功回执。Args: 固定小说范围。Returns: 仍须读回当前资料的原稿。 */
export function readCharacterFactDrafts(scope: string): Promise<CharacterFactDraftV1[]> {
  return readFactDrafts<CharacterFactDraftV1>("character", scope);
}

/** 功能：比较本地版本并登记原命令。Args: 范围、原稿、持有版本及是否清理。Returns: 写入结果与已知首次成功。 */
export function writeCharacterFactDraft(scope: string, draft: CharacterFactDraftV1, expectedRevision: number | null, remove = false): Promise<CharacterFactDraftWriteResult> {
  return writeFactDraft("character", scope, draft, expectedRevision, remove);
}

/** 功能：保存原命令的独立成功回执。Args: 范围及原命令。Returns: 已登记原请求的首次成功。 */
export function writeCharacterFactReceipt(scope: string, command: CharacterFactCommandV1) {
  return writeFactReceipt("character", scope, command);
}
