"use client";

import { useTranslations } from "next-intl";
import { TooltipHint } from "@/components/shared/TooltipHint";

interface WritingPlaceholderProps {
  moduleKey: string;
  phaseGate?: boolean;
}

/**
 * 渲染尚未进入本阶段实现范围的低噪声工作区入口。
 *
 * Args:
 *   moduleKey: 当前侧栏模块键。
 *   phaseGate: 阶段 2 页面是否已经满足准备条件。
 *
 * Returns:
 *   仅包含模块名和必要门禁状态的 React 节点。
 */
export default function WritingPlaceholder({ moduleKey, phaseGate }: WritingPlaceholderProps) {
  const t = useTranslations("writing");

  const LABEL_MAP: Record<string, string> = {
    "chapter-editor": t("sidebar.chapterEditor"),
    "arc-planning": t("sidebar.arcPlanning"),
    "volume-planning": t("sidebar.volumePlanning"),
    "character-cards": t("sidebar.characterCards"),
    "location-cards": t("sidebar.locationCards"),
    "faction-cards": t("sidebar.factionCards"),
    "item-cards": t("sidebar.itemCards"),
    "rule-cards": t("sidebar.ruleCards"),
    "foreshadowings": t("sidebar.foreshadowings"),
    "entity-graph": t("sidebar.entityGraph"),
  };

  const moduleName = LABEL_MAP[moduleKey] || moduleKey;

  return (
    <div className="grid h-full min-h-80 place-items-center px-5">
      <div className="flex items-center gap-3 border-y border-border px-5 py-5">
        <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-muted" aria-hidden="true">
          <path d="M12 6v6l4 2" /><circle cx="12" cy="12" r="10" />
        </svg>
        <h2 className="text-base font-semibold text-foreground">
          {t("placeholder.title", { module: moduleName })}
        </h2>
        {phaseGate !== undefined && (
          <span className="flex items-center gap-1 text-xs text-muted">
            {t(phaseGate ? "placeholder.readOnly" : "placeholder.locked")}
            {!phaseGate && <TooltipHint text={t("initialization.nextPhaseBlocked")} />}
          </span>
        )}
      </div>
    </div>
  );
}
