"use client";
import { useAssistantResource } from "../assistant/AssistantContext";

import { Button } from "@heroui/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { apiGet, apiPut, ApiRequestError } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { HierarchyNode, HierarchyRecord } from "@/types/hierarchy";
import type { EntityChoices } from "@/types/hierarchy";
import ChapterHistory from "./ChapterHistory";

/** 功能：编辑当前章纯文本，保留本地稿并按已读版本明确保存。Args: props 章节详情、页签、当前正文状态、操作及保存和脏稿回调。Returns: 章节工具栏、正文及冲突对照区。 */
export default function ChapterBodyEditor({ node, onSaved, onHistorySaved, onDirty, navigation, bodyActive = true, inactiveActions, panelId, generationAction, choices, requestedVersion, onBusy }: {
  node: HierarchyNode; onSaved: (record: HierarchyRecord) => void; onDirty: (dirty: boolean) => void;
  generationAction?: ReactNode;
  navigation?: ReactNode;
  bodyActive?: boolean;
  inactiveActions?: ReactNode;
  panelId?: string;
  choices?: EntityChoices; requestedVersion?: string | null; onBusy?: (busy: boolean) => void;
  onHistorySaved?: (record: HierarchyRecord) => void;
}) {
  const t = useTranslations("writing.hierarchy");
  const initial = node.record.content!;
  const [content, setContent] = useState(initial);
  const [version, setVersion] = useState(node.record.version);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [storageError, setStorageError] = useState("");
  const [latest, setLatest] = useState<HierarchyRecord | null>(null);
  const [historyOpen, setHistoryOpen] = useState(Boolean(requestedVersion));
  const [historyBusy, setHistoryBusy] = useState(false);
  const savePending = useRef(false);
  const writes = useRef(Promise.resolve());
  const recordRef = useRef(node.record);
  const key = `${node.record.novel_id}:chapter:${node.id}:body`;
  const dirty = content !== initial || version !== node.record.version;

  useEffect(() => { if (requestedVersion) setHistoryOpen(true); }, [requestedVersion]);
  useEffect(() => { onBusy?.(saving || historyBusy); return () => onBusy?.(false); }, [saving, historyBusy, onBusy]);

  useAssistantResource({ resource_type: "chapter", id: node.id, name: node.record.title, version: node.record.version, draft: dirty ? { text: content, fields: ["content"], version } : undefined });

  useEffect(() => {
    const previous = recordRef.current;
    if (previous.version === node.record.version) return;
    recordRef.current = node.record;
    // 远端保存只替换未改过的正文；已有草稿保留其原版本并显示冲突。
    if (content === previous.content && version === previous.version) {
      setContent(node.record.content!); setVersion(node.record.version);
    } else if (version !== node.record.version) setLatest(node.record);
  }, [node.record, content, version]);

  useEffect(() => {
    let active = true;
    readWritingDraft<string>(key, recordRef.current.version).then((draft) => {
      if (!active) return;
      if (draft) {
        setContent(draft.value);
        setVersion(draft.base_version);
        if (draft.base_version !== recordRef.current.version) setLatest(recordRef.current);
      }
    }).catch(() => { if (active) setStorageError(t("draftFailed")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [key, t]);

  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);

  useEffect(() => {
    if (loading || saving) return;
    // 正文还落后于新读到的版本时，先等同步或冲突判断；用户已接受的新版本仍可存稿。
    if (version < node.record.version && !latest) return;
    writes.current = writes.current.then(() => writeWritingDraft(key, version, dirty ? content : null))
      .catch(() => setStorageError(t("draftFailed")));
  }, [content, dirty, key, latest, loading, node.record.version, saving, t, version]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const save = async () => {
    if (savePending.current) return;
    savePending.current = true;
    setSaving(true); setError("");
    try {
      const saved = await apiPut<HierarchyRecord>(`/api/chapters/${node.id}`, { expected_version: version, content });
      await writes.current;
      await writeWritingDraft(key, version, null).catch(() => setStorageError(t("draftFailed")));
      setContent(saved.content!); setVersion(saved.version); setLatest(null);
      onSaved(saved);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      if (failure instanceof ApiRequestError && failure.status === 409) {
        try { setLatest(await apiGet<HierarchyRecord>(`/api/chapters/${node.id}`)); }
        catch (readFailure) { setError(readFailure instanceof Error ? readFailure.message : t("loadFailed")); }
      }
    } finally { savePending.current = false; setSaving(false); }
  };

  // 切换页签只隐藏正文，保留页签节点、输入和本地稿。
  return <>
    <header className="sticky top-0 z-10 mb-3 flex min-h-11 shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-background pb-2">
      <span role={bodyActive ? "status" : undefined} className="shrink-0 text-xs tabular-nums text-muted">{t("version", { version: bodyActive ? version : node.record.version })}{bodyActive && <> · {loading ? t("loading") : saving ? t("saving") : dirty ? t("unsaved") : t("saved")}</>}{node.record.is_deleted ? ` · ${t("trashed")}` : ""}</span>
      {navigation}
      {!bodyActive || historyOpen && node.record.is_deleted ? inactiveActions : !historyOpen && <div className="ml-auto flex flex-wrap gap-2">
        <Button size="sm" variant="primary" isDisabled={!dirty || loading || saving || Boolean(latest) || node.record.is_deleted} onPress={() => void save()}>{saving ? t("saving") : t("saveBody")}</Button>
        <Button id={`chapter-history-${node.id}`} size="sm" variant="outline" isDisabled={loading || saving} onPress={() => setHistoryOpen(true)}>{t("history.title")}</Button>
        {generationAction}
      </div>}
    </header>
    <div id={bodyActive ? panelId : undefined} role={panelId ? "tabpanel" : undefined} aria-labelledby={panelId ? `chapter-${node.id}-tab-true` : undefined} className={`${bodyActive ? "flex" : "hidden"} min-h-0 flex-1 flex-col`}>
    {historyOpen && <ChapterHistory key={node.id} node={node} choices={choices ?? { character_ids: [], faction_ids: [], location_ids: [], item_ids: [], rule_ids: [] }} requestedVersion={requestedVersion} dirty={dirty} onSaved={onHistorySaved ?? onSaved} onBusy={setHistoryBusy} beforeRestore={async () => {
      await writes.current;
      // 离开正文前再次确认本机稿写完；写失败就保留输入，不发恢复请求。
      if (dirty) await writeWritingDraft(key, version, content);
    }} onClose={() => { setHistoryOpen(false); requestAnimationFrame(() => document.getElementById(`chapter-history-${node.id}`)?.focus()); }} />}
    <section className={`${historyOpen ? "hidden" : "flex"} min-h-0 flex-1 flex-col gap-3`} aria-label={t("body")}>
    {storageError && <RelationEditorErrorSummary message={storageError} />}
    {error && <RelationEditorErrorSummary message={error} />}
    {latest && <div className="shrink-0 border-y border-amber-500/50 px-3 py-3" role="alert">
      <p className="text-sm">{t("conflict")}</p>
      <details className="mt-2"><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("latestBody")}</summary><pre className="workspace-scrollbar max-h-60 overflow-y-auto whitespace-pre-wrap reading-copy font-sans">{latest.content}</pre></details>
      <Button size="sm" variant="outline" onPress={() => { void (async () => {
        await writes.current;
        await writeWritingDraft(key, version, null).catch(() => setStorageError(t("draftFailed")));
        setVersion(latest.version); setLatest(null); setError("");
      })(); }}>{t("useLatestVersion")}</Button>
    </div>}
    <label htmlFor="chapter-body" className="sr-only">{t("body")}</label>
    <textarea id="chapter-body" name="content" value={content} disabled={loading || saving || node.record.is_deleted} onChange={(event) => setContent(event.target.value)} className="workspace-scrollbar min-h-80 flex-1 resize-y rounded-xl border border-border bg-background px-4 py-4 text-[15px] leading-[1.85] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-accent/30" />
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
      <span className="text-xs tabular-nums text-muted">{t("characters", { count: Array.from(content.replace(/\s/g, "")).length })}</span>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="ghost" isDisabled={loading || saving} onPress={() => {
          const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
          const url = URL.createObjectURL(blob); const link = document.createElement("a");
          link.href = url; link.download = `${node.record.title}.txt`; link.click(); URL.revokeObjectURL(url);
        }}>{t("exportDraft")}</Button>
        <Button size="sm" variant="ghost" isDisabled={!dirty || loading || saving} onPress={() => { void (async () => {
          await writes.current;
          await writeWritingDraft(key, version, null).catch(() => setStorageError(t("draftFailed")));
          setContent(node.record.content!); setVersion(node.record.version); setLatest(null); setError("");
        })(); }}>{t("discardLocalDraft")}</Button>
      </div>
    </div>
  </section></div></>;
}
