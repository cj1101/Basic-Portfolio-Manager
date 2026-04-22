/**
 * Shared Playwright helpers: an ``/api/*`` interceptor that stands in
 * for the FastAPI backend so e2e specs are hermetic.
 */
import type { Page, Route } from "@playwright/test";
import { optimizationResultSample } from "../../src/fixtures/optimizationResultSample";

export interface ApiMockOptions {
  /** Override the POST /api/optimize response. */
  optimize?: {
    status?: number;
    body?: unknown;
    headers?: Record<string, string>;
  };
  /** Override the chat send endpoint (POST /api/chat/sessions/:id/messages). */
  chatSend?: {
    status?: number;
    body?: unknown;
  };
  /** Force /api/llm/default.llmAvailable to ``false``. */
  llmUnavailable?: boolean;
}

export async function mockApi(page: Page, opts: ApiMockOptions = {}): Promise<void> {
  const chatHistory: Array<{
    role: "user" | "assistant";
    content: string;
    source?: "rule" | "llm";
    citations: Array<{ label: string; value: string }>;
    createdAt: string;
  }> = [];

  await page.route(/\/api\/.*/, async (route: Route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (url.includes("/api/optimize")) {
      const fulfillOpts: Parameters<Route["fulfill"]>[0] = {
        status: opts.optimize?.status ?? 200,
        contentType: "application/json",
        body: JSON.stringify(opts.optimize?.body ?? optimizationResultSample),
      };
      if (opts.optimize?.headers) {
        fulfillOpts.headers = opts.optimize.headers;
      }
      return route.fulfill(fulfillOpts);
    }

    if (url.includes("/api/risk-free-rate")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rate: 0.0523,
          asOf: "2024-11-20T00:00:00Z",
          source: "FRED",
        }),
      });
    }

    if (url.includes("/api/llm/models")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          models: [
            {
              id: "google/gemma-4-31b-it",
              name: "Gemma 4 31B IT",
              contextLength: 128000,
              pricing: { prompt: "0", completion: "0" },
            },
            {
              id: "anthropic/claude-3.5-sonnet",
              name: "Claude 3.5 Sonnet",
              contextLength: 200000,
              pricing: { prompt: "3", completion: "15" },
            },
          ],
          cached: false,
          fetchedAt: 0,
        }),
      });
    }

    if (url.includes("/api/llm/default")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          llmAvailable: !opts.llmUnavailable,
          defaultModel: "google/gemma-4-31b-it",
          baseUrl: "https://openrouter.ai/api/v1",
        }),
      });
    }

    if (/\/api\/chat\/sessions\/[^/]+\/messages/.test(url) && method === "POST") {
      const status = opts.chatSend?.status ?? 200;
      if (status !== 200) {
        return route.fulfill({
          status,
          contentType: "application/json",
          body: JSON.stringify(
            opts.chatSend?.body ?? {
              code: "LLM_UNAVAILABLE",
              message: "LLM is down",
              details: { reason: "rate_limit" },
            },
          ),
        });
      }
      const reqBody = JSON.parse(route.request().postData() ?? "{}") as {
        messages?: Array<{ role: "user" | "assistant"; content: string }>;
      };
      const userTurn = reqBody.messages?.at(-1);
      const now = new Date().toISOString();
      if (userTurn) {
        chatHistory.push({
          role: userTurn.role,
          content: userTurn.content,
          citations: [],
          createdAt: now,
        });
      }
      const reply = {
        answer:
          "Your Sharpe ratio is 0.82 — computed from the ORP's expected excess return over its std dev.",
        source: "rule" as const,
        citations: [{ label: "ORP Sharpe", value: "0.8235" }],
      };
      chatHistory.push({
        role: "assistant",
        content: reply.answer,
        source: reply.source,
        citations: reply.citations,
        createdAt: now,
      });
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(reply),
      });
    }

    if (/\/api\/chat\/sessions\/[^/]+/.test(url) && method === "DELETE") {
      chatHistory.length = 0;
      return route.fulfill({ status: 204, body: "" });
    }

    if (/\/api\/chat\/sessions\/[^/]+/.test(url) && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sessionId: url.split("/").pop(),
          messages: chatHistory,
        }),
      });
    }

    if (url.includes("/api/chat") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          answer: "(stub)",
          source: "rule",
          citations: [],
        }),
      });
    }

    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        code: "INTERNAL",
        message: `unmocked: ${method} ${url}`,
      }),
    });
  });
}
