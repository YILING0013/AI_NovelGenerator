"use client";

import { createContext, useContext, useState, type ComponentProps, type ReactNode } from "react";
import { Modal } from "@heroui/react";

export const RetainedViewActive = createContext(true);

/**
 * 功能：保留访问过的工作区，切换时只隐藏，让生成请求和候选留在原处。
 * Args: activeKey 当前工作区，空值隐藏全部；children 当前内容。
 * Returns: 保持组件身份的工作区列表。
 */
export function RetainedViews({ activeKey, children }: { activeKey: string | null; children: ReactNode }) {
  const parentActive = useContext(RetainedViewActive);
  const [views, setViews] = useState<Record<string, ReactNode>>({});
  // 只保存父组件传入的新内容；隐藏后继续使用离开前的参数，不跟随别的页面变化。
  if (activeKey !== null && views[activeKey] !== children) {
    setViews({ ...views, [activeKey]: children });
  }
  return Object.entries(views).map(([key, content]) => (
    <div key={key} hidden={key !== activeKey} className={key === activeKey ? "flex h-full min-h-0 min-w-0 flex-1 flex-col" : "hidden"}>
      <RetainedViewActive.Provider value={parentActive && key === activeKey}>{content}</RetainedViewActive.Provider>
    </div>
  ));
}

/**
 * 功能：工作区隐藏时同步收起 Portal 弹窗，保留其外层的生成任务与草稿。
 * Args: props HeroUI 弹窗属性。
 * Returns: 仅当前工作区可见时打开的标准弹窗。
 */
export function RetainedModalBackdrop({ isOpen, onOpenChange, ...props }: ComponentProps<typeof Modal.Backdrop>) {
  const active = useContext(RetainedViewActive);
  return <Modal.Backdrop {...props} isOpen={active && isOpen} onOpenChange={(open) => { if (active) onOpenChange?.(open); }} />;
}
