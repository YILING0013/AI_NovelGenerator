"use client";

import { useRef, useEffect, useCallback } from "react";

interface AutoResizeTextareaProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  minHeight?: number;
  maxHeight?: number;
  className?: string;
  disabled?: boolean;
  ariaDescribedBy?: string;
}

/**
 * 渲染会随内容增长的多行文本框，并在达到最大高度后切换为内部滚动。
 *
 * Args:
 *   props: 文本值、变更回调、尺寸限制和可访问性关联属性。
 *
 * Returns:
 *   高度会根据内容自动调整的 textarea 节点。
 */
export default function AutoResizeTextarea({
  id,
  value,
  onChange,
  placeholder,
  minHeight = 80,
  maxHeight = 320,
  className = "",
  disabled = false,
  ariaDescribedBy,
}: AutoResizeTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight, minHeight), maxHeight);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [minHeight, maxHeight]);

  useEffect(() => {
    resize();
  }, [value, resize]);

  return (
    <textarea
      id={id}
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      aria-describedby={ariaDescribedBy}
      className={`w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted/50 focus:outline-none focus:ring-2 focus:ring-accent/20 transition-colors ${disabled ? "opacity-60 cursor-not-allowed" : ""} ${className}`}
      style={{ minHeight: `${minHeight}px`, maxHeight: `${maxHeight}px` }}
    />
  );
}
