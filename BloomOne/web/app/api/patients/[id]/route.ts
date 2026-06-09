import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * GET /api/patients/[id] — Get full patient details with all relations
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const patient = await prisma.patient.findUnique({
      where: { id },
      include: {
        files: { orderBy: { createdAt: "desc" } },
        notes: { orderBy: { createdAt: "desc" } },
        runs: { orderBy: { startedAt: "desc" } },
      },
    });

    if (!patient) {
      return NextResponse.json({ error: "Patient not found" }, { status: 404 });
    }

    return NextResponse.json(patient);
  } catch (error) {
    console.error("Get patient error:", error);
    return NextResponse.json(
      { error: "Failed to get patient" },
      { status: 500 },
    );
  }
}

/**
 * PATCH /api/patients/[id] — Update patient metadata
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const body = await req.json();
    const updates: Record<string, unknown> = {};

    if (body.name) updates.name = body.name;
    if (body.dob !== undefined) updates.dob = body.dob ? new Date(body.dob) : null;
    if (body.hlaAlleles !== undefined) updates.hlaAlleles = body.hlaAlleles;

    // Merge details with existing
    if (body.details) {
      const existing = await prisma.patient.findUnique({
        where: { id },
        select: { details: true },
      });
      const existingDetails =
        existing?.details && typeof existing.details === "object"
          ? existing.details
          : {};
      updates.details = { ...(existingDetails as Record<string, unknown>), ...body.details };
    }

    const patient = await prisma.patient.update({
      where: { id },
      data: updates,
    });

    return NextResponse.json(patient);
  } catch (error) {
    console.error("Update patient error:", error);
    return NextResponse.json(
      { error: "Failed to update patient" },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/patients/[id] — Delete patient (cascades to files, notes, runs)
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    await prisma.patient.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Delete patient error:", error);
    return NextResponse.json(
      { error: "Failed to delete patient" },
      { status: 500 },
    );
  }
}
