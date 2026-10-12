"use client";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { FIELD_LABEL_MAP, REWRITABLE_NOVEL_FIELDS } from "@/lib/novelFields";
import type { TaskFlowPreviewState } from "@/hooks/useTaskFlowPreview";
import type { TaskFlow } from "@/types/taskFlow";
import type { FlowPreviewScope } from "@/types/taskFlowPreview";
import { FLOW_INPUT_CLASS } from "./TaskFlowForm";

type Part = "volume" | "arc" | "scene" | "chapter";
interface Choice { id: string; name: string }
const PARTS: Part[] = ["volume", "arc", "scene", "chapter"];
const TARGETS: Record<string, Part> = {
  plan_volume_launch_by_ai: "volume",
  create_locations_for_volume_by_ai: "volume",
  create_characters_for_volume_by_ai: "volume",
  create_factions_for_volume_by_ai: "volume",
  plan_arcs_by_ai: "volume",
  plan_scenes_by_ai: "arc",
  plan_chapters_by_ai: "scene",
  write_chapter_by_ai: "chapter",
};

/**
 * 在检查面板选择小说资料，并控制已经计算好的模拟步骤。
 * Args: flow 当前完整图；preview 会话状态；onFocus 跳到节点实例及字段。
 * Returns: 范围选择、错误和可回放的步骤清单。
 */
export function TaskFlowPreviewPanel({ flow, preview, onFocus }: {
  flow: TaskFlow;
  preview: TaskFlowPreviewState;
  onFocus: (instancePath: string, port?: string) => void;
}) {
  const t = useTranslations("taskFlows.preview");
  const tn = useTranslations("novel");
  const [novels, setNovels] = useState<Choice[]>([]);
  const [parts, setParts] = useState<Partial<Record<Part, string>>>({});
  const [choices, setChoices] = useState<Partial<Record<Part | "entities", Choice[]>>>({});
  const [catalogError, setCatalogError] = useState("");
  const [rangeError, setRangeError] = useState("");
  const [catalogLoadedFor, setCatalogLoadedFor] = useState(-1);
  const [rangeLoadedFor, setRangeLoadedFor] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const { scope, enabled, setScope } = preview;
  const target = TARGETS[flow.task];
  const relation = flow.task === "create_character_relations_by_ai" ? "character"
    : flow.task === "create_faction_relations_by_ai" ? "faction" : null;
  const selectionKey = JSON.stringify(parts);
  const rangeKey = JSON.stringify([scope.novel_id, target, relation, selectionKey, refreshKey]);
  const catalogLoading = enabled && catalogLoadedFor !== refreshKey;
  const rangeLoading = enabled && Boolean(scope.novel_id) && rangeLoadedFor !== rangeKey;

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    apiGet<{ data: { id: string; title: string }[] }>("/api/novels/list", { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        setNovels(result.data.map((item) => ({ id: item.id, name: item.title })));
        setCatalogError("");
      })
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : String(error)); })
      .finally(() => { if (!controller.signal.aborted) setCatalogLoadedFor(refreshKey); });
    return () => controller.abort();
  }, [enabled, refreshKey]);

  useEffect(() => {
    if (!enabled || !scope.novel_id) return;
    const controller = new AbortController();
    const selected: Partial<Record<Part, string>> = JSON.parse(selectionKey);
    const requests: { key: Part | "entities"; url: string; id: string }[] = [];
    if (target) {
      requests.push({ key: "volume", url: `/api/volumes/novel/${scope.novel_id}`, id: "volume_id" });
      for (let index = 1; index <= PARTS.indexOf(target); index += 1) {
        const parent = PARTS[index - 1];
        if (selected[parent]) requests.push({ key: PARTS[index], url: `/api/${PARTS[index]}s/${parent}/${selected[parent]}`, id: `${PARTS[index]}_id` });
      }
    }
    if (relation) requests.push({ key: "entities", url: `/api/${relation}s/novel/${scope.novel_id}`, id: `${relation}_id` });
    Promise.all(requests.map(async (request) => {
      const response = await apiGet<{ data: Record<string, unknown>[] } | Record<string, unknown>[]>(request.url, { signal: controller.signal });
      const data = Array.isArray(response) ? response : response.data;
      return [request.key, data.filter((item) => !item.is_deleted && (request.key !== "entities"
        || item[relation === "character" ? "status" : "active_status"] === "active"))
        .map((item) => ({ id: String(item[request.id]), name: String(item.title ?? item.name) }))] as const;
    })).then((entries) => { if (!controller.signal.aborted) { setChoices(Object.fromEntries(entries)); setRangeError(""); } })
      .catch((error: unknown) => { if (!controller.signal.aborted) setRangeError(error instanceof Error ? error.message : String(error)); })
      .finally(() => { if (!controller.signal.aborted) setRangeLoadedFor(rangeKey); });
    return () => controller.abort();
  }, [enabled, scope.novel_id, target, relation, selectionKey, refreshKey, rangeKey]);

  const changePart = (part: Part, id: string) => {
    const next = Object.fromEntries(PARTS.slice(0, PARTS.indexOf(part)).map((key) => [key, parts[key]])) as Partial<Record<Part, string>>;
    next[part] = id;
    setParts(next);
    const nextScope: FlowPreviewScope = { novel_id: scope.novel_id, volume_id: next.volume || undefined };
    if (flow.task.startsWith("plan_") && flow.task !== "plan_volume_launch_by_ai" || flow.task === "write_chapter_by_ai") {
      nextScope.target_type = target;
      nextScope.target_id = next[target] || undefined;
    }
    setScope(nextScope);
  };

  const refresh = () => { preview.activate(); setRefreshKey((value) => value + 1); };
  return (
    <section className="min-w-0 space-y-4" aria-label={t("title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <Button size="sm" variant="ghost" onPress={refresh} isDisabled={catalogLoading || rangeLoading}>{t("refreshLists")}</Button>
      </div>
      <label className="grid min-w-0 gap-2 text-xs text-muted">
        {t("novel")}
        <select className={FLOW_INPUT_CLASS} value={scope.novel_id ?? ""} disabled={catalogLoading}
          onFocus={preview.activate}
          onChange={(event) => {
            setParts({}); setChoices({}); setRangeError("");
            setScope(event.target.value ? { novel_id: event.target.value } : {});
          }}>
          <option value="">{t("noNovel")}</option>
          {novels.map((novel) => <option key={novel.id} value={novel.id}>{novel.name}</option>)}
        </select>
      </label>
      {scope.novel_id && target && PARTS.slice(0, PARTS.indexOf(target) + 1).map((part, index) => (
        <label key={part} className="grid min-w-0 gap-2 text-xs text-muted">
          {t(part)}
          <select className={FLOW_INPUT_CLASS} value={parts[part] ?? ""}
            disabled={rangeLoading || index > 0 && !parts[PARTS[index - 1]]}
            onChange={(event) => changePart(part, event.target.value)}>
            <option value="">{t("unselected")}</option>
            {(choices[part] ?? []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
      ))}
      {flow.task === "rewrite_novel_field_by_ai" && (
        <label className="grid min-w-0 gap-2 text-xs text-muted">
          {t("targetField")}
          <select className={FLOW_INPUT_CLASS} value={scope.target_field ?? ""}
            onChange={(event) => setScope({ ...scope, target_field: event.target.value || undefined })}>
            <option value="">{t("unselected")}</option>
            {REWRITABLE_NOVEL_FIELDS.map((field) => <option key={field} value={field}>{tn(FIELD_LABEL_MAP[field])}</option>)}
          </select>
        </label>
      )}
      {scope.novel_id && relation && (
        <fieldset className="min-w-0 space-y-2">
          <legend className="mb-2 text-xs text-muted">{t(relation === "character" ? "characters" : "factions")}</legend>
          <div className="workspace-scrollbar max-h-48 overflow-y-auto" tabIndex={0}>
            {(choices.entities ?? []).map((item) => {
              const field = relation === "character" ? "selected_character_ids" : "selected_faction_ids";
              const selected = scope[field] ?? [];
              return <label key={item.id} className="flex min-h-11 items-center gap-2 text-sm">
                <input type="checkbox" checked={selected.includes(item.id)} disabled={rangeLoading}
                  onChange={(event) => setScope({ ...scope, [field]: event.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id) })} />
                <span className="min-w-0 break-words">{item.name}</span>
              </label>;
            })}
          </div>
          {!rangeLoading && !choices.entities?.length && <p className="text-xs text-muted">{t("noEntities")}</p>}
        </fieldset>
      )}
      <Button variant="primary" onPress={preview.execute} isDisabled={!preview.canExecute || catalogLoading || rangeLoading}>{t("execute")}</Button>
      {(catalogLoading || rangeLoading || preview.busy) && <p role="status" className="text-xs text-muted">{t("loading")}</p>}
      {preview.stale && !preview.busy && <p role="status" className="text-xs text-muted">{t("stale")}</p>}
      {[catalogError, rangeError, preview.error].filter(Boolean).map((error, index) => <p key={index} role="alert" className="break-words text-sm text-red-600 dark:text-red-300">{error}</p>)}
      {preview.result?.errors.length ? <ul className="space-y-2" aria-label={t("issues")}>
        {preview.result.errors.map((issue, index) => <li key={index} role="alert" className="break-words text-sm text-red-600 dark:text-red-300">
          {issue.message}
          {issue.instance_path && <Button size="sm" variant="ghost" onPress={() => onFocus(issue.instance_path!, issue.port)}>{t("locate")}</Button>}
        </li>)}
      </ul> : null}
      {Boolean(preview.result?.unused_overrides?.length) && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-xs text-muted">{t("unusedExamples", { count: preview.result!.unused_overrides!.length })}</summary>
          <ul className="space-y-2">{preview.result!.unused_overrides!.map((item) => <li key={JSON.stringify([item.instance_path, item.port, item.path])} className="min-w-0 text-xs">
            <span className="break-all font-mono">{item.instance_path} · {[item.port, ...item.path].join(".")}</span>
            <Button size="sm" variant="ghost" onPress={() => preview.resetOverride(item)}>{t("resetExample")}</Button>
          </li>)}</ul>
        </details>
      )}
      {preview.result && (
        <div className="space-y-3 border-t border-border pt-4">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" isDisabled={!preview.playable} onPress={preview.playing ? preview.pause : preview.play}>
              {t(preview.playing ? "pause" : "play")}
            </Button>
            <Button size="sm" variant="outline" isDisabled={!preview.playable || preview.cursor >= preview.result.steps.length - 1} onPress={preview.next}>{t("next")}</Button>
            <Button size="sm" variant="ghost" isDisabled={!preview.playable} onPress={preview.restart}>{t("restart")}</Button>
          </div>
          <p role="status" className="text-xs text-muted">
            {preview.cursor < 0 ? t("overview") : t("position", { current: preview.cursor + 1, total: preview.result.steps.length })}
          </p>
          <ol className="divide-y divide-border">
            {preview.result.steps.map((step, index) => {
              let graph = flow;
              for (const part of step.graph_path) graph = graph.subflows[part] ?? graph;
              const label = graph.nodes.find((node) => node.id === step.node_id)?.label ?? step.node_id;
              return <li key={step.instance_path}>
                <button type="button" className={`min-h-11 w-full min-w-0 rounded-lg px-2 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-accent ${index === preview.cursor ? "bg-selected" : "hover:bg-surface-secondary"}`}
                  aria-current={index === preview.cursor ? "step" : undefined}
                  disabled={!preview.playable}
                  onClick={() => { preview.seek(index); onFocus(step.instance_path); }}>
                  <span className="block break-words">{index + 1}. {label}</span>
                  <span className="block break-all font-mono text-xs text-muted">{step.instance_path}</span>
                  <span className="text-xs text-muted">{t(step.state === "skipped" ? "skipped" : step.state === "error" ? "error" : index === preview.cursor ? "current" : preview.cursor >= 0 && index > preview.cursor ? "pending" : "done")}</span>
                </button>
              </li>;
            })}
          </ol>
          {preview.result.source_refs.length > 0 && <details>
            <summary className="min-h-11 cursor-pointer py-3 text-xs text-muted">{t("sourceVersions")}</summary>
            <ul className="space-y-1 text-xs text-muted">{preview.result.source_refs.map((source) => <li key={`${source.resource_type}:${source.id}`} className="break-all">{source.resource_type} · {source.id} · v{source.version}</li>)}</ul>
          </details>}
        </div>
      )}
    </section>
  );
}
