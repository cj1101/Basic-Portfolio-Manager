import { AlertTriangle, Loader2, RefreshCcw } from "lucide-react";
import type { PropsWithChildren } from "react";
import type { ErrorCode } from "@/types/contracts";
import type { ApiError } from "@/lib/api";
import { usePortfolio } from "@/state/portfolioContext";
import { EmptyState } from "./EmptyState";

/**
 * Wrap any component that reads `result` from the portfolio context so it
 * renders a skeleton while `/api/optimize` is fetching, a helpful error
 * panel on failure, and falls through to its children on success.
 *
 * We intentionally keep reading from the context (not props) — this keeps
 * every tab tiny and leaves the boundary as the single place where loading
 * and error UX live.
 */
export function ResultBoundary({ children }: PropsWithChildren) {
  const { status, error, refetch, isFallbackResult, isFetching } = usePortfolio();

  if (status === "error" && error) {
    return <ErrorPanel error={error} onRetry={refetch} isRetrying={isFetching} />;
  }

  if (status === "loading" && isFallbackResult) {
    return <LoadingSkeleton />;
  }

  return <>{children}</>;
}

function LoadingSkeleton() {
  return (
    <EmptyState
      icon={<Loader2 size={28} className="animate-spin" aria-hidden />}
      title="Optimizing your portfolio…"
      description="Fetching 5-year histories and solving the tangency portfolio. Usually takes a second."
    />
  );
}

function describe(error: ApiError): { title: string; body: string } {
  const ticker = (error.details as { ticker?: string } | undefined)?.ticker;
  const mapping: Record<ErrorCode, { title: string; body: string }> = {
    UNKNOWN_TICKER: {
      title: `Ticker ${ticker ?? ""} not recognized`.trim(),
      body: "Alpha Vantage and Yahoo both rejected this symbol. Double-check the spelling and try again.",
    },
    INSUFFICIENT_HISTORY: {
      title: "Not enough history",
      body: "At least one ticker in your universe doesn't have enough overlapping daily history to compute meaningful statistics.",
    },
    DATA_PROVIDER_RATE_LIMIT: {
      title: "Data provider rate-limited",
      body:
        error.retryAfterSeconds != null
          ? `Alpha Vantage / Yahoo are rate-limiting requests. Retry in ~${Math.ceil(error.retryAfterSeconds)}s.`
          : "Alpha Vantage / Yahoo are rate-limiting requests. Try again in a minute.",
    },
    DATA_PROVIDER_UNAVAILABLE: {
      title: "Data provider unavailable",
      body: "We couldn't reach Alpha Vantage or Yahoo. Check your connection or try again shortly.",
    },
    OPTIMIZER_INFEASIBLE: {
      title: "Portfolio is infeasible",
      body: "The optimizer couldn't solve this universe — try removing correlated or negative-premium assets.",
    },
    OPTIMIZER_NON_PSD_COVARIANCE: {
      title: "Covariance matrix issue",
      body: "The covariance estimate isn't positive semi-definite. Try a longer lookback or a different return frequency.",
    },
    INVALID_RISK_PROFILE: {
      title: "Risk profile can't produce a portfolio",
      body: "With the current inputs, utility-max allocation would require shorting the ORP. Lower your target return or reduce risk aversion.",
    },
    INVALID_RETURN_WINDOW: {
      title: "Invalid request",
      body: error.message,
    },
    LLM_UNAVAILABLE: {
      title: "Chat is temporarily unavailable",
      body: "The assistant is offline; the optimizer itself is unaffected.",
    },
    INVALID_VALUATION: {
      title: "Invalid valuation inputs",
      body: error.message || "Discount rate must exceed growth in DDM / terminal models.",
    },
    INTERNAL: {
      title: "Something went wrong on our side",
      body: error.message || "An unexpected error occurred.",
    },
  };
  return mapping[error.code] ?? mapping.INTERNAL;
}

function ErrorPanel({
  error,
  onRetry,
  isRetrying,
}: {
  error: ApiError;
  onRetry: () => void;
  isRetrying: boolean;
}) {
  const { title, body } = describe(error);
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 p-5"
    >
      <div className="flex items-center gap-2 text-rose-900">
        <AlertTriangle size={18} aria-hidden />
        <h3 className="text-base font-semibold">{title}</h3>
      </div>
      <p className="text-sm leading-relaxed text-rose-800">{body}</p>
      <p className="text-xs font-mono text-rose-700/70">
        {error.code}
        {error.status ? ` · HTTP ${error.status}` : ""}
      </p>
      <button
        type="button"
        onClick={onRetry}
        disabled={isRetrying}
        className="inline-flex items-center gap-2 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-sm font-semibold text-rose-800 shadow-sm transition-colors hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <RefreshCcw size={14} aria-hidden className={isRetrying ? "animate-spin" : undefined} />
        {isRetrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}
