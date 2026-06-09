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

    const response = await fetch(`${BLOOMONE_API_URL}/v1/chat/title`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15_000), // 15s timeout
    });

    if (!response.ok) {
      return NextResponse.json(
        { title: "New Chat" },
        { status: 200 },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    // If title generation fails, return a fallback
    return NextResponse.json({ title: "New Chat" });
  }
}
