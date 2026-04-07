"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { useConfig } from "@/hooks/useConfig";
import { DatabaseCard } from "@/components/settings/DatabaseCard";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { WorkflowCard } from "@/components/settings/WorkflowCard";
import { validateConfig } from "@/lib/validation";
import type { AppConfig } from "@/types/config";
import { useRouter, usePathname } from "next/navigation";

type SettingsSection = "database" | "provider" | "workflow";

const NAV_ITEMS: { key: SettingsSection; icon: React.ReactNode }[] = [
  {
    key: "database",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5V19A9 3 0 0 0 21 19V5" />
        <path d="M3 12A9 3 0 0 0 21 12" />
      </svg>
    ),
  },
  {
    key: "provider",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2a4 4 0 0 0-4 4c0 2 1.5 3.5 3 4.5V13H9v2h2v2H9v2h6v-2h-2v-2h2v-2h-2v-2.5c1.5-1 3-2.5 3-4.5a4 4 0 0 0-4-4z" />
      </svg>
    ),
  },
  {
    key: "workflow",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3h6v6H3z" />
        <path d="M15 3h6v6h-6z" />
        <path d="M9 15h6v6H9z" />
        <path d="M6 9v3h6m6-3v3h-6m0 0v3" />
      </svg>
    ),
  },
];

interface SettingsContentProps {
  presentation?: "page" | "modal";
}

export default function SettingsContent({
  presentation = "page",
}: SettingsContentProps) {
  const t = useTranslations("settings");
  const router = useRouter();
  const pathname = usePathname();
  const currentLocale = pathname.startsWith("/en") ? "en" : "zh";
  const isModal = presentation === "modal";
  const [activeSection, setActiveSection] = useState<SettingsSection>("database");
  const {
    config,
    loading,
    saving,
    error,
    success,
    fetchConfig,
    saveConfig,
    setConfig,
    clearMessages,
  } = useConfig();

  useEffect(() => {
    if (!isModal) return;

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;

      if (window.history.length > 1) {
        router.back();
        return;
      }

      router.replace(`/${currentLocale}`);
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [currentLocale, isModal, router]);

  const handleSave = async () => {
    if (!config) return;
    clearMessages();

    const validationError = validateConfig(config, t);
    if (validationError) {
      alert(validationError);
      return;
    }

    const hasMongo =
      config.mongodb_url !== undefined || config.mongo_database_name !== undefined;
    const msg = hasMongo ? t("saveSuccessMongo") : t("saveSuccess");
    await saveConfig(config, msg);
  };

  const handleReload = async () => {
    clearMessages();
    const result = await fetchConfig();
    if (result) {
      alert(t("reloadSuccess"));
    }
  };

  const updateConfig = (partial: Partial<AppConfig>) => {
    if (!config) return;
    setConfig({ ...config, ...partial });
  };

  const closeSettings = () => {
    if (window.history.length > 1) {
      router.back();
      return;
    }

    router.replace(`/${currentLocale}`);
  };

  const header = (
    <div className={isModal ? "flex items-center justify-between gap-4 border-b border-border px-4 py-3" : "mb-8 flex items-start justify-between gap-4"}>
      <div className="flex items-center gap-3">
        <button
          onClick={closeSettings}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground"
          title={t("back")}
          aria-label={t("back")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M19 12H5" />
            <path d="m12 19-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h1 id="settings-title" className="text-2xl font-bold text-foreground">{t("title")}</h1>
          {!isModal && <p className="mt-1 text-sm text-muted">{t("description")}</p>}
        </div>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button
          variant="outline"
          onPress={handleReload}
          isDisabled={saving}
          className="border-border text-foreground hover:bg-surface-secondary"
        >
          {t("reload")}
        </Button>
        <Button
          onPress={handleSave}
          isDisabled={saving || !config}
          className="bg-accent text-white hover:bg-accent-hover"
        >
          {saving ? t("saving") : t("save")}
        </Button>
      </div>
    </div>
  );

  const renderSectionContent = () => {
    if (!config) return null;
    switch (activeSection) {
      case "database":
        return <DatabaseCard config={config} onChange={updateConfig} />;
      case "provider":
        return <ProviderCard config={config} onChange={setConfig} />;
      case "workflow":
        return <WorkflowCard config={config} onChange={setConfig} />;
    }
  };

  const sidebar = (
    <nav className={isModal
      ? "flex w-52 shrink-0 flex-col gap-1 border-r border-border bg-surface-secondary/40 px-2 py-3"
      : "flex w-56 shrink-0 flex-col gap-1 rounded-lg border border-border bg-surface p-3"
    }>
      {NAV_ITEMS.map((item) => (
        <button
          key={item.key}
          onClick={() => setActiveSection(item.key)}
          className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors ${
            activeSection === item.key
              ? "bg-accent/10 font-medium text-accent"
              : "text-muted hover:bg-surface-secondary hover:text-foreground"
          }`}
        >
          <span className="shrink-0">{item.icon}</span>
          <span className="truncate">{t(`${item.key}.title`)}</span>
        </button>
      ))}
    </nav>
  );

  const messages = (
    <>
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300">
          {success}
        </div>
      )}
    </>
  );

  const body = loading ? (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-muted">Loading...</div>
    </div>
  ) : !config ? (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-muted">{error || "Failed to load"}</div>
    </div>
  ) : (
    <div className="flex flex-1 gap-0 overflow-hidden">
      {sidebar}
      <div className={isModal ? "flex-1 overflow-y-auto px-4 py-3" : "flex-1 overflow-y-auto pl-6"}>
        {messages}
        {renderSectionContent()}
      </div>
    </div>
  );

  if (isModal) {
    return (
      <div
        className="fixed inset-0 z-[60] bg-black/40 px-3 py-4 backdrop-blur-sm"
        onMouseDown={closeSettings}
      >
        <div className="mx-auto flex h-full max-w-7xl items-center justify-center">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            className="flex h-[88vh] w-full flex-col overflow-hidden rounded-lg border border-border bg-background shadow-2xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            {header}
            {body}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      {header}
      {body}
    </div>
  );
}
