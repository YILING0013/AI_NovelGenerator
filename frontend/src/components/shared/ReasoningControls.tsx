"use client";

import { Label, ListBox, ListBoxItem, Select } from "@heroui/react";
import { useTranslations } from "next-intl";
import { OptionalNumberParam } from "@/components/shared/OptionalParamControls";
import type { ReasoningOptions } from "@/types/generation";
import type { ProviderConfig } from "@/types/config";

/** 编辑各入口共用的思考参数。Args: value 当前值；onChange 局部更新；providerType 已知服务类别；apiMode 实际接口；disabled 禁用状态。Returns: 未设置时沿用上级配置的控件。 */
export function ReasoningControls({ value, onChange, providerType, apiMode, disabled = false }: {
  value: ReasoningOptions;
  onChange: (patch: ReasoningOptions) => void;
  providerType?: ProviderConfig["type"];
  apiMode?: string;
  disabled?: boolean;
}) {
  const t = useTranslations("reasoning");
  const fields: { key: Exclude<keyof ReasoningOptions, "thinking_budget">; options: string[] }[] = [
    { key: "reasoning_effort", options: providerType === "gemini" ? ["minimal", "low", "medium", "high"] : providerType === "claude" ? ["low", "medium", "high", "xhigh", "max"] : providerType === "deepseek" ? ["none", "low", "high", "max"] : ["none", "minimal", "low", "medium", "high", "xhigh", "max"] },
    ...(!providerType || providerType === "deepseek" || providerType === "claude" ? [{ key: "thinking_mode" as const, options: providerType === "deepseek" ? ["enabled", "disabled"] : ["enabled", "disabled", "adaptive", "between_tools"] }] : []),
    ...(!providerType || providerType === "openai" ? [
      ...(apiMode !== "chat_completions" || value.reasoning_mode ? [{ key: "reasoning_mode" as const, options: ["standard", "pro"] }] : []),
      { key: "verbosity" as const, options: ["low", "medium", "high"] },
    ] : []),
  ];
  return <fieldset disabled={disabled} className="min-w-0 space-y-3">
    <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
      {fields.map(({ key, options }) => <Select key={key} selectedKey={value[key] ?? "inherit"} isDisabled={disabled}
        onSelectionChange={(selected) => onChange({ [key]: selected === "inherit" ? null : selected })}>
        <Label className="text-sm text-muted">{t(!providerType && key !== "reasoning_effort" ? `${key}_generic` : key)}</Label>
        <Select.Trigger className="min-h-11 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3 py-2 text-sm shadow-none">
          <Select.Value className="min-w-0 truncate" />
        </Select.Trigger>
        <Select.Popover><ListBox>
          <ListBoxItem id="inherit">{t("inherit")}</ListBoxItem>
          {[...new Set([...options, ...(value[key] ? [value[key]] : [])])].map((option) => <ListBoxItem key={option} id={option}>{t(`values.${option}`)}</ListBoxItem>)}
        </ListBox></Select.Popover>
      </Select>)}
    </div>
    {(!providerType || providerType === "claude" || (providerType === "gemini" && (apiMode !== "interactions" || value.thinking_budget != null))) && <OptionalNumberParam
      label={t("thinking_budget")} value={value.thinking_budget} min={-1} max={1000000} step={1}
      onToggle={(enabled) => onChange({ thinking_budget: enabled ? 2048 : null })}
      onValueChange={(thinking_budget) => onChange({ thinking_budget })} />}
    {providerType && apiMode && <details className="text-xs text-muted">
      <summary className="cursor-pointer py-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30">{t("protocolHelpTitle", { mode: apiMode })}</summary>
      <p className="mt-2 leading-5">{t(`protocolHelp.${providerType === "gemini" ? apiMode : providerType}`)}</p>
      <a className="mt-2 inline-block text-accent underline underline-offset-2" target="_blank" rel="noreferrer"
        href={{ openai: "https://developers.openai.com/api/docs/guides/reasoning", claude: "https://platform.claude.com/docs/en/build-with-claude/thinking", gemini: "https://ai.google.dev/gemini-api/docs/thinking", deepseek: "https://api-docs.deepseek.com/guides/thinking_mode/" }[providerType]}>{t("officialDocs")}</a>
    </details>}
  </fieldset>;
}
