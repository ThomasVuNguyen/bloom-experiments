import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/** GET /api/chats — list all chat sessions */
export async function GET() {
  try {
    const chats = await prisma.chat.findMany({
      orderBy: { updatedAt: "desc" },
    });

    return NextResponse.json(chats);
  } catch (error) {
    console.error("List chats error:", error);
    return NextResponse.json([], { status: 200 });
  }
}

/** POST /api/chats — create or update a chat session */
export async function POST(req: Request) {
  try {
    const chat = await req.json();

    if (!chat.id) {
      return NextResponse.json({ error: "Missing chat id" }, { status: 400 });
    }

    await prisma.chat.upsert({
      where: { id: chat.id },
      update: {
        title: chat.title || "New Chat",
        customTitle: chat.customTitle || false,
        messages: chat.messages || [],
        updatedAt: new Date(),
      },
      create: {
        id: chat.id,
        title: chat.title || "New Chat",
        customTitle: chat.customTitle || false,
        messages: chat.messages || [],
      },
    });

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}
