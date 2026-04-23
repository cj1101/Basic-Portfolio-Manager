"""``POST /api/valuation`` — FCFF, FCFE, DDM from Alpha Vantage fundamentals."""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.service import DataService
from app.errors import InvalidValuationError, ProviderUnavailableError
from app.schemas import TickerValuationBlock, ValuationRequest, ValuationResult
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
    """Best-effort total debt from Alpha Vantage balance-sheet annual report keys."""
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
        source = "alpha-vantage"
        as_of = datetime.now(UTC)

        for raw in request.tickers:
            t = str(raw).upper().strip()
            tw: list[str] = []
            try:
                inc = await data_service.get_income_statement_json(t)
                bal = await data_service.get_balance_sheet_json(t)
                cf = await data_service.get_cash_flow_json(t)
                ov = await data_service.get_overview_json(t)
            except ProviderUnavailableError:
                raise

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
            depr = _num(
                c0, "depreciationDepletionAndAmortization", "depreciationAndAmortization"
            ) or 0.0
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

            beta = _num(ov, "Beta")
            if beta is None:
                beta = 1.0
                tw.append("Beta missing; using 1.0 for CAPM k_e")
            mrp = 0.05
            k_e = request.cost_of_equity_override
            if k_e is None:
                k_e = float(risk_free_rate) + float(beta) * mrp

            wacc = request.wacc
            g_f = request.fcff_growth or 0.02
            g_t = request.fcff_terminal_growth or 0.02
            if wacc is None:
                wacc = k_e
                sw.append(f"{t}: WACC not set; using {wacc} for FCFF value")

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
            dps = _num(ov, "DividendPerShare", "dividendPerShare")
            ddm_g: float | None = None
            ddm2: float | None = None
            g_div = request.ddm_gordon_g
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
            if dps is not None and request.ddm_two_stage is not None and k_e > 0:
                try:
                    g1 = request.ddm_two_stage.g1
                    g2 = request.ddm_two_stage.g2
                    n_ = int(request.ddm_two_stage.n_periods)
                    if k_e <= g1 or k_e <= g2:
                        raise InvalidValuationError("DDM two-stage: k must exceed g1 and g2", {"k": k_e})
                    ddm2 = ddm_two_stage(float(dps), g1, g2, n_, k_e)
                except (ValueError, InvalidValuationError) as exc:
                    tw.append(f"Two-stage DDM: {exc}")
            elif dps is None:
                tw.append("DDM skipped (dividend per share missing from overview)")
            elif dps is not None and g_div is None and request.ddm_two_stage is None:
                tw.append("DDM skipped (request did not include ddmGordonG or ddmTwoStage)")

            rows.append(
                TickerValuationBlock(
                    ticker=t,
                    fcff=fcff,
                    fcfe=fcfe,
                    fcff_value_per_share=per_share(fcff_equity_v, sh) if fcff_equity_v is not None else None,
                    fcfe_value_per_share=per_share(fcfe_v, sh) if fcfe_v is not None else None,
                    ddm_gordon=ddm_g,
                    ddm_two_stage=ddm2,
                    cost_of_equity=float(k_e),
                    warnings=tw,
                )
            )

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
