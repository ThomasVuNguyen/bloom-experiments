import { NextResponse } from "next/server";
import { readdir, readFile, writeFile, mkdir } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";

const CHATS_DIR = process.env.CHATS_DIR || "/app/data/chats";

async function ensureDir() {
  if (!existsSync(CHATS_DIR)) {
    await mkdir(CHATS_DIR, { recursive: true });
  }
}

/** GET /api/chats — list all chat sessions */
export async function GET() {
  try {
    await ensureDir();
    const files = await readdir(CHATS_DIR);
    const chats = [];

    for (const file of files) {
      if (!file.endsWith(".json")) continue;
      try {
        const raw = await readFile(join(CHATS_DIR, file), "utf-8");
        chats.push(JSON.parse(raw));
      } catch {
        // Skip corrupted files
      }
    }

    // Sort newest first
    chats.sort(
      (a: { updatedAt: number }, b: { updatedAt: number }) =>
        b.updatedAt - a.updatedAt,
    );
    return NextResponse.json(chats);
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}

/** POST /api/chats — create or update a chat session */
export async function POST(req: Request) {
  try {
    await ensureDir();
    const chat = await req.json();

    if (!chat.id) {
      return NextResponse.json({ error: "Missing chat id" }, { status: 400 });
    }

    const filePath = join(CHATS_DIR, `${chat.id}.json`);
    await writeFile(filePath, JSON.stringify(chat, null, 2), "utf-8");

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}
