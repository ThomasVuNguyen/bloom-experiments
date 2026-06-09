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
): Promise<{ id: string; path: string; filename: string; size_bytes: number }> {
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

// ── File Management API ─────────────────────────────────────────────────────

export interface FileRecord {
  id: string;
  filename: string;
  size: number;
  mimeType: string;
  uploadedAt: number;
  status: "uploaded" | "processing" | "completed" | "error";
  tags: string[];
  resultPath?: string;
  blobPath: string;
}

export interface FilesResponse {
  files: FileRecord[];
  stats?: { totalFiles: number; totalSizeBytes: number };
}

/**
 * Fetch all uploaded files, optionally filtered by status.
 */
export async function fetchFiles(
  options?: { status?: FileRecord["status"]; stats?: boolean },
): Promise<FilesResponse> {
  const params = new URLSearchParams();
  if (options?.status) params.set("status", options.status);
  if (options?.stats) params.set("stats", "true");

  const qs = params.toString();
  const response = await fetch(`/api/files${qs ? `?${qs}` : ""}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch files: ${response.status}`);
  }
  return response.json();
}

/**
 * Fetch a single file's metadata.
 */
export async function fetchFile(id: string): Promise<FileRecord> {
  const response = await fetch(`/api/files/${id}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch file: ${response.status}`);
  }
  return response.json();
}

/**
 * Update a file's metadata (status, tags, resultPath).
 */
export async function updateFileRecord(
  id: string,
  updates: Partial<Pick<FileRecord, "status" | "tags" | "resultPath">>,
): Promise<FileRecord> {
  const response = await fetch(`/api/files/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error(`Failed to update file: ${response.status}`);
  }
  return response.json();
}

/**
 * Delete a file and its metadata.
 */
export async function deleteFileRecord(id: string): Promise<void> {
  const response = await fetch(`/api/files/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`Failed to delete file: ${response.status}`);
  }
}

/**
 * Get the download URL for a file.
 */
export function getFileDownloadUrl(id: string): string {
  return `/api/files/${id}/download`;
}

