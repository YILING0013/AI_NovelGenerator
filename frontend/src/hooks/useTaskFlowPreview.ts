"use client";

import { apiPost } from "@/lib/api";
import type { TaskFlow } from "@/types/taskFlow";
import type {
  FlowPreviewOverride,
  FlowPreviewScope,
  TaskFlowPreviewResult,
} from "@/types/taskFlowPreview";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 只比较影响执行的数据，拖动节点和修改标题不重新读取小说。
 * Args: flow 当前完整任务图。
 * Returns: 不包含布局和显示名称的执行定义。
 */
export function previewExecutionDefinition(flow: TaskFlow): unknown {
  const definition = Object.fromEntries(Object.entries(flow).filter(([name]) => !["editor", "name", "revision"].includes(name)));
  return {
    ...definition,
    nodes: flow.nodes.map((node) => Object.fromEntries(Object.entries(node).filter(([name]) => name !== "label"))),
    subflows: Object.fromEntries(
      Object.entries(flow.subflows).map(([id, child]) => [id, previewExecutionDefinition(child)]),
    ),
  };
}

/**
 * 管理编辑器内的资料快照、临时示例和回放游标。
 * Args: flow 当前草稿；ready 定义是否可解析且已加载完成。
 * Returns: 当前预览与只作用于本会话的操作。
 */
export function useTaskFlowPreview(flow: TaskFlow | undefined, ready: boolean) {
  const [enabled, setEnabled] = useState(false);
  const [executionScope, setExecutionScope] = useState<string | null>(null);
  const [scenario, setScenario] = useState<{
    flowId: string | undefined;
    scope: FlowPreviewScope;
    overrides: FlowPreviewOverride[];
  }>({ flowId: flow?.id, scope: {}, overrides: [] });
  if (flow && scenario.flowId !== flow.id) {
    setExecutionScope(null);
    setScenario({
      flowId: flow.id,
      scope: scenario.scope.novel_id ? { novel_id: scenario.scope.novel_id } : {},
      overrides: [],
    });
  }
  const [snapshot, setSnapshot] = useState<{ key: string; scopeKey: string; result: TaskFlowPreviewResult } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  const [cursor, setCursor] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const autoplay = useRef(false);
  const requestGeneration = useRef(0);
  const scopeKey = JSON.stringify([flow?.id, scenario.scope]);
  const requested = executionScope === scopeKey;
  const requestPayload = JSON.stringify({ definition: flow, scope: scenario.scope, overrides: scenario.overrides });
  const key = JSON.stringify([flow ? previewExecutionDefinition(flow) : null, scenario.scope, scenario.overrides, revision]);
  const payloadRef = useRef(requestPayload);
  useEffect(() => { payloadRef.current = requestPayload; }, [requestPayload]);

  useEffect(() => {
    if (!requested || !ready || !flow) return;
    const controller = new AbortController();
    const generation = ++requestGeneration.current;
    const shouldPlay = autoplay.current;
    autoplay.current = false;
    setPlaying(false);
    setCursor(-1);
    setLoading(true);
    setFailure(null);
    // 只有用户执行过当前范围，草稿和示例的后续修改才自动重算。
    const timer = window.setTimeout(async () => {
      try {
        const result = await apiPost<TaskFlowPreviewResult>(
          "/api/task-flows/preview",
          JSON.parse(payloadRef.current),
          { signal: controller.signal },
        );
        if (controller.signal.aborted || generation !== requestGeneration.current) return;
        setSnapshot((previous) => ({
          key,
          scopeKey,
          result: result.valid && result.status === "error" && !result.nodes.length && previous?.scopeKey === scopeKey
            ? { ...result, nodes: previous.result.nodes, steps: previous.result.steps }
            : result,
        }));
        setCursor(shouldPlay && result.steps.length ? 0 : -1);
        setPlaying(shouldPlay && result.status === "ready" && result.steps.length > 1);
      } catch (error) {
        if (!controller.signal.aborted && generation === requestGeneration.current) {
          setFailure({ key, message: error instanceof Error ? error.message : String(error) });
        }
      } finally {
        if (!controller.signal.aborted && generation === requestGeneration.current) setLoading(false);
      }
    }, shouldPlay ? 0 : 400);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
    // 请求由执行内容触发，不能把含画布坐标的 flow 引用加入依赖。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested, ready, key]);

  const current = requested && snapshot?.key === key && ready && !loading && !failure;
  const result = requested && snapshot?.scopeKey === scopeKey ? snapshot.result : null;
  const busy = requested && ready && (loading || (snapshot?.key !== key && failure?.key !== key));
  const playable = Boolean(current && result?.status === "ready" && result.steps.length);
  useEffect(() => {
    if (!playing || !playable || !result) return;
    if (cursor >= result.steps.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setCursor((value) => value + 1), 900);
    return () => window.clearTimeout(timer);
  }, [playing, playable, cursor, result]);

  const execute = useCallback(() => {
    if (!ready) return;
    autoplay.current = true;
    setEnabled(true);
    setExecutionScope(scopeKey);
    setRevision((value) => value + 1);
  }, [ready, scopeKey]);

  const setScope = useCallback((scope: FlowPreviewScope) => {
    setEnabled(true);
    // 范围变化立即撤销旧请求，新的范围必须由用户再次执行。
    requestGeneration.current += 1;
    autoplay.current = false;
    setExecutionScope(null);
    setPlaying(false);
    setCursor(-1);
    setLoading(false);
    setFailure(null);
    setSnapshot(null);
    setScenario((previous) => ({ ...previous, scope, overrides: [] }));
  }, []);

  const setOverride = useCallback((override: FlowPreviewOverride) => {
    setPlaying(false);
    setScenario((previous) => ({
      ...previous,
      overrides: [
        ...previous.overrides.filter((item) => !(item.instance_path === override.instance_path
          && item.port === override.port && JSON.stringify(item.path) === JSON.stringify(override.path))),
        override,
      ],
    }));
  }, []);

  const resetOverride = useCallback((override: FlowPreviewOverride) => {
    setPlaying(false);
    setScenario((previous) => ({
      ...previous,
      overrides: previous.overrides.filter((item) => !(item.instance_path === override.instance_path
        && item.port === override.port && JSON.stringify(item.path) === JSON.stringify(override.path))),
    }));
  }, []);

  return {
    enabled,
    activate: useCallback(() => setEnabled(true), []),
    scope: scenario.scope,
    setScope,
    overrides: scenario.overrides,
    setOverride,
    resetOverride,
    result,
    error: requested && failure?.key === key ? failure.message : "",
    busy,
    stale: Boolean(result && !current),
    canExecute: Boolean(flow && ready && !busy),
    playable,
    cursor: current ? cursor : -1,
    playing: playing && playable,
    execute,
    pause: () => setPlaying(false),
    play: () => {
      if (!playable || !result) return;
      if (cursor < 0 || cursor >= result.steps.length - 1) setCursor(0);
      setPlaying(true);
    },
    next: () => {
      setPlaying(false);
      if (playable && result) setCursor((value) => Math.min(value + 1, result.steps.length - 1));
    },
    restart: () => {
      if (playable) { setCursor(0); setPlaying(true); }
    },
    seek: (index: number) => { setPlaying(false); setCursor(index); },
  };
}

export type TaskFlowPreviewState = ReturnType<typeof useTaskFlowPreview>;
