/**
 * Single source of truth for domain types on the frontend.
 *
 * Transcribed verbatim from `docs/CONTRACTS.md`. The only place these types
 * should be declared on the frontend — every component imports from here.
 *
 * Do NOT add fields here. If a shape needs to change, update `docs/CONTRACTS.md`
 * first and then mirror the change here in the same PR.
 */

// ---------------------------------------------------------------------------
// 2. Enumerations
// ---------------------------------------------------------------------------

export type ReturnFrequency = "daily" | "weekly" | "monthly";

export type ErrorCode =
  | "UNKNOWN_TICKER"
  | "INSUFFICIENT_HISTORY"
  | "DATA_PROVIDER_RATE_LIMIT"
  | "DATA_PROVIDER_UNAVAILABLE"
  | "OPTIMIZER_INFEASIBLE"
  | "OPTIMIZER_NON_PSD_COVARIANCE"
  | "INVALID_RISK_PROFILE"
  | "INVALID_RETURN_WINDOW"
  | "LLM_UNAVAILABLE"
  | "INVALID_VALUATION"
  | "INVALID_SETTINGS"
  | "INTERNAL";

export type ChatSource = "rule" | "llm";

export type ChatMode = "auto" | "rule" | "llm";

// ---------------------------------------------------------------------------
// 3. Domain types
// ---------------------------------------------------------------------------

export type Ticker = string;

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoricalResponse {
  ticker: Ticker;
  frequency: ReturnFrequency;
  bars: PriceBar[];
}

export interface Quote {
  ticker: Ticker;
  price: number;
  asOf: string;
}

export interface StockMetrics {
  ticker: Ticker;
  expectedReturn: number;
  stdDev: number;
  beta: number;
  alpha: number;
  firmSpecificVar: number;
  nObservations: number;
}

export interface MarketMetrics {
  expectedReturn: number;
  stdDev: number;
  variance: number;
}

export interface CovarianceMatrix {
  tickers: Ticker[];
  matrix: number[][];
}

export interface CorrelationMatrix {
  tickers: Ticker[];
  matrix: number[][];
}

export interface RiskProfile {
  riskAversion: number;
  targetReturn?: number | undefined;
}

export interface FrontierPoint {
  stdDev: number;
  expectedReturn: number;
}

export interface CALPoint {
  stdDev: number;
  expectedReturn: number;
  y: number;
}

export interface ORP {
  weights: Record<Ticker, number>;
  expectedReturn: number;
  stdDev: number;
  variance: number;
  sharpe: number;
}

export interface CompletePortfolio {
  yStar: number;
  weightRiskFree: number;
  weights: Record<Ticker, number>;
  expectedReturn: number;
  stdDev: number;
  leverageUsed: boolean;
}

export interface OptimizationResult {
  requestId: string;
  asOf: string;
  riskFreeRate: number;
  market: MarketMetrics;
  stocks: StockMetrics[];
  covariance: CovarianceMatrix;
  correlation: CorrelationMatrix;
  orp: ORP;
  complete: CompletePortfolio;
  frontierPoints: FrontierPoint[];
  calPoints: CALPoint[];
  warnings: string[];
}

export interface Portfolio {
  name: string;
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency?: ReturnFrequency | undefined;
  lookbackYears?: number | undefined;
  allowShort?: boolean | undefined;
  allowLeverage?: boolean | undefined;
}

export interface SavedPortfolio extends Portfolio {
  id: string;
  createdAt: string;
  updatedAt: string;
  lastResult?: OptimizationResult;
}

export interface EquityPoint {
  date: string;
  equity: number;
}

export interface BacktestResult {
  equityCurve: EquityPoint[];
  realizedReturn: number;
  realizedStdDev: number;
  realizedSharpe: number;
  maxDrawdown: number;
  rebalanceCount: number;
  comparedToSpy: EquityPoint;
}

export interface Drift {
  ticker: Ticker;
  targetWeight: number;
  currentWeight: number;
  drift: number;
}

export interface DriftReport {
  portfolioId: string;
  asOf: string;
  totalDrift: number;
  drifts: Drift[];
  needsRebalance: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatOptimizationInputs {
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency: ReturnFrequency;
  lookbackYears: number;
  allowShort: boolean;
  allowLeverage: boolean;
  useHistoricalAsOf: boolean;
  asOf?: string | undefined;
}

export interface TopHolding {
  ticker: Ticker;
  weight: number;
}

export interface PortfolioSnapshot {
  requestId?: string | undefined;
  asOf?: string | undefined;
  riskFreeRate?: number | undefined;
  orpExpectedReturn?: number | undefined;
  orpStdDev?: number | undefined;
  orpSharpe?: number | undefined;
  completeExpectedReturn?: number | undefined;
  completeStdDev?: number | undefined;
  yStar?: number | undefined;
  leverageUsed?: boolean | undefined;
  topHoldings: TopHolding[];
  warnings: string[];
}

export interface LoadedPanelAvailability {
  analytics: boolean;
  valuation: boolean;
  technical: boolean;
}

export interface LoadedPanelData {
  availability: LoadedPanelAvailability;
  analytics?: AnalyticsPerformanceResult | undefined;
  valuation?: ValuationResult | undefined;
  technicalSelectedTicker?: Ticker | undefined;
  technicalHistory?: Record<Ticker, HistoricalResponse> | undefined;
  technicalBenchmark?: HistoricalResponse | undefined;
}

export interface ChatContext {
  optimizationInputs: ChatOptimizationInputs;
  activeTab?: string | undefined;
  portfolioSnapshot?: PortfolioSnapshot | undefined;
  loadedPanelData?: LoadedPanelData | undefined;
}

export interface ChatRequest {
  messages: ChatMessage[];
  portfolioContext?: OptimizationResult | undefined;
  chatContext?: ChatContext | undefined;
  mode?: ChatMode | undefined;
  sessionId?: string | undefined;
  /** OpenRouter model slug (e.g. "google/gemma-4-31b-it"). */
  model?: string | undefined;
}

export interface LLMModelPricing {
  prompt?: string;
  completion?: string;
}

export interface LLMModel {
  id: string;
  name: string;
  contextLength?: number;
  pricing?: LLMModelPricing;
}

export interface LLMModelsResponse {
  models: LLMModel[];
  cached: boolean;
  fetchedAt: number;
}

export interface LLMDefaultResponse {
  llmAvailable: boolean;
  defaultModel: string;
  baseUrl: string;
}

export type ApiKeyName =
  | "OPENROUTER_API_KEY"
  | "ALPHA_VANTAGE_API_KEY"
  | "FRED_API_KEY";

export interface UpdateApiKeyRequest {
  keyName: ApiKeyName;
  newValue: string;
  confirmOverwrite?: boolean;
  confirmCreate?: boolean;
}

export interface UpdateApiKeyResponse {
  updated: boolean;
  created: boolean;
  restartRequired: boolean;
  requiresConfirmation: boolean;
  confirmationType?: "overwrite" | "create";
  message: string;
}

export interface ChatCitation {
  label: string;
  value: string;
  sourceType?: "context" | "tool" | "rule" | "llm" | undefined;
  toolName?: string | undefined;
  scope?: string | undefined;
  asOf?: string | undefined;
}

export interface ChatResponse {
  answer: string;
  source: ChatSource;
  citations: ChatCitation[];
  toolInvocations?: string[] | undefined;
}

export interface ChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
  source?: ChatSource;
  citations: ChatCitation[];
  createdAt: string;
}

export interface ChatSessionResponse {
  sessionId: string;
  portfolioId?: string | undefined;
  createdAt: string;
  updatedAt: string;
  messages: ChatHistoryEntry[];
}

// ---------------------------------------------------------------------------
// 4. Request / response envelopes
// ---------------------------------------------------------------------------

export interface OptimizationRequest {
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  allowShort?: boolean;
  allowLeverage?: boolean;
  alphaOverrides?: Record<Ticker, number>;
  frontierResolution?: number;
  /** YYYY-MM-DD; pins window end when set */
  asOf?: string;
}

export interface BacktestRequest {
  portfolio: Portfolio;
  startDate: string;
  endDate: string;
  rebalance?: "monthly" | "quarterly" | "yearly" | "none";
  initialEquity?: number;
}

export interface CompareRequest {
  portfolioIds: string[];
}

export interface HoldingPeriodMonthlyReturns {
  years: 3 | 5 | 10;
  nObservations: number;
  windowStart: string;
  windowEnd: string;
  arithmeticMeanMonthlyReturn: number;
  geometricMeanMonthlyReturn: number;
}

export interface ORPPerformanceMetrics {
  treynor: number;
  jensenAlpha: number;
  nObservations: number;
  totalVariance: number;
  systematicVariance: number;
  unsystematicVariance: number;
  simVarianceMismatch: number;
}

export interface CompletePerformanceMetrics {
  treynor: number;
  jensenAlpha: number;
  nObservations: number;
  totalVariance: number;
  systematicVariance: number;
  unsystematicVariance: number;
  simVarianceMismatch: number;
}

export interface FamaFrenchThreePerTicker {
  ticker: Ticker;
  betaMkt: number;
  betaSmb: number;
  betaHml: number;
  alpha: number;
  nObservations: number;
  expectedReturnFf3: number;
  expectedReturnCapm: number;
}

export interface AnalyticsPerformanceRequest {
  tickers: Ticker[];
  orpWeights: Record<Ticker, number>;
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  yStar?: number;
  weightRiskFree?: number;
  asOf?: string;
}

export interface AnalyticsPerformanceResult {
  asOf: string;
  windowStart: string;
  windowEnd: string;
  riskFreeRate: number;
  dataSource: string;
  orp: ORPPerformanceMetrics;
  complete?: CompletePerformanceMetrics;
  holding: HoldingPeriodMonthlyReturns[];
  famaFrench: FamaFrenchThreePerTicker[];
  market: MarketMetrics;
  warnings: string[];
}

export interface DdmTwoStageParams {
  g1: number;
  g2: number;
  nPeriods: number;
}

export interface ValuationRequest {
  tickers: Ticker[];
  /** ISO date; NYSE window end pins fundamentals and historical prices when set */
  asOf?: string;
  wacc?: number;
  fcffGrowth?: number;
  fcffTerminalGrowth?: number;
  costOfEquityOverride?: number;
  ddmGordonG?: number;
  ddmTwoStage?: DdmTwoStageParams;
}

export interface TickerValuationBlock {
  ticker: Ticker;
  fcff: number | null;
  fcfe: number | null;
  fcffValuePerShare: number | null;
  fcfeValuePerShare: number | null;
  ddmGordon: number | null;
  ddmTwoStage: number | null;
  costOfEquity: number;

  historicalGrowthRate?: number | null;
  sustainableGrowthRate?: number | null;
  roe?: number | null;

  grossMargin?: number | null;
  operatingMargin?: number | null;
  roa?: number | null;
  bookValuePerShare?: number | null;
  earningsPerShare?: number | null;
  cashFlowPerShare?: number | null;
  priceToBook?: number | null;
  priceToEarnings?: number | null;
  priceToCashFlow?: number | null;

  calculatedBeta?: number | null;
  historicalReturn?: number | null;
  historicalVolatility?: number | null;
  historicalPrices?: PriceBar[] | null;

  warnings: string[];
}

export interface ValuationResult {
  asOf: string;
  perTicker: TickerValuationBlock[];
  dataSource: string;
  warnings: string[];
}

export interface ExportRequest {
  tickers: Ticker[];
  riskProfile: RiskProfile;
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  allowShort?: boolean;
  allowLeverage?: boolean;
  asOf?: string;
  wacc?: number;
  fcffGrowth?: number;
  fcffTerminalGrowth?: number;
  costOfEquityOverride?: number;
  ddmGordonG?: number;
  ddmTwoStage?: DdmTwoStageParams;
}

// ---------------------------------------------------------------------------
// Error envelope
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown>;
}
