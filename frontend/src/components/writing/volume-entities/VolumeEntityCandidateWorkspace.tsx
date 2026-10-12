"use client";

import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";
import { RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import type { GenerationParamsValue } from "@/components/shared/GenerationParamsCollapse";
import { TaskFlowForm, TaskFlowProgress } from "@/components/task-flows/TaskFlowForm";
import type { TaskFlowRunMode } from "@/types/taskFlow";
import { useTaskFlow } from "@/hooks/useTaskFlow";
import { apiGet, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { CharacterProfileFields, CharacterRelationResponseV1, CharacterResponseV1 } from "@/types/character";
import type { CoreFaction } from "@/types/novel";
import type { FlowRef } from "@/types/taskFlow";
import type { VolumeReadV2 } from "@/types/volume";
import type { CharacterVolumePlanFieldsV1, CharacterVolumeStateReadV1 } from "@/types/characterVolumeState";
import { parseVolumeEntityPreview, type VolumeCharacterCandidate, type VolumeEntityCandidate, type VolumeEntityConfirmResult, type VolumeEntityKind, type VolumeEntityPreview, type VolumeFactionCandidate } from "@/types/volumeEntity";
import CharacterProfileForm from "../characters/forms/CharacterProfileForm";
import CharacterVolumeStateForm from "../characters/CharacterVolumeStateForm";
import FactionVolumeStateForm from "../factions/FactionVolumeStateForm";
import VolumeFactionProfileForm from "./VolumeFactionProfileForm";
import { readCharacterVolumeCandidateDraft, writeCharacterVolumeCandidateDraft, type CharacterVolumeCandidateEntry, type CharacterVolumeCandidateResolution } from "./characterVolumeCandidateDrafts";

interface EntityDraft {
  preview: VolumeEntityPreview | null;
  flow_ref: FlowRef | null;
  inputs: Record<string, unknown>;
  params: GenerationParamsValue;
  command: { payload: string; key: string; unknown?: boolean } | null;
  stale: boolean;
  completed?: true;
}

// 本地存储暂时不可用时，关闭重开也不能再次确认已知成功的原请求。
const confirmedCommands = new Set<string>();

/** 功能：生成、审核并确认当前卷的新档案及参与状态。Args: props 当前卷、正式对象和保存回调。Returns: 两种实体共用的候选审核弹窗；生成和审核不写作品。 */
export default function VolumeEntityCandidateWorkspace({ kind, novelId, volume, characters, factions, relations, onClose, onSaved, adoptionOpen = false }: {
  kind: VolumeEntityKind; novelId: string; volume: VolumeReadV2;
  characters: CharacterResponseV1[]; factions: CoreFaction[]; relations: CharacterRelationResponseV1[];
  onClose: () => void; onSaved: (result: VolumeEntityConfirmResult, names: Record<string, string>) => void;
  onAdoptCharacter?: (profile: CharacterProfileFields, candidateRef: string) => Promise<void>;
  onAdoptPlan?: (characterId: string, fields: CharacterVolumePlanFieldsV1) => Promise<void>;
  adoptionOpen?: boolean;
}) {
  const t = useTranslations("writing.volumeEntitiesAi");
  const planT = useTranslations("writing.characterVolumeStates");
  const characterT = useTranslations("writing.characters");
  const flow = useTaskFlow(`create_${kind}_for_volume_by_ai`);
  const { loading: flowLoading, select: selectFlow, setInputs, setParams } = flow;
  const [preview, setPreview] = useState<VolumeEntityPreview | null>(null);
  const [selectedRef, setSelectedRef] = useState("");
  const [running, setRunning] = useState(false);
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
  const [planSnapshot, setPlanSnapshot] = useState<{ source: string; rows: CharacterVolumeStateReadV1[] } | null>(null);
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
  const readOnly = locked || stale || draftConflict || Boolean(command.current);
  const availableCharacters = formalCharacters.filter((item) => !item.is_deleted && item.status === "active");
  const availableFactions = formalFactions.filter((item) => !item.is_deleted && item.active_status === "active" && (item.level_type === "core" || item.volume_id === volume.volume_id));
  const names = new Map(kind === "characters" ? formalCharacters.map((item) => [item.character_id, item.name]) : formalFactions.map((item) => [item.faction_id, item.name]));
  const fieldErrors = (prefix: string) => Object.fromEntries(Object.entries(errors)
    .filter(([field]) => field.startsWith(`candidates.${selectedIndex}.${prefix}.`))
    .map(([field, messages]) => [field.slice(`candidates.${selectedIndex}.${prefix}.`.length), messages]));
  const itemName = (item: VolumeEntityCandidate) => item.profile?.name ?? names.get("character_id" in item ? item.character_id! : item.faction_id!) ?? t("existing");
  const existingPlans = kind === "characters" ? (candidates as VolumeCharacterCandidate[]).filter((row) => row.character_id && row.state_expected_version !== null) : [];
  const planSource = JSON.stringify(existingPlans.map((row) => [row.character_id, row.state_expected_version]));
  useEffect(() => {
    if (planSource === "[]" || retryOnly) return;
    let active = true;
    setPlanError("");
    void apiGet<{ data: CharacterVolumeStateReadV1[] }>(`/api/character-volume-states/novel/${novelId}/volume/${volume.volume_id}`)
      .then((response) => {
        const expected = JSON.parse(planSource) as [string, number][];
        if (!Array.isArray(response.data) || expected.some(([id, expectedVersion]) => !response.data.some((row) => row.character_id === id && row.version === expectedVersion && !row.is_deleted))) throw new Error(t("planChanged"));
        if (active) setPlanSnapshot({ source: planSource, rows: response.data });
      }).catch((failure) => { if (active) setPlanError(failure instanceof Error ? failure.message : t("loadFailed")); });
    return () => { active = false; };
  }, [novelId, volume.volume_id, planSource, retryOnly, t]);
  const planFields = { participation_scope: "participationScope", current_goal: "currentGoal", start_state: "startState", planned_end_state: "plannedEndState", relationship_focus_ids: "relationshipFocus", arc_progress: "arcProgress" } as const;
  const planChanges = existingPlans.flatMap((row) => {
    const before = planSnapshot?.source === planSource ? planSnapshot.rows.find((saved) => saved.character_id === row.character_id) : undefined;
    if (!before) return [];
    const changes = (Object.keys(planFields) as (keyof CharacterVolumePlanFieldsV1)[]).filter((field) => JSON.stringify(before[field]) !== JSON.stringify(row.state[field]));
    return changes.length ? [{ row, before, changes }] : [];
  });
  const changeKey = JSON.stringify(planChanges.map(({ row, before, changes }) => [row.character_id, before.version, changes.map((field) => [field, before[field], row.state[field]])]));
  const planReviewBlocked = !retryOnly && existingPlans.length > 0 && (Boolean(planError) || planSnapshot?.source !== planSource || planChanges.length > 0 && adoptedChanges !== changeKey);
  const planValue = (field: keyof CharacterVolumePlanFieldsV1, value: CharacterVolumePlanFieldsV1[keyof CharacterVolumePlanFieldsV1]) => {
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
        const savedPreview = stored.value.preview;
        if (savedPreview && !parseVolumeEntityPreview(savedPreview, kind, novelId, volume.volume_id)) throw new Error(t("invalidResult"));
        setPreview(savedPreview); setup.current = stored.value; command.current = stored.value.command; version.current = stored.base_version;
        setStale(stored.value.stale || Boolean(savedPreview && !savedPreview.basis.content_fingerprint && !stored.value.command && stored.base_version !== initialVersion.current));
      } else setRestored(true);
    }).catch((failure) => { if (active) { setStorageError(failure instanceof Error ? failure.message : t("draftFailed")); setRestored(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; activeSession.current = null; controller.current?.abort(); };
  }, [key, kind, novelId, volume.volume_id, t, saveLocalDraft]);

  useEffect(() => {
    if (loading || flowLoading || !setup.current) return;
    const session = activeSession.current;
    const stored = setup.current; setup.current = null;
    void (async () => {
      if (stored.flow_ref) await selectFlow(stored.flow_ref);
      if (activeSession.current !== session) return;
      setInputs(stored.inputs); setParams(stored.params); setRestored(true);
    })();
  }, [loading, flowLoading, selectFlow, setInputs, setParams]);

  useEffect(() => {
    if (loading || saving || !restored || completed || cleanupVersion.current !== null || blockedDraft.current) return;
    const draft: EntityDraft = { preview, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null, inputs: flow.inputs, params: flow.params, command: command.current, stale };
    const draftVersion = version.current;
    writes.current = writes.current.then(() => {
      if (blockedDraft.current) throw new Error(t("draftConflict"));
      return saveLocalDraft(draftVersion, draft);
    }).catch((failure) => setStorageError(failure instanceof Error ? failure.message : t("draftFailed")));
  }, [key, loading, saving, restored, completed, preview, flow.definition, flow.inputs, flow.params, stale, t, saveLocalDraft]);

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
    if (controller.current || running) return;
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
    setPreview({ ...preview, candidate: { [kind]: candidates.map((old) => old.candidate_ref === item.candidate_ref ? item : old) } });
    setErrors({});
  };

  const confirm = async () => {
    if (!preview || locked || blockedDraft.current || planReviewBlocked || stale && !retryOnly || completed) return;
    const original = command.current;
    const request = original ? JSON.parse(original.payload) : kind === "characters" ? {
      contract: "participation_plan_v1", basis: preview.basis,
      candidates: (candidates as VolumeCharacterCandidate[]).map((row) => ({
        ...row, state: { participation_scope: row.state.participation_scope, current_goal: row.state.current_goal,
          start_state: row.state.start_state, planned_end_state: row.state.planned_end_state,
          relationship_focus_ids: row.state.relationship_focus_ids, arc_progress: row.state.arc_progress },
      })),
    } : { candidates, basis: preview.basis };
    const payload = JSON.stringify(request);
    if (original && original.payload !== payload) { setError(t("retryConfirmation")); return; }
    setSaving(true); setError(""); setErrors({});
    const session = activeSession.current;
    const pendingCommand = original ? { ...original, unknown: true } : { payload, key: crypto.randomUUID(), unknown: true };
    command.current = pendingCommand;
    const draftVersion = version.current;
    const draft: EntityDraft = { preview, flow_ref: flow.definition ? { id: flow.definition.id, revision: flow.definition.revision } : null, inputs: flow.inputs, params: flow.params, command: pendingCommand, stale };
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
      result = await apiPost<VolumeEntityConfirmResult>(`/api/novels/${novelId}/volumes/${volume.volume_id}/${kind}/confirm`, request, { headers: { "Idempotency-Key": pendingCommand.key } });
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

  const close = async () => {
    controller.current?.abort();
    await writes.current;
    if (blockedDraft.current) { setStorageError(t("draftConflict")); return; }
    onClose();
  };
  const exportDraft = () => {
    const blob = new Blob([JSON.stringify(preview, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = `${volume.title}-${kind}-candidate.json`; link.click(); URL.revokeObjectURL(url);
  };
  const revise = async () => {
    if (locked || command.current?.unknown !== false) return;
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
      await flow.discard(); command.current = null; setPreview(null); setStale(false); setError(""); setErrors({});
      version.current = currentVolume.version;
    } catch (failure) { setStorageError(failure instanceof Error ? failure.message : t("draftFailed")); }
  };

  if (completed) return null;
  return <RetainedModalBackdrop isOpen onOpenChange={(open) => { if (!open && !locked) void close(); }} isDismissable={!locked && !draftConflict} isKeyboardDismissDisabled={locked || draftConflict}>
    <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
      <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-5xl">
        <Modal.Header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-7">
          <Modal.Heading className="text-lg font-semibold">{t(`${kind}.title`)} · {volume.title}</Modal.Heading>
          <Modal.CloseTrigger aria-label={t("close")} isDisabled={locked || draftConflict} />
        </Modal.Header>
        <Modal.Body className="workspace-scrollbar min-h-0 px-5 py-5 sm:px-7">
          {error && <RelationEditorErrorSummary message={error} fieldErrors={errors} className="mb-4" />}
          {storageError && <p role="alert" className="mb-4 border-y border-danger/40 py-3 text-sm text-danger">{storageError}</p>}
          {stale && <p role="alert" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("stale")}</p>}
          {preview && kind === "characters" && <p className="mb-3 text-sm text-muted">{t("characterStart", { title: volume.title })}</p>}
          {retryOnly && command.current?.unknown !== false && !saving && <p role="status" className="mb-4 border-y border-amber-500/50 py-3 text-sm">{t("retryConfirmation")}</p>}
          {!retryOnly && planError && <p role="alert" className="mb-4 text-danger">{planError}</p>}
          {!retryOnly && planChanges.length > 0 && <section aria-label={t("planChanges", { count: planChanges.length })} className="mb-5 space-y-3 border-y border-border py-4">
            <h3 className="text-sm font-semibold">{t("planChanges", { count: planChanges.length })}</h3>
            {planChanges.map(({ row, before, changes }) => <div key={row.candidate_ref} className="space-y-2">
              <p className="font-medium">{itemName(row)}</p>
              <dl className="space-y-2">{changes.map((field) => <div key={field}>
                <dt className="text-xs text-muted">{planT(`fields.${planFields[field]}`)}</dt>
                <dd className="grid gap-2 sm:grid-cols-2 reading-copy"><span>{t("beforeValue", { value: planValue(field, before[field]) })}</span><span>{t("afterValue", { value: planValue(field, row.state[field]) })}</span></dd>
              </div>)}</dl>
            </div>)}
            <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={adoptedChanges === changeKey} disabled={readOnly} onChange={(event) => setAdoptedChanges(event.target.checked ? changeKey : "")} />{t("adoptPlanChanges", { count: planChanges.length })}</label>
          </section>}
          {loading ? <p role="status">{t("loading")}</p> : !preview ? <>
            <div className="mb-4 flex justify-end"><Button size="sm" variant="ghost" isDisabled={running || refreshing} onPress={() => void refreshSources()}>{t("refreshSources")}</Button></div>
            <TaskFlowForm flow={flow} disabled={running || refreshing} showError={error !== flow.error} fieldChoices={{ selected_existing_ids: kind === "characters" ? availableCharacters.map((item) => ({ value: item.character_id, label: item.name })) : availableFactions.map((item) => ({ value: item.faction_id, label: item.name })) }} />
          </> : <div className="@container">
            <div className="grid min-w-0 gap-6 @min-[800px]:grid-cols-[240px_minmax(0,1fr)]">
            <nav aria-label={t("candidates", { count: candidates.length })} className="min-w-0 space-y-2 border-b border-border pb-4 @min-[800px]:border-r @min-[800px]:border-b-0 @min-[800px]:pr-4">
              <p className="text-xs font-medium text-muted">{t("candidates", { count: candidates.length })}</p>
              {candidates.map((item) => <button key={item.candidate_ref} type="button" aria-label={itemName(item)} aria-pressed={selected?.candidate_ref === item.candidate_ref} disabled={locked} onClick={() => setSelectedRef(item.candidate_ref)} className={`min-h-11 w-full rounded-lg px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-accent ${selected?.candidate_ref === item.candidate_ref ? "bg-selected text-foreground" : "hover:bg-surface-raised"}`}>
                <span className="block break-words font-medium">{itemName(item)}</span><span className="text-xs text-muted">{t(item.profile ? "new" : "existing")}</span>
              </button>)}
              <Button size="sm" variant="ghost" isDisabled={readOnly || !selected} onPress={() => { if (!selected) return; setPreview({ ...preview, candidate: { [kind]: candidates.filter((item) => item.candidate_ref !== selected.candidate_ref) } }); setSelectedRef(""); }}>{t("remove")}</Button>
            </nav>
            {selected && <div key={selected.candidate_ref} className="min-w-0 space-y-8">
              {kind === "characters" ? <>
                {(selected as VolumeCharacterCandidate).profile && <CharacterProfileForm value={(selected as VolumeCharacterCandidate).profile!} disabled={readOnly} fieldErrors={fieldErrors("profile")} t={characterT} onChange={(profile) => updateCandidate({ ...selected as VolumeCharacterCandidate, profile: { ...(selected as VolumeCharacterCandidate).profile!, ...profile } })} />}
                <div className="border-t border-border pt-6"><CharacterVolumeStateForm value={(selected as VolumeCharacterCandidate).state} characterId={(selected as VolumeCharacterCandidate).character_id ?? ""} relations={formalRelations} characterNames={new Map(formalCharacters.map((item) => [item.character_id, item.name]))} disabled={readOnly} fieldErrors={fieldErrors("state")} errorIdPrefix={`volume-character-${selected.candidate_ref}`} autoFocusCurrentGoal={false} onChange={(state) => updateCandidate({ ...selected as VolumeCharacterCandidate, state })} /></div>
              </> : <>
                {(selected as VolumeFactionCandidate).profile && <VolumeFactionProfileForm value={(selected as VolumeFactionCandidate).profile!} factions={availableFactions} disabled={readOnly} errors={fieldErrors("profile")} onChange={(profile) => updateCandidate({ ...selected as VolumeFactionCandidate, profile })} />}
                <div className="border-t border-border pt-6"><FactionVolumeStateForm value={(selected as VolumeFactionCandidate).state} disabled={readOnly} fieldErrors={fieldErrors("state")} errorIdPrefix={`volume-faction-${selected.candidate_ref}`} autoFocusCurrentGoal={false} onChange={(state) => updateCandidate({ ...selected as VolumeFactionCandidate, state })} /></div>
              </>}
            </div>}
            </div>
          </div>}
          <TaskFlowProgress flow={flow} running={running} failed={Boolean(error) && !preview} onRetry={() => void generate(true)} onContinue={(additionalRounds) => void generate({ continuation: true, additionalRounds })} onDiscard={() => { void flow.discard(); setError(""); }} />
        </Modal.Body>
        <Modal.Footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
          <Button size="sm" variant="ghost" isDisabled={locked || draftConflict} onPress={() => void close()}>{running ? t("cancel") : t("closeKeep")}</Button>
          {draftConflict && !preview && <Button size="sm" variant="ghost" onPress={onClose}>{t("close")}</Button>}
          {preview && <Button size="sm" variant="ghost" isDisabled={locked} onPress={() => { exportDraft(); if (draftConflict) onClose(); }}>{t(draftConflict ? "draftConflictExport" : "export")}</Button>}
          {preview && command.current?.unknown === false && (kind === "characters" || !stale) && <Button size="sm" variant="outline" isDisabled={locked || draftConflict} onPress={() => void revise()}>{t("reviseRejected")}</Button>}
          {preview && <Button size="sm" variant="outline" isDisabled={locked || draftConflict || Boolean(command.current && command.current.unknown !== false)} onPress={() => void discard()}>{t("discard")}</Button>}
          <Button size="sm" variant="primary" isDisabled={loading || !restored || running || locked || draftConflict || refreshing || planReviewBlocked || (preview ? stale && !retryOnly : flow.loading || !flow.definition)} onPress={() => void (preview ? confirm() : generate())}>{saving ? t("saving") : preview ? retryOnly ? t("retrySave") : t("confirm") : t("generate")}</Button>
        </Modal.Footer>
      </Modal.Dialog>
    </Modal.Container>
  </RetainedModalBackdrop>;
}
