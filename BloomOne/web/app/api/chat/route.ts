import { NextRequest } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/chat
 *
 * Proxies chat requests to the Modal backend's /v1/chat/stream SSE endpoint.
 * Keeps the API key server-side — never exposed to the browser.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const backendUrl = `${BLOOMONE_API_URL}/v1/chat/stream`;

    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      body: JSON.stringify(body),
    });

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
    console.error("Chat proxy error:", error);
    return new Response(
      JSON.stringify({
        error: "Failed to connect to BloomOne backend",
        details: error instanceof Error ? error.message : "Unknown error",
      }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
}
