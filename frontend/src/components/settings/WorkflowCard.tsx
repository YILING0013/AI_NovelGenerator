"use client";

import { useTranslations } from "next-intl";
import {
  Card,
  Select,
  ListBox,
  ListBoxItem,
  Label,
  Chip,
} from "@heroui/react";
import type { AppConfig, WorkflowConfig } from "@/types/config";
import { WORKFLOW_STEPS } from "@/types/config";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
}

export function WorkflowCard({ config, onChange }: Props) {
  const t = useTranslations("settings.workflow");
  const tSteps = useTranslations("settings.workflow.steps");

  const providers = config.llm?.providers || {};
  const providerAliases = Object.keys(providers);

  const workflow: WorkflowConfig = config.llm?.workflows?.create_novel_by_ai || {
    default_provider: config.llm?.default_provider || "",
    steps: Object.fromEntries(WORKFLOW_STEPS.map((s) => [s, { provider: "" }])),
  };

  const updateWorkflow = (updates: Partial<WorkflowConfig>) => {
    const next: AppConfig = {
      ...config,
      llm: {
        ...config.llm,
        workflows: {
          ...config.llm.workflows,
          create_novel_by_ai: { ...workflow, ...updates },
        },
      },
    };
    onChange(next);
  };

  const updateStep = (stepName: string, provider: string) => {
    updateWorkflow({
      steps: {
        ...workflow.steps,
        [stepName]: { provider },
      },
    });
  };

  const getProviderWarning = (providerAlias: string): string | null => {
    if (!providerAlias) return null;
    if (!providerAliases.includes(providerAlias)) return t("providerNotExist");
    if (!providers[providerAlias]?.enabled) return t("providerDisabled");
    return null;
  };

  return (
    <Card className="bg-surface border border-border shadow-sm">
      <Card.Header className="flex-col items-start gap-1">
        <Card.Title className="text-lg font-semibold text-foreground">{t("title")}</Card.Title>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted">{t("workflowName")}:</span>
          <Chip size="sm" variant="soft" className="bg-warm-200 text-foreground">
            create_novel_by_ai
          </Chip>
        </div>
      </Card.Header>
      <Card.Content className="space-y-5">
        {/* Workflow default provider */}
        <div>
          <Select
            selectedKey={workflow.default_provider || null}
            onSelectionChange={(key) => {
              updateWorkflow({ default_provider: key ? String(key) : "" });
            }}
            className="max-w-sm"
          >
            <Label className="text-sm text-muted">{t("defaultProvider")}</Label>
            <Select.Trigger className="border border-border rounded-lg px-3 py-2 text-sm bg-surface hover:border-warm-400">
              <Select.Value />
            </Select.Trigger>
            <Select.Popover>
              <ListBox>
                {providerAliases.map((alias) => (
                  <ListBoxItem key={alias} id={alias}>
                    {alias}
                  </ListBoxItem>
                ))}
              </ListBox>
            </Select.Popover>
          </Select>
          <ProviderWarning warning={getProviderWarning(workflow.default_provider)} />
        </div>

        {/* Steps */}
        <div className="space-y-3">
          {WORKFLOW_STEPS.map((stepName) => {
            const stepProvider = workflow.steps?.[stepName]?.provider || "";
            const isInheriting = !stepProvider;
            const effectiveProvider = stepProvider || workflow.default_provider || "";
            const warning = stepProvider ? getProviderWarning(stepProvider) : null;

            return (
              <div key={stepName} className="p-3 rounded-lg bg-surface-secondary border border-border">
                <div className="flex items-baseline gap-2 mb-1">
                  <span className="font-medium text-sm text-foreground">{stepName}</span>
                  {isInheriting && effectiveProvider && (
                    <span className="text-xs text-muted">
                      ({t("inheritDefault")}: {effectiveProvider})
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted mb-2">{tSteps(stepName)}</p>
                <Select
                  selectedKey={stepProvider || null}
                  onSelectionChange={(key) => {
                    updateStep(stepName, key ? String(key) : "");
                  }}
                  className="max-w-sm"
                >
                  <Label className="text-xs text-muted">{t("stepLabel")} Provider</Label>
                  <Select.Trigger className="border border-border rounded-lg px-3 py-2 text-sm bg-surface hover:border-warm-400">
                    <Select.Value />
                  </Select.Trigger>
                  <Select.Popover>
                    <ListBox>
                      {providerAliases.map((alias) => (
                        <ListBoxItem key={alias} id={alias}>
                          {alias}
                        </ListBoxItem>
                      ))}
                    </ListBox>
                  </Select.Popover>
                </Select>
                <ProviderWarning warning={warning} />
              </div>
            );
          })}
        </div>
      </Card.Content>
    </Card>
  );
}

function ProviderWarning({ warning }: { warning: string | null }) {
  if (!warning) return null;
  return (
    <div className="mt-1 text-xs px-2 py-1 rounded bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-400">
      {warning}
    </div>
  );
}
