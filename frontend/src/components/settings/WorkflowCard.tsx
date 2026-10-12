"use client";

import { FLOW_INPUT_CLASS } from "@/components/task-flows/TaskFlowForm";
import { apiGet } from "@/lib/api";
import { isDeepSeekProvider, type AppConfig } from "@/types/config";
import type { FlowTask } from "@/types/taskFlow";
import { Button } from "@heroui/react";
import { useLocale,useTranslations } from "next-intl";
import { useEffect,useState } from "react";

interface Props {
  config: AppConfig;
  onChange: (config: AppConfig) => void;
}

/**
 * 功能：配置全局模型及格式审校，并进入原任务的流程编辑器。
 * Args:
 *   config: 尚未保存的设置草稿。
 *   onChange: 仅更新设置草稿，保存仍由设置页负责。
 * Returns:
 *   公共模型字段与任务目录。
 */
export function WorkflowCard({ config, onChange }: Props) {
  const t = useTranslations("settings.workflow");
  const tf = useTranslations("taskFlows");
  const locale = useLocale();
  const [tasks, setTasks] = useState<FlowTask[]>([]);
  const [error, setError] = useState("");
  const providers = config.llm.providers ?? {};
  useEffect(() => {
    let active = true;
    apiGet<{ tasks: FlowTask[] }>("/api/task-flows/tasks")
      .then((result) => {
        if (active) setTasks(result.tasks);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error ? failure.message : String(failure),
          );
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <section
      aria-labelledby="workflow-settings-title"
      className="flex min-h-0 flex-col bg-surface lg:h-full lg:overflow-hidden"
    >
      <header className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <h2 id="workflow-settings-title" className="text-lg font-semibold">
          {t("title")}
        </h2>
      </header>
      <div className="workspace-scrollbar min-h-0 flex-1 overflow-auto px-4 py-5 sm:px-6">
        <div className="grid gap-5 md:grid-cols-2">
          <label className="grid gap-2 text-xs font-medium text-muted">
            {t("globalDefaultProvider")}
            <select
              className={FLOW_INPUT_CLASS}
              value={config.llm.default_provider ?? ""}
              onChange={(event) =>
                onChange({
                  ...config,
                  llm: { ...config.llm, default_provider: event.target.value },
                })
              }
            >
              <option value="">{t("noGlobalDefault")}</option>
              {config.llm.default_provider &&
                !providers[config.llm.default_provider] && (
                  <option value={config.llm.default_provider} disabled>
                    {config.llm.default_provider}
                  </option>
                )}
              {Object.entries(providers).map(([alias, provider]) => (
                <option key={alias} value={alias} disabled={!provider.enabled}>
                  {alias}
                  {!provider.enabled ? ` · ${t("providerDisabledShort")}` : ""}
                </option>
              ))}
            </select>
            {config.llm.default_provider &&
              !providers[config.llm.default_provider] && (
                <span role="alert" className="text-danger">
                  {t("providerNotExist")}
                </span>
              )}
          </label>
          <label className="grid gap-2 text-xs font-medium text-muted">
            {t("formatReviewProvider")}
            <select
              className={FLOW_INPUT_CLASS}
              value={config.llm.format_review_provider ?? ""}
              onChange={(event) =>
                onChange({
                  ...config,
                  llm: {
                    ...config.llm,
                    format_review_provider: event.target.value,
                  },
                })
              }
            >
              <option value="">{t("globalDefault")}</option>
              {config.llm.format_review_provider &&
                !providers[config.llm.format_review_provider] && (
                  <option value={config.llm.format_review_provider} disabled>
                    {config.llm.format_review_provider}
                  </option>
                )}
              {Object.entries(providers).map(([alias, provider]) => (
                <option
                  key={alias}
                  value={alias}
                  disabled={
                    !provider.enabled ||
                    (!provider.supports_json_schema && !isDeepSeekProvider(provider))
                  }
                >
                  {alias}
                  {!provider.enabled ? ` · ${t("providerDisabledShort")}` : ""}
                </option>
              ))}
            </select>
            {config.llm.format_review_provider &&
              !providers[config.llm.format_review_provider] && (
                <span role="alert" className="text-danger">
                  {t("providerNotExist")}
                </span>
              )}
          </label>
        </div>
        {error && (
          <p
            role="alert"
            className="mt-5 border-y border-red-500/30 py-3 text-sm text-red-600 dark:text-red-300"
          >
            {error}
          </p>
        )}
        <ul className="mt-6 divide-y divide-border border-y border-border">
          {tasks.map((task) => (
            <li
              key={task.task}
              className="flex min-w-0 flex-wrap items-center justify-between gap-3 py-3"
            >
              <span className="text-sm">
                {tf.has(`tasks.${task.task}`)
                  ? tf(`tasks.${task.task}`)
                  : task.label}
              </span>
              <Button
                variant="outline"
                size="sm"
                onPress={() => {
                  const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
                  // 复用编辑器标签，并保留来源页供返回时恢复焦点。
                  window.open(
                    `/${locale}/task-flows?task=${encodeURIComponent(task.task)}&return_to=${encodeURIComponent(returnTo)}`,
                    "private-ai-task-flow-editor",
                  )?.focus();
                }}
              >
                {tf("editFlow")}
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
