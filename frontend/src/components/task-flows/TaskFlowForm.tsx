"use client";

import { downloadExport } from "@/lib/userExport";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { GenerationParamsCollapse } from "@/components/shared/GenerationParamsCollapse";
import type { TaskFlowState } from "@/hooks/useTaskFlow";
import { resolveTaskFlowSchema,type FlowNodeEvent,type JsonSchema, type PreparedContextV1 } from "@/types/taskFlow";
import { Button,Modal,Tooltip } from "@heroui/react";
import { useLocale,useTranslations } from "next-intl";
import { useEffect,useId,useRef,useState, type ReactNode } from "react";

type FieldChoices = Record<string, { value: string; label: string }[]>;
const WRITING_DEFAULT_TITLES: Record<string, string> = { count: "生成数量", count_mode: "数量方式", user_guidance: "作者要求", target_word_count: "目标字数", search_text: "检索文字", search_scope: "检索范围" };
const WRITING_DEFAULT_NAMES: Record<string, string> = {"plan_arcs_by_ai": "逐级生成篇章", "plan_scenes_by_ai": "逐级生成场景", "plan_chapters_by_ai": "逐级生成章计划", "write_chapter_by_ai": "逐级生成本章正文", "generate_volume_plot_by_ai": "本卷详细剧情", "generate_arc_plot_by_ai": "篇章详细剧情", "create_characters_for_volume_by_ai": "生成卷内角色", "create_factions_for_volume_by_ai": "生成卷内势力", "create_locations_for_volume_by_ai": "默认流程"};

export const FLOW_INPUT_CLASS =
  "min-h-11 w-full min-w-0 rounded-xl border border-border bg-background/80 px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/15 disabled:cursor-not-allowed disabled:opacity-60";

/** 功能：按端口结构编辑作者输入。Args: schema 字段结构；value 字段值；onChange 写入值；fieldLabels 按字段路径指定名称。Returns: 有标签的字段控件。 */
export function TaskFlowSchemaField({
  name,
  schema: rawSchema,
  value,
  onChange,
  disabled = false,
  invalid = false,
  fieldLabels = {},
  fieldPath = name,
  nullableAsEmpty = false,
}: {
  name: string;
  schema: JsonSchema;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  invalid?: boolean;
  fieldLabels?: Record<string, string>;
  fieldPath?: string;
  nullableAsEmpty?: boolean;
}) {
  const id = useId();
  const manualCount = useRef<number | null>(typeof value === "number" ? value : null);
  const t = useTranslations("taskFlows");
  const schema = resolveTaskFlowSchema(rawSchema);
  const type = Array.isArray(schema.type)
    ? schema.type.find((item) => item !== "null")
    : schema.type;
  const label = fieldLabels[fieldPath] ?? (schema.title || name);
  const inlineOptional = nullableAsEmpty && Array.isArray(schema.type) && schema.type.includes("null") && ["string", "number", "integer"].includes(type ?? "");
  const aiCount = ["character_count", "faction_count", "item_count", "core_rule_count"].includes(name)
    && Array.isArray(schema.type) && schema.type.includes("null") && type === "integer";
  if (aiCount) {
    return <div className="grid min-w-0 gap-2">
      <label htmlFor={`${id}-mode`} className="text-xs font-medium text-muted">{t("countModeFor", { field: label })}</label>
      <select id={`${id}-mode`} className={FLOW_INPUT_CLASS} disabled={disabled} value={value === null ? "auto" : "fixed"}
        onChange={(event) => { if (typeof value === "number") manualCount.current = value; onChange(event.target.value === "auto" ? null : manualCount.current ?? (typeof schema.default === "number" ? schema.default : schema.minimum ?? 1)); }}>
        <option value="fixed">{t("countModes.fixed")}</option><option value="auto">{t("countModes.ai")}</option>
      </select>
      {value !== null && <TaskFlowSchemaField name={name} schema={{ ...schema, type: "integer" }} value={value} onChange={onChange} disabled={disabled} invalid={invalid} fieldLabels={fieldLabels} fieldPath={fieldPath} />}
    </div>;
  }
  if (Array.isArray(schema.type) && schema.type.includes("null") && !inlineOptional) {
    return (
      <div className="grid min-w-0 gap-3">
        <label className="flex min-h-11 items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={value === null}
            disabled={disabled}
            aria-invalid={invalid || undefined}
            className="size-4 accent-accent"
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? null
                  : type === "object"
                    ? {}
                    : type === "array"
                      ? []
                      : type === "boolean"
                        ? false
                        : "",
              )
            }
          />
          {t("leaveEmpty", { field: label })}
        </label>
        {value !== null && (
          <TaskFlowSchemaField
            name={name}
            schema={{ ...schema, type }}
            value={value}
            onChange={onChange}
            disabled={disabled}
            invalid={invalid}
            fieldLabels={fieldLabels}
            fieldPath={fieldPath}
          />
        )}
      </div>
    );
  }
  if (type === "object" && schema.properties) {
    const fields =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {};
    return (
      <fieldset className="min-w-0 space-y-4 border-t border-border pt-4">
        <legend className="px-1 text-sm font-medium">{label}</legend>
        {Object.entries(schema.properties).map(([key, child]) => (
          <TaskFlowSchemaField
            key={key}
            name={key}
            schema={child}
            value={fields[key]}
            disabled={disabled}
            fieldLabels={fieldLabels}
            fieldPath={`${fieldPath}.${key}`}
            onChange={(next) => onChange({ ...fields, [key]: next })}
          />
        ))}
      </fieldset>
    );
  }
  if (type === "array") {
    const items = Array.isArray(value) ? value : [];
    const options = schema["x-choices"] as
      | { value: string; label: string }[]
      | undefined;
    if (options)
      return (
        <fieldset className="min-w-0">
          <legend className="mb-2 text-xs font-medium text-muted">
            {label}
          </legend>
          <div className="flex min-w-0 flex-wrap gap-2">{options.map((option) => (
            <label
              key={option.value}
              className={`flex min-h-11 max-w-full cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm focus-within:ring-2 focus-within:ring-accent/30 ${items.includes(option.value) ? "border-accent/40 bg-selected text-selected-foreground" : "border-border bg-background text-foreground"}`}
            >
              <input
                type="checkbox"
                checked={items.includes(option.value)}
                disabled={disabled}
                className="size-4 shrink-0 accent-accent"
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...items, option.value]
                      : items.filter((item) => item !== option.value),
                  )
                }
              />
              <span className="min-w-0 [overflow-wrap:anywhere]">{option.label}</span>
            </label>
          ))}</div>
        </fieldset>
      );
    return (
      <fieldset className="min-w-0 space-y-3">
        <legend className="mb-2 text-xs font-medium text-muted">{label}</legend>
        {items.map((item, index) => (
          <div key={index} className="flex min-w-0 items-end gap-2">
            <div className="min-w-0 flex-1">
              <TaskFlowSchemaField
                name={`${name} ${index + 1}`}
                schema={schema.items ?? { type: "string" }}
                value={item}
                disabled={disabled}
                fieldLabels={fieldLabels}
                fieldPath={`${fieldPath}[]`}
                onChange={(next) =>
                  onChange(
                    items.map((old, itemIndex) =>
                      itemIndex === index ? next : old,
                    ),
                  )
                }
              />
            </div>
            <Button
              size="sm"
              variant="ghost"
              isDisabled={disabled}
              aria-label={t("removeItem", { number: index + 1 })}
              onPress={() =>
                onChange(items.filter((_, itemIndex) => itemIndex !== index))
              }
            >
              {t("remove")}
            </Button>
          </div>
        ))}
        <Button
          size="sm"
          variant="outline"
          isDisabled={disabled}
          onPress={() =>
            onChange([
              ...items,
              schema.items?.default ??
                (schema.items?.type === "object" ? {} : ""),
            ])
          }
        >
          {t("addItem")}
        </Button>
      </fieldset>
    );
  }
  if (type === "boolean")
    return (
      <label htmlFor={id} className="flex min-h-11 items-center gap-3 text-sm">
        <input
          id={id}
          name={name}
          aria-invalid={invalid || undefined}
          type="checkbox"
          checked={value === true}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="size-4 accent-accent"
        />
        {label}
      </label>
    );
  const options = schema.enum;
  const optionLabels = schema["x-choices"] as { value: string; label: string }[] | undefined;
  const numeric = type === "number" || type === "integer";
  return (
    <div className="grid min-w-0 gap-2">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}{inlineOptional && <span aria-hidden="true" className="ml-2 font-normal">{t("optional")}</span>}
      </label>
      {options ? (
        <select
          id={id}
          name={name}
          aria-invalid={invalid || undefined}
          className={FLOW_INPUT_CLASS}
          disabled={disabled}
          value={String(value ?? "")}
          onChange={(event) =>
            onChange(
              event.target.value === "" &&
                Array.isArray(schema.type) &&
                schema.type.includes("null")
                ? null
                : event.target.value === "" ? "" : options.find((item) => String(item) === event.target.value),
            )
          }
        >
          <option value="">{t(name === "provider" ? "followDefaultProvider" : "choose")}</option>
          {options.map((item, index) => (
            <option key={index} value={String(item)}>
              {optionLabels?.find((option) => option.value === String(item))?.label ?? String(item)}
            </option>
          ))}
        </select>
      ) : numeric ? (
        <input
          id={id}
          name={name}
          aria-invalid={invalid || undefined}
          type="number"
          className={FLOW_INPUT_CLASS}
          value={typeof value === "number" ? value : ""}
          min={schema.minimum}
          max={schema.maximum}
          step={type === "integer" ? 1 : "any"}
          disabled={disabled}
          onChange={(event) =>
            onChange(
              event.target.value === ""
                ? Array.isArray(schema.type) && schema.type.includes("null")
                  ? null
                  : ""
                : Number(event.target.value),
            )
          }
        />
      ) : (schema.maxLength ?? 0) > 200 || schema.format === "textarea" ? (
        <textarea
          id={id}
          name={name}
          aria-invalid={invalid || undefined}
          className={`${FLOW_INPUT_CLASS} min-h-28 resize-y leading-6`}
          rows={4}
          value={String(value ?? "")}
          maxLength={schema.maxLength}
          disabled={disabled}
          onChange={(event) => onChange(inlineOptional && event.target.value === "" ? null : event.target.value)}
        />
      ) : (
        <input
          id={id}
          name={name}
          aria-invalid={invalid || undefined}
          className={FLOW_INPUT_CLASS}
          value={String(value ?? "")}
          maxLength={schema.maxLength}
          disabled={disabled}
          onChange={(event) => onChange(inlineOptional && event.target.value === "" ? null : event.target.value)}
        />
      )}
    </div>
  );
}

/** 功能：在原 AI 弹窗中展示所选方案的开始字段。Args: flow 当前任务；disabled 是否正在执行；fieldLabels 当前业务字段名称；showError 外层已展示同一错误时可关闭。Returns: 方案选择与动态字段。 */
export function TaskFlowForm({
  flow,
  disabled = false,
  fieldChoices = {},
  fieldLabels = {},
  showError = true,
  hiddenFields = [],
  toolbarActions,
}: {
  flow: TaskFlowState;
  disabled?: boolean;
  fieldChoices?: FieldChoices;
  fieldLabels?: Record<string, string>;
  showError?: boolean;
  hiddenFields?: string[];
  toolbarActions?: ReactNode;
}) {
  const t = useTranslations("taskFlows");
  const locale = useLocale();
  const id = useId();
  const [paramsOpen, setParamsOpen] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (Object.keys(flow.fieldErrors).length)
      formRef.current?.querySelector<HTMLElement>(disabled ? "[role='alert']" : "[aria-invalid='true']")?.focus();
  }, [flow.fieldErrors, disabled]);
  const fields =
    flow.definition?.nodes
      .filter((node) => node.type === "input")
      .flatMap((node) => Object.entries(node.outputs)) ?? [];
  return (
    <div ref={formRef} className="grid min-w-0 gap-5">
      <div className="flex min-w-0 flex-wrap items-end gap-3">
        <div className="grid min-w-0 flex-[1_1_100%] gap-2 sm:flex-[1_1_16rem]">
          <label htmlFor={id} className="text-xs font-medium text-muted">
            {t("scheme")}
          </label>
          {flow.flows.length === 1 && flow.definition ? <span className="flex min-h-11 items-center text-sm" aria-label={t("scheme")}>{flow.definition.id === `default_${flow.task}` ? t(`tasks.${flow.task}`) : flow.definition.name}</span> : <select
            id={id}
            className={FLOW_INPUT_CLASS}
            disabled={disabled || flow.loading}
            value={flow.definition?.id ?? ""}
            onChange={(event) => {
              const summary = flow.flows.find(
                (item) => item.id === event.target.value,
              );
              if (summary) void flow.select(summary);
            }}
          >
            <option value="" disabled>
              {t("loading")}
            </option>
            {flow.flows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id === `default_${item.task}` && item.name === WRITING_DEFAULT_NAMES[item.task] ? t(`tasks.${item.task}`) : item.name}
              </option>
            ))}
          </select>}
        </div>
        <Button
          variant="ghost"
          size="sm"
          isDisabled={disabled || flow.loading}
          onPress={() => {
                const returnTo = `${window.location.pathname}${window.location.search}${window.location.hash}`;
                // 保留当前生成表单，重复进入时复用同一个编辑器标签。
                window.open(
              `/${locale}/task-flows?task=${encodeURIComponent(flow.task)}&return_to=${encodeURIComponent(returnTo)}`,
                  "private-ai-task-flow-editor",
                )?.focus();
          }}
        >
          {t("editFlow")}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          isDisabled={disabled || flow.loading}
          onPress={() => void flow.refresh()}
        >
          {t("refresh")}
        </Button>
        {toolbarActions}
      </div>
      {flow.loading && (
        <p role="status" className="text-sm text-muted">
          {t("loading")}
        </p>
      )}
      {showError && flow.error && (
        <p
          role="alert"
          tabIndex={-1}
          className="break-words border-y border-red-500/30 py-3 text-sm text-red-600 dark:text-red-300"
        >
          {flow.error}
        </p>
      )}
      {!flow.loading &&
        fields.filter(([name]) => !hiddenFields.includes(name) && !(name === "count" && flow.inputs.count_mode === "auto") && !(flow.inputs.selection_mode === "auto" && ["create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai", "create_locations_for_volume_by_ai"].includes(flow.task) && ["new_count", "selected_existing_ids", "location_count", "selected_existing_location_ids", "allow_incremental"].includes(name))).map(([name, schema]) => {
          const errors = Object.entries(flow.fieldErrors)
            .filter(([key]) => key === name || key.startsWith(`${name}.`))
            .flatMap(([, messages]) => messages);
          const translatedTitle =
            t.has(`inputLabels.${name}`) &&
            (!schema.title ||
              schema.title.toLowerCase().replaceAll(" ", "_") === name ||
              (Boolean(WRITING_DEFAULT_NAMES[flow.definition?.task ?? ""]) && schema.title === WRITING_DEFAULT_TITLES[name]))
              ? t(name === "target_word_count" && WRITING_DEFAULT_NAMES[flow.definition?.task ?? ""] ? "writingInputLabels.target_word_count" : `inputLabels.${name}`)
              : schema.title;
          const displayedSchema = {
            ...schema,
            ...(name === "count" && flow.inputs.count_mode === "fixed" ? { type: "integer", anyOf: undefined, minimum: 1 } : {}),
            title: fieldLabels[name] ?? translatedTitle,
            ...(name === "selection_mode" && !fieldChoices[name] ? { "x-choices": [{ value: "auto", label: t("countModes.ai") }, { value: "manual", label: t("selectionManual") }] } : {}),
            ...(fieldChoices[name] ? { "x-choices": fieldChoices[name] } : {}),
            ...(name === "search_scope" && schema.title === WRITING_DEFAULT_TITLES.search_scope && !fieldChoices[name] ? { "x-choices": [{ value: "novel", label: t("searchScopes.novel") }, { value: "current_part", label: t("searchScopes.current_part") }] } : {}),
            ...(name === "provider" ? { enum: flow.providers } : {}),
            ...(name === "count_mode" ? { "x-choices": [{ value: "auto", label: t("countModes.auto") }, { value: "fixed", label: t("countModes.fixed") }] } : {}),
          };
          return (
            <div key={name} className="grid min-w-0 gap-2">
              <TaskFlowSchemaField
                name={name}
                nullableAsEmpty={["create_faction_relations_by_ai", "create_character_relations_by_ai"].includes(flow.task) && ["relation_count_limit", "user_guidance"].includes(name)}
                schema={displayedSchema}
                value={flow.inputs[name]}
                disabled={disabled}
                invalid={errors.length > 0}
                fieldLabels={fieldLabels}
                onChange={(value) => {
                  flow.setInputs((current) => ({ ...current, [name]: value, ...(name === "count_mode" && value === "fixed" ? { count: current.count ?? 1 } : {}) }));
                }}
              />
              {errors.length > 0 && (
                <p
                  role="alert"
                  className="text-xs text-red-600 dark:text-red-300"
                >
                  {errors.join(" · ")}
                </p>
              )}
            </div>
          );
        })}
      <GenerationParamsCollapse
        disabled={disabled}
        value={flow.params}
        onChange={(params) => {
          flow.setParams(params);
        }}
        isOpen={paramsOpen}
        onOpenChange={setParamsOpen}
        panelClassName="rounded-none border-x-0 border-b-0 bg-transparent px-0"
      />
    </div>
  );
}

/** 功能：显示生成状态与可选的追加轮数，按需展开资料。Args: flow 当前任务；running/failed 请求状态；label 当前操作；回调仍由原页面处理候选。Returns: 紧凑进度和步骤列表。 */
export function TaskFlowProgress({
  flow,
  running = false,
  failed = false,
  label,
  onRetry,
  onRepair,
  onContinue,
  onDiscard,
}: {
  flow: TaskFlowState;
  running?: boolean;
  failed?: boolean;
  label?: string;
  onRetry?: () => void;
  onRepair?: () => void;
  onContinue?: (additionalRounds: number) => void;
  onDiscard?: () => void;
}) {
  const t = useTranslations("taskFlows");
  const [expanded, setExpanded] = useState(false);
  const [additionalRounds, setAdditionalRounds] = useState("4");
  const [dismissedEvents, setDismissedEvents] = useState<FlowNodeEvent[] | null>(null);
  const detailsId = useId();
  const roundsId = useId();
  if (!running && !failed && !flow.events.length) return null;
  const events: (FlowNodeEvent & { displayLabel: string })[] = flow.events.map((event) => {
    const nodeLabel = String(event.label ?? flow.definition?.nodes.find((node) => node.id === event.node_id)?.label ?? event.node_id);
    return { ...event, displayLabel: t.has(`stepNames.${nodeLabel}`) ? t(`stepNames.${nodeLabel}`) : nodeLabel };
  });
  const completed = events.filter((event) => ["done", "completed", "cached"].includes(event.state)).length;
  const current = events.findLast((event) => event.state === "running");
  const failedNode = events.findLast((event) => ["failed", "error"].includes(event.state));
  // 节点跑完后，完整响应或候选校验仍可能失败；最终状态以调用方为准。
  const state = running ? "running" : failed || failedNode ? "failed" : current ? "stopped" : "done";
  // 只收起这一轮的完成提示；新运行、错误和候选本身仍由原任务管理。
  if (state === "done" && dismissedEvents === flow.events) return null;
  const continuation = flow.agentContinuation;
  const networkRecovery = continuation?.reason === "network";
  const canContinue = !running && failed && continuation && !networkRecovery && onContinue;
  const rounds = flow.continuationAdditionalRounds ?? Number(additionalRounds);
  const roundsValid = Number.isInteger(rounds) && rounds >= 1 && rounds <= 16;
  const lastError = continuation?.last_error;
  const lastMessage = typeof lastError === "string" ? lastError : typeof lastError?.error === "string" ? lastError.error : typeof lastError?.message === "string" ? lastError.message : "";
  const lastDetails = lastError && typeof lastError === "object"
    ? Object.fromEntries(Object.entries(lastError).filter(([key]) => key !== (typeof lastError.error === "string" ? "error" : typeof lastError.message === "string" ? "message" : "")))
    : {};
  return (
    <section
      aria-label={t("progress")}
      className="min-w-0 w-full shrink-0 border-y border-border"
    >
      <div className="flex min-h-11 min-w-0 flex-wrap items-center gap-x-3 gap-y-1 py-1">
        <div
          role="status"
          className="flex min-w-0 flex-[1_1_12rem] flex-wrap items-center gap-x-3 gap-y-1 text-sm"
        >
          {running && (
            <span
              className="size-4 shrink-0 animate-spin rounded-full border-2 border-border border-t-accent motion-reduce:animate-none"
              aria-hidden="true"
            />
          )}
          <span className={state === "failed" ? "text-danger" : "text-foreground"}>
            {running && current?.network_state === "waiting" ? t("agent.waiting", { seconds: Math.ceil(Number(current.retry_after)) }) : running && current?.network_state === "retrying" ? t("agent.reconnecting", { attempt: Number(current.retry_attempt), limit: Number(current.retry_limit), seconds: Math.ceil(Number(current.retry_after)) }) : !running && networkRecovery ? t("agent.connectionPaused") : running && flow.continuing ? t("agent.continuing") : running && flow.repairing ? t("repairing") : running && label ? label : t(`states.${state}`)}
          </span>
          {running && current && (
            <span className="min-w-0 truncate text-muted">{current.displayLabel}</span>
          )}
          {completed > 0 && (
            <span className="shrink-0 text-xs tabular-nums text-muted">
              {t("completedSteps", { count: completed })}
            </span>
          )}
        </div>
        {!running && failed && (
          <div className="flex flex-wrap items-center gap-2">
            {onRepair && <Button size="sm" variant="primary" className="min-h-11" onPress={onRepair}>{t("repair")}</Button>}
            {onRetry && <Button size="sm" variant={onRepair || canContinue ? "outline" : "primary"} className={networkRecovery ? "h-11 min-h-11" : "min-h-11"} onPress={onRetry}>{t(networkRecovery ? "agent.recover" : "retry")}</Button>}
            {onDiscard && <Button size="sm" variant="outline" className="min-h-11" onPress={onDiscard}>{t("discardRun")}</Button>}
          </div>
        )}
        {events.length > 0 && (
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={expanded}
            aria-controls={detailsId}
            onPress={() => setExpanded(!expanded)}
          >
            {expanded ? t("hideSteps") : t("showSteps")}
          </Button>
        )}
        {state === "done" && <Tooltip delay={300} closeDelay={0}>
          <Button isIconOnly size="sm" variant="ghost" className="size-11 shrink-0" aria-label={t("dismissCompleted")} onPress={() => setDismissedEvents(flow.events)}>
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </Button>
          <Tooltip.Content className="z-[100] rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs text-foreground shadow-lg">{t("dismissCompleted")}</Tooltip.Content>
        </Tooltip>}
      </div>
      {!running && flow.jsonDiagnostic && <div className="min-w-0 space-y-2 border-t border-border py-3">
        <p className="text-sm text-danger">
          {t(flow.jsonDiagnostic.duplicate_path_truncated ? "jsonDiagnostic.duplicatePathTruncated" : "jsonDiagnostic.duplicatePath")} <code dir="ltr" className="break-all">{flow.jsonDiagnostic.duplicate_path}</code>
        </p>
        {flow.jsonDiagnostic.duplicate_path_truncated && <p className="text-sm text-danger">{t("jsonDiagnostic.pathTruncated", { length: flow.jsonDiagnostic.duplicate_path_length })}</p>}
        {flow.jsonDiagnostic.raw_output_truncated && <p className="text-sm text-danger">{t("jsonDiagnostic.truncated", { length: flow.jsonDiagnostic.raw_output_length })}</p>}
        <details>
          <summary className="min-h-11 cursor-pointer py-2 text-sm text-accent focus-visible:outline-2 focus-visible:outline-accent">{t("jsonDiagnostic.rawOutput")}</summary>
          <pre tabIndex={0} aria-label={t("jsonDiagnostic.rawOutput")} className="workspace-scrollbar max-h-64 w-full min-w-0 overflow-auto whitespace-pre-wrap break-words bg-surface-secondary p-3 text-xs text-foreground focus-visible:outline-2 focus-visible:outline-accent">{flow.jsonDiagnostic.raw_output}</pre>
        </details>
        <Button size="sm" variant="ghost" className="min-h-11" onPress={() => {
          const diagnostic = flow.jsonDiagnostic!;
          const url = URL.createObjectURL(new Blob([diagnostic.raw_output], { type: "text/plain;charset=utf-8" }));
          const link = document.createElement("a");
          link.href = url;
          link.download = diagnostic.raw_output_truncated ? "model-output-untrusted-truncated.txt" : "model-output-untrusted.txt";
          void downloadExport(link);
          URL.revokeObjectURL(url);
        }}>{t("jsonDiagnostic.export")}</Button>
      </div>}
      {!running && failed && networkRecovery && <p className="py-2 text-sm text-muted">{t("agent.recoveryBoundary")}</p>}
      {canContinue && <div className="flex min-w-0 flex-wrap items-end gap-3 border-t border-border py-3">
        <div className="min-w-0 flex-[1_1_16rem] space-y-2">
          <p className="text-sm tabular-nums">{t("agent.round", { round: continuation.round, count: continuation.call_count })}</p>
          {(lastMessage || Object.keys(lastDetails).length > 0) && <div className="space-y-1 text-muted">
            <p className="text-xs font-medium">{t("agent.previousToolError")}</p>
            {lastMessage && <p className="reading-copy whitespace-pre-wrap">{lastMessage}</p>}
            {Object.keys(lastDetails).length > 0 && <p className="reading-copy whitespace-pre-wrap">{JSON.stringify(lastDetails, null, 2)}</p>}
          </div>}
        </div>
        <label htmlFor={roundsId} className="grid gap-2 text-xs font-medium text-muted">
          {t("agent.additionalRounds")}
          <input id={roundsId} type="number" inputMode="numeric" min={1} max={16} step={1} value={flow.continuationAdditionalRounds ?? additionalRounds} disabled={flow.continuationAdditionalRounds != null} onChange={(event) => setAdditionalRounds(event.target.value)} aria-invalid={!roundsValid} aria-describedby={!roundsValid ? `${roundsId}-error` : undefined} className={`${FLOW_INPUT_CLASS} max-w-28`} />
        </label>
        <Button size="sm" variant="primary" className="min-h-11" isDisabled={!roundsValid} onPress={() => onContinue(rounds)}>{t("agent.continue")}</Button>
        {!roundsValid && <p id={`${roundsId}-error`} role="alert" className="w-full text-sm text-danger">{t("agent.roundsInvalid")}</p>}
        {flow.continuationAdditionalRounds != null && <p className="w-full text-sm text-muted">{t("agent.retrySameRounds")}</p>}
      </div>}
      <div id={detailsId} hidden={!expanded}>
        {expanded && (
          <ul className="workspace-scrollbar max-h-64 overflow-y-auto border-t border-border divide-y divide-border">
            {events.map((event) => (
              <li key={event.instance_path} className="min-w-0 text-sm">
                <details>
                  <summary className="flex min-h-11 cursor-pointer flex-wrap items-center justify-between gap-2">
                    <span className="min-w-0 break-words">
                      {event.displayLabel}
                      {typeof event.tool_name === "string" && <span className="ml-2 text-muted">{t.has(`agent.toolNames.${event.tool_name}`) ? t(`agent.toolNames.${event.tool_name}`) : event.tool_name}</span>}
                    </span>
                    <span className="text-xs text-muted">
                      {!running && event.state === "running"
                        ? t("states.stopped")
                        : t.has(`states.${event.state}`)
                          ? t(`states.${event.state}`)
                          : event.state}
                    </span>
                  </summary>
                  {typeof event.elapsed_ms === "number" && (
                    <p className="py-2 text-xs text-muted">
                      {t("elapsed", {
                        seconds: (event.elapsed_ms / 1000).toFixed(2),
                      })}
                    </p>
                  )}
                  {typeof event.message === "string" && (
                    <p className="py-2 text-sm">{event.message}</p>
                  )}
                  {typeof event.round === "number" && <p className="py-2 text-xs text-muted">{t("agent.round", { round: event.round, count: typeof event.call_count === "number" ? event.call_count : 0 })}</p>}
                  {Boolean(event.outputs?.prepared_context) && <PreparedContextReadout value={event.outputs!.prepared_context as PreparedContextV1} />}
                  {event.outputs && <details><summary className="min-h-11 cursor-pointer py-2 text-xs text-muted">{t("agent.rawOutput")}</summary>
                    <pre
                      className="workspace-scrollbar max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-3 text-xs"
                      tabIndex={0}
                      aria-label={t("outputs")}
                    >
                      {JSON.stringify(event.outputs, null, 2)}
                    </pre>
                  </details>}
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** 功能：展示资料整理的边界、采用原因和待补资料。Args: value 本轮整理结果。Returns: 不含模型私有内容的阅读区。 */
export function PreparedContextReadout({ value }: { value: PreparedContextV1 }) {
  const t = useTranslations("taskFlows.agent");
  return <div className="space-y-3 py-3">
    <p className="reading-copy whitespace-pre-wrap">{value.boundaries}</p>
    <p className="reading-copy whitespace-pre-wrap">{value.coverage}</p>
    <p className="text-sm">{t(value.remaining ? "suggestedCount" : "coverageComplete", { count: value.suggested_count })}</p>
    {value.selection_reasons?.length > 0 && <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-accent">{t("adopted", { count: value.selection_reasons.length })}</summary><ul className="space-y-3">{value.selection_reasons.map((item, index) => <li key={`${item.resource_type}:${item.id}:${index}`} className="reading-copy"><p>{item.reason}</p><span className="break-all text-xs text-muted">{item.resource_type} · {item.id}</span></li>)}</ul></details>}
    {value.entity_needs?.length > 0 && <div><h4 className="text-xs font-medium text-muted">{t("needed")}</h4><ul className="space-y-2">{value.entity_needs.map((item, index) => <li key={index} className="reading-copy">{item.role} · {item.reason}</li>)}</ul></div>}
    {value.missing_required?.map((item) => <p key={item.field} role="alert" className="text-sm text-danger">{item.message}</p>)}
  </div>;
}

/** 功能：复用原 AI 操作弹窗的动态开始表单。Args: title 操作名称；flow 任务状态；failed 生成或结果校验是否失败；回调负责原页面操作。Returns: 标准弹窗。 */
export function TaskFlowDialog({
  title,
  flow,
  onCancel,
  onGenerate,
  disabled = false,
  failed = false,
  fieldChoices,
  hiddenFields,
  notice,
}: {
  title: string;
  flow: TaskFlowState;
  onCancel: () => void;
  onGenerate: () => void;
  disabled?: boolean;
  failed?: boolean;
  fieldChoices?: FieldChoices;
  hiddenFields?: string[];
  notice?: string;
}) {
  const t = useTranslations("taskFlows");
  return (
    <RetainedModalBackdrop
      isOpen
      onOpenChange={(open) => !open && onCancel()}
      variant="blur"
      isDismissable={!disabled}
    >
      <Modal.Container size="lg" scroll="inside" className="p-0 sm:p-4">
        <Modal.Dialog className="h-[100dvh] w-full sm:h-auto sm:max-h-[90vh] sm:max-w-3xl">
          <Modal.Header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4 sm:px-7">
            <Modal.Heading className="text-lg font-semibold">
              {title}
            </Modal.Heading>
            <Modal.CloseTrigger aria-label={t("close")} />
          </Modal.Header>
          <Modal.Body className="px-5 py-6 sm:px-7">
            {notice && <p role="status" className="mb-4 text-sm text-muted">{notice}</p>}
            <TaskFlowForm
              flow={flow}
              disabled={disabled}
              fieldChoices={fieldChoices}
              hiddenFields={hiddenFields}
            />
            {(disabled || failed) && <TaskFlowProgress flow={flow} running={disabled} failed={failed} />}
          </Modal.Body>
          <Modal.Footer className="sticky bottom-0 flex flex-wrap justify-end gap-2 border-t border-border bg-surface-raised px-5 py-4 sm:px-7">
            <Button variant="ghost" size="sm" onPress={onCancel}>
              {t("close")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onPress={onGenerate}
              isDisabled={disabled || flow.loading || !flow.definition}
            >
              {disabled ? t("states.running") : t("generate")}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </RetainedModalBackdrop>
  );
}
