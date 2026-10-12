"use client";

import { Button, Tooltip } from "@heroui/react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { apiGet } from "@/lib/api";
import { readWritingDraft, writeWritingDraft } from "@/lib/writingDrafts";
import { useResourceRefresh } from "@/hooks/useResourceRefresh";
import type { InitializationReadinessResponseV1 } from "@/types/initialization";
import type { HierarchyRecord, PlanningReadiness } from "@/types/hierarchy";
import type { VolumeReadV2 } from "@/types/volume";
import type { ItemReadV1 } from "@/types/item";
import type { WorldRuleReadV1 } from "@/types/worldRule";

export interface FlowNavigationProgress {
  novelId: string;
  currentWorkspace: string;
  savedRules: boolean;
  savedItems: boolean;
}

interface CurrentStep { phase: number; title: string; href: string; optional?: string; volumeTitle?: string }

/** 从实际已保存内容找到下一步；资料管理仍可回看，作者不需要选择技术流程。 */
export default function WritingFlowProgress({ novelId, readiness, activeHref, disabled, onNavigate, onProgressChange }: {
  novelId: string; readiness: InitializationReadinessResponseV1 | null; activeHref: string;
  disabled: boolean; onNavigate: (href: string) => void;
  onProgressChange?: (progress: FlowNavigationProgress | null) => void;
}) {
  const t = useTranslations("writing.firstUse");
  const [reviewed, setReviewed] = useState<string[] | null>(null);
  const [step, setStep] = useState<CurrentStep | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const request = useRef(0);
  const [expanded, setExpanded] = useState(false);
  const progressId = useId();
  const scope = `${novelId}:first-use-choices`;
  useEffect(() => {
    let current = true;
    setReviewed(null); setStep(null); setError("");
    void readWritingDraft<string[]>(scope, 1).then((stored) => {
      if (current) setReviewed(stored?.value ?? []);
    }, (failure) => { if (current) setError(String(failure)); });
    return () => { current = false; };
  }, [scope]);
  const load = useCallback(async () => {
    if (readiness?.novel_id !== novelId || reviewed === null) return;
    const id = ++request.current;
    setLoading(true); setError("");
    let savedRules = false, savedItems = false;
    const finish = (value: CurrentStep) => {
      if (request.current !== id) return;
      setStep(value);
      onProgressChange?.({ novelId, currentWorkspace: new URLSearchParams(value.href).get("workspace")!, savedRules, savedItems });
    };
    const href = (workspace: string, values: Record<string, string> = {}) => `?${new URLSearchParams({ workspace, ...values })}`;
    const count = (key: string) => readiness.steps.find((row) => row.key === key)?.count ?? 0;
    let volumeTitle: string | undefined;
    const at = (phase: number, title: string, workspace: string, values?: Record<string, string>, optional?: string) => finish({ phase, title, href: href(workspace, values), optional, volumeTitle });
    try {
      if (!count("core_factions")) return at(1, t("factions"), "faction-cards", { view: "profiles" });
      if (!count("protagonist")) return at(1, t("characters"), "character-cards", { view: "profiles" });
      // 只有服务端已保存资料才自动完成；本机跳过记录不冒充已保存内容。
      const [rules, items] = await Promise.all([
        apiGet<WorldRuleReadV1[]>(`/api/world-rules/novel/${novelId}`),
        apiGet<ItemReadV1[]>(`/api/items/novel/${novelId}`),
      ]);
      savedRules = rules.some((row) => !row.is_deleted);
      savedItems = items.some((row) => !row.is_deleted);
      if (!count("character_relations") && !reviewed.includes("relations")) return at(1, t("relations"), "character-cards", { view: "relations" }, "relations");
      if (!savedRules && !reviewed.includes("rules")) return at(1, t("rules"), "rule-cards", undefined, "rules");
      if (!savedItems && !reviewed.includes("items")) return at(1, t("items"), "item-cards", undefined, "items");
      const volumes = (await apiGet<{ data: VolumeReadV2[] }>(`/api/volumes/novel/${novelId}`)).data.filter((row) => !row.is_deleted).sort((a, b) => a.order_index - b.order_index);
      if (!volumes.length) return at(2, t("firstVolume"), "volume-planning", { view: "overview" });
      for (const volume of volumes) {
        volumeTitle = volume.title;
        const volume_id = volume.volume_id;
        const ready = await apiGet<PlanningReadiness>(`/api/novels/${novelId}/planning-readiness?target_type=volume&target_id=${volume_id}`);
        if (ready.plot_status !== "ready") return at(2, t("volumePlot", { title: volume.title }), "volume-planning", { view: "overview", volume_id, focus: "plot" });
        for (const stage of ["factions", "characters", "locations"] as const) {
          if (!ready.preparation?.[stage]) return at(3, t(`volume${stage}`, { title: volume.title }), "volume-planning", { view: stage, volume_id });
        }
        const arcs = (await apiGet<{ data: HierarchyRecord[] }>(`/api/arcs/volume/${volume_id}`)).data.sort((a, b) => a.order_index - b.order_index);
        if (!arcs.length) return at(4, t("chapterPreparation"), "arc-planning", { volume_id });
        for (const arc of arcs) {
          const arc_id = arc.arc_id!;
          const arcReady = await apiGet<PlanningReadiness>(`/api/novels/${novelId}/planning-readiness?target_type=arc&target_id=${arc_id}`);
          if (arcReady.plot_status !== "ready") return at(4, t("arcPlot", { title: arc.title }), "arc-planning", { volume_id, arc_id, focus: "plot" });
          const scenes = (await apiGet<{ data: HierarchyRecord[] }>(`/api/scenes/arc/${arc_id}`)).data.sort((a, b) => a.order_index - b.order_index);
          if (!scenes.length) return at(4, t("chapterPreparation"), "chapter-editor", { volume_id, arc_id });
          for (const scene of scenes) {
            const scene_id = scene.scene_id!;
            const chapters = (await apiGet<{ data: HierarchyRecord[] }>(`/api/chapters/scene/${scene_id}`)).data.sort((a, b) => a.order_index - b.order_index);
            if (!chapters.length) return at(4, t("chapterPreparation"), "chapter-editor", { volume_id, arc_id, scene_id });
            const next = chapters.find((row) => row.word_count === 0);
            if (next) return at(4, t("writeChapter", { title: next.title }), "chapter-editor", { volume_id, arc_id, scene_id, chapter_id: next.chapter_id! });
          }
        }
      }
      at(5, t("nextVolume"), "volume-planning", { view: "overview" });
    } catch (failure) { if (request.current === id) { setError(failure instanceof Error ? failure.message : String(failure)); onProgressChange?.(null); } }
    finally { if (request.current === id) setLoading(false); }
  }, [novelId, readiness, reviewed, t, onProgressChange]);
  useEffect(() => { void load(); return () => { request.current += 1; }; }, [load]);
  useResourceRefresh(novelId, load);
  const params = new URLSearchParams(activeHref);
  const here = step && [...new URLSearchParams(step.href)].every(([key, value]) => params.get(key) === value || key === "view" && !params.get(key) && value === "profiles");
  const continueOptional = async () => {
    if (!step?.optional || reviewed === null) return;
    const next = [...new Set([...reviewed, step.optional])];
    try { await writeWritingDraft(scope, 1, next); setReviewed(next); }
    catch (failure) { setError(String(failure)); }
  };
  return <section aria-label={t("progress")} className="min-w-0 space-y-2 border-t border-border px-3 py-2">
    <div className="flex min-w-0 items-center justify-between gap-2">
      <p className="min-w-0 [overflow-wrap:anywhere] text-xs text-muted">{t("progress")}</p>
      <Button size="sm" variant="ghost" className="min-h-11 shrink-0" aria-expanded={expanded} aria-controls={progressId} onPress={() => setExpanded(!expanded)}>{t(expanded ? "collapseProgress" : "expandProgress")}</Button>
    </div>
    {error ? <div role="alert" className="space-y-2 text-sm"><p>{error}</p><Button size="sm" variant="outline" onPress={() => void load()}>{t("retry")}</Button></div>
      : step ? <div className="flex min-w-0 flex-wrap items-center gap-2"><p className="min-w-0 flex-[1_1_10rem] [overflow-wrap:anywhere] text-sm" role="status">{step.title}</p>
        {!here && <Button size="sm" variant="outline" className="h-auto min-h-11 max-w-full whitespace-normal [overflow-wrap:anywhere]" isDisabled={disabled || loading} onPress={() => onNavigate(step.href)}>{t("goToStep")}</Button>}
        {here && step.optional && <Button size="sm" variant="outline" className="h-auto min-h-11 max-w-full whitespace-normal [overflow-wrap:anywhere]" isDisabled={disabled || loading} onPress={() => void continueOptional()}>{t("continueOptional")}</Button>}
      </div> : <p role="status" className="text-sm text-muted">{t("loading")}</p>}
    <div id={progressId} hidden={!expanded}>
      {step?.volumeTitle && <p className="mb-2 text-xs text-muted [overflow-wrap:anywhere]">{t("volumeProgress", { title: step.volumeTitle })}</p>}
      <ol className="space-y-1 text-sm">{["book", "opening", "volume", "preparation", "chapters", "continue"].map((name, index) => {
        const done = step && index < step.phase;
        const current = step?.phase === index;
        const locked = step && index > step.phase;
        return <li key={name} className={`group flex min-h-11 min-w-0 items-center gap-2 ${done ? "text-emerald-700 dark:text-emerald-300" : current ? "font-medium text-amber-700 dark:text-amber-300" : "text-muted"}`} aria-current={current ? "step" : undefined}>
          <span aria-hidden="true" className={`grid size-6 shrink-0 place-items-center rounded-full text-xs tabular-nums ${done ? "bg-emerald-500/10" : current ? "bg-amber-500/10" : "bg-surface-secondary"}`}>{done ? "✓" : index + 1}</span>
          <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{t(`phases.${name}`)}<span className="block text-xs font-normal">{t(done ? "done" : current ? "current" : "waiting")}</span>
            {locked && <span className="hidden text-xs font-normal group-focus-within:block">{t("finishCurrent")}：{step.title}</span>}
          </span>
          {locked && <Tooltip delay={300} closeDelay={0}>
            <Button isIconOnly size="sm" variant="ghost" className="size-11 shrink-0 text-muted" aria-label={`${t("finishCurrent")}：${step.title}`} isDisabled={disabled || loading} onPress={() => onNavigate(step.href)}>
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
            </Button>
            <Tooltip.Content className="z-[100] max-w-[min(20rem,calc(100vw-24px))] rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs text-foreground shadow-lg">{t("finishCurrent")}：{step.title}</Tooltip.Content>
          </Tooltip>}
        </li>;
      })}</ol>
    </div>
  </section>;
}
