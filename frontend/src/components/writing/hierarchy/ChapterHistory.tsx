"use client";
import { SectionActionButton } from "@/components/shared/SectionEditButton";

import { Button } from "@heroui/react";
import { useContext, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { apiGet, apiPost, ApiRequestError } from "@/lib/api";
import { readChapterRestoreConfirmations, writeChapterRestoreConfirmation, type ChapterRestoreCommand } from "./chapterRestoreConfirmations";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { ConfirmActionModal, RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import { PlanningReadout } from "./PlanningFields";
import type { ChapterRevision, ChapterRevisionComparison, EntityChoices, HierarchyNode, HierarchyRecord } from "@/types/hierarchy";

/** 功能：只读浏览历史及整稿对照，明确恢复时保存原请求并保留编辑草稿。Args: props 当前章、定位、草稿状态和保存回调。Returns: 历史清单、对照与确认。 */
export default function ChapterHistory({ node, choices, requestedVersion, dirty, onSaved, onBusy, beforeRestore, onClose }: {
  node: HierarchyNode; choices: EntityChoices; requestedVersion?: string | null; dirty: boolean;
  onSaved: (record: HierarchyRecord) => void; onBusy: (busy: boolean) => void;
  beforeRestore: () => Promise<void>; onClose: () => void;
}) {
  const t = useTranslations("writing.hierarchy");
  const locale = useLocale();
  const active = useContext(RetainedViewActive);
  const [rows, setRows] = useState<ChapterRevision[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [comparison, setComparison] = useState<ChapterRevisionComparison | null>(null);
  const requestedRevision = requestedVersion && Number.isSafeInteger(Number(requestedVersion)) && Number(requestedVersion) > 0 ? Number(requestedVersion) : null;
  const [selectedVersion, setSelectedVersion] = useState<number | null>(requestedRevision);
  const requestedSelection = useRef(requestedVersion);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [command, setCommand] = useState<ChapterRestoreCommand | null>(null);
  const [confirm, setConfirm] = useState<{ chapter_id: string; revision: number; expected_version: number } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const pending = useRef(false);
  const alive = useRef(true);
  const readId = useRef(0);
  const callbacks = useRef({ onSaved, active, version: node.record.version }); callbacks.current = { onSaved, active, version: node.record.version };
  const scope = `${node.record.novel_id}:chapter:${node.id}:history-restore`;
  const deletedQuery = node.record.is_deleted ? "include_deleted=true&" : "";

  useEffect(() => { alive.current = true; return () => { alive.current = false; readId.current += 1; }; }, []);
  useEffect(() => { onBusy(saving); return () => onBusy(false); }, [saving, onBusy]);

  useEffect(() => {
    let current = true;
    setLoading(true); setError("");
    Promise.all([
      apiGet<{ data: ChapterRevision[]; next_before_version: number | null }>(`/api/chapters/${node.id}/revisions?${deletedQuery}limit=20`),
      readChapterRestoreConfirmations(scope),
    ]).then(([page, stored]) => {
      if (!current) return;
      setRows(page.data); setCursor(page.next_before_version); setCommand(stored[0]?.value ?? null);
      // 重入先显示原恢复来源，结束后再应用当前 URL。
      if (stored[0]) requestedSelection.current = String(stored[0].value.revision);
      setSelectedVersion((value) => stored[0]?.value.revision ?? value ?? page.data[0]?.version ?? null);
    }).catch((failure) => { if (current) setError(failure instanceof Error ? failure.message : t("loadFailed")); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [node.id, deletedQuery, scope, refresh, t]);

  useEffect(() => {
    if (loading || command || requestedSelection.current === requestedVersion) return;
    requestedSelection.current = requestedVersion;
    if (requestedRevision === null || requestedRevision === selectedVersion) return;
    // 同章定位变化也要作废旧比较；未决恢复仍保留原请求，完成后再定位。
    readId.current += 1;
    setComparison(null); setConfirm(null); setSelectedVersion(requestedRevision);
  }, [requestedVersion, requestedRevision, selectedVersion, loading, command]);

  useEffect(() => {
    if (confirm && (confirm.chapter_id !== node.id || confirm.revision !== selectedVersion || confirm.expected_version !== node.record.version)) setConfirm(null);
  }, [confirm, node.id, node.record.version, selectedVersion]);

  useEffect(() => {
    if (selectedVersion === null || loading) return;
    const current = ++readId.current;
    setReading(true); setComparison(null); setError("");
    apiGet<ChapterRevisionComparison>(`/api/chapters/${node.id}/revisions/${selectedVersion}/compare?${deletedQuery}`).then((result) => {
      if (current === readId.current && alive.current) setComparison(result);
    }).catch((failure) => { if (current === readId.current && alive.current) setError(failure instanceof Error ? failure.message : t("loadFailed")); })
      .finally(() => { if (current === readId.current && alive.current) setReading(false); });
    return () => { readId.current += 1; };
  }, [selectedVersion, loading, node.id, node.record.version, deletedQuery, refresh, t]);

  const restore = async () => {
    if (pending.current || (!command && !confirm)) return;
    pending.current = true; setSaving(true); setError("");
    let frozen = command;
    try {
      await beforeRestore();
      if (!frozen) {
        frozen = { ...confirm!, key: crypto.randomUUID() };
        // 原请求先落本地，断响应或关闭后只能核对这一份请求。
        await writeChapterRestoreConfirmation(scope, frozen);
        if (alive.current) setCommand(frozen);
      }
      const saved = frozen.saved ?? await apiPost<HierarchyRecord>(`/api/chapters/${node.id}/revisions/${frozen.revision}/restore`, { expected_version: frozen.expected_version }, { headers: { "Idempotency-Key": frozen.key } });
      frozen = { ...frozen, saved };
      if (alive.current) setCommand(frozen);
      await writeChapterRestoreConfirmation(scope, frozen);
      // 原成功快照只证明这次确认完成；当前正式章必须重新读取，不能用旧回执覆盖新稿。
      const current = await apiGet<HierarchyRecord>(`/api/chapters/${node.id}`);
      if (alive.current && callbacks.current.active && current.chapter_id === node.id && current.version >= callbacks.current.version) callbacks.current.onSaved(current);
      // 清稿只清恢复请求；正文及章计划草稿始终由原编辑器管理。
      await writeChapterRestoreConfirmation(scope, frozen, true);
      if (alive.current) { setCommand(null); setConfirm(null); setRefresh((value) => value + 1); }
    } catch (failure) {
      if (!alive.current) return;
      setError(failure instanceof Error ? failure.message : t("saveFailed"));
      if (!frozen?.saved && frozen && failure instanceof ApiRequestError && [400, 403, 404, 409, 422].includes(failure.status) && !["CHAPTER_WRITE_CONFLICT", "DATABASE_UNAVAILABLE"].includes(failure.code ?? "")) {
        // 确定拒绝才允许重新比较；未知结果保持原键，绝不自动换版本覆盖。
        try { await writeChapterRestoreConfirmation(scope, frozen, true); setCommand(null); setConfirm(null); setRefresh((value) => value + 1); }
        catch { setError(t("draftFailed")); }
      }
    } finally { pending.current = false; if (alive.current) setSaving(false); }
  };

  const more = async () => {
    if (!cursor || reading) return;
    setReading(true); setError("");
    try {
      const page = await apiGet<{ data: ChapterRevision[]; next_before_version: number | null }>(`/api/chapters/${node.id}/revisions?${deletedQuery}limit=20&before_version=${cursor}`);
      if (alive.current) { setRows((current) => [...current, ...page.data.filter((row) => !current.some((item) => item.version === row.version))]); setCursor(page.next_before_version); }
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : t("loadFailed")); }
    finally { if (alive.current) setReading(false); }
  };

  return <section className="@container/history flex min-h-0 flex-1 flex-col gap-3" aria-label={t("history.title")}>
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-2">
      <h2 className="text-base font-semibold">{t("history.title")}</h2>
      <Button size="sm" variant="ghost" isDisabled={saving} onPress={onClose}>{t("history.back")}</Button>
    </header>
    {error && <RelationEditorErrorSummary message={error} />}
    {command && <div role="status" className="border-y border-amber-500/50 py-3 text-sm">
      <p>{t(command.saved ? "history.savedCleanup" : "history.unknown")}</p>
      <Button size="sm" variant="outline" isDisabled={saving || loading || node.record.is_deleted} onPress={() => void restore()}>{t(command.saved ? "history.finish" : "history.retryRestore")}</Button>
    </div>}
    {loading ? <p role="status">{t("loading")}</p> : <>
      <div className="flex shrink-0 flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1 text-xs text-muted">{t("history.version")}
          <select aria-label={t("history.version")} value={selectedVersion ?? ""} disabled={saving || Boolean(command)} onChange={(event) => setSelectedVersion(Number(event.target.value))} className="mt-1 min-h-11 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground">
            {selectedVersion !== null && !rows.some((row) => row.version === selectedVersion) && <option value={selectedVersion}>{t("version", { version: selectedVersion })}</option>}
            {!rows.length && selectedVersion === null && <option value="">{t("history.empty")}</option>}
            {rows.map((row) => <option key={row.revision_id} value={row.version}>{t("version", { version: row.version })} · {row.restored_from_version ? t("history.restoredFrom", { version: row.restored_from_version }) : t(`history.sources.${row.source}`)} · {new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(row.saved_at))}</option>)}
          </select>
        </label>
        {cursor && <Button size="sm" variant="outline" isDisabled={reading || saving} onPress={() => void more()}>{t("history.more")}</Button>}
        <SectionActionButton action="refresh" label={t("refresh")} size="sm" variant="ghost" isDisabled={saving || Boolean(command)} onPress={() => setRefresh((value) => value + 1)} />
      </div>
      {reading && <p role="status">{t("loading")}</p>}
      {comparison && <>
        {comparison.current.version !== node.record.version && <div role="alert" className="border-y border-amber-500/50 py-3 text-sm"><p>{t("history.currentChanged")}</p><Button size="sm" variant="outline" isDisabled={saving || Boolean(command)} onPress={() => onSaved(comparison.current)}>{t("history.readCurrent")}</Button></div>}
        <Button size="sm" variant="ghost" className="self-start" onPress={() => { void (async () => {
          const url = new URL(window.location.href);
          url.search = new URLSearchParams({ workspace: "chapter-editor", volume_id: node.record.volume_id, arc_id: node.record.arc_id!, scene_id: node.record.scene_id!, chapter_id: node.id, revision_version: String(comparison.revision.version) }).toString();
          try { await navigator.clipboard.writeText(url.toString()); }
          catch { setError(t("history.copyFailed")); }
        })(); }}>{t("history.copyLocation")}</Button>
        <p className="text-xs text-muted">{comparison.changed_fields.length ? t("history.changed", { fields: comparison.changed_fields.map((field) => field === "content" ? t("body") : field === "planning" ? t("plan") : t(`fields.${field}`)).join(locale === "zh" ? "、" : ", ") }) : t("history.same")}</p>
        {dirty && <p role="status" className="border-l-2 border-amber-500 px-3 text-sm">{t("history.draftKept")}</p>}
        <div className="grid shrink-0 gap-4 @min-[760px]/history:grid-cols-2">
          {[comparison.revision, comparison.current].map((record, index) => <section key={index} aria-label={t(index === 0 ? "history.old" : "history.current")} className="min-w-0 border-t border-border pt-3">
            <h3 className="mb-3 text-sm font-semibold">{t(index === 0 ? "history.old" : "history.current")} · {t("version", { version: record.version })}</h3>
            <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("plan")}</summary><PlanningReadout record={record as HierarchyRecord} choices={choices} /></details>
            <div className="workspace-scrollbar mt-3 max-h-[55dvh] overflow-y-auto border-t border-border py-3 outline-none focus-visible:ring-2 focus-visible:ring-accent" tabIndex={0} aria-label={t(index === 0 ? "history.oldBody" : "history.currentBody")}>
              <pre className="reading-copy whitespace-pre-wrap font-sans">{record.content || t("none")}</pre>
            </div>
          </section>)}
        </div>
        {!node.record.is_deleted && <Button className="self-start" size="sm" variant="primary" isDisabled={reading || saving || Boolean(command) || comparison.current.version !== node.record.version} onPress={() => { setConfirm({ chapter_id: node.id, revision: comparison.revision.version, expected_version: comparison.current.version }); setError(""); }}>{t("history.restore")}</Button>}
      </>}
    </>}
    {confirm && <ConfirmActionModal title={t("history.restore")} message={<><p>{t("history.confirm", { old: confirm.revision, current: confirm.expected_version })}</p>{comparison?.restore_normalizes_text && <p className="mt-2">{t("history.normalize")}</p>}{dirty && <p className="mt-2">{t("history.draftKept")}</p>}</>} confirmText={t("history.restore")} cancelText={t("cancel")} isLoading={saving} error={error} onCancel={() => setConfirm(null)} onConfirm={() => void restore()} />}
  </section>;
}
