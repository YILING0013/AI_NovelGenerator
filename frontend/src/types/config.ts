export interface ProviderConfig {
  type: "openai" | "gemini" | "claude";
  base_url: string;
  api_key: string;
  default_model: string;
  enabled: boolean;
  timeout_seconds: number;
  max_retries: number;
  max_concurrency: number;
  supports_streaming: boolean;
  supports_json_schema: boolean;
  supports_function_calling: boolean;
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
    supports_streaming: true,
    supports_json_schema: false,
    supports_function_calling: false,
  };
}

export const WORKFLOW_STEPS = ["extract_idea", "core_seed", "novel_meta"] as const;
