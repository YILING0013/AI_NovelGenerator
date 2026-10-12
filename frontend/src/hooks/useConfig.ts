"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { ApiRequestError, apiGet, apiPut } from "@/lib/api";
import {
  buildConfigSavePayload,
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
  conflict: boolean;
}

export function useConfig() {
  const originalConfig = useRef<AppConfig | null>(null);
  const [pendingProviderRenames, setPendingProviderRenames] = useState<ProviderRenameOperation[]>([]);
  const [state, setState] = useState<ConfigState>({
    config: null,
    loading: true,
    saving: false,
    error: null,
    success: null,
    conflict: false,
  });

  const clearMessages = useCallback(() => {
    setState((s) => ({ ...s, error: null, success: null }));
  }, []);

  const fetchConfig = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null, conflict: false }));
    try {
      const res = await apiGet<{ data: AppConfig }>("/api/config");
      const normalized = normalizeAppConfig(res.data);
      originalConfig.current = normalized;
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
      if (!originalConfig.current) return false;
      setState((s) => ({ ...s, saving: true, error: null, success: null, conflict: false }));
      try {
        const payload: AppConfigSavePayload = buildConfigSavePayload(
          data,
          originalConfig.current,
          pendingProviderRenames
        );
        if (Object.keys(payload.patch).length === 0) {
          setState((s) => ({ ...s, saving: false, success: successMsg }));
          return true;
        }
        const res = await apiPut<{ message: string; data: AppConfig }>(
          "/api/config",
          payload
        );
        const normalized = normalizeAppConfig(res.data);
        originalConfig.current = normalized;
        window.dispatchEvent(new CustomEvent("app-config-saved", { detail: normalized }));
        setPendingProviderRenames([]);
        setState((s) => ({
          ...s,
          config: normalized,
          saving: false,
          success: successMsg,
          conflict: false,
        }));
        return true;
      } catch (err) {
        setState((s) => ({
          ...s,
          saving: false,
          error: err instanceof Error ? err.message : "Unknown error",
          conflict: err instanceof ApiRequestError && err.status === 409,
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
