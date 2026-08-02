import { NextRequest, NextResponse } from "next/server";
import { backendBaseCandidates } from "../../_backend";

// Multipart passthrough to the LOCAL engine's Whisper endpoint. Audio goes to
// 127.0.0.1 only — there is no cloud fallback here by design.
export async function POST(req: NextRequest) {
  const body = await req.arrayBuffer();
  const contentType = req.headers.get("content-type") || "application/octet-stream";
  for (const base of backendBaseCandidates()) {
    try {
      const res = await fetch(`${base}/api/voice/transcribe`, {
        method: "POST",
        headers: { "content-type": contentType },
        body,
        signal: AbortSignal.timeout(90_000),
      });
      const json = await res.json().catch(() => ({}));
      return NextResponse.json(json, { status: res.status });
    } catch {
      // try the next local candidate
    }
  }
  return NextResponse.json({ detail: "local engine unreachable" }, { status: 503 });
}
