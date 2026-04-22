"""Templated rule answers for the chat assistant.

Each function here is pure: given the matched :class:`~app.services.chat.intent.IntentMatch`
and a live ``OptimizationResult`` (may be ``None``), it returns a tuple of
``(answer, citations)``. Citations expose the underlying scalars so the UI
can render them as chips next to the bubble.

Every number is formatted client-side like the rest of the dashboard —
decimals as percentages rounded to 2 dp for display, raw values to 4 dp for
citations so they remain auditable against the SPEC §6 rounding rule.
"""

from __future__ import annotations

from app.schemas import ChatCitation, ChatMessage, OptimizationResult, StockMetrics
from app.services.chat.intent import Intent, IntentMatch

_GLOSSARY: dict[str, str] = {
    "alpha": (
        "Alpha (\u03b1) is the portion of an asset's excess return not explained by "
        "its exposure to the market. Here it is measured as the historical "
        "regression residual over the return window: "
        "\u03b1 = mean(excess_i) \u2212 \u03b2 \u00b7 mean(excess_market). Positive alpha "
        "means the asset beat the CAPM-predicted return."
    ),
    "beta": (
        "Beta (\u03b2) measures an asset's sensitivity to the market benchmark "
        "(SPY). \u03b2 > 1 means the asset moves more than the market, \u03b2 < 1 means "
        "less, and \u03b2 < 0 means it tends to move the opposite way."
    ),
    "sharpe": (
        "The Sharpe ratio is the portfolio's risk-adjusted return: "
        "SR = (E(r_p) \u2212 r_f) / \u03c3_p. Higher is better — the Optimal Risky "
        "Portfolio (ORP) is the long-only tangent portfolio that maximises it."
    ),
    "sharpe ratio": (
        "The Sharpe ratio is the portfolio's risk-adjusted return: "
        "SR = (E(r_p) \u2212 r_f) / \u03c3_p. Higher is better — the Optimal Risky "
        "Portfolio (ORP) is the long-only tangent portfolio that maximises it."
    ),
    "orp": (
        "ORP is the Optimal Risky Portfolio — the tangency portfolio on the "
        "efficient frontier that maximises the Sharpe ratio. It is the risky "
        "half of your complete-portfolio allocation."
    ),
    "cal": (
        "The Capital Allocation Line (CAL) is the straight line through the "
        "risk-free rate and the ORP in (\u03c3, E(r)) space. Every point on it is "
        "a convex combination of cash and the ORP."
    ),
    "capital allocation line": (
        "The Capital Allocation Line (CAL) is the straight line through the "
        "risk-free rate and the ORP in (\u03c3, E(r)) space. Every point on it is "
        "a convex combination of cash and the ORP."
    ),
    "mvp": (
        "The Minimum-Variance Portfolio (MVP) is the long-only portfolio with "
        "the smallest possible variance given the covariance matrix. It sits "
        "at the left tip of the efficient frontier."
    ),
    "minimum variance portfolio": (
        "The Minimum-Variance Portfolio (MVP) is the long-only portfolio with "
        "the smallest possible variance given the covariance matrix. It sits "
        "at the left tip of the efficient frontier."
    ),
    "efficient frontier": (
        "The efficient frontier is the set of risky portfolios with the "
        "highest expected return per unit of standard deviation. It is derived "
        "in closed form via the Merton formula over the covariance matrix."
    ),
    "risk-free rate": (
        "The risk-free rate (r_f) is the annualised yield on a 3-month "
        "T-bill (FRED series DGS3MO). It is the intercept of the Capital "
        "Allocation Line and sets the hurdle the ORP must clear."
    ),
    "risk free rate": (
        "The risk-free rate (r_f) is the annualised yield on a 3-month "
        "T-bill (FRED series DGS3MO). It is the intercept of the Capital "
        "Allocation Line and sets the hurdle the ORP must clear."
    ),
    "risk aversion": (
        "Risk aversion (A) is a 1\u201310 coefficient that scales how much the "
        "utility function penalises variance. Higher A \u2192 less wealth in the "
        "risky ORP. Your allocation solves y* = (E(r_ORP) \u2212 r_f) / (A \u00b7 \u03c3\u00b2_ORP)."
    ),
    "standard deviation": (
        "Standard deviation (\u03c3) is the annualised dispersion of returns "
        "around their mean. It is the primary measure of total risk used "
        "throughout the dashboard."
    ),
    "std dev": (
        "Standard deviation (\u03c3) is the annualised dispersion of returns "
        "around their mean. It is the primary measure of total risk used "
        "throughout the dashboard."
    ),
    "variance": (
        "Variance (\u03c3\u00b2) is the square of the standard deviation. It is "
        "additive across uncorrelated assets and is the basis for the "
        "Markowitz mean-variance optimisation."
    ),
    "covariance": (
        "Covariance Cov(i,j) measures how two assets move together in raw "
        "return units. The covariance matrix \u03a3 is what the optimizer inverts "
        "to produce the ORP weights."
    ),
    "correlation": (
        "Correlation \u03c1(i,j) = Cov(i,j) / (\u03c3_i \u00b7 \u03c3_j) is the unit-free "
        "version of covariance, bounded in [\u22121, 1]."
    ),
    "expected return": (
        "Expected return E(r) is the annualised mean return estimated from the "
        "historical return window (5 years of daily log returns by default, "
        "scaled by 252)."
    ),
    "firm-specific variance": (
        "Firm-specific (residual) variance \u03c3\u00b2(e_i) is the part of an asset's "
        "variance that the Single-Index Model cannot explain via its beta to "
        "the market. It is diversifiable risk."
    ),
    "firm specific variance": (
        "Firm-specific (residual) variance \u03c3\u00b2(e_i) is the part of an asset's "
        "variance that the Single-Index Model cannot explain via its beta to "
        "the market. It is diversifiable risk."
    ),
    "leverage": (
        "Leverage in this dashboard means y* > 1: borrowing at the risk-free "
        "rate to hold more than 100% of wealth in the ORP. It boosts expected "
        "return linearly and risk \u2014 so \u03c3 \u2014 linearly too."
    ),
    "y star": (
        "y* is the optimal share of wealth in the risky ORP: "
        "y* = (E(r_ORP) \u2212 r_f) / (A \u00b7 \u03c3\u00b2_ORP). 1 \u2212 y* goes into the "
        "risk-free asset. y* > 1 implies leverage."
    ),
}


def render_rule_answer(
    match: IntentMatch,
    ctx: OptimizationResult | None,
    messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    """Dispatch to the per-intent handler. Raises ``KeyError`` on unknown intents."""

    handlers = {
        Intent.WHY_OVERWEIGHT: _render_why_overweight,
        Intent.TARGET_RETURN_LEVERAGE: _render_target_return,
        Intent.PORTFOLIO_SUMMARY: _render_summary,
        Intent.RISK_METRIC_LOOKUP: _render_risk_metric,
        Intent.DEFINE_TERM: _render_define_term,
    }
    return handlers[match.intent](match, ctx, messages)


def rule_miss_answer(mode: str) -> tuple[str, list[ChatCitation]]:
    """Polite miss message when the rule classifier didn't match."""

    if mode == "rule":
        return (
            "I couldn't match that to one of my built-in portfolio questions. "
            'Try rephrasing (for example: "why is NVDA overweight?" or '
            '"what\'s my Sharpe?"), or switch the Chat mode to LLM for a '
            "free-form answer.",
            [],
        )
    return (
        "I couldn't classify that question and the LLM fallback is not "
        "configured. Set OPENROUTER_API_KEY on the backend or try one of the "
        "sample prompts.",
        [],
    )


def require_context_answer() -> tuple[str, list[ChatCitation]]:
    return (
        "I need a live portfolio result to answer that. Add some tickers and "
        "wait for the optimizer to finish, then ask again.",
        [],
    )


# ---------------------------------------------------------------------------
# Per-intent renderers
# ---------------------------------------------------------------------------


def _render_why_overweight(
    match: IntentMatch,
    ctx: OptimizationResult | None,
    _messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    if ctx is None:
        return require_context_answer()
    if not ctx.orp.weights:
        return (
            "Your portfolio doesn't have any weights yet. Add tickers and "
            "wait for the optimizer to run.",
            [],
        )
    if match.ticker and match.ticker in ctx.orp.weights:
        ticker = match.ticker
        weight = ctx.orp.weights[ticker]
    else:
        ticker, weight = max(ctx.orp.weights.items(), key=lambda kv: kv[1])
    stock = _find_stock(ctx, ticker)
    rank, total = _ranked_position(ctx.orp.weights, ticker)

    base = (
        f"{ticker} sits at ORP weight {_fmt_pct(weight)} "
        f"(rank {rank}/{total}). The tangency optimizer concentrates weight "
        f"in assets whose excess-return-to-residual-risk ratio is highest."
    )
    citations: list[ChatCitation] = [
        ChatCitation(label=f"ORP weight · {ticker}", value=_fmt_decimal(weight)),
    ]
    if stock is not None:
        base += (
            f" For {ticker} the historical alpha is {_fmt_signed_pct(stock.alpha)} "
            f"against a firm-specific variance of {_fmt_decimal(stock.firm_specific_var)}, "
            f"so its Sharpe contribution dominates once the optimizer solves \u03a3\u207b\u00b9 (\u03bc \u2212 r_f)."
        )
        citations.extend(
            [
                ChatCitation(label=f"alpha · {ticker}", value=_fmt_signed_decimal(stock.alpha)),
                ChatCitation(label=f"beta · {ticker}", value=_fmt_decimal(stock.beta)),
                ChatCitation(
                    label=f"firm-specific var · {ticker}",
                    value=_fmt_decimal(stock.firm_specific_var),
                ),
            ]
        )
    return base, citations


def _render_target_return(
    match: IntentMatch,
    ctx: OptimizationResult | None,
    _messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    if ctx is None:
        return require_context_answer()
    target = match.target_return
    rf = ctx.risk_free_rate
    er_orp = ctx.orp.expected_return
    if target is None:
        return (
            (
                f"Your current ORP expects {_fmt_pct(er_orp)} vs. a risk-free "
                f'rate of {_fmt_pct(rf)}. Tell me a target (e.g. "raise my '
                "target to 30%\") and I'll work out the implied leverage."
            ),
            [
                ChatCitation(label="ORP expected return", value=_fmt_decimal(er_orp)),
                ChatCitation(label="risk-free rate", value=_fmt_decimal(rf)),
            ],
        )
    slope = er_orp - rf
    if abs(slope) < 1e-9:
        return (
            "The ORP's excess return over the risk-free rate is essentially "
            "zero, so no target return is achievable by mixing cash and the "
            "ORP. Re-check your ticker list.",
            [
                ChatCitation(label="ORP expected return", value=_fmt_decimal(er_orp)),
                ChatCitation(label="risk-free rate", value=_fmt_decimal(rf)),
            ],
        )
    y = (target - rf) / slope
    leverage = y > 1.0 + 1e-9
    expected_sigma = abs(y) * ctx.orp.std_dev
    if leverage:
        body = (
            f"To target {_fmt_pct(target)} you'd need y = {y:.3f} \u2014 "
            f"i.e. borrow {_fmt_pct(y - 1)} at the risk-free rate to hold "
            f"{_fmt_pct(y)} of wealth in the ORP. Expected volatility scales "
            f"to \u2248 {_fmt_pct(expected_sigma)}."
        )
    elif y < 0:
        body = (
            f"{_fmt_pct(target)} sits below the risk-free rate ({_fmt_pct(rf)}), "
            f"so the formula yields y = {y:.3f} (a short in the ORP). v1 does "
            "not support negative y \u2014 pick a target above r_f."
        )
    else:
        body = (
            f"Targeting {_fmt_pct(target)} solves to y = {y:.3f}: put "
            f"{_fmt_pct(y)} in the ORP and {_fmt_pct(1 - y)} in the risk-free "
            f"asset. Expected volatility \u2248 {_fmt_pct(expected_sigma)}."
        )
    citations = [
        ChatCitation(label="target return", value=_fmt_decimal(target)),
        ChatCitation(label="implied y*", value=f"{y:.4f}"),
        ChatCitation(label="ORP expected return", value=_fmt_decimal(er_orp)),
        ChatCitation(label="risk-free rate", value=_fmt_decimal(rf)),
    ]
    return body, citations


def _render_summary(
    _match: IntentMatch,
    ctx: OptimizationResult | None,
    _messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    if ctx is None:
        return require_context_answer()
    orp = ctx.orp
    comp = ctx.complete
    leverage_note = " Leverage is active." if comp.leverage_used else ""
    top = sorted(orp.weights.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_str = ", ".join(f"{t} ({_fmt_pct(w)})" for t, w in top) if top else "—"
    body = (
        f"Your ORP expects {_fmt_pct(orp.expected_return)} at "
        f"\u03c3 = {_fmt_pct(orp.std_dev)} for a Sharpe of {orp.sharpe:.3f}. "
        f"With your current risk profile the complete portfolio allocates "
        f"y* = {comp.y_star:.3f} to the ORP and {_fmt_pct(comp.weight_risk_free)} "
        f"to the risk-free asset.{leverage_note} Top weights: {top_str}."
    )
    citations = [
        ChatCitation(label="ORP expected return", value=_fmt_decimal(orp.expected_return)),
        ChatCitation(label="ORP std dev", value=_fmt_decimal(orp.std_dev)),
        ChatCitation(label="ORP Sharpe", value=f"{orp.sharpe:.4f}"),
        ChatCitation(label="y*", value=f"{comp.y_star:.4f}"),
    ]
    return body, citations


def _render_risk_metric(
    match: IntentMatch,
    ctx: OptimizationResult | None,
    _messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    if ctx is None:
        return require_context_answer()
    if match.ticker is None:
        return (
            "Per-ticker risk metrics: "
            + "; ".join(
                f"{s.ticker} \u03c3 {_fmt_pct(s.std_dev)}, \u03b2 {s.beta:.2f}, "
                f"\u03b1 {_fmt_signed_pct(s.alpha)}"
                for s in ctx.stocks
            )
            + ".",
            [
                ChatCitation(label=f"\u03c3 · {s.ticker}", value=_fmt_decimal(s.std_dev))
                for s in ctx.stocks
            ],
        )
    stock = _find_stock(ctx, match.ticker)
    if stock is None:
        return (
            f"I don't see {match.ticker} in your portfolio. Add it to the ticker list first.",
            [],
        )
    body = (
        f"{stock.ticker}: E(r) {_fmt_pct(stock.expected_return)}, "
        f"\u03c3 {_fmt_pct(stock.std_dev)}, \u03b2 {stock.beta:.3f}, "
        f"\u03b1 {_fmt_signed_pct(stock.alpha)}, "
        f"firm-specific variance {_fmt_decimal(stock.firm_specific_var)} over "
        f"{stock.n_observations} observations."
    )
    citations = [
        ChatCitation(label=f"E(r) · {stock.ticker}", value=_fmt_decimal(stock.expected_return)),
        ChatCitation(label=f"\u03c3 · {stock.ticker}", value=_fmt_decimal(stock.std_dev)),
        ChatCitation(label=f"\u03b2 · {stock.ticker}", value=_fmt_decimal(stock.beta)),
        ChatCitation(label=f"\u03b1 · {stock.ticker}", value=_fmt_signed_decimal(stock.alpha)),
    ]
    return body, citations


def _render_define_term(
    match: IntentMatch,
    _ctx: OptimizationResult | None,
    _messages: list[ChatMessage],
) -> tuple[str, list[ChatCitation]]:
    term = (match.term or "").lower()
    definition = _GLOSSARY.get(term)
    if definition is None:
        return (
            "That term isn't in my glossary. Try: alpha, beta, Sharpe, ORP, "
            "CAL, MVP, efficient frontier, risk-free rate, or leverage.",
            [],
        )
    return definition, [ChatCitation(label="term", value=term)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_stock(ctx: OptimizationResult, ticker: str) -> StockMetrics | None:
    for stock in ctx.stocks:
        if stock.ticker == ticker:
            return stock
    return None


def _ranked_position(weights: dict[str, float], ticker: str) -> tuple[int, int]:
    ordered = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    for idx, (t, _w) in enumerate(ordered, start=1):
        if t == ticker:
            return idx, len(ordered)
    return len(ordered), len(ordered)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fmt_signed_pct(value: float) -> str:
    return f"{value * 100:+.2f}%"


def _fmt_decimal(value: float) -> str:
    return f"{value:.4f}"


def _fmt_signed_decimal(value: float) -> str:
    return f"{value:+.4f}"


__all__ = ["render_rule_answer", "require_context_answer", "rule_miss_answer"]
