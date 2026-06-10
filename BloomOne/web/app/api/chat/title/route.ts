import { NextRequest, NextResponse } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/chat/title
 *
 * Proxies title-generation requests to the Modal backend.
 * Uses Gemini 2.5 Flash Lite for fast, cheap title generation.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    console.log("[title] Requesting title generation from backend...");

    const response = await fetch(`${BLOOMONE_API_URL}/v1/chat/title`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      body: JSON.stringify(body),
      // Modal cold starts can take 20s+, give it 45s
      signal: AbortSignal.timeout(45_000),
    });

    if (!response.ok) {
      const errText = await response.text().catch(() => "unknown");
      console.error(
        `[title] Backend returned ${response.status}: ${errText}`,
      );
      return NextResponse.json({ title: "New Chat" }, { status: 200 });
    }

    const data = await response.json();
    console.log(`[title] Generated: "${data.title}"`);
    return NextResponse.json(data);
  } catch (error) {
    const msg =
      error instanceof Error ? error.message : "Unknown error";
    console.error(`[title] Failed: ${msg}`);
    // If title generation fails, return a fallback
    return NextResponse.json({ title: "New Chat" });
  }
}
