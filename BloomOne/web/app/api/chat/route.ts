import { NextRequest } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/** Timeout for the initial connection to Modal (handles cold starts). */
const CONNECT_TIMEOUT_MS = 120_000; // 2 minutes

/** How often to send SSE heartbeat comments while waiting for Modal. */
const HEARTBEAT_INTERVAL_MS = 3_000;

/**
 * POST /api/chat
 *
 * Proxies chat requests to the Modal backend's /v1/chat/stream SSE endpoint.
 * Sends heartbeat SSE comments during Modal cold starts to keep the
 * browser connection alive and show immediate feedback.
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const backendUrl = `${BLOOMONE_API_URL}/v1/chat/stream`;

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();

      // Helper: send an SSE event
      const sendEvent = (data: string) => {
        controller.enqueue(encoder.encode(`data: ${data}\n\n`));
      };

      // Immediately tell the frontend we're connecting
      sendEvent(
        JSON.stringify({
          type: "status",
          content: "⏳ Connecting to server...",
        }),
      );

      // Start heartbeat to keep connection alive during cold boot
      let heartbeatCount = 0;
      const heartbeat = setInterval(() => {
        heartbeatCount++;
        try {
          // SSE comment (colon prefix) — keeps connection alive,
          // ignored by SSE parsers but prevents timeout
          controller.enqueue(encoder.encode(": heartbeat\n\n"));

          // After 5s, send a visible status update
          if (heartbeatCount === 2) {
            sendEvent(
              JSON.stringify({
                type: "status",
                content: "⏳ Server is warming up...",
              }),
            );
          }
        } catch {
          clearInterval(heartbeat);
        }
      }, HEARTBEAT_INTERVAL_MS);

      try {
        const abortController = new AbortController();
        const timeout = setTimeout(
          () => abortController.abort(),
          CONNECT_TIMEOUT_MS,
        );

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
            signal: abortController.signal,
          });
        } finally {
          clearTimeout(timeout);
          clearInterval(heartbeat);
        }

        if (!response.ok) {
          const errorText = await response.text();
          sendEvent(
            JSON.stringify({
              type: "error",
              content: `Backend error: ${response.status} — ${errorText}`,
            }),
          );
          controller.close();
          return;
        }

        // Pipe the backend SSE stream through to the browser
        const reader = response.body?.getReader();
        if (!reader) {
          sendEvent(
            JSON.stringify({
              type: "error",
              content: "No response body from backend",
            }),
          );
          controller.close();
          return;
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }

        controller.close();
      } catch (error) {
        clearInterval(heartbeat);

        const isTimeout =
          error instanceof DOMException && error.name === "AbortError";
        const message = isTimeout
          ? "Server is starting up — please try again in a few seconds"
          : `Connection error: ${error instanceof Error ? error.message : "Unknown error"}`;

        try {
          sendEvent(JSON.stringify({ type: "error", content: message }));
          controller.close();
        } catch {
          // Controller may already be closed
        }
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
