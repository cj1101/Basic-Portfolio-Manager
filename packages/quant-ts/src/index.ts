/**
 * `@portfolio/quant` — Phase 1A TypeScript mirror of the Python Quant Engine.
 *
 * Pure math only. No I/O, no network, no logging. Values match the Python
 * reference implementation to `1e-6` on Dataset A (`docs/FIXTURES.md` §1).
 */

export {
  SYMMETRY_TOL,
  PSD_TOL,
  PROJECTION_FLOOR,
  buildCovariance,
  covarianceToCorrelation,
  ensurePsdCovariance,
  isPsd,
  isSymmetric,
  nearestPsd,
  solve,
  inverse,
  matVec,
  dot,
  quadForm,
  sumVec,
  scaleVec,
  symmetricEigenDecomposition,
} from "./linalg.js";

export {
  ANNUALIZATION_FACTORS,
  annualizationFactor,
  annualizeMean,
  annualizeStd,
  annualizeVariance,
  expectedReturns,
  sampleCovariance,
  stdDevs,
} from "./returns.js";

export { sharpeRatio } from "./sharpe.js";

export {
  capmRequiredReturn,
  capmTotalExpectedReturn,
  capmSystematicVariance,
  capmTotalVariance,
  capmTotalStdDev,
} from "./capm.js";

export { CLAMP_FIRM_VAR_TOL, singleIndexMetrics, type SingleIndexFit } from "./sim.js";

export {
  SUM_TOL as MARKOWITZ_SUM_TOL,
  optimizeMarkowitz,
  type OptimizeMarkowitzInput,
} from "./markowitz.js";

export {
  minimumVariancePortfolio,
  type MinimumVarianceInput,
} from "./minvar.js";

export {
  utilityMaxAllocation,
  type UtilityMaxAllocationInput,
} from "./allocation.js";

export {
  DISCRIMINANT_TOL,
  efficientFrontierPoints,
  calPoints,
  type EfficientFrontierInput,
  type CALPointsInput,
} from "./frontier.js";

export {
  QuantError,
  OptimizerInfeasibleError,
  OptimizerNonPsdCovarianceError,
  InvalidRiskProfileError,
  InvalidReturnWindowError,
  InsufficientHistoryError,
  InternalError,
  ErrorCode,
  type ErrorDetails,
  type ErrorPayload,
} from "./errors.js";

export {
  ReturnFrequency,
  type Ticker,
  type StockMetrics,
  type MarketMetrics,
  type CovarianceMatrix,
  type RiskProfile,
  type FrontierPoint,
  type CALPoint,
  type ORP,
  type CompletePortfolio,
  type OptimizationResult,
} from "./types.js";

export const VERSION = "0.1.0";
