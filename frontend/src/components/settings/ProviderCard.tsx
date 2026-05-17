"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  Chip,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  NumberField,
  Select,
  Switch,
  TextField,
} from "@heroui/react";
import { apiPost } from "@/lib/api";
import type {
  AppConfig,
  ProviderCapabilityResult,
  ProviderConfig,
  ProviderTestCapability,
  ProviderTestResponse,
} from "@/types/config";
import {
  getProviderAliasesForSelection,
  isProviderSelectable,
  newProviderConfig,
  removeProviderAlias,
  renameProviderAlias,
} from "@/types/config";
import {
  OptionalNumberParam,
  OptionalSliderParam,
  OptionalTextParam,
} from "@/components/shared/OptionalParamControls";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
  onProviderRename: (from: string, to: string) => void;
}

type ProviderFilter = "all" | "enabled" | "needsTest";
type ProviderTestRunState = {
  status: "idle" | "running" | "done" | "error";
  activeStep: number;
  response?: ProviderTestResponse;
  error?: string;
};

const PROVIDER_TYPES = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
  { id: "claude", label: "Claude" },
];

const DEFAULT_PROVIDER_BASE_URLS: Record<ProviderConfig["type"], string> = {
  openai: "https://api.openai.com",
  gemini: "https://generativelanguage.googleapis.com",
  claude: "https://api.anthropic.com",
};

function normalizeBaseUrlForComparison(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

const OFFICIAL_PROVIDER_BASE_URLS = new Set([
  ...Object.values(DEFAULT_PROVIDER_BASE_URLS).map(normalizeBaseUrlForComparison),
  "https://api.openai.com/v1",
]);

/**
 * 切换客户端类别时决定是否替换 API 根地址。
 *
 * Args:
 *   currentBaseUrl: 当前表单中的 API 基地址。
 *   nextType: 即将切换到的客户端类别。
 *
 * Returns:
 *   空地址或内置官方地址返回新类别默认根地址；第三方地址保持用户填写值。
 */
function resolveBaseUrlForProviderTypeChange(
  currentBaseUrl: string,
  nextType: ProviderConfig["type"]
): string {
  const normalizedCurrent = normalizeBaseUrlForComparison(currentBaseUrl);
  if (!normalizedCurrent || OFFICIAL_PROVIDER_BASE_URLS.has(normalizedCurrent)) {
    return DEFAULT_PROVIDER_BASE_URLS[nextType];
  }
  return currentBaseUrl;
}

const TEST_STEPS: { capability: ProviderTestCapability; labelKey: string }[] = [
  { capability: "connection", labelKey: "test.connection" },
  { capability: "streaming", labelKey: "test.streaming" },
  { capability: "json_schema", labelKey: "test.jsonSchema" },
  { capability: "function_calling", labelKey: "test.functionCalling" },
];

const ALIAS_REGEX = /^[a-zA-Z0-9_]+$/;

export function ProviderCard({ config, onChange, onProviderRename }: Props) {
  const t = useTranslations("settings.provider");
  const [newAlias, setNewAlias] = useState("");
  const [aliasError, setAliasError] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [renamingAlias, setRenamingAlias] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState("");
  const [selectedAlias, setSelectedAlias] = useState("");
  const [filter, setFilter] = useState<ProviderFilter>("all");
  const [showKey, setShowKey] = useState(false);
  const [showGenParams, setShowGenParams] = useState(false);
  const [pendingDeleteAlias, setPendingDeleteAlias] = useState("");
  const [testStates, setTestStates] = useState<Record<string, ProviderTestRunState>>({});

  const providers = config.llm.providers;
  const providerAliases = Object.keys(providers);
  const defaultProvider = config.llm?.default_provider || "";
  const defaultProviderOptions = getProviderAliasesForSelection(providers, defaultProvider);
  const selectedProvider = selectedAlias ? providers[selectedAlias] : null;
  const selectedTestState = selectedAlias ? testStates[selectedAlias] : undefined;

  useEffect(() => {
    if (selectedAlias && providers[selectedAlias]) return;
    setSelectedAlias(providerAliases[0] || "");
  }, [providerAliases, providers, selectedAlias]);

  const filteredAliases = useMemo(() => {
    return providerAliases.filter((alias) => {
      const provider = providers[alias];
      if (filter === "enabled") return provider.enabled;
      if (filter === "needsTest") return testStates[alias]?.status !== "done";
      return true;
    });
  }, [filter, providerAliases, providers, testStates]);

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
    onChange({
      ...config,
      llm: {
        ...config.llm,
        providers: {
          ...config.llm.providers,
          [trimmed]: newProviderConfig(),
        },
      },
    });
    setSelectedAlias(trimmed);
    setNewAlias("");
    setAliasError("");
    setShowAddForm(false);
  };

  const startRename = (alias: string) => {
    setRenamingAlias(alias);
    setRenameValue(alias);
    setRenameError("");
    setPendingDeleteAlias("");
  };

  const cancelRename = () => {
    setRenamingAlias("");
    setRenameValue("");
    setRenameError("");
  };

  const confirmRename = (alias: string) => {
    const trimmed = renameValue.trim();
    if (!trimmed || !ALIAS_REGEX.test(trimmed)) {
      setRenameError(t("aliasRule"));
      return;
    }
    if (trimmed === alias) {
      cancelRename();
      return;
    }
    if (trimmed in providers) {
      setRenameError(t("aliasDuplicate"));
      return;
    }

    onChange(renameProviderAlias(config, alias, trimmed));
    onProviderRename(alias, trimmed);
    setSelectedAlias(trimmed);
    setTestStates((current) => {
      const next = { ...current };
      if (next[alias]) {
        next[trimmed] = next[alias];
        delete next[alias];
      }
      return next;
    });
    cancelRename();
  };

  const deleteProvider = (alias: string) => {
    const nextAliases = providerAliases.filter((item) => item !== alias);
    if (renamingAlias === alias) {
      cancelRename();
    }
    setPendingDeleteAlias("");
    setSelectedAlias(nextAliases[0] || "");
    setTestStates((current) => {
      const next = { ...current };
      delete next[alias];
      return next;
    });
    onChange(removeProviderAlias(config, alias));
  };

  const runProviderTest = async (alias: string) => {
    const provider = providers[alias];
    if (!provider) return;

    setPendingDeleteAlias("");
    setTestStates((current) => ({
      ...current,
      [alias]: { status: "running", activeStep: 0 },
    }));

    try {
      const response = await apiPost<ProviderTestResponse>("/api/config/llm-providers/test", {
        alias,
        provider,
      });

      // 测试只回填当前表单，是否写入磁盘仍交给顶部保存按钮。
      updateProvider(alias, response.recommendations);
      setTestStates((current) => ({
        ...current,
        [alias]: {
          status: "done",
          activeStep: TEST_STEPS.length - 1,
          response,
        },
      }));
    } catch (error) {
      setTestStates((current) => ({
        ...current,
        [alias]: {
          status: "error",
          activeStep: 0,
          error: error instanceof Error ? error.message : t("test.unknownError"),
        },
      }));
    }
  };

  const baseUrlPlaceholder: Record<ProviderConfig["type"], string> = {
    openai: t("baseUrlPlaceholderOpenai"),
    gemini: t("baseUrlPlaceholderGemini"),
    claude: t("baseUrlPlaceholderClaude"),
  };

  return (
    <Card className="bg-surface border border-border shadow-sm">
      <Card.Header className="flex-col items-start gap-2 border-b border-border/70 pb-2">
        <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Card.Title className="text-lg font-semibold text-foreground">{t("title")}</Card.Title>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <Label className="shrink-0 text-sm font-medium text-muted">{t("defaultProvider")}</Label>
            <Select
              aria-label={t("defaultProvider")}
              selectedKey={defaultProviderOptions.includes(defaultProvider) ? defaultProvider : null}
              onSelectionChange={(key) => {
                if (key) setDefaultProvider(String(key));
              }}
              className="w-full sm:w-72"
            >
              <Select.Trigger className="border border-border rounded-lg px-3 py-2 text-sm bg-surface hover:border-warm-400">
                <Select.Value />
              </Select.Trigger>
              <Select.Popover>
                <ListBox>
                  {defaultProviderOptions.map((alias) => (
                    <ListBoxItem key={alias} id={alias} isDisabled={!isProviderSelectable(providers, alias)}>
                      {alias}
                    </ListBoxItem>
                  ))}
                </ListBox>
              </Select.Popover>
            </Select>
          </div>
        </div>
      </Card.Header>

      <Card.Content className="p-3 pt-4">
        <div className="grid min-h-[720px] grid-cols-1 gap-3 lg:grid-cols-[320px_minmax(0,1fr)]">
          <ProviderList
            aliases={filteredAliases}
            allAliases={providerAliases}
            providers={providers}
            defaultProvider={defaultProvider}
            selectedAlias={selectedAlias}
            filter={filter}
            testStates={testStates}
            newAlias={newAlias}
            aliasError={aliasError}
            showAddForm={showAddForm}
            onFilterChange={setFilter}
            onSelect={setSelectedAlias}
            onNewAliasChange={(value) => {
              setNewAlias(value);
              setAliasError("");
            }}
            onAddProvider={addProvider}
            onShowAddFormChange={setShowAddForm}
            onCancelAdd={() => {
              setShowAddForm(false);
              setNewAlias("");
              setAliasError("");
            }}
            t={t}
          />

          <div className="min-w-0 rounded-lg border border-border bg-surface px-3 py-3">
            {selectedProvider ? (
              <ProviderDetail
                alias={selectedAlias}
                provider={selectedProvider}
                isDefault={selectedAlias === defaultProvider}
                isRenaming={renamingAlias === selectedAlias}
                renameValue={renameValue}
                renameError={renameError}
                showKey={showKey}
                showGenParams={showGenParams}
                pendingDelete={pendingDeleteAlias === selectedAlias}
                testState={selectedTestState}
                baseUrlPlaceholder={baseUrlPlaceholder[selectedProvider.type]}
                onChange={(updates) => updateProvider(selectedAlias, updates)}
                onRenameStart={() => startRename(selectedAlias)}
                onRenameValueChange={(value) => {
                  setRenameValue(value);
                  setRenameError("");
                }}
                onRenameConfirm={() => confirmRename(selectedAlias)}
                onRenameCancel={cancelRename}
                onDeleteAsk={() => {
                  setPendingDeleteAlias(selectedAlias);
                  cancelRename();
                }}
                onDeleteConfirm={() => deleteProvider(selectedAlias)}
                onDeleteCancel={() => setPendingDeleteAlias("")}
                onShowKeyChange={setShowKey}
                onShowGenParamsChange={setShowGenParams}
                onRunTest={() => runProviderTest(selectedAlias)}
                t={t}
              />
            ) : (
              <div className="flex h-full min-h-[360px] items-center justify-center rounded-lg border border-dashed border-border bg-surface-secondary/40 text-sm text-muted">
                {t("empty")}
              </div>
            )}
          </div>
        </div>
      </Card.Content>
    </Card>
  );
}

function ProviderList({
  aliases,
  allAliases,
  providers,
  defaultProvider,
  selectedAlias,
  filter,
  testStates,
  newAlias,
  aliasError,
  showAddForm,
  onFilterChange,
  onSelect,
  onNewAliasChange,
  onAddProvider,
  onShowAddFormChange,
  onCancelAdd,
  t,
}: {
  aliases: string[];
  allAliases: string[];
  providers: Record<string, ProviderConfig>;
  defaultProvider: string;
  selectedAlias: string;
  filter: ProviderFilter;
  testStates: Record<string, ProviderTestRunState>;
  newAlias: string;
  aliasError: string;
  showAddForm: boolean;
  onFilterChange: (filter: ProviderFilter) => void;
  onSelect: (alias: string) => void;
  onNewAliasChange: (value: string) => void;
  onAddProvider: () => void;
  onShowAddFormChange: (show: boolean) => void;
  onCancelAdd: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <aside className="flex min-h-[420px] flex-col rounded-lg bg-surface-secondary/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{t("listTitle")}</h3>
          <p className="text-xs text-muted">{t("listCount", { count: allAliases.length })}</p>
        </div>
        <Chip size="sm" variant="soft" className="bg-accent/10 text-accent">
          {aliases.length}
        </Chip>
      </div>

      <div className="mt-3 flex gap-2">
        {(["all", "enabled", "needsTest"] as ProviderFilter[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onFilterChange(item)}
            className={`h-8 rounded-full px-3 text-xs transition-colors ${
              filter === item
                ? "bg-accent text-white"
                : "border border-border bg-surface text-muted hover:text-foreground"
            }`}
          >
            {t(`filters.${item}`)}
          </button>
        ))}
      </div>

      <div className="mt-3 flex-1 space-y-2 overflow-y-auto pr-1">
        {aliases.map((alias) => {
          const provider = providers[alias];
          const testState = testStates[alias];
          return (
            <button
              key={alias}
              type="button"
              onClick={() => onSelect(alias)}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${
                selectedAlias === alias
                  ? "border-accent bg-surface"
                  : "border-border bg-surface/80 hover:border-warm-400 hover:bg-surface"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-foreground">{alias}</div>
                  <div className="mt-1 truncate text-xs text-muted">
                    {provider.type} · {provider.default_model || t("modelMissing")}
                  </div>
                </div>
                {/* Provider 列表只保留状态标签，避免右侧缩写块撑高卡片。 */}
                <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                  <StatusChip tone={provider.enabled ? "success" : "muted"}>
                    {provider.enabled ? t("statusEnabled") : t("statusDisabled")}
                  </StatusChip>
                  {alias === defaultProvider && <StatusChip tone="accent">{t("badgeDefault")}</StatusChip>}
                  {testState?.status === "done" && <StatusChip tone="success">{t("test.tested")}</StatusChip>}
                  {testState?.status === "running" && <StatusChip tone="warning">{t("test.running")}</StatusChip>}
                  {testState?.status === "error" && <StatusChip tone="danger">{t("test.failed")}</StatusChip>}
                </div>
              </div>
            </button>
          );
        })}
        {aliases.length === 0 && (
          <div className="rounded-lg border border-dashed border-border bg-surface/70 p-4 text-sm text-muted">
            {t("noProviderForFilter")}
          </div>
        )}
      </div>

      <div className="mt-3 border-t border-border pt-3">
        {showAddForm ? (
          <div className="space-y-3">
            <TextField value={newAlias} onChange={onNewAliasChange} isInvalid={!!aliasError}>
              <Label className="text-sm text-muted">{t("alias")}</Label>
              <Input placeholder={t("aliasPlaceholder")} className="border-border" />
            </TextField>
            {aliasError && <p className="text-xs text-red-600">{aliasError}</p>}
            <div className="grid grid-cols-2 gap-2">
              <Button onPress={onAddProvider} size="sm" className="bg-accent text-white hover:bg-accent-hover">
                {t("addProvider")}
              </Button>
              <Button variant="outline" size="sm" onPress={onCancelAdd} className="border-border text-foreground">
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="outline"
            onPress={() => onShowAddFormChange(true)}
            className="w-full border-border text-foreground hover:bg-surface"
          >
            + {t("addProvider")}
          </Button>
        )}
      </div>
    </aside>
  );
}

function ProviderDetail({
  alias,
  provider,
  isDefault,
  isRenaming,
  renameValue,
  renameError,
  showKey,
  showGenParams,
  pendingDelete,
  testState,
  baseUrlPlaceholder,
  onChange,
  onRenameStart,
  onRenameValueChange,
  onRenameConfirm,
  onRenameCancel,
  onDeleteAsk,
  onDeleteConfirm,
  onDeleteCancel,
  onShowKeyChange,
  onShowGenParamsChange,
  onRunTest,
  t,
}: {
  alias: string;
  provider: ProviderConfig;
  isDefault: boolean;
  isRenaming: boolean;
  renameValue: string;
  renameError: string;
  showKey: boolean;
  showGenParams: boolean;
  pendingDelete: boolean;
  testState?: ProviderTestRunState;
  baseUrlPlaceholder: string;
  onChange: (updates: Partial<ProviderConfig>) => void;
  onRenameStart: () => void;
  onRenameValueChange: (value: string) => void;
  onRenameConfirm: () => void;
  onRenameCancel: () => void;
  onDeleteAsk: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
  onShowKeyChange: (show: boolean) => void;
  onShowGenParamsChange: (show: boolean) => void;
  onRunTest: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border bg-surface-secondary/30 p-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <ProviderInitial alias={alias} />
              <h3 className="truncate text-xl font-semibold text-foreground">{alias}</h3>
              {isDefault && <StatusChip tone="accent">{t("badgeDefault")}</StatusChip>}
              <StatusChip tone={provider.enabled ? "success" : "muted"}>
                {provider.enabled ? t("statusEnabled") : t("statusDisabled")}
              </StatusChip>
            </div>
            <p className="mt-1.5 text-sm text-muted">
              {provider.type} · {provider.default_model || t("modelMissing")}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onPress={onRenameStart}
              className="border-border text-foreground"
              isDisabled={testState?.status === "running"}
            >
              {t("renameProvider")}
            </Button>
            <Button
              size="sm"
              onPress={onRunTest}
              isDisabled={testState?.status === "running"}
              className="bg-accent text-white hover:bg-accent-hover"
            >
              {testState?.status === "running" ? t("test.running") : t("test.run")}
            </Button>
          </div>
        </div>

        {isRenaming && (
          <div className="mt-3 grid gap-3 border-t border-border pt-3 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-end">
            <div>
              <TextField value={renameValue} onChange={onRenameValueChange} isInvalid={!!renameError}>
                <Label className="text-sm text-muted">{t("renameTo")}</Label>
                <Input placeholder={t("aliasPlaceholder")} className="border-border" />
              </TextField>
              {renameError && <p className="mt-1 text-xs text-red-600">{renameError}</p>}
            </div>
            <Button size="sm" onPress={onRenameConfirm} className="bg-accent text-white hover:bg-accent-hover">
              {t("confirmRename")}
            </Button>
            <Button size="sm" variant="outline" onPress={onRenameCancel} className="border-border text-foreground">
              {t("cancel")}
            </Button>
          </div>
        )}
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-lg border border-border bg-surface-secondary/20 p-3">
          <SectionTitle title={t("connection.title")} description={t("connection.description")} />
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <Select
              selectedKey={provider.type}
              onSelectionChange={(key) => {
                if (!key) return;
                const nextType = String(key) as ProviderConfig["type"];
                // 第三方网关地址通常跨类型复用，只有空值或官方默认地址才随类别切换。
                onChange({
                  type: nextType,
                  base_url: resolveBaseUrlForProviderTypeChange(provider.base_url, nextType),
                });
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

            <TextField value={provider.default_model} onChange={(value) => onChange({ default_model: value })}>
              <Label className="text-sm text-muted">{t("defaultModel")}</Label>
              <Input className="border-border" />
            </TextField>

            <div className="md:col-span-2">
              <TextField value={provider.base_url} onChange={(value) => onChange({ base_url: value })}>
                <Label className="text-sm text-muted">{t("baseUrl")}</Label>
                <Input placeholder={baseUrlPlaceholder} className="border-border" />
              </TextField>
            </div>

            <div className="md:col-span-2">
              <TextField value={provider.api_key} onChange={(value) => onChange({ api_key: value })}>
                <Label className="text-sm text-muted">{t("apiKey")}</Label>
                <Input type={showKey ? "text" : "password"} className="border-border" />
              </TextField>
              <button
                type="button"
                className="mt-1 text-xs text-muted transition-colors hover:text-foreground"
                onClick={() => onShowKeyChange(!showKey)}
              >
                {showKey ? t("hideApiKey") : t("showApiKey")}
              </button>
            </div>

            {/* 数字配置改为单列，避免步进按钮挤压标签和输入内容。 */}
            <div className="md:col-span-2">
              <NumberField
                value={provider.timeout_seconds}
                onChange={(value) => onChange({ timeout_seconds: Math.max(0, value) })}
                minValue={0}
              >
                <Label className="text-sm text-muted">{t("timeoutSeconds")}</Label>
                <NumberField.Group>
                  <NumberField.DecrementButton />
                  <NumberField.Input className="border-border" />
                  <NumberField.IncrementButton />
                </NumberField.Group>
              </NumberField>
            </div>

            <div className="md:col-span-2">
              <NumberField
                value={provider.max_retries}
                onChange={(value) => onChange({ max_retries: Math.max(0, value) })}
                minValue={0}
              >
                <Label className="text-sm text-muted">{t("maxRetries")}</Label>
                <NumberField.Group>
                  <NumberField.DecrementButton />
                  <NumberField.Input className="border-border" />
                  <NumberField.IncrementButton />
                </NumberField.Group>
              </NumberField>
            </div>

            <div className="md:col-span-2">
              <NumberField
                value={provider.max_concurrency}
                onChange={(value) => onChange({ max_concurrency: Math.max(0, value) })}
                minValue={0}
              >
                <Label className="text-sm text-muted">{t("maxConcurrency")}</Label>
                <NumberField.Group>
                  <NumberField.DecrementButton />
                  <NumberField.Input className="border-border" />
                  <NumberField.IncrementButton />
                </NumberField.Group>
              </NumberField>
            </div>

            <div className="flex items-end md:col-span-2">
              <Switch
                isSelected={provider.use_system_proxy ?? false}
                onChange={(value) => onChange({ use_system_proxy: value })}
              >
                <Switch.Control>
                  <Switch.Thumb />
                </Switch.Control>
                <Switch.Content className="text-sm">{t("useSystemProxy")}</Switch.Content>
              </Switch>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-surface-secondary/20 p-3">
          <SectionTitle title={t("test.title")} description={t("test.description")} />
          <div className="mt-3 space-y-2.5">
            {TEST_STEPS.map((step, index) => (
              <TestStepRow
                key={step.capability}
                label={t(step.labelKey)}
                result={testState?.response?.results.find((item) => item.capability === step.capability)}
                isRunning={testState?.status === "running" && testState.activeStep === index}
                isQueued={testState?.status === "running" && testState.activeStep < index}
                wasSent={testState?.status === "running" && testState.activeStep > index}
                t={t}
              />
            ))}
          </div>
          {testState?.status === "done" && testState.response && (
            <div className="mt-3 rounded-lg border border-border bg-surface p-3">
              <div className="text-sm font-medium text-foreground">{testState.response.summary}</div>
              <p className="mt-1 text-xs text-muted">{t("test.appliedHint")}</p>
            </div>
          )}
          {testState?.status === "error" && (
            <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
              {testState.error}
            </div>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-border bg-surface-secondary/20 p-3">
        <SectionTitle title={t("capabilities.title")} description={t("capabilities.description")} />
        {/* 能力开关保持内容宽度，并压缩控件间距以优先放在同一行。 */}
        <div className="mt-3 flex flex-wrap gap-2">
          <CapabilitySwitch
            label={t("enabled")}
            selected={provider.enabled}
            onChange={(value) => onChange({ enabled: value })}
          />
          <CapabilitySwitch
            label={t("supportsStreaming")}
            selected={provider.supports_streaming}
            onChange={(value) => onChange({ supports_streaming: value })}
          />
          <CapabilitySwitch
            label={t("supportsJsonSchema")}
            selected={provider.supports_json_schema}
            onChange={(value) => onChange({ supports_json_schema: value })}
          />
          <CapabilitySwitch
            label={t("supportsFunctionCalling")}
            selected={provider.supports_function_calling}
            onChange={(value) => onChange({ supports_function_calling: value })}
          />
        </div>
      </section>

      <section className="rounded-lg border border-border bg-surface-secondary/20 p-3">
        <button
          type="button"
          className="flex w-full items-center justify-between gap-3 text-left"
          onClick={() => onShowGenParamsChange(!showGenParams)}
        >
          <SectionTitle title={t("genParams.title")} description={t("genParams.hint")} />
          <span className={`text-muted transition-transform ${showGenParams ? "rotate-90" : ""}`}>›</span>
        </button>
        {showGenParams && (
          <div className="mt-3 space-y-3 border-t border-border pt-3">
            <OptionalSliderParam
              label={t("genParams.temperature")}
              value={provider.temperature}
              onToggle={(enabled) => onChange({ temperature: enabled ? 0.7 : null })}
              onValueChange={(value) => onChange({ temperature: value })}
              min={0}
              max={2}
              step={0.05}
            />
            <OptionalSliderParam
              label={t("genParams.topP")}
              value={provider.top_p}
              onToggle={(enabled) => onChange({ top_p: enabled ? 0.9 : null })}
              onValueChange={(value) => onChange({ top_p: value })}
              min={0}
              max={1}
              step={0.05}
            />
            <OptionalNumberParam
              label={t("genParams.maxTokens")}
              value={provider.max_tokens}
              onToggle={(enabled) => onChange({ max_tokens: enabled ? 4096 : null })}
              onValueChange={(value) => onChange({ max_tokens: value })}
              min={256}
              max={1000000}
              step={256}
            />
            <OptionalSliderParam
              label={t("genParams.presencePenalty")}
              value={provider.presence_penalty}
              onToggle={(enabled) => onChange({ presence_penalty: enabled ? 0 : null })}
              onValueChange={(value) => onChange({ presence_penalty: value })}
              min={-2}
              max={2}
              step={0.1}
            />
            <OptionalSliderParam
              label={t("genParams.frequencyPenalty")}
              value={provider.frequency_penalty}
              onToggle={(enabled) => onChange({ frequency_penalty: enabled ? 0 : null })}
              onValueChange={(value) => onChange({ frequency_penalty: value })}
              min={-2}
              max={2}
              step={0.1}
            />
            <OptionalTextParam
              label={t("genParams.systemPrompt")}
              value={provider.system_prompt}
              onToggle={(enabled) => onChange({ system_prompt: enabled ? "" : null })}
              onValueChange={(value) => onChange({ system_prompt: value })}
              placeholder={t("genParams.systemPromptPlaceholder")}
            />
          </div>
        )}
      </section>

      <section className="rounded-lg border border-red-200 bg-red-50/60 p-3 dark:border-red-900/70 dark:bg-red-950/20">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h4 className="text-sm font-semibold text-red-700 dark:text-red-300">{t("danger.title")}</h4>
            <p className="mt-1 text-xs text-red-700/80 dark:text-red-300/80">{t("danger.description")}</p>
          </div>
          {pendingDelete ? (
            <div className="flex shrink-0 gap-2">
              <Button size="sm" className="bg-red-600 text-white hover:bg-red-700" onPress={onDeleteConfirm}>
                {t("danger.confirmDelete")}
              </Button>
              <Button size="sm" variant="outline" className="border-red-300 text-red-700" onPress={onDeleteCancel}>
                {t("cancel")}
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onPress={onDeleteAsk}
              className="border-red-300 text-red-700 hover:bg-red-100 dark:border-red-800 dark:text-red-300"
              isDisabled={testState?.status === "running"}
            >
              {t("deleteProvider")}
            </Button>
          )}
        </div>
      </section>
    </div>
  );
}

function TestStepRow({
  label,
  result,
  isRunning,
  isQueued,
  wasSent,
  t,
}: {
  label: string;
  result?: ProviderCapabilityResult;
  isRunning: boolean;
  isQueued: boolean;
  wasSent: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const status = result?.status;
  const tone =
    status === "passed"
      ? "success"
      : status === "failed"
        ? "danger"
        : status === "skipped"
          ? "muted"
          : isRunning
            ? "warning"
            : wasSent
              ? "accent"
              : "muted";
  const message =
    result?.message ||
    (isRunning ? t("test.inProgress") : isQueued ? t("test.queued") : wasSent ? t("test.sent") : t("test.notStarted"));

  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <div className="flex items-start gap-3">
        <span
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${getStepToneClass(
            tone
          )}`}
        >
          {status === "passed" ? "✓" : status === "failed" ? "!" : isRunning ? "…" : "•"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium text-foreground">{label}</div>
            {result && <div className="text-xs text-muted">{result.duration_ms}ms</div>}
          </div>
          <p className="mt-1 break-words text-xs text-muted">{message}</p>
        </div>
      </div>
    </div>
  );
}

function CapabilitySwitch({
  label,
  selected,
  onChange,
}: {
  label: string;
  selected: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-surface px-2.5 py-2">
      <Switch isSelected={selected} onChange={onChange}>
        <Switch.Control>
          <Switch.Thumb />
        </Switch.Control>
        <Switch.Content className="whitespace-nowrap text-xs font-medium">{label}</Switch.Content>
      </Switch>
    </div>
  );
}

function SectionTitle({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h4 className="text-base font-semibold text-foreground">{title}</h4>
      <p className="mt-1 text-xs text-muted">{description}</p>
    </div>
  );
}

function ProviderInitial({ alias }: { alias: string }) {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-sm font-semibold text-accent">
      {alias.slice(0, 1).toUpperCase()}
    </span>
  );
}

function StatusChip({ tone, children }: { tone: "accent" | "success" | "warning" | "danger" | "muted"; children: ReactNode }) {
  const classes: Record<typeof tone, string> = {
    accent: "bg-accent/10 text-accent",
    success: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
    warning: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    danger: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    muted: "bg-warm-200 text-muted dark:bg-warm-300/30",
  };
  return (
    <Chip size="sm" variant="soft" className={classes[tone]}>
      {children}
    </Chip>
  );
}

function getStepToneClass(tone: "accent" | "success" | "warning" | "danger" | "muted"): string {
  const classes: Record<typeof tone, string> = {
    accent: "bg-accent/10 text-accent",
    success: "bg-green-600 text-white",
    warning: "bg-amber-500 text-white",
    danger: "bg-red-600 text-white",
    muted: "bg-warm-200 text-muted",
  };
  return classes[tone];
}
