"use client";

import { useContext, useEffect, useRef, useState } from "react";
import { Button, Modal } from "@heroui/react";
import { useTranslations } from "next-intl";
import { RetainedModalBackdrop, RetainedViewActive } from "@/components/layout/RetainedViews";
import { SectionActionButton } from "@/components/shared/SectionEditButton";
import ReadOnlyField from "@/components/shared/ReadOnlyField";
import TagList from "@/components/shared/TagList";
import EvidencePicker from "../foreshadowings/EvidencePicker";
import FactionFactValue from "../factions/FactionFactValue";
import { apiGet, ApiRequestError } from "@/lib/api";
import type { VolumeLaunchContextV1 } from "@/types/volume";
import type { CharacterFactRecordV1 } from "@/types/characterFacts";
import type { FactionFactRecordV1 } from "@/types/factionFacts";
import type { CharacterRelationFactRecordV1 } from "@/types/characterRelationFacts";

type Entity = VolumeLaunchContextV1["entities"][number];
type Source = CharacterFactRecordV1 | FactionFactRecordV1 | CharacterRelationFactRecordV1;
const reviewReasons = new Set(["needs_review", "voided", "unresolved_reference"]);

/** 功能：原启动表单旁只读显示本卷资料范围和待复核对象。Args: 固定小说和目标卷。Returns: 紧凑提醒及原文来源，不影响原生成输入。 */
export default function VolumeLaunchContextNotice({ novelId, volumeId, onProcess }: {
  novelId: string; volumeId: string; onProcess?: (kind: "character" | "faction", id: string) => void;
}) {
  const t = useTranslations("writing.volumes.ai.launchContext");
  const common = useTranslations("writing.characterFacts");
  const wrongScope = common("wrongScope");
  const faction = useTranslations("writing.factionFacts");
  const relation = useTranslations("writing.characterRelationFacts");
  const active = useContext(RetainedViewActive);
  const [result, setResult] = useState<VolumeLaunchContextV1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [source, setSource] = useState<{ entity: Entity; record: Source } | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [sourceLoading, setSourceLoading] = useState("");
  const sourceRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!active) return;
    const abort = new AbortController(); setLoading(true); setError("");
    void apiGet<VolumeLaunchContextV1>(`/api/llm/novels/${novelId}/planning/volumes/${volumeId}/launch-context`, { signal: abort.signal }).then((value) => {
      if (abort.signal.aborted) return;
      if (value.novel_id !== novelId || value.volume_id !== volumeId || value.position.target_type !== "volume" || value.position.target_id !== volumeId) throw new Error(wrongScope);
      setResult(value);
    }).catch((failure) => {
      if (abort.signal.aborted) return;
      setError(failure.message);
      if (failure instanceof ApiRequestError && [403, 404].includes(failure.status)) setResult(null);
    }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [active, novelId, volumeId, refresh, wrongScope]);
  useEffect(() => { setSourceLoading(""); return () => { sourceRequest.current?.abort(); }; }, [active, novelId, volumeId]);
  const entities = result?.entities.map((entity) => ({ ...entity, issues: entity.issues.filter((issue) => reviewReasons.has(issue.reason)) })).filter((entity) => entity.issues.length) ?? [];
  const ordinaryUnknown = result?.entities.reduce((count, entity) => count + entity.issues.filter((issue) => !reviewReasons.has(issue.reason)).length, 0) ?? 0;
  const fieldLabel = (kind: Entity["entity_type"], field: string) => kind === "faction" ? faction(`fields.${field}`) : kind === "character_relation" ? relation("currentState") : common(`fields.${field}`);
  const openSource = async (entity: Entity, historyId: string) => {
    sourceRequest.current?.abort();
    const abort = new AbortController(); sourceRequest.current = abort;
    setSourceLoading(historyId); setSourceError("");
    try {
      const path = entity.entity_type.replaceAll("_", "-");
      const record = await apiGet<Source>(`/api/${path}-facts/novel/${novelId}/history/${historyId}`, { signal: abort.signal });
      if (abort.signal.aborted) return;
      const id = "character_id" in record ? record.character_id : "faction_id" in record ? record.faction_id : record.relation_id;
      if (record.novel_id !== novelId || record.history_id !== historyId || id !== entity.entity_id) throw new Error(wrongScope);
      setSource({ entity, record });
    } catch (failure) { if (!abort.signal.aborted) setSourceError((failure as Error).message); }
    finally { if (!abort.signal.aborted) setSourceLoading(""); }
  };
  return <section className="mb-5 border-b border-border pb-4 text-sm" aria-label={t("title")}>
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{t("title")}</h3><SectionActionButton action="refresh" label={t("refresh")} isPending={loading} onPress={() => setRefresh((value) => value + 1)} /></div>
    {loading && <p role="status" className="text-muted">{common("loading")}</p>}
    {error && <p role="alert" className="break-words text-amber-700 dark:text-amber-300">{t(result ? "stale" : "failed")} {error}</p>}
    {result && <>
      <p className="break-words leading-6">{t("position", { name: result.volume_title, order: result.position.order[0] ?? 0 })}</p>
      <details><summary className="min-h-11 cursor-pointer py-2 text-muted">{t("scope", result.counts)}</summary>
        <p className="pb-2 leading-6 text-muted">{t("scopeDetails", result.counts)}</p>
        <ul className="divide-y divide-border">{result.entities.filter((entity) => entity.source_ids.length).map((entity) => <li key={`${entity.entity_type}:${entity.entity_id}`} className="flex flex-wrap items-center gap-2 py-1"><span className="min-w-0 break-words">{entity.name}</span>{entity.source_ids.map((id, index) => <Button key={id} size="sm" variant="ghost" isPending={sourceLoading === id} onPress={() => void openSource(entity, id)}>{t("source", { number: index + 1 })}</Button>)}</li>)}</ul>
      </details>
      {entities.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2 text-amber-700 dark:text-amber-300">{t("review", { count: entities.length })}</summary>
        <ul className="divide-y divide-border">{entities.map((entity) => <li key={`${entity.entity_type}:${entity.entity_id}`} className="py-2">
          <div className="flex flex-wrap items-center gap-2"><span className="min-w-0 break-words font-medium">{entity.name}</span><span className="text-xs text-muted">{t(`kinds.${entity.entity_type}`)}</span>
            {onProcess && entity.entity_type !== "character_relation" && <Button size="sm" variant="ghost" onPress={() => onProcess(entity.entity_type as "character" | "faction", entity.entity_id)}>{t("process")}</Button>}
          </div>
          <ul className="space-y-1 text-muted">{entity.issues.map((issue) => <li key={issue.field} className="flex flex-wrap items-center gap-x-2"><span>{fieldLabel(entity.entity_type, issue.field)} · {common(`unknown.${issue.reason}`)}</span></li>)}</ul>
          <div className="flex flex-wrap gap-2">{[...new Set(entity.issues.flatMap((issue) => issue.blocking_source_ids))].map((id, index) => <Button key={id} size="sm" variant="ghost" isPending={sourceLoading === id} onPress={() => void openSource(entity, id)}>{t("source", { number: index + 1 })}</Button>)}</div>
        </li>)}</ul>
      </details>}
      <p className="text-xs leading-6 text-muted">{ordinaryUnknown ? t("unknown", { count: ordinaryUnknown }) : t("continueHint")}</p>
    </>}
    {sourceError && <p role="alert" className="text-danger">{sourceError}</p>}
    {source && <RetainedModalBackdrop isOpen onOpenChange={(open) => { if (!open) setSource(null); }}><Modal.Container scroll="inside" size="lg"><Modal.Dialog className="w-full max-w-3xl"><Modal.Header className="px-5 py-4"><Modal.Heading>{common("source")}</Modal.Heading><Modal.CloseTrigger aria-label={common("close")} /></Modal.Header><Modal.Body className="space-y-4 px-5 py-5">
      <p className="break-words text-sm">{source.entity.name} · {common(`positions.${source.record.position.intent}`)}</p>
      <dl className="detail-fields grid gap-3">{Object.entries(source.record.after).map(([field, value]) => <ReadOnlyField key={field} label={fieldLabel(source.entity.entity_type, field)} value={
        source.entity.entity_type === "faction" && (typeof value !== "string" || field === "story_status") ? <FactionFactValue field={field} value={value} />
          : Array.isArray(value) ? value.length ? <TagList values={value} /> : common("cleared") : String(value) || common("cleared")
      } wide />)}</dl>
      {source.record.source.kind === "author" ? <ReadOnlyField label={common("source")} value={source.record.source.note} wide /> : <EvidencePicker novelId={novelId} chapters={[]} value={source.record.source.evidence} readOnly chapterRecordSource label={common("source")} />}
    </Modal.Body></Modal.Dialog></Modal.Container></RetainedModalBackdrop>}
  </section>;
}
