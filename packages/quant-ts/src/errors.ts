/**
 * TypeScript mirror of `backend/quant/errors.py` and `docs/CONTRACTS.md` §2.
 *
 * `QuantError` is the base of every error thrown out of `@portfolio/quant`.
 * Each subclass carries its own `code` so callers can discriminate with
 * `instanceof` or inspect `.code`. The wire shape is
 * `{ code, message, details }` via `toErrorPayload()`.
 */

export const ErrorCode = {
  UnknownTicker: "UNKNOWN_TICKER",
  InsufficientHistory: "INSUFFICIENT_HISTORY",
  DataProviderRateLimit: "DATA_PROVIDER_RATE_LIMIT",
  DataProviderUnavailable: "DATA_PROVIDER_UNAVAILABLE",
  OptimizerInfeasible: "OPTIMIZER_INFEASIBLE",
  OptimizerNonPsdCovariance: "OPTIMIZER_NON_PSD_COVARIANCE",
  InvalidRiskProfile: "INVALID_RISK_PROFILE",
  InvalidReturnWindow: "INVALID_RETURN_WINDOW",
  LlmUnavailable: "LLM_UNAVAILABLE",
  Internal: "INTERNAL",
} as const;

export type ErrorCode = (typeof ErrorCode)[keyof typeof ErrorCode];

export type ErrorDetails = Record<string, unknown>;

export interface ErrorPayload {
  code: ErrorCode;
  message: string;
  details: ErrorDetails;
}

export class QuantError extends Error {
  public readonly code: ErrorCode;
  public readonly details: ErrorDetails;

  public constructor(code: ErrorCode, message: string, details?: ErrorDetails) {
    super(message);
    this.name = new.target.name;
    this.code = code;
    this.details = details ? { ...details } : {};
    Object.setPrototypeOf(this, new.target.prototype);
  }

  public toErrorPayload(): ErrorPayload {
    return { code: this.code, message: this.message, details: this.details };
  }
}

export class OptimizerInfeasibleError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.OptimizerInfeasible, message, details);
  }
}

export class OptimizerNonPsdCovarianceError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.OptimizerNonPsdCovariance, message, details);
  }
}

export class InvalidRiskProfileError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.InvalidRiskProfile, message, details);
  }
}

export class InvalidReturnWindowError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.InvalidReturnWindow, message, details);
  }
}

export class InsufficientHistoryError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.InsufficientHistory, message, details);
  }
}

export class InternalError extends QuantError {
  public constructor(message: string, details?: ErrorDetails) {
    super(ErrorCode.Internal, message, details);
  }
}
