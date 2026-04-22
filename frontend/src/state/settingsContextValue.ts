import { createContext } from "react";

export interface SettingsValue {
  llmModel: string;
  setLlmModel: (model: string) => void;
  resetLlmModel: () => void;
  verboseLogs: boolean;
  setVerboseLogs: (enabled: boolean) => void;
}

export const SettingsContext = createContext<SettingsValue | null>(null);
