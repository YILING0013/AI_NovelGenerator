import type { CharacterImportanceLevel, CharacterRoleType, IsoDateTime } from "@/types/character";
import type { ChapterRecordEntityRefV1, ChapterRecordEvidenceV1 } from "@/types/chapterRecords";

/** 人物确认可接管的十五个实际字段；卷目标计划不在其中。 */
export type CharacterFactField =
  | "gender"
  | "age_group"
  | "race"
  | "identity"
  | "appearance"
  | "personality"
  | "core_desire"
  | "core_fear"
  | "strengths"
  | "weaknesses"
  | "abilities"
  | "psychological_state"
  | "public_state"
  | "hidden_state"
  | "actual_goal";

/** 未知原因必须明确显示，不能退回普通当前字段补值。 */
export type CharacterFactUnknownReason =
  | "nonexistent"
  | "unclaimed"
  | "before_start"
  | "voided"
  | "needs_review"
  | "unresolved_reference";

/** 同一人物一次确认的固定动作。 */
export type CharacterFactOperation = "create" | "establish" | "correct_initial" | "change" | "replace" | "void";

/** 只提交明确的已知值；省略、空字符串及空数组不同，不接受 null。 */
export interface CharacterFactValuesV1 {
  gender?: string;
  age_group?: string;
  race?: string;
  identity?: string;
  appearance?: string;
  personality?: string;
  core_desire?: string;
  core_fear?: string;
  strengths?: string[];
  weaknesses?: string[];
  abilities?: string[];
  psychological_state?: string;
  public_state?: string;
  hidden_state?: string;
  actual_goal?: string;
}

/** 历史和冻结依据保留原字符串；前端不能清理空白或补齐缺省值。 */
export type CharacterFactStoredValuesV1 = CharacterFactValuesV1;

/** 书初使用小说锚，章前后使用章节锚，不保存数字章号。 */
export type CharacterFactPositionV1 =
  | { version: 1; intent: "book_start"; target_type: "novel"; target_id: string }
  | { version: 1; intent: "volume_start"; target_type: "volume"; target_id: string }
  | { version: 1; intent: "chapter_before" | "chapter_after"; target_type: "chapter"; target_id: string };

/** 读取沿用 P1 的真实层级和顺序深度，包括空父级的开始与追加。 */
export type CharacterFactReadPositionV1 =
  | { version: 1; intent: "book_start"; target_type: "novel"; target_id: string; order: [] }
  | { version: 1; intent: "volume_start" | "replan" | "append"; target_type: "volume"; target_id: string; order: [number] }
  | { version: 1; intent: "replan" | "append"; target_type: "arc"; target_id: string; order: [number, number] }
  | { version: 1; intent: "replan" | "append"; target_type: "scene"; target_id: string; order: [number, number, number] }
  | { version: 1; intent: "chapter_before" | "chapter_after"; target_type: "chapter"; target_id: string; order: [number, number, number, number] };

/** 人工起点只需要作者说明，不伪造章节引文。 */
export interface CharacterFactAuthorSourceV1 {
  kind: "author";
  note: string;
}

/** 章后变化使用原不可变修订和码点引文。 */
export interface CharacterFactChapterSourceV1 {
  kind: "chapter";
  evidence: ChapterRecordEvidenceV1;
}

/** 作者说明与章节引文按来源类别区分。 */
export type CharacterFactSourceV1 = CharacterFactAuthorSourceV1 | CharacterFactChapterSourceV1;

/** 已知原值与未知字段分别保存，不能为未知字段填猜测值。 */
export interface CharacterFactBeforeV1 {
  values: CharacterFactStoredValuesV1;
  unknown: Partial<Record<CharacterFactField, CharacterFactUnknownReason>>;
}

/** 尚未被作者替代或作废的记录字段。 */
export interface CharacterFactActiveV1 {
  state: "active";
}

/** 替代只作用于原记录的对应字段。 */
export interface CharacterFactReplacedV1 {
  state: "replaced";
  by_history_id: string;
}

/** 作废追溯原成功命令，不反向执行 before。 */
export interface CharacterFactVoidedV1 {
  state: "voided";
  by_receipt_key_hash: string;
}

/** 记录的逐字段有效状态。 */
export type CharacterFactValidityV1 = CharacterFactActiveV1 | CharacterFactReplacedV1 | CharacterFactVoidedV1;

/** 删除保护使用真实父链，只有小说没有父级。 */
export type CharacterFactProtectedSourceV1 =
  | { resource_type: "novel"; id: string; parent_id: null }
  | { resource_type: "volume" | "arc" | "scene" | "chapter"; id: string; parent_id: string };

/** 一个人物一次多字段确认的完整记录；其他字段不会被补齐进字典。 */
export interface CharacterFactRecordV1 {
  schema_id: "character.fact";
  schema_version: 1;
  history_id: string;
  novel_id: string;
  entity_type: "character";
  entity_id: string;
  character_id: string;
  character_name: string;
  operation: Exclude<CharacterFactOperation, "void">;
  kind: "start" | "change";
  position: CharacterFactPositionV1;
  source: CharacterFactSourceV1;
  before_version: number | null;
  after_version: number;
  before: CharacterFactBeforeV1;
  after: CharacterFactStoredValuesV1;
  previous: Partial<Record<CharacterFactField, string | null>>;
  replaces: Partial<Record<CharacterFactField, string>>;
  resolves: Partial<Record<CharacterFactField, string[]>>;
  validity: Partial<Record<CharacterFactField, CharacterFactValidityV1>>;
  protected_sources: CharacterFactProtectedSourceV1[];
  confirmed_at: IsoDateTime;
}

/** 冻结目录身份、直接父级和顺序，不夹带正文或统计版本。 */
export interface CharacterFactDirectoryEntryV1 {
  resource_type: "volume" | "arc" | "scene" | "chapter";
  id: string;
  parent_id: string;
  order_index: number;
}

/** 读取绑定人物物理身份和业务身份，不靠无关资料版本判过期。 */
export interface CharacterFactIdentityReadV1 {
  entity_id: string;
  character_id: string;
  name: string;
  is_deleted: boolean;
}

/** 保存记录原文摘要及当时逐字段状态，不复制整份历史。 */
export interface CharacterFactHistoryObservationV1 {
  history_id: string;
  entity_id: string;
  immutable_fingerprint: string;
  validity: Partial<Record<CharacterFactField, CharacterFactValidityV1>>;
}

/** 当前正文与不可变修订分别参与复验；缺失来源的字段显式为 null。 */
export interface CharacterFactSourceObservationV1 {
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
export interface CharacterFactReadV1 {
  kind: "character_facts";
  novel_id: string;
  character_ids: string[];
  position: CharacterFactReadPositionV1;
  directory: CharacterFactDirectoryEntryV1[];
  identities: CharacterFactIdentityReadV1[];
  history: CharacterFactHistoryObservationV1[];
  sources: CharacterFactSourceObservationV1[];
  fingerprint: string;
}

/** 指定位置的人物结果；已知值的来源只指已确认记录。 */
export interface CharacterFactsAtPositionV1 {
  entity_id: string;
  character_id: string;
  name: string;
  version: number;
  values: CharacterFactStoredValuesV1;
  unknown: Partial<Record<CharacterFactField, CharacterFactUnknownReason>>;
  blockers: Partial<Record<CharacterFactField, string[]>>;
  origins: Partial<Record<CharacterFactField, string>>;
  claimed_fields: CharacterFactField[];
}

/** 共享读取的完整结果，缺失人物与空查询仍有原读取依据。 */
export interface CharacterFactReadResultV1 {
  novel_id: string;
  position: CharacterFactReadPositionV1;
  characters: CharacterFactsAtPositionV1[];
  missing_character_ids: string[];
  reads: CharacterFactReadV1[];
}

/** 新人物的索引与设计资料；默认字段可省略，事实值只在 after 提交。 */
export interface CharacterFactCreateDataV1 {
  name: string;
  aliases?: string[];
  role_type: CharacterRoleType;
  importance_level: CharacterImportanceLevel;
  is_core_character?: boolean;
  conflict_with_mainline?: string;
  relationship_with_protagonist?: string;
  initial_state?: string;
  growth_direction?: string;
  story_function?: string;
  arc_seed?: string;
  tags?: string[];
  sort_order?: number;
}

/** 已有人物保留作者预览时的完整身份和原版本。 */
export interface CharacterFactExistingTargetV1 {
  kind: "existing";
  novel_id: string;
  entity_id: string;
  character_id: string;
  name: string;
  version: number;
}

/** 新建预览不预占业务号或伪造旧版本，同名查询必须为空。 */
export interface CharacterFactNewTargetV1 {
  kind: "new";
  novel_id: string;
  entity_id: string;
  normalized_name: string;
  candidate: CharacterFactCreateDataV1;
  entity_exists: false;
  name_matches: [];
}

/** 新建和已存在的人物身份不能互换。 */
export type CharacterFactTargetV1 = CharacterFactExistingTargetV1 | CharacterFactNewTargetV1;

/** 已有人物的预览输入只带真实身份和原版本，不接受客户端替换名称。 */
export interface CharacterFactPreviewExistingTargetV1 {
  entity_id: string;
  character_id: string;
  expected_version: number;
}

/** 新人物预览由服务端分配物理身份，输入只提供候选。 */
export interface CharacterFactPreviewNewTargetV1 {
  candidate: CharacterFactCreateDataV1;
}

/** 新建预览选择人工起点及字段，不接受客户端依据。 */
export interface CharacterFactCreatePreviewInputV1 {
  operation: "create";
  target: CharacterFactPreviewNewTargetV1;
  position: CharacterFactPositionV1;
  source: CharacterFactAuthorSourceV1;
  fields: CharacterFactField[];
  references?: ChapterRecordEntityRefV1[];
}

/** 已有人物的预览明确位置、字段及原记录处置。 */
export interface CharacterFactExistingPreviewInputV1 {
  operation: "establish" | "correct_initial" | "change" | "replace";
  target: CharacterFactPreviewExistingTargetV1;
  kind: "start" | "change";
  position: CharacterFactPositionV1;
  source: CharacterFactSourceV1;
  fields: CharacterFactField[];
  replaces?: Partial<Record<CharacterFactField, string>>;
  resolves?: Partial<Record<CharacterFactField, string[]>>;
  references?: ChapterRecordEntityRefV1[];
}

/** 作废位置与来源由原记录决定，作者只选要作废的记录字段。 */
export interface CharacterFactVoidPreviewInputV1 {
  operation: "void";
  target: CharacterFactPreviewExistingTargetV1;
  targets: Partial<Record<CharacterFactField, string>>;
  references?: ChapterRecordEntityRefV1[];
}

/** 后端 RootModel 直接传输三种输入之一，JSON 没有 root 外壳。 */
export type CharacterFactPreviewInputV1 = CharacterFactCreatePreviewInputV1 | CharacterFactExistingPreviewInputV1 | CharacterFactVoidPreviewInputV1;

/** 相关资料引用冻结实际物理身份和版本，不只记录可重指向的业务号。 */
export interface CharacterFactReferenceReadV1 {
  reference: ChapterRecordEntityRefV1;
  entity_id: string;
  version: number;
}

/** 旧主档保存文字，仅作为认领参考；缺键、null 和明确空值不能合并。 */
export interface CharacterFactLegacyProfileSourceV1 {
  kind: "profile";
  entity_id: string;
  character_id: string;
  version: number;
  raw: Partial<{ gender: string | null; age_group: string | null; race: string | null; identity: string | null; appearance: string | null; personality: string | null; core_desire: string | null; core_fear: string | null; strengths: string[] | null; weaknesses: string[] | null; abilities: string[] | null }>;
  notes: { initial_state?: string | null };
}

/** 全部保留卷状态的原文快照；current_goal 仍是旧计划，不映射成 actual_goal。 */
export interface CharacterFactLegacyVolumeSourceV1 {
  kind: "volume_state";
  state_id: string;
  character_id: string;
  version: number;
  is_deleted: boolean;
  volume_id: string;
  volume: { title: string; version: number; is_deleted: boolean } | null;
  raw: Partial<{ psychological_state: string | null; public_state: string | null; hidden_state: string | null; current_goal: string | null }>;
  notes: { start_state?: string | null };
}
export type CharacterFactLegacySourceV1 = CharacterFactLegacyProfileSourceV1 | CharacterFactLegacyVolumeSourceV1;

/** 作者实际看到的身份、位置、字段结果、处置对象和原读取依据。 */
export type CharacterFactBasisV1 = {
  schema_version: 1;
  kind: "start" | "change";
  position: CharacterFactPositionV1;
  source: CharacterFactSourceV1;
  fields: CharacterFactField[];
  before: CharacterFactBeforeV1;
  previous: Partial<Record<CharacterFactField, string | null>>;
  replaces: Partial<Record<CharacterFactField, string>>;
  resolves: Partial<Record<CharacterFactField, string[]>>;
  void_targets: Partial<Record<CharacterFactField, string>>;
  targets: CharacterFactRecordV1[];
  blockers: Partial<Record<CharacterFactField, string[]>>;
  field_sources: CharacterFactRecordV1[];
  references: ChapterRecordEntityRefV1[];
  reference_reads: CharacterFactReferenceReadV1[];
  legacy_sources: CharacterFactLegacySourceV1[];
  reads: CharacterFactReadV1[];
  protected_sources: CharacterFactProtectedSourceV1[];
  fingerprint: string;
} & (
  | { operation: "create"; target: CharacterFactNewTargetV1 }
  | { operation: "establish"; target: CharacterFactExistingTargetV1 }
  | { operation: "correct_initial"; target: CharacterFactExistingTargetV1 }
  | { operation: "change"; target: CharacterFactExistingTargetV1 }
  | { operation: "replace"; target: CharacterFactExistingTargetV1 }
  | { operation: "void"; target: CharacterFactExistingTargetV1 }
);

/** 展示的原值必须与同份冻结依据的 before 一致。 */
export interface CharacterFactPreviewV1 {
  basis: CharacterFactBasisV1;
  values: CharacterFactBeforeV1;
}

/** 新建只使用原新建预览，不接受 expected_version 或第二份候选。 */
export interface CharacterFactCreateConfirmV1 {
  operation: "create";
  basis: CharacterFactBasisV1 & { operation: "create"; target: CharacterFactNewTargetV1 };
  after: CharacterFactValuesV1;
  confirmed: true;
}

/** 确认动作与原预览逐项对应，已有人物始终携带作者原版本。 */
export type CharacterFactExistingConfirmV1 = {
  expected_version: number;
  after: CharacterFactValuesV1;
  confirmed: true;
} & (
  | { operation: "establish"; basis: CharacterFactBasisV1 & { operation: "establish"; target: CharacterFactExistingTargetV1 } }
  | { operation: "correct_initial"; basis: CharacterFactBasisV1 & { operation: "correct_initial"; target: CharacterFactExistingTargetV1 } }
  | { operation: "change"; basis: CharacterFactBasisV1 & { operation: "change"; target: CharacterFactExistingTargetV1 } }
  | { operation: "replace"; basis: CharacterFactBasisV1 & { operation: "replace"; target: CharacterFactExistingTargetV1 } }
);

/** 作废对象必须等于预览里的 void_targets，只说明原因，不接收 after。 */
export interface CharacterFactVoidConfirmV1 {
  operation: "void";
  basis: CharacterFactBasisV1 & { operation: "void"; target: CharacterFactExistingTargetV1 };
  expected_version: number;
  targets: Partial<Record<CharacterFactField, string>>;
  reason: string;
  confirmed: true;
}

/** 冻结原请求；创建、已有人物确认及作废有各自的固定载荷。 */
export type CharacterFactConfirmV1 = CharacterFactCreateConfirmV1 | CharacterFactExistingConfirmV1 | CharacterFactVoidConfirmV1;

/** 一次命令对原记录一个字段的单向处置。 */
export interface CharacterFactValidityChangeV1 {
  history_id: string;
  field: CharacterFactField;
  before: CharacterFactActiveV1;
  after: CharacterFactReplacedV1 | CharacterFactVoidedV1;
}

/** 首次成功的完整结果；旧回执只证明确认成功，界面随后读取当前资料。 */
export interface CharacterFactResultV1 {
  schema_version: 1;
  operation: CharacterFactOperation;
  novel_id: string;
  entity_id: string;
  character_id: string;
  character_name: string;
  before_version: number | null;
  after_version: number;
  record: CharacterFactRecordV1 | null;
  validity_changes: CharacterFactValidityChangeV1[];
  confirmed_at: IsoDateTime;
}
