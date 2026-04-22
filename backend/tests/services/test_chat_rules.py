"""Agent E — rule-engine unit tests (Core 5 intents)."""

from __future__ import annotations

import pytest

from app.schemas import ChatMessage, OptimizationResult
from app.services.chat.intent import Intent, IntentMatch
from app.services.chat.rules import (
    render_rule_answer,
    require_context_answer,
    rule_miss_answer,
)


def test_why_overweight_no_ticker_uses_top_weight(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.WHY_OVERWEIGHT)
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "NVDA" in answer  # largest ORP weight in the fixture
    assert "50.00%" in answer
    labels = [c.label for c in citations]
    assert any("ORP weight" in lbl for lbl in labels)
    assert any("alpha" in lbl for lbl in labels)


def test_why_overweight_specific_ticker(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.WHY_OVERWEIGHT, ticker="AAPL")
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "AAPL" in answer
    assert "28.00%" in answer  # AAPL has 0.28 weight
    assert any("AAPL" in c.label for c in citations)


def test_why_overweight_requires_context():
    answer, citations = render_rule_answer(
        IntentMatch(Intent.WHY_OVERWEIGHT), None, []
    )
    assert "need a live portfolio result" in answer
    assert citations == []


def test_target_return_with_leverage(
    sample_optimization_result: OptimizationResult,
):
    # ORP E(r)=0.29, rf=0.0523 → slope ≈ 0.2377. target 0.40 -> y ≈ 1.46 (leverage)
    match = IntentMatch(Intent.TARGET_RETURN_LEVERAGE, target_return=0.40)
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "borrow" in answer.lower()
    assert any(c.label == "implied y*" for c in citations)


def test_target_return_without_leverage(
    sample_optimization_result: OptimizationResult,
):
    # target 0.15 gives y ≈ 0.41 -> no leverage, some risk-free weight
    match = IntentMatch(Intent.TARGET_RETURN_LEVERAGE, target_return=0.15)
    answer, _ = render_rule_answer(match, sample_optimization_result, [])
    assert "risk-free" in answer.lower()
    assert "borrow" not in answer.lower()


def test_target_return_below_rf(sample_optimization_result: OptimizationResult):
    match = IntentMatch(Intent.TARGET_RETURN_LEVERAGE, target_return=0.02)
    answer, _ = render_rule_answer(match, sample_optimization_result, [])
    assert "below" in answer.lower() or "short" in answer.lower()


def test_target_return_without_target(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.TARGET_RETURN_LEVERAGE, target_return=None)
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "target" in answer.lower()
    assert any("ORP expected return" in c.label for c in citations)


def test_portfolio_summary_cites_core_metrics(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.PORTFOLIO_SUMMARY)
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    labels = {c.label for c in citations}
    assert "ORP Sharpe" in labels
    assert "y*" in labels
    assert "Sharpe" in answer or "sharpe" in answer.lower()
    assert "NVDA" in answer  # top weight should appear in top-3 summary


def test_risk_metric_all_tickers(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.RISK_METRIC_LOOKUP)
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "AAPL" in answer and "MSFT" in answer and "NVDA" in answer
    assert len(citations) == 3


def test_risk_metric_specific_ticker(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.RISK_METRIC_LOOKUP, ticker="MSFT")
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "MSFT" in answer
    # Should cite E(r), sigma, beta, alpha for MSFT.
    labels = [c.label for c in citations]
    assert any("E(r)" in lbl for lbl in labels)
    assert any("\u03b2" in lbl for lbl in labels)


def test_risk_metric_unknown_ticker(
    sample_optimization_result: OptimizationResult,
):
    match = IntentMatch(Intent.RISK_METRIC_LOOKUP, ticker="XYZ")
    answer, citations = render_rule_answer(match, sample_optimization_result, [])
    assert "don't see XYZ" in answer
    assert citations == []


@pytest.mark.parametrize(
    "term",
    ["alpha", "beta", "sharpe", "orp", "efficient frontier", "leverage"],
)
def test_define_term_covers_glossary(term):
    match = IntentMatch(Intent.DEFINE_TERM, term=term)
    answer, citations = render_rule_answer(match, None, [])
    assert len(answer) > 30
    assert any(c.label == "term" for c in citations)


def test_define_term_unknown():
    match = IntentMatch(Intent.DEFINE_TERM, term="wibble")
    answer, citations = render_rule_answer(match, None, [])
    assert "glossary" in answer.lower()
    assert citations == []


def test_rule_miss_answer_rule_mode():
    answer, citations = rule_miss_answer("rule")
    assert "LLM" in answer
    assert citations == []


def test_rule_miss_answer_auto_mode():
    answer, citations = rule_miss_answer("auto")
    assert "OPENROUTER_API_KEY" in answer
    assert citations == []


def test_require_context_answer():
    answer, citations = require_context_answer()
    assert "live portfolio" in answer
    assert citations == []


def test_messages_arg_is_accepted_and_ignored(
    sample_optimization_result: OptimizationResult,
):
    history = [ChatMessage(role="user", content="hi")]
    match = IntentMatch(Intent.PORTFOLIO_SUMMARY)
    answer, _ = render_rule_answer(match, sample_optimization_result, history)
    # Should render identically with or without history.
    answer_empty, _ = render_rule_answer(match, sample_optimization_result, [])
    assert answer == answer_empty


def test_why_overweight_no_weights(
    sample_optimization_result: OptimizationResult,
):
    empty = sample_optimization_result.model_copy(
        update={
            "orp": sample_optimization_result.orp.model_copy(update={"weights": {}}),
        }
    )
    match = IntentMatch(Intent.WHY_OVERWEIGHT)
    answer, _ = render_rule_answer(match, empty, [])
    assert "doesn't have any weights" in answer
