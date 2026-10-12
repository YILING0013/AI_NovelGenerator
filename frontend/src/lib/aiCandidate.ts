/** AI 候选只能存在于当前浏览器页面内的共享状态协议。 */

export type CandidateStateName =
  | "idle"
  | "generating"
  | "preview"
  | "confirming"
  | "error"
  | "stale";

export interface CandidateSourceRefV1 {
  resource_type: string;
  id: string;
  version: number;
}

export interface CandidateBasisV1 {
  flow_ref: import("@/types/taskFlow").FlowRef;
  flow_snapshot: { business_input: unknown; [key: string]: unknown };
  novel_id: string | null;
  workflow: string;
  step: string;
  schema_id: string;
  schema_version: number;
  input_fingerprint: string;
  content_fingerprint?: string | null;
  source_refs: CandidateSourceRefV1[];
}

export interface CandidateGenerationEnvelopeV1<TCandidate> {
  workflow: string;
  step: string;
  schema_id: string;
  schema_version: number;
  candidate: TCandidate;
  basis: CandidateBasisV1;
}

/**
 * 检查接口候选是否带有本轮任务图和确认输入。
 *
 * Args:
 *   value: 接口返回的候选依据。
 * Returns:
 *   是否具备当前确认协议要求的任务图字段。
 */
export function hasCandidateFlow(value: unknown): value is Record<string, unknown> & Pick<CandidateBasisV1, "flow_ref" | "flow_snapshot"> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const { flow_ref: ref, flow_snapshot: snapshot } = value as Record<string, unknown>;
  if (!ref || typeof ref !== "object" || Array.isArray(ref)
    || !snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return false;
  const { id, revision } = ref as Record<string, unknown>;
  return typeof id === "string" && id.length > 0
    && Number.isInteger(revision) && Number(revision) > 0
    && "business_input" in snapshot;
}

/**
 * 按候选的来源版本生成确认请求，避免使用页面刷新后的版本。
 *
 * Args:
 *   basis: 生成这批候选时记录的来源。
 * Returns:
 *   以“来源类型:ID”为键的版本映射。
 */
export function buildCandidateExpectedVersions(basis: CandidateBasisV1): Record<string, number> {
  return Object.fromEntries(
    basis.source_refs.map((source) => [`${source.resource_type}:${source.id}`, source.version]),
  );
}

export interface LocalCandidateState<TCandidate> {
  status: CandidateStateName;
  candidate: TCandidate | null;
  basis: CandidateBasisV1 | null;
  error: string | null;
  requestId: number;
}

export type LocalCandidateAction<TCandidate> =
  | { type: "generate"; requestId: number }
  | { type: "preview"; requestId: number; candidate: TCandidate; basis: CandidateBasisV1 }
  | { type: "confirm" }
  | { type: "confirm_failed"; message: string; stale?: boolean }
  | { type: "generation_failed"; requestId: number; message: string }
  | { type: "mark_stale" }
  | { type: "edit"; candidate: TCandidate }
  | { type: "discard" };

/**
 * 功能：创建不含持久化候选的初始浏览器状态。
 * Args:
 *   requestId: 当前页面请求代次，默认为零。
 * Returns:
 *   可交给 React reducer 使用的 idle 状态。
 */
export function createLocalCandidateState<TCandidate>(
  requestId = 0
): LocalCandidateState<TCandidate> {
  return {
    status: "idle",
    candidate: null,
    basis: null,
    error: null,
    requestId,
  };
}

/**
 * 功能：按固定候选状态机处理生成、预览、确认、失效和放弃。
 * Args:
 *   state: 当前页面内候选状态。
 *   action: 当前交互或异步结果动作。
 * Returns:
 *   新的不可变候选状态；过期请求结果被直接忽略。
 */
export function localCandidateReducer<TCandidate>(
  state: LocalCandidateState<TCandidate>,
  action: LocalCandidateAction<TCandidate>
): LocalCandidateState<TCandidate> {
  switch (action.type) {
    case "generate":
      return { ...createLocalCandidateState<TCandidate>(action.requestId), status: "generating" };
    case "preview":
      if (action.requestId !== state.requestId || state.status !== "generating") return state;
      return { ...state, status: "preview", candidate: action.candidate, basis: action.basis };
    case "confirm":
      return state.candidate && state.basis ? { ...state, status: "confirming", error: null } : state;
    case "confirm_failed":
      return {
        ...state,
        status: action.stale ? "stale" : "error",
        error: action.message,
      };
    case "generation_failed":
      if (action.requestId !== state.requestId) return state;
      return { ...state, status: "error", error: action.message };
    case "mark_stale":
      return state.candidate ? { ...state, status: "stale" } : state;
    case "edit":
      return state.candidate ? { ...state, candidate: action.candidate } : state;
    case "discard":
      return createLocalCandidateState<TCandidate>(state.requestId + 1);
  }
}

/**
 * 功能：比较候选来源版本与页面当前版本，判断是否必须重新生成。
 * Args:
 *   basis: 候选生成时绑定的来源依据。
 *   currentVersions: 以 resource_type:id 为键的页面当前版本。
 * Returns:
 *   任一资源缺失或版本不同返回 true。
 */
export function isCandidateBasisStale(
  basis: CandidateBasisV1,
  currentVersions: Readonly<Record<string, number>>
): boolean {
  return basis.source_refs.some(
    (source) => currentVersions[`${source.resource_type}:${source.id}`] !== source.version
  );
}
