"use client";

import { useState, useCallback, useEffect } from "react";
import { apiGet, apiPut } from "@/lib/api";
import { normalizeAppConfig, type AppConfig } from "@/types/config";

interface ConfigState {
  config: AppConfig | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
}

export function useConfig() {
  const [state, setState] = useState<ConfigState>({
    config: null,
    loading: true,
    saving: false,
    error: null,
    success: null,
  });

  const clearMessages = useCallback(() => {
    setState((s) => ({ ...s, error: null, success: null }));
  }, []);

  const fetchConfig = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await apiGet<{ data: AppConfig }>("/api/config");
      const normalized = normalizeAppConfig(res.data);
      setState((s) => ({
        ...s,
        config: normalized,
        loading: false,
      }));
      return normalized;
    } catch (err) {
      setState((s) => ({
        ...s,
        loading: false,
        error: err instanceof Error ? err.message : "Unknown error",
      }));
      return null;
    }
  }, []);

  const saveConfig = useCallback(
    async (data: AppConfig, successMsg: string) => {
      setState((s) => ({ ...s, saving: true, error: null, success: null }));
      try {
        const res = await apiPut<{ message: string; data: AppConfig }>(
          "/api/config",
          data
        );
        const normalized = normalizeAppConfig(res.data);
        setState((s) => ({
          ...s,
          config: normalized,
          saving: false,
          success: successMsg,
        }));
        return true;
      } catch (err) {
        setState((s) => ({
          ...s,
          saving: false,
          error: err instanceof Error ? err.message : "Unknown error",
        }));
        return false;
      }
    },
    []
  );

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return {
    ...state,
    fetchConfig,
    saveConfig,
    setConfig: (config: AppConfig) =>
      setState((s) => ({ ...s, config })),
    clearMessages,
  };
}
