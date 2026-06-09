import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/** DELETE /api/chats/[id] — delete a chat session */
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    await prisma.chat.delete({ where: { id } }).catch(() => {
      // Ignore if not found
    });
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

  try {
    const chat = await prisma.chat.findUnique({ where: { id } });

    if (!chat) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    return NextResponse.json(chat);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}
