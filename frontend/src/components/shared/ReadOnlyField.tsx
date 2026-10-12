import type { ReactNode } from "react";
import CollapsibleField from "@/components/writing/novel-info/CollapsibleField";

/** 功能：按小说资料样式显示短字段或可展开长文。Args: label 字段名；value 内容；wide 是否允许长内容占满分组并折叠。Returns: 用于 detail-fields 定义列表的字段。 */
export default function ReadOnlyField({ label, value, wide = false }: { label: string; value: ReactNode; wide?: boolean }) {
  const collapsible = wide && typeof value === "string" && (value.length > 200 || value.split("\n").length > 3);
  // 叙述字段内容很短时也可并排，只有实际长文才独占整行。
  const fullWidth = wide && (typeof value !== "string" || value.length > 120 || value.includes("\n"));
  return <div className={`min-w-0 ${fullWidth ? "col-span-full" : ""}`}>
    <dt className={collapsible ? "sr-only" : "text-xs font-medium leading-5 text-muted"}>{label}</dt>
    <dd className={collapsible ? "min-w-0" : "reading-copy mt-1 min-w-0 whitespace-pre-wrap break-words text-foreground"}>
      {collapsible ? <CollapsibleField label={label} value={value as string} /> : value === "" ? "—" : value ?? "—"}
    </dd>
  </div>;
}
