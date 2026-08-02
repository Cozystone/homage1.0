import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// Proxy media-read (image OCR via image_b64, or a YouTube/video URL → transcript) to the
// ATANOR backend so the chat composer's file-attach can turn an upload into text it grounds on.
export async function POST(request: Request) {
  const body = await request.text();
  try {
    const proxied = await proxyJson("/api/media/read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "media read proxy failed" },
      { status: 502 },
    );
  }
  return NextResponse.json({ ok: false, error: "media read proxy unavailable" }, { status: 502 });
}
