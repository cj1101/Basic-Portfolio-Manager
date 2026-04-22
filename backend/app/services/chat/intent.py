"""Rule-based intent classifier for the Portfolio Manager chatbot.

The classifier is deliberately small and deterministic — no ML, no LLM. It
recognises the Core 5 intents from ``docs/SPEC.md`` §3 decision 5 and extracts
a single optional ticker argument when present. Anything that does not match
returns ``None`` so the orchestrator can decide whether to fall back to the
LLM (``ChatMode.AUTO``) or emit a polite miss message (``ChatMode.RULE``).

Keeping the classifier purely regex-based guarantees the ``< 200 ms`` rule
latency target from ``docs/SPEC.md`` §6 and makes the behaviour unit-testable
without mocking out upstream services.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

# Glossary terms the DEFINE_TERM intent understands. Aligned with SPEC §8 plus
# a handful of common English synonyms the user is likely to type.
GLOSSARY_TERMS: tuple[str, ...] = (
    "alpha",
    "beta",
    "sharpe",
    "sharpe ratio",
    "orp",
    "cal",
    "capital allocation line",
    "mvp",
    "minimum variance portfolio",
    "efficient frontier",
    "risk-free rate",
    "risk free rate",
    "risk aversion",
    "standard deviation",
    "std dev",
    "variance",
    "covariance",
    "correlation",
    "expected return",
    "firm-specific variance",
    "firm specific variance",
    "leverage",
    "y star",
)


class Intent(str, Enum):
    """Core 5 intents per the plan + a DEFINE_TERM catch-all."""

    WHY_OVERWEIGHT = "why_overweight"
    TARGET_RETURN_LEVERAGE = "target_return_leverage"
    PORTFOLIO_SUMMARY = "portfolio_summary"
    RISK_METRIC_LOOKUP = "risk_metric_lookup"
    DEFINE_TERM = "define_term"


@dataclass(slots=True, frozen=True)
class IntentMatch:
    intent: Intent
    ticker: str | None = None
    term: str | None = None
    target_return: float | None = None


_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\b")

_WHY_OVERWEIGHT_RE = re.compile(
    r"\b(why|reason|explain|what.*makes)\b.*\b(overweight|over-?weight|big|biggest|large|largest|highest|top|dominates?|concentrat)",
    re.IGNORECASE,
)

_TARGET_RETURN_RE = re.compile(
    r"\b(target|raise|lower|increase|decrease|set).{0,20}(return|target)\b",
    re.IGNORECASE,
)
_TARGET_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?")

_PORTFOLIO_SUMMARY_RE = re.compile(
    r"\b(sharpe(?!\s+ratio\s+(is|of|means|definition))|orp|overall|summary|summarize|my\s+(portfolio|allocation)|how.*(doing|looking)|current\s+(portfolio|weights))\b",
    re.IGNORECASE,
)

_RISK_METRIC_RE = re.compile(
    r"\b(beta|alpha|sigma|std\s*\.?\s*dev|standard\s+deviation|variance|volatil[a-z]*|firm[-\s]?specific)\b",
    re.IGNORECASE,
)

_DEFINE_RE = re.compile(
    r"\b(what(?:\s+is|'s|\s+does)|define|meaning\s+of|explain(?:\s+the)?)\b",
    re.IGNORECASE,
)

# Words we never want to treat as a ticker. Includes short English words that
# happen to be valid ticker-shaped tokens ("A", "IS", "DO", …).
_TICKER_STOPWORDS: frozenset[str] = frozenset(
    {
        "A",
        "AN",
        "AND",
        "AT",
        "BE",
        "DO",
        "FOR",
        "HAS",
        "I",
        "IF",
        "IN",
        "IS",
        "IT",
        "MY",
        "OF",
        "ON",
        "OR",
        "SO",
        "TO",
        "UP",
        "WE",
        "WHY",
        "THE",
        "WHAT",
        "HOW",
        "WHEN",
        "WHERE",
        "WHO",
        "ALPHA",
        "BETA",
        "SIGMA",
        "SHARPE",
        "ORP",
        "CAL",
        "MVP",
        "SPY",
    }
)


def classify_intent(message: str, *, known_tickers: list[str] | None = None) -> IntentMatch | None:
    """Return an ``IntentMatch`` for ``message`` or ``None`` on miss.

    ``known_tickers`` (when supplied) is used to disambiguate ticker extraction:
    if a token in the message matches a known portfolio ticker we prefer that
    one. Otherwise we fall back to the first all-caps token that is neither a
    stopword nor a generic SPEC symbol like ``ORP``.
    """

    if not message or not message.strip():
        return None

    normalized = message.strip()
    known = {t.upper() for t in (known_tickers or [])}

    # DEFINE_TERM wins first so "what is beta" is not swallowed by the generic
    # RISK_METRIC intent. It only matches when the message actually names a
    # glossary term AND the user isn't asking about their own portfolio (a
    # possessive "my" flips the interpretation toward RISK_METRIC /
    # PORTFOLIO_SUMMARY) AND there is no ticker mention (which signals a
    # per-ticker lookup, not a definition request).
    is_possessive = re.search(r"\bmy\b", normalized, re.IGNORECASE) is not None
    has_ticker = any(token in known for token in _TICKER_RE.findall(normalized))
    if _DEFINE_RE.search(normalized) and not is_possessive and not has_ticker:
        term = _extract_glossary_term(normalized)
        if term is not None:
            return IntentMatch(Intent.DEFINE_TERM, term=term)

    if _WHY_OVERWEIGHT_RE.search(normalized):
        ticker = _extract_ticker(normalized, known)
        return IntentMatch(Intent.WHY_OVERWEIGHT, ticker=ticker)

    if _TARGET_RETURN_RE.search(normalized):
        target = _extract_target_return(normalized)
        return IntentMatch(Intent.TARGET_RETURN_LEVERAGE, target_return=target)

    if _RISK_METRIC_RE.search(normalized):
        ticker = _extract_ticker(normalized, known)
        return IntentMatch(Intent.RISK_METRIC_LOOKUP, ticker=ticker)

    if _PORTFOLIO_SUMMARY_RE.search(normalized):
        return IntentMatch(Intent.PORTFOLIO_SUMMARY)

    return None


def _extract_ticker(message: str, known: set[str]) -> str | None:
    candidates = _TICKER_RE.findall(message)
    if not candidates:
        return None
    # Prefer a token that matches a known portfolio ticker.
    for cand in candidates:
        if cand in known:
            return cand
    # Else pick the first non-stopword candidate.
    for cand in candidates:
        if cand in _TICKER_STOPWORDS:
            continue
        # Single-letter ticker candidates without a portfolio match are almost
        # always a pronoun or article — skip them.
        if len(cand) == 1:
            continue
        return cand
    return None


def _extract_glossary_term(message: str) -> str | None:
    lowered = message.lower()
    # Longest-match first so "sharpe ratio" beats "sharpe".
    for term in sorted(GLOSSARY_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            return term
    return None


def _extract_target_return(message: str) -> float | None:
    for match in _TARGET_PCT_RE.finditer(message):
        raw = match.group(1)
        try:
            value = float(raw)
        except ValueError:
            continue
        # Treat bare numbers > 1 as percentages (e.g. "30" -> 0.30),
        # decimals ≤ 1 as already-annualised (e.g. "0.30").
        if value > 1.0:
            value /= 100.0
        if 0.0 < value < 2.0:
            return value
    return None


__all__ = ["GLOSSARY_TERMS", "Intent", "IntentMatch", "classify_intent"]
