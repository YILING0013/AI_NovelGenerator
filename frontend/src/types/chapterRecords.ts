import type { ChapterRevision } from "@/types/hierarchy";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";
import type { WorldRuleReadV1 } from "@/types/worldRule";
import type { CharacterRelationFactsAtPositionV1, CharacterRelationFactReadPositionV1 } from "@/types/characterRelationFacts";

/** 世界规则检查只读取明确选择的版本，不修改规则或自动保存报告。 */
export interface ChapterWorldRulesCheckInputV1 {
  novel_id: string;
  source: ChapterPsychologicalCheckSourceV1;
  rules: Array<{ rule_id: string; expected_version: number }>;
}

/** 服务端绑定实际检查的完整规则，时间戳不参与模型输入。 */
export type ChapterCheckedWorldRuleV1 = Omit<WorldRuleReadV1, "created_at" | "updated_at" | "deleted_at"> & { entity_id: string };

/** 疑点有逐条引文与规则引用；普通报告只接受作者选中的文字。 */
export type ChapterWorldRulesCheckResultV1 = CandidateGenerationEnvelopeV1<{
  issues: Array<{ text: string; rule_ids: string[]; start: number; quote: string }>;
}> & {
  basis: CandidateBasisV1 & { flow_snapshot: { business_input: ChapterWorldRulesCheckInputV1; [key: string]: unknown } };
  checked_rules: ChapterCheckedWorldRuleV1[];
};

/** 人物关系检查只接收作者选定的关系和不可变章修订。 */
export interface ChapterCharacterRelationCheckInputV1 {
  novel_id: string;
  source: ChapterPsychologicalCheckSourceV1;
  relation_id: string;
  expected_version: number;
}

/** 服务器固定关系身份和两端人物，模型不选择这些字段。 */
export interface ChapterCharacterRelationCheckTargetV1 {
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  target_character_id: string;
  expected_version: number;
  current_state: string;
}

/** 保留完整检查依据；建议仅含关系现状和原文位置，也可以没有建议。 */
export type ChapterCharacterRelationCheckResultV1 = CandidateGenerationEnvelopeV1<{
  issues: string[];
  suggestion: { current_state: string; start: number; quote: string } | null;
}> & {
  basis: CandidateBasisV1 & { flow_snapshot: { business_input: ChapterCharacterRelationCheckInputV1; [key: string]: unknown } };
  check_target: ChapterCharacterRelationCheckTargetV1;
};

/** 新版检查保留章前事实；旧裸值既不参与比较，也不作为人工确认依据。 */
export type ChapterCharacterRelationCheckResultV2 = Omit<ChapterCharacterRelationCheckResultV1, "schema_version" | "check_target"> & {
  schema_version: 2;
  check_target: Omit<ChapterCharacterRelationCheckTargetV1, "current_state">;
  checked_facts: Pick<CharacterRelationFactsAtPositionV1, "values" | "unknown" | "blockers" | "origins" | "claimed_fields"> & { position: CharacterRelationFactReadPositionV1 };
};
export type ChapterCharacterRelationCheckResult = ChapterCharacterRelationCheckResultV1 | ChapterCharacterRelationCheckResultV2;

/** 作者单独确认关系现状；其他关系字段和端点不可提交。 */
export interface ChapterCharacterRelationConfirmV1 {
  relation_id: string;
  expected_version: number;
  current_state: string;
  evidence: ChapterRecordEvidenceV1;
  basis: CandidateBasisV1;
}

/** 人物关系属于全书，历史记录物理实体、稳定关系 ID 及固定端点。 */
export interface CharacterRelationStateHistoryReadV1 {
  history_id: string;
  novel_id: string;
  entity_type: "character_relation";
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  target_character_id: string;
  before_version: number;
  after_version: number;
  before: { current_state: string };
  after: { current_state: string };
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
}

/** 原成功回执；同值确认没有历史，随后仍读取当前关系。 */
export interface ChapterCharacterRelationResultV1 {
  novel_id: string;
  entity_id: string;
  relation_id: string;
  source_character_id: string;
  target_character_id: string;
  relation_version: number;
  current_state: string;
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
  history: CharacterRelationStateHistoryReadV1 | null;
}

/** 物品检查的固定范围；作者只选择原持有人到新持有人的一次变更。 */
export interface ChapterItemOwnerCheckInputV1 {
  novel_id: string;
  source: ChapterPsychologicalCheckSourceV1;
  item_id: string;
  expected_version: number;
  from_character_id: string;
  to_character_id: string;
}

/** 完整服务端依据原样保留，模型仅返回问题和原文位置。 */
export type ChapterItemOwnerCheckResultV1 = CandidateGenerationEnvelopeV1<{
  issues: string[];
  suggestion: { start: number; quote: string } | null;
}> & { basis: CandidateBasisV1 & { flow_snapshot: { business_input: ChapterItemOwnerCheckInputV1; [key: string]: unknown } } };

/** 新检查携带章前完整状态，旧检查保持原形状。 */
export type ChapterItemOwnerCheckResultV2 = Omit<ChapterItemOwnerCheckResultV1, "schema_version"> & {
  schema_version: 2;
  check_target: Pick<ChapterItemOwnerCheckInputV1, "item_id" | "expected_version" | "from_character_id" | "to_character_id"> & { entity_id: string };
  checked_facts: Pick<import("./itemFacts").ItemFactsAtPositionV1, "values" | "unknown" | "blockers" | "origin" | "claimed"> & { position: import("./characterFacts").CharacterFactReadPositionV1 };
};
export type ChapterItemOwnerCheckResult = ChapterItemOwnerCheckResultV1 | ChapterItemOwnerCheckResultV2;

/** 本次确认只修改持有人，不提交其他物品字段。 */
export interface ChapterItemOwnerConfirmV1 {
  item_id: string;
  expected_version: number;
  from_character_id: string;
  to_character_id: string;
  evidence: ChapterRecordEvidenceV1;
  basis: CandidateBasisV1;
}

/** 物品历史使用物理实体 ID；item_id 另保留稳定业务 ID。 */
export interface ItemStateHistoryReadV1 {
  history_id: string;
  novel_id: string;
  entity_type: "item";
  entity_id: string;
  item_id: string;
  before_version: number;
  after_version: number;
  before: { owner_character_id: string };
  after: { owner_character_id: string };
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
}

/** 原成功快照只证明确认已完成，随后仍读取当前物品。 */
export interface ChapterItemOwnerResultV1 {
  novel_id: string;
  item_id: string;
  item_version: number;
  owner_character_id: string;
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
  history: ItemStateHistoryReadV1;
}

/** 检查使用的整章不可变修订，不要求作者预先选择引文。 */
export interface ChapterPsychologicalCheckSourceV1 {
  chapter_id: string;
  revision_id: string;
  version: number;
  content_hash: string;
}

/** 服务器绑定的检查结果；模型只提供问题、心理建议和引文位置。 */
export interface ChapterPsychologicalCheckResultV1 {
  candidate: {
    issues: string[];
    suggestion: { psychological_state: string; start: number; quote: string } | null;
  };
  basis: {
    flow_snapshot: {
      business_input: {
        novel_id: string;
        source: ChapterPsychologicalCheckSourceV1;
        state_id: string;
        expected_version: number;
      };
    };
  };
  check_target: {
    state_id: string;
    expected_version: number;
    psychological_state: string;
    character_id: string;
    volume_id: string;
  };
}

/** 原修订和当前回收位置，软删不会改写旧内容或引文。 */
export interface ChapterRecordSourceReadV1 {
  revision: ChapterRevision;
  deleted_sources: Array<"novel" | "volume" | "arc" | "scene" | "chapter">;
}

/** 不可变章修订及原文；start 从零按 Unicode 码点计数，quote 保留空白和 CRLF。 */
export interface ChapterRecordEvidenceV1 {
  chapter_id: string;
  version: number;
  revision_id: string;
  content_hash: string;
  start: number;
  quote: string;
}

/** 相关资料使用已有类别和稳定 ID；引用资料不会自动修改其状态。 */
export interface ChapterRecordEntityRefV1 {
  entity_type:
    | "character"
    | "faction"
    | "character_relation"
    | "faction_relation"
    | "character_faction_binding"
    | "item"
    | "location"
    | "world_rule"
    | "character_volume_state"
    | "faction_volume_state";
  entity_id: string;
}

/** 作者确认已经发生的事件；不接收计划或任意实体修改。 */
export interface ChapterEventConfirmV1 {
  title: string;
  content: string;
  evidence: ChapterRecordEvidenceV1;
  related_entities: ChapterRecordEntityRefV1[];
}

/** 原事件及读取时的正文变化标记；作废仍保留原内容。 */
export interface ChapterEventReadV1 {
  event_id: string;
  novel_id: string;
  title: string;
  content: string;
  evidence: ChapterRecordEvidenceV1;
  related_entities: ChapterRecordEntityRefV1[];
  confirmed_at: string;
  voided_at: string | null;
  void_reason: string | null;
  needs_review: boolean;
}

/** 追加报告；expected_report_version 使用作者已读的报告头版本，首次为零。 */
export interface ChapterReportConfirmV1 {
  expected_report_version: number;
  summary: string;
  issues: string[];
  evidence: ChapterRecordEvidenceV1;
  related_entities: ChapterRecordEntityRefV1[];
}

/** 指定版本的完整报告；旧版不会被覆盖，作废版仍占原版本号。 */
export interface ChapterReportReadV1 {
  report_id: string;
  novel_id: string;
  chapter_id: string;
  report_version: number;
  previous_report_id: string | null;
  summary: string;
  issues: string[];
  evidence: ChapterRecordEvidenceV1;
  related_entities: ChapterRecordEntityRefV1[];
  confirmed_at: string;
  voided_at: string | null;
  void_reason: string | null;
  needs_review: boolean;
}

/** 报告头作废后 report 为 null，但 report_version 和 report_id 仍指向该版。 */
export interface ChapterReportHeadReadV1 {
  chapter_id: string;
  report_version: number;
  report_id: string | null;
  report: ChapterReportReadV1 | null;
}

/** 单向作废事件或报告的原因；不撤销实际发生过的状态更新。 */
export interface ChapterRecordVoidV1 {
  reason: string;
}

/** 只确认已有角色卷状态的心理状态；空字符串表示清空，版本保留作者原值。 */
export interface ChapterPsychologicalStateConfirmV1 {
  state_id: string;
  expected_version: number;
  psychological_state: string;
  evidence: ChapterRecordEvidenceV1;
}

/** 章后确认目前唯一允许修改的实际字段。 */
export interface ChapterPsychologicalValuesV1 {
  psychological_state: string;
}

/** 一次真实心理状态变化；普通编辑可以使相邻历史的实体版本不连续。 */
export interface CharacterStateHistoryReadV1 {
  history_id: string;
  novel_id: string;
  entity_type: "character_volume_state";
  entity_id: string;
  character_id: string;
  volume_id: string;
  before_version: number;
  after_version: number;
  before: ChapterPsychologicalValuesV1;
  after: ChapterPsychologicalValuesV1;
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
}

export type EntityStateHistoryReadV1 = CharacterStateHistoryReadV1 | ItemStateHistoryReadV1 | CharacterRelationStateHistoryReadV1;

/** 原成功快照；history 为 null 表示没有实际变化，重试成功后仍需读取当前状态。 */
export interface ChapterPsychologicalStateResultV1 {
  novel_id: string;
  state_id: string;
  state_version: number;
  psychological_state: string;
  evidence: ChapterRecordEvidenceV1;
  confirmed_at: string;
  needs_review: boolean;
  history: CharacterStateHistoryReadV1 | null;
}
