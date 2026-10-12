/** MongoDB ObjectId 在公开 API 中的 24 位十六进制字符串。 */
export type ObjectIdString = string & { readonly __brand: "ObjectIdString" };

/** 当前已实现及新版预留的稳定业务实体类型。 */
export type BusinessEntityType =
  | "faction"
  | "faction_relation"
  | "character"
  | "character_relation"
  | "character_faction_binding"
  | "world_rule"
  | "location"
  | "item"
  | "foreshadowing";

/** 经实体类型校验的正式业务 ID。 */
export type BusinessId = string & { readonly __brand: "BusinessId" };

/** 仅在单次 AI 结果与确认 DTO 内使用的浏览器局部引用。 */
export type LocalCandidateRef = string & { readonly __brand: "LocalCandidateRef" };

const OBJECT_ID_PATTERN = /^[0-9a-fA-F]{24}$/;
const LOCAL_CANDIDATE_REF_PATTERN = /^[a-z][a-z0-9]*(?:_[a-z0-9]+){1,5}$/;

const BUSINESS_ID_PATTERNS: Readonly<Record<BusinessEntityType, RegExp>> = {
  faction: /^fac_[0-9]{6,}$/,
  faction_relation: /^fr_[0-9]{6,}$/,
  character: /^char_[0-9]{6,}$/,
  character_relation: /^cr_[0-9]{6,}$/,
  character_faction_binding: /^cfb_[0-9]{6,}$/,
  world_rule: /^rule_[0-9]{6,}$/,
  location: /^loc_[0-9]{6,}$/,
  item: /^item_[0-9]{6,}$/,
  foreshadowing: /^fo_[0-9]{6,}$/,
};

/**
 * 功能：判断未知值是否为公开 ObjectId 字符串。
 * Args:
 *   value: API、路由参数或本地状态中的未知值。
 * Returns:
 *   值为 24 位十六进制字符串时返回 true，并收窄类型。
 */
export function isObjectIdString(value: unknown): value is ObjectIdString {
  return typeof value === "string" && OBJECT_ID_PATTERN.test(value);
}

/**
 * 功能：按实体类型判断未知值是否为正式业务 ID。
 * Args:
 *   entityType: 当前引用允许的业务实体类型。
 *   value: API、选择器或候选确认 DTO 中的未知值。
 * Returns:
 *   前缀与至少六位序号均符合当前领域约定时返回 true。
 */
export function isBusinessId(
  entityType: BusinessEntityType,
  value: unknown
): value is BusinessId {
  return typeof value === "string" && BUSINESS_ID_PATTERNS[entityType].test(value);
}

/**
 * 功能：判断未知值是否为单次结果内的候选局部引用。
 * Args:
 *   value: AI 响应或浏览器候选中的未知引用。
 * Returns:
 *   值使用安全局部命名且不冒充任一正式业务 ID 时返回 true。
 */
export function isLocalCandidateRef(value: unknown): value is LocalCandidateRef {
  if (typeof value !== "string" || !LOCAL_CANDIDATE_REF_PATTERN.test(value)) {
    return false;
  }
  // 正式 ID 与候选引用使用互斥命名空间，避免局部 ref 被误提交为外键。
  return !Object.values(BUSINESS_ID_PATTERNS).some((pattern) => pattern.test(value));
}

/**
 * 功能：构造选择器与关系端点统一使用的“名称 · ID”显示文本。
 * Args:
 *   displayName: 用户可读的实体名称。
 *   stableId: 实体的正式稳定 ID。
 * Returns:
 *   不改变引用语义的名称与 ID 组合文本。
 */
export function formatStableReferenceLabel(
  displayName: string,
  stableId: ObjectIdString | BusinessId | string
): string {
  return `${displayName.trim()} · ${stableId}`;
}
