"use client";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { resolveTaskFlowSchema, type JsonSchema } from "@/types/taskFlow";
import type {
  FlowPreviewIssue,
  FlowPreviewOrigin,
  FlowPreviewOverride,
  FlowPreviewPort,
} from "@/types/taskFlowPreview";
import { FlowJsonEditor } from "./FlowCodeEditors";
import { FLOW_INPUT_CLASS } from "./TaskFlowForm";

type PortPreviewProps = {
  port: string;
  schema: JsonSchema;
  data: FlowPreviewPort;
  instancePath?: string;
  output: boolean;
  busy?: boolean;
  overrides?: FlowPreviewOverride[];
  errors?: FlowPreviewIssue[];
  onOverride?: (override: FlowPreviewOverride) => void;
  onResetOverride?: (override: FlowPreviewOverride) => void;
  onFocus?: (instancePath: string, port?: string) => void;
};

function PreviewOriginField({
  origin,
  value,
  schema,
  editable,
  error,
  ...props
}: PortPreviewProps & {
  origin: FlowPreviewOrigin;
  value: unknown;
  schema: JsonSchema;
  editable: boolean;
  error?: string;
}) {
  const t = useTranslations("taskFlows.preview");
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(value);
  const [valid, setValid] = useState(true);
  const [localError, setLocalError] = useState("");
  const pathKey = JSON.stringify(origin.path);
  const overridden = props.overrides?.find(
    (item) =>
      item.instance_path === props.instancePath &&
      item.port === props.port &&
      JSON.stringify(item.path) === pathKey,
  );
  const override = {
    instance_path: props.instancePath!,
    port: props.port,
    path: origin.path,
    value: draft,
  };
  const isString =
    schema.type === "string" ||
    (Array.isArray(schema.type) && schema.type.includes("string")) ||
    (!schema.type && typeof value === "string");
  const isNumber = schema.type === "number" || schema.type === "integer";
  const isBoolean = schema.type === "boolean" || typeof value === "boolean";
  const label = `${t("exampleValue")} · ${[props.port, ...origin.path].join(".")}`;
  const displayedError = localError || error;
  const sourceElsewhere =
    origin.source_instance_path &&
    (origin.source_instance_path !== props.instancePath ||
      origin.source_port !== props.port ||
      !props.output);

  return (
    <div className="min-w-0 space-y-2 border-t border-border-subtle py-3">
      <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-2 text-xs">
        <span className="break-all font-mono">
          {[props.port, ...origin.path].join(".")}
        </span>
        <span className="text-muted">{t(`origins.${origin.kind}`)}</span>
      </div>
      {schema.description && (
        <p className="text-xs leading-5 text-muted">{schema.description}</p>
      )}
      {origin.note && (
        <p className="text-xs leading-5 text-muted">{origin.note}</p>
      )}
      {origin.path.length > 0 && (
        <pre className="whitespace-pre-wrap break-words text-xs leading-5">
          {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
        </pre>
      )}
      {editing ? (
        <div className="grid min-w-0 gap-2">
          {schema.enum ? (
            <label className="grid gap-2 text-xs text-muted" htmlFor={id}>
              {label}
              <select
                id={id}
                className={FLOW_INPUT_CLASS}
                value={JSON.stringify(draft)}
                onChange={(event) => setDraft(JSON.parse(event.target.value))}
              >
                {schema.enum.map((option) => (
                  <option
                    key={JSON.stringify(option)}
                    value={JSON.stringify(option)}
                  >
                    {String(option)}
                  </option>
                ))}
              </select>
            </label>
          ) : isBoolean ? (
            <label
              className="flex min-h-11 items-center gap-2 text-sm"
              htmlFor={id}
            >
              <input
                id={id}
                type="checkbox"
                checked={draft === true}
                onChange={(event) => setDraft(event.target.checked)}
              />
              {label}
            </label>
          ) : isString ? (
            <label className="grid gap-2 text-xs text-muted" htmlFor={id}>
              {label}
              <textarea
                id={id}
                data-flow-preview-field="true"
                aria-invalid={Boolean(displayedError)}
                aria-describedby={displayedError ? `${id}-error` : undefined}
                className={`${FLOW_INPUT_CLASS} min-h-28 resize-y leading-6`}
                value={String(draft ?? "")}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
          ) : isNumber ? (
            <label className="grid gap-2 text-xs text-muted" htmlFor={id}>
              {label}
              <input
                id={id}
                className={FLOW_INPUT_CLASS}
                type="number"
                step={schema.type === "integer" ? 1 : "any"}
                min={schema.minimum}
                max={schema.maximum}
                value={String(draft ?? "")}
                onChange={(event) => {
                  setDraft(
                    event.target.value === "" ? "" : Number(event.target.value),
                  );
                  setLocalError("");
                }}
              />
            </label>
          ) : (
            <FlowJsonEditor
              label={label}
              value={draft}
              onChange={setDraft}
              onValidityChange={setValid}
              validationScope="preview"
            />
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              isDisabled={!valid || props.busy}
              onPress={() => {
                if (
                  isNumber &&
                  (typeof draft !== "number" ||
                    !Number.isFinite(draft) ||
                    (schema.type === "integer" && !Number.isInteger(draft)))
                ) {
                  setLocalError(
                    t("invalidType", { type: schema.type as string }),
                  );
                  return;
                }
                setLocalError("");
                props.onOverride?.(override);
              }}
            >
              {t("applyExample")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onPress={() => {
                setEditing(false);
                setLocalError("");
              }}
            >
              {t("cancelEdit")}
            </Button>
          </div>
        </div>
      ) : editable && !sourceElsewhere && props.onOverride ? (
        <Button
          size="sm"
          variant="ghost"
          isDisabled={props.busy}
          onPress={() => {
            setDraft(overridden ? overridden.value : value);
            setValid(true);
            setEditing(true);
          }}
        >
          {t(origin.kind === "actual" ? "useExample" : "editExample")}
        </Button>
      ) : null}
      {displayedError && (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {displayedError}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {overridden && props.onResetOverride && (
          <Button
            size="sm"
            variant="ghost"
            isDisabled={props.busy}
            onPress={() => {
              props.onResetOverride?.(override);
              setEditing(false);
              setLocalError("");
            }}
          >
            {t("resetExample")}
          </Button>
        )}
        {sourceElsewhere && props.onFocus && (
          <Button
            size="sm"
            variant="ghost"
            onPress={() =>
              props.onFocus?.(origin.source_instance_path!, origin.source_port)
            }
          >
            {t("jumpSource")}
          </Button>
        )}
      </div>
    </div>
  );
}

/** 功能：显示端口实际传值和逐字段来源，临时示例只在点击应用后提交。Args: props 当前端口、实例和覆盖回调。Returns: 端口数据详情。 */
export function TaskFlowPortPreview(props: PortPreviewProps) {
  const t = useTranslations("taskFlows.preview");
  const { data, schema, port } = props;
  let decoded = data.value;
  if (data.json_encoded && typeof data.value === "string") {
    try {
      decoded = JSON.parse(data.value);
    } catch {
      /* 格式错误保留原文，具体错误由服务端返回。 */
    }
  }
  const includesExamples = data.origins.some((origin) =>
    origin.kind.endsWith("_example"),
  );
  // 同一字段可能由多个来源拼成；相同来源只列一次，避免重复 key 重建编辑草稿。
  const origins = new Map(
    data.origins.map((origin) => [
      JSON.stringify([
        origin.path,
        origin.source_instance_path,
        origin.source_port,
        origin.source_path,
        origin.kind,
      ]),
      origin,
    ]),
  );
  return (
    <section
      className="min-w-0 space-y-2"
      aria-label={`${t("dataTitle")} · ${port}`}
      aria-busy={props.busy}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs">
        <h4 className="font-semibold">{t("dataTitle")}</h4>
        <span className="text-muted">
          {data.json_encoded
            ? t("jsonString")
            : `${t("format")}: ${Array.isArray(schema.type) ? schema.type.join(" | ") : (schema.type ?? (decoded === null ? "null" : Array.isArray(decoded) ? "array" : typeof decoded))}`}
        </span>
      </div>
      {props.busy && (
        <p className="text-xs text-muted" role="status">
          {t("updating")}
        </p>
      )}
      {includesExamples && (
        <p className="text-xs text-muted">{t("containsExamples")}</p>
      )}
      <pre
        className="workspace-scrollbar max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-secondary p-3 text-xs leading-6"
        tabIndex={0}
        aria-label={`${t("dataTitle")} · ${port}`}
      >
        {typeof decoded === "string"
          ? decoded
          : JSON.stringify(decoded, null, 2)}
      </pre>
      {[...origins.values()].map((origin) => {
        let value = decoded;
        let fieldSchema = data.json_encoded
          ? ({} as JsonSchema)
          : resolveTaskFlowSchema(schema);
        for (const part of origin.path) {
          value =
            value !== null && typeof value === "object"
              ? (value as Record<string, unknown>)[part]
              : undefined;
          fieldSchema = resolveTaskFlowSchema(
            fieldSchema.properties?.[part] ?? fieldSchema.items ?? {},
          );
        }
        const emptyActual =
          origin.kind === "actual" &&
          (value === null || (Array.isArray(value) && value.length === 0));
        // 混合对象只能修改示例字段，不能从父对象覆盖真实小说数据。
        const protectedChild = data.origins.some(
          (child) =>
            child.path.length > origin.path.length &&
            origin.path.every((part, index) => child.path[index] === part) &&
            (!child.editable ||
              child.source_instance_path !== props.instancePath ||
              child.source_port !== port),
        );
        const editable = Boolean(
          props.instancePath &&
            props.output &&
            (origin.editable || emptyActual) &&
            !protectedChild,
        );
        const error = props.errors?.find(
          (issue) =>
            issue.instance_path === props.instancePath &&
            issue.port === port &&
            (!issue.path ||
              JSON.stringify(issue.path) === JSON.stringify(origin.path)),
        )?.message;
        return (
          <PreviewOriginField
            key={JSON.stringify([
              origin.path,
              origin.source_instance_path,
              origin.source_port,
              origin.source_path,
              origin.kind === "actual" ? "missing_example" : origin.kind,
            ])}
            {...props}
            schema={fieldSchema}
            origin={origin}
            value={value}
            editable={editable}
            error={error}
          />
        );
      })}
    </section>
  );
}
