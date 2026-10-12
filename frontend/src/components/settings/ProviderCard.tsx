"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Chip,
  Input,
  InputGroup,
  Label,
  ListBox,
  ListBoxItem,
  NumberField,
  Select,
  Switch,
  TextArea,
  TextField,
} from "@heroui/react";
import { ReasoningControls } from "@/components/shared/ReasoningControls";
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
  getProviderApiMode,
  isProviderSelectable,
  newProviderConfig,
  removeProviderAlias,
  renameProviderAlias,
} from "@/types/config";
import {
  OptionalNumberParam,
  OptionalSliderParam,
} from "@/components/shared/OptionalParamControls";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
  onProviderRename: (from: string, to: string) => void;
  onSecretEditingChange?: (editing: boolean) => void;
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
  { id: "deepseek", label: "DeepSeek" },
  { id: "gemini", label: "Gemini" },
  { id: "claude", label: "Claude" },
];

const DEFAULT_PROVIDER_BASE_URLS: Record<ProviderConfig["type"], string> = {
  openai: "https://api.openai.com",
  deepseek: "https://api.deepseek.com",
  gemini: "https://generativelanguage.googleapis.com",
  claude: "https://api.anthropic.com",
};

function normalizeBaseUrlForComparison(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

const OFFICIAL_PROVIDER_BASE_URLS = new Set([
  ...Object.values(DEFAULT_PROVIDER_BASE_URLS).map(normalizeBaseUrlForComparison),
  "https://api.openai.com/v1",
  "https://api.deepseek.com/v1",
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

/**
 * 提供 LLM Provider 的主从配置工作台。
 *
 * Args:
 *   config: 当前浏览器中的设置草稿。
 *   onChange: 更新完整设置草稿的回调。
 *   onProviderRename: 记录 Provider 重命名操作的回调。
 *   onSecretEditingChange: 通知设置页是否存在尚未确认的密钥替换输入。
 *
 * Returns:
 *   支持独立滚动、配置编辑与能力测试的 Provider 工作区。
 */
export function ProviderCard({
  config,
  onChange,
  onProviderRename,
  onSecretEditingChange,
}: Props) {
  const t = useTranslations("settings.provider");
  const [newAlias, setNewAlias] = useState("");
  const [aliasError, setAliasError] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [renamingAlias, setRenamingAlias] = useState("");
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState("");
  const [selectedAlias, setSelectedAlias] = useState("");
  const [filter, setFilter] = useState<ProviderFilter>("all");
  const [editingKeyAlias, setEditingKeyAlias] = useState("");
  const [replacementKey, setReplacementKey] = useState("");
  const [replacementKeyError, setReplacementKeyError] = useState("");
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

  useEffect(() => {
    return () => onSecretEditingChange?.(false);
  }, [onSecretEditingChange]);

  useEffect(() => {
    if (!editingKeyAlias || editingKeyAlias === selectedAlias) return;
    setEditingKeyAlias("");
    setReplacementKey("");
    setReplacementKeyError("");
    setShowKey(false);
    onSecretEditingChange?.(false);
  }, [editingKeyAlias, onSecretEditingChange, selectedAlias]);

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

  const startKeyReplacement = (alias: string) => {
    const update = providers[alias]?.api_key_update;
    setEditingKeyAlias(alias);
    setReplacementKey(update?.action === "replace" ? update.value : "");
    setReplacementKeyError("");
    setShowKey(false);
    onSecretEditingChange?.(true);
  };

  const cancelKeyReplacement = () => {
    setEditingKeyAlias("");
    setReplacementKey("");
    setReplacementKeyError("");
    setShowKey(false);
    onSecretEditingChange?.(false);
  };

  const confirmKeyReplacement = (alias: string) => {
    const trimmed = replacementKey.trim();
    if (!trimmed) {
      setReplacementKeyError(t("replacementRequired"));
      return;
    }
    updateProvider(alias, { api_key_update: { action: "replace", value: trimmed } });
    cancelKeyReplacement();
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
    cancelKeyReplacement();
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
    if (editingKeyAlias === alias) {
      cancelKeyReplacement();
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
      const keyUpdate = provider.api_key_update;
      const providerFields = { ...provider } as Partial<ProviderConfig>;
      delete providerFields.api_key;
      delete providerFields.api_key_configured;
      delete providerFields.api_key_update;
      delete providerFields.system_prompt;
      const oneTimeApiKey = keyUpdate.action === "replace" ? keyUpdate.value : "";
      const response = await apiPost<ProviderTestResponse>("/api/config/llm-providers/test", {
        alias,
        provider: { ...providerFields, api_key: oneTimeApiKey },
        use_stored_api_key:
          keyUpdate.action === "preserve" && provider.api_key_configured,
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
    deepseek: t("baseUrlPlaceholderDeepseek"),
    gemini: t("baseUrlPlaceholderGemini"),
    claude: t("baseUrlPlaceholderClaude"),
  };

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden" aria-labelledby="provider-workspace-title">
      <div className="flex shrink-0 flex-col gap-3 border-b border-border px-4 pb-4 sm:flex-row sm:items-end sm:justify-between sm:px-6">
        <h2 id="provider-workspace-title" className="text-lg font-semibold text-foreground">
          {t("title")}
        </h2>
        <div className="flex w-full min-w-0 flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
          <Label className="shrink-0 text-sm font-medium text-muted">{t("defaultProvider")}</Label>
          <Select
            aria-label={t("defaultProvider")}
            selectedKey={defaultProviderOptions.includes(defaultProvider) ? defaultProvider : null}
            onSelectionChange={(key) => {
              if (key) setDefaultProvider(String(key));
            }}
            className="w-full sm:w-72"
          >
            <Select.Trigger className="min-h-11 items-center rounded-xl border border-border bg-background/80 px-3 py-2 text-sm shadow-none hover:border-accent/55 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/15">
              <Select.Value className="min-w-0 truncate leading-5" />
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

      {/* 小屏由整个工作区滚动；桌面端将滚动责任收口到名册和详情。 */}
      <div
        className="workspace-scrollbar grid min-h-0 flex-1 grid-cols-1 overflow-y-auto border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 lg:grid-cols-[minmax(240px,280px)_minmax(0,1fr)] lg:overflow-hidden"
        role="region"
        aria-label={t("title")}
        tabIndex={0}
      >
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
          onSelect={(alias) => {
            cancelKeyReplacement();
            setSelectedAlias(alias);
          }}
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

        <article
          className="workspace-scrollbar min-h-0 min-w-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 lg:overflow-y-auto"
          aria-label={selectedAlias ? `${t("title")} · ${selectedAlias}` : t("title")}
          tabIndex={0}
        >
          {selectedProvider ? (
            <ProviderDetail
              alias={selectedAlias}
              provider={selectedProvider}
              isDefault={selectedAlias === defaultProvider}
              isRenaming={renamingAlias === selectedAlias}
              renameValue={renameValue}
              renameError={renameError}
              isKeyEditing={editingKeyAlias === selectedAlias}
              replacementKey={replacementKey}
              replacementKeyError={replacementKeyError}
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
              onKeyReplacementStart={() => startKeyReplacement(selectedAlias)}
              onKeyReplacementValueChange={(value) => {
                setReplacementKey(value);
                setReplacementKeyError("");
              }}
              onKeyReplacementConfirm={() => confirmKeyReplacement(selectedAlias)}
              onKeyReplacementCancel={cancelKeyReplacement}
              onKeyRestore={() => {
                cancelKeyReplacement();
                updateProvider(selectedAlias, { api_key_update: { action: "preserve" } });
              }}
              onKeyClear={() => {
                cancelKeyReplacement();
                updateProvider(selectedAlias, { api_key_update: { action: "clear" } });
              }}
              onShowKeyChange={setShowKey}
              onShowGenParamsChange={setShowGenParams}
              onRunTest={() => runProviderTest(selectedAlias)}
              t={t}
            />
          ) : (
            <div className="m-4 flex min-h-[360px] items-center justify-center border border-dashed border-border px-5 py-10 text-sm text-muted sm:m-6">
              {t("empty")}
            </div>
          )}
        </article>
      </div>
    </section>
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
    <aside
      className="workspace-scrollbar flex min-h-0 flex-col border-b border-border outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 lg:overflow-y-auto lg:border-b-0 lg:border-r"
      aria-label={t("listTitle")}
      tabIndex={0}
    >
      <div className="flex items-center justify-between gap-3 px-4 pt-5 sm:px-6 lg:px-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{t("listTitle")}</h3>
          <p className="text-xs text-muted">{t("listCount", { count: allAliases.length })}</p>
        </div>
        <Chip size="sm" variant="soft" className="bg-accent/10 text-accent">
          {aliases.length}
        </Chip>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 px-4 sm:px-6 lg:px-4">
        {(["all", "enabled", "needsTest"] as ProviderFilter[]).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onFilterChange(item)}
            className={`min-h-11 rounded-full px-3 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 sm:min-h-10 ${
              filter === item
                ? "bg-accent text-accent-foreground"
                : "border border-border text-muted hover:bg-surface-secondary/55 hover:text-foreground"
            }`}
          >
            {t(`filters.${item}`)}
          </button>
        ))}
      </div>

      <div className="mt-3 flex-1">
        {aliases.length > 0 ? (
          <ul className="divide-y divide-border border-y border-border">
            {aliases.map((alias) => {
              const provider = providers[alias];
              const testState = testStates[alias];
              return (
                <li key={alias}>
                  <button
                    type="button"
                    onClick={() => onSelect(alias)}
                    className={`w-full px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent/30 ${
                      selectedAlias === alias
                        ? "bg-accent/10"
                        : "hover:bg-surface-secondary/55"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-foreground">{alias}</div>
                        <div className="mt-1 truncate text-xs text-muted">
                          {provider.type} · {provider.default_model || t("modelMissing")}
                        </div>
                      </div>
                      {/* 状态同时使用文字标签，避免只靠颜色表达。 */}
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
                </li>
              );
            })}
          </ul>
        ) : (
          <div className="mx-4 border border-dashed border-border px-4 py-6 text-sm text-muted sm:mx-6 lg:mx-4">
            {t("noProviderForFilter")}
          </div>
        )}
      </div>

      <div className="mt-3 border-t border-border px-4 py-4 sm:px-6 lg:px-4">
        {showAddForm ? (
          <div className="space-y-3">
            <TextField value={newAlias} onChange={onNewAliasChange} isInvalid={!!aliasError}>
              <Label className="text-sm text-muted">{t("alias")}</Label>
              <Input placeholder={t("aliasPlaceholder")} className="border-border" />
            </TextField>
            {aliasError && <p className="text-xs text-red-600">{aliasError}</p>}
            <div className="grid grid-cols-2 gap-2">
              <Button onPress={onAddProvider} size="sm" className="bg-accent text-accent-foreground hover:bg-accent-hover">
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
  isKeyEditing,
  replacementKey,
  replacementKeyError,
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
  onKeyReplacementStart,
  onKeyReplacementValueChange,
  onKeyReplacementConfirm,
  onKeyReplacementCancel,
  onKeyRestore,
  onKeyClear,
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
  isKeyEditing: boolean;
  replacementKey: string;
  replacementKeyError: string;
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
  onKeyReplacementStart: () => void;
  onKeyReplacementValueChange: (value: string) => void;
  onKeyReplacementConfirm: () => void;
  onKeyReplacementCancel: () => void;
  onKeyRestore: () => void;
  onKeyClear: () => void;
  onShowKeyChange: (show: boolean) => void;
  onShowGenParamsChange: (show: boolean) => void;
  onRunTest: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const keyUpdate = provider.api_key_update;
  const keyStatusTone = keyUpdate.action === "clear"
    ? "danger"
    : keyUpdate.action === "replace"
      ? "warning"
      : provider.api_key_configured
        ? "accent"
        : "muted";
  const keyStatusLabel = keyUpdate.action === "clear"
    ? t("secretWillClear")
    : keyUpdate.action === "replace"
      ? t("secretWillReplace")
      : provider.api_key_configured
        ? t("secretConfigured")
        : t("secretMissing");
  const keyErrorId = `provider-api-key-error-${alias}`;

  return (
    <div className="@container/provider px-4 sm:px-6">
      <header className="border-b border-border py-5">
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
              isDisabled={testState?.status === "running" || isKeyEditing}
              className="bg-accent text-accent-foreground hover:bg-accent-hover"
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
            <Button size="sm" onPress={onRenameConfirm} className="bg-accent text-accent-foreground hover:bg-accent-hover">
              {t("confirmRename")}
            </Button>
            <Button size="sm" variant="outline" onPress={onRenameCancel} className="border-border text-foreground">
              {t("cancel")}
            </Button>
          </div>
        )}
      </header>

      <div className="grid divide-y divide-border border-b border-border @[840px]/provider:grid-cols-[minmax(0,1fr)_320px] @[840px]/provider:divide-x @[840px]/provider:divide-y-0">
        <section className="py-6 @[840px]/provider:pr-6">
          <SectionTitle title={t("connection.title")} />
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <Select
              selectedKey={provider.type}
              onSelectionChange={(key) => {
                if (!key) return;
                const nextType = String(key) as ProviderConfig["type"];
                // 第三方网关地址通常跨类型复用，只有空值或官方默认地址才随类别切换。
                onChange({
                  type: nextType, api_mode: "auto", structured_output_mode: "auto",
                  reasoning_effort: null, thinking_mode: null, thinking_budget: null, reasoning_mode: null, verbosity: null,
                  base_url: resolveBaseUrlForProviderTypeChange(provider.base_url, nextType),
                });
              }}
            >
              <Label className="text-sm text-muted">{t("type")}</Label>
              <Select.Trigger className="min-h-11 items-center rounded-xl border border-border bg-background/80 px-3 py-2 text-sm shadow-none hover:border-accent/55 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/15">
                <Select.Value className="min-w-0 truncate leading-5" />
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

            {provider.type !== "claude" && <Select selectedKey={provider.api_mode ?? "auto"}
              onSelectionChange={(key) => onChange({ api_mode: String(key) as ProviderConfig["api_mode"] })}>
              <Label className="text-sm text-muted">{t("apiMode")}</Label>
              <Select.Trigger className="min-h-11 rounded-xl border border-border bg-background/80 px-3 py-2 text-sm shadow-none"><Select.Value /></Select.Trigger>
              <Select.Popover><ListBox>
                <ListBoxItem id="auto">{t("apiAuto", { mode: getProviderApiMode({ ...provider, api_mode: "auto" }) })}</ListBoxItem>
                {(provider.type === "gemini" ? ["interactions", "generate_content"] : ["responses", "chat_completions"]).map((mode) => <ListBoxItem key={mode} id={mode}>{mode === "responses" ? "Responses" : mode === "interactions" ? "Interactions" : mode === "chat_completions" ? "Chat Completions" : "Generate Content"}</ListBoxItem>)}
              </ListBox></Select.Popover>
            </Select>}
            {provider.type === "claude" && <Select selectedKey={provider.structured_output_mode ?? "auto"}
              onSelectionChange={(key) => onChange({ structured_output_mode: String(key) as ProviderConfig["structured_output_mode"] })}>
              <Label className="text-sm text-muted">{t("structuredOutputMode")}</Label>
              <Select.Trigger className="min-h-11 rounded-xl border border-border bg-background/80 px-3 py-2 text-sm shadow-none"><Select.Value /></Select.Trigger>
              <Select.Popover><ListBox>
                <ListBoxItem id="auto">{t("nativeSchema")}</ListBoxItem>
                <ListBoxItem id="json_schema">JSON Schema</ListBoxItem>
                <ListBoxItem id="tool_call">{t("legacyToolOutput")}</ListBoxItem>
              </ListBox></Select.Popover>
            </Select>}

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

            <div className="space-y-2 md:col-span-2">
              <div className="flex flex-wrap items-center gap-2">
                <Label className="text-sm text-muted">{t("apiKey")}</Label>
                <StatusChip tone={keyStatusTone}>{keyStatusLabel}</StatusChip>
              </div>
              {isKeyEditing ? (
                <div className="space-y-2">
                  <TextField
                    value={replacementKey}
                    onChange={onKeyReplacementValueChange}
                    isInvalid={Boolean(replacementKeyError)}
                  >
                    <Label className="text-sm text-muted">{t("replacementApiKey")}</Label>
                    <InputGroup
                      fullWidth
                      className="min-h-11 rounded-xl border border-border bg-background/80 shadow-none"
                    >
                      <InputGroup.Input
                        type={showKey ? "text" : "password"}
                        autoComplete="new-password"
                        aria-describedby={replacementKeyError ? keyErrorId : undefined}
                      />
                      <InputGroup.Suffix className="px-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          isIconOnly
                          className="size-9 min-h-9 min-w-9 shrink-0 rounded-lg text-muted hover:bg-surface-secondary hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/30"
                          onPress={() => onShowKeyChange(!showKey)}
                          aria-label={showKey ? t("hideApiKey") : t("showApiKey")}
                          aria-pressed={showKey}
                        >
                          {showKey ? (
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="m3 3 18 18" />
                              <path d="M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                              <path d="M9.9 4.24A9.8 9.8 0 0 1 12 4c6 0 10 8 10 8a18.5 18.5 0 0 1-2.1 3.2" />
                              <path d="M6.6 6.6C3.6 8.6 2 12 2 12s4 8 10 8a9.8 9.8 0 0 0 5.4-1.6" />
                            </svg>
                          ) : (
                            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M2 12s4-8 10-8 10 8 10 8-4 8-10 8S2 12 2 12Z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          )}
                        </Button>
                      </InputGroup.Suffix>
                    </InputGroup>
                  </TextField>
                  {replacementKeyError ? (
                    <p id={keyErrorId} role="alert" className="text-xs leading-5 text-red-700 dark:text-red-300">
                      {replacementKeyError}
                    </p>
                  ) : null}
                  <p className="text-xs leading-5 text-muted">{t("confirmBeforeSave")}</p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="ghost" onPress={onKeyReplacementCancel}>
                      {t("cancel")}
                    </Button>
                    <Button size="sm" variant="primary" onPress={onKeyReplacementConfirm}>
                      {t("confirm")}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onPress={onKeyReplacementStart}
                  >
                    {keyUpdate.action === "replace" ? t("editSecret") : t("replaceSecret")}
                  </Button>
                  {keyUpdate.action !== "preserve" ? (
                    <Button size="sm" variant="ghost" onPress={onKeyRestore}>
                      {t("restoreSecret")}
                    </Button>
                  ) : provider.api_key_configured ? (
                    <Button size="sm" variant="danger-soft" onPress={onKeyClear}>
                      {t("clearSecret")}
                    </Button>
                  ) : null}
                </div>
              )}
            </div>

            {/* 数字配置改为单列，避免步进按钮挤压标签和输入内容。 */}
            <div className="md:col-span-2">
              <NumberField
                value={provider.timeout_seconds}
                onChange={(value) => onChange({ timeout_seconds: Math.max(1, value) })}
                minValue={1}
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
                onChange={(value) => onChange({ max_concurrency: Math.max(1, value) })}
                minValue={1}
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

        <section className="py-6 @[840px]/provider:pl-6">
          <SectionTitle title={t("test.title")} />
          <div className="mt-3 divide-y divide-border border-y border-border">
            {TEST_STEPS.map((step, index) => (
              <TestStepRow
                key={step.capability}
                label={t(
                  step.capability === "json_schema" && provider.type === "deepseek" && getProviderApiMode(provider) !== "responses"
                    ? "test.jsonOutput"
                    : step.labelKey
                )}
                result={testState?.response?.results.find((item) => item.capability === step.capability)}
                isRunning={testState?.status === "running" && testState.activeStep === index}
                isQueued={testState?.status === "running" && testState.activeStep < index}
                wasSent={testState?.status === "running" && testState.activeStep > index}
                t={t}
              />
            ))}
          </div>
          {testState?.status === "done" && testState.response && (
            <div className="mt-3 border-t border-border pt-3">
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

      <section className="border-b border-border py-6">
        <SectionTitle title={t("capabilities.title")} />
        {/* 窄屏两列，空间充足时四项同排，避免单个开关占用整行。 */}
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
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

      <section className="border-b border-border py-6">
        <button
          type="button"
          className="flex min-h-11 w-full items-center justify-between gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
          onClick={() => onShowGenParamsChange(!showGenParams)}
          aria-expanded={showGenParams}
          aria-controls="provider-generation-parameters"
        >
          <SectionTitle title={t("genParams.title")} />
          <span aria-hidden="true" className={`text-muted transition-transform ${showGenParams ? "rotate-90" : ""}`}>›</span>
        </button>
        {showGenParams && (
          <div id="provider-generation-parameters" className="mt-4 space-y-4 border-t border-border pt-4">
            <ReasoningControls value={provider} providerType={provider.type} onChange={onChange} />
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
            <div className="space-y-3 border-t border-border pt-4">
              <TextField
                value={provider.system_prompt ?? ""}
                onChange={(value) => onChange({ system_prompt: value })}
              >
                <Label className="text-sm font-medium text-foreground">
                  {t("genParams.systemPrompt")}
                </Label>
                <TextArea
                  fullWidth
                  rows={5}
                  placeholder={t("genParams.systemPromptPlaceholder")}
                  className="min-h-28 resize-y rounded-xl border border-border bg-background/80 leading-6 shadow-none"
                />
              </TextField>
            </div>
          </div>
        )}
      </section>

      <section className="border-b border-red-200 bg-red-50/60 py-6 dark:border-red-900/70 dark:bg-red-950/20">
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
    <div className="py-3">
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
    <div className="flex min-h-11 min-w-0 items-center rounded-lg border border-border px-2.5 py-2">
      <Switch className="min-w-0" isSelected={selected} onChange={onChange}>
        <Switch.Control>
          <Switch.Thumb />
        </Switch.Control>
        <Switch.Content className="min-w-0 whitespace-nowrap text-xs font-medium">{label}</Switch.Content>
      </Switch>
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <div>
      <h4 className="text-base font-semibold text-foreground">{title}</h4>
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
    success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    warning: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    danger: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
    muted: "bg-surface-secondary text-muted",
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
    success: "bg-emerald-600 text-white",
    warning: "bg-amber-400 text-amber-950",
    danger: "bg-red-600 text-white",
    muted: "bg-surface-secondary text-muted",
  };
  return classes[tone];
}
