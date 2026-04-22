"""Agent E — intent classifier unit tests."""

from __future__ import annotations

import pytest

from app.services.chat.intent import Intent, IntentMatch, classify_intent


@pytest.mark.parametrize(
    ("message", "expected_intent", "expected_ticker"),
    [
        ("Why is NVDA overweight in my portfolio?", Intent.WHY_OVERWEIGHT, "NVDA"),
        ("why is the largest weight what it is", Intent.WHY_OVERWEIGHT, None),
        ("explain why AAPL is the top weight", Intent.WHY_OVERWEIGHT, "AAPL"),
    ],
)
def test_why_overweight(message, expected_intent, expected_ticker):
    match = classify_intent(message, known_tickers=["AAPL", "MSFT", "NVDA"])
    assert match is not None
    assert match.intent is expected_intent
    assert match.ticker == expected_ticker


@pytest.mark.parametrize(
    ("message", "expected_target"),
    [
        ("raise my target return to 30%", 0.30),
        ("set target return to 0.25", 0.25),
        ("can we lower the target return to 18%", 0.18),
        ("raise the target return", None),
    ],
)
def test_target_return(message, expected_target):
    match = classify_intent(message)
    assert match is not None
    assert match.intent is Intent.TARGET_RETURN_LEVERAGE
    if expected_target is None:
        assert match.target_return is None
    else:
        assert match.target_return == pytest.approx(expected_target)


@pytest.mark.parametrize(
    "message",
    [
        "what's my Sharpe?",
        "give me an ORP summary",
        "how is my portfolio looking",
        "show me current portfolio weights",
    ],
)
def test_portfolio_summary(message):
    match = classify_intent(message)
    assert match is not None
    assert match.intent is Intent.PORTFOLIO_SUMMARY


def test_define_term_steps_aside_when_ticker_present():
    match = classify_intent(
        "what is the beta of NVDA", known_tickers=["AAPL", "NVDA"]
    )
    assert match is not None
    # Define-term must defer to RISK_METRIC_LOOKUP when a known ticker is in
    # the sentence — the user wants the actual number, not a definition.
    assert match.intent is Intent.RISK_METRIC_LOOKUP
    assert match.ticker == "NVDA"


def test_risk_metric_without_define_verb():
    match = classify_intent(
        "NVDA beta and alpha please", known_tickers=["AAPL", "NVDA"]
    )
    assert match is not None
    assert match.intent is Intent.RISK_METRIC_LOOKUP
    assert match.ticker == "NVDA"


def test_risk_metric_no_ticker():
    match = classify_intent("show volatility breakdown")
    assert match is not None
    assert match.intent is Intent.RISK_METRIC_LOOKUP
    assert match.ticker is None


@pytest.mark.parametrize(
    ("message", "expected_term"),
    [
        ("what is alpha?", "alpha"),
        ("define the Sharpe ratio", "sharpe ratio"),
        ("what's the efficient frontier", "efficient frontier"),
        ("explain leverage", "leverage"),
        ("meaning of firm-specific variance", "firm-specific variance"),
    ],
)
def test_define_term(message, expected_term):
    match = classify_intent(message)
    assert match is not None
    assert match.intent is Intent.DEFINE_TERM
    assert match.term == expected_term


@pytest.mark.parametrize(
    "message",
    [
        "",
        "   ",
        "hello there",
        "tell me a joke",
        "the weather is nice today",
    ],
)
def test_negative_controls(message):
    assert classify_intent(message) is None


def test_define_term_unknown_falls_through_to_summary():
    match = classify_intent("what is my Sharpe?")
    assert match is not None
    # "what is" without a glossary term should fall through to PORTFOLIO_SUMMARY
    # via the "sharpe" keyword.
    assert match.intent is Intent.PORTFOLIO_SUMMARY


def test_ticker_stopword_ignored():
    match = classify_intent(
        "why is AAPL overweight in my portfolio", known_tickers=["AAPL", "MSFT"]
    )
    assert match is not None
    assert match.intent is Intent.WHY_OVERWEIGHT
    # "IS"/"MY" are stopwords; AAPL must win over them.
    assert match.ticker == "AAPL"


def test_intentmatch_is_frozen():
    im = IntentMatch(Intent.PORTFOLIO_SUMMARY)
    with pytest.raises(Exception):
        im.ticker = "AAPL"  # type: ignore[misc]
