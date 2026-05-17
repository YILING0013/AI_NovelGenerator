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
  "--color-accent-hover": string;
  "--color-surface": string;
  "--color-surface-secondary": string;
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


/* Forest — 亮色默认（用户指定 #546B41 #99AD7A #DCCCAC #FFF8EC） */
export const FOREST_THEME: ThemePreset = {
  id: "forest",
  swatches: ["#546B41", "#99AD7A", "#DCCCAC", "#FFF8EC"],
  light: {
    "--background": "#FFF8EC",
    "--foreground": "#2d3a24",
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
    "--color-accent-hover": "#465a35",
    "--color-surface": "#ffffff",
    "--color-surface-secondary": "#f7f2e6",
    "--color-border": "#DCCCAC",
    "--color-muted": "#7d8a6c",
  },
  dark: {
    "--background": "#1a2015",
    "--foreground": "#e4ead6",
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
    "--color-accent-hover": "#adc08e",
    "--color-surface": "#1f281a",
    "--color-surface-secondary": "#283320",
    "--color-border": "#3f5232",
    "--color-muted": "#94a483",
  },
};


/* Warm — 项目原有暖棕配色 */
export const WARM_THEME: ThemePreset = {
  id: "warm",
  swatches: ["#c2703a", "#b08850", "#e2d0b8", "#faf6f1"],
  light: {
    "--background": "#faf6f1",
    "--foreground": "#2c2418",
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
    "--color-accent": "#c2703a",
    "--color-accent-hover": "#a85e30",
    "--color-surface": "#ffffff",
    "--color-surface-secondary": "#f7f2eb",
    "--color-border": "#e2d6c6",
    "--color-muted": "#8c7e6e",
  },
  dark: {
    "--background": "#1a1510",
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
    "--color-accent-hover": "#e09558",
    "--color-surface": "#211b14",
    "--color-surface-secondary": "#2a2218",
    "--color-border": "#3d3226",
    "--color-muted": "#9c8e7e",
  },
};


/* 导出项 */
export const THEME_PRESETS: ThemePreset[] = [FOREST_THEME, WARM_THEME];

export const DEFAULT_PRESET_ID = "forest";

export function getPreset(id: string): ThemePreset | undefined {
  return THEME_PRESETS.find((p) => p.id === id);
}

/* 在自定义编辑器中优先展示的语义颜色键 */
export const SEMANTIC_COLOR_KEYS: (keyof ThemeColors)[] = [
  "--background",
  "--foreground",
  "--color-accent",
  "--color-accent-hover",
  "--color-surface",
  "--color-surface-secondary",
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

export const ALL_COLOR_KEYS = Object.keys(FOREST_THEME.light) as (keyof ThemeColors)[];

export function createDefaultCustomColors(): { light: ThemeColors; dark: ThemeColors } {
  return {
    light: { ...FOREST_THEME.light },
    dark: { ...FOREST_THEME.dark },
  };
}
