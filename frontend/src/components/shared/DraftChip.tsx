"use client";

import { useRef, useState } from "react";
import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import { TooltipHint } from "./TooltipHint";

interface DraftChipProps {
  label: string;
  status?: "draft" | "pending" | "saved" | "rejected";
  isDisabled?: boolean;
  isResumeDisabled?: boolean;
  isDiscardDisabled?: boolean;
  onResume: () => void;
  onDiscard?: () => Promise<void>;
}

/** 功能：统一草稿入口，点击名称继续编辑，点叉直接放弃。Args: 名称、状态、禁用条件和原有读写回调。Returns: 带移除进度及失败提示的标签。 */
export default function DraftChip({ label, status, isDisabled = false, isResumeDisabled = false, isDiscardDisabled = false, onResume, onDiscard }: DraftChipProps) {
  const t = useTranslations("draftChip");
  const pending = useRef(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState(false);

  return <div className="flex max-w-full flex-col items-start gap-1">
    <div className="draft-chip inline-flex max-w-full items-center rounded-full border border-accent/15 bg-accent/10 text-accent">
      <Button size="sm" variant="ghost" aria-label={t("resume", { name: label })} isDisabled={isDisabled || removing} aria-disabled={isResumeDisabled || undefined} onPress={() => { if (!isResumeDisabled) onResume(); }}
        className="min-h-11 min-w-0 gap-2 rounded-l-full rounded-r-none px-3 py-1.5 text-xs text-accent sm:min-h-8">
        <span className="shrink-0 text-muted">{t(status ?? "draft")}</span>
        <span className="min-w-0 whitespace-normal break-words text-left [overflow-wrap:anywhere]">{label}</span>
      </Button>
      <TooltipHint text={onDiscard ? t("discard", { name: label }) : t("finishBeforeDiscard")}>
        <Button isIconOnly size="sm" variant="ghost" aria-label={t("discard", { name: label })}
          isDisabled={isDisabled || isDiscardDisabled || removing || !onDiscard} isPending={removing}
          className="size-11 min-h-11 shrink-0 rounded-full p-0 text-accent/70 hover:text-danger sm:size-8 sm:min-h-8"
          onPress={async () => {
            if (!onDiscard || pending.current) return;
            pending.current = true; setRemoving(true); setError(false);
            try { await onDiscard(); }
            catch { setError(true); }
            finally { pending.current = false; setRemoving(false); }
          }}>
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="size-3.5"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </Button>
      </TooltipHint>
    </div>
    {error && <p role="alert" className="text-xs text-danger">{t("discardFailed")}</p>}
  </div>;
}
