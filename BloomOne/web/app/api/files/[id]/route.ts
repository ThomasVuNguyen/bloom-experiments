import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * GET /api/files/[id] — Get a single file's metadata
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const record = await prisma.uploadedFile.findUnique({ where: { id } });

    if (!record) {
      return NextResponse.json({ error: "File not found" }, { status: 404 });
    }

    return NextResponse.json(record);
  } catch (error) {
    console.error("Get file error:", error);
    return NextResponse.json(
      { error: "Failed to get file" },
      { status: 500 },
    );
  }
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

    if (body.status) updates.status = body.status;
    if (body.tags) updates.tags = body.tags;
    if (body.resultPath !== undefined) updates.resultPath = body.resultPath;

    const patched = await prisma.uploadedFile.update({
      where: { id },
      data: updates,
    });

    return NextResponse.json(patched);
  } catch (error) {
    console.error("Update file error:", error);
    return NextResponse.json(
      { error: "Failed to update file" },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/files/[id] — Delete file metadata (blob stays on disk)
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    await prisma.uploadedFile.delete({ where: { id } }).catch(() => {
      // Ignore if not found
    });
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Delete file error:", error);
    return NextResponse.json(
      { error: "Failed to delete file" },
      { status: 500 },
    );
  }
}
