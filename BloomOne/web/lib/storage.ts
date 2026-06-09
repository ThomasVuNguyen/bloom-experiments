/**
 * Server-side file storage utility.
 *
 * Manages uploaded files on the local filesystem with JSON metadata,
 * following the same persistence pattern used for chat sessions.
 *
 * File blobs  → /app/data/uploads/{id}/{filename}
 * Metadata    → /app/data/files/{id}.json
 */

import { readdir, readFile, writeFile, mkdir, unlink, rm, stat } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";

// ── Configuration ────────────────────────────────────────────────────────────

const FILES_DIR = process.env.FILES_DIR || "/app/data/files";
const UPLOADS_DIR = process.env.UPLOADS_DIR || "/app/data/uploads";

/** Maximum upload size: 50MB */
export const MAX_UPLOAD_SIZE = 50 * 1024 * 1024;

/** Allowed file extensions */
export const ALLOWED_EXTENSIONS = new Set([
  ".maf", ".vcf", ".tsv", ".csv", ".txt",
]);

// ── Types ────────────────────────────────────────────────────────────────────

export interface FileRecord {
  id: string;
  filename: string;
  size: number;
  mimeType: string;
  uploadedAt: number;
  status: "uploaded" | "processing" | "completed" | "error";
  tags: string[];
  resultPath?: string;
  /** The path within the container where the blob lives */
  blobPath: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `file_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

async function ensureDir(dir: string) {
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
}

function sanitizeFilename(name: string): string {
  // Strip path separators and null bytes, keep the rest
  return name.replace(/[/\\:\0]/g, "_");
}

// ── CRUD Operations ──────────────────────────────────────────────────────────

/**
 * Save an uploaded file and create its metadata record.
 * Returns the newly created FileRecord.
 */
export async function saveFile(
  fileBuffer: Buffer,
  originalFilename: string,
  mimeType: string,
): Promise<FileRecord> {
  const id = generateId();
  const filename = sanitizeFilename(originalFilename);

  // Save blob: /app/data/uploads/{id}/{filename}
  const blobDir = join(UPLOADS_DIR, id);
  await ensureDir(blobDir);
  const blobPath = join(blobDir, filename);
  await writeFile(blobPath, fileBuffer);

  // Create metadata
  const record: FileRecord = {
    id,
    filename,
    size: fileBuffer.length,
    mimeType,
    uploadedAt: Date.now(),
    status: "uploaded",
    tags: detectTags(filename),
    blobPath,
  };

  // Save metadata: /app/data/files/{id}.json
  await ensureDir(FILES_DIR);
  await writeFile(
    join(FILES_DIR, `${id}.json`),
    JSON.stringify(record, null, 2),
    "utf-8",
  );

  return record;
}

/**
 * List all file records, sorted newest first.
 * Optionally filter by status.
 */
export async function listFiles(
  statusFilter?: FileRecord["status"],
): Promise<FileRecord[]> {
  await ensureDir(FILES_DIR);
  const entries = await readdir(FILES_DIR);
  const records: FileRecord[] = [];

  for (const entry of entries) {
    if (!entry.endsWith(".json")) continue;
    try {
      const raw = await readFile(join(FILES_DIR, entry), "utf-8");
      const record: FileRecord = JSON.parse(raw);
      if (!statusFilter || record.status === statusFilter) {
        records.push(record);
      }
    } catch {
      // Skip corrupted files
    }
  }

  records.sort((a, b) => b.uploadedAt - a.uploadedAt);
  return records;
}

/**
 * Get a single file record by ID.
 */
export async function getFile(id: string): Promise<FileRecord | null> {
  const metaPath = join(FILES_DIR, `${id}.json`);
  if (!existsSync(metaPath)) return null;

  try {
    const raw = await readFile(metaPath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Update a file record's metadata (partial update).
 */
export async function updateFile(
  id: string,
  updates: Partial<Pick<FileRecord, "status" | "tags" | "resultPath">>,
): Promise<FileRecord | null> {
  const record = await getFile(id);
  if (!record) return null;

  const patched = { ...record, ...updates };

  await writeFile(
    join(FILES_DIR, `${id}.json`),
    JSON.stringify(patched, null, 2),
    "utf-8",
  );

  return patched;
}

/**
 * Delete a file record and its blob.
 */
export async function deleteFile(id: string): Promise<boolean> {
  const record = await getFile(id);

  // Delete metadata
  const metaPath = join(FILES_DIR, `${id}.json`);
  if (existsSync(metaPath)) {
    await unlink(metaPath);
  }

  // Delete blob directory
  const blobDir = join(UPLOADS_DIR, id);
  if (existsSync(blobDir)) {
    await rm(blobDir, { recursive: true, force: true });
  }

  return true;
}

/**
 * Get the absolute path to a file's blob for streaming.
 */
export async function getFileBlobPath(id: string): Promise<string | null> {
  const record = await getFile(id);
  if (!record) return null;

  if (!existsSync(record.blobPath)) return null;
  return record.blobPath;
}

/**
 * Get storage stats (total files, total size).
 */
export async function getStorageStats(): Promise<{
  totalFiles: number;
  totalSizeBytes: number;
}> {
  const files = await listFiles();
  return {
    totalFiles: files.length,
    totalSizeBytes: files.reduce((sum, f) => sum + f.size, 0),
  };
}

// ── Internal Helpers ─────────────────────────────────────────────────────────

function detectTags(filename: string): string[] {
  const tags: string[] = [];
  const lower = filename.toLowerCase();

  if (lower.endsWith(".maf")) tags.push("maf");
  else if (lower.endsWith(".vcf")) tags.push("vcf");
  else if (lower.endsWith(".tsv")) tags.push("tsv");
  else if (lower.endsWith(".csv")) tags.push("csv");
  else if (lower.endsWith(".txt")) tags.push("txt");

  return tags;
}
