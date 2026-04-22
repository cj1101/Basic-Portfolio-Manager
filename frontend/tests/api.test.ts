import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  deleteChatSession,
  getChatSession,
  postChat,
  postChatSessionMessage,
  postOptimize,
} from "../src/lib/api";
import type { ChatRequest, OptimizationRequest } from "../src/types/contracts";

function mockResponse(body: unknown, init: ResponseInit = {}) {
  const headers = new Headers({ "content-type": "application/json" });
  for (const [k, v] of Object.entries(init.headers ?? {})) headers.set(k, v);
  return new Response(JSON.stringify(body), { ...init, headers });
}

const baseRequest: OptimizationRequest = {
  tickers: ["AAPL", "MSFT"],
  riskProfile: { riskAversion: 3 },
  returnFrequency: "daily",
  lookbackYears: 5,
  allowShort: true,
  allowLeverage: true,
  frontierResolution: 20,
};

describe("api.ts error envelope parsing", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a parsed body on 2xx", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse({ requestId: "opt_x" }),
    );
    const res = await postOptimize(baseRequest);
    expect((res as { requestId: string }).requestId).toBe("opt_x");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/optimize"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws ApiError with typed code + status on 4xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse(
        {
          code: "UNKNOWN_TICKER",
          message: "Unknown ticker: ZZZ",
          details: { ticker: "ZZZ" },
        },
        { status: 404 },
      ),
    );

    await expect(postOptimize(baseRequest)).rejects.toMatchObject({
      name: "ApiError",
      code: "UNKNOWN_TICKER",
      status: 404,
      details: { ticker: "ZZZ" },
      message: "Unknown ticker: ZZZ",
    });
  });

  it("parses Retry-After numeric seconds on 429", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse(
        { code: "DATA_PROVIDER_RATE_LIMIT", message: "rate limited" },
        { status: 429, headers: { "Retry-After": "42" } },
      ),
    );

    try {
      await postOptimize(baseRequest);
      throw new Error("expected ApiError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const e = err as ApiError;
      expect(e.code).toBe("DATA_PROVIDER_RATE_LIMIT");
      expect(e.retryAfterSeconds).toBe(42);
    }
  });

  it("falls back to INTERNAL + generic message on non-JSON errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("<html>oops</html>", {
        status: 500,
        headers: { "content-type": "text/html" },
      }),
    );

    await expect(postOptimize(baseRequest)).rejects.toMatchObject({
      name: "ApiError",
      code: "INTERNAL",
      status: 500,
    });
  });

  it("wraps fetch network errors as DATA_PROVIDER_UNAVAILABLE", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Network down"));

    await expect(postOptimize(baseRequest)).rejects.toMatchObject({
      name: "ApiError",
      code: "DATA_PROVIDER_UNAVAILABLE",
      status: 0,
      message: "Network down",
    });
  });
});

const baseChatRequest: ChatRequest = {
  messages: [{ role: "user", content: "why is NVDA overweight?" }],
  mode: "auto",
  sessionId: "sess-abc",
};

describe("api.ts chat endpoints", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs /api/chat and returns the parsed response", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse({
        answer: "NVDA is overweight because…",
        source: "rule",
        citations: [{ label: "NVDA weight", value: "0.25" }],
      }),
    );

    const res = await postChat(baseChatRequest);
    expect(res.source).toBe("rule");
    expect(res.citations).toHaveLength(1);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/api/chat");
    expect((init as RequestInit).method).toBe("POST");
  });

  it("maps 503 LLM_UNAVAILABLE to a typed ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse(
        { code: "LLM_UNAVAILABLE", message: "OpenAI is unreachable" },
        { status: 503 },
      ),
    );

    try {
      await postChat(baseChatRequest);
      throw new Error("expected ApiError");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const e = err as ApiError;
      expect(e.code).toBe("LLM_UNAVAILABLE");
      expect(e.status).toBe(503);
    }
  });

  it("GETs a chat session by id", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse({
        sessionId: "sess-abc",
        messages: [],
      }),
    );

    const res = await getChatSession("sess-abc");
    expect(res.sessionId).toBe("sess-abc");
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/api/chat/sessions/sess-abc");
    // Default method on GET is undefined (== GET), or explicitly undefined.
    expect((init as RequestInit).method ?? "GET").toBe("GET");
  });

  it("POSTs to /api/chat/sessions/:id/messages", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      mockResponse({ answer: "ok", source: "rule", citations: [] }),
    );

    await postChatSessionMessage("sess-abc", baseChatRequest);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain("/api/chat/sessions/sess-abc/messages");
    expect((init as RequestInit).method).toBe("POST");
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      sessionId: "sess-abc",
    });
  });

  it("URL-encodes the session id on DELETE", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(null, { status: 204 }),
    );

    await deleteChatSession("weird id/with slash");
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain(
      "/api/chat/sessions/weird%20id%2Fwith%20slash",
    );
    expect((init as RequestInit).method).toBe("DELETE");
  });
});
