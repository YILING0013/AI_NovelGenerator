import type { ReasoningOptions } from "@/types/generation";
import type {
  CandidateBasisV1,
  CandidateGenerationEnvelopeV1,
} from "@/lib/aiCandidate";

/** 核心规则 AI 允许生成的稳定范围。 */
export type CoreWorldRuleScopeType = "global" | "faction" | "character";

/** 正式世界规则可绑定的事实范围。 */
export type WorldRuleScopeType = CoreWorldRuleScopeType | "location";

/** 世界规则的业务状态。 */
export type WorldRuleStatus = "draft" | "active" | "retired";

/** 单条规则的条件例外及对应效果。 */
export interface WorldRuleExceptionV1 {
  condition: string;
  effect: string;
}

/** 人工编辑与 AI 候选共同使用的规则内容字段。 */
export interface WorldRuleContentFieldsV1 {
  name: string;
  category: string;
  statement: string;
  scope_type: WorldRuleScopeType;
  scope_entity_ids: string[];
  enforcement: string;
  exceptions: WorldRuleExceptionV1[];
  costs_and_consequences: string[];
  priority: number;
  tags: string[];
}

/** 创建、编辑与正式响应共用的规则业务字段。 */
export interface WorldRuleFieldsV1 extends WorldRuleContentFieldsV1 {
  status: WorldRuleStatus;
}

/** 人工创建世界规则的严格请求。 */
export type WorldRuleCreateV1 = WorldRuleFieldsV1;

/** 正式世界规则更新请求；公开版本只通过 expected_version 提交。 */
export type WorldRuleUpdateV1 = Partial<WorldRuleFieldsV1> & {
  expected_version: number;
};

/** 正式世界规则公开响应。 */
export interface WorldRuleReadV1 extends WorldRuleFieldsV1 {
  rule_id: string;
  novel_id: string;
  order_index: number;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 同分类完整重排中的单条 CAS 命令。 */
export interface WorldRuleReorderItemV1 {
  rule_id: string;
  order_index: number;
  expected_version: number;
}

/** 同分类完整重排请求。 */
export interface WorldRuleReorderRequestV1 {
  items: WorldRuleReorderItemV1[];
}

/** 规则恢复请求。 */
export interface WorldRuleRestoreRequestV1 {
  expected_version: number;
}

/** 永久删除前后使用的引用影响统计。 */
export interface WorldRuleReferenceImpactV1 {
  locations: number;
  arcs: number;
  scenes: number;
  foreshadowings: number;
  total: number;
}

/** 世界规则永久删除响应。 */
export interface WorldRuleHardDeleteResponseV1 {
  message: string;
  rule_id: string;
  references: WorldRuleReferenceImpactV1;
}

/** 规则列表中无法使用的一条引用问题。 */
export interface WorldRuleContextDiagnosticV1 {
  rule_id: string;
  code: string;
  message: string;
  scope_type: WorldRuleScopeType;
  scope_entity_ids: string[];
}

/** 世界观摘要和可用规则组成的只读数据。 */
export interface WorldRuleContextV1 {
  worldview_summary: string;
  active_rules: WorldRuleReadV1[];
  diagnostics: WorldRuleContextDiagnosticV1[];
}

/** 核心规则生成请求中会被 basis 固定下来的业务输入。 */
export interface CoreWorldRulesGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  core_rule_count: number;
  allow_incremental: boolean;
  user_guidance: string;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
}

/** 核心规则生成接口请求；use_stream 只选择普通或 SSE 入口。 */
export interface CoreWorldRulesGenerateRequestV1 extends ReasoningOptions {
  core_rule_count: number;
  allow_incremental: boolean;
  user_guidance: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
  use_stream: boolean;
}

/** 页面可编辑但还未保存的一条核心规则；AI 不会自动生成地点规则。 */
export interface CoreWorldRuleCandidateV1 extends Omit<WorldRuleContentFieldsV1, "scope_type"> {
  candidate_ref: string;
  scope_type: CoreWorldRuleScopeType;
}

/** 核心规则模型结果的严格根对象。 */
export interface CoreWorldRulesResultV1 {
  core_world_rules: CoreWorldRuleCandidateV1[];
}

/** 核心规则候选依据；生成输入由服务端写入且前端只能原样回传。 */
export interface CoreWorldRulesBasisV1 extends CandidateBasisV1 {
  novel_id: string;
  generation_input: CoreWorldRulesGenerationInputV1;
}

/** 普通响应与 SSE done.result 共用的核心规则候选信封。 */
export type CoreWorldRulesCandidateEnvelopeV1 = CandidateGenerationEnvelopeV1<CoreWorldRulesResultV1> & {
  basis: CoreWorldRulesBasisV1;
};

/** 核心规则候选确认请求。 */
export interface CoreWorldRulesConfirmV1 {
  candidates: CoreWorldRuleCandidateV1[];
  basis: CoreWorldRulesBasisV1;
  expected_versions: Record<string, number>;
}

/** 核心规则批量确认成功响应。 */
export interface CoreWorldRulesConfirmResponseV1 {
  candidate_ref_map: Record<string, string>;
  world_rules: WorldRuleReadV1[];
}
