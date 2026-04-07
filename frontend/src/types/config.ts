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

export interface WorkflowStep {
  provider: string;
}

export interface WorkflowConfig {
  default_provider: string;
  steps: Record<string, WorkflowStep>;
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

export const WORKFLOW_STEPS = [
  "expand_idea_to_full_novel_story",
  "extract_idea",
  "core_seed",
  "novel_meta",
] as const;

export function normalizeAppConfig(config: AppConfig): AppConfig {
  const providers = Object.fromEntries(
    Object.entries(config.llm?.providers || {}).map(([alias, provider]) => [
      alias,
      { ...newProviderConfig(), ...provider },
    ])
  );

  const workflows = config.llm?.workflows;
  const createNovelWorkflow = workflows?.create_novel_by_ai;

  return {
    ...config,
    llm: {
      ...config.llm,
      providers,
      workflows: createNovelWorkflow
        ? {
            ...workflows,
            create_novel_by_ai: {
              ...createNovelWorkflow,
              steps: {
                ...Object.fromEntries(WORKFLOW_STEPS.map((step) => [step, { provider: "" }])),
                ...createNovelWorkflow.steps,
              },
            },
          }
        : workflows,
    },
  };
}
