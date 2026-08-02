import { NextResponse } from "next/server";
import { demoMemoryGraph } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") ?? "600";
  try {
    const proxied = await proxyJson(`/api/memory/graph?limit=${encodeURIComponent(limit)}`);
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoMemoryGraph(Number(limit)));
  } catch {
    return NextResponse.json(demoMemoryGraph(Number(limit)));
  }
}
