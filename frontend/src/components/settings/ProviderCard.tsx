"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Card,
  Button,
  TextField,
  Input,
  Label,
  NumberField,
  Select,
  ListBox,
  ListBoxItem,
  Switch,
  Chip,
  Accordion,
} from "@heroui/react";
import type { AppConfig, ProviderConfig } from "@/types/config";
import { newProviderConfig } from "@/types/config";
import { OptionalSliderParam, OptionalNumberParam, OptionalTextParam } from "@/components/shared/OptionalParamControls";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
}

const PROVIDER_TYPES = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
  { id: "claude", label: "Claude" },
];

const ALIAS_REGEX = /^[a-zA-Z0-9_]+$/;

export function ProviderCard({ config, onChange }: Props) {
  const t = useTranslations("settings.provider");
  const [newAlias, setNewAlias] = useState("");
  const [aliasError, setAliasError] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  const providers = config.llm?.providers || {};
  const providerAliases = Object.keys(providers);
  const defaultProvider = config.llm?.default_provider || "";

  const updateProvider = (alias: string, updates: Partial<ProviderConfig>) => {
    const next = {
      ...config,
      llm: {
        ...config.llm,
        providers: {
          ...config.llm.providers,
          [alias]: { ...config.llm.providers[alias], ...updates },
        },
      },
    };
    onChange(next);
  };

  const setDefaultProvider = (alias: string) => {
    onChange({
      ...config,
      llm: { ...config.llm, default_provider: alias },
    });
  };

  const addProvider = () => {
    const trimmed = newAlias.trim();
    if (!trimmed || !ALIAS_REGEX.test(trimmed)) {
      setAliasError(t("aliasRule"));
      return;
    }
    if (trimmed in providers) {
      setAliasError(t("aliasDuplicate"));
      return;
    }
    const next = {
      ...config,
      llm: {
        ...config.llm,
        providers: {
          ...config.llm.providers,
          [trimmed]: newProviderConfig(),
        },
      },
    };
    onChange(next);
    setNewAlias("");
    setAliasError("");
    setShowAddForm(false);
  };

  const deleteProvider = (alias: string) => {
    if (!confirm(t("deleteConfirm"))) return;
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { [alias]: _, ...rest } = config.llm.providers;
    const next = {
      ...config,
      llm: {
        ...config.llm,
        providers: rest,
        default_provider:
          config.llm.default_provider === alias ? "" : config.llm.default_provider,
      },
    };
    onChange(next);
  };

  return (
    <Card className="bg-surface border border-border shadow-sm">
      <Card.Header className="flex-col items-start gap-3">
        <Card.Title className="text-lg font-semibold text-foreground">{t("title")}</Card.Title>
        {/* Default Provider selector */}
        <Select
          selectedKey={defaultProvider || null}
          onSelectionChange={(key) => {
            if (key) setDefaultProvider(String(key));
          }}
          className="max-w-xs"
        >
          <Label className="text-sm text-muted">{t("defaultProvider")}</Label>
          <Select.Trigger className="border border-border rounded-lg px-3 py-2 text-sm bg-surface hover:border-warm-400">
            <Select.Value />
          </Select.Trigger>
          <Select.Popover>
            <ListBox>
              {providerAliases.map((alias) => (
                <ListBoxItem key={alias} id={alias}>
                  {alias}
                </ListBoxItem>
              ))}
            </ListBox>
          </Select.Popover>
        </Select>
      </Card.Header>
      <Card.Content className="space-y-2">
        {/* Provider list */}
        <Accordion allowsMultipleExpanded>
          {providerAliases.map((alias) => {
            const p = providers[alias];
            const isDefault = alias === defaultProvider;
            return (
              <Accordion.Item key={alias} id={alias}>
                <Accordion.Heading>
                  <Accordion.Trigger className="flex items-center gap-2 w-full text-left px-3 py-2 hover:bg-surface-secondary rounded">
                    <span className="font-medium flex-1">{alias}</span>
                    <Chip
                      size="sm"
                      variant="soft"
                      className={
                        p.enabled
                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-warm-200 text-muted"
                      }
                    >
                      {p.enabled ? t("statusEnabled") : t("statusDisabled")}
                    </Chip>
                    {isDefault && (
                      <Chip size="sm" variant="soft" className="bg-accent/15 text-accent">
                        {t("badgeDefault")}
                      </Chip>
                    )}
                    <Accordion.Indicator />
                  </Accordion.Trigger>
                </Accordion.Heading>
                <Accordion.Panel>
                  <Accordion.Body>
                    <ProviderForm
                      alias={alias}
                      provider={p}
                      onChange={(updates) => updateProvider(alias, updates)}
                      onDelete={() => deleteProvider(alias)}
                    />
                  </Accordion.Body>
                </Accordion.Panel>
              </Accordion.Item>
            );
          })}
        </Accordion>

        {/* Add Provider */}
        {showAddForm ? (
          <div className="flex items-end gap-2 pt-2">
            <div className="flex-1">
              <TextField
                value={newAlias}
                onChange={(v) => {
                  setNewAlias(v);
                  setAliasError("");
                }}
                isInvalid={!!aliasError}
              >
                <Label className="text-sm">{t("alias")}</Label>
                <Input placeholder={t("aliasPlaceholder")} className="border-border" />
              </TextField>
              {aliasError && (
                <p className="text-xs text-red-600 mt-1">{aliasError}</p>
              )}
            </div>
            <Button
              onPress={addProvider}
              className="bg-accent text-white hover:bg-accent-hover"
              size="sm"
            >
              {t("addProvider")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onPress={() => {
                setShowAddForm(false);
                setNewAlias("");
                setAliasError("");
              }}
              className="border-border text-foreground"
            >
              Cancel
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            onPress={() => setShowAddForm(true)}
            className="border-border text-foreground hover:bg-surface-secondary w-full"
          >
            + {t("addProvider")}
          </Button>
        )}
      </Card.Content>
    </Card>
  );
}

/* ---- Individual Provider Form ---- */

function ProviderForm({
  alias,
  provider,
  onChange,
  onDelete,
}: {
  alias: string;
  provider: ProviderConfig;
  onChange: (updates: Partial<ProviderConfig>) => void;
  onDelete: () => void;
}) {
  const t = useTranslations("settings.provider");
  const [showKey, setShowKey] = useState(false);
  const [showGenParams, setShowGenParams] = useState(false);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-4">
      {/* Type select */}
      <Select
        selectedKey={provider.type}
        onSelectionChange={(key) => {
          if (key) onChange({ type: String(key) as ProviderConfig["type"] });
        }}
      >
        <Label className="text-sm text-muted">{t("type")}</Label>
        <Select.Trigger className="border border-border rounded-lg px-3 py-2 text-sm bg-surface hover:border-warm-400">
          <Select.Value />
        </Select.Trigger>
        <Select.Popover>
          <ListBox>
            {PROVIDER_TYPES.map((pt) => (
              <ListBoxItem key={pt.id} id={pt.id}>
                {pt.label}
              </ListBoxItem>
            ))}
          </ListBox>
        </Select.Popover>
      </Select>

      {/* Base URL */}
      <TextField value={provider.base_url} onChange={(v) => onChange({ base_url: v })}>
        <Label className="text-sm text-muted">{t("baseUrl")}</Label>
        <Input className="border-border" />
      </TextField>

      {/* API Key */}
      <div>
        <TextField value={provider.api_key} onChange={(v) => onChange({ api_key: v })}>
          <Label className="text-sm text-muted">{t("apiKey")}</Label>
          <Input type={showKey ? "text" : "password"} className="border-border" />
        </TextField>
        <button
          type="button"
          className="text-xs text-muted hover:text-foreground mt-1"
          onClick={() => setShowKey(!showKey)}
        >
          {showKey ? "Hide" : "Show"}
        </button>
      </div>

      {/* Default Model */}
      <TextField value={provider.default_model} onChange={(v) => onChange({ default_model: v })}>
        <Label className="text-sm text-muted">{t("defaultModel")}</Label>
        <Input className="border-border" />
      </TextField>

      {/* Timeout */}
      <NumberField
        value={provider.timeout_seconds}
        onChange={(v) => onChange({ timeout_seconds: Math.max(0, v) })}
        minValue={0}
      >
        <Label className="text-sm text-muted">{t("timeoutSeconds")}</Label>
        <NumberField.Group>
          <NumberField.DecrementButton />
          <NumberField.Input className="border-border" />
          <NumberField.IncrementButton />
        </NumberField.Group>
      </NumberField>

      {/* Max Retries */}
      <NumberField
        value={provider.max_retries}
        onChange={(v) => onChange({ max_retries: Math.max(0, v) })}
        minValue={0}
      >
        <Label className="text-sm text-muted">{t("maxRetries")}</Label>
        <NumberField.Group>
          <NumberField.DecrementButton />
          <NumberField.Input className="border-border" />
          <NumberField.IncrementButton />
        </NumberField.Group>
      </NumberField>

      {/* Max Concurrency */}
      <NumberField
        value={provider.max_concurrency}
        onChange={(v) => onChange({ max_concurrency: Math.max(0, v) })}
        minValue={0}
      >
        <Label className="text-sm text-muted">{t("maxConcurrency")}</Label>
        <NumberField.Group>
          <NumberField.DecrementButton />
          <NumberField.Input className="border-border" />
          <NumberField.IncrementButton />
        </NumberField.Group>
      </NumberField>

      {/* Switches */}
      <div className="md:col-span-2 flex flex-wrap gap-x-6 gap-y-3">
        <Switch isSelected={provider.enabled} onChange={(v) => onChange({ enabled: v })}>
          <Switch.Control>
            <Switch.Thumb />
          </Switch.Control>
          <Switch.Content className="text-sm">{t("enabled")}</Switch.Content>
        </Switch>
        <Switch
          isSelected={provider.use_system_proxy ?? false}
          onChange={(v) => onChange({ use_system_proxy: v })}
        >
          <Switch.Control>
            <Switch.Thumb />
          </Switch.Control>
          <Switch.Content className="text-sm">{t("useSystemProxy")}</Switch.Content>
        </Switch>
        <Switch isSelected={provider.supports_streaming} onChange={(v) => onChange({ supports_streaming: v })}>
          <Switch.Control>
            <Switch.Thumb />
          </Switch.Control>
          <Switch.Content className="text-sm">{t("supportsStreaming")}</Switch.Content>
        </Switch>
        <Switch isSelected={provider.supports_json_schema} onChange={(v) => onChange({ supports_json_schema: v })}>
          <Switch.Control>
            <Switch.Thumb />
          </Switch.Control>
          <Switch.Content className="text-sm">{t("supportsJsonSchema")}</Switch.Content>
        </Switch>
        <Switch isSelected={provider.supports_function_calling} onChange={(v) => onChange({ supports_function_calling: v })}>
          <Switch.Control>
            <Switch.Thumb />
          </Switch.Control>
          <Switch.Content className="text-sm">{t("supportsFunctionCalling")}</Switch.Content>
        </Switch>
      </div>

      {/* Generation Parameters (collapsible) */}
      <div className="md:col-span-2">
        <button
          type="button"
          className="flex items-center gap-2 text-sm font-medium text-muted hover:text-foreground transition-colors py-2"
          onClick={() => setShowGenParams(!showGenParams)}
        >
          <svg
            className={`w-4 h-4 transition-transform ${showGenParams ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          {t("genParams.title")}
        </button>
        {showGenParams && (
          <div className="border border-border rounded-lg p-4 mt-1 space-y-4 bg-surface-secondary/30">
            <p className="text-xs text-muted">{t("genParams.hint")}</p>

            {/* Temperature */}
            <OptionalSliderParam
              label={t("genParams.temperature")}
              value={provider.temperature}
              onToggle={(enabled) =>
                onChange({ temperature: enabled ? 0.7 : null })
              }
              onValueChange={(v) => onChange({ temperature: v })}
              min={0}
              max={2}
              step={0.05}
            />

            {/* Top P */}
            <OptionalSliderParam
              label={t("genParams.topP")}
              value={provider.top_p}
              onToggle={(enabled) =>
                onChange({ top_p: enabled ? 0.9 : null })
              }
              onValueChange={(v) => onChange({ top_p: v })}
              min={0}
              max={1}
              step={0.05}
            />

            {/* Max Tokens */}
            <OptionalNumberParam
              label={t("genParams.maxTokens")}
              value={provider.max_tokens}
              onToggle={(enabled) =>
                onChange({ max_tokens: enabled ? 4096 : null })
              }
              onValueChange={(v) => onChange({ max_tokens: v })}
              min={256}
              max={1000000}
              step={256}
            />

            {/* Presence Penalty */}
            <OptionalSliderParam
              label={t("genParams.presencePenalty")}
              value={provider.presence_penalty}
              onToggle={(enabled) =>
                onChange({ presence_penalty: enabled ? 0 : null })
              }
              onValueChange={(v) => onChange({ presence_penalty: v })}
              min={-2}
              max={2}
              step={0.1}
            />

            {/* Frequency Penalty */}
            <OptionalSliderParam
              label={t("genParams.frequencyPenalty")}
              value={provider.frequency_penalty}
              onToggle={(enabled) =>
                onChange({ frequency_penalty: enabled ? 0 : null })
              }
              onValueChange={(v) => onChange({ frequency_penalty: v })}
              min={-2}
              max={2}
              step={0.1}
            />

            {/* System Prompt */}
            <OptionalTextParam
              label={t("genParams.systemPrompt")}
              value={provider.system_prompt}
              onToggle={(enabled) =>
                onChange({ system_prompt: enabled ? "" : null })
              }
              onValueChange={(v) => onChange({ system_prompt: v })}
              placeholder={t("genParams.systemPromptPlaceholder")}
            />
          </div>
        )}
      </div>

      {/* Delete */}
      <div className="md:col-span-2 flex justify-end">
        <Button
          size="sm"
          variant="outline"
          onPress={onDelete}
          className="border-red-300 text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950/30"
        >
          {t("deleteProvider")} &quot;{alias}&quot;
        </Button>
      </div>
    </div>
  );
}
