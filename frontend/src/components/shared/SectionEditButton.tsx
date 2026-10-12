"use client";

import { Button } from "@heroui/react";
import type { ComponentProps } from "react";
import { TooltipHint } from "./TooltipHint";

type SectionButtonProps = Omit<ComponentProps<typeof Button>, "children" | "aria-label"> & { label: string };

/** 功能：标题旁的编辑、保存和取消，保留提示与键盘名称，不挤压标题。 */
export function SectionActionButton({ action, label, ...props }: SectionButtonProps & { action: "edit" | "save" | "cancel" }) {
  return <TooltipHint text={label}>
    <Button {...props} aria-label={label} isIconOnly size="sm" variant="ghost" className={`${action === "edit" ? "section-edit-button" : "section-action-button"} size-11 shrink-0 ${action === "save" ? "text-accent" : "text-muted hover:text-accent"} sm:size-9 ${props.className ?? ""}`}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="size-4">
        {action === "edit" ? <><path d="m16 3 5 5-12 12-6 1 1-6L16 3Z" /><path d="m14 5 5 5" /></> : action === "save" ? <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z" /><path d="M7 3v6h9V3M7 21v-8h10v8" /></> : <path d="m6 6 12 12M18 6 6 18" />}
      </svg>
    </Button>
  </TooltipHint>;
}

/** 功能：维持原有分节编辑入口，使用统一的图标操作。 */
export default function SectionEditButton(props: SectionButtonProps) {
  return <SectionActionButton {...props} action="edit" />;
}
