import { useId, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { Settings as SettingsIcon, X, Loader2, AlertTriangle } from "lucide-react";
import { useLlmDefault, useLlmModels, useUpdateApiKey } from "@/lib/queries";
import { DEFAULT_LLM_MODEL } from "@/state/settingsContext";
import { useSettings } from "@/state/settingsHooks";
import { ApiError } from "@/lib/api";
import type { ApiKeyName } from "@/types/contracts";

/**
 * Settings panel opened from the gear icon in the header.
 *
 * The LLM model selector is the main concern: the frontend fetches the
 * full list of OpenRouter models from `GET /api/llm/models` (proxied by
 * the backend so the API key stays server-side) and renders a filterable
 * combobox. Users may also paste a custom slug into the text field —
 * the backend validates it against a safe regex before forwarding.
 */
export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const settings = useSettings();
  const modelsQuery = useLlmModels();
  const defaultQuery = useLlmDefault();
  const [query, setQuery] = useState(settings.llmModel);
  const inputId = useId();
  const listId = useId();
  const apiKeyId = useId();
  const apiKeyValueId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const updateApiKey = useUpdateApiKey();
  const [selectedApiKey, setSelectedApiKey] = useState<ApiKeyName>("OPENROUTER_API_KEY");
  const [apiKeyValue, setApiKeyValue] = useState("");
  const [apiKeyStatus, setApiKeyStatus] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<"overwrite" | "create" | null>(
    null,
  );

  const models = useMemo(() => modelsQuery.data?.models ?? [], [modelsQuery.data?.models]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return models.slice(0, 30);
    return models
      .filter(
        (m) =>
          m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q),
      )
      .slice(0, 50);
  }, [models, query]);

  function applyModel(slug: string) {
    const trimmed = slug.trim();
    if (!trimmed) return;
    settings.setLlmModel(trimmed);
  }

  function handleReset() {
    settings.resetLlmModel();
    setQuery(DEFAULT_LLM_MODEL);
  }

  const llmAvailable = defaultQuery.data?.llmAvailable ?? false;
  const backendDefault = defaultQuery.data?.defaultModel ?? DEFAULT_LLM_MODEL;
  const modelsError =
    modelsQuery.error instanceof ApiError ? modelsQuery.error : null;
  const apiKeyError = updateApiKey.error instanceof ApiError ? updateApiKey.error : null;

  async function submitApiKey(options?: {
    confirmOverwrite?: boolean;
    confirmCreate?: boolean;
  }) {
    const response = await updateApiKey.mutateAsync({
      keyName: selectedApiKey,
      newValue: apiKeyValue,
      ...(options?.confirmOverwrite !== undefined
        ? { confirmOverwrite: options.confirmOverwrite }
        : {}),
      ...(options?.confirmCreate !== undefined ? { confirmCreate: options.confirmCreate } : {}),
    });
    setApiKeyStatus(response.message);
    if (response.requiresConfirmation && response.confirmationType) {
      setPendingConfirmation(response.confirmationType);
      return;
    }
    setPendingConfirmation(null);
    if (response.updated) {
      setApiKeyValue("");
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={`${inputId}-title`}
      className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 px-4 pt-24"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2
              id={`${inputId}-title`}
              className="flex items-center gap-2 text-lg font-semibold text-slate-900"
            >
              <SettingsIcon size={18} aria-hidden />
              Settings
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Configure the OpenRouter model used by the chat assistant.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="rounded-full border border-slate-200 bg-white p-1 text-slate-500 transition hover:border-slate-400 hover:text-slate-800"
          >
            <X size={14} aria-hidden />
          </button>
        </div>

        <section className="mt-5 flex flex-col gap-2">
          <label htmlFor={inputId} className="text-sm font-medium text-slate-700">
            Chat LLM model
          </label>
          <div className="relative">
            <input
              id={inputId}
              type="text"
              list={listId}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onBlur={() => applyModel(query)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  applyModel(query);
                }
              }}
              spellCheck={false}
              autoComplete="off"
              placeholder="e.g. google/gemma-4-31b-it"
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
            />
            <datalist id={listId}>
              {filtered.map((m) => (
                <option key={m.id} value={m.id} label={m.name} />
              ))}
            </datalist>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <span>Active:</span>
              <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-800">
                {settings.llmModel}
              </code>
            </div>
            <button
              type="button"
              onClick={handleReset}
              className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-800"
            >
              Reset to {backendDefault}
            </button>
          </div>

          {modelsQuery.isLoading ? (
            <p className="flex items-center gap-1.5 text-xs text-slate-500">
              <Loader2 size={12} className="animate-spin" aria-hidden />
              Loading OpenRouter catalogue…
            </p>
          ) : modelsError ? (
            <p
              role="alert"
              className="flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-800"
            >
              <AlertTriangle size={14} aria-hidden className="mt-0.5" />
              <span>
                Could not load the OpenRouter model list ({modelsError.code}).
                You can still type a slug manually.
              </span>
            </p>
          ) : (
            <p className="text-[11px] text-slate-500">
              {models.length.toLocaleString()} models available · {filtered.length} shown.
            </p>
          )}

          {!llmAvailable && !defaultQuery.isLoading ? (
            <p
              role="note"
              className="rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-amber-800"
            >
              <strong className="font-semibold">LLM not configured.</strong>{" "}
              The backend has no <code>OPENROUTER_API_KEY</code>. Chat will stay rule-only until it is set.
            </p>
          ) : null}
        </section>

        <section className="mt-4 flex flex-col gap-2 border-t border-slate-200 pt-4">
          <label htmlFor={apiKeyId} className="text-sm font-medium text-slate-700">
            API key name
          </label>
          <select
            id={apiKeyId}
            value={selectedApiKey}
            onChange={(e) => setSelectedApiKey(e.target.value as ApiKeyName)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
          >
            <option value="OPENROUTER_API_KEY">OPENROUTER_API_KEY</option>
            <option value="ALPHA_VANTAGE_API_KEY">ALPHA_VANTAGE_API_KEY</option>
            <option value="FRED_API_KEY">FRED_API_KEY</option>
          </select>

          <label htmlFor={apiKeyValueId} className="text-sm font-medium text-slate-700">
            New API key value
          </label>
          <input
            id={apiKeyValueId}
            type="password"
            value={apiKeyValue}
            onChange={(e) => setApiKeyValue(e.target.value)}
            autoComplete="off"
            placeholder="Enter new key value"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
          />

          <button
            type="button"
            onClick={() => void submitApiKey()}
            disabled={updateApiKey.isPending}
            className="self-start rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {updateApiKey.isPending ? "Updating..." : "Update key"}
          </button>

          {apiKeyStatus ? (
            <p className="text-[11px] text-slate-500">{apiKeyStatus}</p>
          ) : null}
          {apiKeyError ? (
            <p className="text-xs text-red-600">
              Could not update key ({apiKeyError.code}).
            </p>
          ) : null}
          <p className="text-[11px] text-slate-500">
            Updates are written to <code>backend/.env</code>. Restart backend after successful
            save to apply changes.
          </p>
        </section>

        {modelsQuery.data && filtered.length > 0 ? (
          <section className="mt-4 flex flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Quick picks
            </span>
            <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto rounded border border-slate-200 bg-slate-50 p-2">
              {filtered.slice(0, 15).map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(m.id);
                      applyModel(m.id);
                    }}
                    className={clsx(
                      "flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs transition",
                      settings.llmModel === m.id
                        ? "bg-brand-50 text-brand-800"
                        : "hover:bg-white",
                    )}
                  >
                    <span className="flex flex-col">
                      <span className="font-mono text-[11px] text-slate-800">
                        {m.id}
                      </span>
                      <span className="text-[10px] text-slate-500">{m.name}</span>
                    </span>
                    {m.contextLength ? (
                      <span className="text-[10px] text-slate-500">
                        {m.contextLength.toLocaleString()} ctx
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
      {pendingConfirmation ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/45 px-4">
          <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-4 shadow-xl">
            <p className="text-sm font-semibold text-slate-900">
              {pendingConfirmation === "overwrite"
                ? "Confirm overwrite of existing key?"
                : "Confirm creation of missing key?"}
            </p>
            <p className="mt-1 text-xs text-slate-600">
              {selectedApiKey} will be updated in <code>backend/.env</code>.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPendingConfirmation(null)}
                className="rounded border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:border-slate-400"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() =>
                  void submitApiKey({
                    confirmOverwrite: pendingConfirmation === "overwrite",
                    confirmCreate: pendingConfirmation === "create",
                  })
                }
                className="rounded border border-brand-500 bg-brand-500 px-3 py-1 text-xs font-medium text-white hover:bg-brand-600"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function SettingsButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label="Open settings"
      className="rounded-full border border-slate-300 bg-white p-2 text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
    >
      <SettingsIcon size={16} aria-hidden />
    </button>
  );
}
