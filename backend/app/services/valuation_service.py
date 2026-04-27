"""``POST /api/valuation`` — FCFF, FCFE, DDM from Yahoo (yfinance) or Alpha Vantage fundamentals."""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.service import DataService
from app.errors import InvalidValuationError, ProviderUnavailableError
from app.schemas import ReturnFrequency, TickerValuationBlock, ValuationRequest, ValuationResult
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


class ValuationService:
    async def run(
        self,
        request: ValuationRequest,
        *,
        data_service: DataService,
        risk_free_rate: float,
    ) -> tuple[ValuationResult, str]:
        rows: list[TickerValuationBlock] = []
        sw: list[str] = []
        sources_seen: set[str] = set()
        as_of = datetime.now(UTC)

        try:
            spy_hist = await data_service.get_historical("SPY", frequency=ReturnFrequency.MONTHLY, lookback_years=10)
            spy_bars = sorted(spy_hist.bars, key=lambda b: b.date.isoformat())
        except Exception as e:
            sw.append(f"Failed to fetch SPY benchmark for beta: {e}")
            spy_bars = []

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
                rows.append(
                    TickerValuationBlock(
                        ticker=t,
                        fcff=None,
                        fcfe=None,
                        fcff_value_per_share=None,
                        fcfe_value_per_share=None,
                        ddm_gordon=None,
                        ddm_two_stage=None,
                        cost_of_equity=risk_free_rate + 0.05,
                        warnings=tw,
                    )
                )
                continue

            i0 = ann_i[0]
            b0, b1 = ann_b[0], ann_b[1] if len(ann_b) > 1 else ann_b[0]
            c0 = ann_c[0]

            financial_unsafe = skip_ebit_based_fcff(t, ov, i0, b0)
            if financial_unsafe:
                tw.append(
                    "FCFF/FCFE from EBIT and working capital omitted: not reliable for this "
                    "sector (bank / financials); use DDM or a bank-specific framework."
                )

            ebit = _num(i0, "ebit", "ebitb")
            tax_e = _num(i0, "incomeTaxExpense", "incomeTax")
            ebt = _num(i0, "incomeBeforeTax", "incomeBeforeTax")
            t_rate = 0.21
            if ebt and ebt > 0 and tax_e is not None:
                t_rate = min(max(tax_e / ebt, 0.0), 0.5)
            depr = (
                _num(c0, "depreciationDepletionAndAmortization", "depreciationAndAmortization")
                or 0.0
            )
            cap_raw = _num(c0, "capitalExpenditures", "capitalExpenditure")
            capex = abs(float(cap_raw)) if cap_raw is not None else 0.0
            ca0 = _num(b0, "totalCurrentAssets", "currentAssets")
            cl0 = _num(b0, "totalCurrentLiabilities", "currentLiabilities")
            ca1 = _num(b1, "totalCurrentAssets", "currentAssets")
            cl1 = _num(b1, "totalCurrentLiabilities", "currentLiabilities")
            nwc0 = (ca0 or 0.0) - (cl0 or 0.0)
            nwc1 = (ca1 or 0.0) - (cl1 or 0.0)
            delta_nwc = nwc0 - nwc1
            _ie = _num(
                i0,
                "interestAndDebtExpense",
                "interestExpense",
                "totalInterestExpense",
            )
            int_exp = abs(float(_ie)) if _ie is not None else 0.0
            debt0 = _interest_bearing_debt(b0)
            debt1 = _interest_bearing_debt(b1)
            net_borrowing = 0.0
            if debt0 is not None and debt1 is not None:
                net_borrowing = debt0 - debt1
            elif not financial_unsafe and ebit is not None:
                tw.append("Total debt incomplete; net borrowing assumed 0 for FCFE")

            if financial_unsafe:
                fcff = None
                fcfe = None
            elif ebit is None:
                tw.append("EBIT missing; cannot compute FCFF")
                fcff = None
                fcfe = None
            else:
                fcff = fcff_nopat_depre_capex_deltanwc(ebit, t_rate, depr, capex, delta_nwc)
                fcfe = fcfe_from_fcff(fcff, int_exp, t_rate, net_borrowing)

            historical_prices = None
            historical_return = None
            historical_volatility = None
            calculated_beta = None

            try:
                hist = await data_service.get_historical(t, frequency=ReturnFrequency.MONTHLY, lookback_years=10)
                historical_prices = sorted(hist.bars, key=lambda b: b.date.isoformat())
                if historical_prices:
                    if spy_bars:
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
                            from quant.sim import single_index_metrics
                            import numpy as np
                            try:
                                sim = single_index_metrics(aligned_i, aligned_m, risk_free_per_period=risk_free_rate/12.0)
                                calculated_beta = float(sim.beta)
                            except Exception as e:
                                tw.append(f"Beta regression failed: {e}")
                            
                            arr_i = np.array(aligned_i)
                            geom_mean = np.prod(1 + arr_i) ** (12.0 / len(arr_i)) - 1.0
                            historical_return = float(geom_mean)
                            historical_volatility = float(np.std(arr_i, ddof=1) * np.sqrt(12.0))
            except Exception as e:
                tw.append(f"Failed to fetch 10y historical prices: {e}")

            # Use calculated beta if available, fallback to Yahoo overview beta
            beta = calculated_beta if calculated_beta is not None else _num(ov, "Beta")
            if beta is None:
                beta = 1.0
                tw.append("Beta missing (and 10y calc failed); using 1.0 for CAPM k_e")
            mrp = 0.05
            k_e = request.cost_of_equity_override
            if k_e is None:
                k_e = float(risk_free_rate) + float(beta) * mrp

            cost_of_debt: float | None = None
            weight_of_equity: float | None = None
            weight_of_debt: float | None = None
            calculated_wacc: float | None = None

            market_cap = _num(ov, "marketCap", "MarketCapitalization")
            if market_cap is not None and market_cap > 0:
                e_val = market_cap
                d_val = debt0 if debt0 is not None else 0.0
                v_val = e_val + d_val

                weight_of_equity = e_val / v_val
                weight_of_debt = d_val / v_val

                if d_val > 0 and int_exp > 0:
                    cost_of_debt = int_exp / d_val
                else:
                    cost_of_debt = 0.0

                calculated_wacc = (weight_of_equity * k_e) + (weight_of_debt * cost_of_debt * (1 - t_rate))
            else:
                calculated_wacc = k_e

            wacc = request.wacc
            if wacc is None:
                wacc = calculated_wacc
                if wacc == k_e:
                    sw.append(f"{t}: WACC not set and market cap unavailable/no debt; using k_e ({wacc}) for FCFF value")

            # Calculate sustainable growth rate early for dynamic defaults
            dps = _num(ov, "DividendPerShare", "dividendPerShare")
            earnings_per_share = _num(ov, "trailingEps", "EPS") or _num(i0, "dilutedEPS") or _num(i0, "basicEPS")
            roe = _num(ov, "returnOnEquity", "ReturnOnEquityTTM")
            if roe is None and _num(i0, "netIncome") and _num(b0, "totalStockholderEquity"):
                try: roe = _num(i0, "netIncome") / _num(b0, "totalStockholderEquity")
                except ZeroDivisionError: pass

            payout_ratio = _num(ov, "payoutRatio", "PayoutRatio")
            if payout_ratio is None and dps is not None and earnings_per_share and earnings_per_share > 0:
                payout_ratio = float(dps) / earnings_per_share

            sustainable_growth_rate = None
            if roe is not None and payout_ratio is not None:
                sustainable_growth_rate = float(roe) * (1.0 - float(payout_ratio))

            g_f = request.fcff_growth
            if g_f is None:
                g_f = sustainable_growth_rate if sustainable_growth_rate is not None else 0.02
            
            g_t = request.fcff_terminal_growth
            if g_t is None:
                g_t = 0.025

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
            if fcfe is not None:
                try:
                    fcfe_v = fcfe_equity_value_perpetuity(fcfe, k_e, g_f)
                except ValueError as exc:
                    tw.append(f"FCFE value: {exc}")

            sh = _num(ov, "SharesOutstanding", "sharesOutstanding")
            ddm_g: float | None = None
            ddm2: float | None = None
            
            g_div = request.ddm_gordon_g
            if g_div is None:
                g_div = sustainable_growth_rate if sustainable_growth_rate is not None else 0.02
            
            if dps is not None and g_div is not None and k_e > g_div:
                try:
                    d1 = float(dps) * (1.0 + g_div)
                    ddm_g = ddm_gordon(d1, k_e, g_div)
                    dy = _dividend_yield_decimal(ov)
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
            elif dps is not None and g_div is not None:
                tw.append("Gordon DDM skipped: cost of equity must exceed dividend growth")
            
            if dps is not None and k_e > 0:
                try:
                    if request.ddm_two_stage is not None:
                        g1 = request.ddm_two_stage.g1
                        g2 = request.ddm_two_stage.g2
                        n_ = int(request.ddm_two_stage.n_periods)
                    else:
                        eps_growth = _num(ov, "earningsGrowth")
                        g1 = eps_growth if eps_growth is not None else (sustainable_growth_rate if sustainable_growth_rate is not None else 0.05)
                        g2 = 0.025
                        n_ = 5

                    if k_e <= g1 or k_e <= g2:
                        raise InvalidValuationError(
                            "DDM two-stage: k must exceed g1 and g2", {"k": k_e}
                        )
                    ddm2 = ddm_two_stage(float(dps), g1, g2, n_, k_e)
                except (ValueError, InvalidValuationError) as exc:
                    tw.append(f"Two-stage DDM: {exc}")
            elif dps is None:
                tw.append("DDM skipped (dividend per share missing from overview)")

            if fcff_equity_v is not None and sh is not None:
                fcff_value_per_share: float | None = per_share(fcff_equity_v, sh)
            else:
                fcff_value_per_share = None
            if fcfe_v is not None and sh is not None:
                fcfe_value_per_share: float | None = per_share(fcfe_v, sh)
            else:
                fcfe_value_per_share = None

            # Earnings and Cash Flow Analysis
            gross_margin = _num(ov, "grossMargins")
            if gross_margin is None and _num(i0, "grossProfit") and _num(i0, "totalRevenue"):
                try: gross_margin = _num(i0, "grossProfit") / _num(i0, "totalRevenue")
                except ZeroDivisionError: pass
            
            operating_margin = _num(ov, "operatingMargins", "OperatingMarginTTM")
            if operating_margin is None and ebit is not None and _num(i0, "totalRevenue"):
                try: operating_margin = ebit / _num(i0, "totalRevenue")
                except ZeroDivisionError: pass

            roa = _num(ov, "returnOnAssets", "ReturnOnAssetsTTM")
            if roa is None and _num(i0, "netIncome") and _num(b0, "totalAssets"):
                try: roa = _num(i0, "netIncome") / _num(b0, "totalAssets")
                except ZeroDivisionError: pass

            roe = _num(ov, "returnOnEquity", "ReturnOnEquityTTM")
            if roe is None and _num(i0, "netIncome") and _num(b0, "totalStockholderEquity"):
                try: roe = _num(i0, "netIncome") / _num(b0, "totalStockholderEquity")
                except ZeroDivisionError: pass

            book_value_per_share = _num(ov, "bookValue", "BookValue")
            earnings_per_share = _num(ov, "trailingEps", "EPS") or _num(i0, "dilutedEPS") or _num(i0, "basicEPS")
            
            cash_flow_per_share = None
            op_cf = _num(c0, "operatingCashFlow", "operatingCashflow")
            if op_cf is not None and sh is not None and sh > 0:
                cash_flow_per_share = op_cf / sh

            price = _num(ov, "currentPrice", "previousClose", "Price")
            
            price_to_book = _num(ov, "priceToBook", "PriceToBookRatio")
            if price_to_book is None and price is not None and book_value_per_share and book_value_per_share > 0:
                price_to_book = price / book_value_per_share

            price_to_earnings = _num(ov, "trailingPE", "PERatio")
            if price_to_earnings is None and price is not None and earnings_per_share and earnings_per_share > 0:
                price_to_earnings = price / earnings_per_share

            price_to_cash_flow = None
            market_cap = _num(ov, "marketCap", "MarketCapitalization")
            if market_cap is not None and op_cf is not None and op_cf > 0:
                price_to_cash_flow = market_cap / op_cf
            elif price is not None and cash_flow_per_share and cash_flow_per_share > 0:
                price_to_cash_flow = price / cash_flow_per_share

            historical_growth_rate = _num(ov, "earningsQuarterlyGrowth", "QuarterlyEarningsGrowthYOY")

            rows.append(
                TickerValuationBlock(
                    ticker=t,
                    fcff=fcff,
                    fcfe=fcfe,
                    fcff_value_per_share=fcff_value_per_share,
                    fcfe_value_per_share=fcfe_value_per_share,
                    ddm_gordon=ddm_g,
                    ddm_two_stage=ddm2,
                    cost_of_equity=float(k_e),
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
                as_of=as_of,
                per_ticker=rows,
                data_source=source,
                warnings=sw,
            ),
            source,
        )


__all__ = ["ValuationService"]
