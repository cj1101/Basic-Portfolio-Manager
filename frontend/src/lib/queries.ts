/**
 * TanStack Query hooks around the typed API client.
 *
 * The cache key for `useOptimization` intentionally includes *every* request
 * field so changing `lookbackYears` or `allowShort` invalidates the cached
 * result. The risk profile is part of the request body (the backend uses it
 * to compute `complete`) but the slider-driven re-derivation happens client
 * side — see `computeCompleteFromORP`. We keep `riskAversion` out of the key
 * so flipping it only updates the Complete Portfolio, not the ORP.
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type {
  OptimizationRequest,
  OptimizationResult,
} from "@/types/contracts";
import {
  ApiError,
  getRiskFreeRate,
  postOptimize,
  type RiskFreeRateResponse,
} from "./api";

/**
 * Which error codes are not worth retrying automatically (user input
 * problems — retrying won't help).
 */
const NON_RETRIABLE_CODES = new Set<string>([
  "UNKNOWN_TICKER",
  "INSUFFICIENT_HISTORY",
  "INVALID_RISK_PROFILE",
  "INVALID_RETURN_WINDOW",
  "OPTIMIZER_INFEASIBLE",
]);

export interface OptimizationQueryKeyInput {
  tickers: string[];
  returnFrequency: OptimizationRequest["returnFrequency"];
  lookbackYears: OptimizationRequest["lookbackYears"];
  allowShort: OptimizationRequest["allowShort"];
  allowLeverage: OptimizationRequest["allowLeverage"];
  frontierResolution: OptimizationRequest["frontierResolution"];
  alphaOverrides?: OptimizationRequest["alphaOverrides"];
}

export function optimizationQueryKey(input: OptimizationQueryKeyInput) {
  return [
    "optimize",
    {
      tickers: [...input.tickers],
      returnFrequency: input.returnFrequency,
      lookbackYears: input.lookbackYears,
      allowShort: input.allowShort,
      allowLeverage: input.allowLeverage,
      frontierResolution: input.frontierResolution,
      alphaOverrides: input.alphaOverrides,
    },
  ] as const;
}

/**
 * Risk profile (riskAversion + targetReturn) is intentionally excluded
 * from the query key: the client re-derives `complete` from the cached
 * ORP via `computeCompleteFromORP`, so slider moves don't invalidate the
 * cache. The risk profile is still sent in the request body for
 * completeness, but any slider-driven re-fetch would be pure duplication.
 */
export function useOptimization(
  request: OptimizationRequest,
  options: { enabled?: boolean } = {},
): UseQueryResult<OptimizationResult, ApiError> {
  const keyInput: OptimizationQueryKeyInput = {
    tickers: request.tickers,
    returnFrequency: request.returnFrequency,
    lookbackYears: request.lookbackYears,
    allowShort: request.allowShort,
    allowLeverage: request.allowLeverage,
    frontierResolution: request.frontierResolution,
    alphaOverrides: request.alphaOverrides,
  };
  return useQuery<OptimizationResult, ApiError>({
    queryKey: optimizationQueryKey(keyInput),
    queryFn: ({ signal }) => postOptimize(request, { signal }),
    enabled: options.enabled !== false && request.tickers.length >= 2,
    retry: (count, error) => {
      if (!(error instanceof ApiError)) return count < 1;
      if (NON_RETRIABLE_CODES.has(error.code)) return false;
      return count < 1;
    },
    staleTime: 60_000,
  });
}

export function useRiskFreeRate(): UseQueryResult<RiskFreeRateResponse, ApiError> {
  return useQuery<RiskFreeRateResponse, ApiError>({
    queryKey: ["risk-free-rate"],
    queryFn: ({ signal }) => getRiskFreeRate({ signal }),
    staleTime: 5 * 60_000,
    retry: 1,
  });
}
