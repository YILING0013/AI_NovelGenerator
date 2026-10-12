"use client";
import { RetainedModalBackdrop } from "@/components/layout/RetainedViews";


import { Button, Modal } from "@heroui/react";
import type { ReactNode } from "react";
import type { ApiFieldErrors } from "@/lib/api";

interface RelationEditorErrorSummaryProps {
  message: string;
  fieldErrors?: ApiFieldErrors;
  className?: string;
}

/**
 * 功能：在当前关系编辑弹窗内展示固定可见的错误摘要。
 * Args:
 *   props: 错误主消息、字段错误映射与可选样式类。
 * Returns:
 *   带 role=alert 和去重字段消息的错误摘要节点。
 */
export function RelationEditorErrorSummary({
  message,
  fieldErrors = {},
  className = "",
}: RelationEditorErrorSummaryProps) {
  const details = Array.from(new Set(Object.values(fieldErrors).flat()));
  return (
    <div
      className={`border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950/35 dark:text-red-200 ${className}`}
      role="alert"
      aria-live="assertive"
      tabIndex={-1}
      data-editor-error-summary=""
    >
      <p className="font-semibold">{message}</p>
      {details.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {details.map((detail) => <li key={detail}>{detail}</li>)}
        </ul>
      )}
    </div>
  );
}

/**
 * 功能：在编辑失败后聚焦首个字段错误；无字段错误时聚焦并滚入错误摘要。
 * Args:
 *   fieldErrors: 已归一化的字段错误映射，字段路径可以包含点号前缀。
 *   container: 同页编辑区；省略时使用最上层弹窗。
 * Returns:
 *   无；待弹窗状态和焦点圈定完成后更新最上层弹窗的键盘焦点与可视位置。
 */
export function focusRelationEditorError(fieldErrors: ApiFieldErrors, container?: HTMLElement | null): void {
  requestAnimationFrame(() => {
    // HeroUI 会在保存状态切换后同步焦点圈定；再等待一帧可避免它覆盖字段错误焦点。
    requestAnimationFrame(() => {
      const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"]');
      const dialog = container ?? dialogs.item(dialogs.length - 1);
      if (!dialog) return;

      const firstField = Object.keys(fieldErrors)[0]?.split(".").at(-1);
      const field = firstField
        ? dialog.querySelector<HTMLElement>(`[name="${CSS.escape(firstField)}"]`)
        : null;
      const target = field ?? dialog.querySelector<HTMLElement>("[data-editor-error-summary]");
      if (!target) return;

      target.focus({ preventScroll: true });
      target.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    });
  });
}

interface RelationFieldShellProps {
  label: string;
  children: ReactNode;
  className?: string;
  error?: string;
  errorId?: string;
}

/**
 * 功能：为人物关系和阵营关系字段提供统一标签、间距与错误位置。
 * Args:
 *   props: 字段标题、输入节点、可选布局类及错误消息和 DOM ID。
 * Returns:
 *   可直接包裹原生表单控件的字段标签节点。
 */
export function RelationFieldShell({
  label,
  children,
  className = "",
  error,
  errorId,
}: RelationFieldShellProps) {
  return (
    <label className={`grid gap-2 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {error && <span id={errorId} className="text-xs text-red-600 dark:text-red-300">{error}</span>}
    </label>
  );
}

interface RelationIntensityFieldProps {
  name?: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  error?: string;
  errorId?: string;
  inputClassName: string;
}

/**
 * 功能：统一渲染关系强度的 1 至 5 数字输入和同步强度条。
 * Args:
 *   props: 字段名、标题、强度值、更新回调、禁用状态、错误及输入样式。
 * Returns:
 *   同时提供精确数字编辑与视觉强度反馈的字段节点。
 */
export function RelationIntensityField({
  name = "intensity",
  label,
  value,
  onChange,
  disabled,
  error,
  errorId = `relation-${name}-error`,
  inputClassName,
}: RelationIntensityFieldProps) {
  return (
    <RelationFieldShell label={`${label}: ${value}/5`} error={error} errorId={errorId}>
      <div className="grid grid-cols-[6rem_1fr] items-center gap-3">
        <input
          name={name}
          type="number"
          min={1}
          max={5}
          step={1}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          disabled={disabled}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={error ? errorId : undefined}
          className={inputClassName}
        />
        <div className="h-2 overflow-hidden rounded-full bg-surface-secondary" aria-hidden="true">
          <div
            className="h-full rounded-full bg-accent transition-[width]"
            style={{ width: `${Math.max(0, Math.min(5, value)) * 20}%` }}
          />
        </div>
      </div>
    </RelationFieldShell>
  );
}

interface ConfirmActionModalProps {
  title: string;
  message: ReactNode;
  confirmText: string;
  cancelText: string;
  loadingText?: string;
  danger?: boolean;
  error?: string;
  isLoading?: boolean;
  isConfirmDisabled?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * 功能：统一渲染实体软删除和永久删除的确认弹窗。
 * Args:
 *   props: 标题、说明、按钮文案、危险态、错误、加载/禁用状态和操作回调。
 * Returns:
 *   具备焦点圈定、关闭保护和弹窗内错误提示的 HeroUI Modal 节点。
 */
export function ConfirmActionModal({
  title,
  message,
  confirmText,
  cancelText,
  loadingText,
  danger = false,
  error = "",
  isLoading = false,
  isConfirmDisabled = false,
  onCancel,
  onConfirm,
}: ConfirmActionModalProps) {
  return (
      <RetainedModalBackdrop isOpen onOpenChange={(isOpen) => !isOpen && !isLoading && onCancel()} variant="blur" isDismissable={!isLoading}>
        <Modal.Container size="xs" scroll="inside">
          <Modal.Dialog className="w-full max-w-sm">
            <Modal.Header className="px-5 pb-0 pt-5">
              <Modal.Heading className="text-base font-semibold text-foreground">{title}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="px-5 py-4">
              <div className="text-sm leading-6 text-muted">{message}</div>
              {error && <RelationEditorErrorSummary message={error} className="mt-3" />}
            </Modal.Body>
            <Modal.Footer className="flex justify-end gap-2 px-5 pb-5 pt-0">
              <Button variant="ghost" size="sm" onPress={onCancel} isDisabled={isLoading}>
                {cancelText}
              </Button>
              <Button
                variant="primary"
                size="sm"
                className={danger ? "bg-red-600 text-white hover:bg-red-700" : undefined}
                onPress={onConfirm}
                isDisabled={isLoading || isConfirmDisabled}
              >
                {isLoading ? (loadingText ?? confirmText) : confirmText}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </RetainedModalBackdrop>
  );
}
