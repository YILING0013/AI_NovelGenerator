"use client";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import type { FlowPreviewAIRequest } from "@/types/taskFlowPreview";

/**
 * 显示模拟节点按当前输入组装的完整提示词和输出格式。
 * Args: request 本次节点实例的请求；busy 数据是否正在重算；containsExamples 是否使用假设输入。
 * Returns: 可完整阅读、复制的 AI 请求详情。
 */
export function TaskFlowAIRequestPreview({ request, busy, containsExamples }: {
  request: FlowPreviewAIRequest;
  busy?: boolean;
  containsExamples?: boolean;
}) {
  const t = useTranslations("taskFlows.preview");
  const [copyResult, setCopyResult] = useState<{ request: FlowPreviewAIRequest; success: boolean }>();
  const copied = copyResult?.request === request ? copyResult.success : undefined;

  return (
    <section className="min-w-0 space-y-3 border-t border-border pt-4" aria-label={t("aiRequest")} aria-busy={busy}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("aiRequest")}</h3>
        <Button size="sm" variant="ghost" isDisabled={busy} onPress={async () => {
          try {
            await navigator.clipboard.writeText(JSON.stringify(request, null, 2));
            setCopyResult({ request, success: true });
          } catch {
            setCopyResult({ request, success: false });
          }
        }}>{t("copyAIRequest")}</Button>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {request.api_mode && <span>{request.api_mode}</span>}
        {request.provider && <span>{request.provider}</span>}
        {request.model && <span className="break-all">{request.model}</span>}
        <span>{t(`aiExecution.${request.execution_mode}`)}</span>
      </div>
      {containsExamples && <p className="text-xs text-muted">{t("containsExamples")}</p>}
      {busy && <p role="status" className="text-xs text-muted">{t("updating")}</p>}
      {copied !== undefined && <p role={copied ? "status" : "alert"} className={copied ? "text-xs text-muted" : "text-xs text-danger"}>
        {t(copied ? "copiedAIRequest" : "copyAIRequestFailed")}
      </p>}
      {request.notes.map((note, index) => <p key={index} className="text-xs text-muted">{t(`aiNotes.${note}`)}</p>)}
      {request.messages.map((message, index) => (
        <div key={`${index}:${message.role}`} className="min-w-0 space-y-2">
          <h4 className="text-xs font-medium">{["system", "user", "assistant"].includes(message.role) ? t(`aiRoles.${message.role}`) : message.role}</h4>
          <pre tabIndex={0} aria-label={`${message.role} · ${t("aiRequest")}`}
            className="workspace-scrollbar max-h-[32rem] w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-3 text-xs leading-6 focus-visible:outline-2 focus-visible:outline-accent">
            {message.content}
          </pre>
        </div>
      ))}
      {request.response_format && <details className="min-w-0 border-t border-border-subtle">
        <summary className="min-h-11 cursor-pointer py-3 text-xs font-medium">{t("aiResponseFormat")}</summary>
        <pre tabIndex={0} aria-label={t("aiResponseFormat")} className="workspace-scrollbar max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs leading-6">{JSON.stringify(request.response_format, null, 2)}</pre>
      </details>}
      {Object.keys(request.api_parameters ?? request.parameters).length > 0 && <details className="min-w-0 border-t border-border-subtle">
        <summary className="min-h-11 cursor-pointer py-3 text-xs font-medium">{t("aiParameters")}</summary>
        <pre tabIndex={0} aria-label={t("aiParameters")} className="workspace-scrollbar max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs leading-6">{JSON.stringify(request.api_parameters ?? request.parameters, null, 2)}</pre>
      </details>}
      {request.output_schema && !request.response_format && <details className="min-w-0 border-t border-border-subtle">
        <summary className="min-h-11 cursor-pointer py-3 text-xs font-medium">{t("aiOutputSchema")}</summary>
        <pre tabIndex={0} aria-label={t("aiOutputSchema")} className="workspace-scrollbar max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs leading-6">{JSON.stringify(request.output_schema, null, 2)}</pre>
      </details>}
    </section>
  );
}
