import type { AppConfig } from "@/types/config";

type TFunc = (key: string) => string;

const ALIAS_REGEX = /^[a-zA-Z0-9_]+$/;

export function validateConfig(config: AppConfig, t: TFunc): string | null {
  // Database fields
  if (!config.mongodb_url?.trim()) {
    return t("database.required") + ": mongodb_url";
  }
  if (!config.mongo_database_name?.trim()) {
    return t("database.required") + ": mongo_database_name";
  }
  if (config.mongo_timeout_ms < 0) {
    return t("database.nonNegative") + ": mongo_timeout_ms";
  }

  const providerAliases = Object.keys(config.llm?.providers || {});

  // LLM default_provider must exist
  if (config.llm?.default_provider && !providerAliases.includes(config.llm.default_provider)) {
    return t("provider.mustExist");
  }

  // Provider alias validation
  for (const alias of providerAliases) {
    if (!ALIAS_REGEX.test(alias)) {
      return t("provider.aliasRule") + `: ${alias}`;
    }
    const p = config.llm.providers[alias];
    if (p.timeout_seconds < 0 || p.max_retries < 0 || p.max_concurrency < 0) {
      return t("database.nonNegative") + `: ${alias}`;
    }
  }

  // Workflow validation
  const workflows = config.llm?.workflows;
  if (workflows) {
    for (const [, wf] of Object.entries(workflows)) {
      if (wf.default_provider && !providerAliases.includes(wf.default_provider)) {
        return t("workflow.providerNotExist") + `: ${wf.default_provider}`;
      }
      if (wf.steps) {
        for (const [stepName, step] of Object.entries(wf.steps)) {
          if (step.provider && !providerAliases.includes(step.provider)) {
            return t("workflow.providerNotExist") + `: ${stepName} → ${step.provider}`;
          }
        }
      }
    }
  }

  return null;
}
