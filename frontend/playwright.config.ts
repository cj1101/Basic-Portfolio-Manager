import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the Portfolio Manager frontend.
 *
 * - Boots Vite via ``pnpm run dev`` on port 5180 (non-default so it won't
 *   collide with a running local dev server).
 * - Every spec uses ``page.route`` to intercept ``/api/*`` calls so tests
 *   are hermetic and never touch a real backend.
 */

const PORT = 5180;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  timeout: 30_000,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `pnpm run dev -- --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
