import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CourseMetricsTab } from "./CourseMetricsTab";

const { postValuation } = vi.hoisted(() => ({
  postValuation: vi.fn(),
}));

vi.mock("@/state/portfolioContext", () => ({
  usePortfolio: () => ({
    optimizationRequest: {
      tickers: ["AAPL", "MSFT"],
      asOf: "2024-01-31",
      returnFrequency: "daily",
      lookbackYears: 5,
    },
    result: {
      orp: { weights: { AAPL: 0.5, MSFT: 0.5 } },
      complete: { yStar: 0.75, weightRiskFree: 0.25 },
    },
  }),
}));

vi.mock("@/lib/api", () => ({
  postAnalyticsPerformance: vi.fn(),
  postValuation,
  ApiError: class ApiError extends Error {
    status = 500;
    code = "INTERNAL";
  },
}));

describe("CourseMetricsTab", () => {
  it("posts valuation without frontend override defaults", async () => {
    postValuation.mockResolvedValueOnce({
      asOf: "2024-01-31T00:00:00Z",
      perTicker: [],
      dataSource: "mock",
      warnings: [],
    });

    render(<CourseMetricsTab />);

    fireEvent.click(screen.getByRole("button", { name: "Load valuation" }));

    await waitFor(() => expect(postValuation).toHaveBeenCalledTimes(1));

    const [payload] = postValuation.mock.calls[0]!;
    expect(payload).toEqual({
      tickers: ["AAPL", "MSFT"],
      asOf: "2024-01-31",
    });
    expect(payload).not.toHaveProperty("wacc");
    expect(payload).not.toHaveProperty("ddmGordonG");
    expect(payload).not.toHaveProperty("ddmTwoStage");
    expect(payload).not.toHaveProperty("fcffGrowth");
    expect(payload).not.toHaveProperty("fcffTerminalGrowth");
  });
});
