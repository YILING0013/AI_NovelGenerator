"use client";
import { REASONING_FIELDS, hasValidReasoningOptions } from "@/types/generation";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { TaskFlowForm,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import { taskFlowDefaultInputs, type TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";

import { Button,Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
useCallback,
useEffect,
useLayoutEffect,
useMemo,
useReducer,
useRef,
useState
} from "react";

import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import VolumeFieldsForm from "@/components/writing/volumes/VolumeFieldsForm";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import {
buildCandidateExpectedVersions,
createLocalCandidateState,
hasCandidateFlow,
localCandidateReducer,
type CandidateSourceRefV1,
} from "@/lib/aiCandidate";
import {
apiGet,
apiPost,
apiPut,
ApiRequestError,
type ApiFieldErrors
} from "@/lib/api";
import { isLocalCandidateRef,isObjectIdString } from "@/types/contracts";
import {
parseVolumeDeleteImpactV2,
type VolumeBulkPlanConfirmV1,
type VolumeBulkPlanResponseV1,
type VolumeDeleteImpactV2,
type VolumeLaunchBasisV1,
type VolumeLaunchConfirmV1,
type VolumeLaunchGenerationInputV1,
type VolumeLaunchImpactV1,
type VolumeLaunchPackageResultV1,
type VolumeLaunchPreviewV1,
type VolumePlanningV1,
type VolumeReadV2,
type VolumeSkeletonBasisV1,
type VolumeSkeletonCandidateV1,
type VolumeSkeletonGenerationInputV1,
type VolumeSkeletonMode,
type VolumeSkeletonPreviewV1,
type VolumeSkeletonResultV1
} from "@/types/volume";

interface VolumePlanningCandidateWorkspaceProps {
  task?: "skeleton" | "launch" | "all";
  novelId: string;
  volumes: VolumeReadV2[];
  selectedVolume: VolumeReadV2 | null;
  disabled?: boolean;
  onReviewingChange?: (reviewing: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
  onSkeletonConfirmed?: (response: VolumeBulkPlanResponseV1) => void;
  onLaunchConfirmed?: (volume: VolumeReadV2) => void;
}

interface StableConfirmCommand {
  fingerprint: string;
  key: string;
}

interface LaunchDraft {
  candidate: VolumeLaunchPackageResultV1;
  basis: VolumeLaunchBasisV1;
  impact: VolumeLaunchImpactV1 | null;
  command: StableConfirmCommand | null;
  stale: boolean;
}

interface ConflictDetail {
  expectedVersion: number | null;
  actualVersion: number | null;
  resourceType: string | null;
  resourceId: string | null;
}

type EditableVolumePackage = Omit<VolumeSkeletonCandidateV1, "candidate_ref" | "order_index">;

const SKELETON_CONTRACT = {
  workflow: "create_volume_skeleton_by_ai",
  step: "create_volume_skeleton",
  schemaId: "volume_skeleton_result",
  schemaVersion: 1,
} as const;
const LAUNCH_CONTRACT = {
  workflow: "plan_volume_launch_by_ai",
  step: "create_volume_launch_package",
  schemaId: "volume_launch_package_result",
  schemaVersion: 1,
} as const;
const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOnlyKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
  optionalKeys: readonly string[] = [],
): boolean {
  const expected = new Set(keys);
  const actual = Object.keys(value).filter((key) => !optionalKeys.includes(key));
  return actual.length === expected.size && actual.every((key) => expected.has(key));
}

function normalizeComparableText(value: string): string {
  return value
    .normalize("NFKC")
    .trim()
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function isNullableNumberInRange(value: unknown, minimum: number, maximum: number): boolean {
  return value === null
    || (typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum);
}

function isNullablePositiveInteger(value: unknown, maximum: number): boolean {
  return value === null || (Number.isInteger(value) && Number(value) >= 1 && Number(value) <= maximum);
}

function isSourceRef(value: unknown): value is CandidateSourceRefV1 {
  return isRecord(value)
    && hasOnlyKeys(value, ["resource_type", "id", "version"])
    && typeof value.resource_type === "string"
    && /^[a-z][a-z0-9_]{1,63}$/.test(value.resource_type)
    && typeof value.id === "string"
    && value.id.length >= 1
    && value.id.length <= 100
    && Number.isInteger(value.version)
    && Number(value.version) >= 1;
}

function isPlanning(value: unknown): value is VolumePlanningV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "premise",
    "major_conflict",
    "key_turning_points",
    "start_state",
    "end_state",
    "target_chapter_count",
    "target_word_count",
  ])) return false;
  if (
    typeof value.premise !== "string" || value.premise.length > 1000
    || typeof value.major_conflict !== "string" || value.major_conflict.length > 2000
    || typeof value.start_state !== "string" || value.start_state.length > 2000
    || typeof value.end_state !== "string" || value.end_state.length > 2000
    || !Array.isArray(value.key_turning_points)
    || value.key_turning_points.length < 1
    || value.key_turning_points.length > 20
    || !Number.isInteger(value.target_chapter_count)
    || Number(value.target_chapter_count) < 1
    || Number(value.target_chapter_count) > 1000
    || !Number.isInteger(value.target_word_count)
    || Number(value.target_word_count) < 1
    || Number(value.target_word_count) > 10_000_000
  ) return false;
  const points = value.key_turning_points;
  if (!points.every((point) => typeof point === "string" && point.trim().length > 0)) return false;
  const normalized = points.map((point) => normalizeComparableText(String(point)));
  return new Set(normalized).size === normalized.length;
}

function isEditablePackage(value: unknown): value is EditableVolumePackage {
  return isRecord(value)
    && hasOnlyKeys(value, ["title", "subtitle", "summary", "goal", "theme", "planning"])
    && typeof value.title === "string"
    && value.title.trim().length >= 1
    && value.title.length <= 120
    && typeof value.subtitle === "string"
    && value.subtitle.length <= 120
    && typeof value.summary === "string"
    && value.summary.length <= 2000
    && typeof value.goal === "string"
    && value.goal.length <= 1000
    && typeof value.theme === "string"
    && value.theme.length <= 500
    && isPlanning(value.planning);
}

function isSkeletonCandidate(value: unknown): value is VolumeSkeletonCandidateV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "candidate_ref",
    "title",
    "subtitle",
    "order_index",
    "summary",
    "goal",
    "theme",
    "planning",
  ])) return false;
  const { candidate_ref: candidateRef, order_index: orderIndex, ...fields } = value;
  return isLocalCandidateRef(candidateRef)
    && Number.isInteger(orderIndex)
    && Number(orderIndex) >= 1
    && isEditablePackage(fields);
}

function isBasisHeader(
  value: Record<string, unknown>,
  novelId: string,
  contract: typeof SKELETON_CONTRACT | typeof LAUNCH_CONTRACT,
): boolean {
  if (
    !hasCandidateFlow(value)
    || value.novel_id !== novelId
    || value.workflow !== contract.workflow
    || value.step !== contract.step
    || value.schema_id !== contract.schemaId
    || value.schema_version !== contract.schemaVersion
    || typeof value.input_fingerprint !== "string"
    || !/^[0-9a-f]{64}$/.test(value.input_fingerprint)
    || !Array.isArray(value.source_refs)
    || value.source_refs.length < 1
    || value.source_refs.length > 2000
    || !value.source_refs.every(isSourceRef)
  ) return false;
  const sourceKeys = value.source_refs.map((source) => `${source.resource_type}:${source.id}`);
  return new Set(sourceKeys).size === sourceKeys.length;
}

function isSkeletonGenerationInput(value: unknown, novelId: string): value is VolumeSkeletonGenerationInputV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "novel_id",
    "target_volume_count",
    "total_chapter_budget",
    "total_word_budget",
    "mode",
    "target_order_range",
    "novel_expected_version",
    "user_guidance",
    ...REASONING_FIELDS.filter((key) => key in value),
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "system_prompt",
  ])) return false;
  if (
    value.novel_id !== novelId
    || !Number.isInteger(value.target_volume_count)
    || Number(value.target_volume_count) < 1
    || Number(value.target_volume_count) > 30
    || !Number.isInteger(value.total_chapter_budget)
    || Number(value.total_chapter_budget) < 1
    || Number(value.total_chapter_budget) > 1000
    || !Number.isInteger(value.total_word_budget)
    || Number(value.total_word_budget) < 1
    || Number(value.total_word_budget) > 10_000_000
    || !["create", "append", "replan"].includes(String(value.mode))
    || !Number.isInteger(value.novel_expected_version)
    || Number(value.novel_expected_version) < 1
    || typeof value.user_guidance !== "string"
    || value.user_guidance.length > 2000
    || !hasValidReasoningOptions(value)
    || !isNullableNumberInRange(value.temperature, 0, 2)
    || !isNullableNumberInRange(value.top_p, 0, 1)
    || !(value.max_tokens === null || (Number.isInteger(value.max_tokens) && Number(value.max_tokens) > 0))
    || !isNullableNumberInRange(value.presence_penalty, -2, 2)
    || !isNullableNumberInRange(value.frequency_penalty, -2, 2)
    || !(value.system_prompt === null || (typeof value.system_prompt === "string" && value.system_prompt.length <= 40_000))
  ) return false;
  if (value.target_order_range === null) return value.mode !== "replan";
  if (!isRecord(value.target_order_range) || !hasOnlyKeys(value.target_order_range, ["start", "end"])) return false;
  const start = value.target_order_range.start;
  const end = value.target_order_range.end;
  const validRange = Number.isInteger(start)
    && Number.isInteger(end)
    && Number(start) >= 1
    && Number(end) >= Number(start);
  if (!validRange) return false;
  return value.mode !== "replan"
    || Number(value.target_volume_count) === Number(end) - Number(start) + 1;
}

function isLaunchGenerationInput(
  value: unknown,
  novelId: string,
  volumeId: string,
): value is VolumeLaunchGenerationInputV1 {
  return isRecord(value)
    && hasOnlyKeys(value, [
      "novel_id",
      "volume_id",
      "volume_expected_version",
      "target_chapter_count",
      "target_word_count",
      "user_guidance",
      ...REASONING_FIELDS.filter((key) => key in value),
      "temperature",
      "top_p",
      "max_tokens",
      "presence_penalty",
      "frequency_penalty",
      "system_prompt",
    ])
    && value.novel_id === novelId
    && value.volume_id === volumeId
    && Number.isInteger(value.volume_expected_version)
    && Number(value.volume_expected_version) >= 1
    && isNullablePositiveInteger(value.target_chapter_count, 1000)
    && isNullablePositiveInteger(value.target_word_count, 10_000_000)
    && typeof value.user_guidance === "string"
    && value.user_guidance.length <= 2000
    && hasValidReasoningOptions(value)
    && isNullableNumberInRange(value.temperature, 0, 2)
    && isNullableNumberInRange(value.top_p, 0, 1)
    && (value.max_tokens === null || (Number.isInteger(value.max_tokens) && Number(value.max_tokens) > 0))
    && isNullableNumberInRange(value.presence_penalty, -2, 2)
    && isNullableNumberInRange(value.frequency_penalty, -2, 2)
    && (value.system_prompt === null || (typeof value.system_prompt === "string" && value.system_prompt.length <= 40_000));
}

function parseImpact(value: unknown): VolumeDeleteImpactV2 | null {
  try {
    return parseVolumeDeleteImpactV2(value);
  } catch {
    return null;
  }
}

function parseConflictDetail(value: unknown): ConflictDetail | null {
  if (!isRecord(value)) return null;
  const hasVersionPair = Number.isInteger(value.expected_version)
    && Number(value.expected_version) >= 1
    && Number.isInteger(value.actual_version)
    && Number(value.actual_version) >= 1;
  const hasResourcePair = typeof value.resource_type === "string"
    && /^[a-z][a-z0-9_]{1,63}$/.test(value.resource_type)
    && typeof value.id === "string"
    && value.id.length >= 1
    && value.id.length <= 100;
  if (!hasVersionPair && !hasResourcePair) return null;
  return {
    expectedVersion: hasVersionPair ? Number(value.expected_version) : null,
    actualVersion: hasVersionPair ? Number(value.actual_version) : null,
    resourceType: hasResourcePair ? String(value.resource_type) : null,
    resourceId: hasResourcePair ? String(value.id) : null,
  };
}

/**
 * 检查 AI 全书分卷的普通响应或流式最终结果。
 *
 * Args:
 *   value: 待解析的未知响应。
 *   novelId: 当前工作台小说 ID。
 *
 * Returns:
 *   完整契约、预算和顺序均匹配时返回预览，否则返回 null。
 */
export function parseVolumeSkeletonPreview(value: unknown, novelId: string): VolumeSkeletonPreviewV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "workflow",
    "step",
    "schema_id",
    "schema_version",
    "candidate",
    "basis",
    "impacts",
  ])) return null;
  if (
    value.workflow !== SKELETON_CONTRACT.workflow
    || value.step !== SKELETON_CONTRACT.step
    || value.schema_id !== SKELETON_CONTRACT.schemaId
    || value.schema_version !== SKELETON_CONTRACT.schemaVersion
    || !isRecord(value.basis)
    || !hasOnlyKeys(value.basis, [
      "novel_id",
      "workflow",
      "step",
      "schema_id",
      "schema_version",
      "input_fingerprint",
      "source_refs",
      "generation_input",
      "flow_ref",
      "flow_snapshot",
    ])
    || !isBasisHeader(value.basis, novelId, SKELETON_CONTRACT)
    || !isSkeletonGenerationInput(value.basis.generation_input, novelId)
    || !isRecord(value.candidate)
    || !hasOnlyKeys(value.candidate, ["volumes"])
    || !Array.isArray(value.candidate.volumes)
    || value.candidate.volumes.length < 1
    || value.candidate.volumes.length > 30
    || !value.candidate.volumes.every(isSkeletonCandidate)
    || !Array.isArray(value.impacts)
    || value.impacts.length > 30
  ) return null;
  const candidates = [...value.candidate.volumes].sort(
    (left, right) => left.order_index - right.order_index,
  );
  const refs = candidates.map((candidate) => candidate.candidate_ref);
  const titles = candidates.map((candidate) => normalizeComparableText(candidate.title));
  const firstOrder = candidates[0]?.order_index ?? 1;
  const skeletonBasis = value.basis as unknown as VolumeSkeletonBasisV1;
  const input = skeletonBasis.generation_input;
  const novelSourceRefs = skeletonBasis.source_refs.filter(
    (source) => source.resource_type === "novel",
  );
  if (
    candidates.length !== input.target_volume_count
    || novelSourceRefs.length !== 1
    || novelSourceRefs[0].id !== novelId
    || novelSourceRefs[0].version !== input.novel_expected_version
    || new Set(refs).size !== refs.length
    || new Set(titles).size !== titles.length
    || candidates.some((candidate, index) => candidate.order_index !== firstOrder + index)
    || candidates.some((candidate, index) => index > 0
      && normalizeComparableText(candidates[index - 1].planning.end_state)
        !== normalizeComparableText(candidate.planning.start_state))
    || candidates.reduce((sum, candidate) => sum + candidate.planning.target_chapter_count, 0) !== input.total_chapter_budget
    || candidates.reduce((sum, candidate) => sum + candidate.planning.target_word_count, 0) !== input.total_word_budget
  ) return null;
  if (
    input.mode === "replan"
    && (firstOrder !== input.target_order_range?.start
      || candidates.at(-1)?.order_index !== input.target_order_range.end)
  ) return null;
  const impacts = value.impacts.map(parseImpact);
  if (impacts.some((impact) => impact === null)) return null;
  return {
    workflow: SKELETON_CONTRACT.workflow,
    step: SKELETON_CONTRACT.step,
    schema_id: SKELETON_CONTRACT.schemaId,
    schema_version: SKELETON_CONTRACT.schemaVersion,
    candidate: { volumes: candidates },
    basis: skeletonBasis,
    impacts: impacts as VolumeDeleteImpactV2[],
  };
}

/**
 * 检查 AI 完善当前卷的普通响应或流式最终结果。
 *
 * Args:
 *   value: 待解析的未知响应。
 *   novelId: 当前工作台小说 ID。
 *   volumeId: 发起请求时选中的卷 ID。
 *
 * Returns:
 *   信封、目标卷和影响字段完全匹配时返回预览，否则返回 null。
 */
export function parseVolumeLaunchPreview(
  value: unknown,
  novelId: string,
  volumeId: string,
): VolumeLaunchPreviewV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "workflow",
    "step",
    "schema_id",
    "schema_version",
    "candidate",
    "basis",
    "impact",
  ])) return null;
  if (
    value.workflow !== LAUNCH_CONTRACT.workflow
    || value.step !== LAUNCH_CONTRACT.step
    || value.schema_id !== LAUNCH_CONTRACT.schemaId
    || value.schema_version !== LAUNCH_CONTRACT.schemaVersion
    || !isRecord(value.basis)
    || !hasOnlyKeys(value.basis, [
      "novel_id",
      "workflow",
      "step",
      "schema_id",
      "schema_version",
      "input_fingerprint",
      "source_refs",
      "generation_input",
      "flow_ref",
      "flow_snapshot",
    ])
    || !isBasisHeader(value.basis, novelId, LAUNCH_CONTRACT)
    || !isLaunchGenerationInput(value.basis.generation_input, novelId, volumeId)
    || !isRecord(value.candidate)
    || !hasOnlyKeys(value.candidate, ["launch_package"])
    || !isEditablePackage(value.candidate.launch_package)
    || !isRecord(value.impact)
    || !hasOnlyKeys(value.impact, [
      "target_volume_id",
      "previous_volume_id",
      "next_volume_id",
      "downstream",
      "next_start_state_conflict",
      "has_blockers",
    ])
    || value.impact.target_volume_id !== volumeId
    || !(value.impact.previous_volume_id === null || isObjectIdString(value.impact.previous_volume_id))
    || !(value.impact.next_volume_id === null || isObjectIdString(value.impact.next_volume_id))
    || typeof value.impact.next_start_state_conflict !== "boolean"
    || typeof value.impact.has_blockers !== "boolean"
  ) return null;
  const launchBasis = value.basis as unknown as VolumeLaunchBasisV1;
  const novelSourceRefs = launchBasis.source_refs.filter(
    (source) => source.resource_type === "novel",
  );
  const volumeSourceRefs = launchBasis.source_refs.filter(
    (source) => source.resource_type === "volume",
  );
  if (
    novelSourceRefs.length !== 1
    || novelSourceRefs[0].id !== novelId
    || volumeSourceRefs.length < 1
    || volumeSourceRefs.length > 3
    || !volumeSourceRefs.some(
      (source) => source.id === volumeId
        && source.version === launchBasis.generation_input.volume_expected_version,
    )
  ) return null;
  const downstream = parseImpact(value.impact.downstream);
  if (
    !downstream
    || downstream.volume_id !== volumeId
    || value.impact.has_blockers !== downstream.has_blockers
  ) return null;
  const input = launchBasis.generation_input;
  const planning = value.candidate.launch_package.planning;
  if (
    (input.target_chapter_count !== null && planning.target_chapter_count !== input.target_chapter_count)
    || (input.target_word_count !== null && planning.target_word_count !== input.target_word_count)
  ) return null;
  return value as unknown as VolumeLaunchPreviewV1;
}

/**
 * 检查两种确认接口共用的卷响应。
 *
 * Args:
 *   value: 待检查的卷数据。
 *   novelId: 当前工作台锁定的小说 ID。
 *
 * Returns:
 *   字段、所属小说和删除记录都正确时返回卷，否则返回 null。
 */
function parseVolumeReadV2(value: unknown, novelId: string): VolumeReadV2 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "_id",
    "volume_id",
    "novel_id",
    "title",
    "subtitle",
    "summary",
    "goal",
    "theme",
    "order_index",
    "status",
    "planning",
    "arcs_count",
    "word_count",
    "version",
    "is_deleted",
    "deleted_at",
    "created_at",
    "updated_at",
  ], ["chapter_count", "plot", "plot_source_fingerprint", "location_ids", "preparation"])) return null;
  if (
    !isObjectIdString(value._id)
    || value.volume_id !== value._id
    || value.novel_id !== novelId
    || !isObjectIdString(value.novel_id)
    || typeof value.title !== "string"
    || value.title.trim().length < 1
    || value.title.length > 120
    || typeof value.subtitle !== "string"
    || value.subtitle.length > 120
    || typeof value.summary !== "string"
    || value.summary.length > 2000
    || typeof value.goal !== "string"
    || value.goal.length > 1000
    || typeof value.theme !== "string"
    || value.theme.length > 500
    || !Number.isInteger(value.order_index)
    || Number(value.order_index) < 1
    || !["draft", "planned", "active", "completed", "archived"].includes(String(value.status))
    || !(value.planning === null || isPlanning(value.planning))
    // 新旧卷响应都可读取；新增资料字段不能让已成功保存的卷被误判为失败。
    || (value.plot !== undefined && (typeof value.plot !== "string" || value.plot.length > 40000))
    || (value.plot_source_fingerprint !== undefined
      && value.plot_source_fingerprint !== null
      && typeof value.plot_source_fingerprint !== "string")
    || (value.location_ids !== undefined
      && (!Array.isArray(value.location_ids) || value.location_ids.some((id) => typeof id !== "string")))
    || (value.preparation !== undefined
      && (!isRecord(value.preparation) || Object.values(value.preparation).some((fingerprint) => typeof fingerprint !== "string")))
    || !Number.isInteger(value.arcs_count)
    || Number(value.arcs_count) < 0
    || (value.chapter_count !== undefined && (!Number.isInteger(value.chapter_count) || Number(value.chapter_count) < 0))
    || !Number.isInteger(value.word_count)
    || Number(value.word_count) < 0
    || !Number.isInteger(value.version)
    || Number(value.version) < 1
    || typeof value.is_deleted !== "boolean"
    || !(value.deleted_at === null || typeof value.deleted_at === "string")
    || value.is_deleted !== (value.deleted_at !== null)
    || typeof value.created_at !== "string"
    || value.created_at.length < 1
    || typeof value.updated_at !== "string"
    || value.updated_at.length < 1
  ) return null;
  return value as unknown as VolumeReadV2;
}

function parseSkeletonConfirmation(
  value: unknown,
  candidates: VolumeSkeletonCandidateV1[],
  novelId: string,
): VolumeBulkPlanResponseV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ["candidate_ref_map", "volumes"])) return null;
  if (
    !isRecord(value.candidate_ref_map)
    || !Array.isArray(value.volumes)
    || value.volumes.length !== candidates.length
  ) return null;
  const candidateRefMap = value.candidate_ref_map;
  const candidateRefs = candidates.map((candidate) => candidate.candidate_ref);
  if (
    Object.keys(candidateRefMap).length !== candidateRefs.length
    || Object.keys(candidateRefMap).some((candidateRef) => !candidateRefs.includes(candidateRef))
  ) return null;
  const parsedVolumes = value.volumes.map((volume) => parseVolumeReadV2(volume, novelId));
  if (parsedVolumes.some((volume) => volume === null)) return null;
  const volumes = parsedVolumes as VolumeReadV2[];
  if (volumes.some((volume) => volume.planning === null)) return null;
  const volumeIds = volumes.map((volume) => volume.volume_id);
  const mappedIds = candidateRefs.map((candidateRef) => candidateRefMap[candidateRef]);
  if (
    mappedIds.some((volumeId) => !isObjectIdString(volumeId))
    || new Set(mappedIds).size !== mappedIds.length
    || new Set(volumeIds).size !== volumeIds.length
    || mappedIds.some((volumeId) => !volumeIds.includes(String(volumeId)))
  ) return null;
  for (const candidate of candidates) {
    const mappedVolume = volumes.find(
      (volume) => volume.volume_id === candidateRefMap[candidate.candidate_ref],
    );
    const expected = normalizePackage(candidate);
    if (
      !mappedVolume
      || mappedVolume.order_index !== candidate.order_index
      || mappedVolume.title !== expected.title
      || mappedVolume.subtitle !== expected.subtitle
      || mappedVolume.summary !== expected.summary
      || mappedVolume.goal !== expected.goal
      || mappedVolume.theme !== expected.theme
      || JSON.stringify(mappedVolume.planning) !== JSON.stringify(expected.planning)
    ) return null;
  }
  return { candidate_ref_map: candidateRefMap as Record<string, string>, volumes };
}

function parseLaunchConfirmation(
  value: unknown,
  novelId: string,
  volumeId: string,
  request: VolumeLaunchConfirmV1,
): VolumeReadV2 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, ["success", "data"]) || value.success !== true) return null;
  const volume = parseVolumeReadV2(value.data, novelId);
  if (
    !volume
    || volume.volume_id !== volumeId
    || volume.version !== request.expected_version + 1
    || volume.planning === null
    || volume.title !== request.title
    || volume.subtitle !== request.subtitle
    || volume.summary !== request.summary
    || volume.goal !== request.goal
    || volume.theme !== request.theme
    || JSON.stringify(volume.planning) !== JSON.stringify(request.planning)
  ) return null;
  return volume;
}

function normalizePackage(value: EditableVolumePackage): EditableVolumePackage {
  return {
    title: value.title.trim(),
    subtitle: value.subtitle.trim(),
    summary: value.summary.trim(),
    goal: value.goal.trim(),
    theme: value.theme.trim(),
    planning: {
      premise: value.planning.premise.trim(),
      major_conflict: value.planning.major_conflict.trim(),
      key_turning_points: value.planning.key_turning_points.map((point) => point.trim()).filter(Boolean),
      start_state: value.planning.start_state.trim(),
      end_state: value.planning.end_state.trim(),
      target_chapter_count: value.planning.target_chapter_count,
      target_word_count: value.planning.target_word_count,
    },
  };
}

function validatePackage(value: EditableVolumePackage, duplicateTitle: boolean, t: ReturnType<typeof useTranslations>): ApiFieldErrors {
  const errors: ApiFieldErrors = {};
  if (!value.title.trim()) errors.title = [t("validation.titleRequired")];
  else if (duplicateTitle) errors.title = [t("ai.validation.duplicateTitle")];
  const normalizedPoints = value.planning.key_turning_points.map(normalizeComparableText);
  if (
    normalizedPoints.length < 1
    || normalizedPoints.length > 20
    || normalizedPoints.some((point) => !point)
    || new Set(normalizedPoints).size !== normalizedPoints.length
  ) errors.key_turning_points = [t("ai.validation.turningPoints")];
  if (!Number.isInteger(value.planning.target_chapter_count) || value.planning.target_chapter_count < 1 || value.planning.target_chapter_count > 1000) {
    errors.target_chapter_count = [t("validation.targetChapterCount")];
  }
  if (!Number.isInteger(value.planning.target_word_count) || value.planning.target_word_count < 1 || value.planning.target_word_count > 10_000_000) {
    errors.target_word_count = [t("validation.targetWordCount")];
  }
  return errors;
}

function focusCandidateError(workspaceId: string, fieldErrors: ApiFieldErrors): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const workspace = document.getElementById(workspaceId);
      if (!workspace) return;
      const firstField = Object.keys(fieldErrors)[0]?.split(".").at(-1);
      const field = firstField
        ? workspace.querySelector<HTMLElement>(`[name="${firstField}"]`)
        : null;
      const target = field ?? workspace.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    });
  });
}

function normalizeSkeletonFieldErrors(
  fieldErrors: ApiFieldErrors,
  candidates: VolumeSkeletonCandidateV1[],
): Record<string, ApiFieldErrors> {
  const result: Record<string, ApiFieldErrors> = {};
  for (const [path, messages] of Object.entries(fieldErrors)) {
    const parts = path.split(".");
    const marker = parts.indexOf("candidates");
    const candidateToken = marker >= 0 ? parts[marker + 1] : undefined;
    const index = Number(candidateToken);
    const candidate = Number.isInteger(index)
      ? candidates[index]
      : candidates.find((item) => item.candidate_ref === candidateToken) ?? candidates[0];
    if (!candidate) continue;
    const field = parts.at(-1) ?? path;
    result[candidate.candidate_ref] = {
      ...(result[candidate.candidate_ref] ?? {}),
      [field]: [...(result[candidate.candidate_ref]?.[field] ?? []), ...messages],
    };
  }
  return result;
}

/**
 * 渲染 AI 全书分卷和完善当前卷的参数、进度、结果与确认入口。
 *
 * Args:
 *   novelId: 当前小说 ID。
 *   volumes: 当前页面已读取的全部活动卷。
 *   selectedVolume: 当前卷；没有卷时不能完善当前卷。
 *   disabled: 数据仍在加载或页面正在执行其他操作时禁用 AI 入口。
 *   onReviewingChange: AI 结果进入或离开检查页面时通知上层页面。
 *   onBusyChange: 生成或确认期间通知上层页面禁用其他修改入口。
 *   onSkeletonConfirmed: 全书分卷确认成功回调。
 *   onLaunchConfirmed: 当前卷确认成功回调。
 *
 * Returns:
 *   卷骨架保留页面候选；单卷候选同时保存到浏览器本地稿。
 */
export default function VolumePlanningCandidateWorkspace({
  task,
  novelId,
  volumes,
  selectedVolume,
  disabled = false,
  onReviewingChange,
  onBusyChange,
  onSkeletonConfirmed,
  onLaunchConfirmed,
}: VolumePlanningCandidateWorkspaceProps) {
  const t = useTranslations("writing.volumes");
  const aiT = useTranslations("writing.volumes.ai");
  const hierarchyT = useTranslations("writing.hierarchy");
  const launchDraftFailureMessage = hierarchyT("draftFailed");
  const skeletonFlow = useTaskFlow("create_volume_skeleton_by_ai");
  const launchFlow = useTaskFlow("plan_volume_launch_by_ai");
  const [skeletonDialogOpen, setSkeletonDialogOpen] = useState(false);
  const [launchDialogOpen, setLaunchDialogOpen] = useState(false);
  const [skeletonState, dispatchSkeleton] = useReducer(
    localCandidateReducer<VolumeSkeletonResultV1>,
    createLocalCandidateState<VolumeSkeletonResultV1>(),
  );
  const [launchState, dispatchLaunch] = useReducer(
    localCandidateReducer<VolumeLaunchPackageResultV1>,
    createLocalCandidateState<VolumeLaunchPackageResultV1>(),
  );
  const [skeletonImpacts, setSkeletonImpacts] = useState<VolumeDeleteImpactV2[]>([]);
  const [launchImpact, setLaunchImpact] = useState<VolumeLaunchImpactV1 | null>(null);
  const [skeletonConflictDetail, setSkeletonConflictDetail] = useState<ConflictDetail | null>(null);
  const [launchConflictDetail, setLaunchConflictDetail] = useState<ConflictDetail | null>(null);
  const [selectedCandidateRef, setSelectedCandidateRef] = useState("");
  const [candidateSearch, setCandidateSearch] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [candidateFieldErrors, setCandidateFieldErrors] = useState<Record<string, ApiFieldErrors>>({});
  const [launchFieldErrors, setLaunchFieldErrors] = useState<ApiFieldErrors>({});
  const [novelVersion, setNovelVersion] = useState<number | null>(null);
  const [novelVersionLoading, setNovelVersionLoading] = useState(false);
  const [novelVersionError, setNovelVersionError] = useState("");
  const [novelBudget, setNovelBudget] = useState<{ novelId: string; chapters: number; words: number } | null>(null);
  const editedSkeletonBudgets = useRef(new Set<string>());
  const skeletonTriggerRef = useRef<HTMLButtonElement | null>(null);
  const launchTriggerRef = useRef<HTMLButtonElement | null>(null);
  const novelVersionAbortRef = useRef<AbortController | null>(null);
  const skeletonGenerationAbortRef = useRef<AbortController | null>(null);
  const skeletonConfirmationAbortRef = useRef<AbortController | null>(null);
  const launchGenerationAbortRef = useRef<AbortController | null>(null);
  const launchConfirmationAbortRef = useRef<AbortController | null>(null);
  const skeletonConfirmCommandRef = useRef<StableConfirmCommand | null>(null);
  const launchConfirmCommandRef = useRef<StableConfirmCommand | null>(null);
  const launchDraftWrites = useRef(Promise.resolve());
  const launchDraftVersion = useRef(selectedVolume?.version ?? 1);
  const latestSelectedVolume = useRef(selectedVolume);
  latestSelectedVolume.current = selectedVolume;
  const persistLaunch = task === "launch" || task === "all";
  const launchDraftKey = persistLaunch && selectedVolume ? `${novelId}:volume:${selectedVolume.volume_id}:launch` : null;
  const [restoredLaunchKey, setRestoredLaunchKey] = useState<string | null>(null);
  const [launchDraftError, setLaunchDraftError] = useState("");
  const launchDraftReady = !launchDraftKey || restoredLaunchKey === launchDraftKey;
  const skeletonPreviewVolumeSignatureRef = useRef("");
  const localCandidateCounterRef = useRef(0);
  const currentNovelIdRef = useRef(novelId);
  const currentVolumeIdRef = useRef(selectedVolume?.volume_id ?? "");
  const onReviewingChangeRef = useRef(onReviewingChange);
  const onBusyChangeRef = useRef(onBusyChange);
  currentNovelIdRef.current = novelId;
  currentVolumeIdRef.current = selectedVolume?.volume_id ?? "";
  onReviewingChangeRef.current = onReviewingChange;
  onBusyChangeRef.current = onBusyChange;

  const skeletonCandidates = skeletonState.candidate?.volumes ?? [];
  const skeletonBasis = skeletonState.basis as VolumeSkeletonBasisV1 | null;
  const normalizedCandidateSearch = normalizeComparableText(candidateSearch);
  const visibleSkeletonCandidates = skeletonCandidates.filter((candidate) => {
    if (!normalizedCandidateSearch) return true;
    return [candidate.title, candidate.subtitle, candidate.summary, candidate.goal, candidate.theme]
      .join(" ")
      .normalize("NFKC")
      .replace(/\s+/g, " ")
      .toLowerCase()
      .includes(normalizedCandidateSearch);
  });
  const selectedSkeletonCandidate = visibleSkeletonCandidates.find((candidate) => candidate.candidate_ref === selectedCandidateRef)
    ?? visibleSkeletonCandidates[0]
    ?? null;
  const skeletonReviewing = Boolean(skeletonState.candidate);
  const launchReviewing = Boolean(launchState.candidate);
  const reviewing = skeletonReviewing || launchReviewing;
  const busy = skeletonState.status === "generating"
    || skeletonState.status === "confirming"
    || launchState.status === "generating"
    || launchState.status === "confirming";
  const skeletonReadOnly = disabled || skeletonState.status === "stale" || skeletonState.status === "confirming";
  const launchReadOnly = disabled || launchState.status === "stale" || launchState.status === "confirming";
  const launchRetryOnly = persistLaunch && Boolean(launchConfirmCommandRef.current) && launchState.status !== "stale";
  const formalVolumeSignature = useMemo(
    () => volumes.map((volume) => `${volume.volume_id}:${volume.version}:${volume.order_index}`).join("|"),
    [volumes],
  );
  const orderedVolumes = useMemo(
    () => [...volumes].sort((left, right) => left.order_index - right.order_index),
    [volumes],
  );
  const selectedFormalVolumeIndex = orderedVolumes.findIndex(
    (volume) => volume.volume_id === selectedVolume?.volume_id,
  );
  const previousVolume = selectedFormalVolumeIndex > 0
    ? orderedVolumes[selectedFormalVolumeIndex - 1]
    : null;
  const nextVolume = selectedFormalVolumeIndex >= 0
    ? orderedVolumes[selectedFormalVolumeIndex + 1] ?? null
    : null;
  const launchPackage = launchState.candidate?.launch_package ?? null;
  const launchNextStateConflict = Boolean(
    launchPackage
    && nextVolume?.planning
    && normalizeComparableText(launchPackage.planning.end_state)
      !== normalizeComparableText(nextVolume.planning.start_state),
  );
  const displayedLaunchImpact = launchImpact
    ? { ...launchImpact, next_start_state_conflict: launchNextStateConflict }
    : null;

  const skeletonDefinition = skeletonFlow.definition;
  const skeletonBudgetKey = `${novelId}:${skeletonDefinition?.id}:${skeletonDefinition?.revision}`;
  const setSkeletonInputs = skeletonFlow.setInputs;
  useEffect(() => {
    if (!skeletonDialogOpen || volumes.length || novelBudget?.novelId !== novelId
      || skeletonDefinition?.id !== "default_create_volume_skeleton_by_ai"
      || (skeletonFlow.inputs.mode && skeletonFlow.inputs.mode !== "create")) return;
    const defaults = taskFlowDefaultInputs(skeletonDefinition);
    // 小说读取晚到、重开弹窗或刷新方案时，不能覆盖作者已经填过的预算。
    setSkeletonInputs((current) => {
      const next = { ...current };
      if (current.mode === "") next.mode = "create";
      for (const [field, value] of [["total_chapter_budget", novelBudget.chapters], ["total_word_budget", novelBudget.words]] as const) {
        if (Number.isInteger(value) && value > 0 && Object.hasOwn(defaults, field)
          && current[field] === defaults[field] && !editedSkeletonBudgets.current.has(`${skeletonBudgetKey}:${field}`)) next[field] = value;
      }
      return next;
    });
  }, [novelBudget, novelId, setSkeletonInputs, skeletonBudgetKey, skeletonDefinition, skeletonDialogOpen, skeletonFlow.inputs.mode, volumes.length]);

  useLayoutEffect(() => {
    onReviewingChange?.(reviewing);
  }, [onReviewingChange, reviewing]);

  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  useEffect(() => {
    if (skeletonState.status !== "generating") return;
    let innerFrame = 0;
    const outerFrame = requestAnimationFrame(() => {
      innerFrame = requestAnimationFrame(() => {
        document.getElementById("volume-ai-skeleton-cancel")?.focus({ preventScroll: true });
      });
    });
    return () => {
      cancelAnimationFrame(outerFrame);
      if (innerFrame) cancelAnimationFrame(innerFrame);
    };
  }, [skeletonState.status]);

  useEffect(() => {
    if (launchState.status !== "generating") return;
    let innerFrame = 0;
    const outerFrame = requestAnimationFrame(() => {
      innerFrame = requestAnimationFrame(() => {
        document.getElementById("volume-ai-launch-cancel")?.focus({ preventScroll: true });
      });
    });
    return () => {
      cancelAnimationFrame(outerFrame);
      if (innerFrame) cancelAnimationFrame(innerFrame);
    };
  }, [launchState.status]);

  useEffect(() => {
    if (skeletonState.status !== "preview") return;
    let innerFrame = 0;
    const outerFrame = requestAnimationFrame(() => {
      innerFrame = requestAnimationFrame(() => {
        const target = document.querySelector<HTMLElement>(
          "#volume-skeleton-candidate-workspace [role='option']",
        ) ?? document.getElementById("volume-skeleton-candidate-heading");
        target?.focus({ preventScroll: true });
      });
    });
    return () => {
      cancelAnimationFrame(outerFrame);
      if (innerFrame) cancelAnimationFrame(innerFrame);
    };
  }, [skeletonState.status]);

  useEffect(() => {
    if (launchState.status !== "preview") return;
    let innerFrame = 0;
    const outerFrame = requestAnimationFrame(() => {
      innerFrame = requestAnimationFrame(() => {
        document.getElementById("volume-launch-candidate-heading")?.focus({ preventScroll: true });
      });
    });
    return () => {
      cancelAnimationFrame(outerFrame);
      if (innerFrame) cancelAnimationFrame(innerFrame);
    };
  }, [launchState.status]);

  useEffect(() => () => {
    onReviewingChangeRef.current?.(false);
    onBusyChangeRef.current?.(false);
  }, []);

  useEffect(() => {
    if (
      skeletonState.basis
      && skeletonState.status !== "stale"
      && skeletonPreviewVolumeSignatureRef.current
      && skeletonPreviewVolumeSignatureRef.current !== formalVolumeSignature
    ) {
      const basis = skeletonState.basis as VolumeSkeletonBasisV1;
      const basisVolumeRefs = basis.source_refs.filter((source) => source.resource_type === "volume");
      const changedBasisRef = basisVolumeRefs.find((source) => {
        const current = volumes.find((volume) => volume.volume_id === source.id);
        return !current || current.version !== source.version;
      });
      const addedVolume = volumes.find((volume) => !basisVolumeRefs.some(
        (source) => source.id === volume.volume_id,
      ));
      const changedId = changedBasisRef?.id ?? addedVolume?.volume_id ?? null;
      const currentChangedVolume = changedId
        ? volumes.find((volume) => volume.volume_id === changedId)
        : null;
      dispatchSkeleton({ type: "mark_stale" });
      setSkeletonImpacts([]);
      setSkeletonConflictDetail(changedId
        ? {
            expectedVersion: changedBasisRef?.version ?? null,
            actualVersion: currentChangedVolume?.version ?? null,
            resourceType: "volume",
            resourceId: changedId,
          }
        : null);
    }
  }, [formalVolumeSignature, skeletonState.basis, skeletonState.status, volumes]);

  useEffect(() => {
    if (!launchState.basis || launchState.status === "stale" || !selectedVolume) return;
    // 请求可能已保存但响应丢失；先允许用落盘的原键取回结果。
    if (persistLaunch && launchConfirmCommandRef.current) return;
    const basis = launchState.basis as VolumeLaunchBasisV1;
    const expectedVolumeRefs = [previousVolume, selectedVolume, nextVolume]
      .filter((volume): volume is VolumeReadV2 => volume !== null)
      .map((volume) => ({ id: volume.volume_id, version: volume.version }));
    const basisVolumeRefs = basis.source_refs
      .filter((source) => source.resource_type === "volume")
      .map((source) => ({ id: source.id, version: source.version }));
    if (
      basis.generation_input.volume_id !== selectedVolume.volume_id
      || basis.generation_input.volume_expected_version !== selectedVolume.version
      || basisVolumeRefs.length !== expectedVolumeRefs.length
      || expectedVolumeRefs.some((expected) => !basisVolumeRefs.some(
        (source) => source.id === expected.id && source.version === expected.version,
      ))
    ) {
      const changedBasisRef = basisVolumeRefs.find((source) => {
        const current = expectedVolumeRefs.find((expected) => expected.id === source.id);
        return !current || current.version !== source.version;
      });
      const addedRef = expectedVolumeRefs.find((expected) => !basisVolumeRefs.some(
        (source) => source.id === expected.id,
      ));
      const changedId = changedBasisRef?.id ?? addedRef?.id ?? null;
      const currentRef = changedId
        ? expectedVolumeRefs.find((expected) => expected.id === changedId)
        : null;
      dispatchLaunch({ type: "mark_stale" });
      setLaunchImpact(null);
      setLaunchConflictDetail(changedId
        ? {
            expectedVersion: changedBasisRef?.version ?? null,
            actualVersion: currentRef?.version ?? null,
            resourceType: "volume",
            resourceId: changedId,
          }
        : null);
    }
  }, [launchState.basis, launchState.candidate, launchState.status, nextVolume, previousVolume, selectedVolume, persistLaunch]);

  useEffect(() => {
    // 切换小说或卷后，旧结果不再适用，所以中止请求并清空结果。
    novelVersionAbortRef.current?.abort();
    skeletonGenerationAbortRef.current?.abort();
    skeletonConfirmationAbortRef.current?.abort();
    launchGenerationAbortRef.current?.abort();
    launchConfirmationAbortRef.current?.abort();
    novelVersionAbortRef.current = null;
    skeletonGenerationAbortRef.current = null;
    skeletonConfirmationAbortRef.current = null;
    launchGenerationAbortRef.current = null;
    launchConfirmationAbortRef.current = null;
    dispatchSkeleton({ type: "discard" });
    dispatchLaunch({ type: "discard" });
    setSkeletonDialogOpen(false);
    setLaunchDialogOpen(false);
    setSkeletonImpacts([]);
    setLaunchImpact(null);
    setSkeletonConflictDetail(null);
    setLaunchConflictDetail(null);
    setCandidateFieldErrors({});
    setLaunchFieldErrors({});
    setSelectedCandidateRef("");
    setCandidateSearch("");
    setMobileDetailOpen(false);
    setNovelVersion(null);
    setNovelVersionError("");
    skeletonConfirmCommandRef.current = null;
    launchConfirmCommandRef.current = null;
    skeletonPreviewVolumeSignatureRef.current = "";
    return () => {
      novelVersionAbortRef.current?.abort();
      skeletonGenerationAbortRef.current?.abort();
      skeletonConfirmationAbortRef.current?.abort();
      launchGenerationAbortRef.current?.abort();
      launchConfirmationAbortRef.current?.abort();
    };
  }, [novelId, selectedVolume?.volume_id]);

  useEffect(() => {
    if (!launchDraftKey) return;
    let active = true;
    setRestoredLaunchKey(null);
    setLaunchDraftError("");
    const version = latestSelectedVolume.current!.version;
    launchDraftVersion.current = version;
    void launchDraftWrites.current.then(() => readWritingDraft<LaunchDraft>(launchDraftKey, version)).then((draft) => {
      if (!active || !draft) return;
      launchDraftVersion.current = draft.base_version;
      launchConfirmCommandRef.current = draft.value.command;
      const requestId = Date.now();
      dispatchLaunch({ type: "generate", requestId });
      dispatchLaunch({ type: "preview", requestId, candidate: draft.value.candidate, basis: draft.value.basis });
      if (draft.value.stale) dispatchLaunch({ type: "mark_stale" });
      // 旧本地预览还没有章后记录计数；只补本地读入值，原确认请求和键保持不变。
      const savedImpact = draft.value.impact;
      setLaunchImpact(savedImpact && savedImpact.downstream.chapter_records === undefined
        ? { ...savedImpact, downstream: { ...savedImpact.downstream, chapter_records: 0 } }
        : savedImpact);
    }).catch(() => { if (active) setLaunchDraftError(launchDraftFailureMessage); })
      .finally(() => { if (active) setRestoredLaunchKey(launchDraftKey); });
    return () => { active = false; };
  }, [launchDraftKey, launchDraftFailureMessage]);

  useEffect(() => {
    if (!launchDraftKey || !launchDraftReady || !launchState.candidate || !launchState.basis || launchState.status === "confirming") return;
    const basis = launchState.basis as VolumeLaunchBasisV1;
    const version = basis.generation_input.volume_expected_version;
    launchDraftVersion.current = version;
    const draft: LaunchDraft = { candidate: launchState.candidate, basis, impact: launchImpact, command: launchConfirmCommandRef.current, stale: launchState.status === "stale" };
    launchDraftWrites.current = launchDraftWrites.current.then(() => writeWritingDraft(launchDraftKey, version, draft))
      .catch(() => setLaunchDraftError(launchDraftFailureMessage));
  }, [launchDraftKey, launchDraftReady, launchState.candidate, launchState.basis, launchState.status, launchImpact, launchDraftFailureMessage]);

  const loadNovelVersion = useCallback(async () => {
    novelVersionAbortRef.current?.abort();
    const controller = new AbortController();
    const requestNovelId = novelId;
    novelVersionAbortRef.current = controller;
    setNovelVersionLoading(true);
    setNovelVersionError("");
    try {
      const response = await apiGet<unknown>(`/api/novels/${novelId}`, { signal: controller.signal });
      if (
        controller.signal.aborted
        || novelVersionAbortRef.current !== controller
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      if (
        !isRecord(response)
        || response.id !== requestNovelId
        || !Number.isInteger(response.version)
        || Number(response.version) < 1
      ) throw new Error(aiT("errors.novelVersion"));
      setNovelVersion(Number(response.version));
      const chapters = Number(response.number_of_chapters);
      const wordsPerChapter = Number(response.words_per_chapter);
      setNovelBudget({ novelId: requestNovelId, chapters, words: chapters * wordsPerChapter });
    } catch (error) {
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
      setNovelVersion(null);
      setNovelVersionError(error instanceof Error ? error.message : aiT("errors.novelVersion"));
    } finally {
      if (novelVersionAbortRef.current === controller) {
        novelVersionAbortRef.current = null;
        setNovelVersionLoading(false);
      }
    }
  }, [aiT, novelId]);

  const closeSkeletonDialog = () => {
    novelVersionAbortRef.current?.abort();
    novelVersionAbortRef.current = null;
    setNovelVersionLoading(false);
    setSkeletonDialogOpen(false);
    requestAnimationFrame(() => skeletonTriggerRef.current?.focus());
  };

  const closeLaunchDialog = () => {
    setLaunchDialogOpen(false);
    requestAnimationFrame(() => launchTriggerRef.current?.focus());
  };

  const openSkeletonDialog = () => {
    if (disabled || busy || reviewing) return;
    const defaultMode: VolumeSkeletonMode = volumes.length === 0 ? "create" : "append";
    if (Object.hasOwn(skeletonFlow.inputs, "mode")) skeletonFlow.setInputs((current) => ({ ...current, mode: !current.mode || current.mode === "create" && volumes.length > 0 ? defaultMode : current.mode }));
    setSkeletonDialogOpen(true);
    void loadNovelVersion();
  };

  const openLaunchDialog = () => {
    if (disabled || busy || reviewing || !selectedVolume) return;
    setLaunchDialogOpen(true);
  };

  const discardSkeleton = () => {
    void skeletonFlow.discard();

    skeletonGenerationAbortRef.current?.abort();
    skeletonConfirmationAbortRef.current?.abort();
    skeletonGenerationAbortRef.current = null;
    skeletonConfirmationAbortRef.current = null;
    dispatchSkeleton({ type: "discard" });
    setSkeletonImpacts([]);
    setSkeletonConflictDetail(null);
    setSelectedCandidateRef("");
    setCandidateSearch("");
    setCandidateFieldErrors({});
    setMobileDetailOpen(false);
    skeletonConfirmCommandRef.current = null;
    skeletonPreviewVolumeSignatureRef.current = "";
    requestAnimationFrame(() => document.getElementById("volume-ai-skeleton-trigger")?.focus());
  };

  const discardLaunch = async () => {
    if (launchRetryOnly) return;
    void launchFlow.discard();

    launchGenerationAbortRef.current?.abort();
    launchConfirmationAbortRef.current?.abort();
    launchGenerationAbortRef.current = null;
    launchConfirmationAbortRef.current = null;
    if (launchDraftKey) {
      try {
        await launchDraftWrites.current;
        await writeWritingDraft(launchDraftKey, launchDraftVersion.current, null);
      } catch {
        setLaunchDraftError(launchDraftFailureMessage);
        return;
      }
      if (launchDraftKey !== `${currentNovelIdRef.current}:volume:${currentVolumeIdRef.current}:launch`) return;
    }
    dispatchLaunch({ type: "discard" });
    setLaunchImpact(null);
    setLaunchConflictDetail(null);
    setLaunchFieldErrors({});
    launchConfirmCommandRef.current = null;
    setLaunchDraftError("");
    requestAnimationFrame(() => document.getElementById("volume-ai-launch-trigger")?.focus());
  };

  const generateSkeleton = async (retry: TaskFlowRunMode = false) => {
    if (
      disabled
      || novelVersion === null
      || skeletonGenerationAbortRef.current
      || skeletonState.candidate
    ) return;
    const requestId = skeletonState.requestId + 1;
    const requestNovelId = novelId;
    const controller = new AbortController();
    skeletonGenerationAbortRef.current = controller;
    dispatchSkeleton({ type: "generate", requestId });
    setSkeletonDialogOpen(false);
    setSkeletonImpacts([]);
    setSkeletonConflictDetail(null);

    try {
      const generated = await skeletonFlow.run(`/api/llm/novels/${novelId}/planning/volume-skeleton/stream`, { novel_id: requestNovelId, novel_expected_version: novelVersion }, controller.signal, retry);
      if (controller.signal.aborted || skeletonGenerationAbortRef.current !== controller || currentNovelIdRef.current !== requestNovelId) return;
      const request = generated.generationInput as VolumeSkeletonGenerationInputV1;
      const expectedInput = request;
      const preview = parseVolumeSkeletonPreview(generated.result, requestNovelId);
      if (!preview || JSON.stringify(preview.basis.generation_input) !== JSON.stringify(expectedInput)) {
        throw new Error(aiT("errors.invalidPreview"));
      }
      const generatedVolumes = preview.candidate.volumes;
      const generatedTitles = new Set(generatedVolumes.map((volume) => normalizeComparableText(volume.title)));
      const targetRange = request.target_order_range;
      const outsideTitles = new Set(orderedVolumes
        .filter((volume) => request.mode !== "replan"
          || !targetRange
          || volume.order_index < targetRange.start
          || volume.order_index > targetRange.end)
        .map((volume) => normalizeComparableText(volume.title)));
      const titleConflict = [...generatedTitles].some((title) => outsideTitles.has(title));
      const expectedFirstOrder = request.mode === "append"
        ? orderedVolumes.length + 1
        : request.mode === "create"
          ? 1
          : targetRange?.start;
      const previousPlanning = request.mode === "append"
        ? orderedVolumes.at(-1)?.planning
        : request.mode === "replan" && targetRange
          ? orderedVolumes.find((volume) => volume.order_index === targetRange.start - 1)?.planning
          : null;
      const nextPlanning = request.mode === "replan" && targetRange
        ? orderedVolumes.find((volume) => volume.order_index === targetRange.end + 1)?.planning
        : null;
      const expectedImpactIds = request.mode === "replan" && targetRange
        ? orderedVolumes
            .filter((volume) => volume.order_index >= targetRange.start && volume.order_index <= targetRange.end)
            .map((volume) => volume.volume_id)
            .sort()
        : [];
      const actualImpactIds = preview.impacts.map((impact) => impact.volume_id).sort();
      if (
        titleConflict
        || generatedVolumes[0]?.order_index !== expectedFirstOrder
        || (
          previousPlanning
          && normalizeComparableText(previousPlanning.end_state)
            !== normalizeComparableText(generatedVolumes[0].planning.start_state)
        )
        || (
          nextPlanning
          && normalizeComparableText(generatedVolumes.at(-1)?.planning.end_state ?? "")
            !== normalizeComparableText(nextPlanning.start_state)
        )
        || JSON.stringify(actualImpactIds) !== JSON.stringify(expectedImpactIds)
      ) throw new Error(aiT("errors.invalidPreview"));
      dispatchSkeleton({
        type: "preview",
        requestId,
        candidate: structuredClone(preview.candidate),
        basis: preview.basis,
      });
      setSkeletonImpacts(preview.impacts);
      setSelectedCandidateRef(preview.candidate.volumes[0]?.candidate_ref ?? "");
      setCandidateSearch("");
      setCandidateFieldErrors({});
      skeletonPreviewVolumeSignatureRef.current = formalVolumeSignature;
    } catch (error) {
      if (!controller.signal.aborted && currentNovelIdRef.current === requestNovelId) {
        let message = aiT("errors.generate");
        if (error instanceof ApiRequestError) {
          if (typeof error.details.message === "string") message = error.details.message;
          else if (error.status === 409) message = error.message;
          else if (error.status === 422) message = aiT("errors.request");
          else if (error.status === 502) message = aiT("errors.invalidPreview");
          else if (error.status === 503) message = aiT("errors.providerUnavailable");
          else if (error.status === 504) message = aiT("errors.timeout");
        } else if (error instanceof Error && error.message === aiT("errors.invalidPreview")) {
          message = aiT("errors.invalidPreview");
        }
        dispatchSkeleton({ type: "generation_failed", requestId, message });
      }
    } finally {
      if (skeletonGenerationAbortRef.current === controller) skeletonGenerationAbortRef.current = null;
    }
  };

  const generateLaunch = async (retry: TaskFlowRunMode = false) => {
    if (
      disabled
      || !selectedVolume
      || !launchDraftReady
      || launchGenerationAbortRef.current
      || launchState.candidate
    ) return;
    const requestId = launchState.requestId + 1;
    const requestNovelId = novelId;
    const requestVolumeId = selectedVolume.volume_id;
    const requestPreviousVolume = previousVolume;
    const requestNextVolume = nextVolume;
    const controller = new AbortController();
    launchGenerationAbortRef.current = controller;
    dispatchLaunch({ type: "generate", requestId });
    setLaunchDialogOpen(false);
    setLaunchImpact(null);
    setLaunchConflictDetail(null);

    try {
      const generated = await launchFlow.run(`/api/llm/novels/${novelId}/planning/volumes/${requestVolumeId}/launch-package/stream`, { novel_id: requestNovelId, volume_id: requestVolumeId, volume_expected_version: selectedVolume.version }, controller.signal, retry);
      if (controller.signal.aborted || launchGenerationAbortRef.current !== controller || currentNovelIdRef.current !== requestNovelId || currentVolumeIdRef.current !== requestVolumeId) return;
      const request = generated.generationInput as VolumeLaunchGenerationInputV1;
      const expectedInput = request;
      const preview = parseVolumeLaunchPreview(generated.result, requestNovelId, requestVolumeId);
      const expectedVolumeRefs = [requestPreviousVolume, selectedVolume, requestNextVolume]
        .filter((volume): volume is VolumeReadV2 => volume !== null)
        .map((volume) => `${volume.volume_id}:${volume.version}`)
        .sort();
      const previewVolumeRefs = preview?.basis.source_refs
        .filter((source) => source.resource_type === "volume")
        .map((source) => `${source.id}:${source.version}`)
        .sort() ?? [];
      const candidatePlanning = preview?.candidate.launch_package.planning;
      const expectedChapterCount = request.target_chapter_count
        ?? selectedVolume.planning?.target_chapter_count;
      const expectedWordCount = request.target_word_count
        ?? selectedVolume.planning?.target_word_count;
      const expectedNextConflict = Boolean(
        candidatePlanning
        && requestNextVolume?.planning
        && normalizeComparableText(candidatePlanning.end_state)
          !== normalizeComparableText(requestNextVolume.planning.start_state),
      );
      if (
        !preview
        || JSON.stringify(preview.basis.generation_input) !== JSON.stringify(expectedInput)
        || JSON.stringify(previewVolumeRefs) !== JSON.stringify(expectedVolumeRefs)
        || preview.impact.previous_volume_id !== (requestPreviousVolume?.volume_id ?? null)
        || preview.impact.next_volume_id !== (requestNextVolume?.volume_id ?? null)
        || candidatePlanning?.target_chapter_count !== expectedChapterCount
        || candidatePlanning?.target_word_count !== expectedWordCount
        || (
          requestPreviousVolume?.planning
          && normalizeComparableText(requestPreviousVolume.planning.end_state)
            !== normalizeComparableText(candidatePlanning?.start_state ?? "")
        )
        || preview.impact.next_start_state_conflict !== expectedNextConflict
      ) {
        throw new Error(aiT("errors.invalidPreview"));
      }
      dispatchLaunch({
        type: "preview",
        requestId,
        candidate: structuredClone(preview.candidate),
        basis: preview.basis,
      });
      setLaunchImpact(preview.impact);
      setLaunchFieldErrors({});
    } catch (error) {
      if (
        !controller.signal.aborted
        && currentNovelIdRef.current === requestNovelId
        && currentVolumeIdRef.current === requestVolumeId
      ) {
        let message = aiT("errors.generate");
        if (error instanceof ApiRequestError) {
          if (typeof error.details.message === "string") message = error.details.message;
          else if (error.status === 409) message = error.message;
          else if (error.status === 422) message = aiT("errors.request");
          else if (error.status === 502) message = aiT("errors.invalidPreview");
          else if (error.status === 503) message = aiT("errors.providerUnavailable");
          else if (error.status === 504) message = aiT("errors.timeout");
        } else if (error instanceof Error && error.message === aiT("errors.invalidPreview")) {
          message = aiT("errors.invalidPreview");
        }
        dispatchLaunch({ type: "generation_failed", requestId, message });
      }
    } finally {
      if (launchGenerationAbortRef.current === controller) launchGenerationAbortRef.current = null;
    }
  };

  const updateSkeletonCandidate = (candidateRef: string, nextValue: EditableVolumePackage) => {
    if (!skeletonState.candidate || skeletonReadOnly) return;
    dispatchSkeleton({
      type: "edit",
      candidate: {
        volumes: skeletonCandidates.map((candidate) => candidate.candidate_ref === candidateRef
          ? { ...candidate, ...nextValue }
          : candidate),
      },
    });
    setCandidateFieldErrors((current) => ({ ...current, [candidateRef]: {} }));
  };

  const removeSkeletonCandidate = (candidateRef: string) => {
    if (!skeletonState.candidate || skeletonReadOnly || skeletonBasis?.generation_input.mode === "replan") return;
    const currentIndex = skeletonCandidates.findIndex((candidate) => candidate.candidate_ref === candidateRef);
    const remaining = skeletonCandidates.filter((candidate) => candidate.candidate_ref !== candidateRef);
    const firstOrder = remaining.length > 0 ? Math.min(...remaining.map((candidate) => candidate.order_index)) : 1;
    const normalized = remaining.map((candidate, index) => ({ ...candidate, order_index: firstOrder + index }));
    dispatchSkeleton({ type: "edit", candidate: { volumes: normalized } });
    setSelectedCandidateRef(normalized[Math.min(currentIndex, normalized.length - 1)]?.candidate_ref ?? "");
    setCandidateFieldErrors((current) => {
      const next = { ...current };
      delete next[candidateRef];
      return next;
    });
    if (normalized.length === 0) setMobileDetailOpen(false);
  };

  const addSkeletonCandidate = () => {
    if (
      !skeletonState.candidate
      || skeletonReadOnly
      || skeletonCandidates.length >= 30
      || skeletonBasis?.generation_input.mode === "replan"
    ) return;
    let candidateRef = "";
    do {
      localCandidateCounterRef.current += 1;
      candidateRef = `volume_candidate_local_${localCandidateCounterRef.current}`;
    } while (skeletonCandidates.some((candidate) => candidate.candidate_ref === candidateRef));
    const orderIndex = skeletonCandidates.length > 0
      ? Math.max(...skeletonCandidates.map((candidate) => candidate.order_index)) + 1
      : skeletonBasis?.generation_input.mode === "append" ? volumes.length + 1 : 1;
    const candidate: VolumeSkeletonCandidateV1 = {
      candidate_ref: candidateRef,
      title: "",
      subtitle: "",
      order_index: orderIndex,
      summary: "",
      goal: "",
      theme: "",
      planning: {
        premise: "",
        major_conflict: "",
        key_turning_points: [],
        start_state: "",
        end_state: "",
        target_chapter_count: 1,
        target_word_count: 1,
      },
    };
    dispatchSkeleton({ type: "edit", candidate: { volumes: [...skeletonCandidates, candidate] } });
    setSelectedCandidateRef(candidateRef);
    setMobileDetailOpen(true);
  };

  const confirmSkeleton = async () => {
    if (
      !skeletonState.candidate
      || !skeletonState.basis
      || skeletonCandidates.length < 1
      || skeletonCandidates.length > 30
      || skeletonState.status === "stale"
      || skeletonState.status === "confirming"
      || skeletonConfirmationAbortRef.current
      || skeletonImpacts.some((impact) => impact.total - impact.chapter_records > 0)
    ) return;
    const basis = skeletonState.basis as VolumeSkeletonBasisV1;
    const targetRange = basis.generation_input.target_order_range;
    const formalTitles = new Set(orderedVolumes
      .filter((volume) => basis.generation_input.mode !== "replan"
        || !targetRange
        || volume.order_index < targetRange.start
        || volume.order_index > targetRange.end)
      .map((volume) => normalizeComparableText(volume.title)));
    const normalizedTitles = skeletonCandidates.map((candidate) => normalizeComparableText(candidate.title));
    const errorsByRef: Record<string, ApiFieldErrors> = {};
    for (const candidate of skeletonCandidates) {
      const normalizedTitle = normalizeComparableText(candidate.title);
      const errors = validatePackage(
        candidate,
        normalizedTitle.length > 0 && (
          normalizedTitles.filter((title) => title === normalizedTitle).length > 1
          || formalTitles.has(normalizedTitle)
        ),
        t,
      );
      if (Object.keys(errors).length > 0) errorsByRef[candidate.candidate_ref] = errors;
    }
    const orderedCandidates = [...skeletonCandidates].sort(
      (left, right) => left.order_index - right.order_index,
    );
    const firstOrder = orderedCandidates[0].order_index;
    const expectedFirstOrder = basis.generation_input.mode === "append"
      ? orderedVolumes.length + 1
      : basis.generation_input.mode === "create"
        ? 1
        : targetRange?.start ?? firstOrder;
    if (
      firstOrder !== expectedFirstOrder
      || orderedCandidates.some((candidate, index) => candidate.order_index !== firstOrder + index)
    ) {
      errorsByRef[orderedCandidates[0].candidate_ref] = {
        ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
        order_index: [aiT("validation.order")],
      };
    }
    if (basis.generation_input.mode === "replan") {
      const range = targetRange;
      if (
        !range
        || orderedCandidates.length !== range.end - range.start + 1
        || firstOrder !== range.start
        || orderedCandidates.at(-1)?.order_index !== range.end
      ) {
        errorsByRef[orderedCandidates[0].candidate_ref] = {
          ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
          order_index: [aiT("validation.replanRange")],
        };
      }
    }
    for (let index = 1; index < orderedCandidates.length; index += 1) {
      const previous = orderedCandidates[index - 1];
      const current = orderedCandidates[index];
      if (
        normalizeComparableText(previous.planning.end_state)
        !== normalizeComparableText(current.planning.start_state)
      ) {
        errorsByRef[current.candidate_ref] = {
          ...(errorsByRef[current.candidate_ref] ?? {}),
          start_state: [aiT("validation.internalBoundary", { order: current.order_index })],
        };
      }
    }
    if (basis.generation_input.mode === "append") {
      const previousPlanning = orderedVolumes.at(-1)?.planning;
      if (
        previousPlanning
        && normalizeComparableText(previousPlanning.end_state)
          !== normalizeComparableText(orderedCandidates[0].planning.start_state)
      ) {
        errorsByRef[orderedCandidates[0].candidate_ref] = {
          ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
          start_state: [aiT("validation.leftBoundary")],
        };
      }
    } else if (basis.generation_input.mode === "replan" && targetRange) {
      const previousPlanning = orderedVolumes.find(
        (volume) => volume.order_index === targetRange.start - 1,
      )?.planning;
      const nextPlanning = orderedVolumes.find(
        (volume) => volume.order_index === targetRange.end + 1,
      )?.planning;
      if (
        previousPlanning
        && normalizeComparableText(previousPlanning.end_state)
          !== normalizeComparableText(orderedCandidates[0].planning.start_state)
      ) {
        errorsByRef[orderedCandidates[0].candidate_ref] = {
          ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
          start_state: [aiT("validation.leftBoundary")],
        };
      }
      const lastCandidate = orderedCandidates.at(-1);
      if (
        lastCandidate
        && nextPlanning
        && normalizeComparableText(lastCandidate.planning.end_state)
          !== normalizeComparableText(nextPlanning.start_state)
      ) {
        errorsByRef[lastCandidate.candidate_ref] = {
          ...(errorsByRef[lastCandidate.candidate_ref] ?? {}),
          end_state: [aiT("validation.rightBoundary")],
        };
      }
    }
    if (skeletonCandidates.reduce((sum, candidate) => sum + candidate.planning.target_chapter_count, 0) !== basis.generation_input.total_chapter_budget) {
      errorsByRef[orderedCandidates[0].candidate_ref] = {
        ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
        target_chapter_count: [aiT("validation.chapterBudget", { total: basis.generation_input.total_chapter_budget })],
      };
    }
    if (skeletonCandidates.reduce((sum, candidate) => sum + candidate.planning.target_word_count, 0) !== basis.generation_input.total_word_budget) {
      errorsByRef[orderedCandidates[0].candidate_ref] = {
        ...(errorsByRef[orderedCandidates[0].candidate_ref] ?? {}),
        target_word_count: [aiT("validation.wordBudget", { total: basis.generation_input.total_word_budget })],
      };
    }
    const firstInvalid = skeletonCandidates.find((candidate) => errorsByRef[candidate.candidate_ref]);
    if (firstInvalid) {
      setCandidateFieldErrors(errorsByRef);
      setCandidateSearch("");
      setSelectedCandidateRef(firstInvalid.candidate_ref);
      setMobileDetailOpen(true);
      dispatchSkeleton({ type: "confirm_failed", message: aiT("errors.validation") });
      focusCandidateError("volume-skeleton-candidate-workspace", errorsByRef[firstInvalid.candidate_ref]);
      return;
    }

    const candidates = skeletonCandidates.map((candidate) => ({
      ...candidate,
      ...normalizePackage(candidate),
    }));
    const request: VolumeBulkPlanConfirmV1 = {
      candidates,
      basis,
      expected_versions: buildCandidateExpectedVersions(basis),
    };
    const fingerprint = JSON.stringify(request);
    if (skeletonConfirmCommandRef.current?.fingerprint !== fingerprint) {
      skeletonConfirmCommandRef.current = {
        fingerprint,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    const requestNovelId = novelId;
    const controller = new AbortController();
    skeletonConfirmationAbortRef.current = controller;
    dispatchSkeleton({ type: "confirm" });
    setCandidateFieldErrors({});
    try {
      const rawResponse = await apiPost<unknown>(
        `/api/volumes/novel/${novelId}/bulk-plan`,
        request,
        {
          headers: { "Idempotency-Key": skeletonConfirmCommandRef.current.key },
          signal: controller.signal,
        },
      );
      if (
        controller.signal.aborted
        || skeletonConfirmationAbortRef.current !== controller
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      const response = parseSkeletonConfirmation(rawResponse, candidates, requestNovelId);
      if (!response) throw new Error(aiT("errors.invalidConfirmation"));
      dispatchSkeleton({ type: "discard" });
      setSkeletonImpacts([]);
      setSkeletonConflictDetail(null);
      setSelectedCandidateRef("");
      setCandidateSearch("");
      setMobileDetailOpen(false);
      setCandidateFieldErrors({});
      skeletonConfirmCommandRef.current = null;
      skeletonPreviewVolumeSignatureRef.current = "";
      onSkeletonConfirmed?.(response);
    } catch (error) {
      if (
        controller.signal.aborted
        || skeletonConfirmationAbortRef.current !== controller
        || currentNovelIdRef.current !== requestNovelId
      ) return;
      if (error instanceof ApiRequestError && error.status === 422) {
        const normalized = normalizeSkeletonFieldErrors(error.fieldErrors, skeletonCandidates);
        setCandidateFieldErrors(normalized);
        const firstRef = skeletonCandidates.find((candidate) => normalized[candidate.candidate_ref])?.candidate_ref;
        if (firstRef) {
          setCandidateSearch("");
          setSelectedCandidateRef(firstRef);
          setMobileDetailOpen(true);
          focusCandidateError("volume-skeleton-candidate-workspace", normalized[firstRef]);
        } else {
          focusCandidateError("volume-skeleton-candidate-workspace", {});
        }
      }
      const stale = error instanceof ApiRequestError && [404, 409].includes(error.status);
      if (stale) {
        const replacementImpact = error instanceof ApiRequestError
          ? parseImpact(error.details.impact)
          : null;
        setSkeletonConflictDetail(error instanceof ApiRequestError
          ? parseConflictDetail(error.details)
          : null);
        setSkeletonImpacts((current) => replacementImpact
          && current.some((impact) => impact.volume_id === replacementImpact.volume_id)
          ? current.map((impact) => impact.volume_id === replacementImpact.volume_id
            ? replacementImpact
            : impact)
          : []);
      }
      let message = aiT("errors.confirm");
      if (stale) message = aiT("errors.conflict");
      else if (error instanceof ApiRequestError && error.status === 422) message = aiT("errors.validation");
      else if (error instanceof ApiRequestError && error.status === 503) message = aiT("errors.providerUnavailable");
      else if (error instanceof ApiRequestError && error.status === 504) message = aiT("errors.timeout");
      else if (error instanceof Error && error.message === aiT("errors.invalidConfirmation")) message = aiT("errors.invalidConfirmation");
      dispatchSkeleton({ type: "confirm_failed", message, stale });
    } finally {
      if (skeletonConfirmationAbortRef.current === controller) skeletonConfirmationAbortRef.current = null;
    }
  };

  const updateLaunchPackage = (nextValue: EditableVolumePackage) => {
    if (!launchState.candidate || launchReadOnly || launchRetryOnly) return;
    if (persistLaunch) launchConfirmCommandRef.current = null;
    dispatchLaunch({ type: "edit", candidate: { launch_package: nextValue } });
    setLaunchFieldErrors({});
  };

  const confirmLaunch = async () => {
    if (
      !launchState.candidate
      || !launchState.basis
      || !launchImpact
      || !selectedVolume
      || !launchDraftReady
      || launchState.status === "stale"
      || launchState.status === "confirming"
      || launchConfirmationAbortRef.current
      || launchImpact.downstream.total - launchImpact.downstream.chapter_records > 0
    ) return;
    const candidate = launchState.candidate.launch_package;
    const fieldErrors = validatePackage(candidate, false, t);
    const basis = launchState.basis as VolumeLaunchBasisV1;
    const submittedRequest = persistLaunch && launchConfirmCommandRef.current
      ? JSON.parse(launchConfirmCommandRef.current.fingerprint) as VolumeLaunchConfirmV1
      : null;
    const expectedChapterCount = basis.generation_input.target_chapter_count
      ?? selectedVolume.planning?.target_chapter_count;
    const expectedWordCount = basis.generation_input.target_word_count
      ?? selectedVolume.planning?.target_word_count;
    if (candidate.planning.target_chapter_count !== expectedChapterCount) {
      fieldErrors.target_chapter_count = [aiT("validation.launchChapterBudget", { total: expectedChapterCount ?? 0 })];
    }
    if (candidate.planning.target_word_count !== expectedWordCount) {
      fieldErrors.target_word_count = [aiT("validation.launchWordBudget", { total: expectedWordCount ?? 0 })];
    }
    if (
      previousVolume?.planning
      && normalizeComparableText(previousVolume.planning.end_state)
        !== normalizeComparableText(candidate.planning.start_state)
    ) {
      fieldErrors.start_state = [aiT("validation.launchPreviousBoundary")];
    }
    if (!submittedRequest && Object.keys(fieldErrors).length > 0) {
      setLaunchFieldErrors(fieldErrors);
      dispatchLaunch({ type: "confirm_failed", message: aiT("errors.validation") });
      focusCandidateError("volume-launch-candidate-workspace", fieldErrors);
      return;
    }
    const normalized = normalizePackage(candidate);
    const request: VolumeLaunchConfirmV1 = submittedRequest ?? {
      expected_version: basis.generation_input.volume_expected_version,
      ...normalized,
      basis,
    };
    const fingerprint = JSON.stringify(request);
    if (launchConfirmCommandRef.current?.fingerprint !== fingerprint) {
      launchConfirmCommandRef.current = {
        fingerprint,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    const requestNovelId = novelId;
    const requestVolumeId = selectedVolume.volume_id;
    const controller = new AbortController();
    launchConfirmationAbortRef.current = controller;
    dispatchLaunch({ type: "confirm" });
    setLaunchFieldErrors({});
    try {
      if (launchDraftKey) {
        await launchDraftWrites.current;
        await writeWritingDraft<LaunchDraft>(launchDraftKey, basis.generation_input.volume_expected_version, {
          candidate: launchState.candidate, basis, impact: launchImpact,
          command: launchConfirmCommandRef.current, stale: false,
        }).catch((error) => { setLaunchDraftError(launchDraftFailureMessage); throw error; });
      }
      const rawResponse = await apiPut<unknown>(
        `/api/volumes/${requestVolumeId}`,
        request,
        {
          headers: { "Idempotency-Key": launchConfirmCommandRef.current.key },
          signal: controller.signal,
        },
      );
      if (
        controller.signal.aborted
        || launchConfirmationAbortRef.current !== controller
        || currentNovelIdRef.current !== requestNovelId
        || currentVolumeIdRef.current !== requestVolumeId
      ) return;
      const response = parseLaunchConfirmation(
        rawResponse,
        requestNovelId,
        requestVolumeId,
        request,
      );
      if (!response) throw new Error(aiT("errors.invalidConfirmation"));
      if (launchDraftKey) {
        await launchDraftWrites.current;
        await writeWritingDraft(launchDraftKey, basis.generation_input.volume_expected_version, null);
      }
      dispatchLaunch({ type: "discard" });
      setLaunchImpact(null);
      setLaunchConflictDetail(null);
      setLaunchFieldErrors({});
      launchConfirmCommandRef.current = null;
      setLaunchDraftError("");
      onLaunchConfirmed?.(response);
    } catch (error) {
      if (
        controller.signal.aborted
        || launchConfirmationAbortRef.current !== controller
        || currentNovelIdRef.current !== requestNovelId
        || currentVolumeIdRef.current !== requestVolumeId
      ) return;
      if (error instanceof ApiRequestError && error.status === 422) {
        // 服务端已明确拒绝这次保存，修改后可以作为新请求再提交。
        if (persistLaunch) launchConfirmCommandRef.current = null;
        const normalizedErrors: ApiFieldErrors = {};
        for (const [path, messages] of Object.entries(error.fieldErrors)) {
          const field = path.split(".").at(-1) ?? path;
          normalizedErrors[field] = [...(normalizedErrors[field] ?? []), ...messages];
        }
        setLaunchFieldErrors(normalizedErrors);
        focusCandidateError("volume-launch-candidate-workspace", normalizedErrors);
      }
      const stale = error instanceof ApiRequestError && [404, 409].includes(error.status);
      if (stale) {
        const replacementImpact = error instanceof ApiRequestError
          ? parseImpact(error.details.impact)
          : null;
        setLaunchConflictDetail(error instanceof ApiRequestError
          ? parseConflictDetail(error.details)
          : null);
        setLaunchImpact((current) => replacementImpact?.volume_id === requestVolumeId && current
          ? {
              ...current,
              downstream: replacementImpact,
              has_blockers: replacementImpact.has_blockers,
            }
          : null);
      }
      let message = aiT("errors.confirm");
      if (stale) message = aiT("errors.conflict");
      else if (error instanceof ApiRequestError && error.status === 422) message = aiT("errors.validation");
      else if (error instanceof ApiRequestError && error.status === 503) message = aiT("errors.providerUnavailable");
      else if (error instanceof ApiRequestError && error.status === 504) message = aiT("errors.timeout");
      else if (error instanceof Error && error.message === aiT("errors.invalidConfirmation")) message = aiT("errors.invalidConfirmation");
      dispatchLaunch({ type: "confirm_failed", message, stale });
    } finally {
      if (launchConfirmationAbortRef.current === controller) launchConfirmationAbortRef.current = null;
    }
  };

  if (skeletonReviewing) {
    const hasBlockingImpact = skeletonImpacts.some((impact) => impact.total - impact.chapter_records > 0);
    return (
      <section
        id="volume-skeleton-candidate-workspace"
        className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden border-y border-border bg-surface"
        aria-labelledby="volume-skeleton-candidate-heading"
      >
        <header className="workspace-scrollbar max-h-[40vh] shrink-0 overflow-y-auto border-b border-border px-4 py-3 sm:px-6">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
              <h2 id="volume-skeleton-candidate-heading" tabIndex={-1} className="text-lg font-semibold text-foreground outline-none">{aiT("preview.skeletonTitle")}</h2>
              <p className="text-xs tabular-nums text-muted">{aiT("preview.skeletonCount", { count: skeletonCandidates.length })}</p>
            </div>
            <span className="self-start rounded-full bg-surface-secondary px-2.5 py-1 text-xs tabular-nums text-muted">
              {aiT(`status.${skeletonState.status}`)}
            </span>
          </div>
          {skeletonState.status === "stale" && (
            <div className="mt-4 border-y border-amber-400/60 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="alert">
              <p>{aiT("errors.conflict")}</p>
              {skeletonConflictDetail
                && skeletonConflictDetail.expectedVersion !== null
                && skeletonConflictDetail.actualVersion !== null && (
                <p className="mt-1">{aiT("errors.versionConflict", {
                  expected: skeletonConflictDetail.expectedVersion,
                  actual: skeletonConflictDetail.actualVersion,
                })}</p>
              )}
              {skeletonConflictDetail?.resourceType && skeletonConflictDetail.resourceId && (
                <p className="mt-1">{aiT("errors.resourceConflict", {
                  type: skeletonConflictDetail.resourceType,
                  id: skeletonConflictDetail.resourceId,
                })}</p>
              )}
            </div>
          )}
          {skeletonState.status !== "stale" && skeletonState.error && (
            <RelationEditorErrorSummary message={skeletonState.error} className="mt-4" />
          )}
          {skeletonImpacts.length > 0 && (
            <SkeletonImpactSummary impacts={skeletonImpacts} t={aiT} />
          )}
        </header>

        <div className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <label className="grid min-w-0 flex-1 gap-1.5 text-xs font-medium text-muted">
              <span>{aiT("preview.search")}</span>
              <input
                type="search"
                value={candidateSearch}
                onChange={(event) => setCandidateSearch(event.target.value)}
                placeholder={aiT("preview.searchPlaceholder")}
                className={INPUT_CLASS}
              />
            </label>
            <Button
              variant="outline"
              size="sm"
              onPress={addSkeletonCandidate}
              isDisabled={skeletonReadOnly || skeletonCandidates.length >= 30 || skeletonBasis?.generation_input.mode === "replan"}
            >
              {aiT("actions.addCandidate")}
            </Button>
          </div>
        </div>

        {selectedSkeletonCandidate ? (
          <div className="grid min-h-0 flex-1 overflow-hidden @min-[800px]/master:grid-cols-[minmax(240px,280px)_minmax(480px,1fr)]">
            <aside
              className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} workspace-scrollbar min-h-0 overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:border-b-0 @min-[800px]/master:border-r`}
              tabIndex={0}
              aria-label={aiT("preview.rosterLabel")}
            >
              <ol className="divide-y divide-border" role="listbox" aria-label={aiT("preview.rosterLabel")}>
                {visibleSkeletonCandidates.map((candidate, index) => (
                  <li key={candidate.candidate_ref} role="none">
                    <button
                      id={`volume-candidate-${candidate.candidate_ref}`}
                      type="button"
                      role="option"
                      aria-selected={selectedSkeletonCandidate.candidate_ref === candidate.candidate_ref}
                      tabIndex={selectedSkeletonCandidate.candidate_ref === candidate.candidate_ref ? 0 : -1}
                      onClick={() => {
                        setSelectedCandidateRef(candidate.candidate_ref);
                        setMobileDetailOpen(true);
                        requestAnimationFrame(() => {
                          const detail = document.getElementById(`volume-candidate-detail-${candidate.candidate_ref}`);
                          if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                            detail.focus();
                          }
                        });
                      }}
                      onKeyDown={(event) => {
                        if (event.altKey) return;
                        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                        event.preventDefault();
                        const next = visibleSkeletonCandidates[index + (event.key === "ArrowDown" ? 1 : -1)];
                        if (next) {
                          setSelectedCandidateRef(next.candidate_ref);
                          document.getElementById(`volume-candidate-${next.candidate_ref}`)?.focus();
                        }
                      }}
                      className={`w-full px-4 py-3 text-left transition-colors ${selectedSkeletonCandidate.candidate_ref === candidate.candidate_ref ? "bg-accent/10" : "hover:bg-surface-secondary/55"}`}
                    >
                      <span className="block truncate text-sm font-semibold text-foreground">{candidate.title || aiT("preview.untitled")}</span>
                      <span className="mt-1 block text-xs text-muted">{t("order", { order: candidate.order_index })} · {candidate.planning.target_chapter_count} / {candidate.planning.target_word_count}</span>
                      {candidateFieldErrors[candidate.candidate_ref] && Object.keys(candidateFieldErrors[candidate.candidate_ref]).length > 0 && (
                        <span className="mt-2 block text-xs font-medium text-red-600 dark:text-red-300">{aiT("preview.hasErrors")}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ol>
            </aside>
            <article
              id={`volume-candidate-detail-${selectedSkeletonCandidate.candidate_ref}`}
              className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30`}
              tabIndex={0}
              aria-label={`${aiT("preview.detailLabel")} · ${selectedSkeletonCandidate.title}`}
            >
              <div className="px-5 py-6 sm:px-7">
                <button
                  type="button"
                  className="mb-5 text-sm font-medium text-accent @min-[800px]/master:hidden"
                  onClick={() => {
                    const candidateRef = selectedSkeletonCandidate.candidate_ref;
                    setMobileDetailOpen(false);
                    requestAnimationFrame(() => document.getElementById(`volume-candidate-${candidateRef}`)?.focus());
                  }}
                >
                  ← {aiT("actions.backToRoster")}
                </button>
                <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h3 className="text-xl font-semibold text-foreground">{selectedSkeletonCandidate.title || aiT("preview.untitled")}</h3>
                    <p className="mt-1 text-xs text-muted">{t("order", { order: selectedSkeletonCandidate.order_index })}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="ghost" size="sm" className="text-danger" onPress={() => removeSkeletonCandidate(selectedSkeletonCandidate.candidate_ref)} isDisabled={skeletonReadOnly || skeletonBasis?.generation_input.mode === "replan"}>{aiT("actions.removeCandidate")}</Button>
                  </div>
                </div>
                {candidateFieldErrors[selectedSkeletonCandidate.candidate_ref] && Object.keys(candidateFieldErrors[selectedSkeletonCandidate.candidate_ref]).length > 0 && (
                  <RelationEditorErrorSummary message={aiT("errors.validation")} fieldErrors={candidateFieldErrors[selectedSkeletonCandidate.candidate_ref]} className="mt-6" />
                )}
                <div className="pt-7">
                  <VolumeFieldsForm
                    value={selectedSkeletonCandidate}
                    onChange={(nextValue) => updateSkeletonCandidate(selectedSkeletonCandidate.candidate_ref, nextValue)}
                    disabled={skeletonReadOnly}
                    fieldErrors={candidateFieldErrors[selectedSkeletonCandidate.candidate_ref] ?? {}}
                    errorIdPrefix={`volume-skeleton-${selectedSkeletonCandidate.candidate_ref}`}
                  />
                </div>
              </div>
            </article>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 place-items-center px-5 py-12 text-center">
            <div>
              <p className="text-sm font-medium text-foreground">{normalizedCandidateSearch ? aiT("preview.filteredEmptyTitle") : aiT("preview.emptyTitle")}</p>
              {!normalizedCandidateSearch && skeletonBasis?.generation_input.mode !== "replan" && (
                <Button className="mt-4" variant="outline" size="sm" onPress={addSkeletonCandidate} isDisabled={skeletonReadOnly}>{aiT("actions.addCandidate")}</Button>
              )}
            </div>
          </div>
        )}

        <footer className="shrink-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
            <Button variant="ghost" size="sm" onPress={discardSkeleton} isDisabled={skeletonState.status === "confirming"}>{aiT("actions.discard")}</Button>
            <Button variant="primary" size="sm" onPress={() => void confirmSkeleton()} isDisabled={skeletonReadOnly || skeletonCandidates.length === 0 || hasBlockingImpact}>
              {skeletonState.status === "confirming" ? aiT("actions.confirming") : aiT("actions.confirmSkeleton")}
            </Button>
          </div>
        </footer>
      </section>
    );
  }

  if (launchReviewing && launchState.candidate) {
    const launchPackage = launchState.candidate.launch_package;
    return (
      <section
        id="volume-launch-candidate-workspace"
        className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden border-y border-border bg-surface"
        aria-labelledby="volume-launch-candidate-heading"
      >
        <header className="workspace-scrollbar max-h-[40vh] shrink-0 overflow-y-auto border-b border-border px-4 py-3 sm:px-6">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <div className="min-w-0">
              <h2 id="volume-launch-candidate-heading" tabIndex={-1} className="text-lg font-semibold text-foreground outline-none">{aiT("preview.launchTitle", { name: selectedVolume?.title ?? "" })}</h2>
            </div>
            <span className="self-start rounded-full bg-surface-secondary px-2.5 py-1 text-xs tabular-nums text-muted">{aiT(`status.${launchState.status}`)}</span>
          </div>
          {launchState.status === "stale" && (
            <div className="mt-4 border-y border-amber-400/60 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="alert">
              <p>{aiT("errors.conflict")}</p>
              {launchConflictDetail
                && launchConflictDetail.expectedVersion !== null
                && launchConflictDetail.actualVersion !== null && (
                <p className="mt-1">{aiT("errors.versionConflict", {
                  expected: launchConflictDetail.expectedVersion,
                  actual: launchConflictDetail.actualVersion,
                })}</p>
              )}
              {launchConflictDetail?.resourceType && launchConflictDetail.resourceId && (
                <p className="mt-1">{aiT("errors.resourceConflict", {
                  type: launchConflictDetail.resourceType,
                  id: launchConflictDetail.resourceId,
                })}</p>
              )}
            </div>
          )}
          {launchState.status !== "stale" && launchState.error && (
            <RelationEditorErrorSummary message={launchState.error} className="mt-4" />
          )}
          {launchRetryOnly && launchState.status !== "confirming" && (
            <p role="status" className="mt-4 border-y border-amber-500/50 py-3 text-sm">{aiT("errors.retryConfirmation")}</p>
          )}
          {launchDraftError && <RelationEditorErrorSummary message={launchDraftError} className="mt-4" />}
          {displayedLaunchImpact ? (
            <LaunchImpactSummary impact={displayedLaunchImpact} t={aiT} />
          ) : (
            <p className="mt-4 border-y border-amber-400/60 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
              {aiT("impact.unavailable")}
            </p>
          )}
        </header>
        <article className="workspace-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={aiT("preview.launchEditorLabel")}>
          <div className="px-5 py-6 sm:px-7">
            {Object.keys(launchFieldErrors).length > 0 && (
              <RelationEditorErrorSummary message={aiT("errors.validation")} fieldErrors={launchFieldErrors} className="mb-6" />
            )}
            <VolumeFieldsForm value={launchPackage} onChange={updateLaunchPackage} disabled={launchReadOnly || launchRetryOnly} fieldErrors={launchFieldErrors} errorIdPrefix="volume-launch" />
          </div>
        </article>
        <footer className="shrink-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:px-6">
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
            <Button variant="ghost" size="sm" onPress={discardLaunch} isDisabled={launchState.status === "confirming" || launchRetryOnly}>{aiT("actions.discard")}</Button>
            <Button variant="primary" size="sm" onPress={() => void confirmLaunch()} isDisabled={launchReadOnly || !launchImpact || launchImpact.downstream.total - launchImpact.downstream.chapter_records > 0}>
              {launchState.status === "confirming" ? aiT("actions.confirming") : aiT("actions.confirmLaunch")}
            </Button>
          </div>
        </footer>
      </section>
    );
  }

  return (
    <div className="contents">
      <section className="workspace-toolbar ml-auto flex flex-wrap items-end gap-2" aria-label={aiT("toolbar.title")}>
          {task !== "launch" && (skeletonState.status === "generating" ? (
            <Button id="volume-ai-skeleton-cancel" variant="outline" size="sm" onPress={discardSkeleton}>{aiT("actions.cancelSkeleton")}</Button>
          ) : (
            <Button id="volume-ai-skeleton-trigger" ref={skeletonTriggerRef} variant="outline" size="sm" onPress={openSkeletonDialog} isDisabled={disabled || busy}>{aiT("actions.openSkeleton")}</Button>
          ))}
          {task !== "skeleton" && (launchState.status === "generating" ? (
            <Button id="volume-ai-launch-cancel" variant="outline" size="sm" onPress={discardLaunch}>{aiT("actions.cancelLaunch")}</Button>
          ) : (
            <Button id="volume-ai-launch-trigger" ref={launchTriggerRef} variant="outline" size="sm" onPress={openLaunchDialog} isDisabled={disabled || busy || !selectedVolume || !launchDraftReady}>{aiT("actions.openLaunch")}</Button>
          ))}
      </section>
      {launchDraftError && <RelationEditorErrorSummary message={launchDraftError} />}
      {skeletonState.status === "error" && !skeletonState.candidate && skeletonState.error && (
        <div className="w-full border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{skeletonState.error}</div>
      )}
      {launchState.status === "error" && !launchState.candidate && launchState.error && (
        <div className="w-full border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">{launchState.error}</div>
      )}

      {(skeletonState.status === "generating" || skeletonState.status === "error") && <TaskFlowProgress flow={skeletonFlow} running={skeletonState.status === "generating"} failed={skeletonState.status === "error" && skeletonState.candidate === null} onRepair={skeletonFlow.canRepair ? () => void generateSkeleton("repair") : undefined} onRetry={() => void generateSkeleton(true)} onContinue={(additionalRounds) => void generateSkeleton({ continuation: true, additionalRounds })} onDiscard={discardSkeleton} label={aiT("progress.skeleton")} />}
      {(launchState.status === "generating" || launchState.status === "error") && <TaskFlowProgress flow={launchFlow} running={launchState.status === "generating"} failed={launchState.status === "error" && launchState.candidate === null} onRepair={launchFlow.canRepair ? () => void generateLaunch("repair") : undefined} onRetry={() => void generateLaunch(true)} onContinue={(additionalRounds) => void generateLaunch({ continuation: true, additionalRounds })} onDiscard={discardLaunch} label={aiT("progress.launch")} />}
      {skeletonDialogOpen && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && closeSkeletonDialog()} variant="blur" isDismissable>
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-4xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">{aiT("skeletonDialog.title")}</Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7" onChangeCapture={(event) => {
                const field = (event.target as HTMLInputElement).name;
                if (field === "total_chapter_budget" || field === "total_word_budget") editedSkeletonBudgets.current.add(`${skeletonBudgetKey}:${field}`);
              }}>{novelVersionError && <p role="alert" className="mb-4 text-sm text-danger">{novelVersionError}</p>}<TaskFlowForm flow={skeletonFlow} fieldChoices={{ mode: ["create", "append", "replan"].map((value) => ({ value, label: aiT(`mode.${value}`) })) }} fieldLabels={{ total_chapter_budget: aiT("fields.totalChapterBudget"), total_word_budget: aiT("fields.totalWordBudget"), "target_order_range.start": aiT("fields.rangeStart"), "target_order_range.end": aiT("fields.rangeEnd") }} /></Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeSkeletonDialog}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void generateSkeleton()} isDisabled={disabled || skeletonFlow.loading || !skeletonFlow.definition || novelVersion === null || novelVersionLoading}>{aiT("actions.generateSkeleton")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}

      {launchDialogOpen && selectedVolume && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && closeLaunchDialog()} variant="blur" isDismissable>
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">{aiT("launchDialog.title", { name: selectedVolume.title })}</Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7"><TaskFlowForm flow={launchFlow} /></Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeLaunchDialog}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void generateLaunch()} isDisabled={disabled || launchFlow.loading || !launchFlow.definition}>{aiT("actions.generateLaunch")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}
    </div>
  );
}


function SkeletonImpactSummary({ impacts, t }: { impacts: VolumeDeleteImpactV2[]; t: ReturnType<typeof useTranslations> }) {
  const total = impacts.reduce((sum, impact) => sum + impact.total, 0);
  const chapterRecords = impacts.reduce((sum, impact) => sum + impact.chapter_records, 0);
  const blocked = impacts.some((impact) => impact.total - impact.chapter_records > 0);
  return (
    <section className={`mt-2 text-sm ${blocked ? "text-danger" : "text-muted"}`} aria-label={t("impact.title")}>
      <details>
        <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium">{t("impact.title")}</span>
          <span>{t("impact.summary", { count: impacts.length, total })}</span>
        </summary>
        <ul className="workspace-scrollbar max-h-32 space-y-1 overflow-y-auto py-2 font-mono text-xs">
          {impacts.map((impact) => <li key={impact.volume_id}>{impact.volume_id} · {t("impact.item", { total: impact.total, blocked: impact.total - impact.chapter_records > 0 ? t("impact.blocked") : t("impact.clear") })}</li>)}
        </ul>
      </details>
      {chapterRecords > 0 && <p>{t("impact.chapterRecordsPreserved", { count: chapterRecords })}</p>}
      {blocked && <p className="font-medium" role="alert">{t("impact.blockedDescription")}</p>}
    </section>
  );
}

function LaunchImpactSummary({ impact, t }: { impact: VolumeLaunchImpactV1; t: ReturnType<typeof useTranslations> }) {
  const blocked = impact.downstream.total - impact.downstream.chapter_records > 0;
  if (!blocked && !impact.next_start_state_conflict && impact.downstream.total === 0) return null;
  return (
    <section className={`mt-2 text-sm ${blocked ? "text-danger" : impact.next_start_state_conflict ? "text-amber-800 dark:text-amber-200" : "text-muted"}`} aria-label={t("impact.title")}>
      <details>
        <summary className="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium">{t("impact.title")}</span>
          <span>{t("impact.launchDownstream", { total: impact.downstream.total })}</span>
        </summary>
        <p className="pb-2 leading-6">{t("impact.launchBoundary", { previous: impact.previous_volume_id ?? t("impact.noneValue"), next: impact.next_volume_id ?? t("impact.noneValue") })}</p>
      </details>
      {impact.downstream.chapter_records > 0 && <p>{t("impact.chapterRecordsPreserved", { count: impact.downstream.chapter_records })}</p>}
      {impact.next_start_state_conflict && <p className="font-medium" role="alert">{t("impact.nextConflict")}</p>}
      {blocked && <p className="font-medium" role="alert">{t("impact.blockedDescription")}</p>}
    </section>
  );
}
