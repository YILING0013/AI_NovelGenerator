"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { usePathname, useSearchParams, useSelectedLayoutSegments } from "next/navigation";
import { useLocale } from "next-intl";
import BookshelfContent from "@/components/bookshelf/BookshelfContent";
import WritingContent from "@/components/writing/WritingContent";
import { RetainedViewActive, RetainedViews } from "./RetainedViews";

export interface WorkspaceHistoryTraversal {
  session: string;
  from: number;
  to: number;
  sourcePathname?: string;
}

/**
 * 功能：在不会随站内导航卸载的布局中保留书架和小说工作区。
 * Args: children 设置、流程编辑器等普通路由的内容。
 * Returns: 当前页面及仍在后台生成的工作区。
 */
export function WorkspacePages({ children }: { children: ReactNode }) {
  const historyTraversalRef = useRef<((event: PopStateEvent, traversal: WorkspaceHistoryTraversal | null) => void) | null>(null);
  const historyPosition = useRef<{ session: string; index: number | null; pathname: string } | null>(null);
  useLayoutEffect(() => {
    const history = window.history;
    const originalPush = history.pushState;
    const originalReplace = history.replaceState;
    const position = historyPosition.current ??= { session: crypto.randomUUID(), index: 0, pathname: window.location.pathname };
    let enabled = true;
    // Next 的 passive effect 捕获这些下层方法；无论 router.push 还是原生调用都只记一次。
    const pushState: History["pushState"] = (data, unused, url) => {
      if (!enabled) return originalPush.call(history, data, unused, url);
      const session = position.index === null ? crypto.randomUUID() : position.session;
      const index = position.index === null ? 0 : position.index + 1;
      originalPush.call(history, { ...data, workspaceHistorySession: session, writingHierarchyIndex: index }, unused, url);
      position.session = session; position.index = index;
      position.pathname = window.location.pathname;
    };
    const replaceState: History["replaceState"] = (data, unused, url) => {
      if (!enabled) return originalReplace.call(history, data, unused, url);
      const session = position.index === null ? crypto.randomUUID() : position.session;
      // Next 可在本监听器收到 popstate 前提交目标 URL；保留物理历史项的编号，不能覆盖成离开位置。
      const entry = history.state;
      const traversing = entry?.workspaceHistorySession === session && Number.isSafeInteger(entry?.writingHierarchyIndex) && entry.writingHierarchyIndex !== position.index;
      const index = traversing ? entry.writingHierarchyIndex : position.index ?? 0;
      originalReplace.call(history, { ...data, workspaceHistorySession: session, writingHierarchyIndex: index }, unused, url);
      if (!traversing) {
        position.session = session; position.index = index;
        position.pathname = window.location.pathname;
      }
    };
    history.pushState = pushState;
    history.replaceState = replaceState;
    replaceState(history.state, "");
    // 在 Next 之前同步物理位置，再把可信距离交给当前活动工作区；旧会话不参与推算。
    const onPop = (event: PopStateEvent) => {
      const target = event.state?.workspaceHistorySession === position.session
        && Number.isSafeInteger(event.state?.writingHierarchyIndex) ? event.state.writingHierarchyIndex as number : null;
      const traversal = position.index !== null && target !== null
        ? { session: position.session, from: position.index, to: target, sourcePathname: position.pathname } : null;
      position.index = target;
      position.pathname = window.location.pathname;
      historyTraversalRef.current?.(event, traversal);
    };
    // StartupGate 异步放行时 Next 已先注册监听；必须在捕获阶段先读取原位置。
    window.addEventListener("popstate", onPop, true);
    return () => {
      // Next 可能仍持有旧包装；StrictMode 重装后旧闭包必须只透传，不能再次计数。
      enabled = false;
      if (history.pushState === pushState) history.pushState = originalPush;
      if (history.replaceState === replaceState) history.replaceState = originalReplace;
      window.removeEventListener("popstate", onPop, true);
    };
  }, []);
  const locale = useLocale();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const segments = useSelectedLayoutSegments();
  const writingId = segments[0] === "writing" ? segments[1] : undefined;
  const pagePath = writingId ? `/${locale}/writing/${writingId}` : segments.length === 0 ? `/${locale}` : null;
  const [queries, setQueries] = useState<Record<string, string>>({});
  const query = searchParams.toString();
  // 设置使用并行弹窗路由，URL 的查询串会清空，但底下的小说位置不能跟着丢失。
  if (pagePath && pathname === pagePath && queries[pagePath] !== query) {
    setQueries({ ...queries, [pagePath]: query });
  }
  const pageQuery = pagePath ? queries[pagePath] ?? query : query;
  const sessionKey = writingId === "new" ? `${pagePath}:${new URLSearchParams(pageQuery).get("draft") ?? "manual"}` : pagePath;
  return (
    <>
      <RetainedViewActive.Provider value={pathname === pagePath}>
        <RetainedViews activeKey={sessionKey}>
          {writingId ? (
            <WritingContent
              mode={writingId === "new" ? "create" : "edit"}
              novelId={writingId === "new" ? undefined : writingId}
              query={pageQuery}
              active={pathname === pagePath}
              historyTraversalRef={historyTraversalRef}
            />
          ) : <BookshelfContent />}
        </RetainedViews>
      </RetainedViewActive.Provider>
      {children}
    </>
  );
}
