"use client";

import { useState, useCallback, useEffect } from "react";
import { apiGet, apiPut } from "@/lib/api";
import {
  normalizeAppConfig,
  type AppConfig,
  type AppConfigSavePayload,
  type ProviderRenameOperation,
} from "@/types/config";

interface ConfigState {
  config: AppConfig | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  success: string | null;
}

export function useConfig() {
  const [pendingProviderRenames, setPendingProviderRenames] = useState<ProviderRenameOperation[]>([]);
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
      setPendingProviderRenames([]);
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
        const payload: AppConfigSavePayload = pendingProviderRenames.length > 0
          ? {
              ...data,
              _provider_renames: pendingProviderRenames,
            }
          : data;
        const res = await apiPut<{ message: string; data: AppConfig }>(
          "/api/config",
          payload
        );
        const normalized = normalizeAppConfig(res.data);
        setPendingProviderRenames([]);
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
    [pendingProviderRenames]
  );

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  return {
    ...state,
    fetchConfig,
    saveConfig,
    queueProviderRename: (rename: ProviderRenameOperation) =>
      setPendingProviderRenames((current) => [...current, rename]),
    setConfig: (config: AppConfig) =>
      setState((s) => ({ ...s, config })),
    clearMessages,
  };
}
