import type { CharacterRelationType, IsoDateTime } from "@/types/character";
import type {
  CharacterFactActiveV1, CharacterFactAuthorSourceV1, CharacterFactDirectoryEntryV1,
  CharacterFactPositionV1, CharacterFactProtectedSourceV1, CharacterFactReadPositionV1,
  CharacterFactReplacedV1, CharacterFactSourceObservationV1, CharacterFactSourceV1,
  CharacterFactUnknownReason, CharacterFactValidityV1, CharacterFactVoidedV1,
} from "@/types/characterFacts";

/** 关系事实只认领当前状态；关系设计和管理启停不属于剧情事实。 */
export type CharacterRelationFactField = "current_state";
export type CharacterRelationFactOperation = "create" | "establish" | "correct_initial" | "change" | "replace" | "void";
export type CharacterRelationFactUnknownReason = CharacterFactUnknownReason;
export type CharacterRelationFactPositionV1 = CharacterFactPositionV1;
export type CharacterRelationFactReadPositionV1 = CharacterFactReadPositionV1;
export type CharacterRelationFactSourceV1 = CharacterFactSourceV1;
export type CharacterRelationFactAuthorSourceV1 = CharacterFactAuthorSourceV1;
export type CharacterRelationFactValidityV1 = CharacterFactValidityV1;

/** 缺项表示未知；已知状态必须为 1–2000 字非空文字，不接受 null 或空白。 */
export interface CharacterRelationFactValuesV1 { current_state?: string }
export type CharacterRelationFactStoredValuesV1 = CharacterRelationFactValuesV1;

/** 已知文字和未知原因分开保存，不能用裸主档补未知值。 */
export interface CharacterRelationFactBeforeV1 {
  values: CharacterRelationFactStoredValuesV1;
  unknown: Partial<Record<CharacterRelationFactField, CharacterRelationFactUnknownReason>>;
}

/** 一次关系状态记录保存当时两端人物的物理身份和名称。 */
export interface CharacterRelationFactRecordV1 {
  schema_id: "character_relation.fact";
  schema_version: 1;
  history_id: string;
  novel_id: string;
  entity_type: "character_relation";
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  source_character_entity_id: string;
  source_character_name: string;
  target_character_id: string;
  target_character_entity_id: string;
  target_character_name: string;
  operation: Exclude<CharacterRelationFactOperation, "void">;
  kind: "start" | "change";
  position: CharacterRelationFactPositionV1;
  source: CharacterRelationFactSourceV1;
  before_version: number | null;
  after_version: number;
  before: CharacterRelationFactBeforeV1;
  after: Required<CharacterRelationFactStoredValuesV1>;
  previous: Record<CharacterRelationFactField, string | null>;
  replaces: Partial<Record<CharacterRelationFactField, string>>;
  resolves: Partial<Record<CharacterRelationFactField, string[]>>;
  validity: Record<CharacterRelationFactField, CharacterRelationFactValidityV1>;
  protected_sources: CharacterFactProtectedSourceV1[];
  confirmed_at: IsoDateTime;
}

/** 指定位置的结果；来源只引用正式记录，停用不会被解释为剧情结束。 */
export interface CharacterRelationFactsAtPositionV1 {
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  target_character_id: string;
  version: number;
  values: CharacterRelationFactStoredValuesV1;
  unknown: Partial<Record<CharacterRelationFactField, CharacterRelationFactUnknownReason>>;
  blockers: Partial<Record<CharacterRelationFactField, string[]>>;
  origins: Partial<Record<CharacterRelationFactField, string>>;
  claimed_fields: CharacterRelationFactField[];
}

/** 原读取中的人物身份与管理状态；历史查询保留停用或回收信息。 */
export interface CharacterRelationFactEndpointReadV1 {
  entity_id: string;
  character_id: string;
  name: string;
  status: "active" | "inactive";
  is_deleted: boolean;
}
export interface CharacterRelationFactEndpointV1 extends CharacterRelationFactEndpointReadV1 { version: number }

/** 原读取的关系身份，不包含裸 current_state。 */
export interface CharacterRelationFactIdentityReadV1 {
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  target_character_id: string;
  is_active: boolean;
  is_deleted: boolean;
}

/** 历史摘要保留当时的版本与有效性，包括替代和作废记录。 */
export interface CharacterRelationFactHistoryObservationV1 {
  history_id: string;
  entity_id: string;
  relation_id: string;
  after_version: number;
  immutable_fingerprint: string;
  validity: Record<CharacterRelationFactField, CharacterRelationFactValidityV1>;
}

/** 原选择、完整目录和累计历史必须原样复验，空选择也保留。 */
export interface CharacterRelationFactReadV1 {
  kind: "character_relation_facts";
  novel_id: string;
  relation_ids: string[];
  position: CharacterRelationFactReadPositionV1;
  directory: CharacterFactDirectoryEntryV1[];
  identities: CharacterRelationFactIdentityReadV1[];
  endpoints: CharacterRelationFactEndpointReadV1[];
  history: CharacterRelationFactHistoryObservationV1[];
  sources: CharacterFactSourceObservationV1[];
  fingerprint: string;
}

/** 缺失关系与已找到的关系分开返回，不以空结果代表空关系。 */
export interface CharacterRelationFactReadResultV1 {
  novel_id: string;
  position: CharacterRelationFactReadPositionV1;
  relations: CharacterRelationFactsAtPositionV1[];
  missing_relation_ids: string[];
  reads: CharacterRelationFactReadV1[];
}

/** 明确选择关系；省略位置只由服务端解析一次最新位置。 */
export interface CharacterRelationFactQueryV1 {
  relation_ids: string[];
  position?: CharacterRelationFactPositionV1 | null;
}

/** 新建只在候选提供两端和六项设计，状态由作者 after 提交。 */
export interface CharacterRelationFactCreateDataV1 {
  source_character_id: string;
  target_character_id: string;
  relation_type: CharacterRelationType;
  core_conflict: string;
  hidden_tension: string;
  possible_change: string;
  story_value: string;
  intensity: number;
  sort_order?: number;
}

/** 既有目标冻结两端身份和原版本，不能按今日名字重新绑定。 */
export interface CharacterRelationFactExistingTargetV1 {
  kind: "existing";
  novel_id: string;
  entity_id: string;
  relation_id: string;
  version: number;
  source_character: CharacterRelationFactEndpointV1;
  target_character: CharacterRelationFactEndpointV1;
}

/** 新建预览只保留待用物理 ID；对称端点顺序由后端固定，不预占业务号。 */
export interface CharacterRelationFactNewTargetV1 {
  kind: "new";
  novel_id: string;
  entity_id: string;
  candidate: CharacterRelationFactCreateDataV1;
  source_character: CharacterRelationFactEndpointV1;
  target_character: CharacterRelationFactEndpointV1;
  entity_exists: false;
  semantic_matches: [];
}
export type CharacterRelationFactTargetV1 = CharacterRelationFactExistingTargetV1 | CharacterRelationFactNewTargetV1;

/** 预览输入只提供实际关系和原版本，不允许换端点。 */
export interface CharacterRelationFactPreviewExistingTargetV1 {
  entity_id: string;
  relation_id: string;
  expected_version: number;
}
export interface CharacterRelationFactPreviewNewTargetV1 { candidate: CharacterRelationFactCreateDataV1 }

export interface CharacterRelationFactCreatePreviewInputV1 {
  operation: "create";
  target: CharacterRelationFactPreviewNewTargetV1;
  position: CharacterRelationFactPositionV1;
  source: CharacterRelationFactAuthorSourceV1;
  fields: [CharacterRelationFactField];
}
export interface CharacterRelationFactExistingPreviewInputV1 {
  operation: "establish" | "correct_initial" | "change" | "replace";
  target: CharacterRelationFactPreviewExistingTargetV1;
  kind: "start" | "change";
  position: CharacterRelationFactPositionV1;
  source: CharacterRelationFactSourceV1;
  fields: [CharacterRelationFactField];
  replaces?: Partial<Record<CharacterRelationFactField, string>>;
  resolves?: Partial<Record<CharacterRelationFactField, string[]>>;
}
export interface CharacterRelationFactVoidPreviewInputV1 {
  operation: "void";
  target: CharacterRelationFactPreviewExistingTargetV1;
  targets: Record<CharacterRelationFactField, string>;
}
export type CharacterRelationFactPreviewInputV1 = CharacterRelationFactCreatePreviewInputV1 | CharacterRelationFactExistingPreviewInputV1 | CharacterRelationFactVoidPreviewInputV1;

/** 作者看过的完整依据；旧裸值只作参考，不能冒充该位置前值。 */
export type CharacterRelationFactBasisV1 = {
  schema_version: 1;
  kind: "start" | "change";
  position: CharacterRelationFactPositionV1;
  source: CharacterRelationFactSourceV1;
  fields: [CharacterRelationFactField];
  before: CharacterRelationFactBeforeV1;
  previous: Record<CharacterRelationFactField, string | null>;
  replaces: Partial<Record<CharacterRelationFactField, string>>;
  resolves: Partial<Record<CharacterRelationFactField, string[]>>;
  void_targets: Partial<Record<CharacterRelationFactField, string>>;
  targets: CharacterRelationFactRecordV1[];
  blockers: Partial<Record<CharacterRelationFactField, string[]>>;
  field_sources: CharacterRelationFactRecordV1[];
  legacy_values: CharacterRelationFactStoredValuesV1;
  reads: CharacterRelationFactReadV1[];
  protected_sources: CharacterFactProtectedSourceV1[];
  fingerprint: string;
} & (
  | { operation: "create"; target: CharacterRelationFactNewTargetV1 }
  | { operation: "establish"; target: CharacterRelationFactExistingTargetV1 }
  | { operation: "correct_initial"; target: CharacterRelationFactExistingTargetV1 }
  | { operation: "change"; target: CharacterRelationFactExistingTargetV1 }
  | { operation: "replace"; target: CharacterRelationFactExistingTargetV1 }
  | { operation: "void"; target: CharacterRelationFactExistingTargetV1 }
);

export interface CharacterRelationFactPreviewV1 {
  basis: CharacterRelationFactBasisV1;
  values: CharacterRelationFactBeforeV1;
}
export interface CharacterRelationFactCreateConfirmV1 {
  operation: "create";
  basis: CharacterRelationFactBasisV1 & { operation: "create"; target: CharacterRelationFactNewTargetV1 };
  after: Required<CharacterRelationFactValuesV1>;
  confirmed: true;
}
export type CharacterRelationFactExistingConfirmV1 = {
  expected_version: number;
  after: Required<CharacterRelationFactValuesV1>;
  confirmed: true;
} & (
  | { operation: "establish"; basis: CharacterRelationFactBasisV1 & { operation: "establish"; target: CharacterRelationFactExistingTargetV1 } }
  | { operation: "correct_initial"; basis: CharacterRelationFactBasisV1 & { operation: "correct_initial"; target: CharacterRelationFactExistingTargetV1 } }
  | { operation: "change"; basis: CharacterRelationFactBasisV1 & { operation: "change"; target: CharacterRelationFactExistingTargetV1 } }
  | { operation: "replace"; basis: CharacterRelationFactBasisV1 & { operation: "replace"; target: CharacterRelationFactExistingTargetV1 } }
);
export interface CharacterRelationFactVoidConfirmV1 {
  operation: "void";
  basis: CharacterRelationFactBasisV1 & { operation: "void"; target: CharacterRelationFactExistingTargetV1 };
  expected_version: number;
  targets: Record<CharacterRelationFactField, string>;
  reason: string;
  confirmed: true;
}
export type CharacterRelationFactConfirmV1 = CharacterRelationFactCreateConfirmV1 | CharacterRelationFactExistingConfirmV1 | CharacterRelationFactVoidConfirmV1;

/** 作废只改变原记录有效性，不伪造一条变化记录。 */
export interface CharacterRelationFactValidityChangeV1 {
  history_id: string;
  field: CharacterRelationFactField;
  before: CharacterFactActiveV1;
  after: CharacterFactReplacedV1 | CharacterFactVoidedV1;
}

/** 首次成功快照随后只用于回执核对；当前事实须单独读取。 */
export interface CharacterRelationFactResultV1 {
  schema_version: 1;
  operation: CharacterRelationFactOperation;
  novel_id: string;
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  source_character_entity_id: string;
  source_character_name: string;
  target_character_id: string;
  target_character_entity_id: string;
  target_character_name: string;
  before_version: number | null;
  after_version: number;
  record: CharacterRelationFactRecordV1 | null;
  validity_changes: CharacterRelationFactValidityChangeV1[];
  confirmed_at: IsoDateTime;
}
