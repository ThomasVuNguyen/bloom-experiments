import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { createReadStream } from "fs";
import { stat } from "fs/promises";
import { Readable } from "stream";

/**
 * GET /api/patients/[id]/files/[fileId]/download
 *
 * Stream file bytes for a PatientFile record.
 * Used by the Modal backend to fetch patient files for multimodal AI analysis.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string; fileId: string }> },
) {
  const { id, fileId } = await params;

  const record = await prisma.patientFile.findFirst({
    where: { id: fileId, patientId: id },
  });

  if (!record) {
    return NextResponse.json(
      { error: "Patient file not found" },
      { status: 404 },
    );
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
