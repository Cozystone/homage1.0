import { NextRequest, NextResponse } from "next/server";
import { backendBaseCandidates } from "../../_backend";

// Imagination passthrough to the LOCAL engine (127.0.0.1 only): the /imagination scene renderer
// posts a query and gets back a graph-grounded SPLATRA scene spec to animate.

async function forward(req: NextRequest, path: string[], method: "GET" | "POST") {
  const suffix = path.join("/");
  const body = method === "POST" ? await req.text() : undefined;
  for (const base of backendBaseCandidates()) {
    try {
      const res = await fetch(`${base}/api/imagination/${suffix}`, {
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
