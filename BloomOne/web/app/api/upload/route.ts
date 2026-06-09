import { NextRequest, NextResponse } from "next/server";
import {
  saveFile,
  MAX_UPLOAD_SIZE,
  ALLOWED_EXTENSIONS,
} from "@/lib/storage";
import { extname } from "path";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/upload
 *
 * Saves uploaded files locally to the Coolify persistent volume,
 * then optionally mirrors to the Modal backend for pipeline access.
 *
 * Response shape matches the previous Modal-only upload:
 *   { id, path, filename, size_bytes }
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
          error: `File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max: 50MB.`,
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

    // ── Save locally ──────────────────────────────────────────────────
    const buffer = Buffer.from(await file.arrayBuffer());
    const record = await saveFile(buffer, file.name, file.type || "application/octet-stream");

    // ── Mirror to Modal backend (best-effort) ─────────────────────────
    // This keeps the Modal volume in sync so the pipeline can still
    // access files directly. If it fails, the pipeline can fall back
    // to fetching from Coolify via GET /api/files/:id/download.
    let modalPath = record.blobPath; // default to local path
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
          modalPath = modalResult.path; // e.g., /data/uploads/filename.maf
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
      size_bytes: record.size,
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
