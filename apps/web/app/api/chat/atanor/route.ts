import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  try {
    const proxied = await proxyJson("/api/chat/atanor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch (error) {
    return NextResponse.json(
      {
        state: "error",
        error: error instanceof Error ? error.message : "ATANOR chat proxy failed",
      },
      { status: 502 },
    );
  }
  return NextResponse.json({ state: "error", error: "ATANOR chat proxy unavailable" }, { status: 502 });
}
