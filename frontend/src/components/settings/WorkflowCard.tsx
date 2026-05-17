"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  Card,
  Select,
  ListBox,
  ListBoxItem,
  Label,
  Chip,
} from "@heroui/react";
import type { AppConfig, WorkflowConfig, WorkflowStep } from "@/types/config";
import {
  CREATE_NOVEL_WORKFLOW_NAME,
  WORKFLOW_DEFINITIONS,
  getProviderAliasesForSelection,
  getWorkflowStepNames,
  isProviderSelectable,
  newWorkflowConfig,
  newWorkflowStepConfig,
} from "@/types/config";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
}

const GLOBAL_DEFAULT_KEY = "__global_default__";
const INHERIT_WORKFLOW_KEY = "__inherit_workflow__";

/**
 * 渲染小说生成流程配置界面，支持按流程名称独立指定步骤 Provider。
 *
 * Args:
 *   config: 当前应用配置。
 *   onChange: 配置变更回调。
 *
 * Returns:
 *   流程 Provider 管理卡片。
 */
export function WorkflowCard({ config, onChange }: Props) {
  const t = useTranslations("settings.workflow");
  const tSteps = useTranslations("settings.workflow.steps");

  const providers = config.llm?.providers || {};
  const providerAliases = Object.keys(providers);
  const workflows = config.llm?.workflows || {};
  const workflowNames = WORKFLOW_DEFINITIONS.map((workflow) => workflow.name);
  const [selectedWorkflowName, setSelectedWorkflowName] = useState(
    CREATE_NOVEL_WORKFLOW_NAME
  );

  const effectiveSelectedWorkflowName = workflowNames.includes(selectedWorkflowName)
    ? selectedWorkflowName
    : CREATE_NOVEL_WORKFLOW_NAME;

  const selectedWorkflow: WorkflowConfig = workflows[effectiveSelectedWorkflowName] || newWorkflowConfig(
    effectiveSelectedWorkflowName,
    config.llm?.default_provider || ""
  );
  const stepNames = getWorkflowStepNames(effectiveSelectedWorkflowName, selectedWorkflow);
  const overriddenSteps = stepNames.filter((stepName) =>
    Boolean(selectedWorkflow.steps?.[stepName]?.provider)
  );
  const formatReviewProvider = config.llm?.format_review_provider || "";
  const workflowDefaultOptions = getProviderAliasesForSelection(
    providers,
    selectedWorkflow.default_provider
  );
  const formatReviewOptions = getProviderAliasesForSelection(
    providers,
    formatReviewProvider,
    { requireJsonSchema: true }
  );

  const setWorkflows = (nextWorkflows: Record<string, WorkflowConfig>) => {
    onChange({
      ...config,
      llm: {
        ...config.llm,
        workflows: nextWorkflows,
      },
    });
  };

  const updateSelectedWorkflow = (updates: Partial<WorkflowConfig>) => {
    setWorkflows({
      ...workflows,
      [effectiveSelectedWorkflowName]: {
        ...selectedWorkflow,
        ...updates,
      },
    });
  };

  const updateStep = (stepName: string, updates: Partial<WorkflowStep>) => {
    const currentStep = selectedWorkflow.steps?.[stepName] || newWorkflowStepConfig();
    updateSelectedWorkflow({
      steps: {
        ...selectedWorkflow.steps,
        [stepName]: { ...currentStep, ...updates },
      },
    });
  };

  const updateFormatReviewProvider = (provider: string) => {
    onChange({
      ...config,
      llm: {
        ...config.llm,
        format_review_provider: provider,
      },
    });
  };

  const getProviderWarning = (providerAlias: string): string | null => {
    if (!providerAlias) return null;
    if (!providerAliases.includes(providerAlias)) return t("providerNotExist");
    if (!providers[providerAlias]?.enabled) return t("providerDisabled");
    return null;
  };

  const providerStatusTone = (providerAlias: string) => {
    if (!providerAlias || !providerAliases.includes(providerAlias)) return "muted";
    return providers[providerAlias]?.enabled ? "success" : "warning";
  };

  const providerStatusText = (providerAlias: string) => {
    if (!providerAlias) return t("globalDefault");
    if (!providerAliases.includes(providerAlias)) return t("providerNotExist");
    return providers[providerAlias]?.enabled ? t("providerEnabled") : t("providerDisabledShort");
  };
  const workflowModuleLabel =
    effectiveSelectedWorkflowName === CREATE_NOVEL_WORKFLOW_NAME
      ? t("novelWorkflowReady")
      : t("factionsWorkflowReady");

  return (
    <Card className="border border-border bg-surface shadow-sm">
      <Card.Header className="flex-col items-start gap-2">
        <Card.Title className="text-lg font-semibold text-foreground">{t("title")}</Card.Title>
        <p className="max-w-3xl text-sm leading-6 text-muted">{t("description")}</p>
      </Card.Header>
      <Card.Content className="space-y-5">
        <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="rounded-lg border border-border bg-background/60 p-3">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-foreground">{t("workflowList")}</div>
                <div className="text-xs text-muted">{t("workflowListHint")}</div>
              </div>
              <Chip size="sm" variant="soft" className="bg-warm-200 text-foreground">
                {workflowNames.length}
              </Chip>
            </div>

            <div className="space-y-1">
              {workflowNames.map((workflowName) => {
                const workflow = workflows[workflowName];
                const count = getWorkflowStepNames(workflowName, workflow).length;
                const isSelected = effectiveSelectedWorkflowName === workflowName;
                return (
                  <button
                    key={workflowName}
                    onClick={() => setSelectedWorkflowName(workflowName)}
                    className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                      isSelected
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-transparent text-foreground hover:border-border hover:bg-surface-secondary"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{workflowName}</span>
                      <span className="shrink-0 text-xs text-muted">{t("stepCount", { count })}</span>
                    </div>
                    <div className="mt-1 truncate text-xs text-muted">
                      {workflow.default_provider || t("globalDefault")}
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="min-w-0 rounded-lg border border-border bg-background/60">
            <div className="border-b border-border px-4 py-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-muted">
                    {t("selectedWorkflow")}
                  </div>
                  <h3 className="mt-1 text-base font-semibold text-foreground">{effectiveSelectedWorkflowName}</h3>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-muted">
                  <span className="rounded-md border border-border bg-surface px-2 py-1">
                    {t("stepCount", { count: stepNames.length })}
                  </span>
                  <span className="rounded-md border border-border bg-surface px-2 py-1">
                    {t("overrideCount", { count: overriddenSteps.length })}
                  </span>
                  <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-amber-700">
                    {workflowModuleLabel}
                  </span>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <Select
                  selectedKey={
                    selectedWorkflow.default_provider &&
                    workflowDefaultOptions.includes(selectedWorkflow.default_provider)
                      ? selectedWorkflow.default_provider
                      : GLOBAL_DEFAULT_KEY
                  }
                  onSelectionChange={(key) => {
                    updateSelectedWorkflow({
                      default_provider: key && String(key) !== GLOBAL_DEFAULT_KEY ? String(key) : "",
                    });
                  }}
                >
                  <Label className="text-xs text-muted">{t("defaultProvider")}</Label>
                  <Select.Trigger className="rounded-lg border border-border bg-surface px-3 py-2 text-sm hover:border-warm-400">
                    <Select.Value />
                  </Select.Trigger>
                  <Select.Popover>
                    <ListBox>
                      <ListBoxItem key={GLOBAL_DEFAULT_KEY} id={GLOBAL_DEFAULT_KEY}>
                        {t("globalDefault")}
                      </ListBoxItem>
                      {workflowDefaultOptions.map((alias) => (
                        <ListBoxItem
                          key={alias}
                          id={alias}
                          isDisabled={!isProviderSelectable(providers, alias)}
                        >
                          {alias}
                        </ListBoxItem>
                      ))}
                    </ListBox>
                  </Select.Popover>
                </Select>

                <Select
                  selectedKey={
                    formatReviewOptions.includes(formatReviewProvider)
                      ? formatReviewProvider
                      : GLOBAL_DEFAULT_KEY
                  }
                  onSelectionChange={(key) => {
                    updateFormatReviewProvider(
                      key && String(key) !== GLOBAL_DEFAULT_KEY ? String(key) : ""
                    );
                  }}
                >
                  <Label className="text-xs text-muted">{t("formatReviewProvider")}</Label>
                  <Select.Trigger className="rounded-lg border border-border bg-surface px-3 py-2 text-sm hover:border-warm-400">
                    <Select.Value />
                  </Select.Trigger>
                  <Select.Popover>
                    <ListBox>
                      <ListBoxItem key={GLOBAL_DEFAULT_KEY} id={GLOBAL_DEFAULT_KEY}>
                        {t("globalDefault")}
                      </ListBoxItem>
                      {formatReviewOptions.map((alias) => (
                        <ListBoxItem
                          key={alias}
                          id={alias}
                          isDisabled={!isProviderSelectable(providers, alias, { requireJsonSchema: true })}
                        >
                          {alias}
                        </ListBoxItem>
                      ))}
                    </ListBox>
                  </Select.Popover>
                </Select>
              </div>
              <ProviderWarning warning={getProviderWarning(selectedWorkflow.default_provider)} />
              <p className="mt-2 text-xs text-muted">{t("formatReviewHint")}</p>
            </div>

            <div className="space-y-3 p-4">
              {stepNames.map((stepName) => {
                const stepConfig = selectedWorkflow.steps?.[stepName] || newWorkflowStepConfig();
                const stepProvider = stepConfig.provider || "";
                const stepTimeout = stepConfig.timeout_seconds ?? null;
                const effectiveProvider = stepProvider || selectedWorkflow.default_provider || config.llm.default_provider || "";
                const inheritedTimeout = effectiveProvider ? providers[effectiveProvider]?.timeout_seconds : undefined;
                const warning = stepProvider ? getProviderWarning(stepProvider) : null;
                const stepProviderOptions = getProviderAliasesForSelection(providers, stepProvider);
                return (
                  <div
                    key={stepName}
                    className="rounded-lg border border-border bg-surface-secondary/70 p-3"
                  >
                    <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-foreground">{stepName}</span>
                          <StatusChip tone={providerStatusTone(effectiveProvider)}>
                            {providerStatusText(effectiveProvider)}
                          </StatusChip>
                        </div>
                        <p className="mt-1 text-xs leading-5 text-muted">
                          {tSteps.has(stepName) ? tSteps(stepName) : t("customStepHint")}
                        </p>
                      </div>
                    </div>

                    <div className="grid items-start gap-3 md:grid-cols-[minmax(0,1fr)_240px]">
                      <Select
                        selectedKey={
                          stepProviderOptions.includes(stepProvider)
                            ? stepProvider
                            : INHERIT_WORKFLOW_KEY
                        }
                        onSelectionChange={(key) => {
                          updateStep(stepName, {
                            provider: key && String(key) !== INHERIT_WORKFLOW_KEY ? String(key) : "",
                          });
                        }}
                      >
                        <Label className="block text-xs text-muted">{t("stepProvider")}</Label>
                        <Select.Trigger className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm hover:border-warm-400">
                          <Select.Value />
                        </Select.Trigger>
                        <Select.Popover>
                          <ListBox>
                            <ListBoxItem key={INHERIT_WORKFLOW_KEY} id={INHERIT_WORKFLOW_KEY}>
                              {t("inheritDefault")}
                            </ListBoxItem>
                            {stepProviderOptions.map((alias) => (
                              <ListBoxItem
                                key={alias}
                                id={alias}
                                isDisabled={!isProviderSelectable(providers, alias)}
                              >
                                {alias}
                              </ListBoxItem>
                            ))}
                          </ListBox>
                        </Select.Popover>
                      </Select>

                      <div className="flex flex-col gap-1">
                        <Label className="block text-xs text-muted">{t("timeoutSeconds")}</Label>
                        <input
                          type="number"
                          min={1}
                          step={30}
                          value={stepTimeout ?? ""}
                          placeholder={inheritedTimeout ? String(inheritedTimeout) : ""}
                          onChange={(event) => {
                            const value = event.target.value;
                            const parsed = Number(value);
                            updateStep(stepName, {
                              timeout_seconds:
                                value && Number.isFinite(parsed)
                                  ? Math.max(1, Math.floor(parsed))
                                  : null,
                            });
                          }}
                          className="h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm text-foreground outline-none focus:border-accent"
                        />
                        <span className="block min-h-4 text-xs text-muted">
                          {stepTimeout
                            ? `${t("timeoutOverride")}: ${stepTimeout}s`
                            : `${t("timeoutInherit")}${inheritedTimeout ? `: ${inheritedTimeout}s` : ""}`}
                        </span>
                      </div>
                    </div>
                    <ProviderWarning warning={warning} />
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      </Card.Content>
    </Card>
  );
}

/**
 * 渲染 Provider 配置警告。
 *
 * Args:
 *   warning: 警告文案，空值不渲染。
 *
 * Returns:
 *   警告提示节点或 null。
 */
function ProviderWarning({ warning }: { warning: string | null }) {
  if (!warning) return null;
  return (
    <div className="mt-2 rounded bg-yellow-50 px-2 py-1 text-xs text-yellow-700 ring-1 ring-yellow-200 dark:bg-yellow-950/30 dark:text-yellow-400 dark:ring-yellow-800">
      {warning}
    </div>
  );
}

/**
 * 小型状态标签，用于标记 Provider 可用性。
 *
 * Args:
 *   tone: 标签视觉语义。
 *   children: 标签内容。
 *
 * Returns:
 *   状态标签节点。
 */
function StatusChip({
  tone,
  children,
}: {
  tone: "success" | "warning" | "muted";
  children: React.ReactNode;
}) {
  const toneClass = {
    success: "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300",
    warning: "border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-800 dark:bg-yellow-950/30 dark:text-yellow-300",
    muted: "border-border bg-background text-muted",
  }[tone];

  return (
    <span className={`rounded-md border px-1.5 py-0.5 text-[11px] ${toneClass}`}>
      {children}
    </span>
  );
}
