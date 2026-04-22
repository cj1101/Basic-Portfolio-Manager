/**
 * Frontend error-banner matrix.
 *
 * For every error code the backend can surface on /api/optimize, the
 * `ResultBoundary` wrapper must render the right title + body copy and a
 * retry button. We drive the mocked fetch through `installFetchMock`'s
 * `optimizeErrorBody` knob and render a tiny subtree that pairs the real
 * ``PortfolioProvider`` with a `ResultBoundary`-wrapped success marker so
 * the boundary actually lights up.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultBoundary } from "../src/components/ui/ResultBoundary";
import type { ErrorCode } from "../src/types/contracts";
import { installFetchMock, renderWithProviders } from "./testUtils";

const WAIT = { timeout: 8000 } as const;

type ErrorCase = {
  code: ErrorCode;
  status: number;
  titleRegex: RegExp;
  /** Matches a substring that must appear in the rendered body copy. */
  bodyRegex: RegExp;
  extraHeaders?: Record<string, string>;
};

const CASES: ErrorCase[] = [
  {
    code: "UNKNOWN_TICKER",
    status: 404,
    titleRegex: /not recognized/i,
    bodyRegex: /alpha vantage/i,
  },
  {
    code: "INSUFFICIENT_HISTORY",
    status: 422,
    titleRegex: /not enough history/i,
    bodyRegex: /overlapping/i,
  },
  {
    code: "DATA_PROVIDER_RATE_LIMIT",
    status: 429,
    titleRegex: /rate-limited/i,
    bodyRegex: /rate-limiting/i,
    extraHeaders: { "Retry-After": "30" },
  },
  {
    code: "DATA_PROVIDER_UNAVAILABLE",
    status: 503,
    titleRegex: /provider unavailable/i,
    bodyRegex: /alpha vantage/i,
  },
  {
    code: "OPTIMIZER_INFEASIBLE",
    status: 422,
    titleRegex: /infeasible/i,
    bodyRegex: /optimizer/i,
  },
  {
    code: "OPTIMIZER_NON_PSD_COVARIANCE",
    status: 500,
    titleRegex: /covariance/i,
    bodyRegex: /positive semi-definite/i,
  },
  {
    code: "INVALID_RISK_PROFILE",
    status: 422,
    titleRegex: /risk profile/i,
    bodyRegex: /shorting the orp/i,
  },
  {
    code: "INVALID_RETURN_WINDOW",
    status: 400,
    titleRegex: /invalid request/i,
    bodyRegex: /lookback/i,
  },
  {
    code: "INTERNAL",
    status: 500,
    titleRegex: /something went wrong/i,
    // The INTERNAL body falls through to the server message when it's set.
    bodyRegex: /invalid lookback window/i,
  },
];


describe("ResultBoundary error banner matrix", () => {
  let fetchMock: ReturnType<typeof installFetchMock>;

  afterEach(() => {
    fetchMock?.mockReset();
    vi.restoreAllMocks();
  });

  for (const { code, status, titleRegex, bodyRegex, extraHeaders } of CASES) {
    it(`renders the ${code} banner on HTTP ${status}`, async () => {
      fetchMock = installFetchMock({
        optimizeStatus: status,
        optimizeErrorBody: {
          code,
          message: "Invalid lookback window",
          details: code === "UNKNOWN_TICKER" ? { ticker: "ZZZZ" } : {},
        },
        ...(extraHeaders ? { optimizeHeaders: extraHeaders } : {}),
      });

      renderWithProviders(
        <ResultBoundary>
          <div>body ok</div>
        </ResultBoundary>,
      );

      const alert = await screen.findByRole("alert", {}, WAIT);
      expect(alert).toHaveTextContent(titleRegex);
      expect(alert).toHaveTextContent(bodyRegex);
      expect(alert).toHaveTextContent(code);

      // Retry button renders with the correct status and is clickable.
      const retry = screen.getByRole("button", { name: /retry/i });
      expect(retry).not.toBeDisabled();
    }, 12000);
  }

  it("surfaces Retry-After seconds for DATA_PROVIDER_RATE_LIMIT", async () => {
    fetchMock = installFetchMock({
      optimizeStatus: 429,
      optimizeErrorBody: {
        code: "DATA_PROVIDER_RATE_LIMIT",
        message: "rate limited",
        details: { retryAfterSeconds: 45 },
      },
      optimizeHeaders: { "Retry-After": "45" },
    });

    renderWithProviders(
      <ResultBoundary>
        <div>body ok</div>
      </ResultBoundary>,
    );

    const alert = await screen.findByRole("alert", {}, WAIT);
    expect(alert).toHaveTextContent(/~45s/);
  }, 12000);

  it("retry button refetches /api/optimize", async () => {
    fetchMock = installFetchMock({
      optimizeStatus: 503,
      optimizeErrorBody: {
        code: "DATA_PROVIDER_UNAVAILABLE",
        message: "down",
      },
    });

    renderWithProviders(
      <ResultBoundary>
        <div>body ok</div>
      </ResultBoundary>,
    );

    await screen.findByRole("alert", {}, WAIT);
    const before = fetchMock.mock.calls.filter(([u]) =>
      typeof u === "string" ? u.includes("/api/optimize") : false,
    ).length;

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /retry/i }));

    await waitFor(() => {
      const after = fetchMock.mock.calls.filter(([u]) =>
        typeof u === "string" ? u.includes("/api/optimize") : false,
      ).length;
      expect(after).toBeGreaterThan(before);
    }, WAIT);
  }, 12000);
});


describe("LLM_UNAVAILABLE is not a portfolio-level banner", () => {
  /**
   * The chat shell owns the `LLM_UNAVAILABLE` banner (tested in chat.test.tsx);
   * `ResultBoundary` should still recognise the code so the fallback mapping
   * is complete, which we verify by running the code path in isolation.
   */
  it("covers the LLM_UNAVAILABLE branch of the describe() mapping", async () => {
    const fetchMock = installFetchMock({
      optimizeStatus: 503,
      optimizeErrorBody: {
        code: "LLM_UNAVAILABLE",
        message: "LLM down",
      },
    });

    renderWithProviders(
      <ResultBoundary>
        <div>body ok</div>
      </ResultBoundary>,
    );

    const alert = await screen.findByRole("alert", {}, WAIT);
    expect(alert).toHaveTextContent(/temporarily unavailable/i);
    fetchMock.mockReset();
  }, 12000);
});
