import { NextRequest } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * GET /api/warmup
 *
 * Pings the Modal backend's /v1/health endpoint to wake the container
 * from cold sleep. Called on page load so that by the time the user
 * sends their first message, the Modal instance is already warm.
 *
 * Returns quickly — the frontend doesn't wait on this.
 */
export async function GET(_request: NextRequest) {
  const started = Date.now();

  try {
    const backendUrl = `${BLOOMONE_API_URL}/v1/health`;

    const controller = new AbortController();
    // 30s timeout — Modal cold starts can take up to ~20s
    const timeout = setTimeout(() => controller.abort(), 30_000);

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      signal: controller.signal,
      // Don't cache — we want this to actually hit Modal every time
      cache: "no-store",
    });

    clearTimeout(timeout);

    const elapsed = Date.now() - started;

    if (!response.ok) {
      return new Response(
        JSON.stringify({
          status: "error",
          elapsed_ms: elapsed,
          backend_status: response.status,
        }),
        { status: 502, headers: { "Content-Type": "application/json" } },
      );
    }

    const data = await response.json();
    return new Response(
      JSON.stringify({
        status: "warm",
        elapsed_ms: elapsed,
        backend: data,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    const elapsed = Date.now() - started;
    const isTimeout =
      error instanceof DOMException && error.name === "AbortError";

    return new Response(
      JSON.stringify({
        status: isTimeout ? "timeout" : "error",
        elapsed_ms: elapsed,
        message: error instanceof Error ? error.message : "Unknown error",
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }
}
