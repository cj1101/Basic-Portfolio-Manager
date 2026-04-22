import { useContext } from "react";
import { SettingsContext } from "./settingsContextValue";
import type { SettingsValue } from "./settingsContextValue";

export function useSettings(): SettingsValue {
  const ctx = useContext(SettingsContext);
  if (ctx === null) {
    throw new Error("useSettings must be called inside a SettingsProvider.");
  }
  return ctx;
}

export function useSettingsOptional(): SettingsValue | null {
  return useContext(SettingsContext);
}
