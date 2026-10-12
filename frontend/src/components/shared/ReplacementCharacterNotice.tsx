"use client";

import { Button } from "@heroui/react";
import { useTranslations } from "next-intl";

interface ReplacementCharacterLocation {
  path: string;
  positions: number[];
}

/**
 * 找出 JSON 内容中的实际替换字符，保留原文。
 *
 * Args:
 *   value: 当前候选的 JSON 内容。
 *   path: 当前字段路径，递归时追加字段名或数组下标。
 *
 * Returns:
 *   各字段路径与从 1 开始的 Unicode 码点位置。
 */
export function findReplacementCharacters(value: unknown, path = "$"): ReplacementCharacterLocation[] {
  if (typeof value === "string") {
    const positions: number[] = [];
    let position = 0;
    // 按码点计数，避免 emoji 的两个 UTF-16 单元把后续位置推偏。
    for (const character of value) {
      position += 1;
      if (character === "\uFFFD") positions.push(position);
    }
    return positions.length > 0 ? [{ path, positions }] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => findReplacementCharacters(item, `${path}[${index}]`));
  }
  if (value !== null && typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) => findReplacementCharacters(item, `${path}[${JSON.stringify(key)}]`));
  }
  return [];
}

/**
 * 提醒当前候选中的可疑替换字符，并允许导出完整原文。
 *
 * Args:
 *   value: 当前候选内容；每次渲染重新检查，不保留旧位置。
 *
 * Returns:
 *   可折叠的位置提示；没有替换字符时不显示内容。
 */
export default function ReplacementCharacterNotice({ value }: { value: unknown }) {
  const t = useTranslations("textQuality");
  const locations = findReplacementCharacters(value);
  if (locations.length === 0) return null;
  const count = locations.reduce((total, location) => total + location.positions.length, 0);

  return (
    <div className="min-w-0 space-y-2 border-y border-amber-500/40 py-3 text-sm text-foreground">
      <p role="status" className="break-words text-amber-800 dark:text-amber-200">
        {t("replacementSummary", { count })}
      </p>
      <details className="min-w-0">
        <summary className="min-h-11 cursor-pointer py-2 text-accent focus-visible:outline-2 focus-visible:outline-accent">
          {t("replacementDetails")}
        </summary>
        <ul className="min-w-0 space-y-3">
          {locations.map(({ path, positions }) => (
            <li key={path}>
              <dl className="min-w-0 space-y-1">
                <dt className="text-xs font-medium text-muted">{t("replacementPath")}</dt>
                <dd className="min-w-0 font-mono text-xs [overflow-wrap:anywhere]">{path}</dd>
                <dt className="text-xs font-medium text-muted">{t("replacementPositions")}</dt>
                <dd className="tabular-nums [overflow-wrap:anywhere]">{positions.join(", ")}</dd>
              </dl>
            </li>
          ))}
        </ul>
      </details>
      <Button size="sm" variant="ghost" className="min-h-11 max-w-full whitespace-normal" onPress={() => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = "candidate-text.json";
        link.click();
        URL.revokeObjectURL(url);
      }}>{t("exportOriginal")}</Button>
    </div>
  );
}
