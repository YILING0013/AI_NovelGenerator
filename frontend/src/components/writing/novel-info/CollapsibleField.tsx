"use client";

import { useId, useState } from "react";

interface CollapsibleFieldProps {
  label: string;
  value: string;
  defaultExpanded?: boolean;
  noContentText?: string;
}

/**
 * 展示可展开的长文本字段，并在折叠状态保留两行内容预览。
 *
 * Args:
 *   label: 字段标题。
 *   value: 字段正文。
 *   defaultExpanded: 是否默认展开全文。
 *   noContentText: 空内容提示。
 *
 * Returns:
 *   带折叠控制、预览和完整正文的字段节点。
 */
export default function CollapsibleField({
  label,
  value,
  defaultExpanded = false,
  noContentText = "",
}: CollapsibleFieldProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const contentId = useId();
  const hasContent = value.trim().length > 0;

  return (
    <div className="border-b border-border/50 last:border-b-0">
      <button
        type="button"
        className="group flex w-full items-center gap-2 py-2.5 text-left"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={contentId}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`shrink-0 text-muted transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
        <span className="text-[15px] font-semibold leading-5 text-foreground transition-colors group-hover:text-accent">
          {label}
        </span>
        {!hasContent && (
          <span className="ml-auto text-xs text-muted/70">{noContentText}</span>
        )}
      </button>
      <div id={contentId} className={`${expanded ? "pb-3" : "pb-2.5"} min-w-0 pl-6`}>
        {hasContent ? (
          <p
            className={`break-words whitespace-pre-wrap text-sm leading-6 ${
              expanded ? "reading-copy text-foreground" : "line-clamp-2 text-muted"
            }`}
          >
            {value}
          </p>
        ) : expanded ? (
          <p className="text-sm italic leading-6 text-muted/70">{noContentText}</p>
        ) : null}
      </div>
    </div>
  );
}
