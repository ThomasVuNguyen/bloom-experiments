import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { createReadStream } from "fs";
import { stat } from "fs/promises";
import { Readable } from "stream";

/**
 * GET /api/files/[id]/download
 *
 * Stream file bytes for download. Used by:
 * 1. The frontend — to let users download their files
 * 2. The Modal backend — to fetch files for pipeline processing
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  const record = await prisma.uploadedFile.findUnique({ where: { id } });
  if (!record) {
    return NextResponse.json({ error: "File not found" }, { status: 404 });
  }

  try {
    const fileStat = await stat(record.blobPath);
    const nodeStream = createReadStream(record.blobPath);
    const webStream = Readable.toWeb(nodeStream) as ReadableStream;

    return new Response(webStream, {
      status: 200,
      headers: {
        "Content-Type": record.mimeType || "application/octet-stream",
        "Content-Length": fileStat.size.toString(),
        "Content-Disposition": `attachment; filename="${record.filename}"`,
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "File blob not found on disk" },
      { status: 404 },
    );
  }
}
