export interface ProviderConfig {
  type: "openai" | "gemini" | "claude";
  base_url: string;
  api_key: string;
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
  system_prompt?: string | null;
  presence_penalty?: number | null;
  frequency_penalty?: number | null;
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

export interface WorkflowStep {
  provider: string;
  timeout_seconds?: number | null;
}

export interface WorkflowConfig {
  default_provider: string;
  steps: Record<string, WorkflowStep>;
}

export interface WorkflowDefinition {
  name: string;
  steps: readonly string[];
}

export interface ProviderRenameOperation {
  from: string;
  to: string;
}

export interface LLMConfig {
  default_provider: string;
  format_review_provider?: string;
  providers: Record<string, ProviderConfig>;
  workflows?: Record<string, WorkflowConfig>;
}

export interface AppConfig {
  mongodb_url: string;
  mongo_database_name: string;
  mongo_timeout_ms: number;
  llm: LLMConfig;
  [key: string]: unknown;
}

export type AppConfigSavePayload = AppConfig & {
  _provider_renames?: ProviderRenameOperation[];
};

export function newProviderConfig(): ProviderConfig {
  return {
    type: "openai",
    base_url: "",
    api_key: "",
    default_model: "",
    enabled: false,
    timeout_seconds: 60,
    max_retries: 2,
    max_concurrency: 5,
    use_system_proxy: false,
    supports_streaming: true,
    supports_json_schema: false,
    supports_function_calling: false,
    temperature: null,
    top_p: null,
    max_tokens: null,
    system_prompt: null,
    presence_penalty: null,
    frequency_penalty: null,
  };
}

function mapWorkflowProviderAliases(
  workflows: AppConfig["llm"]["workflows"] | undefined,
  mapAlias: (alias: string) => string
): AppConfig["llm"]["workflows"] | undefined {
  if (!workflows) {
    return workflows;
  }

  return Object.fromEntries(
    Object.entries(workflows).map(([workflowName, workflowConfig]) => [
      workflowName,
      {
        ...workflowConfig,
        default_provider: mapAlias(workflowConfig.default_provider),
        steps: Object.fromEntries(
          Object.entries(workflowConfig.steps || {}).map(([stepName, stepConfig]) => [
            stepName,
            {
              ...stepConfig,
              provider: mapAlias(stepConfig.provider),
            },
          ])
        ),
      },
    ])
  ) as AppConfig["llm"]["workflows"];
}

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
      workflows: mapWorkflowProviderAliases(config.llm.workflows, mapAlias),
    },
  };
}

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
      workflows: mapWorkflowProviderAliases(config.llm.workflows, mapAlias),
    },
  };
}

export const CREATE_NOVEL_WORKFLOW_NAME = "create_novel_by_ai";
export const CREATE_FACTIONS_WORKFLOW_NAME = "create_factions_by_ai";

export const CREATE_NOVEL_WORKFLOW_STEPS = [
  "expand_idea_to_full_novel_story",
  "extract_idea",
  "core_seed",
  "novel_meta",
] as const;

export const CREATE_FACTIONS_WORKFLOW_STEPS = [
  "create_core_factions",
] as const;

export const WORKFLOW_STEPS = CREATE_NOVEL_WORKFLOW_STEPS;

export const WORKFLOW_DEFINITIONS: readonly WorkflowDefinition[] = [
  {
    name: CREATE_NOVEL_WORKFLOW_NAME,
    steps: CREATE_NOVEL_WORKFLOW_STEPS,
  },
  {
    name: CREATE_FACTIONS_WORKFLOW_NAME,
    steps: CREATE_FACTIONS_WORKFLOW_STEPS,
  },
] as const;

function normalizeStepTimeout(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }

  return Math.floor(parsed);
}

/**
 * 生成单个流程步骤配置。
 *
 * Args:
 *   step: 可选的已有步骤配置。
 *
 * Returns:
 *   已归一化 Provider 与超时字段的步骤配置。
 */
export function newWorkflowStepConfig(step?: Partial<WorkflowStep>): WorkflowStep {
  return {
    provider: step?.provider || "",
    timeout_seconds: normalizeStepTimeout(step?.timeout_seconds),
  };
}

function getWorkflowDefinition(workflowName: string): WorkflowDefinition | undefined {
  return WORKFLOW_DEFINITIONS.find((workflow) => workflow.name === workflowName);
}

/**
 * 返回流程步骤列表；已知流程只允许程序内置步骤，未知流程兼容读取旧配置。
 *
 * Args:
 *   workflowName: 流程名称。
 *   workflow: 当前流程配置。
 *
 * Returns:
 *   去重后的步骤名称列表，模板步骤优先。
 */
export function getWorkflowStepNames(
  workflowName: string,
  workflow?: WorkflowConfig
): string[] {
  const templateSteps = getWorkflowDefinition(workflowName)?.steps ?? [];
  if (templateSteps.length > 0) {
    return [...templateSteps];
  }

  const configuredSteps = Object.keys(workflow?.steps || {});
  return configuredSteps;
}

/**
 * 生成流程配置，已知流程会自动补齐模板步骤。
 *
 * Args:
 *   workflowName: 流程名称。
 *   defaultProvider: 流程默认 Provider。
 *   workflow: 可选的已有流程配置。
 *
 * Returns:
 *   可直接保存到配置文件的流程配置。
 */
export function newWorkflowConfig(
  workflowName: string,
  defaultProvider = "",
  workflow?: Partial<WorkflowConfig>
): WorkflowConfig {
  const stepNames = getWorkflowStepNames(workflowName, workflow as WorkflowConfig | undefined);
  const steps = Object.fromEntries(
    stepNames.map((stepName) => [
      stepName,
      newWorkflowStepConfig(workflow?.steps?.[stepName]),
    ])
  );

  return {
    default_provider: workflow?.default_provider || defaultProvider,
    steps,
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
    Object.entries(config.llm?.providers || {}).map(([alias, provider]) => [
      alias,
      { ...newProviderConfig(), ...provider },
    ])
  );

  const workflows = Object.fromEntries(
    WORKFLOW_DEFINITIONS.map((workflow) => [
      workflow.name,
      newWorkflowConfig(
        workflow.name,
        config.llm?.default_provider || "",
        config.llm?.workflows?.[workflow.name]
      ),
    ])
  );

  return {
    ...config,
    llm: {
      ...config.llm,
      providers,
      workflows,
    },
  };
}
