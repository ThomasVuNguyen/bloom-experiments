import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { extname, join } from "path";
import { writeFile, mkdir } from "fs/promises";
import { randomUUID } from "crypto";

const UPLOADS_DIR = process.env.UPLOADS_DIR || "/app/data/uploads";

const MAX_UPLOAD_SIZE = 100 * 1024 * 1024; // 100MB

const ALLOWED_EXTENSIONS = new Set([
  // Genomic
  ".maf", ".vcf", ".tsv", ".csv", ".txt",
  // Documents
  ".pdf", ".doc", ".docx", ".xlsx", ".xls",
  // Images
  ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
  // Medical
  ".dcm",
]);

/** Detect tags for an uploaded file */
function detectTags(filename: string): string[] {
  const ext = extname(filename).toLowerCase();
  const tags: string[] = [];

  if ([".maf"].includes(ext)) tags.push("maf");
  if ([".vcf"].includes(ext)) tags.push("vcf");
  if ([".maf", ".vcf", ".tsv", ".csv", ".txt"].includes(ext)) tags.push("genomic");
  if ([".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"].includes(ext)) tags.push("image");
  if ([".pdf"].includes(ext)) tags.push("pdf");
  if ([".doc", ".docx", ".xlsx", ".xls"].includes(ext)) tags.push("document");
  if ([".dcm"].includes(ext)) tags.push("dicom");

  return tags;
}

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/upload
 *
 * Saves uploaded files locally to the Coolify persistent volume,
 * stores metadata in PostgreSQL, then optionally mirrors to Modal.
 */
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: "No file provided" },
        { status: 400 },
      );
    }

    // ── Validate file size ────────────────────────────────────────────
    if (file.size > MAX_UPLOAD_SIZE) {
      return NextResponse.json(
        {
          error: `File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max: 100MB.`,
        },
        { status: 413 },
      );
    }

    // ── Validate file extension ───────────────────────────────────────
    const ext = extname(file.name).toLowerCase();
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      return NextResponse.json(
        {
          error: `File type "${ext}" not allowed. Accepted: ${[...ALLOWED_EXTENSIONS].join(", ")}`,
        },
        { status: 415 },
      );
    }

    // ── Save blob to disk ─────────────────────────────────────────────
    const fileId = randomUUID();
    const fileDir = join(UPLOADS_DIR, fileId);
    await mkdir(fileDir, { recursive: true });
    const blobPath = join(fileDir, file.name);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(blobPath, buffer);

    // ── Save metadata to database ─────────────────────────────────────
    const record = await prisma.uploadedFile.create({
      data: {
        id: fileId,
        filename: file.name,
        sizeBytes: file.size,
        mimeType: file.type || "application/octet-stream",
        tags: detectTags(file.name),
        blobPath,
      },
    });

    // ── Mirror to Modal backend (best-effort) ─────────────────────────
    let modalPath = blobPath;
    if (BLOOMONE_API_URL) {
      try {
        const mirrorForm = new FormData();
        mirrorForm.append("file", file);

        const modalResponse = await fetch(`${BLOOMONE_API_URL}/v1/upload`, {
          method: "POST",
          headers: {
            ...(BLOOMONE_API_KEY && {
              Authorization: `Bearer ${BLOOMONE_API_KEY}`,
            }),
          },
          body: mirrorForm,
        });

        if (modalResponse.ok) {
          const modalResult = await modalResponse.json();
          modalPath = modalResult.path;
        } else {
          console.warn(
            `[upload] Modal mirror failed: ${modalResponse.status}`,
          );
        }
      } catch (err) {
        console.warn("[upload] Modal mirror error:", err);
      }
    }

    return NextResponse.json({
      id: record.id,
      path: modalPath,
      filename: record.filename,
      size_bytes: record.sizeBytes,
    });
  } catch (error) {
    console.error("Upload error:", error);
    return NextResponse.json(
      {
        error: "Failed to upload file",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 },
    );
  }
}
