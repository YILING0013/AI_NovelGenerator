"use client";

import { ReasoningControls } from "@/components/shared/ReasoningControls";
import type { ReasoningOptions } from "@/types/generation";
import { useTranslations } from "next-intl";
import {
  BooleanParam,
  OptionalNumberParam,
  OptionalSliderParam,
  OptionalTextParam,
} from "@/components/shared/OptionalParamControls";

export interface GenerationParamsValue extends ReasoningOptions {
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  presence_penalty: number | null;
  frequency_penalty: number | null;
  system_prompt: string | null;
  use_stream: boolean;
}

export const DEFAULT_GENERATION_PARAMS: GenerationParamsValue = {
  temperature: null,
  top_p: null,
  max_tokens: null,
  presence_penalty: null,
  frequency_penalty: null,
  system_prompt: null,
  use_stream: true,
};

/**
 * 提取请求级生成参数，过滤未启用的可选项。
 *
 * Args:
 *   value: 前端生成参数控件状态。
 *
 * Returns:
 *   可直接合并进 AI 请求体的窄参数对象。
 */
export function buildGenerationParamsPayload(value: GenerationParamsValue): Partial<GenerationParamsValue> {
  return {
    ...(value.temperature != null && { temperature: value.temperature }),
    ...(value.top_p != null && { top_p: value.top_p }),
    ...(value.max_tokens != null && { max_tokens: value.max_tokens }),
    ...(value.presence_penalty != null && { presence_penalty: value.presence_penalty }),
    ...(value.frequency_penalty != null && { frequency_penalty: value.frequency_penalty }),
    ...(value.system_prompt != null && { system_prompt: value.system_prompt }),
    ...Object.fromEntries(Object.entries(value).filter(([key, item]) => ["reasoning_effort", "thinking_mode", "thinking_budget", "reasoning_mode", "verbosity"].includes(key) && item != null)),
    use_stream: value.use_stream,
  };
}

interface GenerationParamsCollapseProps {
  value: GenerationParamsValue;
  onChange: (value: GenerationParamsValue) => void;
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  maxTokensMaximum?: number;
  disabled?: boolean;
  className?: string;
  panelClassName?: string;
}

/**
 * 渲染可复用的 LLM 请求级生成参数折叠列表。
 *
 * Args:
 *   value: 当前生成参数状态。
 *   onChange: 参数更新回调。
 *   isOpen: 折叠列表是否展开。
 *   onOpenChange: 展开状态更新回调。
 *   maxTokensMaximum: 最大输出 Token 控件的可选上限。
 *   disabled: 是否禁用折叠开关。
 *   className: 外层容器样式。
 *   panelClassName: 展开面板样式。
 *
 * Returns:
 *   生成参数折叠控件 React 节点。
 */
export function GenerationParamsCollapse({
  value,
  onChange,
  isOpen,
  onOpenChange,
  maxTokensMaximum = 1000000,
  disabled = false,
  className = "",
  panelClassName = "",
}: GenerationParamsCollapseProps) {
  const t = useTranslations("create.genParams");

  const updateParam = <K extends keyof GenerationParamsValue>(key: K, nextValue: GenerationParamsValue[K]) => {
    // 统一从一个对象更新，避免复用组件时各页面散落多组参数状态。
    onChange({ ...value, [key]: nextValue });
  };

  return (
    <div className={className}>
      <button
        type="button"
        className="flex items-center gap-2 py-1 text-sm font-medium text-muted transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
        onClick={() => onOpenChange(!isOpen)}
        disabled={disabled}
        aria-expanded={isOpen}
      >
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {t("title")}
      </button>
      {isOpen && (
        <div className={`mt-1 space-y-3 rounded-lg border border-border bg-surface-secondary/30 p-4 ${panelClassName}`}>
          <BooleanParam
            label={t("streamResponse")}
            value={value.use_stream}
            onValueChange={(nextValue) => updateParam("use_stream", nextValue)}
            disabled={disabled}
          />

          <ReasoningControls value={value} onChange={(patch) => onChange({ ...value, ...patch })} disabled={disabled} />
          <OptionalSliderParam
            label={t("temperature")}
            value={value.temperature}
            onToggle={(enabled) => updateParam("temperature", enabled ? 0.7 : null)}
            onValueChange={(nextValue) => updateParam("temperature", nextValue)}
            min={0}
            max={2}
            step={0.05}
          />
          <OptionalSliderParam
            label={t("topP")}
            value={value.top_p}
            onToggle={(enabled) => updateParam("top_p", enabled ? 0.9 : null)}
            onValueChange={(nextValue) => updateParam("top_p", nextValue)}
            min={0}
            max={1}
            step={0.05}
          />
          <OptionalNumberParam
            label={t("maxTokens")}
            value={value.max_tokens}
            onToggle={(enabled) => updateParam("max_tokens", enabled ? 4096 : null)}
            onValueChange={(nextValue) => updateParam("max_tokens", nextValue)}
            min={256}
            max={maxTokensMaximum}
            step={256}
          />
          <OptionalSliderParam
            label={t("presencePenalty")}
            value={value.presence_penalty}
            onToggle={(enabled) => updateParam("presence_penalty", enabled ? 0 : null)}
            onValueChange={(nextValue) => updateParam("presence_penalty", nextValue)}
            min={-2}
            max={2}
            step={0.1}
          />
          <OptionalSliderParam
            label={t("frequencyPenalty")}
            value={value.frequency_penalty}
            onToggle={(enabled) => updateParam("frequency_penalty", enabled ? 0 : null)}
            onValueChange={(nextValue) => updateParam("frequency_penalty", nextValue)}
            min={-2}
            max={2}
            step={0.1}
          />
          <OptionalTextParam
            label={t("systemPrompt")}
            value={value.system_prompt}
            onToggle={(enabled) => updateParam("system_prompt", enabled ? "" : null)}
            onValueChange={(nextValue) => updateParam("system_prompt", nextValue)}
            placeholder={t("systemPromptPlaceholder")}
          />
        </div>
      )}
    </div>
  );
}
