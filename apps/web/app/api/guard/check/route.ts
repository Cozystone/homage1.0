import { NextResponse } from "next/server";
import { demoGuardCheck } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  let draft = "GraphRAG uses Evidence.";
  try {
    draft = JSON.parse(body || "{}").draft_answer ?? draft;
    const proxied = await proxyJson("/api/guard/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // Fall through to deterministic demo.
  }
  return NextResponse.json(demoGuardCheck(draft));
}
