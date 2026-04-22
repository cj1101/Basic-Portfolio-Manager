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
        return "Volatility (sigma) measures annual uncertainty of returns. Higher sigma means a wider spread of likely outcomes.";
      }
      return `Volatility (sigma) measures annual uncertainty of returns. Current sigma ${pct(value)} means returns are expected to swing more widely than a lower-volatility portfolio, even if average return is the same.`;
    case "orpExpectedReturn":
      if (value == null) {
        return "ORP expected return is E(r_ORP), the weighted average expected return of the optimal risky mix.";
      }
      return `ORP expected return is E(r_ORP), computed from ticker expected returns and ORP weights. Current value ${pct(value)} is the risky portfolio return level that feeds both Sharpe and y* sizing.`;
    case "orpVolatility":
      if (value == null) {
        return "ORP volatility is sigma_ORP, the total risk of the optimal risky portfolio after diversification.";
      }
      return `ORP volatility is sigma_ORP, based on w^T * Sigma * w. Current value ${pct(value)} sets how much risk each extra unit of ORP exposure adds to your complete portfolio.`;
    case "orpSharpe":
      if (value == null) {
        return "ORP Sharpe ratio is (E(r_ORP) - r_f) / sigma_ORP, or excess return earned per unit of risk.";
      }
      return `ORP Sharpe ratio is (E(r_ORP) - r_f) / sigma_ORP. Current value ${value.toFixed(3)} means the ORP delivers about ${value.toFixed(3)} units of excess return for each unit of volatility.`;
    case "riskFreeRate":
      if (riskFreeRate == null) {
        return "Risk-free rate is the baseline return from lending or borrowing with minimal default risk, and anchors the CAL.";
      }
      return `Risk-free rate is the baseline return from lending or borrowing. Current r_f ${pct(riskFreeRate)} is the intercept for Sharpe and the blend point against ORP in your complete allocation.`;
    case "yStar":
      if (value == null) {
        return "Weight in ORP (y*) is the fraction of your wealth allocated to the risky ORP. Formula: y* = (E(r_ORP) - r_f) / (A * sigma_ORP^2).";
      }
      if (riskFreeRate != null && orpExpectedReturn != null && orpStdDev != null) {
        const context = `Inputs now: E(r_ORP)=${pct(orpExpectedReturn)}, r_f=${pct(riskFreeRate)}, sigma_ORP=${pct(orpStdDev)}.`;
        if (value > 1) {
          return `Weight in ORP (y*) sets risky exposure using y* = (E(r_ORP) - r_f) / (A * sigma_ORP^2). ${context} Current y* ${pct(value)} means leveraged risk: you allocate more than 100% to ORP and finance the rest by borrowing at r_f.`;
        }
        if (value < 0) {
          return `Weight in ORP (y*) sets risky exposure using y* = (E(r_ORP) - r_f) / (A * sigma_ORP^2). ${context} Current y* ${pct(value)} implies a net short ORP position, which is generally outside normal v1 usage.`;
        }
        return `Weight in ORP (y*) sets risky exposure using y* = (E(r_ORP) - r_f) / (A * sigma_ORP^2). ${context} Current y* ${pct(value)} means ${pct(value)} of wealth goes to ORP and the remainder stays in risk-free asset.`;
      }
      if (value > 1) {
        return `Weight in ORP (y*) sets risky exposure. Current y* ${pct(value)} means leveraged risk: you allocate more than 100% to ORP and finance the rest by borrowing at r_f.`;
      }
      if (value < 0) {
        return `Weight in ORP (y*) sets risky exposure. Current y* ${pct(value)} implies a net short ORP position, which is generally outside normal v1 usage.`;
      }
      return `Weight in ORP (y*) sets risky exposure. Current y* ${pct(value)} means ${pct(value)} of wealth goes to ORP and the remainder stays in risk-free asset.`;
    case "weightRiskFree":
      if (value == null) {
        return "Weight in risk-free asset equals 1 - y*. Positive values mean lending; negative values mean borrowing (leverage).";
      }
      if (value < 0) {
        return `Weight in risk-free asset equals 1 - y*. Current value ${pct(value)} is negative, so the portfolio is borrowing at r_f to amplify ORP exposure.`;
      }
      return `Weight in risk-free asset equals 1 - y*. Current value ${pct(value)} means this portion is parked in the risk-free asset to dampen total risk.`;
    case "completeExpectedReturn":
      if (value == null) {
        return "Complete portfolio expected return blends ORP and risk-free: E(r_C) = y*E(r_ORP) + (1 - y*)r_f.";
      }
      return `Complete expected return uses E(r_C) = y*E(r_ORP) + (1 - y*)r_f. Current value ${pct(value)} is your personalized return estimate after applying risk preference to ORP.`;
    case "completeStdDev":
      if (value == null) {
        return "Complete portfolio volatility is sigma_C = |y*| * sigma_ORP because the risk-free asset adds no volatility.";
      }
      return `Complete volatility follows sigma_C = |y*| * sigma_ORP. Current value ${pct(value)} is your effective annual risk after scaling ORP exposure by y*.`;
    case "stockExpectedReturn":
      if (value == null) {
        return "E(r_i) is the model's annual expected return for a single stock, used in ORP optimization.";
      }
      return `E(r_i) is each stock's annual expected return estimate. Current value ${pct(value)} increases ORP attractiveness when paired with manageable covariance risk.`;
    case "stockStdDev":
      if (value == null) {
        return "sigma_i is a stock's standalone annual volatility before diversification effects.";
      }
      return `sigma_i is a stock's standalone annual volatility. Current value ${pct(value)} means this name contributes more risk pressure unless offset by low correlation with others.`;
    case "beta":
      if (value == null) {
        return "Beta measures sensitivity to market moves: beta = Cov(r_i, r_M) / Var(r_M).";
      }
      if (value > 1) {
        return `Beta measures market sensitivity. Current beta ${value.toFixed(2)} suggests this stock tends to move more than the market in the same direction.`;
      }
      if (value < 0) {
        return `Beta measures market sensitivity. Current beta ${value.toFixed(2)} indicates this stock tends to move opposite the market on average.`;
      }
      return `Beta measures market sensitivity. Current beta ${value.toFixed(2)} indicates lower-than-market directional sensitivity.`;
    case "alpha":
      if (value == null) {
        return "Alpha is excess return versus CAPM expectation: alpha = mean(excess_i) - beta * mean(excess_M).";
      }
      if (value > 0) {
        return `Alpha is excess return versus CAPM expectation. Current alpha ${signedPct(value)} means the stock has historically outperformed what its beta alone would predict.`;
      }
      if (value < 0) {
        return `Alpha is excess return versus CAPM expectation. Current alpha ${signedPct(value)} means the stock has historically underperformed what its beta alone would predict.`;
      }
      return "Alpha near zero means realized excess return is close to CAPM-implied expectations.";
    case "firmSpecificVar":
      if (value == null) {
        return "Firm-specific variance is idiosyncratic risk not explained by market beta: sigma^2(e_i).";
      }
      return `Firm-specific variance is stock-specific risk after removing market-driven risk. Current value ${value.toFixed(3)} means this amount of variance cannot be diversified by market exposure alone.`;
    case "orpWeight":
      if (value == null) {
        return "ORP weight w_i is the fraction of the risky ORP allocated to this stock. Weights across risky assets sum to 1.";
      }
      return `ORP weight w_i is this stock's share inside the risky ORP. Current value ${pct(value)} means ${pct(value)} of the risky bucket is allocated here before y* scaling to total wealth.`;
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
  return `Capital Allocation Line mixes ORP with r_f. With r_f=${pct(riskFree)}, E(r_ORP)=${pct(orpRet)}, and sigma_ORP=${pct(orpRisk)}, moving along the line changes return and risk proportionally through y*.`;
}
