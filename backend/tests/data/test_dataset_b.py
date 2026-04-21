"""Dataset B — live-gated real-world snapshot lock.

On first successful run (``RUN_LIVE_TESTS=1`` with ``ALPHA_VANTAGE_API_KEY``
set) this test:

1. Fetches 5 years of daily bars for ``AAPL, MSFT, NVDA, JPM, XOM, SPY`` ending
   on the last NYSE session on-or-before 2024-11-21 **via Alpha Vantage**.
2. Normalizes to canonical JSON (sorted keys, LF, no trailing newline).
3. Writes ``backend/data/snapshots/dataset_b.json``.
4. Computes SHA-256 and — if ``docs/FIXTURES.md`` §2 still contains the
   placeholder ``<to-be-set-by-agent-1A-in-its-first-PR>`` — patches it in
   place so the hash becomes the lock for every subsequent run.

On every subsequent run the test re-fetches, recomputes the SHA-256, and
asserts the new hash equals the locked hash byte-exactly. Any drift aborts
the build loudly — "a feature, not a bug" per FIXTURES §2.

Why AV-only: Alpha Vantage returns prices as text with fixed precision, so
a round-trip ``str → float → str`` is exact. Yahoo's ``yfinance`` pipeline
internally uses float32 and auto-adjust multipliers that jitter by ~1e-5
between fetches — enough to flip the hash at any rounding precision that
preserves real information. If ``ALPHA_VANTAGE_API_KEY`` is not set the
test skips with an informational message instead of producing a noisy
Yahoo-based lock.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date as Date
from pathlib import Path

import pytest

from app.data.calendar import last_trading_day_on_or_before
from app.data.cache import MarketCache
from app.data.clients.alpha_vantage import AlphaVantageClient
from app.data.clients.yahoo import YahooClient
from app.data.rate_limit import AlphaVantageRateLimiter
from app.data.service import DataService
from app.schemas import ReturnFrequency


pytestmark = [pytest.mark.asyncio, pytest.mark.live]

REPO_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_PATH = REPO_ROOT / "backend" / "data" / "snapshots" / "dataset_b.json"
FIXTURES_DOC_PATH = REPO_ROOT / "docs" / "FIXTURES.md"

HASH_PLACEHOLDER = "<to-be-set-by-agent-1A-in-its-first-PR>"
HASH_LINE_RE = re.compile(r'(\s*"hashPlaceholder"\s*:\s*")([^"]+)(")')

AS_OF_POLICY = Date(2024, 11, 21)
TICKERS = ("AAPL", "MSFT", "NVDA", "JPM", "XOM", "SPY")
LOOKBACK_YEARS = 5

# Alpha Vantage returns prices as fixed-precision strings (e.g. "192.5300"),
# so parsing them to float and serializing them back is exact. This is why
# the snapshot lock is AV-only — see module docstring.
PRICE_PRECISION = 4


def _canonical_json(obj: object) -> bytes:
    """sorted-key JSON, LF newlines, no trailing newline — SPEC §8 canonical."""

    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _service_from_env(cache: MarketCache) -> DataService:
    import os

    av_key = os.getenv("ALPHA_VANTAGE_API_KEY") or ""
    if not av_key or av_key == "test-key":
        pytest.skip(
            "Dataset B snapshot lock requires ALPHA_VANTAGE_API_KEY. "
            "Yahoo's auto-adjust float32 pipeline jitters by ~1e-5 between "
            "fetches so it can't produce a byte-exact hash; AV's fixed-"
            "precision text prices can. Export a real AV key and rerun."
        )
    limiter = AlphaVantageRateLimiter(cache, per_minute=5, per_day=500)
    av = AlphaVantageClient(api_key=av_key, rate_limiter=limiter)
    return DataService(
        cache=cache,
        alpha_vantage=av,
        yahoo=YahooClient(),
        fred=None,
        use_mock_fallback=False,
        quote_ttl_seconds=300,
        risk_free_rate_ttl_seconds=86400,
    )


async def _fetch_snapshot(cache: MarketCache) -> dict:
    service = _service_from_env(cache)
    window_end = last_trading_day_on_or_before(AS_OF_POLICY)

    rows: dict[str, dict] = {}
    providers: set[str] = set()

    for ticker in TICKERS:
        result = await service.get_historical(
            ticker,
            frequency=ReturnFrequency.DAILY,
            lookback_years=LOOKBACK_YEARS,
            as_of=AS_OF_POLICY,
        )
        providers.add(result.source)
        bars = [
            {
                "date": bar.date.isoformat(),
                "open": round(float(bar.open), PRICE_PRECISION),
                "high": round(float(bar.high), PRICE_PRECISION),
                "low": round(float(bar.low), PRICE_PRECISION),
                "close": round(float(bar.close), PRICE_PRECISION),
                "volume": int(bar.volume),
            }
            for bar in result.bars
            if bar.date <= window_end
        ]
        assert len(bars) >= 1100, f"Dataset B: {ticker} returned only {len(bars)} bars"
        rows[ticker] = {"bars": bars, "count": len(bars)}

    assert len(providers) == 1, (
        f"Dataset B snapshot mixed providers {providers}; "
        "re-run once primary provider is reachable so the lock is provider-stable."
    )
    return {
        "datasetId": "B",
        "asOfPolicy": "last-trading-day-on-or-before(2024-11-21)",
        "windowEnd": window_end.isoformat(),
        "lookbackYears": LOOKBACK_YEARS,
        "tickers": list(TICKERS),
        "provider": next(iter(providers)),
        "series": rows,
    }


def _patch_fixtures_md(new_hash: str) -> bool:
    """Return True if FIXTURES.md was modified."""

    if not FIXTURES_DOC_PATH.exists():
        return False
    text = FIXTURES_DOC_PATH.read_text(encoding="utf-8")
    if HASH_PLACEHOLDER not in text and new_hash in text:
        return False  # already locked to this hash

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{new_hash}{match.group(3)}"

    new_text, count = HASH_LINE_RE.subn(_replace, text, count=1)
    if count == 0:
        return False
    if new_text == text:
        return False
    FIXTURES_DOC_PATH.write_text(new_text, encoding="utf-8", newline="\n")
    return True


async def test_dataset_b_snapshot_lock(cache: MarketCache, isolated_settings) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = await _fetch_snapshot(cache)
    blob = _canonical_json(payload)
    new_hash = hashlib.sha256(blob).hexdigest()

    first_run = not SNAPSHOT_PATH.exists()
    if first_run:
        SNAPSHOT_PATH.write_bytes(blob)
        modified = _patch_fixtures_md(new_hash)
        assert modified, (
            "Wrote backend/data/snapshots/dataset_b.json but failed to patch "
            "docs/FIXTURES.md hashPlaceholder — update it manually."
        )
        return

    existing = SNAPSHOT_PATH.read_bytes()
    existing_hash = hashlib.sha256(existing).hexdigest()

    if existing == blob:
        return

    # Snapshot drifted — but maybe the locked hash is still the placeholder
    # because the existing file was produced before the FIXTURES patch step.
    fixtures_text = (
        FIXTURES_DOC_PATH.read_text(encoding="utf-8")
        if FIXTURES_DOC_PATH.exists()
        else ""
    )
    if HASH_PLACEHOLDER in fixtures_text:
        SNAPSHOT_PATH.write_bytes(blob)
        _patch_fixtures_md(new_hash)
        pytest.fail(
            "Dataset B snapshot existed but FIXTURES hash was still unlocked. "
            f"Rewrote snapshot and locked hash to {new_hash}. "
            "Re-run the test to confirm stability."
        )

    raise AssertionError(
        "Dataset B snapshot drift detected.\n"
        f"  existing hash: {existing_hash}\n"
        f"  new hash:      {new_hash}\n"
        "Either a provider corrected historical data or the fetch code "
        "changed shape. Review the diff before updating the locked hash."
    )
