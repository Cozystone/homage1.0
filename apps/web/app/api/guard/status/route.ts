import { NextResponse } from "next/server";
import { demoState } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/guard/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoState.guard);
  } catch {
    return NextResponse.json(demoState.guard);
  }
}
