import { expect, test } from "@playwright/test";
import { mockApi } from "./fixtures";

test.describe("Error paths", () => {
  test("DATA_PROVIDER_RATE_LIMIT surfaces a 429 banner with retry copy", async ({
    page,
  }) => {
    await mockApi(page, {
      optimize: {
        status: 429,
        headers: { "Retry-After": "30" },
        body: {
          code: "DATA_PROVIDER_RATE_LIMIT",
          message: "rate limited",
          details: { retryAfterSeconds: 30 },
        },
      },
    });
    await page.goto("/");

    const alert = page.getByRole("alert").first();
    await expect(alert).toBeVisible({ timeout: 10_000 });
    await expect(alert).toContainText(/rate-limited/i);
    await expect(alert).toContainText(/DATA_PROVIDER_RATE_LIMIT/);
  });

  test("LLM_UNAVAILABLE in chat shows the rule-only fallback banner", async ({
    page,
  }) => {
    await mockApi(page, {
      chatSend: {
        status: 503,
        body: {
          code: "LLM_UNAVAILABLE",
          message: "LLM is down",
          details: { reason: "rate_limit" },
        },
      },
    });
    await page.goto("/");

    await page.getByRole("button", { name: /ask the portfolio manager/i }).click();

    // Force the mode to LLM so the send request trips the 503.
    await page.getByRole("radio", { name: /^llm$/i }).click();

    const input = page.getByRole("textbox", {
      name: /ask a question about your portfolio/i,
    });
    await input.fill("hello?");
    await page.getByRole("button", { name: /send message/i }).click();

    await expect(
      page.getByText(/LLM unavailable/i).first(),
    ).toBeVisible({ timeout: 10_000 });
    // The LLM radio should be disabled and mode auto-flips back to Auto.
    await expect(page.getByRole("radio", { name: /^llm$/i })).toBeDisabled();
    await expect(page.getByRole("radio", { name: /^auto$/i })).toBeChecked();
  });

  test("LLM unavailable on mount is reflected immediately via /api/llm/default", async ({
    page,
  }) => {
    await mockApi(page, { llmUnavailable: true });
    await page.goto("/");

    await page.getByRole("button", { name: /ask the portfolio manager/i }).click();

    // Banner + "Rule-only" chip should appear without the user sending a turn.
    await expect(page.getByText(/Rule-only/i)).toBeVisible({ timeout: 10_000 });
  });
});
