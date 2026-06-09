import { NextRequest, NextResponse } from "next/server";

const BLOOMONE_API_URL = process.env.BLOOMONE_API_URL || "";
const BLOOMONE_API_KEY = process.env.BLOOMONE_API_KEY || "";

/**
 * POST /api/upload
 *
 * Proxies file uploads to the Modal backend's /v1/upload endpoint.
 */
export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();

    const backendUrl = `${BLOOMONE_API_URL}/v1/upload`;

    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        ...(BLOOMONE_API_KEY && {
          Authorization: `Bearer ${BLOOMONE_API_KEY}`,
        }),
      },
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Upload failed: ${response.status}`, details: errorText },
        { status: response.status },
      );
    }

    const result = await response.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Upload proxy error:", error);
    return NextResponse.json(
      {
        error: "Failed to upload file",
        details: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 },
    );
  }
}
