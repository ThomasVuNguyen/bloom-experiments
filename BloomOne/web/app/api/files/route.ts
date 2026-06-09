import { NextRequest, NextResponse } from "next/server";
import { listFiles, getStorageStats } from "@/lib/storage";
import type { FileRecord } from "@/lib/storage";

/**
 * GET /api/files
 *
 * List all uploaded file records.
 * Optional query params:
 *   ?status=uploaded|processing|completed|error
 *   ?stats=true  (include storage stats in response)
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const statusFilter = searchParams.get("status") as FileRecord["status"] | null;
    const includeStats = searchParams.get("stats") === "true";

    const files = await listFiles(statusFilter || undefined);

    const response: Record<string, unknown> = { files };

    if (includeStats) {
      response.stats = await getStorageStats();
    }

    return NextResponse.json(response);
  } catch (error) {
    console.error("List files error:", error);
    return NextResponse.json(
      { error: "Failed to list files" },
      { status: 500 },
    );
  }
}
