"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Modal } from "@heroui/react";
import { useConfig } from "@/hooks/useConfig";
import { DatabaseCard } from "@/components/settings/DatabaseCard";
import { ProviderCard } from "@/components/settings/ProviderCard";
import { WorkflowCard } from "@/components/settings/WorkflowCard";
import { ThemeCard } from "@/components/settings/ThemeCard";
import { validateConfig } from "@/lib/validation";
import type { AppConfig } from "@/types/config";
import { useRouter, usePathname } from "next/navigation";

type SettingsSection = "theme" | "database" | "provider" | "workflow";

const NAV_ITEMS: { key: SettingsSection; icon: React.ReactNode }[] = [
  {
    key: "theme",
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="13.5" cy="6.5" r="2.5" />
        <circle cx="17.5" cy="10.5" r="2.5" />
        <circle cx="8.5" cy="7.5" r="2.5" />
        <circle cx="6.5" cy="12.5" r="2.5" />
        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
      </svg>
    ),
  },
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
  const [activeSection, setActiveSection] = useState<SettingsSection>("theme");
  const [secretEditorOpen, setSecretEditorOpen] = useState(false);
  const [localMessage, setLocalMessage] = useState<{
    tone: "error" | "success";
    text: string;
  } | null>(null);
  const messageRef = useRef<HTMLDivElement>(null);
  const {
    config,
    loading,
    saving,
    error,
    success,
    conflict,
    fetchConfig,
    saveConfig,
    queueProviderRename,
    setConfig,
    clearMessages,
  } = useConfig();

  useEffect(() => {
    if (error || conflict || localMessage?.tone === "error") {
      // 保存失败后把焦点移到就地错误，键盘用户无需重新寻找反馈位置。
      messageRef.current?.focus();
    }
  }, [conflict, error, localMessage]);

  const handleSave = async () => {
    if (!config || secretEditorOpen) return;
    clearMessages();
    setLocalMessage(null);

    const validationError = validateConfig(config, t);
    if (validationError) {
      setLocalMessage({ tone: "error", text: validationError });
      return;
    }

    await saveConfig(config, t("saveSuccessMongo"));
  };

  const handleReload = async () => {
    clearMessages();
    setLocalMessage(null);
    const result = await fetchConfig();
    if (result) {
      setLocalMessage({ tone: "success", text: t("reloadSuccess") });
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
    <div className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={closeSettings}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
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
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 id="settings-title" className="shrink-0 text-lg font-semibold text-foreground">{t("title")}</h1>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onPress={handleReload}
          isDisabled={saving || secretEditorOpen}
          className="border-border text-foreground hover:bg-surface-secondary"
        >
          {t("reload")}
        </Button>
        <Button
          size="sm"
          onPress={handleSave}
          isDisabled={saving || !config || secretEditorOpen}
          className="bg-accent text-accent-foreground hover:bg-accent-hover"
        >
          {saving ? t("saving") : t("save")}
        </Button>
      </div>
    </div>
  );

  const renderSectionContent = () => {
    if (!config) return null;
    switch (activeSection) {
      case "theme":
        return <ThemeCard />;
      case "database":
        return (
          <DatabaseCard
            config={config}
            onChange={updateConfig}
            onSecretEditingChange={setSecretEditorOpen}
          />
        );
      case "provider":
        return (
          <ProviderCard
            config={config}
            onChange={setConfig}
            onProviderRename={(from, to) => queueProviderRename({ from, to })}
            onSecretEditingChange={setSecretEditorOpen}
          />
        );
      case "workflow":
        return <WorkflowCard config={config} onChange={setConfig} />;
    }
  };

  const sectionUsesInternalScroll = activeSection === "provider" || activeSection === "workflow";

  const sidebar = (
    <nav
      aria-label={t("title")}
      tabIndex={0}
      className="workspace-scrollbar flex w-full shrink-0 gap-1 overflow-x-auto border-b border-border bg-surface-secondary/40 px-2 py-2 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 lg:min-h-0 lg:w-56 lg:self-stretch lg:flex-col lg:overflow-x-hidden lg:overflow-y-auto lg:border-b-0 lg:border-r lg:py-3"
    >
      {NAV_ITEMS.map((item) => (
        <button
          type="button"
          key={item.key}
          onClick={() => {
            setSecretEditorOpen(false);
            setActiveSection(item.key);
          }}
          aria-current={activeSection === item.key ? "page" : undefined}
          className={`flex min-h-11 shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 lg:shrink ${
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
      {(error || conflict || localMessage?.tone === "error") && (
        <div
          ref={messageRef}
          role="alert"
          tabIndex={-1}
          className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 outline-none focus:ring-2 focus:ring-accent dark:border-red-800 dark:bg-red-950/30 dark:text-red-300"
        >
          {conflict ? t("saveConflict") : localMessage?.tone === "error" ? localMessage.text : error}
        </div>
      )}
      {(success || localMessage?.tone === "success") && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300">
          {localMessage?.tone === "success" ? localMessage.text : success}
        </div>
      )}
    </>
  );

  const body = loading && activeSection !== "theme" ? (
    <div className="flex min-h-0 flex-1 items-center justify-center" role="status">
      <div className="text-muted">{t("loading")}</div>
    </div>
  ) : !config && activeSection !== "theme" ? (
    <div className="flex min-h-0 flex-1 items-center justify-center">
      <div className="text-muted">{error || t("loadFailed")}</div>
    </div>
  ) : (
    <div className="settings-workspace workspace-scrollbar flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      {sidebar}
      <section
        aria-label={t(`${activeSection}.title`)}
        tabIndex={0}
        className={`@container/settings min-w-0 flex-1 bg-surface px-4 py-5 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 sm:px-6 lg:flex lg:min-h-0 lg:flex-col ${
          sectionUsesInternalScroll
            ? "lg:overflow-hidden"
            : "workspace-scrollbar lg:overflow-y-auto"
        }`}
      >
        {messages}
        <div className={sectionUsesInternalScroll ? "min-w-0 lg:min-h-0 lg:flex-1 lg:overflow-hidden" : "min-w-0"}>
          {renderSectionContent()}
        </div>
      </section>
    </div>
  );

  if (isModal) {
    return (
      <Modal.Backdrop
        isOpen
        variant="blur"
        isDismissable={!saving}
        isKeyboardDismissDisabled={saving}
        onOpenChange={(isOpen) => !isOpen && !saving && closeSettings()}
      >
        <Modal.Container size="full" scroll="inside" className="p-0 sm:p-4">
          <Modal.Dialog className="flex h-[100dvh] min-h-0 w-full flex-col overflow-hidden sm:h-[88vh] sm:max-h-[88vh] sm:max-w-7xl">
            <Modal.Header className="grid shrink-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border px-5 py-4 text-left sm:px-6">
              <div className="flex min-w-0 items-baseline gap-3">
                <Modal.Heading className="min-w-0 text-left text-base font-semibold text-foreground sm:text-lg">
                  {t("title")}
                </Modal.Heading>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button size="sm" variant="outline" onPress={handleReload} isDisabled={saving || secretEditorOpen}>
                  {t("reload")}
                </Button>
                <Button size="sm" onPress={handleSave} isDisabled={saving || !config || secretEditorOpen} className="bg-accent text-accent-foreground">
                  {saving ? t("saving") : t("save")}
                </Button>
                <Modal.CloseTrigger aria-label={t("back")} isDisabled={saving} />
              </div>
            </Modal.Header>
            <Modal.Body className="flex min-h-0 flex-1 overflow-hidden p-0">{body}</Modal.Body>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] w-full min-h-0 min-w-0 flex-col overflow-hidden px-4 py-4 sm:px-6">
      {header}
      {body}
    </div>
  );
}
