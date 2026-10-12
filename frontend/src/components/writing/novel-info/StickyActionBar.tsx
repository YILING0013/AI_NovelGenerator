"use client";

interface StickyActionBarProps {
  children: React.ReactNode;
}

/**
 * 渲染创建态底部操作栏，并让按钮与编辑工作台正文宽度对齐。
 *
 * Args:
 *   children: 需要固定展示的操作按钮。
 *
 * Returns:
 *   带背景模糊和顶部边界的底部操作区域。
 */
export default function StickyActionBar({ children }: StickyActionBarProps) {
  return (
    <div className="sticky bottom-0 z-10 border-t border-border bg-background/95 px-4 py-4 backdrop-blur-sm sm:px-6">
      <div className="flex w-full flex-col justify-end gap-2 sm:flex-row sm:items-center sm:gap-3 [&>*]:w-full sm:[&>*]:w-auto">
        {children}
      </div>
    </div>
  );
}
