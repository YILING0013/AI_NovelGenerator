"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";
import { useThemeCustomization } from "@/components/ThemeCustomizationProvider";
import {
  THEME_PRESETS,
  SEMANTIC_COLOR_KEYS,
  SCALE_COLOR_KEYS,
  getPreset,
  type ThemeColors,
} from "@/lib/themes";

/* 颜色输入行 */
function ColorRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-3">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-8 shrink-0 cursor-pointer rounded border border-border bg-transparent p-0"
      />
      <span className="min-w-[120px] text-sm text-foreground">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          if (/^#[0-9a-fA-F]{0,6}$/.test(v)) onChange(v);
        }}
        className="w-24 rounded-md border border-border bg-surface px-2 py-1 text-xs font-mono text-foreground"
      />
    </label>
  );
}

/* 根据语言切换的标签映射 */
const LABEL_MAP: Record<string, { zh: string; en: string }> = {
  "--background": { zh: "背景色", en: "Background" },
  "--foreground": { zh: "文字色", en: "Text" },
  "--color-accent": { zh: "强调色", en: "Accent" },
  "--color-accent-hover": { zh: "强调色(悬停)", en: "Accent Hover" },
  "--color-surface": { zh: "表面色", en: "Surface" },
  "--color-surface-secondary": { zh: "次表面色", en: "Surface 2" },
  "--color-border": { zh: "边框色", en: "Border" },
  "--color-muted": { zh: "辅助文字", en: "Muted" },
  "--color-warm-50": { zh: "色阶 50", en: "Scale 50" },
  "--color-warm-100": { zh: "色阶 100", en: "Scale 100" },
  "--color-warm-200": { zh: "色阶 200", en: "Scale 200" },
  "--color-warm-300": { zh: "色阶 300", en: "Scale 300" },
  "--color-warm-400": { zh: "色阶 400", en: "Scale 400" },
  "--color-warm-500": { zh: "色阶 500", en: "Scale 500" },
  "--color-warm-600": { zh: "色阶 600", en: "Scale 600" },
  "--color-warm-700": { zh: "色阶 700", en: "Scale 700" },
  "--color-warm-800": { zh: "色阶 800", en: "Scale 800" },
  "--color-warm-900": { zh: "色阶 900", en: "Scale 900" },
};

/* 主题卡片组件 */
export function ThemeCard() {
  const t = useTranslations("settings.theme");
  const pathname = usePathname();
  const locale = pathname.startsWith("/en") ? "en" : "zh";

  const {
    presetId,
    selectPreset,
    customLight,
    customDark,
    setCustomColors,
  } = useThemeCustomization();

  const [editMode, setEditMode] = useState<"light" | "dark">("light");
  const [showScale, setShowScale] = useState(false);

  /* 选择预设，或切换到自定义配色 */
  const handleSelect = (id: string) => {
    if (id === "custom") {
      const base =
        presetId === "custom"
          ? { light: customLight, dark: customDark }
          : (getPreset(presetId) ?? THEME_PRESETS[0]);

      setCustomColors({ ...base.light }, { ...base.dark });
    } else {
      selectPreset(id);
    }
  };

  /* 更新单个颜色，并立即同步到全局主题 */
  const handleColor = (key: keyof ThemeColors, value: string) => {
    if (editMode === "light") {
      setCustomColors({ ...customLight, [key]: value }, customDark);
    } else {
      setCustomColors(customLight, { ...customDark, [key]: value });
    }
  };

  const draft = editMode === "light" ? customLight : customDark;

  /* 标签读取辅助方法 */
  const label = (key: string) => LABEL_MAP[key]?.[locale] ?? key;

  return (
    <div className="space-y-6">
      {/* 预设选择区 */}
      <section>
        <h3 className="mb-3 text-sm font-medium text-foreground">
          {t("presets")}
        </h3>
        <div className="flex flex-wrap gap-3">
          {THEME_PRESETS.map((preset) => (
            <button
              key={preset.id}
              onClick={() => handleSelect(preset.id)}
              className={`flex flex-col items-center gap-2 rounded-lg border-2 px-4 py-3 transition-all ${
                presetId === preset.id
                  ? "border-accent bg-accent/5 shadow-sm"
                  : "border-border hover:border-muted"
              }`}
            >
              <div className="flex gap-1">
                {preset.swatches.map((c, i) => (
                  <span
                    key={i}
                    className="block h-6 w-6 rounded-full border border-black/10"
                    style={{ backgroundColor: c }}
                  />
                ))}
              </div>
              <span className="text-xs font-medium text-foreground">
                {t(`preset_${preset.id}`)}
              </span>
            </button>
          ))}

          {/* 自定义选项 */}
          <button
            onClick={() => handleSelect("custom")}
            className={`flex flex-col items-center gap-2 rounded-lg border-2 px-4 py-3 transition-all ${
              presetId === "custom"
                ? "border-accent bg-accent/5 shadow-sm"
                : "border-border hover:border-muted"
            }`}
          >
            <div className="flex h-6 w-[104px] items-center justify-center">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-muted"
              >
                <circle cx="13.5" cy="6.5" r="2.5" />
                <circle cx="17.5" cy="10.5" r="2.5" />
                <circle cx="8.5" cy="7.5" r="2.5" />
                <circle cx="6.5" cy="12.5" r="2.5" />
                <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z" />
              </svg>
            </div>
            <span className="text-xs font-medium text-foreground">
              {t("custom")}
            </span>
          </button>
        </div>
      </section>

      {/* 自定义颜色编辑区 */}
      {presetId === "custom" && (
        <section className="rounded-lg border border-border bg-surface p-4">
          {/* 明暗模式切换标签 */}
          <div className="mb-4 flex gap-2">
            {(["light", "dark"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setEditMode(m)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  editMode === m
                    ? "bg-accent text-white"
                    : "bg-surface-secondary text-muted hover:text-foreground"
                }`}
              >
                {t(m === "light" ? "lightMode" : "darkMode")}
              </button>
            ))}
          </div>

          {/* 语义颜色 */}
          <h4 className="mb-2 text-xs font-medium text-muted">
            {t("semanticColors")}
          </h4>
          <div className="mb-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {SEMANTIC_COLOR_KEYS.map((key) => (
              <ColorRow
                key={key}
                label={label(key)}
                value={draft[key]}
                onChange={(v) => handleColor(key, v)}
              />
            ))}
          </div>

          {/* 高级色阶颜色 */}
          <button
            onClick={() => setShowScale((s) => !s)}
            className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-foreground transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transition-transform ${showScale ? "rotate-90" : ""}`}
            >
              <path d="m9 18 6-6-6-6" />
            </svg>
            {t("scaleColors")}
          </button>

          {showScale && (
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {SCALE_COLOR_KEYS.map((key) => (
                <ColorRow
                  key={key}
                  label={label(key)}
                  value={draft[key]}
                  onChange={(v) => handleColor(key, v)}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
