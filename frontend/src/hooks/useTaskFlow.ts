"use client";

import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import { useTranslations } from "next-intl";
import {
  ApiRequestError,
  apiGet,
  apiPostSSE,
  type ApiFieldErrors,
} from "@/lib/api";
import {
  DEFAULT_GENERATION_PARAMS,
  buildGenerationParamsPayload,
  type GenerationParamsValue,
} from "@/components/shared/GenerationParamsCollapse";
import type {
  AgentContinuation,
  CachedFlowNode,
  FlowNodeEvent,
  FlowRef,
  FlowSummary,
  TaskFlow,
  TaskFlowRequest,
  TaskFlowRunMode,
} from "@/types/taskFlow";
import { taskFlowDefaultInputs } from "@/types/taskFlow";
import type { AppConfig } from "@/types/config";

export interface TaskFlowSetup { flow_ref: FlowRef; inputs: Record<string, unknown>; params: GenerationParamsValue }

/** 功能：让原 AI 操作使用选定任务图并保留本轮重试所需的原始输入和完成节点。Args: task 原任务名。Returns: 表单状态与同入口执行方法。 */
export function useTaskFlow(task: string) {
  const t = useTranslations("taskFlows");
  const loadNetworkError = t("loadNetworkError");
  const [flows, setFlows] = useState<FlowSummary[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const defaultProviderRef = useRef("");
  const configEpoch = useRef(0);
  const defaultFlowRef = useRef<FlowRef | null>(null);
  const [definition, setDefinition] = useState<TaskFlow | null>(null);
  const [inputs, updateInputs] = useState<Record<string, unknown>>({});
  const [params, updateParams] = useState<GenerationParamsValue>({
    ...DEFAULT_GENERATION_PARAMS,
  });
  const attempt = useRef<{
    url: string;
    request: TaskFlowRequest;
    nodes: CachedFlowNode[];
    completed: boolean;
    networkInterrupted?: boolean;
    repair?: Record<string, unknown>;
  } | null>(null);
  const activeSignal = useRef<AbortSignal | null>(null);
  const [events, setEvents] = useState<FlowNodeEvent[]>([]);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<ApiFieldErrors>({});
  const [jsonDiagnostic, setJsonDiagnostic] = useState<{
    duplicate_path: string;
    duplicate_path_length: number;
    duplicate_path_truncated: boolean;
    raw_output: string;
    raw_output_truncated: boolean;
    raw_output_length: number;
    raw_output_untrusted: true;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [canRepair, setCanRepair] = useState(false);
  const [repairing, setRepairing] = useState(false);
  const [agentContinuation, setAgentContinuation] = useState<AgentContinuation | null>(null);
  const [continuationAdditionalRounds, setContinuationAdditionalRounds] = useState<number | null>(null);
  const continuationRef = useRef<AgentContinuation | null>(null);
  const continuationEpoch = useRef(0);
  const [continuing, setContinuing] = useState(false);
  const clearContinuation = useCallback(() => {
    continuationEpoch.current += 1;
    continuationRef.current = null;
    setAgentContinuation(null);
    setContinuationAdditionalRounds(null);
  }, []);
  const setInputs = useCallback((value: SetStateAction<Record<string, unknown>>) => {
    clearContinuation();
    updateInputs(value);
  }, [clearContinuation]);
  const setParams = useCallback((value: SetStateAction<GenerationParamsValue>) => {
    clearContinuation();
    updateParams(value);
  }, [clearContinuation]);
  // 刷新目录和手动选修订共用代次，旧目录不能覆盖更新的选择。
  const selection = useRef(0);

  const select = useCallback(async (ref: FlowRef, preserveInputs = false) => {
    clearContinuation();
    const requestId = ++selection.current;
    setLoading(true);
    setError("");
    try {
      const next = await apiGet<TaskFlow>(
        `/api/task-flows/${encodeURIComponent(ref.id)}?revision=${ref.revision}`,
      );
      if (selection.current !== requestId) return;
      setDefinition(next);
      setFieldErrors({});
      setJsonDiagnostic(null);
      const defaults = taskFlowDefaultInputs(next);
      setInputs((current) =>
        preserveInputs
          ? Object.fromEntries(
              Object.entries(defaults).map(([name, value]) => [
                name,
                Object.hasOwn(current, name) ? current[name] : value,
              ]),
            )
          : defaults,
      );
      setEvents([]);
    } catch (failure) {
      if (selection.current === requestId) {
        const disconnected = failure instanceof TypeError && ["Failed to fetch", "NetworkError when attempting to fetch resource.", "Load failed"].includes(failure.message);
        setError(disconnected ? loadNetworkError : failure instanceof Error ? failure.message : String(failure));
      }
    } finally {
      if (selection.current === requestId) setLoading(false);
    }
  }, [clearContinuation, setInputs, loadNetworkError]);

  const loadFlows = useCallback(async (previousSelection?: FlowRef | null) => {
    clearContinuation();
    const requestId = ++selection.current;
    const requestedConfigEpoch = configEpoch.current;
    setLoading(true);
    setError("");
    try {
      const [catalog, config] = await Promise.all([
        apiGet<{ flows: FlowSummary[]; default_ref: FlowRef }>(
          `/api/task-flows?task=${encodeURIComponent(task)}`,
        ),
        apiGet<{ data: AppConfig }>("/api/config"),
      ]);
      if (selection.current !== requestId) return;
      const selectedRef =
        previousSelection?.id === defaultFlowRef.current?.id
          ? catalog.default_ref
          : (catalog.flows.find((item) => item.id === previousSelection?.id) ??
            catalog.default_ref);
      setFlows(catalog.flows);
      // 设置保存后，较早发出的配置查询不能把新默认值覆盖回去。
      if (configEpoch.current === requestedConfigEpoch) {
        setProviders(
          Object.entries(config.data.llm.providers)
            .filter(([, provider]) => provider.enabled)
            .map(([name]) => name),
        );
        defaultProviderRef.current = config.data.llm.default_provider;
      }
      defaultFlowRef.current = catalog.default_ref;
      await select(selectedRef, previousSelection !== undefined);
    } catch (failure) {
      if (selection.current !== requestId) return;
      const disconnected = failure instanceof TypeError && ["Failed to fetch", "NetworkError when attempting to fetch resource.", "Load failed"].includes(failure.message);
      setError(disconnected ? loadNetworkError : failure instanceof Error ? failure.message : String(failure));
      setLoading(false);
    }
  }, [task, select, clearContinuation, loadNetworkError]);

  useEffect(() => {
    void loadFlows();
    return () => {
      selection.current += 1;
    };
  }, [loadFlows]);

  useEffect(() => {
    const updateConfig = (event: Event) => {
      clearContinuation();
      const config = (event as CustomEvent<AppConfig>).detail;
      configEpoch.current += 1;
      defaultProviderRef.current = config.llm.default_provider;
      setProviders(Object.entries(config.llm.providers).filter(([, provider]) => provider.enabled).map(([name]) => name));
    };
    window.addEventListener("app-config-saved", updateConfig);
    return () => window.removeEventListener("app-config-saved", updateConfig);
  }, [clearContinuation]);

  /** 功能：放弃本轮并清除内存中的节点，保留表单以便重新开始。Args: 无。Returns: 本轮状态已清除。 */
  const discard = useCallback(async () => {
    attempt.current = null;
    clearContinuation();
    setCanRepair(false);
    setEvents([]);
    setError("");
    setFieldErrors({});
    setJsonDiagnostic(null);
  }, [clearContinuation]);

  /** 功能：取得本次实际使用的图版本、输入和参数。Args: 无。Returns: 可保存的设置快照，空 Provider 按当前默认值确定。 */
  const resolveSetup = (): TaskFlowSetup => {
    if (!definition) throw new Error(error || t("flowError"));
    const resolvedInputs = structuredClone(inputs);
    if (Object.hasOwn(resolvedInputs, "provider") && !resolvedInputs.provider) resolvedInputs.provider = definition.default_provider || defaultProviderRef.current;
    return { flow_ref: { id: definition.id, revision: definition.revision }, inputs: resolvedInputs, params: structuredClone(params) };
  };

  /** 功能：通过原入口生成、重试、修复或继续整理。Args: url 请求地址；scope 业务范围；signal 取消信号；retry 明确区分重试、修复与追加轮数；setup 事先保存的固定设置。Returns: 不含续跑令牌的候选和确认输入。 */
  const run = async (
    url: string,
    scope: Record<string, unknown>,
    signal: AbortSignal,
    retry: TaskFlowRunMode = false,
    setup?: TaskFlowSetup,
  ): Promise<{
    result: unknown;
    request: TaskFlowRequest;
    generationInput: unknown;
  }> => {
    if (!definition) throw new Error(error || t("flowError"));
    if (activeSignal.current && !activeSignal.current.aborted) throw new Error(t("states.running"));
    if (retry === "repair" && !attempt.current?.repair) throw new Error(t("repairUnavailable"));
    const recovering = retry === true && attempt.current?.networkInterrupted;
    const continuation = typeof retry === "object" || recovering ? continuationRef.current : null;
    if (recovering && continuation) retry = { continuation: true, additionalRounds: continuation.resume_rounds ?? 0 };
    if (typeof retry === "object" || recovering) {
      if (attempt.current && (url !== attempt.current.url || JSON.stringify(scope) !== JSON.stringify(attempt.current.request.scope))) {
        clearContinuation();
        throw new ApiRequestError({ status: 409, code: "AGENT_CONTINUATION_CHANGED", message: t("agent.continuationChanged") });
      }
      if (!continuation || !attempt.current || (!continuation.running && Date.parse(continuation.expires_at) <= Date.now())) {
        clearContinuation();
        throw new ApiRequestError({ status: 409, code: "AGENT_CONTINUATION_EXPIRED", message: t("agent.continuationExpired") });
      }
      if (typeof retry === "object" && (!Number.isInteger(retry.additionalRounds) || retry.additionalRounds < (continuation.reason === "network" ? 0 : 1) || retry.additionalRounds > 16)) throw new Error(t("agent.roundsInvalid"));
    }
    clearContinuation();
    const requestContinuationEpoch = continuationEpoch.current;
    activeSignal.current = signal;
    setCanRepair(false);
    setRepairing(retry === "repair");
    setContinuing(Boolean(continuation));
    setError("");
    setFieldErrors({});
    setJsonDiagnostic(null);
    const { use_stream, ...generationParams } =
      buildGenerationParamsPayload(setup?.params ?? params);
    if (typeof generationParams.system_prompt === "string") generationParams.system_prompt = generationParams.system_prompt.trim();
    const previous = retry ? attempt.current : null;
    const request: TaskFlowRequest = previous ? structuredClone(previous.request) : {
      request_mode: "task_flow",
      flow_ref: setup?.flow_ref ?? { id: definition.id, revision: definition.revision },
      flow_inputs: structuredClone(setup?.inputs ?? inputs),
      generation_params: generationParams,
      use_stream: Boolean(use_stream),
      scope: structuredClone(scope),
      cached_nodes: [],
    };
    if (!previous && Object.hasOwn(request.flow_inputs, "provider") && !request.flow_inputs.provider) {
      request.flow_inputs.provider = definition.default_provider || defaultProviderRef.current;
    }
    // 只重用本轮失败前完成的节点；候选校验失败后重新生成，避免重复返回同一份坏结果。
    let completed = previous && !previous.completed && retry !== "repair" ? structuredClone(previous.nodes) : [];
    request.cached_nodes = completed;
    const currentAttempt = { url: previous?.url ?? url, request, nodes: completed, completed: false, networkInterrupted: Boolean(recovering), repair: retry === "repair" ? previous?.repair : undefined };
    attempt.current = currentAttempt;
    // 继续同一轮时保留已读资料；普通重试只保留完整且可复用的节点。
    if (!continuation) setEvents(completed.map((node) => ({ ...node, state: "cached" })));
    let result: unknown;
    let checkpoint = continuation;
    let checkpointCompleted = false;
    try {
      await apiPostSSE(
        currentAttempt.url,
        continuation && typeof retry === "object"
          ? { ...request, agent_continuation: { token: continuation.token, additional_rounds: retry.additionalRounds } }
          : currentAttempt.repair ? { ...request, repair: currentAttempt.repair } : request,
        (event, data) => {
          if (signal.aborted || attempt.current !== currentAttempt) return;
          if (data.agent_continuation && continuationEpoch.current === requestContinuationEpoch) {
            checkpoint = data.agent_continuation as AgentContinuation;
            checkpointCompleted = false;
          }
          if (typeof data.node_id === "string") {
            const publicData = { ...data };
            delete publicData.agent_continuation;
            if (publicData.details && typeof publicData.details === "object") {
              publicData.details = { ...publicData.details };
              delete (publicData.details as Record<string, unknown>).agent_continuation;
            }
            const nodeEvent = {
              ...publicData,
              ...(event === "error" && data.partial_outputs ? { outputs: (data.partial_outputs as Record<string, Record<string, unknown>>)[String(data.instance_path)] } : {}),
              state: data.cached
                ? "cached"
                : (data.state ?? (event === "error" ? "failed" : "running")),
            } as FlowNodeEvent;
            setEvents((current) => {
              const index = current.findIndex(
                (item) => item.instance_path === nodeEvent.instance_path,
              );
              return index < 0
                ? [...current, nodeEvent]
                : current.map((item, i) =>
                    i === index ? { ...item, ...nodeEvent } : item,
                  );
            });
            if (
              (nodeEvent.state === "done" ||
                nodeEvent.state === "completed" ||
                nodeEvent.state === "cached") &&
              nodeEvent.outputs &&
              nodeEvent.input_fingerprint
            ) {
              const cached: CachedFlowNode = {
                node_id: nodeEvent.node_id,
                instance_path: nodeEvent.instance_path,
                input_fingerprint: nodeEvent.input_fingerprint,
                outputs: nodeEvent.outputs,
              };
              completed = [
                ...completed.filter(
                  (item) => item.instance_path !== nodeEvent.instance_path,
                ),
                cached,
              ];
              currentAttempt.nodes = completed;
              if (nodeEvent.instance_path === checkpoint?.instance_path) checkpointCompleted = true;
            }
          }
          if (event === "done") result = data.result;
        },
        { signal },
      );
      currentAttempt.completed = true;
      currentAttempt.networkInterrupted = false;
      currentAttempt.repair = undefined;
    } catch (failure) {
      let reportedFailure = failure;
      if (!signal.aborted) {
        setError(failure instanceof Error ? failure.message : String(failure));
        const returnedContinuation = failure instanceof ApiRequestError ? failure.details.agent_continuation as AgentContinuation | undefined : undefined;
        const browserDisconnected = !(failure instanceof ApiRequestError) || failure.code === "SSE_PROTOCOL_ERROR" || failure.code === "SSE_CONNECTION_LOST";
        const transientFailure = !(failure instanceof ApiRequestError) || (failure.status >= 500 && !failure.code?.startsWith("AGENT_") && !failure.details.agent_continuation_unavailable) || failure.code === "AGENT_CONTINUATION_BUSY";
        // 整个流程使用原服务端凭证；终态丢失时也不能静默新建请求。
        const resumable = returnedContinuation ?? (transientFailure && (checkpoint?.flow_recovery || !checkpointCompleted || browserDisconnected) ? checkpoint : null);
        const graphs = [definition];
        let hasAgent = false;
        while (graphs.length) {
          const graph = graphs.pop()!;
          hasAgent ||= graph.nodes.some(node => node.type === "agent");
          graphs.push(...Object.values(graph.subflows));
        }
        currentAttempt.networkInterrupted = Boolean((checkpoint?.reason === "network" && (checkpoint.flow_recovery || !checkpointCompleted || browserDisconnected)) || (browserDisconnected && hasAgent));
        if (resumable?.reason === "network") {
          currentAttempt.networkInterrupted = true;
          const message = browserDisconnected ? t("agent.browserDisconnected") : failure instanceof ApiRequestError && failure.code === "AGENT_MODEL_CONNECTION_FAILED" ? t("agent.modelDisconnected") : failure instanceof Error ? failure.message : String(failure);
          setError(message);
          // 外层表单显示同一条本地化错误，保留原错误码与详情供原有处理使用。
          reportedFailure = failure instanceof ApiRequestError ? new ApiRequestError({ ...failure, message }) : new Error(message, { cause: failure });
        }
        if (resumable?.token && continuationEpoch.current === requestContinuationEpoch && attempt.current === currentAttempt) {
          continuationRef.current = resumable;
          setAgentContinuation(resumable);
          // 暂时失败时预算可能已经追加，重试必须沿用同一个 N。
          setContinuationAdditionalRounds(resumable.token === continuation?.token && typeof retry === "object" ? retry.additionalRounds : null);
        }
        if (failure instanceof ApiRequestError) {
          const diagnostic = failure.details;
          if (failure.code === "LLM_JSON_DUPLICATE_KEY"
            && diagnostic.raw_output_untrusted === true
            && typeof diagnostic.duplicate_path === "string"
            && typeof diagnostic.duplicate_path_length === "number"
            && typeof diagnostic.duplicate_path_truncated === "boolean"
            && typeof diagnostic.raw_output === "string"
            && typeof diagnostic.raw_output_truncated === "boolean"
            && typeof diagnostic.raw_output_length === "number") {
            // 原文只供查看和导出，不放进候选、修复请求或节点缓存。
            setJsonDiagnostic({
              duplicate_path: diagnostic.duplicate_path,
              duplicate_path_length: diagnostic.duplicate_path_length,
              duplicate_path_truncated: diagnostic.duplicate_path_truncated,
              raw_output: diagnostic.raw_output,
              raw_output_truncated: diagnostic.raw_output_truncated,
              raw_output_length: diagnostic.raw_output_length,
              raw_output_untrusted: true,
            });
          }
          // 普通 JSON 失败也保留资料摘要，不能只依赖 SSE 事件。
          const partialOutputs = failure.details.partial_outputs as Record<string, Record<string, unknown>> | undefined;
          if (partialOutputs) setEvents((current) => {
            const next = [...current];
            for (const [instancePath, outputs] of Object.entries(partialOutputs)) {
              const index = next.findIndex((event) => event.instance_path === instancePath);
              const previous = next[index];
              const failedPath = failure.details.instance_path ?? resumable?.instance_path;
              const state = failedPath === instancePath || outputs.collected_context ? "failed" : previous?.state ?? "done";
              const event = { ...previous, node_id: previous?.node_id ?? instancePath.split("/").at(-1)!, instance_path: instancePath, outputs, state };
              if (index < 0) next.push(event); else next[index] = event;
            }
            return next;
          });
          const repair = failure.details.repair;
          if (repair && typeof repair === "object" && !Array.isArray(repair)) {
            currentAttempt.repair = repair as Record<string, unknown>;
            // 图已完成但结果不合格，普通重试不能再复用这份坏结果。
            currentAttempt.completed = true;
          } else if (failure.status < 500) {
            currentAttempt.repair = undefined;
          }
          setFieldErrors(
            Object.fromEntries(
              Object.entries(failure.fieldErrors).map(([key, value]) => [
                key.replace(/^body\./, "").replace(/^flow_inputs\./, ""),
                value,
              ]),
            ),
          );
          if (failure.code?.includes("CACHE")) {
            currentAttempt.nodes = [];
          }
        }
        setCanRepair(Boolean(currentAttempt.repair));
      }
      throw reportedFailure;
    } finally {
      if (activeSignal.current === signal) activeSignal.current = null;
      setRepairing(false);
      setContinuing(false);
      if (signal.aborted && attempt.current === currentAttempt) await discard();
    }
    const envelope = result as
      | { basis?: { flow_snapshot?: { business_input?: unknown } } }
      | undefined;
    return {
      result,
      request: { ...request, cached_nodes: [] },
      generationInput: envelope?.basis?.flow_snapshot?.business_input,
    };
  };

  return {
    task,
    flows,
    providers,
    definition,
    inputs,
    setInputs,
    params,
    setParams,
    discard,
    events,
    error,
    fieldErrors,
    jsonDiagnostic,
    loading,
    canRepair,
    repairing,
    agentContinuation,
    continuationAdditionalRounds,
    continuing,
    select,
    refresh: () => loadFlows(definition),
    resolveSetup,
    run,
  };
}
export type TaskFlowState = ReturnType<typeof useTaskFlow>;
