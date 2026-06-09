import { NextRequest } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * GET /api/models
 *
 * Proxies model list requests to the Modal backend's /v1/models endpoint.
 */
export async function GET(_request: NextRequest) {
  try {
    const backendUrl = `${BLOOMONE_API_URL}/v1/models`;

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      // Revalidate every 60s — models don't change often
      next: { revalidate: 60 },
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(
        JSON.stringify({ error: `Backend error: ${response.status}`, details: errorText }),
        { status: response.status, headers: { "Content-Type": "application/json" } },
      );
    }

    const data = await response.json();
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    console.error("Models proxy error:", error);
    return new Response(
      JSON.stringify({
        error: "Failed to fetch models from backend",
        details: error instanceof Error ? error.message : "Unknown error",
      }),
      { status: 502, headers: { "Content-Type": "application/json" } },
    );
  }
}
