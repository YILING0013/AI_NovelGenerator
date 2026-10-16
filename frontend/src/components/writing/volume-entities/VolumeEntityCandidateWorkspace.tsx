"use client";

import { downloadExport } from "@/lib/userExport";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import { TaskFlowForm, TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import { apiGet, apiPostJson, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterProfileFields, CharacterRelationResponseV1, CharacterResponseV1 } from "@/types/character";
import type { CoreFaction } from "@/types/novel";
import type { FlowRef } from "@/types/taskFlow";
import type { VolumeReadV2 } from "@/types/volume";
import type { FactionVolumeStateReadV1 } from "@/types/factionVolumeState";
import type { CharacterVolumePlanFieldsV1, CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";
import { CHARACTER_PLAN_CONTRACT, volumeCharacterDesignForm, editVolumeCharacterDesign, hasExplicitFactionValues, volumeFactionFacts, editVolumeFactionFact, parseVolumeEntityPreview, type VolumeCharacterCandidate, type VolumeEntityCandidate, type VolumeEntityConfirmResult, type VolumeEntityKind, type VolumeEntityPreview, type VolumeFactionCandidate } from "@/types/volumeEntity";
import CharacterProfileForm from "../characters/forms/CharacterProfileForm";
import CharacterFactFieldsEditor from "../characters/CharacterFactFieldsEditor";
import CharacterVolumeStateForm from "../characters/CharacterVolumeStateForm";
import FactionFactFieldsEditor from "../factions/FactionFactFieldsEditor";
import FactionVolumeStateForm from "../factions/FactionVolumeStateForm";
import VolumeFactionProfileForm from "./VolumeFactionProfileForm";
import { readCharacterVolumeCandidateDraft, writeCharacterVolumeCandidateDraft, type CharacterVolumeCandidateEntry, type CharacterVolumeCandidateResolution } from "./characterVolumeCandidateDrafts";

interface EntityDraft {
  preview: unknown;
  flow_ref: FlowRef | null;
  inputs: Record<string, unknown>;
  params: GenerationParamsValue;
  command: { payload: string; key: string; unknown?: boolean } | null;
  stale: boolean;
  completed?: true;
}

// 本地存储暂时不可用时，关闭重开也不能再次确认已知成功的原请求。
const confirmedCommands = new Set<string>();

/** 功能：生成、审核并确认当前卷的新档案及参与状态。Args: props 当前卷、正式对象和保存回调。Returns: 两种实体共用的页内候选审核；生成和审核不写作品。 */
export default function VolumeEntityCandidateWorkspace({ kind, novelId, volume, characters, factions, relations, onClose, onSaved, adoptionOpen = false, minimized, onMinimizedChange }: {
  kind: VolumeEntityKind; novelId: string; volume: VolumeReadV2;
  characters: CharacterResponseV1[]; factions: CoreFaction[]; relations: CharacterRelationResponseV1[];
  onClose: () => void; onSaved: (result: VolumeEntityConfirmResult, names: Record<string, string>) => void;
  onAdoptCharacter?: (profile: CharacterProfileFields, candidateRef: string) => Promise<void>;
  onAdoptPlan?: (characterId: string, fields: CharacterVolumePlanFieldsV1) => Promise<void>;
  adoptionOpen?: boolean;
  minimized: boolean;
  onMinimizedChange: (minimized: boolean) => void;
}) {
  const active = useContext(RetainedViewActive);
  const pageRef = useRef<HTMLElement>(null);
  const t = useTranslations("writing.volumeEntitiesAi");
  const planT = useTranslations(kind === "characters" ? "writing.characterVolumeStates" : "writing.factionVolumeStates");
  const characterT = useTranslations("writing.characters");
  const flow = useTaskFlow(`create_${kind}_for_volume_by_ai`);
  const { loading: flowLoading, select: selectFlow, setInputs, setParams } = flow;
  const [preview, setPreview] = useState<VolumeEntityPreview | null>(null);
  const [retainedDraft, setRetainedDraft] = useState<EntityDraft | null>(null);
  const previewRef = useRef(preview); previewRef.current = preview;
  const editorRef = useRef<HTMLDivElement>(null);
  const [selectedRef, setSelectedRef] = useState("");
  const [running, setRunning] = useState(false);
  useEffect(() => { if (active && !minimized) { const frame = requestAnimationFrame(() => pageRef.current?.focus()); return () => cancelAnimationFrame(frame); } }, [active, minimized]);
  const [cancelled, setCancelled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [restored, setRestored] = useState(false);
  const [error, setError] = useState("");
  const [storageError, setStorageError] = useState("");
  const [errors, setErrors] = useState<ApiFieldErrors>({});
  const [stale, setStale] = useState(false);
  const [currentVolume, setCurrentVolume] = useState(volume);
  const [formalCharacters, setFormalCharacters] = useState(characters);
  const [formalFactions, setFormalFactions] = useState(factions);
  const [formalRelations, setFormalRelations] = useState(relations);
  const [refreshing, setRefreshing] = useState(false);
  const [planSnapshot, setPlanSnapshot] = useState<{ source: string; rows: (CharacterVolumeStateReadV1 | FactionVolumeStateReadV1)[] } | null>(null);
  const [planError, setPlanError] = useState("");
  const [adoptedChanges, setAdoptedChanges] = useState("");
  const [completed, setCompleted] = useState(false);
  const cleanupVersion = useRef<number | null>(null);
  const [draftConflict, setDraftConflict] = useState(false);
  const ownedDraft = useRef<CharacterVolumeCandidateEntry | null>(null);
  const blockedDraft = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const activeSession = useRef<object | null>(null);
  const writes = useRef(Promise.resolve());
  const command = useRef<EntityDraft["command"]>(null);
  const setup = useRef<EntityDraft | null>(null);
  const version = useRef(volume.version);
  const initialVersion = useRef(volume.version);
  const generationVersion = useRef<number | null>(null);
  const key = `${novelId}:volume:${volume.volume_id}:${kind}:generation`;
  const candidates: VolumeEntityCandidate[] = preview?.candidate[kind] ?? [];
  const selected = candidates.find((item) => item.candidate_ref === selectedRef) ?? candidates[0];
  const selectedIndex = selected ? candidates.indexOf(selected) : -1;
  const retryOnly = Boolean(command.current) && (kind === "characters" || !stale || command.current?.unknown !== false);
  const locked = saving || adoptionOpen;
  const legacyFactionCandidate = kind === "factions" && Boolean(preview) && !command.current && !hasExplicitFactionValues(preview);
  const readOnly = locked || stale || draftConflict || Boolean(command.current) || legacyFactionCandidate;
  const availableCharacters = formalCharacters.filter((item) => !item.is_deleted && item.status === "active");
  const availableFactions = formalFactions.filter((item) => !item.is_deleted && item.active_status === "active" && (item.level_type === "core" || item.volume_id === volume.volume_id));
  const names = new Map(kind === "characters" ? formalCharacters.map((item) => [item.character_id, item.name]) : formalFactions.map((item) => [item.faction_id, item.name]));
  const fieldErrors = (prefix: string) => Object.fromEntries(Object.entries(errors)
    .filter(([field]) => field.startsWith(`candidates.${selectedIndex}.${prefix}.`))
    .map(([field, messages]) => [field.slice(`candidates.${selectedIndex}.${prefix}.`.length), messages]));
  const itemName = (item: VolumeEntityCandidate) => item.profile?.name ?? names.get("character_id" in item ? item.character_id! : item.faction_id!) ?? t("existing");
  const identityOf = (row: VolumeEntityCandidate | CharacterVolumeStateReadV1 | FactionVolumeStateReadV1) => "character_id" in row ? row.character_id : row.faction_id;
  const planField = (row: object, field: string) => (row as Record<string, unknown>)[field];
  const existingPlans = candidates.filter((row) => identityOf(row) && row.state_expected_version !== null);
  const planSource = JSON.stringify(existingPlans.map((row) => [identityOf(row), row.state_expected_version]));
  useEffect(() => {
    if (planSource === "[]" || retryOnly) return;
    let active = true;
    setPlanError("");
    void apiGet<{ data: (CharacterVolumeStateReadV1 | FactionVolumeStateReadV1)[] }>(`/api/${kind === "characters" ? "character" : "faction"}-volume-states/novel/${novelId}/volume/${volume.volume_id}`)
      .then((response) => {
        const expected = JSON.parse(planSource) as [string, number][];
        if (!Array.isArray(response.data) || expected.some(([id, expectedVersion]) => !response.data.some((row) => identityOf(row) === id && row.version === expectedVersion && !row.is_deleted))) throw new Error(t(kind === "factions" ? "factions.planChanged" : "planChanged"));
        if (active) setPlanSnapshot({ source: planSource, rows: response.data });
      }).catch((failure) => { if (active) setPlanError(failure instanceof Error ? failure.message : t("loadFailed")); });
    return () => { active = false; };
  }, [novelId, volume.volume_id, planSource, retryOnly, t, kind]);
  const planFields: Record<string, string> = { participation_scope: "participationScope", current_goal: "currentGoal", start_state: "startState", planned_end_state: "plannedEndState", ...(kind === "characters" ? { relationship_focus_ids: "relationshipFocus", arc_progress: "arcProgress" } : { hidden_agenda: "hiddenAgenda" }) };
  const planChanges = existingPlans.flatMap((row) => {
    const before = planSnapshot?.source === planSource ? planSnapshot.rows.find((saved) => identityOf(saved) === identityOf(row)) : undefined;
    if (!before) return [];
    const changes = Object.keys(planFields).filter((field) => JSON.stringify(planField(before, field)) !== JSON.stringify(planField(row.state, field)));
    return changes.length ? [{ row, before, changes }] : [];
  });
  const changeKey = JSON.stringify(planChanges.map(({ row, before, changes }) => [identityOf(row), before.version, changes.map((field) => [field, planField(before, field), planField(row.state, field)])]));
  const planReviewBlocked = !retryOnly && existingPlans.length > 0 && (Boolean(planError) || planSnapshot?.source !== planSource || kind === "characters" && planChanges.length > 0 && adoptedChanges !== changeKey);
  const planValue = (field: string, value: unknown) => {
    if (field === "participation_scope") return planT(`scope.${String(value)}`);
    if (Array.isArray(value)) return value.map((id) => {
      const relation = formalRelations.find((item) => item.relation_id === id);
      return relation ? `${names.get(relation.source_character_id) ?? t("existing")} — ${names.get(relation.target_character_id) ?? t("existing")}` : t("unavailableRelation");
    }).join("、") || t("emptyValue");
    return field === "arc_progress" ? `${value}%` : String(value) || t("emptyValue");
  };
  const saveLocalDraft = useCallback(async (draftVersion: number, value: EntityDraft | null, resolution?: CharacterVolumeCandidateResolution) => {
    // 每笔排队写入使用上一笔已提交原行，不能把同页第二次编辑误判成竞争。
    const result = await writeCharacterVolumeCandidateDraft(key, draftVersion, value, ownedDraft.current, resolution);
    if (!result.written) {
      blockedDraft.current = true; setDraftConflict(true);
      throw new Error(t("draftConflict"));
    }
    ownedDraft.current = result.current;
  }, [key, t]);

  useEffect(() => {
    let active = true;
    activeSession.current = {};
    readCharacterVolumeCandidateDraft(key, initialVersion.current).then(async (stored) => {
      if (!active) return;
      ownedDraft.current = stored;
      if (stored) {
        if (stored.value.completed || stored.value.command && confirmedCommands.has(stored.value.command.key)) {
          cleanupVersion.current = stored.base_version;
          try {
            if (!stored.value.completed && stored.value.command) await saveLocalDraft(stored.base_version, { ...stored.value, completed: true }, { kind: "saved", command: stored.value.command });
            await saveLocalDraft(stored.base_version, null);
            cleanupVersion.current = null;
            if (stored.value.command) confirmedCommands.delete(stored.value.command.key);
          } catch { if (active) setStorageError(t("savedDraftCleanupFailed")); }
          if (active) setRestored(true);
          return;
        }
        // 先恢复冻结命令；展示合同变化不能使原键、原体或未知状态丢失。
        command.current = stored.value.command; version.current = stored.base_version;
        const savedPreview = stored.value.preview;
        const parsed = parseVolumeEntityPreview(savedPreview, kind, novelId, volume.volume_id);
        if (!parsed && (savedPreview || stored.value.command)) {
          setRetainedDraft(stored.value); setPreview(null); setRestored(true);
        } else {
          setPreview(parsed); setup.current = stored.value;
        }
        setStale(stored.value.stale || Boolean(parsed && !parsed.basis.content_fingerprint && !stored.value.command && stored.base_version !== initialVersion.current));
      } else setRestored(true);
    }).catch((failure) => { if (active) { setStorageError(failure instanceof Error ? failure.message : t("draftFailed")); setRestored(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; activeSession.current = null; controller.current?.abort(); };
  }, [key, kind, novelId, volume.volume_id, t, saveLocalDraft]);

  useEffect(() => {
    if (loading || (!command.current && flowLoading) || !setup.current) return;
    const session = activeSession.current;
    const stored = setup.current; setup.current = null;
    void (async () => {
      if (stored.flow_ref && !stored.command) await selectFlow(stored.flow_ref);
      if (activeSession.current !== session) return;
      setInputs(stored.inputs); setParams(stored.params); setRestored(true);
    })();
  }, [loading, flowLoading, selectFlow, setInputs, setParams]);

  useEffect(() => {
    if (loading || saving || !restored || completed || retainedDraft || command.current || cleanupVersion.current !== null || blockedDraft.current) return;
    const draft: EntityDraft = { preview, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null, inputs: flow.inputs, params: flow.params, command: command.current, stale };
    const draftVersion = version.current;
    writes.current = writes.current.then(() => {
      if (blockedDraft.current) throw new Error(t("draftConflict"));
      return saveLocalDraft(draftVersion, draft);
    }).catch((failure) => setStorageError(failure instanceof Error ? failure.message : t("draftFailed")));
  }, [key, loading, saving, restored, completed, retainedDraft, preview, flow.definition, flow.inputs, flow.params, stale, t, saveLocalDraft]);

  const refreshSources = async () => {
    setRefreshing(true); setError("");
    try {
      const latest = await apiGet<VolumeReadV2>(`/api/volumes/${volume.volume_id}`);
      setCurrentVolume(latest);
      if (kind === "characters") {
        const [people, links] = await Promise.all([
          apiGet<{ data: CharacterResponseV1[] }>(`/api/characters/novel/${novelId}`),
          apiGet<{ data: CharacterRelationResponseV1[] }>(`/api/character-relations/novel/${novelId}`),
        ]);
        setFormalCharacters(people.data); setFormalRelations(links.data);
      } else {
        const lists = await Promise.all(["core", "volume", "local"].map((level) => apiGet<{ data: CoreFaction[] }>(`/api/factions/novel/${novelId}/level/${level}`)));
        setFormalFactions(lists.flatMap((result) => result.data));
      }
      if (preview && !command.current) setStale(true);
    } catch (failure) { setError(failure instanceof Error ? failure.message : t("loadFailed")); }
    finally { setRefreshing(false); }
  };

  const generate = async (retry: TaskFlowRunMode = false) => {
    if (controller.current || running || command.current || retainedDraft) return;
    setCancelled(false);
    const abort = new AbortController(); controller.current = abort;
    setRunning(true); setError(""); setErrors({}); setStale(false);
    try {
      if (cleanupVersion.current !== null) {
        await saveLocalDraft(cleanupVersion.current, null); cleanupVersion.current = null; setStorageError("");
      }
      if (!retry) { await flow.discard(); generationVersion.current = null; }
      if (generationVersion.current === null) {
        const latest = await apiGet<VolumeReadV2>(`/api/volumes/${volume.volume_id}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        setCurrentVolume(latest); generationVersion.current = latest.version;
      }
      version.current = generationVersion.current;
      const generated = await flow.run(`/api/llm/novels/${novelId}/volumes/${volume.volume_id}/${kind}/stream`, {
        novel_id: novelId, volume_id: volume.volume_id, volume_expected_version: version.current,
      }, abort.signal, retry);
      if (abort.signal.aborted) return;
      const result = parseVolumeEntityPreview(generated.result, kind, novelId, volume.volume_id);
      if (!result) throw new Error(t("invalidResult"));
      setPreview(result); setSelectedRef(result.candidate[kind]?.[0]?.candidate_ref ?? ""); command.current = null;
    } catch (failure) { if (!abort.signal.aborted) setError(failure instanceof Error ? failure.message : t("generateFailed")); }
    finally { if (controller.current === abort) { controller.current = null; setRunning(false); } }
  };

  const updateCandidate = (item: VolumeEntityCandidate) => {
    if (!preview || readOnly) return;
    const next = { ...preview, candidate: { [kind]: candidates.map((old) => old.candidate_ref === item.candidate_ref ? item : old) } };
    previewRef.current = next; setPreview(next);
    setErrors({});
  };

  const confirm = async () => {
    if ((!preview && !command.current) || locked || blockedDraft.current || legacyFactionCandidate || planReviewBlocked || stale && !retryOnly || completed) return;
    const original = command.current;
    const request = original ? JSON.parse(original.payload) : kind === "characters" ? {
      contract: CHARACTER_PLAN_CONTRACT, basis: preview!.basis,
      candidates: (candidates as VolumeCharacterCandidate[]).map((row) => ({
        ...row, state: { participation_scope: row.state.participation_scope, current_goal: row.state.current_goal,
          start_state: row.state.start_state, planned_end_state: row.state.planned_end_state,
          relationship_focus_ids: row.state.relationship_focus_ids, arc_progress: row.state.arc_progress },
      })),
    } : { contract: "participation_plan_v1", basis: preview!.basis,
      candidates: (candidates as VolumeFactionCandidate[]).map((row) => ({ ...row,
        state: { participation_scope: row.state.participation_scope, current_goal: row.state.current_goal,
          start_state: row.state.start_state, planned_end_state: row.state.planned_end_state, hidden_agenda: row.state.hidden_agenda },
        ...(row.profile ? { initial_facts: volumeFactionFacts(row) } : {}),
      })),
    };
    const payload = original?.payload ?? JSON.stringify(request);
    setSaving(true); setError(""); setErrors({});
    const session = activeSession.current;
    const pendingCommand = original ? { ...original, unknown: true } : { payload, key: crypto.randomUUID(), unknown: true };
    command.current = pendingCommand;
    const draftVersion = version.current;
    const draft: EntityDraft = { ...(retainedDraft ?? (original ? ownedDraft.current?.value : null) ?? { preview, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null, inputs: flow.inputs, params: flow.params, stale }), command: pendingCommand };
    let previous: CharacterVolumeCandidateEntry | null = null;
    let registered: CharacterVolumeCandidateEntry | null = null;
    let result: VolumeEntityConfirmResult;
    try {
      // 请求键和原依据先落本地；刷新或丢响应后只能用同一批内容重试。
      await writes.current;
      if (blockedDraft.current) throw new Error(t("draftConflict"));
      previous = ownedDraft.current;
      await saveLocalDraft(draftVersion, draft);
      registered = ownedDraft.current;
      if (activeSession.current !== session) return;
      setStorageError("");
      result = await apiPostJson<VolumeEntityConfirmResult>(`/api/novels/${novelId}/volumes/${volume.volume_id}/${kind}/confirm`, payload, { headers: { "Idempotency-Key": pendingCommand.key } });
      if (result.novel_id !== novelId || result.volume_id !== volume.volume_id || !Array.isArray(result.data)
        || !result.mapping || typeof result.mapping !== "object" || Array.isArray(result.mapping)
        || result.data.some((item) => !item || typeof item !== "object" || item.novel_id !== novelId || item.volume_id !== volume.volume_id
          || typeof item.state_id !== "string" || !item.state_id || !Number.isInteger(item.version) || item.version < 1
          || (kind === "characters" ? !("character_id" in item) || typeof item.character_id !== "string" || !item.character_id
            : !("faction_id" in item) || typeof item.faction_id !== "string" || !item.faction_id))) throw new Error(t("invalidResult"));
    } catch (failure) {
      if (activeSession.current !== session) return;
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      if (failure instanceof ApiRequestError) {
        setErrors(failure.fieldErrors);
        // 未知后的拒绝仍不能证明之前未保存；两类候选都保留原键。
        command.current = { ...pendingCommand, unknown: Boolean(original && original.unknown !== false) || failure.status < 400 || failure.status >= 500 };
        const sourceChanged = kind === "factions" && ["CANDIDATE_SOURCE_CHANGED", "VOLUME_ENTITY_STATE_VERSION_CONFLICT", "VOLUME_ENTITY_REFERENCE_UNAVAILABLE", "VOLUME_ENTITY_SCOPE_MISMATCH", "VOLUME_ENTITY_VOLUME_NOT_FOUND", "VOLUME_ENTITY_IDEMPOTENCY_CONFLICT"].includes(failure.code ?? "");
        if (failure.status >= 400 && failure.status < 500 && registered) {
          try {
            await saveLocalDraft(draftVersion, { ...draft, command: command.current, stale: stale || sourceChanged },
              { kind: "rejected", previous, registered });
          } catch (storageFailure) { setStorageError(storageFailure instanceof Error ? storageFailure.message : t("draftFailed")); }
        }
        if (sourceChanged) setStale(true);
        const index = Object.keys(failure.fieldErrors)[0]?.match(/^candidates\.(\d+)\./)?.[1];
        if (index !== undefined && candidates[Number(index)]) setSelectedRef(candidates[Number(index)].candidate_ref);
        focusRelationEditorError(failure.fieldErrors);
      }
      setSaving(false);
      return;
    }

    // 正式响应就是保存成功；后面的本地清理不能把它改成保存失败。
    confirmedCommands.add(pendingCommand.key);
    if (activeSession.current === session) setCompleted(true);
    try {
      await saveLocalDraft(draftVersion, { ...draft, completed: true }, { kind: "saved", command: pendingCommand });
      await saveLocalDraft(draftVersion, null);
      confirmedCommands.delete(pendingCommand.key);
    } catch { /* 保留原键和成功标记，下次打开时只清理本地稿。 */ }
    if (activeSession.current !== session) return;
    const savedNames: Record<string, string> = {};
    for (const item of candidates) {
      const entityId = result.mapping[item.candidate_ref];
      if (entityId) savedNames[entityId] = itemName(item);
    }
    onSaved(result, savedNames);
  };

  const cancelGeneration = () => { controller.current?.abort(); setCancelled(true); };
  const close = async () => {
    // 收起页内流程时仍接收同一任务；只有明确停止才中止生成。
    if (running) { onMinimizedChange(true); return; }
    controller.current?.abort();
    const focused = document.activeElement;
    if (focused instanceof HTMLElement && editorRef.current?.contains(focused)) focused.blur();
    if (previewRef.current !== preview) {
      const draft: EntityDraft = { preview: previewRef.current, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null,
        inputs: flow.inputs, params: flow.params, command: command.current, stale };
      writes.current = writes.current.then(() => saveLocalDraft(version.current, draft)).catch((failure) => setStorageError(failure instanceof Error ? failure.message : t("draftFailed")));
    }
    await writes.current;
    if (blockedDraft.current) { setStorageError(t("draftConflict")); return; }
    onClose();
  };
  const exportDraft = () => {
    const blob = new Blob([JSON.stringify(retainedDraft ? { ...retainedDraft, command: command.current } : preview, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `${volume.title}-${kind}-candidate.json`; void downloadExport(link); URL.revokeObjectURL(url);
  };
  const revise = async () => {
    if (locked || retainedDraft || command.current?.unknown !== false) return;
    try {
      await writes.current;
      if (blockedDraft.current) throw new Error(t("draftConflict"));
      const draft: EntityDraft = { preview, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null, inputs: flow.inputs, params: flow.params, command: null, stale };
      await saveLocalDraft(version.current, draft, { kind: "revise" });
      command.current = null; setError(""); setErrors({}); setStorageError("");
    } catch (failure) { setStorageError(failure instanceof Error ? failure.message : t("draftFailed")); }
  };
  const discard = async () => {
    if (locked || command.current && command.current.unknown !== false) return;
    try {
      await writes.current;
      if (blockedDraft.current) throw new Error(t("draftConflict"));
      await saveLocalDraft(version.current, null, command.current?.unknown === false ? { kind: "revise" } : undefined);
      await flow.discard();
      if (retainedDraft) await flow.refresh();
      command.current = null; setRetainedDraft(null); setPreview(null); setStale(false); setError(""); setErrors({});
      version.current = currentVolume.version;
    } catch (failure) { setStorageError(failure instanceof Error ? failure.message : t("draftFailed")); }
  };

  if (completed) return null;
  if (minimized) return <section aria-label={t("backgroundTitle")} className="shrink-0 space-y-3 border-t border-border px-4 py-3">
    <p role="status" className="text-sm">{t(running ? "backgroundRunning" : cancelled ? "cancelled" : preview ? "backgroundReady" : "generateFailed")}</p>
    <TaskFlowProgress flow={flow} running={running} failed={Boolean(error)} />
    <Button size="sm" variant="outline" onPress={() => onMinimizedChange(false)}>{t("openGeneration")}</Button>
    {running && <Button size="sm" variant="ghost" onPress={cancelGeneration}>{t("cancel")}</Button>}
  </section>;
  return <section ref={pageRef} tabIndex={-1} aria-label={t(`${kind}.title`)} className="@container/volumeCandidates flex min-h-0 flex-1 flex-col overflow-hidden bg-surface outline-none" onKeyDown={(event) => { if (event.key === "Escape" && !locked && !draftConflict) { event.stopPropagation(); void close(); } }}>
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3 sm:px-6">
          <h3 className="text-base font-semibold">{t(`${kind}.title`)} · {volume.title}</h3>
          <Button size="sm" variant="ghost" onPress={() => void close()} isDisabled={locked || draftConflict}>{t("close")}</Button>
        </header>
        <div ref={editorRef} className={`workspace-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-3 sm:px-6 ${preview && !planChanges.length ? "@min-[800px]/volumeCandidates:overflow-hidden" : ""}`}>
          {error && <RelationEditorErrorSummary message={error} fieldErrors={errors} className="mb-4" />}
          {storageError && <p role="alert" className="mb-4 border-y border-danger/40 py-3 text-sm text-danger">{storageError}</p>}
          {cancelled && <p role="status" className="mb-4 text-sm text-muted">{t("cancelled")}</p>}
          {legacyFactionCandidate && <p role="alert" className="mb-4 text-sm">{t("factions.explicitFactsRequired")}</p>}
          {stale && <p role="alert" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("stale")}</p>}
          {preview && <p className="mb-3 text-sm text-muted">{t(kind === "characters" ? "characterStart" : "factionStart", { title: volume.title })}</p>}
          {retryOnly && command.current?.unknown !== false && !saving && <p role="status" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("retryConfirmation")}</p>}
          {!retryOnly && planError && <p role="alert" className="mb-4 text-danger">{planError}</p>}
          {!retryOnly && planChanges.length > 0 && <section aria-label={t(kind === "factions" ? "factions.planChanges" : "planChanges", { count: planChanges.length })} className="mb-5 space-y-3 border-y border-border py-4">
            <h3 className="text-sm font-semibold">{t(kind === "factions" ? "factions.planChanges" : "planChanges", { count: planChanges.length })}</h3>
            {planChanges.map(({ row, before, changes }) => <div key={row.candidate_ref} className="space-y-2">
              <p className="font-medium">{itemName(row)}</p>
              <dl className="space-y-2">{changes.map((field) => <div key={field}>
                <dt className="text-xs text-muted">{planT(`fields.${planFields[field]}`)}</dt>
                <dd className="grid gap-2 sm:grid-cols-2 reading-copy"><span>{t("beforeValue", { value: planValue(field, planField(before, field)) })}</span><span>{t("afterValue", { value: planValue(field, planField(row.state, field)) })}</span></dd>
              </div>)}</dl>
            </div>)}
            {kind === "characters" && <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={adoptedChanges === changeKey} disabled={readOnly} onChange={(event) => setAdoptedChanges(event.target.checked ? changeKey : "")} />{t("adoptPlanChanges", { count: planChanges.length })}</label>}
          </section>}
          {loading ? <p role="status">{t("loading")}</p> : retainedDraft ? <section className="space-y-3">
            <p role="status">{t("retainedDraft")}</p>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({ ...retainedDraft, command: command.current }, null, 2)}</pre>
          </section> : !preview ? <>
            <TaskFlowForm toolbarActions={<Button size="sm" variant="ghost" isDisabled={running || refreshing} onPress={() => void refreshSources()}>{t("refreshSources")}</Button>} flow={flow} disabled={running || refreshing} showError={error !== flow.error} fieldChoices={{ selected_existing_ids: kind === "characters" ? availableCharacters.map((item) => ({ value: item.character_id, label: item.name })) : availableFactions.map((item) => ({ value: item.faction_id, label: item.name })) }} />
          </> : <div className="@container min-h-0 shrink-0 @min-[800px]/volumeCandidates:flex-1 @min-[800px]/volumeCandidates:shrink">
            <div className="grid min-h-0 min-w-0 gap-6 @min-[800px]/volumeCandidates:h-full @min-[800px]/volumeCandidates:grid-cols-[240px_minmax(0,1fr)]">
            <nav aria-label={t("candidates", { count: candidates.length })} tabIndex={0} className="workspace-scrollbar min-h-0 min-w-0 max-h-64 overflow-y-auto space-y-2 border-b border-border pb-4 @min-[800px]/volumeCandidates:max-h-none @min-[800px]/volumeCandidates:border-r @min-[800px]/volumeCandidates:border-b-0 @min-[800px]/volumeCandidates:pr-4">
              <p className="text-xs font-medium text-muted">{t("candidates", { count: candidates.length })}</p>
              {candidates.map((item) => <button key={item.candidate_ref} type="button" aria-label={itemName(item)} aria-pressed={selected?.candidate_ref === item.candidate_ref} disabled={locked} onClick={() => setSelectedRef(item.candidate_ref)} className={`min-h-11 w-full rounded-lg px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-accent ${selected?.candidate_ref === item.candidate_ref ? "bg-selected text-foreground" : "hover:bg-surface-raised"}`}>
                <span className="block break-words font-medium">{itemName(item)}</span><span className="text-xs text-muted">{t(item.profile ? "new" : "existing")}</span>
              </button>)}
              <Button size="sm" variant="ghost" isDisabled={readOnly || !selected} onPress={() => { if (!selected) return; setPreview({ ...preview, candidate: { [kind]: candidates.filter((item) => item.candidate_ref !== selected.candidate_ref) } }); setSelectedRef(""); }}>{t("remove")}</Button>
            </nav>
            {selected && <div key={selected.candidate_ref} className="workspace-scrollbar min-h-0 min-w-0 space-y-8 @min-[800px]/volumeCandidates:overflow-y-auto">
              {kind === "characters" ? <>
                {(selected as VolumeCharacterCandidate).profile && <CharacterProfileForm designOnly value={volumeCharacterDesignForm((selected as VolumeCharacterCandidate).profile!)} disabled={readOnly} fieldErrors={fieldErrors("profile")} t={characterT} onChange={(profile) => updateCandidate({ ...selected as VolumeCharacterCandidate, profile: editVolumeCharacterDesign((selected as VolumeCharacterCandidate).profile!, profile) })} />}
                {(selected as VolumeCharacterCandidate).profile && <section aria-label={t("characters.initialFacts")} className="space-y-5 border-t border-border pt-6"><h3 className="text-sm font-semibold">{t("characters.initialFacts")}</h3><CharacterFactFieldsEditor values={(selected as VolumeCharacterCandidate).initial_facts ?? {}} disabled={readOnly} fieldErrors={fieldErrors("initial_facts")} onChange={(initial_facts) => updateCandidate({ ...selected as VolumeCharacterCandidate, initial_facts })} /></section>}
                <div className="border-t border-border pt-6"><CharacterVolumeStateForm value={(selected as VolumeCharacterCandidate).state} characterId={(selected as VolumeCharacterCandidate).character_id ?? ""} relations={formalRelations} characterNames={new Map(formalCharacters.map((item) => [item.character_id, item.name]))} disabled={readOnly} fieldErrors={fieldErrors("state")} errorIdPrefix={`volume-character-${selected.candidate_ref}`} autoFocusCurrentGoal={false} onChange={(state) => updateCandidate({ ...selected as VolumeCharacterCandidate, state })} /></div>
              </> : <>
                {(selected as VolumeFactionCandidate).profile && <VolumeFactionProfileForm value={(selected as VolumeFactionCandidate).profile!} factions={availableFactions} disabled={readOnly} errors={fieldErrors("profile")} onChange={(profile) => updateCandidate({ ...selected as VolumeFactionCandidate, profile })} />}
                {(selected as VolumeFactionCandidate).profile && <section aria-label={t("factions.initialFacts")} className="space-y-5 border-t border-border pt-6"><h3 className="text-sm font-semibold">{t("factions.initialFacts")}</h3><FactionFactFieldsEditor disabled={readOnly} values={volumeFactionFacts(selected as VolumeFactionCandidate)} onChange={(field, value) => updateCandidate(editVolumeFactionFact(selected as VolumeFactionCandidate, field, value))} /></section>}
                <div className="border-t border-border pt-6"><FactionVolumeStateForm planOnly value={(selected as VolumeFactionCandidate).state} disabled={readOnly} fieldErrors={fieldErrors("state")} errorIdPrefix={`volume-faction-${selected.candidate_ref}`} autoFocusCurrentGoal={false} onChange={(state) => updateCandidate({ ...selected as VolumeFactionCandidate, state })} /></div>
              </>}
            </div>}
            </div>
          </div>}
          {!retainedDraft && <TaskFlowProgress flow={flow} running={running} failed={Boolean(error) && !preview} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={() => { void flow.discard(); setError(""); }} />}
        </div>
        <footer className="shrink-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
          <Button size="sm" variant="ghost" isDisabled={locked || draftConflict} onPress={() => { if (running) cancelGeneration(); else void close(); }}>{running ? t("cancel") : t("closeKeep")}</Button>
          {draftConflict && !preview && <Button size="sm" variant="ghost" onPress={onClose}>{t("close")}</Button>}
          {(preview || retainedDraft) && <Button size="sm" variant="ghost" isDisabled={locked} onPress={() => { exportDraft(); if (draftConflict) onClose(); }}>{t(draftConflict ? "draftConflictExport" : "export")}</Button>}
          {preview && command.current?.unknown === false && (kind === "characters" || !stale) && <Button size="sm" variant="outline" isDisabled={locked || draftConflict} onPress={() => void revise()}>{t("reviseRejected")}</Button>}
          {preview && <Button size="sm" variant="outline" isDisabled={locked || draftConflict || Boolean(command.current && command.current.unknown !== false)} onPress={() => void discard()}>{t("discard")}</Button>}
          {retainedDraft && (!command.current || command.current.unknown === false) && <Button size="sm" variant="outline" isDisabled={locked || draftConflict} onPress={() => void discard()}>{t("regenerateRetained")}</Button>}
          {(!retainedDraft || command.current) && <Button size="sm" variant="primary" isDisabled={loading || !restored || running || locked || draftConflict || refreshing || legacyFactionCandidate || planReviewBlocked || (!retryOnly && (preview ? stale : flow.loading || !flow.definition))} onPress={() => void (preview || command.current ? confirm() : generate())}>{saving ? t("saving") : retryOnly ? t("retrySave") : preview ? t("confirm") : t("generate")}</Button>}
        </footer>
  </section>;
}
