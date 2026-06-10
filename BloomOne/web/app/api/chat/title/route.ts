import { NextRequest, NextResponse } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/chat/title
 *
 * Generates a short chat title.
 *
 * Strategy:
 * 1. Try the Modal backend's /v1/chat/title (uses Vertex AI Gemini Flash Lite)
 * 2. If that fails/times out, fall back to truncating the first user message
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const messages: Array<{ role: string; content: string }> =
    body.messages || [];

  if (!messages.length) {
    return NextResponse.json({ title: "New Chat" });
  }

  // Try Modal backend first
  try {
    console.log("[title] Requesting title from Modal backend...");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20_000);

    const response = await fetch(`${BLOOMONE_API_URL}/v1/chat/title`, {
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

    clearTimeout(timeout);

    if (response.ok) {
      const data = await response.json();
      const title = data.title || "";

      // Check if the backend returned a REAL title (not just the user message)
      const firstUserMsg = messages
        .find((m) => m.role === "user")
        ?.content?.replace(/\[.*?\]\s*/g, "")
        .trim();

      if (title && title !== "New Chat" && title !== firstUserMsg) {
        console.log(`[title] Modal returned AI title: "${title}"`);
        return NextResponse.json({ title });
      }
      console.log(
        `[title] Modal returned echo/fallback: "${title}", generating locally...`,
      );
    } else {
      console.log(
        `[title] Modal returned ${response.status}, generating locally...`,
      );
    }
  } catch (error) {
    const msg = error instanceof Error ? error.message : "unknown";
    console.log(`[title] Modal failed (${msg}), generating locally...`);
  }

  // Local fallback: truncate first user message
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) {
    return NextResponse.json({ title: "New Chat" });
  }

  const text = firstUser.content.replace(/\[.*?\]\s*/g, "").trim();
  const title = text.length > 40 ? text.slice(0, 37) + "..." : text;
  console.log(`[title] Local fallback: "${title}"`);
  return NextResponse.json({ title });
}
