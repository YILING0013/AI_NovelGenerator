"use client";

import { Button } from "@heroui/react";
import type { ComponentProps } from "react";
import { TooltipHint } from "./TooltipHint";

type SectionButtonProps = Omit<ComponentProps<typeof Button>, "children" | "aria-label"> & { label: string };

/** 功能：分节与工具栏的简单图标操作。Args: action 图标、label 原动作名称及原按钮属性。Returns: 保留提示、焦点和回调的按钮。 */
export function SectionActionButton({ action, label, ...props }: SectionButtonProps & { action: "edit" | "save" | "cancel" | "refresh" | "trash" | "activate" | "deactivate" }) {
  return <TooltipHint text={label}>
    <Button {...props} aria-label={label} isIconOnly size="sm" variant="ghost" className={`${action === "edit" ? "section-edit-button" : "section-action-button"} size-11 shrink-0 ${action === "save" ? "text-accent" : action === "trash" ? "text-danger" : "text-muted hover:text-accent"} sm:size-9 ${props.className ?? ""}`}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4">
        {action === "edit" ? <><path d="m16 3 5 5-12 12-6 1 1-6L16 3Z" /><path d="m14 5 5 5" /></>
          : action === "save" ? <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z" /><path d="M7 3v6h9V3M7 21v-8h10v8" /></>
          : action === "refresh" ? <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 6a8 8 0 0 1 13 3l1 3M4 12l1 3a8 8 0 0 0 13 3" /></>
          : action === "trash" ? <><path d="M3 6h18M9 6V4h6v2M5 6l1 15h12l1-15M10 10v7M14 10v7" /></>
          : action === "deactivate" ? <><path d="M12 2v10" /><path d="M6.3 5.3a8 8 0 1 0 11.4 0" /></>
          : action === "activate" ? <><path d="M20 4v6h-6" /><path d="M20 10a8 8 0 1 0-2 8" /></>
          : <path d="m6 6 12 12M18 6 6 18" />}
      </svg>
    </Button>
  </TooltipHint>;
}

/** 功能：维持原有分节编辑入口，使用统一的图标操作。 */
export default function SectionEditButton(props: SectionButtonProps) {
  return <SectionActionButton {...props} action="edit" />;
}
