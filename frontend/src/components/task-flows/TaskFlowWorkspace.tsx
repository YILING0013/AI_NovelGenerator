"use client";

import { downloadExport } from "@/lib/userExport";

import { apiGet, apiPost, apiPut } from "@/lib/api";
import { TooltipHint } from "@/components/shared/TooltipHint";
import {
  readTaskFlowEditDraft,
  writeTaskFlowEditDraft,
} from "@/lib/taskFlowCache";
import type { AppConfig } from "@/types/config";
import type {
  FlowRef,
  FlowSummary,
  FlowTask,
  TaskFlow,
} from "@/types/taskFlow";
import { Button } from "@heroui/react";
import { useLocale, useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  FlowJsonField,
  focusInvalidFlowJson,
  isTaskFlowDraft,
  TaskFlowEditor,
} from "./TaskFlowEditor";
import { FLOW_INPUT_CLASS } from "./TaskFlowForm";
import { useTaskFlowPreview } from "@/hooks/useTaskFlowPreview";
import { TaskFlowPreviewPanel } from "./TaskFlowPreviewPanel";
import type { FlowPreviewFocus } from "@/types/taskFlowPreview";

interface FlowHistory {
  past: TaskFlow[];
  present: TaskFlow;
  future: TaskFlow[];
}
interface ValidationResult {
  valid: boolean;
  errors: { node_id?: string; port?: string; message: string }[];
}

/** 功能：在设置工作台编辑原业务任务使用的流程方案。Args: 无。Returns: 方案管理、图编辑和保存界面。 */
export default function TaskFlowWorkspace() {
  const t = useTranslations("taskFlows");
  const locale = useLocale();
  const search = useSearchParams();
  const [tasks, setTasks] = useState<FlowTask[]>([]);
  const [task, setTask] = useState(search.get("task") ?? "create_novel_by_ai");
  const [flows, setFlows] = useState<FlowSummary[]>([]);
  const [defaultRef, setDefaultRef] = useState<FlowRef | null>(null);
  const [defaultVersion, setDefaultVersion] = useState(0);
  const [history, setHistory] = useState<FlowHistory | null>(null);
  const [saved, setSaved] = useState("");
  const [path, setPath] = useState<string[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [draftError, setDraftError] = useState("");
  const [draftConflict, setDraftConflict] = useState<number | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [jsonValid, setJsonValid] = useState(true);
  const [advanced, setAdvanced] = useState(false);
  const [diagnosticsSignal, setDiagnosticsSignal] = useState(0);
  const [previewFocus, setPreviewFocus] = useState<FlowPreviewFocus>();
  const importRef = useRef<HTMLInputElement>(null);
  const requestIdRef = useRef(0);
  const draftWritesRef = useRef<Promise<void>>(Promise.resolve());
  const loadedRef = useRef<FlowRef | null>(null);
  const leavingRef = useRef(false);
  const dirty = Boolean(history && JSON.stringify(history.present) !== saved);
  const root = history?.present;
  const preview = useTaskFlowPreview(root, !loading && jsonValid);
  let graph = root;
  for (const part of path) graph = graph?.subflows[part];

  const focusPreview = (instancePath: string, port?: string) => {
    if (focusInvalidFlowJson()) return;
    const source = preview.result?.steps.find((item) => item.instance_path === instancePath)
      ?? preview.result?.nodes.find((item) => Object.values(item.outputs).some((field) =>
        field.origins.some((origin) => origin.source_instance_path === instancePath),
      ));
    if (source) setPath(source.graph_path);
    setPreviewFocus((previous) => ({ instance_path: instancePath, port, signal: (previous?.signal ?? 0) + 1 }));
  };

  const loadFlow = useCallback(
    async (ref: FlowRef) => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      setError("");
      setDraftError("");
      try {
        await draftWritesRef.current;
        const next = await apiGet<TaskFlow>(
          `/api/task-flows/${encodeURIComponent(ref.id)}?revision=${ref.revision}`,
        );
        const draft = await readTaskFlowEditDraft(next.id).catch(
          (failure: unknown) => {
            if (requestIdRef.current === requestId)
              setDraftError(
                t("draftStorageError", {
                  message:
                    failure instanceof Error
                      ? failure.message
                      : String(failure),
                }),
              );
            return null;
          },
        );
        if (requestIdRef.current !== requestId) return;
        loadedRef.current = { id: next.id, revision: next.revision };
        setHistory({
          past: [],
          present: draft?.definition ?? next,
          future: [],
        });
        setSaved(JSON.stringify(next));
        setDraftConflict(
          draft && draft.base_revision !== next.revision ? next.revision : null,
        );
        setPath([]);
        setValidation(null);
        setJsonValid(true);
      } catch (failure) {
        if (requestIdRef.current === requestId)
          setError(
            failure instanceof Error ? failure.message : String(failure),
          );
      } finally {
        if (requestIdRef.current === requestId) setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    if (!root || loading || saving || draftError) return;
    // 顺序写入，避免快速编辑时较旧内容晚到；保存完成后也不会重新写回旧草稿。
    draftWritesRef.current = draftWritesRef.current
      .then(() => writeTaskFlowEditDraft(root.id, dirty ? root : null))
      .catch((failure: unknown) => {
        setDraftError(
          t("draftStorageError", {
            message:
              failure instanceof Error ? failure.message : String(failure),
          }),
        );
      });
  }, [root, dirty, loading, saving, draftError, t]);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiGet<{ tasks: FlowTask[] }>("/api/task-flows/tasks"),
      apiGet<{ data: AppConfig }>("/api/config"),
    ])
      .then(([metadata, config]) => {
        if (active) {
          setTasks(metadata.tasks);
          setProviders(Object.keys(config.data.llm.providers));
        }
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

  useEffect(() => {
    let active = true;
    apiGet<{ flows: FlowSummary[]; default_ref: FlowRef; version: number }>(
      `/api/task-flows?task=${encodeURIComponent(task)}`,
    )
      .then((result) => {
        if (active) {
          setFlows(result.flows);
          setDefaultRef(result.default_ref);
          setDefaultVersion(result.version);
          void loadFlow(
            result.flows.find((flow) => flow.id === result.default_ref.id) ??
              result.default_ref,
          );
        }
      })
      .catch((failure: unknown) => {
        if (active) {
          setError(
            failure instanceof Error ? failure.message : String(failure),
          );
          setLoading(false);
        }
      });
    return () => {
      active = false;
      requestIdRef.current += 1;
    };
  }, [task, loadFlow]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!leavingRef.current && (dirty || !jsonValid)) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, jsonValid]);

  const changeGraph = useCallback(
    (next: TaskFlow, record = true) => {
      setHistory((current) => {
        if (!current) return current;
        if (!path.length)
          return {
            past: record
              ? [...current.past, current.present].slice(-60)
              : current.past,
            present: next,
            future: [],
          };
        const nextRoot = structuredClone(current.present);
        let parent = nextRoot;
        for (const part of path.slice(0, -1)) parent = parent.subflows[part];
        parent.subflows[path.at(-1)!] = next;
        return {
          past: record
            ? [...current.past, current.present].slice(-60)
            : current.past,
          present: nextRoot,
          future: [],
        };
      });
      setValidation(null);
    },
    [path],
  );

  const verify = async (): Promise<boolean> => {
    if (!root) return false;
    setError("");
    if (focusInvalidFlowJson()) {
      setError(t("invalidJson"));
      return false;
    }
    setDiagnosticsSignal((value) => value + 1);
    const result = await apiPost<ValidationResult>("/api/task-flows/validate", {
      definition: root,
    });
    setValidation(result);
    return result.valid;
  };

  const checkPreview = () => {
    if (!root) return;
    setError("");
    if (focusInvalidFlowJson()) {
      setError(t("invalidJson"));
      return;
    }
    setDiagnosticsSignal((value) => value + 1);
    setValidation(null);
    preview.activate();
  };

  const setDefault = async (ref: FlowRef, expectedVersion = defaultVersion) => {
    const result = await apiPut<{ default_ref: FlowRef; version: number }>(
      `/api/task-flows/default/${encodeURIComponent(task)}`,
      { flow_ref: ref, expected_version: expectedVersion },
    );
    setDefaultRef(result.default_ref);
    setDefaultVersion(result.version);
  };

  const save = async () => {
    if (!root || saving || draftConflict !== null) return;
    setSaving(true);
    setError("");
    try {
      if (!(await verify())) return;
      const next = await apiPut<TaskFlow>(
        `/api/task-flows/${encodeURIComponent(root.id)}`,
        { expected_revision: root.revision, definition: root },
      );
      setHistory({ past: [], present: next, future: [] });
      setSaved(JSON.stringify(next));
      loadedRef.current = { id: next.id, revision: next.revision };
      setDraftConflict(null);
      await draftWritesRef.current;
      await writeTaskFlowEditDraft(root.id, null).catch((failure: unknown) => {
        setDraftError(
          t("draftStorageError", {
            message:
              failure instanceof Error ? failure.message : String(failure),
          }),
        );
      });
      const catalog = await apiGet<{
        flows: FlowSummary[];
        default_ref: FlowRef;
        version: number;
      }>(`/api/task-flows?task=${encodeURIComponent(task)}`);
      setFlows(catalog.flows);
      setDefaultRef(catalog.default_ref);
      setDefaultVersion(catalog.version);
      if (
        defaultRef?.id === root.id &&
        catalog.default_ref.id === defaultRef.id &&
        catalog.default_ref.revision === defaultRef.revision
      )
        await setDefault(
          { id: next.id, revision: next.revision },
          catalog.version,
        );
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };

  const copy = async (useBuiltin = false) => {
    if (!root || saving) return;
    if (focusInvalidFlowJson()) return;
    setSaving(true);
    setError("");
    try {
      const source = useBuiltin ? await apiGet<TaskFlow>(`/api/task-flows/builtin/${encodeURIComponent(task)}`) : root;
      const next = await apiPost<TaskFlow>("/api/task-flows", {
        task,
        name: t("newCopyName", { name: source.name }),
        definition: source,
      });
      const catalog = await apiGet<{
        flows: FlowSummary[];
        default_ref: FlowRef;
        version: number;
      }>(`/api/task-flows?task=${encodeURIComponent(task)}`);
      setFlows(catalog.flows);
      setDefaultRef(catalog.default_ref);
      setDefaultVersion(catalog.version);
      setHistory({ past: [], present: next, future: [] });
      setSaved(JSON.stringify(next));
      loadedRef.current = { id: next.id, revision: next.revision };
      setDraftConflict(null);
      setPath([]);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };

  const restoreBuiltIn = async () => {
    if (!root || saving) return;
    if (focusInvalidFlowJson()) return;
    setSaving(true);
    setError("");
    try {
      const builtin = await apiGet<TaskFlow>(
        `/api/task-flows/builtin/${encodeURIComponent(task)}`,
      );
      setHistory(
        (current) =>
          current && {
            past: [...current.past, current.present].slice(-60),
            present: {
              ...builtin,
              id: root.id,
              name: root.name,
              revision: root.revision,
            },
            future: [],
          },
      );
      setPath([]);
      setValidation(null);
      setJsonValid(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setSaving(false);
    }
  };

  const discardDraft = async () => {
    if (!root || !loadedRef.current || saving) return;
    setSaving(true);
    setDraftError("");
    try {
      await draftWritesRef.current;
      await writeTaskFlowEditDraft(root.id, null);
      await loadFlow(loadedRef.current);
    } catch (failure) {
      setDraftError(
        t("draftStorageError", {
          message: failure instanceof Error ? failure.message : String(failure),
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  const leave = () => {
    if ((dirty || !jsonValid) && !window.confirm(t("leaveWarning"))) return;
    // 返回按钮已经确认过，关闭标签时不再重复弹出浏览器提示。
    leavingRef.current = true;
    const returnTo = search.get("return_to");
    const safe =
      returnTo &&
      /^\/(zh|en)(\/|\?|#|$)/.test(returnTo) &&
      !returnTo.includes("/task-flows") &&
      !returnTo.startsWith("//");
    const destination = safe
      ? returnTo.replace(/^\/(zh|en)/, `/${locale}`)
      : `/${locale}`;
    const source = window.opener as Window | null;
    if (safe && source && !source.closed) {
      try {
        const sourcePath = `${source.location.pathname}${source.location.search}${source.location.hash}`;
        if (source.location.origin === window.location.origin && sourcePath === returnTo) {
          // 直接回到仍然打开的来源页，保留设置弹窗和未提交的输入。
          source.focus();
          window.close();
          return;
        }
      } catch {
        // 来源页可能已经跳到其他网站，此时使用当前返回地址。
      }
    }
    // 直接打开编辑器时完整导航，避免设置弹窗再次叠在编辑器上。
    window.location.replace(destination);
  };

  const schemePanel = root && (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2 text-xs text-muted">
        <span>{t("revision", { revision: root.revision })}</span>
        <TooltipHint text={t("help.revision")} />
      </div>
      <label className="grid min-w-0 gap-1 text-xs text-muted">
        <span className="flex items-center justify-between gap-2">
          {t("name")}
          <TooltipHint text={t("help.name")} />
        </span>
        <input
          aria-label={t("name")}
          className={FLOW_INPUT_CLASS}
          value={root.name}
          disabled={saving}
          onChange={(event) =>
            setHistory(
              (current) =>
                current && {
                  past: [...current.past, current.present].slice(-60),
                  present: { ...current.present, name: event.target.value },
                  future: [],
                },
            )
          }
        />
      </label>
      <label className="grid min-w-0 gap-1 text-xs text-muted">
        <span className="flex items-center justify-between gap-2">
          {t("defaultProvider")}
          <TooltipHint text={t("help.defaultProvider")} />
        </span>
        <select
          aria-label={t("defaultProvider")}
          className={FLOW_INPUT_CLASS}
          value={root.default_provider}
          disabled={saving}
          onChange={(event) =>
            setHistory(
              (current) =>
                current && {
                  past: [...current.past, current.present].slice(-60),
                  present: {
                    ...current.present,
                    default_provider: event.target.value,
                  },
                  future: [],
                },
            )
          }
        >
          <option value="">{t("inherit")}</option>
          {providers.map((provider) => (
            <option key={provider}>{provider}</option>
          ))}
        </select>
      </label>
      <label className="grid min-w-0 gap-1 text-xs text-muted">
        <span className="flex items-center justify-between gap-2">
          {t("maxExecutions")}
          <TooltipHint text={t("help.maxExecutions")} />
        </span>
        <input
          aria-label={t("maxExecutions")}
          type="number"
          min={1}
          max={10000}
          className={FLOW_INPUT_CLASS}
          value={root.max_node_executions}
          disabled={saving}
          onChange={(event) =>
            setHistory(
              (current) =>
                current && {
                  past: [...current.past, current.present].slice(-60),
                  present: {
                    ...current.present,
                    max_node_executions: Number(event.target.value),
                  },
                  future: [],
                },
            )
          }
        />
      </label>
      <div className="flex flex-wrap gap-2 border-t border-border pt-4">
        <Button size="sm" variant="outline" isDisabled={saving} onPress={() => void copy(true)}>{t("useLatestCopy")}</Button>
        <TooltipHint text={t("help.copy")}>
          <Button
            size="sm"
            variant="outline"
            isDisabled={saving}
            onPress={() => void copy()}
          >
            {t("copy")}
          </Button>
        </TooltipHint>
        <TooltipHint text={t("help.setDefault")}>
          <Button
            size="sm"
            variant="outline"
            isDisabled={
              dirty ||
              saving ||
              (defaultRef?.id === root.id &&
                defaultRef.revision === root.revision)
            }
            onPress={() =>
              void setDefault({ id: root.id, revision: root.revision }).catch(
                (failure: unknown) =>
                  setError(
                    failure instanceof Error
                      ? failure.message
                      : String(failure),
                  ),
              )
            }
          >
            {t("setDefault")}
          </Button>
        </TooltipHint>
        <TooltipHint text={t("help.import")}>
          <Button
            size="sm"
            variant="ghost"
            isDisabled={saving}
            onPress={() => {
              if (!focusInvalidFlowJson()) importRef.current?.click();
            }}
          >
            {t("import")}
          </Button>
        </TooltipHint>
        <TooltipHint text={t("help.export")}>
          <Button
            size="sm"
            variant="ghost"
            onPress={() => {
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(root, null, 2)], {
                  type: "application/json",
                }),
              );
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = `${root.name.replace(/[\\/:*?"<>|]/g, "_")}.json`;
              void downloadExport(anchor);
              URL.revokeObjectURL(url);
            }}
          >
            {t("export")}
          </Button>
        </TooltipHint>
        <TooltipHint text={t("help.builtIn")}>
          <Button
            size="sm"
            variant="ghost"
            isDisabled={saving}
            onPress={() => void restoreBuiltIn()}
          >
            {t("builtIn")}
          </Button>
        </TooltipHint>
        {dirty && draftConflict === null && (
          <TooltipHint text={t("help.discardDraft")}>
            <Button
              size="sm"
              variant="ghost"
              isDisabled={saving}
              onPress={() => void discardDraft()}
            >
              {t("discardDraft")}
            </Button>
          </TooltipHint>
        )}
      </div>
      <div className="border-t border-border pt-4">
        <TooltipHint text={t("help.advanced")}>
          <Button
            size="sm"
            variant="ghost"
            isDisabled={!jsonValid}
            aria-expanded={advanced}
            onPress={() => {
              if (!focusInvalidFlowJson()) setAdvanced(true);
            }}
          >
            {t("advanced")}
          </Button>
        </TooltipHint>
      </div>
    </div>
  );

  const displayedValidation = validation ?? (!preview.stale && !preview.busy && preview.result?.valid ? { valid: true, errors: [] } : null);
  const diagnosticsPanel = (
    <div className="space-y-4 text-sm">
      {root && <TaskFlowPreviewPanel key={root.task} flow={root} preview={preview} onFocus={focusPreview} />}
      {error && (
        <p role="alert" className="break-words text-red-600 dark:text-red-300">
          {error}
        </p>
      )}
      {(draftError || draftConflict !== null) && (
        <div role="alert" className="space-y-3 text-red-600 dark:text-red-300">
          <p>
            {draftError ||
              t("draftRevisionConflict", { revision: draftConflict ?? 0 })}
          </p>
          {draftConflict !== null && (
            <Button
              size="sm"
              variant="outline"
              isDisabled={saving}
              onPress={() => void discardDraft()}
            >
              {t("discardDraft")}
            </Button>
          )}
        </div>
      )}
      {displayedValidation &&
        (displayedValidation.valid ? (
          <p role="status" className="flex items-center gap-2 text-foreground">
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="size-4 shrink-0 text-accent"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="m5 12 4 4L19 6" />
            </svg>
            {t("valid")}
          </p>
        ) : (
          <ul role="alert" className="space-y-3">
            {displayedValidation.errors.map((item, index) => (
              <li
                key={index}
                className="break-words border-l-2 border-red-500/50 pl-3 text-red-600 dark:text-red-300"
              >
                {(item.node_id || item.port) && (
                  <span className="mb-1 block text-xs text-muted">
                    {[item.node_id, item.port].filter(Boolean).join(" · ")}
                  </span>
                )}
                {item.message}
              </li>
            ))}
          </ul>
        ))}
      {!preview.enabled && !error && !draftError && draftConflict === null && !validation && (
        <p className="text-muted">{t("notChecked")}</p>
      )}
    </div>
  );
  const hasIssues = Boolean(
    error ||
    draftError ||
    draftConflict !== null ||
    validation?.valid === false || preview.result?.status === "error" || preview.error,
  );

  return (
    <main className="flex h-[calc(100dvh-56px)] min-h-0 min-w-0 flex-col overflow-hidden bg-surface text-foreground">
      <header
        data-flow-toolbar
        className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2 sm:px-4"
      >
        <TooltipHint text={t("help.back")}>
          <Button
            variant="ghost"
            size="sm"
            isIconOnly
            aria-label={t("back")}
            onPress={leave}
            isDisabled={saving}
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="size-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="m14 6-6 6 6 6" />
            </svg>
          </Button>
        </TooltipHint>
        <h1 className="mr-1 text-sm font-semibold max-[460px]:sr-only">
          {t("title")}
        </h1>
        <span
          className="max-w-24 truncate text-xs text-muted max-xl:sr-only"
          role="status"
        >
          {saving ? t("saving") : dirty ? t("unsaved") : t("saved")}
        </span>
        <div className="order-3 grid min-w-0 basis-full grid-cols-2 gap-2 sm:order-none sm:flex sm:flex-1 sm:basis-auto">
          <label className="min-w-0 sm:w-36 sm:flex-1 sm:max-w-48">
            <span className="sr-only">{t("task")}</span>
            <select
              className={`${FLOW_INPUT_CLASS} !rounded-lg !py-1.5 sm:!min-h-10`}
              value={task}
              disabled={saving}
              title={t("help.task")}
              onChange={(event) => {
                if ((!dirty && jsonValid) || window.confirm(t("leaveWarning")))
                  setTask(event.target.value);
              }}
            >
              {tasks.map((item) => (
                <option key={item.task} value={item.task}>
                  {t.has(`tasks.${item.task}`)
                    ? t(`tasks.${item.task}`)
                    : item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-0 sm:w-40 sm:flex-1 sm:max-w-64">
            <span className="sr-only">{t("scheme")}</span>
            <select
              className={`${FLOW_INPUT_CLASS} !rounded-lg !py-1.5 sm:!min-h-10`}
              value={root?.id ?? ""}
              disabled={saving}
              title={t("help.scheme")}
              onChange={(event) => {
                const item = flows.find(
                  (flow) => flow.id === event.target.value,
                );
                if (
                  item &&
                  ((!dirty && jsonValid) || window.confirm(t("leaveWarning")))
                )
                  void loadFlow(item);
              }}
            >
              {flows.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {item.id === defaultRef?.id ? ` · ${t("default")}` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          <TooltipHint text={t("help.undo")}>
            <Button
              size="sm"
              variant="ghost"
              isIconOnly
              aria-label={t("undo")}
              isDisabled={!history?.past.length || saving}
              onPress={() =>
                setHistory((current) =>
                  current && current.past.length
                    ? {
                        past: current.past.slice(0, -1),
                        present: current.past.at(-1)!,
                        future: [current.present, ...current.future],
                      }
                    : current,
                )
              }
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="size-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M9 5 4 10l5 5M4 10h10a6 6 0 0 1 0 12" />
              </svg>
            </Button>
          </TooltipHint>
          <TooltipHint text={t("help.redo")}>
            <Button
              size="sm"
              variant="ghost"
              isIconOnly
              aria-label={t("redo")}
              isDisabled={!history?.future.length || saving}
              onPress={() =>
                setHistory((current) =>
                  current && current.future.length
                    ? {
                        past: [...current.past, current.present],
                        present: current.future[0],
                        future: current.future.slice(1),
                      }
                    : current,
                )
              }
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="size-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="m15 5 5 5-5 5m5-5H10a6 6 0 0 0 0 12" />
              </svg>
            </Button>
          </TooltipHint>
          <TooltipHint text={t("help.validate")}>
            <Button
              size="sm"
              variant="outline"
              aria-label={t("validate")}
              isDisabled={!root || saving}
              className={
                hasIssues
                  ? "border-red-500/60 text-red-600 dark:text-red-300"
                  : ""
              }
              onPress={checkPreview}
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="size-4 shrink-0"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="m8 12 3 3 5-6" />
                <path d="M7 3h10l4 4v13H3V3z" />
              </svg>
              <span className="hidden lg:inline">{t("validate")}</span>
              {hasIssues && (
                <span aria-hidden="true" className="font-bold">
                  !
                </span>
              )}
            </Button>
          </TooltipHint>
          <TooltipHint text={t("help.save")}>
            <Button
              size="sm"
              variant="primary"
              isDisabled={
                !root || saving || !jsonValid || draftConflict !== null
              }
              onPress={() => void save()}
            >
              {saving ? t("saving") : t("save")}
            </Button>
          </TooltipHint>
        </div>
      </header>
      <input
        ref={importRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        aria-label={t("import")}
        onChange={async (event) => {
          const file = event.target.files?.[0];
          if (!file || !root) return;
          try {
            const imported: unknown = JSON.parse(await file.text());
            if (!isTaskFlowDraft(imported)) throw new Error(t("invalidImport"));
            setHistory({
              past: [...(history?.past ?? []), root],
              present: {
                ...imported,
                id: root.id,
                task: root.task,
                revision: root.revision,
              },
              future: [],
            });
            setPath([]);
            setValidation(null);
            setError("");
            setJsonValid(true);
          } catch (failure) {
            setError(
              failure instanceof Error ? failure.message : String(failure),
            );
            setDiagnosticsSignal((value) => value + 1);
          }
          event.target.value = "";
        }}
      />
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col"
        inert={saving}
        aria-busy={saving}
      >
        {path.length > 0 && (
          <div className="flex h-9 shrink-0 items-center gap-2 border-b border-border px-3 text-xs">
            <TooltipHint text={t("help.parentFlow")}>
              <Button
                size="sm"
                variant="ghost"
                isDisabled={!jsonValid}
                onPress={() => setPath((current) => current.slice(0, -1))}
              >
                {t("parentFlow")}
              </Button>
            </TooltipHint>
            <span className="truncate text-muted">{path.join(" / ")}</span>
          </div>
        )}
        {loading && (
          <p role="status" className="px-4 py-5 text-sm text-muted">
            {t("loading")}
          </p>
        )}
        {!loading && !root && (
          <div className="workspace-scrollbar min-h-0 flex-1 overflow-auto p-4">
            {diagnosticsPanel}
          </div>
        )}
        {!loading &&
          root &&
          graph &&
          (advanced ? (
            <section
              className="flex min-h-0 min-w-0 flex-1 flex-col"
              aria-label={t("definition")}
            >
              <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2">
                <span className="text-sm font-medium">{t("definition")}</span>
                <Button
                  size="sm"
                  variant="outline"
                  isDisabled={!jsonValid}
                  onPress={() => {
                    if (!focusInvalidFlowJson()) setAdvanced(false);
                  }}
                >
                  {t("backToCanvas")}
                </Button>
              </div>
              <div className="workspace-scrollbar min-h-0 flex-1 overflow-auto p-4">
                <FlowJsonField
                  label={t("definition")}
                  value={root}
                  onChange={(next) => {
                    if (!isTaskFlowDraft(next))
                      throw new Error(t("invalidImport"));
                    setHistory(
                      (current) =>
                        current && {
                          past: [...current.past, current.present].slice(-60),
                          present: {
                            ...next,
                            id: current.present.id,
                            task: current.present.task,
                            revision: current.present.revision,
                          },
                          future: [],
                        },
                    );
                  }}
                  onValidityChange={setJsonValid}
                />
              </div>
            </section>
          ) : (
            <TaskFlowEditor
              key={path.join("/") || root.id}
              graph={graph}
              onChange={changeGraph}
              providers={providers}
              outputSchema={
                path.length
                  ? { type: "object" }
                  : (tasks.find((item) => item.task === task)?.output_schema ??
                    {})
              }
              onEnterSubflow={(id) => {
                if (!focusInvalidFlowJson())
                  setPath((current) => [...current, id]);
              }}
              onValidityChange={setJsonValid}
              schemePanel={schemePanel}
              diagnosticsPanel={diagnosticsPanel}
              diagnosticsSignal={diagnosticsSignal}
              onDiagnosticsOpen={preview.activate}
              graphPath={path}
              preview={preview.result}
              previewIndex={preview.cursor}
              previewBusy={preview.busy || preview.stale}
              previewSessionKey={JSON.stringify(preview.scope)}
              previewOverrides={preview.overrides}
              onPreviewOverride={preview.setOverride}
              onResetPreviewOverride={preview.resetOverride}
              previewFocus={previewFocus}
              onPreviewFocus={focusPreview}
            />
          ))}
      </div>
    </main>
  );
}
