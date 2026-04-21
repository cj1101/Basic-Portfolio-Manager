import { useState, type FormEvent } from "react";
import clsx from "clsx";
import { Plus, RefreshCcw, Search, X } from "lucide-react";
import { usePortfolio } from "@/state/portfolioContext";

const TICKER_REGEX = /^[A-Z0-9.]{1,10}$/;

export function TickerBar() {
  const { tickers, addTicker, removeTicker, refetch, isFetching } = usePortfolio();
  const [raw, setRaw] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const candidate = raw.trim().toUpperCase();
    if (!candidate) return;
    if (!TICKER_REGEX.test(candidate)) {
      setError("Tickers use 1–10 uppercase letters, digits or dots.");
      return;
    }
    addTicker(candidate);
    setRaw("");
  };

  return (
    <section
      aria-labelledby="ticker-bar-heading"
      className="card mb-6 flex flex-col gap-4 p-5"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 id="ticker-bar-heading" className="text-lg font-semibold text-slate-900">
            Stocks in your portfolio
          </h2>
          <p className="text-sm text-slate-500">
            Add 2–30 tickers. The optimizer fetches 5-year daily history and recomputes every
            metric automatically; changes are auto-debounced.
          </p>
        </div>
        <button
          type="button"
          onClick={refetch}
          disabled={isFetching || tickers.length < 2}
          className={clsx(
            "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium shadow-sm transition-colors",
            isFetching || tickers.length < 2
              ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
              : "border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100",
          )}
          aria-label="Re-optimize the portfolio"
        >
          <RefreshCcw
            size={15}
            aria-hidden
            className={clsx(isFetching && "animate-spin")}
          />
          {isFetching ? "Optimizing…" : "Re-optimize"}
        </button>
      </header>

      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="ticker-input">
          Add ticker
        </label>
        <div className="relative flex-1 min-w-[200px]">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
          <input
            id="ticker-input"
            type="text"
            value={raw}
            onChange={(e) => setRaw(e.target.value.toUpperCase())}
            placeholder="e.g. GOOG, BRK.B, META"
            className={clsx(
              "form-input w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm uppercase tracking-wider placeholder:normal-case placeholder:tracking-normal placeholder:text-slate-400 shadow-sm transition-colors hover:border-slate-400 focus:border-brand-500",
              error && "border-rose-400",
            )}
            aria-invalid={error ? "true" : "false"}
            aria-describedby={error ? "ticker-error" : undefined}
          />
        </div>
        <button
          type="submit"
          className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
        >
          <Plus size={16} aria-hidden /> Add
        </button>
      </form>
      {error ? (
        <p id="ticker-error" className="-mt-2 text-xs text-rose-600">
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {tickers.map((ticker) => (
          <span
            key={ticker}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 pl-3 pr-1 py-1 text-sm font-semibold text-slate-800"
          >
            {ticker}
            <button
              type="button"
              onClick={() => removeTicker(ticker)}
              aria-label={`Remove ${ticker}`}
              className="rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>
      {tickers.length < 2 ? (
        <p className="text-xs text-amber-700">
          Add at least 2 tickers to run the optimizer.
        </p>
      ) : null}
    </section>
  );
}
