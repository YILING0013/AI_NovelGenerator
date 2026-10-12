"use client";

import type { CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import { confirmFact, useFactPersistence, type FactConfirmationStage } from "./factConfirmation";

export type CharacterRelationFactConfirmationStage = FactConfirmationStage;

/** 功能：按原队列保存本域草稿与独立回执。Args: 小说范围及失败提示。Returns: 队列、持有版本和保存清理接口。 */
export function useCharacterRelationFactPersistence(scope: string, failureMessage: string) {
  return useFactPersistence<CharacterRelationFactDraftV1>("character_relation", scope, failureMessage);
}

/** 功能：登记后确认原请求，再读回和清理。Args: 原稿和宿主实际发送、读取回调。Returns: 首次成功或明确失败阶段。 */
export function confirmCharacterRelationFact(options: Parameters<typeof confirmFact<CharacterRelationFactDraftV1>>[0]) {
  return confirmFact(options);
}
