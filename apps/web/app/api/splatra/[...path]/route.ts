import { NextResponse } from "next/server";

// SPLATRA particle-engine bridge: the dashboard talks to the local 3DGS
// generation/rig engine (26.SPLATRA plugin_api) through this proxy, so chat
// and voice can build / rig / melt / crumble particle models without ever
// leaving the ATANOR app. Local companion only — never deployed remote.
function splatraBase() {
  return process.env.SPLATRA_BASE || "http://127.0.0.1:8010";
}

async function forward(req: Request, path: string[], method: "GET" | "POST") {
  const url = `${splatraBase()}/${path.join("/")}${new URL(req.url).search}`;
  try {
    const init: RequestInit = { method, cache: "no-store" };
    if (method === "POST") {
      init.headers = { "Content-Type": "application/json" };
      init.body = await req.text();
    }
    const res = await fetch(url, init);
    const type = res.headers.get("content-type") ?? "application/json";
    if (type.includes("octet-stream")) {
      return new NextResponse(await res.arrayBuffer(), {
        status: res.status,
        headers: { "Content-Type": type, "Cache-Control": "no-store" },
      });
    }
    return new NextResponse(await res.text(), {
      status: res.status,
      headers: { "Content-Type": type },
    });
  } catch {
    return NextResponse.json(
      { ok: false, error: "SPLATRA engine offline (start: python -m uvicorn apps.plugin_api:app --port 8010)" },
      { status: 503 },
    );
  }
}

export async function GET(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "GET");
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return forward(req, path, "POST");
}
