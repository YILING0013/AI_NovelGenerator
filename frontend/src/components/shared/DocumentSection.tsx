import { useId, type ReactNode } from "react";

/**
 * 展示小说资料风格的编号章节，共用于卷、实体资料和层级规划。
 *
 * Args:
 *   props: 章节编号、标题、标题旁操作、下方操作和字段内容。
 *
 * Returns:
 *   按实际宽度切换标题栏的连续资料章节。
 */
export default function DocumentSection({ number, title, actions, secondaryActions, children, id }: {
  id?: string;
  number: string;
  title: string;
  actions?: ReactNode;
  secondaryActions?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <section id={id} tabIndex={id ? -1 : undefined} aria-labelledby={titleId} className="@container/document min-w-0 scroll-mt-4 outline-none">
      <div className="grid min-w-0 gap-4 @[800px]/document:grid-cols-[10rem_minmax(0,1fr)] @[800px]/document:gap-x-8">
        <header className="min-w-0 self-start @[800px]/document:sticky @[800px]/document:top-0">
          <div className="mb-2 flex items-center gap-3">
            <span className="font-mono text-[15px] font-bold leading-none tracking-[0.16em] text-accent" aria-hidden="true">{number}</span>
            <span className="h-px flex-1 bg-border/70" aria-hidden="true" />
          </div>
          <div className={secondaryActions ? "grid w-fit max-w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-1 gap-y-2" : "flex min-w-0 flex-wrap items-center gap-x-1 gap-y-2"}>
            <h3 id={titleId} className="min-w-0 max-w-full text-lg font-semibold tracking-tight text-foreground [overflow-wrap:anywhere]">{title}</h3>
            {actions && <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2">{actions}</div>}
            {secondaryActions && <div className="col-span-full min-w-0">{secondaryActions}</div>}
          </div>
        </header>
        <div className="min-w-0">{children}</div>
      </div>
    </section>
  );
}
