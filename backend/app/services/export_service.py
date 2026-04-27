# ExportService - Automated Portfolio Analysis Excel Export
import io

import openpyxl
from openpyxl.styles import Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.schemas import (
    AnalyticsPerformanceResult,
    OptimizationResult,
    ValuationResult,
)


class ExportService:
    def __init__(self):
        self.header_font = Font(bold=True, color="FFFFFF")
        self.header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        self.border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
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
        for ticker in tickers:
            v_block = next((v for v in valuation.per_ticker if v.ticker == ticker), None)
            self._add_ticker_sheet(wb, ticker, v_block, rf_series, spy_bars)

        self._add_chart_sheet(wb, tickers, valuation, spy_bars, rf_series)
        self._add_regression_sheet(wb, tickers, valuation, spy_bars, rf_series)
        self._add_valuation_sheet(wb, valuation)
        self._add_technical_analysis_sheet(wb, analytics, optimize)
        self._add_portfolio_org_sheet(wb, optimize)

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
        ws["G6"] = f"=AVERAGE(C6:C{5 + len(sorted_rf)})"

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
            
            # Map RF and RM from respective sheets by looking up date if possible, 
            # but for simplicity we assume aligned monthly series
            ws.cell(row=i, column=5, value=f"='Fred Graph'!C{i + 4}")
            ws.cell(row=i, column=6, value=f"='S&P 500'!C{i}")
            ws.cell(row=i, column=8, value=f"=1+C{i}")
            ws.cell(row=i, column=9, value=f"=C{i}-E{i}")

        last_row = len(prices) + 1
        # Metrics Table
        ws["L1"] = "Metric"
        ws["M1"] = "10 Years"
        ws["N1"] = "5 Years"
        ws["O1"] = "3 Years"
        for j in range(12, 16):
            ws.cell(row=1, column=j).font = self.bold_font

        metrics = [
            ("Arithmetic Monthly Return", "C"),
            ("Geometric Monthly Return", "H"), # Uses 1+R
            ("Variance", "C"),
            ("Standard Deviation", "C"),
            ("Monthly Risk Premium", "I")
        ]
        
        for i, (m_name, col) in enumerate(metrics, 2):
            ws.cell(row=i, column=12, value=m_name)
            # 10y (full)
            if m_name == "Geometric Monthly Return":
                ws.cell(row=i, column=13, value=f"=GEOMEAN({col}3:{col}{last_row})-1")
            elif m_name == "Standard Deviation":
                ws.cell(row=i, column=13, value=f"=STDEV.P(C3:C{last_row})")
            else:
                ws.cell(row=i, column=13, value=f"=AVERAGE({col}3:{col}{last_row})" if "Return" in m_name or "Premium" in m_name else f"=VAR.P({col}3:{col}{last_row})")

            # 5y (last 60)
            r5 = max(3, last_row - 59)
            if m_name == "Geometric Monthly Return":
                ws.cell(row=i, column=14, value=f"=GEOMEAN({col}{r5}:{col}{last_row})-1")
            elif m_name == "Standard Deviation":
                ws.cell(row=i, column=14, value=f"=STDEV.P(C{r5}:C{last_row})")
            else:
                ws.cell(row=i, column=14, value=f"=AVERAGE({col}{r5}:{col}{last_row})" if "Return" in m_name or "Premium" in m_name else f"=VAR.P({col}{r5}:{col}{last_row})")

            # 3y (last 36)
            r3 = max(3, last_row - 35)
            if m_name == "Geometric Monthly Return":
                ws.cell(row=i, column=15, value=f"=GEOMEAN({col}{r3}:{col}{last_row})-1")
            elif m_name == "Standard Deviation":
                ws.cell(row=i, column=15, value=f"=STDEV.P(C{r3}:C{last_row})")
            else:
                ws.cell(row=i, column=15, value=f"=AVERAGE({col}{r3}:{col}{last_row})" if "Return" in m_name or "Premium" in m_name else f"=VAR.P({col}{r3}:{col}{last_row})")

    def _add_chart_sheet(self, wb, tickers, valuation, spy_bars, rf_series):
        ws = wb.create_sheet("Chart")
        ws.cell(row=1, column=1, value="Date").font = self.bold_font
        for j, t in enumerate(tickers, 2):
            ws.cell(row=1, column=j, value=t).font = self.bold_font
        ws.cell(row=1, column=len(tickers)+2, value="S&P500").font = self.bold_font
        ws.cell(row=1, column=len(tickers)+3, value="RF").font = self.bold_font

        for j in range(2, len(tickers) + 5):
            ws.cell(row=2, column=j, value=100)
        
        dates = [b.date for b in sorted(spy_bars, key=lambda x: x.date)]
        for i, d in enumerate(dates, 2):
            ws.cell(row=i, column=1, value=d)
            if i > 2:
                for j, ticker in enumerate(tickers, 2):
                    ws.cell(row=i, column=j, value=f"={get_column_letter(j)}{i-1}*(1+'{ticker}'!C{i})")
                spy_col = len(tickers)+2
                rf_col = len(tickers)+3
                ws.cell(row=i, column=spy_col, value=f"={get_column_letter(spy_col)}{i-1}*(1+'S&P 500'!C{i})")
                ws.cell(row=i, column=rf_col, value=f"={get_column_letter(rf_col)}{i-1}*(1+'Fred Graph'!C{i+4})")

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
                ("Observations", f"=COUNT({y})")
            ]
            for i, (lab, form) in enumerate(stats, 4):
                ws.cell(row=i, column=col_off, value=lab)
                ws.cell(row=i, column=col_off+1, value=form)
            
            ws.cell(row=16, column=col_off+1, value="Coefficients").font = self.bold_font
            ws.cell(row=17, column=col_off, value="Intercept")
            ws.cell(row=17, column=col_off+1, value=f"=INTERCEPT({y},{x})")
            ws.cell(row=18, column=col_off, value="Market (Beta)")
            ws.cell(row=18, column=col_off+1, value=f"=SLOPE({y},{x})")
            
            col_off += 5

    def _add_valuation_sheet(self, wb, valuation):
        ws = wb.create_sheet("Valuation and Earnings Analysis")
        row = 1
        for v in valuation.per_ticker:
            ws.cell(row=row, column=1, value=f"{v.ticker} Fundamental Valuation").font = self.title_font
            row += 2
            
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
                ("P/E Ratio", v.price_to_earnings, "0.0x"),
                ("P/B Ratio", v.price_to_book, "0.0x"),
                ("ROE", v.roe, "0.00%"),
                ("Gross Margin", v.gross_margin, "0.00%")
            ]
            
            for lab, val, fmt in fields:
                if lab == "---":
                    row += 1
                    continue
                ws.cell(row=row, column=1, value=lab)
                cell = ws.cell(row=row, column=2, value=val)
                if fmt:
                    cell.number_format = fmt
                row += 1
            row += 2

    def _add_technical_analysis_sheet(self, wb, analytics, optimize):
        ws = wb.create_sheet("Technical Analysis")
        ws.cell(row=1, column=1, value="Technical Performance Metrics").font = self.title_font
        row = 3
        
        # Portfolio Summary
        ws.cell(row=row, column=1, value="ORP Portfolio Performance").font = self.bold_font
        ws.cell(row=row+1, column=1, value="Jensen's Alpha (Annual)")
        ws.cell(row=row+1, column=2, value=analytics.orp.jensen_alpha).number_format = "0.00%"
        ws.cell(row=row+2, column=1, value="Treynor Ratio")
        ws.cell(row=row+2, column=2, value=analytics.orp.treynor).number_format = "0.000"
        
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

    def _add_portfolio_org_sheet(self, wb, optimize):
        ws = wb.create_sheet("Portfolio Organization")
        ws.cell(row=1, column=1, value="Optimal Risky Portfolio (ORP)").font = self.bold_font
        row = 3
        for t, w in optimize.orp.weights.items():
            ws.cell(row=row, column=1, value=t)
            ws.cell(row=row, column=2, value=w).number_format = "0.00%"
            row += 1
        
        row += 2
        ws.cell(row=row, column=1, value="Complete Portfolio").font = self.bold_font
        ws.cell(row=row+1, column=1, value="Weight in Risky (y*)")
        ws.cell(row=row+1, column=2, value=optimize.complete.y_star).number_format = "0.00%"
        ws.cell(row=row+2, column=1, value="Weight in Risk-Free")
        ws.cell(row=row+2, column=2, value=optimize.complete.weight_risk_free).number_format = "0.00%"
        
        row += 4
        # Correlation Matrix
        ws.cell(row=row, column=1, value="Correlation Matrix").font = self.bold_font
        row += 1
        ts = optimize.correlation.tickers
        for j, t in enumerate(ts, 2):
            ws.cell(row=row, column=j, value=t).font = self.bold_font
        row += 1
        for i, t in enumerate(ts):
            ws.cell(row=row, column=1, value=t).font = self.bold_font
            for j, val in enumerate(optimize.correlation.matrix[i], 2):
                ws.cell(row=row, column=j, value=val).number_format = "0.00"
            row += 1
