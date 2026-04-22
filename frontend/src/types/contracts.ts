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

export interface RiskProfile {
  riskAversion: number;
  targetReturn?: number;
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
  returnFrequency?: ReturnFrequency;
  lookbackYears?: number;
  allowShort?: boolean;
  allowLeverage?: boolean;
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

export interface ChatRequest {
  messages: ChatMessage[];
  portfolioContext?: OptimizationResult;
  mode?: ChatMode;
  sessionId?: string;
  /** OpenRouter model slug (e.g. "google/gemma-4-31b-it"). */
  model?: string;
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

export interface ChatCitation {
  label: string;
  value: string;
}

export interface ChatResponse {
  answer: string;
  source: ChatSource;
  citations: ChatCitation[];
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
  portfolioId?: string;
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

// ---------------------------------------------------------------------------
// Error envelope
// ---------------------------------------------------------------------------

export interface ErrorResponse {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown>;
}
