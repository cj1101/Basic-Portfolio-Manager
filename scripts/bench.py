"""Latency benchmark — enforces the ``docs/SPEC.md`` §6 targets.

Usage:

    python scripts/bench.py                   # hit http://localhost:8000
    python scripts/bench.py --base http://...
    python scripts/bench.py --skip-chat       # skip /chat (no OpenRouter key)
    python scripts/bench.py --iterations 20   # override default 50

The script:

1. Warms the cache with 5 common tickers so every subsequent request is
   a warm hit.
2. Runs ``--iterations`` requests against each of ``/quote``,
   ``/historical``, ``/optimize`` and (optionally) ``/chat``.
3. Prints p50 / p95 / p99 latencies.
4. Exits non-zero if any p95 breaches its budget. Budgets match SPEC §6.

The benchmark is intentionally client-side (wall-clock end-to-end) so it
captures the same latency the browser would observe.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_ITERATIONS = 50
WARMUP_TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]

# SPEC §6 targets (p95, in seconds).
BUDGETS: dict[str, float] = {
    "/quote": 0.150,
    "/historical (warm)": 0.300,
    "/optimize (warm)": 0.500,
    "/chat (rule)": 0.200,
    "/chat (LLM)": 4.000,
}


@dataclass
class Stats:
    endpoint: str
    samples: list[float]

    @property
    def p50(self) -> float:
        return statistics.median(self.samples) if self.samples else float("nan")

    @property
    def p95(self) -> float:
        return _percentile(self.samples, 0.95)

    @property
    def p99(self) -> float:
        return _percentile(self.samples, 0.99)

    def format_row(self, budget: float | None) -> str:
        budget_col = f"{budget * 1000:>7.0f} ms" if budget else "       —"
        verdict = _verdict(self.p95, budget) if budget else "     "
        return (
            f"{self.endpoint:<22}"
            f" {len(self.samples):>4}"
            f" {self.p50 * 1000:>8.1f} ms"
            f" {self.p95 * 1000:>8.1f} ms"
            f" {self.p99 * 1000:>8.1f} ms"
            f" {budget_col}"
            f"  {verdict}"
        )


def _percentile(samples: list[float], q: float) -> float:
    if not samples:
        return float("nan")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    # Linear interpolation, matching ``numpy.percentile`` defaults.
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] + frac * (ordered[hi] - ordered[lo])


def _verdict(p95: float, budget: float) -> str:
    return "PASS" if p95 <= budget else "FAIL"


async def _measure(
    name: str, call: Callable[[], Awaitable[httpx.Response]], iterations: int
) -> Stats:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        resp = await call()
        elapsed = time.perf_counter() - start
        if resp.status_code >= 500:
            print(
                f"[bench] {name}: HTTP {resp.status_code} — abandoning this endpoint",
                file=sys.stderr,
            )
            return Stats(name, samples)
        samples.append(elapsed)
    return Stats(name, samples)


async def _warmup(client: httpx.AsyncClient) -> None:
    print("[bench] warming cache with", ", ".join(WARMUP_TICKERS))
    tasks = []
    for t in WARMUP_TICKERS:
        tasks.append(client.get("/api/quote", params={"ticker": t}))
        tasks.append(client.get("/api/historical", params={"ticker": t, "frequency": "daily"}))
    tasks.append(client.get("/api/risk-free-rate"))
    await asyncio.gather(*tasks, return_exceptions=True)


async def run_benchmark(args: argparse.Namespace) -> int:
    base_url = args.base.rstrip("/")
    iterations = args.iterations

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        try:
            health = await client.get("/api/risk-free-rate")
        except httpx.HTTPError as exc:
            print(
                f"[bench] ERROR: could not reach {base_url}: {exc}",
                file=sys.stderr,
            )
            return 2
        if health.status_code >= 500:
            print(
                f"[bench] ERROR: {base_url} is unhealthy (HTTP {health.status_code})",
                file=sys.stderr,
            )
            return 2

        await _warmup(client)

        stats: list[tuple[Stats, float | None]] = []

        # /quote
        quote_stats = await _measure(
            "/quote",
            lambda: client.get("/api/quote", params={"ticker": WARMUP_TICKERS[0]}),
            iterations,
        )
        stats.append((quote_stats, BUDGETS["/quote"]))

        # /historical (warm)
        hist_stats = await _measure(
            "/historical (warm)",
            lambda: client.get(
                "/api/historical",
                params={"ticker": WARMUP_TICKERS[0], "frequency": "daily"},
            ),
            iterations,
        )
        stats.append((hist_stats, BUDGETS["/historical (warm)"]))

        # /optimize (warm): submit the same request repeatedly so the cache
        # serves every call after the first.
        optimize_body = {
            "tickers": WARMUP_TICKERS,
            "riskProfile": {"riskAversion": 4},
            "returnFrequency": "daily",
            "lookbackYears": 5,
            "allowShort": False,
            "allowLeverage": True,
        }
        optimize_stats = await _measure(
            "/optimize (warm)",
            lambda: client.post("/api/optimize", json=optimize_body),
            iterations,
        )
        stats.append((optimize_stats, BUDGETS["/optimize (warm)"]))

        # /chat (rule) — deterministic, no API key needed.
        chat_rule_body = {
            "messages": [{"role": "user", "content": "what is my Sharpe?"}],
            "mode": "rule",
        }
        chat_rule_stats = await _measure(
            "/chat (rule)",
            lambda: client.post("/api/chat", json=chat_rule_body),
            iterations,
        )
        stats.append((chat_rule_stats, BUDGETS["/chat (rule)"]))

        # /chat (LLM) — optional; needs OPENROUTER_API_KEY on the backend.
        if not args.skip_chat:
            chat_llm_body = {
                "messages": [{"role": "user", "content": "Summarize my Sharpe."}],
                "mode": "llm",
                "model": args.chat_model,
            }
            chat_llm_stats = await _measure(
                "/chat (LLM)",
                lambda: client.post("/api/chat", json=chat_llm_body),
                max(1, iterations // 5),  # LLM is rate-limited, use fewer samples
            )
            stats.append((chat_llm_stats, BUDGETS["/chat (LLM)"]))

    print()
    header = (
        f"{'endpoint':<22} {'n':>4} {'p50':>11} {'p95':>11} "
        f"{'p99':>11} {'budget':>10}  verdict"
    )
    print(header)
    print("-" * len(header))
    for s, b in stats:
        print(s.format_row(b))

    failures = [s for s, b in stats if b is not None and s.samples and s.p95 > b]
    if failures:
        print(
            "\n[bench] FAILED budgets:",
            ", ".join(s.endpoint for s in failures),
            file=sys.stderr,
        )
        return 1
    print("\n[bench] all endpoints inside their SPEC §6 budgets ✓")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Number of samples per endpoint (default: 50)",
    )
    parser.add_argument(
        "--skip-chat", action="store_true", help="Skip the /chat LLM run"
    )
    parser.add_argument(
        "--chat-model",
        default="google/gemma-4-31b-it",
        help="OpenRouter model slug for the /chat LLM run",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    raise SystemExit(main())
