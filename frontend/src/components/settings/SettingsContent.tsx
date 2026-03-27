"use client";

import { useTranslations } from "next-intl";
import { Button } from "@heroui/react";
import { useConfig } from "@/hooks/useConfig";
import { DatabaseCard } from "@/components/settings/DatabaseCard";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { WorkflowCard } from "@/components/settings/WorkflowCard";
import { validateConfig } from "@/lib/validation";
import type { AppConfig } from "@/types/config";
import { useRouter, usePathname } from "next/navigation";

export default function SettingsContent() {
  const t = useTranslations("settings");
  const router = useRouter();
  const pathname = usePathname();
  const currentLocale = pathname.startsWith("/en") ? "en" : "zh";
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

  const goBack = () => {
    router.push(`/${currentLocale}`);
  };

  if (loading || !config) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-muted">{loading ? "Loading..." : "Failed to load"}</div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-3">
          {/* Back Button */}
          <button
            onClick={goBack}
            className="w-9 h-9 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-surface-secondary transition-colors"
            title={t("back")}
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
            <h1 className="text-2xl font-bold text-foreground">{t("title")}</h1>
            <p className="text-sm text-muted mt-1">{t("description")}</p>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
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
            isDisabled={saving}
            className="bg-accent text-white hover:bg-accent-hover"
          >
            {saving ? t("saving") : t("save")}
          </Button>
        </div>
      </div>

      {/* Feedback */}
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 text-sm">
          {success}
        </div>
      )}

      {/* Config Cards */}
      <div className="space-y-6">
        <DatabaseCard config={config} onChange={updateConfig} />
        <ProviderCard config={config} onChange={setConfig} />
        <WorkflowCard config={config} onChange={setConfig} />
      </div>
    </div>
  );
}
