"use client";
import { REASONING_FIELDS, hasValidReasoningOptions } from "@/types/generation";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";
import SectionEditButton from "@/components/shared/SectionEditButton";


import { TaskFlowForm,TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";

import {
RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import {
buildCandidateExpectedVersions,
createLocalCandidateState,
hasCandidateFlow,
localCandidateReducer,
type CandidateSourceRefV1,
} from "@/lib/aiCandidate";
import {
apiPost,
ApiRequestError,
type ApiFieldErrors
} from "@/lib/api";
import type { CharacterResponseV1 } from "@/types/character";
import type { CoreFaction } from "@/types/novel";
import type {
CoreWorldRuleCandidateV1,
CoreWorldRulesBasisV1,
CoreWorldRulesCandidateEnvelopeV1,
CoreWorldRulesConfirmResponseV1,
CoreWorldRulesConfirmV1,
CoreWorldRuleScopeType,
CoreWorldRulesGenerationInputV1,
CoreWorldRulesResultV1,
WorldRuleReadV1
} from "@/types/worldRule";
import { Button,Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import {
useEffect,
useMemo,
useReducer,
useRef,
useState,
} from "react";
import WorldRuleFieldsForm from "./WorldRuleFieldsForm";

interface WorldRulesCandidateWorkspaceProps {
  novelId: string;
  rules: WorldRuleReadV1[];
  factions: CoreFaction[];
  characters: CharacterResponseV1[];
  disabled?: boolean;
  onReviewingChange?: (reviewing: boolean) => void;
  onConfirmed: (response: CoreWorldRulesConfirmResponseV1) => void;
}

interface StableConfirmCommand {
  fingerprint: string;
  key: string;
}

const CORE_WORLD_RULES_CONTRACT = {
  workflow: "create_world_rules_by_ai",
  step: "create_core_world_rules",
  schemaId: "world_rule.core_generation.result",
  schemaVersion: 1,
} as const;
const CANDIDATE_REF_PATTERN = /^rule_candidate_\d+$/;
const NOVEL_ID_PATTERN = /^[0-9a-f]{24}$/;
const FACTION_ID_PATTERN = /^fac_[0-9]{6,}$/;
const CHARACTER_ID_PATTERN = /^char_[0-9]{6,}$/;
const CORE_RULE_SCOPES: readonly CoreWorldRuleScopeType[] = ["global", "faction", "character"];

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

function isNullableNumberInRange(value: unknown, minimum: number, maximum: number): boolean {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum);
}

function isGenerationInput(value: unknown, novelId: string): value is CoreWorldRulesGenerationInputV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "novel_id",
    "core_rule_count",
    "allow_incremental",
    "user_guidance",
    ...REASONING_FIELDS.filter((key) => key in value),
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    "system_prompt",
  ])) return false;
  return (
    value.novel_id === novelId &&
    NOVEL_ID_PATTERN.test(novelId) &&
    Number.isInteger(value.core_rule_count) &&
    Number(value.core_rule_count) >= 1 &&
    Number(value.core_rule_count) <= 20 &&
    typeof value.allow_incremental === "boolean" &&
    typeof value.user_guidance === "string" &&
    value.user_guidance.length <= 2000 &&
    hasValidReasoningOptions(value) &&
    isNullableNumberInRange(value.temperature, 0, 2) &&
    isNullableNumberInRange(value.top_p, 0, 1) &&
    (value.max_tokens === null || (Number.isInteger(value.max_tokens) && Number(value.max_tokens) > 0)) &&
    isNullableNumberInRange(value.presence_penalty, -2, 2) &&
    isNullableNumberInRange(value.frequency_penalty, -2, 2) &&
    (value.system_prompt === null || (typeof value.system_prompt === "string" && value.system_prompt.length <= 40000))
  );
}

function isSourceRef(value: unknown): value is CandidateSourceRefV1 {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, ["resource_type", "id", "version"]) &&
    typeof value.resource_type === "string" &&
    /^[a-z][a-z0-9_]{1,63}$/.test(value.resource_type) &&
    typeof value.id === "string" &&
    value.id.length >= 1 &&
    value.id.length <= 100 &&
    Number.isInteger(value.version) &&
    Number(value.version) >= 1
  );
}

function isCoreWorldRulesBasis(value: unknown, novelId: string): value is CoreWorldRulesBasisV1 {
  if (!hasCandidateFlow(value) || !hasOnlyKeys(value, [
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
  ])) return false;
  if (
    value.novel_id !== novelId ||
    value.workflow !== CORE_WORLD_RULES_CONTRACT.workflow ||
    value.step !== CORE_WORLD_RULES_CONTRACT.step ||
    value.schema_id !== CORE_WORLD_RULES_CONTRACT.schemaId ||
    value.schema_version !== CORE_WORLD_RULES_CONTRACT.schemaVersion ||
    typeof value.input_fingerprint !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.input_fingerprint) ||
    !Array.isArray(value.source_refs) ||
    value.source_refs.length > 2000 ||
    !value.source_refs.every(isSourceRef) ||
    !isGenerationInput(value.generation_input, novelId)
  ) return false;
  const sourceKeys = value.source_refs.map((source) => `${source.resource_type}:${source.id}`);
  return sourceKeys.length > 0 && new Set(sourceKeys).size === sourceKeys.length;
}

function isNonEmptyString(value: unknown, maximum: number): value is string {
  return typeof value === "string" && value.trim().length >= 1 && value.length <= maximum;
}

function isCoreWorldRuleCandidate(value: unknown): value is CoreWorldRuleCandidateV1 {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "candidate_ref",
    "name",
    "category",
    "statement",
    "scope_type",
    "scope_entity_ids",
    "enforcement",
    "exceptions",
    "costs_and_consequences",
    "priority",
    "tags",
  ])) return false;
  if (
    typeof value.candidate_ref !== "string" ||
    !CANDIDATE_REF_PATTERN.test(value.candidate_ref) ||
    !isNonEmptyString(value.name, 80) ||
    !isNonEmptyString(value.category, 40) ||
    !isNonEmptyString(value.statement, 2000) ||
    !["global", "faction", "character"].includes(String(value.scope_type)) ||
    !Array.isArray(value.scope_entity_ids) ||
    value.scope_entity_ids.length > 100 ||
    typeof value.enforcement !== "string" ||
    value.enforcement.length > 1000 ||
    !Array.isArray(value.exceptions) ||
    value.exceptions.length > 20 ||
    !Array.isArray(value.costs_and_consequences) ||
    value.costs_and_consequences.length > 20 ||
    !Number.isInteger(value.priority) ||
    Number(value.priority) < 0 ||
    Number(value.priority) > 100 ||
    !Array.isArray(value.tags) ||
    value.tags.length > 20
  ) return false;
  if (!value.exceptions.every((exception) =>
    isRecord(exception) &&
    hasOnlyKeys(exception, ["condition", "effect"]) &&
    isNonEmptyString(exception.condition, 500) &&
    isNonEmptyString(exception.effect, 500)
  )) return false;
  if (!value.costs_and_consequences.every((item) => isNonEmptyString(item, 500))) return false;
  if (!value.tags.every((item) => typeof item === "string" && item.trim().length > 0)) return false;
  if (!value.scope_entity_ids.every((id) => typeof id === "string")) return false;
  const scopeIds = value.scope_entity_ids as string[];
  if (new Set(scopeIds).size !== scopeIds.length) return false;
  if (value.scope_type === "global") return scopeIds.length === 0;
  if (scopeIds.length === 0) return false;
  return value.scope_type === "faction"
    ? scopeIds.every((id) => FACTION_ID_PATTERN.test(id))
    : scopeIds.every((id) => CHARACTER_ID_PATTERN.test(id));
}

function isCoreWorldRulesResult(value: unknown): value is CoreWorldRulesResultV1 {
  if (
    !isRecord(value) ||
    !hasOnlyKeys(value, ["core_world_rules"]) ||
    !Array.isArray(value.core_world_rules) ||
    value.core_world_rules.length < 1 ||
    value.core_world_rules.length > 20 ||
    !value.core_world_rules.every(isCoreWorldRuleCandidate)
  ) return false;
  const refs = value.core_world_rules.map((rule) => rule.candidate_ref);
  const names = value.core_world_rules.map((rule) => rule.name.trim().toLocaleLowerCase());
  return new Set(refs).size === refs.length && new Set(names).size === names.length;
}

/**
 * 严格解析核心规则普通响应或 SSE done.result 信封。
 *
 * Args:
 *   value: 待解析的未知响应值。
 *   novelId: 当前工作台小说 ID。
 *
 * Returns:
 *   完整契约匹配时返回候选信封，否则返回 null。
 */
export function parseCoreWorldRulesEnvelope(
  value: unknown,
  novelId: string,
): CoreWorldRulesCandidateEnvelopeV1 | null {
  if (!isRecord(value) || !hasOnlyKeys(value, [
    "workflow",
    "step",
    "schema_id",
    "schema_version",
    "candidate",
    "basis",
  ])) return null;
  if (
    value.workflow !== CORE_WORLD_RULES_CONTRACT.workflow ||
    value.step !== CORE_WORLD_RULES_CONTRACT.step ||
    value.schema_id !== CORE_WORLD_RULES_CONTRACT.schemaId ||
    value.schema_version !== CORE_WORLD_RULES_CONTRACT.schemaVersion ||
    !isCoreWorldRulesResult(value.candidate) ||
    !isCoreWorldRulesBasis(value.basis, novelId)
  ) return null;
  return value as unknown as CoreWorldRulesCandidateEnvelopeV1;
}

function validateEditableCandidate(
  candidate: CoreWorldRuleCandidateV1,
  duplicateName: boolean,
  messages: {
    nameRequired: string;
    categoryRequired: string;
    statementRequired: string;
    priority: string;
    scopeRequired: string;
    scopeLimit: string;
    exceptionRequired: string;
    costRequired: string;
    duplicateName: string;
  },
): ApiFieldErrors {
  const errors: ApiFieldErrors = {};
  if (!candidate.name.trim()) errors.name = [messages.nameRequired];
  else if (duplicateName) errors.name = [messages.duplicateName];
  if (!candidate.category.trim()) errors.category = [messages.categoryRequired];
  if (!candidate.statement.trim()) errors.statement = [messages.statementRequired];
  if (!Number.isInteger(candidate.priority) || candidate.priority < 0 || candidate.priority > 100) {
    errors.priority = [messages.priority];
  }
  if (candidate.scope_type !== "global" && candidate.scope_entity_ids.length === 0) {
    errors.scope_entity_ids = [messages.scopeRequired];
  } else if (candidate.scope_entity_ids.length > 100) {
    errors.scope_entity_ids = [messages.scopeLimit];
  }
  if (candidate.exceptions.some((item) => !item.condition.trim() || !item.effect.trim())) {
    errors.exceptions = [messages.exceptionRequired];
  }
  if (candidate.costs_and_consequences.some((item) => !item.trim())) {
    errors.costs_and_consequences = [messages.costRequired];
  }
  return errors;
}

function normalizeConfirmFieldErrors(
  fieldErrors: ApiFieldErrors,
  candidates: CoreWorldRuleCandidateV1[],
  localizedMessage: string,
): Record<string, ApiFieldErrors> {
  const result: Record<string, ApiFieldErrors> = {};
  for (const path of Object.keys(fieldErrors)) {
    const parts = path.split(".");
    const candidateIndex = parts[0] === "candidates" ? Number(parts[1]) : Number.NaN;
    const candidate = Number.isInteger(candidateIndex) ? candidates[candidateIndex] : candidates[0];
    if (!candidate) continue;
    const field = parts[0] === "candidates" && parts.length >= 3 ? parts[2] : parts[0];
    result[candidate.candidate_ref] = {
      ...(result[candidate.candidate_ref] ?? {}),
      [field]: [localizedMessage],
    };
  }
  return result;
}

function focusCandidateError(fieldErrors: ApiFieldErrors): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const workspace = document.querySelector<HTMLElement>(
        '[aria-labelledby="world-rules-candidate-heading"]',
      );
      if (!workspace) return;
      const firstField = Object.keys(fieldErrors)[0]?.split(".").at(-1);
      const field = firstField
        ? workspace.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`)
        : null;
      const target = field ?? workspace.querySelector<HTMLElement>("[data-editor-error-summary]");
      target?.focus({ preventScroll: true });
      target?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    });
  });
}

/**
 * 渲染核心世界规则的 AI 参数、生成进度和本地候选复核工作台。
 *
 * Args:
 *   novelId: 当前正式小说 ID。
 *   rules: 当前页面已加载的正式世界规则。
 *   factions: 当前页面已加载的同书势力。
 *   characters: 当前页面已加载的同书角色。
 *   disabled: 正式输入仍在加载时禁止启动或确认候选。
 *   onReviewingChange: 候选进入或离开完整复核态时通知父工作台。
 *   onConfirmed: 整批正式确认成功后的响应回调。
 *
 * Returns:
 *   不持久化候选的参数 Modal、进度区或候选主从复核区。
 */
export default function WorldRulesCandidateWorkspace({
  novelId,
  rules,
  factions,
  characters,
  disabled = false,
  onReviewingChange,
  onConfirmed,
}: WorldRulesCandidateWorkspaceProps) {
  const t = useTranslations("writing.worldRules.ai");
  const commonT = useTranslations("writing.worldRules");
  const taskFlow = useTaskFlow("create_world_rules_by_ai");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [candidateState, dispatchCandidate] = useReducer(
    localCandidateReducer<CoreWorldRulesResultV1>,
    createLocalCandidateState<CoreWorldRulesResultV1>(),
  );
  const [selectedCandidateRef, setSelectedCandidateRef] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [candidateFieldErrors, setCandidateFieldErrors] = useState<Record<string, ApiFieldErrors>>({});
  const generationAbortRef = useRef<AbortController | null>(null);
  const confirmationAbortRef = useRef<AbortController | null>(null);
  const confirmCommandRef = useRef<StableConfirmCommand | null>(null);
  const previewPageVersionsRef = useRef<Record<string, number>>({});
  const currentNovelIdRef = useRef(novelId);
  currentNovelIdRef.current = novelId;

  const candidates = candidateState.candidate?.core_world_rules ?? [];
  const selectedCandidate = candidates.find((candidate) => candidate.candidate_ref === selectedCandidateRef)
    ?? candidates[0]
    ?? null;
  const reviewing = Boolean(candidateState.candidate);
  const readOnly = disabled || candidateState.status === "stale" || candidateState.status === "confirming";

  const currentKnownVersions = useMemo(() => {
    const versions: Record<string, number> = {};
    for (const rule of rules) versions[`world_rule:${rule.rule_id}`] = rule.version;
    for (const faction of factions) versions[`faction:${faction.faction_id}`] = faction.version;
    for (const character of characters) versions[`character:${character.character_id}`] = character.version;
    return versions;
  }, [characters, factions, rules]);
  const currentKnownVersionsRef = useRef(currentKnownVersions);
  currentKnownVersionsRef.current = currentKnownVersions;

  useEffect(() => {
    onReviewingChange?.(reviewing);
  }, [onReviewingChange, reviewing]);

  useEffect(() => {
    const basis = candidateState.basis;
    if (!basis || candidateState.status === "stale") return;
    const knownResourceTypes = new Set(["world_rule", "faction", "character"]);
    const changed = basis.source_refs.some((source) => {
      const key = `${source.resource_type}:${source.id}`;
      const currentVersion = currentKnownVersions[key];
      const previewPageVersion = previewPageVersionsRef.current[key];
      if (!knownResourceTypes.has(source.resource_type) || previewPageVersion === undefined) return false;
      // 生成响应是当前服务端真值；只在页面快照于预览之后发生变化时重新比较 basis。
      if (currentVersion === previewPageVersion) return false;
      return currentVersion === undefined || currentVersion !== source.version;
    });
    if (changed) dispatchCandidate({ type: "mark_stale" });
  }, [candidateState.basis, candidateState.status, currentKnownVersions]);

  useEffect(() => {
    // 小说切换与组件卸载都必须让旧流失去写入页面状态的资格。
    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    confirmationAbortRef.current?.abort();
    confirmationAbortRef.current = null;
    dispatchCandidate({ type: "discard" });
    setDialogOpen(false);
    setSelectedCandidateRef("");
    setCandidateFieldErrors({});
    confirmCommandRef.current = null;
    previewPageVersionsRef.current = {};
    return () => {
      generationAbortRef.current?.abort();
      confirmationAbortRef.current?.abort();
    };
  }, [novelId]);

  const discardCandidate = () => {
    void taskFlow.discard();

    generationAbortRef.current?.abort();
    generationAbortRef.current = null;
    confirmationAbortRef.current?.abort();
    confirmationAbortRef.current = null;
    dispatchCandidate({ type: "discard" });
    setSelectedCandidateRef("");
    setMobileDetailOpen(false);
    setCandidateFieldErrors({});
    confirmCommandRef.current = null;
    previewPageVersionsRef.current = {};
  };

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (disabled || generationAbortRef.current || candidateState.candidate) return;
    const requestId = candidateState.requestId + 1;
    const requestNovelId = novelId;
    const controller = new AbortController();
    generationAbortRef.current = controller;
    dispatchCandidate({ type: "generate", requestId });
    setDialogOpen(false);

    try {
      const generated = await taskFlow.run(`/api/llm/novels/${novelId}/world-rules/core/stream`, { novel_id: requestNovelId }, controller.signal, retry);
      if (controller.signal.aborted || generationAbortRef.current !== controller || currentNovelIdRef.current !== requestNovelId) return;
      const envelope: CoreWorldRulesCandidateEnvelopeV1 | null = parseCoreWorldRulesEnvelope(generated.result, requestNovelId);
      if (!envelope) throw new Error(t("errors.invalidPreview"));
      dispatchCandidate({
        type: "preview",
        requestId,
        candidate: structuredClone(envelope.candidate),
        basis: envelope.basis,
      });
      previewPageVersionsRef.current = Object.fromEntries(
        envelope.basis.source_refs.flatMap((source) => {
          const key = `${source.resource_type}:${source.id}`;
          const pageVersion = currentKnownVersionsRef.current[key];
          return pageVersion === undefined ? [] : [[key, pageVersion]];
        }),
      );
      setSelectedCandidateRef(envelope.candidate.core_world_rules[0]?.candidate_ref ?? "");
      setCandidateFieldErrors({});
    } catch (error) {
      if (!controller.signal.aborted && currentNovelIdRef.current === requestNovelId) {
        let message = t("errors.generate");
        if (error instanceof ApiRequestError) {
          if (error.code?.startsWith("AGENT_")) {
            message = error.message;
          } else if (error.code === "WORLD_RULE_READINESS_REQUIRED" || error.status === 422) {
            message = t("errors.readiness");
          } else if (error.status === 502) {
            message = t("errors.invalidPreview");
          } else if (error.status === 503) {
            message = t("errors.providerUnavailable");
          } else if (error.status === 504) {
            message = t("errors.timeout");
          }
        } else if (error instanceof Error && error.message === t("errors.invalidPreview")) {
          message = t("errors.invalidPreview");
        }
        dispatchCandidate({
          type: "generation_failed",
          requestId,
          message,
        });
      }
    } finally {
      if (generationAbortRef.current === controller) generationAbortRef.current = null;
    }
  };

  const updateCandidate = (nextCandidate: CoreWorldRuleCandidateV1) => {
    if (!candidateState.candidate || readOnly) return;
    dispatchCandidate({
      type: "edit",
      candidate: {
        core_world_rules: candidateState.candidate.core_world_rules.map((candidate) =>
          candidate.candidate_ref === nextCandidate.candidate_ref ? nextCandidate : candidate,
        ),
      },
    });
    setCandidateFieldErrors((current) => ({ ...current, [nextCandidate.candidate_ref]: {} }));
  };

  const removeCandidate = (candidateRef: string) => {
    if (!candidateState.candidate || readOnly) return;
    const currentIndex = candidates.findIndex((candidate) => candidate.candidate_ref === candidateRef);
    const remaining = candidates.filter((candidate) => candidate.candidate_ref !== candidateRef);
    dispatchCandidate({ type: "edit", candidate: { core_world_rules: remaining } });
    setCandidateFieldErrors((current) => {
      const next = { ...current };
      delete next[candidateRef];
      return next;
    });
    setSelectedCandidateRef(remaining[Math.min(currentIndex, remaining.length - 1)]?.candidate_ref ?? "");
    if (remaining.length === 0) setMobileDetailOpen(false);
  };

  const confirmCandidates = async () => {
    if (
      !candidateState.candidate ||
      !candidateState.basis ||
      candidates.length === 0 ||
      candidateState.status === "stale" ||
      candidateState.status === "confirming" ||
      confirmationAbortRef.current
    ) return;
    const normalizedNames = candidates.map((candidate) => candidate.name.trim().toLocaleLowerCase());
    const errorsByRef: Record<string, ApiFieldErrors> = {};
    for (const candidate of candidates) {
      const normalizedName = candidate.name.trim().toLocaleLowerCase();
      const errors = validateEditableCandidate(
        candidate,
        normalizedName.length > 0 && normalizedNames.filter((name) => name === normalizedName).length > 1,
        {
          nameRequired: commonT("validation.nameRequired"),
          categoryRequired: commonT("validation.categoryRequired"),
          statementRequired: commonT("validation.statementRequired"),
          priority: commonT("validation.priority"),
          scopeRequired: commonT("validation.scopeEntitiesRequired"),
          scopeLimit: commonT("validation.scopeEntitiesLimit"),
          exceptionRequired: commonT("validation.exceptionRequired"),
          costRequired: commonT("validation.costRequired"),
          duplicateName: t("errors.duplicateName"),
        },
      );
      if (Object.keys(errors).length > 0) errorsByRef[candidate.candidate_ref] = errors;
    }
    const firstInvalid = candidates.find((candidate) => errorsByRef[candidate.candidate_ref]);
    if (firstInvalid) {
      setCandidateFieldErrors(errorsByRef);
      setSelectedCandidateRef(firstInvalid.candidate_ref);
      setMobileDetailOpen(true);
      dispatchCandidate({ type: "confirm_failed", message: t("errors.validation") });
      focusCandidateError(errorsByRef[firstInvalid.candidate_ref]);
      return;
    }

    const request: CoreWorldRulesConfirmV1 = {
      candidates,
      basis: candidateState.basis as CoreWorldRulesBasisV1,
      expected_versions: buildCandidateExpectedVersions(candidateState.basis),
    };
    const fingerprint = JSON.stringify(request);
    if (confirmCommandRef.current?.fingerprint !== fingerprint) {
      confirmCommandRef.current = {
        fingerprint,
        key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
      };
    }
    dispatchCandidate({ type: "confirm" });
    setCandidateFieldErrors({});
    const requestNovelId = novelId;
    const controller = new AbortController();
    confirmationAbortRef.current = controller;
    try {
      const response = await apiPost<CoreWorldRulesConfirmResponseV1>(
        `/api/world-rules/novel/${novelId}/bulk-core`,
        request,
        {
          headers: { "Idempotency-Key": confirmCommandRef.current.key },
          signal: controller.signal,
        },
      );
      if (
        controller.signal.aborted ||
        confirmationAbortRef.current !== controller ||
        currentNovelIdRef.current !== requestNovelId
      ) return;
      const expectedCandidateRefs = new Set(candidates.map((candidate) => candidate.candidate_ref));
      const responseCandidateRefs = isRecord(response) && isRecord(response.candidate_ref_map)
        ? Object.keys(response.candidate_ref_map)
        : [];
      const mappedRuleIds = isRecord(response) && isRecord(response.candidate_ref_map)
        ? Object.values(response.candidate_ref_map)
        : [];
      const responseRuleIds = isRecord(response) && Array.isArray(response.world_rules)
        ? new Set(response.world_rules.flatMap((rule) =>
          isRecord(rule) && typeof rule.rule_id === "string" ? [rule.rule_id] : [],
        ))
        : new Set<string>();
      if (
        !isRecord(response) ||
        !isRecord(response.candidate_ref_map) ||
        !Array.isArray(response.world_rules) ||
        responseCandidateRefs.length !== expectedCandidateRefs.size ||
        !responseCandidateRefs.every((candidateRef) => expectedCandidateRefs.has(candidateRef)) ||
        !mappedRuleIds.every((ruleId) => typeof ruleId === "string" && /^rule_[0-9]{6,}$/.test(ruleId) && responseRuleIds.has(ruleId)) ||
        new Set(mappedRuleIds).size !== mappedRuleIds.length
      ) {
        throw new Error(t("errors.invalidConfirmation"));
      }
      dispatchCandidate({ type: "discard" });
      setSelectedCandidateRef("");
      setMobileDetailOpen(false);
      confirmCommandRef.current = null;
      previewPageVersionsRef.current = {};
      onConfirmed(response);
    } catch (error) {
      if (
        controller.signal.aborted ||
        confirmationAbortRef.current !== controller ||
        currentNovelIdRef.current !== requestNovelId
      ) return;
      if (error instanceof ApiRequestError && error.status === 422) {
        const normalized = normalizeConfirmFieldErrors(
          error.fieldErrors,
          candidates,
          t("errors.fieldInvalid"),
        );
        setCandidateFieldErrors(normalized);
        const firstRef = candidates.find((candidate) => normalized[candidate.candidate_ref])?.candidate_ref;
        if (firstRef) {
          setSelectedCandidateRef(firstRef);
          setMobileDetailOpen(true);
          focusCandidateError(normalized[firstRef]);
        } else {
          focusCandidateError({});
        }
      }
      const basisInvalid = error instanceof ApiRequestError && [404, 409].includes(error.status);
      let message = t("errors.confirm");
      if (basisInvalid) message = t("errors.conflict");
      else if (error instanceof ApiRequestError && error.status === 422) message = t("errors.validation");
      else if (error instanceof ApiRequestError && error.status === 503) message = t("errors.providerUnavailable");
      else if (error instanceof ApiRequestError && error.status === 504) message = t("errors.timeout");
      else if (error instanceof ApiRequestError && error.status === 502) message = t("errors.invalidConfirmation");
      else if (error instanceof Error && error.message === t("errors.invalidConfirmation")) {
        message = t("errors.invalidConfirmation");
      }
      dispatchCandidate({
        type: "confirm_failed",
        message,
        stale: basisInvalid,
      });
    } finally {
      if (confirmationAbortRef.current === controller) confirmationAbortRef.current = null;
    }
  };

  if (!reviewing) {
    return (
      <div className="contents">
        <section className="workspace-toolbar ml-auto flex flex-wrap items-end gap-2" aria-labelledby="world-rules-ai-heading">
          <h2 id="world-rules-ai-heading" className="sr-only">{t("toolbar.title")}</h2>
          {candidateState.status === "generating" ? (
            <Button variant="outline" size="sm" onPress={discardCandidate}>{t("actions.cancelGeneration")}</Button>
          ) : (
            <Button variant="outline" size="sm" onPress={() => setDialogOpen(true)} isDisabled={disabled}>{t("actions.open")}</Button>
          )}
        </section>
        {candidateState.status === "error" && candidateState.error && (
          <div className="w-full border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
            {candidateState.error}
          </div>
        )}

        {(candidateState.status === "generating" || candidateState.status === "error") && <TaskFlowProgress flow={taskFlow} running={candidateState.status === "generating"} failed={candidateState.status === "error" && candidateState.candidate === null} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={discardCandidate} label={t("progress.starting")} />}
      {dialogOpen && (
          <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && setDialogOpen(false)} variant="blur" isDismissable>
            <Modal.Container size="lg" scroll="inside" className="p-0 sm:p-4">
              <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
                <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                  <div>
                    <Modal.Heading className="text-lg font-semibold text-foreground">{t("dialog.title")}</Modal.Heading>
                  </div>
                  <Modal.CloseTrigger aria-label={t("actions.cancel")} />
                </Modal.Header>
                <Modal.Body className="px-5 py-6 sm:px-7"><TaskFlowForm flow={taskFlow} /></Modal.Body>
                <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                  <Button variant="ghost" size="sm" onPress={() => setDialogOpen(false)}>{t("actions.cancel")}</Button>
                  <Button variant="primary" size="sm" onPress={() => void generate()} isDisabled={disabled || taskFlow.loading || !taskFlow.definition}>{t("actions.generate")}</Button>
                </Modal.Footer>
              </Modal.Dialog>
            </Modal.Container>
          </RetainedModalBackdrop>
        )}
      </div>
    );
  }

  return (
    <section className="@container/master flex min-h-0 flex-1 flex-col overflow-hidden border-y border-border bg-surface" aria-labelledby="world-rules-candidate-heading">
      <header className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
            <h2 id="world-rules-candidate-heading" className="text-lg font-semibold text-foreground">{t("preview.title")}</h2>
            <p className="text-xs tabular-nums text-muted">{t("preview.count", { count: candidates.length })}</p>
          </div>
          <span className="self-start rounded-full bg-surface-secondary px-2.5 py-1 text-xs tabular-nums text-muted">
            {t(`status.${candidateState.status}`)}
          </span>
        </div>
        {candidateState.status === "stale" && (
          <div className="mt-4 border-y border-amber-400/60 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200" role="alert">
            {t("errors.conflict")}
          </div>
        )}
        {candidateState.status !== "stale" && candidateState.error && (
          <RelationEditorErrorSummary message={candidateState.error} className="mt-4" />
        )}
      </header>

      {selectedCandidate ? (
        <div className="grid min-h-0 flex-1 overflow-hidden @min-[800px]/master:grid-cols-[260px_minmax(0,1fr)]">
          <aside
            className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} workspace-scrollbar min-h-0 overflow-y-auto bg-surface-secondary/45 border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:border-b-0 @min-[800px]/master:border-r`}
            tabIndex={0}
            aria-label={t("preview.rosterLabel")}
          >
            <ul className="divide-y divide-border">
              {candidates.map((candidate) => (
                <li key={candidate.candidate_ref}>
                  <button
                    id={`world-rule-candidate-${candidate.candidate_ref}`}
                    type="button"
                    onClick={() => {
                      setSelectedCandidateRef(candidate.candidate_ref);
                      setMobileDetailOpen(true);
                      requestAnimationFrame(() => {
                        const detail = document.getElementById(`world-rule-candidate-detail-${candidate.candidate_ref}`);
                        if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                          detail.focus();
                        }
                      });
                    }}
                    aria-current={selectedCandidate.candidate_ref === candidate.candidate_ref ? "true" : undefined} className={`min-h-11 w-full border-l-2 px-4 py-3 text-left transition-colors ${selectedCandidate.candidate_ref === candidate.candidate_ref ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`}
                  >
                    <span className="block text-sm font-semibold text-foreground [overflow-wrap:anywhere]">{candidate.name || t("preview.untitled")}</span>
                    <span className="mt-1 block truncate text-xs text-muted">{candidate.category || t("preview.uncategorized")} · {commonT(`scope.${candidate.scope_type}`)}</span>
                    {candidateFieldErrors[candidate.candidate_ref] && Object.keys(candidateFieldErrors[candidate.candidate_ref]).length > 0 && (
                      <span className="mt-2 block text-xs font-medium text-red-600 dark:text-red-300">{t("preview.hasErrors")}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <article
            id={`world-rule-candidate-detail-${selectedCandidate.candidate_ref}`}
            className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-h-0 min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30`}
            tabIndex={0}
            aria-label={`${t("preview.detailLabel")} · ${selectedCandidate.name}`}
          >
            <div className="px-5 py-6 sm:px-7">
              <button type="button" className="mb-5 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                const candidateRef = selectedCandidate.candidate_ref;
                setMobileDetailOpen(false);
                requestAnimationFrame(() => document.getElementById(`world-rule-candidate-${candidateRef}`)?.focus());
              }}>
                ← {t("actions.backToRoster")}
              </button>
              <div className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex min-w-0 flex-wrap items-center gap-1"><h3 className="min-w-0 text-xl font-semibold text-foreground [overflow-wrap:anywhere]">{selectedCandidate.name || t("preview.untitled")}</h3><SectionEditButton label={commonT("actions.edit")} isDisabled={readOnly} onPress={() => document.getElementById(`world-rule-candidate-detail-${selectedCandidate.candidate_ref}`)?.querySelector<HTMLElement>("input, select, textarea")?.focus()} /></div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-danger"
                  onPress={() => removeCandidate(selectedCandidate.candidate_ref)}
                  isDisabled={readOnly}
                >
                  {t("actions.removeCandidate")}
                </Button>
              </div>
              {candidateFieldErrors[selectedCandidate.candidate_ref] && Object.keys(candidateFieldErrors[selectedCandidate.candidate_ref]).length > 0 && (
                <RelationEditorErrorSummary
                  message={t("errors.validation")}
                  fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]}
                  className="mt-6"
                />
              )}
              <div className="pt-7">
                <WorldRuleFieldsForm
                  value={selectedCandidate}
                  allowedScopes={CORE_RULE_SCOPES}
                  factions={factions}
                  characters={characters}
                  disabled={readOnly}
                  fieldErrors={candidateFieldErrors[selectedCandidate.candidate_ref]}
                  errorIdPrefix={`world-rule-candidate-${selectedCandidate.candidate_ref}`}
                  onChange={(fields) => updateCandidate({ ...fields, candidate_ref: selectedCandidate.candidate_ref })}
                />
              </div>
            </div>
          </article>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 place-items-center px-5 py-12 text-center">
          <p className="text-sm font-medium text-foreground">{t("preview.emptyTitle")}</p>
        </div>
      )}

      <footer className="shrink-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
          <Button variant="ghost" size="sm" onPress={discardCandidate} isDisabled={candidateState.status === "confirming"}>
            {t("actions.discard")}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onPress={() => void confirmCandidates()}
            isDisabled={readOnly || candidates.length === 0}
          >
            {candidateState.status === "confirming" ? t("actions.confirming") : t("actions.confirm")}
          </Button>
        </div>
      </footer>
    </section>
  );
}
