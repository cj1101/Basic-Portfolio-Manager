import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { SettingsContext } from "./settingsContextValue";
import type { SettingsValue } from "./settingsContextValue";

/**
 * Per-session UI settings (chat LLM model, verbose logging toggle).
 *
 * Values persist to `localStorage` under stable keys so a reload keeps
 * the user's choice. The SettingsContext is consumed by ChatShell (to
 * forward `llmModel` on every `POST /api/chat` request) and by the
 * Settings panel in Header (to render the combobox).
 *
 * Keeping the context opt-in — `useSettingsContextOptional` returns
 * `null` when no provider is mounted — makes it trivial to render
 * isolated components in tests without rebuilding the entire shell.
 */

export const DEFAULT_LLM_MODEL = "google/gemma-4-31b-it";
const LLM_MODEL_KEY = "pm.settings.llmModel";
const VERBOSE_LOGS_KEY = "pm.settings.verboseLogs";

function readString(key: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  try {
    const v = window.localStorage.getItem(key);
    return typeof v === "string" && v.length > 0 ? v : fallback;
  } catch {
    return fallback;
  }
}

function writeString(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // localStorage unavailable — ignore.
  }
}

function readBool(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  try {
    const v = window.localStorage.getItem(key);
    if (v === "true") return true;
    if (v === "false") return false;
    return fallback;
  } catch {
    return fallback;
  }
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [llmModel, setLlmModelState] = useState<string>(() =>
    readString(LLM_MODEL_KEY, DEFAULT_LLM_MODEL),
  );
  const [verboseLogs, setVerboseLogsState] = useState<boolean>(() =>
    readBool(VERBOSE_LOGS_KEY, false),
  );

  useEffect(() => {
    writeString(LLM_MODEL_KEY, llmModel);
  }, [llmModel]);

  useEffect(() => {
    writeString(VERBOSE_LOGS_KEY, verboseLogs ? "true" : "false");
  }, [verboseLogs]);

  const setLlmModel = useCallback((model: string) => {
    setLlmModelState(model);
  }, []);

  const resetLlmModel = useCallback(() => {
    setLlmModelState(DEFAULT_LLM_MODEL);
  }, []);

  const setVerboseLogs = useCallback((enabled: boolean) => {
    setVerboseLogsState(enabled);
  }, []);

  const value = useMemo<SettingsValue>(
    () => ({ llmModel, setLlmModel, resetLlmModel, verboseLogs, setVerboseLogs }),
    [llmModel, setLlmModel, resetLlmModel, verboseLogs, setVerboseLogs],
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

