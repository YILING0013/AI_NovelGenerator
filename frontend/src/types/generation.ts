/** Provider 默认值、单次生成和任务节点共用的思考参数。 */
export interface ReasoningOptions {
  reasoning_effort?: "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | null;
  thinking_mode?: "enabled" | "disabled" | "adaptive" | "between_tools" | null;
  thinking_budget?: number | null;
  reasoning_mode?: "standard" | "pro" | null;
  verbosity?: "low" | "medium" | "high" | null;
}

export const REASONING_FIELDS = ["reasoning_effort", "thinking_mode", "thinking_budget", "reasoning_mode", "verbosity"] as const;

/** 检查候选中保存的可选思考参数。Args: value 候选输入。Returns: 新旧输入均可接受，非法参数返回 false。 */
export function hasValidReasoningOptions(value: Record<string, unknown>): boolean {
  return (value.reasoning_effort == null || ["none", "minimal", "low", "medium", "high", "xhigh", "max"].includes(String(value.reasoning_effort)))
    && (value.thinking_mode == null || ["enabled", "disabled", "adaptive", "between_tools"].includes(String(value.thinking_mode)))
    && (value.thinking_budget == null || (Number.isInteger(value.thinking_budget) && Number(value.thinking_budget) >= -1))
    && (value.reasoning_mode == null || ["standard", "pro"].includes(String(value.reasoning_mode)))
    && (value.verbosity == null || ["low", "medium", "high"].includes(String(value.verbosity)));
}
