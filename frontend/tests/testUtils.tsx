import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";
import { PortfolioProvider } from "../src/state/portfolioContext";
import { optimizationResultSample } from "../src/fixtures/optimizationResultSample";
import type { OptimizationResult } from "../src/types/contracts";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
) {
  const queryClient = options.queryClient ?? createTestQueryClient();
  function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>
        <PortfolioProvider>{children}</PortfolioProvider>
      </QueryClientProvider>
    );
  }
  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) };
}

export interface MockFetchOptions {
  optimizeBody?: OptimizationResult;
  optimizeStatus?: number;
  optimizeHeaders?: Record<string, string>;
  optimizeErrorBody?: { code: string; message: string; details?: Record<string, unknown> };
  riskFreeRate?: { rate: number; asOf: string; source: "FRED" | "FALLBACK" };
}

/**
 * Install a `global.fetch` stub that serves `/api/optimize` from the sample
 * fixture (or a custom body) and `/api/risk-free-rate` from a canned payload.
 *
 * Returns a `vi.fn()` so callers can assert on call counts / arguments.
 */
export function installFetchMock(options: MockFetchOptions = {}) {
  const body = options.optimizeBody ?? optimizationResultSample;
  const rfr =
    options.riskFreeRate ?? { rate: 0.0523, asOf: "2024-11-20T00:00:00Z", source: "FRED" as const };

  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/api/optimize")) {
      if (options.optimizeErrorBody) {
        return new Response(JSON.stringify(options.optimizeErrorBody), {
          status: options.optimizeStatus ?? 400,
          headers: { "content-type": "application/json", ...(options.optimizeHeaders ?? {}) },
        });
      }
      return new Response(JSON.stringify(body), {
        status: options.optimizeStatus ?? 200,
        headers: { "content-type": "application/json", ...(options.optimizeHeaders ?? {}) },
      });
    }
    if (url.includes("/api/risk-free-rate")) {
      return new Response(JSON.stringify(rfr), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    // Fall through — unrecognised endpoint.
    return new Response(JSON.stringify({ code: "INTERNAL", message: `unmocked: ${url}` }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
    void init;
  });

  (globalThis as { fetch: typeof fetch }).fetch = fn as unknown as typeof fetch;
  return fn;
}
