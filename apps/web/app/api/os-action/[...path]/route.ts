import { NextRequest, NextResponse } from "next/server";
import { backendBaseCandidates } from "../../_backend";

// OS action lane passthrough to the LOCAL engine. The desktop (icons, orb) talks
// to /api/os-action/* on :3000; the lane lives in the engine on 127.0.0.1:8502.
// Local only by design — a desktop action must never leave the machine.
// (Missing proxy = the audit log stays empty while the UI looks alive; the
// desktop-icon e2e caught exactly that.)

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  const suffix = path.join("/");
  const body = method === "POST" ? await req.text() : undefined;
  for (const base of backendBaseCandidates()) {
    try {
      const res = await fetch(`${base}/api/os-action/${suffix}`, {
        method,
        headers: body ? { "content-type": "application/json" } : undefined,
        body,
        signal: AbortSignal.timeout(30_000),
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
