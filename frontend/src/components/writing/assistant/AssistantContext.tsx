"use client";

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { apiGet } from "@/lib/api";
import { subscribeResourceChanges } from "@/lib/resourceChanges";
import type { ActiveAssistantResource, AssistantCapabilities, ContextAttachment, NavigationTarget } from "@/types/assistant";

interface AssistantContextValue {
  novelId?: string; enabled: boolean; active: boolean; open: boolean;
  capabilities: AssistantCapabilities | null;
  resource: ActiveAssistantResource | null;
  requestedAttachment: ContextAttachment | null;
  focus: { target: NavigationTarget; serial: number } | null;
  opener: { current: HTMLElement | null };
  setOpen: (open: boolean) => void;
  register: (key: string, resource: ActiveAssistantResource | null) => void;
  openFor: (attachment?: ContextAttachment) => void;
  consumeAttachment: () => void;
  navigate: (target: NavigationTarget) => void;
}
const AssistantContext = createContext<AssistantContextValue>({ enabled: false, active: false, open: false, capabilities: null, resource: null, requestedAttachment: null, focus: null, opener: { current: null },
  setOpen: () => {}, register: () => {}, openFor: () => {}, consumeAttachment: () => {}, navigate: () => {} });

/** 小说级助手控制器放在工作台缓存外层，切页和折叠都不重建对话。
 * Args: novelId 当前小说；active 当前页面可见性；onNavigate 原页面导航；children 工作区。
 * Returns: 常驻的对话上下文。
 */
export function AssistantProvider({ novelId, active, onNavigate, initialFocus, children }: { novelId?: string; active: boolean; onNavigate: (target: NavigationTarget) => Promise<boolean>; initialFocus?: NavigationTarget; children: ReactNode }) {
  const [open, updateOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const setOpen = useCallback((next: boolean) => {
    // 已展开时追加资料不改变这次打开的入口。
    if (next && !open) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    updateOpen(next);
  }, [open]);
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [resources, setResources] = useState<Record<string, ActiveAssistantResource>>({});
  const selection = Object.values(resources).sort((a, b) => Number(Boolean(b.draft)) - Number(Boolean(a.draft)))[0] ?? null;
  const [requestedAttachment, setRequestedAttachment] = useState<ContextAttachment | null>(null);
  const [focus, setFocus] = useState<AssistantContextValue["focus"]>(() => initialFocus ? { target: initialFocus, serial: 1 } : null);
  const focusKey = initialFocus ? JSON.stringify(initialFocus) : "";
  const [seenFocusKey, setSeenFocusKey] = useState(focusKey);
  if (focusKey !== seenFocusKey) {
    setSeenFocusKey(focusKey);
    if (initialFocus) setFocus({ target: initialFocus, serial: (focus?.serial ?? 0) + 1 });
  }
  const current = useRef({ active, onNavigate });
  useEffect(() => { current.current = { active, onNavigate }; }, [active, onNavigate]);
  useEffect(() => {
    if (!novelId) return;
    const abort = new AbortController();
    void apiGet<AssistantCapabilities>(`/api/novels/${novelId}/assistant/capabilities`, { signal: abort.signal }).then(setCapabilities).catch(() => { /* 原编辑入口在能力查询失败时仍可用。 */ });
    return () => abort.abort();
  }, [novelId]);
  const register = useCallback((key: string, resource: ActiveAssistantResource | null) => {
    setResources((current) => {
      if (resource) return { ...current, [key]: resource };
      if (!(key in current)) return current;
      const next = { ...current }; delete next[key]; return next;
    });
  }, []);
  const openFor = useCallback((attachment?: ContextAttachment) => { setRequestedAttachment(attachment ?? null); setOpen(true); }, [setOpen]);
  const consumeAttachment = useCallback(() => setRequestedAttachment(null), []);
  const navigate = useCallback((target: NavigationTarget) => {
    if (!current.current.active) return;
    void current.current.onNavigate(target).then((accepted) => {
      if (accepted && current.current.active) setFocus((previous) => ({ target, serial: (previous?.serial ?? 0) + 1 }));
    });
  }, []);
  const value = useMemo(() => ({ novelId, enabled: Boolean(novelId && capabilities?.enabled), active, open, setOpen, opener, capabilities,
    resource: selection, register, requestedAttachment, focus, openFor, consumeAttachment, navigate }), [novelId, capabilities, active, open, setOpen, selection, register, requestedAttachment, focus, openFor, consumeAttachment, navigate]);
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

/** 读取当前小说的助手控制器。
 * Args: 无。
 * Returns: 只控制当前小说的对话状态。
 */
export function useNovelAssistant() { return useContext(AssistantContext); }

/** 定位当前可见工作台中的对象，不重建它已有的编辑草稿。
 * Args: kind 工作台对象类型；select 原有的选择操作。
 * Returns: 无。
 */
export function useAssistantFocus(kind: NavigationTarget["resource_type"], select: (target: NavigationTarget) => void | boolean): void {
  const { focus } = useNovelAssistant();
  const active = useContext(RetainedViewActive);
  const latest = useRef(select);
  const consumed = useRef(0);
  useEffect(() => { latest.current = select; });
  useEffect(() => {
    if (!active || !focus || focus.target.resource_type !== kind || consumed.current === focus.serial) return;
    if (latest.current(focus.target) !== false) consumed.current = focus.serial;
  });
}

/** 登记当前工作台实际选中的资料和明确草稿；隐藏页面不能覆盖当前选择。
 * Args: resource 当前选中记录，草稿保留编辑开始时的版本。
 * Returns: 无。
 */
export function useAssistantResource(resource: ActiveAssistantResource | null): void {
  const key = useId();
  const active = useContext(RetainedViewActive);
  const { register, enabled } = useNovelAssistant();
  const serialized = JSON.stringify(resource);
  useEffect(() => {
    if (active && enabled && serialized !== "null") register(key, JSON.parse(serialized) as ActiveAssistantResource);
    else register(key, null);
    return () => register(key, null);
  }, [active, enabled, serialized, key, register]);
}

/** 刷新工作台已保存记录；各编辑器继续持有自己的草稿和原版本。
 * Args: novelId 当前小说；reload 原工作台的读取函数。
 * Returns: 无，不发起模型请求。
 */
export function useAssistantRefresh(novelId: string | undefined, reload: () => void | Promise<void>): void {
  const latest = useRef(reload);
  useEffect(() => { latest.current = reload; }, [reload]);
  useEffect(() => subscribeResourceChanges((notice) => {
    if (notice.source === "assistant" && novelId && notice.novelId === novelId) void latest.current();
  }), [novelId]);
}
