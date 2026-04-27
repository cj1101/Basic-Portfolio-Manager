# ExportService - Automated Portfolio Analysis Excel Export
import io
import openpyxl
from openpyxl.styles import Font, Border, Side, PatternFill
from openpyxl.utils import get_column_letter

from app.schemas import (
    OptimizationResult,
    AnalyticsPerformanceResult,
    ValuationResult,
)


def _xl_sheet_ref(name: str) -> str:
    """Single-quoted sheet name for Excel formulas (handles spaces and special chars)."""
    safe = name.replace("'", "''")
    return f"'{safe}'"


class ExportService:
    def __init__(self):
        self.header_font = Font(bold=True, color="FFFFFF")
        self.header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        self.border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        self.bold_font = Font(bold=True)
        self.title_font = Font(bold=True, size=14)

    def build_workbook(
        self,
        optimize: OptimizationResult,
        analytics: AnalyticsPerformanceResult,
        valuation: ValuationResult,
        spy_bars: list,
        rf_series: list,
    ) -> io.BytesIO:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        self._add_fred_graph_sheet(wb, rf_series)
        self._add_market_sheet(wb, spy_bars)

        tickers = [s.ticker for s in optimize.stocks]
        last_row_by_ticker: dict[str, int] = {}
        for ticker in tickers:
            v_block = next((v for v in valuation.per_ticker if v.ticker == ticker), None)
            self._add_ticker_sheet(wb, ticker, v_block, rf_series, spy_bars)
            if v_block and v_block.historical_prices:
                last_row_by_ticker[ticker] = len(v_block.historical_prices) + 1
            else:
                last_row_by_ticker[ticker] = 2
        common_last_row = min(last_row_by_ticker.values()) if last_row_by_ticker else 2

        # Before Chart: Portfolio Organization must exist (Chart ORP column references weights).
        orp_start_row, n_orp = self._add_portfolio_org_sheet(
            wb, optimize, common_last_row=common_last_row
        )
        self._add_chart_sheet(wb, tickers, optimize, spy_bars, orp_start_row=orp_start_row)
        self._add_regression_sheet(wb, tickers, valuation, spy_bars, rf_series)
        self._add_valuation_sheet(wb, valuation)
        self._add_technical_analysis_sheet(
            wb, analytics, orp_start_row=orp_start_row, n_orp_weights=n_orp
        )

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    def _add_fred_graph_sheet(self, wb, rf_series):
        ws = wb.create_sheet("Fred Graph")
        headers = ["observation_date", "DGS3MO", "rf"]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(row=5, column=i, value=h)
            cell.font = self.bold_font
            cell.border = self.border

        # Sort RF series by date
        sorted_rf = sorted(rf_series, key=lambda x: x["date"])
        for i, item in enumerate(sorted_rf, 6):
            ws.cell(row=i, column=1, value=item["date"])
            ws.cell(row=i, column=2, value=item["rate"] * 100)
            ws.cell(row=i, column=3, value=f"=B{i}/(100*12)")

        ws["F6"] = "Average rf"
        n = len(sorted_rf)
        if n > 0:
            end_r = 5 + n
            ws["G6"] = f"=AVERAGE(C6:C{end_r})"

    def _add_market_sheet(self, wb, spy_bars):
        ws = wb.create_sheet("S&P 500")
        headers = ["Date", "PM", "RM"]
        for i, h in enumerate(headers, 1):
            ws.cell(row=1, column=i, value=h).font = self.bold_font

        sorted_bars = sorted(spy_bars, key=lambda x: x.date)
        for i, bar in enumerate(sorted_bars, 2):
            ws.cell(row=i, column=1, value=bar.date)
            ws.cell(row=i, column=2, value=bar.close)
            if i > 2:
                ws.cell(row=i, column=3, value=f"=(B{i}-B{i-1})/B{i-1}")

    @staticmethod
    def _ticker_range(col: str, r0: int, r1: int) -> str:
        return f"{col}{r0}:{col}{r1}"

    def _ticker_metrics_row_formula(
        self, m_name: str, col: str, r_start: int, last_row: int
    ) -> str:
        """Legacy Excel stats: VARP / STDEVP (avoid VAR.P / STDEV.P)."""
        rng = self._ticker_range(col, r_start, last_row)
        if m_name == "Geometric Monthly Return":
            return f"=GEOMEAN({rng})-1"
        if m_name == "Standard Deviation":
            return f"=STDEVP({rng})"
        if m_name == "Variance":
            return f"=VARP({rng})"
        if "Return" in m_name or "Premium" in m_name:
            return f"=AVERAGE({rng})"
        return f"=VARP({rng})"

    def _add_ticker_sheet(self, wb, ticker, v_block, rf_series, spy_bars):
        ws = wb.create_sheet(ticker)
        headers = ["Date", f"P_{ticker}", f"R_{ticker}", "", "RF", "RM", "", f"1+R_{ticker}", "Risk Premium"]
        for i, h in enumerate(headers, 1):
            if h:
                ws.cell(row=1, column=i, value=h).font = self.bold_font

        if not v_block or not v_block.historical_prices:
            return

        prices = sorted(v_block.historical_prices, key=lambda x: x.date)
        for i, p in enumerate(prices, 2):
            ws.cell(row=i, column=1, value=p.date)
            ws.cell(row=i, column=2, value=p.close)
            if i > 2:
                ws.cell(row=i, column=3, value=f"=(B{i}-B{i-1})/B{i-1}")

            # Map RF and RM from respective sheets (aligned monthly rows).
            ws.cell(row=i, column=5, value=f"='Fred Graph'!C{i + 4}")
            ws.cell(row=i, column=6, value=f"='S&P 500'!C{i}")
            ws.cell(row=i, column=8, value=f"=1+C{i}")
            ws.cell(row=i, column=9, value=f"=C{i}-E{i}")

        last_row = len(prices) + 1
        r5y = max(3, last_row - 59)
        r3y = max(3, last_row - 35)

        # Metrics Table
        ws["L1"] = "Metric"
        ws["M1"] = "10 Years"
        ws["N1"] = "5 Years"
        ws["O1"] = "3 Years"
        for j in range(12, 16):
            ws.cell(row=1, column=j).font = self.bold_font

        metrics = [
            ("Arithmetic Monthly Return", "C"),
            ("Geometric Monthly Return", "H"),
            ("Variance", "C"),
            ("Standard Deviation", "C"),
            ("Monthly Risk Premium", "I"),
        ]

        for i, (m_name, col) in enumerate(metrics, 2):
            c = ws.cell(row=i, column=12, value=m_name)
            c.font = self.bold_font
            ws.cell(
                row=i,
                column=13,
                value=self._ticker_metrics_row_formula(m_name, col, 3, last_row),
            )
            ws.cell(
                row=i,
                column=14,
                value=self._ticker_metrics_row_formula(m_name, col, r5y, last_row),
            )
            ws.cell(
                row=i,
                column=15,
                value=self._ticker_metrics_row_formula(m_name, col, r3y, last_row),
            )

        # Row 7–8: annualized metrics (M2..O2 monthly arithmetic, M5..O5 monthly stdev)
        ws["L7"] = "Annualized Arithmetic Return"
        ws["M7"] = "=(1+M2)^12-1"
        ws["N7"] = "=(1+N2)^12-1"
        ws["O7"] = "=(1+O2)^12-1"
        ws["L8"] = "Annualized Volatility (monthly stdev * SQRT(12))"
        ws["M8"] = "=M5*SQRT(12)"
        ws["N8"] = "=N5*SQRT(12)"
        ws["O8"] = "=O5*SQRT(12)"
        for r in (7, 8):
            ws.cell(row=r, column=12).font = self.bold_font

    def _add_chart_sheet(
        self,
        wb,
        tickers: list,
        optimize: OptimizationResult,
        spy_bars: list,
        orp_start_row: int,
    ):
        ws = wb.create_sheet("Chart")
        pg = _xl_sheet_ref("Portfolio Organization")
        ws.cell(row=1, column=1, value="Date").font = self.bold_font
        for j, t in enumerate(tickers, 2):
            ws.cell(row=1, column=j, value=t).font = self.bold_font
        n_t = len(tickers)
        orp_col = n_t + 2
        spy_col = n_t + 3
        rf_col = n_t + 4
        ws.cell(row=1, column=orp_col, value="ORP").font = self.bold_font
        ws.cell(row=1, column=spy_col, value="S&P500").font = self.bold_font
        ws.cell(row=1, column=rf_col, value="RF").font = self.bold_font

        w_by_ticker = {
            t: orp_start_row + k for k, t in enumerate(optimize.orp.weights.keys())
        }
        for j in range(2, rf_col + 1):
            ws.cell(row=2, column=j, value=100)

        dates = [b.date for b in sorted(spy_bars, key=lambda x: x.date)]
        for i, d in enumerate(dates, 2):
            ws.cell(row=i, column=1, value=d)
            if i > 2:
                for j, tick in enumerate(tickers, 2):
                    tref = _xl_sheet_ref(tick)
                    prev = f"{get_column_letter(j)}{i - 1}"
                    ws.cell(
                        row=i,
                        column=j,
                        value=f"={prev}*(1+{tref}!C{i})",
                    )
                o_prev = f"{get_column_letter(orp_col)}{i - 1}"
                sum_r = "+".join(
                    f"{pg}!$B${w_by_ticker[tick]}*{_xl_sheet_ref(tick)}!C{i}"
                    for tick in tickers
                )
                ws.cell(
                    row=i,
                    column=orp_col,
                    value=f"={o_prev}*(1+({sum_r}))",
                )
                s_prev = f"{get_column_letter(spy_col)}{i - 1}"
                ws.cell(row=i, column=spy_col, value=f"={s_prev}*(1+'S&P 500'!C{i})")
                r_prev = f"{get_column_letter(rf_col)}{i - 1}"
                ws.cell(
                    row=i,
                    column=rf_col,
                    value=f"={r_prev}*(1+'Fred Graph'!C{i + 4})",
                )

    def _add_regression_sheet(self, wb, tickers, valuation, spy_bars, rf_series):
        ws = wb.create_sheet("1 Regression")
        last_row = len(spy_bars) + 1
        col_off = 1

        for ticker in tickers:
            ws.cell(row=1, column=col_off, value=f"{ticker} Regression Output").font = self.title_font
            ws.cell(row=3, column=col_off, value="Regression Statistics").font = self.bold_font

            y = f"'{ticker}'!I3:I{last_row}"
            x = f"'{ticker}'!F3:F{last_row}"

            stats = [
                ("Multiple R", f"=SQRT(RSQ({y},{x}))"),
                ("R Square", f"=RSQ({y},{x})"),
                ("Adjusted R Square", f"=1-(1-RSQ({y},{x}))*(COUNT({y})-1)/(COUNT({y})-2)"),
                ("Standard Error", f"=STEYX({y},{x})"),
                ("Observations", f"=COUNT({y})"),
            ]
            for i, (lab, form) in enumerate(stats, 4):
                ws.cell(row=i, column=col_off, value=lab)
                ws.cell(row=i, column=col_off + 1, value=form)

            ws.cell(row=16, column=col_off + 1, value="Coefficients").font = self.bold_font
            ws.cell(row=17, column=col_off, value="Intercept")
            ws.cell(row=17, column=col_off + 1, value=f"=INTERCEPT({y},{x})")
            ws.cell(row=18, column=col_off, value="Market (Beta)")
            ws.cell(row=18, column=col_off + 1, value=f"=SLOPE({y},{x})")

            col_off += 5

    def _add_valuation_sheet(self, wb, valuation):
        ws = wb.create_sheet("Valuation and Earnings Analysis")
        row = 1
        for v in valuation.per_ticker:
            ws.cell(row=row, column=1, value=f"{v.ticker} Fundamental Valuation").font = self.title_font
            row += 2
            in_price = v.historical_prices[-1].close if v.historical_prices else None
            in_eps = v.earnings_per_share
            in_bv = v.book_value_per_share

            r_close = row
            ws.cell(row=row, column=1, value="Last close (for ratios)")
            pc = ws.cell(row=row, column=3, value=in_price)
            if in_price is not None:
                pc.number_format = "$#,##0.00"
            row += 1
            r_eps = row
            ws.cell(row=row, column=1, value="EPS (source)")
            ec = ws.cell(row=row, column=3, value=in_eps)
            if in_eps is not None:
                ec.number_format = "0.00"
            row += 1
            ws.cell(row=row, column=1, value="P/E (implied, last / EPS)")
            pe_cell = ws.cell(row=row, column=2)
            if in_price is not None and in_eps is not None and in_eps not in (0, 0.0):
                pe_cell.value = f"=C{r_close}/C{r_eps}"
            else:
                pe_cell.value = v.price_to_earnings
            if pe_cell.value is not None:
                pe_cell.number_format = "0.0x"
            row += 1
            r_bv = row
            ws.cell(row=row, column=1, value="Book value / share (source)")
            bc = ws.cell(row=row, column=3, value=in_bv)
            if in_bv is not None:
                bc.number_format = "0.00"
            row += 1
            ws.cell(row=row, column=1, value="P/B (implied, last / BV)")
            pb_cell = ws.cell(row=row, column=2)
            if in_price is not None and in_bv is not None and in_bv not in (0, 0.0):
                pb_cell.value = f"=C{r_close}/C{r_bv}"
            else:
                pb_cell.value = v.price_to_book
            if pb_cell.value is not None:
                pb_cell.number_format = "0.0x"
            row += 1

            fields = [
                ("Cost of Equity (k_e)", v.cost_of_equity, "0.00%"),
                ("WACC", v.wacc, "0.00%"),
                ("FCFF (Current)", v.fcff, "#,##0"),
                ("FCFE (Current)", v.fcfe, "#,##0"),
                ("Sustainable Growth Rate", v.sustainable_growth_rate, "0.00%"),
                ("---", None, ""),
                ("FCFF Value per Share", v.fcff_value_per_share, "$#,##0.00"),
                ("FCFE Value per Share", v.fcfe_value_per_share, "$#,##0.00"),
                ("Gordon DDM Value", v.ddm_gordon, "$#,##0.00"),
                ("2-Stage DDM Value", v.ddm_two_stage, "$#,##0.00"),
                ("---", None, ""),
                ("P/E Ratio (data provider)", v.price_to_earnings, "0.0x"),
                ("P/B Ratio (data provider)", v.price_to_book, "0.0x"),
                ("ROE", v.roe, "0.00%"),
                ("Gross Margin", v.gross_margin, "0.00%"),
            ]

            for lab, val, fmt in fields:
                if lab == "---":
                    row += 1
                    continue
                ws.cell(row=row, column=1, value=lab)
                cell = ws.cell(row=row, column=2, value=val)
                if fmt and val is not None:
                    cell.number_format = fmt
                row += 1
            row += 2

    def _add_technical_analysis_sheet(
        self,
        wb,
        analytics: AnalyticsPerformanceResult,
        orp_start_row: int,
        n_orp_weights: int,
    ):
        ws = wb.create_sheet("Technical Analysis")
        pg = _xl_sheet_ref("Portfolio Organization")
        ws.cell(row=1, column=1, value="Technical Performance Metrics").font = self.title_font
        row = 3

        # Portfolio Summary
        ws.cell(row=row, column=1, value="ORP Portfolio Performance").font = self.bold_font
        ws.cell(row=row + 1, column=1, value="Jensen's Alpha (Annual)")
        ws.cell(row=row + 1, column=2, value=analytics.orp.jensen_alpha).number_format = "0.00%"
        ws.cell(row=row + 2, column=1, value="Treynor Ratio")
        ws.cell(row=row + 2, column=2, value=analytics.orp.treynor).number_format = "0.000"

        row += 5
        # Fama-French
        ws.cell(row=row, column=1, value="Fama-French 3-Factor Model").font = self.bold_font
        row += 1
        headers = ["Ticker", "Beta Mkt", "Beta SMB", "Beta HML", "Alpha (Annual)", "Expected Ret (FF3)"]
        for j, h in enumerate(headers, 1):
            ws.cell(row=row, column=j, value=h).font = self.bold_font
        row += 1
        for f in analytics.fama_french:
            ws.cell(row=row, column=1, value=f.ticker)
            ws.cell(row=row, column=2, value=f.beta_mkt)
            ws.cell(row=row, column=3, value=f.beta_smb)
            ws.cell(row=row, column=4, value=f.beta_hml)
            ws.cell(row=row, column=5, value=f.alpha).number_format = "0.00%"
            ws.cell(row=row, column=6, value=f.expected_return_ff3).number_format = "0.00%"
            row += 1
        row += 1
        w_end = orp_start_row + n_orp_weights - 1
        ws.cell(row=row, column=1, value="ORP weight sum (should be 1)").font = self.bold_font
        ws.cell(row=row, column=2, value=f"=SUM({pg}!$B${orp_start_row}:$B${w_end})").number_format = "0.0000"

    def _add_portfolio_org_sheet(
        self, wb, optimize: OptimizationResult, common_last_row: int
    ) -> tuple[int, int]:
        """Returns (first ORP weight row, number of ORP weight rows) for other sheets to reference."""
        ws = wb.create_sheet("Portfolio Organization")
        ws.cell(row=1, column=1, value="Optimal Risky Portfolio (ORP)").font = self.bold_font
        orp_start_row = 3
        row = 3
        tick_order = list(optimize.orp.weights.keys())
        for t, w in optimize.orp.weights.items():
            ws.cell(row=row, column=1, value=t)
            c = ws.cell(row=row, column=2, value=w)
            c.number_format = "0.00%"
            row += 1
        n_w = len(tick_order)
        sum_row = row
        ws.cell(row=sum_row, column=1, value="Sum of weights")
        ws.cell(row=sum_row, column=2, value=f"=SUM(B{orp_start_row}:B{orp_start_row + n_w - 1})").number_format = "0.00%"

        row = sum_row + 2
        ws.cell(row=row, column=1, value="Complete Portfolio").font = self.bold_font
        y_row = row + 1
        wr_row = row + 2
        ws.cell(row=y_row, column=1, value="Weight in Risky (y*)")
        # Source of truth: y* in column B; weight risk-free derived.
        ws.cell(row=y_row, column=2, value=optimize.complete.y_star).number_format = "0.00%"
        ws.cell(row=wr_row, column=1, value="Weight in Risk-Free")
        ws.cell(row=wr_row, column=2, value=f"=1-B{y_row}").number_format = "0.00%"

        row = wr_row + 4
        # Correlation matrix from aligned returns (same date window on all tickers).
        ws.cell(row=row, column=1, value="Correlation Matrix").font = self.bold_font
        r0, r1 = 3, common_last_row
        hdr = row + 1
        data0 = row + 2
        for j, t in enumerate(tick_order, 2):
            ws.cell(row=hdr, column=j, value=t).font = self.bold_font
        for i, ti in enumerate(tick_order):
            r = data0 + i
            ws.cell(row=r, column=1, value=ti).font = self.bold_font
            for j, tj in enumerate(tick_order, 2):
                a = f"{_xl_sheet_ref(ti)}!$C${r0}:$C${r1}"
                b = f"{_xl_sheet_ref(tj)}!$C${r0}:$C${r1}"
                ws.cell(row=r, column=j, value=f"=CORREL({a},{b})").number_format = "0.00"

        return orp_start_row, n_w
