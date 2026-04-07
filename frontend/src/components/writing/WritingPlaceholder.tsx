"use client";

import { useTranslations } from "next-intl";

interface WritingPlaceholderProps {
  moduleKey: string;
}

export default function WritingPlaceholder({ moduleKey }: WritingPlaceholderProps) {
  const t = useTranslations("writing");

  const LABEL_MAP: Record<string, string> = {
    "chapter-editor": t("sidebar.chapterEditor"),
    "character-cards": t("sidebar.characterCards"),
    "location-cards": t("sidebar.locationCards"),
    "faction-cards": t("sidebar.factionCards"),
    "item-cards": t("sidebar.itemCards"),
    "rule-cards": t("sidebar.ruleCards"),
    "relationship-map": t("sidebar.relationshipMap"),
  };

  const moduleName = LABEL_MAP[moduleKey] || moduleKey;

  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] gap-4">
      <div className="w-16 h-16 rounded-2xl bg-muted/10 flex items-center justify-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-muted/40"
        >
          <path d="M12 6v6l4 2" />
          <circle cx="12" cy="12" r="10" />
        </svg>
      </div>
      <div className="text-center space-y-2">
        <h3 className="text-lg font-semibold text-foreground">
          {t("placeholder.title", { module: moduleName })}
        </h3>
        <p className="text-sm text-muted max-w-xs">
          {t("placeholder.description")}
        </p>
        <p className="text-xs text-muted/60 mt-1">
          {t("placeholder.hint")}
        </p>
      </div>
    </div>
  );
}
