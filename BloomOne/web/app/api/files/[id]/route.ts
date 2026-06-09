import { NextRequest, NextResponse } from "next/server";
import { getFile, updateFile, deleteFile } from "@/lib/storage";

/**
 * GET /api/files/[id] — Get a single file's metadata
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const record = await getFile(id);

  if (!record) {
    return NextResponse.json({ error: "File not found" }, { status: 404 });
  }

  return NextResponse.json(record);
}

/**
 * PATCH /api/files/[id] — Update file metadata (status, tags, resultPath)
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const body = await req.json();
    const updates: Record<string, unknown> = {};

    // Only allow specific fields to be updated
    if (body.status) updates.status = body.status;
    if (body.tags) updates.tags = body.tags;
    if (body.resultPath !== undefined) updates.resultPath = body.resultPath;

    const patched = await updateFile(id, updates);

    if (!patched) {
      return NextResponse.json({ error: "File not found" }, { status: 404 });
    }

    return NextResponse.json(patched);
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to update file",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/files/[id] — Delete file blob and metadata
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    await deleteFile(id);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Failed to delete file",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}
