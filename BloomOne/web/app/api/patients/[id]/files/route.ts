import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { extname } from "path";
import { writeFile, mkdir } from "fs/promises";

const UPLOADS_DIR = process.env.UPLOADS_DIR || "/app/data/uploads";

/** Detect file type category from extension */
function detectFileType(filename: string): string {
  const ext = extname(filename).toLowerCase();
  const imageExts = new Set([".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]);
  const genomicExts = new Set([".maf", ".vcf", ".tsv", ".csv", ".txt"]);
  const docExts = new Set([".doc", ".docx", ".xlsx", ".xls"]);

  if (ext === ".pdf") return "pdf";
  if (ext === ".dcm") return "dicom";
  if (imageExts.has(ext)) return "image";
  if (genomicExts.has(ext)) return "genomic";
  if (docExts.has(ext)) return "document";
  return "document";
}

/**
 * GET /api/patients/[id]/files — List patient's files
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const files = await prisma.patientFile.findMany({
      where: { patientId: id },
      orderBy: { createdAt: "desc" },
    });

    return NextResponse.json({ files });
  } catch (error) {
    console.error("List patient files error:", error);
    return NextResponse.json(
      { error: "Failed to list patient files" },
      { status: 500 },
    );
  }
}

/**
 * POST /api/patients/[id]/files — Attach a file to a patient
 *
 * Accepts either:
 * 1. JSON body with { fileId } to link an existing UploadedFile
 * 2. Multipart form upload to upload + attach in one step
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const contentType = req.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      // Link existing UploadedFile to patient
      const body = await req.json();
      const { fileId, notes } = body;

      if (!fileId) {
        return NextResponse.json(
          { error: "fileId is required" },
          { status: 400 },
        );
      }

      // Look up the uploaded file
      const uploadedFile = await prisma.uploadedFile.findUnique({
        where: { id: fileId },
      });

      if (!uploadedFile) {
        return NextResponse.json(
          { error: "File not found" },
          { status: 404 },
        );
      }

      const patientFile = await prisma.patientFile.create({
        data: {
          patientId: id,
          filename: uploadedFile.filename,
          fileType: detectFileType(uploadedFile.filename),
          mimeType: uploadedFile.mimeType,
          sizeBytes: uploadedFile.sizeBytes,
          blobPath: uploadedFile.blobPath,
          notes: notes || "",
        },
      });

      return NextResponse.json(patientFile, { status: 201 });
    }

    // Multipart upload: upload + attach in one step
    const formData = await req.formData();
    const file = formData.get("file");
    const notes = (formData.get("notes") as string) || "";

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: "No file provided" },
        { status: 400 },
      );
    }

    // Save blob to disk
    const buffer = Buffer.from(await file.arrayBuffer());
    const fileDir = `${UPLOADS_DIR}/${id}`;
    await mkdir(fileDir, { recursive: true });
    const blobPath = `${fileDir}/${file.name}`;
    await writeFile(blobPath, buffer);

    // Create DB record
    const patientFile = await prisma.patientFile.create({
      data: {
        patientId: id,
        filename: file.name,
        fileType: detectFileType(file.name),
        mimeType: file.type || "application/octet-stream",
        sizeBytes: file.size,
        blobPath,
        notes,
      },
    });

    return NextResponse.json(patientFile, { status: 201 });
  } catch (error) {
    console.error("Attach file error:", error);
    return NextResponse.json(
      { error: "Failed to attach file" },
      { status: 500 },
    );
  }
}
