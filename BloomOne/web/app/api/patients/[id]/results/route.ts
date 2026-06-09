import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * GET /api/patients/[id]/results — List pipeline runs for a patient
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const runs = await prisma.pipelineRun.findMany({
      where: { patientId: id },
      orderBy: { startedAt: "desc" },
    });

    return NextResponse.json({ runs });
  } catch (error) {
    console.error("List results error:", error);
    return NextResponse.json(
      { error: "Failed to list results" },
      { status: 500 },
    );
  }
}

/**
 * POST /api/patients/[id]/results — Save a pipeline run
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  try {
    const body = await req.json();
    const { stagesCompleted, summary, outputPaths, warnings } = body;

    const run = await prisma.pipelineRun.create({
      data: {
        patientId: id,
        stagesCompleted: stagesCompleted || [],
        summary: summary || "",
        outputPaths: outputPaths || {},
        warnings: warnings || [],
        completedAt: new Date(),
      },
    });

    return NextResponse.json(run, { status: 201 });
  } catch (error) {
    console.error("Add result error:", error);
    return NextResponse.json(
      { error: "Failed to add result" },
      { status: 500 },
    );
  }
}
