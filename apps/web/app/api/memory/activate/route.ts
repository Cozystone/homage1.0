import { NextResponse } from "next/server";
import { demoMemoryActivate } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  let query = "GraphRAG evidence";
  try {
    query = JSON.parse(body || "{}").query ?? query;
  } catch {
    // Use default query.
  }
  try {
    const proxied = await proxyJson("/api/memory/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoMemoryActivate(query));
  } catch {
    return NextResponse.json(demoMemoryActivate(query));
  }
}
