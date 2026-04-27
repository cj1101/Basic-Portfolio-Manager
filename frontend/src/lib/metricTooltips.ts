export type MetricTooltipKey =
  | "expectedReturn"
  | "stdDev"
  | "orpExpectedReturn"
  | "orpVolatility"
  | "orpSharpe"
  | "riskFreeRate"
  | "yStar"
  | "weightRiskFree"
  | "completeExpectedReturn"
  | "completeStdDev"
  | "stockExpectedReturn"
  | "stockStdDev"
  | "beta"
  | "alpha"
  | "firmSpecificVar"
  | "orpWeight"
  | "nObservations"
  | "assetSynergy";

export interface MetricTooltipParams {
  value?: number;
  riskFreeRate?: number;
  orpExpectedReturn?: number;
  orpStdDev?: number;
}

const pct = (value: number) => `${(value * 100).toFixed(2)}%`;

const signedPct = (value: number) => {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${pct(value)}`;
};

export function metricTooltip(key: MetricTooltipKey, params: MetricTooltipParams = {}): string {
  const { value, riskFreeRate, orpExpectedReturn, orpStdDev } = params;

  switch (key) {
    case "expectedReturn":
      if (value == null) {
        return "Expected return is the model's annual average growth estimate for this portfolio, before accounting for uncertainty.";
      }
      return `Expected return is the model's annual average growth estimate. Current value ${pct(value)} means the portfolio is projected to grow by about ${pct(value)} per year on average, with actual outcomes varying around that estimate.`;
    case "stdDev":
      if (value == null) {
        return "Volatility (σ) measures annual uncertainty of returns. Higher Volatility (σ) means a wider spread of likely outcomes.";
      }
      return `Volatility (σ) measures annual uncertainty of returns. Current Volatility (σ) ${pct(value)} means returns are expected to swing more widely than a lower-volatility portfolio, even if average return is the same.`;
    case "orpExpectedReturn":
      if (value == null) {
        return "Optimal Risky Portfolio Expected Rate of Return (E(r_ORP)) is the weighted average expected return of the optimal risky mix.";
      }
      return `Optimal Risky Portfolio Expected Rate of Return (E(r_ORP)) is computed from ticker expected returns and Portfolio Weights (w). Current value ${pct(value)} is the risky portfolio return level that feeds both Sharpe and Optimal Risky Allocation Weight (y*) sizing.`;
    case "orpVolatility":
      if (value == null) {
        return "Optimal Risky Portfolio Volatility (sigma_ORP) is the total risk of the optimal risky portfolio after diversification.";
      }
      return `Optimal Risky Portfolio Volatility (sigma_ORP) is based on Portfolio Weights (w)^T * Volatility (σ) * Portfolio Weights (w). Current value ${pct(value)} sets how much risk each extra unit of Optimal Risky Portfolio exposure adds to your complete portfolio.`;
    case "orpSharpe":
      if (value == null) {
        return "Optimal Risky Portfolio Sharpe Ratio is (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / Optimal Risky Portfolio Volatility (sigma_ORP), or excess return earned per unit of risk.";
      }
      return `Optimal Risky Portfolio Sharpe Ratio is (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / Optimal Risky Portfolio Volatility (sigma_ORP). Current value ${value.toFixed(3)} means the Optimal Risky Portfolio delivers about ${value.toFixed(3)} units of excess return for each unit of Volatility (σ).`;
    case "riskFreeRate":
      if (riskFreeRate == null) {
        return "Risk-Free Rate (r_f) is the baseline return from lending or borrowing with minimal default risk, and anchors the CAL.";
      }
      return `Risk-Free Rate (r_f) is the baseline return from lending or borrowing. Current Risk-Free Rate (r_f) ${pct(riskFreeRate)} is the intercept for Sharpe and the blend point against Optimal Risky Portfolio in your complete allocation.`;
    case "yStar":
      if (value == null) {
        return "Optimal Risky Allocation Weight (y*) is the fraction of your wealth allocated to the risky Optimal Risky Portfolio. Formula: Optimal Risky Allocation Weight (y*) = (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / (Risk Aversion Parameter (A) * Optimal Risky Portfolio Volatility (sigma_ORP)^2).";
      }
      if (riskFreeRate != null && orpExpectedReturn != null && orpStdDev != null) {
        const context = `Inputs now: Expected Optimal Risky Portfolio Rate of Return (E(r_ORP))=${pct(orpExpectedReturn)}, Risk-Free Rate (r_f)=${pct(riskFreeRate)}, Optimal Risky Portfolio Volatility (sigma_ORP)=${pct(orpStdDev)}.`;
        if (value > 1) {
          return `Optimal Risky Allocation Weight (y*) sets risky exposure using Optimal Risky Allocation Weight (y*) = (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / (Risk Aversion Parameter (A) * Optimal Risky Portfolio Volatility (sigma_ORP)^2). ${context} Current Optimal Risky Allocation Weight (y*) ${pct(value)} means leveraged risk: you allocate more than 100% to Optimal Risky Portfolio and finance the rest by borrowing at Risk-Free Rate (r_f).`;
        }
        if (value < 0) {
          return `Optimal Risky Allocation Weight (y*) sets risky exposure using Optimal Risky Allocation Weight (y*) = (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / (Risk Aversion Parameter (A) * Optimal Risky Portfolio Volatility (sigma_ORP)^2). ${context} Current Optimal Risky Allocation Weight (y*) ${pct(value)} implies a net short Optimal Risky Portfolio position, which is generally outside normal v1 usage.`;
        }
        return `Optimal Risky Allocation Weight (y*) sets risky exposure using Optimal Risky Allocation Weight (y*) = (Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) - Risk-Free Rate (r_f)) / (Risk Aversion Parameter (A) * Optimal Risky Portfolio Volatility (sigma_ORP)^2). ${context} Current Optimal Risky Allocation Weight (y*) ${pct(value)} means ${pct(value)} of wealth goes to Optimal Risky Portfolio and the remainder stays in risk-free asset.`;
      }
      if (value > 1) {
        return `Optimal Risky Allocation Weight (y*) sets risky exposure. Current Optimal Risky Allocation Weight (y*) ${pct(value)} means leveraged risk: you allocate more than 100% to Optimal Risky Portfolio and finance the rest by borrowing at Risk-Free Rate (r_f).`;
      }
      if (value < 0) {
        return `Optimal Risky Allocation Weight (y*) sets risky exposure. Current Optimal Risky Allocation Weight (y*) ${pct(value)} implies a net short Optimal Risky Portfolio position, which is generally outside normal v1 usage.`;
      }
      return `Optimal Risky Allocation Weight (y*) sets risky exposure. Current Optimal Risky Allocation Weight (y*) ${pct(value)} means ${pct(value)} of wealth goes to Optimal Risky Portfolio and the remainder stays in risk-free asset.`;
    case "weightRiskFree":
      if (value == null) {
        return "Weight in risk-free asset equals 1 - Optimal Risky Allocation Weight (y*). Positive values mean lending; negative values mean borrowing (leverage).";
      }
      if (value < 0) {
        return `Weight in risk-free asset equals 1 - Optimal Risky Allocation Weight (y*). Current value ${pct(value)} is negative, so the portfolio is borrowing at Risk-Free Rate (r_f) to amplify Optimal Risky Portfolio exposure.`;
      }
      return `Weight in risk-free asset equals 1 - Optimal Risky Allocation Weight (y*). Current value ${pct(value)} means this portion is parked in the risk-free asset to dampen total risk.`;
    case "completeExpectedReturn":
      if (value == null) {
        return "Expected Complete Portfolio Rate of Return (E(r_C)) blends Optimal Risky Portfolio and risk-free: Expected Complete Portfolio Rate of Return (E(r_C)) = Optimal Risky Allocation Weight (y*) * Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) + (1 - Optimal Risky Allocation Weight (y*)) * Risk-Free Rate (r_f).";
      }
      return `Expected Complete Portfolio Rate of Return (E(r_C)) uses Expected Complete Portfolio Rate of Return (E(r_C)) = Optimal Risky Allocation Weight (y*) * Expected Optimal Risky Portfolio Rate of Return (E(r_ORP)) + (1 - Optimal Risky Allocation Weight (y*)) * Risk-Free Rate (r_f). Current value ${pct(value)} is your personalized return estimate after applying risk preference to Optimal Risky Portfolio.`;
    case "completeStdDev":
      if (value == null) {
        return "Complete portfolio volatility is Complete Portfolio Volatility (sigma_C) = |Optimal Risky Allocation Weight (y*)| * Optimal Risky Portfolio Volatility (sigma_ORP) because the risk-free asset adds no volatility.";
      }
      return `Complete volatility follows Complete Portfolio Volatility (sigma_C) = |Optimal Risky Allocation Weight (y*)| * Optimal Risky Portfolio Volatility (sigma_ORP). Current value ${pct(value)} is your effective annual risk after scaling Optimal Risky Portfolio exposure by Optimal Risky Allocation Weight (y*).`;
    case "stockExpectedReturn":
      if (value == null) {
        return "Expected Asset Rate of Return (E(r_i)) is the model's annual expected return for a single stock, used in Optimal Risky Portfolio optimization.";
      }
      return `Expected Asset Rate of Return (E(r_i)) is each stock's annual expected return estimate. Current value ${pct(value)} increases Optimal Risky Portfolio attractiveness when paired with manageable covariance risk.`;
    case "stockStdDev":
      if (value == null) {
        return "Asset Volatility (sigma_i) is a stock's standalone annual volatility before diversification effects.";
      }
      return `Asset Volatility (sigma_i) is a stock's standalone annual volatility. Current value ${pct(value)} means this name contributes more risk pressure unless offset by low correlation with others.`;
    case "beta":
      if (value == null) {
        return "Beta (β) measures sensitivity to market moves: Beta (β) = Covariance (Cov(r_i, r_M)) / Variance (Var(r_M)).";
      }
      if (value > 1) {
        return `Beta (β) measures market sensitivity. Current Beta (β) ${value.toFixed(2)} suggests this stock tends to move more than the market in the same direction.`;
      }
      if (value < 0) {
        return `Beta (β) measures market sensitivity. Current Beta (β) ${value.toFixed(2)} indicates this stock tends to move opposite the market on average.`;
      }
      return `Beta (β) measures market sensitivity. Current Beta (β) ${value.toFixed(2)} indicates lower-than-market directional sensitivity.`;
    case "alpha":
      if (value == null) {
        return "Alpha (α) is excess return versus CAPM expectation: Alpha (α) = mean(excess_i) - Beta (β) * mean(excess_M).";
      }
      if (value > 0) {
        return `Alpha (α) is excess return versus CAPM expectation. Current Alpha (α) ${signedPct(value)} means the stock has historically outperformed what its Beta (β) alone would predict.`;
      }
      if (value < 0) {
        return `Alpha (α) is excess return versus CAPM expectation. Current Alpha (α) ${signedPct(value)} means the stock has historically underperformed what its Beta (β) alone would predict.`;
      }
      return "Alpha (α) near zero means realized excess return is close to CAPM-implied expectations.";
    case "firmSpecificVar":
      if (value == null) {
        return "Firm-specific variance is idiosyncratic risk not explained by market Beta (β): Idiosyncratic Variance (sigma^2(e_i)).";
      }
      return `Firm-specific variance is stock-specific risk after removing market-driven risk. Current value ${value.toFixed(3)} means this amount of variance cannot be diversified by market exposure alone.`;
    case "orpWeight":
      if (value == null) {
        return "Optimal Risky Portfolio Weight (w_i) is the fraction of the risky Optimal Risky Portfolio allocated to this stock. Weights across risky assets sum to 1.";
      }
      return `Optimal Risky Portfolio Weight (w_i) is this stock's share inside the risky Optimal Risky Portfolio. Current value ${pct(value)} means ${pct(value)} of the risky bucket is allocated here before Optimal Risky Allocation Weight (y*) scaling to total wealth.`;
    case "nObservations":
      if (value == null) {
        return "N obs is the number of return observations used to estimate metrics for that stock.";
      }
      return `N obs shows sample size used for estimation. Current value ${Math.round(value)} gives context for statistical confidence in expected return, volatility, beta, and alpha.`;
    case "assetSynergy":
      return "Pairwise correlation ρ is the covariance of two assets normalized to [-1, 1]. The optimizer still uses the full covariance matrix; this view is for human-readable synergy and diversification. Values near +1 move together; near 0 are independent; near -1 move opposite.";
    default:
      return "Portfolio metric explanation.";
  }
}

export function riskFreeBlendTooltip(riskFree: number, orpRet: number, orpRisk: number): string {
  return `Capital Allocation Line mixes Optimal Risky Portfolio with Risk-Free Rate (r_f). With Risk-Free Rate (r_f)=${pct(riskFree)}, Expected Optimal Risky Portfolio Rate of Return (E(r_ORP))=${pct(orpRet)}, and Optimal Risky Portfolio Volatility (sigma_ORP)=${pct(orpRisk)}, moving along the line changes return and risk proportionally through Optimal Risky Allocation Weight (y*).`;
}
