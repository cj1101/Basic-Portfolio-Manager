import { useState } from "react";
import clsx from "clsx";
import { ChevronDown, ChevronUp, Lock, SendHorizontal, Sparkles } from "lucide-react";
import type { ChatMessage } from "@/types/contracts";
import { Tooltip } from "../ui/Tooltip";

const SEEDED_CONVERSATION: ChatMessage[] = [
  {
    role: "user",
    content: "Why is NVDA overweighted in my portfolio?",
  },
  {
    role: "assistant",
    content:
      "NVDA's large ORP weight comes from a positive alpha of +57% and a high Sharpe contribution. The ORP optimizer concentrates weight in assets whose excess-return-to-residual-risk ratio is highest — NVDA's alpha dominates despite its higher firm-specific variance.",
  },
  {
    role: "user",
    content: "What happens if I raise my target return to 30%?",
  },
  {
    role: "assistant",
    content:
      "Your target (30%) exceeds the ORP's expected return of 29.4%, which forces leverage. The complete-portfolio weight in the ORP becomes y = (0.30 − r_f) / (E(r_ORP) − r_f) ≈ 1.03, meaning you borrow 3% at the risk-free rate.",
  },
];

const SAMPLE_PROMPTS = [
  "Compare my ORP to a 60/40 benchmark.",
  "What's the biggest drawdown I should expect?",
  "How sensitive is the allocation to my A score?",
];

export function ChatShell() {
  const [open, setOpen] = useState(false);

  return (
    <aside
      aria-label="Portfolio chat assistant (preview)"
      className={clsx(
        "fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-8px_24px_rgba(15,23,42,0.06)] backdrop-blur transition-transform",
      )}
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
            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
              Preview · Phase 3
            </span>
          </span>
          {open ? (
            <ChevronDown size={16} className="text-slate-500" aria-hidden />
          ) : (
            <ChevronUp size={16} className="text-slate-500" aria-hidden />
          )}
        </button>

        {open ? (
          <div id="chat-panel" className="flex flex-col gap-3 pb-4">
            <div
              className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3"
              aria-live="polite"
            >
              <ul className="flex flex-col gap-2">
                {SEEDED_CONVERSATION.map((m, i) => (
                  <li
                    key={i}
                    className={clsx(
                      "max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed",
                      m.role === "user"
                        ? "self-end bg-brand-600 text-white"
                        : "self-start border border-slate-200 bg-white text-slate-700",
                    )}
                  >
                    {m.content}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex flex-wrap gap-2" aria-label="Sample questions">
              {SAMPLE_PROMPTS.map((p) => (
                <Tooltip key={p} label="Chat is read-only until Phase 3.">
                  <button
                    type="button"
                    disabled
                    className="inline-flex cursor-not-allowed items-center rounded-full border border-dashed border-slate-300 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-400"
                  >
                    {p}
                  </button>
                </Tooltip>
              ))}
            </div>

            <form
              className="flex items-start gap-2"
              onSubmit={(e) => e.preventDefault()}
              aria-disabled="true"
            >
              <label htmlFor="chat-input" className="sr-only">
                Ask a question about your portfolio
              </label>
              <textarea
                id="chat-input"
                disabled
                rows={2}
                placeholder="Chat is read-only in Phase 1 — Phase 3 wires this up to the LLM."
                className="form-textarea flex-1 resize-none rounded-lg border border-slate-300 bg-slate-50 p-2 text-sm text-slate-500 placeholder:text-slate-400 disabled:cursor-not-allowed"
              />
              <Tooltip label="Chat coming in Phase 3 — the UI is ready but the backend is not yet wired.">
                <button
                  type="button"
                  disabled
                  aria-label="Send message (disabled)"
                  className="inline-flex h-10 items-center gap-1.5 self-end rounded-lg border border-slate-300 bg-slate-100 px-3 text-sm font-semibold text-slate-400"
                >
                  <Lock size={14} aria-hidden />
                  <SendHorizontal size={14} aria-hidden />
                </button>
              </Tooltip>
            </form>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
