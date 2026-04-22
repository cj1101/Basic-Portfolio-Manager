/**
 * UI tests for Agent E's ChatShell.
 *
 * These cover the interactions specified by the plan:
 *   - live send (rule-mode response renders bubble + citations)
 *   - mode toggle (Rule / LLM / Auto radio group)
 *   - citations rendering
 *   - LLM_UNAVAILABLE banner disables the LLM toggle
 *
 * The real `PortfolioProvider` is wrapped by `renderWithProviders` so the
 * shell binds to the fallback sample portfolio (no live /api/optimize call
 * required — we stub it anyway).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatShell } from "../src/components/chat/ChatShell";
import { optimizationResultSample } from "../src/fixtures/optimizationResultSample";
import type {
  ChatHistoryEntry,
  ChatResponse,
  ChatSessionResponse,
} from "../src/types/contracts";
import { renderWithProviders } from "./testUtils";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

interface ChatMockOptions {
  sendResponse?: ChatResponse | ((body: unknown) => ChatResponse);
  sendStatus?: number;
  sendError?: { code: string; message: string };
  history?: ChatSessionResponse;
}

function installChatFetchMock(options: ChatMockOptions = {}) {
  // Session history accumulates as turns are posted so the UI gets a
  // populated transcript after TanStack Query refetches.
  const historyMessages: ChatHistoryEntry[] = [
    ...(options.history?.messages ?? []),
  ];
  const sessionId = options.history?.sessionId ?? "test-session";

  const defaultSend: ChatResponse = {
    answer: "NVDA is overweight because its risk-adjusted return is high.",
    source: "rule",
    citations: [{ label: "NVDA weight", value: "0.28" }],
  };

  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (url.includes("/api/optimize")) {
      return json(optimizationResultSample);
    }
    if (url.includes("/api/risk-free-rate")) {
      return json({
        rate: 0.0523,
        asOf: "2024-11-20T00:00:00Z",
        source: "FRED",
      });
    }
    if (url.includes("/api/chat/sessions/") && url.includes("/messages")) {
      if (options.sendError) {
        return json(options.sendError, options.sendStatus ?? 503);
      }
      const body = init?.body ? JSON.parse(init.body as string) : null;
      const resolver = options.sendResponse ?? defaultSend;
      const response =
        typeof resolver === "function" ? resolver(body) : resolver;
      // Accumulate both the user turn and the assistant reply in the
      // mocked session store so subsequent GETs reflect the new history.
      const incoming = body as { messages?: Array<{ role: "user" | "assistant"; content: string }> } | null;
      const userTurn = incoming?.messages?.at(-1);
      const now = new Date().toISOString();
      if (userTurn) {
        historyMessages.push({
          role: userTurn.role,
          content: userTurn.content,
          citations: [],
          createdAt: now,
        });
      }
      historyMessages.push({
        role: "assistant",
        content: response.answer,
        source: response.source,
        citations: response.citations,
        createdAt: now,
      });
      return json(response);
    }
    if (url.includes("/api/chat/sessions/") && init?.method === "DELETE") {
      historyMessages.length = 0;
      return new Response(null, { status: 204 });
    }
    if (url.includes("/api/chat/sessions/")) {
      return json({ sessionId, messages: historyMessages });
    }
    if (url.includes("/api/chat")) {
      const body = init?.body ? JSON.parse(init.body as string) : null;
      const resolver = options.sendResponse ?? defaultSend;
      const response =
        typeof resolver === "function" ? resolver(body) : resolver;
      return json(response);
    }
    return json({ code: "INTERNAL", message: `unmocked: ${url}` }, 404);
  });

  (globalThis as { fetch: typeof fetch }).fetch = fn as unknown as typeof fetch;
  return fn;
}

async function openChatPanel(): Promise<void> {
  const user = userEvent.setup();
  const toggle = await screen.findByRole("button", {
    name: /ask the portfolio manager/i,
  });
  await user.click(toggle);
}

describe("ChatShell", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("sends a message and renders the assistant reply with citations", async () => {
    const fetchMock = installChatFetchMock();
    renderWithProviders(<ChatShell />);
    await openChatPanel();

    const user = userEvent.setup();
    const input = screen.getByRole("textbox", {
      name: /ask a question about your portfolio/i,
    });
    await user.type(input, "Why is NVDA overweight?");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() =>
      expect(
        screen.getByText(/NVDA is overweight because/i),
      ).toBeInTheDocument(),
    );

    // The citation chip renders inside a <ul aria-label="Citations">.
    const citations = await screen.findByLabelText(/citations/i);
    expect(within(citations).getByText(/NVDA weight/i)).toBeInTheDocument();
    expect(within(citations).getByText(/0\.28/)).toBeInTheDocument();

    // The POST body carried the live sessionId + mode=auto + stripped context.
    const sendCall = fetchMock.mock.calls.find(([url, init]) => {
      const u = typeof url === "string" ? url : String(url);
      return (
        u.includes("/api/chat/sessions/") &&
        u.includes("/messages") &&
        (init as RequestInit | undefined)?.method === "POST"
      );
    });
    expect(sendCall).toBeDefined();
    const sentBody = JSON.parse(
      (sendCall![1] as RequestInit).body as string,
    ) as {
      mode: string;
      sessionId: string;
      messages: Array<{ role: string; content: string }>;
      portfolioContext: { complete: Record<string, unknown> };
    };
    expect(sentBody.mode).toBe("auto");
    expect(sentBody.sessionId).toMatch(/.+/);
    expect(sentBody.messages.at(-1)).toEqual({
      role: "user",
      content: "Why is NVDA overweight?",
    });
    // The client-derived extras on `complete` must not be on the wire.
    expect(sentBody.portfolioContext.complete).not.toHaveProperty(
      "targetReturnOverride",
    );
    expect(sentBody.portfolioContext.complete).not.toHaveProperty("yUtility");
  }, 15000);

  it("switches the mode toggle to LLM and sends mode=llm", async () => {
    const fetchMock = installChatFetchMock({
      sendResponse: {
        answer: "From the LLM: diversification helps.",
        source: "llm",
        citations: [],
      },
    });
    renderWithProviders(<ChatShell />);
    await openChatPanel();

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /^llm$/i }));

    const input = screen.getByRole("textbox", {
      name: /ask a question about your portfolio/i,
    });
    await user.type(input, "Tell me about diversification");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() =>
      expect(screen.getByText(/From the LLM:/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/via llm/i)).toBeInTheDocument();

    const sendCall = fetchMock.mock.calls.find(([url, init]) => {
      const u = typeof url === "string" ? url : String(url);
      return (
        u.includes("/messages") &&
        (init as RequestInit | undefined)?.method === "POST"
      );
    });
    const sentBody = JSON.parse(
      (sendCall![1] as RequestInit).body as string,
    ) as { mode: string };
    expect(sentBody.mode).toBe("llm");
  }, 15000);

  it("shows the LLM_UNAVAILABLE banner and disables the LLM radio on 503", async () => {
    installChatFetchMock({
      sendError: {
        code: "LLM_UNAVAILABLE",
        message: "OpenAI is unreachable",
      },
      sendStatus: 503,
    });
    renderWithProviders(<ChatShell />);
    await openChatPanel();

    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /^llm$/i }));

    const input = screen.getByRole("textbox", {
      name: /ask a question about your portfolio/i,
    });
    await user.type(input, "hello?");
    await user.click(screen.getByRole("button", { name: /send message/i }));

    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(/LLM unavailable/i);

    // The radio for LLM should now be disabled; and the shell should have
    // flipped the active mode back to Auto.
    const llmRadio = screen.getByRole("radio", { name: /^llm$/i }) as HTMLInputElement;
    expect(llmRadio.disabled).toBe(true);
    const autoRadio = screen.getByRole("radio", { name: /^auto$/i }) as HTMLInputElement;
    expect(autoRadio.checked).toBe(true);
  }, 15000);
});
