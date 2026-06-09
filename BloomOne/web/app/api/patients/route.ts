import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

/**
 * GET /api/patients — List all patients
 * Optional: ?search=name to filter by name
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const search = searchParams.get("search");

    const patients = await prisma.patient.findMany({
      where: search
        ? { name: { contains: search, mode: "insensitive" } }
        : undefined,
      include: {
        _count: {
          select: {
            files: true,
            runs: true,
            notes: true,
          },
        },
      },
      orderBy: { updatedAt: "desc" },
    });

    return NextResponse.json({
      patients: patients.map((p) => ({
        id: p.id,
        name: p.name,
        dob: p.dob,
        details: p.details,
        hlaAlleles: p.hlaAlleles,
        createdAt: p.createdAt,
        updatedAt: p.updatedAt,
        fileCount: p._count.files,
        runCount: p._count.runs,
        noteCount: p._count.notes,
      })),
      total: patients.length,
    });
  } catch (error) {
    console.error("List patients error:", error);
    return NextResponse.json(
      { error: "Failed to list patients" },
      { status: 500 },
    );
  }
}

/**
 * POST /api/patients — Create a new patient
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name, dob, details, hlaAlleles } = body;

    if (!name || typeof name !== "string") {
      return NextResponse.json(
        { error: "Patient name is required" },
        { status: 400 },
      );
    }

    const patient = await prisma.patient.create({
      data: {
        name: name.trim(),
        dob: dob ? new Date(dob) : null,
        details: details || {},
        hlaAlleles: hlaAlleles || [],
      },
    });

    return NextResponse.json(patient, { status: 201 });
  } catch (error) {
    console.error("Create patient error:", error);
    return NextResponse.json(
      { error: "Failed to create patient" },
      { status: 500 },
    );
  }
}
