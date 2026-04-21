import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";
import { optimizationResultSample } from "../src/fixtures/optimizationResultSample";
import { installFetchMock, renderWithProviders } from "./testUtils";

const WAIT = { timeout: 8000 } as const;

function optimizeCallCount(fetchMock: ReturnType<typeof installFetchMock>): number {
  return fetchMock.mock.calls.filter(
    ([url]) => typeof url === "string" && url.includes("/api/optimize"),
  ).length;
}

/**
 * Integration tests that exercise the full optimize flow.
 *
 *   input change → debounce → /api/optimize → cache → ResultBoundary
 *
 * We use real timers to avoid the well-known userEvent + vi.fakeTimers
 * flakiness. The 400 ms debounce means every `waitFor` here is generous.
 */

describe("optimize flow", () => {
  let fetchMock: ReturnType<typeof installFetchMock>;

  beforeEach(() => {
    fetchMock = installFetchMock();
  });

  afterEach(() => {
    fetchMock.mockReset();
  });

  it("posts to /api/optimize on mount with the default ticker universe", async () => {
    renderWithProviders(<App />);

    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBeGreaterThanOrEqual(1), WAIT);

    const call = fetchMock.mock.calls.find(
      ([url]) => typeof url === "string" && url.includes("/api/optimize"),
    );
    const [, init] = call!;
    const initOpts = init as RequestInit;
    expect(initOpts.method).toBe("POST");
    const body = JSON.parse(initOpts.body as string);
    expect(Array.isArray(body.tickers)).toBe(true);
    expect(body.tickers.length).toBeGreaterThanOrEqual(2);
    expect(body.riskProfile).toMatchObject({ riskAversion: expect.any(Number) });
  }, 15000);

  it("triggers exactly one extra /api/optimize call after adding a ticker (debounced)", async () => {
    renderWithProviders(<App />);
    const user = userEvent.setup();

    // Wait for the initial mount request.
    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBeGreaterThanOrEqual(1), WAIT);
    const baseline = optimizeCallCount(fetchMock);

    const input = screen.getByLabelText(/add ticker/i);
    await user.type(input, "GOOG");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    // After debounce (~400ms) + fetch roundtrip we should see exactly one
    // additional POST — not one per keystroke.
    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBe(baseline + 1), WAIT);

    // Let any straggling debounces resolve, then assert no extra requests.
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(optimizeCallCount(fetchMock)).toBe(baseline + 1);
  }, 15000);

  it("moves the risk slider WITHOUT triggering a new network request", async () => {
    renderWithProviders(<App />);

    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBeGreaterThanOrEqual(1), WAIT);
    // Wait long enough that any debounced trailing request also lands.
    await new Promise((resolve) => setTimeout(resolve, 800));
    const baseline = optimizeCallCount(fetchMock);

    const slider = screen.getByRole("slider", { name: /risk aversion/i }) as HTMLInputElement;
    // jsdom doesn't implement arrow-key nudging on range inputs reliably;
    // drive the change synthetically.
    fireEvent.change(slider, { target: { value: "7" } });

    await waitFor(() =>
      expect(slider.getAttribute("aria-valuenow")).toBe("7"),
    );

    // Give effects a chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 800));
    expect(optimizeCallCount(fetchMock)).toBe(baseline);
  }, 15000);

  it("Re-optimize button calls /api/optimize again (refetch)", async () => {
    renderWithProviders(<App />);
    const user = userEvent.setup();

    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBeGreaterThanOrEqual(1), WAIT);
    await new Promise((resolve) => setTimeout(resolve, 300));
    const baseline = optimizeCallCount(fetchMock);

    await user.click(screen.getByRole("button", { name: /re-optimize the portfolio/i }));

    await waitFor(() => expect(optimizeCallCount(fetchMock)).toBe(baseline + 1), WAIT);
  }, 15000);

  it("renders warnings returned by the optimizer in the Data tab", async () => {
    fetchMock.mockReset();
    const mock = installFetchMock({
      optimizeBody: {
        ...optimizationResultSample,
        warnings: ["Using cached data from 2024-11-19"],
      },
    });

    renderWithProviders(<App />);
    const user = userEvent.setup();

    await waitFor(() => expect(optimizeCallCount(mock)).toBeGreaterThanOrEqual(1), WAIT);

    await user.click(screen.getByRole("tab", { name: /apis & data/i }));
    await waitFor(
      () =>
        expect(
          screen.getByText(/Using cached data from 2024-11-19/i),
        ).toBeInTheDocument(),
      WAIT,
    );
  }, 15000);
});
