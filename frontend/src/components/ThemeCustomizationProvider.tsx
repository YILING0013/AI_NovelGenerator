"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from "react";
import { useTheme } from "next-themes";
import type { ThemeColors } from "@/lib/themes";
import {
  THEME_PRESETS,
  DEFAULT_PRESET_ID,
  getPreset,
  createDefaultCustomColors,
} from "@/lib/themes";

const STORAGE_PRESET_KEY = "novel-theme-preset";
const STORAGE_CUSTOM_KEY = "novel-theme-custom";

type StoredThemeColors = { light: ThemeColors; dark: ThemeColors };

interface ThemeCustomizationState {
  presetId: string;
  customColors: StoredThemeColors;
}

/* 上下文类型 */
interface ThemeCustomizationContextValue {
  presetId: string;
  customLight: ThemeColors;
  customDark: ThemeColors;
  selectPreset: (id: string) => void;
  setCustomColors: (light: ThemeColors, dark: ThemeColors) => void;
}

const ThemeCustomizationContext =
  createContext<ThemeCustomizationContextValue | null>(null);

export function useThemeCustomization() {
  const ctx = useContext(ThemeCustomizationContext);
  if (!ctx) {
    throw new Error(
      "useThemeCustomization must be used within ThemeCustomizationProvider",
    );
  }

  return ctx;
}

/* 工具方法 */
function applyColors(colors: ThemeColors) {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(colors)) {
    root.style.setProperty(key, value);
  }
}

function readStorage<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* 忽略存储额度错误 */
  }
}

function createDefaultThemeCustomizationState(): ThemeCustomizationState {
  return {
    presetId: DEFAULT_PRESET_ID,
    customColors: createDefaultCustomColors(),
  };
}

const DEFAULT_THEME_CUSTOMIZATION_STATE =
  createDefaultThemeCustomizationState();

let currentThemeCustomizationState = DEFAULT_THEME_CUSTOMIZATION_STATE;
let hasLoadedThemeCustomizationState = false;
const themeCustomizationListeners = new Set<() => void>();

function normalizePresetId(id: string | null): string {
  if (id === "custom") {
    return id;
  }

  return id && getPreset(id) ? id : DEFAULT_PRESET_ID;
}

function readThemeCustomizationState(): ThemeCustomizationState {
  const stored = readStorage<StoredThemeColors>(STORAGE_CUSTOM_KEY);

  return {
    presetId: normalizePresetId(localStorage.getItem(STORAGE_PRESET_KEY)),
    customColors:
      stored?.light && stored?.dark
        ? stored
        : createDefaultCustomColors(),
  };
}

function getThemeCustomizationSnapshot(): ThemeCustomizationState {
  if (typeof window !== "undefined" && !hasLoadedThemeCustomizationState) {
    currentThemeCustomizationState = readThemeCustomizationState();
    hasLoadedThemeCustomizationState = true;
  }

  return currentThemeCustomizationState;
}

function getThemeCustomizationServerSnapshot(): ThemeCustomizationState {
  return DEFAULT_THEME_CUSTOMIZATION_STATE;
}

function emitThemeCustomizationChange(nextState?: ThemeCustomizationState) {
  if (typeof window === "undefined") {
    return;
  }

  hasLoadedThemeCustomizationState = true;
  currentThemeCustomizationState = nextState ?? readThemeCustomizationState();
  themeCustomizationListeners.forEach((listener) => listener());
}

function subscribeThemeCustomization(listener: () => void) {
  themeCustomizationListeners.add(listener);

  if (typeof window === "undefined") {
    return () => {
      themeCustomizationListeners.delete(listener);
    };
  }

  const handleStorage = (event: StorageEvent) => {
    if (
      event.key &&
      event.key !== STORAGE_PRESET_KEY &&
      event.key !== STORAGE_CUSTOM_KEY
    ) {
      return;
    }

    emitThemeCustomizationChange();
  };

  window.addEventListener("storage", handleStorage);

  return () => {
    themeCustomizationListeners.delete(listener);
    window.removeEventListener("storage", handleStorage);
  };
}

/* 主题自定义 Provider */
export function ThemeCustomizationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { resolvedTheme } = useTheme();
  const { presetId, customColors } = useSyncExternalStore(
    subscribeThemeCustomization,
    getThemeCustomizationSnapshot,
    getThemeCustomizationServerSnapshot,
  );

  /* 在主题或配色变化时同步 CSS 变量 */
  useEffect(() => {
    const isDark = resolvedTheme === "dark";
    let colors: ThemeColors;

    if (presetId === "custom") {
      colors = isDark ? customColors.dark : customColors.light;
    } else {
      const preset = getPreset(presetId) || THEME_PRESETS[0];
      colors = isDark ? preset.dark : preset.light;
    }

    applyColors(colors);
  }, [resolvedTheme, presetId, customColors]);

  /* 对外操作 */
  const selectPreset = useCallback(
    (id: string) => {
      const nextPresetId = normalizePresetId(id);

      try {
        localStorage.setItem(STORAGE_PRESET_KEY, nextPresetId);
      } catch {
        /* 忽略存储异常 */
      }

      emitThemeCustomizationChange({
        presetId: nextPresetId,
        customColors,
      });
    },
    [customColors],
  );

  const setCustomColors = useCallback((light: ThemeColors, dark: ThemeColors) => {
    const next = { light, dark };

    try {
      localStorage.setItem(STORAGE_PRESET_KEY, "custom");
    } catch {
      /* 忽略存储异常 */
    }

    writeStorage(STORAGE_CUSTOM_KEY, next);
    emitThemeCustomizationChange({
      presetId: "custom",
      customColors: next,
    });
  }, []);

  const value = useMemo(
    () => ({
      presetId,
      customLight: customColors.light,
      customDark: customColors.dark,
      selectPreset,
      setCustomColors,
    }),
    [presetId, customColors, selectPreset, setCustomColors],
  );

  return (
    <ThemeCustomizationContext.Provider value={value}>
      {children}
    </ThemeCustomizationContext.Provider>
  );
}
