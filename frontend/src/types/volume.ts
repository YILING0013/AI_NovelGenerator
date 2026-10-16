import type { ReasoningOptions } from "@/types/generation";
import type { CandidateBasisV1, CandidateGenerationEnvelopeV1 } from "@/lib/aiCandidate";

export type VolumeStatus = "draft" | "planned" | "active" | "completed" | "archived";
export type VolumeSkeletonMode = "create" | "append" | "replan";

/** 一卷的剧情规划，可以暂不填写。 */
export interface VolumePlanningV1 {
  premise: string;
  major_conflict: string;
  key_turning_points: string[];
  start_state: string;
  end_state: string;
  target_chapter_count: number;
  target_word_count: number;
}

/** 页面读取的一卷完整数据。 */
export interface VolumeReadV2 {
  _id: string;
  volume_id: string;
  novel_id: string;
  title: string;
  subtitle: string;
  summary: string;
  goal: string;
  theme: string;
  order_index: number;
  status: VolumeStatus;
  planning: VolumePlanningV1 | null;
  plot?: string;
  plot_source_fingerprint?: string | null;
  location_ids?: string[];
  preparation?: Partial<Record<"factions" | "characters" | "locations", string>>;
  arcs_count: number;
  chapter_count?: number;
  word_count: number;
  version: number;
  is_deleted: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

/** 重新规划时所选的连续卷范围，序号从 1 开始。 */
export interface VolumeOrderRangeV1 {
  start: number;
  end: number;
}

/** 规划全书分卷时锁定的输入。 */
export interface VolumeSkeletonGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  target_volume_count: number;
  total_chapter_budget: number;
  total_word_budget: number;
  mode: VolumeSkeletonMode;
  target_order_range: VolumeOrderRangeV1 | null;
  novel_expected_version: number;
  user_guidance: string;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
}

/** 普通请求和流式请求共用的全书分卷参数。 */
export interface VolumeSkeletonGenerateRequestV1 extends ReasoningOptions {
  target_volume_count: number;
  total_chapter_budget: number;
  total_word_budget: number;
  mode: VolumeSkeletonMode;
  target_order_range: VolumeOrderRangeV1 | null;
  novel_expected_version: number;
  user_guidance: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
  use_stream: boolean;
}

/** 页面中可编辑、还未保存的一卷。 */
export interface VolumeSkeletonCandidateV1 {
  candidate_ref: string;
  title: string;
  subtitle: string;
  order_index: number;
  summary: string;
  goal: string;
  theme: string;
  planning: VolumePlanningV1;
}

/** AI 返回的全书分卷结果。 */
export interface VolumeSkeletonResultV1 {
  volumes: VolumeSkeletonCandidateV1[];
}

/** 生成全书分卷时锁定的数据版本，页面不能修改。 */
export interface VolumeSkeletonBasisV1 extends CandidateBasisV1 {
  novel_id: string;
  generation_input: VolumeSkeletonGenerationInputV1;
}

/** 普通请求和流式请求返回的全书分卷结果。 */
export type VolumeSkeletonPreviewV1 = CandidateGenerationEnvelopeV1<VolumeSkeletonResultV1> & {
  basis: VolumeSkeletonBasisV1;
  impacts: VolumeDeleteImpactV2[];
};

/** 一次保存全部 AI 分卷的请求。 */
export interface VolumeBulkPlanConfirmV1 {
  candidates: VolumeSkeletonCandidateV1[];
  basis: VolumeSkeletonBasisV1;
  expected_versions: Record<string, number>;
}

/** 全部 AI 分卷保存成功后的编号对应关系和最新数据。 */
export interface VolumeBulkPlanResponseV1 {
  candidate_ref_map: Record<string, string>;
  volumes: VolumeReadV2[];
}

/** AI 完善当前卷时锁定的输入。 */
export interface VolumeLaunchGenerationInputV1 extends ReasoningOptions {
  novel_id: string;
  volume_id: string;
  volume_expected_version: number;
  target_chapter_count: number | null;
  target_word_count: number | null;
  user_guidance: string;
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
}

/** 普通请求和流式请求共用的当前卷参数。 */
export interface VolumeLaunchGenerateRequestV1 extends ReasoningOptions {
  volume_expected_version: number;
  target_chapter_count: number | null;
  target_word_count: number | null;
  user_guidance: string;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
  system_prompt?: string | null;
  use_stream: boolean;
}

/** AI 返回的当前卷规划。 */
export interface VolumeLaunchPackageResultV1 {
  launch_package: Omit<VolumeSkeletonCandidateV1, "candidate_ref" | "order_index">;
}

/** 完善当前卷时锁定的卷和数据版本，页面不能修改。 */
export interface VolumeLaunchBasisV1 extends CandidateBasisV1 {
  novel_id: string;
  generation_input: VolumeLaunchGenerationInputV1;
}

/** AI 修改当前卷时可能影响的前后卷和已有内容。 */
export interface VolumeLaunchImpactV1 {
  target_volume_id: string;
  previous_volume_id: string | null;
  next_volume_id: string | null;
  downstream: VolumeDeleteImpactV2;
  next_start_state_conflict: boolean;
  has_blockers: boolean;
}

/** 普通请求和流式请求返回的当前卷规划。 */
export type VolumeLaunchPreviewV1 = CandidateGenerationEnvelopeV1<VolumeLaunchPackageResultV1> & {
  basis: VolumeLaunchBasisV1;
  impact: VolumeLaunchImpactV1;
};

/** 保存 AI 当前卷规划时提交的完整字段。 */
export interface VolumeLaunchConfirmV1 {
  expected_version: number;
  title: string;
  subtitle: string;
  summary: string;
  goal: string;
  theme: string;
  planning: VolumePlanningV1;
  basis: VolumeLaunchBasisV1;
}

/** 人工创建卷时允许提交的业务字段。 */
export interface VolumeCreateV2 {
  novel_id: string;
  title: string;
  subtitle: string;
  summary: string;
  goal: string;
  theme: string;
  status: VolumeStatus;
  planning: VolumePlanningV1 | null;
}

/** 人工编辑卷时提交的业务字段和公开版本。 */
export type VolumeUpdateV2 = Omit<VolumeCreateV2, "novel_id"> & {
  expected_version: number;
};

/** 调整卷顺序时提交的一卷及其当前版本。 */
export interface VolumeReorderItemV2 {
  volume_id: string;
  order_index: number;
  expected_version: number;
}

/** 删除卷前需要展示的关联数据数量。 */
export interface VolumeDeleteImpactV2 {
  volume_id: string;
  arcs: number;
  scenes: number;
  chapters: number;
  factions: number;
  character_volume_states: number;
  faction_volume_states: number;
  character_first_appearances: number;
  faction_first_appearances: number;
  character_faction_binding_boundaries: number;
  foreshadowings: number;
  chapter_records: number;
  total: number;
  has_blockers: boolean;
}

/**
 * 校验删除前检查接口返回的数据，避免确认框漏掉关联内容。
 *
 * @param value 后端返回的未知 JSON 值。
 * @returns 字段和类型正确的关联数据数量。
 */
export function parseVolumeDeleteImpactV2(value: unknown): VolumeDeleteImpactV2 {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("Invalid volume delete impact response");
  }
  const impact = value as Record<string, unknown>;
  const keys = [
    "volume_id",
    "arcs",
    "scenes",
    "chapters",
    "factions",
    "character_volume_states",
    "faction_volume_states",
    "character_first_appearances",
    "faction_first_appearances",
    "character_faction_binding_boundaries",
    "foreshadowings",
    "chapter_records",
    "total",
    "has_blockers",
  ];
  if (
    Object.keys(impact).length !== keys.length
    || keys.some((key) => !(key in impact))
    || typeof impact.volume_id !== "string"
    || ![
      impact.arcs,
      impact.scenes,
      impact.chapters,
      impact.factions,
      impact.character_volume_states,
      impact.faction_volume_states,
      impact.character_first_appearances,
      impact.faction_first_appearances,
      impact.character_faction_binding_boundaries,
      impact.foreshadowings,
      impact.chapter_records,
      impact.total,
    ]
      .every((count) => typeof count === "number" && Number.isInteger(count) && count >= 0)
    || typeof impact.has_blockers !== "boolean"
  ) {
    throw new Error("Invalid volume delete impact response");
  }
  return impact as unknown as VolumeDeleteImpactV2;
}

/** 卷启动表单的只读提醒；不是生成或采用依据。 */
export interface VolumeLaunchContextV1 {
  novel_id: string;
  volume_id: string;
  volume_title: string;
  position: import("./characterFacts").CharacterFactReadPositionV1;
  counts: Record<"characters" | "factions" | "character_relations" | "faction_relations" | "bindings" | "world_rules" | "volumes", number>;
  entities: {
    entity_type: "character" | "faction" | "character_relation";
    entity_id: string;
    name: string;
    source_ids: string[];
    issues: { field: string; reason: import("./characterFacts").CharacterFactUnknownReason; blocking_source_ids: string[] }[];
  }[];
}
