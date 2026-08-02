import { NextRequest, NextResponse } from "next/server";
import { backendBaseCandidates } from "../../_backend";

// Perception ledger passthrough to the LOCAL engine (127.0.0.1 only): the orb
// and dashboard read interests/status; the OS daemon posts distilled activity.

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  const suffix = path.join("/");
  const body = method === "POST" ? await req.text() : undefined;
  for (const base of backendBaseCandidates()) {
    try {
      const res = await fetch(`${base}/api/perception/${suffix}`, {
        method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body,
        signal: AbortSignal.timeout(20_000),
      });
      const json = await res.json().catch(() => ({}));
      return NextResponse.json(json, { status: res.status });
    } catch {
      // try the next local candidate
    }
  }
  return NextResponse.json({ detail: "local engine unreachable" }, { status: 503 });
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "GET");
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "POST");
}
