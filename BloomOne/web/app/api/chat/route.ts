import { NextRequest } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/** Timeout for the initial connection to Modal (handles cold starts). */
const CONNECT_TIMEOUT_MS = 120_000; // 2 minutes

/**
 * POST /api/chat
 *
 * Proxies chat requests to the Modal backend's /v1/chat/stream SSE endpoint.
 * Keeps the API key server-side — never exposed to the browser.
 *
 * Uses a generous timeout to handle Modal cold starts (~10-30s).
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const backendUrl = `${BLOOMONE_API_URL}/v1/chat/stream`;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CONNECT_TIMEOUT_MS);

    let response: Response;
    try {
      response = await fetch(backendUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(BLOOMONE_API_KEY && {
            Authorization: `Bearer ${BLOOMONE_API_KEY}`,
          }),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(
        JSON.stringify({ error: `Backend error: ${response.status}`, details: errorText }),
        { status: response.status, headers: { "Content-Type": "application/json" } },
      );
    }

    // Stream the SSE response directly to the client
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    const isTimeout =
      error instanceof DOMException && error.name === "AbortError";
    const isNetwork =
      error instanceof TypeError && /fetch|network/i.test(error.message);

    console.error("Chat proxy error:", error);

    return new Response(
      JSON.stringify({
        error: isTimeout
          ? "Backend is starting up — please try again in a few seconds"
          : isNetwork
            ? "Could not reach the backend server"
            : "Failed to connect to BloomOne backend",
        details: error instanceof Error ? error.message : "Unknown error",
        retryable: isTimeout || isNetwork,
      }),
      {
        status: isTimeout ? 504 : 502,
        headers: { "Content-Type": "application/json" },
      },
    );
  }
}
