import { useEffect, useId, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { AlertTriangle, ChevronDown, ChevronUp, SendHorizontal, Sparkles, Trash2 } from "lucide-react";
import type {
  ChatCitation,
  ChatHistoryEntry,
  ChatMode,
  ChatRequest,
  CompletePortfolio,
  OptimizationResult,
} from "@/types/contracts";
import { ApiError } from "@/lib/api";
import {
  useChatSession,
  useDeleteChatSession,
  useLlmDefault,
  useSendChatMessage,
} from "@/lib/queries";
import { usePortfolio } from "@/state/portfolioContext";
import { useSettingsOptional } from "@/state/settingsContext";
import { Tooltip } from "../ui/Tooltip";

const SESSION_STORAGE_KEY = "pm.chat.sessionId";

const SAMPLE_PROMPTS: string[] = [
  "Why is NVDA overweight?",
  "What's my Sharpe?",
  "What happens if I raise my target return to 30%?",
  "Explain the efficient frontier.",
];

type ModeOption = { value: ChatMode; label: string; hint: string };

const MODE_OPTIONS: readonly ModeOption[] = [
  { value: "auto", label: "Auto", hint: "Rule engine first, LLM fallback on miss" },
  { value: "rule", label: "Rule", hint: "Deterministic rule-based answers only" },
  {
    value: "llm",
    label: "LLM",
    hint: "Always go to the OpenRouter LLM (requires OPENROUTER_API_KEY)",
  },
];

function readStoredSessionId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const fresh =
      typeof window.crypto?.randomUUID === "function"
        ? window.crypto.randomUUID()
        : `sess-${Math.random().toString(36).slice(2)}${Date.now()}`;
    window.localStorage.setItem(SESSION_STORAGE_KEY, fresh);
    return fresh;
  } catch {
    return "";
  }
}

function resetStoredSessionId(): string {
  if (typeof window === "undefined") return "";
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // localStorage unavailable — ignore.
  }
  return readStoredSessionId();
}

interface UiMessage {
  role: "user" | "assistant";
  content: string;
  source?: "rule" | "llm";
  citations: ChatCitation[];
  pending?: boolean;
}

function toUi(entry: ChatHistoryEntry): UiMessage {
  const base: UiMessage = {
    role: entry.role,
    content: entry.content,
    citations: entry.citations,
  };
  return entry.source ? { ...base, source: entry.source } : base;
}

export function ChatShell() {
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<ChatMode>("auto");
  const [llmUnavailable, setLlmUnavailable] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [pendingUser, setPendingUser] = useState<UiMessage | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const formId = useId();

  useEffect(() => {
    setSessionId(readStoredSessionId());
  }, []);

  const portfolio = usePortfolio();
  const serverContext = portfolio.result;
  const hasPortfolio = !!serverContext;
  const settings = useSettingsOptional();
  const defaultQuery = useLlmDefault();

  useEffect(() => {
    if (defaultQuery.data && !defaultQuery.data.llmAvailable) {
      setLlmUnavailable(true);
    }
  }, [defaultQuery.data]);

  const sessionQuery = useChatSession(sessionId || null);
  const sendMutation = useSendChatMessage(sessionId || null);
  const deleteMutation = useDeleteChatSession(sessionId || null);

  const persisted: UiMessage[] = useMemo(() => {
    const entries = sessionQuery.data?.messages ?? [];
    return entries.map(toUi);
  }, [sessionQuery.data]);

  const messages: UiMessage[] = useMemo(() => {
    if (!pendingUser) return persisted;
    return [...persisted, pendingUser];
  }, [persisted, pendingUser]);

  // Auto-scroll to the bottom whenever the message list grows.
  useEffect(() => {
    if (!listRef.current) return;
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages.length, open]);

  async function handleSubmit(prompt: string) {
    const text = prompt.trim();
    if (!text || !sessionId) return;
    setLocalError(null);

    // Build the outgoing transcript: full persisted history + the new user turn.
    const outgoingMessages = [
      ...persisted.map((m) => ({ role: m.role, content: m.content })),
      { role: "user" as const, content: text },
    ];
    const pending: UiMessage = {
      role: "user",
      content: text,
      citations: [],
      pending: true,
    };
    setPendingUser(pending);
    setDraft("");

    const body: ChatRequest = {
      messages: outgoingMessages,
      mode,
      sessionId,
      ...(settings?.llmModel ? { model: settings.llmModel } : {}),
      ...(serverContext
        ? { portfolioContext: stripDerivedComplete(serverContext) }
        : {}),
    };
    try {
      await sendMutation.mutateAsync(body);
    } catch (err) {
      if (err instanceof ApiError && err.code === "LLM_UNAVAILABLE") {
        setLlmUnavailable(true);
        if (mode === "llm") setMode("auto");
        setLocalError(err.message);
      } else if (err instanceof ApiError) {
        setLocalError(err.message);
      } else {
        setLocalError("Unexpected error sending message.");
      }
    } finally {
      setPendingUser(null);
    }
  }

  function handleClear() {
    deleteMutation.mutate(undefined, {
      onSuccess: () => {
        setSessionId(resetStoredSessionId());
        setPendingUser(null);
        setLocalError(null);
      },
    });
  }

  const canSend =
    open &&
    !!sessionId &&
    !sendMutation.isPending &&
    !!draft.trim();

  return (
    <aside
      aria-label="Portfolio chat assistant"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-8px_24px_rgba(15,23,42,0.06)] backdrop-blur"
    >
      <div className="mx-auto flex max-w-6xl flex-col px-6">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="chat-panel"
          className="flex items-center justify-between gap-3 py-3 text-left"
        >
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <Sparkles size={16} className="text-brand-600" aria-hidden />
            Ask the Portfolio Manager
            {llmUnavailable ? (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                Rule-only
              </span>
            ) : null}
          </span>
          {open ? (
            <ChevronDown size={16} className="text-slate-500" aria-hidden />
          ) : (
            <ChevronUp size={16} className="text-slate-500" aria-hidden />
          )}
        </button>

        {open ? (
          <div id="chat-panel" className="flex flex-col gap-3 pb-4">
            {llmUnavailable ? (
              <div
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
              >
                <AlertTriangle size={14} className="mt-0.5" aria-hidden />
                <div>
                  <strong className="font-semibold">LLM unavailable.</strong>{" "}
                  The backend couldn&apos;t reach OpenRouter (likely{" "}
                  <code>OPENROUTER_API_KEY</code> is unset). Rule-based answers
                  still work; the LLM toggle is disabled.
                </div>
              </div>
            ) : null}

            <ul
              ref={listRef}
              role="log"
              aria-live="polite"
              aria-label="Chat transcript"
              className="flex max-h-64 min-h-[140px] flex-col gap-2 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3"
            >
              {messages.length === 0 ? (
                <li className="text-center text-xs text-slate-500">
                  Ask about your Sharpe, top holdings, or any term in the SPEC glossary.
                </li>
              ) : null}
              {messages.map((m, i) => (
                <li
                  key={`${m.role}-${i}-${m.content.slice(0, 12)}`}
                  className={clsx(
                    "flex max-w-[85%] flex-col gap-1",
                    m.role === "user" ? "self-end" : "self-start",
                  )}
                >
                  <div
                    className={clsx(
                      "rounded-2xl px-3 py-2 text-sm leading-relaxed",
                      m.role === "user"
                        ? "bg-brand-600 text-white"
                        : "border border-slate-200 bg-white text-slate-700",
                      m.pending ? "opacity-70" : null,
                    )}
                  >
                    {m.content}
                  </div>
                  {m.role === "assistant" && m.source ? (
                    <span className="text-[10px] uppercase tracking-wide text-slate-400">
                      via {m.source}
                    </span>
                  ) : null}
                  {m.citations.length > 0 ? (
                    <ul
                      aria-label="Citations"
                      className="flex flex-wrap gap-1.5"
                    >
                      {m.citations.map((c, idx) => (
                        <li
                          key={`${c.label}-${idx}`}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600"
                        >
                          <span className="text-slate-500">{c.label}</span>
                          <span className="font-semibold text-slate-800">{c.value}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
              {sendMutation.isPending ? (
                <li className="self-start text-xs italic text-slate-400">
                  Thinking…
                </li>
              ) : null}
            </ul>

            {localError && !llmUnavailable ? (
              <p role="alert" className="text-xs text-red-600">
                {localError}
              </p>
            ) : null}

            <div
              role="radiogroup"
              aria-label="Answer mode"
              className="flex flex-wrap items-center gap-2 text-xs"
            >
              <span className="font-medium text-slate-500">Mode:</span>
              {MODE_OPTIONS.map((opt) => {
                const disabled = opt.value === "llm" && llmUnavailable;
                const control = (
                  <label
                    key={opt.value}
                    className={clsx(
                      "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 transition",
                      mode === opt.value
                        ? "border-brand-500 bg-brand-50 text-brand-700"
                        : "border-slate-300 bg-white text-slate-600 hover:border-slate-400",
                      disabled ? "cursor-not-allowed opacity-50" : null,
                    )}
                  >
                    <input
                      type="radio"
                      name={`${formId}-mode`}
                      value={opt.value}
                      checked={mode === opt.value}
                      disabled={disabled}
                      onChange={() => setMode(opt.value)}
                      className="sr-only"
                    />
                    {opt.label}
                  </label>
                );
                return disabled ? (
                  <Tooltip
                    key={opt.value}
                    label="OPENROUTER_API_KEY is unset on the backend (LLM_UNAVAILABLE)."
                  >
                    {control}
                  </Tooltip>
                ) : (
                  <Tooltip key={opt.value} label={opt.hint}>
                    {control}
                  </Tooltip>
                );
              })}
              {settings ? (
                <Tooltip
                  label={`Chat LLM model (change in Settings). OpenRouter default: ${defaultQuery.data?.defaultModel ?? "google/gemma-4-31b-it"}.`}
                >
                  <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[10px] text-slate-600">
                    model: {settings.llmModel}
                  </span>
                </Tooltip>
              ) : null}
              <button
                type="button"
                onClick={handleClear}
                disabled={!persisted.length || deleteMutation.isPending}
                className="ml-auto inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-500 transition hover:border-slate-400 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Trash2 size={12} aria-hidden />
                Clear history
              </button>
            </div>

            <div className="flex flex-wrap gap-2" aria-label="Sample questions">
              {SAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  disabled={sendMutation.isPending || !sessionId}
                  onClick={() => void handleSubmit(p)}
                  className="inline-flex items-center rounded-full border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {p}
                </button>
              ))}
            </div>

            <form
              className="flex items-start gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void handleSubmit(draft);
              }}
            >
              <label htmlFor={`${formId}-chat-input`} className="sr-only">
                Ask a question about your portfolio
              </label>
              <textarea
                id={`${formId}-chat-input`}
                rows={2}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSubmit(draft);
                  }
                }}
                placeholder={
                  hasPortfolio
                    ? "Ask about your portfolio — e.g. 'Why is NVDA overweight?'"
                    : "Waiting for an optimizer result…"
                }
                className="form-textarea flex-1 resize-none rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-700 placeholder:text-slate-400"
              />
              <button
                type="submit"
                disabled={!canSend}
                aria-label="Send message"
                className="inline-flex h-10 items-center gap-1.5 self-end rounded-lg border border-brand-500 bg-brand-600 px-3 text-sm font-semibold text-white transition hover:bg-brand-500 disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-400"
              >
                <SendHorizontal size={14} aria-hidden />
                Send
              </button>
            </form>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

/**
 * The provider decorates `complete` with client-only fields
 * (`targetReturnOverride`, `yUtility`, `yTarget`) so the risk slider can
 * explain overrides live. The backend's `CompletePortfolio` Pydantic model
 * has `extra="forbid"`, so we rebuild the payload with only the wire fields
 * before sending it as chat context.
 */
function stripDerivedComplete(result: OptimizationResult): OptimizationResult {
  const { complete, ...rest } = result;
  const sanitized: CompletePortfolio = {
    yStar: complete.yStar,
    weightRiskFree: complete.weightRiskFree,
    weights: complete.weights,
    expectedReturn: complete.expectedReturn,
    stdDev: complete.stdDev,
    leverageUsed: complete.leverageUsed,
  };
  return { ...rest, complete: sanitized };
}
