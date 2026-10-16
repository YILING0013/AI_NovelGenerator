"use client";

import { downloadExport } from "@/lib/userExport";
import { useAssistantResource } from "@/components/writing/assistant/AssistantContext";
import { useResourceRefresh } from "@/hooks/useResourceRefresh";
import { useCharacterBatchCreation } from "./useCharacterBatchCreation";
import { CHARACTER_PROFILE_FACT_FIELDS } from "./characterFactFields";
import type { CharacterFactBatchCreateV1, CharacterRelationFactBatchCreateV1 } from "@/types/characterFactBatch";

import {
ConfirmActionModal,
focusRelationEditorError,
RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import { TaskFlowDialog,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import {
createLocalCandidateState,
hasCandidateFlow,
isCandidateBasisStale,
localCandidateReducer,
type CandidateBasisV1,
type CandidateGenerationEnvelopeV1,
} from "@/lib/aiCandidate";
import {
apiDelete,
apiGet,
apiPost,
apiPut,
ApiRequestError
} from "@/lib/api";
import type {
CharacterCreateRequestV1,
CharacterFactionBindingActiveRequestV1,
CharacterFactionBindingCandidateV1,
CharacterFactionBindingCreateRequestV1,
CharacterFactionBindingEditableMembershipType,
CharacterFactionBindingPrimaryRequestV1,
CharacterFactionBindingResponseV1,
CharacterFactionBindingUpdateRequestV1,
CharacterImportanceLevel,
CharacterProfileFields,
CharacterRelationFields,
CharacterRelationResponseV1,
CharacterRelationsCandidateEnvelopeV1,
CharacterRelationsGenerationInputV1,
CharacterRelationsResultV1,
CharacterResponseV1,
CharacterRoleType,
CharacterUpdateRequestV1,
CoreCharactersAIConfirmationRequestV1,
CoreCharactersCandidateEnvelopeV1,
CoreCharactersGenerationInputV1,
CoreCharactersResultV1
} from "@/types/character";
import type { CoreFaction,NovelDetail } from "@/types/novel";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
useCallback,
useContext,
useEffect,
useMemo,
useReducer,
useRef,
useState,
type RefObject,
} from "react";
import { RetainedViewActive, RetainedViews } from "@/components/layout/RetainedViews";
import type { ProfileSectionUpdate } from "./views/CharacterDocumentDetails";
import CharacterFactCreateDialog from "./CharacterFactCreateDialog";
import { createEmptyCharacterProfile, REQUIRED_PROFILE_TEXT_FIELDS, profileForCharacterFactDraft, splitCharacterFactCreate } from "./characterFactCreate";
export { splitCharacterFactCreate, profileForCharacterFactDraft } from "./characterFactCreate";
import CharacterFactConfirmationDialog from "./CharacterFactConfirmationDialog";
import { characterFactDraftScope, type CharacterFactDraftV1 } from "./characterFactDrafts";
import { readCharacterFactDrafts, writeCharacterFactDraft } from "./characterFactStorage";
import DraftChip from "@/components/shared/DraftChip";
import { readCharacterFactPreparations, removeCharacterFactPreparation, useCharacterFactPreparationPersistence, type CharacterFactPreparationV1 } from "./characterFactPreparation";
import type { CharacterFactField, CharacterFactPositionV1, CharacterFactReadResultV1 } from "@/types/characterFacts";
import CharacterRelationFactPreparationDialog from "./CharacterRelationFactPreparationDialog";
import CharacterRelationFactConfirmationDialog from "./CharacterRelationFactConfirmationDialog";
import { readCharacterRelationFactPreparations, removeCharacterRelationFactPreparation, useCharacterRelationFactPreparationPersistence, type CharacterRelationFactPreparationV1 } from "./characterRelationFactPreparation";
import { characterRelationFactDraftScope, type CharacterRelationFactDraftV1 } from "./characterRelationFactDrafts";
import { readCharacterRelationFactDrafts, writeCharacterRelationFactDraft } from "./characterRelationFactStorage";
import { loadCharacterFactChapters } from "./characterFactPositions";
import type { HierarchyRecord } from "@/types/hierarchy";
import type { CharacterRelationFactCreateDataV1, CharacterRelationFactReadResultV1 } from "@/types/characterRelationFacts";
import { readCharacterRelationCandidateDrafts, writeCharacterRelationCandidateDraft, handoffCharacterRelationCandidate, reprepareCharacterRelationCandidate, type CharacterRelationCandidateDraft, type CharacterRelationCandidateDraftEntry, type CharacterRelationCandidateCommand } from "./characterRelationCandidateDrafts";
import { readChapterRelationFactHandoff } from "../chapter-records/chapterRecordDrafts";
import CharacterGenerationPreview from "./review/CharacterGenerationPreview";
import {
BindingsView,
isSymmetricCharacterRelation,
ModalLayer,
ProfilesView,
RelationsView,
TrashView,
UnavailablePanel,
WorkspaceHeader,
type CharacterWorkspaceView,
} from "./views/CharacterWorkspaceViews";

interface CharacterCardsWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: CharacterWorkspaceView;
  onViewChange?: (view: CharacterWorkspaceView) => void;
  onFormalFactsChanged?: () => void;
  onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
}

/** 已发出的旧批量请求只用于原样核对；新事实稿不改变它。 */
export interface LegacyCoreCharacterCommand {
  key: string;
  body: CoreCharactersAIConfirmationRequestV1;
  unknown: boolean;
  saved: boolean;
}

/** 功能：保留原批量命令，禁止用新候选重基原请求。Args: 原命令及首次请求。Returns: 原冻结对象或首次副本。 */
export function freezeLegacyCoreCharacterCommand(original: LegacyCoreCharacterCommand | null, body: CoreCharactersAIConfirmationRequestV1, key: string): LegacyCoreCharacterCommand {
  return original ?? { key, body: structuredClone(body), unknown: true, saved: false };
}

interface StableCommand {
  fingerprint: string;
  key: string;
}

type DeleteIntent =
  | { kind: "character"; entity: CharacterResponseV1; hard: boolean }
  | { kind: "relation"; entity: CharacterRelationResponseV1; hard: boolean };

interface BindingDraft {
  character_id: string;
  faction_id: string;
  membership_type: CharacterFactionBindingEditableMembershipType;
  role_title: string;
  public_status: string;
  loyalty_level: string;
  notes: string;
}

type BindingEditorState = {
  mode: "create" | "edit";
  draft: BindingDraft;
  source?: CharacterFactionBindingResponseV1;
} | null;

type BindingConfirmIntent = {
  mode: "active" | "soft" | "restore" | "hard";
  binding: CharacterFactionBindingResponseV1;
} | null;

type BindingPrimaryIntent = {
  target: CharacterFactionBindingResponseV1;
  replaced: CharacterFactionBindingResponseV1[];
} | null;

const CORE_CHARACTERS_ENVELOPE = {
  workflow: "create_characters_by_ai",
  step: "create_core_characters",
  schemaId: "character.core_generation.result",
  schemaVersion: 1,
} as const;

const CHARACTER_RELATIONS_ENVELOPE = {
  workflow: "create_character_relations_by_ai",
  step: "create_character_relations",
  schemaId: "character.relation_generation.result",
  schemaVersion: 1,
} as const;

const BINDING_INPUT_CLASS = "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";


const REQUIRED_RELATION_TEXT_FIELDS: Array<
  keyof Pick<
    CharacterRelationFields,
    "current_state" | "core_conflict" | "hidden_tension" | "possible_change" | "story_value"
  >
> = ["current_state", "core_conflict", "hidden_tension", "possible_change", "story_value"];

/**
 * 创建字段齐全的空角色档案。
 *
 * Args:
 *   无。
 *
 * Returns:
 *   可直接交给角色表单编辑的白名单业务字段。
 */
/**
 * 功能：构造手工角色创建接口的严格请求载荷。
 * Args:
 *   profile: 用户填写的角色业务档案。
 *   isCoreCharacter: 与重要程度独立的核心身份开关。
 * Returns:
 *   包含核心标记、默认排序与扩展字段的创建请求。
 */
export function buildManualCharacterCreateRequest(
  profile: CharacterProfileFields,
  isCoreCharacter: boolean,
): CharacterCreateRequestV1 {
  return {
    ...profile,
    is_core_character: isCoreCharacter,
    sort_order: 0,
    extra: {},
  };
}

/**
 * 功能：构造正式角色普通编辑接口的严格白名单载荷。
 * Args:
 *   character: 提供当前 CAS 版本的正式角色。
 *   profile: 编辑器中允许修改的角色业务档案字段。
 * Returns:
 *   仅含 expected_version 与档案白名单、不含核心标记和审计字段的请求。
 */
export function buildCharacterUpdateRequest(
  character: CharacterResponseV1,
  profile: CharacterProfileFields,
): CharacterUpdateRequestV1 {
  return {
    expected_version: character.version,
    ...profile,
  };
}

/**
 * 功能：从正式角色响应中提取普通更新允许的档案白名单。
 * Args:
 *   character: 已落库的角色响应。
 * Returns:
 *   不含核心标记、ID、状态、版本及审计字段的表单值。
 */
export function characterProfileFromResponse(
  character: CharacterResponseV1,
): CharacterProfileFields {
  const empty = createEmptyCharacterProfile();
  return Object.fromEntries(
    Object.keys(empty).map((key) => [key, structuredClone(character[key as keyof CharacterProfileFields])]),
  ) as unknown as CharacterProfileFields;
}

/**
 * 判断角色表单是否满足后端全部必填文本约束。
 *
 * Args:
 *   value: 当前角色业务字段。
 *
 * Returns:
 *   所有必填文本去除空白后均非空时返回 true。
 */
function isCompleteCharacterProfile(value: CharacterProfileFields): boolean {
  return REQUIRED_PROFILE_TEXT_FIELDS.every((field) => value[field].trim().length > 0);
}

/**
 * 创建字段齐全的空角色关系。
 *
 * Args:
 *   characters: 可作为人工关系端点的 active 未删除角色。
 *
 * Returns:
 *   默认选择前两个不同角色的关系表单值。
 */
function createEmptyRelation(characters: CharacterResponseV1[]): CharacterRelationFields {
  return {
    source_character_id: characters[0]?.character_id ?? "",
    target_character_id: characters[1]?.character_id ?? "",
    relation_type: "ally",
    current_state: "",
    core_conflict: "",
    hidden_tension: "",
    possible_change: "",
    story_value: "",
    intensity: 3,
    is_active: true,
  };
}

/**
 * 功能：从正式人物关系响应中提取编辑器允许的业务字段。
 * Args:
 *   relation: 已落库的人物关系响应。
 * Returns:
 *   可用于内容编辑或复制创建的关系草稿。
 */
export function characterRelationFromResponse(
  relation: CharacterRelationResponseV1,
): CharacterRelationFields {
  return {
    source_character_id: relation.source_character_id,
    target_character_id: relation.target_character_id,
    relation_type: relation.relation_type,
    current_state: relation.current_state,
    core_conflict: relation.core_conflict,
    hidden_tension: relation.hidden_tension,
    possible_change: relation.possible_change,
    story_value: relation.story_value,
    intensity: relation.intensity,
    is_active: relation.user_is_active ?? relation.is_active,
  };
}

/**
 * 判断角色关系是否满足本轮创建与候选编辑的本地必填约束。
 *
 * Args:
 *   value: 当前关系业务字段。
 *
 * Returns:
 *   端点不同、叙述字段完整且强度合法时返回 true。
 */
function isCompleteRelation(value: CharacterRelationFields): boolean {
  return (
    Boolean(value.source_character_id) &&
    Boolean(value.target_character_id) &&
    value.source_character_id !== value.target_character_id &&
    value.intensity >= 1 &&
    value.intensity <= 5 &&
    REQUIRED_RELATION_TEXT_FIELDS.every((field) => value[field].trim().length > 0)
  );
}

/**
 * 判断核心角色的势力绑定候选是否满足后端的可空绑定约束。
 *
 * Args:
 *   value: 当前角色对应的势力绑定候选。
 *
 * Returns:
 *   未绑定时其余字段全空，或已绑定且必填字段完整时返回 true。
 */
function isCompleteBindingCandidate(value: CharacterFactionBindingCandidateV1): boolean {
  if (value.faction_id === null) {
    return (
      value.membership_type === null &&
      value.role_title === null &&
      value.public_status === null &&
      value.loyalty_level === null &&
      value.reason === null
    );
  }

  return (
    value.membership_type !== null &&
    Boolean(value.public_status?.trim()) &&
    value.loyalty_level !== null &&
    value.loyalty_level >= 1 &&
    value.loyalty_level <= 5 &&
    Boolean(value.reason?.trim())
  );
}

/**
 * 生成在相同请求重试期间保持不变的幂等命令键。
 *
 * Args:
 *   cache: 组件生命周期内的命令缓存。
 *   scope: 逻辑操作范围。
 *   payload: 本次请求载荷。
 *
 * Returns:
 *   同范围同载荷复用、载荷变化后自动轮换的合法幂等键。
 */
function getStableCommandKey(
  cache: Map<string, StableCommand>,
  scope: string,
  payload: unknown,
): string {
  const fingerprint = JSON.stringify(payload);
  const cached = cache.get(scope);
  if (cached?.fingerprint === fingerprint) return cached.key;
  const key = `${scope}:${globalThis.crypto.randomUUID()}`;
  cache.set(scope, { fingerprint, key });
  return key;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isCandidateBasis(value: unknown, novelId: string): value is CandidateBasisV1 {
  return (
    hasCandidateFlow(value) &&
    value.novel_id === novelId &&
    typeof value.workflow === "string" &&
    typeof value.step === "string" &&
    typeof value.schema_id === "string" &&
    Number.isInteger(value.schema_version) &&
    typeof value.input_fingerprint === "string" &&
    Array.isArray(value.source_refs) &&
    value.source_refs.every((source) =>
      isRecord(source) &&
      typeof source.resource_type === "string" &&
      typeof source.id === "string" &&
      Number.isInteger(source.version) &&
      Number(source.version) >= 1
    )
  );
}

function isCoreCharactersPayload(value: unknown): value is CoreCharactersResultV1 {
  if (!isRecord(value) || !Array.isArray(value.core_characters) || !Array.isArray(value.binding_candidates)) {
    return false;
  }
  if (value.core_characters.length === 0 || value.core_characters.length !== value.binding_candidates.length) return false;
  const characterRefs = new Set<string>();
  for (const item of value.core_characters) {
    if (
      !isRecord(item) ||
      typeof item.character_ref !== "string" ||
      typeof item.name !== "string" ||
      !REQUIRED_PROFILE_TEXT_FIELDS.every((field) => typeof item[field] === "string") ||
      !["protagonist", "deuteragonist", "antagonist", "supporting", "minor"].includes(String(item.role_type)) ||
      !["core", "major", "supporting", "background"].includes(String(item.importance_level)) ||
      !isStringArray(item.aliases) ||
      !isStringArray(item.strengths) ||
      !isStringArray(item.weaknesses) ||
      !isStringArray(item.abilities) ||
      !isStringArray(item.tags)
    ) return false;
    const profile = item as unknown as CharacterProfileFields;
    if (!isCompleteCharacterProfile(profile) || characterRefs.has(item.character_ref)) return false;
    characterRefs.add(item.character_ref);
  }
  const bindingRefs = new Set<string>();
  for (const item of value.binding_candidates) {
    if (
      !isRecord(item) ||
      typeof item.character_ref !== "string" ||
      (item.faction_id !== null && typeof item.faction_id !== "string") ||
      (item.membership_type !== null && !["primary", "secondary", "covert"].includes(String(item.membership_type))) ||
      (item.role_title !== null && typeof item.role_title !== "string") ||
      (item.public_status !== null && typeof item.public_status !== "string") ||
      (item.loyalty_level !== null && !Number.isInteger(item.loyalty_level)) ||
      (item.reason !== null && typeof item.reason !== "string")
    ) return false;
    const binding = item as unknown as CharacterFactionBindingCandidateV1;
    if (!characterRefs.has(binding.character_ref) || bindingRefs.has(binding.character_ref) || !isCompleteBindingCandidate(binding)) return false;
    bindingRefs.add(binding.character_ref);
  }
  return characterRefs.size === bindingRefs.size;
}

function isCharacterRelationsPayload(value: unknown): value is CharacterRelationsResultV1 {
  return (
    isRecord(value) &&
    Array.isArray(value.relations) &&
    value.relations.length > 0 &&
    value.relations.every(
      (item) =>
        isRecord(item) &&
        typeof item.relation_ref === "string" &&
        typeof item.source_character_id === "string" &&
        typeof item.target_character_id === "string" &&
        ["friend", "romantic", "ally", "rival", "enemy", "parent_of", "mentor_of", "superior_of", "protector_of", "debtor_to"].includes(String(item.relation_type)) &&
        REQUIRED_RELATION_TEXT_FIELDS.every((field) => typeof item[field] === "string") &&
        Number.isInteger(item.intensity) &&
        item.is_active === true &&
        isCompleteRelation(item as unknown as CharacterRelationFields),
    )
  );
}

function parseCandidateEnvelope<TCandidate>(
  value: unknown,
  novelId: string,
  contract: typeof CORE_CHARACTERS_ENVELOPE | typeof CHARACTER_RELATIONS_ENVELOPE,
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

/** 严格解析核心角色普通响应或 SSE done.result 候选信封。 */
export function parseCoreCharactersEnvelope(value: unknown, novelId: string): CoreCharactersCandidateEnvelopeV1 | null {
  return parseCandidateEnvelope(value, novelId, CORE_CHARACTERS_ENVELOPE, isCoreCharactersPayload);
}

/** 严格解析角色关系普通响应或 SSE done.result 候选信封。 */
export function parseCharacterRelationsEnvelope(value: unknown, novelId: string): CharacterRelationsCandidateEnvelopeV1 | null {
  return parseCandidateEnvelope(value, novelId, CHARACTER_RELATIONS_ENVELOPE, isCharacterRelationsPayload);
}

/**
 * 渲染全书级角色档案、核心角色生成审核和关系边摘要工作台。
 *
 * Args:
 *   mode: 写作页创建或编辑模式。
 *   novelId: 已保存小说 ObjectId。
 *   initialView: 从深链接决定的角色、关系、势力归属或回收站视图。
 *   onViewChange: 用户切换角色子视图时同步 URL。
 *   onFormalFactsChanged: 数据保存成功后通知上层刷新准备状态。
 *
 * Returns:
 *   不包含卷级状态与复杂图布局的角色工作台 React 节点。
 */
export default function CharacterCardsWorkspace({
  mode,
  novelId,
  initialView = "profiles",
  onViewChange,
  onFormalFactsChanged,
  onBusyChange,
  beforeLeaveRef,
}: CharacterCardsWorkspaceProps) {
  const t = useTranslations("writing.characters");
  const ft = useTranslations("writing.characterFacts");
  const relationT = useTranslations("writing.characterRelationFacts");
  const recordT = useTranslations("writing.chapterRecords");
  const active = useContext(RetainedViewActive);
  const coreBatch = useCharacterBatchCreation(novelId, "characters");
  const relationBatch = useCharacterBatchCreation(novelId, "relations");
  const restoredBatches = useRef(new Set<string>());
  const relationEpoch = useRef(0);
  const relationContext = useRef({ novelId, active }); relationContext.current = { novelId, active };
  const [view, setView] = useState<CharacterWorkspaceView>(initialView);
  const [characters, setCharacters] = useState<CharacterResponseV1[]>([]);
  const [relations, setRelations] = useState<CharacterRelationResponseV1[]>([]);
  const [trashCharacters, setTrashCharacters] = useState<CharacterResponseV1[]>([]);
  const [trashRelations, setTrashRelations] = useState<CharacterRelationResponseV1[]>([]);
  const [bindings, setBindings] = useState<CharacterFactionBindingResponseV1[]>([]);
  const [factions, setFactions] = useState<CoreFaction[]>([]);
  const [novelVersion, setNovelVersion] = useState<number | null>(null);
  const [loadedNovelId, setLoadedNovelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [basisReady, setBasisReady] = useState(false);
  const [dataError, setDataError] = useState("");
  const [actionError, setActionError] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<CharacterRoleType | "all">("all");
  const [importanceFilter, setImportanceFilter] = useState<CharacterImportanceLevel | "all">("all");
  const [manualPreparation, setManualPreparation] = useState<Extract<CharacterFactPreparationV1, { kind: "create" }> | null>(null);
  const [newFactDraft, setNewFactDraft] = useState<CharacterFactDraftV1 | null>(null);
  const [newFactDrafts, setNewFactDrafts] = useState<CharacterFactDraftV1[]>([]);
  const [newFactBusy, setNewFactBusy] = useState(false);
  const [profileFactBusy, setProfileFactBusy] = useState(false);
  const [leavingFacts, setLeavingFacts] = useState(false);
  const profileLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const createLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const [createPreparations, setCreatePreparations] = useState<Extract<CharacterFactPreparationV1, { kind: "create" }>[]>([]);
  const preparationStore = useCharacterFactPreparationPersistence(novelId ?? "");
  const [relationSession, setRelationSession] = useState<({ preparation: CharacterRelationFactPreparationV1 } | { draft: CharacterRelationFactDraftV1 }) & { epoch: number } | null>(null);
  const [relationPreparations, setRelationPreparations] = useState<CharacterRelationFactPreparationV1[]>([]);
  const [relationFactDrafts, setRelationFactDrafts] = useState<CharacterRelationFactDraftV1[]>([]);
  const [relationChapters, setRelationChapters] = useState<HierarchyRecord[]>([]);
  const [relationBusy, setRelationBusy] = useState(false);
  const [relationDetailBusy, setRelationDetailBusy] = useState(false);
  const relationLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const relationDetailLeaveRef = useRef<(() => Promise<void>) | null>(null);
  const relationPreparationStore = useCharacterRelationFactPreparationPersistence(novelId ?? "");
  const [relationCandidateDrafts, setRelationCandidateDrafts] = useState<CharacterRelationCandidateDraftEntry[]>([]);
  const [relationCandidateEntry, setRelationCandidateEntry] = useState<CharacterRelationCandidateDraftEntry | null>(null);
  const relationCandidateRef = useRef<CharacterRelationCandidateDraftEntry | null>(null);
  const relationCandidateQueue = useRef<Promise<unknown>>(Promise.resolve());
  const relationCandidateUnsaved = useRef(false);
  const [relationLocalError, setRelationLocalError] = useState("");
  const [relationBatchNotice, setRelationBatchNotice] = useState("");
  const [relationExported, setRelationExported] = useState(false);
  const relationPending = useRef(false);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (relationPending.current || relationCandidateUnsaved.current) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);
  const coreFlow = useTaskFlow("create_characters_by_ai");
  const relationFlow = useTaskFlow("create_character_relations_by_ai");
  const [coreDialogOpen, setCoreDialogOpen] = useState(false);
  const [relationDialogOpen, setRelationDialogOpen] = useState(false);
  const [coreCandidateState, dispatchCoreCandidate] = useReducer(
    localCandidateReducer<CoreCharactersResultV1>,
    createLocalCandidateState<CoreCharactersResultV1>(),
  );
  const [relationCandidateState, dispatchRelationCandidate] = useReducer(
    localCandidateReducer<CharacterRelationsResultV1>,
    createLocalCandidateState<CharacterRelationsResultV1>(),
  );
  const [legacyCoreCommand, setLegacyCoreCommand] = useState<LegacyCoreCharacterCommand | null>(null);
  const legacyCoreRef = useRef<LegacyCoreCharacterCommand | null>(null);
  const [coreGenerationInput, setCoreGenerationInput] = useState<CoreCharactersGenerationInputV1 | null>(null);
  const [relationGenerationInput, setRelationGenerationInput] = useState<CharacterRelationsGenerationInputV1 | null>(null);
  const [selectedCoreCharacterRefs, setSelectedCoreCharacterRefs] = useState<string[]>([]);
  const [selectedRelationRefs, setSelectedRelationRefs] = useState<string[]>([]);
  const [selectedCoreIndex, setSelectedCoreIndex] = useState(0);
  const [selectedRelationIndex, setSelectedRelationIndex] = useState(0);
  const [coreConfirmOpen, setCoreConfirmOpen] = useState(false);
  const [inlineSaving, setInlineSaving] = useState(false);
  const [editorError, setEditorError] = useState("");
  const [actionId, setActionId] = useState("");
  const [deleteIntent, setDeleteIntent] = useState<DeleteIntent | null>(null);
  const [bindingEditor, setBindingEditor] = useState<BindingEditorState>(null);
  useAssistantResource(view === "bindings" && bindingEditor?.mode === "edit" && bindingEditor.source ? { resource_type: "character_faction_binding", id: bindingEditor.source.binding_id, name: bindingEditor.source.binding_id, version: bindingEditor.source.version, draft: { text: JSON.stringify(bindingEditor.draft), fields: Object.keys(bindingEditor.draft), version: bindingEditor.source.version } } : null);
  const [bindingConfirmIntent, setBindingConfirmIntent] = useState<BindingConfirmIntent>(null);
  const [bindingPrimaryIntent, setBindingPrimaryIntent] = useState<BindingPrimaryIntent>(null);
  const [bindingError, setBindingError] = useState("");
  const [bindingSaving, setBindingSaving] = useState(false);
  const bindingFormRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (bindingEditor?.mode === "edit" && bindingError) bindingFormRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]")?.focus();
  }, [bindingEditor?.mode, bindingError]);

  const generationAbortRef = useRef<AbortController | null>(null);
  const dataAbortRef = useRef<AbortController | null>(null);
  const novelIdRef = useRef(novelId);
  const commandCacheRef = useRef(new Map<string, StableCommand>());
  novelIdRef.current = novelId;
  useEffect(() => {
    const cached = commandCacheRef.current.get("ai-core-character-confirm");
    if (!cached || legacyCoreRef.current) return;
    try {
      const original = JSON.parse(cached.fingerprint) as CoreCharactersAIConfirmationRequestV1;
      if (original.request_type !== "ai_confirmation" || original.basis.novel_id !== novelId) return;
      const frozen = freezeLegacyCoreCharacterCommand(null, original, cached.key);
      legacyCoreRef.current = frozen; setLegacyCoreCommand(frozen);
    } catch { setActionError(ft("legacyMustResolve")); }
  }, [novelId, coreCandidateState.candidate, ft]);

  const canUseSavedNovel = mode === "edit" && Boolean(novelId);
  const generationError = coreCandidateState.error ?? relationCandidateState.error ?? "";
  const panelGenerationError = coreCandidateState.candidate || relationCandidateState.candidate
    ? ""
    : generationError;
  const activeCharacters = useMemo(
    () => characters.filter((item) => item.status === "active" && !item.is_deleted),
    [characters],
  );
  const coreCharacters = useMemo(
    () => activeCharacters.filter((item) => item.is_core_character),
    [activeCharacters],
  );

  const filteredCharacters = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return characters.filter((character) => {
      if (roleFilter !== "all" && character.role_type !== roleFilter) return false;
      if (importanceFilter !== "all" && character.importance_level !== importanceFilter) return false;
      if (!query) return true;
      return [character.name, ...character.aliases, ...character.tags]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query);
    });
  }, [characters, importanceFilter, roleFilter, search]);

  const characterNames = useMemo(
    () => new Map(characters.map((character) => [character.character_id, character.name])),
    [characters],
  );
  const factionNames = useMemo(
    () =>
      new Map(
        factions.flatMap((faction) =>
          faction.faction_id ? [[faction.faction_id, faction.name] as const] : [],
        ),
      ),
    [factions],
  );
  const relationCountByCharacter = useMemo(() => {
    const result = new Map<string, number>();
    for (const relation of relations) {
      result.set(relation.source_character_id, (result.get(relation.source_character_id) ?? 0) + 1);
      result.set(relation.target_character_id, (result.get(relation.target_character_id) ?? 0) + 1);
    }
    return result;
  }, [relations]);

  const existingActiveProtagonistCount = useMemo(
    () => activeCharacters.filter((character) => character.role_type === "protagonist").length,
    [activeCharacters],
  );
  const currentCandidateVersions = useMemo(() => {
    const versions: Record<string, number> = {};
    if (novelId && novelVersion !== null) versions[`novel:${novelId}`] = novelVersion;
    for (const faction of factions) versions[`faction:${faction.faction_id}`] = faction.version;
    for (const character of characters) versions[`character:${character.character_id}`] = character.version;
    for (const binding of bindings) versions[`character_faction_binding:${binding.binding_id}`] = binding.version;
    for (const relation of relations) versions[`character_relation:${relation.relation_id}`] = relation.version;
    return versions;
  }, [bindings, characters, factions, novelId, novelVersion, relations]);

  useEffect(() => {
    if (!basisReady || loading || coreBatch.busy || relationBatch.busy) return;
    if (
      novelVersion !== null &&
      coreCandidateState.basis &&
      coreCandidateState.status !== "stale" &&
      isCandidateBasisStale(coreCandidateState.basis, currentCandidateVersions)
    ) dispatchCoreCandidate({ type: "mark_stale" });
    if (
      novelVersion !== null &&
      relationCandidateState.basis &&
      relationCandidateState.status !== "stale" &&
      isCandidateBasisStale(relationCandidateState.basis, currentCandidateVersions)
    ) dispatchRelationCandidate({ type: "mark_stale" });
  }, [basisReady, loading, coreBatch.busy, relationBatch.busy, coreCandidateState.basis, coreCandidateState.status, currentCandidateVersions, novelVersion, relationCandidateState.basis, relationCandidateState.status]);

  useEffect(() => {
    if (coreCandidateState.status === "stale") setCoreConfirmOpen(false);
  }, [coreCandidateState.status, relationCandidateState.status]);

  const clearPreview = useCallback(() => {
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    setSelectedCoreCharacterRefs([]);
    setSelectedRelationRefs([]);
    setCoreConfirmOpen(false);
  }, []);

  const loadData = useCallback(async (throwOnFailure = false) => {
    if (!novelId) return;
    setBasisReady(false);
    dataAbortRef.current?.abort();
    const controller = new AbortController();
    const requestNovelId = novelId;
    dataAbortRef.current = controller;
    setLoading(true);
    setDataError("");
    try {
      const [novelResponse, characterResponse] = await Promise.all([
        apiGet<NovelDetail>(`/api/novels/${requestNovelId}`, { signal: controller.signal }),
        apiGet<{ data: CharacterResponseV1[] }>(`/api/characters/novel/${requestNovelId}`, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || novelIdRef.current !== requestNovelId) { if (throwOnFailure) throw new Error(ft("readInterrupted")); return; }
      setNovelVersion(typeof novelResponse.version === "number" ? novelResponse.version : null);
      setCharacters(characterResponse.data);
      setLoadedNovelId(requestNovelId);

      // 辅助数据独立加载；任一集合失败时仍保留已经成功取得的角色主档。
      const [
        relationResult,
        activeBindingResult,
        inactiveBindingResult,
        bindingTrashResult,
        factionResult,
        characterTrashResult,
        relationTrashResult,
      ] = await Promise.allSettled([
        apiGet<{ data: CharacterRelationResponseV1[] }>(`/api/character-relations/novel/${requestNovelId}`, { signal: controller.signal }),
        apiGet<{ data: CharacterFactionBindingResponseV1[] }>(
          `/api/character-faction-bindings/novel/${requestNovelId}?is_active=true`,
          { signal: controller.signal },
        ),
        apiGet<{ data: CharacterFactionBindingResponseV1[] }>(
          `/api/character-faction-bindings/novel/${requestNovelId}?is_active=false`,
          { signal: controller.signal },
        ),
        apiGet<{ data: CharacterFactionBindingResponseV1[] }>(
          `/api/character-faction-bindings/novel/${requestNovelId}/trash`,
          { signal: controller.signal },
        ),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${requestNovelId}/level/core`, { signal: controller.signal }),
        apiGet<{ data: CharacterResponseV1[] }>(`/api/characters/novel/${requestNovelId}/trash`, { signal: controller.signal }),
        apiGet<{ data: CharacterRelationResponseV1[] }>(`/api/character-relations/novel/${requestNovelId}/trash`, { signal: controller.signal }),
      ]);
      if (controller.signal.aborted || novelIdRef.current !== requestNovelId) { if (throwOnFailure) throw new Error(ft("readInterrupted")); return; }
      const optionalErrors: string[] = [];
      if (relationResult.status === "fulfilled") setRelations(relationResult.value.data);
      else optionalErrors.push(t("errors.relationsLoadFailed"));
      const bindingResults = [activeBindingResult, inactiveBindingResult, bindingTrashResult];
      const loadedBindings = bindingResults.flatMap((result) => result.status === "fulfilled" ? result.value.data : []);
      setBindings([...new Map(loadedBindings.map((binding) => [binding.binding_id, binding])).values()]);
      if (bindingResults.some((result) => result.status === "rejected")) optionalErrors.push(t("errors.bindingsLoadFailed"));
      if (factionResult.status === "fulfilled") setFactions(factionResult.value.data);
      else optionalErrors.push(t("errors.factionsLoadFailed"));
      if (characterTrashResult.status === "fulfilled") setTrashCharacters(characterTrashResult.value.data);
      else optionalErrors.push(t("errors.trashLoadFailed"));
      if (relationTrashResult.status === "fulfilled") setTrashRelations(relationTrashResult.value.data);
      else optionalErrors.push(t("errors.trashLoadFailed"));
      setDataError(optionalErrors.join(" "));
      setBasisReady(relationResult.status === "fulfilled" && factionResult.status === "fulfilled" && bindingResults.every((result) => result.status === "fulfilled"));
    } catch (error) {
      if (controller.signal.aborted || novelIdRef.current !== requestNovelId) { if (throwOnFailure) throw new Error(ft("readInterrupted")); return; }
      setDataError(error instanceof Error ? error.message : String(error));
      if (throwOnFailure) throw error;
    } finally {
      if (dataAbortRef.current === controller && novelIdRef.current === requestNovelId) {
        dataAbortRef.current = null;
        setLoading(false);
      }
    }
  }, [novelId, t, ft]);

  const requestedViewRef = useRef(initialView);
  useResourceRefresh(novelId, loadData, active);
  const factBusy = profileFactBusy || newFactBusy || relationBusy || relationDetailBusy || leavingFacts || coreBatch.busy || relationBatch.busy;
  const keepFacts = useCallback(async () => {
    if (legacyCoreRef.current?.unknown || legacyCoreRef.current?.saved) throw new Error(ft("legacyMustResolve"));
    if (profileFactBusy || newFactBusy || relationBusy || relationDetailBusy || relationPending.current) throw new Error(ft("saving"));
    await profileLeaveRef.current?.();
    await createLeaveRef.current?.();
    await relationDetailLeaveRef.current?.();
    await relationLeaveRef.current?.();
    await relationCandidateQueue.current;
  }, [profileFactBusy, newFactBusy, relationBusy, relationDetailBusy, ft]);
  useEffect(() => { onBusyChange?.(factBusy); return () => onBusyChange?.(false); }, [factBusy, onBusyChange]);
  useEffect(() => { if (!beforeLeaveRef) return; beforeLeaveRef.current = keepFacts; return () => { beforeLeaveRef.current = null; }; }, [beforeLeaveRef, keepFacts]);
  const changeView = useCallback(async (nextView: CharacterWorkspaceView) => {
    if (inlineSaving || bindingSaving || factBusy) return;
    setLeavingFacts(true);
    try { await keepFacts(); setView(nextView); onViewChange?.(nextView); }
    catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
    finally { setLeavingFacts(false); }
  }, [onViewChange, inlineSaving, bindingSaving, factBusy, keepFacts]);
  useEffect(() => {
    if (inlineSaving || bindingSaving || factBusy || requestedViewRef.current === initialView) return;
    let current = true;
    void keepFacts().then(() => { if (current) { requestedViewRef.current = initialView; setView(initialView); } }).catch((error) => { if (current) setActionError(error.message); });
    return () => { current = false; };
  }, [initialView, inlineSaving, bindingSaving, factBusy, keepFacts]);
  const refreshNewFactDrafts = useCallback(async () => {
    if (!novelId) return;
    const [rows, pending] = await Promise.allSettled([readCharacterFactDrafts(characterFactDraftScope(novelId)), readCharacterFactPreparations(novelId)]);
    if (novelIdRef.current !== novelId) return;
    if (rows.status === "fulfilled") setNewFactDrafts(rows.value.filter((row) => row.preview.basis.target.kind === "new"));
    if (pending.status === "fulfilled") setCreatePreparations(pending.value.filter((row): row is Extract<CharacterFactPreparationV1, { kind: "create" }> => row.kind === "create"));
    if (rows.status === "rejected") throw rows.reason;
    if (pending.status === "rejected") throw pending.reason;
  }, [novelId]);
  const openCreatePreparation = async (profile: CharacterProfileFields, isCore: boolean, position: CharacterFactPositionV1 | null = null, note = "", fromRejectedDraft = false, fields: CharacterFactField[] = []) => {
    if (!novelId) return;
    if (!fromRejectedDraft) await keepFacts();
    const preparation: Extract<CharacterFactPreparationV1, { kind: "create" }> = { schema_id: "character.fact.preparation", schema_version: 1, kind: "create", key: crypto.randomUUID(), revision: 1, novel_id: novelId, profile: structuredClone(profile), fields: [...fields], is_core_character: isCore, position, note };
    await preparationStore.persist(preparation);
    setManualPreparation(preparation);
  };

  const refreshRelationDrafts = useCallback(async () => {
    if (!novelId) return;
    const [preparations, drafts, candidates] = await Promise.all([
      readCharacterRelationFactPreparations(novelId), readCharacterRelationFactDrafts(characterRelationFactDraftScope(novelId)), readCharacterRelationCandidateDrafts(novelId),
    ]);
    if (novelIdRef.current !== novelId) return;
    setRelationPreparations(preparations.filter((row) => row.kind === "create"));
    setRelationFactDrafts(drafts.filter((row) => row.preview.basis.target.kind === "new"));
    setRelationCandidateDrafts(candidates);
    const held = relationCandidateRef.current;
    const current = candidates.find((row) => row.key === held?.key);
    if (current && !relationCandidateUnsaved.current && JSON.stringify(current.value.candidate) === JSON.stringify(held?.value.candidate)) {
      relationCandidateRef.current = current; setRelationCandidateEntry(current);
    }
  }, [novelId]);
  useEffect(() => { void refreshRelationDrafts().catch((error) => setActionError(error.message)); }, [refreshRelationDrafts]);
  useEffect(() => {
    if (!novelId) return;
    void (async () => {
      let rows = await readCharacterRelationCandidateDrafts(novelId);
      for (const scope of ["manual-relation", "ai-character-relation-confirm"] as const) {
        const cached = commandCacheRef.current.get(scope);
        if (!cached || rows.some((row) => row.value.command?.key === cached.key)) continue;
        const body = JSON.parse(cached.fingerprint);
        const command = { kind: scope === "manual-relation" ? "create" : "bulk", key: cached.key, body, unknown: true } as CharacterRelationCandidateCommand;
        const ai = command.kind === "bulk" && command.body.request_type === "ai_confirmation" ? command.body : null;
        const value: CharacterRelationCandidateDraft = { key: crypto.randomUUID(), revision: 1, candidate: ai?.candidate ?? null, original_candidate: ai?.candidate ?? null, basis: ai?.basis ?? null, generation_input: ai?.generation_input ?? null, members: {}, command };
        const result = await writeCharacterRelationCandidateDraft(novelId, value, null);
        if (!result.written || !result.current) throw new Error(relationT("preparationConflict"));
        rows = [...rows, result.current];
      }
      if (novelIdRef.current === novelId) setRelationCandidateDrafts(rows);
    })().catch((error) => setActionError(error.message));
  }, [novelId, relationT]);
  useEffect(() => {
    if (!active) { relationEpoch.current += 1; setRelationSession(null); }
    return () => { relationEpoch.current += 1; };
  }, [active, novelId]);

  const persistRelationCandidate = async (value: CharacterRelationCandidateDraft, expected: CharacterRelationCandidateDraftEntry | null) => {
    const result = await writeCharacterRelationCandidateDraft(novelId!, value, expected);
    if (!result.written || !result.current) throw new Error(relationT("preparationConflict"));
    if (novelIdRef.current === novelId) { relationCandidateRef.current = result.current; setRelationCandidateEntry(result.current); }
    return result.current;
  };
  const openRelationPreparation = async (value: CharacterRelationFactCreateDataV1) => {
    if (!novelId || relationPending.current) return;
    await keepFacts();
    relationPending.current = true; setRelationBusy(true);
    const request = ++relationEpoch.current;
    try {
      const { source_character_id, target_character_id, relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity } = value;
      const preparation: CharacterRelationFactPreparationV1 = { schema_id: "character_relation.fact.preparation", schema_version: 1, key: crypto.randomUUID(), revision: 1, novel_id: novelId, kind: "create", candidate: { source_character_id, target_character_id, relation_type, core_conflict, hidden_tension, possible_change, story_value, intensity }, position: null, note: "" };
      await relationPreparationStore.persist(preparation);
      const chapters = await loadCharacterFactChapters(novelId);
      if (relationContext.current.novelId === novelId && relationContext.current.active && relationEpoch.current === request) { setRelationChapters(chapters); setRelationSession({ preparation, epoch: request }); }
      await refreshRelationDrafts();
    } finally { if (novelIdRef.current === novelId) { relationPending.current = false; setRelationBusy(false); } }
  };
  const resumeRelationFact = async (value: CharacterRelationFactPreparationV1 | CharacterRelationFactDraftV1) => {
    await keepFacts();
    const request = ++relationEpoch.current;
    const chapters = await loadCharacterFactChapters(novelId!);
    if (relationContext.current.novelId !== novelId || !relationContext.current.active || relationEpoch.current !== request) return;
    setRelationChapters(chapters);
    setRelationSession("preview" in value ? { draft: value, epoch: request } : { preparation: value, epoch: request });
  };
  const resumeRelationCandidate = async (stored: CharacterRelationCandidateDraftEntry) => {
    if (!novelId || factBusy || relationPending.current || relationBatch.command) return;
    // keepFacts 同步检查旧锁后，立即锁住本次切换；旧编辑写完才读取下一份稿。
    const leaving = keepFacts();
    relationPending.current = true; setRelationBusy(true);
    const request = ++relationEpoch.current;
    try {
      await leaving;
      const current = (await readCharacterRelationCandidateDrafts(novelId)).find((row) => row.key === stored.key);
      if (!current) throw new Error(relationT("preparationConflict"));
      if (novelIdRef.current !== novelId || !relationContext.current.active || relationEpoch.current !== request) return;
      relationCandidateRef.current = current; setRelationCandidateEntry(current); setRelationLocalError(""); setRelationExported(false); setRelationBatchNotice("");
      const value = current.value;
      clearPreview();
      if (value.candidate && value.basis) {
        const requestId = relationCandidateState.requestId + 1;
        dispatchRelationCandidate({ type: "generate", requestId });
        dispatchRelationCandidate({ type: "preview", requestId, candidate: value.candidate, basis: value.basis });
        setRelationGenerationInput(value.generation_input); setSelectedRelationRefs(value.candidate.relations.map((row) => row.relation_ref)); setSelectedRelationIndex(0);
      }
    } finally { if (novelIdRef.current === novelId) { relationPending.current = false; setRelationBusy(false); } }
  };
  const adoptRelationAsFactDraft = async () => {
    if (!novelId || relationPending.current) return;
    await keepFacts();
    const original = relationCandidateRef.current;
    if (!original || original.value.command && (original.value.command.unknown !== false || original.value.command.saved !== undefined)) throw new Error(ft("legacyMustResolve"));
    const member = relationCandidateState.candidate?.relations[selectedRelationIndex]?.relation_ref ?? "manual-create";
    relationPending.current = true; setRelationBusy(true);
    const request = ++relationEpoch.current;
    try {
      const chapters = await loadCharacterFactChapters(novelId);
      const current = (await readCharacterRelationCandidateDrafts(novelId)).find((row) => row.key === original.key);
      if (!current || current.value.revision !== original.value.revision) throw new Error(relationT("preparationConflict"));
      const link = current.value.members[member];
      let next: CharacterRelationFactPreparationV1 | CharacterRelationFactDraftV1 | null = null;
      if (link) {
        const linked = await readChapterRelationFactHandoff(novelId, link);
        if (linked.draft) next = linked.draft;
        else if (linked.preparation) next = linked.preparation;
        else if (linked.operation?.saved) setActionError(recordT("saved"));
        else throw new Error(relationT("preparationConflict"));
      } else {
        const handed = await handoffCharacterRelationCandidate(novelId, current, member);
        relationCandidateRef.current = handed.entry; setRelationCandidateEntry(handed.entry); next = handed.preparation;
      }
      if (relationContext.current.novelId === novelId && relationContext.current.active && relationEpoch.current === request && next) {
        setRelationChapters(chapters); setRelationSession("preview" in next ? { draft: next, epoch: request } : { preparation: next, epoch: request });
      }
      await refreshRelationDrafts();
    } finally { if (novelIdRef.current === novelId) { relationPending.current = false; setRelationBusy(false); } }
  };
  const exportRelationCandidate = () => {
    const value = { ...relationCandidateRef.current?.value, candidate: relationCandidateState.candidate ?? relationCandidateRef.current?.value.candidate, basis: relationCandidateState.basis ?? relationCandidateRef.current?.value.basis, generation_input: relationGenerationInput ?? relationCandidateRef.current?.value.generation_input };
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `relationship-candidates-${novelId}.json`; void downloadExport(link); URL.revokeObjectURL(url);
    setRelationExported(true);
  };

  useEffect(() => { void refreshNewFactDrafts().catch((error) => setActionError(error.message)); }, [refreshNewFactDrafts]);

  useEffect(() => () => dataAbortRef.current?.abort(), [novelId]);

  useEffect(() => {
    // 小说切换时立即中止旧请求并丢弃其本地预览，避免结果串入新小说。
    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    legacyCoreRef.current = null; setLegacyCoreCommand(null);
    setSelectedCoreCharacterRefs([]);
    setSelectedRelationRefs([]);
    setCoreConfirmOpen(false);
    setActionError("");
    setDataError("");
    setLoadedNovelId(null);
    setNovelVersion(null);
    setCharacters([]);
    setRelations([]);
    setTrashCharacters([]);
    setTrashRelations([]);
    setBindings([]);
    setFactions([]);
    setManualPreparation(null);
    setNewFactDraft(null);
    setNewFactDrafts([]);
    setCreatePreparations([]);
    relationEpoch.current += 1; setRelationSession(null);
    setRelationPreparations([]); setRelationFactDrafts([]); setRelationCandidateDrafts([]);
    relationCandidateRef.current = null; setRelationCandidateEntry(null); setRelationLocalError(""); setRelationBatchNotice("");
    relationCandidateQueue.current = Promise.resolve(); relationCandidateUnsaved.current = false; relationPending.current = false; setRelationBusy(false);
    setDeleteIntent(null);
    setEditorError("");
    setBindingEditor(null);
    setBindingConfirmIntent(null);
    setBindingPrimaryIntent(null);
    setBindingError("");
    return () => generationAbortRef.current?.abort();
  }, [novelId]);

  const handleCancelGeneration = () => {
    if (legacyCoreRef.current?.unknown || legacyCoreRef.current?.saved) { setActionError(ft("legacyMustResolve")); return; }
    void coreFlow.discard();
    void relationFlow.discard();

    // 面板中的取消动作只中止当前浏览器请求并清理瞬时状态，不再参与参数弹窗的关闭。
    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    setSelectedCoreCharacterRefs([]);
    setSelectedRelationRefs([]);
    setActionError("");
  };

  const handleGenerateCoreCharacters = async (retry: TaskFlowRunMode = false) => {
    if (
      !novelId ||
      generationAbortRef.current ||
      coreCandidateState.candidate ||
      relationCandidateState.candidate ||
      coreCandidateState.status === "generating" ||
      relationCandidateState.status === "generating"
    ) return;

    const requestId = coreCandidateState.requestId + 1;
    const controller = new AbortController();
    generationAbortRef.current = controller;
    dispatchCoreCandidate({ type: "generate", requestId });
    setActionError("");
    // 请求一经发起就退出参数弹窗，后续状态、取消动作和错误统一留在角色卡面板。
    setCoreDialogOpen(false);

    try {
      await loadData(true);
      const generated = await coreFlow.run("/api/llm/generate-core-characters/stream", { novel_id: novelId }, controller.signal, retry);
      if (controller.signal.aborted || generationAbortRef.current !== controller) return;
      const generationInput = generated.generationInput as CoreCharactersGenerationInputV1;
      const envelope: CoreCharactersCandidateEnvelopeV1 | null = parseCoreCharactersEnvelope(generated.result, novelId);

      if (!envelope) throw new Error(t("errors.invalidCorePreview"));
      dispatchCoreCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      setCoreGenerationInput(generationInput);
      setSelectedCoreCharacterRefs(envelope.candidate.core_characters.map((character) => character.character_ref));
      setSelectedCoreIndex(0);
    } catch (error) {
      if (!controller.signal.aborted) {
        dispatchCoreCandidate({
          type: "generation_failed",
          requestId,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    } finally {
      if (generationAbortRef.current === controller) {
        generationAbortRef.current = null;
      }
    }
  };

  const handleGenerateRelations = async (retry: TaskFlowRunMode = false) => {
    if (
      !novelId ||
      generationAbortRef.current ||
      coreCandidateState.candidate ||
      relationCandidateState.candidate ||
      coreCandidateState.status === "generating" ||
      relationCandidateState.status === "generating"
    ) return;

    const requestId = relationCandidateState.requestId + 1;
    const controller = new AbortController();
    generationAbortRef.current = controller;
    dispatchRelationCandidate({ type: "generate", requestId });
    setActionError("");
    // 人物关系生成与角色生成共用同一瞬时交互：参数弹窗关闭，工作台接管运行状态。
    setRelationDialogOpen(false);

    try {
      const generated = await relationFlow.run("/api/llm/generate-character-relations/stream", { novel_id: novelId }, controller.signal, retry);
      if (controller.signal.aborted || generationAbortRef.current !== controller) return;
      const generationInput = generated.generationInput as CharacterRelationsGenerationInputV1;
      const envelope: CharacterRelationsCandidateEnvelopeV1 | null = parseCharacterRelationsEnvelope(generated.result, novelId);

      if (!envelope) throw new Error(t("errors.invalidRelationPreview"));
      dispatchRelationCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      setRelationGenerationInput(generationInput);
      setSelectedRelationRefs(envelope.candidate.relations.map((relation) => relation.relation_ref));
      setSelectedRelationIndex(0);
      const value: CharacterRelationCandidateDraft = { key: crypto.randomUUID(), revision: 1, batch_creation: true, original_candidate: structuredClone(envelope.candidate), candidate: structuredClone(envelope.candidate), basis: structuredClone(envelope.basis), generation_input: structuredClone(generationInput), members: {}, command: null };
      relationCandidateUnsaved.current = true;
      const pending = persistRelationCandidate(value, null);
      relationCandidateQueue.current = pending;
      try { await pending; relationCandidateUnsaved.current = false; setRelationLocalError(""); await refreshRelationDrafts(); }
      catch (error) { setRelationLocalError((error as Error).message); }
    } catch (error) {
      if (!controller.signal.aborted) {
        dispatchRelationCandidate({
          type: "generation_failed",
          requestId,
          message: error instanceof Error ? error.message : String(error),
        });
      }
    } finally {
      if (generationAbortRef.current === controller) {
        generationAbortRef.current = null;
      }
    }
  };

  const openManualRelation = () => {
    const value = createEmptyRelation(activeCharacters);
    void openRelationPreparation(value).catch((error) => setActionError(error.message));
  };

  const saveProfileSection = async (character: CharacterResponseV1, payload: ProfileSectionUpdate) => {
    setInlineSaving(true);
    try {
      const saved = await apiPut<CharacterResponseV1>(`/api/characters/novel/${character.novel_id}/${character.character_id}`, payload);
      if (novelIdRef.current !== character.novel_id) return;
      // 保存回包是已落库的正式资料，附加刷新失败时仍显示新值和新版本。
      setCharacters((current) => current.map((item) => item.character_id === saved.character_id ? saved : item));
      onFormalFactsChanged?.();
      await loadData();
    } finally { setInlineSaving(false); }
  };

  const copyRelationAsNew = (relation: CharacterRelationResponseV1) => {
    // 复制只带入端点和六个设计字段，旧裸值不能自动变成新关系起点。
    void openRelationPreparation(relation).catch((error) => setActionError(error.message));
  };

  const openCreateBinding = (character: CharacterResponseV1) => {
    setBindingEditor({
      mode: "create",
      draft: {
        character_id: character.character_id,
        faction_id: "",
        membership_type: "secondary",
        role_title: "",
        public_status: "",
        loyalty_level: "",
        notes: "",
      },
    });
    setBindingError("");
  };

  const openEditBinding = (binding: CharacterFactionBindingResponseV1) => {
    setBindingEditor({
      mode: "edit",
      source: binding,
      draft: {
        character_id: binding.character_id,
        faction_id: binding.faction_id,
        membership_type: binding.membership_type === "covert" ? "covert" : "secondary",
        role_title: binding.role_title ?? "",
        public_status: binding.public_status ?? "",
        loyalty_level: binding.loyalty_level?.toString() ?? "",
        notes: binding.notes ?? "",
      },
    });
    setBindingError("");
    requestAnimationFrame(() => bindingFormRef.current?.querySelector<HTMLElement>("select, input:not([readonly]), textarea")?.focus());
  };

  const handleSaveBinding = async () => {
    if (!novelId || !bindingEditor || !bindingEditor.draft.faction_id) {
      setBindingError(t("binding.factionRequired"));
      return;
    }
    const draft = bindingEditor.draft;
    const loyaltyLevel = draft.loyalty_level ? Number(draft.loyalty_level) : null;
    if (loyaltyLevel !== null && (!Number.isInteger(loyaltyLevel) || loyaltyLevel < 1 || loyaltyLevel > 5)) {
      setBindingError(t("binding.loyaltyInvalid"));
      return;
    }
    setBindingSaving(true);
    setBindingError("");
    try {
      if (bindingEditor.mode === "create") {
        const request: CharacterFactionBindingCreateRequestV1 = {
          character_id: draft.character_id,
          faction_id: draft.faction_id,
          membership_type: draft.membership_type,
          role_title: draft.role_title.trim() || null,
          public_status: draft.public_status.trim() || null,
          loyalty_level: loyaltyLevel,
          notes: draft.notes.trim() || null,
        };
        const commandScope = `binding-create:${draft.character_id}`;
        const key = getStableCommandKey(commandCacheRef.current, commandScope, request);
        await apiPost(`/api/character-faction-bindings/novel/${novelId}`, request, {
          headers: { "Idempotency-Key": key },
        });
        commandCacheRef.current.delete(commandScope);
      } else if (bindingEditor.source) {
        const request: CharacterFactionBindingUpdateRequestV1 = {
          expected_version: bindingEditor.source.version,
          ...(bindingEditor.source.membership_type === "primary" ? {} : { membership_type: draft.membership_type }),
          role_title: draft.role_title.trim() || null,
          public_status: draft.public_status.trim() || null,
          loyalty_level: loyaltyLevel,
          notes: draft.notes.trim() || null,
        };
        await apiPut(
          `/api/character-faction-bindings/novel/${novelId}/${bindingEditor.source.binding_id}`,
          request,
        );
      }
      setBindingEditor(null);
      if (bindingEditor.source) requestAnimationFrame(() => document.getElementById(`character-binding-edit-${bindingEditor.source?.binding_id}`)?.focus());
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setBindingError(error instanceof Error ? error.message : String(error));
      focusRelationEditorError({});
    } finally {
      setBindingSaving(false);
    }
  };

  const openPrimarySwitch = (target: CharacterFactionBindingResponseV1) => {
    setBindingPrimaryIntent({
      target,
      replaced: bindings.filter((binding) =>
        binding.character_id === target.character_id &&
        binding.binding_id !== target.binding_id &&
        binding.membership_type === "primary" &&
        binding.is_active &&
        !binding.is_deleted,
      ),
    });
    setBindingError("");
  };

  const handleConfirmPrimarySwitch = async () => {
    if (!novelId || !bindingPrimaryIntent) return;
    const { target, replaced } = bindingPrimaryIntent;
    const request: CharacterFactionBindingPrimaryRequestV1 = {
      expected_version: target.version,
      replaced_expected_versions: Object.fromEntries(
        replaced.map((binding) => [binding.binding_id, binding.version]),
      ),
    };
    const commandScope = `binding-primary:${target.binding_id}`;
    const key = getStableCommandKey(commandCacheRef.current, commandScope, request);
    setBindingSaving(true);
    setBindingError("");
    try {
      await apiPut(
        `/api/character-faction-bindings/novel/${novelId}/${target.binding_id}/primary`,
        request,
        { headers: { "Idempotency-Key": key } },
      );
      commandCacheRef.current.delete(commandScope);
      setBindingPrimaryIntent(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setBindingError(error instanceof Error ? error.message : String(error));
      focusRelationEditorError({});
    } finally {
      setBindingSaving(false);
    }
  };

  const handleConfirmBindingAction = async () => {
    if (!novelId || !bindingConfirmIntent) return;
    const { mode: action, binding } = bindingConfirmIntent;
    setBindingSaving(true);
    setBindingError("");
    try {
      if (action === "active") {
        const request: CharacterFactionBindingActiveRequestV1 = {
          expected_version: binding.version,
          is_active: !binding.user_is_active,
        };
        await apiPut(
          `/api/character-faction-bindings/novel/${novelId}/${binding.binding_id}/active`,
          request,
        );
      } else if (action === "restore") {
        await apiPost(
          `/api/character-faction-bindings/novel/${novelId}/${binding.binding_id}/restore`,
          { expected_version: binding.version },
        );
      } else {
        await apiDelete(
          `/api/character-faction-bindings/novel/${novelId}/${binding.binding_id}${action === "hard" ? "/hard" : ""}?expected_version=${binding.version}`,
        );
      }
      setBindingConfirmIntent(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setBindingError(error instanceof Error ? error.message : String(error));
      focusRelationEditorError({});
    } finally {
      setBindingSaving(false);
    }
  };

  const handleToggleCharacterStatus = async (character: CharacterResponseV1) => {
    if (!novelId) return;
    setActionId(`character-status:${character.character_id}`);
    setActionError("");
    try {
      await apiPut(`/api/characters/novel/${novelId}/${character.character_id}/status`, {
        expected_version: character.version,
        status: character.status === "active" ? "inactive" : "active",
      });
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionId("");
    }
  };

  const handleToggleRelationActive = async (relation: CharacterRelationResponseV1) => {
    if (!novelId) return;
    setActionId(`relation-active:${relation.relation_id}`);
    setActionError("");
    try {
      await apiPut(`/api/character-relations/novel/${novelId}/${relation.relation_id}/active`, {
        expected_version: relation.version,
        is_active: !(relation.user_is_active ?? relation.is_active),
      });
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionId("");
    }
  };

  const handleRestoreCharacter = async (character: CharacterResponseV1) => {
    if (!novelId) return;
    setActionId(`restore-character:${character.character_id}`);
    setActionError("");
    try {
      await apiPost(`/api/characters/novel/${novelId}/${character.character_id}/restore`, {
        expected_version: character.version,
      });
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionId("");
    }
  };

  const handleRestoreRelation = async (relation: CharacterRelationResponseV1) => {
    if (!novelId) return;
    setActionId(`restore-relation:${relation.relation_id}`);
    setActionError("");
    try {
      await apiPost(`/api/character-relations/novel/${novelId}/${relation.relation_id}/restore`, {
        expected_version: relation.version,
      });
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionId("");
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteIntent || !novelId) return;
    const id = deleteIntent.kind === "character"
      ? deleteIntent.entity.character_id
      : deleteIntent.entity.relation_id;
    setActionId(`${deleteIntent.hard ? "hard" : "soft"}:${id}`);
    setEditorError("");
    try {
      if (deleteIntent.kind === "character") {
        await apiDelete(
          `/api/characters/novel/${novelId}/${id}${deleteIntent.hard ? "/hard" : ""}?expected_version=${deleteIntent.entity.version}`,
        );
      } else {
        await apiDelete(
          `/api/character-relations/novel/${novelId}/${id}${deleteIntent.hard ? "/hard" : ""}?expected_version=${deleteIntent.entity.version}`,
        );
      }
      setDeleteIntent(null);
      onFormalFactsChanged?.();
      await loadData();
    } catch (error) {
      setEditorError(error instanceof Error ? error.message : String(error));
    } finally {
      setActionId("");
    }
  };

  useEffect(() => {
    const original = coreBatch.command;
    if (!original || restoredBatches.current.has(original.key)) return;
    if (!("core_characters" in original.preview) || !original.body.generation) return;
    restoredBatches.current.add(original.key);
    const requestId = coreCandidateState.requestId + 1;
    dispatchCoreCandidate({ type: "generate", requestId });
    dispatchCoreCandidate({ type: "preview", requestId, candidate: original.preview, basis: original.body.generation.basis });
    setCoreGenerationInput(original.body.generation.generation_input as CoreCharactersGenerationInputV1);
    setSelectedCoreCharacterRefs(original.body.candidates.map((row) => row.candidate_ref));
  }, [coreBatch.command, coreCandidateState.candidate, coreCandidateState.requestId]);
  useEffect(() => {
    const original = relationBatch.command;
    if (!original || restoredBatches.current.has(original.key)) return;
    if (!("relations" in original.preview) || !original.body.generation) return;
    restoredBatches.current.add(original.key);
    const requestId = relationCandidateState.requestId + 1;
    dispatchRelationCandidate({ type: "generate", requestId });
    dispatchRelationCandidate({ type: "preview", requestId, candidate: original.preview, basis: original.body.generation.basis });
    if (original.sourceCandidate) { relationCandidateRef.current = original.sourceCandidate; setRelationCandidateEntry(original.sourceCandidate); }
    setRelationGenerationInput(original.body.generation.generation_input as CharacterRelationsGenerationInputV1);
    setSelectedRelationRefs(original.body.candidates.map((row) => row.candidate_ref));
  }, [relationBatch.command, relationCandidateState.candidate, relationCandidateState.requestId]);

  const handleConfirmCorePreview = async () => {
    if (!novelId || coreCandidateState.status === "confirming") return;
    const original = legacyCoreRef.current;
    // 旧成功和未知请求只核对原冻结 body；当前候选修改不参与 replay。
    if (!original) return;
    setActionError("");
    const command = original;
    dispatchCoreCandidate({ type: "confirm" });
    legacyCoreRef.current = command; setLegacyCoreCommand(command);
    try {
      if (!command.saved) {
        await apiPost(`/api/characters/novel/${novelId}/bulk-core-with-bindings`, command.body, { headers: { "Idempotency-Key": command.key } });
        const saved = { ...command, unknown: false, saved: true }; legacyCoreRef.current = saved; setLegacyCoreCommand(saved);
      }
      await loadData(true);
      commandCacheRef.current.delete("ai-core-character-confirm");
      legacyCoreRef.current = null; setLegacyCoreCommand(null);
      dispatchCoreCandidate({ type: "discard" }); setCoreGenerationInput(null); setSelectedCoreCharacterRefs([]); setCoreConfirmOpen(false); onFormalFactsChanged?.();
    } catch (error) {
      if (!legacyCoreRef.current?.saved) {
        const unknown = Boolean(original?.unknown) || !(error instanceof ApiRequestError && error.status >= 400 && error.status < 500);
        const failed = { ...command, unknown }; legacyCoreRef.current = failed; setLegacyCoreCommand(failed);
      }
      dispatchCoreCandidate({ type: "confirm_failed", message: error instanceof Error ? error.message : String(error) });
    }
  };

  const saveCoreBatch = async () => {
    if (legacyCoreRef.current) { await handleConfirmCorePreview(); return; }
    const preview = coreCandidateState.candidate;
    if (!novelId || !preview || !coreGenerationInput || !coreCandidateState.basis) return;
    try {
      const body: CharacterFactBatchCreateV1 = coreBatch.command?.body as CharacterFactBatchCreateV1 ?? {
        position: { version: 1, intent: "book_start", target_type: "novel", target_id: novelId },
        generation: { basis: coreCandidateState.basis, generation_input: coreGenerationInput }, confirmed: true,
        candidates: preview.core_characters.filter((row) => selectedCoreCharacterRefs.includes(row.character_ref)).map((row) => {
          const fields = CHARACTER_PROFILE_FACT_FIELDS.filter((field) => {
            const value = row[field as keyof typeof row];
            return Array.isArray(value) || typeof value === "string" && value.trim().length > 0;
          });
          const parts = splitCharacterFactCreate(row, true, fields);
          const binding = preview.binding_candidates.find((item) => item.character_ref === row.character_ref);
          const faction = factions.find((item) => item.faction_id === binding?.faction_id);
          if (binding?.faction_id && (!faction || !binding.membership_type)) throw new Error(t("errors.factionsLoadFailed"));
          return { candidate_ref: row.character_ref, profile: parts.candidate, facts: parts.after,
            bindings: binding?.faction_id && faction && binding.membership_type ? [{
              faction_id: binding.faction_id, faction_version: faction.version, membership_type: binding.membership_type,
              role_title: binding.role_title, public_status: binding.public_status, loyalty_level: binding.loyalty_level, notes: binding.reason,
            }] : [] };
        }),
      };
      if (await coreBatch.save(body, preview, () => loadData(true))) {
        dispatchCoreCandidate({ type: "discard" }); setCoreGenerationInput(null);
        setSelectedCoreCharacterRefs([]); onFormalFactsChanged?.();
      }
    } catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
  };

  const saveRelationBatch = async () => {
    if (relationPending.current || relationBatch.busy) return;
    if (relationCandidateRef.current?.value.command) { await handleConfirmRelationPreview(); return; }
    const preview = relationCandidateState.candidate;
    if (!novelId || !preview || !relationGenerationInput || !relationCandidateState.basis) return;
    relationPending.current = true; setRelationBusy(true); setRelationBatchNotice("");
    const request = relationEpoch.current;
    try {
      await relationCandidateQueue.current;
      if (novelIdRef.current !== novelId || !relationContext.current.active || relationEpoch.current !== request) return;
      const source = relationCandidateRef.current;
      if (!relationBatch.command && (!source
          || JSON.stringify(source.value.candidate) !== JSON.stringify(preview)
          || JSON.stringify(source.value.basis) !== JSON.stringify(relationCandidateState.basis)
          || JSON.stringify(source.value.generation_input) !== JSON.stringify(relationGenerationInput))) throw new Error(relationT("preparationConflict"));
      const body: CharacterRelationFactBatchCreateV1 = relationBatch.command?.body as CharacterRelationFactBatchCreateV1 ?? {
        position: { version: 1, intent: "book_start", target_type: "novel", target_id: novelId },
        generation: { basis: relationCandidateState.basis, generation_input: relationGenerationInput }, confirmed: true,
        candidates: preview.relations.filter((row) => selectedRelationRefs.includes(row.relation_ref)).map((row) => ({
          candidate_ref: row.relation_ref, facts: { current_state: row.current_state },
          profile: { source_character_id: row.source_character_id, target_character_id: row.target_character_id,
            relation_type: row.relation_type, core_conflict: row.core_conflict, hidden_tension: row.hidden_tension,
            possible_change: row.possible_change, story_value: row.story_value, intensity: row.intensity },
        })),
      };
      const completed = await relationBatch.save(body, preview, async (saved) => {
        await loadData(true);
        const original = saved.sourceCandidate;
        if (original) {
          const removed = await writeCharacterRelationCandidateDraft(novelId, null, original);
          // 保存已成功；别人改过的源稿留下，不能反复阻塞旧批次清理。
          if (!removed.written && removed.current !== null) {
            const newer = removed.current;
            setRelationCandidateDrafts((rows) => [...rows.filter((row) => row.key !== original.key), newer]);
            setRelationBatchNotice(t("candidate.savedNewerDraftKept"));
          } else setRelationCandidateDrafts((rows) => rows.filter((row) => row.key !== original.key));
          if (relationCandidateRef.current?.key === original.key) { relationCandidateRef.current = null; setRelationCandidateEntry(null); }
        }
      }, source ?? undefined);
      if (completed) {
        dispatchRelationCandidate({ type: "discard" }); setRelationGenerationInput(null);
        setSelectedRelationRefs([]); onFormalFactsChanged?.();
      }
    } catch (error) { setActionError(error instanceof Error ? error.message : String(error)); }
    finally { if (novelIdRef.current === novelId) { relationPending.current = false; setRelationBusy(false); } }
  };

  const handleConfirmRelationPreview = async () => {
    if (!novelId || relationPending.current) return;
    if (relationCandidateRef.current?.value.command?.saved === undefined) await relationCandidateQueue.current;
    const original = relationCandidateRef.current;
    const command = original?.value.command;
    if (!original || !command || command.saved === undefined && Object.keys(original.value.members).length > 0) return;
    relationPending.current = true; setRelationBusy(true); setActionError("");
    let registered = original;
    let saved = command.saved;
    try {
      if (saved === undefined) {
        registered = await persistRelationCandidate({ ...original.value, revision: original.value.revision + 1, command: { ...command, unknown: true } }, original);
        saved = await apiPost(command.kind === "create" ? `/api/character-relations/novel/${novelId}` : `/api/character-relations/novel/${novelId}/bulk-append`, command.body, { headers: { "Idempotency-Key": command.key } });
      }
      const received = { ...registered, value: { ...registered.value, revision: registered.value.revision + 1, command: { ...command, unknown: false, saved } } };
      // HTTP 已成功，先保留首次回执；磁盘失败只补存，不再发送原请求。
      if (novelIdRef.current === novelId && relationCandidateRef.current?.key === original.key) {
        relationCandidateRef.current = received; setRelationCandidateEntry(received); relationCandidateUnsaved.current = true;
      }
      const pending = writeCharacterRelationCandidateDraft(novelId, received.value, registered, { kind: "saved", command }).then((result) => {
        const current = result.current, stored = current?.value.command;
        // 别页先存的同请求成功优先；连同当前成员关联一起恢复，不覆盖首次回执。
        if (!current || current.key !== original.key || current.scope !== original.scope || current.value.key !== original.value.key
          || !result.written && (!stored || stored.saved === undefined || stored.kind !== command.kind || stored.key !== command.key
            || JSON.stringify(stored.body) !== JSON.stringify(command.body))) throw new Error(relationT("preparationConflict"));
        if (novelIdRef.current === novelId && relationCandidateRef.current?.key === original.key) {
          relationCandidateRef.current = current; setRelationCandidateEntry(current); relationCandidateUnsaved.current = false; setRelationLocalError("");
        }
      });
      if (novelIdRef.current === novelId && relationCandidateRef.current?.key === original.key) relationCandidateQueue.current = pending;
      await pending;
      if (novelIdRef.current === novelId && relationContext.current.active) { await loadData(true); await refreshRelationDrafts(); onFormalFactsChanged?.(); }
    } catch (error) {
      // 只有此前明确失败的原请求才可再次记录明确拒绝；未知原请求及 409 始终保留未知。
      if (saved === undefined && command.unknown === false && error instanceof ApiRequestError && error.status >= 400 && error.status < 500 && error.status !== 409) {
        const result = await writeCharacterRelationCandidateDraft(novelId, { ...registered.value, revision: registered.value.revision + 1, command: { ...command, unknown: false } }, registered, { kind: "rejected", previous: original, registered });
        if (result.written && result.current && novelIdRef.current === novelId) { relationCandidateRef.current = result.current; setRelationCandidateEntry(result.current); }
      }
      if (novelIdRef.current === novelId) {
        const message = error instanceof Error ? error.message : String(error);
        setActionError(message);
        if (saved !== undefined && relationCandidateUnsaved.current) setRelationLocalError(message);
      }
    } finally { if (novelIdRef.current === novelId) { relationPending.current = false; setRelationBusy(false); } }
  };

  const handleDiscardPreview = async () => {
    if (coreBatch.command || relationBatch.command || coreBatch.busy || relationBatch.busy) return;
    if (relationCandidateState.candidate || relationCandidateEntry) {
      try { await relationCandidateQueue.current; }
      catch (error) { setRelationLocalError((error as Error).message); return; }
      clearPreview(); relationCandidateRef.current = null; setRelationCandidateEntry(null); await refreshRelationDrafts(); return;
    }
    if (legacyCoreRef.current?.unknown || legacyCoreRef.current?.saved) { setActionError(ft("legacyMustResolve")); return; }
    legacyCoreRef.current = null; setLegacyCoreCommand(null);
    clearPreview();
    setActionError("");
  };

  const openCoreGeneration = () => {
    if (coreCandidateState.candidate || relationCandidateState.candidate || coreCandidateState.status === "generating" || relationCandidateState.status === "generating") return;
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    setActionError("");
    setCoreDialogOpen(true);
  };

  const openRelationGeneration = () => {
    if (coreCandidateState.candidate || relationCandidateState.candidate || coreCandidateState.status === "generating" || relationCandidateState.status === "generating") return;
    dispatchCoreCandidate({ type: "discard" });
    dispatchRelationCandidate({ type: "discard" });
    setCoreGenerationInput(null);
    setRelationGenerationInput(null);
    const coreIds = coreCharacters.slice(0, 100).map((character) => character.character_id);
    if (Object.hasOwn(relationFlow.inputs, "character_ids")) relationFlow.setInputs((current) => ({ ...current, character_ids: coreIds }));
    setActionError("");
    setRelationDialogOpen(true);
  };

  if (!canUseSavedNovel) {
    return <UnavailablePanel title={t("title")} message={t("createModeUnavailable")} />;
  }

  const corePreview = coreCandidateState.candidate;
  const relationPreview = relationCandidateState.candidate;
  const generationKind = coreCandidateState.status === "generating" ? "core_characters" : "character_relations";
  const generationLocked = Boolean(
    corePreview ||
    relationPreview ||
    coreCandidateState.status === "generating" ||
    relationCandidateState.status === "generating" ||
    coreCandidateState.status === "confirming" ||
    relationCandidateState.status === "confirming",
  );

  const bindingForm = bindingEditor ? <div ref={bindingFormRef} className="space-y-4">
          {bindingError && <RelationEditorErrorSummary message={bindingError} className="mb-5" />}
          <div className="grid gap-5 detail-fields">
            <label className="grid gap-2 text-sm">
              <span className="text-xs font-medium text-muted">{t("binding.faction")}</span>
              {bindingEditor.mode === "edit" ? (
                <input readOnly value={`${factionNames.get(bindingEditor.draft.faction_id) ?? bindingEditor.draft.faction_id} · ${bindingEditor.draft.faction_id}`} className={`${BINDING_INPUT_CLASS} bg-surface-secondary/55`} />
              ) : (
                <select
                  value={bindingEditor.draft.faction_id}
                  onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, faction_id: event.target.value } } : current)}
                  disabled={bindingSaving}
                  className={BINDING_INPUT_CLASS}
                >
                  <option value="">{t("binding.selectFaction")}</option>
                  {factions.filter((faction) => !faction.is_deleted && (faction.active_status ?? "active") === "active" && (faction.level_type ?? "core") === "core").map((faction) => <option key={faction.faction_id} value={faction.faction_id}>{faction.name} · {faction.faction_id}</option>)}
                </select>
              )}
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-xs font-medium text-muted">{t("binding.membershipType")}</span>
              {bindingEditor.source?.membership_type === "primary" ? (
                <input readOnly value={t("options.membershipType.primary")} className={`${BINDING_INPUT_CLASS} bg-surface-secondary/55`} />
              ) : (
                <select
                  value={bindingEditor.draft.membership_type}
                  onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, membership_type: event.target.value as CharacterFactionBindingEditableMembershipType } } : current)}
                  disabled={bindingSaving}
                  className={BINDING_INPUT_CLASS}
                >
                  <option value="secondary">{t("options.membershipType.secondary")}</option>
                  <option value="covert">{t("options.membershipType.covert")}</option>
                </select>
              )}
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-xs font-medium text-muted">{t("binding.roleTitle")}</span>
              <input value={bindingEditor.draft.role_title} onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, role_title: event.target.value } } : current)} disabled={bindingSaving} className={BINDING_INPUT_CLASS} />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-xs font-medium text-muted">{t("binding.publicStatus")}</span>
              <input value={bindingEditor.draft.public_status} onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, public_status: event.target.value } } : current)} disabled={bindingSaving} className={BINDING_INPUT_CLASS} />
            </label>
            <label className="grid gap-2 text-sm">
              <span className="text-xs font-medium text-muted">{t("binding.loyaltyLevel")}</span>
              <input type="number" min={1} max={5} value={bindingEditor.draft.loyalty_level} onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, loyalty_level: event.target.value } } : current)} disabled={bindingSaving} className={BINDING_INPUT_CLASS} />
            </label>
            <label className="grid gap-2 text-sm col-span-full">
              <span className="text-xs font-medium text-muted">{t("binding.notes")}</span>
              <textarea rows={4} value={bindingEditor.draft.notes} onChange={(event) => setBindingEditor((current) => current ? { ...current, draft: { ...current.draft, notes: event.target.value } } : current)} disabled={bindingSaving} className={`${BINDING_INPUT_CLASS} min-h-28 resize-y leading-6`} />
            </label>
          </div>
    {bindingEditor.mode === "edit" && <div className="flex flex-wrap gap-2">
      <Button key="save" type="button" variant="primary" size="sm" onPress={() => void handleSaveBinding()} isDisabled={bindingSaving}>{bindingSaving ? t("binding.saving") : t("binding.save")}</Button>
      <Button key="cancel" type="button" variant="ghost" size="sm" onPress={() => { const id = bindingEditor.source?.binding_id; setBindingEditor(null); requestAnimationFrame(() => document.getElementById(`character-binding-edit-${id}`)?.focus()); }} isDisabled={bindingSaving}>{t("actions.cancel")}</Button>
    </div>}
  </div> : null;

  return (
    <section className="flex h-full min-h-0 flex-col bg-background">
      <WorkspaceHeader
        view={view}
        characterCount={characters.length}
        relationCount={relations.length}
        bindingCount={bindings.length}
        trashCount={trashCharacters.length + trashRelations.length}
        loading={loading}
        saving={inlineSaving || bindingSaving || factBusy}
        onViewChange={(next) => void changeView(next)}
        onRefresh={() => void loadData()}
        t={t}
      />

      {relationBatchNotice && <p role="status" className="px-4 py-3 text-sm sm:px-6">{relationBatchNotice}</p>}
      {(dataError || actionError || panelGenerationError) && (
        <div className="border-y border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-300 sm:px-6" role="alert">
          {actionError || panelGenerationError || dataError}
        </div>
      )}

      {(coreCandidateState.status === "generating" || relationCandidateState.status === "generating") && (
        <div
          className="flex shrink-0 flex-wrap items-start gap-3 px-4 py-2 sm:px-6"
        >
          <div className="min-w-0 flex-1">
            <TaskFlowProgress
              flow={generationKind === "core_characters" ? coreFlow : relationFlow}
              running
              label={generationKind === "core_characters"
                ? t("generation.generatingCharacters")
                : t("generation.generatingRelations")}
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className="mt-1 shrink-0"
            onPress={handleCancelGeneration}
          >
            {t("generation.cancelGeneration")}
          </Button>
        </div>
      )}

      <div
        data-entity-body
        className={`flex min-h-0 flex-1 flex-col gap-3 ${corePreview || relationPreview ? "overflow-hidden" : "workspace-scrollbar overflow-y-auto px-4 py-3 sm:px-6"}`}
      >
        {view === "relations" && <div className="flex flex-wrap gap-2 empty:hidden">
          {relationPreparations.filter((row) => !row.origin?.candidateRef).map((row) => <DraftChip key={row.key} label={row.kind === "create" ? `${row.candidate.source_character_id} / ${row.candidate.target_character_id}` : row.relation_id} isDisabled={factBusy || Boolean(relationSession)}
            onResume={() => void resumeRelationFact(row).catch((error) => setActionError(error.message))}
            onDiscard={!row.origin ? async () => { await relationPreparationStore.queue.current; await removeCharacterRelationFactPreparation(novelId!, row.key, row.revision); await refreshRelationDrafts(); } : undefined} />)}
          {relationFactDrafts.filter((row) => !row.origin?.candidateRef).map((row) => <DraftChip key={row.key} label={row.positionLabel} status={row.command?.saved ? "saved" : row.command ? row.command.unknown ? "pending" : "rejected" : "draft"} isDisabled={factBusy || Boolean(relationSession)}
            onResume={() => void resumeRelationFact(row).catch((error) => setActionError(error.message))}
            onDiscard={!row.origin && (!row.command || row.command.saved && row.command.readbackDone) ? async () => { await writeCharacterRelationFactDraft(characterRelationFactDraftScope(novelId!), row, row.revision, true); await refreshRelationDrafts(); } : undefined} />)}
          {relationCandidateDrafts.map((row, index) => row.key === relationCandidateEntry?.key ? null : <DraftChip key={row.key} label={`${t("candidate.relationTitle")} ${index + 1}`} status={row.value.command?.saved !== undefined ? "saved" : row.value.command ? row.value.command.unknown !== false ? "pending" : "rejected" : "draft"}
            isDisabled={factBusy || Boolean(relationBatch.command) || relationBatch.busy || relationCandidateEntry?.key === row.key}
            onResume={() => void resumeRelationCandidate(row).catch((error) => setActionError(error.message))}
            onDiscard={!row.value.command && Object.keys(row.value.members).length === 0 ? async () => {
              const result = await writeCharacterRelationCandidateDraft(novelId!, null, row);
              if (!result.written) throw new Error(relationT("preparationConflict"));
              await refreshRelationDrafts();
            } : undefined} />)}
        </div>}
        {relationCandidateEntry?.value.command && !relationPreview && <div className="grid gap-3 border-y border-border py-4">
          <p role="status">{recordT(relationCandidateEntry.value.command.saved !== undefined ? "saved" : relationCandidateEntry.value.command.unknown !== false ? "unknown" : "rejected")}</p>
          <div className="flex flex-wrap gap-2"><Button variant="outline" isDisabled={factBusy || Object.keys(relationCandidateEntry.value.members).length > 0} onPress={() => void handleConfirmRelationPreview().catch((error) => setActionError(error.message))}>{t("candidate.retryRelationOriginal")}</Button><Button variant="ghost" onPress={exportRelationCandidate}>{t("candidate.exportOriginal")}</Button>
            {relationCandidateEntry.value.command.unknown === false && relationCandidateEntry.value.command.saved === undefined && <Button variant="primary" isDisabled={factBusy || Boolean(relationLocalError)} onPress={() => void adoptRelationAsFactDraft().catch((error) => setActionError(error.message))}>{t("candidate.adoptRelationFactStart")}</Button>}
            <Button variant="ghost" isDisabled={factBusy} onPress={() => void handleDiscardPreview()}>{ft("closeKeep")}</Button></div>
        </div>}
        {relationLocalError && <RelationEditorErrorSummary message={relationLocalError} />}
        {relationLocalError && relationExported && <Button variant="outline" isDisabled={factBusy} onPress={() => { clearPreview(); relationCandidateRef.current = null; setRelationCandidateEntry(null); setRelationLocalError(""); relationCandidateQueue.current = Promise.resolve(); relationCandidateUnsaved.current = false; void refreshRelationDrafts().catch((error) => setActionError(error.message)); }}>{relationT("closeAfterSavingCopy")}</Button>}
        {view === "profiles" && (createPreparations.length > 0 || newFactDrafts.length > 0) && <div className="flex flex-wrap items-center gap-2" aria-label={ft("retainedDrafts")}>
          {createPreparations.map((preparation) => <DraftChip key={preparation.key} label={preparation.profile.name || t("manualCharacter.title")} isDisabled={factBusy || Boolean(manualPreparation || newFactDraft)}
            onResume={() => void keepFacts().then(() => setManualPreparation(preparation)).catch((error) => setActionError(error.message))}
            onDiscard={async () => { await preparationStore.queue.current; await removeCharacterFactPreparation(novelId!, preparation.key, preparation.revision); await refreshNewFactDrafts(); }} />)}
          {newFactDrafts.map((draft) => <DraftChip key={draft.key} label={`${draft.preview.basis.target.kind === "new" ? draft.preview.basis.target.candidate.name : ""} · ${draft.positionLabel}`} status={draft.command?.saved ? "saved" : draft.command ? draft.command.unknown ? "pending" : "rejected" : "draft"} isDisabled={factBusy || Boolean(manualPreparation || newFactDraft)}
            onResume={() => void keepFacts().then(() => setNewFactDraft(draft)).catch((error) => setActionError(error.message))}
            onDiscard={!draft.command || draft.command.saved && draft.command.readbackDone ? async () => { await writeCharacterFactDraft(characterFactDraftScope(novelId!), draft, draft.revision, true); await refreshNewFactDrafts(); } : undefined} />)}
        </div>}
        {coreCandidateState.status !== "generating" && relationCandidateState.status !== "generating" && (
          <div className={corePreview || relationPreview ? "shrink-0 px-4 pt-5 empty:hidden sm:px-6" : "empty:hidden"}>
            {view === "profiles" ? <TaskFlowProgress key="profiles" flow={coreFlow} failed={coreCandidateState.status === "error" && coreCandidateState.candidate === null} onRetry={() => void handleGenerateCoreCharacters(true)} onContinue={(additionalRounds) => void handleGenerateCoreCharacters({ continuation: true, additionalRounds })} onDiscard={handleCancelGeneration} />
              : view === "relations" ? <TaskFlowProgress key="relations" flow={relationFlow} failed={relationCandidateState.status === "error" && relationCandidateState.candidate === null} onRetry={() => void handleGenerateRelations(true)} onContinue={(additionalRounds) => void handleGenerateRelations({ continuation: true, additionalRounds })} onDiscard={handleCancelGeneration} />
              : null}
          </div>
        )}
        {corePreview || relationPreview ? (
          <div
            id={`character-workspace-${view}-panel`}
            role="tabpanel"
            aria-labelledby={`character-workspace-${view}-tab`}
            className="min-h-0 flex-1"
          >
          <CharacterGenerationPreview
            corePreview={corePreview}
            relationPreview={relationPreview}
            selectedCoreCharacterRefs={selectedCoreCharacterRefs}
            selectedRelationRefs={selectedRelationRefs}
            relationCharacterIds={relationGenerationInput?.character_ids ?? []}
            selectedCoreIndex={selectedCoreIndex}
            selectedRelationIndex={selectedRelationIndex}
            characters={relationPreview && relationGenerationInput
              ? coreCharacters.filter((character) => relationGenerationInput.character_ids.includes(character.character_id))
              : coreCharacters}
            factions={factions}
            bindings={bindings}
            status={coreBatch.busy || relationBatch.busy ? "confirming" : corePreview ? coreCandidateState.status : relationCandidateState.status}
            error={(corePreview ? coreBatch.error || coreCandidateState.error : relationBatch.error || relationLocalError || relationCandidateState.error) ?? ""}
            hasRequiredProtagonist={Boolean(
              existingActiveProtagonistCount > 0 ||
              corePreview?.core_characters.some((character) =>
                selectedCoreCharacterRefs.includes(character.character_ref) && character.role_type === "protagonist"
              )
            )}
            onSelectCore={setSelectedCoreIndex}
            onSelectRelation={setSelectedRelationIndex}
            onToggleCore={(characterRef) => setSelectedCoreCharacterRefs((current) =>
              current.includes(characterRef)
                ? current.filter((item) => item !== characterRef)
                : [...current, characterRef]
            )}
            onCoreChange={(index, value) => {
              if (!corePreview) return;
              const data = structuredClone(corePreview);
              data.core_characters[index] = value;
              dispatchCoreCandidate({ type: "edit", candidate: data });
            }}
            onBindingChange={(characterRef, value) => {
              if (!corePreview) return;
              const data = structuredClone(corePreview);
              const index = data.binding_candidates.findIndex((item) => item.character_ref === characterRef);
              if (index >= 0) {
                data.binding_candidates[index] = value;
              }
              dispatchCoreCandidate({ type: "edit", candidate: data });
            }}
            onRelationChange={(index, value) => {
              if (!relationPreview || relationPending.current || relationBatch.command || relationBatch.busy) return;
              const data = structuredClone(relationPreview);
              if (relationCandidateRef.current?.value.members[value.relation_ref] || relationCandidateRef.current?.value.command || relationLocalError) return;
              data.relations[index] = value;
              dispatchRelationCandidate({ type: "edit", candidate: data });
              relationCandidateUnsaved.current = true;
              const write = relationCandidateQueue.current.then(async () => {
                const current = relationCandidateRef.current;
                if (!current) throw new Error(relationT("preparationConflict"));
                await persistRelationCandidate({ ...current.value, revision: current.value.revision + 1, candidate: data }, current);
              });
              relationCandidateQueue.current = write;
              void write.then(() => { if (relationCandidateQueue.current === write) relationCandidateUnsaved.current = false; }, (error) => { if (novelIdRef.current === novelId) setRelationLocalError(error.message); });
            }}
            onToggleRelation={(relationRef) => setSelectedRelationRefs((current) =>
              current.includes(relationRef)
                ? current.filter((item) => item !== relationRef)
                : [...current, relationRef]
            )}
            onExportCore={() => {
              const content = { candidate: coreCandidateState.candidate, basis: coreCandidateState.basis, generation_input: coreGenerationInput, command: legacyCoreRef.current };
              const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], { type: "application/json" }));
              const link = document.createElement("a"); link.href = url; link.download = `character-candidates-${novelId}.json`; void downloadExport(link); URL.revokeObjectURL(url);
            }}
            coreAdoptionBlocked={Boolean(coreBatch.command || legacyCoreCommand?.unknown || legacyCoreCommand?.saved || factBusy)}
            hasLegacyCoreCommand={Boolean(legacyCoreCommand || coreBatch.command)}
            onAdoptRelation={relationCandidateEntry && !relationCandidateEntry.value.batch_creation ? () => void adoptRelationAsFactDraft().catch((error) => setActionError(error.message)) : undefined}
            onExportRelation={exportRelationCandidate}
            relationRequestBusy={relationBusy}
            relationAdoptionBlocked={factBusy || Boolean(relationLocalError) || !relationCandidateEntry || Boolean(relationCandidateEntry.value.command && (relationCandidateEntry.value.command.unknown !== false || relationCandidateEntry.value.command.saved !== undefined))}
            relationEditingBlocked={factBusy || Boolean(relationLocalError) || Boolean(relationBatch.command || relationCandidateEntry?.value.command)}
            preparedRelationRefs={Object.keys(relationCandidateEntry?.value.members ?? {})}
            hasLegacyRelationCommand={Boolean(relationBatch.command) || Boolean(relationCandidateEntry?.value.command) && Object.keys(relationCandidateEntry?.value.members ?? {}).length === 0}
            onConfirm={() => void (corePreview ? saveCoreBatch() : saveRelationBatch())}
            discardBlocked={Boolean(relationBatch.command)}
            onRevise={corePreview ? coreBatch.command?.rejected ? () => void coreBatch.revise() : undefined : relationBatch.command?.rejected ? () => void relationBatch.revise() : undefined}
            onDiscard={handleDiscardPreview}
            t={t}
          />
          </div>
        ) : null}
        <RetainedViews key={novelId} activeKey={corePreview || relationPreview ? null : view}>{view === "profiles" ? (
          <ProfilesView
            key={novelId}
            allCharacters={loadedNovelId === novelId ? characters : []}
            characters={loadedNovelId === novelId ? filteredCharacters : []}
            allCharacterCount={loadedNovelId === novelId ? characters.length : 0}
            search={search}
            roleFilter={roleFilter}
            importanceFilter={importanceFilter}
            relationCountByCharacter={relationCountByCharacter}
            loading={loading}
            generationLocked={generationLocked}
            actionId={actionId}
            onSearchChange={setSearch}
            onRoleFilterChange={setRoleFilter}
            onImportanceFilterChange={setImportanceFilter}
            onManualCreate={() => void openCreatePreparation(createEmptyCharacterProfile(), false).catch((error) => setActionError(error.message))}
            onGenerate={() => void keepFacts().then(openCoreGeneration).catch((error) => setActionError(error.message))}
            onFactsChanged={async () => { await loadData(true); onFormalFactsChanged?.(); }}
            onBusyChange={setProfileFactBusy}
            beforeLeaveRef={profileLeaveRef}
            saving={inlineSaving || bindingSaving}
            onSave={saveProfileSection}
            onToggleStatus={(character) => void handleToggleCharacterStatus(character)}
            onDelete={(character) => {
              setEditorError("");
              setDeleteIntent({ kind: "character", entity: character, hard: false });
            }}
            t={t}
          />
        ) : view === "relations" ? (
          <RelationsView
            relations={relations}
            activeCharacters={activeCharacters}
            coreCharacters={coreCharacters}
            characterNames={characterNames}
            loading={loading}
            generationLocked={generationLocked}
            actionId={actionId}
            onManualCreate={openManualRelation}
            onGenerate={openRelationGeneration}
            saving={inlineSaving || bindingSaving}
            onRelationChanged={(saved) => { setRelations((rows) => rows.map((row) => row.relation_id === saved.relation_id ? saved : row)); onFormalFactsChanged?.(); }}
            onFactsChanged={async () => { await loadData(true); onFormalFactsChanged?.(); }}
            onBusyChange={setRelationDetailBusy}
            beforeLeaveRef={relationDetailLeaveRef}
            onCopy={copyRelationAsNew}
            onToggleActive={(relation) => void handleToggleRelationActive(relation)}
            onDelete={(relation) => {
              setEditorError("");
              setDeleteIntent({ kind: "relation", entity: relation, hard: false });
            }}
            t={t}
          />
        ) : view === "bindings" ? (
          <BindingsView
            characters={characters}
            bindings={bindings}
            factions={factions}
            loading={loading}
            actionId={actionId}
            onCreate={openCreateBinding}
            onEdit={openEditBinding}
            saving={bindingSaving || inlineSaving}
            editingBindingId={bindingEditor?.mode === "edit" ? bindingEditor.source?.binding_id : undefined}
            editor={bindingEditor?.mode === "edit" ? bindingForm : undefined}
            onToggleActive={(binding) => {
              setBindingError("");
              setBindingConfirmIntent({ mode: "active", binding });
            }}
            onMakePrimary={openPrimarySwitch}
            onDelete={(binding) => {
              setBindingError("");
              setBindingConfirmIntent({ mode: "soft", binding });
            }}
            onRestore={(binding) => {
              setBindingError("");
              setBindingConfirmIntent({ mode: "restore", binding });
            }}
            onHardDelete={(binding) => {
              setBindingError("");
              setBindingConfirmIntent({ mode: "hard", binding });
            }}
            t={t}
          />
        ) : (
          <TrashView
            characters={trashCharacters}
            relations={trashRelations}
            actionId={actionId}
            onRestoreCharacter={(character) => void handleRestoreCharacter(character)}
            onHardDeleteCharacter={(character) => {
              setEditorError("");
              setDeleteIntent({ kind: "character", entity: character, hard: true });
            }}
            onRestoreRelation={(relation) => void handleRestoreRelation(relation)}
            onHardDeleteRelation={(relation) => {
              setEditorError("");
              setDeleteIntent({ kind: "relation", entity: relation, hard: true });
            }}
            t={t}
          />
        )}</RetainedViews>
      </div>

      {newFactDraft && novelId && <CharacterFactConfirmationDialog key={newFactDraft.key} novelId={novelId} initialDraft={newFactDraft} onBusy={setNewFactBusy} beforeLeaveRef={createLeaveRef} onRepreview={async (previous) => {
        const body = previous.command?.body;
        const basis = body?.basis ?? previous.preview.basis;
        if (basis.operation !== "create") throw new Error(ft("wrongScope"));
        const after = body && body.operation !== "void" ? body.after : previous.after;
        await openCreatePreparation(profileForCharacterFactDraft({ ...createEmptyCharacterProfile(), ...basis.target.candidate, ...structuredClone(after) }), Boolean(basis.target.candidate.is_core_character), basis.position, basis.source.kind === "author" ? basis.source.note : "", true, basis.fields);
      }} onClose={() => { setNewFactDraft(null); void refreshNewFactDrafts().catch((error) => setActionError(error.message)); }} onReadback={async (receipt) => {
        await apiPost<CharacterFactReadResultV1>(`/api/character-facts/novel/${novelId}/read`, { character_ids: [receipt.character_id], position: null });
        await loadData(true); onFormalFactsChanged?.();
      }} />}
      {manualPreparation && novelId && <CharacterFactCreateDialog key={manualPreparation.key} novelId={novelId} initialPreparation={manualPreparation} onBusy={setNewFactBusy} beforeLeaveRef={createLeaveRef} onClose={() => { setManualPreparation(null); void refreshNewFactDrafts().catch((error) => setActionError(error.message)); }} onPreviewed={(draft) => { setManualPreparation(null); setNewFactDraft(draft); void refreshNewFactDrafts().catch((error) => setActionError(error.message)); }} />}

      {relationSession && "preparation" in relationSession && <CharacterRelationFactPreparationDialog key={relationSession.preparation.key} initialPreparation={relationSession.preparation} chapters={relationChapters} characters={activeCharacters} onBusy={setRelationBusy} beforeLeaveRef={relationLeaveRef} onPrepared={(draft) => {
        if (relationEpoch.current !== relationSession.epoch || relationContext.current.novelId !== novelId) return;
        if (!relationContext.current.active) { setRelationSession(null); return; }
        setRelationSession({ draft, epoch: relationSession.epoch });
        void refreshRelationDrafts().catch((error) => setActionError(error.message));
      }} onClose={() => {
        if (relationEpoch.current !== relationSession.epoch) return;
        relationEpoch.current += 1; setRelationSession(null); void refreshRelationDrafts().catch((error) => setActionError(error.message));
      }} />}
      {relationSession && "draft" in relationSession && <CharacterRelationFactConfirmationDialog key={relationSession.draft.key} novelId={novelId!} initialDraft={relationSession.draft} onBusy={setRelationBusy} beforeLeaveRef={relationLeaveRef} onReadback={async (receipt) => {
        const read = await apiPost<CharacterRelationFactReadResultV1>(`/api/character-relation-facts/novel/${novelId}/read`, { relation_ids: [receipt.relation_id], position: null });
        if (read.novel_id !== novelId || !read.relations.some((row) => row.entity_id === receipt.entity_id && row.relation_id === receipt.relation_id)) throw new Error(relationT("missingRelation"));
        if (relationEpoch.current === relationSession.epoch && relationContext.current.active && relationContext.current.novelId === novelId) { await loadData(true); onFormalFactsChanged?.(); }
      }} onRepreview={async (previous) => {
        const preparation = await reprepareCharacterRelationCandidate(novelId!, previous);
        if (relationEpoch.current !== relationSession.epoch || relationContext.current.novelId !== novelId) return;
        relationEpoch.current += 1; setRelationSession(relationContext.current.active ? { preparation, epoch: relationEpoch.current } : null);
        await refreshRelationDrafts();
      }} onClose={() => {
        if (relationEpoch.current !== relationSession.epoch) return;
        relationEpoch.current += 1; setRelationSession(null); void refreshRelationDrafts().catch((error) => setActionError(error.message));
      }} />}

      {bindingEditor?.mode === "create" && (
        <ModalLayer
          title={bindingEditor.mode === "create" ? t("binding.createTitle") : t("binding.editTitle")}
          busy={bindingSaving}
          onClose={() => setBindingEditor(null)}
          footer={(
            <>
              <Button variant="ghost" size="sm" onPress={() => setBindingEditor(null)} isDisabled={bindingSaving}>{t("actions.cancel")}</Button>
              <Button key="save" type="button" variant="primary" size="sm" onPress={() => void handleSaveBinding()} isDisabled={bindingSaving}>{bindingSaving ? t("binding.saving") : t("binding.save")}</Button>
            </>
          )}
        >
          {bindingForm}
        </ModalLayer>
      )}

      {bindingPrimaryIntent && (
        <ConfirmActionModal
          title={t("binding.primaryTitle")}
          message={(
            <>
              <p>{t("binding.primaryDescription", { faction: factionNames.get(bindingPrimaryIntent.target.faction_id) ?? bindingPrimaryIntent.target.faction_id })}</p>
              {bindingPrimaryIntent.replaced.length > 0 ? (
                <ul className="mt-3 divide-y divide-border border-y border-border">
                  {bindingPrimaryIntent.replaced.map((binding) => (
                    <li key={binding.binding_id} className="py-2">
                      <span className="block font-medium text-foreground">{factionNames.get(binding.faction_id) ?? binding.faction_id}</span>
                      <span className="font-mono text-xs text-muted">{binding.faction_id} · {binding.binding_id}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-3 text-muted">{t("binding.noPreviousPrimary")}</p>}
            </>
          )}
          confirmText={t("binding.makePrimary")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          error={bindingError}
          isLoading={bindingSaving}
          onCancel={() => setBindingPrimaryIntent(null)}
          onConfirm={() => void handleConfirmPrimarySwitch()}
        />
      )}

      {bindingConfirmIntent && (
        <ConfirmActionModal
          title={t(`binding.confirm.${bindingConfirmIntent.mode}.${bindingConfirmIntent.mode === "active" ? (bindingConfirmIntent.binding.user_is_active ? "disableTitle" : "enableTitle") : "title"}`)}
          message={(
            <>
              <p>{t(`binding.confirm.${bindingConfirmIntent.mode}.${bindingConfirmIntent.mode === "active" ? (bindingConfirmIntent.binding.user_is_active ? "disableMessage" : "enableMessage") : "message"}`)}</p>
              <p className="mt-3 font-medium text-foreground">{factionNames.get(bindingConfirmIntent.binding.faction_id) ?? bindingConfirmIntent.binding.faction_id}</p>
              <p className="mt-1 font-mono text-xs text-muted">{bindingConfirmIntent.binding.faction_id} · {bindingConfirmIntent.binding.binding_id}</p>
            </>
          )}
          confirmText={bindingConfirmIntent.mode === "hard" ? t("actions.hardDelete") : bindingConfirmIntent.mode === "soft" ? t("actions.delete") : bindingConfirmIntent.mode === "restore" ? t("actions.restore") : bindingConfirmIntent.binding.user_is_active ? t("actions.deactivate") : t("actions.activate")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          danger={bindingConfirmIntent.mode === "soft" || bindingConfirmIntent.mode === "hard"}
          error={bindingError}
          isLoading={bindingSaving}
          onCancel={() => setBindingConfirmIntent(null)}
          onConfirm={() => void handleConfirmBindingAction()}
        />
      )}

      {deleteIntent && (
        <ConfirmActionModal
          title={deleteIntent.hard ? t("confirm.hardDeleteTitle") : t("confirm.deleteTitle")}
          message={(
            <>
              <p>{deleteIntent.hard ? t("confirm.hardDeleteDescription") : t("confirm.deleteDescription")}</p>
              <p className="mt-3 font-medium text-foreground">{deleteIntent.kind === "character" ? deleteIntent.entity.name : `${deleteIntent.entity.source_character_name || deleteIntent.entity.source_character_id} ${isSymmetricCharacterRelation(deleteIntent.entity.relation_type) ? "↔" : "→"} ${deleteIntent.entity.target_character_name || deleteIntent.entity.target_character_id}`}</p>
              <p className="mt-1 font-mono text-xs text-muted">{deleteIntent.kind === "character" ? deleteIntent.entity.character_id : deleteIntent.entity.relation_id}</p>
            </>
          )}
          confirmText={deleteIntent.hard ? t("actions.hardDelete") : t("actions.delete")}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          danger
          error={editorError}
          isLoading={Boolean(actionId)}
          onCancel={() => setDeleteIntent(null)}
          onConfirm={() => void handleConfirmDelete()}
        />
      )}

      {coreConfirmOpen && corePreview && (
        <ConfirmActionModal
          title={t("candidate.confirmCharacterTitle")}
          message={t("candidate.confirmCharacterMessage", {
            characters: selectedCoreCharacterRefs.length,
            protagonists: corePreview.core_characters.filter((character) =>
              selectedCoreCharacterRefs.includes(character.character_ref) && character.role_type === "protagonist"
            ).length,
            unbound: corePreview.binding_candidates.filter((binding) =>
              selectedCoreCharacterRefs.includes(binding.character_ref) && binding.faction_id === null
            ).length,
          })}
          confirmText={t("candidate.confirmCharacters")}
          cancelText={t("actions.cancel")}
          loadingText={t("candidate.confirming")}
          error={coreCandidateState.error ?? ""}
          isLoading={coreCandidateState.status === "confirming"}
          onCancel={() => setCoreConfirmOpen(false)}
          onConfirm={() => void handleConfirmCorePreview()}
        />
      )}

      {coreDialogOpen && (
        <TaskFlowDialog title={t("generation.characterTitle")} flow={coreFlow} failed={coreCandidateState.status === "error" && coreCandidateState.candidate === null} onCancel={() => setCoreDialogOpen(false)} onGenerate={() => void handleGenerateCoreCharacters()} />
      )}

      {relationDialogOpen && (
        <TaskFlowDialog title={t("generation.relationTitle")} flow={relationFlow} failed={relationCandidateState.status === "error" && relationCandidateState.candidate === null} fieldChoices={{ character_ids: coreCharacters.map((character) => ({ value: character.character_id, label: character.name })) }} onCancel={() => setRelationDialogOpen(false)} onGenerate={() => void handleGenerateRelations()} />
      )}
    </section>
  );
}
