"use client";

import { useState } from "react";

interface CollapsibleFieldProps {
  label: string;
  value: string;
  defaultExpanded?: boolean;
  noContentText?: string;
}

export default function CollapsibleField({
  label,
  value,
  defaultExpanded = false,
  noContentText = "",
}: CollapsibleFieldProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasContent = value && value.trim().length > 0;

  return (
    <div className="border-b border-border/50 last:border-b-0">
      <button
        type="button"
        className="flex items-center gap-2 w-full py-2.5 text-left group"
        onClick={() => setExpanded(!expanded)}
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
          className={`text-muted shrink-0 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
        >
          <path d="m9 18 6-6-6-6" />
        </svg>
        <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
          {label}
        </span>
        {!hasContent && (
          <span className="text-xs text-muted/60 ml-auto">{noContentText}</span>
        )}
      </button>
      {expanded && (
        <div className="pb-3 pl-6">
          {hasContent ? (
            <p className="text-sm text-foreground/80 whitespace-pre-wrap leading-relaxed">
              {value}
            </p>
          ) : (
            <p className="text-sm text-muted/50 italic">{noContentText}</p>
          )}
        </div>
      )}
    </div>
  );
}
