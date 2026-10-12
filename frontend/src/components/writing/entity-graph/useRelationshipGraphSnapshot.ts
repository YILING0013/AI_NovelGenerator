"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "@/lib/api";
import type {
  CharacterFactionBindingResponseV1,
  CharacterRelationResponseV1,
  CharacterResponseV1,
} from "@/types/character";
import type { CoreFaction, FactionRelation } from "@/types/novel";
import { createRelationshipGraphSnapshot } from "./graphModel";
import type { RelationshipGraphSnapshotV1 } from "./graphTypes";

export const RELATIONSHIP_GRAPH_POLL_INTERVAL_MS = 30_000;

export type RelationshipGraphLoadStatus =
  | "idle"
  | "loading"
  | "ready"
  | "refreshing"
  | "error"
  | "stale";

export interface UseRelationshipGraphSnapshotResult {
  snapshot: RelationshipGraphSnapshotV1 | null;
  status: RelationshipGraphLoadStatus;
  error: string | null;
  isStale: boolean;
  lastAttemptAt: string | null;
  refresh: () => Promise<void>;
}

type RelationshipGraphHookState = Omit<UseRelationshipGraphSnapshotResult, "refresh"> & {
  novelId: string | null;
};

interface UseRelationshipGraphSnapshotOptions {
  pollIntervalMs?: number;
  loader?: typeof loadRelationshipGraphSnapshot;
}

interface DataResponse<T> {
  data: T[];
}

/**
 * 功能：按版本和更新时间排列两组角色势力归属，让同一 ID 的最新记录排在前面。
 * Args:
 *   activeBindings: 活动态接口返回的绑定记录。
 *   inactiveBindings: 非活动态接口返回的绑定记录。
 * Returns:
 *   保留全部记录并把同 ID 的最新版本放在前面；重复项仍交给关系图检查。
 */
export function orderBindingsForRelationshipGraph(
  activeBindings: CharacterFactionBindingResponseV1[],
  inactiveBindings: CharacterFactionBindingResponseV1[],
): CharacterFactionBindingResponseV1[] {
  const groups = new Map<string, CharacterFactionBindingResponseV1[]>();
  for (const binding of [...activeBindings, ...inactiveBindings]) {
    const group = groups.get(binding.binding_id) ?? [];
    group.push(binding);
    groups.set(binding.binding_id, group);
  }

  return [...groups.values()].flatMap((group) =>
    group.sort((left, right) => {
      if (left.version !== right.version) return right.version - left.version;

      const updatedAtDifference = Date.parse(right.updated_at) - Date.parse(left.updated_at);
      if (Number.isFinite(updatedAtDifference) && updatedAtDifference !== 0) {
        return updatedAtDifference;
      }

      // 极端情况下同版本、同时间却状态冲突，优先保守地采用 inactive，同时保留重复诊断。
      return Number(left.is_active) - Number(right.is_active);
    }),
  );
}

/**
 * 功能：并行读取构建统一关系图谱所需的六组正式数据，并在全部成功后生成原子快照。
 * Args:
 *   novelId: 当前小说 ObjectId。
 *   signal: 六组请求共享的中止信号。
 * Returns:
 *   完整的 V1 图谱快照；任一请求失败时整体抛错，不返回部分数据。
 */
export async function loadRelationshipGraphSnapshot(
  novelId: string,
  signal: AbortSignal,
): Promise<RelationshipGraphSnapshotV1> {
  const encodedNovelId = encodeURIComponent(novelId);
  const [
    charactersResponse,
    factionsResponse,
    characterRelationsResponse,
    factionRelationsResponse,
    activeBindingsResponse,
    inactiveBindingsResponse,
  ] = await Promise.all([
    apiGet<DataResponse<CharacterResponseV1>>(`/api/characters/novel/${encodedNovelId}`, { signal }),
    apiGet<DataResponse<CoreFaction>>(`/api/factions/novel/${encodedNovelId}`, { signal }),
    apiGet<DataResponse<CharacterRelationResponseV1>>(
      `/api/character-relations/novel/${encodedNovelId}`,
      { signal },
    ),
    apiGet<DataResponse<FactionRelation>>(`/api/faction-relations/novel/${encodedNovelId}`, { signal }),
    apiGet<DataResponse<CharacterFactionBindingResponseV1>>(
      `/api/character-faction-bindings/novel/${encodedNovelId}?is_active=true`,
      { signal },
    ),
    apiGet<DataResponse<CharacterFactionBindingResponseV1>>(
      `/api/character-faction-bindings/novel/${encodedNovelId}?is_active=false`,
      { signal },
    ),
  ]);

  return createRelationshipGraphSnapshot(novelId, {
    characters: charactersResponse.data,
    factions: factionsResponse.data,
    characterRelations: characterRelationsResponse.data,
    factionRelations: factionRelationsResponse.data,
    // 两个显式状态请求在原子边界内合并；状态切换瞬间的跨响应重复按最新版本优先。
    bindings: orderBindingsForRelationshipGraph(
      activeBindingsResponse.data,
      inactiveBindingsResponse.data,
    ),
  });
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException
    ? error.name === "AbortError"
    : error instanceof Error && error.name === "AbortError";
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * 功能：管理图谱原子快照、串行轮询、页面可见性刷新和旧请求取消。
 * Args:
 *   novelId: 当前小说 ObjectId；创建模式下可为空。
 *   options: 测试或特殊宿主可覆盖轮询间隔与加载器。
 * Returns:
 *   当前快照、加载/过期状态、错误和手动刷新入口。
 */
export function useRelationshipGraphSnapshot(
  novelId?: string,
  options: UseRelationshipGraphSnapshotOptions = {},
): UseRelationshipGraphSnapshotResult {
  const pollIntervalMs = options.pollIntervalMs ?? RELATIONSHIP_GRAPH_POLL_INTERVAL_MS;
  const loader = options.loader ?? loadRelationshipGraphSnapshot;
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);
  const snapshotCacheRef = useRef<{
    novelId: string;
    snapshot: RelationshipGraphSnapshotV1;
  } | null>(null);
  const [state, setState] = useState<RelationshipGraphHookState>({
    novelId: null,
    snapshot: null,
    status: "idle",
    error: null,
    isStale: false,
    lastAttemptAt: null,
  });

  useEffect(() => {
    let disposed = false;
    // effect 因加载器或轮询配置重建时，继续持有同一小说最后一次完整快照。
    const cachedSnapshot = snapshotCacheRef.current;
    let currentSnapshot: RelationshipGraphSnapshotV1 | null = null;
    if (cachedSnapshot && cachedSnapshot.novelId === novelId) {
      currentSnapshot = cachedSnapshot.snapshot;
    }
    let inFlight: Promise<void> | null = null;
    let controller: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const clearPollTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    if (!novelId) {
      refreshRef.current = async () => undefined;
      return () => undefined;
    }

    const scheduleNextPoll = () => {
      clearPollTimer();
      if (disposed || document.visibilityState !== "visible") return;
      // 完成后再开始计时，保证慢请求不会与下一轮轮询重叠。
      timer = setTimeout(() => {
        void runLoad();
      }, pollIntervalMs);
    };

    const runLoad = (): Promise<void> => {
      if (disposed || inFlight) return inFlight ?? Promise.resolve();
      clearPollTimer();
      const requestController = new AbortController();
      controller = requestController;
      const attemptAt = new Date().toISOString();
      setState((previous) => ({
        novelId,
        snapshot: currentSnapshot,
        status: currentSnapshot ? "refreshing" : "loading",
        error: null,
        isStale: currentSnapshot ? previous.isStale : false,
        lastAttemptAt: attemptAt,
      }));

      const request = loader(novelId, requestController.signal)
        .then((nextSnapshot) => {
          if (disposed || requestController.signal.aborted) return;
          currentSnapshot = nextSnapshot;
          snapshotCacheRef.current = { novelId, snapshot: nextSnapshot };
          setState({
            novelId,
            snapshot: nextSnapshot,
            status: "ready",
            error: null,
            isStale: false,
            lastAttemptAt: attemptAt,
          });
        })
        .catch((error: unknown) => {
          if (disposed || requestController.signal.aborted || isAbortError(error)) return;
          // 任一原子请求失败后立刻取消共享信号，防止同批其余请求游离到下一轮轮询。
          requestController.abort(error);
          // 后台刷新失败时保留最后一次完整快照，绝不把部分响应覆盖到图面。
          setState({
            novelId,
            snapshot: currentSnapshot,
            status: currentSnapshot ? "stale" : "error",
            error: getErrorMessage(error),
            isStale: Boolean(currentSnapshot),
            lastAttemptAt: attemptAt,
          });
        })
        .finally(() => {
          if (inFlight === request) inFlight = null;
          if (controller === requestController) controller = null;
          if (!disposed) scheduleNextPoll();
        });
      inFlight = request;
      return request;
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void runLoad();
      } else {
        clearPollTimer();
      }
    };
    const handleFocus = () => {
      if (document.visibilityState === "visible") void runLoad();
    };

    refreshRef.current = runLoad;
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleFocus);
    void runLoad();

    return () => {
      disposed = true;
      clearPollTimer();
      controller?.abort();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleFocus);
      refreshRef.current = async () => undefined;
    };
  }, [loader, novelId, pollIntervalMs]);

  const refresh = useCallback(() => refreshRef.current(), []);
  if (!novelId) {
    return {
      snapshot: null,
      status: "idle",
      error: null,
      isStale: false,
      lastAttemptAt: null,
      refresh,
    };
  }
  if (state.novelId !== novelId) {
    return {
      snapshot: null,
      status: "loading",
      error: null,
      isStale: false,
      lastAttemptAt: null,
      refresh,
    };
  }
  return {
    snapshot: state.snapshot,
    status: state.status,
    error: state.error,
    isStale: state.isStale,
    lastAttemptAt: state.lastAttemptAt,
    refresh,
  };
}
