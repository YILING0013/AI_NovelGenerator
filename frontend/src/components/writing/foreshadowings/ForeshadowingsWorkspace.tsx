"use client";

import { Button, Modal } from "@heroui/react";
import { useCallback, useContext, useEffect, useId, useRef, useState, type RefObject } from "react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import DocumentSection from "@/components/shared/DocumentSection";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import DraftChip from "@/components/shared/DraftChip";
import SectionEditButton, { SectionActionButton } from "@/components/shared/SectionEditButton";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import { ConfirmActionModal, RelationEditorErrorSummary, focusRelationEditorError } from "@/components/shared/RelationEditorPrimitives";
import { apiGet, apiPatch, apiPost, ApiRequestError, type ApiFieldErrors } from "@/lib/api";
import type { HierarchyRecord } from "@/types/hierarchy";
import { FORESHADOWING_TRANSITIONS, type Foreshadowing, type ForeshadowingEvidence, type ForeshadowingPlan, type ForeshadowingPosition } from "@/types/foreshadowing";
import { readForeshadowingDrafts, writeForeshadowingDraft, type ForeshadowingDraft } from "./foreshadowingDrafts";
import EvidencePicker, { FORESHADOWING_INPUT as INPUT } from "./EvidencePicker";
import { useAssistantFocus, useAssistantResource } from "../assistant/AssistantContext";

type PositionChoice = ForeshadowingPosition & { title: string };
const EMPTY_PLAN: ForeshadowingPlan = { title: "", content: "", target_effect: "", planting_position: null, resolution_position: null };
const PLAN_FIELDS = ["title", "content", "target_effect", "planting_position", "resolution_position"] as const;
const COMPARISON_FIELDS = [...PLAN_FIELDS, "status", "planted_evidence", "resolved_evidence"] as const;

/** 功能：显示伏笔名册、计划、作者记录及回收站；删书后只提供逐条清理。Args: props 小说范围、回收站模式及脏稿通知。Returns: 实体主从工作台。 */
export default function ForeshadowingsWorkspace({ novelId, cleanupOnly = false, initialView = "active", requestedId = null, onLocationChange, onDirtyChange, onBusyChange, beforeLeaveRef }: {
  novelId: string; cleanupOnly?: boolean; onDirtyChange?: (dirty: boolean) => void; onBusyChange?: (busy: boolean) => void;
  beforeLeaveRef?: RefObject<(() => Promise<void>) | null>;
  initialView?: "active" | "trash"; requestedId?: string | null; onLocationChange?: (view: "active" | "trash", id: string | null) => void;
}) {
  const t = useTranslations("writing.foreshadowings");
  const draftT = useTranslations("writing.characterFacts");
  const active = useContext(RetainedViewActive);
  const id = useId();
  const scope = `${novelId}:foreshadowings`;
  const base = `/api/foreshadowings/novel/${novelId}`;
  const [view, setView] = useState<string>(initialView);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [position, setPosition] = useState("");
  const [positions, setPositions] = useState<PositionChoice[]>([]);
  const [chapters, setChapters] = useState<HierarchyRecord[]>([]);
  const [structureError, setStructureError] = useState("");
  const [rows, setRows] = useState<Foreshadowing[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(requestedId);
  const [mobileDetail, setMobileDetail] = useState(Boolean(requestedId));
  const [collapsed, setCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [drafts, setDrafts] = useState<ForeshadowingDraft[]>([]);
  const [draft, setDraft] = useState<ForeshadowingDraft | null>(null);
  const [editorError, setEditorError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [localError, setLocalError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [reference, setReference] = useState<ForeshadowingEvidence | null>(null);
  const [currentResult, setCurrentRead] = useState<{ editorId: string; value: Foreshadowing } | null>(null);
  const [mergeChoices, setMergeChoices] = useState<Partial<Record<typeof COMPARISON_FIELDS[number], "current" | "draft">>>({});
  const [readMessage, setReadMessage] = useState("");
  const [leave, setLeave] = useState<(() => void) | null>(null);
  const detailRef = useRef<HTMLElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<ForeshadowingDraft | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const persisted = useRef(new Map<string, number>());
  const pending = useRef(false);
  const epoch = useRef(0);
  const listEpoch = useRef(0);
  const readEpoch = useRef(0);
  const internalLocation = useRef<{ view: string; id: string | null } | null>(null);
  const context = useRef({ active, selectedId, view }); context.current = { active, selectedId, view };
  const selected = rows.find((row) => row.foreshadowing_id === selectedId) ?? null;
  const currentRead = currentResult && currentResult.editorId === draft?.key ? currentResult.value : null;
  const draftValues = draft && { ...draft.plan, status: draft.status, planted_evidence: draft.planted_evidence, resolved_evidence: draft.resolved_evidence };
  const mergeFields = draft?.source && draftValues ? COMPARISON_FIELDS.filter((field) => (draft.mode === "plan" ? PLAN_FIELDS.some((planField) => planField === field) : draft.mode === "records" && !PLAN_FIELDS.some((planField) => planField === field)) && JSON.stringify(draftValues[field]) !== JSON.stringify(draft.source![field])) : [];
  const blocked = saving || Boolean(draft?.command);
  const planChanged = draft?.mode === "plan" && (!draft.source || PLAN_FIELDS.some((field) => JSON.stringify(draft.plan[field]) !== JSON.stringify(draft.source![field])));
  const invalidMergeStatus = draft?.mode === "records" && currentRead && mergeChoices.status === "draft" && !FORESHADOWING_TRANSITIONS[currentRead.status].includes(draft.status);
  useAssistantResource(!cleanupOnly && selected ? { resource_type: "foreshadowing", id: selected.foreshadowing_id, name: selected.title, version: selected.version, draft: draft?.source?.foreshadowing_id === selected.foreshadowing_id ? { text: JSON.stringify(draftValues), fields: draft.mode === "plan" ? [...PLAN_FIELDS] : ["status", "planted_evidence", "resolved_evidence"], version: draft.source.version } : undefined } : null);
  useAssistantFocus("foreshadowing", (target) => {
    if (pending.current || draftRef.current) return false;
    // 同一对象也可能被旧筛选隐藏；每次助手导航序号都重新显示目标。
    epoch.current += 1; setQ(""); setStatus(""); setPosition(""); setView(initialView); setSelectedId(target.id); setMobileDetail(true); setCurrentRead(null); setMergeChoices({}); setReadMessage("");
  });
  useEffect(() => { if (active) {
    const internal = internalLocation.current?.id === requestedId && internalLocation.current.view === initialView;
    internalLocation.current = null;
    epoch.current += 1; setView(initialView); setSelectedId(requestedId); setMobileDetail(Boolean(requestedId)); setCurrentRead(null); setMergeChoices({}); setReadMessage("");
    if (!internal) { setQ(""); setStatus(""); setPosition(""); }
  } }, [active, initialView, requestedId]);

  const readDrafts = useCallback(async () => {
    try { setDrafts(await readForeshadowingDrafts(scope)); }
    catch { setLocalError(t("localFailed")); }
  }, [scope, t]);

  useEffect(() => { if (active) void readDrafts(); }, [active, readDrafts, refresh]);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); const request = ++listEpoch.current;
    const params = new URLSearchParams({ deleted: String(view === "trash"), include_deleted_novel: String(cleanupOnly) });
    if (q.trim()) params.set("q", q.trim());
    if (status) params.set("status", status);
    if (position) { const [kind, identity] = position.split(":"); params.set("position_kind", kind); params.set("position_id", identity); }
    setLoading(true); setError("");
    apiGet<Foreshadowing[]>(`${base}?${params}`, { signal: abort.signal }).then((result) => {
      if (abort.signal.aborted || request !== listEpoch.current) return;
      if (result.some((row) => row.novel_id !== novelId || row.is_deleted !== (view === "trash"))) throw new Error(t("wrongScope"));
      // needs_review 与业务版本无关；同版本刷新也替换服务器警告。
      setRows(result);
    }).catch((failure) => { if (!abort.signal.aborted && request === listEpoch.current) setError(failure.message); })
      .finally(() => { if (!abort.signal.aborted && request === listEpoch.current) setLoading(false); });
    return () => { abort.abort(); listEpoch.current += 1; };
  }, [active, base, novelId, cleanupOnly, view, q, status, position, refresh, t]);

  useEffect(() => {
    if (cleanupOnly || !active) return;
    const abort = new AbortController();
    const load = async () => {
      try {
        const volumes = (await apiGet<{ data: HierarchyRecord[] }>(`/api/volumes/novel/${novelId}`, { signal: abort.signal })).data;
        const arcs = (await Promise.all(volumes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/arcs/volume/${row.volume_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
        const scenes = (await Promise.all(arcs.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/scenes/arc/${row.arc_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
        const chapterRows = (await Promise.all(scenes.map((row) => apiGet<{ data: HierarchyRecord[] }>(`/api/chapters/scene/${row.scene_id}`, { signal: abort.signal })))).flatMap((page) => page.data);
        if (abort.signal.aborted) return;
        if ([...volumes, ...arcs, ...scenes, ...chapterRows].some((row) => row.novel_id !== novelId || row.is_deleted)) throw new Error(t("wrongScope"));
        setPositions([
          ...volumes.map((row) => ({ kind: "volume" as const, id: row.volume_id, title: row.title })),
          ...arcs.map((row) => ({ kind: "arc" as const, id: row.arc_id!, title: `${volumes.find((parent) => parent.volume_id === row.volume_id)?.title} / ${row.title}` })),
          ...scenes.map((row) => ({ kind: "scene" as const, id: row.scene_id!, title: `${arcs.find((parent) => parent.arc_id === row.arc_id)?.title} / ${row.title}` })),
        ]); setChapters(chapterRows); setStructureError("");
      } catch (failure) { if (!abort.signal.aborted) setStructureError((failure as Error).message); }
    };
    void load(); return () => abort.abort();
  }, [active, novelId, cleanupOnly, refresh, t]);

  useEffect(() => { if (active) onDirtyChange?.(Boolean(draft)); return () => onDirtyChange?.(false); }, [draft, active, onDirtyChange]);
  useEffect(() => () => { epoch.current += 1; readEpoch.current += 1; context.current.active = false; }, []);
  useEffect(() => { onBusyChange?.(saving); return () => onBusyChange?.(false); }, [saving, onBusyChange]);
  useEffect(() => {
    if (!active || !beforeLeaveRef) return;
    beforeLeaveRef.current = async () => { await queue.current; if (pending.current) throw new Error(t("saving")); epoch.current += 1; setDraft(null); draftRef.current = null; setConfirm(false); };
    return () => { beforeLeaveRef.current = null; };
  }, [active, beforeLeaveRef, t]);
  useEffect(() => {
    if (!draft || !active) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [draft, active]);

  // 每个编辑器只写自己的 ID；串行写入和事务内 CAS 让迟到写入不能覆盖或清理新稿。
  const persist = (next: ForeshadowingDraft) => {
    const write = queue.current.catch(() => {}).then(async () => {
      const receipt = await writeForeshadowingDraft(scope, next, persisted.current.get(next.key) ?? null);
      persisted.current.set(next.key, next.revision);
      return receipt;
    });
    queue.current = write;
    void write.then(() => setLocalError(""), () => setLocalError(t("localFailed")));
    return write;
  };
  const changeDraft = (next: ForeshadowingDraft) => {
    const updated = { ...next, revision: (draftRef.current?.revision ?? 0) + 1 };
    draftRef.current = updated; setDraft(updated); void persist(updated);
  };
  const openDraft = (source: Foreshadowing | null, mode: ForeshadowingDraft["mode"], restored?: ForeshadowingDraft) => {
    epoch.current += 1; setEditorError(""); setFieldErrors({}); setReadMessage(""); setCurrentRead(null); setMergeChoices({}); setConfirm(false);
    const next: ForeshadowingDraft = restored ? { ...restored, key: crypto.randomUUID(), revision: 1 } : {
      key: crypto.randomUUID(), revision: 1, source, mode,
      plan: source ? { title: source.title, content: source.content, target_effect: source.target_effect, planting_position: source.planting_position, resolution_position: source.resolution_position } : { ...EMPTY_PLAN },
      status: source?.status ?? "planned", planted_evidence: source?.planted_evidence ?? null, resolved_evidence: source?.resolved_evidence ?? null,
    };
    draftRef.current = next; setDraft(next); void persist(next);
    if (source) { setSelectedId(source.foreshadowing_id); setMobileDetail(true); }
    if (["delete", "restore", "hard-delete"].includes(mode)) setConfirm(true);
  };
  const closeEditor = async () => {
    if (pending.current) return;
    try { if (draftRef.current) await persist(draftRef.current); epoch.current += 1; setDraft(null); draftRef.current = null; setConfirm(false); setEditorError(""); await readDrafts(); }
    catch { setEditorError(t("localFailed")); }
  };
  const discardEditor = async () => {
    if (pending.current || !draftRef.current || draftRef.current.command) return;
    pending.current = true; setSaving(true);
    try {
      await queue.current;
      const original = draftRef.current;
      await writeForeshadowingDraft(scope, original, original.revision, true);
      persisted.current.delete(original.key);
      epoch.current += 1; draftRef.current = null; setDraft(null); setConfirm(false); setEditorError("");
      await readDrafts();
    } catch { setEditorError(t("localFailed")); }
    finally { pending.current = false; setSaving(false); }
  };
  const navigate = (action: () => void) => {
    if (saving) return;
    if (draft) setLeave(() => action);
    else { epoch.current += 1; action(); }
  };
  const select = (row: Foreshadowing) => navigate(() => {
    setCurrentRead(null); setMergeChoices({}); setReadMessage("");
    setSelectedId(row.foreshadowing_id); setMobileDetail(true);
    internalLocation.current = { view, id: row.foreshadowing_id };
    onLocationChange?.(view as "active" | "trash", row.foreshadowing_id);
    requestAnimationFrame(() => { if (context.current.active && detailRef.current && getComputedStyle(document.getElementById(`${id}-roster`)!).display === "none") detailRef.current.focus(); });
  });

  const readCurrent = async (session: ForeshadowingDraft, command: ForeshadowingDraft["command"], requestEpoch: number) => {
    const readRequest = ++readEpoch.current;
    const identity = command?.saved && "foreshadowing_id" in command.saved ? command.saved.foreshadowing_id : session.source?.foreshadowing_id;
    if (!identity) return;
    try {
      const current = await apiGet<Foreshadowing>(`${base}/${identity}?include_deleted=true`);
      if (current.novel_id !== novelId || current.foreshadowing_id !== identity) throw new Error(t("wrongScope"));
      if (epoch.current !== requestEpoch || readRequest !== readEpoch.current || !context.current.active || draftRef.current?.key !== session.key) return;
      setCurrentRead({ editorId: session.key, value: current }); setMergeChoices({});
      setReadMessage(command?.saved ? t("readBack") : command ? t("unconfirmedCurrent") : t("readBack"));
      setRows((old) => current.is_deleted === (context.current.view === "trash") ? old.some((row) => row.foreshadowing_id === identity) ? old.map((row) => row.foreshadowing_id === identity && current.version >= row.version ? current : row) : [...old, current] : old.filter((row) => row.foreshadowing_id !== identity));
    } catch (failure) {
      if (epoch.current !== requestEpoch || readRequest !== readEpoch.current || !context.current.active) return;
      if (failure instanceof ApiRequestError && failure.status === 404) { setReadMessage(t("gone")); setCurrentRead(null); }
      else throw failure;
    }
  };

  const submit = async () => {
    if (pending.current || !draftRef.current) return;
    pending.current = true; setSaving(true); setEditorError("");
    let session = draftRef.current;
    const requestEpoch = epoch.current;
    const wasUnknown = Boolean(session.command?.unknown);
    let stage = "register";
    try {
      let command = session.command;
      if (!command) {
        const action = session.mode === "plan" ? session.source ? "patch" : "create" : session.mode;
        const expected_version = session.source?.version;
        // 只提交作者实际改动的计划字段，不把旧版其它字段一起写回。
        const body = action === "create" ? session.plan : action === "patch" ? { ...Object.fromEntries(PLAN_FIELDS.filter((field) => JSON.stringify(session.plan[field]) !== JSON.stringify(session.source![field])).map((field) => [field, session.plan[field]])), expected_version } : action === "records" ? {
          expected_version, status: session.status,
          // 原证据不变时省略，保留服务端已有绑定；null 仅代表作者明确清除。
          ...(JSON.stringify(session.planted_evidence) === JSON.stringify(session.source?.planted_evidence) ? {} : { planted_evidence: session.planted_evidence && { chapter_id: session.planted_evidence.chapter_id, version: session.planted_evidence.version, start: session.planted_evidence.start, quote: session.planted_evidence.quote } }),
          ...(JSON.stringify(session.resolved_evidence) === JSON.stringify(session.source?.resolved_evidence) ? {} : { resolved_evidence: session.resolved_evidence && { chapter_id: session.resolved_evidence.chapter_id, version: session.resolved_evidence.version, start: session.resolved_evidence.start, quote: session.resolved_evidence.quote } }),
        } : { expected_version };
        command = { action, body, key: crypto.randomUUID(), unknown: true };
        session = { ...session, command, revision: session.revision + 1 };
      }
      draftRef.current = session; setDraft(session);
      // 先完成本地事务。崩溃或断响应后仍只有原键、原载荷和原版本。
      const receipt = await persist(session);
      // 另一标签页已经收到成功响应时，本标签页只读回与清稿，不能再写一次。
      if (receipt && !command.saved) {
        command = { ...command, saved: receipt, unknown: false };
        session = { ...session, command, revision: session.revision + 1 }; draftRef.current = session; setDraft(session);
        await persist(session);
      }
      if (!command.saved) {
        stage = "write";
        const path = command.action === "create" ? base : `${base}/${session.source!.foreshadowing_id}${command.action === "patch" ? "" : `/${command.action}`}`;
        const saved = command.action === "patch" ? await apiPatch<Foreshadowing>(path, command.body) : await apiPost<Foreshadowing | { deleted: true }>(path, command.body, command.action === "create" ? { headers: { "Idempotency-Key": command.key } } : undefined);
        command = { ...command, saved, unknown: false };
        session = { ...session, command, revision: session.revision + 1 };
        draftRef.current = session; setDraft(session);
        stage = "saveReceipt";
        await persist(session);
      }
      stage = "readback";
      if (command.action !== "hard-delete") await readCurrent(session, command, requestEpoch);
      else if (epoch.current === requestEpoch && context.current.active) setRows((old) => old.filter((row) => row.foreshadowing_id !== session.source!.foreshadowing_id));
      // 仅成功响应允许清本编辑器稿，读回404也不能用创建快照复建目标。
      stage = "cleanup";
      await writeForeshadowingDraft(scope, session, persisted.current.get(session.key)!, true);
      persisted.current.delete(session.key);
      if (epoch.current === requestEpoch) { setDraft(null); draftRef.current = null; setConfirm(false); if (context.current.active) setRefresh((value) => value + 1); }
    } catch (failure) {
      const rejected = failure instanceof ApiRequestError && failure.status >= 400 && failure.status < 500;
      // 曾经断响应的命令，即使重试409也仍未确认；字段相同也不算成功。
      if (!session.command?.saved && rejected && !wasUnknown) {
        session = { ...session, command: undefined, revision: session.revision + 1 }; draftRef.current = session; setDraft(session); await persist(session).catch(() => {});
      }
      if (epoch.current === requestEpoch && context.current.active) {
        setFieldErrors(failure instanceof ApiRequestError ? failure.fieldErrors : {});
        setEditorError(stage === "register" ? t("localFailed") : `${session.command?.saved ? t("savedPending") + " " : session.command ? t("unknown") + " " : ""}${failure instanceof Error ? failure.message : t("saveFailed")}`);
        requestAnimationFrame(() => { if (!context.current.active || epoch.current !== requestEpoch) return; if (confirm || !session.source) focusRelationEditorError(failure instanceof ApiRequestError ? failure.fieldErrors : {}); else editorRef.current?.querySelector<HTMLElement>("[data-editor-error-summary]")?.focus(); });
      }
    } finally { pending.current = false; setSaving(false); }
  };

  const positionLabel = (value: ForeshadowingPosition | null) => value ? positions.find((row) => row.kind === value.kind && row.id === value.id)?.title ?? `${t(value.kind)} · ${value.id}` : t("none");
  const planForm = draft && <div ref={editorRef} className="grid min-w-0 gap-4">
    {!confirm && (editorError || localError) && <RelationEditorErrorSummary message={editorError || localError} fieldErrors={fieldErrors} />}
    <label className="grid gap-1 text-xs text-muted">{t("titleField")}<input name="title" required maxLength={120} aria-invalid={Boolean(fieldErrors.title)} aria-describedby={fieldErrors.title ? `${id}-title-error` : undefined} className={INPUT} value={draft.plan.title} disabled={blocked} onChange={(event) => changeDraft({ ...draft, plan: { ...draft.plan, title: event.target.value } })} />{fieldErrors.title && <span id={`${id}-title-error`} className="text-danger">{fieldErrors.title.join(" ")}</span>}</label>
    {(["content", "target_effect"] as const).map((field) => <label key={field} className="grid gap-1 text-xs text-muted">{t(field)}<textarea name={field} required={field === "content"} maxLength={12000} className={`${INPUT} min-h-28 resize-y leading-6`} value={draft.plan[field]} disabled={blocked} onChange={(event) => changeDraft({ ...draft, plan: { ...draft.plan, [field]: event.target.value } })} /></label>)}
    <div className="detail-fields">{(["planting_position", "resolution_position"] as const).map((field) => <label key={field} className="grid min-w-0 gap-1 text-xs text-muted">{t(field)}<select className={INPUT} disabled={blocked} value={draft.plan[field] ? `${draft.plan[field]!.kind}:${draft.plan[field]!.id}` : ""} onChange={(event) => { const row = positions.find((entry) => `${entry.kind}:${entry.id}` === event.target.value); changeDraft({ ...draft, plan: { ...draft.plan, [field]: row ? { kind: row.kind, id: row.id } : null } }); }}><option value="">{t("none")}</option>{draft.plan[field] && !positions.some((row) => row.id === draft.plan[field]!.id) && <option value={`${draft.plan[field]!.kind}:${draft.plan[field]!.id}`}>{positionLabel(draft.plan[field])}</option>}{positions.map((row) => <option key={`${row.kind}:${row.id}`} value={`${row.kind}:${row.id}`}>{t(row.kind)} · {row.title}</option>)}</select></label>)}</div>
  </div>;
  const draftActions = draft && <div className="grid gap-3">
    {draft.command && <p role="status" className="text-sm">{t(draft.command.saved ? "savedPending" : "unknown")}</p>}
    {readMessage && <p role="status" className="text-sm">{readMessage}</p>}
    {currentRead && draft.source && draftValues && <div className="@container/comparison grid min-w-0 gap-4 border-y border-border py-4">
      {COMPARISON_FIELDS.map((field) => {
        const label = t(field === "title" ? "titleField" : field === "planted_evidence" ? "plantedEvidence" : field === "resolved_evidence" ? "resolvedEvidence" : field);
        return <div key={field} className="grid min-w-0 gap-2"><h4 className="text-sm font-medium">{label}</h4><div className="grid min-w-0 gap-3 @min-[640px]/comparison:grid-cols-3">
          {([{ label: t("originalValue"), value: draft.source![field] }, { label: t("currentValue"), value: currentRead[field] }, { label: t("draftValue"), value: draftValues[field] }]).map((entry) => <div key={entry.label} className="min-w-0"><p className="mb-1 text-xs text-muted">{entry.label}</p><pre className="reading-copy workspace-scrollbar max-h-44 min-w-0 overflow-y-auto whitespace-pre-wrap break-words text-sm">{field === "status" ? t(entry.value as ForeshadowingDraft["status"]) : entry.value === null ? t("none") : typeof entry.value === "string" ? entry.value : JSON.stringify(entry.value, null, 2)}</pre></div>)}
        </div>{mergeFields.includes(field) ? <fieldset className="flex min-w-0 flex-wrap gap-3"><legend className="text-xs text-muted">{t("chooseMerge")}</legend>{(["current", "draft"] as const).map((choice) => <label key={choice} className="flex min-h-11 items-center gap-2 text-sm"><input type="radio" name={`${id}-merge-${field}`} aria-label={`${t(choice === "current" ? "keepCurrentValue" : "keepDraftValue")} ${label}`} disabled={saving || Boolean(draft.command)} checked={mergeChoices[field] === choice} onChange={() => setMergeChoices({ ...mergeChoices, [field]: choice })} />{t(choice === "current" ? "keepCurrentValue" : "keepDraftValue")}</label>)}</fieldset> : <p className="text-xs text-muted">{t("currentValueKept")}</p>}</div>;
      })}
    </div>}
    <div className="flex flex-wrap gap-2">
      <Button variant="primary" isDisabled={saving || !draft.command && draft.mode === "plan" && (!planChanged || !draft.plan.title.trim() || !draft.plan.content.trim())} onPress={() => draft.command ? void submit() : setConfirm(true)}>{t(saving ? "saving" : draft.command?.saved ? "finishSaved" : draft.command ? "retryOriginal" : "save")}</Button>
      {draft.source && !draft.command?.saved && <Button variant="outline" isDisabled={saving} onPress={() => { setEditorError(""); void readCurrent(draft, draft.command, epoch.current).catch((failure) => setEditorError(failure.message)); }}>{t("readCurrent")}</Button>}
      {invalidMergeStatus && <p role="alert" className="text-sm text-danger">{t("mergeStatusNotAllowed")}</p>}
      {currentRead && !draft.command && !cleanupOnly && ["plan", "records"].includes(draft.mode) && <Button variant="outline" isDisabled={saving || Boolean(invalidMergeStatus) || mergeFields.some((field) => !mergeChoices[field])} onPress={() => {
        const plan: ForeshadowingPlan = {
          title: mergeChoices.title === "draft" ? draft.plan.title : currentRead.title,
          content: mergeChoices.content === "draft" ? draft.plan.content : currentRead.content,
          target_effect: mergeChoices.target_effect === "draft" ? draft.plan.target_effect : currentRead.target_effect,
          planting_position: mergeChoices.planting_position === "draft" ? draft.plan.planting_position : currentRead.planting_position,
          resolution_position: mergeChoices.resolution_position === "draft" ? draft.plan.resolution_position : currentRead.resolution_position,
        };
        openDraft(currentRead, draft.mode, { ...draft, source: currentRead, command: undefined, plan, status: mergeChoices.status === "draft" ? draft.status : currentRead.status, planted_evidence: mergeChoices.planted_evidence === "draft" ? draft.planted_evidence : currentRead.planted_evidence, resolved_evidence: mergeChoices.resolved_evidence === "draft" ? draft.resolved_evidence : currentRead.resolved_evidence });
      }}>{t("editCurrentKeepDraft")}</Button>}
      {!draft.command && <Button variant="ghost" isDisabled={saving} onPress={() => void discardEditor()}>{draftT("discardClose")}</Button>}
      <Button variant="ghost" isDisabled={saving} onPress={() => void closeEditor()}>{t("closeKeepDraft")}</Button>
    </div>
  </div>;

  return <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-surface">
    <h2 className="sr-only">{t(cleanupOnly ? "cleanupTitle" : "heading")}</h2>
    {error && <div className="border-y border-danger px-4 py-3 sm:px-6"><RelationEditorErrorSummary message={error} /></div>}
    <div className="flex shrink-0 items-center gap-3 border-b border-border px-4 sm:px-6">
    <div role="tablist" aria-label={t("heading")} className="flex min-w-0 flex-1 overflow-x-auto">{["active", "trash"].map((tab, index) => <button key={tab} role="tab" id={`${id}-${tab}-tab`} aria-selected={view === tab} aria-controls={`${id}-panel`} tabIndex={view === tab ? 0 : -1} disabled={saving} className={`min-h-11 shrink-0 border-b-2 px-4 text-sm focus-visible:outline-2 focus-visible:outline-accent ${view === tab ? "border-accent text-accent" : "border-transparent text-muted"}`} onClick={() => navigate(() => { setView(tab); setSelectedId(null); setMobileDetail(false); onLocationChange?.(tab as "active" | "trash", null); })} onKeyDown={(event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const next = event.key === "Home" ? "active" : event.key === "End" ? "trash" : index ? "active" : "trash";
      navigate(() => { setView(next); setSelectedId(null); setMobileDetail(false); onLocationChange?.(next as "active" | "trash", null); document.getElementById(`${id}-${next}-tab`)?.focus(); });
    }}>{t(tab)}</button>)}</div>
    <SectionActionButton action="refresh" label={t("refresh")} size="sm" variant="ghost" isDisabled={saving} onPress={() => setRefresh((value) => value + 1)} />
    </div>
    <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${view}-tab`} className="@container/master flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-4 py-3 sm:px-6">
      <div className={`workspace-toolbar mb-3 flex shrink-0 flex-wrap items-end gap-3 ${mobileDetail ? "hidden @min-[800px]/master:flex" : ""}`}>
        <label className="grid min-w-0 flex-1 gap-1 text-xs text-muted">{t("search")}<input className={INPUT} value={q} disabled={saving} onChange={(event) => navigate(() => setQ(event.target.value))} /></label>
        {!cleanupOnly && <label className="grid min-w-0 flex-1 gap-1 text-xs text-muted">{t("structure")}<select className={INPUT} value={position} disabled={saving} onChange={(event) => navigate(() => setPosition(event.target.value))}><option value="">{t("all")}</option>{positions.map((row) => <option key={`${row.kind}:${row.id}`} value={`${row.kind}:${row.id}`}>{t(row.kind)} · {row.title}</option>)}</select></label>}
        <label className="grid min-w-0 gap-1 text-xs text-muted">{t("status")}<select className={INPUT} value={status} disabled={saving} onChange={(event) => navigate(() => setStatus(event.target.value))}><option value="">{t("all")}</option>{Object.keys(FORESHADOWING_TRANSITIONS).map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
        {!cleanupOnly && view === "active" && <Button variant="primary" isDisabled={saving || Boolean(draft)} onPress={() => openDraft(null, "plan")}>{t("create")}</Button>}
      </div>
      {structureError && <p role="alert" className="mb-3 text-sm text-danger">{structureError}</p>}
      {readMessage && !draft && <p role="status" className="mb-3 text-sm">{readMessage}</p>}
      {localError && !draft && <RelationEditorErrorSummary message={localError} />}
      {drafts.length > 0 && !draft && <div className="workspace-scrollbar mb-3 flex max-h-44 shrink-0 flex-wrap gap-2 overflow-y-auto" aria-label={t("retainedDrafts", { count: drafts.length })}>
        {drafts.map((stored) => <DraftChip key={stored.key} label={stored.plan.title || t("create")} status={stored.command?.saved ? "saved" : stored.command ? "pending" : "draft"} isDisabled={saving} isResumeDisabled={cleanupOnly && !["delete", "hard-delete"].includes(stored.mode)}
          onResume={() => openDraft(stored.source, stored.mode, stored)}
          onDiscard={!stored.command || stored.command.saved ? async () => { await queue.current; await writeForeshadowingDraft(scope, stored, stored.revision, true); await readDrafts(); } : undefined} />)}
      </div>}
      <div className={`grid min-h-0 min-w-0 flex-1 overflow-hidden ${collapsed ? "@min-[800px]/master:grid-cols-[0_minmax(0,1fr)]" : "@min-[800px]/master:grid-cols-[minmax(240px,280px)_minmax(0,1fr)]"}`}>
        <div className={`relative min-h-0 min-w-0 ${mobileDetail ? "hidden @min-[800px]/master:block" : "block"}`}>
          <aside id={`${id}-roster`} aria-label={t("roster")} tabIndex={0} className={`workspace-scrollbar h-full min-h-0 overflow-y-auto focus-visible:outline-2 focus-visible:outline-accent ${mobileDetail ? "hidden" : "block"} ${collapsed ? "@min-[800px]/master:hidden" : "@min-[800px]/master:block"}`}>
            {loading && <p role="status" className="p-3 text-sm">{t("loading")}</p>}
            {!loading && rows.length === 0 && <p className="p-3 text-sm text-muted">{t(q || status || position ? "filteredEmpty" : "empty")}</p>}
            <ul className="divide-y divide-border">{rows.map((row) => <li key={row.foreshadowing_id}><button className={`min-h-11 w-full border-l-2 px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-accent ${row.foreshadowing_id === selectedId ? "border-accent bg-selected" : "border-transparent hover:bg-surface-secondary"}`} aria-current={row.foreshadowing_id === selectedId ? "true" : undefined} disabled={saving} onClick={() => select(row)}><span className="block truncate text-sm font-medium">{row.title}</span><span className="block text-xs text-muted">{t(row.status)}{row.planted_needs_review || row.resolved_needs_review ? ` · ${t("needsReview")}` : ""}</span></button></li>)}</ul>
          </aside>
          <SidebarEdgeHandle controls={`${id}-roster`} className="hidden @min-[800px]/master:flex" {...collapsed ? { rightAction: { label: t("showRoster"), expanded: false, onPress: () => setCollapsed(false) } } : { leftAction: { label: t("hideRoster"), expanded: true, onPress: () => setCollapsed(true) } }} />
        </div>
        <article ref={detailRef} aria-label={t("detail")} tabIndex={0} className={`workspace-scrollbar min-h-0 min-w-0 overflow-y-auto border-border px-5 py-4 focus-visible:outline-2 focus-visible:outline-accent sm:px-7 @min-[800px]/master:block @min-[800px]/master:border-l ${mobileDetail ? "block" : "hidden"}`}>
          <Button className="mb-3 @min-[800px]/master:hidden" variant="ghost" isDisabled={saving} onPress={() => navigate(() => { setMobileDetail(false); requestAnimationFrame(() => document.getElementById(`${id}-roster`)?.focus()); })}>{t("back")}</Button>
          {!selected && !(draft?.source && draft.mode === "plan") && <p className="text-sm text-muted">{t("chooseForeshadowing")}</p>}
          {(selected || draft?.source) && <div className="grid min-w-0 gap-4">
            <DocumentSection number="01" title={t("plan")} actions={!cleanupOnly && !selected?.is_deleted && !draft && selected && <SectionEditButton label={t("editPlan")} onPress={() => openDraft(selected, "plan")} />}>
              {draft?.source && draft.mode === "plan" ? <div className="grid gap-4">{planForm}{draftActions}</div> : selected && <dl className="detail-fields"><ReadOnlyField label={t("titleField")} value={selected.title} /><ReadOnlyField label={t("status")} value={t(selected.status)} /><ReadOnlyField label={t("content")} value={selected.content} wide /><ReadOnlyField label={t("target_effect")} value={selected.target_effect} wide /><ReadOnlyField label={t("planting_position")} value={positionLabel(selected.planting_position)} /><ReadOnlyField label={t("resolution_position")} value={positionLabel(selected.resolution_position)} /></dl>}
            </DocumentSection>
            {selected && <>
              {(selected.status === "planned" || selected.status === "planted") && <p className="text-sm text-muted">{t("unresolved")}</p>}
              {(["planted", "resolved"] as const).map((kind, index) => <DocumentSection key={kind} number={`0${index + 2}`} title={t(`${kind}Evidence`)}><div className="grid gap-3">{selected[`${kind}_needs_review`] && <p role="status" className="border-y border-amber-500 py-3 text-sm">{t("reviewWarning")}</p>}{selected[`${kind}_evidence`] ? <><pre className="reading-copy min-w-0 whitespace-pre-wrap break-words">{selected[`${kind}_evidence`]!.quote}</pre><p className="text-xs text-muted">{t("version", { version: selected[`${kind}_evidence`]!.version })} · {t("start")} {selected[`${kind}_evidence`]!.start}</p><Button variant="outline" onPress={() => setReference(selected[`${kind}_evidence`]!)}>{t("openReference")}</Button></> : <p className="text-sm text-muted">{t("noEvidence")}</p>}</div></DocumentSection>)}
              {!draft && <div className="flex flex-wrap gap-2">{!cleanupOnly && !selected.is_deleted && <Button variant="outline" onPress={() => openDraft(selected, "records")}>{t(selected.planted_needs_review || selected.resolved_needs_review ? "reviewRecords" : "record")}</Button>}{selected.is_deleted ? <>{!cleanupOnly && <Button variant="outline" onPress={() => openDraft(selected, "restore")}>{t("restore")}</Button>}<Button variant="danger-soft" onPress={() => openDraft(selected, "hard-delete")}>{t("hardDelete")}</Button></> : <SectionActionButton action="trash" label={t("delete")} variant="danger-soft" onPress={() => openDraft(selected, "delete")} />}</div>}
            </>}
            {draft?.mode === "records" && <DocumentSection number="04" title={t("record")}><div ref={editorRef} className="grid gap-4">
              {!confirm && (editorError || localError) && <RelationEditorErrorSummary message={editorError || localError} fieldErrors={fieldErrors} />}
              <label className="grid gap-1 text-xs text-muted">{t("status")}<select className={INPUT} value={draft.status} disabled={blocked} onChange={(event) => changeDraft({ ...draft, status: event.target.value as ForeshadowingDraft["status"] })}>{FORESHADOWING_TRANSITIONS[draft.source!.status].map((value) => <option key={value} value={value}>{t(value)}</option>)}</select></label>
              <EvidencePicker key={`${draft.key}:planted`} novelId={novelId} chapters={chapters} value={draft.planted_evidence} label={t("plantedEvidence")} disabled={blocked} onChange={(value) => changeDraft({ ...draft, planted_evidence: value })} />
              <EvidencePicker key={`${draft.key}:resolved`} novelId={novelId} chapters={chapters} value={draft.resolved_evidence} label={t("resolvedEvidence")} disabled={blocked} onChange={(value) => changeDraft({ ...draft, resolved_evidence: value })} />
              {draftActions}
            </div></DocumentSection>}
            {draft && ["delete", "restore", "hard-delete"].includes(draft.mode) && !confirm && <div ref={editorRef} className="grid gap-3">{editorError && <RelationEditorErrorSummary message={editorError} />}{draftActions}</div>}
          </div>}
        </article>
      </div>
    </div>
    {draft && !draft.source && <RetainedModalBackdrop isOpen onOpenChange={(open) => !open && void closeEditor()} isDismissable={!saving}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full max-w-2xl"><Modal.Header className="px-5 py-4"><Modal.Heading>{t("create")}</Modal.Heading><Modal.CloseTrigger isDisabled={saving} aria-label={t("closeKeepDraft")} /></Modal.Header><Modal.Body className="px-5 py-5">{planForm}</Modal.Body><Modal.Footer className="sticky bottom-0 border-t border-border bg-surface-raised px-5 py-4">{draftActions}</Modal.Footer></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
    {confirm && draft && <ConfirmActionModal title={t(draft.mode === "records" ? "record" : draft.mode === "hard-delete" ? "hardDelete" : draft.mode === "delete" ? "delete" : draft.mode === "restore" ? "restore" : "save")} message={<div className="grid gap-3"><p>{t(draft.mode === "hard-delete" ? "hardDeleteMessage" : draft.mode === "delete" ? "deleteMessage" : draft.mode === "restore" ? "restoreMessage" : "confirmMessage")}</p>{draft.mode === "records" && <p>{t("status")}: {t(draft.status)}</p>}{["delete", "hard-delete"].includes(draft.mode) && draft.source && <ul className="break-words"><li>{t("planting_position")}: {positionLabel(draft.source.planting_position)}</li><li>{t("resolution_position")}: {positionLabel(draft.source.resolution_position)}</li>{[draft.source.planted_evidence, draft.source.resolved_evidence].filter(Boolean).map((evidence, index) => <li key={index}>{evidence!.chapter_id} · {t("version", { version: evidence!.version })} · {t("start")} {evidence!.start}</li>)}</ul>}</div>} confirmText={t("confirm")} cancelText={t("cancel")} isLoading={saving} danger={["delete", "hard-delete"].includes(draft.mode)} error={editorError || localError} onCancel={() => setConfirm(false)} onConfirm={() => void submit()} />}
    {reference && <RetainedModalBackdrop isOpen onOpenChange={(open) => !open && setReference(null)}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full max-w-3xl"><Modal.Header className="px-5 py-4"><Modal.Heading>{t("openReference")}</Modal.Heading><Modal.CloseTrigger aria-label={t("close")} /></Modal.Header><Modal.Body className="px-5 py-5"><EvidencePicker key={`${reference.chapter_id}:${reference.version}:${reference.start}`} novelId={novelId} chapters={chapters} value={reference} readOnly label={t("openReference")} /></Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
    {leave && <ConfirmActionModal title={t("leaveTitle")} message={t("leaveMessage")} confirmText={t("closeKeepDraft")} cancelText={t("cancel")} error={editorError} onCancel={() => setLeave(null)} onConfirm={async () => { const action = leave; await closeEditor(); if (!draftRef.current) { setLeave(null); action(); } }} />}
  </div>;
}
