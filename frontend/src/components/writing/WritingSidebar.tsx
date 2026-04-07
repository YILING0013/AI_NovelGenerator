"use client";

import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "next/navigation";
import type { WritingSidebarItem } from "@/types/novel";

interface WritingSidebarProps {
  activeItem: WritingSidebarItem;
  onSelect: (item: WritingSidebarItem) => void;
}

interface NavItem {
  key: WritingSidebarItem;
  labelKey: string;
  icon: React.ReactNode;
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
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m7.5 4.27 9 5.15" /><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
      </svg>
    ),
  },
  {
    key: "rule-cards",
    labelKey: "sidebar.ruleCards",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z" /><path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /><path d="M12 2v2" /><path d="M12 22v-2" /><path d="m17 20.66-1-1.73" /><path d="M11 10.27 7 3.34" /><path d="m20.66 17-1.73-1" /><path d="m3.34 7 1.73 1" /><path d="M14 12h8" /><path d="M2 12h2" /><path d="m20.66 7-1.73 1" /><path d="m3.34 17 1.73-1" /><path d="m17 3.34-1 1.73" /><path d="m11 13.73-4 6.93" />
      </svg>
    ),
  },
  {
    key: "relationship-map",
    labelKey: "sidebar.relationshipMap",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="18" cy="18" r="3" /><circle cx="6" cy="6" r="3" /><path d="M13 6h3a2 2 0 0 1 2 2v7" /><path d="M11 18H8a2 2 0 0 1-2-2V9" />
      </svg>
    ),
  },
];

export default function WritingSidebar({ activeItem, onSelect }: WritingSidebarProps) {
  const t = useTranslations("writing");
  const router = useRouter();
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";

  const renderItem = (item: NavItem) => {
    const isActive = activeItem === item.key;
    return (
      <button
        key={item.key}
        onClick={() => onSelect(item.key)}
        className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? "bg-accent/10 text-accent"
            : "text-muted hover:text-foreground hover:bg-surface-secondary"
        }`}
      >
        <span className={isActive ? "text-accent" : "text-muted"}>{item.icon}</span>
        {t(item.labelKey)}
      </button>
    );
  };

  return (
    <aside className="w-56 shrink-0 border-r border-border bg-surface flex flex-col h-full">
      {/* Back button */}
      <div className="px-3 pt-4 pb-2">
        <button
          onClick={() => router.push(`/${locale}`)}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm font-medium text-muted hover:text-foreground hover:bg-surface-secondary transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5" /><path d="m12 19-7-7 7-7" />
          </svg>
          {t("backToShelf")}
        </button>
      </div>

      {/* Main nav */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {MAIN_ITEMS.map(renderItem)}

        {/* Divider */}
        <div className="border-t border-dashed border-border my-3" />

        {/* Entity group label */}
        <div className="px-3 py-1">
          <span className="text-xs font-semibold text-muted uppercase tracking-wider">
            {t("sidebar.entityGroup")}
          </span>
        </div>

        {ENTITY_ITEMS.map(renderItem)}
      </nav>
    </aside>
  );
}
