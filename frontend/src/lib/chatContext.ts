import type {
  ChatContext,
  ChatOptimizationInputs,
  HistoricalResponse,
  LoadedPanelData,
  OptimizationResult,
  PortfolioSnapshot,
  ReturnFrequency,
  RiskProfile,
  Ticker,
} from "@/types/contracts";

export interface ChatContextBuilderInput {
  tickers: Ticker[];
  returnFrequency: ReturnFrequency;
  lookbackYears: number;
  allowShort: boolean;
  allowLeverage: boolean;
  riskProfile: RiskProfile;
  useHistoricalAsOf: boolean;
  asOfDate: string;
  activeTab?: string | undefined;
  result?: OptimizationResult | null | undefined;
  loadedPanelData?: LoadedPanelData | undefined;
}

export function buildPortfolioSnapshot(
  result: OptimizationResult | null | undefined,
): PortfolioSnapshot | undefined {
  if (!result) return undefined;
  const topHoldings = Object.entries(result.orp.weights)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([ticker, weight]) => ({ ticker, weight }));
  return {
    requestId: result.requestId,
    asOf: result.asOf,
    riskFreeRate: result.riskFreeRate,
    orpExpectedReturn: result.orp.expectedReturn,
    orpStdDev: result.orp.stdDev,
    orpSharpe: result.orp.sharpe,
    completeExpectedReturn: result.complete.expectedReturn,
    completeStdDev: result.complete.stdDev,
    yStar: result.complete.yStar,
    leverageUsed: result.complete.leverageUsed,
    topHoldings,
    warnings: [...(result.warnings ?? [])],
  };
}

export function buildChatOptimizationInputs(
  input: Omit<ChatContextBuilderInput, "activeTab" | "result" | "loadedPanelData">,
): ChatOptimizationInputs {
  return {
    tickers: [...input.tickers],
    riskProfile: input.riskProfile,
    returnFrequency: input.returnFrequency,
    lookbackYears: input.lookbackYears,
    allowShort: input.allowShort,
    allowLeverage: input.allowLeverage,
    useHistoricalAsOf: input.useHistoricalAsOf,
    ...(input.useHistoricalAsOf && input.asOfDate ? { asOf: input.asOfDate } : {}),
  };
}

export function buildChatContext(input: ChatContextBuilderInput): ChatContext {
  return {
    optimizationInputs: buildChatOptimizationInputs(input),
    ...(input.activeTab ? { activeTab: input.activeTab } : {}),
    ...(input.result ? { portfolioSnapshot: buildPortfolioSnapshot(input.result) } : {}),
    ...(input.loadedPanelData ? { loadedPanelData: sanitizeLoadedPanelData(input.loadedPanelData) } : {}),
  };
}

function sanitizeLoadedPanelData(data: LoadedPanelData): LoadedPanelData {
  return {
    availability: { ...data.availability },
    ...(data.analytics ? { analytics: data.analytics } : {}),
    ...(data.valuation ? { valuation: data.valuation } : {}),
    ...(data.technicalSelectedTicker ? { technicalSelectedTicker: data.technicalSelectedTicker } : {}),
    ...(data.technicalHistory ? { technicalHistory: sanitizeHistoryMap(data.technicalHistory) } : {}),
    ...(data.technicalBenchmark ? { technicalBenchmark: sanitizeHistorical(data.technicalBenchmark) } : {}),
  };
}

function sanitizeHistoryMap(history: Record<string, HistoricalResponse>): Record<string, HistoricalResponse> {
  return Object.fromEntries(
    Object.entries(history).map(([ticker, response]) => [ticker, sanitizeHistorical(response)]),
  );
}

function sanitizeHistorical(response: HistoricalResponse): HistoricalResponse {
  return {
    ticker: response.ticker,
    frequency: response.frequency,
    bars: response.bars.map((bar) => ({
      date: bar.date,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    })),
  };
}
