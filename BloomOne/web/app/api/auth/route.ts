import { NextResponse } from "next/server";

/**
 * POST /api/auth — validate password server-side.
 * 
 * Passwords are stored in BLOOMONE_PASSWORDS env var as a comma-separated list.
 * Example: BLOOMONE_PASSWORDS=bloom,research2025,demopass
 */
export async function POST(req: Request) {
  try {
    const { password } = await req.json();

    if (!password || typeof password !== "string") {
      return NextResponse.json({ ok: false }, { status: 400 });
    }

    const passwordList = (process.env.BLOOMONE_PASSWORDS || "bloom")
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);

    const valid = passwordList.includes(password.trim());

    return NextResponse.json({ ok: valid }, { status: valid ? 200 : 401 });
  } catch {
    return NextResponse.json({ ok: false }, { status: 500 });
  }
}
