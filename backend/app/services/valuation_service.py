"""``POST /api/valuation`` — FCFF, FCFE, DDM from Yahoo (yfinance) or Alpha Vantage fundamentals."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from datetime import date as Date
from typing import Any

import numpy as np

from app.data.calendar import last_trading_day_on_or_before
from app.data.service import DataService
from app.errors import InvalidValuationError, ProviderUnavailableError
from app.schemas import (
    PriceBar,
    ReturnFrequency,
    TickerValuationBlock,
    ValuationExportDrivers,
    ValuationRequest,
    ValuationResult,
)
from quant.sim import single_index_metrics
from quant.valuation_cashflow import (
    equity_value_from_enterprise_value,
    fcfe_equity_value_perpetuity,
    fcfe_from_fcff,
    fcff_firm_value_perpetuity,
    fcff_nopat_depre_capex_deltanwc,
    per_share,
)
from quant.valuation_ddm import ddm_gordon, ddm_two_stage
from quant.valuation_eligibility import skip_ebit_based_fcff


def _num(d: dict, *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if v is None or v == "None" or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _interest_bearing_debt(b: dict) -> float | None:
    """Best-effort total debt from balance-sheet annual report keys."""
    td = _num(b, "totalDebt")
    if td is not None:
        return td
    st = _num(b, "shortTermDebt", "currentDebt")
    lt = _num(b, "longTermDebt", "longTermDebtNoncurrent")
    if st is None and lt is None:
        return None
    return (st or 0.0) + (lt or 0.0)


def _cash_and_equivalents(b: dict) -> float | None:
    return _num(
        b,
        "cashAndCashEquivalentsAtCarryingValue",
        "cashAndShortTermInvestments",
        "cashCashEquivalentsAndShortTermInvestments",
    )


def _book_net_debt(b: dict) -> float | None:
    debt = _interest_bearing_debt(b)
    if debt is None:
        return None
    cash = _cash_and_equivalents(b)
    return debt - (cash if cash is not None else 0.0)


def _dividend_yield_decimal(ov: dict) -> float | None:
    """Alpha Vantage ``DividendYield``: decimal (e.g. 0.004) or percent string (e.g. 0.4)."""
    raw = ov.get("DividendYield") or ov.get("dividendYield")
    if raw is None or raw == "" or raw == "None":
        return None
    try:
        y = float(raw)
    except (TypeError, ValueError):
        return None
    if y > 1.0:
        y /= 100.0
    return y


def _parse_fiscal_end(row: dict[str, Any]) -> Date | None:
    for key in ("fiscalDateEnding", "fiscal_year_end", "fiscalYearEnd"):
        raw = row.get(key)
        if raw is None or raw == "" or raw == "None":
            continue
        try:
            s = str(raw).strip()[:10]
            return Date.fromisoformat(s)
        except ValueError:
            continue
    return None


def select_annual_reports_as_of(
    ann_i: list[dict[str, Any]],
    ann_b: list[dict[str, Any]],
    ann_c: list[dict[str, Any]],
    window_end: Date | None,
    tw: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Latest fiscal year-end on or before ``window_end``; balance prior year for ΔNWC."""

    if window_end is None:
        i0 = ann_i[0]
        c0 = ann_c[0]
        b0 = ann_b[0]
        b1 = ann_b[1] if len(ann_b) > 1 else ann_b[0]
        return i0, c0, b0, b1

    def best_stmt(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
        dated = [(_parse_fiscal_end(r), r) for r in rows]
        if all(fd is None for fd, _ in dated):
            tw.append(
                f"No fiscal period dates on {label} statements; using newest-available row order."
            )
            return rows[0]

        qualified = [(fd, r) for fd, r in dated if fd is not None and fd <= window_end]
        if qualified:
            return max(qualified, key=lambda x: x[0])[1]

        tw.append(
            f"All {label} fiscal period ends are after {window_end.isoformat()}; "
            "using oldest available annual row."
        )
        return rows[-1]

    i0 = best_stmt(ann_i, "income")
    fd_i = _parse_fiscal_end(i0)

    def match_or_best(
        rows: list[dict[str, Any]], label: str, preferred_fd: Date | None
    ) -> dict[str, Any]:
        if preferred_fd is None:
            return best_stmt(rows, label)
        for r in rows:
            if _parse_fiscal_end(r) == preferred_fd:
                return r
        tw.append(
            f"No {label} row matching income fiscal period "
            f"{preferred_fd.isoformat()}; using latest fiscal period on or before window end."
        )
        return best_stmt(rows, label)

    c0 = match_or_best(ann_c, "cash flow", fd_i)
    b0 = match_or_best(ann_b, "balance sheet", fd_i)

    fd_b0 = _parse_fiscal_end(b0)
    prior_candidates: list[tuple[Date, dict[str, Any]]] = []
    if fd_b0 is not None:
        for r in ann_b:
            fd = _parse_fiscal_end(r)
            if fd is not None and fd < fd_b0:
                prior_candidates.append((fd, r))

    if prior_candidates:
        b1 = max(prior_candidates, key=lambda x: x[0])[1]
        return i0, c0, b0, b1

    idx_b0 = next((i for i, r in enumerate(ann_b) if r is b0), 0)
    if idx_b0 + 1 < len(ann_b):
        b1 = ann_b[idx_b0 + 1]
        tw.append(
            "Prior-year balance sheet for ΔNWC: adjacent annual row fallback (missing prior fiscal period)."
        )
        return i0, c0, b0, b1

    tw.append("Prior-year balance sheet unavailable for ΔNWC; using same annual balance row twice.")
    b1 = b0
    return i0, c0, b0, b1


def _last_monthly_close_on_or_before(bars: list[PriceBar], window_end: Date) -> float | None:
    eligible = [b for b in bars if b.date <= window_end]
    if not eligible:
        return None
    last_bar = max(eligible, key=lambda b: b.date.isoformat())
    return float(last_bar.close)


def _bounded_growth_for_perpetuity(
    growth: float | None,
    discount_rate: float | None,
    *,
    min_spread: float = 0.0025,
) -> tuple[float | None, bool]:
    """Ensure inferred perpetual growth stays below the discount rate.

    Returns ``(adjusted_growth, was_adjusted)``.
    """
    if growth is None:
        return None, False
    g = float(growth)
    if not np.isfinite(g):
        return None, True
    if discount_rate is None or not np.isfinite(discount_rate):
        return g, False
    k = float(discount_rate)
    cap = k - float(min_spread)
    if g >= cap:
        return cap, True
    return g, False


class ValuationService:
    async def run(
        self,
        request: ValuationRequest,
        *,
        data_service: DataService,
        risk_free_rate: float,
    ) -> tuple[ValuationResult, str]:
        rows: list[TickerValuationBlock] = []
        export_drivers: list[ValuationExportDrivers] = []
        sw: list[str] = []
        sources_seen: set[str] = set()
        anchor: Date | None = request.as_of
        window_end: Date | None = (
            last_trading_day_on_or_before(anchor) if anchor is not None else None
        )
        valuation_ts = (
            datetime.combine(window_end, datetime.min.time(), tzinfo=UTC)
            if window_end is not None
            else datetime.now(UTC)
        )

        try:
            spy_hist = await data_service.get_historical(
                "SPY",
                frequency=ReturnFrequency.MONTHLY,
                lookback_years=10,
                as_of=anchor,
            )
            spy_bars = sorted(spy_hist.bars, key=lambda b: b.date.isoformat())
        except Exception as e:
            sw.append(f"Failed to fetch SPY benchmark for beta: {e}")
            spy_bars = []

        dynamic_mrp: float | None = None
        try:
            if len(spy_bars) >= 2:
                spy_returns: list[float] = []
                prev_close = None
                for bar in spy_bars:
                    if prev_close is not None and prev_close > 0:
                        spy_returns.append((bar.close - prev_close) / prev_close)
                    prev_close = bar.close

                if spy_returns:
                    arr_spy = np.array(spy_returns)
                    spy_annualized_return = np.prod(1 + arr_spy) ** (12.0 / len(arr_spy)) - 1.0
                    candidate_mrp = float(spy_annualized_return) - float(risk_free_rate)

                    # Guardrail: keep a plausible long-run equity premium range.
                    if 0.0 <= candidate_mrp <= 0.2:
                        dynamic_mrp = candidate_mrp
                    else:
                        sw.append(
                            f"SPY-derived MRP {candidate_mrp:.4f} out of bounds; market risk premium unavailable."
                        )
                else:
                    sw.append("SPY historical returns unavailable for MRP.")
            else:
                sw.append("Insufficient SPY history for MRP.")
        except Exception as e:
            sw.append(f"Failed to compute SPY-derived MRP: {e}")

        for raw in request.tickers:
            t = str(raw).upper().strip()
            tw: list[str] = []
            try:
                inc, bal, cf, ov, prov = await data_service.get_fundamentals_bundle_for_valuation(t)
            except ProviderUnavailableError:
                raise
            sources_seen.add(prov)

            ann_i = list(inc.get("annualReports") or [])
            ann_b = list(bal.get("annualReports") or [])
            ann_c = list(cf.get("annualReports") or [])
            if not ann_i or not ann_b or not ann_c:
                tw.append("Missing annual reports in fundamentals response")
                export_drivers.append(
                    ValuationExportDrivers(
                        ticker=t,
                        financial_unsafe=True,
                        risk_free_annual=float(risk_free_rate),
                        market_risk_premium=float(dynamic_mrp) if dynamic_mrp is not None else None,
                    )
                )
                rows.append(
                    TickerValuationBlock(
                        ticker=t,
                        fcff=None,
                        fcfe=None,
                        fcff_value_per_share=None,
                        fcfe_value_per_share=None,
                        ddm_gordon=None,
                        ddm_two_stage=None,
                        cost_of_equity=request.cost_of_equity_override,
                        wacc=request.wacc,
                        warnings=tw,
                    )
                )
                continue

            i0, c0, b0, b1 = select_annual_reports_as_of(ann_i, ann_b, ann_c, window_end, tw)

            financial_unsafe = skip_ebit_based_fcff(t, ov, i0, b0)
            if financial_unsafe:
                tw.append(
                    "FCFF/FCFE from EBIT and working capital omitted: not reliable for this "
                    "sector (bank / financials); use DDM or a bank-specific framework."
                )

            ebit = _num(i0, "ebit", "ebitb")
            tax_e = _num(i0, "incomeTaxExpense", "incomeTax")
            ebt = _num(i0, "incomeBeforeTax", "incomeBeforeTax")
            t_rate: float | None = None
            if ebt is not None and ebt > 0 and tax_e is not None:
                t_rate = min(max(tax_e / ebt, 0.0), 0.5)
            elif not financial_unsafe and ebit is not None:
                tw.append("Effective tax rate unavailable; EBIT-based valuation skipped.")
            depr = _num(c0, "depreciationDepletionAndAmortization", "depreciationAndAmortization")
            cap_raw = _num(c0, "capitalExpenditures", "capitalExpenditure")
            capex = abs(float(cap_raw)) if cap_raw is not None else None
            ca0 = _num(b0, "totalCurrentAssets", "currentAssets")
            cl0 = _num(b0, "totalCurrentLiabilities", "currentLiabilities")
            ca1 = _num(b1, "totalCurrentAssets", "currentAssets")
            cl1 = _num(b1, "totalCurrentLiabilities", "currentLiabilities")
            delta_nwc: float | None = None
            if ca0 is not None and cl0 is not None and ca1 is not None and cl1 is not None:
                nwc0 = float(ca0) - float(cl0)
                nwc1 = float(ca1) - float(cl1)
                delta_nwc = nwc0 - nwc1
            elif not financial_unsafe and ebit is not None:
                tw.append("Working capital inputs incomplete; EBIT-based valuation skipped.")
            _ie = _num(
                i0,
                "interestAndDebtExpense",
                "interestExpense",
                "totalInterestExpense",
            )
            int_exp = abs(float(_ie)) if _ie is not None else None
            debt0 = _interest_bearing_debt(b0)
            debt1 = _interest_bearing_debt(b1)
            net_borrowing: float | None = None
            if debt0 is not None and debt1 is not None:
                net_borrowing = debt0 - debt1
            elif not financial_unsafe and ebit is not None:
                tw.append("Total debt incomplete; FCFE valuation skipped.")

            if financial_unsafe:
                fcff = None
                fcfe = None
            elif ebit is None:
                tw.append("EBIT missing; cannot compute FCFF")
                fcff = None
                fcfe = None
            elif None in (t_rate, depr, capex, delta_nwc):
                fcff = None
                fcfe = None
            else:
                assert t_rate is not None
                assert depr is not None
                assert capex is not None
                assert delta_nwc is not None
                fcff = fcff_nopat_depre_capex_deltanwc(ebit, t_rate, depr, capex, delta_nwc)
                if int_exp is None or net_borrowing is None:
                    fcfe = None
                else:
                    fcfe = fcfe_from_fcff(fcff, int_exp, t_rate, net_borrowing)

            historical_prices = None
            historical_return = None
            historical_volatility = None
            calculated_beta = None

            try:
                hist = await data_service.get_historical(
                    t,
                    frequency=ReturnFrequency.MONTHLY,
                    lookback_years=10,
                    as_of=anchor,
                )
                historical_prices = sorted(hist.bars, key=lambda b: b.date.isoformat())
                if historical_prices and spy_bars:
                    spy_dict = {b.date.isoformat(): b.close for b in spy_bars}
                    aligned_i = []
                    aligned_m = []
                    prev_i = None
                    prev_m = None
                    for b in historical_prices:
                        dstr = b.date.isoformat()
                        if dstr in spy_dict:
                            if prev_i is not None and prev_m is not None:
                                aligned_i.append((b.close - prev_i) / prev_i)
                                aligned_m.append((spy_dict[dstr] - prev_m) / prev_m)
                            prev_i = b.close
                            prev_m = spy_dict[dstr]
                        else:
                            prev_i = None
                            prev_m = None

                    if len(aligned_i) >= 2:
                        try:
                            sim = single_index_metrics(
                                aligned_i,
                                aligned_m,
                                risk_free_per_period=risk_free_rate / 12.0,
                            )
                            calculated_beta = float(sim.beta)
                        except Exception as e:
                            tw.append(f"Beta regression failed: {e}")

                        arr_i = np.array(aligned_i)
                        geom_mean = np.prod(1 + arr_i) ** (12.0 / len(arr_i)) - 1.0
                        historical_return = float(geom_mean)
                        historical_volatility = float(np.std(arr_i, ddof=1) * np.sqrt(12.0))
            except Exception as e:
                tw.append(f"Failed to fetch 10y historical prices: {e}")

            ov_inputs: dict[str, Any] = dict(ov)
            if anchor is not None and window_end is not None:
                ov_inputs.pop("Beta", None)
                tw.append(
                    "Historical as-of mode: fiscal statements use annual periods ending on or before "
                    "the NYSE window end; Yahoo overview fields default to live snapshot unless overridden."
                )
                if historical_prices:
                    px_hist = _last_monthly_close_on_or_before(historical_prices, window_end)
                    if px_hist is not None:
                        ov_inputs["currentPrice"] = str(px_hist)
                        ov_inputs["previousClose"] = str(px_hist)
                        sh_mc = _num(ov, "SharesOutstanding", "sharesOutstanding")
                        if sh_mc is not None and sh_mc > 0:
                            mc = px_hist * sh_mc
                            ov_inputs["marketCap"] = str(mc)
                            ov_inputs["MarketCapitalization"] = str(mc)
                            tw.append(
                                "Historical mode: market cap proxied as last monthly close "
                                "(≤ window end) × shares outstanding from overview."
                            )

            # Use calculated beta if available, fallback to Yahoo overview beta (stripped when anchored)
            beta = calculated_beta if calculated_beta is not None else _num(ov_inputs, "Beta")
            if anchor is not None and calculated_beta is None and _num(ov, "Beta") is not None:
                tw.append(
                    "Historical mode: Yahoo overview beta omitted; regression beta unavailable — "
                    "using CAPM fallback chain without live overview beta."
                )
            if beta is None:
                tw.append("Beta unavailable; CAPM cost of equity cannot be calculated.")
            mrp = dynamic_mrp
            k_e = request.cost_of_equity_override
            if k_e is None and beta is not None and mrp is not None:
                k_e = float(risk_free_rate) + float(beta) * mrp
            elif k_e is None and mrp is None:
                tw.append(
                    "Market risk premium unavailable; CAPM cost of equity cannot be calculated."
                )

            cost_of_debt: float | None = None
            weight_of_equity: float | None = None
            weight_of_debt: float | None = None
            calculated_wacc: float | None = None

            market_cap = _num(ov_inputs, "marketCap", "MarketCapitalization")
            if market_cap is not None and market_cap > 0 and k_e is not None:
                e_val = market_cap
                d_val = debt0 if debt0 is not None else 0.0
                v_val = e_val + d_val

                weight_of_equity = e_val / v_val
                weight_of_debt = d_val / v_val

                if d_val > 0:
                    if int_exp is not None and int_exp > 0:
                        cost_of_debt = int_exp / d_val
                    elif int_exp == 0:
                        cost_of_debt = 0.0

                if t_rate is not None and cost_of_debt is not None:
                    calculated_wacc = (weight_of_equity * k_e) + (
                        weight_of_debt * cost_of_debt * (1 - t_rate)
                    )
                elif d_val == 0.0:
                    calculated_wacc = k_e
                else:
                    tw.append("WACC unavailable; debt or tax inputs are incomplete.")
            elif market_cap is None or market_cap <= 0:
                tw.append("WACC unavailable; market capitalization is missing.")
            elif k_e is not None:
                calculated_wacc = k_e

            wacc = request.wacc
            if wacc is None:
                wacc = calculated_wacc
                if wacc is not None and k_e is not None and wacc == k_e:
                    sw.append(
                        f"{t}: WACC not set and market cap unavailable/no debt; using k_e ({wacc}) for FCFF value"
                    )

            # Calculate sustainable growth rate early for dynamic defaults
            dps = _num(ov_inputs, "DividendPerShare", "dividendPerShare")
            earnings_per_share = (
                _num(ov_inputs, "trailingEps", "EPS")
                or _num(i0, "dilutedEPS")
                or _num(i0, "basicEPS")
            )
            roe = _num(ov_inputs, "returnOnEquity", "ReturnOnEquityTTM")
            ni_sg = _num(i0, "netIncome")
            teq_sg = _num(b0, "totalStockholderEquity")
            if roe is None and ni_sg is not None and teq_sg is not None and ni_sg and teq_sg:
                with contextlib.suppress(ZeroDivisionError):
                    roe = ni_sg / teq_sg

            payout_ratio = _num(ov_inputs, "payoutRatio", "PayoutRatio")
            if (
                payout_ratio is None
                and dps is not None
                and earnings_per_share
                and earnings_per_share > 0
            ):
                payout_ratio = float(dps) / earnings_per_share

            sustainable_growth_rate = None
            if roe is not None and payout_ratio is not None:
                sustainable_growth_rate = float(roe) * (1.0 - float(payout_ratio))

            g_f = request.fcff_growth
            if g_f is None:
                g_f = sustainable_growth_rate
                g_f, adj = _bounded_growth_for_perpetuity(g_f, k_e)
                if adj and g_f is not None:
                    tw.append(
                        f"FCFE growth auto-adjusted to {g_f:.2%} to stay below cost of equity."
                    )
            if g_f is None and fcfe is not None:
                tw.append("FCFE growth unavailable; FCFE perpetuity valuation skipped.")

            g_t = request.fcff_terminal_growth
            if g_t is None:
                g_t = sustainable_growth_rate
                g_t, adj = _bounded_growth_for_perpetuity(g_t, wacc)
                if adj and g_t is not None:
                    tw.append(
                        f"FCFF terminal growth auto-adjusted to {g_t:.2%} to stay below WACC."
                    )
            if g_t is None and fcff is not None:
                tw.append("FCFF terminal growth unavailable; FCFF perpetuity valuation skipped.")

            fcff_equity_v = None
            fcfe_v = None
            if fcff is not None and wacc is not None and g_t is not None:
                try:
                    enterprise_v = fcff_firm_value_perpetuity(fcff, wacc, g_t)
                    nd = _book_net_debt(b0)
                    if nd is None:
                        tw.append(
                            "FCFF implied equity per share skipped: cannot compute book net debt "
                            "(debt and/or cash fields missing on balance sheet)."
                        )
                    else:
                        fcff_equity_v = equity_value_from_enterprise_value(enterprise_v, nd)
                except ValueError as exc:
                    tw.append(f"FCFF value: {exc}")
            if fcfe is not None and k_e is not None and g_f is not None:
                try:
                    fcfe_v = fcfe_equity_value_perpetuity(fcfe, k_e, g_f)
                except ValueError as exc:
                    tw.append(f"FCFE value: {exc}")

            sh = _num(ov_inputs, "SharesOutstanding", "sharesOutstanding")
            ddm_g: float | None = None
            ddm2: float | None = None

            g_div = request.ddm_gordon_g
            if g_div is None:
                g_div = sustainable_growth_rate
                g_div, adj = _bounded_growth_for_perpetuity(g_div, k_e)
                if adj and g_div is not None:
                    tw.append(
                        f"Gordon DDM growth auto-adjusted to {g_div:.2%} to stay below cost of equity."
                    )

            if dps is not None and k_e is not None and g_div is not None and k_e > g_div:
                try:
                    d1 = float(dps) * (1.0 + g_div)
                    ddm_g = ddm_gordon(d1, k_e, g_div)
                    dy = _dividend_yield_decimal(ov_inputs)
                    if dy is not None and dy < 0.01:
                        tw.append(
                            "Gordon DDM: very low dividend yield from overview — model reflects "
                            "cash payouts only, not operating value (typical for low-payout growth names)."
                        )
                    elif dy is None and float(dps) < 0.5 and k_e > 0.12:
                        tw.append(
                            "Gordon DDM: small absolute dividend per share vs. high k_e — payout-based "
                            "value is usually not comparable to market for low-dividend growth names."
                        )
                except (ValueError, InvalidValuationError) as exc:
                    tw.append(f"Gordon DDM: {exc}")
            elif dps is not None and k_e is not None and g_div is not None:
                tw.append("Gordon DDM skipped: cost of equity must exceed dividend growth")
            elif dps is not None and g_div is None:
                tw.append("Gordon DDM skipped: dividend growth unavailable.")
            elif dps is not None and k_e is None:
                tw.append("Gordon DDM skipped: cost of equity unavailable.")

            if dps is not None and k_e is not None and k_e > 0:
                try:
                    g1: float | None
                    g2: float | None
                    n_: int
                    if request.ddm_two_stage is not None:
                        g1 = request.ddm_two_stage.g1
                        g2 = request.ddm_two_stage.g2
                        n_ = int(request.ddm_two_stage.n_periods)
                    else:
                        eps_growth = _num(ov_inputs, "earningsGrowth")
                        g1 = eps_growth if eps_growth is not None else sustainable_growth_rate
                        g2 = sustainable_growth_rate
                        n_ = 5
                        g1, g1_adj = _bounded_growth_for_perpetuity(g1, k_e)
                        g2, g2_adj = _bounded_growth_for_perpetuity(g2, k_e)
                        if g1_adj and g1 is not None:
                            tw.append(
                                f"Two-stage DDM stage-1 growth auto-adjusted to {g1:.2%} to stay below cost of equity."
                            )
                        if g2_adj and g2 is not None:
                            tw.append(
                                f"Two-stage DDM stage-2 growth auto-adjusted to {g2:.2%} to stay below cost of equity."
                            )

                    if g1 is None or g2 is None:
                        tw.append("Two-stage DDM skipped: growth inputs unavailable.")
                    elif k_e <= g1 or k_e <= g2:
                        raise InvalidValuationError(
                            "DDM two-stage: k must exceed g1 and g2", {"k": k_e}
                        )
                    else:
                        ddm2 = ddm_two_stage(float(dps), g1, g2, n_, k_e)
                except (ValueError, InvalidValuationError) as exc:
                    tw.append(f"Two-stage DDM: {exc}")
            elif dps is None:
                tw.append("DDM skipped (dividend per share missing from overview)")
            elif k_e is None:
                tw.append("Two-stage DDM skipped: cost of equity unavailable.")

            if fcff_equity_v is not None and sh is not None:
                fcff_value_per_share: float | None = per_share(fcff_equity_v, sh)
            else:
                fcff_value_per_share = None
            if fcfe_v is not None and sh is not None:
                fcfe_value_per_share: float | None = per_share(fcfe_v, sh)
            else:
                fcfe_value_per_share = None

            # Earnings and Cash Flow Analysis
            gross_margin = _num(ov_inputs, "grossMargins")
            gp = _num(i0, "grossProfit")
            rev_gm = _num(i0, "totalRevenue")
            if gross_margin is None and gp is not None and rev_gm is not None and gp and rev_gm:
                with contextlib.suppress(ZeroDivisionError):
                    gross_margin = gp / rev_gm

            operating_margin = _num(ov_inputs, "operatingMargins", "OperatingMarginTTM")
            rev_om = _num(i0, "totalRevenue")
            if operating_margin is None and ebit is not None and rev_om is not None and rev_om:
                with contextlib.suppress(ZeroDivisionError):
                    operating_margin = ebit / rev_om

            roa = _num(ov_inputs, "returnOnAssets", "ReturnOnAssetsTTM")
            ni_roa = _num(i0, "netIncome")
            ta = _num(b0, "totalAssets")
            if roa is None and ni_roa is not None and ta is not None and ni_roa and ta:
                with contextlib.suppress(ZeroDivisionError):
                    roa = ni_roa / ta

            roe = _num(ov_inputs, "returnOnEquity", "ReturnOnEquityTTM")
            ni_roe2 = _num(i0, "netIncome")
            teq_roe2 = _num(b0, "totalStockholderEquity")
            if (
                roe is None
                and ni_roe2 is not None
                and teq_roe2 is not None
                and ni_roe2
                and teq_roe2
            ):
                with contextlib.suppress(ZeroDivisionError):
                    roe = ni_roe2 / teq_roe2

            book_value_per_share = _num(ov_inputs, "bookValue", "BookValue")
            earnings_per_share = (
                _num(ov_inputs, "trailingEps", "EPS")
                or _num(i0, "dilutedEPS")
                or _num(i0, "basicEPS")
            )

            cash_flow_per_share = None
            op_cf = _num(c0, "operatingCashFlow", "operatingCashflow")
            if op_cf is not None and sh is not None and sh > 0:
                cash_flow_per_share = op_cf / sh

            price = _num(ov_inputs, "currentPrice", "previousClose", "Price")

            price_to_book = _num(ov_inputs, "priceToBook", "PriceToBookRatio")
            if (
                price_to_book is None
                and price is not None
                and book_value_per_share
                and book_value_per_share > 0
            ):
                price_to_book = price / book_value_per_share

            price_to_earnings = _num(ov_inputs, "trailingPE", "PERatio")
            if (
                price_to_earnings is None
                and price is not None
                and earnings_per_share
                and earnings_per_share > 0
            ):
                price_to_earnings = price / earnings_per_share

            price_to_cash_flow = None
            market_cap = _num(ov_inputs, "marketCap", "MarketCapitalization")
            if market_cap is not None and op_cf is not None and op_cf > 0:
                price_to_cash_flow = market_cap / op_cf
            elif price is not None and cash_flow_per_share and cash_flow_per_share > 0:
                price_to_cash_flow = price / cash_flow_per_share

            historical_growth_rate = _num(
                ov_inputs, "earningsQuarterlyGrowth", "QuarterlyEarningsGrowthYOY"
            )

            export_drivers.append(
                ValuationExportDrivers(
                    ticker=t,
                    ebit=ebit,
                    tax_rate=float(t_rate) if t_rate is not None else None,
                    depreciation=float(depr) if depr is not None else None,
                    capex=float(capex) if capex is not None else None,
                    delta_nwc=float(delta_nwc) if delta_nwc is not None else None,
                    interest_expense=float(int_exp) if int_exp is not None else None,
                    net_borrowing=float(net_borrowing) if net_borrowing is not None else None,
                    financial_unsafe=bool(financial_unsafe),
                    beta=float(beta) if beta is not None else None,
                    market_risk_premium=float(mrp) if mrp is not None else None,
                    risk_free_annual=float(risk_free_rate),
                    market_cap=float(market_cap) if market_cap is not None else None,
                    total_debt=float(debt0) if debt0 is not None else None,
                    cost_of_debt_pretax=float(cost_of_debt) if cost_of_debt is not None else None,
                )
            )

            rows.append(
                TickerValuationBlock(
                    ticker=t,
                    fcff=fcff,
                    fcfe=fcfe,
                    fcff_value_per_share=fcff_value_per_share,
                    fcfe_value_per_share=fcfe_value_per_share,
                    ddm_gordon=ddm_g,
                    ddm_two_stage=ddm2,
                    cost_of_equity=float(k_e) if k_e is not None else None,
                    cost_of_debt=cost_of_debt,
                    weight_of_equity=weight_of_equity,
                    weight_of_debt=weight_of_debt,
                    wacc=float(wacc) if wacc is not None else None,
                    historical_growth_rate=historical_growth_rate,
                    sustainable_growth_rate=sustainable_growth_rate,
                    roe=roe,
                    gross_margin=gross_margin,
                    operating_margin=operating_margin,
                    roa=roa,
                    book_value_per_share=book_value_per_share,
                    earnings_per_share=earnings_per_share,
                    cash_flow_per_share=cash_flow_per_share,
                    price_to_book=price_to_book,
                    price_to_earnings=price_to_earnings,
                    price_to_cash_flow=price_to_cash_flow,
                    calculated_beta=calculated_beta,
                    historical_return=historical_return,
                    historical_volatility=historical_volatility,
                    historical_prices=historical_prices,
                    warnings=tw,
                )
            )

        source = next(iter(sources_seen)) if len(sources_seen) == 1 else "mixed"

        return (
            ValuationResult(
                as_of=valuation_ts,
                per_ticker=rows,
                data_source=source,
                warnings=sw,
                export_drivers=export_drivers,
            ),
            source,
        )


__all__ = ["ValuationService"]
