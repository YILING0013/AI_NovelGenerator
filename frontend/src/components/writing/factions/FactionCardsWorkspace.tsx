"use client";
import { useFactionBatchCreation } from "../characters/useCharacterBatchCreation";
import { useResourceRefresh } from "@/hooks/useResourceRefresh";
import { useAssistantResource, useAssistantFocus } from "@/components/writing/assistant/AssistantContext";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";


import { TaskFlowDialog,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";

import {
ConfirmActionModal,
focusRelationEditorError,
RelationEditorErrorSummary,
RelationFieldShell,
RelationIntensityField,
} from "@/components/shared/RelationEditorPrimitives";
import TagInput from "@/components/shared/TagInput";
import TagList from "@/components/shared/TagList";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import {
buildCandidateExpectedVersions,
createLocalCandidateState,
hasCandidateFlow,
isCandidateBasisStale,
localCandidateReducer,
type CandidateBasisV1,
type CandidateGenerationEnvelopeV1,
type CandidateStateName,
} from "@/lib/aiCandidate";
import { apiDelete,apiGet,apiPost,apiPut,ApiRequestError,type ApiFieldErrors } from "@/lib/api";
import type {
CoreFaction,
CoreFactionRelationCandidateV2,
CoreFactionRelationEndpointV2,
CoreFactionsAIConfirmationRequestV2,
CoreFactionsCandidateEnvelopeV2,
CoreFactionsGenerationInputV2,
CoreFactionsResultV2,
FactionCreateRequestV1,
FactionRelation,
FactionRelationCreateRequestV1,
FactionRelationsAIConfirmationRequestV1,
FactionRelationsCandidateEnvelopeV1,
FactionRelationsGenerationInputV1,
FactionRelationsResultV1,
FactionRelationType,
FactionRelationUpdateRequestV1,
FactionUpdateRequestV1,
NovelDetail
} from "@/types/novel";
import type { VolumeReadV2 } from "@/types/volume";
import { Button,Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useContext,useEffect,useId,useMemo,useReducer,useRef,useState,type ReactNode } from "react";
import {
FactionRelationGenerationPreview,
} from "./FactionRelationGenerationWorkspace";

interface FactionCardsWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: FactionWorkspaceView;
  requestedVolumeId?: string | null;
  onViewChange?: (view: FactionWorkspaceView) => void;
  onVolumeIdChange?: (volumeId: string | null, replace?: boolean) => void;
  onFormalFactsChanged?: () => void;
}

export type FactionWorkspaceView = "profiles" | "relations" | "trash";
type FactionLevelFilter = "all" | "core" | "volume" | "local";
type FactionSection = "identity" | "strategy" | "structure" | "story";
type EditorState = { mode: "create" | "edit"; draft: CoreFaction; section?: FactionSection } | null;
const FACTION_SECTION_FIELDS = {
  identity: ["name", "alias", "faction_type", "influence_scope", "is_public", "parent_faction_id", "active_status"],
  strategy: ["positioning", "public_stance", "core_goal", "hidden_goal"],
  structure: ["organization_style", "resources_and_advantages", "core_values"],
  story: ["conflict_with_mainline", "expandability", "tags"],
} as const;
interface FactionInlineEditingProps {
  editor: EditorState;
  editorError: string;
  editorFieldErrors: ApiFieldErrors;
  saving: boolean;
  onEditorChange: (draft: CoreFaction) => void;
  onEditorCancel: () => void;
  onEditorSave: () => void;
}

type DeleteIntent = { mode: "soft" | "hard"; faction: CoreFaction } | null;
type RelationEditorState = {
  mode: "create" | "edit";
  draft: FactionRelationCreateRequestV1;
  source?: FactionRelation;
} | null;
type RelationDeleteIntent = { mode: "soft" | "hard"; relation: FactionRelation } | null;

const RELATION_TYPES: FactionRelationType[] = [
  "hostile",
  "allied",
  "cold_war",
  "dependent",
  "subordinate",
  "trade_partner",
  "secret_cooperation",
  "historical_enemy",
];

const SYMMETRIC_FACTION_RELATION_TYPES = new Set<FactionRelationType>([
  "hostile",
  "allied",
  "cold_war",
  "trade_partner",
  "secret_cooperation",
  "historical_enemy",
]);

interface StableRequestCommand {
  signature: string;
  key: string;
}

/**
 * 为同一载荷复用幂等键，并在载荷变化后生成新键。
 *
 * Args:
 *   commandRef: 当前逻辑命令保存的载荷签名与幂等键。
 *   payload: 将提交给后端的严格 JSON 请求体。
 *
 * Returns:
 *   可直接写入 Idempotency-Key 的稳定命令键。
 */
function getStableRequestKey(
  commandRef: { current: StableRequestCommand | null },
  payload: unknown,
): string {
  const signature = JSON.stringify(payload);
  if (commandRef.current?.signature !== signature) {
    commandRef.current = {
      signature,
      key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
    };
  }
  return commandRef.current.key;
}

/** 判断阵营关系类型是否为无方向的对称关系。 */
export function isSymmetricFactionRelation(type: FactionRelationType): boolean {
  return SYMMETRIC_FACTION_RELATION_TYPES.has(type);
}

const FACTION_WORKSPACE_TAB_PREFIX = "faction-workspace";
const CORE_FACTIONS_ENVELOPE = {
  workflow: "create_factions_by_ai",
  step: "create_core_factions",
  schemaId: "faction.core_generation.result",
  schemaVersion: 2,
} as const;
const FACTION_RELATIONS_ENVELOPE = {
  workflow: "create_faction_relations_by_ai",
  step: "create_faction_relations",
  schemaId: "faction.relation_generation.result",
  schemaVersion: 1,
} as const;

const CORE_FACTION_WARNING_COUNT = 6;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCandidateBasis(value: unknown, novelId: string): value is CandidateBasisV1 {
  if (!hasCandidateFlow(value) || value.novel_id !== novelId || !Array.isArray(value.source_refs)) return false;
  return (
    typeof value.workflow === "string" &&
    typeof value.step === "string" &&
    typeof value.schema_id === "string" &&
    Number.isInteger(value.schema_version) &&
    typeof value.input_fingerprint === "string" &&
    value.source_refs.every((source) =>
      isRecord(source) &&
      typeof source.resource_type === "string" &&
      typeof source.id === "string" &&
      Number.isInteger(source.version) &&
      Number(source.version) >= 1,
    )
  );
}

function isCoreFactionEndpoint(value: unknown): value is CoreFactionRelationEndpointV2 {
  return isRecord(value) && (
    (value.kind === "candidate" && typeof value.faction_ref === "string") ||
    (value.kind === "existing" && typeof value.faction_id === "string")
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function hasValidRelationFields(value: Record<string, unknown>, activeMustBeTrue: boolean): boolean {
  return (
    typeof value.relation_ref === "string" &&
    RELATION_TYPES.includes(value.relation_type as FactionRelationType) &&
    typeof value.current_state === "string" &&
    typeof value.core_conflict === "string" &&
    typeof value.hidden_tension === "string" &&
    typeof value.possible_change === "string" &&
    Number.isInteger(value.intensity) &&
    Number(value.intensity) >= 1 &&
    Number(value.intensity) <= 5 &&
    (activeMustBeTrue ? value.is_active === true : typeof value.is_active === "boolean")
  );
}

function isCoreFactionsCandidate(value: unknown): value is CoreFactionsResultV2 {
  if (!isRecord(value) || !Array.isArray(value.core_factions) || !Array.isArray(value.faction_relations)) return false;
  return value.core_factions.length > 0 && value.core_factions.every((faction) =>
    isRecord(faction) &&
    typeof faction.faction_ref === "string" &&
    typeof faction.name === "string" &&
    typeof faction.faction_type === "string" &&
    typeof faction.positioning === "string" &&
    typeof faction.public_stance === "string" &&
    typeof faction.core_goal === "string" &&
    typeof faction.hidden_goal === "string" &&
    isStringArray(faction.resources_and_advantages) &&
    typeof faction.organization_style === "string" &&
    isStringArray(faction.core_values) &&
    typeof faction.conflict_with_mainline === "string" &&
    typeof faction.is_public === "boolean" &&
    typeof faction.influence_scope === "string" &&
    typeof faction.expandability === "string" &&
    isStringArray(faction.tags),
  ) && value.faction_relations.every((relation) =>
    isRecord(relation) &&
    hasValidRelationFields(relation, false) &&
    isCoreFactionEndpoint(relation.source) &&
    isCoreFactionEndpoint(relation.target),
  );
}

function isFactionRelationsCandidate(value: unknown): value is FactionRelationsResultV1 {
  return isRecord(value) && Array.isArray(value.relations) && value.relations.length > 0 && value.relations.every((relation) =>
    isRecord(relation) &&
    hasValidRelationFields(relation, true) &&
    typeof relation.source_faction_id === "string" &&
    typeof relation.target_faction_id === "string",
  );
}

function parseCandidateEnvelope<TCandidate>(
  value: unknown,
  novelId: string,
  contract: typeof CORE_FACTIONS_ENVELOPE | typeof FACTION_RELATIONS_ENVELOPE,
  candidateGuard: (candidate: unknown) => candidate is TCandidate,
): CandidateGenerationEnvelopeV1<TCandidate> | null {
  if (!isRecord(value) || !candidateGuard(value.candidate) || !isCandidateBasis(value.basis, novelId)) return null;
  if (
    value.workflow !== contract.workflow ||
    value.step !== contract.step ||
    value.schema_id !== contract.schemaId ||
    value.schema_version !== contract.schemaVersion ||
    value.basis.workflow !== contract.workflow ||
    value.basis.step !== contract.step ||
    value.basis.schema_id !== contract.schemaId ||
    value.basis.schema_version !== contract.schemaVersion
  ) return null;
  return value as unknown as CandidateGenerationEnvelopeV1<TCandidate>;
}

/** 解析并严格校验核心势力普通响应或 SSE done.result 信封。 */
export function parseCoreFactionsEnvelope(value: unknown, novelId: string): CoreFactionsCandidateEnvelopeV2 | null {
  return parseCandidateEnvelope(value, novelId, CORE_FACTIONS_ENVELOPE, isCoreFactionsCandidate);
}

/** 解析并严格校验增量阵营关系普通响应或 SSE done.result 信封。 */
export function parseFactionRelationsEnvelope(value: unknown, novelId: string): FactionRelationsCandidateEnvelopeV1 | null {
  return parseCandidateEnvelope(value, novelId, FACTION_RELATIONS_ENVELOPE, isFactionRelationsCandidate);
}

/**
 * 生成可编辑的核心阵营草稿。
 *
 * Args:
 *   source: 可选的已有阵营数据。
 *   index: 草稿排序位置。
 *
 * Returns:
 *   字段齐全的核心阵营草稿。
 */
function createFactionDraft(source: Partial<CoreFaction> = {}, index = 0): CoreFaction {
  return {
    novel_id: source.novel_id ?? "",
    faction_id: source.faction_id ?? "",
    is_deleted: source.is_deleted ?? false,
    deleted_at: source.deleted_at ?? null,
    deletion_sources: source.deletion_sources ?? [],
    created_at: source.created_at ?? "",
    updated_at: source.updated_at ?? "",
    name: source.name ?? "",
    alias: source.alias ?? [],
    faction_type: source.faction_type ?? "",
    level_type: source.level_type ?? "core",
    parent_faction_id: source.parent_faction_id ?? null,
    volume_id: source.volume_id ?? null,
    positioning: source.positioning ?? "",
    public_stance: source.public_stance ?? "",
    core_goal: source.core_goal ?? "",
    hidden_goal: source.hidden_goal ?? "",
    resources_and_advantages: source.resources_and_advantages ?? [],
    organization_style: source.organization_style ?? "",
    core_values: source.core_values ?? [],
    conflict_with_mainline: source.conflict_with_mainline ?? "",
    is_public: source.is_public ?? true,
    influence_scope: source.influence_scope ?? "",
    active_status: source.active_status ?? "active",
    expandability: source.expandability ?? "",
    tags: source.tags ?? [],
    sort_order: source.sort_order ?? (index + 1) * 10,
    // 新建与 AI 预览草稿从版本 1 起步；正式数据沿用接口返回的当前版本。
    version: source.version ?? 1,
  };
}

/**
 * 提取阵营写入 API 支持的字段。
 *
 * Args:
 *   draft: 前端编辑中的阵营草稿。
 *
 * Returns:
 *   可提交给创建或更新接口的阵营字段。
 */
function buildFactionEditableRequest(
  draft: CoreFaction,
): Omit<FactionCreateRequestV1, "level_type" | "parent_faction_id" | "volume_id"> {
  return {
    name: draft.name.trim(),
    alias: draft.alias ?? [],
    faction_type: draft.faction_type.trim(),
    positioning: draft.positioning.trim(),
    public_stance: draft.public_stance.trim(),
    core_goal: draft.core_goal.trim(),
    hidden_goal: draft.hidden_goal?.trim() ?? "",
    resources_and_advantages: draft.resources_and_advantages ?? [],
    organization_style: draft.organization_style.trim(),
    core_values: draft.core_values ?? [],
    conflict_with_mainline: draft.conflict_with_mainline.trim(),
    is_public: draft.is_public,
    influence_scope: draft.influence_scope.trim(),
    expandability: draft.expandability.trim(),
    tags: draft.tags ?? [],
    sort_order: draft.sort_order ?? 0,
  };
}

function buildFactionCreateRequest(draft: CoreFaction): FactionCreateRequestV1 {
  return {
    level_type: (draft.level_type ?? "core") as "core" | "volume" | "local",
    parent_faction_id: draft.parent_faction_id ?? null,
    volume_id: draft.volume_id ?? null,
    ...buildFactionEditableRequest(draft),
  };
}

/**
 * 构造势力档案更新请求，并携带当前实体版本用于 CAS 校验。
 *
 * Args:
 *   draft: 包含服务端当前版本的势力编辑草稿。
 *
 * Returns:
 *   仅包含可编辑字段及 expected_version 的更新请求体。
 */
export function buildFactionUpdateRequest(
  draft: CoreFaction,
): FactionUpdateRequestV1 {
  return {
    ...buildFactionEditableRequest(draft),
    parent_faction_id: draft.parent_faction_id ?? null,
    expected_version: draft.version,
    active_status: (draft.active_status ?? "active") as "active" | "inactive",
  };
}

/**
 * 只更新当前资料节，沿用开始编辑时的版本。
 * Args:
 *   draft: 已固定版本的势力草稿。
 *   section: 正在编辑的资料节。
 * Returns:
 *   当前节字段与乐观锁版本，不带其他节的旧内容。
 */
export function buildFactionSectionRequest(draft: CoreFaction, section: FactionSection): Partial<FactionUpdateRequestV1> & { expected_version: number } {
  const editable = buildFactionUpdateRequest(draft);
  return {
    ...Object.fromEntries(FACTION_SECTION_FIELDS[section].map((field) => [field, editable[field]])),
    expected_version: draft.version,
  };
}

/** 在原位表单中聚焦首错字段；无字段错误时聚焦当前节的错误摘要。 */
function focusFactionInlineError(id: string, errors: ApiFieldErrors): void {
  requestAnimationFrame(() => {
    const form = document.getElementById(id);
    const field = Object.keys(errors)[0]?.split(".").at(-1);
    const target = (field ? form?.querySelector<HTMLElement>(`[name="${CSS.escape(field)}"]`) : null)
      ?? form?.querySelector<HTMLElement>("[data-editor-error-summary]");
    target?.focus({ preventScroll: true });
    target?.scrollIntoView?.({ block: "nearest" });
  });
}

/**
 * 构造势力恢复接口使用的乐观锁请求体。
 *
 * Args:
 *   faction: 待恢复的正式势力实体。
 *
 * Returns:
 *   仅包含当前 expected_version 的请求体。
 */
export function buildFactionVersionRequest(
  faction: Pick<CoreFaction, "version">,
): { expected_version: number } {
  return { expected_version: faction.version };
}

/**
 * 为势力软删除或硬删除接口附加当前实体版本查询参数。
 *
 * Args:
 *   path: 不含查询参数的删除接口路径。
 *   faction: 待删除的正式势力实体。
 *
 * Returns:
 *   带 expected_version 查询参数的删除接口路径。
 */
export function buildFactionVersionedDeletePath(
  path: string,
  faction: Pick<CoreFaction, "version">,
): string {
  const query = new URLSearchParams({ expected_version: String(faction.version) });
  return `${path}?${query.toString()}`;
}

/**
 * 读取已有核心阵营可用于选择器展示的名称。
 *
 * Args:
 *   faction: 已保存的核心阵营数据。
 *
 * Returns:
 *   去除首尾空白后的阵营名称。
 */
function getFactionName(faction: CoreFaction): string {
  return faction.name.trim();
}

function endpointIdentity(endpoint: CoreFactionRelationEndpointV2): string {
  return endpoint.kind === "candidate"
    ? `candidate:${endpoint.faction_ref}`
    : `existing:${endpoint.faction_id}`;
}

/** 返回所选核心关系中引用了未选择新势力的关系 ref。 */
export function findRelationsWithUnselectedFaction(
  candidate: CoreFactionsResultV2,
  selectedFactionRefs: readonly string[],
  selectedRelationRefs: readonly string[],
): string[] {
  const selectedFactions = new Set(selectedFactionRefs);
  const selectedRelations = new Set(selectedRelationRefs);
  return candidate.faction_relations
    .filter((relation) => selectedRelations.has(relation.relation_ref))
    .filter((relation) => [relation.source, relation.target].some(
      (endpoint) => endpoint.kind === "candidate" && !selectedFactions.has(endpoint.faction_ref),
    ))
    .map((relation) => relation.relation_ref);
}

/**
 * Resolve the stable frontend identity for a saved core faction.
 *
 * Args:
 *   faction: A faction returned by the API or held in local state.
 *
 * Returns:
 *   The business id when available, then Mongo id, then the faction name.
 */
function getFactionRenderKey(faction: CoreFaction): string {
  return faction.faction_id;
}

/**
 * 功能：按势力层级与搜索关键词筛选正式势力档案。
 *
 * Args:
 *   factions: 当前小说下已加载的正式势力。
 *   search: 用户输入的名称或档案关键词。
 *   levelFilter: 全部或指定势力层级。
 *
 * Returns:
 *   同时满足层级和关键词条件的势力列表，原始数组保持不变。
 */
export function filterFactionProfiles(
  factions: CoreFaction[],
  search: string,
  levelFilter: FactionLevelFilter,
): CoreFaction[] {
  const query = search.trim().toLocaleLowerCase();

  return factions.filter((faction) => {
    const level = faction.level_type || "core";
    if (levelFilter !== "all" && level !== levelFilter) {
      return false;
    }
    if (!query) {
      return true;
    }

    // 搜索覆盖名册识别信息和主要叙述字段，便于从较长的势力档案中快速定位。
    const searchableValues = [
      faction.name,
      faction.faction_type,
      faction.positioning,
      faction.public_stance,
      faction.core_goal,
      faction.hidden_goal,
      faction.organization_style,
      faction.conflict_with_mainline,
      faction.influence_scope,
      ...(faction.alias ?? []),
      ...(faction.tags ?? []),
      ...(faction.resources_and_advantages ?? []),
      ...(faction.core_values ?? []),
    ];
    return searchableValues.some((value) => value?.toLocaleLowerCase().includes(query));
  });
}

/**
 * 功能：筛出可作为新阵营关系端点的全部活动正式势力。
 *
 * Args:
 *   factions: 当前小说已加载的正式势力。
 *
 * Returns:
 *   保留原排序的活动、未删除全书核心势力。
 */
export function getAvailableRelationFactions(
  factions: CoreFaction[],
): Array<CoreFaction & { faction_id: string }> {
  return factions.filter(
    (faction): faction is CoreFaction & { faction_id: string } =>
      typeof faction.faction_id === "string" &&
      faction.faction_id.length > 0 &&
      faction.is_deleted !== true &&
      (faction.level_type || "core") === "core" &&
      (faction.active_status ?? "active") === "active",
  );
}

/**
 * Resolve the stable frontend identity for a saved faction relation.
 *
 * Args:
 *   relation: A relation returned by the API or held in local state.
 *
 * Returns:
 *   The business id when available, then Mongo id, then a relation endpoint signature.
 */
function getRelationRenderKey(relation: FactionRelation): string {
  return relation.relation_id;
}

/**
 * Merge incoming API rows into current state without duplicating React keys.
 *
 * Args:
 *   current: Rows already rendered in the workspace.
 *   incoming: Fresh rows returned by save or reload APIs.
 *   getKey: Stable identity resolver for each row.
 *
 * Returns:
 *   A list where later rows replace earlier rows with the same key.
 */
function mergeUniqueByKey<T>(current: T[], incoming: T[], getKey: (item: T) => string): T[] {
  const rowsByKey = new Map<string, T>();

  // 保存响应和刷新请求可能交错返回，统一按业务 ID 覆盖旧行，避免同一条记录被追加两次。
  for (const item of [...current, ...incoming]) {
    rowsByKey.set(getKey(item), item);
  }

  return Array.from(rowsByKey.values());
}

/**
 * 渲染已保存小说的势力卡工作台，并承接核心阵营生成、编辑与垃圾桶操作。
 *
 * Args:
 *   mode: 写作页当前模式，只有 edit 模式允许读取和写入已保存小说。
 *   novelId: 已保存小说的 ObjectId 字符串。
 *   initialView: URL 深链接指定的资料、关系或回收站视图。
 *   onViewChange: 用户切换子视图时同步 Writing 查询参数。
 *   onFormalFactsChanged: 数据保存成功后通知上层刷新准备状态。
 *
 * Returns:
 *   势力卡模块 React 节点。
 */
export default function FactionCardsWorkspace({
  mode,
  novelId,
  initialView = "profiles",
  requestedVolumeId = null,
  onViewChange,
  onVolumeIdChange,
  onFormalFactsChanged,
}: FactionCardsWorkspaceProps) {
  const t = useTranslations("writing.factions");
  const [activeView, setActiveView] = useState<FactionWorkspaceView>(initialView);
  const [search, setSearch] = useState("");
  const [coreWarningDismissed, setCoreWarningDismissed] = useState(false);
  const [levelFilter, setLevelFilter] = useState<FactionLevelFilter>("all");
  const [factions, setFactions] = useState<CoreFaction[]>([]);
  const [trashFactions, setTrashFactions] = useState<CoreFaction[]>([]);
  const [relations, setRelations] = useState<FactionRelation[]>([]);
  const [trashRelations, setTrashRelations] = useState<FactionRelation[]>([]);
  const [volumes, setVolumes] = useState<VolumeReadV2[]>([]);
  const [selectedVolumeId, setSelectedVolumeId] = useState("");
  const [invalidVolumeId, setInvalidVolumeId] = useState("");
  const [loadedNovelId, setLoadedNovelId] = useState("");
  const [novelVersion, setNovelVersion] = useState<number | null>(null);
  const [coreCandidateState, dispatchCoreCandidate] = useReducer(
    localCandidateReducer<CoreFactionsResultV2>,
    createLocalCandidateState<CoreFactionsResultV2>(),
  );
  const [coreGenerationInput, setCoreGenerationInput] = useState<CoreFactionsGenerationInputV2 | null>(null);
  const [selectedCoreFactionRefs, setSelectedCoreFactionRefs] = useState<string[]>([]);
  const [selectedCoreRelationRefs, setSelectedCoreRelationRefs] = useState<string[]>([]);
  const [editor, setEditor] = useState<EditorState>(null);
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [deleteIntent, setDeleteIntent] = useState<DeleteIntent>(null);
  const [relationEditor, setRelationEditor] = useState<RelationEditorState>(null);
  const [relationDeleteIntent, setRelationDeleteIntent] = useState<RelationDeleteIntent>(null);
  const [relationEditorError, setRelationEditorError] = useState("");
  const [relationFieldErrors, setRelationFieldErrors] = useState<ApiFieldErrors>({});
  const coreFlow = useTaskFlow("create_factions_by_ai");
  const relationFlow = useTaskFlow("create_faction_relations_by_ai");
  const [generationDialogOpen, setGenerationDialogOpen] = useState(false);
  const [relationGenerationDialogOpen, setRelationGenerationDialogOpen] = useState(false);
  const [relationCandidateState, dispatchRelationCandidate] = useReducer(
    localCandidateReducer<FactionRelationsResultV1>,
    createLocalCandidateState<FactionRelationsResultV1>(),
  );
  const [relationGenerationInput, setRelationGenerationInput] = useState<FactionRelationsGenerationInputV1 | null>(null);
  const [selectedRelationRefs, setSelectedRelationRefs] = useState<string[]>([]);
  const [selectedRelationIndex, setSelectedRelationIndex] = useState(0);
  const [relationConfirmOpen, setRelationConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [actionId, setActionId] = useState("");
  const [error, setError] = useState("");
  const coreGenerationAbortRef = useRef<AbortController | null>(null);
  const relationGenerationAbortRef = useRef<AbortController | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const editorMutationAbortRef = useRef<AbortController | null>(null);
  const currentNovelIdRef = useRef(novelId);
  const factionCreateCommandRef = useRef<StableRequestCommand | null>(null);
  const coreBatch = useFactionBatchCreation(novelId);
  const restoredCoreBatch = useRef("");
  const relationCreateCommandRef = useRef<StableRequestCommand | null>(null);
  const relationBulkCommandRef = useRef<StableRequestCommand | null>(null);
  currentNovelIdRef.current = novelId;
  const savingRef = useRef(false);
  savingRef.current = saving;

  const preview = coreCandidateState.candidate;
  const relationReview = relationCandidateState.candidate ? {
    relations: relationCandidateState.candidate.relations,
    selectedRelationRefs,
    selectedIndex: selectedRelationIndex,
  } : null;
  const generating = coreCandidateState.status === "generating";
  const relationGenerating = relationCandidateState.status === "generating";
  const relationSaving = relationCandidateState.status === "confirming";
  const relationGenerationError = relationCandidateState.error ?? "";

  useEffect(() => {
    if (!savingRef.current) setActiveView(initialView);
  }, [initialView]);

  const changeActiveView = useCallback((view: FactionWorkspaceView) => {
    if (saving) return;
    setActiveView(view);
    onViewChange?.(view);
  }, [onViewChange, saving]);

  const canUseSavedNovel = mode === "edit" && Boolean(novelId);
  const selectedVolume = volumes.find((volume) => volume.volume_id === selectedVolumeId) ?? null;
  const coreFactions = useMemo(
    () => factions.filter((faction) => (faction.level_type || "core") === "core"),
    [factions],
  );
  const singleWithoutRelations = coreFlow.inputs.faction_count === 1 && (!coreFactions.length || !coreFlow.inputs.connect_to_existing);
  const filteredFactions = useMemo(
    () => filterFactionProfiles(factions, search, levelFilter),
    [factions, levelFilter, search],
  );
  const shouldWarnTooManyCoreFactions = coreFactions.length >= CORE_FACTION_WARNING_COUNT && !coreWarningDismissed;
  const generationLocked = Boolean(
    preview || relationReview || generating || relationGenerating || coreCandidateState.status === "confirming" || saving || relationSaving,
  );
  const canOpenGeneratePanel = !generationLocked;
  const availableRelationFactions = useMemo(
    () => getAvailableRelationFactions(factions),
    [factions],
  );

  const relationTypeLabels: Record<FactionRelationType, string> = useMemo(
    () => ({
      hostile: t("relationTypes.hostile"),
      allied: t("relationTypes.allied"),
      cold_war: t("relationTypes.coldWar"),
      dependent: t("relationTypes.dependent"),
      subordinate: t("relationTypes.subordinate"),
      trade_partner: t("relationTypes.tradePartner"),
      secret_cooperation: t("relationTypes.secretCooperation"),
      historical_enemy: t("relationTypes.historicalEnemy"),
    }),
    [t],
  );

  const workspaceTabs = useMemo(
    () => [
      { key: "profiles" as const, label: t("tabs.profiles"), count: factions.length },
      { key: "relations" as const, label: t("tabs.relations"), count: relations.length },
      { key: "trash" as const, label: t("tabs.trash"), count: trashFactions.length + trashRelations.length },
    ],
    [factions.length, relations.length, trashFactions.length, trashRelations.length, t],
  );

  const currentCandidateVersions = useMemo(() => {
    const versions: Record<string, number> = {};
    if (novelId && novelVersion !== null) versions[`novel:${novelId}`] = novelVersion;
    for (const faction of factions) versions[`faction:${faction.faction_id}`] = faction.version;
    for (const relation of relations) versions[`faction_relation:${relation.relation_id}`] = relation.version;
    return versions;
  }, [factions, novelId, novelVersion, relations]);

  const loadData = useCallback(async () => {
    if (!novelId) return false;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestNovelId = novelId;
    loadAbortRef.current = controller;
    try {
      setLoading(true);
      setError("");
      const [novelRes, coreRes, volumeRes, localRes, relationRes, trashRes, relationTrashRes, volumesRes] = await Promise.all([
        apiGet<NovelDetail>(`/api/novels/${requestNovelId}`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${requestNovelId}/level/core`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${requestNovelId}/level/volume`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${requestNovelId}/level/local`, { signal: controller.signal }),
        apiGet<{ data: FactionRelation[] }>(`/api/faction-relations/novel/${requestNovelId}`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${requestNovelId}/trash`, { signal: controller.signal }),
        apiGet<{ data: FactionRelation[] }>(`/api/faction-relations/novel/${requestNovelId}/trash`, { signal: controller.signal }),
        apiGet<{ data: VolumeReadV2[] }>(`/api/volumes/novel/${requestNovelId}`, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return false;
      setNovelVersion(typeof novelRes.version === "number" ? novelRes.version : null);
      setFactions(mergeUniqueByKey(
        [],
        [...coreRes.data, ...volumeRes.data, ...localRes.data].map((item, index) => createFactionDraft(item, index)),
        getFactionRenderKey,
      ));
      setRelations(mergeUniqueByKey([], relationRes.data, getRelationRenderKey));
      setTrashFactions(mergeUniqueByKey([], trashRes.data.map((item, index) => createFactionDraft(item, index)), getFactionRenderKey));
      setTrashRelations(mergeUniqueByKey([], relationTrashRes.data, getRelationRenderKey));
      setVolumes(volumesRes.data);
      setLoadedNovelId(requestNovelId);
      return true;
    } catch (err) {
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return false;
      setError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      if (loadAbortRef.current === controller && currentNovelIdRef.current === requestNovelId) {
        loadAbortRef.current = null;
        setLoading(false);
      }
    }
  }, [novelId]);

  const active = useContext(RetainedViewActive);
  useResourceRefresh(novelId, loadData, active);

  useEffect(() => {
    // 小说切换或工作台卸载时同时取消两条 AI 请求，并丢弃仅存在内存中的候选。
    coreGenerationAbortRef.current?.abort();
    relationGenerationAbortRef.current?.abort();
    loadAbortRef.current?.abort();
    editorMutationAbortRef.current?.abort();
    coreGenerationAbortRef.current = null;
    relationGenerationAbortRef.current = null;
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    setSelectedCoreFactionRefs([]);
    setSelectedCoreRelationRefs([]);
    setSelectedRelationRefs([]);
    setRelationConfirmOpen(false);
    setFactions([]);
    setCoreWarningDismissed(false);
    setTrashFactions([]);
    setRelations([]);
    setTrashRelations([]);
    setVolumes([]);
    setSelectedVolumeId("");
    setInvalidVolumeId("");
    setLoadedNovelId("");
    setEditor(null);
    setEditorFieldErrors({});
    setRelationEditor(null);
    setRelationEditorError("");
    setRelationFieldErrors({});
    setDeleteIntent(null);
    setSaving(false);
    factionCreateCommandRef.current = null;
    return () => {
      coreGenerationAbortRef.current?.abort();
      relationGenerationAbortRef.current?.abort();
      loadAbortRef.current?.abort();
      editorMutationAbortRef.current?.abort();
    };
  }, [canUseSavedNovel, loadData, novelId]);

  useEffect(() => {
    if (!novelId || loadedNovelId !== novelId || saving) return;
    if (requestedVolumeId) {
      const requested = volumes.find((volume) => volume.volume_id === requestedVolumeId);
      if (requested) {
        if (selectedVolumeId && selectedVolumeId !== requested.volume_id && editor?.mode === "create") {
          editorMutationAbortRef.current?.abort();
          setEditor(null);
          setEditorFieldErrors({});
          setSaving(false);
          factionCreateCommandRef.current = null;
        }
        setSelectedVolumeId(requested.volume_id);
        setInvalidVolumeId("");
      } else if (invalidVolumeId !== requestedVolumeId) {
        editorMutationAbortRef.current?.abort();
        setEditor(null);
        setEditorFieldErrors({});
        setSaving(false);
        factionCreateCommandRef.current = null;
        setSelectedVolumeId("");
        setInvalidVolumeId(requestedVolumeId);
        onVolumeIdChange?.(null, true);
      }
      return;
    }
    if (invalidVolumeId) return;
    if (volumes.some((volume) => volume.volume_id === selectedVolumeId)) return;
    const firstVolume = volumes[0];
    if (firstVolume) {
      setSelectedVolumeId(firstVolume.volume_id);
      onVolumeIdChange?.(firstVolume.volume_id, true);
    }
  }, [editor?.mode, invalidVolumeId, loadedNovelId, novelId, onVolumeIdChange, requestedVolumeId, saving, selectedVolumeId, volumes]);

  useEffect(() => {
    if (
      novelVersion !== null &&
      !coreBatch.command && !coreBatch.busy && !loading && loadedNovelId === novelId &&
      coreCandidateState.basis &&
      coreCandidateState.status !== "stale" &&
      isCandidateBasisStale(coreCandidateState.basis, currentCandidateVersions)
    ) {
      dispatchCoreCandidate({ type: "mark_stale" });
    }
    if (
      novelVersion !== null &&
      relationCandidateState.basis &&
      relationCandidateState.status !== "stale" &&
      isCandidateBasisStale(relationCandidateState.basis, currentCandidateVersions)
    ) {
      dispatchRelationCandidate({ type: "mark_stale" });
    }
  }, [coreBatch.command, coreBatch.busy, loading, loadedNovelId, novelId, coreCandidateState.basis, coreCandidateState.status, currentCandidateVersions, novelVersion, relationCandidateState.basis, relationCandidateState.status]);

  useEffect(() => {
    if (relationCandidateState.status === "stale") setRelationConfirmOpen(false);
  }, [coreCandidateState.status, relationCandidateState.status]);

  const handleOpenGenerationDialog = () => {
    if (preview) {
      setError(t("previewBlockingGenerate"));
      return;
    }
    setError("");
    setGenerationDialogOpen(true);
  };

  const handleCancelCoreGeneration = () => {
    if (coreBatch.command || coreBatch.busy) return;
    void coreFlow.discard();

    coreGenerationAbortRef.current?.abort();
    coreGenerationAbortRef.current = null;
    dispatchCoreCandidate({ type: "discard" });
    setGenerationDialogOpen(false);
  };

  const handleGenerate = async (retry: TaskFlowRunMode = false) => {
    if (!novelId || preview || coreGenerationAbortRef.current) return;
    const requestId = coreCandidateState.requestId + 1;
    const controller = new AbortController();
    coreGenerationAbortRef.current = controller;
    dispatchCoreCandidate({ type: "generate", requestId });
    setError("");
    setGenerationDialogOpen(false);
    try {
      const setup = retry ? undefined : coreFlow.resolveSetup();
      if (setup && singleWithoutRelations) setup.inputs.independent_faction_count = 1;
      const generated = await coreFlow.run("/api/llm/generate-core-factions/stream", { novel_id: novelId }, controller.signal, retry, setup);
      if (controller.signal.aborted || coreGenerationAbortRef.current !== controller) return;
      const generationInput = generated.generationInput as CoreFactionsGenerationInputV2;
      const envelope = parseCoreFactionsEnvelope(generated.result, novelId);

      if (!envelope) {
        throw new Error(t("candidate.invalidEnvelope"));
      }
      dispatchCoreCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      setCoreGenerationInput(generationInput);
      setSelectedCoreFactionRefs(envelope.candidate.core_factions.map((faction) => faction.faction_ref));
      setSelectedCoreRelationRefs(envelope.candidate.faction_relations.map((relation) => relation.relation_ref));
      setGenerationDialogOpen(false);
    } catch (err) {
      if (!controller.signal.aborted) {
        dispatchCoreCandidate({
          type: "generation_failed",
          requestId,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    } finally {
      if (coreGenerationAbortRef.current === controller) coreGenerationAbortRef.current = null;
    }
  };

  useEffect(() => {
    const original = coreBatch.command;
    if (!original || restoredCoreBatch.current === original.key) return;
    restoredCoreBatch.current = original.key;
    const requestId = coreCandidateState.requestId + 1;
    dispatchCoreCandidate({ type: "generate", requestId });
    dispatchCoreCandidate({ type: "preview", requestId, candidate: original.preview, basis: original.body.basis });
    setCoreGenerationInput(original.body.generation_input);
    setSelectedCoreFactionRefs(original.body.selected_faction_refs);
    setSelectedCoreRelationRefs(original.body.selected_relation_refs);
  }, [coreBatch.command, coreCandidateState.requestId]);

  const handleSavePreview = async () => {
    if (!novelId || !preview || !coreCandidateState.basis || !coreGenerationInput || coreBatch.busy
        || !coreBatch.command && coreCandidateState.status === "stale") return;
    if (!selectedCoreFactionRefs.length || findRelationsWithUnselectedFaction(preview, selectedCoreFactionRefs, selectedCoreRelationRefs).length) return;
    const request: CoreFactionsAIConfirmationRequestV2 = coreBatch.command?.body ?? {
      request_type: "ai_confirmation", candidate: preview,
      selected_faction_refs: selectedCoreFactionRefs, selected_relation_refs: selectedCoreRelationRefs,
      basis: coreCandidateState.basis, generation_input: coreGenerationInput,
      expected_versions: buildCandidateExpectedVersions(coreCandidateState.basis),
    };
    const complete = await coreBatch.save(request, preview, async () => {
      // 创建回执是旧快照，恢复时只读取当前资料；读取失败保留已成功命令。
      if (!await loadData()) throw new Error(t("candidate.savedRefreshFailed"));
      onFormalFactsChanged?.();
    });
    if (complete) {
      dispatchCoreCandidate({ type: "discard" }); setCoreGenerationInput(null);
      setSelectedCoreFactionRefs([]); setSelectedCoreRelationRefs([]);
    }
  };

  const handleOpenCreate = () => {
    setError("");
    setEditorFieldErrors({});
    changeActiveView("profiles");
    const requestedLevel = levelFilter === "all" ? "core" : levelFilter;
    const level = requestedLevel === "core" || selectedVolume ? requestedLevel : "core";
    const volumeId = level === "core" ? null : selectedVolume?.volume_id ?? null;
    const siblingCount = factions.filter((faction) => (
      (faction.level_type ?? "core") === level && (faction.volume_id ?? null) === volumeId
    )).length;
    setLevelFilter(level);
    setEditor({
      mode: "create",
      draft: createFactionDraft({
        level_type: level,
        volume_id: volumeId,
        parent_faction_id: null,
        sort_order: (siblingCount + 1) * 10,
      }, siblingCount),
    });
  };

  const handleOpenEdit = (faction: CoreFaction, section: FactionSection) => {
    setError("");
    setEditorFieldErrors({});
    changeActiveView("profiles");
    setEditor({ mode: "edit", draft: createFactionDraft(faction), section });
    requestAnimationFrame(() => document.getElementById(`faction-inline-${faction.faction_id}`)?.querySelector<HTMLElement>("input:not([readonly]), textarea, select")?.focus());
  };

  const handleSaveEditor = async () => {
    if (!novelId || !editor || saving) return;
    if ((!editor.section || editor.section === "identity") && !editor.draft.name.trim()) {
      setError(t("validation.nameRequired"));
      setEditorFieldErrors({ name: [t("validation.nameRequired")] });
      if (editor.section) focusFactionInlineError(`faction-inline-${editor.draft.faction_id}`, { name: [t("validation.nameRequired")] });
      else focusRelationEditorError({ name: [t("validation.nameRequired")] });
      return;
    }
    if (editor.mode === "create" && editor.draft.level_type !== "core" && !editor.draft.volume_id) {
      setError(t("validation.volumeRequired"));
      setEditorFieldErrors({ volume_id: [t("validation.volumeRequired")] });
      focusRelationEditorError({ volume_id: [t("validation.volumeRequired")] });
      return;
    }

    editorMutationAbortRef.current?.abort();
    const controller = new AbortController();
    const requestNovelId = novelId;
    editorMutationAbortRef.current = controller;
    let restoreFocusId = "";
    try {
      setSaving(true);
      setError("");
      setEditorFieldErrors({});
      if (editor.mode === "create") {
        const request = buildFactionCreateRequest(editor.draft);
        await apiPost(`/api/factions/novel/${novelId}/create`, request, {
          headers: { "Idempotency-Key": getStableRequestKey(factionCreateCommandRef, request) },
          signal: controller.signal,
        });
        if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
        factionCreateCommandRef.current = null;
      } else if (editor.draft.faction_id) {
        const savedFaction = await apiPut<CoreFaction>(
          `/api/factions/novel/${novelId}/${editor.draft.faction_id}`,
          editor.section ? buildFactionSectionRequest(editor.draft, editor.section) : buildFactionUpdateRequest(editor.draft),
          { signal: controller.signal },
        );
        if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
        // PUT 已返回正式资料，后续刷新失败也保留刚保存的值和版本。
        setFactions((current) => current.map((faction) => faction.faction_id === savedFaction.faction_id ? createFactionDraft(savedFaction) : faction));
        if (editor.section) restoreFocusId = `faction-edit-${savedFaction.faction_id}-${editor.section}`;
      }
      setEditor(null);
      setEditorFieldErrors({});
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
      setError(err instanceof Error ? err.message : String(err));
      if (err instanceof ApiRequestError) {
        setEditorFieldErrors(err.fieldErrors);
        if (editor.section) focusFactionInlineError(`faction-inline-${editor.draft.faction_id}`, err.fieldErrors);
        else focusRelationEditorError(err.fieldErrors);
      } else {
        setEditorFieldErrors({});
        if (editor.section) focusFactionInlineError(`faction-inline-${editor.draft.faction_id}`, {});
        else focusRelationEditorError({});
      }
    } finally {
      if (editorMutationAbortRef.current === controller && currentNovelIdRef.current === requestNovelId) {
        editorMutationAbortRef.current = null;
        setSaving(false);
        // 等待保存锁解除，阅读态按钮恢复可用后再还原焦点。
        if (restoreFocusId) requestAnimationFrame(() => document.getElementById(restoreFocusId)?.focus());
      }
    }
  };

  const handleConfirmDelete = async () => {
    if (!novelId || !deleteIntent?.faction.faction_id) return;
    const factionId = deleteIntent.faction.faction_id;
    const requestKey = `${deleteIntent.mode}:${factionId}`;
    try {
      setActionId(requestKey);
      setError("");
      const deletePath = `/api/factions/novel/${novelId}/${factionId}${deleteIntent.mode === "hard" ? "/hard" : ""}`;
      await apiDelete(buildFactionVersionedDeletePath(deletePath, deleteIntent.faction));
      setDeleteIntent(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const handleRestore = async (faction: CoreFaction) => {
    if (!novelId || !faction.faction_id) return;
    const requestKey = `restore:${faction.faction_id}`;
    try {
      setActionId(requestKey);
      setError("");
      await apiPost(
        `/api/factions/novel/${novelId}/${faction.faction_id}/restore`,
        buildFactionVersionRequest(faction),
      );
      onFormalFactsChanged?.();
      await loadData();
      changeActiveView("profiles");
      const restoredLevel = faction.level_type || "core";
      setLevelFilter(restoredLevel === "core" || restoredLevel === "volume" || restoredLevel === "local" ? restoredLevel : "all");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const openCreateRelation = () => {
    changeActiveView("relations");
    setRelationEditor({ mode: "create", draft: createFactionRelationDraft(availableRelationFactions) });
    relationCreateCommandRef.current = null;
    setRelationEditorError("");
    setRelationFieldErrors({});
  };

  const openEditRelation = (relation: FactionRelation) => {
    setRelationEditor({ mode: "edit", draft: createFactionRelationDraft(factions, relation), source: relation });
    setRelationEditorError("");
    setRelationFieldErrors({});
    requestAnimationFrame(() => document.getElementById(`faction-relation-inline-${relation.relation_id}`)?.querySelector<HTMLElement>("select, input, textarea")?.focus());
  };

  const copyRelationAsNew = (relation: FactionRelation) => {
    setRelationEditor({ mode: "create", draft: createFactionRelationDraft(availableRelationFactions, relation) });
    relationCreateCommandRef.current = null;
    setRelationEditorError("");
    setRelationFieldErrors({});
  };

  const handleSaveRelation = async () => {
    if (!novelId || !relationEditor || saving) return;
    if (!isCompleteFactionRelation(relationEditor.draft)) {
      const fields: ApiFieldErrors = {};
      for (const field of ["current_state", "core_conflict", "possible_change"] as const) {
        if (!relationEditor.draft[field].trim()) fields[field] = [t("relationValidation.required")];
      }
      if (!relationEditor.draft.source_faction_id) fields.source_faction_id = [t("relationValidation.required")];
      if (!relationEditor.draft.target_faction_id) fields.target_faction_id = [t("relationValidation.required")];
      if (relationEditor.draft.source_faction_id === relationEditor.draft.target_faction_id) fields.target_faction_id = [t("relationValidation.sameEndpoint")];
      if (relationEditor.draft.intensity < 1 || relationEditor.draft.intensity > 5) fields.intensity = [t("relationValidation.intensity")];
      setRelationEditorError(t("relationValidation.incomplete"));
      setRelationFieldErrors(fields);
      if (relationEditor.mode === "edit") focusFactionInlineError(`faction-relation-inline-${relationEditor.source?.relation_id}`, fields);
      else focusRelationEditorError(fields);
      return;
    }
    editorMutationAbortRef.current?.abort();
    const controller = new AbortController();
    const requestNovelId = novelId;
    editorMutationAbortRef.current = controller;
    let restoreFocusId = "";
    setSaving(true);
    setRelationEditorError("");
    setRelationFieldErrors({});
    try {
      if (relationEditor.mode === "create") {
        await apiPost(`/api/faction-relations/novel/${novelId}`, relationEditor.draft, {
          headers: { "Idempotency-Key": getStableRequestKey(relationCreateCommandRef, relationEditor.draft) },
          signal: controller.signal,
        });
        relationCreateCommandRef.current = null;
      } else if (relationEditor.source?.relation_id) {
        const request: FactionRelationUpdateRequestV1 = {
          expected_version: relationEditor.source.version,
          relation_type: relationEditor.draft.relation_type,
          current_state: relationEditor.draft.current_state,
          core_conflict: relationEditor.draft.core_conflict,
          hidden_tension: relationEditor.draft.hidden_tension,
          possible_change: relationEditor.draft.possible_change,
          intensity: relationEditor.draft.intensity,
        };
        const savedRelation = await apiPut<FactionRelation>(`/api/faction-relations/novel/${novelId}/${relationEditor.source.relation_id}`, request, { signal: controller.signal });
        if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
        setRelations((current) => current.map((relation) => relation.relation_id === savedRelation.relation_id ? savedRelation : relation));
        restoreFocusId = `faction-relation-edit-${savedRelation.relation_id}`;
      }
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
      setRelationEditor(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      if (controller.signal.aborted || currentNovelIdRef.current !== requestNovelId) return;
      if (err instanceof ApiRequestError) {
        setRelationEditorError(err.message);
        setRelationFieldErrors(err.fieldErrors);
        if (relationEditor.mode === "edit") focusFactionInlineError(`faction-relation-inline-${relationEditor.source?.relation_id}`, err.fieldErrors);
        else focusRelationEditorError(err.fieldErrors);
      } else {
        setRelationEditorError(err instanceof Error ? err.message : String(err));
        if (relationEditor.mode === "edit") focusFactionInlineError(`faction-relation-inline-${relationEditor.source?.relation_id}`, {});
        else focusRelationEditorError({});
      }
    } finally {
      if (editorMutationAbortRef.current === controller && currentNovelIdRef.current === requestNovelId) {
        editorMutationAbortRef.current = null;
        setSaving(false);
        if (restoreFocusId) requestAnimationFrame(() => document.getElementById(restoreFocusId)?.focus());
      }
    }
  };

  const openRelationGeneration = () => {
    if (generationLocked || availableRelationFactions.length < 2) return;
    dispatchRelationCandidate({ type: "discard" });
    if (Object.hasOwn(relationFlow.inputs, "faction_ids")) relationFlow.setInputs((current) => ({ ...current, faction_ids: availableRelationFactions.slice(0, 100).map((faction) => faction.faction_id) }));
    setError("");
    setRelationGenerationDialogOpen(true);
  };

  const handleCancelRelationGeneration = () => {
    void relationFlow.discard();

    relationGenerationAbortRef.current?.abort();
    relationGenerationAbortRef.current = null;
    dispatchRelationCandidate({ type: "discard" });
    setRelationGenerationInput(null);
    setSelectedRelationRefs([]);
    setRelationConfirmOpen(false);
  };

  const handleGenerateRelations = async (retry: TaskFlowRunMode = false) => {
    if (!novelId || generationLocked || relationGenerationAbortRef.current) return;
    const requestId = relationCandidateState.requestId + 1;
    const controller = new AbortController();
    relationGenerationAbortRef.current = controller;
    dispatchRelationCandidate({ type: "generate", requestId });
    setError("");
    // 请求发起后关闭参数弹窗，运行状态与完成后的候选统一留在阵营关系工作台。
    setRelationGenerationDialogOpen(false);

    try {
      const generated = await relationFlow.run("/api/llm/generate-faction-relations/stream", { novel_id: novelId }, controller.signal, retry);
      if (controller.signal.aborted || relationGenerationAbortRef.current !== controller) return;
      const generationInput = generated.generationInput as FactionRelationsGenerationInputV1;
      const envelope = parseFactionRelationsEnvelope(generated.result, novelId);

      if (!envelope) {
        throw new Error(t("candidate.invalidEnvelope"));
      }
      dispatchRelationCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      setRelationGenerationInput(generationInput);
      setSelectedRelationRefs(envelope.candidate.relations.map((relation) => relation.relation_ref));
      setSelectedRelationIndex(0);
    } catch (err) {
      if (!controller.signal.aborted) {
        dispatchRelationCandidate({
          type: "generation_failed",
          requestId,
          message: err instanceof Error ? err.message : String(err),
        });
      }
    } finally {
      if (relationGenerationAbortRef.current === controller) {
        relationGenerationAbortRef.current = null;
      }
    }
  };

  const handleConfirmRelationReview = async () => {
    if (
      !novelId ||
      !relationReview ||
      !relationCandidateState.basis ||
      !relationGenerationInput ||
      relationCandidateState.status === "stale"
    ) return;
    const selectedRefs = new Set(selectedRelationRefs);
    const selectedRelations = relationReview.relations.filter((relation) =>
      selectedRefs.has(relation.relation_ref),
    );
    const allowedFactionIds = new Set(availableRelationFactions.map((faction) => faction.faction_id));
    if (selectedRelations.length === 0) {
      dispatchRelationCandidate({ type: "confirm_failed", message: t("relationGeneration.selectCandidate") });
      return;
    }
    if (!selectedRelations.every((relation) =>
      isCompleteFactionRelation(relation) &&
      allowedFactionIds.has(relation.source_faction_id) &&
      allowedFactionIds.has(relation.target_faction_id)
    )) {
      dispatchRelationCandidate({ type: "confirm_failed", message: t("relationGeneration.incompleteCandidate") });
      return;
    }
    const request: FactionRelationsAIConfirmationRequestV1 = {
      request_type: "ai_confirmation",
      candidate: { relations: relationReview.relations },
      selected_faction_refs: relationGenerationInput.faction_ids,
      selected_relation_refs: selectedRelationRefs,
      basis: relationCandidateState.basis,
      generation_input: relationGenerationInput,
      expected_versions: buildCandidateExpectedVersions(relationCandidateState.basis),
    };
    dispatchRelationCandidate({ type: "confirm" });
    try {
      await apiPost(`/api/faction-relations/novel/${novelId}/bulk-append`, request, {
        headers: { "Idempotency-Key": getStableRequestKey(relationBulkCommandRef, request) },
      });
      relationBulkCommandRef.current = null;
      dispatchRelationCandidate({ type: "discard" });
      setRelationGenerationInput(null);
      setSelectedRelationRefs([]);
      setRelationConfirmOpen(false);
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      dispatchRelationCandidate({
        type: "confirm_failed",
        message: err instanceof Error ? err.message : String(err),
        stale: err instanceof ApiRequestError && err.status === 409,
      });
    }
  };

  const handleToggleRelation = async (relation: FactionRelation) => {
    if (!novelId || !relation.relation_id) return;
    setActionId(`relation-active:${relation.relation_id}`);
    setError("");
    try {
      await apiPut(`/api/faction-relations/novel/${novelId}/${relation.relation_id}/active`, {
        expected_version: relation.version,
        is_active: !(relation.user_is_active ?? relation.is_active),
      });
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const handleRestoreRelation = async (relation: FactionRelation) => {
    if (!novelId || !relation.relation_id) return;
    setActionId(`relation-restore:${relation.relation_id}`);
    setError("");
    try {
      await apiPost(`/api/faction-relations/novel/${novelId}/${relation.relation_id}/restore`, { expected_version: relation.version });
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const handleConfirmRelationDelete = async () => {
    if (!novelId || !relationDeleteIntent?.relation.relation_id) return;
    const relation = relationDeleteIntent.relation;
    const id = relation.relation_id;
    setActionId(`relation-${relationDeleteIntent.mode}:${id}`);
    setRelationEditorError("");
    try {
      await apiDelete(`/api/faction-relations/novel/${novelId}/${id}${relationDeleteIntent.mode === "hard" ? "/hard" : ""}?expected_version=${relation.version}`);
      setRelationDeleteIntent(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (err) {
      setRelationEditorError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionId("");
    }
  };

  const updatePreviewFaction = (factionRef: string, patch: Partial<FactionEditorValue>) => {
    if (coreBatch.command || coreBatch.busy) return;
    if (!preview) return;
    dispatchCoreCandidate({
      type: "edit",
      candidate: {
        ...preview,
        core_factions: preview.core_factions.map((faction) =>
          faction.faction_ref === factionRef ? { ...faction, ...patch } : faction,
        ),
      },
    });
  };

  const updatePreviewRelation = (relationRef: string, patch: Partial<CoreFactionRelationCandidateV2>) => {
    if (coreBatch.command || coreBatch.busy) return;
    if (!preview) return;
    dispatchCoreCandidate({
      type: "edit",
      candidate: {
        ...preview,
        faction_relations: preview.faction_relations.map((relation) =>
          relation.relation_ref === relationRef ? { ...relation, ...patch } : relation,
        ),
      },
    });
  };

  const updateIncrementalRelation = (index: number, relation: FactionRelationsResultV1["relations"][number]) => {
    if (!relationCandidateState.candidate) return;
    const nextRelations = [...relationCandidateState.candidate.relations];
    nextRelations[index] = relation;
    dispatchRelationCandidate({
      type: "edit",
      candidate: { relations: nextRelations },
    });
  };

  if (!canUseSavedNovel) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="max-w-sm text-center">
          <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
          <p className="mt-2 text-sm text-muted">{t("createModeUnavailable")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border bg-surface">
        <h2 className="sr-only">{t("title")}</h2>
        {((error && !editor?.section) || (activeView === "profiles" && preview) || (activeView === "profiles" && shouldWarnTooManyCoreFactions)) && (
          <div className="px-4 pt-3 sm:px-6">
          {error && !editor?.section && (
            <div className="border-y border-red-200 bg-red-50/70 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
              {error}
            </div>
          )}
          {activeView === "profiles" && preview && (
            <InfoBlock tone="muted" text={t("previewBlockingGenerate")} />
          )}
          {activeView === "profiles" && shouldWarnTooManyCoreFactions && (
            <div className="mt-3 flex items-center gap-3 border-y border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              <p className="min-w-0 flex-1">{t("tooManyWarning")}</p>
              <Button isIconOnly variant="ghost" size="sm" className="shrink-0 text-current" aria-label={t("dismissWarning")} onPress={() => setCoreWarningDismissed(true)}>
                <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-4">
                  <path d="m6 6 12 12M6 18 18 6" strokeLinecap="round" />
                </svg>
              </Button>
            </div>
          )}
          </div>
        )}

        <div className="flex min-w-0 items-center gap-3 px-4 sm:px-6">
          <nav className="flex min-w-0 flex-1 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
            {workspaceTabs.map((item, index) => (
              <button
                key={item.key}
                id={`${FACTION_WORKSPACE_TAB_PREFIX}-${item.key}-tab`}
                type="button"
                role="tab"
                aria-selected={activeView === item.key}
                aria-controls={`${FACTION_WORKSPACE_TAB_PREFIX}-${item.key}-panel`}
                tabIndex={activeView === item.key ? 0 : -1}
                disabled={saving}
                onClick={() => changeActiveView(item.key)}
                onKeyDown={(event) => {
                  if (saving || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? workspaceTabs.length - 1
                      : (index + (event.key === "ArrowRight" ? 1 : -1) + workspaceTabs.length) % workspaceTabs.length;
                  const nextTab = workspaceTabs[nextIndex];
                  changeActiveView(nextTab.key);
                  document.getElementById(`${FACTION_WORKSPACE_TAB_PREFIX}-${nextTab.key}-tab`)?.focus();
                }}
                className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors ${
                  activeView === item.key
                    ? "border-accent text-accent"
                    : "border-transparent text-muted hover:border-border hover:text-foreground"
                }`}
              >
                <span>{item.label}</span>
                <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs text-muted">{item.count}</span>
              </button>
            ))}
          </nav>
          <Button className="shrink-0" variant="ghost" size="sm" onPress={loadData} isDisabled={loading || saving || generating || coreCandidateState.status === "confirming" || relationGenerating || relationSaving}>
            {loading ? t("loading") : t("refresh")}
          </Button>
        </div>
      </header>

      {((generating && !generationDialogOpen) || (relationGenerating && !relationGenerationDialogOpen)) && (
        <div className="flex shrink-0 flex-wrap items-start gap-3 px-4 py-2 sm:px-6">
          <div className="min-w-0 flex-1">
            <TaskFlowProgress
              flow={generating ? coreFlow : relationFlow}
              running
              label={`${t(generating ? "generateDialog.title" : "relationGeneration.title")} · ${t("generating")}`}
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className="mt-1 shrink-0"
            onPress={generating ? handleCancelCoreGeneration : handleCancelRelationGeneration}
          >
            {t("cancel")}
          </Button>
        </div>
      )}

      <div data-entity-body className={`@container/master flex min-h-0 flex-1 flex-col gap-3 ${(activeView === "profiles" && preview) || (activeView === "relations" && relationReview) ? "overflow-hidden" : "workspace-scrollbar overflow-y-auto px-4 py-3 sm:px-6"}`}>
        {!generating && !relationGenerating && !generationDialogOpen && !relationGenerationDialogOpen && (
          <div className={(activeView === "profiles" && preview) || (activeView === "relations" && relationReview) ? "shrink-0 px-4 pt-5 empty:hidden sm:px-6" : "empty:hidden"}>
            {activeView === "profiles" ? <TaskFlowProgress key="profiles" flow={coreFlow} failed={coreCandidateState.status === "error" && coreCandidateState.candidate === null} onRepair={coreFlow.canRepair ? () => void handleGenerate("repair") : undefined} onRetry={() => void handleGenerate(true)} onContinue={(additionalRounds) => void handleGenerate({ continuation: true, additionalRounds })} onDiscard={handleCancelCoreGeneration} />
              : activeView === "relations" ? <TaskFlowProgress key="relations" flow={relationFlow} failed={relationCandidateState.status === "error" && relationCandidateState.candidate === null} onRetry={() => void handleGenerateRelations(true)} onContinue={(additionalRounds) => void handleGenerateRelations({ continuation: true, additionalRounds })} onDiscard={handleCancelRelationGeneration} />
              : null}
          </div>
        )}
        {(
          <div
            hidden={activeView !== "profiles"}
            inert={activeView !== "profiles"}
            style={activeView !== "profiles" ? { display: "none" } : undefined}
            id={`${FACTION_WORKSPACE_TAB_PREFIX}-profiles-panel`}
            role="tabpanel"
            aria-labelledby={`${FACTION_WORKSPACE_TAB_PREFIX}-profiles-tab`}
            className="flex min-h-0 w-full flex-1 flex-col gap-3"
          >
            {!preview && coreCandidateState.status === "error" && coreCandidateState.error && (
              <p role="alert" className="border-y border-red-500/30 py-3 text-sm text-red-600 dark:text-red-300">{coreCandidateState.error}</p>
            )}
            {preview ? (
              <CoreFactionCandidateReview
                candidate={preview}
                savedFactions={availableRelationFactions}
                selectedFactionRefs={selectedCoreFactionRefs}
                selectedRelationRefs={selectedCoreRelationRefs}
                relationTypeLabels={relationTypeLabels}
                status={coreBatch.busy ? "confirming" : coreCandidateState.status}
                frozen={Boolean(coreBatch.command)}
                canRetry={Boolean(coreBatch.command)}
                onRevise={coreBatch.command?.rejected ? () => void coreBatch.revise() : undefined}
                error={coreBatch.error || coreCandidateState.error || ""}
                onToggleFaction={(factionRef) => setSelectedCoreFactionRefs((current) => current.includes(factionRef) ? current.filter((ref) => ref !== factionRef) : [...current, factionRef])}
                onToggleRelation={(relationRef) => setSelectedCoreRelationRefs((current) => current.includes(relationRef) ? current.filter((ref) => ref !== relationRef) : [...current, relationRef])}
                onFactionChange={updatePreviewFaction}
                onRelationChange={updatePreviewRelation}
                onConfirm={() => void handleSavePreview()}
                onDiscard={() => {
                  if (coreBatch.command || coreBatch.busy) return;
                  dispatchCoreCandidate({ type: "discard" });
                  setCoreGenerationInput(null);
                  setSelectedCoreFactionRefs([]);
                  setSelectedCoreRelationRefs([]);
                }}
                t={t}
              />
            ) : (
              <FactionProfilesWorkspace
              factions={filteredFactions}
              allFactions={factions}
              editor={editor?.mode === "edit" ? editor : null}
              editorError={error}
              editorFieldErrors={editorFieldErrors}
              saving={saving}
              onEditorChange={(draft) => setEditor((current) => current ? { ...current, draft } : current)}
              onEditorCancel={() => { const triggerId = editor ? `faction-edit-${editor.draft.faction_id}-${editor.section}` : ""; setEditor(null); setEditorFieldErrors({}); setError(""); requestAnimationFrame(() => document.getElementById(triggerId)?.focus()); }}
              onEditorSave={() => void handleSaveEditor()}
              allFactionCount={factions.length}
              search={search}
              levelFilter={levelFilter}
              volumes={volumes}
              selectedVolumeId={selectedVolumeId}
              invalidVolumeId={invalidVolumeId}
              loading={loading}
              generationLocked={!canOpenGeneratePanel || Boolean(editor || relationEditor)}
              actionId={actionId}
              onSearchChange={setSearch}
              onLevelFilterChange={setLevelFilter}
              onVolumeIdChange={(volumeId, replace) => {
                if (saving) return;
                if (selectedVolumeId !== volumeId && editor?.mode === "create") {
                  editorMutationAbortRef.current?.abort();
                  setEditor(null);
                  setEditorFieldErrors({});
                  setSaving(false);
                  factionCreateCommandRef.current = null;
                }
                setSelectedVolumeId(volumeId);
                setInvalidVolumeId("");
                onVolumeIdChange?.(volumeId || null, replace);
              }}
              onManualCreate={handleOpenCreate}
              onGenerate={handleOpenGenerationDialog}
              onEdit={handleOpenEdit}
              onDelete={(faction) => {
                setError("");
                setDeleteIntent({ mode: "soft", faction });
              }}
              t={t}
              />
            )}
          </div>
        )}

        {(
          <div
            hidden={activeView !== "relations"}
            inert={activeView !== "relations"}
            style={activeView !== "relations" ? { display: "none" } : undefined}
            id={`${FACTION_WORKSPACE_TAB_PREFIX}-relations-panel`}
            role="tabpanel"
            aria-labelledby={`${FACTION_WORKSPACE_TAB_PREFIX}-relations-tab`}
            className="min-h-0 flex-1"
          >
          {relationReview ? (
            <FactionRelationGenerationPreview
              value={relationReview}
              factions={availableRelationFactions}
              relationTypeLabels={relationTypeLabels}
              saving={relationSaving}
              stale={relationCandidateState.status === "stale"}
              error={relationGenerationError}
              onSelect={setSelectedRelationIndex}
              onToggle={(relationRef) => setSelectedRelationRefs((current) => current.includes(relationRef) ? current.filter((ref) => ref !== relationRef) : [...current, relationRef])}
              onChange={updateIncrementalRelation}
              onConfirm={() => setRelationConfirmOpen(true)}
              onDiscard={handleCancelRelationGeneration}
              t={t}
            />
          ) : (
          <div className="flex h-full min-h-0 w-full flex-col gap-3">
            <section className="workspace-toolbar flex shrink-0 items-end justify-end border-b border-border pb-3">
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onPress={openCreateRelation} isDisabled={availableRelationFactions.length < 2 || generationLocked || Boolean(editor || relationEditor)}>
                  {t("relationActions.create")}
                </Button>
                <Button variant="primary" size="sm" onPress={openRelationGeneration} isDisabled={availableRelationFactions.length < 2 || generationLocked || Boolean(editor || relationEditor)}>
                  {relationGenerating ? t("generating") : t("relationActions.generate")}
                </Button>
              </div>
            </section>
            {!relationReview && relationCandidateState.status === "error" && relationGenerationError && (
              <div className="border-y border-red-200 bg-red-50/70 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">{relationGenerationError}</div>
            )}
            {relations.length === 0 ? (
              <EmptyBlock text={t("emptyRelations")} />
            ) : (
              <div className="min-h-[500px] flex-1 @min-[800px]/master:min-h-0">
                <FactionRelationsWorkspace editor={relationEditor?.mode === "edit" ? relationEditor : null} saving={saving} error={relationEditorError} fieldErrors={relationFieldErrors} onChange={(draft) => setRelationEditor((current) => current ? { ...current, draft } : current)} onCancel={() => { const triggerId = `faction-relation-edit-${relationEditor?.source?.relation_id}`; setRelationEditor(null); setRelationEditorError(""); setRelationFieldErrors({}); requestAnimationFrame(() => document.getElementById(triggerId)?.focus()); }} onSave={() => void handleSaveRelation()} relations={relations} relationTypeLabels={relationTypeLabels} actionId={actionId} onEdit={openEditRelation} onCopy={copyRelationAsNew} onToggle={(relation) => void handleToggleRelation(relation)} onDelete={(relation) => { setRelationEditorError(""); setRelationDeleteIntent({ mode: "soft", relation }); }} t={t} />
              </div>
            )}
          </div>
          )}
          </div>
        )}

        {activeView === "trash" && (
          <div
            id={`${FACTION_WORKSPACE_TAB_PREFIX}-trash-panel`}
            role="tabpanel"
            aria-labelledby={`${FACTION_WORKSPACE_TAB_PREFIX}-trash-tab`}
            className="workspace-scrollbar h-full w-full overflow-y-auto pr-1"
          >
            <TrashPanel
              factions={trashFactions}
              relations={trashRelations}
              actionId={actionId}
              onRestore={handleRestore}
              onHardDelete={(faction) => {
                setError("");
                setDeleteIntent({ mode: "hard", faction });
              }}
              onRestoreRelation={(relation) => void handleRestoreRelation(relation)}
              onHardDeleteRelation={(relation) => {
                setRelationEditorError("");
                setRelationDeleteIntent({ mode: "hard", relation });
              }}
              t={t}
            />
          </div>
        )}
      </div>

      {editor?.mode === "create" && (
        <EditorModal
          editor={editor}
          factions={factions}
          volumes={volumes}
          selectedVolumeId={selectedVolumeId}
          saving={saving}
          error={error}
          fieldErrors={editorFieldErrors}
          onChange={(draft) => setEditor((prev) => (prev ? { ...prev, draft } : prev))}
          onCancel={() => { setEditor(null); setEditorFieldErrors({}); }}
          onSave={handleSaveEditor}
          t={t}
        />
      )}

      {relationEditor?.mode === "create" && (
        <FactionRelationEditorModal
          editor={relationEditor}
          factions={relationEditor.mode === "create" ? availableRelationFactions : factions}
          saving={saving}
          error={relationEditorError}
          fieldErrors={relationFieldErrors}
          onChange={(draft) => setRelationEditor((current) => current ? { ...current, draft } : current)}
          onCancel={() => setRelationEditor(null)}
          onSave={() => void handleSaveRelation()}
          t={t}
        />
      )}

      {generationDialogOpen && (
        <TaskFlowDialog title={t("generateDialog.title")} notice={singleWithoutRelations ? t("generateDialog.singleWithoutRelations") : undefined} hiddenFields={[...(!coreFactions.length ? ["connect_to_existing", "existing_relation_targets", "existing_relation_score"] : []), ...(singleWithoutRelations ? ["independent_faction_count"] : [])]} flow={coreFlow} disabled={generating} failed={coreCandidateState.status === "error" && coreCandidateState.candidate === null} onCancel={handleCancelCoreGeneration} onGenerate={() => void handleGenerate()} />
      )}

      {deleteIntent && (
          <ConfirmActionModal
          title={deleteIntent.mode === "soft" ? t("deleteConfirmTitle") : t("hardDeleteConfirmTitle")}
          message={
            deleteIntent.mode === "soft"
              ? t("deleteConfirmMessage", { name: deleteIntent.faction.name })
              : t("hardDeleteConfirmMessage", { name: deleteIntent.faction.name })
          }
          confirmText={deleteIntent.mode === "soft" ? t("delete") : t("hardDelete")}
          danger={deleteIntent.mode === "hard"}
          error={error}
          isLoading={actionId === `${deleteIntent.mode}:${deleteIntent.faction.faction_id}`}
          onCancel={() => setDeleteIntent(null)}
          onConfirm={handleConfirmDelete}
          cancelText={t("cancel")}
          loadingText={t("processing")}
        />
      )}

      {relationConfirmOpen && relationReview && (
        <ConfirmActionModal
          title={t("relationCandidate.confirmTitle")}
          message={t("relationCandidate.confirmMessage", {
            relations: selectedRelationRefs.length,
          })}
          confirmText={t("relationCandidate.confirm")}
          error={relationCandidateState.error ?? ""}
          isLoading={relationCandidateState.status === "confirming"}
          onCancel={() => setRelationConfirmOpen(false)}
          onConfirm={() => void handleConfirmRelationReview()}
          cancelText={t("cancel")}
          loadingText={t("relationCandidate.confirming")}
        />
      )}

      {relationDeleteIntent && (
        <ConfirmActionModal
          title={relationDeleteIntent.mode === "soft" ? t("relationConfirm.deleteTitle") : t("relationConfirm.hardDeleteTitle")}
          message={(
            <>
              <p>{relationDeleteIntent.mode === "soft" ? t("relationConfirm.deleteMessage") : t("relationConfirm.hardDeleteMessage")}</p>
              <p className="mt-3 font-medium text-foreground">{relationDeleteIntent.relation.source_faction_name ?? relationDeleteIntent.relation.source_faction_id} {isSymmetricFactionRelation(relationDeleteIntent.relation.relation_type) ? "↔" : "→"} {relationDeleteIntent.relation.target_faction_name ?? relationDeleteIntent.relation.target_faction_id}</p>
              <p className="mt-1 font-mono text-xs text-muted">{relationDeleteIntent.relation.relation_id}</p>
            </>
          )}
          confirmText={relationDeleteIntent.mode === "soft" ? t("delete") : t("hardDelete")}
          danger
          error={relationEditorError}
          isLoading={actionId === `relation-${relationDeleteIntent.mode}:${relationDeleteIntent.relation.relation_id}`}
          onCancel={() => setRelationDeleteIntent(null)}
          onConfirm={() => void handleConfirmRelationDelete()}
          cancelText={t("cancel")}
          loadingText={t("processing")}
        />
      )}

      {relationGenerationDialogOpen && (
        <TaskFlowDialog title={t("relationGeneration.title")} flow={relationFlow} failed={relationCandidateState.status === "error" && relationCandidateState.candidate === null} fieldChoices={{ faction_ids: availableRelationFactions.map((faction) => ({ value: faction.faction_id, label: getFactionName(faction) })) }} onCancel={() => setRelationGenerationDialogOpen(false)} onGenerate={() => void handleGenerateRelations()} />
      )}
    </div>
  );
}

/**
 * 功能：创建人工阵营关系表单草稿，或从正式响应提取可复制字段。
 * Args:
 *   factions: 当前可选的活动核心势力。
 *   source: 可选的已落库关系。
 * Returns:
 *   只包含关系创建契约字段的草稿。
 */
export function createFactionRelationDraft(
  factions: CoreFaction[],
  source?: FactionRelation,
): FactionRelationCreateRequestV1 {
  const requestedSourceId = source?.source_faction_id;
  const sourceFactionId = factions.some((item) => item.faction_id === requestedSourceId)
    ? requestedSourceId ?? ""
    : factions[0]?.faction_id ?? "";
  const requestedTargetId = source?.target_faction_id;
  const targetFactionId = factions.some((item) => item.faction_id === requestedTargetId && item.faction_id !== sourceFactionId)
    ? requestedTargetId ?? ""
    : factions.find((item) => item.faction_id !== sourceFactionId)?.faction_id ?? "";
  return {
    source_faction_id: sourceFactionId,
    target_faction_id: targetFactionId,
    relation_type: source?.relation_type ?? "allied",
    current_state: source?.current_state ?? "",
    core_conflict: source?.core_conflict ?? "",
    hidden_tension: source?.hidden_tension ?? "",
    possible_change: source?.possible_change ?? "",
    intensity: source?.intensity ?? 3,
    is_active: source?.user_is_active ?? source?.is_active ?? true,
  };
}

/**
 * 功能：校验人工阵营关系是否满足提交前的最低约束。
 * Args:
 *   draft: 当前关系草稿。
 * Returns:
 *   端点不同、必填叙述完整且强度位于 1 至 5 时返回 true；隐藏张力允许为空。
 */
function isCompleteFactionRelation(draft: FactionRelationCreateRequestV1): boolean {
  return Boolean(
    draft.source_faction_id &&
    draft.target_faction_id &&
    draft.source_faction_id !== draft.target_faction_id &&
    draft.current_state.trim() &&
    draft.core_conflict.trim() &&
    draft.possible_change.trim() &&
    Number.isInteger(draft.intensity) &&
    draft.intensity >= 1 &&
    draft.intensity <= 5
  );
}

type FactionEditorValue = Pick<
  CoreFaction,
  | "name"
  | "alias"
  | "faction_type"
  | "positioning"
  | "public_stance"
  | "core_goal"
  | "hidden_goal"
  | "resources_and_advantages"
  | "organization_style"
  | "core_values"
  | "conflict_with_mainline"
  | "is_public"
  | "influence_scope"
  | "expandability"
  | "tags"
>;

interface CoreFactionCandidateReviewProps {
  candidate: CoreFactionsResultV2;
  savedFactions: CoreFaction[];
  selectedFactionRefs: string[];
  selectedRelationRefs: string[];
  relationTypeLabels: Record<FactionRelationType, string>;
  status: CandidateStateName;
  frozen?: boolean;
  canRetry?: boolean;
  onRevise?: () => void;
  error: string;
  onToggleFaction: (factionRef: string) => void;
  onToggleRelation: (relationRef: string) => void;
  onFactionChange: (factionRef: string, patch: Partial<FactionEditorValue>) => void;
  onRelationChange: (relationRef: string, patch: Partial<CoreFactionRelationCandidateV2>) => void;
  onConfirm: () => void;
  onDiscard: () => void;
  t: ReturnType<typeof useTranslations>;
}

type CoreCandidateEditIntent =
  | { kind: "faction"; ref: string }
  | { kind: "relation"; ref: string }
  | null;

/** 渲染核心势力 AI 候选的平面选择、编辑与确认工作区。 */
function CoreFactionCandidateReview({
  candidate,
  savedFactions,
  selectedFactionRefs,
  selectedRelationRefs,
  relationTypeLabels,
  status,
  frozen, canRetry, onRevise,
  error,
  onToggleFaction,
  onToggleRelation,
  onFactionChange,
  onRelationChange,
  onConfirm,
  onDiscard,
  t,
}: CoreFactionCandidateReviewProps) {
  const [editIntent, setEditIntent] = useState<CoreCandidateEditIntent>({ kind: "faction", ref: candidate.core_factions[0]?.faction_ref ?? "" });
  const detailRef = useRef<HTMLDivElement>(null);
  const disabled = status === "confirming" || frozen;
  const stale = status === "stale";
  const selectedFactionSet = new Set(selectedFactionRefs);
  const selectedRelationSet = new Set(selectedRelationRefs);
  const invalidRelationRefs = findRelationsWithUnselectedFaction(
    candidate,
    selectedFactionRefs,
    selectedRelationRefs,
  );
  const editedFaction = editIntent?.kind === "faction"
    ? candidate.core_factions.find((faction) => faction.faction_ref === editIntent.ref) ?? null
    : null;
  const editedRelation = editIntent?.kind === "relation"
    ? candidate.faction_relations.find((relation) => relation.relation_ref === editIntent.ref) ?? null
    : null;
  const endpointOptions: Array<{ value: string; endpoint: CoreFactionRelationEndpointV2; label: string }> = [
    ...candidate.core_factions.map((faction) => ({
      value: `candidate:${faction.faction_ref}`,
      endpoint: { kind: "candidate" as const, faction_ref: faction.faction_ref },
      label: faction.name,
    })),
    ...savedFactions.map((faction) => ({
      value: `existing:${faction.faction_id}`,
      endpoint: { kind: "existing" as const, faction_id: faction.faction_id },
      label: faction.name,
    })),
  ];
  const endpointLabels = new Map(endpointOptions.map((option) => [option.value, option.label]));
  const endpointByValue = new Map(endpointOptions.map((option) => [option.value, option.endpoint]));

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface">
      <div className="@container workspace-scrollbar min-h-0 w-full min-w-0 flex-1 overflow-y-auto px-4 py-3 sm:px-6 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30" tabIndex={0} aria-label={t("candidate.title")}>
        <header className="border-b border-border pb-4">
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
            <h3 className="text-lg font-semibold text-foreground">{t("candidate.title")}</h3>
            <p className="text-xs text-muted">
              {t("candidate.meta", {
                factions: selectedFactionRefs.length,
                relations: selectedRelationRefs.length,
              })}
            </p>
          </div>
          {stale && (
            <p className="mt-4 border-y border-amber-300 bg-amber-50/70 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/25 dark:text-amber-200" role="alert">
              {t("candidate.stale")}
            </p>
          )}
          {!stale && error && (
            <p className="mt-4 border-y border-red-200 bg-red-50/70 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300" role="alert">
              {error}
            </p>
          )}
          {invalidRelationRefs.length > 0 && (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-300" role="status">
              {t("candidate.relationNeedsFaction", { refs: invalidRelationRefs.join(", ") })}
            </p>
          )}
        </header>
        <div className="grid min-h-0 min-w-0 gap-5 @min-[800px]:grid-cols-[260px_minmax(0,1fr)]"><div className="workspace-scrollbar max-h-64 overflow-y-auto border-x border-border bg-surface-secondary/45 @min-[800px]:max-h-[65vh]">

        <section className="py-5" aria-labelledby="core-candidate-factions-heading">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h4 id="core-candidate-factions-heading" className="text-sm font-semibold text-foreground">
              {t("candidate.factions", { count: candidate.core_factions.length })}
            </h4>
            <span className="text-xs text-muted">{t("candidate.selectedCount", { count: selectedFactionRefs.length })}</span>
          </div>
          <ul className="divide-y divide-border border-y border-border">
            {candidate.core_factions.map((faction) => (
              <li key={faction.faction_ref} className={`flex min-w-0 items-center gap-3 border-l-2 px-3 py-3 ${editIntent?.kind === "faction" && editIntent.ref === faction.faction_ref ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
                <input
                  type="checkbox"
                  aria-label={t("candidate.toggleFaction", { name: faction.name })}
                  checked={selectedFactionSet.has(faction.faction_ref)}
                  onChange={() => onToggleFaction(faction.faction_ref)}
                  disabled={disabled}
                  className="size-4 shrink-0 accent-[var(--color-accent)]"
                />
                <div className="min-w-0 flex-1">
                  <button type="button" className="min-h-11 w-full min-w-0 text-left text-sm font-medium text-foreground [overflow-wrap:anywhere] focus-visible:outline-2 focus-visible:outline-accent" aria-current={editIntent?.kind === "faction" && editIntent.ref === faction.faction_ref ? "true" : undefined} disabled={disabled} onClick={() => setEditIntent({ kind: "faction", ref: faction.faction_ref })}>{faction.name}</button>

                </div>
                <SectionEditButton label={t("edit")} onPress={() => { setEditIntent({ kind: "faction", ref: faction.faction_ref }); requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus()); }} isDisabled={disabled} />
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-border py-5" aria-labelledby="core-candidate-relations-heading">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h4 id="core-candidate-relations-heading" className="text-sm font-semibold text-foreground">
              {t("candidate.relations", { count: candidate.faction_relations.length })}
            </h4>
            <span className="text-xs text-muted">{t("candidate.selectedCount", { count: selectedRelationRefs.length })}</span>
          </div>
          {candidate.faction_relations.length === 0 ? (
            <p className="border-y border-border px-1 py-4 text-sm text-muted">{t("emptyPreviewRelations")}</p>
          ) : (
            <ul className="divide-y divide-border border-y border-border">
              {candidate.faction_relations.map((relation) => {
                const connector = isSymmetricFactionRelation(relation.relation_type) ? "↔" : "→";
                return (
                  <li key={relation.relation_ref} className={`flex min-w-0 items-center gap-3 border-l-2 px-3 py-3 ${editIntent?.kind === "relation" && editIntent.ref === relation.relation_ref ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}>
                    <input
                      type="checkbox"
                      aria-label={t("candidate.toggleRelation", { ref: relation.relation_ref })}
                      checked={selectedRelationSet.has(relation.relation_ref)}
                      onChange={() => onToggleRelation(relation.relation_ref)}
                      disabled={disabled}
                      className="size-4 shrink-0 accent-[var(--color-accent)]"
                    />
                    <div className="min-w-0 flex-1">
                      <button type="button" className="min-h-11 w-full min-w-0 text-left text-sm font-medium text-foreground [overflow-wrap:anywhere] focus-visible:outline-2 focus-visible:outline-accent" aria-current={editIntent?.kind === "relation" && editIntent.ref === relation.relation_ref ? "true" : undefined} disabled={disabled} onClick={() => setEditIntent({ kind: "relation", ref: relation.relation_ref })}>
                        {endpointLabels.get(endpointIdentity(relation.source)) ?? endpointIdentity(relation.source)} {connector} {endpointLabels.get(endpointIdentity(relation.target)) ?? endpointIdentity(relation.target)}
                      </button>
                      <p className="truncate text-xs text-muted">{relationTypeLabels[relation.relation_type]} · {relation.intensity}/5</p>

                    </div>
                    <SectionEditButton label={t("edit")} onPress={() => { setEditIntent({ kind: "relation", ref: relation.relation_ref }); requestAnimationFrame(() => detailRef.current?.querySelector<HTMLElement>("input, select, textarea")?.focus()); }} isDisabled={disabled} />
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        </div><div ref={detailRef} className="workspace-scrollbar min-w-0 bg-surface py-5 @min-[800px]:max-h-[65vh] @min-[800px]:overflow-y-auto @min-[800px]:px-3">
                <h3 className="mb-4 text-[22px] font-semibold leading-7 [overflow-wrap:anywhere]">{editedFaction?.name ?? (editedRelation ? `${endpointLabels.get(endpointIdentity(editedRelation.source))} ${isSymmetricFactionRelation(editedRelation.relation_type) ? "↔" : "→"} ${endpointLabels.get(endpointIdentity(editedRelation.target))}` : "")}</h3>
                {editedFaction && (
                  <FactionEditor
                    value={editedFaction}
                    onChange={(patch) => onFactionChange(editedFaction.faction_ref, patch)}
                    t={t}
                    disabled={disabled}
                  />
                )}
                {editedRelation && (
                  <fieldset disabled={disabled} className="min-w-0 space-y-6">
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(170px,0.7fr)_minmax(0,1fr)]">
                      <SelectInput
                        label={t("fields.sourceFaction")}
                        value={endpointIdentity(editedRelation.source)}
                        options={endpointOptions.map((option) => option.value)}
                        optionLabel={(option) => endpointLabels.get(option) ?? option}
                        onChange={(value) => {
                          const endpoint = endpointByValue.get(value);
                          if (endpoint) onRelationChange(editedRelation.relation_ref, { source: endpoint });
                        }}
                      />
                      <SelectInput
                        label={t("fields.relationType")}
                        value={editedRelation.relation_type}
                        options={RELATION_TYPES}
                        optionLabel={(option) => relationTypeLabels[option as FactionRelationType]}
                        onChange={(value) => onRelationChange(editedRelation.relation_ref, { relation_type: value as FactionRelationType })}
                      />
                      <SelectInput
                        label={t("fields.targetFaction")}
                        value={endpointIdentity(editedRelation.target)}
                        options={endpointOptions.map((option) => option.value)}
                        optionLabel={(option) => endpointLabels.get(option) ?? option}
                        onChange={(value) => {
                          const endpoint = endpointByValue.get(value);
                          if (endpoint) onRelationChange(editedRelation.relation_ref, { target: endpoint });
                        }}
                      />
                    </div>
                    <TextArea label={t("fields.currentState")} value={editedRelation.current_state} rows={3} onChange={(current_state) => onRelationChange(editedRelation.relation_ref, { current_state })} />
                    <TextArea label={t("fields.coreConflict")} value={editedRelation.core_conflict} rows={4} onChange={(core_conflict) => onRelationChange(editedRelation.relation_ref, { core_conflict })} />
                    <div className="grid gap-5 lg:grid-cols-2">
                      <TextArea label={t("fields.hiddenTension")} value={editedRelation.hidden_tension} rows={3} onChange={(hidden_tension) => onRelationChange(editedRelation.relation_ref, { hidden_tension })} />
                      <TextArea label={t("fields.possibleChange")} value={editedRelation.possible_change} rows={3} onChange={(possible_change) => onRelationChange(editedRelation.relation_ref, { possible_change })} />
                    </div>
                    <RelationIntensityField
                      label={t("fields.intensity")}
                      value={editedRelation.intensity}
                      onChange={(intensity) => onRelationChange(editedRelation.relation_ref, { intensity })}
                      inputClassName="min-h-11 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                    />
                  </fieldset>
                )}

        </div></div>
      </div>
      <footer className="flex shrink-0 flex-col-reverse flex-wrap gap-2 border-t border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-end sm:px-6">
        {onRevise && <Button variant="outline" size="sm" onPress={onRevise} isDisabled={status === "confirming"}>{t("candidate.reviseBatch")}</Button>}
        <Button variant="ghost" size="sm" onPress={onDiscard} isDisabled={disabled}>{t("candidate.discard")}</Button>
        <Button
          variant="primary"
          size="sm"
          onPress={onConfirm}
          isDisabled={status === "confirming" || !canRetry && (stale || selectedFactionRefs.length === 0 || invalidRelationRefs.length > 0)}
        >
          {status === "confirming" ? t("candidate.confirming") : canRetry ? t("candidate.retrySave") : t("candidate.review")}
        </Button>
      </footer>


    </div>
  );
}

/**
 * 按身份、战略、组织和剧情作用渲染势力档案编辑器。
 *
 * Args:
 *   props: 当前势力数据、字段更新回调、翻译函数、别名可见性及禁用状态。
 *
 * Returns:
 *   使用语义化控件编辑势力字段的 React 节点。
 */
function FactionEditor({
  value,
  onChange,
  t,
  showAliases = false,
  disabled = false,
  section,
  fieldErrors = {},
}: {
  value: FactionEditorValue;
  onChange: (patch: Partial<FactionEditorValue>) => void;
  t: ReturnType<typeof useTranslations>;
  showAliases?: boolean;
  disabled?: boolean;
  section?: FactionSection;
  fieldErrors?: ApiFieldErrors;
}) {
  const fieldError = (name: string) => fieldErrors[name]?.[0] ?? fieldErrors[`payload.${name}`]?.[0];
  return (
    <div className={section ? "min-w-0" : "space-y-9"}>
      {(!section || section === "identity") && <section>
        {!section && <SectionHeading index="A" title={t("sections.identity")} />}
        <div className="detail-fields grid gap-4">
          <TextInput
            name="name"
            error={fieldError("name")}
            label={t("fields.name")}
            value={value.name}
            required
            placeholder={t("placeholders.name")}
            disabled={disabled}
            onChange={(name) => onChange({ name })}
          />
          <TextInput
            name="faction_type"
            error={fieldError("faction_type")}
            label={t("fields.factionType")}
            value={value.faction_type}
            placeholder={t("placeholders.factionType")}
            disabled={disabled}
            onChange={(faction_type) => onChange({ faction_type })}
          />
          <TextInput
            name="influence_scope"
            error={fieldError("influence_scope")}
            label={t("fields.influenceScope")}
            value={value.influence_scope}
            placeholder={t("placeholders.influenceScope")}
            disabled={disabled}
            onChange={(influence_scope) => onChange({ influence_scope })}
          />
        </div>
        {showAliases && (
          <TagInput
            className="mt-5"
            name="alias"
            error={fieldError("alias")}
            label={t("fields.aliases")}
            values={value.alias ?? []}
            onChange={(alias) => onChange({ alias })}
            getRemoveAriaLabel={(tag) => t("removeTag", { tag })}
            placeholder={t("placeholders.aliases")}
            limitReachedText={t("tagLimitReached")}
            disabled={disabled}
          />
        )}
        <div className="mt-5 border-l-2 border-accent/30 pl-4">
          <PublicStatusSwitch
            name="is_public"
            checked={value.is_public}
            disabled={disabled}
            label={t("fields.isPublic")}
            onChange={(is_public) => onChange({ is_public })}
          />
        </div>
      </section>}

      {(!section || section === "strategy") && <section className={section ? "" : "border-t border-border pt-8"}>
        {!section && <SectionHeading index="B" title={t("sections.strategy")} />}
        <div className="grid gap-5">
          <TextArea
            name="positioning"
            error={fieldError("positioning")}
            className="col-span-full"
            label={t("fields.positioning")}
            value={value.positioning}
            rows={4}
            placeholder={t("placeholders.positioning")}
            disabled={disabled}
            onChange={(positioning) => onChange({ positioning })}
          />
          <TextArea
            name="public_stance"
            error={fieldError("public_stance")}
            label={t("fields.publicStance")}
            value={value.public_stance}
            rows={3}
            placeholder={t("placeholders.publicStance")}
            disabled={disabled}
            onChange={(public_stance) => onChange({ public_stance })}
          />
          <TextArea
            name="core_goal"
            error={fieldError("core_goal")}
            label={t("fields.coreGoal")}
            value={value.core_goal}
            rows={4}
            placeholder={t("placeholders.coreGoal")}
            disabled={disabled}
            onChange={(core_goal) => onChange({ core_goal })}
          />
          <TextArea
            name="hidden_goal"
            error={fieldError("hidden_goal")}
            className="col-span-full"
            label={t("fields.hiddenGoal")}
            value={value.hidden_goal ?? ""}
            rows={3}
            placeholder={t("placeholders.hiddenGoal")}
            disabled={disabled}
            onChange={(hidden_goal) => onChange({ hidden_goal })}
          />
        </div>
      </section>}

      {(!section || section === "structure") && <section className={section ? "" : "border-t border-border pt-8"}>
        {!section && <SectionHeading index="C" title={t("sections.structure")} />}
        <TextArea
          name="organization_style"
            error={fieldError("organization_style")}
          label={t("fields.organizationStyle")}
          value={value.organization_style}
          rows={3}
          placeholder={t("placeholders.organizationStyle")}
          disabled={disabled}
          onChange={(organization_style) => onChange({ organization_style })}
        />
        <div className="mt-5 grid gap-5">
          <TagInput
            name="resources_and_advantages"
            error={fieldError("resources_and_advantages")}
            label={t("fields.resources")}
            values={value.resources_and_advantages ?? []}
            onChange={(resources_and_advantages) => onChange({ resources_and_advantages })}
            getRemoveAriaLabel={(tag) => t("removeTag", { tag })}
            placeholder={t("placeholders.resources")}
            limitReachedText={t("tagLimitReached")}
            maxItems={6}
            disabled={disabled}
          />
          <TagInput
            name="core_values"
            error={fieldError("core_values")}
            label={t("fields.values")}
            values={value.core_values ?? []}
            onChange={(core_values) => onChange({ core_values })}
            getRemoveAriaLabel={(tag) => t("removeTag", { tag })}
            placeholder={t("placeholders.values")}
            limitReachedText={t("tagLimitReached")}
            maxItems={6}
            disabled={disabled}
          />
        </div>
      </section>}

      {(!section || section === "story") && <section className={section ? "" : "border-t border-border pt-8"}>
        {!section && <SectionHeading index="D" title={t("sections.story")} />}
        <div className="grid gap-5">
          <TextArea
            name="conflict_with_mainline"
            error={fieldError("conflict_with_mainline")}
            label={t("fields.conflict")}
            value={value.conflict_with_mainline}
            rows={5}
            placeholder={t("placeholders.conflict")}
            disabled={disabled}
            onChange={(conflict_with_mainline) => onChange({ conflict_with_mainline })}
          />
          <TextArea
            name="expandability"
            error={fieldError("expandability")}
            label={t("fields.expandability")}
            value={value.expandability}
            rows={4}
            placeholder={t("placeholders.expandability")}
            disabled={disabled}
            onChange={(expandability) => onChange({ expandability })}
          />
        </div>
        <TagInput
          className="mt-5"
          name="tags"
            error={fieldError("tags")}
          label={t("fields.tags")}
          values={value.tags ?? []}
          onChange={(tags) => onChange({ tags })}
          getRemoveAriaLabel={(tag) => t("removeTag", { tag })}
          placeholder={t("placeholders.tags")}
          limitReachedText={t("tagLimitReached")}
          maxItems={8}
          disabled={disabled}
        />
      </section>}
    </div>
  );
}

/**
 * 渲染势力编辑区的语义分段标题。
 *
 * Args:
 *   index: 分段序号或字母标识。
 *   title: 分段标题。
 * Returns:
 *   带序号和标题的 React 节点。
 */
function SectionHeading({ index, title }: { index: string; title: string }) {
  return (
    <div className="mb-5 flex items-center gap-3">
      <span className="font-mono text-xs font-semibold text-accent">{index}</span>
      <h4 className="text-sm font-semibold text-foreground">{title}</h4>
    </div>
  );
}

/**
 * 渲染公开状态开关。
 *
 * Args:
 *   checked: 当前是否公开存在。
 *   disabled: 是否禁止切换。
 *   label: 开关标题。
 *   onChange: 状态变更回调。
 *
 * Returns:
 *   可访问的 switch 控件 React 节点。
 */
function PublicStatusSwitch({
  name,
  checked,
  disabled,
  label,
  onChange,
}: {
  name?: string;
  checked: boolean;
  disabled: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <p className="text-sm font-medium text-foreground">{label}</p>
      <button
        name={name}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className={`relative h-7 w-12 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${
          checked ? "bg-accent" : "bg-surface-secondary"
        }`}
      >
        <span
          className={`absolute left-1 top-1 h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}

/**
 * 渲染手动创建或编辑核心势力的模态工作区。
 *
 * Args:
 *   props: 编辑状态、保存状态、错误信息、草稿更新与保存取消回调及翻译函数。
 *
 * Returns:
 *   带固定标题和操作区的势力编辑对话框 React 节点。
 */
function EditorModal({
  editor,
  factions,
  volumes,
  selectedVolumeId,
  saving,
  error,
  fieldErrors,
  onChange,
  onCancel,
  onSave,
  t,
}: {
  editor: NonNullable<EditorState>;
  factions: CoreFaction[];
  volumes: VolumeReadV2[];
  selectedVolumeId: string;
  saving: boolean;
  error: string;
  fieldErrors: ApiFieldErrors;
  onChange: (draft: CoreFaction) => void;
  onCancel: () => void;
  onSave: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const level = (editor.draft.level_type ?? "core") as "core" | "volume" | "local";
  const parentOptions = factions.filter((faction) => {
    if (faction.is_deleted || (faction.active_status ?? "active") !== "active") return false;
    if (faction.faction_id === editor.draft.faction_id) return false;
    const parentLevel = faction.level_type ?? "core";
    if (level === "core") return parentLevel === "core";
    return parentLevel === "core" || (
      (parentLevel === "volume" || parentLevel === "local")
      && faction.volume_id === editor.draft.volume_id
    );
  });
  return (
      <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !saving && onCancel()} variant="blur" isDismissable={!saving}>
        <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
          <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-5xl">
            <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
          <div>
            <Modal.Heading className="text-lg font-semibold text-foreground">
              {editor.mode === "create" ? t("editor.createTitle") : t("editor.editTitle")}
            </Modal.Heading>
          </div>
              <Modal.CloseTrigger aria-label={t("cancel")} isDisabled={saving} />
            </Modal.Header>
        {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} className="mx-5 mt-4 sm:mx-7" />}
        <Modal.Body className="px-5 py-6 sm:px-7 sm:py-8">
          <section className="mb-8 border-b border-border pb-7" aria-labelledby="faction-editor-scope-heading">
            <h3 id="faction-editor-scope-heading" className="text-sm font-semibold text-foreground">{t("editor.scopeTitle")}</h3>
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              <label className="grid gap-1.5 text-xs font-medium text-muted">
                <span>{t("fields.levelType")}</span>
                <select
                  name="level_type"
                  value={level}
                  disabled={saving || editor.mode === "edit"}
                  className={RELATION_INPUT_CLASS}
                  onChange={(event) => {
                    const nextLevel = event.target.value as "core" | "volume" | "local";
                    const nextVolumeId = nextLevel === "core"
                      ? null
                      : editor.draft.volume_id || selectedVolumeId || volumes[0]?.volume_id || null;
                    const siblingCount = factions.filter((faction) => (
                      (faction.level_type ?? "core") === nextLevel
                      && (faction.volume_id ?? null) === nextVolumeId
                    )).length;
                    onChange({
                      ...editor.draft,
                      level_type: nextLevel,
                      volume_id: nextVolumeId,
                      parent_faction_id: null,
                      sort_order: (siblingCount + 1) * 10,
                    });
                  }}
                >
                  <option value="core">{t("categories.core")}</option>
                  <option value="volume" disabled={volumes.length === 0}>{t("categories.volume")}</option>
                  <option value="local" disabled={volumes.length === 0}>{t("categories.local")}</option>
                </select>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted">
                <span>{t("fields.volumeId")}</span>
                <select
                  name="volume_id"
                  value={editor.draft.volume_id ?? ""}
                  disabled={saving || editor.mode === "edit" || level === "core"}
                  className={RELATION_INPUT_CLASS}
                  onChange={(event) => {
                    const nextVolumeId = event.target.value;
                    const siblingCount = factions.filter((faction) => (
                      (faction.level_type ?? "core") === level && faction.volume_id === nextVolumeId
                    )).length;
                    onChange({
                      ...editor.draft,
                      volume_id: nextVolumeId,
                      parent_faction_id: null,
                      sort_order: (siblingCount + 1) * 10,
                    });
                  }}
                >
                  {level === "core" && <option value="">{t("editor.coreNoVolume")}</option>}
                  {level !== "core" && volumes.map((volume) => <option key={volume.volume_id} value={volume.volume_id}>{volume.title} · {volume.volume_id}</option>)}
                </select>
              </label>
              <label className="grid gap-1.5 text-xs font-medium text-muted md:col-span-2">
                <span>{t("fields.parentFaction")}</span>
                <select
                  name="parent_faction_id"
                  value={editor.draft.parent_faction_id ?? ""}
                  disabled={saving}
                  className={RELATION_INPUT_CLASS}
                  onChange={(event) => onChange({ ...editor.draft, parent_faction_id: event.target.value || null })}
                >
                  <option value="">{t("editor.noParent")}</option>
                  {parentOptions.map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{faction.name} · {faction.faction_id}</option>)}
                </select>
              </label>
            </div>
          </section>
          <FactionEditor
            value={editor.draft}
            onChange={(patch) => onChange({ ...editor.draft, ...patch })}
            t={t}
            showAliases
            disabled={saving}
          />
        </Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
          <Button variant="ghost" size="sm" onPress={onCancel} isDisabled={saving}>
            {t("cancel")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            className="bg-accent text-accent-foreground hover:bg-accent-hover"
            onPress={onSave}
            isDisabled={saving}
          >
            {saving ? t("saving") : t("save")}
          </Button>
        </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </RetainedModalBackdrop>
  );
}

/**
 * 功能：渲染势力名称名册与单一势力详情组成的主从工作台。
 *
 * Args:
 *   props: 已筛选势力、搜索与类别状态、加载状态及档案操作回调。
 *
 * Returns:
 *   名册和详情可独立滚动的响应式势力档案工作台。
 */
function FactionProfilesWorkspace({
  factions,
  allFactions,
  allFactionCount,
  search,
  levelFilter,
  volumes,
  selectedVolumeId,
  invalidVolumeId,
  loading,
  generationLocked,
  actionId,
  onSearchChange,
  onLevelFilterChange,
  onVolumeIdChange,
  onManualCreate,
  onGenerate,
  onEdit,
  onDelete,
  t,
  ...inlineEditing
}: FactionInlineEditingProps & {
  factions: CoreFaction[];
  allFactions: CoreFaction[];
  allFactionCount: number;
  search: string;
  levelFilter: FactionLevelFilter;
  volumes: VolumeReadV2[];
  selectedVolumeId: string;
  invalidVolumeId: string;
  loading: boolean;
  generationLocked: boolean;
  actionId: string;
  onSearchChange: (value: string) => void;
  onLevelFilterChange: (value: FactionLevelFilter) => void;
  onVolumeIdChange: (value: string, replace?: boolean) => void;
  onManualCreate: () => void;
  onGenerate: () => void;
  onEdit: (faction: CoreFaction, section: FactionSection) => void;
  onDelete: (faction: CoreFaction) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const listT = useTranslations("writing.listLayout");
  const listId = useId();
  const [listCollapsed, setListCollapsed] = useState(false);
  const [selectedKey, setSelectedKey] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  useAssistantFocus("faction", (target) => { setSelectedKey(target.id); setMobileDetailOpen(true); onSearchChange(""); onLevelFilterChange("all"); });
  const selected = factions.find((item) => getFactionRenderKey(item) === selectedKey) ?? factions[0];
  const assistantDraft = inlineEditing.editor?.mode === "edit" && inlineEditing.editor.draft.faction_id === selected?.faction_id ? inlineEditing.editor.draft : null;
  useAssistantResource(selected?.faction_id ? { resource_type: "faction", id: selected.faction_id, name: selected.name, version: selected.version, draft: assistantDraft ? { text: JSON.stringify(assistantDraft), fields: Object.keys(assistantDraft), version: assistantDraft.version } : undefined } : null);
  const filtersActive = Boolean(search) || levelFilter !== "all";

  return (
    <div className="@container/master flex min-h-0 flex-1 flex-col gap-3">
      <section className={`shrink-0 border-b border-border pb-3 ${mobileDetailOpen ? "hidden @min-[800px]/master:block" : ""}`}>
        <div data-entity-toolbar className="workspace-toolbar flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div className="grid flex-1 items-end gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_190px_minmax(260px,0.8fr)]">
            <label className="grid gap-1.5 text-xs font-medium text-muted">
              <span>{t("filters.searchLabel")}</span>
              <span className="relative block min-w-0"><input
                type="search" aria-label={t("filters.searchLabel")}
                disabled={inlineEditing.saving}
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={t("filters.searchPlaceholder")}
                className={`${FACTION_FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`}
              />{filtersActive && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={inlineEditing.saving} onClick={() => { onSearchChange(""); onLevelFilterChange("all"); }}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
            </label>
            <div className="grid gap-1.5 text-xs font-medium text-muted">
              <label htmlFor="faction-level-filter">{t("filters.levelType")}</label>
              <select disabled={inlineEditing.saving} id="faction-level-filter" value={levelFilter} onChange={(event) => onLevelFilterChange(event.target.value as FactionLevelFilter)} className={FACTION_FILTER_CLASS}>
                <option value="all">{t("categories.all")}</option>
                {(["core", "volume", "local"] as const).map((level) => (
                  <option key={level} value={level}>{t(`categories.${level}`)}</option>
                ))}
              </select>
            </div>
            <label className="grid gap-1.5 text-xs font-medium text-muted md:col-span-2 xl:col-span-1">
              <span>{t("filters.volumeContext")}</span>
              <select value={selectedVolumeId} onChange={(event) => onVolumeIdChange(event.target.value)} className={FACTION_FILTER_CLASS} disabled={inlineEditing.saving || loading || volumes.length === 0}>
                {volumes.length === 0 && <option value="">{t("filters.noVolumes")}</option>}
                {invalidVolumeId && <option value="">{t("filters.selectVolume")}</option>}
                {volumes.map((volume) => <option key={volume.volume_id} value={volume.volume_id}>{volume.title} · {volume.volume_id}</option>)}
              </select>
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onPress={onManualCreate} isDisabled={loading || inlineEditing.saving || Boolean(inlineEditing.editor)}>{t("manualCreate")}</Button>
            <Button variant="primary" size="sm" onPress={onGenerate} isDisabled={loading || generationLocked}>
              {generationLocked ? t("generating") : t("generate")}
            </Button>
          </div>
        </div>
      </section>

      {invalidVolumeId && (
        <div className="shrink-0 border-y border-amber-500/45 bg-amber-50 px-4 py-4 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" role="alert">
          <p className="font-semibold">{t("filters.invalidVolumeTitle")}</p>
          <p className="mt-1 text-sm leading-6">{t("filters.invalidVolumeDescription")}</p>
          <p className="mt-2 font-mono text-xs">{invalidVolumeId}</p>
        </div>
      )}

      {invalidVolumeId ? null : loading && allFactionCount === 0 ? (
        <div className="border-y border-border px-5 py-14 text-center" role="status">{t("loading")}</div>
      ) : !selected ? (
        <div className="border-y border-dashed border-border px-5 py-14 text-center text-sm text-muted">
          {filtersActive ? t("filters.noResults") : t("emptyFactions")}
        </div>
      ) : (
        <div
          className={`grid min-h-[420px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}
        >
          <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
          <aside data-entity-roster
            id={listId}
            inert={listCollapsed}
            aria-hidden={listCollapsed || undefined}
            className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
            aria-label={t("tabs.profiles")}
            tabIndex={0}
          >
            <ul className="divide-y divide-border">
              {factions.map((faction) => {
                const key = getFactionRenderKey(faction);
                return (
                  <li key={key} className="flex items-stretch">
                    <button
                      id={`faction-roster-${key}`}
                      type="button"
                      disabled={inlineEditing.saving}
                      aria-current={getFactionRenderKey(selected) === key ? "true" : undefined}
                      onClick={() => {
                        setSelectedKey(key);
                        setMobileDetailOpen(true);
                        requestAnimationFrame(() => {
                          const detail = document.getElementById(`faction-detail-${key}`);
                          if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                            detail.focus();
                          }
                        });
                      }}
                      className={`min-w-0 flex-1 px-4 py-3 text-left transition-colors ${getFactionRenderKey(selected) === key ? "bg-selected border-l-2 border-accent" : "hover:bg-surface-secondary/55"}`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-semibold text-foreground">{faction.name}</span>
                        <span className={`size-2 shrink-0 rounded-full ${(faction.active_status ?? "active") === "active" ? "bg-emerald-500" : "bg-muted/45"}`} aria-hidden="true" />
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted">{getFactionLevelLabel(faction, t)} · {faction.faction_type || t("card.typeEmpty")} · {(faction.active_status ?? "active") === "active" ? t("factionStatus.active") : t("factionStatus.inactive")}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
          <SidebarEdgeHandle controls={listId} className="hidden @min-[800px]/master:flex" leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }} rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined} />
          </div>
          <div
            id={`faction-detail-${getFactionRenderKey(selected)}`}
            className={`@container/detail workspace-scrollbar min-w-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0 @min-[800px]/master:overflow-y-auto ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"}`}
            tabIndex={0}
          >
            <button type="button" disabled={inlineEditing.saving} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
              const key = getFactionRenderKey(selected);
              setListCollapsed(false);
              setMobileDetailOpen(false);
              requestAnimationFrame(() => document.getElementById(`faction-roster-${key}`)?.focus());
            }}>
              ← {t("profileActions.back")}
            </button>
            <FactionDetail
              {...inlineEditing}
              allFactions={allFactions}
              volumes={volumes}
              faction={selected}
              busy={Boolean(selected.faction_id && actionId.includes(selected.faction_id))}
              onEdit={(section) => onEdit(selected, section)}
              onDelete={() => onDelete(selected)}
              t={t}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 功能：渲染按身份、战略、组织和剧情作用分区的势力详情。
 *
 * Args:
 *   props: 当前势力、动作状态以及编辑和删除回调。
 *
 * Returns:
 *   不使用卡片嵌套、以章节分隔组织的完整势力档案。
 */
function FactionDetail({ faction, allFactions, volumes, busy, onEdit, onDelete, t, editor, editorError, editorFieldErrors, saving, onEditorChange, onEditorCancel, onEditorSave }: FactionInlineEditingProps & {
  faction: CoreFaction;
  allFactions: CoreFaction[];
  volumes: VolumeReadV2[];
  busy: boolean;
  onEdit: (section: FactionSection) => void;
  onDelete: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const activeEditor = editor?.draft.faction_id === faction.faction_id ? editor : null;
  const parentOptions = allFactions.filter((parent) => !parent.is_deleted
    && (parent.active_status ?? "active") === "active"
    && parent.faction_id !== faction.faction_id
    && ((parent.level_type ?? "core") === "core" || ((faction.level_type ?? "core") !== "core" && parent.volume_id === faction.volume_id)));
  const sections: Array<{ key: FactionSection; values: Array<[string, string | string[]]> }> = [
    { key: "identity", values: [
      [t("fields.name"), faction.name],
      [t("fields.aliases"), faction.alias ?? []],
      [t("fields.factionType"), faction.faction_type],
      [t("fields.levelType"), getFactionLevelLabel(faction, t)],
      [t("fields.volumeId"), volumes.find((volume) => volume.volume_id === faction.volume_id)?.title ?? faction.volume_id ?? t("editor.coreNoVolume")],
      [t("fields.parentFaction"), allFactions.find((parent) => parent.faction_id === faction.parent_faction_id)?.name ?? faction.parent_faction_id ?? t("editor.noParent")],
      [t("fields.influenceScope"), faction.influence_scope],
      [t("fields.isPublic"), faction.is_public ? t("publicStatus.public") : t("publicStatus.hidden")],
    ] },
    { key: "strategy", values: [[t("fields.positioning"), faction.positioning], [t("fields.publicStance"), faction.public_stance], [t("fields.coreGoal"), faction.core_goal], [t("fields.hiddenGoal"), faction.hidden_goal ?? ""]] },
    { key: "structure", values: [[t("fields.organizationStyle"), faction.organization_style], [t("fields.resources"), faction.resources_and_advantages ?? []], [t("fields.values"), faction.core_values ?? []]] },
    { key: "story", values: [[t("fields.conflict"), faction.conflict_with_mainline], [t("fields.expandability"), faction.expandability], [t("fields.tags"), faction.tags ?? []]] },
  ];
  return (
    <article data-entity-detail className="@container/detail min-w-0 px-5 py-4 sm:px-7">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <FactionStatusPill active={(faction.active_status ?? "active") === "active"}>{t(`factionStatus.${(faction.active_status ?? "active") === "active" ? "active" : "inactive"}`)}</FactionStatusPill>
          </div>
          <h3 className="sr-only">{faction.name}</h3>
          <p className="mt-1 break-all font-mono text-xs text-muted">{faction.faction_id}</p>
        </div>
        <Button size="sm" variant="ghost" className="text-danger" onPress={onDelete} isDisabled={busy || saving || Boolean(editor)}>{t("delete")}</Button>
      </header>
      <div className="mt-4 space-y-4">
        {sections.map((section, index) => {
          const editing = activeEditor?.section === section.key;
          return <DocumentSection key={section.key} number={String(index + 1).padStart(2, "0")} title={t(`sections.${section.key}`)} actions={editing ? <>
            <SectionActionButton action="cancel" label={t("cancel")} size="sm" variant="ghost" onPress={onEditorCancel} isDisabled={saving} />
            <SectionActionButton action="save" label={t(saving ? "saving" : "save")} size="sm" variant="primary" onPress={onEditorSave} isDisabled={saving} />
          </> : <SectionEditButton id={`faction-edit-${faction.faction_id}-${section.key}`} onPress={() => onEdit(section.key)} isDisabled={busy || saving || Boolean(editor)} label={t("edit")} />}>
            {editing && activeEditor ? <div id={`faction-inline-${faction.faction_id}`} className="space-y-4">
              {editorError && <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} />}
              <FactionEditor value={activeEditor.draft} section={section.key} fieldErrors={editorFieldErrors} showAliases disabled={saving} onChange={(patch) => onEditorChange({ ...activeEditor.draft, ...patch })} t={t} />
              {section.key === "identity" && <div className="detail-fields grid gap-4">
                <RelationFieldShell label={t("fields.levelType")}><input readOnly aria-readonly="true" value={getFactionLevelLabel(faction, t)} className={RELATION_INPUT_CLASS} /></RelationFieldShell>
                <RelationFieldShell label={t("fields.volumeId")}><input readOnly aria-readonly="true" value={volumes.find((volume) => volume.volume_id === faction.volume_id)?.title ?? faction.volume_id ?? t("editor.coreNoVolume")} className={RELATION_INPUT_CLASS} /></RelationFieldShell>
                <RelationFieldShell label={t("fields.parentFaction")} error={editorFieldErrors.parent_faction_id?.[0] ?? editorFieldErrors["payload.parent_faction_id"]?.[0]} errorId="faction-parent_faction_id-error">
                  <select name="parent_faction_id" disabled={saving} value={activeEditor.draft.parent_faction_id ?? ""} className={RELATION_INPUT_CLASS} aria-invalid={Boolean(editorFieldErrors.parent_faction_id ?? editorFieldErrors["payload.parent_faction_id"]) || undefined} aria-describedby="faction-parent_faction_id-error" onChange={(event) => onEditorChange({ ...activeEditor.draft, parent_faction_id: event.target.value || null })}>
                    <option value="">{t("editor.noParent")}</option>
                    {parentOptions.map((parent) => <option key={parent.faction_id} value={parent.faction_id}>{parent.name}</option>)}
                  </select>
                </RelationFieldShell>
                <RelationFieldShell label={t("fields.activeStatus")}><select name="active_status" disabled={saving} value={activeEditor.draft.active_status ?? "active"} className={RELATION_INPUT_CLASS} onChange={(event) => onEditorChange({ ...activeEditor.draft, active_status: event.target.value as "active" | "inactive" })}><option value="active">{t("factionStatus.active")}</option><option value="inactive">{t("factionStatus.inactive")}</option></select></RelationFieldShell>
              </div>}
            </div> : <dl className="detail-fields grid min-w-0 gap-4">{section.values.map(([label, value]) => <ReadOnlyField key={label} label={label} wide={section.key !== "identity" && !Array.isArray(value)} value={Array.isArray(value) ? value.length ? <TagList values={value} label={label} /> : "—" : value || "—"} />)}</dl>}
          </DocumentSection>;
        })}
      </div>
    </article>
  );
}

/** 获取势力层级的本地化名称，未知层级保留服务端原值。 */
function getFactionLevelLabel(faction: CoreFaction, t: ReturnType<typeof useTranslations>): string {
  const level = faction.level_type || "core";
  if (level === "core" || level === "volume" || level === "local") {
    return t(`categories.${level}`);
  }
  return level;
}

/** 渲染势力详情顶部的层级或状态标签。 */
function FactionStatusPill({ active, children }: { active: boolean; children: ReactNode }) {
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-surface-secondary text-muted"}`}>{children}</span>;
}

const FACTION_FILTER_CLASS = "min-h-10 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";

function TrashPanel({
  factions,
  relations,
  actionId,
  onRestore,
  onHardDelete,
  onRestoreRelation,
  onHardDeleteRelation,
  t,
}: {
  factions: CoreFaction[];
  relations: FactionRelation[];
  actionId: string;
  onRestore: (faction: CoreFaction) => void;
  onHardDelete: (faction: CoreFaction) => void;
  onRestoreRelation: (relation: FactionRelation) => void;
  onHardDeleteRelation: (relation: FactionRelation) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  if (factions.length === 0 && relations.length === 0) {
    return <EmptyBlock text={t("trashEmpty")} />;
  }

  return (
    <div className="space-y-8">
      <section>
        <h3 className="border-b border-border pb-3 text-lg font-semibold text-foreground">{t("trashSections.factions")}</h3>
        {factions.length === 0 ? <p className="py-6 text-sm text-muted">{t("trashSections.emptyFactions")}</p> : <div className="divide-y divide-border">
          {factions.map((faction) => (
            <div key={getFactionRenderKey(faction)} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-foreground">{faction.name}</p>
                <p className="mt-1 truncate text-xs text-muted">{getFactionLevelLabel(faction, t)} · {faction.faction_type || t("card.typeEmpty")} · {faction.faction_id}</p>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onPress={() => onRestore(faction)} isDisabled={actionId === `restore:${faction.faction_id}`}>
                  {actionId === `restore:${faction.faction_id}` ? t("restoring") : t("restore")}
                </Button>
                <Button variant="ghost" size="sm" className="text-danger" onPress={() => onHardDelete(faction)}>{t("hardDelete")}</Button>
              </div>
            </div>
          ))}
        </div>}
      </section>
      <section>
        <h3 className="border-b border-border pb-3 text-lg font-semibold text-foreground">{t("trashSections.relations")}</h3>
        {relations.length === 0 ? <p className="py-6 text-sm text-muted">{t("trashSections.emptyRelations")}</p> : <div className="divide-y divide-border">
          {relations.map((relation) => {
            const connector = isSymmetricFactionRelation(relation.relation_type) ? "↔" : "→";
            return (
              <div key={getRelationRenderKey(relation)} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0"><p className="truncate text-sm font-semibold text-foreground">{relation.source_faction_name ?? relation.source_faction_id} {connector} {relation.target_faction_name ?? relation.target_faction_id}</p><p className="mt-1 font-mono text-xs text-muted">{relation.source_faction_id} {connector} {relation.target_faction_id} · {relation.relation_id}</p></div>
                <div className="flex gap-2"><Button variant="outline" size="sm" onPress={() => onRestoreRelation(relation)} isDisabled={actionId === `relation-restore:${relation.relation_id}`}>{actionId === `relation-restore:${relation.relation_id}` ? t("restoring") : t("restore")}</Button><Button variant="ghost" size="sm" className="text-danger" onPress={() => onHardDeleteRelation(relation)}>{t("hardDelete")}</Button></div>
              </div>
            );
          })}
        </div>}
      </section>
    </div>
  );
}

/**
 * 功能：渲染阵营关系清单与详情组成的响应式主从工作台。
 * Args:
 *   props: 正式关系、类型标签、动作状态、编辑/复制/启停/删除回调与翻译函数。
 * Returns:
 *   桌面双栏、中屏可收起、小屏列表到详情切换的关系工作台。
 */
function FactionRelationsWorkspace({ relations, relationTypeLabels, actionId, onEdit, onCopy, onToggle, onDelete, t, editor, saving, error, fieldErrors, onChange, onCancel, onSave }: {
  editor: RelationEditorState;
  saving: boolean;
  error: string;
  fieldErrors: ApiFieldErrors;
  onChange: (draft: FactionRelationCreateRequestV1) => void;
  onCancel: () => void;
  onSave: () => void;
  relations: FactionRelation[];
  relationTypeLabels: Record<FactionRelationType, string>;
  actionId: string;
  onEdit: (relation: FactionRelation) => void;
  onCopy: (relation: FactionRelation) => void;
  onToggle: (relation: FactionRelation) => void;
  onDelete: (relation: FactionRelation) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const listT = useTranslations("writing.listLayout");
  const listId = useId();
  const [listCollapsed, setListCollapsed] = useState(false);
  const [selectedKey, setSelectedKey] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [relationSearch, setRelationSearch] = useState("");
  const relationQuery = relationSearch.trim().toLocaleLowerCase();
  const filteredRelations = relations.filter((relation) => !relationQuery || [
    relation.source_faction_name,
    relation.source_faction_id,
    relation.target_faction_name,
    relation.target_faction_id,
    relationTypeLabels[relation.relation_type],
  ].some((value) => value?.toLocaleLowerCase().includes(relationQuery)));
  useAssistantFocus("faction_relation", (target) => { setSelectedKey(target.id); setRelationSearch(""); setMobileDetailOpen(true); });
  const selected = filteredRelations.find((item) => getRelationRenderKey(item) === selectedKey) ?? filteredRelations[0];
  useAssistantResource(selected?.relation_id ? { resource_type: "faction_relation", id: selected.relation_id, name: selected.relation_id, version: selected.version, draft: editor?.source?.relation_id === selected.relation_id ? { text: JSON.stringify(editor.draft), fields: Object.keys(editor.draft), version: editor.source.version } : undefined } : null);
  if (!selected) {
    return (
      <div className="border-y border-border py-5">
        <label className="workspace-toolbar grid gap-1.5 text-xs font-medium text-muted">
          <span>{t("relationFilters.searchLabel")}</span>
          <span className="relative block min-w-0"><input type="search" aria-label={t("relationFilters.searchLabel")} disabled={saving} value={relationSearch} onChange={(event) => setRelationSearch(event.target.value)} placeholder={t("relationFilters.searchPlaceholder")} className={`${FACTION_FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`} />{Boolean(relationSearch) && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={saving} onClick={() => setRelationSearch("")}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
        </label>
        <p className="mt-5 border border-dashed border-border px-5 py-10 text-center text-sm text-muted">{t("relationFilters.noResults")}</p>
      </div>
    );
  }
  const sourceName = selected.source_faction_name ?? selected.source_faction_id ?? "—";
  const targetName = selected.target_faction_name ?? selected.target_faction_id ?? "—";
  const busy = saving || Boolean(selected.relation_id && actionId.includes(selected.relation_id));
  const activeEditor = editor?.source?.relation_id === selected.relation_id ? editor : null;

  return (
    <div className="@container/master flex h-full min-h-0 flex-col overflow-hidden border-y border-border bg-surface">
      <label className={`workspace-toolbar shrink-0 border-b border-border px-4 py-3 text-xs font-medium text-muted ${mobileDetailOpen ? "hidden @min-[800px]/master:grid" : "grid"}`}>
        <span>{t("relationFilters.searchLabel")}</span>
        <span className="relative block min-w-0"><input type="search" aria-label={t("relationFilters.searchLabel")} disabled={saving} value={relationSearch} onChange={(event) => setRelationSearch(event.target.value)} placeholder={t("relationFilters.searchPlaceholder")} className={`${FACTION_FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`} />{Boolean(relationSearch) && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("filters.clear")} title={t("filters.clear")} disabled={saving} onClick={() => setRelationSearch("")}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
      </label>
      <div className={`grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] overflow-visible transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:gap-x-2 ${listCollapsed ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
        <div className={`${mobileDetailOpen || listCollapsed ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
        <aside id={listId} inert={listCollapsed} aria-hidden={listCollapsed || undefined} className={`${listCollapsed ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`} aria-label={t("tabs.relations")} tabIndex={0}>
          <ul className="divide-y divide-border">
            {filteredRelations.map((relation) => {
              const key = getRelationRenderKey(relation);
              const symmetric = isSymmetricFactionRelation(relation.relation_type);
              const connector = symmetric ? "↔" : "→";
              return (
                <li key={key}>
                  <button
                    id={`faction-relation-roster-${key}`}
                    type="button"
                    disabled={saving}
                    aria-current={getRelationRenderKey(selected) === key ? "true" : undefined}
                    onClick={() => {
                      setSelectedKey(key);
                      setMobileDetailOpen(true);
                      requestAnimationFrame(() => {
                        const detail = document.getElementById(`faction-relation-detail-${key}`);
                        if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                          detail.focus();
                        }
                      });
                    }}
                    className={`w-full px-4 py-3 text-left transition-colors ${getRelationRenderKey(selected) === key ? "bg-selected border-l-2 border-accent" : "hover:bg-surface-secondary/50"}`}
                  >
                    <span className="block truncate text-sm font-semibold text-foreground">
                      {relation.source_faction_name ?? "—"} <span className="text-accent">{connector}</span> {relation.target_faction_name ?? "—"}
                    </span>
                    <span className="mt-1 block text-xs text-muted">{relationTypeLabels[relation.relation_type]} · {t(`relationDirection.${symmetric ? "symmetric" : "directed"}`)} · {relation.intensity}/5</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>
        <SidebarEdgeHandle controls={listId} className="hidden @min-[800px]/master:flex" leftAction={listCollapsed ? undefined : { label: listT("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }} rightAction={listCollapsed ? { label: listT("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined} />
        </div>
        <article id={`faction-relation-detail-${getRelationRenderKey(selected)}`} className={`@container/detail workspace-scrollbar min-h-0 min-w-0 overflow-y-auto px-5 py-4 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 sm:px-7 ${mobileDetailOpen || listCollapsed ? "block" : "hidden @min-[800px]/master:block"}`} tabIndex={0}>
          <button type="button" disabled={saving} className="mb-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
            const key = getRelationRenderKey(selected);
            setListCollapsed(false);
            setMobileDetailOpen(false);
            requestAnimationFrame(() => document.getElementById(`faction-relation-roster-${key}`)?.focus());
          }}>← {t("relationActions.back")}</button>
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="sr-only">{sourceName} <span className="text-accent">{isSymmetricFactionRelation(selected.relation_type) ? "↔" : "→"}</span> {targetName}</h3>
              <p className="mt-1 text-xs text-muted">{t(`relationDirection.${isSymmetricFactionRelation(selected.relation_type) ? "symmetric" : "directed"}`)} · {selected.is_active ? t("relationStatus.active") : t("relationStatus.inactive")}</p>
            </div>
            <div className="flex flex-wrap gap-2"><Button size="sm" variant="ghost" onPress={() => onCopy(selected)} isDisabled={busy || Boolean(editor)}>{t("relationActions.copy")}</Button><Button size="sm" variant="ghost" onPress={() => onToggle(selected)} isDisabled={busy || Boolean(editor)}>{(selected.user_is_active ?? selected.is_active) ? t("relationActions.deactivate") : t("relationActions.activate")}</Button><Button size="sm" variant="ghost" className="text-danger" onPress={() => onDelete(selected)} isDisabled={busy || Boolean(editor)}>{t("delete")}</Button></div>
          </header>
          <div className="mt-4 space-y-4">
            <DocumentSection number="01" title={t("relationEditor.endpoints")}>
              <dl className="detail-fields grid gap-4">
                <ReadOnlyField label={t("fields.sourceFaction")} value={sourceName} />
                <ReadOnlyField label={t("fields.targetFaction")} value={targetName} />
              </dl>
              <p className="mt-2 break-all font-mono text-xs text-muted"><span>{selected.source_faction_id} {isSymmetricFactionRelation(selected.relation_type) ? "↔" : "→"} {selected.target_faction_id}</span> · <span>{selected.relation_id}</span></p>
            </DocumentSection>
            <DocumentSection number="02" title={t("relationEditor.content")} actions={activeEditor ? <><SectionActionButton action="cancel" label={t("cancel")} size="sm" variant="ghost" onPress={onCancel} isDisabled={saving} /><SectionActionButton action="save" label={t(saving ? "saving" : "save")} size="sm" variant="primary" onPress={onSave} isDisabled={saving} /></> : <SectionEditButton id={`faction-relation-edit-${selected.relation_id}`} onPress={() => onEdit(selected)} isDisabled={busy || Boolean(editor)} label={t("edit")} />}>
              {activeEditor ? <div id={`faction-relation-inline-${selected.relation_id}`} className="space-y-4">
                {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} />}
                <FactionRelationContentFields value={activeEditor.draft} disabled={saving} fieldErrors={fieldErrors} onChange={onChange} t={t} />
              </div> : <div className="space-y-4">
                <dl className="detail-fields grid gap-4"><ReadOnlyField label={t("fields.relationType")} value={relationTypeLabels[selected.relation_type]} /><ReadOnlyField label={t("fields.intensity")} value={`${selected.intensity}/5`} /></dl>
                <dl className="detail-fields grid min-w-0 gap-4">{[[t("fields.currentState"), selected.current_state], [t("fields.coreConflict"), selected.core_conflict], [t("fields.hiddenTension"), selected.hidden_tension ?? ""], [t("fields.possibleChange"), selected.possible_change]].map(([label, value]) => <ReadOnlyField key={label} wide label={label} value={value} />)}</dl>
              </div>}
            </DocumentSection>
          </div>
        </article>
      </div>
    </div>
  );
}

/**
 * 复用关系的内容字段，创建弹窗与正式详情都采用同一组控件。
 * Args:
 *   props: 固定端点之外的草稿内容、字段错误、保存状态与更新回调。
 * Returns:
 *   类型和强度并排，叙述字段占满正文宽度的表单。
 */
function FactionRelationContentFields({ value, disabled, fieldErrors, onChange, t }: {
  value: FactionRelationCreateRequestV1;
  disabled: boolean;
  fieldErrors: ApiFieldErrors;
  onChange: (value: FactionRelationCreateRequestV1) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const fieldError = (name: string) => fieldErrors[name]?.[0] ?? fieldErrors[`payload.${name}`]?.[0];
  const labelKeys = { cold_war: "coldWar", trade_partner: "tradePartner", secret_cooperation: "secretCooperation", historical_enemy: "historicalEnemy" };
  return <div className="space-y-4">
    <div className="detail-fields grid gap-4">
      <RelationFieldShell label={t("fields.relationType")} error={fieldError("relation_type")} errorId="faction-relation-relation_type-error"><select name="relation_type" disabled={disabled} value={value.relation_type} className={RELATION_INPUT_CLASS} aria-invalid={Boolean(fieldError("relation_type")) || undefined} aria-describedby={fieldError("relation_type") ? "faction-relation-relation_type-error" : undefined} onChange={(event) => onChange({ ...value, relation_type: event.target.value as FactionRelationType })}>{RELATION_TYPES.map((type) => <option key={type} value={type}>{t(`relationTypes.${type in labelKeys ? labelKeys[type as keyof typeof labelKeys] : type}`)}</option>)}</select></RelationFieldShell>
      <RelationIntensityField value={value.intensity} disabled={disabled} error={fieldError("intensity")} errorId="faction-relation-intensity-error" label={t("fields.intensity")} inputClassName={RELATION_INPUT_CLASS} onChange={(intensity) => onChange({ ...value, intensity })} />
    </div>
    {(["current_state", "core_conflict", "hidden_tension", "possible_change"] as const).map((field) => <TextArea key={field} name={field} label={t(`fields.${field === "current_state" ? "currentState" : field === "core_conflict" ? "coreConflict" : field === "hidden_tension" ? "hiddenTension" : "possibleChange"}`)} value={value[field]} rows={4} error={fieldError(field)} disabled={disabled} onChange={(text) => onChange({ ...value, [field]: text })} />)}
  </div>;
}

/**
 * 功能：渲染正式阵营关系的创建或编辑弹窗。
 * Args:
 *   props: 编辑模式、势力候选、错误状态、草稿更新及保存取消回调。
 * Returns:
 *   使用 HeroUI v3 Modal 且在编辑态锁定端点的关系表单。
 */
function FactionRelationEditorModal({ editor, factions, saving, error, fieldErrors, onChange, onCancel, onSave, t }: {
  editor: NonNullable<RelationEditorState>;
  factions: CoreFaction[];
  saving: boolean;
  error: string;
  fieldErrors: ApiFieldErrors;
  onChange: (draft: FactionRelationCreateRequestV1) => void;
  onCancel: () => void;
  onSave: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const fieldError = (name: string) => fieldErrors[name]?.[0];
  const describedBy = (name: string) => fieldError(name) ? `faction-relation-${name}-error` : undefined;
  const update = <K extends keyof FactionRelationCreateRequestV1>(name: K, value: FactionRelationCreateRequestV1[K]) => onChange({ ...editor.draft, [name]: value });
  const endpoint = (name: "source_faction_id" | "target_faction_id", label: string, opposite: string) => {
    if (editor.mode === "edit") {
      return <RelationFieldShell label={label} error={fieldError(name)} errorId={`faction-relation-${name}-error`}><input name={name} readOnly aria-readonly="true" aria-invalid={Boolean(fieldError(name)) || undefined} aria-describedby={describedBy(name)} value={`${factions.find((item) => item.faction_id === editor.draft[name])?.name ?? editor.draft[name]} · ${editor.draft[name]}`} className={`${RELATION_INPUT_CLASS} bg-surface-secondary/55`} /></RelationFieldShell>;
    }
    return (
      <RelationFieldShell label={label} error={fieldError(name)} errorId={`faction-relation-${name}-error`}>
        <select name={name} value={editor.draft[name]} onChange={(event) => update(name, event.target.value)} aria-invalid={Boolean(fieldError(name)) || undefined} aria-describedby={describedBy(name)} className={RELATION_INPUT_CLASS}>
          <option value="">{t("relationEditor.selectFaction")}</option>
          {getAvailableRelationFactions(factions).map((faction) => <option key={faction.faction_id} value={faction.faction_id} disabled={faction.faction_id === opposite}>{faction.name} · {faction.faction_id}</option>)}
        </select>
      </RelationFieldShell>
    );
  };
  return (
      <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !saving && onCancel()} variant="blur" isDismissable={!saving}>
        <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4"><Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-5xl">
          <Modal.Header className="border-b border-border px-5 py-4 sm:px-7"><Modal.Heading className="text-lg font-semibold text-foreground">{editor.mode === "create" ? t("relationEditor.createTitle") : t("relationEditor.editTitle")}</Modal.Heading><Modal.CloseTrigger aria-label={t("cancel")} isDisabled={saving} /></Modal.Header>
          <Modal.Body className="px-5 py-6 sm:px-7">
            {error && <RelationEditorErrorSummary message={error} fieldErrors={fieldErrors} className="mb-6" />}
            <div className="space-y-8">
              <section className="space-y-4"><h4 className="text-sm font-semibold text-foreground">{t("relationEditor.endpoints")}</h4><div className="detail-fields grid gap-5">{endpoint("source_faction_id", t("fields.sourceFaction"), editor.draft.target_faction_id)}{endpoint("target_faction_id", t("fields.targetFaction"), editor.draft.source_faction_id)}</div></section>
              <FactionRelationContentFields value={editor.draft} disabled={saving} fieldErrors={fieldErrors} onChange={onChange} t={t} />
            </div>
          </Modal.Body>
          <Modal.Footer className="sticky bottom-0 border-t border-border bg-surface px-5 py-4 sm:px-7"><Button variant="ghost" size="sm" onPress={onCancel} isDisabled={saving}>{t("cancel")}</Button><Button variant="primary" size="sm" onPress={onSave} isDisabled={saving}>{saving ? t("saving") : t("save")}</Button></Modal.Footer>
        </Modal.Dialog></Modal.Container>
      </RetainedModalBackdrop>
  );
}

const RELATION_INPUT_CLASS = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15";

function InfoBlock({ text, tone }: { text: string; tone: "muted" | "warning" }) {
  const className =
    tone === "warning"
      ? "mt-3 border-y border-amber-200 bg-amber-50/70 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200"
      : "mt-3 border-y border-border px-3 py-2 text-sm text-muted";
  return <div className={className}>{text}</div>;
}

function EmptyBlock({ text }: { text: string }) {
  return (
    <div className="border-y border-dashed border-border px-4 py-8 text-center text-sm text-muted">
      {text}
    </div>
  );
}

/**
 * 渲染势力表单中的单行文本输入。
 *
 * Args:
 *   props: 字段标签、当前值、必填与禁用状态、占位提示、外层样式及变更回调。
 *
 * Returns:
 *   带标签和聚焦反馈的单行输入 React 节点。
 */
function TextInput({
  name,
  label,
  value,
  required,
  placeholder,
  disabled,
  className = "",
  onChange,
  error,
}: {
  name?: string;
  error?: string;
  label: string;
  value: string;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className={`grid gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}{required ? " *" : ""}</span>
      <input
        name={name}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? `faction-${name}-error` : undefined}
        type="text"
        value={value}
        required={required}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60"
      />
      {error && <span id={`faction-${name}-error`} className="text-xs text-danger">{error}</span>}
    </label>
  );
}

/**
 * 渲染可按语义配置初始高度的多行文本输入。
 *
 * Args:
 *   props: 字段标签、当前值、占位提示、行数、禁用状态、外层样式及变更回调。
 *
 * Returns:
 *   可纵向调整高度的多行输入 React 节点。
 */
function TextArea({
  name,
  label,
  value,
  placeholder,
  rows = 3,
  disabled,
  className = "",
  onChange,
  error,
}: {
  name?: string;
  error?: string;
  label: string;
  value: string;
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  className?: string;
  onChange: (value: string) => void;
}) {
  return (
    // 不同行数的文本域共处一行时保持顶部对齐，避免 Grid 拉伸内部行距造成较矮文本域下沉。
    <label className={`grid content-start gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}</span>
      <textarea
        name={name}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={error ? `faction-${name}-error` : undefined}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        className="resize-y rounded-xl border border-border bg-background/80 px-3.5 py-3 text-sm leading-6 text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60"
      />
      {error && <span id={`faction-${name}-error`} className="text-xs text-danger">{error}</span>}
    </label>
  );
}

/**
 * 渲染关系端点或枚举字段的原生选择器。
 *
 * Args:
 *   props: 字段标签、当前值、选项、可选标签映射、禁用状态及变更回调。
 *
 * Returns:
 *   使用项目主题样式的下拉选择 React 节点。
 */
function SelectInput({
  label,
  value,
  options,
  optionLabel,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  optionLabel?: (value: string) => string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="text-xs font-medium text-muted">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {optionLabel ? optionLabel(option) : option}
          </option>
        ))}
      </select>
    </label>
  );
}
