"use client";

import { Button, Tooltip } from "@heroui/react";
import { useState, type ReactElement } from "react";

interface TooltipHintProps {
  text: string;
  className?: string;
  children?: ReactElement;
}

/**
 * 渲染可悬停、聚焦或点击打开的说明，浮层不受面板滚动裁剪。
 *
 * Args:
 *   text: 展示的说明文本。
 *   className: 可选的外层样式。
 *   children: 可选的 HeroUI 操作按钮；未传时显示问号按钮。
 *
 * Returns:
 *   带问号圆点与悬浮说明的 React 节点。
 */
export function TooltipHint({
  text,
  className = "",
  children,
}: TooltipHintProps) {
  const [open, setOpen] = useState(false);
  return (
    <span className={`inline-flex min-w-0 align-middle ${className}`}>
      <Tooltip
        isOpen={open}
        onOpenChange={setOpen}
        delay={300}
        closeDelay={0}
        shouldCloseOnPress={false}
      >
        {children ?? (
          <Button
            isIconOnly
            size="sm"
            variant="ghost"
            aria-label={text}
            className="size-9 shrink-0 rounded-full text-muted hover:text-accent"
            onPress={() => setOpen(true)}
            // 问号可能位于字段标签或可拖节点中，点击不能顺便选中字段或拖动节点。
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            <span
              aria-hidden="true"
              className="grid size-4 place-items-center rounded-full border border-current text-xs font-semibold leading-none"
            >
              ?
            </span>
          </Button>
        )}
        <Tooltip.Content
          placement="top"
          className="z-[100] max-w-[min(20rem,calc(100vw-24px))] rounded-lg border border-border bg-surface-raised px-3 py-2 text-xs font-normal leading-5 text-foreground shadow-lg"
        >
          {text}
        </Tooltip.Content>
      </Tooltip>
    </span>
  );
}
