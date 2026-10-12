import { REASONING_FIELDS, type ReasoningOptions } from "@/types/generation";

export interface ProviderConfig extends ReasoningOptions {
  api_mode?: "auto" | "responses" | "chat_completions" | "interactions" | "generate_content";
  structured_output_mode?: "auto" | "json_schema" | "tool_call";
  type: "openai" | "deepseek" | "gemini" | "claude";
  base_url: string;
  /** 服务端读取模型永不返回已保存密钥明文。 */
  api_key: null;
  api_key_configured: boolean;
  api_key_update: SecretUpdate;
  default_model: string;
  enabled: boolean;
  timeout_seconds: number;
  max_retries: number;
  max_concurrency: number;
  use_system_proxy: boolean;
  supports_streaming: boolean;
  supports_json_schema: boolean;
  supports_function_calling: boolean;
  // 生成参数默认值（可选）
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  /** 系统 Prompt 不是敏感字段，由配置接口直接读取和保存。 */
  system_prompt: string | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
}

/**
 * 判断配置是否选择了 DeepSeek 适配。
 *
 * Args:
 *   provider: 当前 Provider 配置。
 * Returns:
 *   明确选择 DeepSeek 类型时返回 true，与 API 地址无关。
 */
export function isDeepSeekProvider(provider: ProviderConfig): boolean {
  return provider.type === "deepseek";
}

/** 选择实际接口。Args: provider 当前配置。Returns: 官方地址用新版，自定义地址保留兼容接口。 */
export function getProviderApiMode(provider: ProviderConfig): string {
  if (provider.type === "claude") return "messages";
  if (provider.api_mode && provider.api_mode !== "auto") return provider.api_mode;
  const officialHosts = { openai: "api.openai.com", deepseek: "api.deepseek.com", gemini: "generativelanguage.googleapis.com" };
  let official = !provider.base_url.trim();
  if (!official) {
    try { official = new URL(provider.base_url).hostname === officialHosts[provider.type]; }
    catch { official = false; }
  }
  return provider.type === "gemini" ? (official ? "interactions" : "generate_content") : (official ? "responses" : "chat_completions");
}

export type ProviderTestCapability =
  | "connection"
  | "streaming"
  | "json_schema"
  | "function_calling";

export type ProviderTestStatus = "passed" | "failed" | "skipped";

export interface ProviderCapabilityResult {
  capability: ProviderTestCapability;
  label: string;
  status: ProviderTestStatus;
  duration_ms: number;
  message: string;
}

export interface ProviderCapabilityRecommendation {
  supports_streaming: boolean;
  supports_json_schema: boolean;
  supports_function_calling: boolean;
}

export interface ProviderTestResponse {
  alias: string;
  provider_type: string;
  model: string;
  summary: string;
  results: ProviderCapabilityResult[];
  recommendations: ProviderCapabilityRecommendation;
}

export interface ProviderRenameOperation {
  from: string;
  to: string;
}

export interface LLMConfig {
  default_provider: string;
  format_review_provider?: string;
  providers: Record<string, ProviderConfig>;
}

export interface AppConfig {
  config_version: number;
  mongodb_url_configured: boolean;
  mongodb_url_update: SecretUpdate;
  mongo_database_name: string;
  mongo_timeout_ms: number;
  mongo_transaction_mode?: "auto" | "required" | "disabled";
  llm: LLMConfig;
  [key: string]: unknown;
}

export type SecretUpdate =
  | { action: "preserve" }
  | { action: "clear" }
  | { action: "replace"; value: string };

export type ProviderConfigPatch = Partial<Omit<
  ProviderConfig,
  "api_key" | "api_key_configured"
>>;

export interface AppConfigPatch {
  mongodb_url_update?: SecretUpdate;
  mongo_database_name?: string;
  mongo_timeout_ms?: number;
  mongo_transaction_mode?: "auto" | "required" | "disabled";
  llm?: {
    default_provider?: string;
    format_review_provider?: string;
    providers?: Record<string, ProviderConfigPatch>;
  };
  _provider_renames?: ProviderRenameOperation[];
}

export interface AppConfigSavePayload {
  expected_config_version: number;
  patch: AppConfigPatch;
}

export function newProviderConfig(): ProviderConfig {
  return {
    type: "openai",
    base_url: "",
    api_key: null,
    api_key_configured: false,
    api_key_update: { action: "preserve" },
    default_model: "",
    enabled: false,
    timeout_seconds: 60,
    max_retries: 2,
    max_concurrency: 5,
    use_system_proxy: false,
    supports_streaming: true,
    supports_json_schema: false,
    supports_function_calling: false,
    api_mode: "auto",
    structured_output_mode: "auto",
    temperature: null,
    top_p: null,
    max_tokens: null,
    system_prompt: null,
    presence_penalty: null,
    frequency_penalty: null,
  };
}

/**
 * 功能：只提交作者相对读取版本改动的合法配置字段。
 * Args:
 *   config: 当前设置草稿；密钥只保存状态和显式动作，系统 Prompt 直接保存。
 *   original: 最近成功读取或保存的配置，固定本次比较和 CAS 版本。
 *   providerRenames: 本次会话尚未提交的 Provider 重命名操作。
 * Returns:
 *   不含旧配置扩展键或读取占位字段的载荷；无改动时 patch 为空。
 */
export function buildConfigSavePayload(
  config: AppConfig,
  original: AppConfig,
  providerRenames: ProviderRenameOperation[] = []
): AppConfigSavePayload {
  const patch: AppConfigPatch = {};
  if (config.mongodb_url_update.action !== "preserve") patch.mongodb_url_update = config.mongodb_url_update;
  if (config.mongo_database_name !== original.mongo_database_name) patch.mongo_database_name = config.mongo_database_name;
  if (config.mongo_timeout_ms !== original.mongo_timeout_ms) patch.mongo_timeout_ms = config.mongo_timeout_ms;
  if (config.mongo_transaction_mode !== undefined && config.mongo_transaction_mode !== original.mongo_transaction_mode) {
    patch.mongo_transaction_mode = config.mongo_transaction_mode;
  }

  const llm: NonNullable<AppConfigPatch["llm"]> = {};
  if (config.llm.default_provider !== original.llm.default_provider) llm.default_provider = config.llm.default_provider;
  if (config.llm.format_review_provider !== undefined && config.llm.format_review_provider !== original.llm.format_review_provider) {
    llm.format_review_provider = config.llm.format_review_provider;
  }
  const previousProviders = { ...original.llm.providers };
  for (const { from, to } of providerRenames) {
    if (from !== to && from in previousProviders) {
      previousProviders[to] = previousProviders[from];
      delete previousProviders[from];
    }
  }
  let providersChanged = Object.keys(previousProviders).some((alias) => !(alias in config.llm.providers));
  const providers = Object.fromEntries(
    Object.entries(config.llm.providers).map(([alias, provider]) => {
      const previous = previousProviders[alias];
      const fields = [
        "type", "api_mode", "structured_output_mode", "base_url", "default_model", "enabled",
        "timeout_seconds", "max_retries", "max_concurrency", "use_system_proxy", "supports_streaming",
        "supports_json_schema", "supports_function_calling", "temperature", "top_p", "max_tokens",
        "system_prompt", "presence_penalty", "frequency_penalty", ...REASONING_FIELDS,
      ] as const;
      const providerPatch: ProviderConfigPatch = Object.fromEntries(fields.flatMap((field) => {
        // 输入保持原样；仅比较和提交时把空白 Prompt 归一为空值。
        const value = field === "system_prompt" ? (provider.system_prompt?.trim() ? provider.system_prompt : null) : provider[field];
        const before = field === "system_prompt" ? (previous?.system_prompt?.trim() ? previous.system_prompt : null) : previous?.[field];
        return value !== undefined && (!previous || value !== before) ? [[field, value]] : [];
      }));
      if (provider.api_key_update.action !== "preserve") providerPatch.api_key_update = provider.api_key_update;
      if (!previous || Object.keys(providerPatch).length > 0) providersChanged = true;
      return [alias, providerPatch];
    })
  );
  // 后端沿用整个别名集合的删除语义；未修改的 Provider 传空对象，由服务端保留原设置。
  if (providersChanged) llm.providers = providers;
  if (Object.keys(llm).length > 0) patch.llm = llm;
  if (providerRenames.length > 0) patch._provider_renames = providerRenames;

  return {
    expected_config_version: original.config_version,
    patch,
  };
}

/**
 * 功能：重命名 Provider，并同步更新所有引用该别名的配置字段。
 * Args:
 *   config: 当前设置草稿。
 *   currentAlias: 待替换的 Provider 别名。
 *   nextAlias: 新 Provider 别名。
 * Returns:
 *   Provider 与全部关联引用均已更新的新配置；无需变更时返回原配置。
 */
export function renameProviderAlias(
  config: AppConfig,
  currentAlias: string,
  nextAlias: string
): AppConfig {
  if (!(currentAlias in config.llm.providers) || currentAlias === nextAlias) {
    return config;
  }

  const providers = Object.fromEntries(
    Object.entries(config.llm.providers).map(([alias, provider]) => [
      alias === currentAlias ? nextAlias : alias,
      provider,
    ])
  ) as Record<string, ProviderConfig>;

  const mapAlias = (alias: string) =>
    alias === currentAlias ? nextAlias : alias;

  return {
    ...config,
    llm: {
      ...config.llm,
      providers,
      default_provider: mapAlias(config.llm.default_provider),
      format_review_provider: mapAlias(config.llm.format_review_provider || ""),
    },
  };
}

/**
 * 功能：删除 Provider，并清空全局与审校中的对应引用。
 * Args:
 *   config: 当前设置草稿。
 *   aliasToRemove: 要删除的 Provider 别名。
 * Returns:
 *   已移除 Provider 且不存在悬空引用的新配置；别名不存在时返回原配置。
 */
export function removeProviderAlias(config: AppConfig, aliasToRemove: string): AppConfig {
  if (!(aliasToRemove in config.llm.providers)) {
    return config;
  }

  const providers = { ...config.llm.providers };
  delete providers[aliasToRemove];
  const mapAlias = (alias: string) => (alias === aliasToRemove ? "" : alias);

  return {
    ...config,
    llm: {
      ...config.llm,
      providers,
      default_provider: mapAlias(config.llm.default_provider),
      format_review_provider: mapAlias(config.llm.format_review_provider || ""),
    },
  };
}

interface ProviderSelectionOptions {
  requireJsonSchema?: boolean;
}

export function isProviderSelectable(
  providers: Record<string, ProviderConfig>,
  alias: string,
  options: ProviderSelectionOptions = {}
): boolean {
  const provider = providers[alias];
  if (!provider?.enabled) {
    return false;
  }
  if (options.requireJsonSchema && !provider.supports_json_schema) {
    return false;
  }
  return true;
}

export function getProviderAliasesForSelection(
  providers: Record<string, ProviderConfig>,
  currentAlias = "",
  options: ProviderSelectionOptions = {}
): string[] {
  const aliases = Object.keys(providers).filter((alias) =>
    isProviderSelectable(providers, alias, options)
  );

  if (
    currentAlias &&
    currentAlias in providers &&
    !aliases.includes(currentAlias)
  ) {
    return [currentAlias, ...aliases];
  }

  return aliases;
}

export function normalizeAppConfig(config: AppConfig): AppConfig {
  const providers = Object.fromEntries(
    Object.entries(config.llm.providers).map(([alias, provider]) => [
      alias,
      {
        ...provider,
        api_key: null,
        api_key_update: { action: "preserve" } as SecretUpdate,
      },
    ])
  );

  return {
    ...config,
    mongodb_url_configured: Boolean(config.mongodb_url_configured),
    mongodb_url_update: { action: "preserve" },
    llm: {
      ...config.llm,
      providers,
    },
  };
}
