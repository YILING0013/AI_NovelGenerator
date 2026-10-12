"use client";

import { useEffect, useId, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Chip,
  Input,
  InputGroup,
  Label,
  NumberField,
  TextField,
} from "@heroui/react";
import type { AppConfig } from "@/types/config";

interface Props {
  config: AppConfig;
  onChange: (partial: Partial<AppConfig>) => void;
  onSecretEditingChange?: (editing: boolean) => void;
}

/**
 * 渲染数据库连接设置，并在本地确认 MongoDB 地址后再写入页面配置草稿。
 *
 * Args:
 *   config: 当前页面中的设置草稿。
 *   onChange: 更新页面设置草稿的回调。
 *   onSecretEditingChange: 通知父级当前是否有尚未确认的连接地址输入。
 *
 * Returns:
 *   扁平的数据库配置章节。
 */
export function DatabaseCard({ config, onChange, onSecretEditingChange }: Props) {
  const t = useTranslations("settings.database");
  const replacementErrorId = useId();
  const [isEditingSecret, setIsEditingSecret] = useState(false);
  const [replacementDraft, setReplacementDraft] = useState("");
  const [replacementError, setReplacementError] = useState("");
  const [showUrl, setShowUrl] = useState(false);

  useEffect(() => {
    return () => onSecretEditingChange?.(false);
  }, [onSecretEditingChange]);

  const setSecretEditing = (editing: boolean) => {
    setIsEditingSecret(editing);
    onSecretEditingChange?.(editing);
  };

  const startReplacingSecret = () => {
    setReplacementDraft(
      config.mongodb_url_update.action === "replace"
        ? config.mongodb_url_update.value
        : ""
    );
    setReplacementError("");
    setShowUrl(false);
    setSecretEditing(true);
  };

  const cancelReplacingSecret = () => {
    setReplacementDraft("");
    setReplacementError("");
    setShowUrl(false);
    setSecretEditing(false);
  };

  const confirmReplacingSecret = () => {
    if (!replacementDraft.trim()) {
      setReplacementError(t("replacementRequired"));
      return;
    }

    onChange({
      mongodb_url_update: { action: "replace", value: replacementDraft },
    });
    setReplacementError("");
    setShowUrl(false);
    setSecretEditing(false);
  };

  const restoreStoredSecret = () => {
    setReplacementDraft("");
    setReplacementError("");
    setShowUrl(false);
    onChange({ mongodb_url_update: { action: "preserve" } });
  };

  const secretStatus =
    config.mongodb_url_update.action === "replace"
      ? t("secretWillReplace")
      : config.mongodb_url_update.action === "clear"
        ? t("secretWillClear")
        : config.mongodb_url_configured
          ? t("secretConfigured")
          : t("secretMissing");

  return (
    <section className="min-w-0" aria-labelledby="database-settings-title">
      <header className="border-b border-border pb-4">
        <h2 id="database-settings-title" className="text-lg font-semibold text-foreground">
          {t("title")}
        </h2>
      </header>

      <div className="grid min-w-0 gap-5 py-6 md:grid-cols-2">
        <div className="min-w-0 space-y-3 md:col-span-2">
          <div className="flex flex-wrap items-center gap-2">
            <Label className="text-sm font-medium text-muted">{t("mongodbUrl")}</Label>
            <Chip size="sm" variant="soft">
              {secretStatus}
            </Chip>
          </div>

          {isEditingSecret ? (
            <TextField
              value={replacementDraft}
              onChange={(value) => {
                setReplacementDraft(value);
                if (replacementError) setReplacementError("");
              }}
              isRequired
              isInvalid={Boolean(replacementError)}
              className="grid min-w-0 gap-2"
            >
              <Label className="text-sm font-medium text-muted">{t("replacementUrl")}</Label>
              <InputGroup
                fullWidth
                className="min-h-11 w-full rounded-xl border border-border bg-background/80 shadow-none focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15"
              >
                <InputGroup.Input
                  type={showUrl ? "text" : "password"}
                  autoComplete="new-password"
                  placeholder={t("mongodbUrlPlaceholder")}
                  aria-invalid={Boolean(replacementError)}
                  aria-describedby={replacementError ? replacementErrorId : undefined}
                  className="min-h-11 min-w-0 bg-transparent px-3.5 py-2.5 text-sm text-foreground shadow-none placeholder:text-muted/55"
                />
                <InputGroup.Suffix className="h-auto self-stretch border-l border-border/70 px-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    isIconOnly
                    className="size-9 min-h-9 min-w-9 shrink-0 rounded-lg text-muted hover:bg-surface-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/30"
                    aria-label={showUrl ? t("hideUrl") : t("showUrl")}
                    aria-pressed={showUrl}
                    onPress={() => setShowUrl((visible) => !visible)}
                  >
                    {showUrl ? (
                      <svg
                        aria-hidden="true"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="m3 3 18 18" />
                        <path d="M10.6 10.7a2 2 0 0 0 2.7 2.7" />
                        <path d="M9.9 4.2A10.7 10.7 0 0 1 12 4c5.5 0 9.5 5 10 8a11.8 11.8 0 0 1-2.1 4.2" />
                        <path d="M6.6 6.6C4.1 8.2 2.4 10.5 2 12c.5 3 4.5 8 10 8a10.7 10.7 0 0 0 5.4-1.4" />
                      </svg>
                    ) : (
                      <svg
                        aria-hidden="true"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </Button>
                </InputGroup.Suffix>
              </InputGroup>
              {replacementError ? (
                <p
                  id={replacementErrorId}
                  role="alert"
                  className="text-xs leading-5 text-red-700 dark:text-red-300"
                >
                  {replacementError}
                </p>
              ) : (
                <p className="text-xs leading-5 text-muted">{t("confirmBeforeSave")}</p>
              )}
            </TextField>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {isEditingSecret ? (
              <>
                <Button size="sm" variant="ghost" onPress={cancelReplacingSecret}>
                  {t("cancel")}
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  className="bg-accent text-accent-foreground hover:bg-accent-hover"
                  onPress={confirmReplacingSecret}
                >
                  {t("confirm")}
                </Button>
              </>
            ) : config.mongodb_url_update.action === "replace" ? (
              <>
                <Button size="sm" variant="outline" onPress={startReplacingSecret}>
                  {t("editSecret")}
                </Button>
                <Button size="sm" variant="ghost" onPress={restoreStoredSecret}>
                  {t("restoreSecret")}
                </Button>
              </>
            ) : config.mongodb_url_update.action === "clear" ? (
              <>
                <Button size="sm" variant="outline" onPress={startReplacingSecret}>
                  {t("replaceSecret")}
                </Button>
                <Button size="sm" variant="ghost" onPress={restoreStoredSecret}>
                  {t("restoreSecret")}
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onPress={startReplacingSecret}>
                  {t("replaceSecret")}
                </Button>
                {config.mongodb_url_configured ? (
                  <Button
                    size="sm"
                    variant="danger-soft"
                    onPress={() =>
                      onChange({ mongodb_url_update: { action: "clear" } })
                    }
                  >
                    {t("clearSecret")}
                  </Button>
                ) : null}
              </>
            )}
          </div>
        </div>

        <TextField
          value={config.mongo_database_name || ""}
          onChange={(value) => onChange({ mongo_database_name: value })}
          isRequired
          className="grid min-w-0 gap-2"
        >
          <Label className="text-sm font-medium text-muted">{t("databaseName")}</Label>
          <Input
            placeholder={t("databaseNamePlaceholder")}
            className="min-h-11 rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground shadow-none outline-none transition-[border-color,box-shadow] placeholder:text-muted/55 focus:border-accent focus:ring-2 focus:ring-accent/15"
          />
        </TextField>

        <NumberField
          value={config.mongo_timeout_ms ?? 5000}
          onChange={(value) => onChange({ mongo_timeout_ms: Math.max(0, value) })}
          minValue={0}
          className="grid min-w-0 gap-2"
        >
          <Label className="text-sm font-medium text-muted">{t("timeoutMs")}</Label>
          <NumberField.Group className="min-h-11 w-full rounded-xl border border-border bg-background/80 shadow-none focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
            <NumberField.DecrementButton />
            <NumberField.Input className="min-h-11 min-w-0 flex-1 border-0 bg-transparent text-sm shadow-none outline-none" />
            <NumberField.IncrementButton />
          </NumberField.Group>
        </NumberField>
      </div>
    </section>
  );
}
