"use client";

import { useCallback, useEffect, useState, useRef, type ReactNode } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { apiGet } from "@/lib/api";
import SettingsContent from "@/components/settings/SettingsContent";

/**
 * 首次运行复用现有设置页，检查失败时不能当成空白配置。
 * Args: children 已配置实例的原工作区。
 * Returns: 设置页、原工作区或可重试的连接错误。
 */
export function StartupGate({ children }: { children: ReactNode }) {
  const t = useTranslations("userStorage");
  const ready = useRef(false);
  const [required, setRequired] = useState<boolean | null>(null);
  const [error, setError] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const check = useCallback(() => apiGet<{ setup_required: boolean; setup_error?: { code: string } | null }>("/api/startup")
    .then((status) => {
      setError(false);
      ready.current = !status.setup_required;
      setRequired(status.setup_required);
      setSetupError(status.setup_error?.code ?? null);
    })
    .catch(() => { setError(true); }), []);
  useEffect(() => {
    void check();
    const saved = () => { if (!ready.current) void check(); };
    window.addEventListener("app-config-saved", saved);
    return () => window.removeEventListener("app-config-saved", saved);
  }, [check]);
  if (error) return <div className="px-4 py-3 sm:px-6"><p role="alert">{t("checkFailed")}</p><Button variant="outline" onPress={() => void check()}>{t("retry")}</Button></div>;
  if (required === null) return <p role="status" className="px-4 py-3 sm:px-6">{t("checking")}</p>;
  if (required) return <>
    {setupError && <p role="alert" className="px-4 pt-3 text-sm text-red-700 dark:text-red-300 sm:px-6">{t(setupError === "DATABASE_AUTHENTICATION_FAILED" ? "databaseAuthenticationFailed" : "databaseConnectionUnavailable")}</p>}
    <SettingsContent initialSection="database" />
  </>;
  return children;
}
