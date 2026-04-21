import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../src/App";
import { TABS } from "../src/components/Tabs";
import { installFetchMock, renderWithProviders } from "./testUtils";

const WAIT = { timeout: 5000 } as const;

describe("App", () => {
  let fetchMock: ReturnType<typeof installFetchMock>;

  beforeEach(() => {
    fetchMock = installFetchMock();
  });

  afterEach(() => {
    fetchMock.mockReset();
  });

  it("renders the header, risk controls, ticker bar, and default tab", async () => {
    renderWithProviders(<App />);

    expect(
      screen.getByRole("banner", { name: /portfolio manager report header/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /your risk profile/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /stocks in your portfolio/i }),
    ).toBeInTheDocument();
    await waitFor(
      () =>
        expect(
          screen.getByRole("heading", { name: /your complete portfolio/i }),
        ).toBeInTheDocument(),
      WAIT,
    );
  });

  it("renders every tab without errors", async () => {
    renderWithProviders(<App />);
    const user = userEvent.setup();

    await waitFor(() => expect(fetchMock).toHaveBeenCalled(), WAIT);

    for (const tab of TABS) {
      await user.click(screen.getByRole("tab", { name: tab.label }));
      const panel = document.getElementById(`panel-${tab.id}`);
      expect(panel).not.toBeNull();
      expect(panel?.hidden).toBe(false);
    }
  });

  it("adds a user-typed ticker and removes it", async () => {
    renderWithProviders(<App />);
    const user = userEvent.setup();

    const input = screen.getByLabelText(/add ticker/i);
    await user.type(input, "GOOG");
    await user.click(screen.getByRole("button", { name: /^add$/i }));

    expect(screen.getByText("GOOG")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /remove goog/i }));
    expect(screen.queryByText("GOOG")).not.toBeInTheDocument();
  });

  it("renders the risk aversion slider at default A = 3", () => {
    renderWithProviders(<App />);
    const slider = screen.getByRole("slider", { name: /risk aversion/i });
    expect(slider).toHaveAttribute("aria-valuenow", "3");
  });

  it("shows an error banner with code and retry button when optimize returns 429", async () => {
    fetchMock.mockReset();
    installFetchMock({
      optimizeStatus: 429,
      optimizeHeaders: { "Retry-After": "30" },
      optimizeErrorBody: {
        code: "DATA_PROVIDER_RATE_LIMIT",
        message: "Alpha Vantage rate limit exceeded",
      },
    });

    renderWithProviders(<App />);

    await waitFor(
      () =>
        expect(screen.getByRole("alert")).toHaveTextContent(
          /DATA_PROVIDER_RATE_LIMIT/,
        ),
      { timeout: 8000 },
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  }, 15000);
});
