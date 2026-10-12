"use client";
import { useAssistantRefresh, useAssistantResource, useAssistantFocus } from "@/components/writing/assistant/AssistantContext";
import { RetainedModalBackdrop, RetainedViews } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ConfirmActionModal,
  focusRelationEditorError,
  RelationEditorErrorSummary,
} from "@/components/shared/RelationEditorPrimitives";
import WorldRuleFieldsForm, { type WorldRuleEditorSection } from "./WorldRuleFieldsForm";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import TagList from "@/components/shared/TagList";
import WorldRulesCandidateWorkspace from "./WorldRulesCandidateWorkspace";
import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
  ApiRequestError,
  type ApiFieldErrors,
} from "@/lib/api";
import { formatStableReferenceLabel } from "@/types/contracts";
import type { CharacterResponseV1 } from "@/types/character";
import {
  parseActiveLocationListV1,
  type LocationReadV1,
} from "@/types/location";
import type { CoreFaction } from "@/types/novel";
import type {
  WorldRuleCreateV1,
  WorldRuleFieldsV1,
  WorldRuleHardDeleteResponseV1,
  WorldRuleReadV1,
  WorldRuleScopeType,
  WorldRuleStatus,
} from "@/types/worldRule";

export type WorldRulesWorkspaceView = "rules" | "trash";

interface WorldRulesWorkspaceProps {
  mode: "create" | "edit";
  novelId?: string;
  initialView?: WorldRulesWorkspaceView;
  onViewChange?: (view: WorldRulesWorkspaceView) => void;
  onFormalFactsChanged?: () => void;
}

type RuleEditorState = { mode: "create"; source: null };

interface RuleInlineSession {
  section: WorldRuleEditorSection;
  source: WorldRuleReadV1;
  draft: WorldRuleFieldsV1;
  error: string;
  fieldErrors: ApiFieldErrors;
}

const SECTION_FIELDS: Record<WorldRuleEditorSection, (keyof WorldRuleFieldsV1)[]> = {
  identity: ["name", "category", "statement", "enforcement", "priority", "tags"],
  scope: ["scope_type", "scope_entity_ids"],
  exceptions: ["exceptions"],
  consequences: ["costs_and_consequences"],
};

type ConfirmIntent =
  | { kind: "soft-delete"; rule: WorldRuleReadV1 }
  | { kind: "restore"; rule: WorldRuleReadV1 }
  | { kind: "hard-delete"; rule: WorldRuleReadV1 };

const RULE_STATUSES: WorldRuleStatus[] = ["draft", "active", "retired"];
const RULE_SCOPES: readonly WorldRuleScopeType[] = ["global", "faction", "character", "location"];
const INPUT_CLASS =
  "min-h-11 w-full rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";
const FILTER_CLASS =
  "min-h-10 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3 text-sm text-foreground outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15";
const TAB_PREFIX = "world-rules-workspace";
const EMPTY_RULE_LIST: WorldRuleReadV1[] = [];
const EMPTY_FACTION_LIST: CoreFaction[] = [];
const EMPTY_CHARACTER_LIST: CharacterResponseV1[] = [];
const EMPTY_LOCATION_LIST: LocationReadV1[] = [];

const EMPTY_RULE: WorldRuleFieldsV1 = {
  name: "",
  category: "",
  statement: "",
  scope_type: "global",
  scope_entity_ids: [],
  enforcement: "",
  exceptions: [],
  costs_and_consequences: [],
  priority: 0,
  status: "draft",
  tags: [],
};

/**
 * 渲染正式世界规则的主从工作台。
 *
 * Args:
 *   mode: 当前小说处于创建态或正式编辑态。
 *   novelId: 已保存小说的 ObjectId 字符串。
 *   initialView: 初始展示规则或回收站。
 *   onViewChange: 切换子视图时通知 Writing 上层同步状态。
 *   onFormalFactsChanged: 规则保存成功后通知上层刷新准备状态。
 *
 * Returns:
 *   支持筛选、状态管理和响应式详情的世界规则工作台。
 */
export default function WorldRulesWorkspace({
  mode,
  novelId,
  initialView = "rules",
  onViewChange,
  onFormalFactsChanged,
}: WorldRulesWorkspaceProps) {
  const t = useTranslations("writing.worldRules");
  const tLayout = useTranslations("writing.listLayout");
  const [view, setView] = useState<WorldRulesWorkspaceView>(initialView);
  const [storedRules, setRules] = useState<WorldRuleReadV1[]>([]);
  const [storedTrashRules, setTrashRules] = useState<WorldRuleReadV1[]>([]);
  const [storedFactions, setFactions] = useState<CoreFaction[]>([]);
  const [storedCharacters, setCharacters] = useState<CharacterResponseV1[]>([]);
  const [storedLocations, setLocations] = useState<LocationReadV1[]>([]);
  const [loadedNovelId, setLoadedNovelId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState("");
  const [pageActionError, setPageActionError] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | WorldRuleStatus>("all");
  const [scopeFilter, setScopeFilter] = useState<"all" | WorldRuleScopeType>("all");
  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [wideLayout, setWideLayout] = useState(false);
  const workspaceRef = useRef<HTMLElement>(null);
  const [inlineSessions, setInlineSessions] = useState<Record<string, RuleInlineSession>>({});
  const [editor, setEditor] = useState<RuleEditorState | null>(null);
  const [draft, setDraft] = useState<WorldRuleFieldsV1>(EMPTY_RULE);
  const [editorError, setEditorError] = useState("");
  const [editorFieldErrors, setEditorFieldErrors] = useState<ApiFieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [statusRule, setStatusRule] = useState<WorldRuleReadV1 | null>(null);
  const [statusDraft, setStatusDraft] = useState<WorldRuleStatus>("draft");
  const [confirmIntent, setConfirmIntent] = useState<ConfirmIntent | null>(null);
  const [actionRuleId, setActionRuleId] = useState("");
  const [confirmError, setConfirmError] = useState("");
  const [rulesCandidateReviewing, setCandidateReviewing] = useState(false);
  const candidateReviewing = view === "rules" && rulesCandidateReviewing;
  const [candidateSessionKey, setCandidateSessionKey] = useState(0);
  const createCommandRef = useRef<{ fingerprint: string; key: string } | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  const loadRequestIdRef = useRef(0);
  const commandAbortRef = useRef<AbortController | null>(null);
  const commandRequestIdRef = useRef(0);
  const currentNovelIdRef = useRef(novelId);
  const previousNovelIdRef = useRef(novelId);
  currentNovelIdRef.current = novelId;

  const workspaceReady = loadedNovelId === novelId;
  const rules = workspaceReady ? storedRules : EMPTY_RULE_LIST;
  const trashRules = workspaceReady ? storedTrashRules : EMPTY_RULE_LIST;
  const factions = workspaceReady ? storedFactions : EMPTY_FACTION_LIST;
  const characters = workspaceReady ? storedCharacters : EMPTY_CHARACTER_LIST;
  const locations = workspaceReady ? storedLocations : EMPTY_LOCATION_LIST;

  const canUseSavedNovel = mode === "edit" && Boolean(novelId);

  useEffect(() => {
    const element = workspaceRef.current?.querySelector<HTMLElement>(`#${TAB_PREFIX}-${view}-panel`);
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWideLayout(entry.contentRect.width >= 800);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [canUseSavedNovel, novelId, view, candidateSessionKey]);
  const hideList = listCollapsed && wideLayout;
  const workspaceBusy = saving || Boolean(actionRuleId);

  const loadWorkspace = useCallback(async () => {
    if (!novelId || mode !== "edit") return;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    const requestId = loadRequestIdRef.current + 1;
    const requestNovelId = novelId;
    loadAbortRef.current = controller;
    loadRequestIdRef.current = requestId;
    setLoading(true);
    setDataError("");
    try {
      const [loadedRules, loadedTrash, loadedFactions, loadedCharacters, loadedLocations] = await Promise.all([
        apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}`, { signal: controller.signal }),
        apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}/trash`, { signal: controller.signal }),
        apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}`, { signal: controller.signal }),
        apiGet<{ data: CharacterResponseV1[] }>(`/api/characters/novel/${novelId}`, { signal: controller.signal }),
        apiGet<unknown>(`/api/locations/novel/${novelId}`, { signal: controller.signal }),
      ]);
      if (
        controller.signal.aborted ||
        loadAbortRef.current !== controller ||
        loadRequestIdRef.current !== requestId ||
        currentNovelIdRef.current !== requestNovelId
      ) return;
      const parsedLocations = parseActiveLocationListV1(loadedLocations, requestNovelId);
      setRules(loadedRules);
      setTrashRules(loadedTrash);
      setFactions(loadedFactions.data);
      setCharacters(loadedCharacters.data);
      setLocations(parsedLocations);
      setLoadedNovelId(requestNovelId);
    } catch (error) {
      if (
        controller.signal.aborted ||
        loadAbortRef.current !== controller ||
        loadRequestIdRef.current !== requestId ||
        currentNovelIdRef.current !== requestNovelId
      ) return;
      setDataError(error instanceof Error ? error.message : t("errors.load"));
    } finally {
      if (
        loadAbortRef.current === controller &&
        loadRequestIdRef.current === requestId &&
        currentNovelIdRef.current === requestNovelId
      ) {
        loadAbortRef.current = null;
        setLoading(false);
      }
    }
  }, [mode, novelId, t]);

  useAssistantRefresh(novelId, loadWorkspace);

  useEffect(() => {
    if (previousNovelIdRef.current === novelId) return;
    previousNovelIdRef.current = novelId;
    commandAbortRef.current?.abort();
    commandRequestIdRef.current += 1;
    setRules([]);
    setTrashRules([]);
    setFactions([]);
    setCharacters([]);
    setLocations([]);
    setLoadedNovelId(null);
    setSearch("");
    setCategoryFilter("all");
    setStatusFilter("all");
    setScopeFilter("all");
    setSelectedRuleId("");
    setMobileDetailOpen(false);
    setEditor(null);
    setInlineSessions({});
    setEditorError("");
    setEditorFieldErrors({});
    setSaving(false);
    setStatusRule(null);
    setConfirmIntent(null);
    setActionRuleId("");
    setConfirmError("");
    setPageActionError("");
    setCandidateReviewing(false);
    createCommandRef.current = null;
  }, [novelId]);

  useEffect(() => {
    void loadWorkspace();
    return () => loadAbortRef.current?.abort();
  }, [loadWorkspace]);

  useEffect(() => () => {
    commandAbortRef.current?.abort();
    commandRequestIdRef.current += 1;
  }, []);

  const sourceRules = view === "trash" ? trashRules : rules;
  const categories = useMemo(
    () => Array.from(new Set([...rules, ...trashRules].map((rule) => rule.category))).sort((left, right) => left.localeCompare(right)),
    [rules, trashRules],
  );
  const filteredRules = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return sourceRules.filter((rule) => {
      if (categoryFilter !== "all" && rule.category !== categoryFilter) return false;
      if (statusFilter !== "all" && rule.status !== statusFilter) return false;
      if (scopeFilter !== "all" && rule.scope_type !== scopeFilter) return false;
      if (!query) return true;
      return [rule.name, rule.category, rule.statement, rule.enforcement, ...rule.tags]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query);
    });
  }, [categoryFilter, scopeFilter, search, sourceRules, statusFilter]);
  useAssistantFocus("world_rule", (target) => { setSelectedRuleId(target.id); setSearch(""); setCategoryFilter("all"); setStatusFilter("all"); setScopeFilter("all"); setMobileDetailOpen(true); });
  const selectedRule = filteredRules.find((rule) => rule.rule_id === selectedRuleId) ?? filteredRules[0] ?? null;
  const assistantDraft = selectedRule ? inlineSessions[selectedRule.rule_id] : undefined;
  useAssistantResource(selectedRule ? { resource_type: "world_rule", id: selectedRule.rule_id, name: selectedRule.name, version: selectedRule.version, draft: assistantDraft ? { text: JSON.stringify(assistantDraft.draft), fields: Object.keys(assistantDraft.draft), version: assistantDraft.source.version } : undefined } : null);
  const inlineSession = selectedRule ? inlineSessions[selectedRule.rule_id] : undefined;
  const filtersActive = Boolean(search) || categoryFilter !== "all" || statusFilter !== "all" || scopeFilter !== "all";
  const factionNames = new Map(factions.map((faction) => [faction.faction_id, faction.name]));
  const characterNames = new Map(characters.map((character) => [character.character_id, character.name]));
  const locationsById = new Map(locations.map((location) => [location.location_id, location]));

  const changeView = (nextView: WorldRulesWorkspaceView) => {
    if (workspaceBusy) return;
    setView(nextView);
    setSelectedRuleId("");
    setMobileDetailOpen(false);
    setPageActionError("");
    onViewChange?.(nextView);
  };

  const openCreate = () => {
    setDraft({ ...EMPTY_RULE, scope_entity_ids: [], exceptions: [], costs_and_consequences: [], tags: [] });
    setEditor({ mode: "create", source: null });
    setEditorError("");
    setEditorFieldErrors({});
    createCommandRef.current = null;
  };

  const openEdit = (rule: WorldRuleReadV1, section: WorldRuleEditorSection) => {
    if (workspaceBusy || inlineSessions[rule.rule_id]) return;
    const nextDraft = {
      name: rule.name,
      category: rule.category,
      statement: rule.statement,
      scope_type: rule.scope_type,
      scope_entity_ids: [...rule.scope_entity_ids],
      enforcement: rule.enforcement,
      exceptions: rule.exceptions.map((item) => ({ ...item })),
      costs_and_consequences: [...rule.costs_and_consequences],
      priority: rule.priority,
      status: rule.status,
      tags: [...rule.tags],
    };
    // 每个对象独立保留草稿与开始编辑时的版本；刷新不能替换旧基准。
    setInlineSessions((current) => ({ ...current, [rule.rule_id]: { section, source: rule, draft: nextDraft, error: "", fieldErrors: {} } }));
    requestAnimationFrame(() => {
      const section = document.getElementById(`world-rule-editor-${rule.rule_id}`);
      const field = section?.querySelector<HTMLElement>('input:not(:disabled), textarea:not(:disabled), select:not(:disabled)');
      (field ?? section?.querySelector<HTMLElement>('button:not(:disabled)'))?.focus();
    });
  };

  const closeEditor = () => {
    if (saving) return;
    setEditor(null);
    setEditorError("");
    setEditorFieldErrors({});
  };

  const saveEditor = async (session?: RuleInlineSession) => {
    const targetEditor = session ? { mode: "edit" as const, source: session.source } : editor;
    const targetDraft = session?.draft ?? draft;
    if (!targetEditor || !novelId) return;
    const reportError = (message: string, errors: ApiFieldErrors = {}) => {
      if (!session) {
        setEditorError(message);
        setEditorFieldErrors(errors);
        if (message) focusRelationEditorError(errors);
        return;
      }
      setInlineSessions((current) => ({ ...current, [session.source.rule_id]: { ...session, error: message, fieldErrors: errors } }));
      if (message) requestAnimationFrame(() => {
        const section = document.getElementById(`world-rule-editor-${session.source.rule_id}`);
        const firstField = Object.keys(errors)[0];
        const target = (firstField ? section?.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`) : null)
          ?? section?.querySelector<HTMLElement>("[data-editor-error-summary]");
        target?.focus();
      });
    };
    const fieldErrors: ApiFieldErrors = {};
    if (!targetDraft.name.trim()) fieldErrors.name = [t("validation.nameRequired")];
    if (!targetDraft.category.trim()) fieldErrors.category = [t("validation.categoryRequired")];
    if (!targetDraft.statement.trim()) fieldErrors.statement = [t("validation.statementRequired")];
    if (!Number.isInteger(targetDraft.priority) || targetDraft.priority < 0 || targetDraft.priority > 100) {
      fieldErrors.priority = [t("validation.priority")];
    }
    if (targetDraft.scope_type !== "global" && targetDraft.scope_entity_ids.length === 0) {
      fieldErrors.scope_entity_ids = [t("validation.scopeEntitiesRequired")];
    }
    if (targetDraft.scope_entity_ids.length > 100) {
      fieldErrors.scope_entity_ids = [t("validation.scopeEntitiesLimit")];
    }
    const invalidException = targetDraft.exceptions.find((item) => !item.condition.trim() || !item.effect.trim());
    if (invalidException) fieldErrors.exceptions = [t("validation.exceptionRequired")];
    if (targetDraft.costs_and_consequences.some((item) => !item.trim())) {
      fieldErrors.costs_and_consequences = [t("validation.costRequired")];
    }
    if (session) {
      for (const field of Object.keys(fieldErrors)) {
        if (!SECTION_FIELDS[session.section].includes(field as keyof WorldRuleFieldsV1)) delete fieldErrors[field];
      }
    }
    if (Object.keys(fieldErrors).length > 0) {
      reportError(t("errors.validation"), fieldErrors);
      return;
    }

    const payload: WorldRuleCreateV1 = {
      ...targetDraft,
      name: targetDraft.name.trim(),
      category: targetDraft.category.trim(),
      statement: targetDraft.statement.trim(),
      enforcement: targetDraft.enforcement.trim(),
      exceptions: targetDraft.exceptions.map((item) => ({
        condition: item.condition.trim(),
        effect: item.effect.trim(),
      })),
      costs_and_consequences: targetDraft.costs_and_consequences.map((item) => item.trim()),
      tags: targetDraft.tags.map((item) => item.trim()),
    };

    setSaving(true);
    reportError("");
    // 已发出的刷新不能在保存之后用旧列表覆盖新版本。
    loadAbortRef.current?.abort();
    loadRequestIdRef.current += 1;
    setLoading(false);
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      let saved: WorldRuleReadV1;
      if (targetEditor.mode === "create") {
        const fingerprint = JSON.stringify(payload);
        if (createCommandRef.current?.fingerprint !== fingerprint) {
          createCommandRef.current = {
            fingerprint,
            key: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`,
          };
        }
        saved = await apiPost<WorldRuleReadV1>(
          `/api/world-rules/novel/${novelId}`,
          payload,
          {
            headers: { "Idempotency-Key": createCommandRef.current.key },
            signal: controller.signal,
          },
        );
      } else {
        saved = await apiPut<WorldRuleReadV1>(
          `/api/world-rules/novel/${novelId}/${targetEditor.source.rule_id}`,
          { ...Object.fromEntries(SECTION_FIELDS[session!.section].map((field) => [field, payload[field]])), expected_version: targetEditor.source.version },
          { signal: controller.signal },
        );
      }
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      if (targetEditor.mode === "create") {
        setRules((current) => [...current, saved]);
      } else {
        setRules((current) => current.map((rule) => rule.rule_id === saved.rule_id ? saved : rule));
      }
      if (session) {
        setInlineSessions((current) => {
          const next = { ...current };
          delete next[saved.rule_id];
          return next;
        });
        requestAnimationFrame(() => document.getElementById(`world-rule-edit-${saved.rule_id}-${session.section}`)?.focus({ preventScroll: true }));
      } else {
        setSelectedRuleId(saved.rule_id);
        setEditor(null);
      }
      createCommandRef.current = null;
      onFormalFactsChanged?.();
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      if (error instanceof ApiRequestError) {
        const normalizedFieldErrors: ApiFieldErrors = {};
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          // 数组子项错误落回可聚焦的顶层字段，同时保留完整明细。
          const topLevelField = field.split(".")[0];
          normalizedFieldErrors[topLevelField] = [
            ...(normalizedFieldErrors[topLevelField] ?? []),
            ...messages,
          ];
        }
        reportError(error.status === 409 ? t("errors.conflict") : error.message, normalizedFieldErrors);
      } else {
        reportError(error instanceof Error ? error.message : t("errors.save"));
      }
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setSaving(false);
    }
  };

  const saveStatus = async () => {
    if (!statusRule || !novelId || statusDraft === statusRule.status) return;
    setActionRuleId(statusRule.rule_id);
    setConfirmError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      const saved = await apiPut<WorldRuleReadV1>(
        `/api/world-rules/novel/${novelId}/${statusRule.rule_id}`,
        { expected_version: statusRule.version, status: statusDraft },
        { signal: controller.signal },
      );
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setRules((current) => current.map((rule) => rule.rule_id === saved.rule_id ? saved : rule));
      setStatusRule(null);
      onFormalFactsChanged?.();
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.conflict")
        : error instanceof Error ? error.message : t("errors.save"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setActionRuleId("");
    }
  };

  const runConfirmAction = async () => {
    if (!confirmIntent || !novelId) return;
    const { kind, rule } = confirmIntent;
    setActionRuleId(rule.rule_id);
    setConfirmError("");
    commandAbortRef.current?.abort();
    const controller = new AbortController();
    const commandId = commandRequestIdRef.current + 1;
    const commandNovelId = novelId;
    commandAbortRef.current = controller;
    commandRequestIdRef.current = commandId;
    try {
      let changedRule: WorldRuleReadV1 | null = null;
      if (kind === "soft-delete") {
        changedRule = await apiDelete<WorldRuleReadV1>(
          `/api/world-rules/novel/${novelId}/${rule.rule_id}?expected_version=${rule.version}`,
          { signal: controller.signal },
        );
      } else if (kind === "restore") {
        changedRule = await apiPost<WorldRuleReadV1>(
          `/api/world-rules/novel/${novelId}/${rule.rule_id}/restore`,
          { expected_version: rule.version },
          { signal: controller.signal },
        );
      } else {
        await apiDelete<WorldRuleHardDeleteResponseV1>(
          `/api/world-rules/novel/${novelId}/${rule.rule_id}/hard?expected_version=${rule.version}`,
          { signal: controller.signal },
        );
      }
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      if (kind === "soft-delete" && changedRule) {
        setRules((current) => current.filter((item) => item.rule_id !== rule.rule_id));
        setTrashRules((current) => [changedRule, ...current]);
      } else if (kind === "restore" && changedRule) {
        setTrashRules((current) => current.filter((item) => item.rule_id !== rule.rule_id));
        setRules((current) => [...current, changedRule]);
      } else {
        setTrashRules((current) => current.filter((item) => item.rule_id !== rule.rule_id));
      }
      setSelectedRuleId("");
      setMobileDetailOpen(false);
      setConfirmIntent(null);
      onFormalFactsChanged?.();
    } catch (error) {
      if (
        controller.signal.aborted
        || commandRequestIdRef.current !== commandId
        || currentNovelIdRef.current !== commandNovelId
      ) return;
      setConfirmError(error instanceof ApiRequestError && error.status === 409
        ? t("errors.conflict")
        : error instanceof Error ? error.message : t("errors.action"));
    } finally {
      if (
        !controller.signal.aborted
        && commandRequestIdRef.current === commandId
        && currentNovelIdRef.current === commandNovelId
      ) setActionRuleId("");
    }
  };

  if (!canUseSavedNovel) {
    return (
      <section className="grid h-full min-h-72 place-items-center bg-background px-5 py-10">
        <div className="w-full max-w-xl border-y border-border py-10 text-center">
          <span className="text-2xl text-accent" aria-hidden="true">◇</span>
          <h1 className="mt-3 text-xl font-semibold text-foreground">{t("disabled.title")}</h1>
        </div>
      </section>
    );
  }

  const toolbar = (
    <section data-entity-toolbar className="workspace-toolbar flex min-w-0 flex-[1_1_560px] flex-wrap items-end gap-3">
      <label className="grid min-w-0 flex-[2_1_220px] gap-1.5 text-xs font-medium text-muted">
        <span>{t("filters.search")}</span>
        <span className="relative block min-w-0"><input
          type="search" aria-label={t("filters.search")}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("filters.searchPlaceholder")}
          className={`${FILTER_CLASS} w-full pr-11 [&::-webkit-search-cancel-button]:appearance-none`}
          disabled={workspaceBusy}
        />{filtersActive && <button type="button" className="absolute right-0 top-0 grid h-11 w-11 place-items-center rounded-lg text-muted hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 disabled:opacity-50 sm:h-10 sm:w-10" aria-label={t("actions.clearFilters")} title={t("actions.clearFilters")} disabled={workspaceBusy} onClick={() => { setSearch(""); setCategoryFilter("all"); setStatusFilter("all"); setScopeFilter("all"); }}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-4"><path d="m6 6 12 12M18 6 6 18" /></svg></button>}</span>
      </label>
      <label className="grid min-w-0 flex-[1_1_120px] gap-1.5 text-xs font-medium text-muted">
        <span>{t("filters.category")}</span>
        <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} className={FILTER_CLASS} disabled={workspaceBusy}>
          <option value="all">{t("filters.allCategories")}</option>
          {categories.map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
      </label>
      <label className="grid min-w-0 flex-[1_1_120px] gap-1.5 text-xs font-medium text-muted">
        <span>{t("filters.status")}</span>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "all" | WorldRuleStatus)} className={FILTER_CLASS} disabled={workspaceBusy}>
          <option value="all">{t("filters.allStatuses")}</option>
          {RULE_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
        </select>
      </label>
      <label className="grid min-w-0 flex-[1_1_120px] gap-1.5 text-xs font-medium text-muted">
        <span>{t("filters.scope")}</span>
        <select value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value as "all" | WorldRuleScopeType)} className={FILTER_CLASS} disabled={workspaceBusy}>
          <option value="all">{t("filters.allScopes")}</option>
          {RULE_SCOPES.map((scope) => <option key={scope} value={scope}>{t(`scope.${scope}`)}</option>)}
        </select>
      </label>
      <div className="flex shrink-0 flex-wrap gap-2">
        {view === "rules" && <Button variant="primary" size="sm" onPress={openCreate} isDisabled={loading || workspaceBusy}>{t("actions.create")}</Button>}
      </div>
    </section>
  );

  return (
    <section ref={workspaceRef} className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b border-border bg-surface">
        <h1 className="sr-only">{t("title")}</h1>
        {dataError && (
          <div className="flex flex-col gap-3 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200 sm:flex-row sm:items-center sm:justify-between sm:px-6" role="alert">
            <span>{dataError}</span>
            <Button size="sm" variant="outline" isDisabled={workspaceBusy} onPress={() => void loadWorkspace()}>{t("actions.retry")}</Button>
          </div>
        )}
        <div className="flex min-w-0 items-center gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 flex-1 gap-5 overflow-x-auto" role="tablist" aria-label={t("title")}>
            {(["rules", "trash"] as const).map((tab, index, tabs) => (
              <button
                key={tab}
                id={`${TAB_PREFIX}-${tab}-tab`}
                type="button"
                role="tab"
                disabled={workspaceBusy}
                aria-selected={view === tab}
                aria-controls={`${TAB_PREFIX}-${tab}-panel`}
                tabIndex={view === tab ? 0 : -1}
                onClick={() => changeView(tab)}
                onKeyDown={(event) => {
                  if (workspaceBusy) return;
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const nextIndex = event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? tabs.length - 1
                      : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                  const nextTab = tabs[nextIndex];
                  changeView(nextTab);
                  document.getElementById(`${TAB_PREFIX}-${nextTab}-tab`)?.focus();
                }}
                className={`flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors ${
                  view === tab
                    ? "border-accent text-accent"
                    : "border-transparent text-muted hover:border-border hover:text-foreground"
                }`}
              >
                {t(`tabs.${tab}`)}
                <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-xs tabular-nums text-muted">
                  {tab === "rules" ? rules.length : trashRules.length}
                </span>
              </button>
            ))}
          </div>
          <Button className="shrink-0" variant="ghost" size="sm" onPress={() => {
            setCandidateReviewing(false);
            setCandidateSessionKey((current) => current + 1);
            void loadWorkspace();
          }} isDisabled={loading || workspaceBusy}>
            {loading ? t("actions.refreshing") : t("actions.refresh")}
          </Button>
        </div>
      </header>

      <RetainedViews key={`${novelId}:${candidateSessionKey}`} activeKey={view}>
      <div
        id={`${TAB_PREFIX}-${view}-panel`}
        data-entity-body role="tabpanel"
        aria-labelledby={`${TAB_PREFIX}-${view}-tab`}
        className="@container/master flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 sm:px-6"
      >
        <div className={candidateReviewing
          ? "contents"
          : `flex shrink-0 flex-wrap items-end gap-3 border-b border-border pb-3 ${mobileDetailOpen ? "hidden @min-[800px]/master:flex" : ""}`}>
          {!candidateReviewing && toolbar}
          {view === "rules" && novelId && (
            <WorldRulesCandidateWorkspace
              key={`${novelId}:${candidateSessionKey}`}
              novelId={novelId}
              rules={rules}
              factions={factions}
              characters={characters}
              disabled={loading || !workspaceReady || workspaceBusy || Boolean(inlineSession)}
              onReviewingChange={setCandidateReviewing}
              onConfirmed={(response) => {
                setSelectedRuleId(Object.values(response.candidate_ref_map)[0] ?? "");
                setMobileDetailOpen(false);
                onFormalFactsChanged?.();
                // 保存后重新读取规则列表，避免页面自己猜测分类顺序。
                void loadWorkspace();
              }}
            />
          )}
        </div>

        {!candidateReviewing && (
          <>
        {pageActionError && (
          <div className="shrink-0 border-y border-red-500/40 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200" role="alert">
            {pageActionError}
          </div>
        )}

        {loading && sourceRules.length === 0 ? (
          <div className="border-y border-border px-5 py-14 text-center" role="status">
            <span className="mx-auto block size-6 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden="true" />
            <p className="mt-3 text-sm text-muted">{t("loading")}</p>
          </div>
        ) : filteredRules.length === 0 ? (
          <div className="border-y border-dashed border-border px-5 py-14 text-center">
            <p className="text-sm font-medium text-foreground">
              {filtersActive ? t("empty.filteredTitle") : view === "trash" ? t("empty.trashTitle") : t("empty.rulesTitle")}
            </p>
            {!filtersActive && view === "rules" && <Button className="mt-5" variant="primary" size="sm" onPress={openCreate}>{t("actions.createFirst")}</Button>}
          </div>
        ) : selectedRule && (
          <div className={`grid min-h-[520px] flex-1 grid-cols-[minmax(0,1fr)] overflow-visible border-y border-border bg-surface transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none @min-[800px]/master:min-h-0 @min-[800px]/master:gap-x-2 ${hideList ? "@min-[800px]/master:grid-cols-[0px_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[280px_minmax(0,1fr)]"}`}>
            <div className={`${mobileDetailOpen ? "hidden @min-[800px]/master:block" : "block"} relative min-h-0 min-w-0 overflow-visible @min-[800px]/master:border-r @min-[800px]/master:border-border`}>
            <aside data-entity-roster
              id={`world-rule-list-${novelId}-${view}`}
              className={`${hideList ? "invisible pointer-events-none" : ""} workspace-scrollbar h-full min-h-0 max-h-[55vh] w-full overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:max-h-none @min-[800px]/master:w-[280px] @min-[800px]/master:border-b-0`}
              aria-label={t(`tabs.${view}`)}
              aria-hidden={hideList || undefined}
              inert={hideList}
              tabIndex={0}
            >
              <ul className="divide-y divide-border">
                {filteredRules.map((rule) => (
                  <li key={rule.rule_id}>
                    <button
                      id={`world-rule-roster-${rule.rule_id}`}
                      type="button"
                      disabled={workspaceBusy}
                      aria-current={selectedRule.rule_id === rule.rule_id ? "true" : undefined}
                      onClick={() => {
                        setSelectedRuleId(rule.rule_id);
                        setMobileDetailOpen(true);
                        requestAnimationFrame(() => {
                          const detail = document.getElementById(`world-rule-detail-${rule.rule_id}`);
                          if (detail?.previousElementSibling && getComputedStyle(detail.previousElementSibling).display === "none") {
                            detail.focus();
                          }
                        });
                      }}
                      className={`w-full border-l-2 px-4 py-3 text-left transition-colors disabled:cursor-wait ${selectedRule.rule_id === rule.rule_id ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary/55"}`}
                    >
                      <span className="flex items-center justify-between gap-3">
                        <span className="truncate text-sm font-semibold text-foreground">{rule.name}</span>
                        <span aria-hidden="true" className={`size-2 shrink-0 rounded-full ${rule.status === "active" ? "bg-emerald-500" : "bg-muted/45"}`} />
                      </span>
                      <span className="mt-1 block truncate text-xs text-muted">{rule.category} · {t(`status.${rule.status}`)} · {t(`scope.${rule.scope_type}`)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </aside>
            <SidebarEdgeHandle
              controls={`world-rule-list-${novelId}-${view}`}
              className="hidden @min-[800px]/master:flex"
              leftAction={hideList ? undefined : { label: tLayout("collapseList"), expanded: true, onPress: () => setListCollapsed(true) }}
              rightAction={hideList ? { label: tLayout("expandList"), expanded: false, onPress: () => setListCollapsed(false) } : undefined}
            />
            </div>

            <article
              id={`world-rule-detail-${selectedRule.rule_id}`}
              className={`@container/detail ${mobileDetailOpen ? "block" : "hidden @min-[800px]/master:block"} workspace-scrollbar min-w-0 overflow-y-auto outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 @min-[800px]/master:min-h-0`}
              aria-label={`${t(`tabs.${view}`)} · ${selectedRule.name}`}
              tabIndex={0}
            >
              <button type="button" disabled={workspaceBusy} className="mx-5 mt-4 text-sm font-medium text-accent @min-[800px]/master:hidden" onClick={() => {
                const ruleId = selectedRule.rule_id;
                setMobileDetailOpen(false);
                requestAnimationFrame(() => document.getElementById(`world-rule-roster-${ruleId}`)?.focus());
              }}>
                ← {t("actions.backToRoster")}
              </button>
              <div data-entity-detail className="min-w-0 px-5 py-4 sm:px-7">
                <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-2">
                      <StatusPill active={selectedRule.status === "active"}>{t(`status.${selectedRule.status}`)}</StatusPill>
                    </div>
                    <h2 className="sr-only">{selectedRule.name}</h2>
                    <p className="mt-1 font-mono text-xs text-muted">{selectedRule.rule_id} · v{selectedRule.version}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {view === "rules" ? (
                      <>
                        <Button size="sm" variant="ghost" onPress={() => { setStatusRule(selectedRule); setStatusDraft(selectedRule.status); setConfirmError(""); }} isDisabled={workspaceBusy || Boolean(inlineSession)}>{t("actions.changeStatus")}</Button>
                        <Button size="sm" variant="ghost" className="text-danger" onPress={() => { setConfirmIntent({ kind: "soft-delete", rule: selectedRule }); setConfirmError(""); }} isDisabled={workspaceBusy || Boolean(inlineSession)}>{t("actions.delete")}</Button>
                      </>
                    ) : (
                      <>
                        <Button size="sm" variant="outline" onPress={() => { setConfirmIntent({ kind: "restore", rule: selectedRule }); setConfirmError(""); }} isDisabled={Boolean(actionRuleId)}>{t("actions.restore")}</Button>
                        <Button size="sm" variant="ghost" className="text-danger" onPress={() => { setConfirmIntent({ kind: "hard-delete", rule: selectedRule }); setConfirmError(""); }} isDisabled={Boolean(actionRuleId)}>{t("actions.hardDelete")}</Button>
                      </>
                    )}
                  </div>
                </header>

                <div className="mt-4 space-y-4">
                  {(["identity", "scope", "exceptions", "consequences"] as const).map((section, index) => {
                    const editing = view === "rules" && inlineSession?.section === section;
                    return (
                      <DocumentSection
                        key={section}
                        number={String(index + 1).padStart(2, "0")}
                        title={t(`sections.${section === "identity" ? "rule" : section}`)}
                        actions={view === "rules" && (editing ? <>
                          <SectionActionButton action="cancel" label={t("actions.cancel")} size="sm" variant="ghost" isDisabled={saving} onPress={() => {
                            setInlineSessions((current) => {
                              const next = { ...current };
                              delete next[selectedRule.rule_id];
                              return next;
                            });
                            requestAnimationFrame(() => document.getElementById(`world-rule-edit-${selectedRule.rule_id}-${section}`)?.focus({ preventScroll: true }));
                          }} />
                          <SectionActionButton action="save" label={saving ? t("actions.saving") : t("actions.save")} size="sm" variant="primary" isDisabled={workspaceBusy} onPress={() => void saveEditor(inlineSession)} />
                        </> : <SectionEditButton id={`world-rule-edit-${selectedRule.rule_id}-${section}`} isDisabled={workspaceBusy || Boolean(inlineSession)} onPress={() => openEdit(selectedRule, section)} label={t("actions.edit")} />)}
                      >
                        {editing ? (
                          <div id={`world-rule-editor-${selectedRule.rule_id}`}>
                            {inlineSession.error && <RelationEditorErrorSummary message={inlineSession.error} fieldErrors={inlineSession.fieldErrors} className="mb-4" />}
                            <WorldRuleFieldsForm
                              section={section}
                              value={inlineSession.draft}
                              allowedScopes={RULE_SCOPES}
                              factions={factions}
                              characters={characters}
                              locations={locations}
                              disabled={saving}
                              fieldErrors={inlineSession.fieldErrors}
                              errorIdPrefix={`world-rule-${selectedRule.rule_id}`}
                              onChange={(fields) => setInlineSessions((current) => ({
                                ...current,
                                [selectedRule.rule_id]: { ...inlineSession, draft: { ...inlineSession.draft, ...fields } },
                              }))}
                            />
                          </div>
                        ) : section === "identity" ? (
                          <dl className="detail-fields grid min-w-0 gap-4">
                              <ReadOnlyField label={t("fields.name")} value={selectedRule.name} />
                              <ReadOnlyField label={t("fields.category")} value={selectedRule.category} />
                              <ReadOnlyField label={t("fields.priority")} value={String(selectedRule.priority)} />
                            <ReadOnlyField label={t("fields.tags")} value={selectedRule.tags.length ? <TagList values={selectedRule.tags} /> : <span className="text-sm text-muted">{t("empty.noTags")}</span>} />
                            <ReadOnlyField wide label={t("fields.statement")} value={selectedRule.statement} />
                            <ReadOnlyField wide label={t("fields.enforcement")} value={selectedRule.enforcement} />

                          </dl>
                        ) : section === "scope" ? (
                          <dl className="detail-fields grid min-w-0 gap-4"><ReadOnlyField label={t("fields.scopeType")} value={t(`scope.${selectedRule.scope_type}`)} /><ReadOnlyField label={t("fields.scopeEntities")} value={selectedRule.scope_type === "global" ? t("scope.globalDescription") : <TagList values={selectedRule.scope_entity_ids.map((id) => {
                            if (selectedRule.scope_type === "location") {
                              const location = locationsById.get(id);
                              const label = location ? formatStableReferenceLabel(location.name, id) : id;
                              return !location || location.status !== "active" || location.is_deleted ? `${label} · ${t("scope.unavailable")}` : label;
                            }
                            const name = selectedRule.scope_type === "faction" ? factionNames.get(id) : characterNames.get(id);
                            return name ? formatStableReferenceLabel(name, id) : id;
                          })} />} /></dl>
                        ) : section === "exceptions" ? (
                          selectedRule.exceptions.length === 0 ? <p className="text-sm text-muted">{t("empty.noExceptions")}</p> : (
                            <dl className="detail-fields grid min-w-0 gap-4">
                              {selectedRule.exceptions.map((item, exceptionIndex) => (
                                <div key={`${selectedRule.rule_id}-exception-${exceptionIndex}`} className="col-span-full detail-fields grid min-w-0 gap-4">
                                  <ReadOnlyField wide label={t("fields.exceptionCondition")} value={item.condition} />
                                  <ReadOnlyField wide label={t("fields.exceptionEffect")} value={item.effect} />
                                </div>
                              ))}
                            </dl>
                          )
                        ) : selectedRule.costs_and_consequences.length === 0 ? <p className="text-sm text-muted">{t("empty.noConsequences")}</p> : <TagList values={selectedRule.costs_and_consequences} />}
                      </DocumentSection>
                    );
                  })}
                </div>
              </div>
            </article>
          </div>
        )}
          </>
        )}
      </div>
      </RetainedViews>

      {editor && (
        <RetainedModalBackdrop
          isOpen
          onOpenChange={(isOpen) => !isOpen && !saving && closeEditor()}
          variant="blur"
          isDismissable={!saving}
          isKeyboardDismissDisabled={saving}
        >
          <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
            <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[min(90vh,960px)] sm:max-w-5xl">
              <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
                <div>
                  <Modal.Heading className="text-lg font-semibold text-foreground">
                    {editor.mode === "create" ? t("editor.createTitle") : t("editor.editTitle")}
                  </Modal.Heading>
                </div>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={saving} />
              </Modal.Header>
              <Modal.Body className="min-h-0 px-5 py-6 sm:px-7">
                {editorError && <RelationEditorErrorSummary message={editorError} fieldErrors={editorFieldErrors} className="mb-6" />}
                <div className="mb-8 grid gap-2 text-sm">
                  <span className="text-xs font-medium text-muted">{t("fields.status")}</span>
                  <select
                    name="status"
                    aria-label={t("fields.status")}
                    value={draft.status}
                    onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as WorldRuleStatus }))}
                    className={INPUT_CLASS}
                    disabled={saving}
                  >
                    {RULE_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
                  </select>
                </div>
                <WorldRuleFieldsForm
                  value={draft}
                  allowedScopes={RULE_SCOPES}
                  factions={factions}
                  characters={characters}
                  locations={locations}
                  disabled={saving}
                  fieldErrors={editorFieldErrors}
                  errorIdPrefix="world-rule"
                  onChange={(fields) => setDraft((current) => ({ ...current, ...fields }))}
                />
              </Modal.Body>
              <Modal.Footer className="sticky bottom-0 flex justify-end gap-2 border-t border-border bg-surface px-5 py-4 sm:px-7">
                <Button variant="ghost" size="sm" onPress={closeEditor} isDisabled={saving}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void saveEditor()} isDisabled={saving}>{saving ? t("actions.saving") : t("actions.save")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}

      {statusRule && (
        <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !actionRuleId && setStatusRule(null)} variant="blur" isDismissable={!actionRuleId}>
          <Modal.Container size="xs" scroll="inside">
            <Modal.Dialog className="w-full max-w-sm">
              <Modal.Header className="flex items-center justify-between gap-3 px-5 pb-0 pt-5">
                <Modal.Heading className="text-base font-semibold text-foreground">{t("statusDialog.title")}</Modal.Heading>
                <Modal.CloseTrigger aria-label={t("actions.cancel")} isDisabled={Boolean(actionRuleId)} />
              </Modal.Header>
              <Modal.Body className="px-5 py-4">
                {confirmError && <RelationEditorErrorSummary message={confirmError} className="mt-4" />}
                <Field label={t("fields.status")}>
                  <select value={statusDraft} onChange={(event) => setStatusDraft(event.target.value as WorldRuleStatus)} className={INPUT_CLASS} disabled={Boolean(actionRuleId)}>
                    {RULE_STATUSES.map((status) => <option key={status} value={status}>{t(`status.${status}`)}</option>)}
                  </select>
                </Field>
              </Modal.Body>
              <Modal.Footer className="flex justify-end gap-2 px-5 pb-5 pt-0">
                <Button variant="ghost" size="sm" onPress={() => setStatusRule(null)} isDisabled={Boolean(actionRuleId)}>{t("actions.cancel")}</Button>
                <Button variant="primary" size="sm" onPress={() => void saveStatus()} isDisabled={Boolean(actionRuleId) || statusDraft === statusRule.status}>{actionRuleId ? t("actions.saving") : t("actions.confirm")}</Button>
              </Modal.Footer>
            </Modal.Dialog>
          </Modal.Container>
        </RetainedModalBackdrop>
      )}

      {confirmIntent && (
        <ConfirmActionModal
          title={t(`confirm.${confirmIntent.kind}.title`)}
          message={t(`confirm.${confirmIntent.kind}.message`, { name: confirmIntent.rule.name })}
          confirmText={t(`confirm.${confirmIntent.kind}.confirm`)}
          cancelText={t("actions.cancel")}
          loadingText={t("actions.processing")}
          danger={confirmIntent.kind !== "restore"}
          error={confirmError}
          isLoading={actionRuleId === confirmIntent.rule.rule_id}
          onCancel={() => { setConfirmIntent(null); setConfirmError(""); }}
          onConfirm={() => void runConfirmAction()}
        />
      )}
    </section>
  );
}

function Field({ label, children, className = "", error, errorId }: { label: string; children: ReactNode; className?: string; error?: string; errorId?: string }) {
  return (
    <label className={`grid gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {error && <span id={errorId} className="text-xs text-red-600 dark:text-red-300">{error}</span>}
    </label>
  );
}


function StatusPill({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${active ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-surface-secondary text-muted"}`}>
      {children}
    </span>
  );
}
