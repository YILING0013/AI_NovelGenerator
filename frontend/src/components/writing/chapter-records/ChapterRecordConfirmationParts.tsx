"use client";

import { downloadExport } from "@/lib/userExport";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";
import type { ChapterRecordDraft } from "./chapterRecordDrafts";

/** 功能：显示两个确认表单共用的冻结请求状态。Args: draft 当前稿。Returns: 状态提示。 */
export function ChapterRecordCommandStatus({ draft }: { draft: ChapterRecordDraft }) {
  const t = useTranslations("writing.chapterRecords");
  return draft.command ? <p role="status" className="border-y border-amber-500/50 py-3 text-sm">{t(draft.command.saved ? "savedPending" : draft.command.unknown !== false ? "unknown" : "rejected")}</p> : null;
}

/** 功能：两个固定表单共用作者明确勾选。Args: checked 当前选择；disabled 锁定；onChange 更新。Returns: 可访问勾选框。 */
export function ChapterRecordAuthorConfirmation({ checked, disabled, onChange }: { checked: boolean; disabled: boolean; onChange: (checked: boolean) => void }) {
  const t = useTranslations("writing.chapterRecords");
  return <label className="flex min-h-11 items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />{t("authorConfirmed")}</label>;
}

/** 功能：导出当前内存稿，包括尚未成功写入本机的检查结果。Args: draft 原稿。Returns: 导出按钮。 */
export function ChapterRecordExport({ draft }: { draft: ChapterRecordDraft }) {
  const t = useTranslations("writing.chapterRecords");
  return <Button variant="ghost" onPress={() => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: "application/json;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `chapter-record-${draft.key}.json`; void downloadExport(link); URL.revokeObjectURL(url);
  }}>{t("exportDraft")}</Button>;
}
