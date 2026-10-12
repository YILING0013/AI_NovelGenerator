import type { AppConfig } from "@/types/config";

type TFunc = (key: string) => string;

const ALIAS_REGEX = /^[a-zA-Z0-9_]+$/;

export function validateConfig(config: AppConfig, t: TFunc): string | null {
  // Database fields
  if (
    config.mongodb_url_update.action === "replace" &&
    !config.mongodb_url_update.value.trim()
  ) {
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
  if (
    config.llm?.format_review_provider &&
    !providerAliases.includes(config.llm.format_review_provider)
  ) {
    return t("validation.providerNotExist") + `: ${config.llm.format_review_provider}`;
  }

  // Provider alias validation
  for (const alias of providerAliases) {
    if (!ALIAS_REGEX.test(alias)) {
      return t("provider.aliasRule") + `: ${alias}`;
    }
    const p = config.llm.providers[alias];
    if (p.api_key_update.action === "replace" && !p.api_key_update.value.trim()) {
      return t("provider.replacementRequired") + `: ${alias}`;
    }
    if (p.timeout_seconds <= 0 || p.max_concurrency <= 0) {
      return t("provider.positiveRequired") + `: ${alias}`;
    }
    if (p.max_retries < 0) {
      return t("database.nonNegative") + `: ${alias}`;
    }
  }

  return null;
}
