"use client";

import { Button, Tooltip } from "@heroui/react";
import { useEffect, useRef, useState, type ReactElement } from "react";

interface TooltipHintProps {
  text: string;
  className?: string;
  children?: ReactElement;
  label?: string;
}

/**
 * 渲染可悬停、键盘聚焦或触屏长按打开的说明，浮层不受面板滚动裁剪。
 *
 * Args:
 *   text: 展示的说明文本。
 *   className: 可选的外层样式。
 *   children: 可选的 HeroUI 操作按钮；未传时显示问号按钮。
 *   label: 用字段名称本身作为提示入口，避免额外问号。
 *
 * Returns:
 *   使用原操作、字段名称或问号作为入口的悬浮说明节点。
 */
export function TooltipHint({
  text,
  className = "",
  children,
  label,
}: TooltipHintProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const press = useRef<{ timer: ReturnType<typeof setTimeout>; x: number; y: number } | null>(null);
  const held = useRef(false);
  const cancelPress = () => { if (press.current) clearTimeout(press.current.timer); press.current = null; };
  useEffect(() => () => cancelPress(), []);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", dismiss, true);
    return () => document.removeEventListener("pointerdown", dismiss, true);
  }, [open]);
  return (
    <span ref={root} className={`inline-flex min-w-0 align-middle ${className}`}
      onPointerDownCapture={(event) => {
        if (event.pointerType !== "touch") return;
        cancelPress(); held.current = false;
        const target = event.target as HTMLElement;
        press.current = { x: event.clientX, y: event.clientY, timer: setTimeout(() => {
          held.current = true;
          // 与 React Aria 长按一致：取消原按钮按压，避免松手误触或让下次轻触失效。
          target.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true }));
          setOpen(true);
        }, 500) };
      }}
      onPointerMoveCapture={(event) => { if (press.current && Math.hypot(event.clientX - press.current.x, event.clientY - press.current.y) > 10) cancelPress(); }}
      onPointerUpCapture={cancelPress}
      onPointerCancel={cancelPress}
      onClickCapture={(event) => { if (held.current) { held.current = false; event.preventDefault(); event.stopPropagation(); } }}
      onContextMenu={(event) => { if (press.current || held.current) event.preventDefault(); }}
    >
      <Tooltip
        isOpen={open}
        onOpenChange={setOpen}
        delay={300}
        closeDelay={0}
        shouldCloseOnPress={false}
      >
        {children ?? (label ? <Button variant="ghost" size="sm" className="h-auto min-h-0 justify-start rounded-sm p-0 text-left text-inherit [font:inherit]" onPress={() => setOpen((value) => !value)}>{label}</Button> : (
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
        ))}
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
