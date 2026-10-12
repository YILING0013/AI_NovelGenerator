import type { ResourceRef } from "@/types/assistant";

export interface ResourceChangeNotice { path?: string; novelId?: string; resources?: ResourceRef[]; source: "manual" | "assistant" }
const listeners = new Set<(notice: ResourceChangeNotice) => void>();

/** 成功保存后通知已打开的工作台；通知本身不触发模型调用。
 * Args: notice 保存范围和来源。
 * Returns: 无。
 */
export function notifyResourceChange(notice: ResourceChangeNotice): void {
  listeners.forEach((listener) => listener(notice));
}

/** 订阅业务资料变化，供常驻页面刷新已保存内容。
 * Args: listener 接收成功保存通知。
 * Returns: 取消订阅函数。
 */
export function subscribeResourceChanges(listener: (notice: ResourceChangeNotice) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
