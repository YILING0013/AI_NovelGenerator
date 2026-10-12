/**
 * 完整展示标签数组，长句标签自然换行。
 *
 * Args:
 *   props: 标签值和可选的列表名称。
 *
 * Returns:
 *   使用主题颜色的只读标签列表。
 */
export default function TagList({ values, label }: { values: string[]; label?: string }) {
  return (
    <ul aria-label={label} className="flex min-w-0 flex-wrap gap-2">
      {values.map((value, index) => (
        <li key={`${index}:${value}`} className="max-w-full rounded-xl bg-accent/10 px-3 py-1.5 text-sm leading-6 break-words [overflow-wrap:anywhere] text-accent">{value}</li>
      ))}
    </ul>
  );
}
