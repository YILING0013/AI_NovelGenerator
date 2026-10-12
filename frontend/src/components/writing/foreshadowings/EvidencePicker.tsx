"use client";

import { Button } from "@heroui/react";
import { useContext, useEffect, useRef, useState } from "react";
import { RetainedViewActive } from "@/components/layout/RetainedViews";
import { useTranslations } from "next-intl";
import { apiGet } from "@/lib/api";
import { RelationEditorErrorSummary } from "@/components/shared/RelationEditorPrimitives";
import type { ChapterRevision, HierarchyRecord } from "@/types/hierarchy";
import type { ForeshadowingEvidence, ForeshadowingEvidenceInput } from "@/types/foreshadowing";
import type { ChapterPsychologicalCheckSourceV1, ChapterRecordSourceReadV1 } from "@/types/chapterRecords";

export const FORESHADOWING_INPUT = "min-h-11 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3 py-2 text-sm text-foreground focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:opacity-60";

/** 功能：从真实章节历史挑选原文，或只读精确定位既有证据。Args: props 同书目录、证据及更新回调。Returns: 历史目录、原文和码点范围。 */
export default function EvidencePicker({ novelId, chapters, value, fixedSource, initialSource, onChange, onSelectEvidence, onSelectRevision, chapterRecordSource = false, readOnly = false, disabled = false, label }: {
  novelId: string; chapters: HierarchyRecord[]; value: ForeshadowingEvidenceInput | ForeshadowingEvidence | null;
  onChange?: (value: ForeshadowingEvidenceInput | null) => void; onSelectEvidence?: (value: ForeshadowingEvidence) => void; chapterRecordSource?: boolean; readOnly?: boolean; disabled?: boolean; label: string;
  /** 固定检查使用的整章来源；仍允许选择或清除引文。 */
  fixedSource?: ChapterPsychologicalCheckSourceV1;
  /** 恢复检查稿时重读原修订，不替作者选取报告引文。 */
  initialSource?: ChapterPsychologicalCheckSourceV1;
  /** 核验书、章、版本和正文哈希后回传整章来源；来源切换或清空时立即回传 null。 */
  onSelectRevision?: (revision: ChapterPsychologicalCheckSourceV1 | null) => void;
}) {
  const t = useTranslations("writing.foreshadowings");
  const recordT = useTranslations("writing.chapterRecords");
  const requireIdentity = Boolean(onSelectEvidence);
  const selectRevision = Boolean(onSelectRevision);
  const active = useContext(RetainedViewActive);
  const [selectedChapter, setChapter] = useState(value?.chapter_id ?? initialSource?.chapter_id ?? "");
  const [selectedVersion, setVersion] = useState<number | null>(value?.version ?? initialSource?.version ?? null);
  const chapter = fixedSource?.chapter_id ?? selectedChapter;
  const version = fixedSource?.version ?? selectedVersion;
  const fixed = Boolean(fixedSource);
  const fixedRevisionId = fixedSource?.revision_id;
  const fixedContentHash = fixedSource?.content_hash;
  const [rows, setRows] = useState<ChapterRevision[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [revision, setRevision] = useState<ChapterRevision | null>(null);
  const [search, setSearch] = useState("");
  const [start, setStart] = useState(value?.start ?? 0);
  const [length, setLength] = useState(value ? Array.from(value.quote).length : 0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [directoryLoading, setDirectoryLoading] = useState(false);
  const [more, setMore] = useState(false);
  const [deletedSources, setDeletedSources] = useState<ChapterRecordSourceReadV1["deleted_sources"]>([]);
  const directoryId = useRef(0);
  const bodyRef = useRef<HTMLPreElement>(null);
  const onSelectRevisionRef = useRef(onSelectRevision);
  const evidenceIdentity = readOnly ? JSON.stringify(value) : "";

  // 父层改回调不应重新加载原文，也不能触发回传与重渲染的循环。
  useEffect(() => { onSelectRevisionRef.current = onSelectRevision; }, [onSelectRevision]);

  useEffect(() => {
    if (!chapter || readOnly || fixed || !active) { setDirectoryLoading(false); return; }
    const abort = new AbortController();
    const id = ++directoryId.current;
    setDirectoryLoading(true); setError("");
    apiGet<{ data: ChapterRevision[]; next_before_version: number | null }>(`/api/chapters/${chapter}/revisions?limit=50`, { signal: abort.signal }).then((page) => {
      if (abort.signal.aborted || id !== directoryId.current) return;
      setRows(page.data); setCursor(page.next_before_version);
    }).catch((failure) => { if (!abort.signal.aborted) setError(failure.message); })
      .finally(() => { if (!abort.signal.aborted && id === directoryId.current) setDirectoryLoading(false); });
    return () => { abort.abort(); directoryId.current += 1; };
  }, [chapter, readOnly, fixed, active]);

  useEffect(() => {
    onSelectRevisionRef.current?.(null);
    setRevision(null); setError(""); setDeletedSources([]);
    if (!chapter || version === null || !active) { setLoading(false); return; }
    const abort = new AbortController();
    setLoading(true);
    const stored: ForeshadowingEvidence | null = evidenceIdentity ? JSON.parse(evidenceIdentity) : null;
    const request = chapterRecordSource && readOnly
      ? apiGet<ChapterRecordSourceReadV1>(`/api/chapter-records/novel/${novelId}/chapters/${chapter}/revisions/${version}`, { signal: abort.signal }).then((source) => { if (!abort.signal.aborted) setDeletedSources(source.deleted_sources); return source.revision; })
      : apiGet<ChapterRevision>(`/api/chapters/${chapter}/revisions/${version}${readOnly ? "?include_deleted=true" : ""}`, { signal: abort.signal });
    request.then(async (result) => {
      if (abort.signal.aborted) return;
      if (result.novel_id !== novelId || result.chapter_id !== chapter || result.version !== version || !Number.isSafeInteger(version) || version < 1) throw new Error(t("wrongRevision"));
      if (fixed && (result.revision_id !== fixedRevisionId || result.content_hash !== fixedContentHash)) throw new Error(t("wrongRevision"));
      if (stored && (stored.revision_id !== result.revision_id || stored.content_hash !== result.content_hash)) throw new Error(t("wrongRevision"));
      if (stored) {
        const points = Array.from(result.content);
        const length = Array.from(stored.quote).length;
        if (!Number.isSafeInteger(stored.start) || stored.start < 0 || !length || stored.start + length > points.length || points.slice(stored.start, stored.start + length).join("") !== stored.quote) throw new Error(t("wrongRevision"));
      }
      if (stored || fixed || requireIdentity || selectRevision) {
        const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(result.content));
        if (Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("") !== result.content_hash) throw new Error(t("wrongRevision"));
      }
      if (!abort.signal.aborted) {
        setRevision(result);
        onSelectRevisionRef.current?.({ chapter_id: result.chapter_id, revision_id: result.revision_id, version: result.version, content_hash: result.content_hash });
      }
    }).catch((failure) => { if (!abort.signal.aborted) setError(failure.message); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => { abort.abort(); onSelectRevisionRef.current?.(null); };
  }, [chapter, version, novelId, readOnly, t, evidenceIdentity, active, requireIdentity, selectRevision, chapterRecordSource, fixed, fixedRevisionId, fixedContentHash]);

  useEffect(() => { if (readOnly && revision && active) bodyRef.current?.querySelector("mark")?.scrollIntoView({ block: "center" }); }, [revision, readOnly, active]);
  const points = Array.from(revision?.content ?? "");
  const valid = Number.isSafeInteger(start) && Number.isSafeInteger(length) && length > 0 && length <= 10000 && start >= 0 && start + length <= points.length;
  const matches: number[] = [];
  if (revision && search) {
    let offset = revision.content.indexOf(search);
    while (offset !== -1) {
      matches.push(Array.from(revision.content.slice(0, offset)).length);
      offset = revision.content.indexOf(search, offset + 1);
    }
  }

  return <section aria-label={label} className="grid min-w-0 gap-3">
    {!readOnly && !fixed && <>
      <label className="grid min-w-0 gap-1 text-xs text-muted">{t("chapter")}<select className={FORESHADOWING_INPUT} value={chapter} disabled={disabled} onChange={(event) => {
        onSelectRevisionRef.current?.(null);
        setChapter(event.target.value); setVersion(null); setRevision(null); setRows([]); setCursor(null); setSearch(""); setStart(0); setLength(0); setMore(false);
      }}><option value="">{t("chooseChapter")}</option>{chapters.map((row) => <option key={row.chapter_id} value={row.chapter_id}>{row.title}</option>)}</select></label>
      {chapter && <label className="grid gap-1 text-xs text-muted">{t("revision")}<select className={FORESHADOWING_INPUT} value={version ?? ""} disabled={disabled} onChange={(event) => {
        onSelectRevisionRef.current?.(null);
        setVersion(Number(event.target.value) || null); setRevision(null); setStart(0); setLength(0);
      }}><option value="">{t("chooseRevision")}</option>{rows.map((row) => <option key={row.revision_id} value={row.version}>{t("version", { version: row.version })} · {row.title}</option>)}</select></label>}
      {chapter && !directoryLoading && !error && rows.length === 0 && <p role="status" className="text-sm text-muted">{t("noRevisions")}</p>}
      {cursor !== null && <Button variant="outline" isDisabled={disabled || more} onPress={async () => {
        const id = directoryId.current; setMore(true); setError("");
        try { const page = await apiGet<{ data: ChapterRevision[]; next_before_version: number | null }>(`/api/chapters/${chapter}/revisions?limit=50&before_version=${cursor}`);
          if (id === directoryId.current) { setRows((old) => [...old, ...page.data]); setCursor(page.next_before_version); }
        } catch (failure) { if (id === directoryId.current) setError((failure as Error).message); }
        finally { if (id === directoryId.current) setMore(false); }
      }}>{t("more")}</Button>}
    </>}
    {(loading || directoryLoading) && <p role="status">{t("loading")}</p>}
    {error && <RelationEditorErrorSummary message={error} />}
    {deletedSources.length > 0 && <p role="status" className="border-l-2 border-amber-500 px-3 text-sm">{recordT("deletedSources", { sources: deletedSources.map((kind) => recordT(`sourceKinds.${kind}`)).join(" / ") })}</p>}
    {revision && <>
      <p className="text-xs text-muted">{revision.title} · {t("version", { version: revision.version })}</p>
      <pre ref={bodyRef} tabIndex={0} aria-label={t("historicalBody")} className="reading-copy workspace-scrollbar max-h-80 w-full min-w-0 overflow-y-auto whitespace-pre-wrap break-words border-y border-border py-3 focus-visible:outline-2 focus-visible:outline-accent">{readOnly && value ? <>{points.slice(0, value.start).join("")}<mark className="bg-selected text-foreground" tabIndex={-1}>{value.quote}</mark>{points.slice(value.start + Array.from(value.quote).length).join("")}</> : revision.content}</pre>
      {!readOnly && <>
        <label className="grid gap-1 text-xs text-muted">{t("findQuote")}<textarea className={FORESHADOWING_INPUT} value={search} disabled={disabled} onChange={(event) => setSearch(event.target.value)} /></label>
        {search && <fieldset className="grid min-w-0 gap-2"><legend className="text-xs text-muted">{t("occurrences", { count: matches.length })}</legend>{matches.map((offset, index) => <label key={offset} className="flex min-h-11 items-center gap-2 text-sm"><input type="radio" name={`${label}-occurrence`} disabled={disabled} checked={start === offset && length === Array.from(search).length} onChange={() => { setStart(offset); setLength(Array.from(search).length); }} />{t("occurrence", { index: index + 1, start: offset })}</label>)}</fieldset>}
        <div className="detail-fields">
          <label className="grid gap-1 text-xs text-muted">{t("start")}<input className={FORESHADOWING_INPUT} type="number" min={0} max={points.length} value={start} disabled={disabled} onChange={(event) => setStart(Number(event.target.value))} /></label>
          <label className="grid gap-1 text-xs text-muted">{t("length")}<input className={FORESHADOWING_INPUT} type="number" min={0} max={10000} value={length} disabled={disabled} onChange={(event) => setLength(Number(event.target.value))} /></label>
        </div>
        <pre aria-label={t("selectedQuote")} className="reading-copy min-w-0 whitespace-pre-wrap break-words">{valid ? points.slice(start, start + length).join("") : ""}</pre>
        <Button variant="outline" isDisabled={disabled || !valid} onPress={() => {
          const evidence = { chapter_id: chapter, version: revision.version, start, quote: points.slice(start, start + length).join("") };
          if (onSelectEvidence) onSelectEvidence({ ...evidence, revision_id: revision.revision_id, content_hash: revision.content_hash });
          else onChange?.(evidence);
        }}>{t("useQuote")}</Button>
      </>}
    </>}
    {value && !readOnly && <div className="flex min-w-0 flex-wrap items-center gap-2"><pre className="reading-copy min-w-0 flex-1 whitespace-pre-wrap break-words">{value.quote}</pre><Button variant="ghost" isDisabled={disabled} onPress={() => {
      // 固定检查仍使用整章；清除引文后可以在同一修订重新选取。
      setSearch(""); setStart(0); setLength(0);
      if (!fixed) {
        onSelectRevisionRef.current?.(null);
        if (selectRevision) { setVersion(null); setRevision(null); }
      }
      onChange?.(null);
    }}>{t("clearEvidence")}</Button></div>}
  </section>;
}
