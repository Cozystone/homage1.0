import { NextResponse } from "next/server";
import { backendBaseUrl } from "../../../_backend";

const AUDIO_NAME_RE = /^atanor_voice_[a-f0-9]{32}\.wav$/;

export async function GET(_request: Request, context: { params: Promise<{ filename: string }> }) {
  const { filename } = await context.params;
  if (!AUDIO_NAME_RE.test(filename)) {
    return NextResponse.json({ error: "voice audio not found" }, { status: 404 });
  }

  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return NextResponse.json({ error: "voice backend unavailable" }, { status: 502 });
  }

  const response = await fetch(`${baseUrl}/api/voice-loop/audio/${encodeURIComponent(filename)}`, {
    cache: "no-store",
  });
  if (!response.ok || !response.body) {
    return NextResponse.json({ error: "voice audio not found" }, { status: response.status || 502 });
  }

  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "audio/wav",
      "cache-control": "no-store",
    },
  });
}
