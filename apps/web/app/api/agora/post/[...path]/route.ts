import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

// Moltbook click-through endpoints: GET /api/agora/post/{id} (detail) and
// POST /api/agora/post/{id}/discuss (agents continue the thread). A catch-all so the
// path segments pass straight through to the engine.

async function forward(req: NextRequest, method: "GET" | "POST", path: string[]) {
  const scope = new URL(req.url).searchParams.get("scope") === "private" ? "private" : "public";
  try {
    const proxied = await proxyJson(`/api/agora/post/${path.join("/")}?scope=${scope}`, { method });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({ error: "backend_unavailable" }, { status: 503 });
  } catch {
    return NextResponse.json({ error: "backend_unavailable" }, { status: 503 });
  }
}

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, "GET", (await ctx.params).path);
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(req, "POST", (await ctx.params).path);
}
