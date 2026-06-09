/**
 * BloomOne API client — proxied through Next.js API routes
 * to keep the Modal API key server-side.
 */

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface StreamEvent {
  type: "status" | "text" | "error" | "done";
  content?: string;
  updated_messages?: ChatMessage[];
}

export interface ModelInfo {
  id: string;
  provider: string;
  display_name: string;
}

export interface ModelsResponse {
  models: ModelInfo[];
  default: string;
}

/**
 * Fetch available models from the backend.
 */
export async function fetchModels(): Promise<ModelsResponse> {
  const response = await fetch("/api/models");
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.status}`);
  }
  return response.json();
}

/**
 * Send a chat message via SSE streaming.
 * Yields StreamEvents as they arrive from the backend.
 */
export async function* streamChat(
  messages: ChatMessage[],
  model?: string,
): AsyncGenerator<StreamEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, ...(model && { model }) }),
  });

  if (!response.ok) {
    const err = await response.text();
    yield { type: "error", content: `API error: ${response.status} — ${err}` };
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    yield { type: "error", content: "No response body" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || !trimmed.startsWith("data: ")) continue;
      const data = trimmed.slice(6);
      if (data === "[DONE]") return;

      try {
        const event: StreamEvent = JSON.parse(data);
        yield event;
      } catch {
        // Skip unparseable lines
      }
    }
  }
}

/**
 * Upload a file to the BloomOne backend via the proxy route.
 */
export async function uploadFile(
  file: File,
): Promise<{ path: string; filename: string; size_bytes: number }> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  return response.json();
}
