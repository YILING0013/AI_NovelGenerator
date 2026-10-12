"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Modal, Popover } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import { apiGet, apiPatch, apiPost, apiPostSSE } from "@/lib/api";
import { notifyResourceChange, subscribeResourceChanges } from "@/lib/resourceChanges";
import type { ActiveAssistantResource, AssistantEvent, AssistantMessage, AssistantRun, AssistantSession, AssistantTurnRequest, ChangeSet, ContextAttachment, NavigationTarget, ResourceIndexEntry, ResourceRef, SessionDetail } from "@/types/assistant";
import { useNovelAssistant } from "./AssistantContext";
import ChangeReview from "./ChangeReview";

const CONTROL = "min-h-9 min-w-0 rounded-lg border border-border bg-field px-2 py-1.5 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-accent";
const EVENTS = ["progress", "run", "message", "tool", "tool_progress", "change", "resources_changed", "navigation", "question", "run_error", "state"];

/** 常驻小说侧栏；桌面占440px，剩余工作区不足1040px时使用标准Modal抽屉。
 * Args: 无，读取小说级助手上下文。
 * Returns: 折叠手柄、独立滚动的对话和候选审核。
 */
export default function AssistantSidebar() {
  const t = useTranslations("writing.assistant");
  const taskNames = useTranslations("taskFlows.tasks");
  const assistant = useNovelAssistant();
  const { novelId, enabled, active, open, setOpen, resource, requestedAttachment, consumeAttachment, capabilities, navigate } = assistant;
  const base = `/api/novels/${novelId}/assistant`;
  const slot = useRef<HTMLElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const abort = useRef<AbortController | null>(null);
  const selectedSession = useRef<string | null>(null);
  const requestSequence = useRef(0);
  const changeActions = useRef(new Set<string>());
  const [pendingChangeActions, setPendingChangeActions] = useState<string[]>([]);
  const activeRun = useRef<string | null>(null);
  const lastSequence = useRef<Record<string, number>>({});
  const lastQuoted = useRef<{ text: string; field?: string; resource: ActiveAssistantResource; version?: number } | null>(null);
  const currentResource = useRef(resource);
  useEffect(() => { currentResource.current = resource; }, [resource]);
  const candidateDrafts = useRef(new Map<string, { revision: number; value: ChangeSet }>());
  const composing = useRef(false);
  const sendKey = useRef<{ text: string; key: string } | null>(null);
  const [narrow, setNarrow] = useState(true);
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [newSettings, setNewSettings] = useState<Pick<AssistantSession, "mode" | "provider" | "model">>({ mode: "auto", provider: "", model: "" });
  const settings = session ?? newSettings;
  const pendingSettings = useRef<Promise<AssistantSession> | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const draftKey = session?.id ?? "new";
  const savingChange = pendingChangeActions.some((key) => key.startsWith(`${draftKey}:`));
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [changes, setChanges] = useState<ChangeSet[]>([]);
  const [run, setRun] = useState<AssistantRun | null>(null);
  const [tools, setTools] = useState<Record<string, { name: string; state: string; result?: Record<string, unknown> }>>({});
  const [navigation, setNavigation] = useState<NavigationTarget[]>([]);
  const [childProgress, setChildProgress] = useState<Record<string, string>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [sentTarget, setSentTarget] = useState<(ResourceRef & { name: string }) | null>(null);
  const [attachmentNames, setAttachmentNames] = useState<Record<string, string>>({});
  const [writingTargets, setWritingTargets] = useState<Record<string, (ResourceRef & { name: string }) | null>>({});
  const writingTarget = writingTargets[draftKey] === undefined ? (resource && ["volume", "arc", "scene", "chapter"].includes(resource.resource_type) ? resource : null) : writingTargets[draftKey];
  const originalTarget = run?.request?.writing_target;
  const originalTargetName = originalTarget ? attachmentNames[`${originalTarget.resource_type}/${originalTarget.id}`] ?? (resource?.id === originalTarget.id ? resource.name : t(`kinds.${originalTarget.resource_type}`)) : "";
  const displayedTarget = busy ? sentTarget : run?.status === "waiting_input" ? (originalTarget ? { ...originalTarget, name: originalTargetName } : null) : writingTarget;
  const writingOptions = [displayedTarget, writingTarget, resource && ["volume", "arc", "scene", "chapter"].includes(resource.resource_type) ? resource : null]
    .filter((value, index, values): value is ResourceRef & { name: string } => Boolean(value) && values.findIndex((item) => item?.resource_type === value?.resource_type && item?.id === value?.id) === index);
  const [attachmentDrafts, setAttachmentDrafts] = useState<Record<string, ContextAttachment[]>>({});
  const attachments = attachmentDrafts[draftKey] ?? [];
  const setAttachments = useCallback((update: ContextAttachment[] | ((current: ContextAttachment[]) => ContextAttachment[])) => {
    setAttachmentDrafts((current) => ({ ...current, [draftKey]: typeof update === "function" ? update(current[draftKey] ?? []) : update }));
  }, [draftKey]);
  const attachmentKeys = [...new Set([...attachments.filter((item) => item.origin === "saved").map((item) => `${item.resource_type}/${item.id}`), ...(originalTarget && run?.status === "waiting_input" ? [`${originalTarget.resource_type}/${originalTarget.id}`] : [])])].join(",");
  useEffect(() => {
    if (!attachmentKeys) return;
    const controller = new AbortController();
    for (const key of attachmentKeys.split(",")) {
      void apiGet<{ name: string }>(`${base}/resources/${key}`, { signal: controller.signal }).then((value) => setAttachmentNames((current) => ({ ...current, [key]: value.name }))).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : t("loadFailed")); });
    }
    return () => controller.abort();
  }, [attachmentKeys, base, t]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [archived, setArchived] = useState(false);
  const [rename, setRename] = useState<string | null>(null);
  const [allowNavigation, setAllowNavigation] = useState(false);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [manualChanged, setManualChanged] = useState(false);
  const [picker, setPicker] = useState(false);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [resources, setResources] = useState<ResourceIndexEntry[]>([]);
  const [resourceOffset, setResourceOffset] = useState(0);
  const [moreResources, setMoreResources] = useState(false);
  const [olderBefore, setOlderBefore] = useState<string | null>(null);
  const message = drafts[draftKey] ?? "";
  const unboundQuestion = run?.status === "waiting_input" && !run.pending_question;
  const messageTooLong = Array.from(message).length > (run?.status === "waiting_input" || writingTarget ? 5000 : 16000);
  const updateChange = useCallback((value: ChangeSet) => setChanges((current) => current.some((item) => item.id === value.id) ? current.map((item) => item.id === value.id ? value : item) : [...current, value]), []);

  /** 仅把常驻侧栏内的焦点归还给仍可用的原入口。
   * Args: fromResize 连续切换布局时，也接住已经落到 BODY 的焦点。
   * Returns: 无；用户已在页面别处操作时保留其焦点。
   */
  const restoreDesktopFocus = useCallback((fromResize = false) => {
    const opener = assistant.opener.current;
    const focused = document.activeElement;
    if (active && (slot.current?.contains(focused) || (fromResize && focused === document.body)) && opener?.isConnected
      && opener.getClientRects().length && !opener.matches(":disabled, [aria-disabled='true']") && !opener.closest("[inert]")) {
      opener.focus({ preventScroll: true });
    }
  }, [active, assistant.opener]);

  useEffect(() => {
    const parent = slot.current?.parentElement;
    if (!parent) return;
    const measure = () => {
      const nextNarrow = parent.getBoundingClientRect().width < 1040;
      // 桌面输入即将卸载，先还入口，才能让新抽屉记住正确的恢复目标。
      if (nextNarrow && !narrow && open) restoreDesktopFocus(true);
      setNarrow(nextNarrow);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [enabled, narrow, open, restoreDesktopFocus]);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    if (!requestedAttachment) return;
    setAttachments((current) => [...current.filter((item) => !(item.id === requestedAttachment.id && item.resource_type === requestedAttachment.resource_type && item.fields.join() === requestedAttachment.fields.join())), requestedAttachment]);
    consumeAttachment();
  }, [requestedAttachment, consumeAttachment, setAttachments]);
  useEffect(() => {
    if (!active) return;
    const selected = (event: Event) => {
      const target = event.target;
      if (!currentResource.current || !(target instanceof HTMLElement) || target.closest("[data-assistant-sidebar]") || !target.closest("[data-assistant-workspaces]")) return;
      if (target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement) {
        const start = target.selectionStart ?? 0, end = target.selectionEnd ?? 0;
        if (start !== end) lastQuoted.current = { text: target.value.slice(start, end), field: target.name || undefined, resource: structuredClone(currentResource.current),
          version: target.readOnly || target.disabled ? currentResource.current.version : currentResource.current.draft?.version ?? currentResource.current.version };
      } else {
        const text = window.getSelection()?.toString().trim();
        if (text) lastQuoted.current = { text, resource: structuredClone(currentResource.current), version: currentResource.current.version };
      }
    };
    document.addEventListener("mouseup", selected);
    document.addEventListener("select", selected);
    return () => { document.removeEventListener("mouseup", selected); document.removeEventListener("select", selected); };
  }, [active]);
  useEffect(() => subscribeResourceChanges((notice) => {
    if (notice.source !== "manual" || !enabled) return;
    if (notice.novelId && notice.novelId !== novelId) return;
    setManualChanged(true);
    // 人工或原 AI 保存只刷新基础索引，不因提示发起付费模型检查。
    void apiGet(`${base}/index/status`).catch(() => {});
  }), [base, enabled, novelId]);

  const loadSession = useCallback(async (id: string) => {
    const request = ++requestSequence.current;
    selectedSession.current = id;
    pendingSettings.current = null; setSavingSettings(false);
    setLoading(true); setError(""); setRename(null); setTools({}); setNavigation([]); setChildProgress({});
    try {
      const detail = await apiGet<SessionDetail>(`${base}/sessions/${id}`);
      if (selectedSession.current !== id || requestSequence.current !== request) return;
      setSession(detail.session); setMessages(detail.messages); setChanges(detail.changes); setRun(detail.runs[0] ?? null); setOlderBefore(detail.before);
      activeRun.current = detail.runs[0]?.id ?? null;
      if (detail.runs[0]) {
        const runId = detail.runs[0].id;
        let after = 0;
        let more = true;
        const restoredTools: typeof tools = {};
        const restoredNavigation: NavigationTarget[] = [];
        const restoredProgress: Record<string, string> = {};
        while (more && selectedSession.current === id && requestSequence.current === request) {
          const page = await apiGet<{ events: AssistantEvent[]; has_more: boolean }>(`${base}/runs/${runId}/events?after=${after}`);
          for (const event of page.events) {
            after = event.seq;
            if (event.event === "tool") restoredTools[String(event.data.key)] = { name: String(event.data.name), state: String(event.data.state), result: event.data.result as Record<string, unknown> | undefined };
            const source = event.event === "tool" ? event.data.result as Partial<NavigationTarget> | undefined : undefined;
            if (source?.resource_type && source.id) restoredNavigation.push({ resource_type: source.resource_type, id: source.id });
            if (event.event === "navigation") restoredNavigation.push(event.data as unknown as NavigationTarget);
            if (detail.runs[0].status === "running" && event.event === "tool_progress" && event.data.message) restoredProgress[String(event.data.task)] = String(event.data.message);
          }
          more = page.has_more;
        }
        if (selectedSession.current === id && requestSequence.current === request) { setTools(restoredTools); setChildProgress(restoredProgress); setNavigation([...new Map(restoredNavigation.map((target) => [`${target.resource_type}:${target.id}`, target])).values()]); lastSequence.current[runId] = after; }
      }
      if (selectedSession.current === id && requestSequence.current === request) localStorage.setItem(`novel-assistant:${novelId}:session`, id);
    } catch (reason) { if (selectedSession.current === id && requestSequence.current === request) setError(reason instanceof Error ? reason.message : t("loadFailed")); }
    finally { if (requestSequence.current === request) setLoading(false); }
  }, [base, novelId, t]);

  const newSession = async () => {
    setError(""); setLoading(true);
    try {
      await pendingSettings.current;
      const value = await apiPost<AssistantSession>(`${base}/sessions`, { title: t("newConversation"), ...newSettings });
      setSessions((current) => [value, ...current]); setArchived(false);
      await loadSession(value.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("operationFailed")); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!enabled || !open || initialized) return;
    let current = true;
    setLoading(true);
    void apiGet<{ data: AssistantSession[] }>(`${base}/sessions`).then(async ({ data }) => {
      if (!current) return;
      setSessions(data); setInitialized(true);
      const saved = localStorage.getItem(`novel-assistant:${novelId}:session`);
      const chosen = data.find((item) => item.id === saved) ?? data[0];
      if (chosen) await loadSession(chosen.id);
      else setLoading(false);
    }).catch((reason) => { if (current) { setError(reason instanceof Error ? reason.message : t("loadFailed")); setLoading(false); } });
    return () => { current = false; };
  }, [base, enabled, initialized, loadSession, novelId, open, t]);

  const changeSetting = async (patch: Partial<AssistantSession>) => {
    setError("");
    // 第一条消息发送前只保留本地选项，创建对话时一起提交。
    if (!session) { setNewSettings((current) => ({ ...current, ...patch })); return; }
    setSavingSettings(true);
    const request = apiPatch<AssistantSession>(`${base}/sessions/${session.id}`, patch);
    pendingSettings.current = request;
    try {
      const value = await request;
      if (selectedSession.current !== session.id || pendingSettings.current !== request) return;
      setSession(value); setSessions((current) => current.map((item) => item.id === value.id ? value : item)); setRename(null);
    } catch (reason) { if (selectedSession.current === session.id && pendingSettings.current === request) setError(reason instanceof Error ? reason.message : t("operationFailed")); }
    finally { if (pendingSettings.current === request) { pendingSettings.current = null; setSavingSettings(false); } }
  };

  const handleEvent = async (event: string, data: Record<string, unknown>) => {
    if (typeof data.seq === "number" && activeRun.current) lastSequence.current[activeRun.current] = Math.max(lastSequence.current[activeRun.current] ?? 0, data.seq);
    if (event === "run" || event === "done" || event === "state") {
      const value = data as unknown as AssistantRun;
      activeRun.current = value.id; setRun(value);
      if (value.status !== "running") setChildProgress({});
      if (value.error && value.status === "failed") setError(value.error.message);
    } else if (event === "message" || event === "question") {
      setMessages((current) => [...current, { id: `${activeRun.current}:${data.seq}`, run_id: activeRun.current ?? "", role: "assistant", content: String(data.content ?? data.question ?? "") }]);
    } else if (event === "progress") {
      setRun((current) => current ? { ...current, rounds: Number(data.round), tool_calls: Number(data.tool_calls) } : current);
    } else if (event === "tool") {
      setTools((current) => ({ ...current, [String(data.key)]: { name: String(data.name), state: String(data.state), result: data.result as Record<string, unknown> | undefined } }));
      const toolError = (data.result as { error?: { code?: string; message?: string } } | undefined)?.error;
      if (toolError?.message && /^(ASSISTANT_WRITING_|ASSISTANT_POSITION_|ASSISTANT_CREATION_)/.test(toolError.code ?? "")) setError(toolError.message);
      const source = data.result as Partial<NavigationTarget> | undefined;
      if (source?.resource_type && source.id) setNavigation((current) => [...current.filter((item) => item.resource_type !== source.resource_type || item.id !== source.id), { resource_type: source.resource_type!, id: source.id! }]);
    } else if (event === "tool_progress") {
      if (data.message) setChildProgress((current) => ({ ...current, [String(data.task)]: String(data.message) }));
    } else if (event === "change") updateChange(data as unknown as ChangeSet);
    else if (event === "resources_changed") {
      notifyResourceChange({ novelId, source: "assistant", resources: data.resources as ResourceRef[] });
    } else if (event === "navigation") {
      const target = data as unknown as NavigationTarget;
      setNavigation((current) => [...current.filter((item) => item.id !== target.id || item.resource_type !== target.resource_type), target]);
      if (data.navigate) navigate(target);
    } else if (event === "error" || event === "run_error") {
      setChildProgress({}); setError(String(data.message ?? t("operationFailed")));
    }
  };

  const send = async (continuing = false, resumeRunId?: string) => {
    if (busy || loading || composing.current || (!continuing && !message.trim())) return;
    // 同会话保存期间可编辑下一条草稿；只有核对过代次的保存回调可以续跑。
    if (!resumeRunId && [...changeActions.current].some((key) => key.startsWith(`${draftKey}:`))) return;
    if (unboundQuestion && !resumeRunId) { setError(t("legacyQuestion")); return; }
    if (!continuing && messageTooLong) { input.current?.focus(); return; }
    const request = ++requestSequence.current;
    setSentTarget(continuing || run?.status === "waiting_input" ? (originalTarget ? { ...originalTarget, name: originalTargetName } : null) : writingTarget);
    setBusy(true); setError(""); setManualChanged(false); setChildProgress({});
    const controller = new AbortController(); abort.current = controller;
    try {
      // 先等设置保存完成，避免刚切换模型就发送时仍使用旧配置。
      await pendingSettings.current;
      let chat = session;
      if (!chat) {
        chat = await apiPost<AssistantSession>(`${base}/sessions`, { title: message.trim().slice(0, 40) || t("newConversation"), ...newSettings });
        setDrafts((current) => ({ ...current, [chat!.id]: message }));
        setAttachmentDrafts((current) => ({ ...current, [chat!.id]: attachments }));
        setWritingTargets((current) => ({ ...current, [chat!.id]: writingTarget }));
        selectedSession.current = chat.id; setSession(chat); setSessions((current) => [chat!, ...current]); setInitialized(true);
      }
      if (continuing && (run || resumeRunId)) {
        await apiPostSSE(`${base}/runs/${resumeRunId ?? run!.id}/continue`, { additional_rounds: resumeRunId ? 0 : 4 }, async (event, data) => {
          if (requestSequence.current === request) await handleEvent(event, data);
        }, { signal: controller.signal, allowedEvents: EVENTS });
      } else {
        const text = message;
        const payload: AssistantTurnRequest = { message: text, attachments, location: resource ? { resource_type: resource.resource_type, id: resource.id } : null,
          writing_target: writingTarget ? { resource_type: writingTarget.resource_type, id: writingTarget.id } : null, allow_navigation: allowNavigation, execution_mode: "auto" };
        const answering = run?.status === "waiting_input" && run.pending_question;
        const body = answering ? { question_id: answering.id, message: text, ...(answering.confirmation?.token ? { confirmation_token: answering.confirmation.token } : {}) } : payload;
        const endpoint = answering ? `${base}/runs/${run.id}/answers/stream` : `${base}/sessions/${chat.id}/turns/stream`;
        const signature = JSON.stringify({ endpoint, body });
        if (sendKey.current?.text !== signature) sendKey.current = { text: signature, key: crypto.randomUUID() };
        const requestKey = sendKey.current.key;
        setMessages((current) => [...current, { id: requestKey, run_id: "", role: "user", content: text, attachments }]);
        activeRun.current = null;
        setTools({}); setChildProgress({});
        let accepted = false;
        await apiPostSSE(endpoint, body, async (event, data) => {
          if (requestSequence.current !== request) return;
          if (event === "run" && !accepted) {
            accepted = true;
            setDrafts((current) => ({ ...current, [draftKey]: current[draftKey] === message ? "" : current[draftKey], [chat!.id]: current[chat!.id] === message ? "" : current[chat!.id] }));
            setAttachmentDrafts((current) => ({ ...current, [draftKey]: [], [chat!.id]: [] }));
            setWritingTargets((current) => { const next = { ...current }; delete next[draftKey]; delete next[chat!.id]; return next; });
          }
          await handleEvent(event, data);
        }, { headers: { "Idempotency-Key": requestKey }, signal: controller.signal, allowedEvents: EVENTS });
        if (requestSequence.current === request) sendKey.current = null;
      }
    } catch (reason) {
      if (requestSequence.current === request && !(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : t("operationFailed"));
    } finally {
      if (requestSequence.current === request) {
        setBusy(false); setChildProgress({}); abort.current = null;
        const sessionId = selectedSession.current;
        if (sessionId) {
          const detail = await apiGet<SessionDetail>(`${base}/sessions/${sessionId}`).catch(() => null);
          // 可以立即发送下一轮；旧轮次或旧会话的读回结果不能覆盖新内容。
          if (detail && selectedSession.current === sessionId && requestSequence.current === request) {
            setMessages(detail.messages); setChanges(detail.changes); setRun(detail.runs[0] ?? null); setOlderBefore(detail.before);
          }
        }
      }
    }
  };
  const stop = async () => {
    if (!activeRun.current) { abort.current?.abort(); return; }
    try { await apiPost(`${base}/runs/${activeRun.current}/cancel`, {}); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("operationFailed")); }
  };
  const attach = (origin: "saved" | "draft" | "selection") => {
    if (!resource) return;
    if (origin === "draft" && !resource.draft) { setError(t("noDraft")); return; }
    const quoted = origin === "selection" ? lastQuoted.current : null;
    if (origin === "selection" && !quoted) { setError(t("noSelection")); return; }
    const source = quoted?.resource ?? resource;
    const value: ContextAttachment = { resource_type: source.resource_type, id: source.id, fields: origin === "draft" ? resource.draft!.fields : quoted?.field ? [quoted.field] : [],
      origin: origin === "saved" ? "saved" : "draft", usage: "reference", version: origin === "draft" ? resource.draft?.version : quoted ? quoted.version : source.version,
      ...(origin === "draft" ? { text: resource.draft!.text.slice(0, 12000) } : quoted ? { text: quoted.text.slice(0, 12000) } : {}) };
    setAttachments((current) => [...current.slice(0, 19), value]); setError("");
  };
  useEffect(() => {
    if (!picker) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void apiGet<{ items: ResourceIndexEntry[]; has_more: boolean }>(`${base}/resources?query=${encodeURIComponent(query)}&offset=${resourceOffset}`, { signal: controller.signal }).then((data) => { setResources(data.items); setMoreResources(data.has_more); }).catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : t("loadFailed")); });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [base, picker, query, resourceOffset, t]);

  if (!enabled) return null;
  /** 关闭顶部或边缘入口，抽屉继续由 HeroUI 还焦点。
   * Args: 无。
   * Returns: 无。
   */
  const close = () => {
    if (!narrow) restoreDesktopFocus();
    setOpen(false);
  };
  const viewRequest = requestSequence.current;
  const resumable = run && !busy && !["completed", "running", "waiting_input"].includes(run.status);
  const legacyRun = resumable && run.creation_contract_version !== 1;
  const canContinue = resumable && !legacyRun && !run.pending_question;
  const content = <div data-assistant-sidebar className="flex h-full min-h-0 min-w-0 flex-col bg-surface text-foreground">
    <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-4 py-3">
      <h2 className="min-w-0 flex-1 text-base font-semibold" id="novel-assistant-heading">{t("title")}</h2>
      <Popover isOpen={sessionMenuOpen && open && active} onOpenChange={setSessionMenuOpen}>
        <Button size="sm" variant="ghost" aria-label={t("conversationMenu")}>•••</Button>
        <Popover.Content placement="bottom end" className="w-80 max-w-[calc(100vw-2rem)] border border-border bg-surface-raised">
          <Popover.Dialog aria-label={t("conversationMenu")} className="space-y-2 p-3">
      <Button size="sm" variant="ghost" isDisabled={busy || loading} onPress={() => void newSession()}>{t("new")}</Button>
      <label className="sr-only" htmlFor="assistant-session">{t("conversation")}</label>
      <select id="assistant-session" className={`${CONTROL} w-full`} value={session?.id ?? ""} disabled={busy || loading} onChange={(event) => void loadSession(event.target.value)}>
        <option value="" disabled>{t("newConversation")}</option>{sessions.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
      </select>
      {session && <div className="flex w-full flex-wrap items-center gap-2 text-xs">
        {rename !== null ? <form className="flex min-w-0 flex-1 gap-2" onSubmit={(event) => { event.preventDefault(); if (rename.trim()) void changeSetting({ title: rename.trim() }); }}><input aria-label={t("conversationName")} autoFocus className={`${CONTROL} flex-1`} maxLength={100} value={rename} onChange={(event) => setRename(event.target.value)} /><Button size="sm" type="submit" variant="ghost">{t("save")}</Button><Button size="sm" variant="ghost" onPress={() => setRename(null)}>{t("cancel")}</Button></form>
          : <><Button size="sm" variant="ghost" isDisabled={busy} onPress={() => setRename(session.title)}>{t("rename")}</Button><Button size="sm" variant="ghost" isDisabled={busy} onPress={() => void changeSetting({ archived: !session.archived })}>{t(session.archived ? "unarchive" : "archive")}</Button></>}
        <Button size="sm" variant="ghost" isDisabled={busy} onPress={() => { const next = !archived; setArchived(next); void apiGet<{ data: AssistantSession[] }>(`${base}/sessions?archived=${next}`).then(({ data }) => setSessions(data)).catch((reason) => setError(String(reason))); }}>{t(archived ? "activeConversations" : "archivedConversations")}</Button>
      </div>}
      <details><summary className="cursor-pointer text-xs text-muted">{t("modelAndNavigation")}</summary><div className="mt-2 space-y-2">
        <div className="grid gap-1 text-xs text-muted"><label htmlFor="assistant-provider">{t("provider")}</label><select id="assistant-provider" className={CONTROL} value={settings.provider || capabilities?.default_provider || ""} disabled={loading || busy || savingSettings} onChange={(event) => void changeSetting({ provider: event.target.value, model: "" })}>{capabilities?.providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.id}{provider.supports_function_calling ? "" : ` · ${t("unsupported")}`}</option>)}</select></div>
        <div className="grid gap-1 text-xs text-muted"><label htmlFor="assistant-model">{t("model")}</label><input id="assistant-model" className={CONTROL} value={settings.model} placeholder={capabilities?.providers.find((item) => item.id === (settings.provider || capabilities.default_provider))?.model} disabled={loading || busy || savingSettings} onChange={(event) => { if (session) setSession({ ...session, model: event.target.value }); else setNewSettings((current) => ({ ...current, model: event.target.value })); }} onBlur={() => { if (session) void changeSetting({ model: session.model }); }} /></div>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={allowNavigation} onChange={(event) => setAllowNavigation(event.target.checked)} />{t("allowNavigation")}</label>
      </div></details>
          </Popover.Dialog>
        </Popover.Content>
      </Popover>
      <Button size="sm" variant="ghost" onPress={close} aria-label={t("collapse")}>{t("collapse")}</Button>
    </header>
    <div className="workspace-scrollbar min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 focus-visible:outline-accent" data-assistant-messages tabIndex={0} role="region" aria-label={t("conversation")}>
      {loading && <p className="py-4 text-sm text-muted" role="status">{t("loading")}</p>}
      {olderBefore && <Button size="sm" variant="ghost" onPress={() => {
        if (!session) return;
        void apiGet<SessionDetail>(`${base}/sessions/${session.id}?before=${olderBefore}`).then((detail) => {
          if (selectedSession.current !== session.id || requestSequence.current !== viewRequest) return;
          setMessages((current) => [...detail.messages, ...current]); setOlderBefore(detail.before);
        }).catch((reason) => { if (selectedSession.current === session.id && requestSequence.current === viewRequest) setError(String(reason)); });
      }}>{t("olderMessages")}</Button>}
      <div aria-live="polite" aria-relevant="additions text">{messages.map((item) => <article key={item.id} className="min-w-0 border-b border-border/60 py-4">
        <span className="mb-2 block text-xs font-medium text-muted">{t(item.role === "user" ? "author" : "assistant")}</span>
        <p className="reading-copy w-full whitespace-pre-wrap break-words text-sm leading-7">{item.content}</p>
        {item.attachments?.map((attachment, index) => <span key={index} className="mt-2 mr-2 inline-block text-xs text-muted">{t(`kinds.${attachment.resource_type}`)} · {t(`origin.${attachment.origin}`)}</span>)}
      </article>)}</div>
      {Object.keys(tools).length > 0 && <details className="border-b border-border py-3"><summary className="cursor-pointer text-xs text-muted">{t("toolDetails", { count: Object.keys(tools).length })}</summary><ol className="mt-2 space-y-2">{Object.entries(tools).map(([key, tool]) => <li key={key} className="min-w-0 text-xs"><span>{t.has(`tools.${tool.name}`) ? t(`tools.${tool.name}`) : tool.name}</span><span className="ml-2 text-muted">{t(`toolState.${tool.state}`)}</span>{tool.result && <details className="mt-1"><summary className="cursor-pointer text-muted">{t("result")}</summary><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(tool.result, null, 2)}</pre></details>}</li>)}</ol></details>}
      {navigation.map((target) => <Button key={`${target.resource_type}:${target.id}`} size="sm" variant="ghost" onPress={() => navigate(target)}>{t("source", { kind: t(`kinds.${target.resource_type}`), id: target.id })}</Button>)}
      {run?.status === "running" && Object.entries(childProgress).map(([task, progress]) => <p key={task} className="my-2 text-xs text-muted" role="status">{taskNames.has(task) ? taskNames(task) : t("runStatus.running")} · {progress}</p>)}
      {changes.map((change) => <ChangeReview key={change.id} change={change} onChanged={(value) => {
        if (selectedSession.current === session?.id && requestSequence.current === viewRequest) updateChange(value);
      }} disabled={busy || savingChange} onBusyChange={(value) => {
        const key = `${session?.id}:${viewRequest}:${change.id}`;
        if (value) changeActions.current.add(key); else changeActions.current.delete(key);
        setPendingChangeActions([...changeActions.current]);
      }} onApplied={async (runId) => {
        if (selectedSession.current !== session?.id || requestSequence.current !== viewRequest) return;
        if (runId) await send(true, runId);
        else if (session) {
          const detail = await apiGet<SessionDetail>(`${base}/sessions/${session.id}`);
          if (selectedSession.current === session.id && requestSequence.current === viewRequest) { setChanges(detail.changes); setRun(detail.runs[0] ?? null); setMessages(detail.messages); }
        }
      }} drafts={candidateDrafts.current} />)}
      {run && <div className="flex flex-wrap items-center gap-2 text-xs text-muted" role="status"><span>{legacyRun ? t("legacyRunStatus") : t(`runStatus.${busy ? "running" : run.status}`)}</span><details><summary className="cursor-pointer">{t("details")}</summary><span>{t("budget", { rounds: run.rounds, maxRounds: run.round_limit, tools: run.tool_calls, maxTools: run.tool_limit })}</span>{run.usage && <p>{t("reportedTokens", { tokens: run.usage.total_tokens })}</p>}</details></div>}
      {legacyRun && <div className="space-y-1"><p className="text-xs text-muted">{t("legacyRunReadOnly")}</p><Button size="sm" variant="ghost" onPress={() => {
        const url = URL.createObjectURL(new Blob([JSON.stringify({ run, messages: messages.filter((item) => item.run_id === run.id) }, null, 2)], { type: "application/json;charset=utf-8" }));
        const link = document.createElement("a"); link.href = url; link.download = `assistant-request-${run.id}.json`; link.click(); URL.revokeObjectURL(url);
      }}>{t("exportRequest")}</Button></div>}
      {canContinue && <div className="my-3 flex flex-wrap items-center gap-2"><span className="text-sm">{t(run.status === "budget_exhausted" ? "continueQuestion" : "resumeQuestion")}</span><Button size="sm" variant="outline" isDisabled={savingChange} onPress={() => void send(true)}>{t(run.status === "budget_exhausted" ? "continue" : "retry")}</Button></div>}
      {run?.status === "waiting_input" && run.pending_question && !run.pending_question.confirmation && <div className="my-3 flex flex-wrap gap-2">{run.pending_question.choices.map((choice) => <Button key={choice} size="sm" variant="outline" onPress={() => { setDrafts((current) => ({ ...current, [draftKey]: choice })); input.current?.focus(); }}>{choice}</Button>)}</div>}
      {unboundQuestion && <p className="my-3 text-sm text-muted">{t("legacyQuestion")}</p>}
    </div>
    <div className="shrink-0 space-y-2 border-t border-border bg-surface px-4 py-3">
      {manualChanged && <div className="flex items-center gap-2 text-xs text-muted"><span className="min-w-0 flex-1">{t("manualChanged")}</span><Button size="sm" variant="ghost" onPress={() => { setDrafts((current) => ({ ...current, [draftKey]: t("checkChangesMessage") })); setManualChanged(false); input.current?.focus(); }}>{t("checkChanges")}</Button></div>}
      {error && <p role="alert" className="max-h-24 overflow-y-auto break-words text-sm text-danger">{error}</p>}
      {attachments.length > 0 && <ul className="workspace-scrollbar flex max-h-20 flex-wrap gap-1 overflow-y-auto">{attachments.map((attachment, index) => <li key={index} className="flex min-w-0 items-center rounded-lg bg-surface-secondary pl-2 text-xs">
        <span className="max-w-52 truncate">{attachmentNames[`${attachment.resource_type}/${attachment.id}`] ?? (resource?.id === attachment.id ? resource.name : t(`kinds.${attachment.resource_type}`))} · {t(`origin.${attachment.origin}`)}</span>
        <Button isIconOnly size="sm" variant="ghost" aria-label={t("removeAttachment")} onPress={() => setAttachments((current) => current.filter((_, at) => at !== index))}>×</Button>
      </li>)}</ul>}
      <div className="flex min-w-0 items-center gap-1 text-xs text-muted"><label htmlFor="assistant-writing-target">{t("currentTarget")}</label>
        <select id="assistant-writing-target" className="min-w-0 flex-1 bg-transparent py-1 text-xs text-foreground" disabled={busy || loading || run?.status === "waiting_input"} value={displayedTarget ? `${displayedTarget.resource_type}:${displayedTarget.id}` : ""}
          onChange={(event) => setWritingTargets((current) => ({ ...current, [draftKey]: writingOptions.find((item) => `${item.resource_type}:${item.id}` === event.target.value) ?? null }))}>
          <option value="">{t("wholeBook")}</option>{writingOptions.map((item) => <option key={`${item.resource_type}:${item.id}`} value={`${item.resource_type}:${item.id}`}>{item.name}</option>)}
        </select>
      </div>
      <label className="sr-only" htmlFor="assistant-message">{t("message")}</label>
      <textarea id="assistant-message" ref={input} className={`${CONTROL} h-20 min-h-16 max-h-40 w-full resize-y leading-6`} value={message} aria-invalid={messageTooLong || undefined} aria-describedby={messageTooLong ? "assistant-message-length-error" : undefined} placeholder={t("message")} onChange={(event) => setDrafts((current) => ({ ...current, [draftKey]: event.target.value }))} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={(event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing && !composing.current) { event.preventDefault(); void send(); } }} />
      {messageTooLong && <p id="assistant-message-length-error" role="alert" className="text-sm text-danger">{t(writingTarget ? "writingMessageTooLong" : "managementMessageTooLong")}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Popover isOpen={attachmentMenuOpen && open && active} onOpenChange={(value) => { setAttachmentMenuOpen(value); if (!value) setPicker(false); }}>
          <Button isIconOnly size="sm" variant="ghost" className="h-11 w-11 shrink-0" aria-label={t("addAttachment")} isDisabled={busy}>
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          </Button>
          <Popover.Content placement="top start" className="w-72 max-w-[calc(100vw-2rem)] border border-border bg-surface-raised shadow-lg">
            <Popover.Dialog aria-label={t("addAttachment")} className="workspace-scrollbar max-h-[60dvh] overflow-y-auto p-2 text-foreground">
              <div className="flex flex-col">
                <Button size="sm" variant="ghost" className="min-h-11 justify-start" isDisabled={!resource} onPress={() => { attach("saved"); setAttachmentMenuOpen(false); }}>{t("attachCurrent")}</Button>
                <Button size="sm" variant="ghost" className="min-h-11 justify-start" isDisabled={!resource?.draft} onPress={() => { attach("draft"); setAttachmentMenuOpen(false); }}>{t("attachDraft")}</Button>
                <Button size="sm" variant="ghost" className="min-h-11 justify-start" isDisabled={!resource} onPress={() => { attach("selection"); setAttachmentMenuOpen(false); }}>{t("attachSelection")}</Button>
                <Button size="sm" variant="ghost" className="min-h-11 justify-start" aria-expanded={picker} aria-controls="assistant-resource-picker" onPress={() => setPicker((current) => !current)}>{t("attachOther")}</Button>
              </div>
              {picker && <div id="assistant-resource-picker" className="mt-2 space-y-2 border-t border-border pt-2">
                <input autoFocus className={`${CONTROL} w-full`} aria-label={t("searchResources")} placeholder={t("searchResources")} value={query} onChange={(event) => { setQuery(event.target.value); setResourceOffset(0); }} />
                <div className="max-h-40 overflow-y-auto">{resources.map((item) => <button type="button" key={`${item.resource_type}:${item.resource_id}`} className="block min-h-11 w-full rounded-sm px-2 py-2 text-left text-sm hover:bg-selected focus-visible:outline-2 focus-visible:outline-accent" onClick={() => { setAttachments((current) => [...current.slice(0, 19), { resource_type: item.resource_type, id: item.resource_id, version: item.source_version, fields: [], origin: "saved", usage: "reference" }]); setAttachmentMenuOpen(false); setPicker(false); }}>{item.name}<span className="ml-2 text-xs text-muted">{t(`kinds.${item.resource_type}`)}</span></button>)}</div>
                <div className="flex justify-between"><Button size="sm" variant="ghost" isDisabled={resourceOffset === 0} onPress={() => setResourceOffset(Math.max(0, resourceOffset - 20))}>{t("previous")}</Button><Button size="sm" variant="ghost" isDisabled={!moreResources} onPress={() => setResourceOffset(resourceOffset + 20)}>{t("next")}</Button></div>
              </div>}
            </Popover.Dialog>
          </Popover.Content>
        </Popover>
        <select aria-label={t("model")} className={`${CONTROL} flex-1`} value={settings.provider || capabilities?.default_provider || ""} disabled={loading || busy || savingSettings} onChange={(event) => void changeSetting({ provider: event.target.value, model: "" })}>{capabilities?.providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.id === (settings.provider || capabilities.default_provider) ? settings.model || provider.model : provider.model} · {provider.id}{provider.supports_function_calling ? "" : ` · ${t("unsupported")}`}</option>)}</select>
        {busy ? <Button size="sm" variant="outline" onPress={() => void stop()}>{t("stop")}</Button> : <Button size="sm" variant="primary" isDisabled={loading || savingChange || unboundQuestion || !message.trim() || messageTooLong || Boolean(session?.archived)} onPress={() => void send()}>{t("send")}</Button>}
      </div>

    </div>
  </div>;

  return <aside ref={slot} className={`relative z-20 h-full shrink-0 ${open && !narrow ? "w-[440px] border-l border-border" : "w-0"}`} aria-label={t("title")}>
    <SidebarEdgeHandle controls="novel-assistant-panel" side="left" {...(open ? { rightAction: { label: t("collapse"), onPress: close, expanded: true } } : { leftAction: { label: t("expand"), onPress: () => setOpen(true), expanded: false } })} />
    {!narrow && <div id="novel-assistant-panel" hidden={!open} className={open ? "h-full min-h-0 min-w-0" : "hidden"}>{content}</div>}
    {narrow && <RetainedModalBackdrop isOpen={open && active} onOpenChange={setOpen} isDismissable variant="blur">
      <Modal.Container scroll="inside" placement="center" className="!m-0 !ml-auto !h-dvh !max-h-dvh !w-full !max-w-[480px] !rounded-none !p-0">
        <Modal.Dialog id="novel-assistant-panel" aria-labelledby="novel-assistant-heading" className="!h-full !max-h-full !w-full !rounded-none !border-l !border-border !bg-surface-raised !p-0">
          {content}
        </Modal.Dialog>
      </Modal.Container>
    </RetainedModalBackdrop>}
  </aside>;
}
