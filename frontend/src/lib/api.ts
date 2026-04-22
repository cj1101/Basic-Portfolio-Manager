/**
 * Typed fetch client for the Portfolio Manager backend.
 *
 * Every route conforms to the universal error envelope defined in
 * `docs/CONTRACTS.md` §6. Non-2xx responses are converted into an `ApiError`
 * that carries the error `code` + `message` + optional `details` + HTTP
 * `status`. When the server emits a `Retry-After` header (see 429 responses
 * from the data layer) it is surfaced as `retryAfterSeconds`.
 *
 * The base URL defaults to `/api` so the Vite dev proxy can forward requests
 * to `http://localhost:8000`. Override via `VITE_API_BASE_URL` in production.
 */
import type {
  AnalyticsPerformanceRequest,
  AnalyticsPerformanceResult,
  ChatRequest,
  ChatResponse,
  ChatSessionResponse,
  ErrorCode,
  LLMDefaultResponse,
  LLMModelsResponse,
  UpdateApiKeyRequest,
  UpdateApiKeyResponse,
  OptimizationRequest,
  OptimizationResult,
  ValuationRequest,
  ValuationResult,
} from "@/types/contracts";

const DEFAULT_BASE = "/api";

/**
 * Resolves the `/api` prefix for requests. In dev, default `"/api"` is proxied by Vite.
 * When `VITE_API_BASE_URL` is an absolute origin (e.g. `http://localhost:8000`), we append
 * `/api` if missing so paths like `/optimize` hit `http://localhost:8000/api/optimize`, not
 * `.../optimize` (which 404s).
 */
function resolveBaseUrl(): string {
  const envBase = import.meta.env?.VITE_API_BASE_URL;
  if (typeof envBase === "string" && envBase.length > 0) {
    const trimmed = envBase.replace(/\/+$/, "");
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
    }
    return trimmed;
  }
  return DEFAULT_BASE;
}

export interface ApiErrorPayload {
  code: ErrorCode;
  message: string;
  details?: Record<string, unknown> | undefined;
  /** HTTP status code. */
  status: number;
  /** Parsed from `Retry-After` when present (seconds). */
  retryAfterSeconds?: number | undefined;
}

export class ApiError extends Error implements ApiErrorPayload {
  readonly code: ErrorCode;
  readonly status: number;
  readonly details: Record<string, unknown> | undefined;
  readonly retryAfterSeconds: number | undefined;

  constructor(payload: ApiErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.code = payload.code;
    this.status = payload.status;
    this.details = payload.details;
    this.retryAfterSeconds = payload.retryAfterSeconds;
  }
}

const JSON_CONTENT_TYPE = "application/json";

async function parseJsonSafely(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes(JSON_CONTENT_TYPE)) {
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function parseRetryAfter(header: string | null): number | undefined {
  if (!header) return undefined;
  const seconds = Number(header);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds;
  }
  // HTTP-date form is also allowed; best-effort parse it.
  const date = Date.parse(header);
  if (!Number.isNaN(date)) {
    const delta = (date - Date.now()) / 1000;
    return delta > 0 ? delta : 0;
  }
  return undefined;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const base = resolveBaseUrl();
  const url = path.startsWith("http") ? path : `${base}${path.startsWith("/") ? path : `/${path}`}`;

  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Accept")) headers.set("Accept", JSON_CONTENT_TYPE);
  if (init.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", JSON_CONTENT_TYPE);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch (cause) {
    throw new ApiError({
      code: "DATA_PROVIDER_UNAVAILABLE",
      message: cause instanceof Error ? cause.message : "Network request failed",
      status: 0,
    });
  }

  if (!response.ok) {
    const body = await parseJsonSafely(response);
    const envelope = (body && typeof body === "object" ? body : {}) as {
      code?: string;
      message?: string;
      details?: Record<string, unknown>;
    };
    throw new ApiError({
      code: (envelope.code as ErrorCode | undefined) ?? "INTERNAL",
      message:
        envelope.message ??
        `Request to ${url} failed with status ${response.status}`,
      details: envelope.details,
      status: response.status,
      retryAfterSeconds: parseRetryAfter(response.headers.get("Retry-After")),
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }
  const body = await parseJsonSafely(response);
  return body as T;
}

export function postOptimize(
  body: OptimizationRequest,
  init?: RequestInit,
): Promise<OptimizationResult> {
  return request<OptimizationResult>("/optimize", {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postAnalyticsPerformance(
  body: AnalyticsPerformanceRequest,
  init?: RequestInit,
): Promise<AnalyticsPerformanceResult> {
  return request<AnalyticsPerformanceResult>("/analytics/performance", {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function postValuation(
  body: ValuationRequest,
  init?: RequestInit,
): Promise<ValuationResult> {
  return request<ValuationResult>("/valuation", {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface RiskFreeRateResponse {
  rate: number;
  asOf: string;
  source: "FRED" | "FALLBACK";
}

export function getRiskFreeRate(init?: RequestInit): Promise<RiskFreeRateResponse> {
  return request<RiskFreeRateResponse>("/risk-free-rate", init);
}

/**
 * Chat (Agent E)
 * ----------------
 * Hybrid rule + LLM chat per CONTRACTS.md §5.9 / §5.11. Every function here
 * is a thin wrapper around `request<T>`; the frontend query layer is
 * responsible for caching and optimistic invalidation.
 */

export function postChat(body: ChatRequest, init?: RequestInit): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getChatSession(
  sessionId: string,
  init?: RequestInit,
): Promise<ChatSessionResponse> {
  return request<ChatSessionResponse>(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    init,
  );
}

export function postChatSessionMessage(
  sessionId: string,
  body: ChatRequest,
  init?: RequestInit,
): Promise<ChatResponse> {
  return request<ChatResponse>(
    `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      ...init,
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function deleteChatSession(
  sessionId: string,
  init?: RequestInit,
): Promise<void> {
  return request<void>(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    ...init,
    method: "DELETE",
  });
}

/**
 * LLM provider metadata (Agent E settings panel).
 *
 * The backend proxies OpenRouter's /models endpoint so the browser never
 * sees an API key. `getLlmDefault()` tells the UI whether the LLM toggle
 * should be enabled and which model is the pre-filled default.
 */

export function getLlmModels(init?: RequestInit): Promise<LLMModelsResponse> {
  return request<LLMModelsResponse>("/llm/models", init);
}

export function getLlmDefault(init?: RequestInit): Promise<LLMDefaultResponse> {
  return request<LLMDefaultResponse>("/llm/default", init);
}

export function patchApiKey(
  body: UpdateApiKeyRequest,
  init?: RequestInit,
): Promise<UpdateApiKeyResponse> {
  return request<UpdateApiKeyResponse>("/settings/api-keys", {
    ...init,
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
