import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * POST /api/patients/[id]/notes — Add a note to a patient
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const body = await req.json();
    const { content, source } = body;

    if (!content || typeof content !== "string") {
      return NextResponse.json(
        { error: "Note content is required" },
        { status: 400 },
      );
    }

    const note = await prisma.patientNote.create({
      data: {
        patientId: id,
        content: content.trim(),
        source: source || "user",
      },
    });

    return NextResponse.json(note, { status: 201 });
  } catch (error) {
    console.error("Add note error:", error);
    return NextResponse.json(
      { error: "Failed to add note" },
      { status: 500 },
    );
  }
}
