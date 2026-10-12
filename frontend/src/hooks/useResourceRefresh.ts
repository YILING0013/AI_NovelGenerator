"use client";

import { useEffect, useRef } from "react";
import { subscribeResourceChanges } from "@/lib/resourceChanges";

/** 保存通知和页面重新激活都刷新已保存资料，不改本地编辑稿。 */
export function useResourceRefresh(novelId: string | undefined, refresh: () => void | Promise<unknown>, active = true): void {
  const callback = useRef(refresh);
  useEffect(() => { callback.current = refresh; }, [refresh]);
  useEffect(() => {
    if (!novelId || !active) return;
    let queued = false;
    let current = true;
    const reload = () => {
      if (queued) return;
      queued = true;
      queueMicrotask(() => { queued = false; if (current) void callback.current(); });
    };
    reload();
    const unsubscribe = subscribeResourceChanges((notice) => {
      if (!notice.novelId || notice.novelId === novelId) reload();
    });
    return () => { current = false; unsubscribe(); };
  }, [novelId, active]);
}
