"use client";

import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import { Button, Tooltip } from "@heroui/react";
import { useId, useState } from "react";
import SidebarEdgeHandle from "@/components/shared/SidebarEdgeHandle";
import type { WritingSidebarItem } from "@/types/novel";
import type { InitializationReadinessResponseV1 } from "@/types/initialization";
import type { FlowNavigationProgress } from "./WritingFlowProgress";

interface WritingSidebarProps {
  activeItem: WritingSidebarItem;
  onSelect: (item: WritingSidebarItem) => void;
  nextPhaseReady?: boolean;
  nextPhaseBlockedReason?: string;
  flow?: React.ReactNode;
  readiness?: InitializationReadinessResponseV1 | null;
  progress?: FlowNavigationProgress | null;
}

interface NavItem {
  key: WritingSidebarItem;
  labelKey: string;
  icon: React.ReactNode;
  requiresNextPhase?: boolean;
}

const MAIN_ITEMS: NavItem[] = [
  {
    key: "novel-info",
    labelKey: "sidebar.novelInfo",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20" />
      </svg>
    ),
  },
  {
    key: "volume-planning",
    labelKey: "sidebar.volumePlanning",
    requiresNextPhase: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m12 2 8 4-8 4-8-4 8-4Z" /><path d="m4 10 8 4 8-4" /><path d="m4 14 8 4 8-4" />
      </svg>
    ),
  },
  {
    key: "arc-planning",
    labelKey: "sidebar.arcPlanning",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4h16v5H4zM4 15h7v5H4zM15 15h5v5h-5zM12 9v3M7.5 15v-3H18v3" />
      </svg>
    ),
  },
  {
    key: "chapter-editor",
    labelKey: "sidebar.chapterEditor",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20h9" /><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z" />
      </svg>
    ),
  },
];

const ENTITY_ITEMS: NavItem[] = [
  {
    key: "foreshadowings",
    labelKey: "sidebar.foreshadowings",
    icon: <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16v16H4zM8 8h8M8 12h5M8 16h8" /></svg>,
  },
  {
    key: "character-cards",
    labelKey: "sidebar.characterCards",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    key: "location-cards",
    labelKey: "sidebar.locationCards",
    requiresNextPhase: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0" /><circle cx="12" cy="10" r="3" />
      </svg>
    ),
  },
  {
    key: "faction-cards",
    labelKey: "sidebar.factionCards",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" x2="4" y1="22" y2="15" />
      </svg>
    ),
  },
  {
    key: "item-cards",
    labelKey: "sidebar.itemCards",
    requiresNextPhase: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m7.5 4.27 9 5.15" /><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
      </svg>
    ),
  },
  {
    key: "rule-cards",
    labelKey: "sidebar.ruleCards",
    requiresNextPhase: true,
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z" /><path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /><path d="M12 2v2" /><path d="M12 22v-2" /><path d="m17 20.66-1-1.73" /><path d="M11 10.27 7 3.34" /><path d="m20.66 17-1.73-1" /><path d="m3.34 7 1.73 1" /><path d="M14 12h8" /><path d="M2 12h2" /><path d="m20.66 7-1.73 1" /><path d="m3.34 17 1.73-1" /><path d="m17 3.34-1 1.73" /><path d="m11 13.73-4 6.93" />
      </svg>
    ),
  },
  {
    key: "entity-graph",
    labelKey: "sidebar.entityGraph",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="18" cy="18" r="3" /><circle cx="6" cy="6" r="3" /><path d="M13 6h3a2 2 0 0 1 2 2v7" /><path d="M11 18H8a2 2 0 0 1-2-2V9" />
      </svg>
    ),
  },
];

/** 功能：显示创作导航，桌面可收为图标或隐藏，手机保留横向入口。Args: props 当前栏目、选择回调和资料就绪状态。Returns: 可独立滚动的导航和边缘收放控件。 */
export default function WritingSidebar({
  activeItem,
  onSelect,
  nextPhaseReady = false,
  nextPhaseBlockedReason,
  flow,
  readiness,
  progress,
}: WritingSidebarProps) {
  const t = useTranslations("writing");
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";
  const [display, setDisplay] = useState<"expanded" | "icons" | "hidden">("expanded");
  const sidebarId = useId();
  const iconsOnly = display === "icons";

  const renderItem = (item: NavItem) => {
    const isActive = activeItem === item.key;
    const locked = item.requiresNextPhase && !nextPhaseReady;
    const savedKey = ({ "novel-info": "novel_profile", "faction-cards": "core_factions", "character-cards": "protagonist" } as Partial<Record<WritingSidebarItem, string>>)[item.key];
    const saved = savedKey ? readiness?.steps.some((row) => row.key === savedKey && row.state === "ready")
      : item.key === "rule-cards" ? progress?.savedRules : item.key === "item-cards" ? progress?.savedItems : false;
    const current = progress?.currentWorkspace === item.key;
    const status = locked ? "locked" : current ? "current" : saved ? "saved" : "available";
    const blockers = readiness?.steps.filter((row) => ["core_factions", "protagonist"].includes(row.key) && row.state !== "ready").flatMap((row) => row.blockers) ?? [];
    const reason = locked ? nextPhaseBlockedReason ?? (blockers.length ? `${t("firstUse.finishCurrent")}：${blockers.map((key) => t(`initialization.blockers.${key}`)).join("；")}` : t("initialization.nextPhaseBlocked")) : current ? t("firstUse.current") : undefined;
    const statusColor = status === "current" ? "text-amber-700 dark:text-amber-300" : "text-muted";
    return (
      <div key={item.key} className={`flex min-w-0 shrink-0 items-center md:w-full ${iconsOnly ? "md:justify-center" : ""}`}>
        <Tooltip delay={300} closeDelay={0}>
          <Button
            variant="ghost"
            onPress={() => onSelect(item.key)}
            aria-label={t(item.labelKey)}
            aria-describedby={reason ? `${sidebarId}-${item.key}-status` : undefined}
            aria-current={isActive ? "page" : undefined}
            data-module-status={status}
            className={`flex min-h-11 w-auto min-w-0 flex-1 items-center justify-start gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${iconsOnly ? "md:mx-auto md:h-11 md:w-11 md:flex-none md:justify-center md:gap-0 md:p-0" : "md:w-full"} ${
              isActive
                ? "bg-selected text-accent"
                : "text-muted hover:text-foreground hover:bg-surface-secondary"
            }`}
          >
            <span aria-hidden="true" className="shrink-0">{item.icon}</span>
            <span className={`min-w-0 whitespace-nowrap md:flex-1 md:whitespace-normal md:text-left md:[overflow-wrap:anywhere] ${iconsOnly ? "md:hidden" : ""}`}>{t(item.labelKey)}</span>
            {reason && <span aria-hidden="true" className={`shrink-0 ${iconsOnly ? "md:hidden" : ""} ${statusColor}`}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                {locked ? <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>
                  : <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>}
              </svg>
            </span>}
            {reason && <span id={`${sidebarId}-${item.key}-status`} className="sr-only">{reason}</span>}
          </Button>
          <Tooltip.Content placement="right" className="z-[100] max-w-[min(20rem,calc(100vw-24px))] rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs font-normal leading-5 text-foreground shadow-lg">
            <p>{t(item.labelKey)}</p>
            {reason && <p>{reason}</p>}
          </Tooltip.Content>
        </Tooltip>
      </div>
    );
  };

  return (
    <aside data-sidebar-state={display} className={`relative z-20 flex max-h-[45dvh] w-full min-w-0 max-w-full shrink-0 md:max-h-none flex-col overflow-visible border-b border-border bg-surface md:h-full md:border-b-0 md:transition-[width] md:duration-200 md:ease-in-out motion-reduce:transition-none ${display === "expanded" ? "md:w-56 md:border-r" : iconsOnly ? "md:w-16 md:border-r" : "md:w-0 md:border-r-0"}`}>
      {/* 桌面隐藏用 visibility 同时移出 Tab 顺序，手机不继承桌面的隐藏状态。 */}
      <div id={sidebarId} className={`flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden ${iconsOnly ? "md:pb-24" : ""} ${display === "hidden" ? "md:invisible" : ""}`}>
        <div className={`hidden px-3 pb-2 pt-4 md:block ${iconsOnly ? "md:flex md:justify-center md:px-0" : ""}`}>
          <Tooltip isDisabled={!iconsOnly} delay={300} closeDelay={0}>
            <Button
              variant="ghost"
              onPress={() => router.push(`/${locale}`)}
              aria-label={t("backToShelf")}
              className={`flex min-h-11 w-auto min-w-0 items-center justify-start gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-surface-secondary hover:text-foreground ${iconsOnly ? "md:h-11 md:w-11 md:justify-center md:gap-0 md:p-0" : "md:w-full"}`}
            >
              <svg aria-hidden="true" className="shrink-0" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5" /><path d="m12 19-7-7 7-7" />
              </svg>
              <span className={iconsOnly ? "md:hidden" : ""}>{t("backToShelf")}</span>
            </Button>
            <Tooltip.Content placement="right" className="z-[100] max-w-[min(20rem,calc(100vw-24px))] rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs font-normal leading-5 text-foreground shadow-lg">{t("backToShelf")}</Tooltip.Content>
          </Tooltip>
        </div>

        <div className="workspace-scrollbar w-full min-h-0 min-w-0 max-w-full flex-1 overflow-x-clip overflow-y-auto">
          <nav aria-label={t("pageTitle")} className={`workspace-scrollbar flex min-w-0 max-w-full gap-1 overflow-x-auto px-3 py-2 md:block md:space-y-1 md:overflow-x-hidden ${iconsOnly ? "md:px-0" : ""}`}>
            <Button variant="ghost" className="min-h-11 shrink-0 md:hidden" onPress={() => router.push(`/${locale}`)}>{t("backToShelf")}</Button>
            {MAIN_ITEMS.map(renderItem)}

            <div className="my-3 hidden border-t border-dashed border-border md:block" />

            <div className={`hidden px-3 py-1 ${iconsOnly ? "" : "md:block"}`}>
              <span className="text-xs font-medium text-muted">
                {t("sidebar.entityGroup")}
              </span>
            </div>

            {ENTITY_ITEMS.map(renderItem)}
          </nav>
          {flow && <div className={display !== "expanded" ? "md:hidden" : ""}>{flow}</div>}
        </div>
      </div>
      {/* 完整侧栏的箭头在边缘外；只有图标态为栏内的第二个箭头留出底部空间。 */}
      <SidebarEdgeHandle controls={sidebarId} className="hidden md:bottom-0 md:top-auto md:flex md:translate-y-0"
        leftAction={display === "hidden" ? undefined : {
          label: t(iconsOnly ? "sidebar.hideSidebar" : "sidebar.collapseToIcons"), expanded: true,
          onPress: () => setDisplay(iconsOnly ? "hidden" : "icons"),
        }}
        rightAction={display === "expanded" ? undefined : {
          label: t(iconsOnly ? "sidebar.expandSidebar" : "sidebar.showIcons"), expanded: false,
          onPress: () => setDisplay(iconsOnly ? "expanded" : "icons"),
        }}
      />
    </aside>
  );
}
