"use client";

import { Button } from "@heroui/react";
import { useRef } from "react";

interface EdgeAction {
  label: string;
  onPress: () => void;
  expanded: boolean;
}

/**
 * 在侧栏边缘显示与分隔线相连的曲面折叠手柄。
 *
 * Args:
 *   controls: 被控制的侧栏 ID。
 *   leftAction: 向左操作；可与向右操作同时显示。
 *   rightAction: 向右操作。
 *   side: 手柄贴合侧栏的哪一侧，右侧详情栏使用 left。
 *   className: 所在工作区的响应式显隐样式。
 *
 * Returns:
 *   支持键盘、文字提示和单向或双向操作的边缘手柄。
 */
export default function SidebarEdgeHandle({ controls, leftAction, rightAction, side = "right", className = "" }: {
  controls: string;
  leftAction?: EdgeAction;
  rightAction?: EdgeAction;
  side?: "left" | "right";
  className?: string;
}) {
  const handleRef = useRef<HTMLDivElement>(null);
  const double = Boolean(leftAction && rightAction);
  const curve = "M24 0 C24 24 40 24 40 48 C40 72 24 72 24 96";

  return (
    <div ref={handleRef} data-sidebar-edge-handle className={`pointer-events-none absolute top-1/2 z-30 flex h-24 w-12 -translate-y-1/2 items-center ${side === "left" ? "-left-6 justify-start" : "-right-6 justify-end"} ${className}`}>
      {/* 外轮廓固定为 16px 浅凸起，双箭头向栏内借位，不把曲面加宽。 */}
      <svg aria-hidden="true" viewBox="0 0 48 96" className={`absolute inset-0 h-full w-full overflow-visible ${side === "left" ? "-scale-x-100" : ""}`}>
        <path d={`${curve} L23 96 L23 0 Z`} className="fill-surface" />
        <path d={curve} fill="none" className="stroke-border" strokeWidth="1" />
      </svg>
      {/* 单个箭头换方向时保留按钮，让弹窗关闭后仍能找到实际打开入口。 */}
      {([['left', leftAction], ['right', rightAction]] as const).map(([direction, action]) => action && (
        <span key={double ? direction : "single"} title={action.label} className="contents">
          <Button
            isIconOnly
            variant="ghost"
            aria-label={action.label}
            aria-controls={controls}
            aria-expanded={action.expanded}
            data-edge-action={direction}
            className="pointer-events-auto relative z-10 h-11 min-h-11 w-6 min-w-0 shrink-0 rounded-sm bg-transparent px-0 text-muted hover:bg-transparent hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent"
            onPress={(event) => {
              const pressed = event.target;
              action.onPress();
              // 双向切成单向时补回被移除按钮的焦点；弹窗或用户已接走焦点时不再抢回。
              requestAnimationFrame(() => {
                const handle = handleRef.current;
                if (pressed.isConnected || document.activeElement !== document.body || handle?.closest("[hidden], [inert]")) return;
                const target = handle?.querySelector<HTMLButtonElement>(`[data-edge-action="${direction}"]`)
                  ?? handle?.querySelector<HTMLButtonElement>("button");
                target?.focus({ preventScroll: true });
              });
            }}
          >
            <svg aria-hidden="true" className={`size-3.5 shrink-0 ${(double ? direction === "left" : side === "left") ? "translate-x-1" : "-translate-x-1"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d={direction === "left" ? "m14 6-6 6 6 6" : "m10 6 6 6-6 6"} />
            </svg>
          </Button>
        </span>
      ))}
      {double && <span aria-hidden="true" className="absolute left-6 top-1/2 h-2.5 w-px -translate-y-1/2 bg-border" />}
    </div>
  );
}
