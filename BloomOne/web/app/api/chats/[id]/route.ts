import { NextResponse } from "next/server";
import { readFile, unlink } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";

const CHATS_DIR = process.env.CHATS_DIR || "/app/data/chats";

/** DELETE /api/chats/[id] — delete a chat session */
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const filePath = join(CHATS_DIR, `${id}.json`);

  try {
    if (existsSync(filePath)) {
      await unlink(filePath);
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}

/** GET /api/chats/[id] — get a single chat */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const filePath = join(CHATS_DIR, `${id}.json`);

  try {
    if (!existsSync(filePath)) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    const raw = await readFile(filePath, "utf-8");
    return NextResponse.json(JSON.parse(raw));
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}
