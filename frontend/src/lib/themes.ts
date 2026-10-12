export interface ThemeColors {
  "--background": string;
  "--foreground": string;
  "--color-warm-50": string;
  "--color-warm-100": string;
  "--color-warm-200": string;
  "--color-warm-300": string;
  "--color-warm-400": string;
  "--color-warm-500": string;
  "--color-warm-600": string;
  "--color-warm-700": string;
  "--color-warm-800": string;
  "--color-warm-900": string;
  "--color-accent": string;
  "--color-accent-foreground": string;
  "--color-accent-hover": string;
  "--color-surface": string;
  "--color-surface-secondary": string;
  "--color-surface-raised": string;
  "--color-selected": string;
  "--color-border": string;
  "--color-muted": string;
}

export interface ThemePreset {
  id: string;
  light: ThemeColors;
  dark: ThemeColors;
  /* 用于预览的 4 个代表性色块 */
  swatches: [string, string, string, string];
}


/* 雾蓝：亮色保留纸面质感，暗色用表面明度区分层次。 */
export const MIST_THEME: ThemePreset = {
  id: "mist",
  swatches: ["#456783", "#aac3df", "#e2eaf2", "#fafaf9"],
  light: {
    "--background": "#f1f3f5",
    "--foreground": "#303844",
    "--color-warm-50": "#f7f9fb",
    "--color-warm-100": "#edf2f7",
    "--color-warm-200": "#dce5ee",
    "--color-warm-300": "#c2d1df",
    "--color-warm-400": "#9bb1c6",
    "--color-warm-500": "#7995af",
    "--color-warm-600": "#5d7e9b",
    "--color-warm-700": "#456783",
    "--color-warm-800": "#344f68",
    "--color-warm-900": "#263b50",
    "--color-accent": "#456783",
    "--color-accent-foreground": "#f8fafc",
    "--color-accent-hover": "#3a5973",
    "--color-surface": "#fafaf9",
    "--color-surface-secondary": "#e9edf1",
    "--color-surface-raised": "#fdfdfc",
    "--color-selected": "#e2eaf2",
    "--color-border": "#d6dce3",
    "--color-muted": "#5b6877",
  },
  dark: {
    "--background": "#171b22",
    "--foreground": "#d9dfe7",
    "--color-warm-50": "#1b232e",
    "--color-warm-100": "#222d3a",
    "--color-warm-200": "#2c3b4d",
    "--color-warm-300": "#3b5068",
    "--color-warm-400": "#536f8e",
    "--color-warm-500": "#7392b2",
    "--color-warm-600": "#90adc9",
    "--color-warm-700": "#aac3df",
    "--color-warm-800": "#c6d7e9",
    "--color-warm-900": "#e0e9f2",
    "--color-accent": "#aac3df",
    "--color-accent-foreground": "#1c2a39",
    "--color-accent-hover": "#bed1e8",
    "--color-surface": "#20252e",
    "--color-surface-secondary": "#272e38",
    "--color-surface-raised": "#2a303b",
    "--color-selected": "#2c3b4d",
    "--color-border": "#3b4655",
    "--color-muted": "#a4b0bf",
  },
};


/* 森林绿只用于强调；大面积背景和文字采用接近中性的颜色。 */
export const FOREST_THEME: ThemePreset = {
  id: "forest",
  swatches: ["#546B41", "#99AD7A", "#d9dfd6", "#f6f7f4"],
  light: {
    "--background": "#f6f7f4",
    "--foreground": "#252d28",
    "--color-warm-50": "#fffdf7",
    "--color-warm-100": "#FFF8EC",
    "--color-warm-200": "#f0e8d5",
    "--color-warm-300": "#DCCCAC",
    "--color-warm-400": "#b8b892",
    "--color-warm-500": "#99AD7A",
    "--color-warm-600": "#7a9460",
    "--color-warm-700": "#546B41",
    "--color-warm-800": "#3f5232",
    "--color-warm-900": "#2d3a24",
    "--color-accent": "#546B41",
    "--color-accent-foreground": "#ffffff",
    "--color-accent-hover": "#465a35",
    "--color-surface": "#ffffff",
    "--color-surface-secondary": "#edf0eb",
    "--color-surface-raised": "#ffffff",
    "--color-selected": "#edf0eb",
    "--color-border": "#d9dfd6",
    "--color-muted": "#626f65",
  },
  dark: {
    "--background": "#151917",
    "--foreground": "#e7ece7",
    "--color-warm-50": "#1a2015",
    "--color-warm-100": "#222b1b",
    "--color-warm-200": "#303d24",
    "--color-warm-300": "#3f5232",
    "--color-warm-400": "#546B41",
    "--color-warm-500": "#7a9460",
    "--color-warm-600": "#99AD7A",
    "--color-warm-700": "#b5c89e",
    "--color-warm-800": "#DCCCAC",
    "--color-warm-900": "#f0e8d5",
    "--color-accent": "#99AD7A",
    "--color-accent-foreground": "#172019",
    "--color-accent-hover": "#adc08e",
    "--color-surface": "#1c221e",
    "--color-surface-secondary": "#252d27",
    "--color-surface-raised": "#2a332d",
    "--color-selected": "#303930",
    "--color-border": "#364038",
    "--color-muted": "#a4b0a5",
  },
};


/* Warm — 项目原有暖棕配色 */
export const WARM_THEME: ThemePreset = {
  id: "warm",
  swatches: ["#9d6038", "#b08850", "#dfd9cf", "#faf9f6"],
  light: {
    "--background": "#faf9f6",
    "--foreground": "#302d28",
    "--color-warm-50": "#fdfbf7",
    "--color-warm-100": "#faf6f1",
    "--color-warm-200": "#f0e6d6",
    "--color-warm-300": "#e2d0b8",
    "--color-warm-400": "#c9a87c",
    "--color-warm-500": "#b08850",
    "--color-warm-600": "#96703a",
    "--color-warm-700": "#7a5a2e",
    "--color-warm-800": "#5c4322",
    "--color-warm-900": "#3d2c16",
    "--color-accent": "#9d6038",
    "--color-accent-foreground": "#ffffff",
    "--color-accent-hover": "#85502d",
    "--color-surface": "#ffffff",
    "--color-surface-secondary": "#f0ede6",
    "--color-surface-raised": "#ffffff",
    "--color-selected": "#f0ede6",
    "--color-border": "#dfd9cf",
    "--color-muted": "#736858",
  },
  dark: {
    "--background": "#191816",
    "--foreground": "#ede6dc",
    "--color-warm-50": "#1a1510",
    "--color-warm-100": "#231d15",
    "--color-warm-200": "#352a1c",
    "--color-warm-300": "#4a3b28",
    "--color-warm-400": "#6b5638",
    "--color-warm-500": "#8c7248",
    "--color-warm-600": "#b08850",
    "--color-warm-700": "#c9a87c",
    "--color-warm-800": "#e2d0b8",
    "--color-warm-900": "#f0e6d6",
    "--color-accent": "#d4864a",
    "--color-accent-foreground": "#241a11",
    "--color-accent-hover": "#e09558",
    "--color-surface": "#22201c",
    "--color-surface-secondary": "#2c2923",
    "--color-surface-raised": "#332f28",
    "--color-selected": "#3c3025",
    "--color-border": "#403a31",
    "--color-muted": "#b7a996",
  },
};


/* 导出项 */
export const THEME_PRESETS: ThemePreset[] = [MIST_THEME, FOREST_THEME, WARM_THEME];

export const DEFAULT_PRESET_ID = "mist";

/**
 * 按保存的名称查找预设，保留用户之前选择的配色。
 * Args:
 *   id: 预设名称。
 * Returns:
 *   匹配的预设；名称不存在时返回 undefined。
 */
export function getPreset(id: string): ThemePreset | undefined {
  return THEME_PRESETS.find((p) => p.id === id);
}

/* 在自定义编辑器中优先展示的语义颜色键 */
export const SEMANTIC_COLOR_KEYS: (keyof ThemeColors)[] = [
  "--background",
  "--foreground",
  "--color-accent",
  "--color-accent-foreground",
  "--color-accent-hover",
  "--color-surface",
  "--color-surface-secondary",
  "--color-surface-raised",
  "--color-selected",
  "--color-border",
  "--color-muted",
];

/* 在高级区域中展示的暖色阶颜色键 */
export const SCALE_COLOR_KEYS: (keyof ThemeColors)[] = [
  "--color-warm-50",
  "--color-warm-100",
  "--color-warm-200",
  "--color-warm-300",
  "--color-warm-400",
  "--color-warm-500",
  "--color-warm-600",
  "--color-warm-700",
  "--color-warm-800",
  "--color-warm-900",
];

export const ALL_COLOR_KEYS = Object.keys(MIST_THEME.light) as (keyof ThemeColors)[];

/**
 * 创建独立的雾蓝配色，供首次自定义时编辑。
 * Args:
 *   无。
 * Returns:
 *   亮色与暗色的颜色副本。
 */
export function createDefaultCustomColors(): { light: ThemeColors; dark: ThemeColors } {
  return {
    light: { ...MIST_THEME.light },
    dark: { ...MIST_THEME.dark },
  };
}
