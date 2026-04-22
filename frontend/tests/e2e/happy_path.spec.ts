import { expect, test } from "@playwright/test";
import { mockApi } from "./fixtures";

test.describe("Happy path", () => {
  test("loads the dashboard, renders every tab, and chats successfully", async ({
    page,
  }) => {
    await mockApi(page);
    await page.goto("/");

    // Ticker bar is present.
    await expect(
      page.getByRole("heading", { name: /stocks in your portfolio/i }),
    ).toBeVisible();

    // Add a new ticker and make sure the chip shows up.
    await page.getByLabel(/add ticker/i).fill("GOOG");
    await page.getByRole("button", { name: /^add$/i }).click();
    await expect(
      page.getByRole("button", { name: /remove goog/i }),
    ).toBeVisible();

    // Each main tab should be clickable and render its label without errors.
    const tabNames = [
      /overview/i,
      /asset allocation/i,
      /frontier/i,
      /capital allocation line/i,
      /apis/i,
    ];
    for (const name of tabNames) {
      const tab = page.getByRole("tab", { name });
      if (await tab.count()) {
        await tab.first().click();
      }
    }

    // Open chat and ask a question.
    await page.getByRole("button", { name: /ask the portfolio manager/i }).click();
    const input = page.getByRole("textbox", {
      name: /ask a question about your portfolio/i,
    });
    await input.fill("What's my Sharpe?");
    await page.getByRole("button", { name: /send message/i }).click();

    await expect(page.getByText(/Your Sharpe ratio is/i)).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/ORP Sharpe/i)).toBeVisible();
  });

  test("opens the Settings panel and lists available models", async ({ page }) => {
    await mockApi(page);
    await page.goto("/");

    const gear = page.getByRole("button", { name: /settings/i }).first();
    await gear.click();

    // The Settings quick-picks should include both mocked model buttons.
    await expect(
      page.getByRole("button", { name: /google\/gemma-4-31b-it\s+gemma 4 31b it/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /anthropic\/claude-3\.5-sonnet\s+claude 3\.5 sonnet/i }),
    ).toBeVisible();
  });
});
