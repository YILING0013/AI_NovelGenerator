import type { IsoDateTime } from "@/types/character";
import type { ChapterRecordEntityRefV1, ChapterRecordEvidenceV1 } from "@/types/chapterRecords";

/** 势力确认可接管的十一个实际字段；卷目标计划不在其中。 */
export type FactionFactField = "faction_type" | "positioning" | "organization_style" | "core_values" | "is_public"
  | "actual_goal" | "public_stance" | "power_level" | "resources" | "influence_scope" | "story_status";

/** 未知原因必须明确显示，不能退回普通当前字段补值。 */
export type FactionFactUnknownReason =
  | "nonexistent"
  | "unclaimed"
  | "before_start"
  | "voided"
  | "needs_review"
  | "unresolved_reference";

/** 同一势力一次确认的固定动作。 */
export type FactionFactOperation = "create" | "establish" | "correct_initial" | "change" | "replace" | "void";

/** 只提交明确的已知值；省略、空字符串及空数组不同，不接受 null。 */
export interface FactionFactValuesV1 {
  faction_type?: string;
  positioning?: string;
  organization_style?: string;
  core_values?: string[];
  is_public?: boolean;
  actual_goal?: string;
  public_stance?: string;
  power_level?: number;
  resources?: string[];
  influence_scope?: string;
  story_status?: "active" | "dormant" | "dissolved";
}

/** 历史和冻结依据保留原字符串；前端不能清理空白或补齐缺省值。 */
export type FactionFactStoredValuesV1 = FactionFactValuesV1;

/** 书初使用小说锚，章前后使用章节锚，不保存数字章号。 */
export type FactionFactPositionV1 =
  | { version: 1; intent: "book_start"; target_type: "novel"; target_id: string }
  | { version: 1; intent: "volume_start"; target_type: "volume"; target_id: string }
  | { version: 1; intent: "chapter_before" | "chapter_after"; target_type: "chapter"; target_id: string };

/** 读取沿用 P1 的真实层级和顺序深度，包括空父级的开始与追加。 */
export type FactionFactReadPositionV1 =
  | { version: 1; intent: "book_start"; target_type: "novel"; target_id: string; order: [] }
  | { version: 1; intent: "volume_start" | "replan" | "append"; target_type: "volume"; target_id: string; order: [number] }
  | { version: 1; intent: "replan" | "append"; target_type: "arc"; target_id: string; order: [number, number] }
  | { version: 1; intent: "replan" | "append"; target_type: "scene"; target_id: string; order: [number, number, number] }
  | { version: 1; intent: "chapter_before" | "chapter_after"; target_type: "chapter"; target_id: string; order: [number, number, number, number] };

/** 人工起点只需要作者说明，不伪造章节引文。 */
export interface FactionFactAuthorSourceV1 {
  kind: "author";
  note: string;
}

/** 章后变化使用原不可变修订和码点引文。 */
export interface FactionFactChapterSourceV1 {
  kind: "chapter";
  evidence: ChapterRecordEvidenceV1;
}

/** 作者说明与章节引文按来源类别区分。 */
export type FactionFactSourceV1 = FactionFactAuthorSourceV1 | FactionFactChapterSourceV1;

/** 已知原值与未知字段分别保存，不能为未知字段填猜测值。 */
export interface FactionFactBeforeV1 {
  values: FactionFactStoredValuesV1;
  unknown: Partial<Record<FactionFactField, FactionFactUnknownReason>>;
}

/** 尚未被作者替代或作废的记录字段。 */
export interface FactionFactActiveV1 {
  state: "active";
}

/** 替代只作用于原记录的对应字段。 */
export interface FactionFactReplacedV1 {
  state: "replaced";
  by_history_id: string;
}

/** 作废追溯原成功命令，不反向执行 before。 */
export interface FactionFactVoidedV1 {
  state: "voided";
  by_receipt_key_hash: string;
}

/** 记录的逐字段有效状态。 */
export type FactionFactValidityV1 = FactionFactActiveV1 | FactionFactReplacedV1 | FactionFactVoidedV1;

/** 删除保护使用真实父链，只有小说没有父级。 */
export type FactionFactProtectedSourceV1 =
  | { resource_type: "novel"; id: string; parent_id: null }
  | { resource_type: "volume" | "arc" | "scene" | "chapter"; id: string; parent_id: string };

/** 一个势力一次多字段确认的完整记录；其他字段不会被补齐进字典。 */
export interface FactionFactRecordV1 {
  schema_id: "faction.fact";
  schema_version: 1;
  history_id: string;
  novel_id: string;
  entity_type: "faction";
  entity_id: string;
  faction_id: string;
  faction_name: string;
  operation: Exclude<FactionFactOperation, "void">;
  kind: "start" | "change";
  position: FactionFactPositionV1;
  source: FactionFactSourceV1;
  before_version: number | null;
  after_version: number;
  before: FactionFactBeforeV1;
  after: FactionFactStoredValuesV1;
  previous: Partial<Record<FactionFactField, string | null>>;
  replaces: Partial<Record<FactionFactField, string>>;
  resolves: Partial<Record<FactionFactField, string[]>>;
  validity: Partial<Record<FactionFactField, FactionFactValidityV1>>;
  protected_sources: FactionFactProtectedSourceV1[];
  confirmed_at: IsoDateTime;
}

/** 冻结目录身份、直接父级和顺序，不夹带正文或统计版本。 */
export interface FactionFactDirectoryEntryV1 {
  resource_type: "volume" | "arc" | "scene" | "chapter";
  id: string;
  parent_id: string;
  order_index: number;
}

/** 读取绑定势力物理身份和业务身份，不靠无关资料版本判过期。 */
export interface FactionFactIdentityReadV1 {
  entity_id: string;
  faction_id: string;
  name: string;
  is_deleted: boolean;
}

/** 保存记录原文摘要及当时逐字段状态，不复制整份历史。 */
export interface FactionFactHistoryObservationV1 {
  history_id: string;
  entity_id: string;
  immutable_fingerprint: string;
  validity: Partial<Record<FactionFactField, FactionFactValidityV1>>;
}

/** 当前正文与不可变修订分别参与复验；缺失来源的字段显式为 null。 */
export interface FactionFactSourceObservationV1 {
  chapter_id: string;
  exists: boolean;
  content_hash: string | null;
  is_deleted: boolean | null;
  parents_active: boolean;
  revision_id: string | null;
  revision_hash: string | null;
  revision_valid: boolean;
}

/** 原读取选择和累计依据，空查询也必须保留。 */
export interface FactionFactReadV1 {
  kind: "faction_facts";
  novel_id: string;
  faction_ids: string[];
  position: FactionFactReadPositionV1;
  directory: FactionFactDirectoryEntryV1[];
  identities: FactionFactIdentityReadV1[];
  history: FactionFactHistoryObservationV1[];
  sources: FactionFactSourceObservationV1[];
  fingerprint: string;
}

/** 指定位置的势力结果；已知值的来源只指已确认记录。 */
export interface FactionFactsAtPositionV1 {
  entity_id: string;
  faction_id: string;
  name: string;
  version: number;
  values: FactionFactStoredValuesV1;
  unknown: Partial<Record<FactionFactField, FactionFactUnknownReason>>;
  blockers: Partial<Record<FactionFactField, string[]>>;
  origins: Partial<Record<FactionFactField, string>>;
  claimed_fields: FactionFactField[];
}

/** 共享读取的完整结果，缺失势力与空查询仍有原读取依据。 */
export interface FactionFactReadResultV1 {
  novel_id: string;
  position: FactionFactReadPositionV1;
  factions: FactionFactsAtPositionV1[];
  missing_faction_ids: string[];
  reads: FactionFactReadV1[];
}

/** 新势力的索引与设计资料；默认字段可省略，事实值只在 after 提交。 */
export interface FactionFactCreateDataV1 {
  name: string;
  alias?: string[];
  level_type?: "core" | "volume" | "local";
  parent_faction_id?: string | null;
  volume_id?: string | null;
  core_goal?: string;
  hidden_goal?: string;
  resources_and_advantages?: string[];
  conflict_with_mainline?: string;
  expandability?: string;
  tags?: string[];
  first_appearance_volume_id?: string | null;
  first_appearance_chapter_id?: string | null;
  sort_order?: number;
  extra?: Record<string, unknown>;
}

/** 已有势力保留作者预览时的完整身份和原版本。 */
export interface FactionFactExistingTargetV1 {
  kind: "existing";
  novel_id: string;
  entity_id: string;
  faction_id: string;
  name: string;
  version: number;
}

/** 新建预览不预占业务号或伪造旧版本，同名查询必须为空。 */
export interface FactionFactNewTargetV1 {
  kind: "new";
  novel_id: string;
  entity_id: string;
  normalized_name: string;
  candidate: FactionFactCreateDataV1;
  entity_exists: false;
  name_matches: [];
}

/** 新建和已存在的势力身份不能互换。 */
export type FactionFactTargetV1 = FactionFactExistingTargetV1 | FactionFactNewTargetV1;

/** 已有势力的预览输入只带真实身份和原版本，不接受客户端替换名称。 */
export interface FactionFactPreviewExistingTargetV1 {
  entity_id: string;
  faction_id: string;
  expected_version: number;
}

/** 新势力预览由服务端分配物理身份，输入只提供候选。 */
export interface FactionFactPreviewNewTargetV1 {
  candidate: FactionFactCreateDataV1;
}

/** 新建预览选择人工起点及字段，不接受客户端依据。 */
export interface FactionFactCreatePreviewInputV1 {
  operation: "create";
  target: FactionFactPreviewNewTargetV1;
  position: FactionFactPositionV1;
  source: FactionFactAuthorSourceV1;
  fields: FactionFactField[];
  references?: ChapterRecordEntityRefV1[];
}

/** 已有势力的预览明确位置、字段及原记录处置。 */
export interface FactionFactExistingPreviewInputV1 {
  operation: "establish" | "correct_initial" | "change" | "replace";
  target: FactionFactPreviewExistingTargetV1;
  kind: "start" | "change";
  position: FactionFactPositionV1;
  source: FactionFactSourceV1;
  fields: FactionFactField[];
  replaces?: Partial<Record<FactionFactField, string>>;
  resolves?: Partial<Record<FactionFactField, string[]>>;
  references?: ChapterRecordEntityRefV1[];
}

/** 作废位置与来源由原记录决定，作者只选要作废的记录字段。 */
export interface FactionFactVoidPreviewInputV1 {
  operation: "void";
  target: FactionFactPreviewExistingTargetV1;
  targets: Partial<Record<FactionFactField, string>>;
  references?: ChapterRecordEntityRefV1[];
}

/** 后端 RootModel 直接传输三种输入之一，JSON 没有 root 外壳。 */
export type FactionFactPreviewInputV1 = FactionFactCreatePreviewInputV1 | FactionFactExistingPreviewInputV1 | FactionFactVoidPreviewInputV1;

/** 相关资料引用冻结实际物理身份和版本，不只记录可重指向的业务号。 */
export interface FactionFactReferenceReadV1 {
  reference: ChapterRecordEntityRefV1;
  entity_id: string;
  version: number;
}

/** 旧主档保存文字，仅作为认领参考；缺键、null 和明确空值不能合并。 */
export interface FactionFactLegacyProfileSourceV1 {
  kind: "profile";
  entity_id: string;
  faction_id: string;
  version: number;
  raw: Partial<Record<"faction_type" | "positioning" | "organization_style" | "core_values" | "is_public"
    | "core_goal" | "hidden_goal" | "resources_and_advantages" | "public_stance" | "influence_scope", string | string[] | boolean | null>>;
}

/** 旧卷资料保持原义；隐藏计划和卷目标不能自动变成实际目标。 */
export interface FactionFactLegacyVolumeSourceV1 {
  kind: "volume_state";
  state_id: string;
  faction_id: string;
  version: number;
  is_deleted: boolean;
  volume_id: string;
  volume: { title: string; version: number; is_deleted: boolean } | null;
  raw: Partial<Record<"public_stance" | "power_level" | "resources" | "influence_scope" | "hidden_agenda" | "current_goal" | "active_status", string | string[] | number | null>>;
  notes: { start_state?: string | null };
}
export type FactionFactLegacySourceV1 = FactionFactLegacyProfileSourceV1 | FactionFactLegacyVolumeSourceV1;

/** 作者实际看到的身份、位置、字段结果、处置对象和原读取依据。 */
export type FactionFactBasisV1 = {
  schema_version: 1;
  kind: "start" | "change";
  position: FactionFactPositionV1;
  source: FactionFactSourceV1;
  fields: FactionFactField[];
  before: FactionFactBeforeV1;
  previous: Partial<Record<FactionFactField, string | null>>;
  replaces: Partial<Record<FactionFactField, string>>;
  resolves: Partial<Record<FactionFactField, string[]>>;
  void_targets: Partial<Record<FactionFactField, string>>;
  targets: FactionFactRecordV1[];
  blockers: Partial<Record<FactionFactField, string[]>>;
  field_sources: FactionFactRecordV1[];
  references: ChapterRecordEntityRefV1[];
  reference_reads: FactionFactReferenceReadV1[];
  legacy_sources: FactionFactLegacySourceV1[];
  reads: FactionFactReadV1[];
  protected_sources: FactionFactProtectedSourceV1[];
  fingerprint: string;
} & (
  | { operation: "create"; target: FactionFactNewTargetV1 }
  | { operation: "establish"; target: FactionFactExistingTargetV1 }
  | { operation: "correct_initial"; target: FactionFactExistingTargetV1 }
  | { operation: "change"; target: FactionFactExistingTargetV1 }
  | { operation: "replace"; target: FactionFactExistingTargetV1 }
  | { operation: "void"; target: FactionFactExistingTargetV1 }
);

/** 展示的原值必须与同份冻结依据的 before 一致。 */
export interface FactionFactPreviewV1 {
  basis: FactionFactBasisV1;
  values: FactionFactBeforeV1;
}

/** 新建只使用原新建预览，不接受 expected_version 或第二份候选。 */
export interface FactionFactCreateConfirmV1 {
  operation: "create";
  basis: FactionFactBasisV1 & { operation: "create"; target: FactionFactNewTargetV1 };
  after: FactionFactValuesV1;
  confirmed: true;
}

/** 确认动作与原预览逐项对应，已有势力始终携带作者原版本。 */
export type FactionFactExistingConfirmV1 = {
  expected_version: number;
  after: FactionFactValuesV1;
  confirmed: true;
} & (
  | { operation: "establish"; basis: FactionFactBasisV1 & { operation: "establish"; target: FactionFactExistingTargetV1 } }
  | { operation: "correct_initial"; basis: FactionFactBasisV1 & { operation: "correct_initial"; target: FactionFactExistingTargetV1 } }
  | { operation: "change"; basis: FactionFactBasisV1 & { operation: "change"; target: FactionFactExistingTargetV1 } }
  | { operation: "replace"; basis: FactionFactBasisV1 & { operation: "replace"; target: FactionFactExistingTargetV1 } }
);

/** 作废对象必须等于预览里的 void_targets，只说明原因，不接收 after。 */
export interface FactionFactVoidConfirmV1 {
  operation: "void";
  basis: FactionFactBasisV1 & { operation: "void"; target: FactionFactExistingTargetV1 };
  expected_version: number;
  targets: Partial<Record<FactionFactField, string>>;
  reason: string;
  confirmed: true;
}

/** 冻结原请求；创建、已有势力确认及作废有各自的固定载荷。 */
export type FactionFactConfirmV1 = FactionFactCreateConfirmV1 | FactionFactExistingConfirmV1 | FactionFactVoidConfirmV1;

/** 一次命令对原记录一个字段的单向处置。 */
export interface FactionFactValidityChangeV1 {
  history_id: string;
  field: FactionFactField;
  before: FactionFactActiveV1;
  after: FactionFactReplacedV1 | FactionFactVoidedV1;
}

/** 首次成功的完整结果；旧回执只证明确认成功，界面随后读取当前资料。 */
export interface FactionFactResultV1 {
  schema_version: 1;
  operation: FactionFactOperation;
  novel_id: string;
  entity_id: string;
  faction_id: string;
  faction_name: string;
  before_version: number | null;
  after_version: number;
  record: FactionFactRecordV1 | null;
  validity_changes: FactionFactValidityChangeV1[];
  confirmed_at: IsoDateTime;
}
