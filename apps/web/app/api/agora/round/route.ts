import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(req: Request) {
  const scope = new URL(req.url).searchParams.get("scope") === "private" ? "private" : "public";
  try {
    const proxied = await proxyJson(`/api/agora/round?scope=${scope}`, { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({ error: "backend_unavailable" }, { status: 503 });
  } catch {
    return NextResponse.json({ error: "backend_unavailable" }, { status: 503 });
  }
}
